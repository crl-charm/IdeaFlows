"""Monthly cost allocation, attendance and salary privacy share the existing cash ledger."""
from datetime import date, datetime, timezone
from decimal import Decimal
from io import BytesIO
import re

import pytest
from sqlalchemy import inspect, text

from app import create_app, db, socketio
from app.db.migrator import SchemaMigrator
from app.models import (User, Expense, StaffShift, StaffAttendance, CustomerSession, SpaceType,
                        Transaction, CheckoutVoidRequest, Payable, PayablePayment, FinanceTransaction)
from app.repositories.sales_repository import SalesRepository
from app.services.accountant_report_service import AccountantReportService
import app.services.expense_service as expense_module
import app.services.accountant_report_service as report_module
from app.utils.dates import month_bounds


@pytest.fixture
def app():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return app


@pytest.fixture
def team(app, monkeypatch):
    class Clock(datetime):
        current = datetime(2026, 11, 5, 3)

        @classmethod
        def utcnow(cls):
            return cls.current
    monkeypatch.setattr(expense_module, "datetime", Clock)
    monkeypatch.setattr(report_module, "datetime", Clock)
    with app.app_context():
        db.session.get(User, 1).role = "admin"
        for id, name in ((2, "Payroll Employee"), (3, "Ordinary Staff")):
            user = User(id=id, full_name=name, username=f"employee_{id}", role="staff", is_active=True)
            user.set_password("IsolatedStaff123!")
            db.session.add(user)
        db.session.commit()
    return Clock


def login(client, role="admin"):
    with client.session_transaction() as session:
        session.update(user_id=1 if role == "admin" else 3, role=role,
                       username="test_user" if role == "admin" else "employee_3",
                       last_activity=datetime.now(timezone.utc).timestamp())


def salary(client, amount="20000.00", month="2026-10", paid="2026-11-05", **extra):
    return client.post("/admin/expenses/api/expenses", json={
        "category": "salaries", "description": "", "salary_employee_id": 2, "salary_month": month,
        "amount": amount, "expense_date": paid, "payment_method": "gcash", **extra})


def test_october_salary_paid_in_november_counts_once_and_keeps_cash_dates(app, team):
    client = app.test_client()
    login(client)
    team.current = datetime(2026, 10, 15, 2)
    repair = client.post("/admin/expenses/api/expenses", json={
        "category": "repairs_maintenance", "description": "Aircon repair", "amount": "5000.00",
        "expense_date": "2026-10-15", "payment_method": "bdo"})
    assert repair.status_code == 201
    team.current = datetime(2026, 11, 5, 3)
    assert salary(client, "12000").status_code == salary(client, "8000").status_code == 201
    with app.app_context():
        october = AccountantReportService.build("2026-10", 1)
        november = AccountantReportService.build("2026-11", 1)
        assert (october["salary_total"], october["other_expenses"], october["total_expenses"]) == (20000, 5000, 25000)
        assert november["salary_total"] == november["total_expenses"] == 0
        assert october["reconciliation"]["allocated_here_paid_elsewhere"] == 20000
        assert november["reconciliation"]["paid_here_other_salary_month"] == 20000
        assert october["reconciliation"]["net_posted_expenses"] == 5000
        assert november["reconciliation"]["net_posted_expenses"] == 20000
        assert len(october["salary_employees"]) == 1 and len(october["salary_employees"][0]["payments"]) == 2
        assert Expense.query.count() == 3 and FinanceTransaction.query.count() == 0
        db.session.get(User, 2).full_name = "Renamed employee"
        db.session.commit()
        assert AccountantReportService.build("2026-10", 1)["salary_employees"][0]["name"] == "Payroll Employee"


