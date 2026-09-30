from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import ceil
from typing import Any, Iterable, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import selectinload

from app import db
from app.models import (
    BoardroomBooking,
    BookingChange,
    CheckoutVoidRequest,
    CustomerSession,
    Order,
    OrderItem,
    SpaceType,
    Transaction,
)
from app.utils.dates import manila_day_bounds
from app.utils.payment import VALID_PAYMENT_METHODS


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
            .filter_by(status="active", service_mode="timed")
            .order_by(CustomerSession.time_in.desc())
            .all()
        )

    def get_active_food_orders(self) -> list[CustomerSession]:
        return (
            CustomerSession.query.options(selectinload(CustomerSession.space_type))
            .filter_by(status="active", service_mode="food_only")
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

    def sum_active_occupancy(self, space_type_id: int, *, lock: bool = False) -> int:
        if lock:
            # A current read after locking the space includes check-ins committed while waiting.
            counts = (db.session.query(CustomerSession.number_of_people)
                      .filter_by(space_type_id=space_type_id, status="active", service_mode="timed")
                      .with_for_update().all())
            return sum(count or 0 for (count,) in counts)
        occupied = (
            db.session.query(func.coalesce(func.sum(CustomerSession.number_of_people), 0))
            .filter_by(space_type_id=space_type_id, status="active", service_mode="timed")
            .scalar()
        ) or 0
        return int(occupied)

    def get_space_type(self, space_type_id: int, *, lock: bool = False) -> Optional[SpaceType]:
        query = SpaceType.query.filter_by(id=space_type_id)
        return (query.with_for_update() if lock else query).first()

    def get_space_type_by_name(self, name: str) -> Optional[SpaceType]:
        return SpaceType.query.filter_by(name=name).first()

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

    def link_booking_completion_if_any(self, session_id: int, time_out_utc: datetime,
                                       transaction: Transaction) -> None:
        linked = BoardroomBooking.query.filter_by(session_id=session_id, status="active").first()
        if not linked:
            return
        before = BookingChange.snapshot(linked)
        linked.status = "completed"
        linked.ended_at = time_out_utc
        if linked.expected_end_at:
            extra_seconds = (time_out_utc + timedelta(hours=8) - linked.expected_end_at).total_seconds() - 600
            if extra_seconds > 0:
                linked.extended_minutes = (linked.extended_minutes or 0) + ceil(extra_seconds / 60)
        db.session.flush()
        db.session.add(BookingChange.capture(
            linked, "checked_out", transaction.collected_by, time_out_utc, before, transaction
        ))

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

    def food_totals_for_sessions(self, session_ids: list[int]) -> dict[int, float]:
        if not session_ids:
            return {}
        return dict(
            db.session.query(Order.customer_session_id, func.sum(OrderItem.quantity * OrderItem.price))
            .join(OrderItem, OrderItem.order_id == Order.id)
            .filter(Order.customer_session_id.in_(session_ids))
            .group_by(Order.customer_session_id)
            .all()
        )

    def get_order_item_for_session(self, session_id: int, item_id: int) -> Optional[OrderItem]:
        return (OrderItem.query.join(Order, OrderItem.order_id == Order.id)
                .filter(Order.customer_session_id == session_id, OrderItem.id == item_id).first())

    def list_transactions(self) -> list[Transaction]:
        return (
            Transaction.query.options(
                selectinload(Transaction.session).selectinload(CustomerSession.space_type),
                selectinload(Transaction.void_requests),
            )
            .order_by(Transaction.created_at.desc())
            .all()
        )

    def list_transactions_paginated(self, page: int, per_page: int, *, date_from=None, date_to=None,
                                    payment_method: str = ""):
        query = Transaction.query.options(
            selectinload(Transaction.session).selectinload(CustomerSession.space_type),
            selectinload(Transaction.void_requests),
        )
        if date_from:
            query = query.filter(Transaction.created_at >= manila_day_bounds(date_from)[0])
        if date_to:
            query = query.filter(Transaction.created_at < manila_day_bounds(date_to)[1])
        if payment_method:
            stored_method = func.lower(func.trim(Transaction.payment_method))
            if payment_method == "cash":
                query = query.filter(or_(stored_method == "cash", stored_method.notin_(VALID_PAYMENT_METHODS),
                                         Transaction.payment_method.is_(None)))
            else:
                query = query.filter(stored_method == payment_method)
        return query.order_by(Transaction.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )

    def list_space_types_for_availability(self) -> list[SpaceType]:
        return SpaceType.query.filter(SpaceType.name.in_(["Regular Lounge", "Premium Lounge"])).all()

    def get_all_spaces(self) -> list[SpaceType]:
        return SpaceType.query.all()

    def get_transaction(self, transaction_id: int) -> Optional[Transaction]:
        return Transaction.query.get(transaction_id)

    def get_transaction_for_update(self, transaction_id: int) -> Optional[Transaction]:
        return Transaction.query.filter_by(id=transaction_id).with_for_update().first()

    def get_transaction_for_session(self, session_id: int) -> Optional[Transaction]:
        """Returns the active (non-voided) transaction for this session."""
        return (
            Transaction.query.filter_by(session_id=session_id, is_voided=False)
            .order_by(Transaction.created_at.desc())
            .first()
        )

    def get_latest_transaction_for_session(self, session_id: int, *, include_voided: bool = False) -> Optional[Transaction]:
        query = Transaction.query.filter_by(session_id=session_id)
        if not include_voided:
            query = query.filter_by(is_voided=False)
        return query.order_by(Transaction.created_at.desc()).first()

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
                    "item_name": item.display_name,
                    "quantity": item.quantity,
                    "price": float(item.price),
                    "base_price": float(item.base_price if item.base_price is not None else item.price),
                    "unit_deduction": float(item.unit_deduction or 0),
                    "no_rice": bool(item.no_rice),
                    "no_egg": bool(item.no_egg),
                })
        return items_list
