from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app import create_app, db
from app.models import (BookingChange, BoardroomBooking, CheckoutVoidRequest, CustomerSession, Expense,
                        Order, SpaceType, StaffAttendance, Transaction, User)
from app.repositories.booking_repository import BookingRepository
from app.repositories.sales_repository import SalesRepository
from app.repositories.session_repository import SessionRepository
from app.services.booking_service import BookingService
from app.services.session_service import SessionService
from app.utils.dates import manila_date


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _staff_client(app):
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="staff",
                    last_activity=datetime.now(timezone.utc).timestamp())
    return client


def test_checkout_filters_before_pagination_using_manila_day(app):
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        old = CustomerSession(customer_name="Matching sale", space_type_id=space.id, status="completed")
        newer = CustomerSession(customer_name="Newer sales", space_type_id=space.id, status="completed")
        db.session.add_all([old, newer])
        db.session.flush()
        target = Transaction(session_id=old.id, time_bill=10, food_bill=0, total_bill=10,
                             payment_method="bdo", created_at=datetime(2026, 9, 24, 16, 30))
        newer_rows = [Transaction(session_id=newer.id, time_bill=10, food_bill=0, total_bill=10,
                                  payment_method="cash", created_at=datetime(2026, 9, 25, 16, 30))
                      for _ in range(51)]
        db.session.add_all([target, *newer_rows])
        db.session.commit()
        target_id = target.id

    response = _staff_client(app).get(
        "/api/checkout-records?date_from=2026-09-25&date_to=2026-09-25&payment_method=bdo"
    )
    assert response.status_code == 200
    assert [row["transaction_id"] for row in response.get_json()] == [target_id]


def test_checkout_daily_pages_search_and_status_reach_all_records(app):
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        sessions = [CustomerSession(customer_name=f"Guest {i}", space_type_id=space.id,
                                    status="completed", time_in=datetime(2026, 10, 4, 12))
                    for i in range(56)]
        db.session.add_all(sessions)
        db.session.flush()
        old = Transaction(session_id=sessions[0].id, time_bill=10, food_bill=0, total_bill=10,
                          payment_method="cash", created_at=datetime(2026, 10, 5, 15, 59))
        current = [Transaction(session_id=sessions[i].id, time_bill=10, food_bill=0,
                               total_bill=10, payment_method="cash",
                               created_at=datetime(2026, 10, 5, 16, 1))
                   for i in range(1, 54)]
        current[0].customer_name_snapshot = ""
        pending = Transaction(session_id=sessions[54].id, time_bill=10, food_bill=0,
                              total_bill=10, payment_method="bdo",
                              customer_name_snapshot="Snapshot Customer",
                              created_at=datetime(2026, 10, 5, 16, 1))
        voided = Transaction(session_id=sessions[55].id, time_bill=10, food_bill=0,
                             total_bill=10, payment_method="gcash", is_voided=True,
                             created_at=datetime(2026, 10, 5, 16, 1))
        db.session.add_all([old, *current, pending, voided])
        db.session.flush()
        db.session.add(CheckoutVoidRequest(
            transaction_id=pending.id, requested_by_id=1, status="pending",
            request_reason="Mistake", original_amount=10, original_payment_method="bdo",
            original_business_date=date(2026, 10, 6),
        ))
        db.session.commit()
        old_id, pending_id, voided_id, empty_snapshot_id = old.id, pending.id, voided.id, current[0].id

    client = _staff_client(app)
    base = "/api/checkout-records?paginated=1&date_from=2026-10-06&date_to=2026-10-06"
    first = client.get(base).get_json()
    second = client.get(base + "&page=2").get_json()
    assert first["total"] == 55 and first["has_next"] is True
    assert len(first["data"]) == 50 and len(second["data"]) == 5
    assert second["has_next"] is False
    ids = [row["transaction_id"] for row in first["data"] + second["data"]]
    assert len(set(ids)) == 55 and old_id not in ids
    assert all(row["created_date"] == "2026-10-06" for row in first["data"] + second["data"])
    assert client.get(base + "&search=Snapshot&status=pending_void&payment_method=bdo").get_json()["data"][0]["transaction_id"] == pending_id
    assert empty_snapshot_id in {
        row["transaction_id"] for row in client.get(base + "&search=Guest%201").get_json()["data"]
    }
    assert client.get(base + "&status=voided").get_json()["data"][0]["transaction_id"] == voided_id
    assert client.get(base + "&status=completed").get_json()["total"] == 53
    assert client.get("/api/checkout-records?paginated=1&date_from=2026-10-05&date_to=2026-10-05").get_json()["data"][0]["transaction_id"] == old_id
    assert client.get("/api/checkout-records?paginated=1").get_json()["total"] == 56
    assert isinstance(client.get("/api/checkout-records").get_json(), list)
    for bad in ("page=0", "page=1000001", "per_page=101", "date_from=bad", "status=bad", "payment_method=bad"):
        assert client.get("/api/checkout-records?paginated=1&" + bad).status_code == 400


