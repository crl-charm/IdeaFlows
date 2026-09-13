from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.interfaces import Notifier
from app.core.realtime import AUTHENTICATED_ROOM, compact_payload


@dataclass(frozen=True)
class SocketIONotifier(Notifier):
    socketio: Any

    def session_checked_out(self, payload: dict[str, Any]) -> None:
        self.socketio.emit(
            "session_checked_out", compact_payload(payload), to=AUTHENTICATED_ROOM
        )

    def order_status_changed(self, payload: dict[str, Any]) -> None:
        self.socketio.emit(
            "order_status_changed", compact_payload(payload), to=AUTHENTICATED_ROOM
        )

    def booking_updated(self, payload: dict[str, Any]) -> None:
        self.socketio.emit(
            "booking_updated", compact_payload(payload), to=AUTHENTICATED_ROOM
        )
