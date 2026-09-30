"""Dated debt history and open customer cycles remain separate from payment dates."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app import create_app, db
from app.db.migrator import SchemaMigrator
from app.models import Receivable, ReceivablePayment, ReceivableTab
from app.repositories.receivable_repository import ReceivableRepository
from app.repositories.sales_repository import SalesRepository
from app.services.receivable_service import ReceivableService
import app.services.receivable_service as service_module


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def auth(client, role="staff"):
    with client.session_transaction() as session:
        session.update(user_id=1, username="test_user", role=role,
                       last_activity=datetime.now(timezone.utc).timestamp())


def create(name, contact, item, amount, taken, tab_id=None):
    return ReceivableService(ReceivableRepository()).create(
        name, contact, item, amount, "2026-10-10", 1, None,
        incurred_date=taken, tab_id=tab_id,
    )["data"]


def test_date_search_pagination_and_all_date_totals(app):
    with app.app_context():
        first = create(" Ana  Cruz ", "0911", "Rice", 100, "2026-09-29")
        second = create("ana cruz", "0911", "Eggs", 80, "2026-09-30")
        separate = create("Ana Cruz", "0922", "Milk", 35, "2026-09-30")
        assert first["tab_id"] == second["tab_id"] != separate["tab_id"]

    client = app.test_client()
    auth(client)
    base = "/receivables-view/api/receivables"
    staff_page = client.get("/receivables-view").data
    assert b'id="debt-date"' in staff_page and b'id="debt-search"' in staff_page
    assert b"Show All Utang" in staff_page and b"Receivable Records / Date Taken" in staff_page
    yesterday = client.get(base, query_string={"date": "2026-09-29", "page": 1, "per_page": 1}).get_json()
    assert yesterday["pagination"]["total"] == 1
    assert yesterday["data"][0]["items"] == "Rice"
    assert yesterday["totals"] == {"all_outstanding": 215, "selected_taken": 100, "selected_outstanding": 100}
    dated_tabs = client.get(base + "/tabs", query_string={"date": "2026-09-29"}).get_json()
    assert [tab["id"] for tab in dated_tabs["data"]] == [first["tab_id"]]
    assert dated_tabs["data"][0]["date_taken_amount"] == 100
    assert dated_tabs["data"][0]["outstanding_balance"] == 180

    today = client.get(base, query_string={"date": "2026-09-30", "page": 1, "per_page": 1}).get_json()
    assert today["pagination"]["total"] == 2
    assert today["pagination"]["has_next"] is True
    assert today["totals"]["selected_taken"] == 115
    searched = client.get(base, query_string={"date": "2026-09-30", "search": "Eggs", "page": 1}).get_json()
    assert [row["id"] for row in searched["data"]] == [second["id"]]
    assert client.get(base, query_string={"date": "2026-09-29", "search": "ana cruz", "page": 1}).get_json()["pagination"]["total"] == 1
    assert client.get(base, query_string={"page": 1, "search": "0911"}).get_json()["pagination"]["total"] == 2
    assert client.get(base, query_string={"page": 1, "date": "2026-02-30"}).status_code == 400
    assert client.get(base, query_string={"page": 0}).status_code == 400
    assert client.get(base, query_string={"page": 1, "status": "unknown"}).status_code == 400


def test_blank_contact_requires_selection_and_settlement_starts_new_cycle(app):
    with app.app_context():
        one = create("Sam", "", "Coffee", 30, "2026-09-29")
        two = create(" sam ", "", "Bread", 20, "2026-09-30")
        joined = create("SAM", "", "Tea", 10, "2026-09-30", tab_id=one["tab_id"])
        assert len({one["tab_id"], two["tab_id"], joined["tab_id"]}) == 2
        assert joined["tab_id"] == one["tab_id"]
        with pytest.raises(ValueError, match="does not match"):
            create("Other", "", "Tea", 1, "2026-09-30", tab_id=one["tab_id"])
        db.session.rollback()

    client = app.test_client()
    auth(client)
    base = "/receivables-view/api/receivables"
    assert client.post(base + "/customer-payment", json={"customer_name": "Sam", "amount": "10"}).status_code == 400
    result = client.post(f"{base}/tabs/{one['tab_id']}/payments", json={"amount": "40", "payment_method": "cash"})
    assert result.status_code == 200 and result.get_json()["remaining"] == 0
    assert client.get(base + "/tabs").get_json()["pagination"]["total"] == 1
    assert client.get(f"{base}/tabs/{one['tab_id']}").get_json()["data"]["open"] is False
    assert client.post(f"{base}/tabs/{one['tab_id']}/payments", json={"amount": "1"}).status_code == 400
    with app.app_context():
        with pytest.raises(ValueError, match="closed"):
            create("Sam", "", "Bad", 1, "2026-10-01", tab_id=one["tab_id"])
        db.session.rollback()
        new = create("Sam", "", "Fresh", 15, "2026-10-01")
        assert new["tab_id"] not in (one["tab_id"], two["tab_id"])
        assert ReceivablePayment.query.count() == 2
    history = client.get(f"{base}/tabs/{new['tab_id']}/payments").get_json()["data"]
    assert history == []
    assert client.get(f"{base}/tabs/{new['tab_id']}").get_json()["data"]["orders_total"] == 15


def test_contacted_customer_reborrows_on_new_tab_after_record_payment(app):
    with app.app_context():
        old = create("Nina", "0911 123", "Lunch", 25, "2026-09-29")
        service = ReceivableService(ReceivableRepository())
        assert service.mark_paid(old["id"], "25", 1, "cash")["success"] is True
        assert db.session.get(ReceivableTab, old["tab_id"]).closed_at is not None
        fresh = create(" nina ", "0911123", "Dinner", 40, "2026-09-30")
        assert fresh["tab_id"] != old["tab_id"]
        assert service.tab_detail(fresh["tab_id"])["orders_total"] == 40
        assert len(service.list_customer_payments(tab_id=fresh["tab_id"])) == 0

    client = app.test_client()
    auth(client)
    base = "/receivables-view/api/receivables"
    assert client.get(base, query_string={"date": "2026-09-29", "page": 1}).get_json()["data"][0]["paid"] is True
    assert [row["id"] for row in client.get(base + "/tabs").get_json()["data"]] == [fresh["tab_id"]]
    assert client.get(f"{base}/tabs/{old['tab_id']}/payments").get_json()["data"][0]["amount"] == 25
    assert client.get(f"{base}/tabs/{fresh['tab_id']}/payments").get_json()["data"] == []
    assert client.get("/admin/receivables/api/receivables/tabs").status_code == 403


def test_legacy_backfill_uses_manila_date_and_preserves_money(app):
    with app.app_context():
        rows = [Receivable(customer_name="Lee", customer_contact="0999", items_description=item,
                           amount_owed=Decimal(amount), partial_paid=Decimal(paid), paid=closed,
                           due_date=date(2026, 10, 10), created_by=1,
                           created_at=datetime(2026, 9, 29, 17))
                for item, amount, paid, closed in (("Rice", "100", "20", False),
                                                   ("Eggs", "50", "0", False),
                                                   ("Old", "30", "30", True))]
        db.session.add_all(rows)
        db.session.commit()
        ids = [row.id for row in rows]
        db.session.add(ReceivablePayment(receivable_id=ids[0], amount=20,
                                         payment_method="gcash", received_by=1,
                                         received_at=datetime(2026, 9, 30, 4)))
        db.session.commit()
        migrator = SchemaMigrator(db, app)
        migrator._backfill_receivable_tabs()
        migrator._backfill_receivable_tabs()
        refreshed = [db.session.get(Receivable, value) for value in ids]
        assert {row.incurred_date for row in refreshed} == {date(2026, 9, 30)}
        assert refreshed[0].tab_id == refreshed[1].tab_id != refreshed[2].tab_id
        assert db.session.get(ReceivableTab, refreshed[2].tab_id).closed_at is not None
        assert ReceivableTab.query.count() == 2
        assert sum(row.amount_owed for row in refreshed) == Decimal("180")
        assert sum(row.partial_paid for row in refreshed) == Decimal("50")
        assert ReceivablePayment.query.count() == 1


def test_backdated_debt_collection_reconciles_on_payment_day(app, monkeypatch):
    class Clock:
        @staticmethod
        def utcnow():
            return datetime(2026, 9, 30, 16, 15)  # Oct 1 in Manila

    monkeypatch.setattr(service_module, "datetime", Clock)
    with app.app_context():
        debt = create("Mara", "0912", "Meal", 75, "2026-09-29")
    client = app.test_client()
    auth(client)
    path = f"/receivables-view/api/receivables/tabs/{debt['tab_id']}/payments"
    response = client.post(path, json={"amount": "75", "payment_method": "gcash"},
                           headers={"Idempotency-Key": "mara-full-2026-10-01"})
    assert response.status_code == 200
    assert client.post(path, json={"amount": "75", "payment_method": "gcash"},
                       headers={"Idempotency-Key": "mara-full-2026-10-01"}).status_code == 409
    records = client.get("/receivables-view/api/receivables", query_string={"date": "2026-09-29", "page": 1}).get_json()
    assert records["data"][0]["paid"] is True
    assert client.get("/receivables-view/api/receivables/tabs", query_string={"date": "2026-09-29"}).get_json()["data"] == []
    assert client.get(path).get_json()["data"][0]["amount"] == 75
    with app.app_context():
        before = SalesRepository().daily_ledger(date(2026, 9, 29), date(2026, 9, 29))
        paid_day = SalesRepository().daily_ledger(date(2026, 10, 1), date(2026, 10, 1))[date(2026, 10, 1)]
        assert date(2026, 9, 29) not in before
        assert paid_day["collection_methods"]["gcash"] == 75
        assert paid_day["total_collections"] == paid_day["net_balance"] == 75
        assert paid_day["total_revenue"] == 0
