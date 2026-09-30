"""Mistaken Time In cancellation releases only unused Regular/Premium seats."""

import re
from datetime import date, datetime, time as clock_time, timedelta
from decimal import Decimal
from time import time

import pytest
from sqlalchemy import inspect, text

from app import create_app, db
from app.db.migrator import SchemaMigrator
from app.models import BoardroomBooking, CustomerSession, MenuItem, Order, OrderItem, Receivable, SpaceType, Transaction
from app.repositories.sales_repository import SalesRepository
from app.repositories.receivable_repository import ReceivableRepository
from app.services.receivable_service import ReceivableService
from app.utils.dates import manila_date


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


@pytest.fixture
def client(app, isolated_database):
    with app.app_context():
        db.session.add_all([
            SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"), capacity=10),
            SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333"), capacity=10),
            SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")),
            SpaceType(name="Take Out", rate_per_minute=Decimal("0")),
            MenuItem(name="Coffee", price=Decimal("50.00"), category="Drinks",
                     inventory_mode="untracked", is_available=True),
        ])
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    return client


def checkin(client, space_id=1, name="Wrong lounge"):
    response = client.post("/api/checkin", json={
        "customer_name": name, "space_type_id": space_id, "number_of_people": 1,
    })
    assert response.status_code == 200
    return response.get_json()["session_id"]


