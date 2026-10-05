"""Dated debt history and open customer cycles remain separate from payment dates."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app import create_app, db
from app.db.migrator import SchemaMigrator
from app.models import Admin, Receivable, ReceivablePayment, ReceivableTab
from app.repositories.receivable_repository import ReceivableRepository
from app.repositories.sales_repository import SalesRepository
from app.services.receivable_service import ReceivableService
from app.utils.dates import manila_date
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


def test_customer_suggestions_include_old_paid_and_ambiguous_customers(app):
    with app.app_context():
        paid = create(" Ana  Cruz ", "0911 123", "Coffee", 20, "2026-09-29")
        active = create("ana cruz", "0922", "Bread", 30, "2026-09-30")
        no_contact_one = create("Ana Cruz", "", "Tea", 10, "2026-09-29")
        no_contact_two = create("Ana Cruz", "", "Egg", 15, "2026-09-30")
        ReceivableService(ReceivableRepository()).mark_paid(paid["id"], "20", 1, "cash")
        db.session.add(Receivable(customer_name="Legacy Lee", customer_contact="0999 000",
                                  items_description="Old item", amount_owed=Decimal("10"),
                                  due_date=date(2026, 10, 10), created_by=1))
        db.session.commit()

    client = app.test_client()
    path = "/receivables-view/api/receivables/customer-suggestions"
    assert client.get(path, query_string={"q": "Ana"}).status_code == 401
    auth(client)
    assert client.get("/admin/receivables/api/receivables/customer-suggestions", query_string={"q": "Ana"}).status_code == 403
    assert client.get(path, query_string={"q": "A"}).status_code == 400
    assert client.get(path, query_string={"q": "a" * 101}).status_code == 400
    assert client.get(path, query_string={"q": "%%"}).get_json()["data"] == []

    # Today's Date Taken filter must not limit the identity lookup.
    response = client.get(path, query_string={"q": " ana   CRUZ ", "date": "2026-10-05"})
    assert response.status_code == 200
    matches = response.get_json()["data"]
    assert len(matches) == 4
    assert {row["open_tab_id"] for row in matches} == {
        None, active["tab_id"], no_contact_one["tab_id"], no_contact_two["tab_id"]
    }
    assert next(row for row in matches if row["customer_contact"] == "0911 123")["label"] == "Past customer—new tab"
    assert next(row for row in matches if row["customer_contact"] == "0922")["open_tab_id"] == active["tab_id"]
    assert client.get(path, query_string={"q": "0911123"}).get_json()["data"][0]["open_tab_id"] is None
    legacy = client.get(path, query_string={"q": "0999000"}).get_json()["data"]
    assert legacy[0]["customer_name"] == "Legacy Lee" and legacy[0]["open_tab_id"] is None


def test_selected_customer_actor_paid_cycle_conflict_and_retry(app):
    with app.app_context():
        old = create("Nina", "0911", "Old meal", 25, "2026-09-29")
        db.session.get(Receivable, old["id"]).approved_by_staff = "Historical free text"
        db.session.commit()
        ReceivableService(ReceivableRepository()).mark_paid(old["id"], "25", 1, "cash")

    client = app.test_client()
    auth(client)
    staff = "/receivables-view/api/receivables"
    match = client.get(staff + "/customer-suggestions", query_string={"q": "nina"}).get_json()["data"][0]
    assert match["open_tab_id"] is None
    assert b'id="approvedByStaff"' not in client.get("/receivables-view").data
    payload = {"customer_name": match["customer_name"], "customer_contact": match["customer_contact"],
               "items_description": "New meal", "amount_owed": "40.00", "incurred_date": "2026-10-05",
               "due_date": "2026-10-10", "approved_by_staff": "Impostor"}
    saved = client.post(staff, json=payload, headers={"Idempotency-Key": "new-cycle-nina"})
    assert saved.status_code == 201
    assert client.post(staff, json=payload, headers={"Idempotency-Key": "new-cycle-nina"}).status_code == 409
    new = saved.get_json()["data"]
    assert new["tab_id"] != old["tab_id"]
    assert client.post(staff, json={**payload, "tab_id": old["tab_id"]}).status_code == 409
    assert client.get(staff, query_string={"date": "2026-10-05", "page": 1}).get_json()["data"][0]["approved_by_staff"] == "test_user"
    with app.app_context():
        assert Receivable.query.count() == 2
        assert db.session.get(Receivable, new["id"]).created_by == 1
        assert db.session.get(Receivable, old["id"]).approved_by_staff == "Historical free text"
        assert db.session.get(ReceivableTab, old["tab_id"]).closed_at is not None

    with app.app_context():
        owner = Admin(id=1, full_name="Owner", username="owner")
        owner.set_password("TestOwner123!")
        db.session.add(owner)
        db.session.commit()
    auth(client, "admin")
    admin = client.post("/admin/receivables/api/receivables", json={
        **payload, "customer_name": "Brand New", "customer_contact": "0900", "tab_id": None,
    })
    assert admin.status_code == 201
    assert client.get("/admin/receivables/api/receivables/customer-suggestions", query_string={"q": "Brand"}).get_json()["data"][0]["open_tab_id"] == admin.get_json()["data"]["tab_id"]
    with app.app_context():
        record = db.session.get(Receivable, admin.get_json()["data"]["id"])
        assert (record.created_by, record.approved_by_staff) == (1, "owner")


def test_suggested_open_tab_debt_and_payment_reconcile_on_payment_date(app):
    with app.app_context():
        old = create("Carl", "0912", "Yesterday", 100, "2026-09-30")
    client = app.test_client()
    auth(client)
    base = "/receivables-view/api/receivables"
    suggestion = client.get(base + "/customer-suggestions", query_string={"q": "carl"}).get_json()["data"][0]
    assert suggestion["open_tab_id"] == old["tab_id"]
    saved = client.post(base, json={
        "customer_name": suggestion["customer_name"], "customer_contact": suggestion["customer_contact"],
        "tab_id": suggestion["open_tab_id"], "items_description": "Today", "amount_owed": "50.00",
        "incurred_date": "2026-10-05", "due_date": "2026-10-10",
    })
    assert saved.status_code == 201 and saved.get_json()["data"]["tab_id"] == old["tab_id"]
    assert client.get(base, query_string={"date": "2026-09-30", "page": 1}).get_json()["totals"]["selected_taken"] == 100
    today_view = client.get(base, query_string={"date": "2026-10-05", "page": 1}).get_json()
    assert today_view["totals"] == {"all_outstanding": 150, "selected_taken": 50, "selected_outstanding": 50}
    assert today_view["data"][0]["items"] == "Today"
    assert client.get(base + "/tabs", query_string={"date": "2026-10-05"}).get_json()["data"][0]["outstanding_balance"] == 150

    paid_day = manila_date(datetime.utcnow())
    with app.app_context():
        assert SalesRepository().daily_ledger(paid_day, paid_day) == {}
    path = f"{base}/tabs/{old['tab_id']}/payments"
    result = client.post(path, json={"amount": "70.00", "payment_method": "gcash"},
                         headers={"Idempotency-Key": "carl-partial-payment"})
    assert result.status_code == 200
    assert client.post(path, json={"amount": "70.00", "payment_method": "gcash"},
                       headers={"Idempotency-Key": "carl-partial-payment"}).status_code == 409
    with app.app_context():
        payments = ReceivablePayment.query.all()
        assert len(payments) == 1
        assert (payments[0].amount, payments[0].balance_before, payments[0].balance_after) == (
            Decimal("70.00"), Decimal("100.00"), Decimal("30.00"))
        ledger = SalesRepository().daily_ledger(paid_day, paid_day)[paid_day]
        assert ledger["collection_methods"]["gcash"] == 70
        assert ledger["total_collections"] == ledger["net_balance"] == 70
        assert ledger["total_revenue"] == 0
