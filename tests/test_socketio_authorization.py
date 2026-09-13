"""Phase 6 authentication and role-room tests for real-time events."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import create_app, db, socketio
from app.core.socketio_handlers import emit_expenses_update, emit_inventory_update
from app.models import User


@pytest.fixture
def app():
    application = create_app()
    application.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return application


def _authenticated_flask_client(app, user_id: int, role: str):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["username"] = f"socket_{role}"
        sess["role"] = role
        sess["last_activity"] = datetime.now(timezone.utc).timestamp()
    return client


def _event_names(client) -> list[str]:
    return [event["name"] for event in client.get_received()]


def test_anonymous_socket_connection_is_rejected(app):
    socket_client = socketio.test_client(app, flask_test_client=app.test_client())
    assert socket_client.is_connected() is False


def test_expired_socket_session_is_rejected(app):
    flask_client = app.test_client()
    with flask_client.session_transaction() as sess:
        sess["user_id"] = 1
        sess["role"] = "staff"
        sess["last_activity"] = 0
    socket_client = socketio.test_client(app, flask_test_client=flask_client)
    assert socket_client.is_connected() is False


def test_financial_events_reach_admin_but_not_staff(app):
    with app.app_context():
        admin = User(
            full_name="Socket Admin",
            username="socket_admin",
            role="admin",
            job_role="admin",
            is_active=True,
        )
        admin.set_password("TestPassword123!")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    admin_socket = socketio.test_client(
        app,
        flask_test_client=_authenticated_flask_client(app, admin_id, "admin"),
    )
    staff_socket = socketio.test_client(
        app,
        flask_test_client=_authenticated_flask_client(app, 1, "staff"),
    )
    assert admin_socket.is_connected() is True
    assert staff_socket.is_connected() is True
    admin_socket.get_received()
    staff_socket.get_received()

    with app.app_context():
        emit_expenses_update(
            "create", {"id": 91, "amount": 5000, "description": "private"}
        )
        socketio.sleep(0)

    admin_events = admin_socket.get_received()
    staff_events = staff_socket.get_received()
    expense = next(event for event in admin_events if event["name"] == "expenses_update")
    assert expense["args"][0] == {"event": "create", "id": 91}
    assert "expenses_update" not in [event["name"] for event in staff_events]

    admin_socket.disconnect()
    staff_socket.disconnect()


def test_operational_events_reach_both_roles_with_compact_payload(app):
    with app.app_context():
        admin = User(
            full_name="Operations Admin",
            username="operations_admin",
            role="admin",
            job_role="admin",
            is_active=True,
        )
        admin.set_password("TestPassword123!")
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id

    admin_socket = socketio.test_client(
        app,
        flask_test_client=_authenticated_flask_client(app, admin_id, "admin"),
    )
    staff_socket = socketio.test_client(
        app,
        flask_test_client=_authenticated_flask_client(app, 1, "staff"),
    )
    admin_socket.get_received()
    staff_socket.get_received()

    with app.app_context():
        emit_inventory_update(
            "stock_change", {"item_id": 7, "stock_qty": 99, "cost": 1200}
        )
        socketio.sleep(0)

    for client in (admin_socket, staff_socket):
        events = client.get_received()
        inventory = next(event for event in events if event["name"] == "inventory_update")
        assert inventory["args"][0] == {"event": "stock_change", "item_id": 7}

    admin_socket.disconnect()
    staff_socket.disconnect()
