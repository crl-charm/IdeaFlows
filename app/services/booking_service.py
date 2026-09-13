from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional

from app.core.interfaces import Clock, Notifier
from app.dto.serializers import serialize_booking
from app.repositories.booking_repository import BookingRepository


@dataclass(frozen=True)
class BookingService:
    repo: BookingRepository
    notifier: Notifier
    clock: Clock

    def create_booking(self, data: dict[str, Any]):
        customer_name = data.get("customer_name")
        date_str = data.get("date")
        start_time_str = data.get("start_time")
        end_time_str = data.get("end_time")
        number_of_people = data.get("number_of_people")
        course = data.get("course")
        purpose = data.get("purpose")
        if not all([customer_name, date_str, start_time_str, end_time_str, number_of_people]):
            return {"error": "Missing required fields"}, 400
        now = self.clock.now()
        local_now = now + timedelta(hours=8)
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        start_time = datetime.strptime(start_time_str, "%H:%M").time()
        end_time = datetime.strptime(end_time_str, "%H:%M").time()
        try:
            people_count = int(number_of_people)
        except (TypeError, ValueError):
            return {"error": "Number of people must be a valid number"}, 400
        if people_count <= 0:
            return {"error": "Number of people must be greater than 0"}, 400
        if end_time <= start_time:
            return {"error": "End time must be after start time"}, 400
        if selected_date < local_now.date():
            return {"error": "Booking date cannot be in the past"}, 400
        if selected_date == local_now.date() and datetime.combine(selected_date, end_time) <= local_now:
            return {"error": "Booking end time must be in the future"}, 400
        conflict = self.repo.find_conflict(selected_date, start_time, end_time)
        if conflict:
            return {
                "error": f"Slot conflicts with existing booking ({conflict.start_time.strftime('%H:%M')}–{conflict.end_time.strftime('%H:%M')})"
            }, 400
        from app.models import BoardroomBooking

        booking = BoardroomBooking(
            customer_name=customer_name,
            date=selected_date,
            start_time=start_time,
            end_time=end_time,
            number_of_people=people_count,
            course=(course or "").strip() or None,
            purpose=purpose,
            status="booked",
            expected_end_at=datetime.combine(selected_date, end_time),
        )
        self.repo.add(booking)
        self.repo.save()
        self.notifier.booking_updated({"booking_id": booking.id, "status": booking.status})
        return {"message": "Boardroom booked successfully"}

    def list_bookings(self, date_str: str, status_filter: str) -> list[dict[str, Any]]:
        selected_date = None
        if date_str:
            try:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                selected_date = None
        bookings = self.repo.list_bookings(selected_date, status_filter)
        now = self.clock.now()
        local_now = now + timedelta(hours=8)
        rows: list[dict[str, Any]] = []
        for booking in bookings:
            row = serialize_booking(booking)
            row["can_start"] = booking.status == "booked" and str(booking.date) == local_now.date().isoformat()
            row["is_active"] = booking.status == "active"
            row["is_overdue"] = bool(
                booking.expected_end_at and booking.status == "active" and local_now >= booking.expected_end_at
            )
            rows.append(row)
        return rows

    def update_booking_start(self, booking_id: int, start_time_str: str):
        booking = self.repo.get_booking(booking_id)
        if not booking:
            return {"error": "Booking not found"}, 404
        if booking.status != "booked":
            return {"error": "Only booked boardroom slots can be edited."}, 400
        if not start_time_str:
            return {"error": "Start time is required."}, 400

        try:
            new_start = datetime.strptime(start_time_str, "%H:%M").time()
        except ValueError:
            return {"error": "Invalid start time format. Use HH:MM."}, 400

        end_time = booking.end_time
        if new_start >= end_time:
            return {"error": "Start time must be before the booked end time."}, 400

        day_start = datetime.strptime("07:00", "%H:%M").time()
        day_end = datetime.strptime("22:00", "%H:%M").time()
        if new_start < day_start or new_start > day_end:
            return {"error": "Start time must be within 7:00 AM to 10:00 PM."}, 400

        now = self.clock.now()
        local_now = now + timedelta(hours=8)
        if booking.date < local_now.date():
            return {"error": "Cannot edit a booking in the past."}, 400

        if booking.date == local_now.date():
            new_start_dt = datetime.combine(booking.date, new_start)
            if new_start_dt > local_now + timedelta(minutes=15):
                return {
                    "error": "Start time cannot be more than 15 minutes in the future for today's booking."
                }, 400

        conflict = self.repo.find_conflict_excluding(
            booking.id, booking.date, new_start, end_time
        )
        if conflict:
            return {
                "error": f"Slot conflicts with existing booking ({conflict.start_time.strftime('%H:%M')}–{conflict.end_time.strftime('%H:%M')})"
            }, 400

        booking.start_time = new_start
        booking.expected_end_at = datetime.combine(booking.date, end_time)
        self.repo.save()
        self.notifier.booking_updated({"booking_id": booking.id, "status": "updated"})
        return {
            "message": "Booking start time updated.",
            "data": serialize_booking(booking),
        }

    def start_booking(self, booking_id: int):
        booking = self.repo.get_booking(booking_id)
        if not booking:
            return {"error": "Booking not found"}, 404
        if booking.status != "booked":
            return {"error": "Only booked boardroom slots can be started."}, 400
        now = self.clock.now()
        local_now = now + timedelta(hours=8)
        if booking.date != local_now.date():
            return {"error": "Booking can only be started on its scheduled date."}, 400
        boardroom = self.repo.get_boardroom_space()
        if not boardroom:
            return {"error": "Boardroom space is missing. Please seed spaces first."}, 500
        occupied = self.repo.sum_active_boardroom_occupancy(boardroom.id)
        requested = booking.number_of_people or 1
        if boardroom.capacity and (occupied + requested) > boardroom.capacity:
            seats_left = max(int(boardroom.capacity) - int(occupied), 0)
            return {"error": f"Boardroom has only {seats_left} seat(s) left."}, 409
        session = self.repo.create_customer_session_for_booking(booking, boardroom.id, now)
        booking.status = "active"
        booking.started_at = now
        booking.expected_end_at = datetime.combine(booking.date, booking.end_time)
        booking.session_id = session.id
        self.repo.save()
        self.notifier.booking_updated({"booking_id": booking.id, "status": "active", "session_id": session.id})
        return {"message": "Boardroom session started.", "session_id": session.id}

    def extend_booking(self, booking_id: int, minutes: int):
        booking = self.repo.get_booking(booking_id)
        if not booking:
            return {"error": "Booking not found"}, 404
        if booking.status != "active":
            return {"error": "Only active bookings can be extended."}, 400
        if minutes <= 0:
            return {"error": "Extension minutes must be greater than 0."}, 400
        current_end = booking.expected_end_at or datetime.combine(booking.date, booking.end_time)
        new_end = current_end + timedelta(minutes=minutes)
        booking.expected_end_at = new_end
        booking.end_time = new_end.time()
        booking.extended_minutes = (booking.extended_minutes or 0) + minutes
        self.repo.save()
        self.notifier.booking_updated({"booking_id": booking.id, "status": "extended"})
        return {
            "message": "Booking extended.",
            "end_time": booking.end_time.strftime("%H:%M"),
            "expected_end_at": booking.expected_end_at.isoformat(),
            "extended_minutes": booking.extended_minutes,
        }

    def cancel_booking(self, booking_id: int):
        booking = self.repo.get_booking(booking_id)
        if not booking:
            return {"error": "Booking not found"}, 404
        if booking.status == "active":
            return {"error": "Active session cannot be cancelled. Checkout first."}, 400
        booking.status = "cancelled"
        self.repo.save()
        self.notifier.booking_updated({"booking_id": booking.id, "status": "cancelled"})
        return {"message": "Booking cancelled"}

    def overdue_alerts(self) -> list[dict[str, Any]]:
        now = self.clock.now()
        local_now = now + timedelta(hours=8)
        overdue = self.repo.list_overdue_active(local_now)
        return [
            {
                "booking_id": b.id,
                "customer_name": b.customer_name,
                "expected_end_at": b.expected_end_at.isoformat() if b.expected_end_at else None,
                "session_id": b.session_id,
            }
            for b in overdue
        ]

