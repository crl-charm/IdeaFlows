from __future__ import annotations

from datetime import date
from typing import Optional
from decimal import Decimal

from sqlalchemy import func

from app import db
from app.models import (
    Transaction, DailySalesReport, Order, CustomerSession, Expense,
    SoftBalanceEntry, ReceivablePayment, PayablePayment, FinanceTransaction,
)
from app.utils.dates import manila_day_bounds, inclusive_manila_bounds, manila_date
from app.utils.payment import VALID_PAYMENT_METHODS

METHODS = (*sorted(VALID_PAYMENT_METHODS), "unclassified")


class SalesRepository:
    def summary_for_range(self, start_date: date, end_date: date):
        start_at, end_at = inclusive_manila_bounds(start_date, end_date)
        return (
            Transaction.query.with_entities(
                func.count(Transaction.id).label("transactions"),
                func.coalesce(func.sum(Transaction.total_bill), 0).label("total_revenue"),
                func.coalesce(func.sum(Transaction.time_bill), 0).label("space_revenue"),
                func.coalesce(func.sum(Transaction.food_bill), 0).label("food_revenue"),
            )
            .filter(Transaction.created_at >= start_at)
            .filter(Transaction.created_at < end_at)
            .first()
        )

    def summary_for_day(self, target_date: date):
        return self.summary_for_range(target_date, target_date)

    def get_daily_report(self, report_date: date) -> Optional[DailySalesReport]:
        return DailySalesReport.query.filter_by(report_date=report_date).first()

    def list_reports(self) -> list[DailySalesReport]:
        return DailySalesReport.query.order_by(DailySalesReport.report_date.desc()).all()

    def create_report(
        self,
        report_date: date,
        total_revenue: Decimal,
        total_expenses: Decimal,
        total_collections: Decimal,
        total_payables_paid: Decimal,
        total_other_income: Decimal,
        total_budget_spend: Decimal,
        net_balance: Decimal,
        total_orders: int,
        total_sessions: int,
        generated_by: int,
        notes: Optional[str],
    ) -> DailySalesReport:
        report = DailySalesReport(
            report_date=report_date,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            total_collections=total_collections,
            total_payables_paid=total_payables_paid,
            total_other_income=total_other_income,
            total_budget_spend=total_budget_spend,
            net_balance=net_balance,
            total_orders=total_orders,
            total_sessions=total_sessions,
            generated_by=generated_by,
            notes=notes,
        )
        db.session.add(report)
        db.session.flush()
        return report

    @staticmethod
    def _dated(query, column, start_date: date | None, end_date: date | None):
        if start_date:
            query = query.filter(column >= manila_day_bounds(start_date)[0])
        if end_date:
            query = query.filter(column < manila_day_bounds(end_date)[1])
        return query

    def daily_ledger(self, start_date: date | None = None, end_date: date | None = None) -> dict[date, dict]:
        """One source for sales, collections, outflows and payment methods."""
        rows: dict[date, dict] = {}

        def row(day: date) -> dict:
            if day not in rows:
                rows[day] = {
                    "checkout_methods": {m: Decimal("0") for m in METHODS},
                    "checkout_counts": {m: 0 for m in METHODS},
                    "collection_methods": {m: Decimal("0") for m in METHODS},
                    "expense_methods": {m: Decimal("0") for m in METHODS},
                    "payable_methods": {m: Decimal("0") for m in METHODS},
                    "adjustment_income_methods": {m: Decimal("0") for m in METHODS},
                    "adjustment_expense_methods": {m: Decimal("0") for m in METHODS},
                    "collection_groups": set(), "session_ids": set(), "total_orders": 0,
                }
            return rows[day]

        def method(value: str | None) -> str:
            return value if value in VALID_PAYMENT_METHODS else "unclassified"

        for tx in self._dated(Transaction.query, Transaction.created_at, start_date, end_date).all():
            daily = row(manila_date(tx.created_at))
            bucket = method(tx.payment_method)
            daily["checkout_methods"][bucket] += Decimal(str(tx.total_bill or 0))
            daily["checkout_counts"][bucket] += 1
            daily["session_ids"].add(tx.session_id)

        for payment in self._dated(ReceivablePayment.query, ReceivablePayment.received_at, start_date, end_date).all():
            daily = row(manila_date(payment.received_at))
            daily["collection_methods"][method(payment.payment_method)] += Decimal(str(payment.amount))
            daily["collection_groups"].add(payment.payment_group_id or f"single-{payment.id}")

        expenses = Expense.query.filter(Expense.voided_at.is_(None))
        if start_date:
            expenses = expenses.filter(Expense.expense_date >= start_date)
        if end_date:
            expenses = expenses.filter(Expense.expense_date <= end_date)
        for expense in expenses.all():
            row(expense.expense_date)["expense_methods"][method(expense.payment_method)] += Decimal(str(expense.amount))

        for payment in self._dated(PayablePayment.query, PayablePayment.paid_at, start_date, end_date).all():
            row(manila_date(payment.paid_at))["payable_methods"][method(payment.payment_method)] += Decimal(str(payment.amount))

        for adjustment in self._dated(FinanceTransaction.query, FinanceTransaction.created_at, start_date, end_date).all():
            if adjustment._type in {"income", "expense"}:
                bucket = "adjustment_income_methods" if adjustment._type == "income" else "adjustment_expense_methods"
                row(manila_date(adjustment.created_at))[bucket][method(adjustment.payment_method)] += Decimal(str(adjustment._amount))

        for order in self._dated(Order.query, Order.created_at, start_date, end_date).all():
            row(manila_date(order.created_at))["total_orders"] += 1

        result = {}
        for day, daily in rows.items():
            checkout = daily["checkout_methods"]
            collection = daily["collection_methods"]
            expense = daily["expense_methods"]
            payable = daily["payable_methods"]
            other_income = daily["adjustment_income_methods"]
            budget_spend = daily["adjustment_expense_methods"]
            result[day] = {
                "report_date": day.isoformat(),
                "total_revenue": float(sum(checkout.values())),
                "total_collections": float(sum(collection.values())),
                "total_expenses": float(sum(expense.values())),
                "total_payables_paid": float(sum(payable.values())),
                "total_other_income": float(sum(other_income.values())),
                "total_budget_spend": float(sum(budget_spend.values())),
                "net_balance": float(sum(checkout.values()) + sum(collection.values()) + sum(other_income.values()) - sum(expense.values()) - sum(payable.values()) - sum(budget_spend.values())),
                "cash_on_hand": float(checkout["cash"] + collection["cash"] + other_income["cash"] - expense["cash"] - payable["cash"] - budget_spend["cash"]),
                "collection_count": len(daily["collection_groups"]),
                "total_orders": daily["total_orders"],
                "total_sessions": len(daily["session_ids"]),
                "checkout_methods": {m: float(v) for m, v in checkout.items()},
                "collection_methods": {m: float(v) for m, v in collection.items()},
                "expense_methods": {m: float(v) for m, v in expense.items()},
                "payable_methods": {m: float(v) for m, v in payable.items()},
                "adjustment_income_methods": {m: float(v) for m, v in other_income.items()},
                "adjustment_expense_methods": {m: float(v) for m, v in budget_spend.items()},
                **{f"{m}_total": float(checkout[m]) for m in METHODS},
                **{f"{m}_count": daily["checkout_counts"][m] for m in METHODS},
            }
        return result

    @staticmethod
    def daily_ledger_empty(day: date) -> dict:
        return {
            "report_date": day.isoformat(), "total_revenue": 0.0,
            "total_collections": 0.0, "total_expenses": 0.0,
            "total_payables_paid": 0.0, "net_balance": 0.0,
            "total_other_income": 0.0, "total_budget_spend": 0.0,
            "cash_on_hand": 0.0, "collection_count": 0,
            "total_orders": 0, "total_sessions": 0,
            **{f"{m}_total": 0.0 for m in METHODS},
            **{f"{m}_count": 0 for m in METHODS},
            **{f"{bucket}_methods": {m: 0.0 for m in METHODS}
               for bucket in ("checkout", "collection", "expense", "payable", "adjustment_income", "adjustment_expense")},
        }

    def payment_totals_by_dates(self, dates: list[date]) -> dict[date, dict[str, float | int]]:
        if not dates:
            return {}
        ledger = self.daily_ledger(min(dates), max(dates))
        return {day: {f"{method}_{kind}": ledger.get(day, {}).get(f"{method}_{kind}", 0)
                      for method in METHODS for kind in ("total", "count")} for day in dates}

    def get_daily_transactions(self, report_date: date) -> list[Transaction]:
        start_at, end_at = manila_day_bounds(report_date)
        return (
            Transaction.query.filter(
                Transaction.created_at >= start_at,
                Transaction.created_at < end_at,
            )
            .order_by(Transaction.created_at)
            .all()
        )

    def get_daily_orders(self, report_date: date) -> list[Order]:
        start_at, end_at = manila_day_bounds(report_date)
        return (
            Order.query.filter(Order.created_at >= start_at, Order.created_at < end_at)
            .all()
        )

    def get_daily_sessions(self, report_date: date) -> list[CustomerSession]:
        start_at, end_at = manila_day_bounds(report_date)
        return (
            CustomerSession.query.filter(
                CustomerSession.time_in >= start_at,
                CustomerSession.time_in < end_at,
            )
            .all()
        )

    def save(self) -> None:
        db.session.commit()

    def sum_expenses_for_day(self, target_date: date) -> Decimal:
        value = (
            db.session.query(func.coalesce(func.sum(Expense.amount), 0))
            .filter(Expense.expense_date == target_date)
            .filter(Expense.voided_at.is_(None))
            .scalar()
        )
        return Decimal(str(value or 0))

    def list_soft_balances(self) -> list[SoftBalanceEntry]:
        return SoftBalanceEntry.query.order_by(SoftBalanceEntry.balance_date.desc(), SoftBalanceEntry.period.asc()).all()

    def create_soft_balance(
        self,
        balance_date: date,
        period: str,
        total_revenue: Decimal,
        total_expenses: Decimal,
        total_collections: Decimal,
        total_payables_paid: Decimal,
        total_other_income: Decimal,
        total_budget_spend: Decimal,
        net_balance: Decimal,
        generated_by: int,
        notes: Optional[str],
    ) -> SoftBalanceEntry:
        entry = SoftBalanceEntry(
            balance_date=balance_date,
            period=period,
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            total_collections=total_collections,
            total_payables_paid=total_payables_paid,
            total_other_income=total_other_income,
            total_budget_spend=total_budget_spend,
            net_balance=net_balance,
            generated_by=generated_by,
            notes=notes,
        )
        db.session.add(entry)
        db.session.flush()
        return entry
