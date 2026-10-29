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


def historical_billable_microseconds(session, departure: datetime, events) -> int:
    """Count only pauses inside the visit; never use a later pause as its end."""
    paused_from = None
    completed = 0
    applicable = 0
    partial_history = False
    relevant_pairs = 0
    for event in events:
        if event.action not in {"paused", "resumed"}:
            continue
        when = event.occurred_at
        if when < session.time_in:
            raise ValueError("Time history needs review before recording this checkout.")
        if event.action == "paused":
            if paused_from is not None:
                raise ValueError("Time history contains overlapping pauses; review it first.")
            paused_from = when
        else:
            if paused_from is None or when < paused_from:
                raise ValueError("Time history contains an unmatched resume; review it first.")
            completed += (when - paused_from) // timedelta(microseconds=1)
            if paused_from < departure:
                applicable += (min(when, departure) - paused_from) // timedelta(microseconds=1)
                relevant_pairs += 1
            partial_history = partial_history or when > departure
            paused_from = None

    stored = int(session.paused_microseconds or 0)
    if stored < 0:
        raise ValueError("Recorded pause totals are invalid; review them first.")
    if stored and not any(event.action == "resumed" for event in events):
        raise ValueError("Recorded pauses are missing their history; review them first.")
    if abs(completed - stored) > 2_000_000 * (len(events) + 1):
        raise ValueError("Recorded pause totals do not match time history; review them first.")
    if bool(paused_from is not None) != bool(session.paused_at):
        raise ValueError("The current pause does not match time history; review it first.")
    if paused_from is not None:
        if abs((paused_from - session.paused_at).total_seconds()) > 1:
            raise ValueError("The current pause does not match time history; review it first.")
        if paused_from < departure:
            applicable += (departure - session.paused_at) // timedelta(microseconds=1)
    # Completed pauses entirely before departure can use the exact stored total.
    if not partial_history:
        applicable += stored - completed
    elapsed = (departure - session.time_in) // timedelta(microseconds=1)
    billable = max(0, elapsed - applicable)
    # Older MySQL DATETIME fields may have lost fractions. Refuse an ambiguous
    # price boundary instead of inventing the missing precision in a past pause.
    if partial_history and relevant_pairs and completed != stored:
        uncertainty = abs(completed - stored) + relevant_pairs * 1_000_000
        low = max(0, billable - uncertainty)
        high = min(elapsed, billable + uncertainty)
        if calculate_time_bill(session.space_type, Decimal(low) / 60_000_000) != calculate_time_bill(session.space_type, Decimal(high) / 60_000_000):
            raise ValueError("Pause timestamp precision affects this bill; review the departure time first.")
    return billable


def current_time_bill(session, now_utc: datetime, *, booking=None) -> Decimal:
    if session.retained_time_bill is not None:
        return Decimal(str(session.retained_time_bill)).quantize(Decimal("0.01"))
    if session.service_mode == "food_only":
        return Decimal("0.00")
    minutes = Decimal(billable_microseconds(session, now_utc)) / Decimal(60_000_000)
    return calculate_time_bill(session.space_type, minutes, booking=booking, now_utc=now_utc)
