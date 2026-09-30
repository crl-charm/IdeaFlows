"""Selected pre-order meal removals use one price from cart to Daily Balance."""

import json
from decimal import Decimal
from time import time

import pytest
from sqlalchemy import inspect, text

from app import create_app, db
from app.db.migrator import SchemaMigrator
from app.models import MenuItem, Order, OrderItem, SpaceType, Transaction
from app.models.inventory import InventoryItem
from app.models.menu_category import MenuCategory
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
            MenuCategory(name="Main Dish"),
            SpaceType(name="Take Out", rate_per_minute=Decimal("0")),
        ])
        db.session.commit()
    test_client = app.test_client()
    with test_client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="admin", last_activity=time())
    return test_client


def create_meal(client, **overrides):
    data = {"name": "Silog", "category": "Main Dish", "price": "100.00",
            "inventory_mode": "prepared", "stock_quantity": "8", "stock_threshold": "2",
            "can_remove_rice": "true", "can_remove_egg": "true"}
    data.update(overrides)
    return client.post("/admin/menu/api/items", data=data)


def start_food_order(client, key):
    response = client.post("/api/food-orders", json={"customer_name": "Guest", "location": "Take Out"},
                           headers={"Idempotency-Key": key})
    assert response.status_code == 201, response.get_json()
    return response.get_json()["session_id"]


def test_selected_options_reconcile_orders_receipts_and_daily_balance(app, client):
    created = create_meal(client)
    assert created.status_code == 201, created.get_json()
    meal_id = created.get_json()["data"]["id"]
    owner_item = next(row for row in client.get("/admin/menu/api/items/all").get_json()["data"] if row["id"] == meal_id)
    assert owner_item["can_remove_rice"] and owner_item["can_remove_egg"]
    menu_item = next(row for row in client.get("/api/menu").get_json() if row["id"] == meal_id)
    assert menu_item["can_remove_rice"] and menu_item["can_remove_egg"]

    gcash_session = start_food_order(client, "mod-gcash-session")
    lines = [
        {"menu_item_id": meal_id, "quantity": 2, "expected_base_price": "100.00"},
        {"menu_item_id": meal_id, "quantity": 1, "no_rice": True, "expected_base_price": "100.00"},
        {"menu_item_id": meal_id, "quantity": 1, "no_egg": True, "expected_base_price": "100.00"},
        {"menu_item_id": meal_id, "quantity": 2, "no_rice": True, "no_egg": True,
         "expected_base_price": "100.00"},
    ]
    placed = client.post("/api/add-order", json={"session_id": gcash_session, "items": lines},
                         headers={"Idempotency-Key": "mod-mixed-order"})
    assert placed.status_code == 200, placed.get_json()
    assert client.post("/api/add-order", json={"session_id": gcash_session, "items": lines},
                       headers={"Idempotency-Key": "mod-mixed-order"}).status_code == 409
    kitchen = client.get(f"/api/session-orders/{gcash_session}").get_json()
    assert kitchen["food_total"] == 492
    assert {row["item_name"] for row in kitchen["orders"]} == {
        "Silog", "Silog (No rice)", "Silog (No egg)", "Silog (No rice, No egg)"}
    assert client.get(f"/api/preview-checkout/{gcash_session}").get_json()["food_bill"] == 492

    with app.app_context():
        order = db.session.get(Order, placed.get_json()["order_id"])
        assert (order.food_total_before, order.food_total_after) == (Decimal("0.00"), Decimal("492.00"))
        assert {(item.no_rice, item.no_egg): (item.quantity, item.base_price, item.unit_deduction, item.price)
                for item in order.items} == {
            (False, False): (2, Decimal("100.00"), Decimal("0.00"), Decimal("100.00")),
            (True, False): (1, Decimal("100.00"), Decimal("18.00"), Decimal("82.00")),
            (False, True): (1, Decimal("100.00"), Decimal("18.00"), Decimal("82.00")),
            (True, True): (2, Decimal("100.00"), Decimal("36.00"), Decimal("64.00")),
        }
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 2

    changed = client.patch(f"/admin/menu/api/items/{meal_id}", data={"price": "130.00"})
    assert changed.status_code == 200, changed.get_json()
    assert client.get(f"/api/preview-checkout/{gcash_session}").get_json()["food_bill"] == 492
    gcash = client.post(f"/api/checkout/{gcash_session}", json={"payment_method": "gcash"},
                        headers={"Idempotency-Key": "mod-gcash-checkout"})
    assert gcash.status_code == 200, gcash.get_json()
    assert gcash.get_json()["food_bill"] == gcash.get_json()["total_bill"] == 492
    receipt = client.get(f"/receipt/{gcash_session}")
    assert receipt.status_code == 200
    assert b"No rice" in receipt.data and b"No egg" in receipt.data

    cash_session = start_food_order(client, "mod-cash-session")
    cash_order = client.post("/api/add-order", json={"session_id": cash_session, "items": [
        {"menu_item_id": meal_id, "quantity": 1, "no_egg": True, "expected_base_price": "130.00"}
    ]}, headers={"Idempotency-Key": "mod-cash-order"})
    assert cash_order.status_code == 200, cash_order.get_json()
    assert client.post(f"/api/checkout/{cash_session}", json={
        "payment_method": "cash", "amount_tendered": "120.00"},
        headers={"Idempotency-Key": "mod-cash-checkout"}).status_code == 200

    with app.app_context():
        txs = Transaction.query.order_by(Transaction.id).all()
        assert [(tx.payment_method, tx.food_bill) for tx in txs] == [
            ("gcash", Decimal("492.00")), ("cash", Decimal("112.00"))]
        day = manila_date(txs[0].created_at)
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert (ledger["gcash_total"], ledger["cash_total"], ledger["total_revenue"]) == (492, 112, 604)
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 1
    report = client.get(f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}")
    assert report.status_code == 200
    row = report.get_json()["data"][0]
    assert (row["gcash_total"], row["cash_total"], row["total_revenue"]) == (492, 112, 604)


