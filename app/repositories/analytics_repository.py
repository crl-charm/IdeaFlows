from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any

from sqlalchemy import Integer, cast, func

from app import db
from app.models import Transaction, Order, CustomerSession, MenuItem
from app.utils.dates import manila_date, manila_day_bounds, manila_sql_datetime


class AnalyticsRepository:
    def daily_revenue(self, days: int = 30) -> list[dict[str, Any]]:
        start_date = manila_date(datetime.utcnow()) - timedelta(days=days)
        start_at, _ = manila_day_bounds(start_date)
        day = func.date(manila_sql_datetime(Transaction.effective_paid_at))
        result = (
            db.session.query(
                day.label("date"),
                func.sum(Transaction.total_bill).label("revenue"),
            )
            .filter(Transaction.payment_range(start_at))
            .group_by(day)
            .order_by(day)
            .all()
        )
        return [
            {
                "date": str(row.date),
                "revenue": float(row.revenue or 0),
            }
            for row in result
        ]

    def top_menu_items(self, limit: int = 10) -> list[dict[str, Any]]:
        from app.models import OrderItem
        result = (
            db.session.query(
                MenuItem.name,
                func.sum(OrderItem.quantity).label("count"),
                func.sum(OrderItem.quantity * OrderItem.price).label("total"),
            )
            .join(OrderItem, MenuItem.id == OrderItem.menu_item_id)
            .group_by(MenuItem.id, MenuItem.name)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "name": row.name,
                "count": int(row.count or 0),
                "total": float(row.total or 0),
            }
            for row in result
        ]

    def space_utilization(self) -> list[dict[str, Any]]:
        result = (
            db.session.query(
                CustomerSession.space_type_id,
            )
            .group_by(CustomerSession.space_type_id)
            .all()
        )
        return [{"space_id": row.space_type_id} for row in result]

    def peak_hours(self) -> list[dict[str, Any]]:
        local_time = manila_sql_datetime(Transaction.effective_paid_at)
        hour = cast(func.strftime("%H", local_time), Integer) if db.engine.dialect.name == "sqlite" else func.hour(local_time)
        result = (
            db.session.query(
                hour.label("hour"),
                func.count(Transaction.id).label("count"),
            )
            .filter(Transaction.effective_paid_at.isnot(None))
            .group_by(hour)
            .order_by(hour)
            .all()
        )
        return [
            {
                "hour": int(row.hour or 0),
                "count": int(row.count),
            }
            for row in result
        ]
