"""
Date calculation helpers for TSDB consolidation cadence.

Pure functions for weekly/monthly period windows and retention cutoffs.
All functions are timezone-aware and use UTC.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Tuple


def calculate_week_period(now: datetime) -> Tuple[datetime, datetime]:
    """
    Calculate the previous Monday-Sunday period.

    If today is Monday, returns last week (Mon-Sun).
    Otherwise, returns the most recent Monday to the coming Sunday.

    Args:
        now: Current datetime (must be timezone-aware)

    Returns:
        Tuple of (period_start, period_end) as timezone-aware datetimes
    """
    if now.tzinfo is None:
        raise ValueError("calculate_week_period requires timezone-aware datetime")

    days_since_monday = now.weekday()  # Monday = 0, Sunday = 6

    if days_since_monday == 0:
        # It's Monday, so we want last week (Mon-Sun)
        week_start_date = now.date() - timedelta(days=7)
        week_end_date = now.date() - timedelta(days=1)
    else:
        week_start_date = now.date() - timedelta(days=days_since_monday)
        week_end_date = week_start_date + timedelta(days=6)

    period_start = datetime.combine(week_start_date, time.min, tzinfo=timezone.utc)
    period_end = datetime.combine(week_end_date, time.max, tzinfo=timezone.utc)
    return period_start, period_end


def calculate_month_period(now: datetime) -> Tuple[datetime, datetime]:
    """
    Calculate the previous month's period (1st to last day).

    Args:
        now: Current datetime (must be timezone-aware)

    Returns:
        Tuple of (period_start, period_end) as timezone-aware datetimes
    """
    if now.tzinfo is None:
        raise ValueError("calculate_month_period requires timezone-aware datetime")

    first_of_current = date(now.year, now.month, 1)
    last_of_previous = first_of_current - timedelta(days=1)
    first_of_previous = date(last_of_previous.year, last_of_previous.month, 1)

    period_start = datetime.combine(first_of_previous, time.min, tzinfo=timezone.utc)
    period_end = datetime.combine(last_of_previous, time.max, tzinfo=timezone.utc)
    return period_start, period_end


def get_retention_cutoff_date(now: datetime, retention_hours: int) -> datetime:
    """
    Calculate the cutoff date for data retention.

    Data older than this date should be pruned.

    Args:
        now: Current datetime (must be timezone-aware)
        retention_hours: Number of hours to retain data

    Returns:
        Cutoff datetime (timezone-aware)
    """
    if now.tzinfo is None:
        raise ValueError("get_retention_cutoff_date requires timezone-aware datetime")

    if retention_hours < 0:
        raise ValueError(f"retention_hours must be non-negative, got {retention_hours}")

    return now - timedelta(hours=retention_hours)
