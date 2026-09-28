from datetime import datetime, time, timedelta, timezone

import pytest

from app import create_app, db
from app.models import StaffAttendance, StaffShift, User
from app.utils.dates import MANILA_OFFSET


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


def _signed_in(app, role="staff"):
    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role=role,
                    last_activity=datetime.now(timezone.utc).timestamp())
    return client


def _past_local_shift():
    yesterday = (datetime.now(timezone.utc).replace(tzinfo=None) + MANILA_OFFSET).date() - timedelta(days=2)
    started = datetime.combine(yesterday, time(23, 0))
    ended = started + timedelta(hours=3)
    return started.strftime("%Y-%m-%dT%H:%M"), ended.strftime("%Y-%m-%dT%H:%M")


def test_staff_can_record_role_and_overnight_shift_without_changing_permissions(app):
    client = _signed_in(app)
    started, ended = _past_local_shift()
    assert client.get("/api/staff-shift").get_json() == {
        "name": "Test User", "account_role": "general", "open_shift": None,
    }

    created = client.post("/api/staff-shift/time-in", json={"role": "cashier", "time_in": started})
    assert created.status_code == 201
    assert created.get_json()["shift"]["time_out"] is None
    assert client.get("/api/staff-shift").get_json()["open_shift"]["role"] == "cashier"
    assert client.post("/api/staff-shift/time-in", json={"role": "cook", "time_in": started}).status_code == 409

    with app.app_context():
        shift = StaffShift.query.one()
        assert shift.time_in == datetime.strptime(started, "%Y-%m-%dT%H:%M") - MANILA_OFFSET
        assert shift.recorded_at is not None
        assert db.session.get(User, 1).job_role == "general"

    assert client.get("/logout").status_code == 302
    with app.app_context():
        assert StaffShift.query.one().time_out is None

    later_session = _signed_in(app)
    assert later_session.get("/api/staff-shift").get_json()["open_shift"]["time_in"] == started
    closed = later_session.post("/api/staff-shift/time-out", json={"time_out": ended})
    assert closed.status_code == 200
    assert closed.get_json()["shift"]["time_out"] == ended
    with app.app_context():
        shift = StaffShift.query.one()
        assert shift.time_out_recorded_at is not None
        assert db.session.get(User, 1).job_role == "general"


def test_staff_shift_rejects_bad_inputs_and_requires_staff_account(app):
    client = _signed_in(app)
    started, _ = _past_local_shift()
    future = (datetime.now(timezone.utc).replace(tzinfo=None) + MANILA_OFFSET + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    assert client.post("/api/staff-shift/time-in", json={"role": "admin", "time_in": started}).status_code == 400
    assert client.post("/api/staff-shift/time-in", json={"role": "cashier", "time_in": future}).status_code == 400
    assert client.post("/api/staff-shift/time-out", json={"time_out": started}).status_code == 409
    assert client.post("/api/staff-shift/time-in", json={"role": "cook", "time_in": started}).status_code == 201
    assert client.post("/api/staff-shift/time-out", json={"time_out": "bad"}).status_code == 400
    assert client.post("/api/staff-shift/time-out", json={"time_out": (datetime.strptime(started, "%Y-%m-%dT%H:%M") - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M")}).status_code == 400

    anonymous = app.test_client()
    assert anonymous.get("/api/staff-shift").status_code == 401
    admin = _signed_in(app, role="admin")
    assert admin.get("/api/staff-shift").status_code == 403
    assert admin.post("/api/staff-shift/time-in", json={"role": "cook", "time_in": started}).status_code == 403


def test_admin_history_shows_manual_shift_and_only_older_login_records(app):
    started, _ = _past_local_shift()
    entered = datetime.strptime(started, "%Y-%m-%dT%H:%M") - MANILA_OFFSET
    with app.app_context():
        db.session.add_all([
            StaffAttendance(user_id=1, time_in=entered - timedelta(days=1), show_in_history=True),
            StaffAttendance(user_id=1, time_in=entered, show_in_history=False),
            StaffShift(user_id=1, shift_role="server", time_in=entered),
        ])
        db.session.commit()

    admin = _signed_in(app, role="admin")
    response = admin.get("/api/admin/staff-attendance")
    assert response.status_code == 200
    rows = response.get_json()
    assert len(rows) == 2
    assert rows[0]["source"] == "Manual shift"
    assert rows[0]["shift_role"] == "Server"
    assert rows[0]["time_in"] == datetime.strptime(started, "%Y-%m-%dT%H:%M").strftime("%Y-%m-%d %I:%M %p")
    assert rows[1]["source"] == "Legacy login record"
    assert rows[1]["shift_role"] == "Not recorded"
    assert _signed_in(app).get("/api/admin/staff-attendance").status_code == 403
