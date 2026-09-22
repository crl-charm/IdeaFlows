import pytest
import json
from decimal import Decimal
from datetime import datetime, UTC

from app import create_app, db
from app.models import Admin, CustomerSession, MenuItem, MenuItemIngredient, Order, SpaceType, User
from app.models.inventory import InventoryItem
from app.db.migrator import SchemaMigrator
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
from app.services.menu_service import MenuService
from app.repositories.menu_repository import MenuRepository
from app.core import get_notifier
from app.utils.inventory_helpers import is_ingredient_category, units_are_compatible


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with application.app_context():
        db.create_all()
        SchemaMigrator(db, application).run()
        if not SpaceType.query.get(1):
            db.session.add(
                SpaceType(id=1, name="Regular Lounge", capacity=10, rate_per_minute=Decimal("1.50"))
            )
            db.session.commit()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _set_auth_session(client, role: str = "staff", user_id: int = 1):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = f"test_{role}"
        sess["role"] = role
        sess["last_activity"] = datetime.now(UTC).timestamp()


def test_menu_setup_and_inventory_dashboard_share_availability(app):
    with app.app_context():
        service = MenuService(MenuRepository())
        prepared_id = service.create("Batch Meal", 80, "Main Dish", inventory_mode="prepared",
                                     stock_quantity=6, stock_threshold=2)["data"]["id"]
        untracked_id = service.create("Uncounted Service", 20, "Main Dish")["data"]["id"]
        rows = {row["id"]: row for row in InventoryService(InventoryRepository()).build_dashboard_snapshot()["data"]}
        assert rows[prepared_id]["availability_message"] == "6 servings left"
        assert rows[untracked_id]["availability_message"] == "Available"
        assert rows[untracked_id]["can_order"] is True
        assert InventoryItem.query.filter_by(menu_item_id=prepared_id).one().stock_qty == 6


def test_menu_create_mode_and_stock_are_atomic(app, client):
    from app.models.menu_category import MenuCategory
    with app.app_context():
        owner = User(full_name="Owner Test", username="owner_menu_setup", role="admin",
                     job_role="admin", is_active=True, password="not-used")
        db.session.add_all([owner, MenuCategory(name="Main Dish")])
        db.session.commit()
        owner_id = owner.id
    _set_auth_session(client, "admin", owner_id)
    good = client.post("/admin/menu/api/items", data={"name": "Owner Meal", "category": "Main Dish",
        "price": "80", "inventory_mode": "prepared", "stock_quantity": "5", "stock_threshold": "2"})
    bad = client.post("/admin/menu/api/items", data={"name": "Bad Count Meal", "category": "Main Dish",
        "price": "80", "inventory_mode": "prepared", "stock_quantity": "1.5"})
    assert good.status_code == 201, good.get_json()
    assert bad.status_code == 400
    changed = client.patch(f"/admin/menu/api/items/{good.get_json()['data']['id']}", data={
        "inventory_mode": "direct", "stock_quantity": "3", "stock_threshold": "1"})
    assert changed.status_code == 200, changed.get_json()
    with app.app_context():
        good_item = MenuItem.query.filter_by(name="Owner Meal").one()
        assert good_item.inventory_mode == "direct"
        stock = InventoryItem.query.filter_by(menu_item_id=good_item.id).one()
        assert (stock.stock_qty, stock.unit) == (3, "pieces")
        assert MenuItem.query.filter_by(name="Bad Count Meal").first() is None