def test_owner_paid_salary_reimbursement_is_private_and_not_another_expense(app, team):
    client = app.test_client()
    login(client)
    result = salary(client, "8000", payment_method="cash", cash_box="owner", repay_owner=True)
    assert result.status_code == 201
    with app.app_context():
        payable = Payable.query.one()
        payable_id = payable.id
        assert Expense.query.count() == 1 and payable.owner_expense_id == result.json["data"]["id"]
    login(client, "staff")
    for base in ("/staff/payables",):
        response = client.get(base + "/api/payables")
        assert response.status_code == 200 and response.json["data"] == []
        assert client.get(base + "/api/due-count").json["count"] == 0
        assert client.patch(f"{base}/api/payables/{payable_id}/mark-paid", json={"amount": "8000", "payment_method": "cash"}).status_code == 404
    assert client.get("/admin/payables/api/payables").status_code == 403
    login(client)
    assert len(client.get("/admin/payables/api/payables").json["data"]) == 1
    assert client.patch(f"/admin/payables/api/payables/{payable_id}/mark-paid", json={"amount": "8000", "payment_method": "cash"}).status_code == 200
    with app.app_context():
        assert Expense.query.count() == PayablePayment.query.count() == 1
        assert AccountantReportService.build("2026-10", 1)["total_expenses"] == 8000
        assert AccountantReportService.build("2026-11", 1)["total_expenses"] == 0


@pytest.mark.parametrize("payload", [
    {"category": "salaries"}, {"category": " SALARY "}, {"category": "PAYROLL"},
    {"category": "misc", "salary_month": "2026-10"},
    {"category": "misc", "salary_employee_id": None}, {"category": "misc", "salary_employee_name": "spoof"},
])
def test_staff_cannot_submit_salary_category_or_metadata(app, team, payload):
    client = app.test_client()
    login(client, "staff")
    assert client.post("/expenses-view/api/expenses", json={"amount": "100", "description": "Attempt", **payload}).status_code == 403
    with app.app_context():
        assert Expense.query.count() == 0


def test_staff_history_and_daily_exports_do_not_contain_salary_details(app, team):
    client = app.test_client()
    login(client)
    assert salary(client, "12345.67", description="SECRET WAGE DESCRIPTION").status_code == 201
    login(client, "staff")
    assert client.post("/expenses-view/api/expenses", json={
        "category": "repairs_maintenance", "description": "Ordinary repair", "amount": "50",
        "expense_date": "2026-10-15", "payment_method": "bdo"}).status_code == 201
    rows = client.get("/expenses-view/api/expenses").json["data"]
    assert len(rows) == 1 and rows[0]["description"] == "Ordinary repair"
    assert not any(key.startswith("salary_") for key in rows[0])
    page = client.get("/expenses-view").data
    assert b"SECRET WAGE" not in page and b"Payroll Employee" not in page and b'value="salaries"' not in page
    assert b"Repairs / Maintenance" in page
    for suffix in ("", "/pdf"):
        assert client.get("/admin/reports/api/monthly-accountant" + suffix + "?month=2026-10").status_code == 403
    assert client.patch("/admin/expenses/api/expenses/1/salary-metadata", json={"confirmed": True}).status_code == 403
    for export in ("export-csv", "export-excel", "export-pdf"):
        response = client.get(f"/staff/daily-balance/api/reports/{export}?start_date=2026-11-01&end_date=2026-11-30")
        assert response.status_code == 200
        if export == "export-pdf":
            from pypdf import PdfReader
            content = "\n".join(p.extract_text() for p in PdfReader(BytesIO(response.data)).pages)
        elif export == "export-excel":
            from openpyxl import load_workbook
            book = load_workbook(BytesIO(response.data))
            content = str([list(sheet.values) for sheet in book])
        else:
            content = response.data.decode()
        assert "SECRET WAGE" not in content and "Payroll Employee" not in content and "salary_month" not in content
    daily = client.get("/staff/daily-balance/api/reports?start_date=2026-11-05&end_date=2026-11-05").json["data"]
    assert daily[0]["total_expenses"] == 12395.67  # Operational totals retain all actual spending.


def test_salary_entries_use_authenticated_actor_idempotency_and_snapshot(app, team, monkeypatch):
    client = app.test_client()
    login(client)
    import app.routes.expenses as routes
    monkeypatch.setattr(routes, "emit_expenses_update", lambda *a: (_ for _ in ()).throw(RuntimeError("offline")))
    payload = {"category": "salaries", "salary_employee_id": 2, "salary_employee_name": "Spoof",
               "salary_month": "2026-10", "amount": "200", "expense_date": "2026-11-05", "payment_method": "bdo"}
    headers = {"Idempotency-Key": "single-salary-entry"}
    assert client.post("/admin/expenses/api/expenses", json=payload, headers=headers).status_code == 201
    assert client.post("/admin/expenses/api/expenses", json=payload, headers=headers).status_code == 409
    with app.app_context():
        row = Expense.query.one()
        assert row.logged_by == 1 and row.salary_employee_name == "Payroll Employee"
        assert row.salary_month == date(2026, 10, 1)


