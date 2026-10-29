"""Helpers for index-friendly filtering of naive datetime columns."""

from datetime import date, datetime, time, timedelta


# Database timestamps are naive UTC; Philippine business days are UTC+8.
MANILA_OFFSET = timedelta(hours=8)


def month_bounds(value: str) -> tuple[date, date]:
    """A strict YYYY-MM and an exclusive end, shared by salaries and reports."""
    try:
        if not isinstance(value, str) or len(value) != 7:
            raise ValueError
        start = date.fromisoformat(value + "-01")
        end = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
        # Ensure both boundaries can be represented as naive UTC, too.
        datetime.combine(start, time.min) - MANILA_OFFSET
        return start, end
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Choose a valid month in YYYY-MM format.") from None


def manila_sql_datetime(column):
    from sqlalchemy import func, text
    from app import db
    if db.engine.dialect.name == "sqlite":
        return func.datetime(column, "+8 hours")
    return func.date_add(column, text("INTERVAL 8 HOUR"))


def entered_manila_time(value):
    """A minute-precision picker value is Manila time, never device time."""
    if not isinstance(value, str) or len(value) != 16:
        raise ValueError("Enter a valid date and time in Manila time.")
    try:
        local = datetime.strptime(value, "%Y-%m-%dT%H:%M")
        if local.strftime("%Y-%m-%dT%H:%M") != value:
            raise ValueError
        return local - MANILA_OFFSET
    except (ValueError, OverflowError):
        raise ValueError("Enter a valid date and time in Manila time.") from None


def day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min)
    return start, start + timedelta(days=1)


def inclusive_date_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(start_date, time.min)
    end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min)
    return start, end_exclusive


def manila_date(utc_at: datetime) -> date:
    return (utc_at + MANILA_OFFSET).date()


def manila_day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start, end = day_bounds(target_date)
    return start - MANILA_OFFSET, end - MANILA_OFFSET


def inclusive_manila_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start, end = inclusive_date_bounds(start_date, end_date)
    return start - MANILA_OFFSET, end - MANILA_OFFSET
