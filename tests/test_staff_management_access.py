"""Staff management actions use the existing inventory and finance histories."""

from datetime import date, datetime, timezone
from decimal import Decimal
import re

import pytest

from app import create_app, db
from app.models import (CustomerSession, DailySalesReport, InventoryAction, InventoryItem, InventoryLog, MenuItem,
                        MenuItemIngredient,
                        PayablePayment, SoftBalanceEntry, SpaceType, Transaction)
from app.repositories.sales_repository import SalesRepository
from app.models.menu_category import MenuCategory
from app.utils.dates import manila_date


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def sign_in(client, role="staff"):
    with client.session_transaction() as login:
        login.update(user_id=1, username="test_user", role=role,
                     last_activity=datetime.now(timezone.utc).timestamp())


def test_staff_uses_full_menu_management_without_admin_urls(app):
    client = app.test_client()
    sign_in(client)
    page = client.get("/staff/menu")
    assert page.status_code == 200
    assert b"Menu Management" in page.data
    assert b"Add Menu Item" in page.data
    assert b'/admin/' not in page.data
    assert b'/staff/menu' in client.get("/dashboard").data
    assert client.get("/admin/menu/api/items/all").status_code == 403

    for name in ("Main Dish", "Beverages"):
        added = client.post("/staff/menu/api/categories", json={"name": name},
                            headers={"Idempotency-Key": f"staff-category-{name}"})
        assert added.status_code == 201
    created = client.post("/staff/menu/api/items", data={
        "name": "Staff Meal", "category": "Main Dish", "price": "80.00",
        "can_remove_rice": "true", "inventory_mode": "prepared", "stock_quantity": "5",
    }, headers={"Idempotency-Key": "staff-menu-meal"})
    assert created.status_code == 201, created.get_json()
    item_id = created.get_json()["data"]["id"]
    updated = client.patch(f"/staff/menu/api/items/{item_id}", data={"price": "85.00"},
                           headers={"Idempotency-Key": "staff-menu-price"})
    assert updated.status_code == 200
    toggled = client.patch(f"/staff/menu/api/items/{item_id}/availability",
                           headers={"Idempotency-Key": "staff-menu-toggle"})
    assert toggled.status_code == 200 and toggled.get_json()["is_available"] is False
    variants = client.post("/staff/menu/api/items/variants", data={
        "base_name": "Coffee", "variant_labels": "Hot,Iced", "variant_prices": "80,95",
    }, headers={"Idempotency-Key": "staff-menu-variants"})
    assert variants.status_code == 201, variants.get_json()
    assert len(variants.get_json()["data"]["created_ids"]) == 2
    removed = client.delete(f"/staff/menu/api/items/{item_id}",
                            headers={"Idempotency-Key": "staff-menu-delete"})
    assert removed.status_code == 200
    with app.app_context():
        meal = db.session.get(MenuItem, item_id)
        assert meal.price == Decimal("85.00") and meal.status == "deleted"
        assert InventoryAction.query.filter_by(menu_item_id=item_id, changed_by=1).count() == 1
        assert MenuCategory.query.count() == 2


