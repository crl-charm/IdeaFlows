from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app.repositories.receivable_repository import ReceivableRepository


@dataclass(frozen=True)
class ReceivableService:
    repo: ReceivableRepository

    @staticmethod
    def _serialize(receivables) -> list[dict[str, Any]]:
        return [
            {
                "id": r.id,
                "customer_name": r.customer_name,
                "customer_contact": r.customer_contact,
                "items": r.items_description,
                "amount_owed": float(r.amount_owed),
                "partial_paid": float(r.partial_paid),
                "due_date": r.due_date.strftime("%Y-%m-%d"),
                "incurred_date": (r.incurred_date or r.created_at.date()).strftime("%Y-%m-%d") if (r.incurred_date or r.created_at) else "",
                "paid": r.paid,
                "created_by": r.created_by_user.username if r.created_by_user else "Unknown",
                "approved_by_staff": r.approved_by_staff or "",
            }
            for r in receivables
        ]

    def list_all(self) -> list[dict[str, Any]]:
        return self._serialize(self.repo.list_all())

    def list_paginated(
        self,
        page: int,
        per_page: int,
        status: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        pagination = self.repo.list_paginated(page, per_page, status, search)
        return {
            "data": self._serialize(pagination.items),
            "pagination": {
                "page": pagination.page,
                "per_page": pagination.per_page,
                "pages": pagination.pages,
                "total": pagination.total,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }

    def list_unpaid(self) -> list[dict[str, Any]]:
        receivables = self.repo.list_unpaid()
        return [
            {
                "id": r.id,
                "customer_name": r.customer_name,
                "amount_owed": float(r.amount_owed),
                "partial_paid": float(r.partial_paid),
                "due_date": r.due_date.strftime("%Y-%m-%d"),
            }
            for r in receivables
        ]

    def create(
        self,
        customer_name: str,
        customer_contact: str,
        items_description: str,
        amount_owed: float,
        due_date: str,
        created_by: int,
        session_id: Optional[int],
        approved_by_staff: Optional[str] = None,
        incurred_date: Optional[str] = None,
    ) -> dict[str, Any]:
        due = date.fromisoformat(due_date)
        incurred = date.fromisoformat(incurred_date) if incurred_date else None
        amount_decimal = Decimal(str(amount_owed))
        receivable = self.repo.create(
            customer_name, customer_contact, items_description, amount_decimal, due, created_by, session_id, approved_by_staff, incurred
        )
        self.repo.save()
        return {"success": True, "data": {"id": receivable.id}}

    def mark_paid(self, receivable_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        success = self.repo.mark_paid(receivable_id)
        if not success:
            return {"error": "Receivable not found"}, 404
        self.repo.save()
        from app.core.socketio_handlers import emit_receivable_marked_paid

        emit_receivable_marked_paid(receivable_id)
        return {"success": True}

    def mark_customer_paid(self, customer_name: str) -> dict[str, Any]:
        success = self.repo.mark_customer_paid(customer_name)
        self.repo.save()
        return {"success": True}

    def emit_due_reminders(self) -> None:
        due_today = self.repo.list_due_today()
        for r in due_today:
            from app.core.socketio_handlers import emit_debt_due_reminder

            emit_debt_due_reminder({
                "receivable_id": r.id,
                "customer_name": r.customer_name,
                "amount_owed": float(r.amount_owed),
            })
