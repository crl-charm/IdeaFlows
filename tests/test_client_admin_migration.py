"""Production admin provisioning keeps credentials private and never resets accounts."""

import os

import bcrypt
import pytest

from app import create_app, db
from app.db.run_migrations import provision_client_admins
from app.models import Admin, User


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, FLASK_ENV="production", SINGLE_SESSION_ENABLED=False)
    return application


def test_creates_both_admins_once_without_changing_existing_admin(app, tmp_path, capsys):
    credentials = tmp_path / "credentials.txt"
    with app.app_context():
        original = Admin(full_name="System Admin", username="admin")
        original.set_password("ExistingOwnerPassword123!")
        db.session.add(original)
        db.session.commit()
        original_hash = original.password

    assert provision_client_admins(app, credentials) is True
    passwords = dict(line.split(": ", 1) for line in credentials.read_text().splitlines())
    assert set(passwords) == {"admin_gilbert", "admin3"}
    assert passwords["admin_gilbert"] != passwords["admin3"]
    migration_output = capsys.readouterr().out
    assert all(password not in migration_output for password in passwords.values())
    if os.name != "nt":
        assert credentials.stat().st_mode & 0o777 == 0o600

    with app.app_context():
        assert Admin.query.filter_by(username="admin").one().password == original_hash
        hashes = {}
        for username, full_name in (("admin_gilbert", "Admin Gilbert"), ("admin3", "Admin 3")):
            account = Admin.query.filter_by(username=username).one()
            assert account.full_name == full_name
            assert bcrypt.checkpw(passwords[username].encode(), account.password.encode())
            hashes[username] = account.password

    client = app.test_client()
    for username, password in passwords.items():
        assert client.post("/api/login", json={"username": username, "password": password}).status_code == 200
        assert client.get("/admin").status_code == 200
        assert client.get("/logout").status_code == 302

    assert provision_client_admins(app, credentials) is False
    with app.app_context():
        assert Admin.query.count() == 3
        assert Admin.query.filter_by(username="admin").one().password == original_hash
        for username, old_hash in hashes.items():
            assert Admin.query.filter_by(username=username).one().password == old_hash
            shadow = User.query.filter_by(username=username).one()
            assert shadow.role == "admin" and shadow.is_active is False


@pytest.mark.parametrize("collision_table", ["admins", "users"])
def test_collision_creates_neither_account_nor_secret(app, tmp_path, collision_table):
    with app.app_context():
        if collision_table == "admins":
            existing = Admin(full_name="Someone Else", username="admin3")
        else:
            existing = User(full_name="Someone Else", username="admin3", role="staff")
        existing.set_password("ExistingPassword123!")
        db.session.add(existing)
        db.session.commit()

    credentials = tmp_path / "credentials.txt"
    with pytest.raises(RuntimeError, match="username"):
        provision_client_admins(app, credentials)
    assert not credentials.exists()
    with app.app_context():
        assert Admin.query.filter_by(username="admin_gilbert").first() is None


def test_existing_secret_file_is_not_overwritten(app, tmp_path):
    credentials = tmp_path / "credentials.txt"
    credentials.write_text("keep this private")
    with pytest.raises(FileExistsError):
        provision_client_admins(app, credentials)
    assert credentials.read_text() == "keep this private"
    with app.app_context():
        assert Admin.query.count() == 0
