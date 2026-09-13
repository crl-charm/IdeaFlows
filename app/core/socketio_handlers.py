"""Authenticated, role-scoped Socket.IO events."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from flask import current_app, request, session
from flask_socketio import emit, join_room

from app import db, socketio
from app.core.realtime import (
    ADMIN_ROOM,
    AUTHENTICATED_ROOM,
    STAFF_ROOM,
    compact_change,
    compact_payload,
)

logger = logging.getLogger("security")


# Inventory Events
@socketio.on('connect')
def handle_connect(auth=None):
    """Reject anonymous/stale sessions and join the validated role room."""
    from app.models import User

    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    role = (getattr(user, "role", "") or "").strip().lower()
    last_activity = session.get("last_activity")
    lifetime = current_app.config.get("PERMANENT_SESSION_LIFETIME", 86400)
    lifetime_seconds = (
        lifetime.total_seconds() if hasattr(lifetime, "total_seconds") else float(lifetime)
    )
    try:
        session_age = datetime.now(timezone.utc).timestamp() - float(last_activity)
    except (TypeError, ValueError):
        session_age = lifetime_seconds + 1

    if (
        not user
        or not user.is_active
        or role not in {"admin", "staff"}
        or session_age > lifetime_seconds
    ):
        logger.warning(
            "Socket.IO connection rejected user_id=%s role=%s ip=%s",
            user_id,
            role or "missing",
            request.remote_addr,
        )
        return False

    join_room(AUTHENTICATED_ROOM)
    join_room(ADMIN_ROOM if role == "admin" else STAFF_ROOM)
    join_room(f"user:{user.id}")
    logger.info(
        "Socket.IO connected user_id=%s role=%s sid=%s ip=%s",
        user.id,
        role,
        request.sid,
        request.remote_addr,
    )
    emit('connected', {'authenticated': True, 'role': role})


@socketio.on('disconnect')
def handle_disconnect(reason=None):
    logger.info(
        "Socket.IO disconnected user_id=%s sid=%s reason=%s",
        session.get("user_id"),
        request.sid,
        reason or "client disconnect",
    )


def emit_inventory_update(event_type, item_data):
    """Broadcast compact inventory changes to authenticated clients.
    
    Args:
        event_type: 'create', 'update', 'delete', 'stock_change'
        item_data: dict containing item information
    """
    socketio.emit(
        'inventory_update', compact_change(event_type, item_data),
        to=AUTHENTICATED_ROOM,
    )


def emit_menu_update(event_type, item_data):
    """Broadcast compact menu changes to authenticated clients.
    
    Args:
        event_type: 'create', 'update', 'delete', 'availability_toggle'
        item_data: dict containing menu item information
    """
    socketio.emit(
        'menu_update', compact_change(event_type, item_data),
        to=AUTHENTICATED_ROOM,
    )


def emit_expenses_update(event_type, expense_data):
    """Broadcast compact expense changes to admin clients.
    
    Args:
        event_type: 'create', 'delete'
        expense_data: dict containing expense information
    """
    socketio.emit(
        'expenses_update', compact_change(event_type, expense_data), to=ADMIN_ROOM
    )


def emit_receivables_update(event_type, receivable_data):
    """Broadcast compact receivable changes to admin clients.
    
    Args:
        event_type: 'create', 'mark_paid', 'update'
        receivable_data: dict containing receivable information
    """
    socketio.emit(
        'receivables_update', compact_change(event_type, receivable_data),
        to=ADMIN_ROOM,
    )


def emit_inventory_low_stock(payload: dict) -> None:
    socketio.emit(
        "inventory_low_stock", compact_payload(payload), to=AUTHENTICATED_ROOM
    )


def emit_receivable_marked_paid(receivable_id: int) -> None:
    socketio.emit(
        "receivable_marked_paid", {"receivable_id": receivable_id}, to=ADMIN_ROOM
    )


def emit_debt_due_reminder(payload: dict) -> None:
    socketio.emit("debt_due_reminder", compact_payload(payload), to=ADMIN_ROOM)


def emit_daily_sales_closed(payload: dict) -> None:
    socketio.emit("daily_sales_closed", compact_payload(payload), to=ADMIN_ROOM)


def emit_staff_status_change(user_id: int, status: str) -> None:
    """Broadcast staff status updates (online/offline) to admin clients."""
    socketio.emit(
        'staff_status_change', {'user_id': user_id, 'status': status}, to=ADMIN_ROOM
    )

