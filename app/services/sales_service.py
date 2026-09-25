from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

from app.core.interfaces import Clock
from app.repositories.sales_repository import SalesRepository


@dataclass(frozen=True)
class SalesService:
    repo: SalesRepository
    clock: Clock = None

    @staticmethod
    def _shape(summary_row: Any) -> dict[str, Any]:
        return {
            "transactions": int(summary_row.transactions or 0),
            "total_revenue": float(summary_row.total_revenue or 0),
            "space_revenue": float(summary_row.space_revenue or 0),
            "food_revenue": float(summary_row.food_revenue or 0),
        }

    def daily_sales(self) -> dict[str, Any]:
        today = self.clock.now().date()
        return {"date": str(today), **self._shape(self.repo.summary_for_day(today))}

    def sales_summary(self, period: str) -> dict[str, Any]:
        today = self.clock.now().date()
        if period == "yesterday":
            start_date = today - timedelta(days=1)
            end_date = start_date
        elif period == "7days":
            start_date = today - timedelta(days=6)
            end_date = today
        elif period == "1month":
            start_date = today - timedelta(days=29)
            end_date = today
        else:
            period = "today"
            start_date = today
            end_date = today
        return {
            "period": period,
            "start_date": str(start_date),
            "end_date": str(end_date),
            **self._shape(self.repo.summary_for_range(start_date, end_date)),
        }

    def sales_compare(self) -> dict[str, Any]:
        today = self.clock.now().date()
        yesterday = today - timedelta(days=1)
        return {
            "today": self._shape(self.repo.summary_for_day(today)),
            "yesterday": self._shape(self.repo.summary_for_day(yesterday)),
            "last_7_days": self._shape(self.repo.summary_for_range(today - timedelta(days=6), today)),
            "last_30_days": self._shape(self.repo.summary_for_range(today - timedelta(days=29), today)),
        }

    def list_reports(self) -> list[dict[str, Any]]:
        reports = self.repo.list_reports()
        report_dates = [r.report_date for r in reports]
        payments = self.repo.payment_totals_by_dates(report_dates)
        shaped: list[dict[str, Any]] = []
        for r in reports:
            pay = payments.get(r.report_date, {})
            shaped.append(
                {
                    "id": r.id,
                    "report_date": r.report_date.strftime("%Y-%m-%d"),
                    "total_revenue": float(r.total_revenue),
                    "total_expenses": float(r.total_expenses),
                    "net_balance": float(r.net_balance),
                    "total_orders": r.total_orders,
                    "total_sessions": r.total_sessions,
                    "generated_by": r.generated_by_user.username if r.generated_by_user else "Unknown",
                    "notes": r.notes,
                    "cash_total": float(pay.get("cash_total", 0)),
                    "gcash_total": float(pay.get("gcash_total", 0)),
                    "bdo_total": float(pay.get("bdo_total", 0)),
                    "bpi_total": float(pay.get("bpi_total", 0)),
                    "queenbank_total": float(pay.get("queenbank_total", 0)),
                    "cash_count": int(pay.get("cash_count", 0)),
                    "gcash_count": int(pay.get("gcash_count", 0)),
                    "bdo_count": int(pay.get("bdo_count", 0)),
                    "bpi_count": int(pay.get("bpi_count", 0)),
                    "queenbank_count": int(pay.get("queenbank_count", 0)),
                }
            )
        return shaped

    def list_soft_balances(self) -> list[dict[str, Any]]:
        entries = self.repo.list_soft_balances()
        return [
            {
                "id": row.id,
                "balance_date": row.balance_date.strftime("%Y-%m-%d"),
                "period": row.period,
                "total_revenue": float(row.total_revenue or 0),
                "total_expenses": float(row.total_expenses or 0),
                "net_balance": float(row.net_balance or 0),
                "generated_by": row.generated_by_user.username if row.generated_by_user else "Unknown",
                "notes": row.notes,
                "generated_at": row.generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            }
            for row in entries
        ]

    def generate_report(
        self,
        report_date: date,
        generated_by: int,
        notes: Optional[str],
    ) -> dict[str, Any]:
        transactions = self.repo.get_daily_transactions(report_date)
        orders = self.repo.get_daily_orders(report_date)
        sessions = self.repo.get_daily_sessions(report_date)

        total_revenue = Decimal("0")
        for tx in transactions:
            if tx.total_bill:
                total_revenue += Decimal(str(tx.total_bill))

        total_expenses = self.repo.sum_expenses_for_day(report_date)

        net_balance = total_revenue - total_expenses

        existing = self.repo.get_daily_report(report_date)
        if existing:
            existing.total_revenue = total_revenue
            existing.total_expenses = total_expenses
            existing.net_balance = net_balance
            existing.total_orders = len(orders)
            existing.total_sessions = len(sessions)
            existing.generated_by = generated_by
            existing.notes = notes
            report = existing
        else:
            report = self.repo.create_report(
                report_date=report_date,
                total_revenue=total_revenue,
                total_expenses=total_expenses,
                net_balance=net_balance,
                total_orders=len(orders),
                total_sessions=len(sessions),
                generated_by=generated_by,
                notes=notes,
            )
        self.repo.save()

        from app.core.socketio_handlers import emit_daily_sales_closed

        emit_daily_sales_closed({
            "report_date": report_date.strftime("%Y-%m-%d"),
            "total_revenue": float(total_revenue),
            "net_balance": float(net_balance),
        })

        return {
            "success": True,
            "data": {
                "id": report.id,
                "report_date": report_date.strftime("%Y-%m-%d"),
                "total_revenue": float(total_revenue),
                "total_expenses": float(total_expenses),
                "net_balance": float(net_balance),
            },
        }

    def create_soft_balance(
        self,
        balance_date: date,
        period: str,
        generated_by: int,
        notes: Optional[str],
    ) -> dict[str, Any]:
        transactions = self.repo.get_daily_transactions(balance_date)
        total_revenue = sum(Decimal(str(tx.total_bill or 0)) for tx in transactions)
        total_expenses = self.repo.sum_expenses_for_day(balance_date)
        net_balance = total_revenue - total_expenses

        entry = self.repo.create_soft_balance(
            balance_date=balance_date,
            period=(period or "AM").upper(),
            total_revenue=total_revenue,
            total_expenses=total_expenses,
            net_balance=net_balance,
            generated_by=generated_by,
            notes=notes,
        )
        self.repo.save()
        return {
            "success": True,
            "data": {
                "id": entry.id,
                "balance_date": entry.balance_date.strftime("%Y-%m-%d"),
                "period": entry.period,
                "net_balance": float(entry.net_balance or 0),
            },
        }
