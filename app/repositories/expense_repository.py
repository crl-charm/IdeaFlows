from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from decimal import Decimal

from app import db
from app.models.expense import Expense
from sqlalchemy.orm import selectinload


class ExpenseRepository:
    def get(self, expense_id: int) -> Optional[Expense]:
        return Expense.query.filter_by(id=expense_id).first()

    @staticmethod
    def visible(include_salary=True):
        query = Expense.query.options(selectinload(Expense.logged_by_user), selectinload(Expense.voided_by_user))
        return query if include_salary else query.filter(~Expense.is_salary)

    def list_all(self, *, include_salary=True) -> list[Expense]:
        return self.visible(include_salary).filter(Expense.voided_at.is_(None)).order_by(Expense.expense_date.desc(), Expense.id.desc()).all()

    def list_history(self, *, include_salary=True) -> list[Expense]:
        return self.visible(include_salary).order_by(Expense.created_at.desc(), Expense.id.desc()).all()

    def list_by_date(self, expense_date: date, *, include_salary=True) -> list[Expense]:
        return self.visible(include_salary).filter_by(expense_date=expense_date).filter(Expense.voided_at.is_(None)).order_by(
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
        *,
        posted_at: datetime,
        funding_source: str,
        balance_before: Decimal,
        balance_after: Decimal,
        cash_box: str | None = None,
        box_balance_before: Decimal | None = None,
        box_balance_after: Decimal | None = None,
        repay_owner: bool = False,
        salary_employee_id: int | None = None,
        salary_employee_name: str | None = None,
        salary_month: date | None = None,
    ) -> Expense:
        expense = Expense(
            category=category,
            description=description,
            amount=amount,
            expense_date=expense_date,
            logged_by=logged_by,
            payment_method=payment_method,
            funding_source=funding_source,
            balance_before=balance_before,
            balance_after=balance_after,
            cash_box=cash_box,
            box_balance_before=box_balance_before,
            box_balance_after=box_balance_after,
            repay_owner=repay_owner,
            created_at=posted_at,
            request_key=request_key,
            salary_employee_id=salary_employee_id,
            salary_employee_name=salary_employee_name,
            salary_month=salary_month,
        )
        db.session.add(expense)
        db.session.flush()
        return expense

    def delete(self, expense_id: int, voided_by: int, reason: str, voided_at: datetime,
               balance_before: Decimal, balance_after: Decimal) -> bool:
        expense = self.get(expense_id)
        if not expense or expense.voided_at is not None:
            return False
        expense.voided_at = voided_at
        expense.voided_by = voided_by
        expense.void_reason = reason
        expense.void_balance_before = balance_before
        expense.void_balance_after = balance_after
        return True

    def get_total_by_date(self, expense_date: date) -> Decimal:
        total = db.session.query(db.func.sum(Expense.amount)).filter_by(
            expense_date=expense_date
        ).filter(Expense.voided_at.is_(None)).scalar()
        return Decimal(str(total or 0))

    def save(self) -> None:
        db.session.commit()