def test_staff_can_manage_inventory_and_review_named_stock_history(app):
    with app.app_context():
        ingredient = MenuItem(name="Rice", price=0, category="ingredient", is_available=True)
        meal = MenuItem(name="Meal", price=80, category="Meals", is_available=True,
                        inventory_mode="prepared")
        db.session.add_all([ingredient, meal])
        db.session.flush()
        row = InventoryItem(menu_item_id=ingredient.id, stock_qty=5, unit="pieces")
        db.session.add(row)
        db.session.commit()
        ingredient_id, row_id, meal_id = ingredient.id, row.id, meal.id

    client = app.test_client()
    sign_in(client)
    page = client.get("/staff/inventory")
    assert page.status_code == 200
    assert b'data-admin="true"' in page.data
    assert b'/staff/payables' in page.data
    assert b'/admin/' not in page.data
    for path in ("/expenses-view", "/receivables-view"):
        staff_page = client.get(path)
        assert staff_page.status_code == 200
        assert b'/admin/' not in staff_page.data
    assert b'/admin/' not in client.get("/static/js/receivable-collections.js").data
    assert client.get("/staff/inventory/api/dashboard-items").status_code == 200
    created = client.post("/staff/inventory/api/items", json={
        "ingredient_name": "Egg", "stock_qty": 4, "unit": "pieces",
        "low_stock_threshold": 2,
    }, headers={"Idempotency-Key": "staff-create-egg"})
    assert created.status_code == 201 and created.get_json()["success"]
    created_logs = client.get(f"/staff/inventory/api/items/{created.get_json()['data']['id']}/logs").get_json()["data"]
    assert len(created_logs) == 1 and created_logs[0]["changed_by"] == "test_user"
    assert created_logs[0]["change_qty"] == 4
    deleted = client.delete(f"/staff/inventory/api/items/{created.get_json()['data']['id']}",
                            headers={"Idempotency-Key": "staff-delete-egg-stock"})
    assert deleted.status_code == 200 and deleted.get_json()["success"]
    archived_history = client.get("/inventory/api/history").get_json()["data"]
    assert {entry["action"] for entry in archived_history if entry["item"] == "Egg"} >= {"archived_log", "delete"}
    with app.app_context():
        assert InventoryAction.query.filter_by(item_name="Egg", action="archived_log").count() == 1
        assert InventoryAction.query.filter_by(item_name="Egg", action="delete", changed_by=1).count() == 1

    stock = client.patch(f"/staff/inventory/api/items/{row_id}/stock",
                         json={"quantity": 3, "mode": "add", "reason": "Restock"},
                         headers={"Idempotency-Key": "staff-restock-rice"})
    assert stock.status_code == 200 and stock.get_json()["success"]
    logs = client.get(f"/staff/inventory/api/items/{row_id}/logs").get_json()["data"]
    assert len(logs) == 1 and logs[0]["changed_by"] == "test_user"
    assert logs[0]["change_qty"] == 3
    assert client.post("/staff/inventory/api/items", json={
        "menu_item_id": ingredient_id, "stock_qty": 8, "unit": "grams",
    }).status_code == 400

    setup = client.post(f"/inventory/api/menu-items/{meal_id}/action",
                        json={"action": "setup", "inventory_mode": "prepared",
                              "quantity": 5, "threshold": 2, "reason": "Morning count"},
                        headers={"Idempotency-Key": "staff-meal-setup"})
    assert setup.status_code == 200 and setup.get_json()["success"]
    meal_history = client.get(f"/inventory/api/menu-items/{meal_id}/history").get_json()["data"]
    assert any(entry["actor"] == "Test User" for entry in meal_history)

    with app.app_context():
        mapping = MenuItemIngredient(menu_item_id=meal_id, ingredient_item_id=ingredient_id,
                                     quantity_required=1, unit="pieces")
        db.session.add(mapping)
        db.session.commit()
        mapping_id = mapping.id
    unlinked = client.delete(f"/staff/inventory/api/recipes/{mapping_id}",
                             headers={"Idempotency-Key": "staff-unlink-recipe"})
    assert unlinked.status_code == 200 and unlinked.get_json()["success"]
    logs = client.get(f"/staff/inventory/api/items/{row_id}/logs").get_json()["data"]
    assert any(log["reason"] == "Unlinked from Meal" and log["changed_by"] == "test_user" for log in logs)

    with app.app_context():
        assert db.session.get(InventoryItem, row_id).stock_qty == 8
        assert InventoryLog.query.filter_by(inventory_item_id=row_id).count() == 2
        assert db.session.get(MenuItem, ingredient_id).status != "deleted"


