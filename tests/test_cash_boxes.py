"""Physical cash custody must reconcile with the dated financial ledger."""

from csv import DictReader
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO, StringIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from app import create_app, db
from app.models import (CashBoxEvent, CheckoutVoidRequest, CustomerSession, Expense, Payable, Receivable,
                        ReceivablePayment, SpaceType, Transaction)
from app.repositories.sales_repository import SalesRepository
from app.services.cash_box_service import CashBoxService
from app.services.daily_balance_export_service import DailyBalanceExportService
from app.services.sales_service import SalesService
from app.utils.dates import manila_date, manila_day_bounds


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


@pytest.fixture
def staff(app):
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff",
                    last_activity=datetime.now(timezone.utc).timestamp())
    return client


def opening(client, day, *, petty="0", customer="0"):
    response = client.post("/api/cash-boxes/opening", json={
        "date": day.isoformat(), "petty": petty, "customer": customer,
    }, headers={"Idempotency-Key": f"open-boxes-{uuid4()}"})
    assert response.status_code == 201, response.get_json()


def action(client, key, kind, box, amount, day, **extra):
    if kind == "withdrawal":
        extra.setdefault("owner_debt_repayment", False)
    return client.post("/api/cash-boxes/entries", json={
        "kind": kind, "box": box, "amount": amount, "date": day.isoformat(), **extra,
    }, headers={"Idempotency-Key": key})


def expense(client, key, amount, day, box, repay=None):
    return client.post("/expenses-view/api/expenses", json={
        "category": "supplies", "description": key, "amount": amount,
        "expense_date": day.isoformat(), "payment_method": "cash", "cash_box": box,
        "repay_owner": repay,
    }, headers={"Idempotency-Key": key})


def test_first_petty_cash_entry_is_audited_in_daily_balance(app, staff):
    day = manila_date(datetime.utcnow())
    payload = {"date": day.isoformat(), "initial_topup": "300", "repay_owner": True,
               "note": "  Owner handed over petty cash  "}
    missing_choice = staff.post("/api/cash-boxes/opening",
                                json={"date": day.isoformat(), "initial_topup": "300"},
                                headers={"Idempotency-Key": "petty-missing-repayment-choice"})
    assert missing_choice.status_code == 400
    response = staff.post("/api/cash-boxes/opening", json=payload,
                          headers={"Idempotency-Key": "first-petty-cash"})
    assert response.status_code == 201, response.get_json()
    retry = staff.post("/api/cash-boxes/opening", json=payload,
                       headers={"Idempotency-Key": "first-petty-cash"})
    assert retry.status_code == 201 and retry.get_json()["replayed"]

    with app.app_context():
        entries = CashBoxEvent.query.order_by(CashBoxEvent.id).all()
        assert [(entry.kind, entry.box, entry.effect) for entry in entries] == [
            ("opening", "petty", Decimal("0.00")),
            ("opening", "customer", Decimal("0.00")),
            ("owner_topup", "petty", Decimal("300.00")),
        ]
        owner_debt = Payable.query.filter_by(owner_cash_event_id=entries[-1].id).one()
        assert owner_debt.amount_owed == Decimal("300.00")
        assert entries[-1].note == "Owner handed over petty cash"
        assert Payable.query.count() == 1

    boxes = staff.get("/api/cash-boxes").get_json()["balances"]
    assert boxes["closing"] == {"petty": 300.0, "customer": 0.0}
    report = staff.get(f"/staff/daily-balance/api/reports?start_date={day}&end_date={day}")
    assert report.status_code == 200
    live = report.get_json()["data"][0]
    assert live["total_owner_topups"] == 300.0
    assert live["cash_boxes"]["total_closing"] == 300.0
    assert live["cash_on_hand"] == 300.0
    assert live["total_revenue"] == 0.0


@pytest.mark.parametrize("note", [["invalid"], "x" * 256])
def test_first_petty_cash_note_is_validated_before_recording(app, staff, note):
    response = staff.post("/api/cash-boxes/opening", json={
        "date": manila_date(datetime.utcnow()).isoformat(), "initial_topup": "300",
        "repay_owner": True, "note": note,
    }, headers={"Idempotency-Key": "invalid-first-note"})
    assert response.status_code == 400
    with app.app_context():
        assert CashBoxEvent.query.count() == Payable.query.count() == 0


def test_cash_history_rejects_reversed_date_range(staff):
    response = staff.get("/api/cash-boxes/history?start_date=2026-10-02&end_date=2026-10-01")
    assert response.status_code == 400


