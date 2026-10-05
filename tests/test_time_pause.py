"""Pause/resume must freeze only the lounge time charge and preserve its audit trail."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from time import time
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text

from app import create_app, db
from app.db.migrator import SchemaMigrator
from app.models import CustomerSession, MenuItem, Order, OrderItem, SessionTimeEvent, SpaceType, Transaction, User
from app.repositories.sales_repository import SalesRepository
from app.repositories.session_repository import SessionRepository
from app.services.session_service import SessionService
from app.utils.dates import manila_date


class Clock:
    def __init__(self, now):
        self.value = now

    def now(self):
        return self.value


class Notifier:
    def session_checked_out(self, data):
        pass


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


@pytest.fixture
def client(app, monkeypatch):
    import app.routes.session_routes as routes

    clock = Clock(datetime.utcnow().replace(microsecond=0) - timedelta(hours=1))
    monkeypatch.setattr(routes, "_service", SessionService(SessionRepository(), clock, Notifier()))
    with app.app_context():
        db.session.add_all([
            SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"), capacity=30),
            SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333"), capacity=30),
            SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667"), capacity=1),
            SpaceType(name="Take Out", rate_per_minute=Decimal("0"), capacity=0),
            MenuItem(name="Meal", price=Decimal("120.00"), inventory_mode="untracked"),
        ])
        db.session.commit()
    browser = app.test_client()
    with browser.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    return browser, clock


def create_session(space, started_at, *, mode="timed"):
    row = CustomerSession(customer_name="Carl", space_type_id=space, service_mode=mode,
                          time_in=started_at, status="active")
    db.session.add(row)
    db.session.commit()
    return row.id


def place_meal(session_id):
    order = Order(customer_session_id=session_id, handled_by=1)
    db.session.add(order)
    db.session.flush()
    item = OrderItem(order_id=order.id, menu_item_id=1, quantity=1,
                     price=Decimal("120.00"), name_snapshot="Meal")
    db.session.add(item)
    db.session.commit()
    return item.id


def post_action(client, session_id, action):
    return client.post(f"/api/sessions/{session_id}/{action}",
                       headers={"Idempotency-Key": str(uuid4())})


def test_pause_resume_food_discount_checkout_and_daily_balance(app, client):
    browser, clock = client
    started_at = clock.now() - timedelta(minutes=59)
    with app.app_context():
        session_id = create_session(1, started_at)

    preview = browser.get(f"/api/preview-checkout/{session_id}").get_json()
    assert preview["time_bill"] == 10
    assert preview["minutes_used"] == 59

    response = post_action(browser, session_id, "pause")
    assert response.status_code == 200
    assert post_action(browser, session_id, "pause").status_code == 409

    clock.value += timedelta(minutes=6)
    with app.app_context():
        item_id = place_meal(session_id)
    paused = browser.get(f"/api/preview-checkout/{session_id}").get_json()
    assert paused["paused"] is True
    assert paused["time_bill"] == 10
    assert paused["food_bill"] == 120
    assert paused["minutes_used"] == 59
    active = browser.get("/api/active-sessions").get_json()[0]
    assert active["paused"] is True
    assert active["seconds_used"] == 59 * 60
    assert active["current_bill"] == 10
    stats = browser.get("/staff/daily-balance/api/today-stats")
    assert stats.status_code == 200
    assert stats.get_json()["data"]["expected_to_collect"] == 130

    assert post_action(browser, session_id, "resume").status_code == 200
    assert post_action(browser, session_id, "resume").status_code == 409
    clock.value += timedelta(minutes=1)
    assert browser.get(f"/api/preview-checkout/{session_id}").get_json()["time_bill"] == 10
    clock.value += timedelta(minutes=1)
    assert browser.get(f"/api/preview-checkout/{session_id}").get_json()["time_bill"] == 15

    checkout = browser.post(f"/api/checkout/{session_id}", json={
        "payment_method": "cash", "amount_tendered": "200.00",
        "discount_type": "pwd", "discount_item_id": item_id,
    })
    assert checkout.status_code == 200
    assert checkout.get_json()["total_bill"] == 111
    with app.app_context():
        row = db.session.get(CustomerSession, session_id)
        tx = Transaction.query.filter_by(session_id=session_id).one()
        events = SessionTimeEvent.query.filter_by(session_id=session_id).order_by(SessionTimeEvent.id).all()
        assert row.paused_at is None
        assert row.paused_microseconds == 6 * 60_000_000
        assert tx.billable_microseconds == 61 * 60_000_000
        assert [event.action for event in events] == ["paused", "resumed"]
        assert all(event.actor_id == 1 and event.actor_name == "test_user" for event in events)
        day = manila_date(tx.created_at)
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["total_revenue"] == 111
        assert ledger["checkout_methods"]["cash"] == 111

    record = browser.get("/api/checkout-records").get_json()[0]
    assert record["seconds_spent"] == 61 * 60
    assert record["has_time_pause"] is True
    assert browser.get(f"/receipt/{session_id}").status_code == 200
    assert b"Billable duration:</strong> 61 minutes" in browser.get(f"/receipt/{session_id}").data
    history = browser.get(f"/api/sessions/{session_id}/time-history").get_json()
    assert [event["action"] for event in history["events"]] == ["paused", "resumed"]


def test_checkout_while_paused_and_invalid_spaces(app, client):
    browser, clock = client
    with app.app_context():
        premium_id = create_session(2, clock.now() - timedelta(minutes=61))
        boardroom_id = create_session(3, clock.now())
        food_id = create_session(4, clock.now(), mode="food_only")

    assert post_action(browser, boardroom_id, "pause").status_code == 409
    assert post_action(browser, food_id, "pause").status_code == 409
    assert post_action(browser, 99999, "pause").status_code == 404
    assert post_action(browser, premium_id, "pause").status_code == 200
    clock.value += timedelta(hours=2)
    with app.app_context():
        place_meal(premium_id)
    checkout = browser.post(f"/api/checkout/{premium_id}", json={
        "payment_method": "gcash",
    })
    assert checkout.status_code == 200
    assert checkout.get_json()["time_bill"] == 30
    assert checkout.get_json()["food_bill"] == 120
    with app.app_context():
        tx = Transaction.query.filter_by(session_id=premium_id).one()
        events = SessionTimeEvent.query.filter_by(session_id=premium_id).order_by(SessionTimeEvent.id).all()
        assert tx.billable_microseconds == 61 * 60_000_000
        assert [event.action for event in events] == ["paused", "checked_out"]
        assert db.session.get(CustomerSession, premium_id).paused_at is None
        day = manila_date(tx.created_at)
        assert SalesRepository().daily_ledger(day, day)[day]["checkout_methods"]["gcash"] == 150
    assert post_action(browser, premium_id, "resume").status_code == 409


def test_multiple_pauses_cross_manila_midnight_and_admin_can_resume(app, client):
    browser, clock = client
    clock.value = datetime(2026, 10, 4, 15, 59)  # 11:59 p.m. in Manila
    with app.app_context():
        session_id = create_session(1, datetime(2026, 10, 4, 15, 0))
        admin = User(id=2, full_name="Owner", username="owner", role="admin", is_active=True)
        admin.set_password("OwnerPass123!")
        db.session.add(admin)
        db.session.commit()

    assert post_action(browser, session_id, "pause").status_code == 200
    clock.value = datetime(2026, 10, 4, 15, 58)
    assert browser.get(f"/api/preview-checkout/{session_id}").get_json()["time_bill"] == 10
    clock.value = datetime(2026, 10, 4, 16, 2)
    with browser.session_transaction() as auth:
        auth.update(user_id=2, username="owner", role="admin", last_activity=time())
    assert post_action(browser, session_id, "resume").status_code == 200
    clock.value += timedelta(minutes=1)
    assert browser.get(f"/api/preview-checkout/{session_id}").get_json()["time_bill"] == 10
    clock.value += timedelta(seconds=1)
    assert browser.get(f"/api/preview-checkout/{session_id}").get_json()["time_bill"] == 15
    assert post_action(browser, session_id, "pause").status_code == 200
    clock.value += timedelta(minutes=5)
    assert browser.get(f"/api/preview-checkout/{session_id}").get_json()["time_bill"] == 15
    assert post_action(browser, session_id, "resume").status_code == 200

    with app.app_context():
        events = SessionTimeEvent.query.filter_by(session_id=session_id).order_by(SessionTimeEvent.id).all()
        assert [event.action for event in events] == ["paused", "resumed", "paused", "resumed"]
        assert [event.business_date for event in events] == [
            date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 5), date(2026, 10, 5),
        ]
        assert events[0].actor_role == "staff"
        assert all(event.actor_role == "admin" for event in events[1:])
        assert db.session.get(CustomerSession, session_id).paused_microseconds == 8 * 60_000_000

    unauthenticated = app.test_client()
    assert unauthenticated.post(f"/api/sessions/{session_id}/pause").status_code in (401, 302)


def test_existing_database_gets_pause_columns_idempotently(app):
    with app.app_context():
        db.session.execute(text("ALTER TABLE customer_sessions DROP COLUMN paused_at"))
        db.session.execute(text("ALTER TABLE customer_sessions DROP COLUMN paused_microseconds"))
        db.session.execute(text("ALTER TABLE transactions DROP COLUMN billable_microseconds"))
        db.session.commit()
        migrator = SchemaMigrator(db, app)
        migrator.run()
        migrator.run()
        inspector = inspect(db.engine)
        assert {"paused_at", "paused_microseconds"} <= {
            column["name"] for column in inspector.get_columns("customer_sessions")
        }
        assert "billable_microseconds" in {
            column["name"] for column in inspector.get_columns("transactions")
        }
        assert inspector.has_table("session_time_events")


def test_cancel_unused_paused_checkin_keeps_frozen_uncollected_bill(app, client):
    browser, clock = client
    with app.app_context():
        session_id = create_session(1, clock.now() - timedelta(minutes=10))
    assert post_action(browser, session_id, "pause").status_code == 200
    clock.value += timedelta(hours=3)
    cancelled = browser.post(f"/api/sessions/{session_id}/cancel", json={"reason": "Wrong customer"})
    assert cancelled.status_code == 200
    assert cancelled.get_json()["uncollected_time_charge"] == 10
    history = browser.get(f"/api/sessions/{session_id}/time-history").get_json()["events"]
    assert [event["action"] for event in history] == ["paused", "cancelled"]
    assert browser.get("/api/sessions/cancellations").get_json()["data"][0]["has_time_pause"] is True
    with app.app_context():
        assert db.session.get(CustomerSession, session_id).status == "cancelled"
        assert Transaction.query.filter_by(session_id=session_id).count() == 0
