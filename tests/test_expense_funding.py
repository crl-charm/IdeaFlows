"""Expense funding must reconcile with the same Daily Balance ledger in every view."""

from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app import create_app, db
from app.models import CustomerSession, Expense, Receivable, ReceivablePayment, SpaceType, Transaction
from app.repositories.sales_repository import SalesRepository
from app.services.daily_balance_export_service import DailyBalanceExportService
from app.utils.dates import manila_date
import app.services.expense_service as expense_service


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


@pytest.fixture
def admin_client(app, monkeypatch):
    class FrozenDateTime:
        current = datetime(2026, 9, 25, 3, 0)

        @classmethod
        def utcnow(cls):
            return cls.current

    monkeypatch.setattr(expense_service, "datetime", FrozenDateTime)
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="admin",
                    last_activity=datetime.now(timezone.utc).timestamp())
    return client, FrozenDateTime


def _post_expense(client, amount, method, key, receipt_date="2026-09-25"):
    return client.post("/admin/expenses/api/expenses", json={
        "category": "supplies", "description": f"{method} supplies", "amount": amount,
        "expense_date": receipt_date, "payment_method": method,
    }, headers={"Idempotency-Key": key})


def _sale(session_id, amount, method, when):
    return Transaction(session_id=session_id, time_bill=amount, food_bill=0,
                       total_bill=amount, payment_method=method, created_at=when)


def test_method_funding_and_void_reconcile_across_history_report_and_exports(app, admin_client):
    client, _ = admin_client
    day = date(2026, 9, 25)
    for path in ("/admin/expenses", "/expenses-view", "/admin/daily-balance"):
        assert client.get(path).status_code == 200
    assert client.get("/static/js/expense-summary.js").status_code == 200
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        sessions = [CustomerSession(customer_name=f"Customer {n}", space_type_id=space.id,
                                    time_in=datetime(2026, 9, 25, 2), status="completed") for n in range(3)]
        db.session.add_all(sessions)
        db.session.flush()
        db.session.add_all([
            _sale(sessions[0].id, Decimal("100"), "gcash", datetime(2026, 9, 25, 2, 10)),
            _sale(sessions[1].id, Decimal("80"), "bdo", datetime(2026, 9, 25, 2, 15)),
            _sale(sessions[2].id, Decimal("1000"), "gcash", datetime(2026, 9, 24, 2, 10)),
        ])
        debt = Receivable(customer_name="Debtor", items_description="Debt", amount_owed=Decimal("50"),
                          partial_paid=Decimal("50"), due_date=day, created_by=1)
        db.session.add(debt)
        db.session.flush()
        db.session.add(ReceivablePayment(receivable_id=debt.id, amount=Decimal("50"), payment_method="gcash",
                                         received_by=1, received_at=datetime(2026, 9, 25, 2, 30)))
        db.session.commit()

    ids = {}
    for amount, method, key, source in (
        ("100.00", "gcash", "gcash-business", "business"),
        ("75.00", "gcash", "gcash-owner", "external"),
        ("200.00", "bdo", "bdo-owner", "external"),
        ("20.00", "cash", "cash-business", "business"),
    ):
        response = _post_expense(client, amount, method, key,
                                 receipt_date="2026-09-24" if key == "gcash-owner" else "2026-09-25")
        assert response.status_code == 201
        assert response.get_json()["data"]["funding_source"] == source
        ids[key] = response.get_json()["data"]["id"]

    with app.app_context():
        rows = {e.id: e for e in Expense.query.all()}
        assert (rows[ids["gcash-business"]].balance_before,
                rows[ids["gcash-business"]].balance_after) == (Decimal("150"), Decimal("50"))
        assert (rows[ids["gcash-owner"]].balance_before,
                rows[ids["gcash-owner"]].balance_after) == (Decimal("50"), Decimal("50"))
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["expense_methods"]["gcash"] == 100
        assert ledger["external_expense_methods"]["gcash"] == 75
        assert ledger["external_expense_methods"]["bdo"] == 200
        assert ledger["total_expenses"] == 395
        assert ledger["total_business_expenses"] == 120
        assert ledger["total_external_expenses"] == 275
        assert ledger["net_balance"] == 110
        assert SalesRepository.method_balance(ledger, "gcash") == Decimal("50")

    report = client.get(f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}").get_json()["data"][0]
    assert (report["total_expenses"], report["total_external_expenses"], report["net_balance"]) == (395, 275, 110)
    history = client.get("/expenses-view/api/expenses").get_json()["data"]
    assert {e["funding_source"] for e in history} == {"business", "external"}
    assert all(e["business_date"] == day.isoformat() and e["posted_at"] for e in history)
    assert next(e for e in history if e["id"] == ids["gcash-owner"])["expense_date"] == "2026-09-24"
    with app.app_context():
        context = DailyBalanceExportService(db).build_pdf_context([report], [])
    assert context["total_external_expenses"] == 275
    assert next(row for row in context["method_rows"] if row["method"] == "gcash")["net"] == 50
    csv_data = client.get(f"/admin/daily-balance/api/reports/export-csv?start_date={day}&end_date={day}").data.decode("utf-8")
    assert "External-funded Expenses" in csv_data and "₱275.00" in csv_data
    pdf = client.get(f"/admin/daily-balance/api/reports/export-pdf?start_date={day}&end_date={day}")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")
    excel = client.get(f"/admin/daily-balance/api/reports/export-excel?start_date={day}&end_date={day}")
    assert excel.status_code == 200
    methods_sheet = load_workbook(BytesIO(excel.data))["Payment Methods"]
    excel_rows = list(methods_sheet.values)
    bdo_column = excel_rows[0].index("bdo")
    assert any(row[1] == "external_expense" and row[bdo_column] == 200 for row in excel_rows)

    for key in ("gcash-business", "gcash-owner"):
        response = client.delete(f"/admin/expenses/api/expenses/{ids[key]}",
                                 json={"reason": "Receipt correction"},
                                 headers={"Idempotency-Key": f"void-{key}"})
        assert response.status_code == 200
    assert client.delete(f"/admin/expenses/api/expenses/{ids['gcash-business']}",
                         json={"reason": "Again"}).status_code == 404
    with app.app_context():
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["expense_methods"]["gcash"] == 0
        assert ledger["external_expense_methods"]["gcash"] == 0
        assert ledger["expense_void_methods"]["gcash"] == 175
        assert ledger["net_balance"] == 210
        assert SalesRepository.method_balance(ledger, "gcash") == Decimal("150")
        owner_void = db.session.get(Expense, ids["gcash-owner"])
        assert (owner_void.void_balance_before, owner_void.void_balance_after) == (Decimal("150"), Decimal("150"))
    history = client.get("/admin/expenses/api/expenses").get_json()["data"]
    assert next(e for e in history if e["id"] == ids["gcash-business"])["void_reason"] == "Receipt correction"


