from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.core.interfaces import Clock, Notifier
from app.dto.serializers import serialize_booking
from app.repositories.booking_repository import BookingRepository


@dataclass(frozen=True)
class BookingService:
    repo: BookingRepository
    notifier: Notifier
    clock: Clock

    def create_booking(self, data: dict[str, Any], *, allow_custom_rate: bool = False):
        customer_name = data.get("customer_name")
        date_str = data.get("date")
        start_time_str = data.get("start_time")
        end_time_str = data.get("end_time")
        number_of_people = data.get("number_of_people")
        course = data.get("course")
        purpose = data.get("purpose")
        booking_type = data.get("booking_type") or "boardroom"
        if booking_type not in {"boardroom", "whole_hub"}:
            return {"error": "Invalid booking type"}, 400
        if not isinstance(customer_name, str) or not customer_name.strip() or len(customer_name) > 100:
            return {"error": "Enter a customer name up to 100 characters."}, 400
        customer_name = customer_name.strip()
        if course is not None and (not isinstance(course, str) or len(course) > 100):
            return {"error": "Course must be text up to 100 characters."}, 400
        if purpose is not None and (not isinstance(purpose, str) or len(purpose) > 255):
            return {"error": "Purpose must be text up to 255 characters."}, 400
        if not all([customer_name, date_str, start_time_str, end_time_str, number_of_people]):
            return {"error": "Missing required fields"}, 400
        now = self.clock.now()
        local_now = now + timedelta(hours=8)
        try:
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
        except (TypeError, ValueError):
            return {"error": "Enter a valid booking date and time."}, 400
        walk_in = data.get("walk_in") is True
        if walk_in:
            if selected_date != local_now.date() or abs((datetime.combine(selected_date, start_time) - local_now).total_seconds()) > 300:
                return {"error": "Walk-in start time must be right now."}, 400
            start_time = local_now.time().replace(second=0, microsecond=0)
        try:
            hourly_rate = Decimal("500.00") if booking_type == "whole_hub" else Decimal(str(data.get("hourly_rate", 250)))
            if not hourly_rate.is_finite() or hourly_rate < 0 or hourly_rate > 100000 or hourly_rate.as_tuple().exponent < -2:
                raise ValueError
        except (InvalidOperation, TypeError, ValueError):
            return {"error": "Enter a valid hourly price (₱0–₱100,000)."}, 400
        if booking_type == "boardroom" and not allow_custom_rate and hourly_rate != Decimal("250"):
            return {"error": "Only the owner can change the boardroom price."}, 403
        if isinstance(number_of_people, bool) or not str(number_of_people).isdigit():
            return {"error": "Number of people must be a valid number"}, 400
        people_count = int(number_of_people)
        if people_count <= 0:
            return {"error": "Number of people must be greater than 0"}, 400
        if end_time <= start_time:
            return {"error": "End time must be after start time"}, 400
        if start_time < datetime.strptime("07:00", "%H:%M").time() or end_time > datetime.strptime("22:00", "%H:%M").time():
            return {"error": "Booking hours are 7:00 AM to 10:00 PM."}, 400
        if selected_date < local_now.date():
            return {"error": "Booking date cannot be in the past"}, 400
        if selected_date == local_now.date() and datetime.combine(selected_date, end_time) <= local_now:
            return {"error": "Booking end time must be in the future"}, 400
        conflict = self.repo.find_conflict(selected_date, start_time, end_time)
        if conflict:
            return {
                "error": f"Slot conflicts with existing booking ({conflict.start_time.strftime('%H:%M')}–{conflict.end_time.strftime('%H:%M')})"
            }, 400
        space = self.repo.get_whole_hub_space() if booking_type == "whole_hub" else self.repo.get_boardroom_space()
        if not space:
            return {"error": "Booking space is missing. Run database setup first."}, 500
        if walk_in and (self.repo.has_active_sessions() if booking_type == "whole_hub" else self.repo.sum_active_boardroom_occupancy(space.id) > 0):
            return {"error": "The requested space is currently occupied."}, 409
        if booking_type == "boardroom" and space.capacity and people_count > space.capacity:
            return {"error": f"Boardroom fits only {space.capacity} people."}, 400
        from app.models import BoardroomBooking

        booking = BoardroomBooking(
            customer_name=customer_name,
            date=selected_date,
            start_time=start_time,
            end_time=end_time,
            number_of_people=people_count,
            course=(course or "").strip() or None,
            purpose=purpose,
            booking_type=booking_type,
            hourly_rate=hourly_rate,
            status="active" if walk_in else "booked",
            expected_end_at=datetime.combine(selected_date, end_time),
        )
        self.repo.add(booking)
        if walk_in:
            session = self.repo.create_customer_session_for_booking(booking, space.id, now)
            booking.session_id = session.id
            booking.started_at = now
        self.repo.save()
        self.notifier.booking_updated({"booking_id": booking.id, "status": booking.status})
        return {"message": "Customer checked in." if walk_in else "Booking saved.", "booking_id": booking.id,
                "session_id": booking.session_id}

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
                booking.expected_end_at and booking.status == "active" and local_now >= booking.expected_end_at + timedelta(minutes=10)
            )
            rows.append(row)
        return rows

    def update_booking_start(self, booking_id: int, start_time_str: str):
        booking = self.repo.get_booking(booking_id)
        if not booking:
            return {"error": "Booking not found"}, 404
        if booking.status != "booked":
            return {"error": "Only upcoming bookings can be edited."}, 400
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
            return {"error": "Only upcoming bookings can be started."}, 400
        now = self.clock.now()
        local_now = now + timedelta(hours=8)
        if booking.date != local_now.date():
            return {"error": "Booking can only be started on its scheduled date."}, 400
        if datetime.combine(booking.date, booking.start_time) > local_now + timedelta(minutes=15):
            return {"error": "This booking cannot be checked in more than 15 minutes early."}, 400
        if booking.expected_end_at and booking.expected_end_at <= local_now:
            return {"error": "This booking has already ended. Make a new booking."}, 400
        whole_hub = booking.booking_type == "whole_hub"
        space = self.repo.get_whole_hub_space() if whole_hub else self.repo.get_boardroom_space()
        if not space:
            return {"error": "Booking space is missing. Please seed spaces first."}, 500
        if (self.repo.has_active_sessions() if whole_hub else self.repo.sum_active_boardroom_occupancy(space.id) > 0):
            return {"error": "The requested space is currently occupied."}, 409
        if not whole_hub and space.capacity and booking.number_of_people > space.capacity:
            return {"error": f"Boardroom fits only {space.capacity} people."}, 409
        session = self.repo.create_customer_session_for_booking(booking, space.id, now)
        booking.status = "active"
        booking.started_at = now
        booking.expected_end_at = datetime.combine(booking.date, booking.end_time)
        booking.session_id = session.id
        self.repo.save()
        self.notifier.booking_updated({"booking_id": booking.id, "status": "active", "session_id": session.id})
        return {"message": "Booking started.", "session_id": session.id}

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
        if new_end.date() != booking.date or new_end.time() > datetime.strptime("22:00", "%H:%M").time():
            return {"error": "Extension must end by 10:00 PM."}, 400
        if self.repo.find_conflict_excluding(booking.id, booking.date, booking.start_time, new_end.time()):
            return {"error": "Extension overlaps another booking."}, 409
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