def test_salary_realtime_notifications_do_not_expose_staff_details(app, team):
    owner, staff = app.test_client(), app.test_client()
    login(owner)
    login(staff, "staff")
    owner_socket = socketio.test_client(app, flask_test_client=owner)
    staff_socket = socketio.test_client(app, flask_test_client=staff)
    assert owner_socket.is_connected() and staff_socket.is_connected()
    owner_socket.get_received()
    staff_socket.get_received()
    try:
        assert salary(owner, description="SECRET SALARY NOTES").status_code == 201
        owner_events = owner_socket.get_received()
        staff_events = staff_socket.get_received()
        assert any(e["name"] == "expenses_update" for e in owner_events)
        assert not any(e["name"] == "expenses_update" for e in staff_events)
        assert any(e["name"] == "daily_balance_update" for e in staff_events)
        assert all("Payroll Employee" not in str(e) and "SECRET SALARY" not in str(e)
                   and "salary_month" not in str(e) for e in staff_events)
    finally:
        owner_socket.disconnect()
        staff_socket.disconnect()


@pytest.mark.parametrize("extra", [
    {"salary_employee_id": True}, {"salary_employee_id": 999}, {"salary_employee_id": 1},
    {"salary_month": "2026-13"}, {"salary_month": "2026-1"}, {"amount": "NaN"},
    {"amount": "1.001"}, {"expense_date": "2026-11-06"},
])
def test_invalid_salary_entries_do_not_post_a_payment(app, team, extra):
    client = app.test_client()
    login(client)
    assert salary(client, **extra).status_code == 400
    with app.app_context():
        assert Expense.query.count() == Payable.query.count() == 0


def test_attendance_clips_month_boundaries_and_unions_overlap_without_login_presence(app, team):
    with app.app_context():
        employee = db.session.get(User, 2)
        employee.is_active = False
        employee.role = "admin"  # A later role change must not remove earlier shifts.
        db.session.add_all([
            StaffShift(user_id=2, shift_role="cashier", time_in=datetime(2026, 10, 31, 14), time_out=datetime(2026, 10, 31, 22)),
            StaffShift(user_id=2, shift_role="cashier", time_in=datetime(2026, 10, 15, 1), time_out=datetime(2026, 10, 15, 4)),
            StaffShift(user_id=2, shift_role="cashier", time_in=datetime(2026, 10, 15, 2), time_out=datetime(2026, 10, 15, 6)),
            StaffShift(user_id=3, shift_role="general", time_in=datetime(2026, 10, 15, 1), time_out=None),
            StaffShift(user_id=3, shift_role="general", time_in=datetime(2026, 10, 15, 5), time_out=datetime(2026, 10, 15, 4)),
            StaffAttendance(user_id=1, time_in=datetime(2026, 10, 1), time_out=datetime(2026, 10, 30)),
        ])
        db.session.commit()
        october = AccountantReportService.build("2026-10", 1)["attendance"]
        november = AccountantReportService.build("2026-11", 1)["attendance"]
        assert october["duration"] == "7h 00m 00s" and october["employee_count"] == 2
        assert october["incomplete"] == october["invalid"] == october["overlap_count"] == 1
        assert november["duration"] == "6h 00m 00s"
        assert october["employees"][1]["name"] == "Payroll Employee"
        assert any(row["status"] == "Completed / month portion only" for row in october["rows"])


