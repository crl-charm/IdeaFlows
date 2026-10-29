"""Late arrivals use the real billing start, with an atomic, private audit trail."""

from datetime import datetime, time as wall_time, timedelta
from decimal import Decimal
from time import time
from uuid import uuid4

import pytest
from sqlalchemy import event, inspect

from app import create_app, db, socketio
from app.models import (
    BoardroomBooking, CustomerSession, MenuItem, OrderItem, SessionTimeEvent,
    SpaceType, Transaction, User,
)
from app.repositories.sales_repository import SalesRepository
from app.repositories.session_repository import SessionRepository
from app.services.session_service import SessionService
from app.utils.dates import MANILA_OFFSET, manila_date


class Clock:
    value = datetime(2026, 10, 27, 2, 20)  # 10:20 a.m. Manila

    def now(self):
        return self.value


class Notifier:
    def session_checked_out(self, payload):
        pass


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


@pytest.fixture
def setup(app, monkeypatch):
    import app.routes.dashboard_routes as dashboard
    import app.routes.session_routes as routes

    clock = Clock()
    monkeypatch.setattr(routes, "_service", SessionService(SessionRepository(), clock, Notifier()))
    monkeypatch.setattr(dashboard, "SystemClock", lambda: clock)
    with app.app_context():
        db.session.add_all([
            SpaceType(name=name, rate_per_minute=1, capacity=30)
            for name in ("Regular Lounge", "Premium Lounge", "Boardroom", "Whole Hub", "Take Out")
        ])
        db.session.add(MenuItem(name="Coffee", price=50, inventory_mode="untracked", is_available=True))
        db.session.add(User(id=2, full_name="Admin Gilbert", username="admin_gilbert", role="admin",
                            password=db.session.get(User, 1).password))
        db.session.commit()
        spaces = {space.name: space.id for space in SpaceType.query.all()}
    staff = app.test_client()
    with staff.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    return staff, clock, spaces


def late(staff, spaces, *, space="Premium Lounge", **overrides):
    payload = dict(customer_name="Carl", space_type_id=spaces[space], checkin_mode="late",
                   arrival_time="2026-10-27T09:00")
    payload.update(overrides)
    return staff.post("/api/checkin", json=payload, headers={"Idempotency-Key": str(uuid4())})


def test_late_bill_pause_food_discount_checkout_and_private_history(app, setup):
    staff, clock, spaces = setup
    response = late(staff, spaces, actor_id=999, actor_name="Forged", actor_role="admin")
    assert response.status_code == 200
    session_id = response.get_json()["session_id"]
    active = staff.get("/api/active-sessions").get_json()[0]
    assert active["seconds_used"] == 80 * 60
    assert active["current_bill"] == 30
    assert active["has_time_history"] is True and active["has_time_pause"] is False
    history = staff.get(f"/api/sessions/{session_id}/time-history").get_json()["events"][0]
    assert history["action"] == "late_checkin" and history["actor"] == "test_user"
    assert history["role"] == "staff" and "09:00 AM" in history["arrival_at"]
    assert "10:20:00 AM" in history["at"]
    with app.app_context():
        row = db.session.get(CustomerSession, session_id)
        audit = SessionTimeEvent.query.one()
        assert row.time_in == datetime(2026, 10, 27, 1)
        assert audit.occurred_at == clock.now() and audit.actor_id == 1
        assert Transaction.query.count() == 0
        assert "has_time_history" not in {col["name"] for col in inspect(db.engine).get_columns("customer_sessions")}

    public = app.test_client().get("/api/current-customers").get_json()["customers"][0]
    assert public["time_bill"] == 30 and public["seconds_used"] == 4800
    assert not ({"actor", "actor_id", "actor_name", "has_time_history", "events", "arrival_at"} & public.keys())
    assert staff.post("/api/add-order", json={
        "session_id": session_id, "items": [{"menu_item_id": 1, "quantity": 1}],
    }).status_code == 200
    assert staff.post(f"/api/sessions/{session_id}/pause").status_code == 200
    clock.value += timedelta(minutes=45)
    preview = staff.get(f"/api/preview-checkout/{session_id}").get_json()
    assert preview["time_bill"] == 30 and preview["food_bill"] == 50
    assert staff.get("/staff/daily-balance/api/today-stats").get_json()["data"]["expected_to_collect"] == 80
    assert staff.post(f"/api/sessions/{session_id}/resume").status_code == 200
    clock.value += timedelta(minutes=11)
    with app.app_context():
        item_id = OrderItem.query.one().id
    checked = staff.post(f"/api/checkout/{session_id}", json={
        "payment_method": "cash", "amount_tendered": "100", "discount_type": "pwd",
        "discount_item_id": item_id,
    })
    assert checked.status_code == 200 and checked.get_json()["total_bill"] == 80
    record = staff.get("/api/checkout-records").get_json()[0]
    assert record["time_bill"] == 40 and record["food_bill"] == 50 and record["discount_amount"] == 10
    assert record["seconds_spent"] == 91 * 60 and record["has_time_history"] is True
    receipt = staff.get(f"/receipt/{session_id}")
    assert receipt.status_code == 200 and b"2026-10-27 09:00:00" in receipt.data
    assert app.test_client().get("/api/current-customers").get_json()["customers"] == []
    with app.app_context():
        tx = Transaction.query.one()
        assert tx.billing_start_at == datetime(2026, 10, 27, 1)
        assert tx.change_given == 20
        day = manila_date(tx.created_at)
        assert SalesRepository().daily_ledger(day, day)[day]["total_revenue"] == 80


