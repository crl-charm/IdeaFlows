"""Shared room names and minimal payload shaping for real-time events."""

from __future__ import annotations

from typing import Any, Iterable


AUTHENTICATED_ROOM = "authenticated"
ADMIN_ROOM = "role:admin"
STAFF_ROOM = "role:staff"

IDENTIFIER_FIELDS = frozenset(
    {
        "id",
        "item_id",
        "menu_item_id",
        "inventory_item_id",
        "recipe_id",
        "expense_id",
        "receivable_id",
        "payable_id",
        "order_id",
        "session_id",
        "booking_id",
        "user_id",
        "report_date",
        "status",
    }
)


def compact_payload(
    payload: dict[str, Any] | None, allowed: Iterable[str] = IDENTIFIER_FIELDS
) -> dict[str, Any]:
    """Return only fields clients need to decide what data to refresh."""
    if not isinstance(payload, dict):
        return {}
    allowed_fields = set(allowed)
    return {key: payload[key] for key in allowed_fields if key in payload}


def compact_change(event_type: str, payload: dict[str, Any] | None) -> dict[str, Any]:
    return {"event": event_type, **compact_payload(payload)}