def test_sales_use_effective_payment_date_discounts_and_separate_refund_day(app, team):
    with app.app_context():
        space = SpaceType(name="Premium Lounge", rate_per_minute=1)
        db.session.add(space)
        db.session.flush()
        visit = CustomerSession(customer_name="Paid customer", space_type_id=space.id, status="completed")
        db.session.add(visit)
        db.session.flush()
        normal = Transaction(session_id=visit.id, time_bill=100, food_bill=200, total_bill=280, discount_amount=20,
                             discount_item_id=123, paid_at=datetime(2026, 10, 31, 15, 59), created_at=datetime(2026, 11, 1, 1))
        refund = Transaction(session_id=visit.id, time_bill=100, food_bill=0, total_bill=100,
                             created_at=datetime(2026, 10, 15), is_voided=True)
        false = Transaction(session_id=visit.id, time_bill=50, food_bill=0, total_bill=50,
                            created_at=datetime(2026, 10, 15), is_voided=True)
        retained = Transaction(session_id=visit.id, time_bill=60, food_bill=0, total_bill=60,
                               created_at=datetime(2026, 10, 15), is_voided=True)
        db.session.add_all([normal, refund, false, retained])
        db.session.flush()
        for tx, treatment in ((refund, "refund"), (false, "false_entry"), (retained, "retained_credit")):
            db.session.add(CheckoutVoidRequest(transaction_id=tx.id, status="approved", request_reason="Correction",
                requested_by_id=1, approver_id=1, decided_at=datetime(2026, 11, 1, 3), money_treatment=treatment,
                original_amount=tx.total_bill, original_payment_method="cash", original_business_date=date(2026, 10, 15),
                refund_amount=100 if treatment == "refund" else 0))
        db.session.commit()
        october = AccountantReportService.build("2026-10", 1)["sales"]
        november = AccountantReportService.build("2026-11", 1)["sales"]
        assert (october["cowork_bill"], october["cafe_bill"], october["discounts"], october["checkout_sales"]) == (200, 200, 20, 380)
        assert october["refunds"] == november["checkout_sales"] == 0 and november["refunds"] == 100
        assert all(isinstance(value, Decimal) for value in october.values())


def test_legacy_classification_is_audited_and_does_not_move_cash(app, team):
    with app.app_context():
        row = Expense(category="PAYROLL", description="Older wages", amount=500, expense_date=date(2026, 11, 5),
                      created_at=datetime(2026, 11, 5, 3), funding_source="external", payment_method="gcash", logged_by=1)
        db.session.add(row)
        db.session.commit()
        expense_id = row.id
        before = SalesRepository().daily_ledger(date(2026, 11, 5), date(2026, 11, 5))
        report = AccountantReportService.build("2026-10", 1)
        assert report["issues"] and not report["can_export"]
    client = app.test_client()
    login(client)
    assert client.get("/admin/reports/api/monthly-accountant/pdf?month=2026-10").status_code == 409
    data = {"salary_employee_id": 2, "salary_month": "2026-10", "confirmed": True}
    endpoint = f"/admin/expenses/api/expenses/{expense_id}/salary-metadata"
    assert client.patch(endpoint, json=data, headers={"Idempotency-Key": "classify-once"}).status_code == 200
    assert client.patch(endpoint, json=data, headers={"Idempotency-Key": "classify-once"}).status_code == 409
    assert client.patch(endpoint, json={**data, "salary_month": "2026-09"}).status_code == 400
    with app.app_context():
        row = db.session.get(Expense, expense_id)
        assert (row.salary_original_category, row.salary_assigned_by, row.amount, row.expense_date) == ("PAYROLL", 1, 500, date(2026, 11, 5))
        assert SalesRepository().daily_ledger(date(2026, 11, 5), date(2026, 11, 5)) == before
        report = AccountantReportService.build("2026-10", 1)
        assert report["salary_total"] == 500 and report["can_export"]


def test_ordinary_expense_cannot_be_classified_as_salary(app, team):
    client = app.test_client()
    login(client)
    response = client.post("/admin/expenses/api/expenses", json={
        "category": "repairs_maintenance", "description": "Aircon maintenance", "amount": "600",
        "expense_date": "2026-10-29", "payment_method": "bdo"})
    assert response.status_code == 201
    before = client.get("/admin/expenses/api/expenses").json["data"]
    expense_id = response.json["data"]["id"]
    response = client.patch(f"/admin/expenses/api/expenses/{expense_id}/salary-metadata", json={
        "salary_employee_id": 2, "salary_month": "2026-10", "confirmed": True})
    assert response.status_code == 400
    assert response.json["error"] == "Only existing salary records can receive salary details."
    assert client.get("/admin/expenses/api/expenses").json["data"] == before
    with app.app_context():
        report = AccountantReportService.build("2026-10", 1)
        assert report["salary_total"] == 0 and report["total_expenses"] == 600


