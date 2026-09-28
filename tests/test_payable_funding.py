"""Supplier payment funding, history, and Daily Balance use one dated ledger."""

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app import create_app, db
from app.models import CustomerSession, Payable, PayablePayment, Receivable, ReceivablePayment, SpaceType, Transaction
from app.repositories.sales_repository import SalesRepository
from app.services.daily_balance_export_service import DailyBalanceExportService

import app.services.payable_service as payable_service
import app.services.expense_service as expense_service


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


@pytest.fixture
def admin_client(app, monkeypatch):
    class FrozenDateTime:
        current = datetime(2026, 9, 25, 3)

        @classmethod
        def utcnow(cls):
            return cls.current

    monkeypatch.setattr(payable_service, "datetime", FrozenDateTime)
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="admin",
                    last_activity=datetime.now(timezone.utc).timestamp())
    return client, FrozenDateTime


def _payable(amount, name):
    return Payable(creditor_name=name, items_description="Supplies", amount_owed=Decimal(str(amount)),
                   partial_paid=Decimal("0"), due_date=date(2026, 9, 25),
                   incurred_date=date(2026, 9, 25), created_by=1, status="Unpaid")


def _pay(client, payable_id, method, amount, key):
    body = {"payment_method": method}
    if amount is not None:
        body["amount"] = amount
    return client.patch(f"/admin/payables/api/payables/{payable_id}/mark-paid",
                        json=body, headers={"Idempotency-Key": key})


def test_available_funds_round_trip_through_json_without_losing_a_cent():
    daily = SalesRepository.daily_ledger_empty(date(2026, 9, 25))
    daily["checkout_methods"]["gcash"] = 0.7999999999999999
    assert SalesRepository.method_balance(daily, "gcash") == Decimal("0.80")


def test_payables_reconcile_by_method_history_and_exports(app, admin_client):
    client, _ = admin_client
    day = date(2026, 9, 25)
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        sessions = [CustomerSession(customer_name=f"Customer {n}", space_type_id=space.id,
                                    time_in=datetime(2026, 9, 25, 2), status="completed") for n in range(4)]
        db.session.add_all(sessions)
        db.session.flush()
        db.session.add_all([
            Transaction(session_id=sessions[0].id, time_bill=Decimal("500"), food_bill=0,
                        total_bill=Decimal("500"), payment_method="gcash", created_at=datetime(2026, 9, 25, 2)),
            Transaction(session_id=sessions[1].id, time_bill=Decimal("100"), food_bill=0,
                        total_bill=Decimal("100"), payment_method="bdo", created_at=datetime(2026, 9, 25, 2)),
            Transaction(session_id=sessions[2].id, time_bill=Decimal("100"), food_bill=0,
                        total_bill=Decimal("100"), payment_method="bpi", created_at=datetime(2026, 9, 25, 2)),
            Transaction(session_id=sessions[3].id, time_bill=Decimal("1000"), food_bill=0,
                        total_bill=Decimal("1000"), payment_method="queenbank", created_at=datetime(2026, 9, 24, 2)),
        ])
        debt = Receivable(customer_name="Debtor", items_description="Debt", amount_owed=Decimal("50"),
                          partial_paid=Decimal("50"), due_date=day, created_by=1)
        db.session.add(debt)
        db.session.flush()
        db.session.add(ReceivablePayment(receivable_id=debt.id, amount=Decimal("50"),
                                         payment_method="gcash", received_by=1,
                                         received_at=datetime(2026, 9, 25, 2, 30)))
        payables = [_payable(amount, name) for amount, name in
                    [(600, "GCash supplier"), (400, "BDO supplier"), (100, "BPI supplier"),
                     (50, "QueenBank supplier"), (20, "Cash supplier")]]
        db.session.add_all(payables)
        db.session.commit()
        ids = [payable.id for payable in payables]

    payments = [
        (ids[0], "gcash", "200", "gcash-first", "business"),
        (ids[0], "gcash", "400", "gcash-second", "external"),
        (ids[1], "bdo", None, "bdo-full", "external"),
        (ids[2], "bpi", None, "bpi-exact", "business"),
        (ids[3], "queenbank", None, "queenbank-zero", "external"),
        (ids[4], "cash", None, "cash-existing-behavior", "business"),
    ]
    first_id = None
    for payable_id, method, amount, key, expected_source in payments:
        response = _pay(client, payable_id, method, amount, key)
        assert response.status_code == 200
        assert response.get_json()["funding_source"] == expected_source
        if key == "gcash-first":
            first_id = response.get_json()["payment_id"]

    replay = _pay(client, ids[0], "gcash", "200", "gcash-first")
    assert replay.status_code == 200
    assert replay.get_json()["payment_id"] == first_id
    assert replay.get_json()["replayed"] is True
    conflict = _pay(client, ids[0], "gcash", "300", "gcash-first")
    assert conflict.status_code == 409

    with app.app_context():
        assert PayablePayment.query.count() == 6
        paid = db.session.get(Payable, ids[0])
        assert (paid.partial_paid, paid.status) == (Decimal("600"), "Paid")
        entries = PayablePayment.query.filter_by(payable_id=ids[0]).order_by(PayablePayment.id).all()
        assert [(entry.balance_before, entry.balance_after) for entry in entries] == [
            (Decimal("600"), Decimal("400")), (Decimal("400"), Decimal("0"))]
        assert [(entry.method_balance_before, entry.method_balance_after) for entry in entries] == [
            (Decimal("550"), Decimal("350")), (Decimal("350"), Decimal("350"))]
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["total_payables_paid"] == 1170
        assert ledger["total_business_payables_paid"] == 320
        assert ledger["total_external_payables_paid"] == 850
        assert ledger["payable_methods"]["gcash"] == 200
        assert ledger["external_payable_methods"]["gcash"] == 400
        assert ledger["external_payable_methods"]["bdo"] == 400
        assert ledger["payable_methods"]["bpi"] == 100
        assert ledger["external_payable_methods"]["queenbank"] == 50
        assert ledger["payable_methods"]["cash"] == 20
        assert ledger["net_balance"] == 430
        assert sum(SalesRepository.method_balance(ledger, method) for method in
                   ("cash", "gcash", "bdo", "bpi", "queenbank")) == Decimal("430")

    history = client.get("/admin/payables/api/payables").get_json()["data"]
    gcash_history = next(row for row in history if row["id"] == ids[0])["payments"]
    assert {entry["funding_source"] for entry in gcash_history} == {"business", "external"}
    assert all(entry["paid_at"] and entry["paid_by"] and entry["method_balance_before"] is not None
               for entry in gcash_history)
    report = client.get(f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}").get_json()["data"][0]
    assert (report["total_payables_paid"], report["total_external_payables_paid"], report["net_balance"]) == (1170, 850, 430)
    generated = client.post("/admin/daily-balance/api/reports", json={"report_date": str(day), "notes": "Supplier reconciliation"},
                            headers={"Idempotency-Key": "payable-daily-report"})
    assert generated.status_code == 201
    assert (generated.get_json()["data"]["total_payables_paid"], generated.get_json()["data"]["net_balance"]) == (1170, 430)
    context = DailyBalanceExportService(db).build_pdf_context([report], [])
    assert context["total_external_payables_paid"] == 850
    assert next(row for row in context["method_rows"] if row["method"] == "gcash")["net"] == 350
    csv_data = client.get(f"/admin/daily-balance/api/reports/export-csv?start_date={day}&end_date={day}").data.decode("utf-8")
    assert "External-funded Supplier Paid" in csv_data and "₱850.00" in csv_data
    pdf = client.get(f"/admin/daily-balance/api/reports/export-pdf?start_date={day}&end_date={day}")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    excel = client.get(f"/admin/daily-balance/api/reports/export-excel?start_date={day}&end_date={day}")
    assert excel.status_code == 200
    workbook = load_workbook(BytesIO(excel.data))
    assert workbook["Summary"]["B23"].value == 850
    method_rows = list(workbook["Payment Methods"].values)
    gcash_col = method_rows[0].index("gcash")
    assert any(row[1] == "external_payable" and row[gcash_col] == 400 for row in method_rows)


