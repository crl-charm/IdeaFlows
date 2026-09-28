"""Receivable history and Daily Balance must agree on each collected method."""

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO, StringIO
import csv

import pytest
from openpyxl import load_workbook

from app import create_app, db
from app.core import idempotency
from app.models import Expense, Payable, Receivable, ReceivablePayment
from app.repositories.sales_repository import SalesRepository
from app.services.daily_balance_export_service import DailyBalanceExportService

import app.services.expense_service as expense_service
import app.services.payable_service as payable_service
import app.services.receivable_service as receivable_service


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _auth(client, role="staff"):
    with client.session_transaction() as session:
        session.update(user_id=1, username="test_user", role=role,
                       last_activity=datetime.now(timezone.utc).timestamp())


def _debt(name, item, amount, day):
    return Receivable(customer_name=name, customer_contact="09123456789",
                      items_description=item, amount_owed=Decimal(str(amount)),
                      partial_paid=Decimal("0"), due_date=day, incurred_date=day,
                      created_by=1)


@pytest.mark.parametrize("method", ["cash", "gcash", "bdo", "bpi", "queenbank"])
def test_grouped_staff_collection_reconciles_across_history_and_daily_balance(app, monkeypatch, method):
    class Clock:
        @staticmethod
        def utcnow():
            return datetime(2026, 9, 24, 16, 30)  # Sep 25 in Manila

    monkeypatch.setattr(receivable_service, "datetime", Clock)
    day = date(2026, 9, 25)
    with app.app_context():
        debts = [_debt("Carl", "Snack", 30, day), _debt("carl", "Lunch", 50, day)]
        db.session.add_all(debts)
        db.session.commit()
        ids = [debt.id for debt in debts]

    client = app.test_client()
    _auth(client)
    url = "/receivables-view/api/receivables/customer-payment"
    body = {"customer_name": "Carl", "customer_contact": "09123456789",
            "amount": "40.00", "payment_method": method}
    key = f"collection-{method}"
    response = client.post(url, json=body, headers={"Idempotency-Key": key})
    assert response.status_code == 200
    assert response.get_json()["remaining"] == 40
    assert client.post(url, json=body, headers={"Idempotency-Key": key}).status_code == 409

    history = client.get("/receivables-view/api/receivables/customer-payments",
                         query_string={"customer_name": "Carl", "customer_contact": "09123456789"})
    assert history.status_code == 200
    entries = history.get_json()["data"]
    assert len(entries) == 1
    assert entries[0]["amount"] == 40
    assert entries[0]["payment_method"] == method
    assert entries[0]["received_by"] == "Test User"
    assert entries[0]["received_at"] == "2026-09-24T16:30:00Z"
    assert [(a["balance_before"], a["balance_after"]) for a in sorted(entries[0]["allocations"], key=lambda a: a["receivable_id"])] == [
        (30, 0), (50, 40)]

    with app.app_context():
        payments = ReceivablePayment.query.order_by(ReceivablePayment.id).all()
        assert len(payments) == 2
        assert {p.receivable_id for p in payments} == set(ids)
        assert len({p.payment_group_id for p in payments}) == 1
        assert sum((p.amount for p in payments), Decimal("0")) == Decimal("40")
        assert all(p.received_at == Clock.utcnow() and p.request_key == key for p in payments)
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["collection_methods"][method] == 40
        assert ledger["collection_count"] == 1
        assert ledger["total_collections"] == ledger["net_balance"] == 40
        assert ledger["total_revenue"] == 0
        assert SalesRepository.method_balance(ledger, method) == Decimal("40")
        assert DailyBalanceExportService(db).build_pdf_context([ledger], [])["method_rows"][
            list(DailyBalanceExportService.METHODS).index(method)]["collection"] == 40

    report_url = f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}"
    report = client.get(report_url).get_json()["data"][0]
    assert (report["total_revenue"], report["total_collections"],
            report["collection_methods"][method], report["net_balance"]) == (0, 40, 40, 40)
    staff_page = client.get("/receivables-view")
    assert b'id="receivable-method-cards"' in staff_page.data
    assert b'receivable-collections.js' in staff_page.data

    _auth(client, "admin")
    admin_page = client.get("/admin/receivables")
    assert b'id="receivable-method-cards"' in admin_page.data
    assert b'receivable-collections.js' in admin_page.data
    generated = client.post("/admin/daily-balance/api/reports",
                            json={"report_date": str(day), "notes": "Collection audit"},
                            headers={"Idempotency-Key": f"collection-report-{method}"})
    assert generated.status_code == 201
    assert (generated.get_json()["data"]["total_revenue"],
            generated.get_json()["data"]["total_collections"]) == (0, 40)
    csv_response = client.get(f"/admin/daily-balance/api/reports/export-csv?start_date={day}&end_date={day}")
    csv_row = next(csv.DictReader(StringIO(csv_response.data.decode("utf-8-sig"))))
    assert csv_row["Debt Collected"] == "₱40.00"
    assert csv_row[f"Collection {method.title()}"] == "₱40.00"