def test_staff_payable_payment_and_soft_balance_reconcile_with_daily_balance(app):
    today = manila_date(datetime.utcnow())
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        visit = CustomerSession(customer_name="Sale", space_type_id=space.id,
                                time_in=datetime.utcnow(), status="completed")
        db.session.add(visit)
        db.session.flush()
        db.session.add(Transaction(session_id=visit.id, time_bill=Decimal("500"),
                                   food_bill=0, total_bill=Decimal("500"),
                                   payment_method="gcash", created_at=datetime.utcnow()))
        db.session.commit()

    client = app.test_client()
    sign_in(client)
    payables_page = client.get("/staff/payables")
    assert payables_page.status_code == 200
    assert b'/admin/' not in payables_page.data
    invalid = client.post("/staff/payables/api/payables", json={
        "creditor_name": "Supplier", "items_description": "Rice",
        "amount_owed": "not a number", "due_date": str(today),
    })
    assert invalid.status_code == 400
    created = client.post("/staff/payables/api/payables", json={
        "creditor_name": "Supplier", "items_description": "Rice",
        "amount_owed": "200.00", "incurred_date": str(today), "due_date": str(today),
    }, headers={"Idempotency-Key": "staff-payable-create"})
    assert created.status_code == 201 and created.get_json()["success"]
    payable_id = created.get_json()["data"]["id"]
    payment_url = f"/staff/payables/api/payables/{payable_id}/mark-paid"
    paid = client.patch(payment_url, json={"amount": "200.00", "payment_method": "gcash"},
                        headers={"Idempotency-Key": "staff-payable-gcash"})
    assert paid.status_code == 200 and paid.get_json()["funding_source"] == "business"
    replay = client.patch(payment_url, json={"amount": "200.00", "payment_method": "gcash"},
                          headers={"Idempotency-Key": "staff-payable-gcash"})
    assert replay.get_json()["replayed"] is True
    history = client.get("/staff/payables/api/payables").get_json()["data"][0]["payments"]
    assert len(history) == 1
    assert history[0]["paid_by"] == "test_user"
    assert history[0]["payment_method"] == "gcash"
    assert history[0]["amount"] == 200

    external_payable = client.post("/staff/payables/api/payables", json={
        "creditor_name": "Second supplier", "items_description": "Eggs",
        "amount_owed": "400.00", "incurred_date": str(today), "due_date": str(today),
    }).get_json()["data"]["id"]
    external = client.patch(f"/staff/payables/api/payables/{external_payable}/mark-paid",
                            json={"amount": "400.00", "payment_method": "gcash"},
                            headers={"Idempotency-Key": "staff-external-gcash"})
    assert external.status_code == 200 and external.get_json()["funding_source"] == "external"

    report = client.get(f"/staff/daily-balance/api/reports?start_date={today}&end_date={today}")
    assert report.status_code == 200
    live = report.get_json()["data"][0]
    assert live["total_revenue"] == 500
    assert live["total_payables_paid"] == 600
    assert live["payable_methods"]["gcash"] == 200
    assert live["external_payable_methods"]["gcash"] == 400
    assert live["payable_paid_methods"]["gcash"] == 600
    assert client.get(f"/staff/daily-balance/api/reports/export-csv?start_date={today}&end_date={today}").status_code == 200
    with app.app_context():
        ledger = SalesRepository().daily_ledger(today, today)[today]
        assert SalesRepository.method_balance(ledger, "gcash") == Decimal("300.00")
        assert PayablePayment.query.count() == 2

    balance_page = client.get("/staff/daily-balance")
    assert b"Generate Report" in balance_page.data
    assert b'onclick="generateReport()"' in balance_page.data
    assert b'/admin/' not in balance_page.data
    assert client.post("/staff/daily-balance/api/soft-balances",
                       json={"balance_date": "bad-date", "period": "AM"}).status_code == 400
    assert client.post("/staff/daily-balance/api/soft-balances",
                       json={"balance_date": str(today), "period": "night"}).status_code == 400
    saved = client.post("/staff/daily-balance/api/soft-balances",
                        json={"balance_date": str(today), "period": "AM", "notes": "Morning shift"},
                        headers={"Idempotency-Key": "staff-soft-balance"})
    assert saved.status_code == 201 and saved.get_json()["success"]
    assert client.post("/staff/daily-balance/api/soft-balances",
                       json={"balance_date": str(today), "period": "AM", "notes": "Morning shift"},
                       headers={"Idempotency-Key": "staff-soft-balance"}).status_code == 409
    snapshots = client.get("/staff/daily-balance/api/soft-balances").get_json()["data"]
    assert len(snapshots) == 1
    assert snapshots[0]["generated_by"] == "test_user"
    assert snapshots[0]["total_payables_paid"] == 600
    assert snapshots[0]["total_revenue"] == 500
    with app.app_context():
        assert SoftBalanceEntry.query.count() == 1

    report_payload = {"report_date": str(today), "notes": "Shift close"}
    assert client.post("/staff/daily-balance/api/reports",
                       json={"report_date": "invalid"}).status_code == 400
    generated = client.post("/staff/daily-balance/api/reports", json=report_payload,
                            headers={"Idempotency-Key": "staff-daily-report"})
    assert generated.status_code == 201 and generated.get_json()["data"]["net_balance"] == 300
    assert client.post("/staff/daily-balance/api/reports", json=report_payload,
                       headers={"Idempotency-Key": "staff-daily-report"}).status_code == 409
    with app.app_context():
        report_row = DailySalesReport.query.one()
        assert report_row.generated_by == 1
        assert report_row.total_payables_paid == Decimal("600.00")
        assert report_row.net_balance == Decimal("300.00")
    assert client.get("/admin").status_code in {302, 403}
    assert client.post("/admin/expenses/api/expenses/1/void", json={}).status_code == 403