@pytest.mark.parametrize("role", ["staff", "admin"])
def test_cash_retries_reuse_records_and_reject_changed_details(app, staff, role):
    with staff.session_transaction() as auth:
        auth["role"] = role
    day = manila_date(datetime.utcnow())
    opening_payload = {"date": day.isoformat(), "initial_topup": "300",
                       "repay_owner": False, "note": "Start of day"}
    headers = {"Idempotency-Key": f"first-cash-{role}"}
    assert staff.post("/api/cash-boxes/opening", json=opening_payload, headers=headers).status_code == 201
    retried = staff.post("/api/cash-boxes/opening", json=opening_payload, headers=headers)
    assert retried.status_code == 201 and retried.get_json()["replayed"]
    assert staff.post("/api/cash-boxes/opening", json={**opening_payload, "note": "Different"},
                      headers=headers).status_code == 409

    key = f"repayable-cash-{role}"
    added = action(staff, key, "owner_topup", "petty", "50", day, repay_owner=True, note="Float")
    entry_id = added.get_json()["data"]["id"]
    retried = action(staff, key, "owner_topup", "petty", "50", day, repay_owner=True, note="Float")
    assert retried.status_code == 201 and retried.get_json()["replayed"]
    assert retried.get_json()["data"]["id"] == entry_id
    assert action(staff, key, "owner_topup", "petty", "60", day,
                  repay_owner=True, note="Float").status_code == 409
    assert action(staff, f"withdraw-{role}", "withdrawal", "petty", "10", day,
                  recipient="Owner", note="Cash collected").status_code == 201
    retried = action(staff, f"withdraw-{role}", "withdrawal", "petty", "10", day,
                     recipient="Owner", note="Cash collected")
    assert retried.status_code == 201 and retried.get_json()["replayed"]
    correction = f"/api/cash-boxes/entries/{entry_id}/reverse"
    headers = {"Idempotency-Key": f"reverse-cash-{role}"}
    corrected = staff.post(correction, json={"reason": "Entered twice"}, headers=headers)
    assert corrected.status_code == 201
    retried = staff.post(correction, json={"reason": "Entered twice"}, headers=headers)
    assert retried.status_code == 201 and retried.get_json()["replayed"]
    assert retried.get_json()["data"]["id"] == corrected.get_json()["data"]["id"]
    assert staff.post(correction, json={"reason": "Different"}, headers=headers).status_code == 409
    history = staff.get("/api/cash-boxes/history").get_json()["data"]
    assert len(history) == 6  # Two baselines, two top-ups, one withdrawal, one reversal.
    assert next(row for row in history if row["id"] == entry_id)["repay_owner"] is True
    with app.app_context():
        assert Payable.query.count() == 1
        assert Payable.query.one().cancelled_at is not None
    report = staff.get(f"/{role}/daily-balance/api/reports?start_date={day}&end_date={day}").get_json()["data"][0]
    assert report["cash_boxes"]["closing"]["petty"] == 290
    assert report["total_owner_topups"] == 300
    assert report["total_cash_withdrawals"] == 10
    assert report["total_revenue"] == 0


