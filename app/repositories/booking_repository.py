from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Optional

from sqlalchemy import func

from app import db
from app.models import BoardroomBooking, CustomerSession, SpaceType


class BookingRepository:
    def get_booking(self, booking_id: int) -> Optional[BoardroomBooking]:
        return BoardroomBooking.query.filter_by(id=booking_id).first()

    def list_bookings(self, selected_date: Optional[date], status_filter: str) -> list[BoardroomBooking]:
        query = BoardroomBooking.query
        if selected_date:
            query = query.filter(BoardroomBooking.date == selected_date)
        if status_filter == "active":
            query = query.filter(BoardroomBooking.status == "active")
        elif status_filter == "booked":
            query = query.filter(BoardroomBooking.status == "booked")
        elif status_filter == "open":
            query = query.filter(BoardroomBooking.status.in_(["booked", "active"]))
        return query.order_by(BoardroomBooking.date, BoardroomBooking.start_time).all()

    def list_overdue_active(self, now: datetime) -> list[BoardroomBooking]:
        return (
            BoardroomBooking.query.filter(BoardroomBooking.status == "active")
            .filter(BoardroomBooking.expected_end_at.isnot(None))
            .filter(BoardroomBooking.expected_end_at <= now - timedelta(minutes=10))
            .all()
        )

    def find_conflict(self, selected_date: date, start_time: time, end_time: time) -> Optional[BoardroomBooking]:
        return self._find_conflict(selected_date, start_time, end_time)

    def find_conflict_excluding(
        self,
        booking_id: int,
        selected_date: date,
        start_time: time,
        end_time: time,
    ) -> Optional[BoardroomBooking]:
        return self._find_conflict(selected_date, start_time, end_time, exclude_id=booking_id)

    def _find_conflict(self, selected_date: date, start_time: time, end_time: time,
                       exclude_id: int | None = None) -> Optional[BoardroomBooking]:
        query = BoardroomBooking.query.filter(
            BoardroomBooking.date == selected_date,
            BoardroomBooking.status.in_(["booked", "active"]),
        )
        if exclude_id is not None:
            query = query.filter(BoardroomBooking.id != exclude_id)
        requested_start = datetime.combine(selected_date, start_time)
        requested_end = datetime.combine(selected_date, end_time) + timedelta(minutes=10)
        for booking in query.all():
            existing_start = datetime.combine(selected_date, booking.start_time)
            existing_end = datetime.combine(selected_date, booking.end_time) + timedelta(minutes=10)
            if existing_start < requested_end and requested_start < existing_end:
                return booking
        return None

    def get_boardroom_space(self) -> Optional[SpaceType]:
        return SpaceType.query.filter_by(name="Boardroom").first()

    def get_whole_hub_space(self) -> Optional[SpaceType]:
        return SpaceType.query.filter_by(name="Whole Hub").first()

    def has_active_sessions(self) -> bool:
        return CustomerSession.query.filter_by(status="active").first() is not None

    def sum_active_boardroom_occupancy(self, boardroom_space_id: int) -> int:
        occupied = (
            db.session.query(func.coalesce(func.sum(CustomerSession.number_of_people), 0))
            .filter(
                CustomerSession.space_type_id == boardroom_space_id,
                CustomerSession.status == "active",
            )
            .scalar()
        ) or 0
        return int(occupied)

    def create_customer_session_for_booking(
        self,
        booking: BoardroomBooking,
        boardroom_space_id: int,
        started_at: datetime,
    ) -> CustomerSession:
        session = CustomerSession(
            customer_name=booking.customer_name,
            school="Whole Hub Booking" if booking.booking_type == "whole_hub" else "Boardroom Booking",
            course=booking.course or "N/A",
            number_of_people=booking.number_of_people or 1,
            space_type_id=boardroom_space_id,
            time_in=started_at,
            status="active",
        )
        db.session.add(session)
        db.session.flush()
        return session

    def save(self) -> None:
        db.session.commit()

    def add(self, obj) -> None:
        db.session.add(obj)
