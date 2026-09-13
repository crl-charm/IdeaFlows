"""Regression tests for Phase 4 bounded-query database reads."""

from __future__ import annotations

from datetime import date, datetime, UTC
from decimal import Decimal

import pytest
from sqlalchemy import event

from app import create_app, db
from app.models import CustomerSession, MenuItem, MenuItemIngredient, SpaceType
from app.models.inventory import InventoryItem
from app.models.receivable import Receivable
from app.models.space_price_history import SpacePriceHistory
from app.repositories.admin_repository import AdminRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.receivable_repository import ReceivableRepository
from app.services.admin_service import AdminService
from app.services.inventory_service import InventoryService
from app.services.receivable_service import ReceivableService


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


class SelectCounter:
    def __init__(self, engine):
        self.engine = engine
        self.count = 0

    def _record(self, _conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            self.count += 1

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._record)
        return self

    def __exit__(self, *_args):
        event.remove(self.engine, "before_cursor_execute", self._record)


def test_inventory_dashboard_queries_do_not_grow_per_menu_row(app):
    with app.app_context():
        ingredients = []
        meals = []
        for index in range(12):
            ingredient = MenuItem(
                name=f"Ingredient {index}",
                price=0,
                category="Ingredient",
                is_available=True,
            )
            meal = MenuItem(
                name=f"Meal {index}",
                price=Decimal("100"),
                category="Main Dish",
                is_available=True,
            )
            db.session.add_all([ingredient, meal])
            db.session.flush()
            db.session.add_all(
                [
                    InventoryItem(
                        menu_item_id=ingredient.id,
                        stock_qty=Decimal("20"),
                        unit="pieces",
                        low_stock_threshold=5,
                    ),
                    MenuItemIngredient(
                        menu_item_id=meal.id,
                        ingredient_item_id=ingredient.id,
                        quantity_required=Decimal("2"),
                        unit="pieces",
                        conversion_ratio=Decimal("1"),
                    ),
                ]
            )
            ingredients.append(ingredient)
            meals.append(meal)
        db.session.commit()
        db.session.expire_all()

        service = InventoryService(InventoryRepository())
        with SelectCounter(db.engine) as queries:
            result = service.build_dashboard_snapshot()

        assert queries.count == 3
        assert len(result["data"]) == 12
        assert len(result["direct_stock"]) == 12
        assert all(row["capacity"] == 10 for row in result["data"])


def test_admin_count_and_latest_prices_are_each_single_query(app):
    with app.app_context():
        spaces = [
            SpaceType(name=f"Space {index}", rate_per_minute=Decimal("1.5"))
            for index in range(10)
        ]
        db.session.add_all(spaces)
        db.session.flush()
        db.session.add_all(
            CustomerSession(
                customer_name=f"Customer {index}",
                space_type_id=spaces[0].id,
                status="active",
            )
            for index in range(15)
        )
        for space in spaces:
            db.session.add_all(
                [
                    SpacePriceHistory(
                        space_type_id=space.id,
                        old_price=Decimal("1"),
                        new_price=Decimal("1.25"),
                        changed_at=datetime(2026, 1, 1),
                    ),
                    SpacePriceHistory(
                        space_type_id=space.id,
                        old_price=Decimal("1.25"),
                        new_price=Decimal("1.5"),
                        changed_at=datetime(2026, 2, 1),
                    ),
                ]
            )
        db.session.commit()

        service = AdminService(AdminRepository())
        with SelectCounter(db.engine) as count_queries:
            assert service.customer_count() == 15
        with SelectCounter(db.engine) as price_queries:
            prices = service.space_prices()

        assert count_queries.count == 1
        assert price_queries.count == 1
        assert len(prices) == 10
        assert all(row["last_changed"].startswith("2026-02-01") for row in prices)


def test_paginated_receivables_eager_load_creator_with_bounded_queries(app):
    with app.app_context():
        db.session.add_all(
            Receivable(
                customer_name=f"Customer {index}",
                customer_contact=f"09{index:09d}",
                items_description="Meal",
                amount_owed=Decimal("100"),
                due_date=date(2026, 12, 31),
                incurred_date=date(2026, 9, 13),
                created_by=1,
                paid=index % 2 == 0,
            )
            for index in range(30)
        )
        db.session.commit()
        db.session.expire_all()

        service = ReceivableService(ReceivableRepository())
        with SelectCounter(db.engine) as queries:
            result = service.list_paginated(1, 10, status="unpaid", search="Customer")

        assert queries.count <= 3
        assert len(result["data"]) == 10
        assert result["pagination"]["total"] == 15
        assert result["pagination"]["has_next"] is True
        assert all(row["created_by"] == "test_user" for row in result["data"])


def test_phase4_pages_use_browser_loading_only():
    from pathlib import Path

    routes = {
        "app/routes/menu.py": 'return render_template("admin/menu.html")',
        "app/routes/inventory.py": 'return render_template("admin/inventory.html")',
        "app/routes/receivables.py": 'return render_template("admin/receivables.html")',
        "app/routes/staff_receivables.py": 'return render_template("staff/receivables.html")',
    }
    root = Path(__file__).resolve().parents[1]
    for relative_path, expected in routes.items():
        assert expected in (root / relative_path).read_text(encoding="utf-8")