def test_boxes_expenses_withdrawals_and_exports_reconcile(app, staff):
    day = manila_date(datetime.utcnow())
    opening(staff, day)
    for index in (1, 2):
        result = action(staff, f"topup-{index}", "owner_topup", "petty", "300", day,
                        repay_owner=False)
        assert result.status_code == 201, result.get_json()
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        session = CustomerSession(customer_name="Buyer", space_type_id=space.id,
                                  time_in=datetime.utcnow(), status="completed")
        db.session.add(session)
        db.session.flush()
        db.session.add(Transaction(session_id=session.id, time_bill=0, food_bill=Decimal("200"),
                                   total_bill=Decimal("200"), payment_method="cash",
                                   created_at=datetime.utcnow()))
        debt = Receivable(customer_name="Debtor", items_description="Debt", amount_owed=Decimal("50"),
                          partial_paid=Decimal("50"), due_date=day, created_by=1)
        db.session.add(debt)
        db.session.flush()
        db.session.add(ReceivablePayment(receivable_id=debt.id, amount=Decimal("50"),
                                         payment_method="cash", received_by=1,
                                         received_at=datetime.utcnow()))
        db.session.commit()
    for key, amount, box, repay in (("petty-expense", "80", "petty", None),
                                    ("customer-expense", "30", "customer", None),
                                    ("owner-expense", "90", "owner", False)):
        response = expense(staff, key, amount, day, box, repay)
        assert response.status_code == 201, response.get_json()
    assert action(staff, "petty-out", "withdrawal", "petty", "20", day,
                  recipient="Owner", note="Collected cash").status_code == 201
    assert action(staff, "customer-out", "withdrawal", "customer", "100", day,
                  recipient="Owner", note="Collected sales").status_code == 201
    today = staff.get("/staff/daily-balance/api/today-stats").get_json()["data"]
    parts = today["cash_flow_parts"]
    assert parts == {"received": 250.0, "owner_added": 600.0,
                     "spent_refunded": 110.0, "taken_out": 120.0}
    assert today["cash_on_hand"] == (parts["received"] + parts["owner_added"]
                                      - parts["spent_refunded"] - parts["taken_out"])
    with app.app_context():
        ledger = SalesRepository().daily_ledger(day, day)[day]
        boxes = CashBoxService.summaries(day)[day]
        assert boxes["closing"] == {"petty": 500.0, "customer": 120.0}
        assert boxes["total_closing"] == 620
        for box in ("petty", "customer"):
            assert (boxes["opening"][box] + boxes["receipts"][box] + boxes["topups"][box]
                    - boxes["spending"][box] - boxes["withdrawals"][box]) == boxes["closing"][box]
        assert (ledger["total_revenue"], ledger["total_expenses"], ledger["total_other_income"]) == (200, 200, 0)
        assert (ledger["total_owner_topups"], ledger["total_cash_withdrawals"]) == (600, 120)
        assert ledger["cash_on_hand"] == boxes["total_movement"] == 620
        assert SalesRepository.method_balance(ledger, "cash") == Decimal("620")
        assert Payable.query.count() == 0
        assert {entry.payment_method for entry in CashBoxEvent.query.all()} == {"cash"}
        report = SalesService(SalesRepository()).list_reports(day, day)[0]
        assert DailyBalanceExportService._method_rows([report])[0]["net"] == 620
    csv = staff.get(f"/staff/daily-balance/api/reports/export-csv?start_date={day}&end_date={day}").data.decode("utf-8")
    csv_rows = list(DictReader(StringIO(csv.lstrip('\ufeff'))))
    assert any(row["Item"] == "Petty Closing" and row["Amount"] == "500.00" for row in csv_rows)
    excel = staff.get(f"/staff/daily-balance/api/reports/export-excel?start_date={day}&end_date={day}")
    assert excel.status_code == 200
    details = load_workbook(BytesIO(excel.data), read_only=True)["Report Details"]
    assert any(row[2] == "Petty Closing" and row[3] == 500 for row in details.values)
    pdf = staff.get(f"/staff/daily-balance/api/reports/export-pdf?start_date={day}&end_date={day}")
    assert pdf.status_code == 200 and pdf.data.startswith(b"%PDF")


def test_owner_debt_payment_and_reversal_are_audited(app, staff):
    day = manila_date(datetime.utcnow())
    opening(staff, day)
    topup = action(staff, "repayable-topup", "owner_topup", "petty", "300", day,
                   repay_owner=True)
    assert topup.status_code == 201, topup.get_json()
    with app.app_context():
        payable = Payable.query.filter_by(owner_cash_event_id=topup.get_json()["data"]["id"]).one()
        payable_id = payable.id
        assert payable.amount_owed == 300
    paid = staff.patch(f"/staff/payables/api/payables/{payable_id}/mark-paid",
                       json={"payment_method": "cash", "cash_box": "petty", "amount": "100"},
                       headers={"Idempotency-Key": "owner-partial"})
    assert paid.status_code == 200, paid.get_json()
    retry = staff.patch(f"/staff/payables/api/payables/{payable_id}/mark-paid",
                        json={"payment_method": "cash", "cash_box": "petty", "amount": "100"},
                        headers={"Idempotency-Key": "owner-partial"})
    assert retry.status_code == 200 and retry.get_json()["replayed"]
    refused = staff.post(f"/api/cash-boxes/entries/{topup.get_json()['data']['id']}/reverse",
                         json={"reason": "Mistake"}, headers={"Idempotency-Key": "refused-reversal"})
    assert refused.status_code == 409
    with app.app_context():
        assert CashBoxService.summaries(day)[day]["closing"]["petty"] == 200
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["total_owner_reimbursements"] == 100
        assert ledger["total_supplier_payments"] == 0
        assert ledger["total_expenses"] == 0
        assert len(db.session.get(Payable, payable_id).payments) == 1
    other = action(staff, "reversible-topup", "owner_topup", "petty", "25", day,
                   repay_owner=True)
    entry_id = other.get_json()["data"]["id"]
    reverse = staff.post(f"/api/cash-boxes/entries/{entry_id}/reverse",
                         json={"reason": "Entered twice"}, headers={"Idempotency-Key": "reverse-25"})
    assert reverse.status_code == 201, reverse.get_json()
    with app.app_context():
        linked = Payable.query.filter_by(owner_cash_event_id=entry_id).one()
        assert linked.cancelled_at is not None and linked.cancel_reason == "Entered twice"
        assert CashBoxEvent.query.filter_by(reverses_id=entry_id).count() == 1
        assert CashBoxService.summaries(day)[day]["closing"]["petty"] == 200


