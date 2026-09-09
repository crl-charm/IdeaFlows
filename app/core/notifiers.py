from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.interfaces import Notifier


@dataclass(frozen=True)
class SocketIONotifier(Notifier):
    socketio: Any

    def session_checked_out(self, payload: dict[str, Any]) -> None:
        self.socketio.emit("session_checked_out", payload)

    def order_status_changed(self, payload: dict[str, Any]) -> None:
        self.socketio.emit("order_status_changed", payload)

    def booking_updated(self, payload: dict[str, Any]) -> None:
        self.socketio.emit("booking_updated", payload)