def test_payable_new_day_starts_at_zero_and_legacy_keeps_old_effect(app, admin_client):
    client, clock = admin_client
    with app.app_context():
        payable = _payable(100, "Supplier")
        old_payable = _payable(10, "Old supplier")
        old_payable.partial_paid = Decimal("10")
        old_payable.status = "Paid"
        db.session.add_all([payable, old_payable])
        db.session.flush()
        old_payment = PayablePayment(payable_id=old_payable.id, amount=Decimal("10"),
                                     payment_method="gcash", paid_by=1,
                                     paid_at=datetime(2026, 9, 25, 2),
                                     balance_before=Decimal("10"), balance_after=Decimal("0"))
        db.session.add(old_payment)
        db.session.commit()
        payable_id = payable.id
        old_payable_id = old_payable.id
    clock.current = datetime(2026, 9, 26, 3)
    response = _pay(client, payable_id, "gcash", "100", "new-day-no-carry")
    assert response.status_code == 200
    assert response.get_json()["funding_source"] == "external"
    with app.app_context():
        old = SalesRepository().daily_ledger(date(2026, 9, 25), date(2026, 9, 25))[date(2026, 9, 25)]
        new = SalesRepository().daily_ledger(date(2026, 9, 26), date(2026, 9, 26))[date(2026, 9, 26)]
        assert old["payable_methods"]["gcash"] == 10
        assert new["external_payable_methods"]["gcash"] == 100
        assert SalesRepository.method_balance(new, "gcash") == Decimal("0")
    history = client.get("/admin/payables/api/payables").get_json()["data"]
    assert next(row for row in history if row["id"] == old_payable_id)["payments"][0]["funding_source"] == "legacy"


def test_expense_and_payable_share_the_same_business_method_balance(app, admin_client, monkeypatch):
    client, clock = admin_client
    monkeypatch.setattr(expense_service, "datetime", clock)
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        session = CustomerSession(customer_name="Customer", space_type_id=space.id,
                                  time_in=datetime(2026, 9, 25, 2), status="completed")
        db.session.add(session)
        db.session.flush()
        db.session.add(Transaction(session_id=session.id, time_bill=Decimal("100"), food_bill=0,
                                   total_bill=Decimal("100"), payment_method="gcash",
                                   created_at=datetime(2026, 9, 25, 2)))
        payable = _payable(50, "Supplier")
        db.session.add(payable)
        db.session.commit()
        payable_id = payable.id
    expense = client.post("/admin/expenses/api/expenses", json={
        "category": "supplies", "description": "Packaging", "amount": "60",
        "expense_date": "2026-09-25", "payment_method": "gcash",
    }, headers={"Idempotency-Key": "shared-method-expense"})
    assert expense.status_code == 201
    assert expense.get_json()["data"]["funding_source"] == "business"
    payment = _pay(client, payable_id, "gcash", "50", "shared-method-payable")
    assert payment.status_code == 200
    assert payment.get_json()["funding_source"] == "external"
    with app.app_context():
        day = SalesRepository().daily_ledger(date(2026, 9, 25), date(2026, 9, 25))[date(2026, 9, 25)]
        assert day["expense_methods"]["gcash"] == 60
        assert day["external_payable_methods"]["gcash"] == 50
        assert SalesRepository.method_balance(day, "gcash") == Decimal("40")