def test_backdated_topup_changes_live_balance_but_not_snapshot(app, staff):
    today = manila_date(datetime.utcnow())
    yesterday = today - timedelta(days=1)
    opening(staff, yesterday, customer="100")
    with app.app_context():
        saved = SalesService(SalesRepository()).generate_report(yesterday, 1, "counted yesterday")
        assert saved["success"]
        soft = SalesService(SalesRepository()).create_soft_balance(yesterday, "PM", 1, "counted yesterday")
        assert soft["success"]
    result = action(staff, "late-topup", "owner_topup", "petty", "50", yesterday,
                    repay_owner=False)
    assert result.status_code == 201, result.get_json()
    with app.app_context():
        reports = SalesService(SalesRepository()).list_reports(yesterday, today)
        prior = next(r for r in reports if r["report_date"] == yesterday.isoformat())
        assert prior["cash_boxes"]["closing"]["petty"] == 50
        assert prior["snapshot_petty_cash_closing"] == 0
        assert prior["cash_snapshot_difference"] == 50
        assert prior["petty_cash_snapshot_difference"] == 50
        assert prior["customer_cash_snapshot_difference"] == 0
        prior_soft = next(row for row in SalesService(SalesRepository()).list_soft_balances()
                          if row["balance_date"] == yesterday.isoformat())
        assert prior_soft["petty_cash_closing"] == 0
        assert prior_soft["live_cash_difference"] == 50
        assert CashBoxService.summaries(today)[today]["opening"]["petty"] == 50
        assert CashBoxEvent.query.filter_by(kind="owner_topup").one().recorded_at.date() == datetime.utcnow().date()
    assert action(staff, "late-withdrawal", "withdrawal", "customer", "50", yesterday,
                  recipient="Owner", note="Collected sales").status_code == 201
    with app.app_context():
        prior = SalesService(SalesRepository()).list_reports(yesterday, yesterday)[0]
        assert prior["cash_snapshot_difference"] == 0
        assert prior["petty_cash_snapshot_difference"] == 50
        assert prior["customer_cash_snapshot_difference"] == -50
    csv = staff.get(f"/staff/daily-balance/api/reports/export-csv?start_date={yesterday}&end_date={yesterday}")
    differences = {row["Item"]: row["Amount"] for row in DictReader(StringIO(csv.data.decode("utf-8-sig")))
                   if row["Section"] == "Daily summary / Saved cash snapshot"}
    assert (differences["Petty Snapshot Difference"], differences["Customer Snapshot Difference"]) == ("50.00", "-50.00")


def test_cash_carries_through_days_with_no_transactions(app, staff):
    today = manila_date(datetime.utcnow())
    start = today - timedelta(days=2)
    opening(staff, start)
    assert action(staff, "topup-before-idle-day", "owner_topup", "petty", "75", start,
                  repay_owner=False).status_code == 201
    with app.app_context():
        daily = CashBoxService.summaries(today)
        idle = daily[start + timedelta(days=1)]
        assert idle["opening"]["petty"] == 75
        assert idle["movement"]["petty"] == 0
        assert idle["closing"]["petty"] == daily[today]["opening"]["petty"] == 75
        reports = SalesService(SalesRepository()).list_reports(start, today)
        idle_report = next(row for row in reports if row["report_date"] == (start + timedelta(days=1)).isoformat())
        assert idle_report["cash_boxes"]["closing"]["petty"] == 75


