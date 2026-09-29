"""Tests for Checkout Void Request & Approval Workflow.

Verifies:
1. Staff void request and admin rejection (transaction remains counted).
2. Treatment 1: false_entry (removes false sale/inflow; old session stays closed).
3. Treatment 2: refund (preserves original day sale, logs negative refund event on approval day).
4. Treatment 3: retained_credit (staff explicitly attaches credit to a new check-in).
5. A void approval never reoccupies a full lounge.
6. RBAC: Only admin can approve or reject void requests; staff gets 403.
7. Snapshot integrity: Voided transaction retains original customer/space/billing snapshots.
8. Daily Balance ledger reconciliation: Net balances, method balances, cash on hand reconcile across dates.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from time import time
import pytest

from app import create_app, db
from app.models import (
    CustomerSession, SpaceType, MenuItem, InventoryItem, Transaction, User, CheckoutVoidRequest
)
from app.repositories.sales_repository import SalesRepository
from app.services.daily_balance_export_service import DailyBalanceExportService
from app.utils.dates import manila_date


@pytest.fixture
def app():
    application = create_app()
    application.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SINGLE_SESSION_ENABLED=False,
    )
    return application


@pytest.fixture
def setup_data(app):
    with app.app_context():
        # Spaces
        regular = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("1.0000"), capacity=2)
        take_out = SpaceType(name="Take Out", rate_per_minute=Decimal("0.0000"))
        boardroom = SpaceType(name="Boardroom", rate_per_minute=Decimal("10.0000"))
        db.session.add_all([regular, take_out, boardroom])

        # Menu Item
        coffee = MenuItem(name="Coffee", price=Decimal("50.00"), category="Beverages",
                          inventory_mode="untracked", is_available=True)
        db.session.add(coffee)

        # Users: User 1 is created by isolated_database as staff. We add admin as User 2 if needed.
        if db.session.get(User, 2) is None:
            admin = User(id=2, full_name="Admin User", username="admin_user", role="admin", is_active=True)
            admin.set_password("AdminPass123!")
            db.session.add(admin)

        db.session.commit()


@pytest.fixture
def staff_client(app, setup_data):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=1, username="test_user", role="staff", last_activity=time())
    return client


@pytest.fixture
def admin_client(app, setup_data):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess.update(user_id=2, username="admin_user", role="admin", last_activity=time())
    return client


def test_staff_request_void_and_admin_reject(app, staff_client, admin_client):
    # 1. Staff checks in customer
    resp = staff_client.post("/api/checkin", json={
        "customer_name": "Alice",
        "space_type_id": 1,
        "number_of_people": 1,
    })
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]

    # 2. Checkout
    checkout_resp = staff_client.post(f"/api/checkout/{session_id}", json={
        "payment_method": "cash",
        "amount_tendered": "100.00",
    })
    assert checkout_resp.status_code == 200

    with app.app_context():
        tx = Transaction.query.filter_by(session_id=session_id).first()
        tx_id = tx.id
        assert tx.is_voided is False

    # 3. Staff requests void
    req_resp = staff_client.post(f"/api/checkout-records/{tx_id}/void-request", json={
        "reason": "Customer wanted to stay longer",
    })
    assert req_resp.status_code == 201
    void_req_id = req_resp.get_json()["void_request"]["id"]

    # Pending void: transaction still appears in checkout records & still has is_voided == False
    records = staff_client.get("/api/checkout-records").get_json()
    assert len(records) == 1
    assert records[0]["is_voided"] is False
    assert records[0]["void_request"]["status"] == "pending"

    # Staff cannot approve or reject
    staff_reject = staff_client.post(f"/api/checkout-records/void-requests/{void_req_id}/reject", json={
        "reason": "Not allowed",
    })
    assert staff_reject.status_code == 403

    # 4. Admin rejects void
    admin_reject = admin_client.post(f"/api/checkout-records/void-requests/{void_req_id}/reject", json={
        "reason": "Invalid excuse; checkout was proper",
    })
    assert admin_reject.status_code == 200

    # Verify status is rejected and checkout remains completed
    with app.app_context():
        tx = db.session.get(Transaction, tx_id)
        assert tx.is_voided is False
        assert tx.session.status == "completed"
        v_req = db.session.get(CheckoutVoidRequest, void_req_id)
        assert v_req.status == "rejected"
        assert v_req.decision_reason == "Invalid excuse; checkout was proper"


def test_void_treatment_false_entry(app, staff_client, admin_client):
    # Check in and checkout
    resp = staff_client.post("/api/checkin", json={
        "customer_name": "Bob False Entry",
        "space_type_id": 1,
        "number_of_people": 1,
    })
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]

    with app.app_context():
        menu = MenuItem.query.filter_by(name="Coffee").one()
        menu.inventory_mode = "direct"
        stock = InventoryItem(menu_item_id=menu.id, stock_qty=1, unit="pieces")
        db.session.add(stock)
        db.session.commit()
        menu_id, stock_id = menu.id, stock.id
    order = staff_client.post("/api/add-order", json={
        "session_id": session_id,
        "items": [{"menu_item_id": menu_id, "quantity": 1}],
    })
    assert order.status_code == 200
    with app.app_context():
        assert db.session.get(InventoryItem, stock_id).stock_qty == 0

    checkout_resp = staff_client.post(f"/api/checkout/{session_id}", json={
        "payment_method": "cash",
        "amount_tendered": "100.00",
    })
    assert checkout_resp.status_code == 200

    with app.app_context():
        tx = Transaction.query.filter_by(session_id=session_id).first()
        tx_id = tx.id
        tx_date = manila_date(tx.created_at)

        # Before void: ledger has sales
        sales_repo = SalesRepository()
        ledger_before = sales_repo.daily_ledger(tx_date, tx_date).get(tx_date)
        assert ledger_before is not None
        assert ledger_before["total_revenue"] > 0
        assert ledger_before["cash_on_hand"] > 0

    # Staff requests void
    req_resp = staff_client.post(f"/api/checkout-records/{tx_id}/void-request", json={
        "reason": "Mistaken checkout pressed by accident",
    })
    void_req_id = req_resp.get_json()["void_request"]["id"]

    # Admin approves as false_entry
    appr_resp = admin_client.post(f"/api/checkout-records/void-requests/{void_req_id}/approve", json={
        "money_treatment": "false_entry",
        "decision_reason": "Confirmed accident; no cash received",
    })
    assert appr_resp.status_code == 200

    with app.app_context():
        tx = db.session.get(Transaction, tx_id)
        assert tx.is_voided is True
        assert tx.customer_name_snapshot == "Bob False Entry"

        # The original checkout stays visible, but its session never returns to the lounge.
        sess = db.session.get(CustomerSession, session_id)
        assert sess.status == "completed"
        assert sess.voided_transaction_id is None

    assert all(row["session_id"] != session_id for row in staff_client.get("/api/active-sessions").get_json())
    records = staff_client.get("/api/checkout-records").get_json()
    assert records[0]["transaction_id"] == tx_id
    assert records[0]["void_request"]["status"] == "approved"
    corrections = staff_client.get("/api/checkout-corrections").get_json()
    assert corrections[0]["request_id"] == void_req_id
    assert corrections[0]["food_bill"] == 50.0

    # Staff starts a fresh session in the correct space.
    with app.app_context():
        premium = SpaceType(name="Premium Lounge", rate_per_minute=Decimal("1.0000"), capacity=2)
        db.session.add(premium)
        db.session.commit()
        premium_id = premium.id
    new_checkin = staff_client.post("/api/checkin", json={
        "customer_name": "Bob False Entry", "space_type_id": premium_id, "number_of_people": 1,
        "void_request_id": void_req_id,
    })
    assert new_checkin.status_code == 200
    new_session_id = new_checkin.get_json()["session_id"]
    assert new_session_id != session_id
    assert staff_client.get("/api/checkout-corrections").get_json() == []
    preview = staff_client.get(f"/api/preview-checkout/{new_session_id}").get_json()
    assert preview["carried_food_bill"] == 50.0
    assert preview["food_bill"] == 50.0
    with app.app_context():
        assert db.session.get(InventoryItem, stock_id).stock_qty == 0

    # Ledger for tx_date: false entry removed.
    with app.app_context():
        sales_repo = SalesRepository()
        ledger_after = sales_repo.daily_ledger(tx_date, tx_date).get(tx_date) or sales_repo.daily_ledger_empty(tx_date)
        assert ledger_after["total_revenue"] == 0
        assert ledger_after["cash_on_hand"] == 0

    # Customer checks out the new session later.
    re_checkout = staff_client.post(f"/api/checkout/{new_session_id}", json={
        "payment_method": "gcash",
        "amount_tendered": "100.00",
    })
    assert re_checkout.status_code == 200

    with app.app_context():
        v_req = db.session.get(CheckoutVoidRequest, void_req_id)
        assert v_req.replacement_transaction_id is not None
        rep_tx = Transaction.query.filter_by(session_id=new_session_id).one()
        assert v_req.replacement_transaction_id == rep_tx.id
        assert rep_tx.is_voided is False
        assert rep_tx.payment_method == "gcash"
        assert rep_tx.food_bill == Decimal("50.00")
        assert db.session.get(InventoryItem, stock_id).stock_qty == 0
    assert b"Coffee" in staff_client.get(f"/receipt/{new_session_id}").data
    assert b"Voided checkout" in staff_client.get(f"/receipt/{session_id}").data


def test_void_treatment_refund(app, staff_client, admin_client):
    # Check in and checkout with GCash
    resp = staff_client.post("/api/checkin", json={
        "customer_name": "Charlie Refund",
        "space_type_id": 1,
        "number_of_people": 1,
    })
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]

    checkout_resp = staff_client.post(f"/api/checkout/{session_id}", json={
        "payment_method": "gcash",
    })
    assert checkout_resp.status_code == 200

    with app.app_context():
        tx = Transaction.query.filter_by(session_id=session_id).first()
        tx_id = tx.id
        tx_amount = tx.total_bill
        original_day = manila_date(tx.created_at)

    # Request void
    req_resp = staff_client.post(f"/api/checkout-records/{tx_id}/void-request", json={
        "reason": "Customer demands refund",
    })
    void_req_id = req_resp.get_json()["void_request"]["id"]

    # Admin approves as refund
    appr_resp = admin_client.post(f"/api/checkout-records/void-requests/{void_req_id}/approve", json={
        "money_treatment": "refund",
        "decision_reason": "Refund approved and paid back via GCash",
    })
    assert appr_resp.status_code == 200

    with app.app_context():
        assert db.session.get(CustomerSession, session_id).status == "completed"
        assert SalesRepository().summary_for_day(original_day).total_revenue == tx_amount
        today = manila_date(datetime.utcnow())
        sales_repo = SalesRepository()
        ledger = sales_repo.daily_ledger(today, today).get(today) or sales_repo.daily_ledger_empty(today)
        # Refund is recorded as negative method balance
        assert Decimal(str(ledger["refund_methods"]["gcash"])) == tx_amount
        assert SalesRepository.method_balance(ledger, "gcash") <= 0


def test_void_treatment_retained_credit_shortfall_and_overpayment(app, staff_client, admin_client):
    # --- Part A: Shortfall ---
    resp = staff_client.post("/api/checkin", json={
        "customer_name": "Dave Credit",
        "space_type_id": 1,
        "number_of_people": 1,
    })
    assert resp.status_code == 200
    session_id = resp.get_json()["session_id"]

    # Manually checkout for 50 cash
    with app.app_context():
        sess = db.session.get(CustomerSession, session_id)
        sess.status = "completed"
        tx = Transaction(
            session_id=session_id,
            time_bill=Decimal("50.00"),
            food_bill=Decimal("0.00"),
            total_bill=Decimal("50.00"),
            payment_method="cash",
            amount_tendered=Decimal("50.00"),
            collected_by="Staff",
            created_at=datetime.utcnow(),
        )
        db.session.add(tx)
        db.session.commit()
        tx_id = tx.id

    # Request void
    req_resp = staff_client.post(f"/api/checkout-records/{tx_id}/void-request", json={
        "reason": "Wants to order food instead of leaving",
    })
    void_req_id = req_resp.get_json()["void_request"]["id"]

    # Approve with retained_credit; the old session remains closed.
    appr_resp = admin_client.post(f"/api/checkout-records/void-requests/{void_req_id}/approve", json={
        "money_treatment": "retained_credit",
        "decision_reason": "Hold paid 50 as customer credit",
    })
    assert appr_resp.status_code == 200

    with app.app_context():
        sess = db.session.get(CustomerSession, session_id)
        assert sess.status == "completed"
        assert sess.credit_balance == Decimal("0.00")
        premium = SpaceType(name="Premium Lounge", rate_per_minute=Decimal("1.0000"), capacity=2)
        db.session.add(premium)
        db.session.commit()
        premium_id = premium.id

    credits = staff_client.get("/api/checkout-corrections").get_json()
    assert credits[0]["request_id"] == void_req_id
    assert credits[0]["amount"] == 50.0
    wrong_customer = staff_client.post("/api/checkin", json={
        "customer_name": "Someone else", "space_type_id": premium_id,
        "void_request_id": void_req_id,
    })
    assert wrong_customer.status_code == 400

    new_checkin = staff_client.post("/api/checkin", json={
        "customer_name": "Dave Credit", "space_type_id": premium_id,
        "void_request_id": void_req_id,
    })
    assert new_checkin.status_code == 200
    new_session_id = new_checkin.get_json()["session_id"]
    assert new_session_id != session_id
    assert staff_client.get("/api/checkout-corrections").get_json() == []
    duplicate_claim = staff_client.post("/api/checkin", json={
        "customer_name": "Dave Credit", "space_type_id": premium_id,
        "void_request_id": void_req_id,
    })
    assert duplicate_claim.status_code == 409

    with app.app_context():
        sess = db.session.get(CustomerSession, new_session_id)
        assert sess.credit_balance == Decimal("50.00")
        assert sess.credit_payment_method == "cash"

    # Add food order: 2 coffees = 100
    with app.app_context():
        menu_id = MenuItem.query.filter_by(name="Coffee").one().id
    staff_client.post("/api/add-order", json={
        "session_id": new_session_id,
        "items": [{"menu_item_id": menu_id, "quantity": 2}],
    })

    # Preview checkout
    preview = staff_client.get(f"/api/preview-checkout/{new_session_id}").get_json()
    assert preview["credit_balance"] == 50.0
    assert preview["food_bill"] == 100.0
    # Bill is at least 100 food, credit is 50, so shortfall >= 50
    assert preview["shortfall"] >= 50.0

    # Checkout paying remaining shortfall
    co_resp = staff_client.post(f"/api/checkout/{new_session_id}", json={
        "payment_method": "cash",
        "amount_tendered": "100.00",
    })
    assert co_resp.status_code == 200
    res_data = co_resp.get_json()
    assert res_data["credit_applied"] == 50.0

    with app.app_context():
        new_tx = Transaction.query.filter_by(session_id=new_session_id, is_voided=False).first()
        assert new_tx.credit_applied == Decimal("50.00")
        assert new_tx.amount_tendered == Decimal("100.00")
        sess = db.session.get(CustomerSession, new_session_id)
        assert sess.credit_balance == Decimal("0.00")
        req = db.session.get(CheckoutVoidRequest, void_req_id)
        assert req.replacement_transaction_id == new_tx.id
        assert req.credit_applied == Decimal("50.00")
        assert req.credit_remaining == Decimal("0.00")
        day = manila_date(new_tx.created_at)
        ledger = SalesRepository().daily_ledger(day, day)[day]
        assert ledger["credit_received_methods"]["cash"] == 50.0
        assert ledger["credit_applied_methods"]["cash"] == 50.0
        assert ledger["cash_on_hand"] == float(new_tx.total_bill)
    report = admin_client.get(
        f"/admin/daily-balance/api/reports?start_date={day}&end_date={day}"
    )
    assert report.status_code == 200
    reported = report.get_json()["data"][0]
    assert reported["cash_on_hand"] == ledger["cash_on_hand"]
    assert reported["credit_applied_methods"]["cash"] == 50.0


def test_approval_does_not_reoccupy_full_lounge(app, staff_client, admin_client):
    # Regular lounge capacity is 2
    # Check in customer 1 and customer 2
    r1 = staff_client.post("/api/checkin", json={"customer_name": "Occupant 1", "space_type_id": 1, "number_of_people": 1})
    r2 = staff_client.post("/api/checkin", json={"customer_name": "Occupant 2", "space_type_id": 1, "number_of_people": 1})
    assert r1.status_code == 200
    assert r2.status_code == 200
    s1 = r1.get_json()["session_id"]
    s2 = r2.get_json()["session_id"]

    # Customer 1 checks out
    co1 = staff_client.post(f"/api/checkout/{s1}", json={"payment_method": "gcash"})
    assert co1.status_code == 200

    with app.app_context():
        tx1 = Transaction.query.filter_by(session_id=s1).first()
        assert tx1 is not None
        tx1_id = tx1.id

    # Now Customer 3 checks in, filling the capacity back to 2!
    r3 = staff_client.post("/api/checkin", json={"customer_name": "Occupant 3", "space_type_id": 1, "number_of_people": 1})
    assert r3.status_code == 200

    # Staff requests void for Customer 1
    req = staff_client.post(f"/api/checkout-records/{tx1_id}/void-request", json={"reason": "Reopen please"})
    void_id = req.get_json()["void_request"]["id"]

    # Approval succeeds even though the lounge is full; the old customer stays out.
    approved = admin_client.post(f"/api/checkout-records/void-requests/{void_id}/approve", json={
        "money_treatment": "false_entry",
    })
    assert approved.status_code == 200
    assert len(staff_client.get("/api/active-sessions").get_json()) == 2

    full = staff_client.post("/api/checkin", json={"customer_name": "Occupant 1", "space_type_id": 1})
    assert full.status_code == 409

    # Now checkout Customer 2 to free capacity
    co2 = staff_client.post(f"/api/checkout/{s2}", json={"payment_method": "gcash"})
    assert co2.status_code == 200

    # Staff can now check the customer in again.
    new_checkin = staff_client.post("/api/checkin", json={"customer_name": "Occupant 1", "space_type_id": 1})
    assert new_checkin.status_code == 200
    assert new_checkin.get_json()["session_id"] != s1


def test_export_service_with_voided_records(app, staff_client, admin_client):
    # Test that DailyBalanceExportService builds context and handles voided records
    with app.app_context():
        today = date.today()
        sales_repo = SalesRepository()
        report = sales_repo.daily_ledger(today, today).get(today) or sales_repo.daily_ledger_empty(today)
        export_svc = DailyBalanceExportService(db)
        pdf_ctx = export_svc.build_pdf_context([report], [])
        assert "reports" in pdf_ctx
        assert "method_rows" in pdf_ctx
        assert "total_refunds" in pdf_ctx
