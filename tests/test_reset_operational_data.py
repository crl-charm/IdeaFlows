from decimal import Decimal
from time import time

import pytest
from sqlalchemy import text

from app import create_app, db
from app.db.reset_operational_data import ACCOUNT_TABLES, RESET_TABLES, preview_reset, reset_operational_data
from app.models import (
    Admin, CustomerSession, InventoryItem, MenuItem, Order, OrderItem,
    SpaceType, StaffAttendance, Transaction, User,
)


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


def test_operational_reset_preserves_accounts_and_reseeds_defaults(app):
    with app.app_context():
        db.session.execute(text("PRAGMA foreign_keys=ON"))
        assert db.session.scalar(text("PRAGMA foreign_keys")) == 1
        admin = Admin(full_name="Owner", username="owner", password="stored-hash")
        space = SpaceType(name="Custom Space", rate_per_minute=Decimal("1.0000"))
        menu = MenuItem(name="Coffee", price=Decimal("50.00"))
        db.session.add_all([admin, space, menu])
        db.session.commit()

        inventory = InventoryItem(menu_item_id=menu.id, stock_qty=10)
        customer = CustomerSession(customer_name="Guest", space_type_id=space.id)
        attendance = StaffAttendance(user_id=1)
        db.session.add_all([inventory, customer, attendance])
        db.session.commit()

        order = Order(customer_session_id=customer.id, handled_by=1)
        transaction = Transaction(session_id=customer.id, time_bill=0, food_bill=50, total_bill=50)
        db.session.add_all([order, transaction])
        db.session.commit()
        db.session.add(OrderItem(order_id=order.id, menu_item_id=menu.id, quantity=1, price=50))
        db.session.commit()

        account_passwords = (db.session.get(User, 1).password, admin.password)
        before = preview_reset()
        assert before["users"] == before["admins"] == 1
        assert before["order_items"] == before["transactions"] == 1
        assert before["staff_attendance"] == 1
        assert before["menu_items"] == 1

        with pytest.raises(ValueError, match="Database name does not match"):
            reset_operational_data("wrong-database")
        assert preview_reset() == before

        reset_operational_data(db.engine.url.database or ":memory:")
        after = preview_reset()
        assert set(after) == ACCOUNT_TABLES | RESET_TABLES
        assert after["users"] == after["admins"] == 1
        assert (db.session.get(User, 1).password, db.session.get(Admin, admin.id).password) == account_passwords
        assert {name: after[name] for name in ("space_types", "menu_categories", "finance_budgets")} == {
            "space_types": 3,
            "menu_categories": 3,
            "finance_budgets": 1,
        }
        assert all(after[name] == 0 for name in RESET_TABLES - {"space_types", "menu_categories", "finance_budgets"})

        db.session.execute(text("CREATE TABLE unexpected_records (id INTEGER PRIMARY KEY)"))
        with pytest.raises(RuntimeError, match=r"Unreviewed tables: \['unexpected_records'\]"):
            preview_reset()
        db.session.execute(text("DROP TABLE unexpected_records"))


def test_checkin_uses_current_space_ids_after_reset(app):
    with app.app_context():
        db.session.add_all([
            SpaceType(id=10, name="Regular Lounge", rate_per_minute=Decimal("0.1667")),
            SpaceType(id=11, name="Premium Lounge", rate_per_minute=Decimal("0.3333")),
            SpaceType(id=12, name="Boardroom", rate_per_minute=Decimal("4.1667")),
        ])
        db.session.commit()

    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert b'<option value="11">Premium Lounge</option>' in page.data

    valid = client.post("/api/checkin", json={
        "customer_name": "Carl", "number_of_people": 1, "space_type_id": 11,
    })
    assert valid.status_code == 200
    invalid = client.post("/api/checkin", json={
        "customer_name": "Other", "number_of_people": 1, "space_type_id": 2,
    })
    assert invalid.status_code == 400
    assert invalid.get_json()["error"] == "Please select a valid space."
