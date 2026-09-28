from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app import db
from app.repositories.expense_repository import ExpenseRepository
from app.utils.payment import VALID_PAYMENT_METHODS
from app.models.expense import Expense
from app.repositories.sales_repository import SalesRepository
from app.utils.dates import manila_date


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
                "business_date": (manila_date(e.created_at) if e.funding_source else e.expense_date).isoformat(),
                "posted_at": e.created_at.isoformat() + "Z" if e.created_at else None,
                "logged_by": e.logged_by_user.username if e.logged_by_user else "Unknown",
                "payment_method": e.payment_method or "unclassified",
                "funding_source": e.funding_source or "legacy",
                "balance_before": float(e.balance_before) if e.balance_before is not None else None,
                "balance_after": float(e.balance_after) if e.balance_after is not None else None,
                "voided_at": e.voided_at.isoformat() + "Z" if e.voided_at else None,
                "void_business_date": manila_date(e.voided_at).isoformat() if e.voided_at else None,
                "voided_by": e.voided_by_user.username if e.voided_by_user else None,
                "void_reason": e.void_reason,
                "void_balance_before": float(e.void_balance_before) if e.void_balance_before is not None else None,
                "void_balance_after": float(e.void_balance_after) if e.void_balance_after is not None else None,
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
        amount: Any,
        expense_date: str,
        logged_by: int,
        payment_method: str,
        request_key: str | None = None,
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Select a payment method."}, 400
        if not isinstance(category, str) or not category.strip() or len(category) > 50:
            return {"error": "Enter a valid expense category."}, 400
        if not isinstance(description, str) or not description.strip():
            return {"error": "Enter an expense description."}, 400
        try:
            date_obj = date.fromisoformat(expense_date)
            amount_decimal = Decimal(str(amount))
            if (not amount_decimal.is_finite() or amount_decimal <= 0 or amount_decimal > Decimal("99999999.99")
                    or amount_decimal.as_tuple().exponent < -2):
                raise ValueError
        except (ValueError, TypeError, InvalidOperation):
            return {"error": "Enter a valid date and amount with up to two decimal places."}, 400
        business_day = manila_date(datetime.utcnow())
        try:
            with SalesRepository.method_lock(business_day, payment_method):
                posted_at = datetime.utcnow()
                if manila_date(posted_at) != business_day:
                    return {"error": "The business day changed. Please retry."}, 409
                if request_key and Expense.query.filter_by(request_key=request_key).first():
                    return {"error": "This expense was already recorded."}, 409
                sales = SalesRepository()
                daily = sales.daily_ledger(business_day, business_day).get(business_day)
                before = sales.method_balance(daily, payment_method)
                source = "business" if payment_method == "cash" or before >= amount_decimal else "external"
                after = before - amount_decimal if source == "business" else before
                expense = self.repo.create(
                    category.strip(), description.strip(), amount_decimal, date_obj, logged_by,
                    payment_method, request_key, posted_at=posted_at, funding_source=source,
                    balance_before=before, balance_after=after,
                )
                self.repo.save()
        except TimeoutError as exc:
            return {"error": str(exc)}, 503
        return {"success": True, "data": {"id": expense.id, "funding_source": source}}

    def delete(self, expense_id: int, voided_by: int, reason: str) -> dict[str, Any] | tuple[dict[str, Any], int]:
        if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 255:
            return {"error": "Enter a reason (up to 255 characters)."}, 400
        expense = self.repo.get(expense_id)
        if not expense or expense.voided_at:
            return {"error": "Expense not found or already voided"}, 404
        day = manila_date(datetime.utcnow())
        method = expense.payment_method if expense.payment_method in VALID_PAYMENT_METHODS else "unclassified"
        try:
            with SalesRepository.method_lock(day, method):
                now = datetime.utcnow()
                if manila_date(now) != day:
                    return {"error": "The business day changed. Please retry."}, 409
                db.session.refresh(expense)
                if expense.voided_at:
                    return {"error": "Expense not found or already voided"}, 404
                sales = SalesRepository()
                daily = sales.daily_ledger(day, day).get(day)
                before = sales.method_balance(daily, method)
                after = before + expense.amount if expense.funding_source != "external" else before
                if not self.repo.delete(expense_id, voided_by, reason.strip(), now, before, after):
                    return {"error": "Expense not found or already voided"}, 404
                self.repo.save()
        except TimeoutError as exc:
            return {"error": str(exc)}, 503
        return {"success": True}
