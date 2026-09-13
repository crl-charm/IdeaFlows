from __future__ import annotations

from app import socketio
from app.core.notifiers import SocketIONotifier


def get_notifier():
    """Return the Socket.IO notifier used by the VPS deployment."""
    return SocketIONotifier(socketio=socketio)
