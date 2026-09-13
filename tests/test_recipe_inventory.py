import pytest
from decimal import Decimal
from datetime import datetime, UTC

from app import create_app, db
from app.models import Admin, CustomerSession, MenuItem, MenuItemIngredient, Order, SpaceType
from app.models.inventory import InventoryItem
from app.db.migrator import SchemaMigrator
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.order_repository import OrderRepository
from app.services.inventory_service import InventoryService
from app.services.order_service import OrderService
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

            monkeypatch.setattr(
                InventoryService, "validate_order_stock", lambda *_args, **_kwargs: None
            )
            monkeypatch.setattr(
                InventoryService, "deduct_on_order", lambda *_args, **_kwargs: False
            )

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
            assert status == 400
            assert payload.get("message") or payload.get("error")

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

