"""Public bills share checkout calculations without granting staff access."""

from datetime import datetime, timedelta
from decimal import Decimal
from time import time
from uuid import uuid4

import pytest
from sqlalchemy import event

from app import create_app, db, socketio
from app.core import get_notifier
from app.core.realtime import PUBLIC_CUSTOMERS_NAMESPACE
from app.core.socketio_handlers import emit_inventory_update
from app.models import BoardroomBooking, CustomerSession, MenuItem, Order, OrderItem, SpaceType, Transaction
from app.repositories.booking_repository import BookingRepository
from app.repositories.session_repository import SessionRepository
from app.services.booking_service import BookingService
from app.services.session_service import SessionService


class Clock:
    def __init__(self):
        self.value = datetime(2026, 10, 26, 6, 30)

    def now(self):
        return self.value


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


@pytest.fixture
def setup(app, monkeypatch):
    import app.routes.session_routes as routes

    clock = Clock()
    service = SessionService(SessionRepository(), clock, get_notifier())
    monkeypatch.setattr(routes, "_service", service)
    with app.app_context():
        for name in ("Regular Lounge", "Premium Lounge", "Boardroom", "Whole Hub", "Take Out"):
            db.session.add(SpaceType(name=name, rate_per_minute=1, capacity=30))
        db.session.add(MenuItem(name="Meal", price=Decimal("120.00"), inventory_mode="untracked"))
        db.session.commit()
        spaces = {s.name: s.id for s in SpaceType.query.all()}
    staff = app.test_client()
    with staff.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    return clock, service, spaces, staff


def visit(clock, space_id, **values):
    row = CustomerSession(customer_name="Carl", space_type_id=space_id,
                          time_in=clock.now() - timedelta(minutes=59),
                          status="active", service_mode="timed")
    for key, value in values.items():
        setattr(row, key, value)
    db.session.add(row)
    db.session.flush()
    return row


def meal(session_id, *, price="82.00", quantity=2, done=False):
    order = Order(customer_session_id=session_id, handled_by=1, status="done" if done else "preparing")
    db.session.add(order)
    db.session.flush()
    item = OrderItem(order_id=order.id, menu_item_id=1, quantity=quantity, price=Decimal(price),
                     base_price=Decimal("100.00"), name_snapshot="Original Meal", no_rice=True,
                     unit_deduction=Decimal("18.00"), status="done" if done else "preparing")
    db.session.add(item)
    return item


def booking(clock, **values):
    local = clock.now() + timedelta(hours=8)
    row = BoardroomBooking(customer_name="Boardroom Guest", date=local.date(),
                          start_time=local.replace(hour=14, minute=0).time(),
                          end_time=local.replace(hour=16, minute=0).time(),
                          number_of_people=3, purpose="PRIVATE PURPOSE", booked_by="PRIVATE STAFF")
    for key, value in values.items():
        setattr(row, key, value)
    db.session.add(row)
    db.session.commit()
    return row


def assert_signal(client):
    assert client.get_received(namespace=PUBLIC_CUSTOMERS_NAMESPACE) == [{
        "name": "current_customers_changed", "args": [{}], "namespace": PUBLIC_CUSTOMERS_NAMESPACE,
    }]


def test_public_page_and_feed_are_read_only_uncached_and_allowlisted(app, setup):
    clock, _, spaces, _ = setup
    with app.app_context():
        visit(clock, spaces["Regular Lounge"], school="PRIVATE SCHOOL", course="PRIVATE COURSE", credit_balance=77)
        visit(clock, spaces["Premium Lounge"])
        visit(clock, spaces["Regular Lounge"], status="completed")
        visit(clock, spaces["Regular Lounge"], status="cancelled")
        visit(clock, spaces["Whole Hub"])
        visit(clock, spaces["Premium Lounge"], service_mode="food_only")
        visit(clock, spaces["Take Out"], service_mode="food_only")
        booking(clock)  # A future/unstarted booking has no active visit.

    public = app.test_client()
    for path in ("/current-customer", "/api/current-customers"):
        response = public.get(path)
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "no-store"
        assert response.headers["CDN-Cache-Control"] == "no-store"
        assert response.headers["Cloudflare-CDN-Cache-Control"] == "no-store"
        assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
        assert "Set-Cookie" not in response.headers
        assert public.post(path, json={}).status_code == 405
    page = public.get("/current-customer").text
    assert "Search your name" in page and "current-customers.js" in page
    assert "layout.html" not in page and "/api/session-status" not in page and "Cash Boxes" not in page
    payload = public.get("/api/current-customers").get_json()
    assert payload["as_of"] == "2026-10-26T06:30:00+00:00"
    assert len(payload["customers"]) == 2  # Duplicate names are separate visits.
    assert {r["space_type"] for r in payload["customers"]} == {"Regular Lounge", "Premium Lounge"}
    assert set(payload["customers"][0]) == {
        "session_id", "customer_name", "space_type", "time_in", "seconds_used", "paused",
        "food_items", "time_bill", "food_bill", "carried_food_bill", "total_bill",
    }
    assert "PRIVATE" not in str(payload)
    for path, method in (("/api/checkin", "post"), ("/api/add-order", "post"),
                         ("/api/sessions/1/pause", "post"), ("/api/sessions/1/resume", "post"),
                         ("/api/checkout/1", "post"), ("/api/void-item/1", "delete")):
        assert getattr(public, method)(path, json={}).status_code == 401


