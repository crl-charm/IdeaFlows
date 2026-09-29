"""Food orders use checkout and sales history without lounge time or occupancy."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from time import time

import pytest

from app import create_app, db
from app.models import CustomerSession, InventoryItem, MenuItem, SpaceType, Transaction
from app.repositories.booking_repository import BookingRepository
from app.repositories.sales_repository import SalesRepository
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
            SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"), capacity=30),
            SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333"), capacity=30),
            SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")),
            SpaceType(name="Whole Hub", rate_per_minute=Decimal("8.3333")),
            SpaceType(name="Take Out", rate_per_minute=Decimal("0")),
            MenuItem(name="Coffee", price=Decimal("80.00"), category="Beverages",
                     inventory_mode="untracked", is_available=True),
        ])
        db.session.commit()
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff", last_activity=time())
    return client


def create_food_order(client, location, key):
    return client.post("/api/food-orders", json={"customer_name": "  Guest  ", "location": location},
                       headers={"Idempotency-Key": key})


def test_food_locations_do_not_use_lounge_capacity_or_timer(app, client):
    page = client.get("/food-orders")
    assert page.status_code == 200
    assert b"New Food Order" in page.data
    assert b"Take Out" in page.data
    assert b"Food Orders" in client.get("/dashboard").data

    locations = ("Regular Lounge", "Premium Lounge", "Boardroom", "Take Out")
    ids = []
    for location in locations:
        response = create_food_order(client, location, f"food-location-{location}")
        assert response.status_code == 201
        ids.append(response.get_json()["session_id"])
    duplicate = create_food_order(client, locations[0], "food-location-Regular Lounge")
    assert duplicate.status_code == 409
    assert duplicate.get_json()["duplicate"] is True

    active = client.get("/api/food-orders").get_json()
    assert {row["space_type"] for row in active} == set(locations)
    assert all(row["food_total"] == 0 for row in active)
    assert client.get("/api/active-sessions").get_json() == []
    assert all(row["occupied"] == 0 for row in client.get("/api/space-availability").get_json())
    with app.app_context():
        assert CustomerSession.query.count() == 4
        assert all(row.customer_name == "Guest" and row.service_mode == "food_only"
                   for row in CustomerSession.query.all())
        assert not BookingRepository().has_active_sessions()
        take_out_id = SpaceType.query.filter_by(name="Take Out").one().id

    assert client.post("/api/checkin", json={
        "customer_name": "Wrong mode", "number_of_people": 1, "space_type_id": take_out_id,
    }).status_code == 400
    assert client.post("/api/checkout/" + str(ids[0]),
                       json={"payment_method": "cash", "amount_tendered": "1"}).status_code == 400
    assert client.post("/api/food-orders", json={"customer_name": " ", "location": "Take Out"}).status_code == 400
    assert client.post("/api/food-orders", json={"customer_name": "Guest", "location": "Whole Hub"}).status_code == 400
    with app.app_context():
        assert Transaction.query.count() == 0


def test_food_checkout_reconciles_cash_gcash_and_daily_balance(app, client):
    ids = [create_food_order(client, location, f"food-pay-{location}").get_json()["session_id"]
           for location in ("Boardroom", "Take Out")]
    with app.app_context():
        menu_id = MenuItem.query.filter_by(name="Coffee").one().id
        for session_id in ids:
            db.session.get(CustomerSession, session_id).time_in = datetime.utcnow() - timedelta(days=2)
        db.session.commit()

    for session_id in ids:
        added = client.post("/api/add-order", json={
            "session_id": session_id, "items": [{"menu_item_id": menu_id, "quantity": 1}],
        }, headers={"Idempotency-Key": f"food-item-{session_id}"})
        assert added.status_code == 200
        order_page = client.get(f"/order/{session_id}")
        assert order_page.status_code == 200
        assert b"/food-orders" in order_page.data
        preview = client.get(f"/api/preview-checkout/{session_id}").get_json()
        assert preview["service_mode"] == "food_only"
        assert preview["time_bill"] == 0
        assert preview["food_bill"] == preview["total_bill"] == 80

    assert client.get("/api/active-sessions").get_json() == []
    assert {row["food_total"] for row in client.get("/api/food-orders").get_json()} == {80}
    stats = client.get("/admin/daily-balance/api/today-stats")
    assert stats.status_code == 200
    assert stats.get_json()["data"]["expected_to_collect"] == 160

    cash = client.post(f"/api/checkout/{ids[0]}", json={
        "payment_method": "cash", "amount_tendered": "100.00",
    }, headers={"Idempotency-Key": "food-cash-checkout"})
    discount_item_id = client.get(f"/api/session-orders/{ids[1]}?include_done=1").get_json()["orders"][0]["id"]
    gcash = client.post(f"/api/checkout/{ids[1]}", json={
        "payment_method": "gcash", "discount_type": "senior", "discount_item_id": discount_item_id,
    }, headers={"Idempotency-Key": "food-gcash-checkout"})
    assert cash.status_code == gcash.status_code == 200
    assert cash.get_json()["change_given"] == 20
    assert cash.get_json()["time_bill"] == gcash.get_json()["time_bill"] == 0
    assert gcash.get_json()["discount_amount"] == 16
    assert client.post(f"/api/checkout/{ids[0]}", json={
        "payment_method": "cash", "amount_tendered": "100.00",
    }).status_code == 400
    assert client.get("/api/food-orders").get_json() == []

    with app.app_context():
        txs = Transaction.query.order_by(Transaction.id).all()
        assert len(txs) == 2
        assert [(tx.payment_method, tx.total_bill, tx.time_bill, tx.collected_by) for tx in txs] == [
            ("cash", Decimal("80.00"), Decimal("0.00"), "test_user"),
            ("gcash", Decimal("64.00"), Decimal("0.00"), "test_user"),
        ]
        day = manila_date(txs[0].created_at)
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["cash_total"] == 80
        assert ledger["gcash_total"] == 64
        assert ledger["total_revenue"] == 144
        assert ledger["total_sessions"] == 0
        assert ledger["total_orders"] == 2

    report = client.get(f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}")
    assert report.status_code == 200
    row = report.get_json()["data"][0]
    assert row["cash_total"] == 80
    assert row["gcash_total"] == 64
    assert row["total_revenue"] == 144
    assert row["total_sessions"] == 0
    csv = client.get(f"/admin/daily-balance/api/reports/export-csv?start_date={day}&end_date={day}")
    assert csv.status_code == 200
    assert "₱144.00" in csv.data.decode("utf-8")

    records = client.get("/api/checkout-records").get_json()
    assert len(records) == 2
    assert all(record["service_mode"] == "food_only" and record["seconds_spent"] is None
               and record["time_bill"] == 0 for record in records)
    receipt = client.get(f"/receipt/{ids[0]}")
    assert receipt.status_code == 200
    assert b"Food only" in receipt.data
    assert b"Duration:" not in receipt.data
    assert b"Time Charges:" not in receipt.data

    with app.app_context():
        cash_tx, gcash_tx = Transaction.query.order_by(Transaction.id).all()
        cash_tx.created_at = datetime(2026, 9, 28, 15, 59)  # 23:59 Manila
        gcash_tx.created_at = datetime(2026, 9, 28, 16, 1)  # 00:01 Manila next day
        db.session.commit()
        rows = SalesRepository().daily_ledger(date(2026, 9, 28), date(2026, 9, 29))
        assert rows[date(2026, 9, 28)]["cash_total"] == 80
        assert rows[date(2026, 9, 28)]["gcash_total"] == 0
        assert rows[date(2026, 9, 29)]["cash_total"] == 0
        assert rows[date(2026, 9, 29)]["gcash_total"] == 64


def test_food_order_reserves_and_returns_existing_inventory(app, client):
    session_id = create_food_order(client, "Take Out", "food-stock-start").get_json()["session_id"]
    with app.app_context():
        menu = MenuItem.query.filter_by(name="Coffee").one()
        menu.inventory_mode = "direct"
        stock = InventoryItem(menu_item_id=menu.id, stock_qty=1, unit="pieces")
        db.session.add(stock)
        db.session.commit()
        menu_id, stock_id = menu.id, stock.id

    body = {"session_id": session_id, "items": [{"menu_item_id": menu_id, "quantity": 1}]}
    first = client.post("/api/add-order", json=body, headers={"Idempotency-Key": "food-stock-first"})
    assert first.status_code == 200
    second = client.post("/api/add-order", json=body, headers={"Idempotency-Key": "food-stock-second"})
    assert second.status_code == 409
    with app.app_context():
        assert db.session.get(InventoryItem, stock_id).stock_qty == 0

    order_item_id = client.get(f"/api/session-orders/{session_id}?include_done=1").get_json()["orders"][0]["id"]
    voided = client.delete(f"/api/void-item/{order_item_id}", json={
        "return_stock": True, "reason": "Customer changed order",
    }, headers={"Idempotency-Key": "food-stock-void"})
    assert voided.status_code == 200
    with app.app_context():
        assert db.session.get(InventoryItem, stock_id).stock_qty == 1
    assert client.get(f"/api/preview-checkout/{session_id}").get_json()["total_bill"] == 0


def test_every_food_payment_method_reconciles_to_total_checkout(app, client):
    with app.app_context():
        menu_id = MenuItem.query.filter_by(name="Coffee").one().id

    methods = ("cash", "gcash", "bdo", "bpi", "queenbank")
    for method in methods:
        started = create_food_order(client, "Take Out", f"food-{method}-start")
        assert started.status_code == 201, (method, started.get_json())
        session_id = started.get_json()["session_id"]
        order = client.post("/api/add-order", json={
            "session_id": session_id, "items": [{"menu_item_id": menu_id, "quantity": 1}],
        }, headers={"Idempotency-Key": f"food-{method}-order"})
        assert order.status_code == 200
        payment = {"payment_method": method}
        if method == "cash":
            payment["amount_tendered"] = "80.00"
        checkout = client.post(f"/api/checkout/{session_id}", json=payment,
                               headers={"Idempotency-Key": f"food-all-methods-{method}-checkout"})
        assert checkout.status_code == 200, (method, checkout.get_json())
        assert checkout.get_json()["total_bill"] == 80

    with app.app_context():
        txs = Transaction.query.all()
        assert len(txs) == len(methods)
        day = manila_date(txs[0].created_at)
    report = client.get(f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}")
    assert report.status_code == 200
    row = report.get_json()["data"][0]
    assert row["total_revenue"] == 400
    assert row["cash_on_hand"] == 80
    for method in methods:
        assert row[f"{method}_total"] == 80
        assert row[f"{method}_count"] == 1
        assert row["checkout_methods"][method] == 80

    records = client.get("/api/checkout-records").get_json()
    assert len(records) == 5
    assert sum(record["total_bill"] for record in records) == row["total_revenue"]
