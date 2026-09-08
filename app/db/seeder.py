from __future__ import annotations

from decimal import Decimal

from app.models import MenuItem, SpaceType
from app.models.user import User
from app.models.admin import Admin
from app.models.finance import FinanceBudget


class DatabaseSeeder:
    """Populates lookup tables with defaults."""

    def __init__(self, db, app) -> None:
        self._db = db
        self._app = app

    def run(self, force: bool = False) -> None:
        db = self._db
        if force:
            MenuItem.query.delete()
            SpaceType.query.delete()
            db.session.commit()

        if SpaceType.query.count() == 0:
            db.session.add_all(
                [
                    SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667")),
                    SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333")),
                    SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")),
                ]
            )
            db.session.commit()

        default_caps = {"Regular Lounge": 30, "Premium Lounge": 30}
        for name, cap in default_caps.items():
            space = SpaceType.query.filter_by(name=name).first()
            if space and (space.capacity is None or space.capacity == 0):
                space.capacity = cap
        db.session.commit()

        # Update existing menu items with old categories to standard ones
        category_mappings = {
            "MainDish - Silog": "Main Dish",
            "MainDish - Main Meals": "Main Dish",
            "MainDish - Modern Meals": "Main Dish",
            "Snacks - Pancit": "Snack",
            "Snacks - Fries & Sides": "Snack",
            "Snacks - Appetizers": "Snack",
            "Snacks - Desserts": "Snack",
            "Drinks - Coffee (Hot)": "Beverages",
            "Drinks - Coffee (Cold)": "Beverages",
            "Drinks - Juices": "Beverages",
            "Drinks - Soft Drinks": "Beverages",
        }
        for old_cat, new_cat in category_mappings.items():
            db.session.query(MenuItem).filter_by(category=old_cat).update({"category": new_cat})
        db.session.commit()

        # Menu items are now managed through admin interface
        # No hardcoded items seeded on startup

        admin = Admin.query.filter_by(username="admin").first()
        if not admin:
            existing_user_admin = User.query.filter_by(username="admin", is_active=True).first()
            if existing_user_admin:
                admin = Admin(
                    full_name=existing_user_admin.full_name,
                    username=existing_user_admin.username,
                    created_at=existing_user_admin.created_at,
                )
                admin.password = existing_user_admin.password
                admin.failed_login_attempts = existing_user_admin.failed_login_attempts
                admin.locked_until = existing_user_admin.locked_until
                admin.last_login = existing_user_admin.last_login
                admin.password_changed_at = existing_user_admin.password_changed_at
                existing_user_admin.is_active = False
                db.session.add(admin)
                db.session.add(existing_user_admin)
            else:
                admin = Admin(full_name="System Admin", username="admin")
                admin.set_password("Admin123!@#$")
                db.session.add(admin)
            db.session.commit()
        else:
            existing_user_admin = User.query.filter_by(username="admin", is_active=True).first()
            if existing_user_admin:
                existing_user_admin.is_active = False
                db.session.commit()

        if FinanceBudget.query.count() == 0:
            db.session.add(FinanceBudget(_name="Main Budget", _total_budget=Decimal("0.00"), _allocated=Decimal("0.00")))
            db.session.commit()

        from app.models.menu_category import MenuCategory
        if MenuCategory.query.count() == 0:
            db.session.add_all(
                [
                    MenuCategory(name="Main Dish"),
                    MenuCategory(name="Snack"),
                    MenuCategory(name="Beverages"),
                ]
            )
            db.session.commit()