def test_invalid_options_price_and_recipe_are_rejected_without_stock_change(app, client):
    assert create_meal(client, name="Too cheap", price="36.00").status_code == 400
    created = create_meal(client, name="Rice only", can_remove_egg="false", stock_quantity="2")
    assert created.status_code == 201, created.get_json()
    meal_id = created.get_json()["data"]["id"]
    assert client.patch(f"/admin/menu/api/items/{meal_id}", data={"price": "18.00"}).status_code == 400
    session_id = start_food_order(client, "mod-invalid-session")
    for index, row in enumerate((
        {"menu_item_id": meal_id, "quantity": 1, "no_egg": True},
        {"menu_item_id": meal_id, "quantity": 1, "no_rice": "true"},
        {"menu_item_id": meal_id, "quantity": 1, "no_rice": True, "unknown": 1},
        {"menu_item_id": meal_id, "quantity": 1, "expected_base_price": "99.00"},
    )):
        response = client.post("/api/add-order", json={"session_id": session_id, "items": [row]},
                               headers={"Idempotency-Key": f"mod-invalid-{index}"})
        assert response.status_code in {400, 409}, response.get_json()
    too_many = client.post("/api/add-order", json={"session_id": session_id, "items": [
        {"menu_item_id": meal_id, "quantity": 2},
        {"menu_item_id": meal_id, "quantity": 1, "no_rice": True},
    ]}, headers={"Idempotency-Key": "mod-variants-too-many"})
    assert too_many.status_code == 409, too_many.get_json()
    with app.app_context():
        assert Order.query.count() == OrderItem.query.count() == 0
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 2


def test_recipe_meal_option_uses_finished_serving_without_changing_raw_stock(app, client):
    created = create_meal(client, name="Recipe Silog", inventory_mode="recipe", stock_quantity="1",
                          recipe_ingredients=json.dumps([{"name": "Rice", "quantity": "1", "unit": "pieces"}]))
    assert created.status_code == 201, created.get_json()
    meal_id = created.get_json()["data"]["id"]
    with app.app_context():
        raw_id = MenuItem.query.filter_by(name="Rice").one().id
        InventoryItem.query.filter_by(menu_item_id=raw_id).one().stock_qty = 10
        db.session.commit()
    session_id = start_food_order(client, "mod-recipe-session")
    placed = client.post("/api/add-order", json={"session_id": session_id, "items": [
        {"menu_item_id": meal_id, "quantity": 1, "no_rice": True, "no_egg": True}
    ]}, headers={"Idempotency-Key": "mod-recipe-order"})
    assert placed.status_code == 200, placed.get_json()
    with app.app_context():
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 0
        assert InventoryItem.query.filter_by(menu_item_id=raw_id).one().stock_qty == 10
        assert db.session.get(Order, placed.get_json()["order_id"]).items[0].price == Decimal("64.00")


def test_voiding_one_customized_serving_returns_one_stock_unit(app, client):
    created = create_meal(client, stock_quantity="3")
    meal_id = created.get_json()["data"]["id"]
    session_id = start_food_order(client, "mod-void-session")
    added = client.post("/api/add-order", json={"session_id": session_id, "items": [
        {"menu_item_id": meal_id, "quantity": 2, "no_rice": True, "no_egg": True}
    ]}, headers={"Idempotency-Key": "mod-void-order"})
    assert added.status_code == 200
    item_id = client.get(f"/api/session-orders/{session_id}").get_json()["orders"][0]["id"]
    voided = client.delete(f"/api/void-item/{item_id}", json={
        "return_stock": True, "reason": "Customer changed order"},
        headers={"Idempotency-Key": "mod-void-serving"})
    assert voided.status_code == 200, voided.get_json()
    with app.app_context():
        assert db.session.get(OrderItem, item_id).quantity == 1
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 2
    assert client.get(f"/api/preview-checkout/{session_id}").get_json()["food_bill"] == 64


def test_existing_tables_gain_modifier_columns_with_safe_defaults(app, isolated_database):
    columns = {
        "menu_items": ("can_remove_rice", "can_remove_egg"),
        "order_items": ("name_snapshot", "base_price", "no_rice", "no_egg", "unit_deduction"),
        "orders": ("food_total_before", "food_total_after"),
    }
    with app.app_context():
        menu = MenuItem(name="Existing meal", price=Decimal("100.00"), category="Main Dish")
        db.session.add(menu)
        db.session.commit()
        menu_id = menu.id
        for table, names in columns.items():
            for name in names:
                db.session.execute(text(f"ALTER TABLE {table} DROP COLUMN {name}"))
        db.session.commit()
        SchemaMigrator(db, app).run()
        SchemaMigrator(db, app).run()
        inspector = inspect(db.engine)
        for table, names in columns.items():
            assert set(names) <= {column["name"] for column in inspector.get_columns(table)}
        db.session.expire_all()
        existing = db.session.get(MenuItem, menu_id)
        assert existing.can_remove_rice is False and existing.can_remove_egg is False
