from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app import create_app, db
from app.models import CustomerSession, Expense, Receivable, ReceivablePayment, SpaceType, Transaction
from app.repositories.receivable_repository import ReceivableRepository
from app.services.receivable_service import ReceivableService


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _auth(client, role="admin"):
    with client.session_transaction() as session:
        session.update(user_id=1, role=role, username="test_user", last_activity=datetime.now(timezone.utc).timestamp())


def test_customer_can_pay_part_of_debt_and_notes_are_editable(app):
    with app.app_context():
        service = ReceivableService(ReceivableRepository())
        today = (datetime.utcnow() + timedelta(hours=8)).date().isoformat()
        with pytest.raises(ValueError, match="Notes must be text"):
            service.create("Customer", "", "Lunch", 200, today, 1, None, notes="x" * 2001)
        rec_id = service.create("Customer", "", "Lunch", 200, today, 1, None, notes="2 spoons borrowed")["data"]["id"]
        assert service.mark_paid(rec_id, "100", 1, "cash") == {"success": True}
        rec = db.session.get(Receivable, rec_id)
        assert rec.partial_paid == Decimal("100.00")
        assert rec.paid is False
        assert service.mark_paid(rec_id, "101", 1, "cash")[1] == 400
        assert service.update_notes(rec_id, "Spoons returned") == {"success": True}
        assert service.mark_paid(rec_id, "100", 1, "gcash") == {"success": True}
        db.session.refresh(rec)
        assert rec.paid is True
        assert rec.notes == "Spoons returned"
        assert [(p.amount, p.payment_method) for p in rec.payments] == [
            (Decimal("100.00"), "cash"), (Decimal("100.00"), "gcash")
        ]


def test_customer_tab_payment_covers_all_orders_and_logs_one_payment(app):
    with app.app_context():
        service = ReceivableService(ReceivableRepository())
        due = (datetime.utcnow() + timedelta(days=1)).date().isoformat()
        first_id = service.create("Carl", "", "Snack", 30, due, 1, None)["data"]["id"]
        second_id = service.create("carl", "", "Lunch", 100, due, 1, None)["data"]["id"]

    client = app.test_client()
    _auth(client, "staff")
    payment = client.post("/receivables-view/api/receivables/customer-payment", json={
        "customer_name": "Carl", "amount": "50", "payment_method": "cash",
    }, headers={"Idempotency-Key": "carl-50"})
    assert payment.status_code == 200
    assert payment.get_json()["remaining"] == 80
    denied = client.post("/admin/receivables/api/receivables/customer-payment", json={
        "customer_name": "Carl", "amount": "1", "payment_method": "cash",
    })
    assert denied.status_code == 403
    duplicate = client.post("/receivables-view/api/receivables/customer-payment", json={
        "customer_name": "Carl", "amount": "50", "payment_method": "cash",
    }, headers={"Idempotency-Key": "carl-50"})
    assert duplicate.status_code == 409

    with app.app_context():
        first = db.session.get(Receivable, first_id)
        second = db.session.get(Receivable, second_id)
        assert first.partial_paid == Decimal("30.00")
        assert second.partial_paid == Decimal("20.00")
        assert first.paid is True and second.paid is False
        assert sum((p.amount for p in ReceivablePayment.query.all()), Decimal("0")) == Decimal("50.00")
        assert len({p.payment_group_id for p in ReceivablePayment.query.all()}) == 1

    history = client.get("/receivables-view/api/receivables/customer-payments?customer_name=carl")
    assert history.status_code == 200
    assert len(history.get_json()["data"]) == 1
    assert history.get_json()["data"][0]["amount"] == 50
    assert history.get_json()["data"][0]["received_by"] == "Test User"

    stats = client.get("/admin/daily-balance/api/today-stats").get_json()["data"]
    assert stats["cash_on_hand"] == 50
    assert stats["expected_to_collect"] == 80
    assert stats["receivables_paid_today"] == 1

    _auth(client, "admin")
    full = client.post("/admin/receivables/api/receivables/customer-payment", json={
        "customer_name": "Carl", "amount": "80", "payment_method": "gcash",
    })
    assert full.status_code == 200
    assert full.get_json()["remaining"] == 0
    with app.app_context():
        assert db.session.get(Receivable, second_id).paid is True
        assert len(ReceivableService(ReceivableRepository()).list_customer_payments("Carl")) == 2


