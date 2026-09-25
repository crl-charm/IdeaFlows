"""Helpers for index-friendly filtering of naive datetime columns."""

from datetime import date, datetime, time, timedelta


# Database timestamps are naive UTC; Philippine business days are UTC+8.
MANILA_OFFSET = timedelta(hours=8)


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
