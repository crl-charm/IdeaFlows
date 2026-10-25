from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

from app.core.interfaces import Clock
from app.repositories.sales_repository import SalesRepository
from app.utils.dates import manila_date
from app.services.cash_box_service import CashBoxService


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
        today = manila_date(self.clock.now())
        return {"date": str(today), **self._shape(self.repo.summary_for_day(today))}

    def sales_summary(self, period: str) -> dict[str, Any]:
        today = manila_date(self.clock.now())
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
        today = manila_date(self.clock.now())
        yesterday = today - timedelta(days=1)
        return {
            "today": self._shape(self.repo.summary_for_day(today)),
            "yesterday": self._shape(self.repo.summary_for_day(yesterday)),
            "last_7_days": self._shape(self.repo.summary_for_range(today - timedelta(days=6), today)),
            "last_30_days": self._shape(self.repo.summary_for_range(today - timedelta(days=29), today)),
        }

    def list_reports(self, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
        live = self.repo.daily_ledger(start_date, end_date)
        saved = {r.report_date: r for r in self.repo.list_reports()
                 if (not start_date or r.report_date >= start_date) and (not end_date or r.report_date <= end_date)}
        days = set(live) | set(saved)
        if start_date and start_date == end_date:
            days.add(start_date)
        opening = CashBoxService.opening_date()
        today = manila_date(datetime.utcnow())
        cash_end = min(end_date, today) if end_date else (today if opening else max(days, default=None))
        cash = CashBoxService.summaries(cash_end) if cash_end else {}
        days.update(day for day in cash if (not start_date or day >= start_date)
                    and (not end_date or day <= end_date))
        result = []
        for day in sorted(days, reverse=True):
            row = live.get(day) or self.repo.daily_ledger_empty(day)
            snapshot = saved.get(day)
            result.append({
                **row,
                "id": snapshot.id if snapshot else None,
                "generated_by": snapshot.generated_by_user.username if snapshot and snapshot.generated_by_user else "Not generated",
                "generated_at": snapshot.generated_at.isoformat() + "Z" if snapshot else None,
                "notes": snapshot.notes if snapshot else None,
                "cash_boxes": cash.get(day),
                "snapshot_cash_movement": float(snapshot.cash_movement) if snapshot and snapshot.cash_movement is not None else None,
                "snapshot_petty_cash_closing": float(snapshot.petty_cash_closing) if snapshot and snapshot.petty_cash_closing is not None else None,
                "snapshot_customer_cash_closing": float(snapshot.customer_cash_closing) if snapshot and snapshot.customer_cash_closing is not None else None,
                "petty_cash_snapshot_difference": (cash[day]["closing"]["petty"] - float(snapshot.petty_cash_closing)
                                                   if snapshot and snapshot.petty_cash_closing is not None and day in cash else None),
                "customer_cash_snapshot_difference": (cash[day]["closing"]["customer"] - float(snapshot.customer_cash_closing)
                                                      if snapshot and snapshot.customer_cash_closing is not None and day in cash else None),
                "cash_snapshot_difference": (cash[day]["total_closing"] - float(snapshot.petty_cash_closing + snapshot.customer_cash_closing)
                                             if snapshot and snapshot.petty_cash_closing is not None
                                             and snapshot.customer_cash_closing is not None and day in cash else None),
            })
        return result

    def list_soft_balances(self) -> list[dict[str, Any]]:
        entries = self.repo.list_soft_balances()
        cash = CashBoxService.summaries(max(e.balance_date for e in entries)) if entries else {}
        return [
            {
                "id": row.id,
                "balance_date": row.balance_date.strftime("%Y-%m-%d"),
                "period": row.period,
                "total_revenue": float(row.total_revenue or 0),
                "total_expenses": float(row.total_expenses or 0),
                "total_collections": float(row.total_collections or 0),
                "total_payables_paid": float(row.total_payables_paid or 0),
                "total_other_income": float(row.total_other_income or 0),
                "total_budget_spend": float(row.total_budget_spend or 0),
                "net_balance": float(row.net_balance or 0),
                "petty_cash_closing": float(row.petty_cash_closing) if row.petty_cash_closing is not None else None,
                "customer_cash_closing": float(row.customer_cash_closing) if row.customer_cash_closing is not None else None,
                "cash_movement": float(row.cash_movement) if row.cash_movement is not None else None,
                "petty_cash_live_difference": (cash[row.balance_date]["closing"]["petty"] - float(row.petty_cash_closing)
                                               if row.balance_date in cash and row.petty_cash_closing is not None else None),
                "customer_cash_live_difference": (cash[row.balance_date]["closing"]["customer"] - float(row.customer_cash_closing)
                                                  if row.balance_date in cash and row.customer_cash_closing is not None else None),
                "live_cash_difference": (cash[row.balance_date]["total_closing"] - float(row.petty_cash_closing + row.customer_cash_closing)
                                         if row.balance_date in cash and row.petty_cash_closing is not None
                                         and row.customer_cash_closing is not None else None),
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
        live = self.list_reports(report_date, report_date)[0]
        total_revenue = Decimal(str(live["total_revenue"]))
        total_expenses = Decimal(str(live["total_expenses"]))
        total_collections = Decimal(str(live["total_collections"]))
        total_payables_paid = Decimal(str(live["total_payables_paid"]))
        total_other_income = Decimal(str(live["total_other_income"]))
        total_budget_spend = Decimal(str(live["total_budget_spend"]))
        net_balance = Decimal(str(live["net_balance"]))

        existing = self.repo.get_daily_report(report_date)
        if existing:
            existing.total_revenue = total_revenue
            existing.total_expenses = total_expenses
            existing.total_collections = total_collections
            existing.total_payables_paid = total_payables_paid
            existing.total_other_income = total_other_income
            existing.total_budget_spend = total_budget_spend
            existing.net_balance = net_balance
            existing.total_orders = live["total_orders"]
            existing.total_sessions = live["total_sessions"]
            existing.generated_by = generated_by
            existing.generated_at = datetime.utcnow()
            existing.notes = notes
            report = existing
        else:
            report = self.repo.create_report(
                report_date=report_date,
                total_revenue=total_revenue,
                total_expenses=total_expenses,
                total_collections=total_collections,
                total_payables_paid=total_payables_paid,
                total_other_income=total_other_income,
                total_budget_spend=total_budget_spend,
                net_balance=net_balance,
                total_orders=live["total_orders"],
                total_sessions=live["total_sessions"],
                generated_by=generated_by,
                notes=notes,
            )
        boxes = live.get("cash_boxes")
        report.petty_cash_closing = Decimal(str(boxes["closing"]["petty"])) if boxes else None
        report.customer_cash_closing = Decimal(str(boxes["closing"]["customer"])) if boxes else None
        report.cash_movement = Decimal(str(boxes["total_movement"])) if boxes else None
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
                "cowork_bill": live["cowork_bill"],
                "cafe_bill": live["cafe_bill"],
                "discounts_total": live["discounts_total"],
                "total_refunds": live["total_refunds"],
                "total_expenses": float(total_expenses),
                "total_collections": float(total_collections),
                "total_payables_paid": float(total_payables_paid),
                "total_other_income": float(total_other_income),
                "total_budget_spend": float(total_budget_spend),
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
        live = self.list_reports(balance_date, balance_date)[0]
        total_revenue = Decimal(str(live["total_revenue"]))
        total_expenses = Decimal(str(live["total_expenses"]))
        total_collections = Decimal(str(live["total_collections"]))
        total_payables_paid = Decimal(str(live["total_payables_paid"]))
        total_other_income = Decimal(str(live["total_other_income"]))
        total_budget_spend = Decimal(str(live["total_budget_spend"]))
        net_balance = Decimal(str(live["net_balance"]))

        entry = self.repo.create_soft_balance(
            balance_date=balance_date,
            period=(period or "AM").upper(),
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
        boxes = live.get("cash_boxes")
        entry.petty_cash_closing = Decimal(str(boxes["closing"]["petty"])) if boxes else None
        entry.customer_cash_closing = Decimal(str(boxes["closing"]["customer"])) if boxes else None
        entry.cash_movement = Decimal(str(boxes["total_movement"])) if boxes else None
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