def test_typed_menu_recipe_creates_shared_raw_stock_and_deducts_orders(app, client):
    from app.models.menu_category import MenuCategory
    from app.services.menu_availability import MenuAvailability
    with app.app_context():
        owner = User(full_name="Recipe Owner", username="recipe_owner", role="admin",
                     job_role="admin", is_active=True, password="not-used")
        db.session.add_all([owner, MenuCategory(name="Main Dish")])
        db.session.commit()
        owner_id = owner.id
    _set_auth_session(client, "admin", owner_id)
    menu_page = client.get("/admin/menu")
    assert menu_page.status_code == 200
    assert menu_page.get_data(as_text=True).count("+ Add Ingredient") == 2
    ingredients = [
        {"name": "Corned beef", "quantity": "30", "unit": "grams"},
        {"name": "Egg", "quantity": "1", "unit": "pieces"},
        {"name": "Rice", "quantity": "30", "unit": "grams"},
        {"name": "Cucumber slices", "quantity": "3", "unit": "pieces"},
        {"name": "Salt", "quantity": "1", "unit": "grams"},
        {"name": "Pepper", "quantity": "1", "unit": "grams"},
    ]
    created = client.post("/admin/menu/api/items", data={"name": "Corned Beef Silog",
        "price": "120", "category": "Main Dish", "recipe_ingredients": json.dumps(ingredients)})
    assert created.status_code == 201, created.get_json()
    meal_id = created.get_json()["data"]["id"]
    with app.app_context():
        meal = db.session.get(MenuItem, meal_id)
        assert meal.inventory_mode == "recipe" and len(meal.ingredients) == 6
        assert MenuAvailability([meal_id]).snapshot(meal)["can_order"] is False
        stock = {row.menu_item.name: row for row in InventoryItem.query.all()}
        stock_ids = {name: row.id for name, row in stock.items()}
        rice_menu_id = stock["Rice"].menu_item_id
        assert all(row.stock_qty == 0 for row in stock.values())
        for name, amount in {"Corned beef": 120, "Egg": 24, "Rice": 120,
                             "Cucumber slices": 30, "Salt": 99, "Pepper": 99}.items():
            stock[name].stock_qty = amount
        customer = CustomerSession(customer_name="Recipe test", space_type_id=1,
                                   number_of_people=1, status="active")
        db.session.add(customer)
        db.session.commit()
        customer_id = customer.id
        assert MenuAvailability([meal_id]).snapshot(meal)["available_quantity"] == 4
        placed = OrderService(OrderRepository(), get_notifier()).add_order(
            session_id=customer_id, items=[{"menu_item_id": meal_id, "quantity": 1}], handled_by=owner_id)
        assert not isinstance(placed, tuple), placed
        assert {name: InventoryItem.query.filter_by(id=row.id).one().stock_qty for name, row in stock.items()} == {
            "Corned beef": 90, "Egg": 23, "Rice": 90, "Cucumber slices": 27, "Salt": 98, "Pepper": 98}
        assert MenuAvailability([meal_id]).snapshot(meal)["available_quantity"] == 3
        before_orders = Order.query.count()
        too_many = OrderService(OrderRepository(), get_notifier()).add_order(
            session_id=customer_id, items=[{"menu_item_id": meal_id, "quantity": 4}], handled_by=owner_id)
        assert isinstance(too_many, tuple) and too_many[1] == 409
        assert "Corned beef" in too_many[0]["message"]
        assert Order.query.count() == before_orders
        assert InventoryItem.query.filter_by(id=stock["Rice"].id).one().stock_qty == 90
    shared = client.post("/admin/menu/api/items", data={"name": "Rice Plate", "price": "80",
        "category": "Main Dish", "recipe_ingredients": json.dumps([
            {"name": " rice ", "quantity": "30", "unit": "grams"}])})
    assert shared.status_code == 201, shared.get_json()
    ingredients[0]["quantity"] = "40"
    edited = client.patch(f"/admin/menu/api/items/{meal_id}", data={
        "recipe_ingredients": json.dumps(ingredients)})
    assert edited.status_code == 200, edited.get_json()
    with app.app_context():
        from app.models.inventory import OrderInventoryAllocation
        assert MenuItem.query.filter(db.func.lower(MenuItem.name) == "rice").count() == 1
        second = db.session.get(MenuItem, shared.get_json()["data"]["id"])
        assert second.ingredients[0].ingredient_item_id == rice_menu_id
        assert MenuAvailability([second.id]).snapshot(second)["available_quantity"] == 3
        assert MenuAvailability([meal_id]).snapshot(db.session.get(MenuItem, meal_id))["available_quantity"] == 2
        order_item = db.session.get(Order, placed["order_id"]).items[0]
        old_corn_beef = OrderInventoryAllocation.query.filter_by(
            order_item_id=order_item.id, inventory_item_id=stock_ids["Corned beef"]).one()
        assert old_corn_beef.quantity_deducted == 30
        service = OrderService(OrderRepository(), get_notifier())
        returned = service.void_item(order_item.id, request_key="typed-recipe-void")
        repeated = service.void_item(order_item.id, request_key="typed-recipe-void")
        assert returned["message"].endswith("Stock returned.") and repeated["duplicate"] is True
        assert InventoryItem.query.filter_by(id=stock_ids["Rice"]).one().stock_qty == 120
        assert InventoryItem.query.filter_by(id=stock_ids["Corned beef"]).one().stock_qty == 120