def test_discounted_sales_breakdown_reconciles_with_daily_balance(app):
    with app.app_context():
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add(space)
        db.session.flush()
        customers = [CustomerSession(customer_name=f"Customer {i}", space_type_id=space.id,
                                     status="completed") for i in range(2)]
        db.session.add_all(customers)
        db.session.flush()
        db.session.add_all([
            Transaction(session_id=customers[0].id, time_bill=30, food_bill=240,
                        discount_item_id=1, discount_amount=24, total_bill=246,
                        payment_method="cash", created_at=datetime(2026, 9, 24, 16, 30)),
            Transaction(session_id=customers[1].id, time_bill=30, food_bill=0,
                        discount_amount=6, total_bill=24, payment_method="gcash",
                        created_at=datetime(2026, 9, 24, 16, 30)),
        ])
        db.session.commit()
        day = date(2026, 9, 25)
        summary = SalesRepository().summary_for_day(day)
        daily = SalesRepository().daily_ledger(day, day)[day]
        assert (summary.space_revenue, summary.food_revenue, summary.total_revenue) == (
            Decimal("54.00"), Decimal("216.00"), Decimal("270.00")
        )
        assert summary.space_revenue + summary.food_revenue == summary.total_revenue
        assert daily["total_revenue"] == 270
        assert daily["checkout_methods"]["cash"] == 246
        assert daily["checkout_methods"]["gcash"] == 24


def test_deactivating_staff_preserves_money_and_attendance_attribution(app):
    with app.app_context():
        staff = User(full_name="Former cashier", username="former_cashier", role="staff",
                     job_role="cashier", is_active=True)
        staff.set_password("TestPassword123!")
        space = SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667"))
        db.session.add_all([staff, space])
        db.session.flush()
        customer = CustomerSession(customer_name="Guest", space_type_id=space.id)
        db.session.add(customer)
        db.session.flush()
        order = Order(customer_session_id=customer.id, handled_by=staff.id)
        expense = Expense(category="supplies", description="Paper", amount=Decimal("20.00"),
                          expense_date=date(2026, 9, 25), payment_method="cash", logged_by=staff.id)
        attendance = StaffAttendance(user_id=staff.id, time_in=datetime(2026, 9, 25, 1, 0))
        db.session.add_all([order, expense, attendance])
        db.session.commit()
        staff_id, order_id, expense_id, attendance_id = staff.id, order.id, expense.id, attendance.id

        app.config["SINGLE_SESSION_ENABLED"] = False
        client = app.test_client()
        with client.session_transaction() as auth:
            auth.update(user_id=1, username="owner", role="admin",
                        last_activity=datetime.now(timezone.utc).timestamp())
        response = client.delete(f"/api/admin/users/{staff_id}",
                                 headers={"Idempotency-Key": "deactivate-former-cashier"})
        assert response.status_code == 200
        assert response.get_json() == {"message": "Staff deactivated."}
        assert db.session.get(User, staff_id).is_active is False
        assert db.session.get(Order, order_id).handled_by == staff_id
        assert db.session.get(Expense, expense_id).logged_by == staff_id
        assert db.session.get(StaffAttendance, attendance_id).time_out is not None
        assert staff_id not in {row["id"] for row in client.get("/api/admin/users").get_json()}


