import pytest
from decimal import Decimal
from datetime import datetime, UTC
from app import create_app, db
from app.models import Admin, MenuItem, MenuItemIngredient, Order, OrderItem, User
from app.models.inventory import InventoryItem, InventoryLog
from app.db.migrator import SchemaMigrator
from app.repositories.menu_repository import MenuRepository
from app.repositories.inventory_repository import InventoryRepository
from app.services.inventory_service import InventoryService


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
    )
    with application.app_context():
        db.create_all()
        SchemaMigrator(db, application).run()
        # Seed test admin account if not present
        admin = Admin.query.filter_by(username="admin").first()
        if not admin:
            admin = Admin(full_name="System Admin", username="admin")
            admin.set_password("Admin123!@#$")
            db.session.add(admin)
            db.session.commit()
    return application


@pytest.fixture
def client(app):
    return app.test_client()


def _set_auth_session(client, role: str = "admin", user_id: int = 1):
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = f"test_{role}"
        sess["role"] = role
        sess["last_activity"] = datetime.now(UTC).timestamp()


class TestRecipeConversions:
    def test_case_insensitive_ingredient_filtering(self, app):
        with app.app_context():
            # Clean up existing items in correct FK dependency order
            db.session.query(MenuItemIngredient).delete()
            db.session.query(OrderItem).delete()
            db.session.query(Order).delete()
            db.session.query(InventoryLog).delete()
            db.session.query(InventoryItem).delete()
            db.session.query(MenuItem).delete()
            db.session.commit()

            # Create standard foods and raw ingredients
            food1 = MenuItem(name="Adobo", price=Decimal("150.00"), category="Main Dish", is_available=True)
            food2 = MenuItem(name="Fries", price=Decimal("60.00"), category="Snack", is_available=True)
            ing1 = MenuItem(name="Pork", price=Decimal("0.00"), category="ingredient", is_available=True)
            ing2 = MenuItem(name="Potato", price=Decimal("0.00"), category="Ingredient", is_available=True)
            ing3 = MenuItem(name="Garlic", price=Decimal("0.00"), category="INGREDIENT", is_available=True)

            db.session.add_all([food1, food2, ing1, ing2, ing3])
            db.session.commit()

            repo = MenuRepository()
            all_items = repo.list_all()
            available_items = repo.list_available()
            ordering_items = repo.list_for_ordering()

            # None of these listings should return the ingredients
            assert len(all_items) == 2
            assert all(item.category.lower() != "ingredient" for item in all_items)

            assert len(available_items) == 2
            assert all(item.category.lower() != "ingredient" for item in available_items)

            assert len(ordering_items) == 2
            assert all(item.category.lower() != "ingredient" for item in ordering_items)

    def test_recipe_linking_validation(self, app, client):
        with app.app_context():
            admin = Admin.query.filter_by(username="admin").first()
            admin_id = admin.id if admin else 1

        _set_auth_session(client, role="admin", user_id=admin_id)

        with app.app_context():
            meal = MenuItem(name="Bangus Silog", price=Decimal("145.00"), category="Main Dish", is_available=True)
            ing = MenuItem(name="Fish bangus", price=Decimal("0.00"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.commit()
            
            meal_id = meal.id
            ing_id = ing.id

        # 1. Invalid qty <= 0
        resp = client.post("/admin/inventory/api/recipes", json={
            "menu_item_id": meal_id,
            "ingredient_item_id": ing_id,
            "quantity_required": 0,
            "unit": "pieces",
            "conversion_ratio": 1.0
        })
        assert resp.status_code == 400
        assert b"Quantity required must be greater than zero" in resp.data

        # 2. Invalid ratio <= 0
        resp = client.post("/admin/inventory/api/recipes", json={
            "menu_item_id": meal_id,
            "ingredient_item_id": ing_id,
            "quantity_required": 1.0,
            "unit": "pieces",
            "conversion_ratio": -0.5
        })
        assert resp.status_code == 400
        assert b"Conversion ratio must be greater than zero" in resp.data

        # 3. Invalid unit format (e.g. not in standard list)
        resp = client.post("/admin/inventory/api/recipes", json={
            "menu_item_id": meal_id,
            "ingredient_item_id": ing_id,
            "quantity_required": 1.0,
            "unit": "kilograms",
            "conversion_ratio": 1.0
        })
        assert resp.status_code == 400
        assert b"Invalid unit. Must be one of:" in resp.data

    def test_linking_math_and_audit_logging(self, app, client):
        with app.app_context():
            admin = Admin.query.filter_by(username="admin").first()
            admin_id = admin.id if admin else 1

        _set_auth_session(client, role="admin", user_id=admin_id)

        with app.app_context():
            # Add fresh items
            meal = MenuItem(name="Bangus Silog", price=Decimal("145.00"), category="Main Dish", is_available=True)
            ing = MenuItem(name="Fish bangus", price=Decimal("0.00"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.commit()

            meal_id = meal.id
            ing_id = ing.id

        # Link with qty=1.0, unit="pieces", ratio=0.25 (1 piece = 0.25 klg)
        resp = client.post("/admin/inventory/api/recipes", json={
            "menu_item_id": meal_id,
            "ingredient_item_id": ing_id,
            "quantity_required": 1.0,
            "unit": "pieces",
            "conversion_ratio": 0.25
        })
        assert resp.status_code == 200

        with app.app_context():
            link = MenuItemIngredient.query.filter_by(menu_item_id=meal_id, ingredient_item_id=ing_id).first()
            assert link is not None
            assert float(link.quantity_required) == 1.0
            assert link.unit == "pieces"
            assert float(link.conversion_ratio) == 0.25

            # Verify the InventoryItem row was auto-created and logged
            inv_item = InventoryItem.query.filter_by(menu_item_id=ing_id).first()
            assert inv_item is not None

            # Verify the audit log exists in InventoryLog
            log = InventoryLog.query.filter_by(inventory_item_id=inv_item.id).first()
            assert log is not None
            assert float(log.change_qty) == 0.0
            assert "linked to Bangus Silog" in log.reason

            # Verify capacity math: Stock 3.00 klg, recipe requires 1.00 pieces (ratio 0.25) -> capacity = 3 / 0.25 = 12 servings
            inv_item.stock_qty = Decimal("3.00")
            inv_item.unit = "klg"
            db.session.commit()

            service = InventoryService(repo=InventoryRepository())
            recipe_items = service.build_recipe_inventory_items()
            meal_record = next(x for x in recipe_items if x["id"] == meal_id)
            assert meal_record["capacity"] == 12

    def test_deduction_and_backward_compatibility(self, app):
        with app.app_context():
            # Test precise deduction: order 1 meal -> deducts 0.25 klg from 3.00 klg stock
            meal = MenuItem(name="Bangus Silog", price=Decimal("145.00"), category="Main Dish", is_available=True)
            ing = MenuItem(name="Fish bangus", price=Decimal("0.00"), category="ingredient", is_available=True)
            db.session.add_all([meal, ing])
            db.session.commit()

            # Set up recipe link (1 pieces, ratio = 0.25)
            link = MenuItemIngredient(
                menu_item_id=meal.id,
                ingredient_item_id=ing.id,
                quantity_required=Decimal("1.00"),
                unit="pieces",
                conversion_ratio=Decimal("0.2500")
            )
            inv_item = InventoryItem(
                menu_item_id=ing.id,
                stock_qty=Decimal("3.00"),
                unit="klg",
                low_stock_threshold=1
            )
            db.session.add_all([link, inv_item])
            db.session.commit()

            service = InventoryService(repo=InventoryRepository())
            # Deduct on order (quantity = 1)
            assert service.deduct_on_order(meal.id, 1) is True

            # Check stock is updated to 2.75 klg
            db.session.refresh(inv_item)
            assert float(inv_item.stock_qty) == 2.75

            # ----------------------------------------------------
            # Test Backward Compatibility: Legacy Link (unit=None, ratio=None/1.0)
            # ----------------------------------------------------
            legacy_meal = MenuItem(name="Legacy Rice", price=Decimal("50.00"), category="Main Dish", is_available=True)
            legacy_ing = MenuItem(name="Rice Raw", price=Decimal("0.00"), category="ingredient", is_available=True)
            db.session.add_all([legacy_meal, legacy_ing])
            db.session.commit()

            legacy_link = MenuItemIngredient(
                menu_item_id=legacy_meal.id,
                ingredient_item_id=legacy_ing.id,
                quantity_required=Decimal("2.00"),
                unit=None,
                conversion_ratio=Decimal("1.0000") # default fallback is 1.0
            )
            legacy_inv = InventoryItem(
                menu_item_id=legacy_ing.id,
                stock_qty=Decimal("10.00"),
                unit="cups",
                low_stock_threshold=2
            )
            db.session.add_all([legacy_link, legacy_inv])
            db.session.commit()

            # Capacity: 10.00 cups stock / 2.00 required = 5 capacity
            recipe_items = service.build_recipe_inventory_items()
            legacy_meal_record = next(x for x in recipe_items if x["id"] == legacy_meal.id)
            assert legacy_meal_record["capacity"] == 5

            # Deduct: order 2 legacy meals -> deducts 2 * 2 = 4 cups
            assert service.deduct_on_order(legacy_meal.id, 2) is True
            db.session.refresh(legacy_inv)
            assert float(legacy_inv.stock_qty) == 6.00