def test_typed_recipe_edit_and_invalid_save_are_atomic(app, client):
    from app.models.menu_category import MenuCategory
    with app.app_context():
        owner = User(full_name="Edit Recipe Owner", username="edit_recipe_owner", role="admin",
                     job_role="admin", is_active=True, password="not-used")
        db.session.add_all([owner, MenuCategory(name="Main Dish")])
        db.session.commit()
        owner_id = owner.id
    _set_auth_session(client, "admin", owner_id)
    failed_create = client.post("/admin/menu/api/items", data={"name": "Incomplete Recipe",
        "price": "90", "category": "Main Dish", "recipe_ingredients": json.dumps([
            {"name": "Unused flour", "quantity": "30", "unit": "grams"},
            {"name": "Bad portion", "quantity": "-1", "unit": "grams"}])})
    assert failed_create.status_code == 400
    with app.app_context():
        assert MenuItem.query.filter_by(name="Incomplete Recipe").first() is None
        assert MenuItem.query.filter_by(name="Unused flour").first() is None
    first = client.post("/admin/menu/api/items", data={"name": "Edit Meal", "price": "90",
        "category": "Main Dish", "recipe_ingredients": json.dumps([
            {"name": "Rice", "quantity": "30", "unit": "grams"}])})
    assert first.status_code == 201, first.get_json()
    meal_id = first.get_json()["data"]["id"]
    bad = client.patch(f"/admin/menu/api/items/{meal_id}", data={"price": "100",
        "recipe_ingredients": json.dumps([{"name": "Rices", "quantity": "40", "unit": "grams"}])})
    assert bad.status_code == 400
    with app.app_context():
        meal = db.session.get(MenuItem, meal_id)
        assert meal.price == 90 and meal.ingredients[0].quantity_required == 30
        assert MenuItem.query.filter_by(name="Rices").first() is None
    good = client.patch(f"/admin/menu/api/items/{meal_id}", data={"price": "100",
        "recipe_ingredients": json.dumps([{"name": "Rice", "quantity": "40", "unit": "grams"}])})
    assert good.status_code == 200, good.get_json()
    with app.app_context():
        meal = db.session.get(MenuItem, meal_id)
        assert meal.price == 100 and meal.ingredients[0].quantity_required == 40
        assert InventoryItem.query.filter_by(menu_item_id=meal.ingredients[0].ingredient_item_id).one().stock_qty == 0


def test_typed_recipe_switch_requires_confirmation_and_keeps_old_count(app, client):
    from app.models.menu_category import MenuCategory
    from app.services.menu_availability import MenuAvailability
    with app.app_context():
        owner = User(full_name="Switch Owner", username="switch_recipe_owner", role="admin",
                     job_role="admin", is_active=True, password="not-used")
        db.session.add_all([owner, MenuCategory(name="Main Dish")])
        db.session.commit()
        owner_id = owner.id
        meal_id = MenuService(MenuRepository()).create("Prepared to Recipe", 90, "Main Dish",
            inventory_mode="prepared", stock_quantity=5)["data"]["id"]
    _set_auth_session(client, "admin", owner_id)
    data = {"recipe_ingredients": json.dumps([{"name": "Egg", "quantity": "1", "unit": "pieces"}])}
    refused = client.patch(f"/admin/menu/api/items/{meal_id}", data=data)
    assert refused.status_code == 400
    accepted = client.patch(f"/admin/menu/api/items/{meal_id}", data={**data, "confirm_recipe_switch": "true"})
    assert accepted.status_code == 200, accepted.get_json()
    with app.app_context():
        meal = db.session.get(MenuItem, meal_id)
        assert meal.inventory_mode == "recipe"
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 5
        assert MenuAvailability([meal_id]).snapshot(meal)["available_quantity"] == 0
    removed = client.patch(f"/admin/menu/api/items/{meal_id}", data={"recipe_ingredients": "[]"})
    assert removed.status_code == 200, removed.get_json()
    with app.app_context():
        meal = db.session.get(MenuItem, meal_id)
        assert meal.inventory_mode == "untracked" and not meal.ingredients
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 5


def test_typed_recipe_converts_grams_to_existing_kilogram_stock(app):
    from app.services.menu_availability import MenuAvailability
    with app.app_context():
        rice = MenuItem(name="Rice", price=0, category="ingredient", is_available=True)
        db.session.add(rice)
        db.session.flush()
        db.session.add(InventoryItem(menu_item_id=rice.id, stock_qty=Decimal("4.00"), unit="klg"))
        db.session.commit()
        meal_id = MenuService(MenuRepository()).create("Rice Serving", 80, "Main Dish",
            recipe_ingredients=[{"name": "rice", "quantity": "30", "unit": "grams"}])["data"]["id"]
        meal = db.session.get(MenuItem, meal_id)
        assert meal.ingredients[0].ingredient_item_id == rice.id
        assert meal.ingredients[0].conversion_ratio == Decimal("0.0010")
        assert MenuAvailability([meal_id]).snapshot(meal)["available_quantity"] == 133


