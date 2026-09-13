from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app.repositories.expense_repository import ExpenseRepository


@dataclass(frozen=True)
class ExpenseService:
    repo: ExpenseRepository

    def list_all(self) -> list[dict[str, Any]]:
        expenses = self.repo.list_all()
        return [
            {
                "id": e.id,
                "category": e.category,
                "description": e.description,
                "amount": float(e.amount),
                "expense_date": e.expense_date.strftime("%Y-%m-%d"),
                "logged_by": e.logged_by_user.username if e.logged_by_user else "Unknown",
            }
            for e in expenses
        ]

    def list_by_date(self, expense_date: str) -> list[dict[str, Any]]:
        date_obj = date.fromisoformat(expense_date)
        expenses = self.repo.list_by_date(date_obj)
        return [
            {
                "id": e.id,
                "category": e.category,
                "description": e.description,
                "amount": float(e.amount),
                "logged_by": e.logged_by_user.username if e.logged_by_user else "Unknown",
            }
            for e in expenses
        ]

    def create(
        self,
        category: str,
        description: str,
        amount: float,
        expense_date: str,
        logged_by: int,
    ) -> dict[str, Any]:
        date_obj = date.fromisoformat(expense_date)
        amount_decimal = Decimal(str(amount))
        expense = self.repo.create(category, description, amount_decimal, date_obj, logged_by)
        self.repo.save()
        return {"success": True, "data": {"id": expense.id}}

    def delete(self, expense_id: int) -> dict[str, Any] | tuple[dict[str, Any], int]:
        success = self.repo.delete(expense_id)
        if not success:
            return {"error": "Expense not found"}, 404
        self.repo.save()
        return {"success": True}
