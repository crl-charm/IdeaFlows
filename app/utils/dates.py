"""Helpers for index-friendly filtering of naive datetime columns."""

from datetime import date, datetime, time, timedelta


def day_bounds(target_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(target_date, time.min)
    return start, start + timedelta(days=1)


def inclusive_date_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(start_date, time.min)
    end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min)
    return start, end_exclusive
