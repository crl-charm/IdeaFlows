from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.repositories.receivable_repository import ReceivableRepository
from app.utils.payment import VALID_PAYMENT_METHODS


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
                "notes": r.notes or "",
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
        notes: Optional[str] = None,
    ) -> dict[str, Any]:
        due = date.fromisoformat(due_date)
        incurred = date.fromisoformat(incurred_date) if incurred_date else None
        amount_decimal = Decimal(str(amount_owed))
        if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
            raise ValueError("Notes must be text up to 2,000 characters.")
        clean_notes = notes.strip() if notes else ""
        receivable = self.repo.create(
            customer_name, customer_contact, items_description, amount_decimal, due, created_by, session_id, approved_by_staff, incurred, clean_notes
        )
        self.repo.save()
        return {"success": True, "data": {"id": receivable.id}}

    def mark_paid(self, receivable_id: int, amount: Any, received_by: int, payment_method: str) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Invalid payment method"}, 400
        try:
            payment = None if amount is None else Decimal(str(amount))
            if payment is not None and (not payment.is_finite() or payment.as_tuple().exponent < -2):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return {"error": "Enter a valid payment amount with up to two decimal places."}, 400
        try:
            success = self.repo.record_payment(receivable_id, payment, received_by, payment_method)
        except ValueError as exc:
            return {"error": str(exc)}, 400
        if not success:
            return {"error": "Receivable not found"}, 404
        self.repo.save()
        from app.core.socketio_handlers import emit_receivable_marked_paid

        emit_receivable_marked_paid(receivable_id)
        return {"success": True}

    def record_customer_payment(self, customer_name: str, amount: Any, received_by: int, payment_method: str, customer_contact: str = "") -> dict[str, Any] | tuple[dict[str, Any], int]:
        if payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Invalid payment method"}, 400
        if not isinstance(customer_name, str) or not customer_name.strip():
            return {"error": "Customer name is required"}, 400
        if not isinstance(customer_contact, str):
            return {"error": "Customer contact must be text"}, 400
        try:
            payment = Decimal(str(amount))
            if not payment.is_finite() or payment.as_tuple().exponent < -2 or payment <= 0:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return {"error": "Enter a valid payment amount with up to two decimal places."}, 400
        try:
            remaining = self.repo.record_customer_payment(customer_name, payment, received_by, payment_method, customer_contact)
        except ValueError as exc:
            return {"error": str(exc)}, 400
        self.repo.save()
        return {"success": True, "remaining": float(remaining)}

    def list_customer_payments(self, customer_name: str, customer_contact: str = "") -> list[dict[str, Any]]:
        payments = self.repo.list_customer_payments(customer_name, customer_contact)
        grouped = {}
        for payment in payments:
            key = payment.payment_group_id or f"single-{payment.id}"
            if key not in grouped:
                actor = payment.received_by_user
                grouped[key] = {
                    "amount": Decimal("0"),
                    "received_at": payment.received_at.isoformat() + "Z",
                    "payment_method": payment.payment_method,
                    "received_by": (actor.full_name or actor.username) if actor else "Unknown",
                }
            grouped[key]["amount"] += payment.amount
        return [{**entry, "amount": float(entry["amount"])} for entry in grouped.values()]

    def update_notes(self, receivable_id: int, notes: str) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if len(notes) > 2000:
            return {"error": "Notes must be 2,000 characters or fewer."}, 400
        if not self.repo.update_notes(receivable_id, notes.strip()):
            return {"error": "Receivable not found"}, 404
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