def test_prepared_void_returns_one_serving_once(app):
    from app.models.inventory import OrderInventoryAllocation

    with app.app_context():
        menu_id = MenuService(MenuRepository()).create("Void Meal", 80, "Main Dish",
            inventory_mode="prepared", stock_quantity=2)["data"]["id"]
        customer = CustomerSession(customer_name="Void test", space_type_id=1, number_of_people=1, status="active")
        db.session.add(customer)
        db.session.commit()
        service = OrderService(OrderRepository(), get_notifier())
        placed = service.add_order(session_id=customer.id, items=[{"menu_item_id": menu_id, "quantity": 2}], handled_by=None)
        assert not isinstance(placed, tuple)
        item = Order.query.get(placed["order_id"]).items[0]
        first = service.void_item(item.id, request_key="void-one-serving")
        duplicate = service.void_item(item.id, request_key="void-one-serving")
        assert first["message"].endswith("Stock returned.")
        assert duplicate["duplicate"] is True
        assert InventoryItem.query.filter_by(menu_item_id=menu_id).one().stock_qty == 1
        assert OrderInventoryAllocation.query.filter_by(order_item_id=item.id).one().quantity_restored == 1


def test_prepared_summary_reports_batches_orders_and_waste(app, client):
    from app.services.stock_management import change_stock

    with app.app_context():
        cook = User(full_name="Kitchen Test", username="kitchen_summary", role="staff", job_role="cook", is_active=True, password="not-used")
        db.session.add(cook)
        db.session.commit()
        menu_id = MenuService(MenuRepository()).create("Summary Meal", 80, "Main Dish",
            inventory_mode="prepared", stock_quantity=2)["data"]["id"]
        customer = CustomerSession(customer_name="Summary test", space_type_id=1, number_of_people=1, status="active")
        db.session.add(customer)
        db.session.commit()
        placed = OrderService(OrderRepository(), get_notifier()).add_order(
            session_id=customer.id, items=[{"menu_item_id": menu_id, "quantity": 2}], handled_by=None)
        assert not isinstance(placed, tuple)
        change_stock(menu_id, {"action": "add", "quantity": 3}, cook.id, "summary-batch-one")
        change_stock(menu_id, {"action": "waste", "quantity": 1, "reason": "Dropped"}, cook.id, "summary-waste-one")
        cook_id = cook.id
    _set_auth_session(client, "staff", cook_id)
    response = client.get("/inventory/api/prepared-summary")
    last_batch = client.get(f"/inventory/api/menu-items/{menu_id}/last-batch")
    assert response.status_code == 200
    assert last_batch.get_json()["quantity"] == 3
    row = next(row for row in response.get_json()["data"] if row["name"] == "Summary Meal")
    assert (row["prepared"], row["ordered"], row["wasted"], row["remaining"]) == (3, 2, 1, 2)


def test_stock_event_contains_affected_availability(app, monkeypatch):
    from app.core.socketio_handlers import emit_inventory_update
    with app.app_context():
        menu_id = MenuService(MenuRepository()).create("Event Meal", 80, "Main Dish",
            inventory_mode="prepared", stock_quantity=4)["data"]["id"]
        stock_id = InventoryItem.query.filter_by(menu_item_id=menu_id).one().id
        sent = []
        monkeypatch.setattr("app.core.socketio_handlers.socketio.emit", lambda name, payload, **kwargs: sent.append((name, payload)))
        emit_inventory_update("stock_change", {"item_id": stock_id})
        assert len(sent) == 1
        assert sent[0][0] == "inventory_update"
        assert sent[0][1]["availability"][str(menu_id)]["available_quantity"] == 4


