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
from app.services.cash_box_service import CashBoxService, BOXES
from app.models.payable import Payable
from app.models import User
from app.utils.expense_categories import EXPENSE_CATEGORIES, expense_category
from app.utils.dates import month_bounds
from sqlalchemy import or_


@dataclass(frozen=True)
class ExpenseService:
    repo: ExpenseRepository

    @staticmethod
    def _serialize(expenses, *, salary_details=True) -> list[dict[str, Any]]:
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
                "cash_box": e.cash_box,
                "box_balance_before": float(e.box_balance_before) if e.box_balance_before is not None else None,
                "box_balance_after": float(e.box_balance_after) if e.box_balance_after is not None else None,
                "repay_owner": e.repay_owner,
                "balance_before": float(e.balance_before) if e.balance_before is not None else None,
                "balance_after": float(e.balance_after) if e.balance_after is not None else None,
                "voided_at": e.voided_at.isoformat() + "Z" if e.voided_at else None,
                "void_business_date": manila_date(e.voided_at).isoformat() if e.voided_at else None,
                "voided_by": e.voided_by_user.username if e.voided_by_user else None,
                "void_reason": e.void_reason,
                "void_balance_before": float(e.void_balance_before) if e.void_balance_before is not None else None,
                "void_balance_after": float(e.void_balance_after) if e.void_balance_after is not None else None,
                "void_box_balance_before": float(e.void_box_balance_before) if e.void_box_balance_before is not None else None,
                "void_box_balance_after": float(e.void_box_balance_after) if e.void_box_balance_after is not None else None,
                **({"is_salary": e.is_salary, "salary_employee_id": e.salary_employee_id,
                    "salary_employee_name": e.salary_employee_name,
                    "salary_month": e.salary_month.strftime("%Y-%m") if e.salary_month else None,
                    "salary_original_category": e.salary_original_category,
                    "salary_assigned_at": e.salary_assigned_at.isoformat() + "Z" if e.salary_assigned_at else None,
                    "salary_assigned_by": e.salary_assigned_by} if salary_details else {}),
            }
            for e in expenses
        ]

    def list_all(self, *, include_salary=True) -> list[dict[str, Any]]:
        return self._serialize(self.repo.list_all(include_salary=include_salary), salary_details=include_salary)

    def list_history(self, *, include_salary=True) -> list[dict[str, Any]]:
        return self._serialize(self.repo.list_history(include_salary=include_salary), salary_details=include_salary)

    def list_by_date(self, expense_date: str, *, include_salary=True) -> list[dict[str, Any]]:
        date_obj = date.fromisoformat(expense_date)
        return self._serialize(self.repo.list_by_date(date_obj, include_salary=include_salary), salary_details=include_salary)

    @staticmethod
    def salary_employees():
        return User.query.filter(or_(User.role == "staff", User.manual_shifts.any())).order_by(User.full_name, User.id).all()

    @staticmethod
    def salary_metadata(employee_id, month, actor_id, actor_role):
        actor = db.session.get(User, actor_id)
        if actor_role != "admin" or not actor or actor.role != "admin":
            raise PermissionError("Only admins can record or change salary details.")
        if isinstance(employee_id, bool) or not str(employee_id).isdigit() or not 1 <= int(employee_id) <= 2147483647:
            raise ValueError("Choose an employee for this salary.")
        employee = User.query.filter(User.id == int(employee_id), or_(User.role == "staff", User.manual_shifts.any())).first()
        if not employee:
            raise ValueError("Choose an existing employee; inactive/former staff with history are available too.")
        start, _ = month_bounds(month)
        return {"salary_employee_id": employee.id, "salary_employee_name": employee.full_name or employee.username,
                "salary_month": start}

    def classify_salary(self, expense_id, employee_id, month, actor_id):
        metadata = self.salary_metadata(employee_id, month, actor_id, "admin")
        expense = Expense.query.filter_by(id=expense_id).with_for_update().first()
        if not expense or expense.voided_at:
            raise ValueError("Choose an active expense to classify.")
        if not expense.is_salary:
            raise ValueError("Only existing salary records can receive salary details.")
        if any((expense.salary_month, expense.salary_employee_id, expense.salary_employee_name)):
            raise ValueError("Salary details already exist. Use the audited void/correction flow for a mistake.")
        expense.salary_original_category = expense.category
        expense.salary_assigned_at = datetime.utcnow()
        expense.salary_assigned_by = actor_id
        expense.category = "salaries"
        for key, value in metadata.items():
            setattr(expense, key, value)
        self.repo.save()
        return {"success": True}

    def create(
        self,
        category: str,
        description: str,
        amount: Any,
        expense_date: str,
        logged_by: int,
        payment_method: str,
        request_key: str | None = None,
        cash_box: str | None = None,
        repay_owner: bool | None = None,
        actor_role: str = "staff",
        salary_employee_id: int | None = None,
        salary_month: str | None = None,
    ) -> dict[str, Any] | tuple[dict[str, Any], int]:
        category = expense_category(category)
        if category not in EXPENSE_CATEGORIES:
            return {"error": "Choose a valid expense category."}, 400
        metadata = {}
        if category == "salaries":
            try:
                metadata = self.salary_metadata(salary_employee_id, salary_month, logged_by, actor_role)
            except PermissionError as exc:
                return {"error": str(exc)}, 403
            except ValueError as exc:
                return {"error": str(exc)}, 400
        elif salary_employee_id is not None or salary_month is not None:
            return {"error": "Salary details apply only to Salaries."}, 400
        if category == "salaries" and (description is None or isinstance(description, str) and not description.strip()):
            description = f"Salary payment: {metadata['salary_employee_name']} / {metadata['salary_month']:%Y-%m}"
        if not isinstance(payment_method, str) or payment_method not in VALID_PAYMENT_METHODS:
            return {"error": "Select a payment method."}, 400
        if payment_method == "cash":
            if cash_box not in (*BOXES, "owner") and not (cash_box is None and CashBoxService.opening_date() is None):
                return {"error": "Choose Petty cash, Customer cash, or Owner paid directly."}, 400
            if cash_box == "owner" and not isinstance(repay_owner, bool):
                return {"error": "Choose whether the owner must be repaid."}, 400
        elif cash_box or repay_owner:
            return {"error": "Cash box applies only to cash expenses."}, 400
        if not isinstance(category, str) or not category.strip() or len(category) > 50:
            return {"error": "Enter a valid expense category."}, 400
        if not isinstance(description, str) or not description.strip():
            return {"error": "Enter an expense description."}, 400
        try:
            date_obj = date.fromisoformat(expense_date)
            if category == "salaries" and date_obj > manila_date(datetime.utcnow()):
                return {"error": "A salary payment date cannot be in the future."}, 400
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
                source = ("external" if cash_box == "owner" else "business") if payment_method == "cash" else ("business" if before >= amount_decimal else "external")
                after = before - amount_decimal if source == "business" else before
                box_before = None
                if payment_method == "cash" and cash_box in BOXES:
                    try:
                        box_before = CashBoxService.balance(cash_box, business_day)
                    except ValueError as exc:
                        return {"error": str(exc)}, 400
                expense = self.repo.create(
                    category.strip(), description.strip(), amount_decimal, date_obj, logged_by,
                    payment_method, request_key, posted_at=posted_at, funding_source=source,
                    balance_before=before, balance_after=after,
                    cash_box=cash_box if cash_box in BOXES else None,
                    box_balance_before=box_before,
                    box_balance_after=box_before - amount_decimal if box_before is not None else None,
                    repay_owner=bool(repay_owner) if cash_box == "owner" else False,
                    **metadata,
                )
                if expense.repay_owner:
                    CashBoxService.owner_payable(amount_decimal, logged_by, business_day, expense=expense)
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
                owner_debt = Payable.query.filter_by(owner_expense_id=expense.id).with_for_update().first()
                if owner_debt and owner_debt.partial_paid:
                    return {"error": "Owner repayment already began. Correct its payments before voiding this expense."}, 409
                sales = SalesRepository()
                daily = sales.daily_ledger(day, day).get(day)
                before = sales.method_balance(daily, method)
                after = before + expense.amount if expense.funding_source != "external" else before
                box_before = CashBoxService.balance(expense.cash_box, day) if expense.cash_box else None
                if not self.repo.delete(expense_id, voided_by, reason.strip(), now, before, after):
                    return {"error": "Expense not found or already voided"}, 404
                if box_before is not None:
                    expense.void_box_balance_before = box_before
                    expense.void_box_balance_after = box_before + expense.amount
                if owner_debt:
                    owner_debt.cancelled_at = now
                    owner_debt.cancelled_by = voided_by
                    owner_debt.cancel_reason = reason.strip()
                self.repo.save()
        except TimeoutError as exc:
            return {"error": str(exc)}, 503
        return {"success": True}
