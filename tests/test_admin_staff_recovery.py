from datetime import datetime, timedelta, timezone
import re
import shutil
import subprocess

import pytest
from flask import render_template
from sqlalchemy import inspect, text

from app import create_app, db
from app.db.migrator import SchemaMigrator
from app.models import StaffAttendance, User


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SINGLE_SESSION_ENABLED=False)
    return application


def test_admin_can_reactivate_deactivated_staff_without_losing_history(app):
    with app.app_context():
        owner = db.session.get(User, 1)
        owner.role = "admin"
        staff = User(full_name="Arnold", username="arnold", role="staff",
                     job_role="cashier", is_active=True)
        staff.set_password("StaffPassword123!")
        db.session.add(staff)
        db.session.flush()
        attendance = StaffAttendance(user_id=staff.id, time_in=datetime(2026, 9, 25, 1, 0),
                                     time_out=datetime(2026, 9, 25, 9, 0))
        db.session.add(attendance)
        db.session.commit()
        staff_id, attendance_id = staff.id, attendance.id

    client = app.test_client()
    with client.session_transaction() as auth:
        auth.update(user_id=1, username="test_user", role="admin",
                    last_activity=datetime.now(timezone.utc).timestamp())

    assert client.delete(f"/api/admin/users/{staff_id}").status_code == 200
    assert client.get("/api/admin/users").get_json() == []
    inactive = client.get("/api/admin/users?inactive=1").get_json()
    assert [(row["id"], row["is_active"]) for row in inactive] == [(staff_id, False)]
    with app.app_context():
        deactivated_at = db.session.get(User, staff_id).deactivated_at
    assert datetime.fromisoformat(inactive[0]["reactivate_until"].replace("Z", "+00:00")) == (
        deactivated_at + timedelta(hours=24)
    ).replace(tzinfo=timezone.utc)

    duplicate = client.post("/api/register", json={
        "full_name": "Arnold", "username": "arnold", "job_role": "cashier",
        "password": "NewPassword123!",
    })
    assert duplicate.status_code == 409
    assert "reactivate" in duplicate.get_json()["error"]

    response = client.post(f"/api/admin/users/{staff_id}/reactivate",
                           headers={"Idempotency-Key": "restore-arnold"})
    assert response.status_code == 200
    assert response.get_json() == {"message": "Staff reactivated."}
    assert [row["id"] for row in client.get("/api/admin/users").get_json()] == [staff_id]
    assert client.get("/api/admin/users?inactive=1").get_json() == []

    with app.app_context():
        assert db.session.get(User, staff_id).is_active is True
        assert db.session.get(User, staff_id).deactivated_at is None
        assert db.session.get(StaffAttendance, attendance_id).user_id == staff_id

    staff_client = app.test_client()
    with staff_client.session_transaction() as auth:
        auth.update(user_id=staff_id, username="arnold", role="staff",
                    last_activity=datetime.now(timezone.utc).timestamp())
    assert staff_client.post(f"/api/admin/users/{staff_id}/reactivate").status_code == 403

    assert client.delete(f"/api/admin/users/{staff_id}").status_code == 200
    with app.app_context():
        staff = db.session.get(User, staff_id)
        staff.deactivated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=24, seconds=1)
        db.session.commit()
    assert client.get("/api/admin/users?inactive=1").get_json() == []
    expired = client.post(f"/api/admin/users/{staff_id}/reactivate")
    assert expired.status_code == 410
    assert "24-hour" in expired.get_json()["error"]
    assert "cannot be reused" in client.post("/api/register", json={
        "full_name": "Arnold", "username": "arnold", "job_role": "cashier",
        "password": "NewPassword123!",
    }).get_json()["error"]
    with app.app_context():
        assert db.session.get(User, staff_id).is_active is False
        assert db.session.get(StaffAttendance, attendance_id).user_id == staff_id


def test_migration_starts_recovery_window_for_existing_inactive_staff(app):
    with app.app_context():
        staff = User(full_name="Former server", username="former_server", role="staff",
                     job_role="server", is_active=False)
        staff.set_password("StaffPassword123!")
        db.session.add(staff)
        db.session.commit()
        db.session.execute(text("ALTER TABLE users DROP COLUMN deactivated_at"))
        db.session.commit()
        before = datetime.now(timezone.utc).replace(tzinfo=None)
        migrator = SchemaMigrator(db, app)
        migrator.run()
        assert "deactivated_at" in {column["name"] for column in inspect(db.engine).get_columns("users")}
        db.session.refresh(staff)
        assert before <= staff.deactivated_at <= datetime.now(timezone.utc).replace(tzinfo=None)
        backfilled_at = staff.deactivated_at
        migrator.run()
        db.session.refresh(staff)
        assert staff.deactivated_at == backfilled_at


def test_admin_page_javascript_parses(app):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is needed to check the admin page script")
    with app.test_request_context("/admin"):
        html = render_template("admin.html")
    scripts = re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, re.DOTALL)
    admin_script = next(script for script in scripts if "function loadUsers()" in script)
    result = subprocess.run([node, "--check"], input=admin_script,
                            text=True, encoding="utf-8", capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