def test_booking_change_history_records_quote_actors_and_one_checkout_payment(app):
    with app.app_context():
        db.session.add(SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")))
        db.session.commit()
        booked_at = datetime(2026, 9, 24, 2, 0)
        clock = SimpleNamespace(now=lambda: booked_at)
        notifier = SimpleNamespace(booking_updated=lambda _: None, session_checked_out=lambda _: None)
        bookings = BookingService(BookingRepository(), notifier, clock)
        created = bookings.create_booking({
            "customer_name": "Friend", "date": "2026-09-24", "start_time": "10:00",
            "end_time": "11:00", "number_of_people": 2, "hourly_rate": "150",
        }, allow_custom_rate=True, actor_name="cashier_a")
        booking_id = created["booking_id"]
        assert bookings.update_booking_start(booking_id, "09:55", actor_name="cashier_b")["data"]
        assert bookings.start_booking(booking_id, actor_name="cashier_b")["session_id"]
        assert bookings.extend_booking(booking_id, 60, actor_name="cashier_a")["extended_minutes"] == 60

        checkout = SessionService(SessionRepository(),
                                  SimpleNamespace(now=lambda: booked_at + timedelta(hours=2)), notifier)
        session_id = db.session.get(BoardroomBooking, booking_id).session_id
        assert checkout.checkout(session_id, payment_method="cash", amount_tendered="450",
                                 actor_name="cashier_b")["total_bill"] == 450
        transaction = Transaction.query.filter_by(session_id=session_id).one()
        transaction.created_at = booked_at + timedelta(hours=2)
        db.session.commit()

        changes = BookingChange.query.filter_by(booking_id=booking_id).order_by(BookingChange.id).all()
        assert [row.action for row in changes] == [
            "created", "time_changed", "started", "extended", "checked_out"
        ]
        assert [(row.amount_before, row.amount_after) for row in changes] == [
            (Decimal("0.00"), Decimal("150.00")),
            (Decimal("150.00"), Decimal("300.00")),
            (Decimal("300.00"), Decimal("300.00")),
            (Decimal("300.00"), Decimal("450.00")),
            (Decimal("450.00"), Decimal("450.00")),
        ]
        assert changes[-1].actor == "cashier_b"
        assert changes[-1].payment_method == "cash"
        assert changes[-1].transaction_id == transaction.id
        assert all(row.business_date == date(2026, 9, 24) for row in changes)
        sale_day = manila_date(transaction.created_at)
        daily = SalesRepository().daily_ledger(sale_day, sale_day)[sale_day]
        assert daily["total_revenue"] == daily["checkout_methods"]["cash"] == 450
        assert daily["cash_count"] == 1

        another = bookings.create_booking({
            "customer_name": "Other", "date": "2026-09-24", "start_time": "13:00",
            "end_time": "14:00", "number_of_people": 1, "hourly_rate": "150",
        }, allow_custom_rate=True, actor_name="cashier_a")
        cancelled_id = another["booking_id"]
        assert bookings.cancel_booking(cancelled_id, actor_name="cashier_b")["message"] == "Booking cancelled"
        cancelled = BookingChange.query.filter_by(booking_id=cancelled_id).order_by(BookingChange.id).all()
        assert [(row.action, row.amount_after) for row in cancelled] == [
            ("created", Decimal("150.00")), ("cancelled", Decimal("0.00"))
        ]
        assert SalesRepository().daily_ledger(sale_day, sale_day)[sale_day]["total_revenue"] == 450

    response = _staff_client(app).get(f"/api/lounge-bookings/{booking_id}/history")
    assert response.status_code == 200
    assert len(response.get_json()) == 5
