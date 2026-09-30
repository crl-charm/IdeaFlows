from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app import create_app, db
from app.core import get_notifier
from app.models import CustomerSession, MenuItem, Order, OrderItem, SpaceType
from app.models.inventory import InventoryAction, InventoryItem, InventoryLog
from app.repositories.order_repository import OrderRepository
from app.repositories.sales_repository import SalesRepository
from app.services.order_service import OrderService
from app.utils.dates import manila_date, manila_day_bounds


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


@pytest.fixture
def client(app):
    with app.app_context():
        db.session.add(SpaceType(id=1, name="Take Out", capacity=0, rate_per_minute=0))
        db.session.commit()
    browser = app.test_client()
    with browser.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff",
                    last_activity=datetime.now(UTC).timestamp())
    return browser


def meal(app, name="Audit Meal", mode="prepared"):
    with app.app_context():
        item = MenuItem(name=name, price=80, category="Main Dish", inventory_mode=mode,
                        is_available=True)
        db.session.add(item)
        db.session.flush()
        if mode == "prepared":
            db.session.add(InventoryItem(menu_item_id=item.id, stock_qty=0, unit="servings"))
        db.session.commit()
        return item.id


def add_batch(client, meal_id, amount, key):
    response = client.post(f"/inventory/api/menu-items/{meal_id}/action",
                           json={"action": "add", "quantity": amount},
                           headers={"Idempotency-Key": key})
    assert response.status_code == 200, response.get_json()


def order(app, client, meal_id, customer, servings):
    with app.app_context():
        sess = CustomerSession(customer_name=customer, space_type_id=1,
                               service_mode="food_only", number_of_people=1, status="active")
        db.session.add(sess)
        db.session.commit()
        session_id = sess.id
    response = client.post("/api/add-order", json={"session_id": session_id,
        "items": [{"menu_item_id": meal_id, "quantity": servings}]},
        headers={"Idempotency-Key": f"audit-order-{customer}-{servings}"})
    assert response.status_code == 200, response.get_json()
    return session_id, response.get_json()["order_id"]


def test_daily_batches_customers_and_checkout_money_reconcile(app, client):
    meal_id = meal(app)
    add_batch(client, meal_id, 10, "audit-batch-ten")
    add_batch(client, meal_id, 5, "audit-batch-five")
    first_session, _ = order(app, client, meal_id, "Ana", 4)
    _, _ = order(app, client, meal_id, "Bea", 2)

    day = manila_date(datetime.utcnow())
    summary = client.get("/inventory/api/meal-day-summary").get_json()
    row = next(row for row in summary["data"] if row["meal_id"] == meal_id)
    assert summary["date"] == day.isoformat()
    assert (row["opening"], row["added"], row["placed"], row["cancelled"],
            row["ordered"], row["available"], row["remaining"]) == (0, 15, 6, 0, 6, 15, 9)
    assert row["history_complete"] is True
    detail = client.get(f"/inventory/api/menu-items/{meal_id}/daily-audit?date={day}").get_json()
    assert {entry["customer"]: entry["placed"] for entry in detail["orders"]} == {"Ana": 4, "Bea": 2}
    assert all(entry["checkout_status"] == "Not checked out" for entry in detail["orders"])
    assert [entry["quantity"] for entry in detail["batches"]] == [10, 5]
    assert all(entry["actor"] == "Test User" for entry in detail["batches"])

    with app.app_context():
        assert SalesRepository().daily_ledger(day, day)[day]["total_revenue"] == 0
    paid = client.post(f"/api/checkout/{first_session}", json={
        "payment_method": "gcash"}, headers={"Idempotency-Key": "audit-gcash-checkout"})
    assert paid.status_code == 200, paid.get_json()
    detail = client.get(f"/inventory/api/menu-items/{meal_id}/daily-audit?date={day}").get_json()
    assert {entry["customer"]: entry["checkout_status"] for entry in detail["orders"]} == {
        "Ana": "Checked out", "Bea": "Not checked out"}
    with app.app_context():
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["gcash_total"] == 320
        assert ledger["cash_total"] == 0
        assert ledger["total_revenue"] == 320