@pytest.mark.parametrize("space,minutes,expected", [
    ("Regular Lounge", 59, 10), ("Regular Lounge", 60, 10), ("Regular Lounge", 61, 15),
    ("Premium Lounge", 59, 20), ("Premium Lounge", 60, 20), ("Premium Lounge", 61, 30),
])
def test_late_arrival_uses_existing_started_billing_blocks(setup, space, minutes, expected):
    staff, clock, spaces = setup
    arrival = (clock.now() + MANILA_OFFSET - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")
    assert late(staff, spaces, space=space, arrival_time=arrival).status_code == 200
    assert staff.get("/api/active-sessions").get_json()[0]["current_bill"] == expected


@pytest.mark.parametrize("changes", [
    {"arrival_time": None}, {"arrival_time": ""}, {"arrival_time": []}, {"arrival_time": True},
    {"arrival_time": "2026-10-27T9:00"}, {"arrival_time": "2026-10-27T09:00Z"},
    {"arrival_time": "2026-10-27T09:00:00"}, {"arrival_time": "2026-10-27T09:00+08:00"},
    {"arrival_time": "2026-10-26T23:59"}, {"arrival_time": "2026-10-28T00:00"},
    {"arrival_time": "2026-10-27T10:21"}, {"arrival_time": "2026-10-27T25:00"},
    {"checkin_mode": None}, {"checkin_mode": ""}, {"checkin_mode": []}, {"checkin_mode": {}},
    {"checkin_mode": True}, {"checkin_mode": "now"}, {"void_request_id": 1},
])
def test_invalid_late_input_never_creates_a_visit_or_audit(app, setup, changes):
    staff, _, spaces = setup
    assert late(staff, spaces, **changes).status_code == 400
    with app.app_context():
        assert CustomerSession.query.count() == SessionTimeEvent.query.count() == 0


def test_normal_checkin_still_uses_server_now_and_late_dates_use_manila_midnight(app, setup):
    staff, clock, spaces = setup
    clock.value = datetime(2026, 10, 26, 16, 2)  # Next Manila day, still Oct 26 UTC
    assert late(staff, spaces, arrival_time="2026-10-27T00:00").status_code == 200
    expired = late(staff, spaces, arrival_time="2026-10-26T23:59")
    assert expired.status_code == 400 and "today in Manila" in expired.get_json()["error"]
    assert staff.post("/api/checkin", json={
        "customer_name": "On time", "space_type_id": spaces["Regular Lounge"],
    }).status_code == 200
    with app.app_context():
        on_time = CustomerSession.query.filter_by(customer_name="On time").one()
        assert on_time.time_in == clock.now() and on_time.has_time_history is False


def test_history_keeps_arrival_when_mysql_truncates_recording_microseconds(app, setup):
    staff, clock, spaces = setup
    clock.value = clock.now().replace(microsecond=123456)
    response = late(staff, spaces)
    assert response.status_code == 200
    with app.app_context():
        audit = SessionTimeEvent.query.one()
        audit.occurred_at = audit.occurred_at.replace(microsecond=0)
        db.session.commit()
    history = staff.get(f"/api/sessions/{response.get_json()['session_id']}/time-history").get_json()
    assert "09:00 AM" in history["events"][0]["arrival_at"]


def test_only_staff_and_admin_can_make_late_lounge_entries(app, setup):
    staff, _, spaces = setup
    assert late(app.test_client(), spaces).status_code == 401
    with staff.session_transaction() as auth:
        auth["role"] = "manager"
    assert late(staff, spaces).status_code == 403
    with staff.session_transaction() as auth:
        auth.update(user_id=2, username="admin_gilbert", role="admin")
    assert late(staff, spaces).status_code == 200
    for name in ("Boardroom", "Whole Hub", "Take Out"):
        assert late(staff, spaces, space=name).status_code == 400
    assert staff.post("/api/food-orders", json={
        "customer_name": "Food", "location": "Regular Lounge", "checkin_mode": "late",
        "arrival_time": "2026-10-27T09:00",
    }).status_code == 400
    with app.app_context():
        audit = SessionTimeEvent.query.one()
        assert audit.actor_id == 2 and audit.actor_name == "admin_gilbert" and audit.actor_role == "admin"


def test_capacity_and_reservations_cannot_be_bypassed_by_backdating(app, setup):
    staff, clock, spaces = setup
    with app.app_context():
        db.session.get(SpaceType, spaces["Premium Lounge"]).capacity = 1
        booking = BoardroomBooking(customer_name="Meeting", date=manila_date(clock.now()),
            start_time=wall_time(9), end_time=wall_time(10), number_of_people=3,
            booking_type="whole_hub", status="completed",
            started_at=datetime(2026, 10, 27, 1), ended_at=datetime(2026, 10, 27, 2))
        db.session.add(booking)
        db.session.commit()
        booking_id = booking.id
    assert late(staff, spaces, arrival_time="2026-10-27T09:30").status_code == 409
    # An arrival exactly when the completed reservation ended is valid.
    assert late(staff, spaces, arrival_time="2026-10-27T10:00").status_code == 200
    assert late(staff, spaces, arrival_time="2026-10-27T10:01").status_code == 409
    with app.app_context():
        booking = db.session.get(BoardroomBooking, booking_id)
        booking.booking_type = "boardroom"
        db.session.commit()
    assert late(staff, spaces, space="Regular Lounge", arrival_time="2026-10-27T09:30").status_code == 200
    with app.app_context():
        booking = db.session.get(BoardroomBooking, booking_id)
        booking.booking_type, booking.status = "whole_hub", "booked"
        booking.start_time, booking.end_time = wall_time(10), wall_time(11)
        db.session.commit()
    assert late(staff, spaces, space="Regular Lounge", arrival_time="2026-10-27T09:30").status_code == 409


def test_atomic_save_idempotency_and_failed_notifications(app, setup, monkeypatch):
    staff, _, spaces = setup
    original = SessionService._record_time_event
    def failed_audit(*args):
        original(*args)
        db.session.flush()
        raise RuntimeError("Simulated audit failure")
    monkeypatch.setattr(SessionService, "_record_time_event", staticmethod(failed_audit))
    assert late(staff, spaces).status_code == 500
    with app.app_context():
        assert CustomerSession.query.count() == SessionTimeEvent.query.count() == 0
    monkeypatch.setattr(SessionService, "_record_time_event", staticmethod(original))
    def failed_emit(*args, **kwargs):
        raise RuntimeError("Simulated socket failure")
    monkeypatch.setattr(socketio, "emit", failed_emit)
    payload = dict(customer_name="Carl", space_type_id=spaces["Regular Lounge"],
                   checkin_mode="late", arrival_time="2026-10-27T09:00")
    headers = {"Idempotency-Key": str(uuid4())}
    assert staff.post("/api/checkin", json=payload, headers=headers).status_code == 200
    assert staff.post("/api/checkin", json=payload, headers=headers).status_code == 409
    with app.app_context():
        assert CustomerSession.query.count() == SessionTimeEvent.query.count() == 1
    session_id = staff.get("/api/active-sessions").get_json()[0]["session_id"]
    assert staff.post(f"/api/sessions/{session_id}/cancel", json={"reason": "Wrong customer"}).status_code == 200
    assert staff.get("/api/sessions/cancellations").get_json()["data"][0]["has_time_history"] is True
    assert staff.get(f"/api/sessions/{session_id}/time-history").status_code == 200


def test_history_flags_do_not_add_a_query_per_customer_or_checkout(app, setup):
    staff, clock, spaces = setup
    def seed(count):
        with app.app_context():
            for _ in range(count):
                for status in ("active", "completed"):
                    row = CustomerSession(customer_name="Carl", space_type_id=spaces["Regular Lounge"],
                        time_in=clock.now() - timedelta(minutes=80), status=status)
                    db.session.add(row)
                    db.session.flush()
                    SessionService._record_time_event(row, "late_checkin", clock.now(), 1, "test_user", "staff", 0, Decimal(0))
                    if status == "completed":
                        db.session.add(Transaction(session_id=row.id, time_bill=15, food_bill=0, total_bill=15))
            db.session.commit()
    def select_counts():
        counts = []
        with app.app_context():
            for url in ("/api/active-sessions", "/api/checkout-records"):
                statements = []
                def record(_conn, _cursor, statement, _params, _context, _many):
                    if statement.lstrip().upper().startswith("SELECT"):
                        statements.append(statement)
                event.listen(db.engine, "before_cursor_execute", record)
                try:
                    response = staff.get(url)
                    assert response.status_code == 200
                    assert all(row["has_time_history"] for row in response.get_json())
                    counts.append(len(statements))
                finally:
                    event.remove(db.engine, "before_cursor_execute", record)
        return counts
    seed(1)
    one = select_counts()
    seed(24)
    assert select_counts() == one


def test_pages_offer_late_entry_only_for_lounges_and_keep_native_picker(setup):
    staff, _, _ = setup
    for url in ("/dashboard", "/dashboard?space=Regular+Lounge", "/dashboard?space=Premium+Lounge"):
        html = staff.get(url).get_data(as_text=True)
        assert 'type="datetime-local" id="lateArrivalTime"' in html
        assert html.index('id="lateCheckinToggle"') > html.index('id="checkinModal"')
        assert 'data-checkin-mode="late"' not in html
        assert '2026-10-27T02:20:00.000Z' in html
    for url in ("/dashboard?space=Boardroom", "/food-orders"):
        assert 'id="lateCheckinToggle"' not in staff.get(url).get_data(as_text=True)
