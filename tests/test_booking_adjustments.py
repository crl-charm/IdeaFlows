from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import inspect

from app import create_app, db
from app.models import BoardroomBooking, SpaceType
from app.repositories.booking_repository import BookingRepository
from app.repositories.session_repository import SessionRepository
from app.services.booking_service import BookingService
from app.services.session_service import SessionService
from app.utils.billing import calculate_time_bill


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _services(now):
    clock = SimpleNamespace(now=lambda: now)
    notifier = SimpleNamespace(booking_updated=lambda _: None, session_checked_out=lambda _: None)
    return BookingService(BookingRepository(), notifier, clock), SessionService(SessionRepository(), clock, notifier)


def _booking(**changes):
    data = dict(customer_name="Friend", date="2026-09-24", start_time="10:00", end_time="11:00",
                number_of_people=2, booking_type="boardroom")
    data.update(changes)
    return data


def test_boardroom_friend_price_and_ten_minute_grace(app):
    with app.app_context():
        db.session.add(SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")))
        db.session.commit()
        service, sessions = _services(datetime(2026, 9, 24, 2, 0))
        assert service.create_booking(_booking(hourly_rate="150"))[1] == 403
        assert service.create_booking(_booking(hourly_rate="150"), allow_custom_rate=True)["booking_id"]
        booking = BoardroomBooking.query.one()
        assert service.create_booking(_booking(start_time="11:00", end_time="12:00"))[1] == 400
        assert service.create_booking(_booking(start_time="11:10", end_time="12:10"))["booking_id"]
        assert service.start_booking(booking.id)["session_id"]
        assert calculate_time_bill(None, 70, booking=booking, now_utc=datetime(2026, 9, 24, 3, 10)) == Decimal("150.00")
        assert calculate_time_bill(None, 71, booking=booking, now_utc=datetime(2026, 9, 24, 3, 11)) == Decimal("300.00")
        checkout = SessionService(SessionRepository(), SimpleNamespace(now=lambda: datetime(2026, 9, 24, 3, 11)),
                                  SimpleNamespace(session_checked_out=lambda _: None))
        assert checkout.checkout(booking.session_id, amount_tendered="300")["time_bill"] == 300
        assert booking.extended_minutes == 1


def test_whole_hub_blocks_all_spaces_and_walk_in_starts_session(app):
    with app.app_context():
        db.session.add_all([
            SpaceType(name="Boardroom", rate_per_minute=Decimal("4.1667")),
            SpaceType(name="Whole Hub", rate_per_minute=Decimal("8.3333")),
            SpaceType(name="Regular Lounge", rate_per_minute=Decimal("0.1667")),
            SpaceType(name="Premium Lounge", rate_per_minute=Decimal("0.3333")),
        ])
        db.session.commit()
        service, sessions = _services(datetime(2026, 9, 24, 2, 0))
        result = service.create_booking(_booking(booking_type="whole_hub", walk_in=True))
        assert result["session_id"]
        booking = BoardroomBooking.query.one()
        assert booking.hourly_rate == Decimal("500.00")
        regular = SpaceType.query.filter_by(name="Regular Lounge").one()
        premium = SpaceType.query.filter_by(name="Premium Lounge").one()
        boardroom = SpaceType.query.filter_by(name="Boardroom").one()
        assert sessions.checkin(customer_name="Visitor", school=None, course=None,
                                space_type_id=regular.id, number_of_people=1)[1] == 409
        for space in (premium, boardroom):
            assert sessions.checkin(customer_name="Visitor", school=None, course=None,
                                    space_type_id=space.id, number_of_people=1)[1] == 409
        assert service.create_booking(_booking(start_time="10:30", end_time="11:30"))[1] == 400
        assert sessions.preview_checkout(result["session_id"])["time_bill"] == 500


def test_invalid_booking_inputs_return_client_errors(app):
    with app.app_context():
        service, _ = _services(datetime(2026, 9, 24, 2, 0))
        for bad in (dict(customer_name={"bad": "name"}), dict(course=[]),
                    dict(purpose=["invalid"]), dict(number_of_people="1.5")):
            assert service.create_booking(_booking(**bad))[1] == 400


def test_staff_booking_page_shows_walk_in_and_whole_hub(app):
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, role="staff", last_activity=datetime.now(timezone.utc).timestamp())
    response = client.get("/lounge-booking")
    assert response.status_code == 200
    assert b"Walk in now" in response.data
    assert b"Whole Hub" in response.data


def test_development_app_factory_prepares_booking_schema(app, monkeypatch):
    from config import Config

    monkeypatch.setattr(Config, "FLASK_ENV", "development")
    monkeypatch.setattr(Config, "AUTO_MIGRATE_ON_STARTUP", True)
    runtime_app = create_app()
    with runtime_app.app_context():
        columns = {column["name"] for column in inspect(db.engine).get_columns("boardroom_bookings")}
        assert {"booking_type", "hourly_rate"} <= columns
        assert SpaceType.query.filter_by(name="Whole Hub").one()
