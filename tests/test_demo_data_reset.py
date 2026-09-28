from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app import create_app, db
from app.db.reset_demo_data import ACTIVITY_TABLES, preview_demo_reset, reset_demo_data
from app.models import (BoardroomBooking, CustomerSession, Expense, FinanceBudget,
                        FinanceTransaction, InventoryItem, InventoryLog, MenuItem,
                        Order, SpacePriceHistory, SpaceType, StaffAttendance,
                        StaffShift, Transaction, User)
from app.models.menu_category import MenuCategory


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


def test_demo_reset_keeps_accounts_and_setup_but_clears_activity_and_amounts(app):
    with app.app_context():
        space = SpaceType(name="Client Regular", rate_per_minute=Decimal("0.5000"), capacity=16)
        category = MenuCategory(name="Client Menu")
        menu = MenuItem(name="Coffee", category="Client Menu", price=Decimal("80.00"))
        budget = FinanceBudget(_name="Operating", _total_budget=Decimal("500.00"), _allocated=Decimal("125.00"))
        db.session.add_all([space, category, menu, budget])
        db.session.flush()
        stock = InventoryItem(menu_item_id=menu.id, stock_qty=Decimal("12.00"), unit="packs")
        customer = CustomerSession(customer_name="Demo Guest", space_type_id=space.id, status="completed")
        db.session.add_all([stock, customer, SpacePriceHistory(
            space_type_id=space.id, old_price=Decimal("0.4000"), new_price=Decimal("0.5000"),
            changed_by_id=1,
        )])
        db.session.flush()
        db.session.add_all([
            InventoryLog(inventory_item_id=stock.id, change_qty=12, reason="Demo restock", changed_by=1),
            FinanceTransaction(_budget_id=budget.id, _type="expense", _amount=25),
            Expense(category="supplies", description="Demo", amount=25, expense_date=date.today(), logged_by=1),
            Order(customer_session_id=customer.id, handled_by=1),
            Transaction(session_id=customer.id, time_bill=20, food_bill=0, total_bill=20),
            StaffAttendance(user_id=1),
            StaffShift(user_id=1, shift_role="cashier", time_in=datetime(2026, 9, 29, 2)),
        ])
        db.session.commit()
        space_id, menu_id, stock_id, budget_id = space.id, menu.id, stock.id, budget.id

        counts, active, upcoming = preview_demo_reset()
        assert active == upcoming == 0
        delete_rows = sum(counts[name] for name in ACTIVITY_TABLES)
        assert delete_rows > 0
        assert db.session.get(InventoryItem, stock_id).stock_qty == 12

        with pytest.raises(ValueError, match="Database name does not match"):
            reset_demo_data("wrong-database", delete_rows)
        with pytest.raises(ValueError, match="row count changed"):
            reset_demo_data(db.engine.url.database or ":memory:", delete_rows + 1)
        assert db.session.get(InventoryItem, stock_id).stock_qty == 12

        reset_demo_data(db.engine.url.database or ":memory:", delete_rows)
        after, _, _ = preview_demo_reset()
        assert all(after[name] == 0 for name in ACTIVITY_TABLES)
        assert after["users"] == 1
        assert db.session.get(User, 1).username == "test_user"
        assert (db.session.get(SpaceType, space_id).name,
                db.session.get(SpaceType, space_id).rate_per_minute) == ("Client Regular", Decimal("0.5000"))
        assert after["space_price_history"] == 1
        assert db.session.get(MenuItem, menu_id).price == 80
        assert after["menu_categories"] == 1
        assert db.session.get(InventoryItem, stock_id).stock_qty == 0
        assert db.session.get(InventoryItem, stock_id).unit == "packs"
        assert db.session.get(FinanceBudget, budget_id)._total_budget == 0
        assert db.session.get(FinanceBudget, budget_id)._allocated == 0


def test_demo_reset_requires_explicit_review_of_active_sessions_and_future_bookings(app):
    with app.app_context():
        space = SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667"))
        db.session.add(space)
        db.session.flush()
        db.session.add_all([
            CustomerSession(customer_name="Possible guest", space_type_id=space.id, status="active"),
            BoardroomBooking(customer_name="Possible booking", date=date.today() + timedelta(days=2),
                             start_time=time(14), end_time=time(15), number_of_people=1),
        ])
        db.session.commit()
        counts, active, upcoming = preview_demo_reset()
        assert active == upcoming == 1
        delete_rows = sum(counts[name] for name in ACTIVITY_TABLES)
        database = db.engine.url.database or ":memory:"

        with pytest.raises(RuntimeError, match="Active customer sessions"):
            reset_demo_data(database, delete_rows)
        with pytest.raises(RuntimeError, match="Upcoming bookings"):
            reset_demo_data(database, delete_rows, confirm_active_sessions=True)
        assert CustomerSession.query.count() == 1
        reset_demo_data(database, delete_rows, confirm_active_sessions=True, confirm_future_bookings=True)
        assert CustomerSession.query.count() == BoardroomBooking.query.count() == 0