def test_customer_cash_carries_across_manila_midnight(app, staff):
    next_day = manila_date(datetime.utcnow())
    day = next_day - timedelta(days=1)
    opening(staff, day)
    midnight_utc = manila_day_bounds(day)[1]
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        for amount, paid_at in (("100", midnight_utc - timedelta(microseconds=1)),
                                ("20", midnight_utc)):
            session = CustomerSession(customer_name="Cash buyer", space_type_id=space.id,
                                      time_in=paid_at, status="completed")
            db.session.add(session)
            db.session.flush()
            db.session.add(Transaction(session_id=session.id, time_bill=0,
                                       food_bill=Decimal(amount), total_bill=Decimal(amount),
                                       payment_method="cash", created_at=paid_at))
        db.session.commit()

        summaries = CashBoxService.summaries(next_day)
        assert summaries[day]["closing"]["customer"] == 100
        assert summaries[next_day]["opening"]["customer"] == 100
        assert summaries[next_day]["movement"]["customer"] == 20
        assert summaries[next_day]["closing"]["customer"] == 120

    reports = staff.get(f"/staff/daily-balance/api/reports?start_date={day}&end_date={next_day}")
    assert reports.status_code == 200
    today = next(row for row in reports.get_json()["data"] if row["report_date"] == next_day.isoformat())
    assert today["cash_on_hand"] == 20
    assert today["cash_boxes"]["opening"]["customer"] == 100
    assert today["cash_boxes"]["closing"]["customer"] == 120


def test_opening_correction_keeps_both_original_and_replacement(app, staff):
    day = manila_date(datetime.utcnow())
    opening(staff, day)
    with app.app_context():
        original = CashBoxEvent.query.filter_by(kind="opening", box="petty").one().id
    corrected = staff.post(f"/api/cash-boxes/entries/{original}/reverse",
                           json={"reason": "Physical recount", "replacement_amount": "40"},
                           headers={"Idempotency-Key": "opening-correction"})
    assert corrected.status_code == 201, corrected.get_json()
    retried = staff.post(f"/api/cash-boxes/entries/{original}/reverse",
                         json={"reason": "Physical recount", "replacement_amount": "40"},
                         headers={"Idempotency-Key": "opening-correction"})
    assert retried.status_code == 201 and retried.get_json()["replayed"]
    changed = staff.post(f"/api/cash-boxes/entries/{original}/reverse",
                         json={"reason": "Physical recount", "replacement_amount": "50"},
                         headers={"Idempotency-Key": "opening-correction"})
    assert changed.status_code == 409
    with app.app_context():
        assert CashBoxService.summaries(day)[day]["closing"]["petty"] == 40
        assert CashBoxEvent.query.filter_by(reverses_id=original).count() == 1
        assert CashBoxEvent.query.filter_by(replaces_id=original).count() == 1
        assert all(event.request_key for event in CashBoxEvent.query.all())


def test_owner_paid_expense_reimbursement_is_not_second_expense(app, staff):
    day = manila_date(datetime.utcnow())
    opening(staff, day)
    created = expense(staff, "owner-paid-direct", "90", day, "owner", True)
    assert created.status_code == 201, created.get_json()
    expense_id = created.get_json()["data"]["id"]
    with app.app_context():
        payable = Payable.query.filter_by(owner_expense_id=expense_id).one()
        payable_id = payable.id
        assert payable.amount_owed == 90
        assert db.session.get(Expense, expense_id).cash_box is None
        assert CashBoxService.summaries(day)[day]["total_closing"] == 0
    payment = staff.patch(f"/staff/payables/api/payables/{payable_id}/mark-paid",
                          json={"payment_method": "gcash", "amount": "40"},
                          headers={"Idempotency-Key": "owner-direct-repay"})
    assert payment.status_code == 200, payment.get_json()
    with app.app_context():
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["total_expenses"] == ledger["total_external_expenses"] == 90
        assert ledger["total_owner_reimbursements"] == 40
        assert ledger["total_supplier_payments"] == 0
        assert ledger["net_balance"] == -40
        assert CashBoxService.summaries(day)[day]["total_closing"] == 0
    with staff.session_transaction() as auth:
        auth["role"] = "admin"
    cannot_void = staff.delete(f"/admin/expenses/api/expenses/{expense_id}", json={"reason": "Mistaken"})
    assert cannot_void.status_code == 409