@pytest.mark.parametrize("space,expected_time", [("Regular Lounge", 10), ("Premium Lounge", 20), ("Boardroom", 691.34)])
def test_public_amounts_match_checkout_including_pauses_bookings_and_saved_food(app, setup, space, expected_time):
    clock, service, spaces, _ = setup
    with app.app_context():
        row = visit(clock, spaces[space], time_in=clock.now() - timedelta(minutes=75))
        if space != "Boardroom":
            row.paused_at = clock.now() - timedelta(minutes=5)
            row.paused_microseconds = 10 * 60_000_000
        meal(row.id, done=True)
        db.session.get(MenuItem, 1).price = Decimal("999.00")
        if space == "Boardroom":
            booking(clock, status="active", session_id=row.id, hourly_rate=Decimal("345.67"))
        db.session.commit()
        preview = service.preview_checkout(row.id)
    response = app.test_client().get("/api/current-customers").get_json()["customers"][0]
    assert response["time_bill"] == preview["time_bill"] == expected_time
    assert response["food_bill"] == preview["food_bill"] == 164
    assert response["total_bill"] == preview["total_bill"]
    assert response["food_items"] == [{"item_name": "Original Meal (No rice)", "quantity": 2,
                                       "unit_price": 82, "line_total": 164}]
    if space != "Boardroom":
        assert response["paused"] is True
        assert response["seconds_used"] == 3600


def test_carried_food_and_retained_time_are_explained_without_applying_credit(app, setup):
    clock, service, spaces, _ = setup
    with app.app_context():
        row = visit(clock, spaces["Premium Lounge"], retained_time_bill=Decimal("12.34"), credit_balance=77)
        meal(row.id)
        original = Transaction(session_id=row.id, time_bill=Decimal("12.34"), food_bill=Decimal("45.67"),
                               total_bill=Decimal("58.01"), is_voided=True)
        db.session.add(original)
        db.session.flush()
        row.voided_transaction_id = original.id
        db.session.commit()
        preview = service.preview_checkout(row.id)
    row = app.test_client().get("/api/current-customers").get_json()["customers"][0]
    assert row["carried_food_bill"] == preview["carried_food_bill"] == 45.67
    assert row["time_bill"] == 12.34
    assert row["food_bill"] == 209.67
    assert row["total_bill"] == preview["total_bill"] == 222.01
    assert "credit_balance" not in row


def test_staff_changes_publish_only_after_success_and_checkout_removes_visit(app, setup):
    clock, _, spaces, staff = setup
    public = socketio.test_client(app, namespace=PUBLIC_CUSTOMERS_NAMESPACE)
    viewer = app.test_client()
    response = staff.post("/api/checkin", json={"customer_name": "Carl", "space_type_id": spaces["Regular Lounge"]})
    assert response.status_code == 200
    session_id = response.get_json()["session_id"]
    assert_signal(public)
    clock.value += timedelta(minutes=59)
    assert staff.post(f"/api/sessions/{session_id}/pause").status_code == 200
    assert_signal(public)
    assert staff.post(f"/api/sessions/{session_id}/pause").status_code == 409
    assert public.get_received(namespace=PUBLIC_CUSTOMERS_NAMESPACE) == []
    clock.value += timedelta(minutes=6)
    added = staff.post("/api/add-order", json={"session_id": session_id, "items": [{"menu_item_id": 1, "quantity": 2}]})
    assert added.status_code == 200
    assert_signal(public)
    row = viewer.get("/api/current-customers").get_json()["customers"][0]
    assert row["paused"] is True and row["time_bill"] == 10 and row["food_bill"] == 240
    with app.app_context():
        item_id = OrderItem.query.filter_by(order_id=added.get_json()["order_id"]).one().id
    cancelled = staff.delete(f"/api/void-item/{item_id}", json={"reason": "Customer changed order"},
                             headers={"Idempotency-Key": str(uuid4())})
    assert cancelled.status_code == 200
    assert_signal(public)
    assert staff.put(f"/api/order-item-status/{item_id}").status_code == 200
    assert_signal(public)
    assert staff.post(f"/api/session-served/{session_id}").status_code == 200
    assert_signal(public)
    row = viewer.get("/api/current-customers").get_json()["customers"][0]
    assert row["food_bill"] == 120 and row["total_bill"] == 130
    assert staff.post(f"/api/sessions/{session_id}/resume").status_code == 200
    assert_signal(public)
    clock.value += timedelta(minutes=2)
    assert viewer.get("/api/current-customers").get_json()["customers"][0]["time_bill"] == 15
    result = staff.post(f"/api/checkout/{session_id}", json={"payment_method": "cash", "amount_tendered": "200"})
    assert result.status_code == 200 and result.get_json()["total_bill"] == 135
    assert_signal(public)
    assert viewer.get("/api/current-customers").get_json()["customers"] == []
    public.disconnect(namespace=PUBLIC_CUSTOMERS_NAMESPACE)