def test_salary_void_removes_current_cost_but_keeps_original_and_reversal_dates(app, team):
    client = app.test_client()
    login(client)
    result = salary(client, "500")
    expense_id = result.json["data"]["id"]
    team.current = datetime(2026, 11, 6, 3)
    assert client.delete(f"/admin/expenses/api/expenses/{expense_id}", json={"reason": "Wrong amount"}).status_code == 200
    with app.app_context():
        october = AccountantReportService.build("2026-10", 1)
        assert october["salary_total"] == october["total_expenses"] == 0
        assert october["expense_payment_history"][0]["void_reason"] == "Wrong amount"
        daily = SalesRepository().daily_ledger(date(2026, 11, 5), date(2026, 11, 6))
        assert daily[date(2026, 11, 5)]["total_expenses"] == 500
        assert daily[date(2026, 11, 6)]["total_expenses"] == -500


def test_report_auth_validation_and_empty_month(app, team):
    client = app.test_client()
    api = "/admin/reports/api/monthly-accountant"
    assert client.get(api).status_code == client.get(api + "/pdf").status_code == 401
    login(client, "staff")
    assert client.get(api).status_code == client.get(api + "/pdf").status_code == 403
    login(client)
    for month in ("2026-13", "2026-1", "bad", "", "0001-01", "9999-12"):
        assert client.get(api, query_string={"month": month}).status_code == 400
    assert client.get("/admin/reports?view=monthly&month=2026-10").status_code == 200
    empty = client.get(api + "?month=2025-12").json["data"]
    assert empty["total_expenses"] == "0.00" and not empty["salary_employees"]
    assert empty["attendance"]["employee_count"] == 0 and empty["can_export"]
    assert month_bounds("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))
    with client.session_transaction() as session:
        session["last_activity"] = 1
    assert client.get(api).status_code == 401


def test_migration_adds_salary_columns_to_old_schema_without_changing_money(app, team):
    with app.app_context():
        ddl = db.session.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='expenses'")).scalar()
        old = "\n".join(line for line in ddl.splitlines() if "salary_" not in line)
        old = re.sub(r",\s*\)", "\n)", old)
        db.session.execute(text("DROP TABLE expenses"))
        db.session.execute(text(old))
        db.session.execute(text("""INSERT INTO expenses (id, category, description, amount, expense_date, logged_by, repay_owner)
                                    VALUES (1, 'supplies', 'Old paper', 50, '2026-10-01', 1, 0)"""))
        db.session.commit()
        migrator = SchemaMigrator(db, app)
        migrator.run()
        migrator.run()
        columns = {c["name"] for c in inspect(db.engine).get_columns("expenses")}
        assert {"salary_employee_id", "salary_employee_name", "salary_month", "salary_assigned_at", "salary_assigned_by", "salary_original_category"} <= columns
        row = db.session.get(Expense, 1)
        assert row.amount == 50 and row.salary_month is None and row.salary_employee_id is None


def test_real_monthly_pdf_contains_all_four_sections_and_all_records(app, team):
    from pypdf import PdfReader
    client = app.test_client()
    login(client)
    assert salary(client, "20000").status_code == 201
    with app.app_context():
        for n in range(35):
            db.session.add(Expense(category="repairs_maintenance", description=f"Repair record {n+1}", amount=10,
                expense_date=date(2026, 10, 10), logged_by=1, created_at=datetime(2026, 10, 10, 1)))
            db.session.add(StaffShift(user_id=2, shift_role="cashier", time_in=datetime(2026, 10, 15, 1),
                                     time_out=datetime(2026, 10, 15, 9)))
        db.session.commit()
        count = Expense.query.count(), StaffShift.query.count(), Transaction.query.count()
    response = client.get("/admin/reports/api/monthly-accountant/pdf?month=2026-10")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "private, no-store"
    assert 'IdeaFlow-Accountant-Report-2026-10.pdf' in response.headers['Content-Disposition']
    pdf = PdfReader(BytesIO(response.data))
    content = "\n".join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) >= 4
    for phrase in ("Salaries for October 2026", "1. Sales", "3. Expenses", "4. Employee attendance", "Repair record 35", "S-35", "20000.00", "20350.00", "Payroll Employee"):
        assert phrase in content
    with app.app_context():
        assert count == (Expense.query.count(), StaffShift.query.count(), Transaction.query.count())