def test_voids_and_manual_changes_are_not_customer_orders(app, client):
    meal_id = meal(app)
    add_batch(client, meal_id, 10, "audit-void-batch")
    _, order_id = order(app, client, meal_id, "Cara", 3)
    with app.app_context():
        item_id = Order.query.get(order_id).items[0].id
        service = OrderService(OrderRepository(), get_notifier())
        returned = service.void_item(item_id, actor=1, request_key="audit-return-one",
                                     reason="Customer changed mind", return_stock=True)
        unreturned = service.void_item(item_id, actor=1, request_key="audit-no-return-one",
                                       reason="Prepared meal discarded", return_stock=False)
        assert not isinstance(returned, tuple) and not isinstance(unreturned, tuple)
    waste = client.post(f"/inventory/api/menu-items/{meal_id}/action", json={
        "action": "waste", "quantity": 1, "reason": "Dropped"},
        headers={"Idempotency-Key": "audit-waste-one"})
    assert waste.status_code == 200
    correction = client.post(f"/inventory/api/menu-items/{meal_id}/action", json={
        "action": "count", "quantity": 5, "reason": "Physical count"},
        headers={"Idempotency-Key": "audit-count-five"})
    assert correction.status_code == 200
    day = manila_date(datetime.utcnow())
    detail = client.get(f"/inventory/api/menu-items/{meal_id}/daily-audit?date={day}").get_json()
    row = detail["summary"]
    assert (row["placed"], row["cancelled"], row["ordered"], row["not_returned"],
            row["remaining"], row["other_change"]) == (3, 2, 1, 1, 5, -3)
    assert detail["orders"][0]["not_returned"] == 1
    assert any("Dropped" in movement["reason"] for movement in detail["movements"])
    assert any("Physical count" in movement["reason"] for movement in detail["movements"])
    assert any("without stock return" in movement["reason"] for movement in detail["movements"])


def test_manila_day_carryover_and_initial_recipe_servings(app, client):
    meal_id = meal(app)
    recipe_id = meal(app, "Recipe Audit Meal", mode="recipe")
    untracked_id = meal(app, "Untracked Audit Meal", mode="untracked")
    add_batch(client, meal_id, 10, "audit-yesterday-batch")
    add_batch(client, meal_id, 5, "audit-today-batch")
    add_batch(client, recipe_id, 3, "audit-recipe-first-batch")
    add_batch(client, untracked_id, 2, "audit-untracked-first-batch")
    today = manila_date(datetime.utcnow())
    yesterday = today - timedelta(days=1)
    start, _ = manila_day_bounds(today)
    with app.app_context():
        actions = InventoryAction.query.filter_by(menu_item_id=meal_id, action="add").order_by(InventoryAction.id).all()
        logs = InventoryLog.query.join(InventoryItem).filter(
            InventoryItem.menu_item_id == meal_id, InventoryLog.reason.like("Add:%")
        ).order_by(InventoryLog.id).all()
        actions[0].created_at = logs[0].created_at = start - timedelta(minutes=1)
        actions[1].created_at = logs[1].created_at = start + timedelta(minutes=1)
        db.session.commit()
    _, order_id = order(app, client, meal_id, "Dina", 6)
    with app.app_context():
        placed = db.session.get(Order, order_id)
        stock_id = InventoryItem.query.filter_by(menu_item_id=meal_id).one().id
        sale_log = InventoryLog.query.filter_by(inventory_item_id=stock_id).filter(
            InventoryLog.reason.like("Sale:%")).one()
        placed.created_at = sale_log.created_at = start + timedelta(minutes=2)
        db.session.commit()
    old = client.get(f"/inventory/api/meal-day-summary?date={yesterday}").get_json()
    current = client.get(f"/inventory/api/meal-day-summary?date={today}").get_json()
    prev = next(row for row in old["data"] if row["meal_id"] == meal_id)
    now = next(row for row in current["data"] if row["meal_id"] == meal_id)
    assert (prev["opening"], prev["added"], prev["remaining"]) == (0, 10, 10)
    assert (now["opening"], now["added"], now["ordered"], now["available"], now["remaining"]) == (10, 5, 6, 15, 9)
    with app.app_context():
        assert InventoryItem.query.filter_by(menu_item_id=recipe_id).one().stock_qty == 3
        assert InventoryItem.query.filter_by(menu_item_id=untracked_id).one().stock_qty == 2
        assert db.session.get(MenuItem, untracked_id).inventory_mode == "prepared"


def test_audit_validation_access_and_duplicate_batch(app, client):
    meal_id = meal(app)
    add_batch(client, meal_id, 4, "audit-one-submit")
    again = client.post(f"/inventory/api/menu-items/{meal_id}/action",
                        json={"action": "add", "quantity": 4},
                        headers={"Idempotency-Key": "audit-one-submit"})
    assert again.status_code == 409 and again.get_json()["duplicate"] is True
    with app.app_context():
        assert InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty == 4
    assert client.get("/inventory/api/meal-day-summary?date=2026-02-30").status_code == 400
    assert client.get("/inventory/api/meal-day-summary?date=2099-01-01").status_code == 400
    assert client.get(f"/inventory/api/menu-items/{meal_id}/daily-audit?page=0").status_code == 400
    assert client.get("/inventory/api/menu-items/999999/daily-audit").status_code == 404
    anonymous = app.test_client()
    assert anonymous.get("/inventory/api/meal-day-summary").status_code in (302, 401)
    assert anonymous.get(f"/inventory/api/menu-items/{meal_id}/daily-audit").status_code in (302, 401)


