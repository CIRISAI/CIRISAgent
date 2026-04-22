"""
Date calculation helper functions for TSDB consolidation.

Pure functions for calculating periods, retention cutoffs, and date parsing.
All functions are timezone-aware and use UTC.
"""

from datetime import date, datetime, time, timedelta, timezone
from typing import Tuple

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX


def calculate_week_period(now: datetime) -> Tuple[datetime, datetime]:
    """
    Calculate the previous Monday-Sunday period.

    If today is Monday, returns last week (Mon-Sun).
    Otherwise, returns the most recent Monday to last Sunday.

    Args:
        now: Current datetime (must be timezone-aware)

    Returns:
        Tuple of (period_start, period_end) as timezone-aware datetimes

    Examples:
        >>> from datetime import datetime, timezone
        >>> # Monday, Oct 9, 2023
        >>> monday = datetime(2023, 10, 9, 12, 0, tzinfo=timezone.utc)
        >>> start, end = calculate_week_period(monday)
        >>> start.date()
        datetime.date(2023, 10, 2)
        >>> end.date()
        datetime.date(2023, 10, 8)

        >>> # Wednesday, Oct 11, 2023
        >>> wednesday = datetime(2023, 10, 11, 12, 0, tzinfo=timezone.utc)
        >>> start, end = calculate_week_period(wednesday)
        >>> start.date()
        datetime.date(2023, 10, 9)
        >>> end.date()
        datetime.date(2023, 10, 15)
    """
    if now.tzinfo is None:
        raise ValueError("calculate_week_period requires timezone-aware datetime")

    days_since_monday = now.weekday()  # Monday = 0, Sunday = 6

    if days_since_monday == 0:
        # It's Monday, so we want last week (Mon-Sun)
        week_start_date = now.date() - timedelta(days=7)
        week_end_date = now.date() - timedelta(days=1)
    else:
        # Any other day, find the most recent Monday through next Sunday
        week_start_date = now.date() - timedelta(days=days_since_monday)
        week_end_date = week_start_date + timedelta(days=6)

    # Convert to datetime at start/end of day (UTC)
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

    Examples:
        >>> from datetime import datetime, timezone
        >>> # Mid-October 2023
        >>> oct_15 = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        >>> start, end = calculate_month_period(oct_15)
        >>> start.date()
        datetime.date(2023, 9, 1)
        >>> end.date()
        datetime.date(2023, 9, 30)
    """
    if now.tzinfo is None:
        raise ValueError("calculate_month_period requires timezone-aware datetime")

    # Get first day of current month
    first_of_current = date(now.year, now.month, 1)

    # Subtract one day to get last day of previous month
    last_of_previous = first_of_current - timedelta(days=1)

    # First day of previous month
    first_of_previous = date(last_of_previous.year, last_of_previous.month, 1)

    # Convert to datetimes
    period_start = datetime.combine(first_of_previous, time.min, tzinfo=timezone.utc)
    period_end = datetime.combine(last_of_previous, time.max, tzinfo=timezone.utc)

    return period_start, period_end


def get_retention_cutoff_date(now: datetime, retention_hours: int) -> datetime:
    """
    Calculate the cutoff date for data retention.

    Data older than this date should be deleted.

    Args:
        now: Current datetime (must be timezone-aware)
        retention_hours: Number of hours to retain data

    Returns:
        Cutoff datetime (timezone-aware)

    Examples:
        >>> from datetime import datetime, timezone
        >>> now = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        >>> cutoff = get_retention_cutoff_date(now, 24)
        >>> cutoff
        datetime.datetime(2023, 10, 14, 12, 0, tzinfo=datetime.timezone.utc)
    """
    if now.tzinfo is None:
        raise ValueError("get_retention_cutoff_date requires timezone-aware datetime")

    if retention_hours < 0:
        raise ValueError(f"retention_hours must be non-negative, got {retention_hours}")

    return now - timedelta(hours=retention_hours)


def parse_period_datetime(period_str: str) -> datetime:
    """
    Parse a period datetime string from database attributes.

    Handles both ISO format with 'Z' suffix and UTC timezone suffix.

    Args:
        period_str: ISO format datetime string (e.g., "2023-10-15T12:00:00Z")

    Returns:
        Timezone-aware datetime

    Examples:
        >>> dt = parse_period_datetime("2023-10-15T12:00:00Z")
        >>> dt.tzinfo
        datetime.timezone.utc

        >>> dt = parse_period_datetime("2023-10-15T12:00:00+00:00")
        >>> dt.tzinfo
        datetime.timezone.utc
    """
    if not period_str:
        raise ValueError("period_str cannot be empty")

    # Replace 'Z' suffix with UTC timezone suffix for consistency
    normalized = period_str.replace("Z", UTC_TIMEZONE_SUFFIX)

    try:
        return datetime.fromisoformat(normalized)
    except ValueError as e:
        raise ValueError(f"Invalid datetime format: {period_str}") from e


def format_period_label(start: datetime, end: datetime, level: str) -> str:
    """
    Format a human-readable period label.

    Args:
        start: Period start datetime
        end: Period end datetime
        level: Consolidation level ('basic', 'daily', 'weekly', 'monthly')

    Returns:
        Formatted period label

    Examples:
        >>> from datetime import datetime, timezone
        >>> start = datetime(2023, 10, 9, 0, 0, tzinfo=timezone.utc)
        >>> end = datetime(2023, 10, 15, 23, 59, 59, tzinfo=timezone.utc)
        >>> format_period_label(start, end, 'weekly')
        'weekly_2023-10-09_to_2023-10-15'

        >>> start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        >>> end = datetime(2023, 10, 31, 23, 59, 59, tzinfo=timezone.utc)
        >>> format_period_label(start, end, 'monthly')
        'monthly_2023-10-01_to_2023-10-31'
    """
    start_date_str = start.date().isoformat()
    end_date_str = end.date().isoformat()
    return f"{level}_{start_date_str}_to_{end_date_str}"
