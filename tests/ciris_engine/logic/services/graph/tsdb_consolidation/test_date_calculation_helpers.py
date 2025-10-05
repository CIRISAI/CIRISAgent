"""
Tests for date calculation helper functions.

Ensures 80%+ coverage for all date calculation logic.
"""

import pytest
from datetime import datetime, date, time, timedelta, timezone

from ciris_engine.logic.services.graph.tsdb_consolidation.date_calculation_helpers import (
    calculate_week_period,
    calculate_month_period,
    get_retention_cutoff_date,
    parse_period_datetime,
    format_period_label,
)


class TestCalculateWeekPeriod:
    """Tests for calculate_week_period function."""

    def test_monday_returns_previous_week(self):
        """Monday should return last Monday to last Sunday."""
        # Monday, Oct 9, 2023
        monday = datetime(2023, 10, 9, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_week_period(monday)

        # Should return Mon Oct 2 to Sun Oct 8
        assert start.date() == date(2023, 10, 2)
        assert end.date() == date(2023, 10, 8)
        assert start.time() == time.min
        assert end.time() == time.max

    def test_tuesday_returns_current_week(self):
        """Tuesday should return this Monday to next Sunday."""
        # Tuesday, Oct 10, 2023
        tuesday = datetime(2023, 10, 10, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_week_period(tuesday)

        # Should return Mon Oct 9 to Sun Oct 15
        assert start.date() == date(2023, 10, 9)
        assert end.date() == date(2023, 10, 15)

    def test_sunday_returns_current_week(self):
        """Sunday should return this Monday to next Sunday."""
        # Sunday, Oct 15, 2023
        sunday = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_week_period(sunday)

        # Should return Mon Oct 9 to Sun Oct 15
        assert start.date() == date(2023, 10, 9)
        assert end.date() == date(2023, 10, 15)

    def test_returns_timezone_aware_datetimes(self):
        """Should return UTC timezone-aware datetimes."""
        now = datetime(2023, 10, 10, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_week_period(now)

        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc

    def test_raises_on_naive_datetime(self):
        """Should raise ValueError for naive (non-timezone-aware) datetime."""
        naive_dt = datetime(2023, 10, 10, 12, 0)  # No tzinfo

        with pytest.raises(ValueError, match="timezone-aware"):
            calculate_week_period(naive_dt)


class TestCalculateMonthPeriod:
    """Tests for calculate_month_period function."""

    def test_mid_october_returns_september(self):
        """Mid-October should return September 1-30."""
        oct_15 = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_month_period(oct_15)

        assert start.date() == date(2023, 9, 1)
        assert end.date() == date(2023, 9, 30)
        assert start.time() == time.min
        assert end.time() == time.max

    def test_january_returns_december_of_previous_year(self):
        """January should return December of previous year."""
        jan_15 = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_month_period(jan_15)

        assert start.date() == date(2023, 12, 1)
        assert end.date() == date(2023, 12, 31)

    def test_march_handles_february_leap_year(self):
        """March in leap year should return Feb 1-29."""
        mar_15_2024 = datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_month_period(mar_15_2024)

        assert start.date() == date(2024, 2, 1)
        assert end.date() == date(2024, 2, 29)  # 2024 is leap year

    def test_march_handles_february_non_leap_year(self):
        """March in non-leap year should return Feb 1-28."""
        mar_15_2023 = datetime(2023, 3, 15, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_month_period(mar_15_2023)

        assert start.date() == date(2023, 2, 1)
        assert end.date() == date(2023, 2, 28)  # 2023 is not leap year

    def test_returns_timezone_aware_datetimes(self):
        """Should return UTC timezone-aware datetimes."""
        now = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        start, end = calculate_month_period(now)

        assert start.tzinfo == timezone.utc
        assert end.tzinfo == timezone.utc

    def test_raises_on_naive_datetime(self):
        """Should raise ValueError for naive datetime."""
        naive_dt = datetime(2023, 10, 15, 12, 0)

        with pytest.raises(ValueError, match="timezone-aware"):
            calculate_month_period(naive_dt)


class TestGetRetentionCutoffDate:
    """Tests for get_retention_cutoff_date function."""

    def test_24_hours_returns_yesterday(self):
        """24 hours retention should return 24 hours ago."""
        now = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        cutoff = get_retention_cutoff_date(now, 24)

        expected = datetime(2023, 10, 14, 12, 0, tzinfo=timezone.utc)
        assert cutoff == expected

    def test_zero_hours_returns_now(self):
        """0 hours retention should return current time."""
        now = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        cutoff = get_retention_cutoff_date(now, 0)

        assert cutoff == now

    def test_720_hours_returns_30_days_ago(self):
        """720 hours (30 days) should return 30 days ago."""
        now = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        cutoff = get_retention_cutoff_date(now, 720)

        expected = datetime(2023, 9, 15, 12, 0, tzinfo=timezone.utc)
        assert cutoff == expected

    def test_returns_timezone_aware_datetime(self):
        """Should return timezone-aware datetime."""
        now = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)
        cutoff = get_retention_cutoff_date(now, 24)

        assert cutoff.tzinfo == timezone.utc

    def test_raises_on_naive_datetime(self):
        """Should raise ValueError for naive datetime."""
        naive_dt = datetime(2023, 10, 15, 12, 0)

        with pytest.raises(ValueError, match="timezone-aware"):
            get_retention_cutoff_date(naive_dt, 24)

    def test_raises_on_negative_retention_hours(self):
        """Should raise ValueError for negative retention hours."""
        now = datetime(2023, 10, 15, 12, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="non-negative"):
            get_retention_cutoff_date(now, -10)


class TestParsePeriodDatetime:
    """Tests for parse_period_datetime function."""

    def test_parses_z_suffix_format(self):
        """Should parse ISO format with 'Z' suffix."""
        dt = parse_period_datetime("2023-10-15T12:00:00Z")

        assert dt.year == 2023
        assert dt.month == 10
        assert dt.day == 15
        assert dt.hour == 12
        assert dt.tzinfo == timezone.utc

    def test_parses_utc_offset_format(self):
        """Should parse ISO format with UTC offset."""
        dt = parse_period_datetime("2023-10-15T12:00:00+00:00")

        assert dt.year == 2023
        assert dt.month == 10
        assert dt.day == 15
        assert dt.hour == 12
        assert dt.tzinfo == timezone.utc

    def test_raises_on_empty_string(self):
        """Should raise ValueError for empty string."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_period_datetime("")

    def test_raises_on_invalid_format(self):
        """Should raise ValueError for invalid format."""
        with pytest.raises(ValueError, match="Invalid datetime format"):
            parse_period_datetime("not-a-date")

    def test_raises_on_none(self):
        """Should raise ValueError for None."""
        with pytest.raises(ValueError, match="cannot be empty"):
            parse_period_datetime(None)


class TestFormatPeriodLabel:
    """Tests for format_period_label function."""

    def test_weekly_label_format(self):
        """Should format weekly period label correctly."""
        start = datetime(2023, 10, 9, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 15, 23, 59, 59, tzinfo=timezone.utc)
        label = format_period_label(start, end, "weekly")

        assert label == "weekly_2023-10-09_to_2023-10-15"

    def test_monthly_label_format(self):
        """Should format monthly period label correctly."""
        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 31, 23, 59, 59, tzinfo=timezone.utc)
        label = format_period_label(start, end, "monthly")

        assert label == "monthly_2023-10-01_to_2023-10-31"

    def test_basic_label_format(self):
        """Should format basic period label correctly."""
        start = datetime(2023, 10, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 15, 5, 59, 59, tzinfo=timezone.utc)
        label = format_period_label(start, end, "basic")

        assert label == "basic_2023-10-15_to_2023-10-15"

    def test_daily_label_format(self):
        """Should format daily period label correctly."""
        start = datetime(2023, 10, 15, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 15, 23, 59, 59, tzinfo=timezone.utc)
        label = format_period_label(start, end, "daily")

        assert label == "daily_2023-10-15_to_2023-10-15"
