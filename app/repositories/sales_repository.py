from __future__ import annotations

from datetime import date
from contextlib import contextmanager
from threading import RLock
from typing import Optional
from decimal import Decimal

from sqlalchemy import and_, case, func, or_, text
from sqlalchemy.orm import selectinload

from app import db
from app.models import (
    Transaction, DailySalesReport, Order, CustomerSession, Expense,
    SoftBalanceEntry, ReceivablePayment, PayablePayment, FinanceTransaction,
    CheckoutVoidRequest,
)
from app.utils.dates import manila_day_bounds, inclusive_manila_bounds, manila_date
from app.utils.payment import VALID_PAYMENT_METHODS

METHODS = (*sorted(VALID_PAYMENT_METHODS), "unclassified")
_local_funding_lock = RLock()


class SalesRepository:
    @staticmethod
    @contextmanager
    def method_lock(day: date, method: str):
        # Serialize funding decisions for expenses and payables across workers.
        if db.engine.dialect.name != "mysql":
            with _local_funding_lock:
                db.session.rollback()
                yield
            return
        name = f"funding:{day.isoformat()}:{method}"
        with db.engine.connect() as connection:
            if connection.execute(text("SELECT GET_LOCK(:name, 10)"), {"name": name}).scalar() != 1:
                raise TimeoutError("Could not reserve this payment method. Please retry.")
            try:
                # Authentication can open a repeatable-read snapshot before this lock.
                db.session.rollback()
                yield
            finally:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})

    @staticmethod
    def method_balance(daily: dict | None, method: str) -> Decimal:
        if not daily:
            return Decimal("0")
        return sum((
            Decimal(str(daily.get(f"{bucket}_methods", {}).get(method, 0))).quantize(Decimal("0.01")) * sign
            for bucket, sign in (
                ("checkout", 1),
                ("credit_received", 1),
                ("credit_applied", -1),
                ("collection", 1),
                ("adjustment_income", 1),
                ("expense", -1),
                ("payable", -1),
                ("adjustment_expense", -1),
                ("refund", -1),
            )
        ), Decimal("0"))

    def summary_for_range(self, start_date: date, end_date: date):
        start_at, end_at = inclusive_manila_bounds(start_date, end_date)
        time_discount = case(
            (Transaction.discount_item_id.is_(None), Transaction.discount_amount), else_=0
        )
        food_discount = case(
            (Transaction.discount_item_id.is_not(None), Transaction.discount_amount), else_=0
        )
        return (
            Transaction.query.with_entities(
                func.count(Transaction.id).label("transactions"),
                func.coalesce(func.sum(Transaction.total_bill), 0).label("total_revenue"),
                func.coalesce(func.sum(Transaction.time_bill - time_discount), 0).label("space_revenue"),
                func.coalesce(func.sum(Transaction.food_bill - food_discount), 0).label("food_revenue"),
            )
            .filter(Transaction.created_at >= start_at)
            .filter(Transaction.created_at < end_at)
            .filter(or_(
                Transaction.is_voided.is_(False),
                Transaction.void_requests.any(and_(
                    CheckoutVoidRequest.status == "approved",
                    CheckoutVoidRequest.money_treatment == "refund",
                )),
            ))
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
        total_refunds: Decimal = Decimal("0.00"),
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
        if hasattr(report, "total_refunds"):
            report.total_refunds = total_refunds
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
                    "cowork_methods": {m: Decimal("0") for m in METHODS},
                    "cafe_methods": {m: Decimal("0") for m in METHODS},
                    "discount_methods": {m: Decimal("0") for m in METHODS},
                    "cowork_discounts": Decimal("0"),
                    "cafe_discounts": Decimal("0"),
                    "refund_methods": {m: Decimal("0") for m in METHODS},
                    "refund_counts": {m: 0 for m in METHODS},
                    "credit_received_methods": {m: Decimal("0") for m in METHODS},
                    "credit_applied_methods": {m: Decimal("0") for m in METHODS},
                    "collection_methods": {m: Decimal("0") for m in METHODS},
                    "expense_methods": {m: Decimal("0") for m in METHODS},
                    "external_expense_methods": {m: Decimal("0") for m in METHODS},
                    "expense_paid_methods": {m: Decimal("0") for m in METHODS},
                    "expense_void_methods": {m: Decimal("0") for m in METHODS},
                    "payable_methods": {m: Decimal("0") for m in METHODS},
                    "external_payable_methods": {m: Decimal("0") for m in METHODS},
                    "payable_paid_methods": {m: Decimal("0") for m in METHODS},
                    "adjustment_income_methods": {m: Decimal("0") for m in METHODS},
                    "adjustment_expense_methods": {m: Decimal("0") for m in METHODS},
                    "collection_groups": set(), "session_ids": set(), "total_orders": 0,
                }
            return rows[day]

        def method(value: str | None) -> str:
            return value if value in VALID_PAYMENT_METHODS else "unclassified"

        # 1. Transactions & checkouts
        for tx in self._dated(
            Transaction.query.options(
                selectinload(Transaction.session),
                selectinload(Transaction.void_requests),
            ),
            Transaction.created_at, start_date, end_date,
        ).all():
            void_req = tx.active_void_request
            is_approved_void = void_req and void_req.status == "approved"
            treatment = void_req.money_treatment if is_approved_void else None

            # Pending and rejected voids do not alter totals: counted as normal checkouts.
            # Only approved voids alter totals.
            if is_approved_void:
                if treatment == "false_entry":
                    # Removed completely from original business day
                    continue
                elif treatment == "retained_credit":
                    # Sale reversed on original day, but cash remains received as credit liability
                    daily = row(manila_date(tx.created_at))
                    bucket = method(tx.payment_method)
                    daily["credit_received_methods"][bucket] += Decimal(str(tx.total_bill or 0))
                    continue
                elif treatment == "refund":
                    # Sale history preserved on original day; refund event recorded on decision day
                    daily = row(manila_date(tx.created_at))
                    bucket = method(tx.payment_method)
                    daily["checkout_methods"][bucket] += Decimal(str(tx.total_bill or 0))
                    daily["checkout_counts"][bucket] += 1
                    if tx.session and tx.session.service_mode != "food_only":
                        daily["session_ids"].add(tx.session_id)
            else:
                # Normal checkout (including replacement checkouts)
                daily = row(manila_date(tx.created_at))
                bucket = method(tx.payment_method)
                daily["checkout_methods"][bucket] += Decimal(str(tx.total_bill or 0))
                daily["checkout_counts"][bucket] += 1
                if tx.session and tx.session.service_mode != "food_only":
                    daily["session_ids"].add(tx.session_id)

                if getattr(tx, "credit_applied", None) and tx.credit_applied > 0:
                    daily["credit_applied_methods"][bucket] += Decimal(str(tx.credit_applied))
                if getattr(tx, "credit_refunded", None) and tx.credit_refunded > 0:
                    daily["refund_methods"][bucket] += Decimal(str(tx.credit_refunded))
                    daily["refund_counts"][bucket] += 1

            # These are the original checkout bills, not order-placement estimates.
            # Only branches counted as checkout sales reach this point.
            daily["cowork_methods"][bucket] += Decimal(str(tx.time_bill or 0))
            daily["cafe_methods"][bucket] += Decimal(str(tx.food_bill or 0))
            discount = Decimal(str(tx.discount_amount or 0))
            daily["discount_methods"][bucket] += discount
            daily["cafe_discounts" if tx.discount_item_id is not None else "cowork_discounts"] += discount

        # 2. Approved void refunds on their decision business day
        approved_refunds = CheckoutVoidRequest.query.filter(
            CheckoutVoidRequest.status == "approved",
            CheckoutVoidRequest.money_treatment == "refund",
            CheckoutVoidRequest.refund_amount > 0,
        )
        if start_date:
            approved_refunds = approved_refunds.filter(CheckoutVoidRequest.decided_at >= manila_day_bounds(start_date)[0])
        if end_date:
            approved_refunds = approved_refunds.filter(CheckoutVoidRequest.decided_at < manila_day_bounds(end_date)[1])

        for req in approved_refunds.all():
            dec_day = req.decision_business_date or manila_date(req.decided_at)
            if (not start_date or dec_day >= start_date) and (not end_date or dec_day <= end_date):
                daily = row(dec_day)
                bucket = method(req.original_payment_method)
                daily["refund_methods"][bucket] += Decimal(str(req.refund_amount))
                daily["refund_counts"][bucket] += 1

        for payment in self._dated(ReceivablePayment.query, ReceivablePayment.received_at, start_date, end_date).all():
            daily = row(manila_date(payment.received_at))
            daily["collection_methods"][method(payment.payment_method)] += Decimal(str(payment.amount))
            daily["collection_groups"].add(payment.payment_group_id or f"single-{payment.id}")

        expenses = Expense.query
        posted = [Expense.funding_source.is_not(None)]
        legacy = [Expense.funding_source.is_(None)]
        reversed_on = [Expense.void_balance_before.is_not(None)]
        if start_date:
            start_at = manila_day_bounds(start_date)[0]
            posted.append(Expense.created_at >= start_at)
            legacy.append(Expense.expense_date >= start_date)
            reversed_on.append(Expense.voided_at >= start_at)
        if end_date:
            end_at = manila_day_bounds(end_date)[1]
            posted.append(Expense.created_at < end_at)
            legacy.append(Expense.expense_date <= end_date)
            reversed_on.append(Expense.voided_at < end_at)
        expenses = expenses.filter(or_(and_(*posted), and_(*legacy), and_(*reversed_on)))
        for expense in expenses.all():
            bucket = method(expense.payment_method)
            amount = Decimal(str(expense.amount))
            posted_day = manila_date(expense.created_at) if expense.funding_source else expense.expense_date
            if ((not start_date or posted_day >= start_date) and (not end_date or posted_day <= end_date)
                    and (expense.funding_source or not expense.voided_at or expense.void_balance_before is not None)):
                daily = row(posted_day)
                daily["expense_paid_methods"][bucket] += amount
                target = "external_expense_methods" if expense.funding_source == "external" else "expense_methods"
                daily[target][bucket] += amount
            if expense.voided_at and expense.void_balance_before is not None:
                void_day = manila_date(expense.voided_at)
                if (not start_date or void_day >= start_date) and (not end_date or void_day <= end_date):
                    daily = row(void_day)
                    daily["expense_void_methods"][bucket] += amount
                    target = "external_expense_methods" if expense.funding_source == "external" else "expense_methods"
                    daily[target][bucket] -= amount

        for payment in self._dated(PayablePayment.query, PayablePayment.paid_at, start_date, end_date).all():
            daily = row(manila_date(payment.paid_at))
            bucket = method(payment.payment_method)
            amount = Decimal(str(payment.amount))
            daily["payable_paid_methods"][bucket] += amount
            target = "external_payable_methods" if payment.funding_source == "external" else "payable_methods"
            daily[target][bucket] += amount

        for adjustment in self._dated(FinanceTransaction.query, FinanceTransaction.created_at, start_date, end_date).all():
            if adjustment._type in {"income", "expense"}:
                bucket = "adjustment_income_methods" if adjustment._type == "income" else "adjustment_expense_methods"
                row(manila_date(adjustment.created_at))[bucket][method(adjustment.payment_method)] += Decimal(str(adjustment._amount))

        for order in self._dated(Order.query, Order.created_at, start_date, end_date).all():
            row(manila_date(order.created_at))["total_orders"] += 1

        result = {}
        for day, daily in rows.items():
            checkout = daily["checkout_methods"]
            refund = daily["refund_methods"]
            credit_received = daily["credit_received_methods"]
            credit_applied = daily["credit_applied_methods"]
            collection = daily["collection_methods"]
            expense = daily["expense_methods"]
            external_expense = daily["external_expense_methods"]
            payable = daily["payable_methods"]
            external_payable = daily["external_payable_methods"]
            other_income = daily["adjustment_income_methods"]
            budget_spend = daily["adjustment_expense_methods"]

            tot_rev = float(sum(checkout.values()))
            cowork = daily["cowork_methods"]
            cafe = daily["cafe_methods"]
            discounts = daily["discount_methods"]
            tot_ref = float(sum(refund.values()))
            net_bal = float(
                sum(checkout.values()) - sum(credit_applied.values()) + sum(credit_received.values())
                + sum(collection.values()) + sum(other_income.values())
                - sum(expense.values()) - sum(payable.values()) - sum(budget_spend.values()) - sum(refund.values())
            )
            cash_hand = float(
                checkout["cash"] - credit_applied["cash"] + credit_received["cash"]
                + collection["cash"] + other_income["cash"]
                - expense["cash"] - payable["cash"] - budget_spend["cash"] - refund["cash"]
            )

            result[day] = {
                "report_date": day.isoformat(),
                "total_revenue": tot_rev,
                "cowork_bill": float(sum(cowork.values())),
                "cafe_bill": float(sum(cafe.values())),
                "discounts_total": float(sum(discounts.values())),
                "cowork_discounts": float(daily["cowork_discounts"]),
                "cafe_discounts": float(daily["cafe_discounts"]),
                "sales_reconciliation_difference": float(sum(
                    abs(checkout[m] - cowork[m] - cafe[m] + discounts[m]) for m in METHODS
                )),
                "total_refunds": tot_ref,
                "net_revenue": tot_rev - tot_ref,
                "total_collections": float(sum(collection.values())),
                "total_expenses": float(sum(expense.values()) + sum(external_expense.values())),
                "total_business_expenses": float(sum(expense.values())),
                "total_external_expenses": float(sum(external_expense.values())),
                "total_payables_paid": float(sum(payable.values()) + sum(external_payable.values())),
                "total_business_payables_paid": float(sum(payable.values())),
                "total_external_payables_paid": float(sum(external_payable.values())),
                "total_other_income": float(sum(other_income.values())),
                "total_budget_spend": float(sum(budget_spend.values())),
                "net_balance": net_bal,
                "cash_on_hand": cash_hand,
                "collection_count": len(daily["collection_groups"]),
                "total_orders": daily["total_orders"],
                "total_sessions": len(daily["session_ids"]),
                "checkout_methods": {m: float(v) for m, v in checkout.items()},
                "cowork_methods": {m: float(v) for m, v in cowork.items()},
                "cafe_methods": {m: float(v) for m, v in cafe.items()},
                "discount_methods": {m: float(v) for m, v in discounts.items()},
                "refund_methods": {m: float(v) for m, v in refund.items()},
                "refund_counts": {m: daily["refund_counts"][m] for m in METHODS},
                "credit_received_methods": {m: float(v) for m, v in credit_received.items()},
                "credit_applied_methods": {m: float(v) for m, v in credit_applied.items()},
                "collection_methods": {m: float(v) for m, v in collection.items()},
                "expense_methods": {m: float(v) for m, v in expense.items()},
                "external_expense_methods": {m: float(v) for m, v in external_expense.items()},
                "expense_paid_methods": {m: float(v) for m, v in daily["expense_paid_methods"].items()},
                "expense_void_methods": {m: float(v) for m, v in daily["expense_void_methods"].items()},
                "payable_methods": {m: float(v) for m, v in payable.items()},
                "external_payable_methods": {m: float(v) for m, v in external_payable.items()},
                "payable_paid_methods": {m: float(v) for m, v in daily["payable_paid_methods"].items()},
                "adjustment_income_methods": {m: float(v) for m, v in other_income.items()},
                "adjustment_expense_methods": {m: float(v) for m, v in budget_spend.items()},
                **{f"{m}_total": float(checkout[m]) for m in METHODS},
                **{f"{m}_count": daily["checkout_counts"][m] for m in METHODS},
                **{f"{m}_refund": float(refund[m]) for m in METHODS},
            }
        return result

    @staticmethod
    def daily_ledger_empty(day: date) -> dict:
        return {
            "report_date": day.isoformat(), "total_revenue": 0.0,
            "cowork_bill": 0.0, "cafe_bill": 0.0, "discounts_total": 0.0,
            "cowork_discounts": 0.0, "cafe_discounts": 0.0,
            "sales_reconciliation_difference": 0.0,
            "total_refunds": 0.0, "net_revenue": 0.0,
            "total_collections": 0.0, "total_expenses": 0.0,
            "total_payables_paid": 0.0, "net_balance": 0.0,
            "total_other_income": 0.0, "total_budget_spend": 0.0,
            "total_business_expenses": 0.0, "total_external_expenses": 0.0,
            "total_business_payables_paid": 0.0, "total_external_payables_paid": 0.0,
            "cash_on_hand": 0.0, "collection_count": 0,
            "total_orders": 0, "total_sessions": 0,
            **{f"{m}_total": 0.0 for m in METHODS},
            **{f"{m}_count": 0 for m in METHODS},
            **{f"{m}_refund": 0.0 for m in METHODS},
            **{f"{bucket}_methods": {m: 0.0 for m in METHODS}
               for bucket in ("checkout", "cowork", "cafe", "discount", "collection", "expense", "external_expense", "expense_paid",
                              "expense_void", "payable", "external_payable", "payable_paid",
                              "adjustment_income", "adjustment_expense", "refund",
                              "credit_received", "credit_applied")},
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
        total_refunds: Decimal = Decimal("0.00"),
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
        if hasattr(entry, "total_refunds"):
            entry.total_refunds = total_refunds
        db.session.add(entry)
        db.session.flush()
        return entry