def test_staff_management_paths_deny_unauthenticated_and_other_roles(app):
    client = app.test_client()
    assert client.get("/staff/inventory").status_code == 302
    assert client.get("/staff/payables/api/payables").status_code == 401
    assert client.get("/staff/daily-balance/api/reports").status_code == 401
    assert client.get("/staff/menu/api/items/all").status_code == 401
    sign_in(client, "customer")
    assert client.get("/staff/inventory/api/items").status_code == 403
    assert client.get("/staff/payables/api/payables").status_code == 403
    assert client.get("/staff/daily-balance/api/reports").status_code == 403
    assert client.get("/staff/menu/api/items/all").status_code == 403
    assert client.post("/staff/daily-balance/api/reports",
                       json={"report_date": str(date.today())}).status_code == 403
    assert client.post("/staff/daily-balance/api/soft-balances",
                       json={"balance_date": str(date.today()), "period": "AM"}).status_code == 403

    sign_in(client, "staff")
    assert client.get("/admin/inventory").status_code == 302
    assert client.get("/admin/payables/api/payables").status_code == 403
    assert client.get("/admin/daily-balance/api/reports").status_code == 403
    assert client.get("/admin/menu/api/items/all").status_code == 403
    assert client.post("/admin/daily-balance/api/reports",
                       json={"report_date": str(date.today())}).status_code == 403
    assert client.get("/staff/daily-balance/api/reports").status_code == 200

    sign_in(client, "admin")
    assert client.get("/admin/inventory").status_code == 200
    assert client.get("/admin/payables/api/payables").status_code == 200
    assert client.get("/admin/daily-balance/api/reports").status_code == 200
    assert client.get("/admin/menu/api/items/all").status_code == 200


def test_staff_soft_balance_write_requires_page_csrf_token(app):
    app.config["WTF_CSRF_ENABLED"] = True
    client = app.test_client()
    sign_in(client)
    page = client.get("/staff/daily-balance")
    assert page.status_code == 200
    token = re.search(rb'<meta name="csrf-token" content="([^"]+)"', page.data).group(1).decode()
    url = "/staff/daily-balance/api/soft-balances"
    body = {"balance_date": str(manila_date(datetime.utcnow())), "period": "PM"}
    assert client.post(url, json=body).status_code == 400
    saved = client.post(url, json=body, headers={"X-CSRFToken": token})
    assert saved.status_code == 201 and saved.get_json()["success"]
    report_url = "/staff/daily-balance/api/reports"
    report_body = {"report_date": str(date.today())}
    assert client.post(report_url, json=report_body).status_code == 400
    assert client.post(report_url, json=report_body,
                       headers={"X-CSRFToken": token}).status_code == 201
    payable = {"creditor_name": "Supplier", "items_description": "Rice",
               "amount_owed": "10.00", "due_date": str(date.today())}
    assert client.post("/staff/payables/api/payables", json=payable).status_code == 400
    assert client.post("/staff/payables/api/payables", json=payable,
                       headers={"X-CSRFToken": token}).status_code == 201
    ingredient = {"ingredient_name": "Rice", "stock_qty": 5, "unit": "pieces"}
    assert client.post("/staff/inventory/api/items", json=ingredient).status_code == 400
    assert client.post("/staff/inventory/api/items", json=ingredient,
                       headers={"X-CSRFToken": token}).status_code == 201
    menu_category = {"name": "Meals"}
    assert client.post("/staff/menu/api/categories", json=menu_category).status_code == 400
    assert client.post("/staff/menu/api/categories", json=menu_category,
                       headers={"X-CSRFToken": token}).status_code == 201