def test_customer_tab_rejects_overpayment_without_changing_orders(app):
    with app.app_context():
        service = ReceivableService(ReceivableRepository())
        due = (datetime.utcnow() + timedelta(days=1)).date().isoformat()
        rec_id = service.create("Carl", "", "Snack", 30, due, 1, None)["data"]["id"]
        for amount in ("30.001", "31", "nan", "0", None):
            assert service.record_customer_payment("Carl", amount, 1, "cash")[1] == 400
        db.session.refresh(db.session.get(Receivable, rec_id))
        assert db.session.get(Receivable, rec_id).partial_paid == Decimal("0.00")
        assert ReceivablePayment.query.count() == 0


def test_customer_tabs_with_same_name_and_different_contacts_stay_separate(app):
    with app.app_context():
        service = ReceivableService(ReceivableRepository())
        due = (datetime.utcnow() + timedelta(days=1)).date().isoformat()
        first_id = service.create("Carl", "09111111111", "Lunch", 100, due, 1, None)["data"]["id"]
        second_id = service.create("carl", "09222222222", "Dinner", 100, due, 1, None)["data"]["id"]
        assert service.record_customer_payment("Carl", "50", 1, "cash", "09111111111") == {
            "success": True, "remaining": 50.0,
        }
        assert db.session.get(Receivable, first_id).partial_paid == Decimal("50.00")
        assert db.session.get(Receivable, second_id).partial_paid == Decimal("0.00")
        assert len(service.list_customer_payments("Carl", "09111111111")) == 1
        assert service.list_customer_payments("Carl", "09222222222") == []


def test_owner_and_staff_receivables_pages_show_open_tab_controls(app):
    client = app.test_client()
    _auth(client, "admin")
    owner_page = client.get("/admin/receivables")
    assert owner_page.status_code == 200
    assert b"Orders total" in owner_page.data
    assert b"Payment history" in owner_page.data
    assert b"Use full balance" in owner_page.data

    _auth(client, "staff")
    staff_page = client.get("/receivables-view")
    assert staff_page.status_code == 200
    assert b"Customer tabs" in staff_page.data
    assert b"Payment history" in staff_page.data


def test_staff_daily_balance_separates_cash_expenses_and_expected_collections(app):
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        today = (datetime.utcnow() + timedelta(hours=8)).date()
        session_cash = CustomerSession(customer_name="Cash", space_type_id=space.id, number_of_people=1,
                                       time_in=datetime.utcnow(), status="completed")
        session_gcash = CustomerSession(customer_name="GCash", space_type_id=space.id, number_of_people=1,
                                        time_in=datetime.utcnow(), status="completed")
        db.session.add_all([session_cash, session_gcash])
        db.session.flush()
        db.session.add_all([
            Transaction(session_id=session_cash.id, time_bill=Decimal("250"), food_bill=Decimal("0"),
                        total_bill=Decimal("250"), payment_method="cash"),
            Transaction(session_id=session_gcash.id, time_bill=Decimal("90"), food_bill=Decimal("0"),
                        total_bill=Decimal("90"), payment_method="gcash"),
            Expense(category="supplies", description="Paper", amount=Decimal("40"), expense_date=today, logged_by=1),
        ])
        rec = Receivable(customer_name="Owing customer", items_description="Meal", amount_owed=Decimal("200"),
                         partial_paid=Decimal("100"), due_date=today, created_by=1)
        db.session.add(rec)
        db.session.flush()
        db.session.add(ReceivablePayment(receivable_id=rec.id, amount=Decimal("100"),
                                         payment_method="cash", received_by=1))
        db.session.commit()

    client = app.test_client()
    _auth(client, "staff")
    page = client.get("/admin/daily-balance")
    assert page.status_code == 200
    assert b"Still to Collect" in page.data
    assert b'data-href="/admin/daily-balance"' in page.data
    assert b"Generate Report" not in page.data
    response = client.get("/admin/daily-balance/api/today-stats")
    assert response.status_code == 200
    stats = response.get_json()["data"]
    assert stats["cash_on_hand"] == 310
    assert stats["expected_to_collect"] == 100
    assert stats["expected_cash_on_hand"] == 410
    assert stats["receivables_collected_today"] == 100
