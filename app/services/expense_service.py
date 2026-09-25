from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.repositories.expense_repository import ExpenseRepository
from app.utils.payment import VALID_PAYMENT_METHODS
from app.models.expense import Expense


@dataclass(frozen=True)
class ExpenseService:
    repo: ExpenseRepository

    @staticmethod
    def _serialize(expenses) -> list[dict[str, Any]]:
        return [
            {
                "id": e.id,
                "category": e.category,
                "description": e.description,
                "amount": float(e.amount),
                "expense_date": e.expense_date.strftime("%Y-%m-%d"),
                "logged_by": e.logged_by_user.username if e.logged_by_user else "Unknown",
                "payment_method": e.payment_method or "unclassified",
                "voided_at": e.voided_at.isoformat() + "Z" if e.voided_at else None,
                "voided_by": e.voided_by_user.username if e.voided_by_user else None,
                "void_reason": e.void_reason,
            }
            for e in expenses
        ]

    def list_all(self) -> list[dict[str, Any]]:
        return self._serialize(self.repo.list_all())

    def list_history(self) -> list[dict[str, Any]]:
        return self._serialize(self.repo.list_history())

    def list_by_date(self, expense_date: str) -> list[dict[str, Any]]:
        date_obj = date.fromisoformat(expense_date)
        return self._serialize(self.repo.list_by_date(date_obj))

    def create(
        self,
        category: str,
        description: str,
        amount: float,
        expense_date: str,
        logged_by: int,
        payment_method: str,
        request_key: str | None = None,
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Select a payment method."}, 400
        if request_key and Expense.query.filter_by(request_key=request_key).first():
            return {"error": "This expense was already recorded."}, 409
        try:
            date_obj = date.fromisoformat(expense_date)
            amount_decimal = Decimal(str(amount))
            if (not amount_decimal.is_finite() or amount_decimal <= 0
                    or amount_decimal.as_tuple().exponent < -2):
                raise ValueError
        except (ValueError, TypeError, InvalidOperation):
            return {"error": "Enter a valid date and amount with up to two decimal places."}, 400
        expense = self.repo.create(category, description, amount_decimal, date_obj, logged_by, payment_method, request_key)
        self.repo.save()
        return {"success": True, "data": {"id": expense.id}}

    def delete(self, expense_id: int, voided_by: int, reason: str) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 255:
            return {"error": "Enter a reason (up to 255 characters)."}, 400
        success = self.repo.delete(expense_id, voided_by, reason.strip())
        if not success:
            return {"error": "Expense not found"}, 404
        self.repo.save()
        return {"success": True}