def test_later_cancellations_keep_deleted_order_item_in_original_day(app, client):
    meal_id = meal(app)
    other_id = meal(app, "Other Meal")
    add_batch(client, meal_id, 10, "audit-old-day-batch")
    add_batch(client, other_id, 4, "audit-other-batch")
    _, order_id = order(app, client, meal_id, "Ella", 2)
    today = manila_date(datetime.utcnow())
    yesterday = today - timedelta(days=1)
    start, _ = manila_day_bounds(today)
    with app.app_context():
        stock = InventoryItem.query.filter_by(menu_item_id=meal_id).one()
        stock.created_at = start - timedelta(minutes=3)
        InventoryAction.query.filter_by(menu_item_id=meal_id, action="add").one().created_at = start - timedelta(minutes=2)
        logs = InventoryLog.query.filter_by(inventory_item_id=stock.id).order_by(InventoryLog.id).all()
        logs[0].created_at = start - timedelta(minutes=2)
        logs[1].created_at = start - timedelta(minutes=1)
        db.session.get(Order, order_id).created_at = start - timedelta(minutes=1)
        item_id = Order.query.get(order_id).items[0].id
        db.session.commit()
        service = OrderService(OrderRepository(), get_notifier())
        for number in range(2):
            result = service.void_item(item_id, actor=1,
                request_key=f"audit-late-void-{number}", reason="Wrong meal",
                return_stock=True)
            assert not isinstance(result, tuple)
        assert OrderItem.query.filter_by(order_id=order_id).count() == 0

    previous = client.get(f"/inventory/api/menu-items/{meal_id}/daily-audit?date={yesterday}").get_json()
    row = previous["summary"]
    assert (row["opening"], row["added"], row["placed"], row["cancelled"],
            row["ordered"], row["remaining"], row["later_cancellations"]) == (0, 10, 2, 2, 0, 8, 2)
    assert row["history_complete"] is True
    assert previous["orders"][0]["customer"] == "Ella"
    assert len(previous["orders"][0]["cancellations"]) == 2
    assert all(manila_date(datetime.fromisoformat(event["at"][:-1])) == today
               for event in previous["orders"][0]["cancellations"])
    current = client.get(f"/inventory/api/meal-day-summary?date={today}").get_json()
    current_rows = {row["meal_id"]: row for row in current["data"]}
    assert current_rows[meal_id]["opening"] == 8
    assert current_rows[meal_id]["remaining"] == 10
    assert current_rows[other_id]["added"] == 4
    assert current_rows[other_id]["ordered"] == 0


def test_missing_stock_history_is_marked_incomplete(app, client):
    meal_id = meal(app)
    empty_id = meal(app, "Not Yet Prepared")
    corrected_id = meal(app, "Corrected Meal")
    add_batch(client, corrected_id, 10, "audit-corrected-batch")
    corrected = client.post(f"/inventory/api/menu-items/{corrected_id}/action",
        json={"action": "count", "quantity": 12, "reason": "Found two more"},
        headers={"Idempotency-Key": "audit-corrected-count"})
    assert corrected.status_code == 200
    with app.app_context():
        InventoryItem.query.filter_by(menu_item_id=meal_id).one().stock_qty = 4
        db.session.commit()
    rows = {row["meal_id"]: row for row in client.get("/inventory/api/meal-day-summary").get_json()["data"]}
    row = rows[meal_id]
    assert (row["opening"], row["remaining"], row["history_complete"]) == (4, 4, False)
    assert rows[empty_id]["configured"] is False
    assert (rows[corrected_id]["available"], rows[corrected_id]["remaining"],
            rows[corrected_id]["history_complete"]) == (10, 12, False)


def test_staff_inventory_renders_dated_audit_controls(app, client):
    page = client.get("/inventory")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'id="meal-daily-audit-dialog"' in html
    assert 'id="meal-daily-audit-date"' in html
    assert 'New servings in this batch' in html


def test_orders_before_serving_tracking_do_not_make_a_false_ratio(app, client):
    meal_id = meal(app, "Previously Untracked", mode="untracked")
    order(app, client, meal_id, "Finn", 2)
    add_batch(client, meal_id, 10, "audit-after-untracked-order")
    row = next(row for row in client.get("/inventory/api/meal-day-summary").get_json()["data"]
               if row["meal_id"] == meal_id)
    assert row["configured"] is True
    assert row["untracked_orders"] is True
    assert row["history_complete"] is False
