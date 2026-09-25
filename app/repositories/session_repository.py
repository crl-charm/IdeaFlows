from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import selectinload

from app import db
from app.models import BoardroomBooking, CustomerSession, Order, OrderItem, SpaceType, Transaction


@dataclass(frozen=True)
class SessionRepository:
    def get_session(self, session_id: int) -> Optional[CustomerSession]:
        return (
            CustomerSession.query.options(selectinload(CustomerSession.space_type))
            .filter_by(id=session_id)
            .first()
        )

    def get_session_for_update(self, session_id: int) -> Optional[CustomerSession]:
        return (
            CustomerSession.query.options(selectinload(CustomerSession.space_type))
            .filter_by(id=session_id)
            .with_for_update()
            .first()
        )

    def get_active_sessions(self) -> list[CustomerSession]:
        return (
            CustomerSession.query.options(selectinload(CustomerSession.space_type))
            .filter_by(status="active")
            .order_by(CustomerSession.time_in.desc())
            .all()
        )

    def get_active_boardroom_bookings_by_session_ids(self, session_ids: Iterable[int]) -> dict[int, BoardroomBooking]:
        session_ids = list(session_ids)
        if not session_ids:
            return {}
        rows = BoardroomBooking.query.filter(
            BoardroomBooking.session_id.in_(session_ids),
            BoardroomBooking.status == "active",
        ).all()
        return {b.session_id: b for b in rows if b.session_id is not None}

    def sum_active_occupancy(self, space_type_id: int) -> int:
        occupied = (
            db.session.query(func.coalesce(func.sum(CustomerSession.number_of_people), 0))
            .filter_by(space_type_id=space_type_id, status="active")
            .scalar()
        ) or 0
        return int(occupied)

    def get_space_type(self, space_type_id: int) -> Optional[SpaceType]:
        return SpaceType.query.get(space_type_id)

    def blocking_booking_at(self, local_now: datetime, *, whole_hub_only: bool = False) -> Optional[BoardroomBooking]:
        query = BoardroomBooking.query.filter(
            or_(
                BoardroomBooking.status == "active",
                and_(
                    BoardroomBooking.status == "booked",
                    BoardroomBooking.date == local_now.date(),
                    BoardroomBooking.start_time <= local_now.time(),
                    BoardroomBooking.end_time > local_now.time(),
                ),
            ),
        )
        if whole_hub_only:
            query = query.filter(BoardroomBooking.booking_type == "whole_hub")
        return query.first()

    def add_session(self, sess: CustomerSession) -> None:
        db.session.add(sess)
        db.session.commit()

    def complete_session(self, session: CustomerSession, time_out_utc: datetime) -> None:
        session.time_out = time_out_utc
        session.status = "completed"

    def link_booking_completion_if_any(self, session_id: int, time_out_utc: datetime) -> None:
        linked = BoardroomBooking.query.filter_by(session_id=session_id, status="active").first()
        if not linked:
            return
        linked.status = "completed"
        linked.ended_at = time_out_utc
        if linked.expected_end_at:
            extra_seconds = (time_out_utc + timedelta(hours=8) - linked.expected_end_at).total_seconds() - 600
            if extra_seconds > 0:
                linked.extended_minutes = (linked.extended_minutes or 0) + ceil(extra_seconds / 60)

    def create_transaction(self, tx: Transaction) -> None:
        db.session.add(tx)

    def commit(self) -> None:
        db.session.commit()

    def sum_food_total_for_session(self, session_id: int) -> float:
        total = (
            db.session.query(func.coalesce(func.sum(OrderItem.quantity * OrderItem.price), 0))
            .select_from(OrderItem)
            .join(Order, OrderItem.order_id == Order.id)
            .filter(Order.customer_session_id == session_id)
            .scalar()
        ) or 0
        return float(total)

    def get_order_item_for_session(self, session_id: int, item_id: int) -> Optional[OrderItem]:
        return (OrderItem.query.join(Order, OrderItem.order_id == Order.id)
                .filter(Order.customer_session_id == session_id, OrderItem.id == item_id).first())

    def list_transactions(self) -> list[Transaction]:
        return (
            Transaction.query.options(
                selectinload(Transaction.session).selectinload(CustomerSession.space_type)
            )
            .order_by(Transaction.created_at.desc())
            .all()
        )

    def list_transactions_paginated(self, page: int, per_page: int):
        return (
            Transaction.query.options(
                selectinload(Transaction.session).selectinload(CustomerSession.space_type)
            )
            .order_by(Transaction.created_at.desc())
            .paginate(page=page, per_page=per_page, error_out=False)
        )

    def list_space_types_for_availability(self) -> list[SpaceType]:
        return SpaceType.query.filter(SpaceType.name.in_(["Regular Lounge", "Premium Lounge"])).all()

    def get_all_spaces(self) -> list[SpaceType]:
        return SpaceType.query.all()

    def get_transaction_for_session(self, session_id: int) -> Optional[Transaction]:
        return (
            Transaction.query.filter_by(session_id=session_id)
            .order_by(Transaction.created_at.desc())
            .first()
        )

    def get_orders_for_session(self, session_id: int) -> list[dict[str, Any]]:
        orders = (
            Order.query.options(
                selectinload(Order.items).selectinload(OrderItem.menu_item)
            )
            .filter_by(customer_session_id=session_id)
            .all()
        )
        items_list = []
        for order in orders:
            for item in order.items:
                items_list.append({
                    "item_name": item.menu_item.name if item.menu_item else "Unknown Item",
                    "quantity": item.quantity,
                    "price": float(item.price),
                })
        return items_list

