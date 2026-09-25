from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from app.repositories.payable_repository import PayableRepository
from app.models.payable import Payable


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

    def mark_paid(self, payable_id: int, amount: Optional[float] = None) -> dict[str, Any] | tuple[dict[str, Any], int]:
        success = self.repo.mark_paid(payable_id, amount)
        if not success:
            return {"error": "Payable not found"}, 404
        self.repo.save()
        return {"success": True}

    def get_due_count(self) -> int:
        today = date.today()
        three_days_later = today + timedelta(days=3)
        count = Payable.query.filter(
            Payable.status != "Paid",
            Payable.due_date <= three_days_later
        ).count()
        return count
