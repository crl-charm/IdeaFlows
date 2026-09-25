from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from app import db
from app.models.expense import Expense


class ExpenseRepository:
    def get(self, expense_id: int) -> Optional[Expense]:
        return Expense.query.filter_by(id=expense_id).first()

    def list_all(self) -> list[Expense]:
        return Expense.query.filter(Expense.voided_at.is_(None)).order_by(Expense.expense_date.desc(), Expense.id.desc()).all()

    def list_history(self) -> list[Expense]:
        return Expense.query.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()

    def list_by_date(self, expense_date: date) -> list[Expense]:
        return Expense.query.filter_by(expense_date=expense_date).filter(Expense.voided_at.is_(None)).order_by(
            Expense.created_at.desc()
        ).all()

    def list_by_category(self, category: str) -> list[Expense]:
        return Expense.query.filter_by(category=category).filter(Expense.voided_at.is_(None)).order_by(
            Expense.expense_date.desc()
        ).all()

    def create(
        self,
        category: str,
        description: str,
        amount: Decimal,
        expense_date: date,
        logged_by: int,
        payment_method: str,
        request_key: str | None = None,
    ) -> Expense:
        expense = Expense(
            category=category,
            description=description,
            amount=amount,
            expense_date=expense_date,
            logged_by=logged_by,
            payment_method=payment_method,
            request_key=request_key,
        )
        db.session.add(expense)
        db.session.flush()
        return expense

    def delete(self, expense_id: int, voided_by: int, reason: str) -> bool:
        expense = self.get(expense_id)
        if not expense or expense.voided_at is not None:
            return False
        expense.voided_at = datetime.utcnow()
        expense.voided_by = voided_by
        expense.void_reason = reason
        return True

    def get_total_by_date(self, expense_date: date) -> Decimal:
        total = db.session.query(db.func.sum(Expense.amount)).filter_by(
            expense_date=expense_date
        ).filter(Expense.voided_at.is_(None)).scalar()
        return Decimal(str(total or 0))

    def save(self) -> None:
        db.session.commit()