def cancel(client, session_id, reason="Entered Regular instead of Premium", key=None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(f"/api/sessions/{session_id}/cancel", json={"reason": reason}, headers=headers)


def test_cancel_unused_checkin_releases_seat_and_preserves_history_without_money(app, client):
    session_id = checkin(client)
    with app.app_context():
        db.session.get(CustomerSession, session_id).time_in = datetime.utcnow() - timedelta(minutes=70)
        db.session.commit()
    assert next(row for row in client.get("/api/space-availability").get_json()
                if row["space_name"] == "Regular Lounge")["occupied"] == 1

    response = cancel(client, session_id, key="cancel-wrong-space")
    assert response.status_code == 200
    assert response.get_json()["uncollected_time_charge"] == 15
    assert cancel(client, session_id, key="cancel-wrong-space").status_code == 409
    assert cancel(client, session_id).status_code == 409
    assert client.get("/api/active-sessions").get_json() == []
    assert next(row for row in client.get("/api/space-availability").get_json()
                if row["space_name"] == "Regular Lounge")["occupied"] == 0
    assert client.get(f"/api/preview-checkout/{session_id}").status_code == 400
    assert client.post(f"/api/checkout/{session_id}", json={"payment_method": "cash"}).status_code == 400
    with app.app_context():
        menu_id = MenuItem.query.filter_by(name="Coffee").one().id
    assert client.post("/api/add-order", json={
        "session_id": session_id, "items": [{"menu_item_id": menu_id, "quantity": 1}],
    }).status_code == 400

    history = client.get("/api/sessions/cancellations?page=1").get_json()
    assert history["pages"] == 1
    assert history["data"][0]["session_id"] == session_id
    assert history["data"][0]["reason"] == "Entered Regular instead of Premium"
    assert history["data"][0]["actor"] == "test_user"
    assert history["data"][0]["uncollected_time_charge"] == 15
    with app.app_context():
        row = db.session.get(CustomerSession, session_id)
        assert row.status == "cancelled" and row.time_out == row.cancelled_at
        assert row.cancelled_by_id == 1 and row.cancelled_by_role == "staff"
        assert row.cancelled_space_name == "Regular Lounge"
        assert row.cancelled_uncollected_amount == Decimal("15.00")
        assert Transaction.query.count() == Order.query.count() == 0
        day = manila_date(row.cancelled_at)
        assert SalesRepository().daily_ledger(day, day).get(day) is None
        with pytest.raises(ValueError, match="cannot receive a debt"):
            ReceivableService(ReceivableRepository()).create(
                customer_name="Wrong lounge", customer_contact="", items_description="Debt",
                amount_owed=Decimal("10.00"), due_date=date.today().isoformat(),
                created_by=1, session_id=session_id,
            )
        assert Receivable.query.count() == 0
    assert checkin(client, 2, "Wrong lounge") != session_id

    page = client.get("/dashboard").data
    assert b"Cancel mistaken Time In" in page
    assert b"Cancelled Time Ins" in page
    assert b"openCancelCheckin" in page
    assert b"cancelButton" in page


def test_cancel_rejects_used_credit_booking_and_wrong_mode(app, client):
    with app.app_context():
        menu_id = MenuItem.query.filter_by(name="Coffee").one().id
    ordered = checkin(client, name="Ordered")
    assert client.post("/api/add-order", json={
        "session_id": ordered, "items": [{"menu_item_id": menu_id, "quantity": 1}],
    }).status_code == 200
    assert cancel(client, ordered).status_code == 409
    with app.app_context():
        item_id = OrderItem.query.one().id
    assert client.delete(f"/api/void-item/{item_id}", json={"reason": "Wrong item"}).status_code == 200
    assert cancel(client, ordered).status_code == 409

    debt = checkin(client, name="Debt")
    booked = checkin(client, name="Booked")
    credit = checkin(client, name="Credit")
    boardroom = checkin(client, 3, "Boardroom")
    food = client.post("/api/food-orders", json={"customer_name": "Food", "location": "Take Out"}).get_json()["session_id"]
    with app.app_context():
        db.session.add(Receivable(
            customer_name="Debt", items_description="Unpaid", amount_owed=Decimal("10.00"),
            due_date=date.today(), created_by=1, session_id=debt,
        ))
        db.session.add(BoardroomBooking(
            customer_name="Booked", date=date.today(), start_time=clock_time(9),
            end_time=clock_time(10), number_of_people=1, status="cancelled", session_id=booked,
        ))
        db.session.get(CustomerSession, credit).credit_balance = Decimal("10.00")
        db.session.commit()
    for session_id in (debt, booked, credit, boardroom, food):
        assert cancel(client, session_id).status_code == 409
    assert cancel(client, ordered, "  ").status_code == 400
    assert cancel(client, 9999).status_code == 404
    assert client.get("/api/sessions/cancellations").get_json()["data"] == []
    assert len(client.get("/api/active-sessions").get_json()) == 5

    completed = checkin(client, name="Completed")
    paid = client.post(f"/api/checkout/{completed}", json={
        "payment_method": "cash", "amount_tendered": "10.00",
    })
    assert paid.status_code == 200
    assert cancel(client, completed).status_code == 409


def test_cancel_requires_login_and_csrf(app, client):
    session_id = checkin(client)
    app.config["WTF_CSRF_ENABLED"] = True
    assert cancel(client, session_id).status_code == 400
    page = client.get("/dashboard")
    token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    assert client.post(f"/api/sessions/{session_id}/cancel", json={"reason": "Wrong lounge"},
                       headers={"X-CSRFToken": token}).status_code == 200
    anonymous = app.test_client()
    assert anonymous.get("/api/sessions/cancellations").status_code in (302, 401)
    assert anonymous.post(f"/api/sessions/{session_id}/cancel", json={"reason": "Wrong"}).status_code in (302, 400, 401)
    with client.session_transaction() as auth:
        auth["role"] = "customer"
    assert client.get("/api/sessions/cancellations").status_code == 403


def test_existing_database_receives_cancellation_columns(app):
    with app.app_context():
        db.session.execute(text("ALTER TABLE customer_sessions DROP COLUMN cancel_reason"))
        db.session.commit()
        migrator = SchemaMigrator(db, app)
        migrator.run()
        migrator.run()
        assert "cancel_reason" in {column["name"] for column in inspect(db.engine).get_columns("customer_sessions")}
