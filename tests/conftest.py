"""Shared isolated database setup for the automated test suite."""

from __future__ import annotations

import os

import pytest

# Set test configuration before importing the Flask application. The application
# loads .env without overriding explicit process variables, so no local or VPS
# database can be selected during test collection.
os.environ["FLASK_ENV"] = "testing"
os.environ["SECRET_KEY"] = "isolated-pytest-secret-key-with-32-characters"
os.environ["DATABASE_URL"] = "sqlite://"

from app import db  # noqa: E402
from app.models import User  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_database(app):
    """Create clean in-memory tables and a valid authenticated account per test."""
    with app.app_context():
        db.create_all()
        if db.session.get(User, 1) is None:
            user = User(
                id=1,
                full_name="Test User",
                username="test_user",
                role="staff",
                job_role="general",
                is_active=True,
            )
            user.set_password("TestPassword123!")
            db.session.add(user)
            db.session.commit()

    yield

    with app.app_context():
        db.session.remove()
        db.drop_all()