def test_later_day_void_is_reversal_not_rewrite(app, admin_client):
    client, clock = admin_client
    day = date(2026, 9, 25)
    next_day = date(2026, 9, 26)
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        session = CustomerSession(customer_name="Customer", space_type_id=space.id,
                                  time_in=datetime(2026, 9, 25, 2), status="completed")
        db.session.add(session)
        db.session.flush()
        db.session.add(_sale(session.id, Decimal("100"), "gcash", datetime(2026, 9, 25, 2)))
        db.session.commit()
    expense = _post_expense(client, "60.00", "gcash", "day-one")
    assert expense.status_code == 201
    expense_id = expense.get_json()["data"]["id"]
    clock.current = datetime(2026, 9, 26, 3)
    voided = client.delete(f"/admin/expenses/api/expenses/{expense_id}",
                           json={"reason": "Wrong receipt"}, headers={"Idempotency-Key": "day-two-void"})
    assert voided.status_code == 200
    with app.app_context():
        daily = SalesRepository().daily_ledger(day, next_day)
        assert daily[day]["expense_methods"]["gcash"] == 60
        assert daily[day]["net_balance"] == 40
        assert daily[next_day]["expense_methods"]["gcash"] == -60
        assert daily[next_day]["expense_void_methods"]["gcash"] == 60
        assert daily[next_day]["net_balance"] == 60
        entry = db.session.get(Expense, expense_id)
        assert manila_date(entry.voided_at) == next_day
        assert (entry.void_balance_before, entry.void_balance_after) == (Decimal("0"), Decimal("60"))


@pytest.mark.parametrize("amount", [None, "0", "-1", "0.001", "100000000", "NaN"])
def test_invalid_expense_amount_does_not_post(app, admin_client, amount):
    client, _ = admin_client
    response = _post_expense(client, amount, "gcash", f"bad-{amount}")
    assert response.status_code == 400
    with app.app_context():
        assert Expense.query.count() == 0
