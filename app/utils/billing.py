"""Per-session seating charges using started billing blocks."""

from decimal import Decimal, ROUND_CEILING
from datetime import datetime, timedelta


def calculate_time_bill(space, minutes, *, booking=None, now_utc: datetime | None = None) -> Decimal:
    elapsed = max(Decimal(str(minutes)), Decimal(0))
    if booking is not None and now_utc is not None:
        booked_start = datetime.combine(booking.date, booking.start_time)
        booked_end = booking.expected_end_at or datetime.combine(booking.date, booking.end_time)
        booked_minutes = Decimal(str((booked_end - booked_start).total_seconds() / 60))
        past_end = Decimal(str(((now_utc + timedelta(hours=8)) - booked_end).total_seconds() / 60))
        extra = max(past_end - Decimal(10), Decimal(0))
        hours = max(Decimal(1), ((booked_minutes + extra) / 60).to_integral_value(rounding=ROUND_CEILING))
        default_rate = 500 if booking.booking_type == "whole_hub" else 250
        rate = Decimal(str(booking.hourly_rate if booking.hourly_rate is not None else default_rate))
        return (hours * rate).quantize(Decimal("0.01"))
    name = (space.name if space else "").strip().lower()
    if name in {"boardroom", "whole hub"}:
        hours = max(Decimal(1), (elapsed / 60).to_integral_value(rounding=ROUND_CEILING))
        return (hours * (500 if name == "whole hub" else 250)).quantize(Decimal("0.01"))
    if name in {"regular lounge", "premium lounge"}:
        hourly = Decimal(10 if name == "regular lounge" else 20)
        extra = (max(elapsed - 60, Decimal(0)) / 30).to_integral_value(rounding=ROUND_CEILING)
        return (hourly + extra * hourly / 2).quantize(Decimal("0.01"))
    rate = Decimal(str(space.rate_per_minute or 0)) if space else Decimal(0)
    return (elapsed * rate).quantize(Decimal("0.01"))


def billable_microseconds(session, now_utc: datetime) -> int:
    """Elapsed time excluding completed pauses and the current open pause."""
    end = session.paused_at or now_utc
    elapsed = (end - session.time_in) // timedelta(microseconds=1)
    return max(0, elapsed - int(session.paused_microseconds or 0))


def current_time_bill(session, now_utc: datetime, *, booking=None) -> Decimal:
    if session.retained_time_bill is not None:
        return Decimal(str(session.retained_time_bill)).quantize(Decimal("0.01"))
    if session.service_mode == "food_only":
        return Decimal("0.00")
    minutes = Decimal(billable_microseconds(session, now_utc)) / Decimal(60_000_000)
    return calculate_time_bill(session.space_type, minutes, booking=booking, now_utc=now_utc)