def test_owner_paid_expense_void_cancels_unpaid_debt_without_moving_cash(app, staff):
    day = manila_date(datetime.utcnow())
    opening(staff, day)
    created = expense(staff, "owner-expense-to-void", "45", day, "owner", True)
    assert created.status_code == 201, created.get_json()
    expense_id = created.get_json()["data"]["id"]
    with staff.session_transaction() as auth:
        auth["role"] = "admin"
    voided = staff.delete(f"/admin/expenses/api/expenses/{expense_id}",
                          json={"reason": "Duplicate receipt"},
                          headers={"Idempotency-Key": "void-owner-expense"})
    assert voided.status_code == 200, voided.get_json()
    with app.app_context():
        debt = Payable.query.filter_by(owner_expense_id=expense_id).one()
        assert debt.cancelled_at is not None and debt.cancel_reason == "Duplicate receipt"
        assert CashBoxService.summaries(day)[day]["total_closing"] == 0
        assert SalesRepository().daily_ledger(day, day)[day]["total_expenses"] == 0


def test_cash_refund_and_manila_midnight_use_customer_box(app, staff):
    day = date(2026, 10, 2)
    opening(staff, day)
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        session = CustomerSession(customer_name="Refund buyer", space_type_id=space.id,
                                  time_in=datetime(2026, 10, 1, 16, 20), status="completed")
        db.session.add(session)
        db.session.flush()
        tx = Transaction(session_id=session.id, time_bill=0, food_bill=Decimal("100"),
                         total_bill=Decimal("100"), payment_method="cash",
                         created_at=datetime(2026, 10, 1, 16, 30))
        db.session.add(tx)
        db.session.flush()
        db.session.add(CheckoutVoidRequest(
            transaction_id=tx.id, status="approved", request_reason="Returned",
            requested_by_id=1, approver_id=1, money_treatment="refund",
            requested_at=datetime(2026, 10, 1, 17), decided_at=datetime(2026, 10, 1, 17),
            original_amount=Decimal("100"), original_payment_method="cash",
            original_business_date=day, decision_business_date=day,
            refund_amount=Decimal("100"),
        ))
        db.session.commit()
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["total_revenue"] == ledger["total_refunds"] == 100
        assert ledger["cash_box_receipts"]["customer"] == 100
        assert ledger["cash_box_spending"]["customer"] == 100
        assert CashBoxService.summaries(day)[day]["closing"]["customer"] == 0


def test_older_cash_expense_without_box_stays_unassigned(app, staff):
    day = manila_date(datetime.utcnow())
    opening(staff, day)
    with app.app_context():
        db.session.add(Expense(category="supplies", description="Older cash record",
                               amount=Decimal("15"), expense_date=day, payment_method="cash",
                               funding_source="business", logged_by=1,
                               created_at=datetime.utcnow()))
        db.session.commit()
        ledger = SalesRepository().daily_ledger(day, day)[day]
        summary = CashBoxService.summaries(day)[day]
        assert ledger["cash_on_hand"] == -15
        assert summary["total_movement"] == 0
        assert summary["unassigned_cash_movement"] == -15
        assert summary["unassigned_cash_entries"] == 1


def test_cash_box_api_requires_login(app):
    response = app.test_client().get("/api/cash-boxes")
    assert response.status_code == 401
    assert response.get_json()["error"]


def test_cash_box_writes_require_request_key(staff):
    response = staff.post("/api/cash-boxes/opening", json={"date": "2026-10-01", "petty": "0", "customer": "0"})
    assert response.status_code == 400
    malformed = staff.post("/api/cash-boxes/opening", json=[], headers={"Idempotency-Key": "bad-shape"})
    assert malformed.status_code == 400


def test_owner_repayment_cannot_be_logged_as_ordinary_withdrawal(staff):
    day = manila_date(datetime.utcnow())
    opening(staff, day)
    blocked = action(staff, "misfiled-repayment", "withdrawal", "petty", "20", day,
                     recipient="Owner", note="Repay loan", owner_debt_repayment=True)
    assert blocked.status_code == 400
    with staff.application.app_context():
        assert CashBoxEvent.query.filter_by(kind="withdrawal").count() == 0


def test_both_roles_are_asked_about_owner_repayment(staff):
    staff_page = staff.get("/expenses-view")
    assert staff_page.status_code == 200
    assert b"Must the business repay the owner?" in staff_page.data
    assert b"Cash Boxes" in staff_page.data
    with staff.session_transaction() as auth:
        auth["role"] = "admin"
    admin_page = staff.get("/admin/expenses")
    assert admin_page.status_code == 200
    assert b"Must the business repay the owner?" in admin_page.data
