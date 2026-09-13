from __future__ import annotations

from datetime import datetime, date, timedelta
from typing import Any

from sqlalchemy import func

from app import db
from app.models import Transaction, Order, CustomerSession, MenuItem
from app.utils.dates import day_bounds


class AnalyticsRepository:
    def daily_revenue(self, days: int = 30) -> list[dict[str, Any]]:
        start_date = date.today() - timedelta(days=days)
        start_at, _ = day_bounds(start_date)
        result = (
            db.session.query(
                func.date(Transaction.created_at).label("date"),
                func.sum(Transaction.total_bill).label("revenue"),
            )
            .filter(Transaction.created_at >= start_at)
            .group_by(func.date(Transaction.created_at))
            .order_by(func.date(Transaction.created_at))
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
        result = (
            db.session.query(
                func.hour(Transaction.created_at).label("hour"),
                func.count(Transaction.id).label("count"),
            )
            .filter(Transaction.created_at.isnot(None))
            .group_by(func.hour(Transaction.created_at))
            .order_by(func.hour(Transaction.created_at))
            .all()
        )
        return [
            {
                "hour": int(row.hour or 0),
                "count": int(row.count),
            }
            for row in result
        ]