def test_admin_partial_payment_history_and_retry_after_cache_expiry(app, monkeypatch):
    class Clock:
        @staticmethod
        def utcnow():
            return datetime(2026, 9, 25, 3)

    monkeypatch.setattr(receivable_service, "datetime", Clock)
    day = date(2026, 9, 25)
    with app.app_context():
        debt = _debt("Ana", "Boardroom", 100, day)
        db.session.add(debt)
        db.session.commit()
        debt_id = debt.id

    client = app.test_client()
    _auth(client, "admin")
    url = f"/admin/receivables/api/receivables/{debt_id}/mark-paid"
    first = client.patch(url, json={"amount": "35.50", "payment_method": "bdo"},
                         headers={"Idempotency-Key": "ana-bdo-partial"})
    assert first.status_code == 200
    monkeypatch.setattr(idempotency, "_local_requests", {})  # Simulate HTTP cache expiry.
    retry = client.patch(url, json={"amount": "35.50", "payment_method": "bdo"},
                         headers={"Idempotency-Key": "ana-bdo-partial"})
    assert retry.status_code == 400
    second = client.patch(url, json={"amount": "64.50", "payment_method": "bpi"},
                          headers={"Idempotency-Key": "ana-bpi-full"})
    assert second.status_code == 200

    with app.app_context():
        debt = db.session.get(Receivable, debt_id)
        assert debt.paid and debt.partial_paid == Decimal("100")
        assert debt.paid_at == Clock.utcnow()
        payments = ReceivablePayment.query.order_by(ReceivablePayment.id).all()
        assert [(p.amount, p.balance_before, p.balance_after, p.payment_method) for p in payments] == [
            (Decimal("35.50"), Decimal("100"), Decimal("64.50"), "bdo"),
            (Decimal("64.50"), Decimal("64.50"), Decimal("0"), "bpi")]
        assert all(p.received_at == Clock.utcnow() for p in payments)

    history = client.get("/admin/receivables/api/receivables/customer-payments",
                         query_string={"customer_name": "Ana", "customer_contact": "09123456789"}).get_json()["data"]
    assert {entry["payment_method"] for entry in history} == {"bdo", "bpi"}
    report = client.get(f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}").get_json()["data"][0]
    assert report["collection_methods"]["bdo"] == 35.5
    assert report["collection_methods"]["bpi"] == 64.5
    assert (report["total_collections"], report["total_revenue"], report["net_balance"]) == (100, 0, 100)


def test_manila_midnight_and_later_spending_use_only_todays_collection(app, monkeypatch):
    class Clock:
        current = datetime(2026, 9, 24, 15, 59)

        @classmethod
        def utcnow(cls):
            return cls.current

    for service in (receivable_service, expense_service, payable_service):
        monkeypatch.setattr(service, "datetime", Clock)
    with app.app_context():
        debt = _debt("Mia", "Tab", 50, date(2026, 9, 25))
        payable = Payable(creditor_name="Supplier", items_description="Stock",
                          amount_owed=Decimal("20"), partial_paid=Decimal("0"),
                          due_date=date(2026, 9, 25), incurred_date=date(2026, 9, 25),
                          created_by=1, status="Unpaid")
        db.session.add_all([debt, payable])
        db.session.commit()
        debt_id, payable_id = debt.id, payable.id

    client = app.test_client()
    _auth(client, "admin")
    pay_url = f"/admin/receivables/api/receivables/{debt_id}/mark-paid"
    assert client.patch(pay_url, json={"amount": "10", "payment_method": "gcash"},
                        headers={"Idempotency-Key": "mia-before-midnight"}).status_code == 200
    Clock.current = datetime(2026, 9, 24, 16, 1)
    assert client.patch(pay_url, json={"amount": "40", "payment_method": "gcash"},
                        headers={"Idempotency-Key": "mia-after-midnight"}).status_code == 200
    expense = client.post("/admin/expenses/api/expenses", json={
        "category": "supplies", "description": "Packaging", "amount": "25",
        "expense_date": "2026-09-25", "payment_method": "gcash",
    }, headers={"Idempotency-Key": "mia-funded-expense"})
    assert expense.status_code == 201
    assert expense.get_json()["data"]["funding_source"] == "business"
    supplier = client.patch(f"/admin/payables/api/payables/{payable_id}/mark-paid",
                            json={"amount": "20", "payment_method": "gcash"},
                            headers={"Idempotency-Key": "mia-external-payable"})
    assert supplier.status_code == 200
    assert supplier.get_json()["funding_source"] == "external"

    with app.app_context():
        ledger = SalesRepository().daily_ledger(date(2026, 9, 24), date(2026, 9, 25))
        old, today = ledger[date(2026, 9, 24)], ledger[date(2026, 9, 25)]
        assert old["collection_methods"]["gcash"] == 10
        assert today["collection_methods"]["gcash"] == 40
        assert today["expense_methods"]["gcash"] == 25
        assert today["external_payable_methods"]["gcash"] == 20
        assert SalesRepository.method_balance(today, "gcash") == Decimal("15")
        assert db.session.query(Expense).one().balance_before == Decimal("40")

    report = client.get("/admin/daily-balance/api/reports?start_date=2026-09-25&end_date=2026-09-25").get_json()["data"][0]
    assert (report["total_collections"], report["total_revenue"], report["net_balance"]) == (40, 0, 15)
    export = client.get("/admin/daily-balance/api/reports/export-excel?start_date=2026-09-25&end_date=2026-09-25")
    assert export.status_code == 200
    workbook = load_workbook(BytesIO(export.data))
    rows = list(workbook["Payment Methods"].values)
    gcash_column = rows[0].index("gcash")
    assert next(row[gcash_column] for row in rows if row[1] == "collection") == 40
    assert client.get("/admin/daily-balance/api/reports/export-pdf?start_date=2026-09-25&end_date=2026-09-25").data.startswith(b"%PDF")