def test_inventory_upgrade_adds_audit_columns_to_existing_table():
    from sqlalchemy import create_engine, inspect, text
    from app.db.inventory_upgrade import upgrade
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE menu_items (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE order_inventory_allocations (id INTEGER PRIMARY KEY, order_id INTEGER)"))
    upgrade(engine)
    upgrade(engine)
    assert {"menu_item_id", "ordered_units", "updated_at"}.issubset(
        {column["name"] for column in inspect(engine).get_columns("order_inventory_allocations")})


class TestIngredientCategoryHelper:
    @pytest.mark.parametrize(
        "category,expected",
        [
            ("ingredient", True),
            ("Ingredient", True),
            ("INGREDIENT", True),
            (" ingredient ", True),
            ("Main Dish", False),
            ("", False),
            (None, False),
        ],
    )
    def test_is_ingredient_category(self, category, expected):
        assert is_ingredient_category(category) is expected


class TestUnitCompatibility:
    def test_same_units_compatible(self):
        assert units_are_compatible("pieces", "pcs") is True

    def test_legacy_null_recipe_unit(self):
        assert units_are_compatible(None, "cups", 1.0) is True

    def test_explicit_conversion_ratio_allows_mismatch(self):
        assert units_are_compatible("pieces", "klg", 0.25) is True

    def test_mismatch_without_conversion_rule(self):
        assert units_are_compatible("pieces", "klg", 1.0) is False


class TestStockStatus:
    def test_low_stock_excludes_zero(self):
        status = InventoryService.compute_stock_status(0, 5)
        assert status["is_out_of_stock"] is True
        assert status["is_low"] is False

    def test_low_stock_at_threshold(self):
        status = InventoryService.compute_stock_status(2, 5)
        assert status["is_low"] is True
        assert status["is_out_of_stock"] is False

    def test_normal_stock_above_threshold(self):
        status = InventoryService.compute_stock_status(10, 5)
        assert status["is_low"] is False
        assert status["is_out_of_stock"] is False


class TestRecipeCapacity:
    def _setup_meal_with_ingredient(self, stock_qty="10.00", threshold=5):
        meal = MenuItem(name="Test Meal", price=Decimal("100"), category="Main", is_available=True)
        ing = MenuItem(name="Test Ing", price=Decimal("0"), category="Ingredient", is_available=True)
        db.session.add_all([meal, ing])
        db.session.flush()
        db.session.add(
            MenuItemIngredient(
                menu_item_id=meal.id,
                ingredient_item_id=ing.id,
                quantity_required=Decimal("2.00"),
                unit="pieces",
                conversion_ratio=Decimal("1.0000"),
            )
        )
        db.session.add(
            InventoryItem(
                menu_item_id=ing.id,
                stock_qty=Decimal(stock_qty),
                unit="pieces",
                low_stock_threshold=threshold,
            )
        )
        db.session.commit()
        return meal, ing

    def test_positive_capacity_available(self, app):
        with app.app_context():
            meal, _ = self._setup_meal_with_ingredient()
            service = InventoryService(repo=InventoryRepository())
            cap = service.calculate_recipe_capacity(meal.id)
            assert cap["capacity"] == 5
            assert cap["is_available"] is True
            assert cap["error"] is None

    def test_zero_stock_unavailable(self, app):
        with app.app_context():
            meal, _ = self._setup_meal_with_ingredient(stock_qty="0")
            service = InventoryService(repo=InventoryRepository())
            cap = service.calculate_recipe_capacity(meal.id)
            assert cap["capacity"] == 0
            assert cap["is_available"] is False

    def test_missing_inventory_row(self, app):
        with app.app_context():
            meal = MenuItem(name="Solo Meal", price=Decimal("50"), category="Main", is_available=True)
            ing = MenuItem(name="Orphan Ing", price=Decimal("0"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.flush()
            db.session.add(
                MenuItemIngredient(
                    menu_item_id=meal.id,
                    ingredient_item_id=ing.id,
                    quantity_required=Decimal("1.00"),
                    unit="pieces",
                    conversion_ratio=Decimal("1.0000"),
                )
            )
            db.session.commit()
            service = InventoryService(repo=InventoryRepository())
            cap = service.calculate_recipe_capacity(meal.id)
            assert cap["error"] == "INVENTORY_ROW_NOT_FOUND"
            assert cap["capacity"] == 0

    def test_invalid_unit_without_conversion(self, app):
        with app.app_context():
            meal = MenuItem(name="Bad Units Meal", price=Decimal("50"), category="Main", is_available=True)
            ing = MenuItem(name="Bangus", price=Decimal("0"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.flush()
            db.session.add(
                MenuItemIngredient(
                    menu_item_id=meal.id,
                    ingredient_item_id=ing.id,
                    quantity_required=Decimal("1.00"),
                    unit="pieces",
                    conversion_ratio=Decimal("1.0000"),
                )
            )
            db.session.add(
                InventoryItem(
                    menu_item_id=ing.id,
                    stock_qty=Decimal("4.00"),
                    unit="klg",
                    low_stock_threshold=1,
                )
            )
            db.session.commit()
            service = InventoryService(repo=InventoryRepository())
            cap = service.calculate_recipe_capacity(meal.id)
            assert cap["error"] == "INVALID_UNIT_CONVERSION"
            assert cap["capacity"] == 0

    def test_category_casing_availability(self, app):
        with app.app_context():
            meal = MenuItem(name="Casing Meal", price=Decimal("100"), category="Main", is_available=True)
            ing = MenuItem(name="Casing Ing", price=Decimal("0"), category=" INGREDIENT ", is_available=True)
            db.session.add_all([meal, ing])
            db.session.flush()
            db.session.add(
                MenuItemIngredient(
                    menu_item_id=meal.id,
                    ingredient_item_id=ing.id,
                    quantity_required=Decimal("2.00"),
                    unit="pieces",
                    conversion_ratio=Decimal("1.0000"),
                )
            )
            db.session.add(
                InventoryItem(
                    menu_item_id=ing.id,
                    stock_qty=Decimal("10.00"),
                    unit="pieces",
                    low_stock_threshold=5,
                )
            )
            db.session.commit()
            service = InventoryService(repo=InventoryRepository())
            cap = service.calculate_recipe_capacity(meal.id)
            assert cap["capacity"] == 5
            assert cap["is_available"] is True


class TestInventorySummary:
    def test_summary_counts(self, app):
        with app.app_context():
            from app.models.menu_item import MenuItemIngredient
            from app.models.inventory import InventoryLog

            MenuItemIngredient.query.delete()
            InventoryLog.query.delete()
            InventoryItem.query.delete()
            MenuItem.query.delete()
            db.session.commit()

            ing_low = MenuItem(name="Low Ing", price=0, category="ingredient", is_available=True)
            ing_out = MenuItem(name="Out Ing", price=0, category="ingredient", is_available=True)
            meal1 = MenuItem(name="Meal A", price=Decimal("50"), category="Main", is_available=True)
            meal2 = MenuItem(name="Meal B", price=Decimal("60"), category="Main", is_available=True)
            db.session.add_all([ing_low, ing_out, meal1, meal2])
            db.session.flush()
            db.session.add_all(
                [
                    InventoryItem(menu_item_id=ing_low.id, stock_qty=Decimal("2"), unit="pieces", low_stock_threshold=5),
                    InventoryItem(menu_item_id=ing_out.id, stock_qty=Decimal("0"), unit="pieces", low_stock_threshold=5),
                ]
            )
            db.session.commit()
            service = InventoryService(repo=InventoryRepository())
            summary = service.get_inventory_summary()
            assert summary["low_stock"] == 1
            assert summary["no_stock"] == 1
            assert summary["total_menu_items"] == 2
            assert summary["low_stock"] + summary["no_stock"] == 2

    def test_summary_counts_no_overlap(self, app):
        with app.app_context():
            from app.models.menu_item import MenuItemIngredient
            from app.models.inventory import InventoryLog

            MenuItemIngredient.query.delete()
            InventoryLog.query.delete()
            InventoryItem.query.delete()
            MenuItem.query.delete()
            db.session.commit()

            ing = MenuItem(name="Test overlap Ing", price=0, category="ingredient", is_available=True)
            db.session.add(ing)
            db.session.flush()

            inv = InventoryItem(menu_item_id=ing.id, stock_qty=Decimal("0"), unit="pieces", low_stock_threshold=5)
            db.session.add(inv)
            db.session.commit()

            service = InventoryService(repo=InventoryRepository())
            summary = service.get_inventory_summary()
            assert summary["no_stock"] == 1
            assert summary["low_stock"] == 0


class TestRecipeLinkingAPI:
    def test_invalid_ingredient_category(self, app, client):
        with app.app_context():
            admin = Admin.query.filter_by(username="admin").first()
            if not admin:
                admin = Admin(full_name="Admin", username="admin")
                admin.set_password("Admin123!@#$")
                db.session.add(admin)
                db.session.commit()
            admin_id = admin.id
            meal = MenuItem(name="Meal", price=Decimal("50"), category="Main", is_available=True)
            not_ing = MenuItem(name="Not Ing", price=Decimal("0"), category="Snack", is_available=True)
            db.session.add_all([meal, not_ing])
            db.session.commit()
            meal_id, not_ing_id = meal.id, not_ing.id

        _set_auth_session(client, role="admin", user_id=admin_id)
        resp = client.post(
            "/admin/inventory/api/recipes",
            json={
                "menu_item_id": meal_id,
                "ingredient_item_id": not_ing_id,
                "quantity_required": 1,
                "unit": "pieces",
                "conversion_ratio": 1,
            },
        )
        assert resp.status_code == 400
        data = resp.get_json()
        assert data["error"] == "INVALID_INGREDIENT"

    def test_ingredient_category_casing(self, app, client):
        with app.app_context():
            admin = Admin.query.filter_by(username="admin").first()
            if not admin:
                admin = Admin(full_name="Admin", username="admin")
                admin.set_password("Admin123!@#$")
                db.session.add(admin)
                db.session.commit()
            admin_id = admin.id
            meal = MenuItem(name="Meal", price=Decimal("50"), category="Main", is_available=True)
            ing = MenuItem(name="Bangus", price=Decimal("0"), category=" INGREDIENT ", is_available=True)
            db.session.add_all([meal, ing])
            db.session.commit()
            meal_id, ing_id = meal.id, ing.id

        _set_auth_session(client, role="admin", user_id=admin_id)
        resp = client.post(
            "/admin/inventory/api/recipes",
            json={
                "menu_item_id": meal_id,
                "ingredient_item_id": ing_id,
                "quantity_required": 1,
                "unit": "pieces",
                "conversion_ratio": 1,
            },
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True

    def test_duplicate_recipe_mapping(self, app, client):
        with app.app_context():
            admin = Admin.query.filter_by(username="admin").first()
            if not admin:
                admin = Admin(full_name="Admin", username="admin")
                admin.set_password("Admin123!@#$")
                db.session.add(admin)
                db.session.commit()
            admin_id = admin.id
            meal = MenuItem(name="Duplicate Meal", price=Decimal("50"), category="Main", is_available=True)
            ing = MenuItem(name="Duplicate Ing", price=Decimal("0"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.commit()
            meal_id, ing_id = meal.id, ing.id

        _set_auth_session(client, role="admin", user_id=admin_id)

        # Link once
        resp = client.post(
            "/admin/inventory/api/recipes",
            json={
                "menu_item_id": meal_id,
                "ingredient_item_id": ing_id,
                "quantity_required": 1,
                "unit": "pieces",
                "conversion_ratio": 1,
            },
        )
        assert resp.status_code == 200

        # Link again (duplicate)
        resp2 = client.post(
            "/admin/inventory/api/recipes",
            json={
                "menu_item_id": meal_id,
                "ingredient_item_id": ing_id,
                "quantity_required": 2,
                "unit": "pieces",
                "conversion_ratio": 1,
            },
        )
        assert resp2.status_code == 400
        data = resp2.get_json()
        assert data["error"] == "MAPPING_ALREADY_EXISTS"


class TestOrdering:
    def _active_session(self):
        sess = CustomerSession(
            customer_name="Test",
            space_type_id=1,
            number_of_people=1,
            status="active",
        )
        db.session.add(sess)
        db.session.commit()
        return sess

    def test_untracked_item_orders_without_stock_and_prepared_item_deducts_servings(self, app):
        from app.models.inventory import OrderInventoryAllocation

        with app.app_context():
            service_item = MenuItem(name="Service", price=Decimal("20"), category="Main",
                                    is_available=True, inventory_mode="untracked")
            meal = MenuItem(name="Prepared Meal", price=Decimal("80"), category="Main",
                            is_available=True, inventory_mode="prepared")
            db.session.add_all([service_item, meal])
            db.session.flush()
            stock = InventoryItem(menu_item_id=meal.id, stock_qty=Decimal("3.00"),
                                  unit="servings", low_stock_threshold=1)
            db.session.add(stock)
            sess = self._active_session()
            db.session.commit()

            result = OrderService(repo=OrderRepository(), notifier=get_notifier()).add_order(
                session_id=sess.id,
                items=[{"menu_item_id": service_item.id, "quantity": 1},
                       {"menu_item_id": meal.id, "quantity": 2}],
                handled_by=None,
            )

            assert not isinstance(result, tuple)
            db.session.refresh(stock)
            assert stock.stock_qty == Decimal("1.00")
            allocations = OrderInventoryAllocation.query.filter_by(order_id=result["order_id"]).all()
            assert len(allocations) == 1
            assert allocations[0].quantity_deducted == Decimal("2.00")

    def test_successful_recipe_order(self, app):
        with app.app_context():
            meal = MenuItem(name="Order Meal", price=Decimal("80"), category="Main", is_available=True)
            ing = MenuItem(name="Order Ing", price=Decimal("0"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.flush()
            db.session.add(
                MenuItemIngredient(
                    menu_item_id=meal.id,
                    ingredient_item_id=ing.id,
                    quantity_required=Decimal("1.00"),
                    unit="pieces",
                    conversion_ratio=Decimal("1.0000"),
                )
            )
            inv = InventoryItem(
                menu_item_id=ing.id,
                stock_qty=Decimal("5.00"),
                unit="pieces",
                low_stock_threshold=2,
            )
            db.session.add(inv)
            sess = self._active_session()
            db.session.commit()
            meal_id, sess_id, ing_id = meal.id, sess.id, ing.id

            service = OrderService(repo=OrderRepository(), notifier=get_notifier())
            result = service.add_order(
                session_id=sess_id,
                items=[{"menu_item_id": meal_id, "quantity": 1}],
                handled_by=None,
            )
            assert not isinstance(result, tuple)
            db.session.refresh(inv)
            assert float(inv.stock_qty) == 4.0

    def test_order_and_stock_roll_back_together_if_deduction_loses_a_race(
        self, app, monkeypatch
    ):
        from app.services.menu_availability import MenuAvailability, StockError
        with app.app_context():
            meal = MenuItem(
                name="Race Meal",
                price=Decimal("80"),
                category="Main",
                is_available=True,
            )
            db.session.add(meal)
            session = self._active_session()
            db.session.commit()

            def lose_race(*_args, **_kwargs):
                raise StockError("Stock changed while saving the order.")
            monkeypatch.setattr(MenuAvailability, "reserve", lose_race)

            before = Order.query.count()
            service = OrderService(repo=OrderRepository(), notifier=get_notifier())
            result = service.add_order(
                session_id=session.id,
                items=[{"menu_item_id": meal.id, "quantity": 1}],
                handled_by=None,
            )

            assert isinstance(result, tuple)
            assert result[1] == 409
            assert Order.query.count() == before

    def test_insufficient_stock_returns_message(self, app):
        with app.app_context():
            meal = MenuItem(name="Low Meal", price=Decimal("80"), category="Main", is_available=True)
            ing = MenuItem(name="Low Ing", price=Decimal("0"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.flush()
            db.session.add(
                MenuItemIngredient(
                    menu_item_id=meal.id,
                    ingredient_item_id=ing.id,
                    quantity_required=Decimal("2.00"),
                    unit="pieces",
                    conversion_ratio=Decimal("1.0000"),
                )
            )
            db.session.add(
                InventoryItem(
                    menu_item_id=ing.id,
                    stock_qty=Decimal("1.00"),
                    unit="pieces",
                    low_stock_threshold=2,
                )
            )
            sess = self._active_session()
            db.session.commit()

            service = OrderService(repo=OrderRepository(), notifier=get_notifier())
            result = service.add_order(
                session_id=sess.id,
                items=[{"menu_item_id": meal.id, "quantity": 1}],
                handled_by=None,
            )
            assert isinstance(result, tuple)
            payload, status = result
            assert status == 409
            assert payload.get("message") or payload.get("error")
            assert "Low Ing" in payload["message"]

    def test_ordering_missing_inventory_row(self, app):
        with app.app_context():
            meal = MenuItem(name="Missing Inv Meal", price=Decimal("80"), category="Main", is_available=True)
            ing = MenuItem(name="Missing Inv Ing", price=Decimal("0"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.flush()
            db.session.add(
                MenuItemIngredient(
                    menu_item_id=meal.id,
                    ingredient_item_id=ing.id,
                    quantity_required=Decimal("1.00"),
                    unit="pieces",
                    conversion_ratio=Decimal("1.0000"),
                )
            )
            sess = self._active_session()
            db.session.commit()

            service = OrderService(repo=OrderRepository(), notifier=get_notifier())
            result = service.add_order(
                session_id=sess.id,
                items=[{"menu_item_id": meal.id, "quantity": 1}],
                handled_by=None,
            )
            assert isinstance(result, tuple)
            payload, status = result
            assert status == 400
            assert payload.get("error") == "INVENTORY_ROW_NOT_FOUND"
            assert "has no inventory record" in payload.get("message")

    def test_ordering_invalid_unit_conversion(self, app):
        with app.app_context():
            meal = MenuItem(name="Bad Unit Meal", price=Decimal("80"), category="Main", is_available=True)
            ing = MenuItem(name="Bad Unit Ing", price=Decimal("0"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.flush()
            db.session.add(
                MenuItemIngredient(
                    menu_item_id=meal.id,
                    ingredient_item_id=ing.id,
                    quantity_required=Decimal("1.00"),
                    unit="pieces",
                    conversion_ratio=Decimal("1.0000"),
                )
            )
            db.session.add(
                InventoryItem(
                    menu_item_id=ing.id,
                    stock_qty=Decimal("10.00"),
                    unit="klg",
                    low_stock_threshold=2,
                )
            )
            sess = self._active_session()
            db.session.commit()

            service = OrderService(repo=OrderRepository(), notifier=get_notifier())
            result = service.add_order(
                session_id=sess.id,
                items=[{"menu_item_id": meal.id, "quantity": 1}],
                handled_by=None,
            )
            assert isinstance(result, tuple)
            payload, status = result
            assert status == 400
            assert payload.get("error") == "INVALID_UNIT_CONVERSION"