def test_booking_start_and_extension_publish_and_unused_cancellation_disappears(app, setup):
    clock, _, spaces, staff = setup
    public = socketio.test_client(app, namespace=PUBLIC_CUSTOMERS_NAMESPACE)
    viewer = app.test_client()
    with app.app_context():
        row = booking(clock)
        booking_id = row.id
        service = BookingService(repo=BookingRepository(), clock=clock, notifier=get_notifier())
        result = service.start_booking(booking_id, "Test Staff")
        assert isinstance(result, dict), result
    assert_signal(public)
    assert viewer.get("/api/current-customers").get_json()["customers"][0]["time_bill"] == 500
    with app.app_context():
        assert isinstance(service.extend_booking(booking_id, 30, "Test Staff"), dict)
    assert_signal(public)
    assert viewer.get("/api/current-customers").get_json()["customers"][0]["time_bill"] == 750
    checked = staff.post("/api/checkin", json={"customer_name": "Unused", "space_type_id": spaces["Regular Lounge"]})
    assert checked.status_code == 200
    assert_signal(public)
    session_id = checked.get_json()["session_id"]
    assert staff.post(f"/api/sessions/{session_id}/cancel", json={"reason": "Mistaken check-in"}).status_code == 200
    assert_signal(public)
    assert all(c["session_id"] != session_id for c in viewer.get("/api/current-customers").get_json()["customers"])
    public.disconnect(namespace=PUBLIC_CUSTOMERS_NAMESPACE)


def test_public_socket_cannot_join_private_namespace_or_receive_private_events(app, setup):
    _, _, _, staff = setup
    anonymous = app.test_client()
    assert not socketio.test_client(app, flask_test_client=anonymous).is_connected()
    public = socketio.test_client(app, flask_test_client=anonymous, namespace=PUBLIC_CUSTOMERS_NAMESPACE)
    assert public.is_connected(namespace=PUBLIC_CUSTOMERS_NAMESPACE)
    private = socketio.test_client(app, flask_test_client=staff)
    assert private.is_connected()
    private.get_received()
    with app.app_context():
        emit_inventory_update("change", {"id": 1, "private": "PRIVATE DATA"})
    assert any(e["name"] == "inventory_update" for e in private.get_received())
    assert public.get_received(namespace=PUBLIC_CUSTOMERS_NAMESPACE) == []
    public.emit("session_heartbeat", {}, namespace=PUBLIC_CUSTOMERS_NAMESPACE)
    public.emit("checkin", {"customer_name": "Forged"}, namespace=PUBLIC_CUSTOMERS_NAMESPACE)
    with app.app_context():
        assert CustomerSession.query.count() == 0
    private.disconnect()
    public.disconnect(namespace=PUBLIC_CUSTOMERS_NAMESPACE)


def test_failed_public_notification_does_not_fail_committed_staff_action(app, setup, monkeypatch, caplog):
    _, _, spaces, staff = setup
    original_emit = socketio.emit

    def unavailable(event_name, *args, **kwargs):
        if kwargs.get("namespace") == PUBLIC_CUSTOMERS_NAMESPACE:
            raise RuntimeError("Simulated notification outage")
        return original_emit(event_name, *args, **kwargs)

    monkeypatch.setattr(socketio, "emit", unavailable)
    result = staff.post("/api/checkin", json={"customer_name": "Saved", "space_type_id": spaces["Regular Lounge"]})
    assert result.status_code == 200
    assert app.test_client().get("/api/current-customers").get_json()["customers"][0]["customer_name"] == "Saved"
    assert "Public bill notification unavailable" in caplog.text


def test_snapshot_queries_are_batched(app, setup):
    clock, _, spaces, _ = setup
    with app.app_context():
        for _ in range(25):
            row = visit(clock, spaces["Regular Lounge"])
            meal(row.id)
        db.session.commit()
        db.session.remove()
        selects = []

        def collect(_conn, _cursor, statement, _params, _context, _many):
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        engine = db.engine
        event.listen(engine, "after_cursor_execute", collect)
        try:
            response = app.test_client().get("/api/current-customers")
        finally:
            event.remove(engine, "after_cursor_execute", collect)
        assert response.status_code == 200
        assert len(response.get_json()["customers"]) == 25
        assert len(selects) <= 7, selects


def test_shared_ip_viewers_do_not_hit_the_default_100_request_limit(app, setup):
    viewers = [app.test_client() for _ in range(10)]
    for index in range(110):
        assert viewers[index % len(viewers)].get("/api/current-customers").status_code == 200
