from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app import db
from app.models import Admin, CustomerSession, Order, OrderItem, SpaceType, StaffAttendance, User, StaffPerformanceLog
from app.models.space_price_history import SpacePriceHistory


class AdminRepository:
    def list_staff_paginated(self, page: int, per_page: int):
        return (
            User.query.filter_by(role="staff")
            .order_by(User.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    def list_online_staff_ids(self, idle_seconds: float) -> set[int]:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=idle_seconds)
        rows = StaffAttendance.query.with_entities(StaffAttendance.user_id).filter(
            StaffAttendance.time_out.is_(None),
            func.coalesce(StaffAttendance.last_activity_at, StaffAttendance.time_in) > cutoff,
        )
        return {row.user_id for row in rows.all()}

    def close_inactive_staff_attendance(self, online_ids: set[int], idle_seconds: float) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        changed = False
        for row in StaffAttendance.query.filter(StaffAttendance.time_out.is_(None)).all():
            if row.user_id in online_ids:
                continue
            row.time_out = min(now, row.last_activity_at + timedelta(seconds=idle_seconds)) if row.last_activity_at else now
            changed = True
        if changed:
            db.session.commit()

    def close_staff_attendance(self, user_id: int, ended_at: datetime) -> None:
        rows = StaffAttendance.query.filter(
            StaffAttendance.user_id == user_id,
            StaffAttendance.time_out.is_(None),
            StaffAttendance.time_in <= ended_at,
        ).all()
        for row in rows:
            row.time_out = ended_at
        if rows:
            db.session.commit()

    def get_staff_user(self, user_id: int):
        return User.query.filter_by(id=user_id, role="staff").first()

    def username_exists_for_other(self, username: str, user_id: int) -> bool:
        existing_user = User.query.filter_by(username=username).first()
        if existing_user and existing_user.id != user_id:
            return True
        existing_admin = Admin.query.filter_by(username=username).first()
        return bool(existing_admin)

    def delete_staff_attendance(self, user_id: int) -> None:
        StaffAttendance.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        StaffPerformanceLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
        db.session.commit()

    def clear_user_orders(self, user_id: int) -> None:
        Order.query.filter_by(handled_by=user_id).update({"handled_by": None}, synchronize_session=False)
        db.session.commit()

    def list_customer_sessions(self) -> list[CustomerSession]:
        return (
            CustomerSession.query.options(
                selectinload(CustomerSession.orders)
                .selectinload(Order.items)
                .selectinload(OrderItem.menu_item),
                selectinload(CustomerSession.space_type),
            )
            .order_by(CustomerSession.time_in.desc())
            .all()
        )

    def count_customer_sessions(self) -> int:
        return CustomerSession.query.count()

    def list_spaces_with_latest_price_change(self):
        latest_history = (
            db.session.query(
                SpacePriceHistory.space_type_id.label("space_type_id"),
                func.max(SpacePriceHistory.changed_at).label("last_changed"),
            )
            .group_by(SpacePriceHistory.space_type_id)
            .subquery()
        )
        return (
            db.session.query(SpaceType, latest_history.c.last_changed)
            .outerjoin(
                latest_history,
                latest_history.c.space_type_id == SpaceType.id,
            )
            .order_by(SpaceType.name.asc())
            .all()
        )

    def list_staff_attendance(self) -> list[StaffAttendance]:
        return (
            StaffAttendance.query.options(selectinload(StaffAttendance.user))
            .order_by(StaffAttendance.time_in.desc())
            .all()
        )

    def list_spaces_with_occupancy(self):
        return (
            db.session.query(
                SpaceType.id,
                SpaceType.name,
                SpaceType.capacity,
                func.coalesce(func.sum(CustomerSession.number_of_people), 0).label("occupied"),
            )
            .outerjoin(
                CustomerSession,
                (CustomerSession.space_type_id == SpaceType.id)
                & (CustomerSession.status == "active"),
            )
            .group_by(SpaceType.id, SpaceType.name, SpaceType.capacity)
            .all()
        )

    def get_space(self, space_id: int):
        return SpaceType.query.get(space_id)

    def staff_analytics(self):
        return (
            db.session.query(
                User.id,
                User.full_name,
                User.job_role,
                func.count(Order.id).label("orders_count"),
                func.count(func.distinct(Order.customer_session_id)).label("customers_count"),
            )
            .outerjoin(Order, Order.handled_by == User.id)
            .filter(User.role == "staff")
            .group_by(User.id, User.full_name, User.job_role)
            .all()
        )

    def save(self) -> None:
        db.session.commit()

    def add(self, obj) -> None:
        db.session.add(obj)
