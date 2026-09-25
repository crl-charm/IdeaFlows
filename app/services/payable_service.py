from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from app.repositories.payable_repository import PayableRepository
from app.models.payable import Payable
from app.utils.payment import VALID_PAYMENT_METHODS


@dataclass(frozen=True)
class PayableService:
    repo: PayableRepository

    def list_all(self) -> list[dict[str, Any]]:
        payables = self.repo.list_all()
        return [
            {
                "id": p.id,
                "creditor_name": p.creditor_name,
                "items": p.items_description,
                "amount_owed": float(p.amount_owed),
                "partial_paid": float(p.partial_paid),
                "due_date": p.due_date.strftime("%Y-%m-%d"),
                "incurred_date": p.incurred_date.strftime("%Y-%m-%d"),
                "status": p.status,
                "created_by": p.created_by_user.username if p.created_by_user else "Unknown",
                "payments": [
                    {
                        "amount": float(payment.amount),
                        "payment_method": payment.payment_method,
                        "paid_at": payment.paid_at.isoformat() + "Z",
                        "paid_by": payment.paid_by_user.username if payment.paid_by_user else "Unknown",
                        "balance_before": float(payment.balance_before),
                        "balance_after": float(payment.balance_after),
                    }
                    for payment in p.payments
                ],
                "legacy_paid_unattributed": float(max(
                    p.partial_paid - sum((payment.amount for payment in p.payments), Decimal("0")),
                    Decimal("0"),
                )),
            }
            for p in payables
        ]

    def create(
        self,
        creditor_name: str,
        items_description: str,
        amount_owed: float,
        due_date: str,
        incurred_date: str,
        created_by: int,
    ) -> dict[str, Any]:
        due = date.fromisoformat(due_date)
        incurred = date.fromisoformat(incurred_date) if incurred_date else date.today()
        amount_decimal = Decimal(str(amount_owed))
        payable = self.repo.create(
            creditor_name=creditor_name,
            items_description=items_description,
            amount_owed=amount_decimal,
            due_date=due,
            incurred_date=incurred,
            created_by=created_by,
        )
        self.repo.save()
        return {"success": True, "data": {"id": payable.id}}

    def mark_paid(self, payable_id: int, amount: Any, payment_method: str, paid_by: int, request_key: str | None = None) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Invalid payment method"}, 400
        try:
            payment_amount = None if amount is None else Decimal(str(amount))
            if payment_amount is not None and (
                not payment_amount.is_finite() or payment_amount.as_tuple().exponent < -2
            ):
                raise ValueError
        except (InvalidOperation, ValueError, TypeError):
            return {"error": "Enter a valid payment amount with up to two decimal places."}, 400
        try:
            payment = self.repo.mark_paid(payable_id, payment_amount, payment_method, paid_by, request_key)
        except ValueError as exc:
            return {"error": str(exc)}, 400
        if not payment:
            return {"error": "Payable not found"}, 404
        self.repo.save()
        return {"success": True, "payment_id": payment.id}

    def get_due_count(self) -> int:
        today = date.today()
        three_days_later = today + timedelta(days=3)
        count = Payable.query.filter(
            Payable.status != "Paid",
            Payable.due_date <= three_days_later
        ).count()
        return count
