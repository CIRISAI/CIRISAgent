"""
Period management utilities for TSDB consolidation.

Handles time period calculations, alignment, and labeling for 6-hour consolidation windows.
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple


class PeriodManager:
    """Manages consolidation period calculations and utilities."""

    def __init__(self, consolidation_interval_hours: int = 6):
        """
        Initialize period manager.

        Args:
            consolidation_interval_hours: Hours per consolidation period (default: 6)
        """
        self.interval = timedelta(hours=consolidation_interval_hours)
        self.interval_hours = consolidation_interval_hours

    def get_period_boundaries(self, timestamp: datetime) -> Tuple[datetime, datetime]:
        """
        Get the consolidation period boundaries for a given timestamp.

        Args:
            timestamp: The timestamp to align

        Returns:
            Tuple of (period_start, period_end)
        """
        # Ensure timezone aware
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        # Align to period boundary
        hour = timestamp.hour
        aligned_hour = (hour // self.interval_hours) * self.interval_hours

        period_start = timestamp.replace(hour=aligned_hour, minute=0, second=0, microsecond=0)
        period_end = period_start + self.interval

        return period_start, period_end

    def get_period_start(self, timestamp: datetime) -> datetime:
        """
        Get the start of the consolidation period containing the given timestamp.

        Args:
            timestamp: The timestamp to align

        Returns:
            Period start time
        """
        period_start, _ = self.get_period_boundaries(timestamp)
        return period_start

    def get_next_period_start(self, current_time: datetime) -> datetime:
        """
        Calculate the next consolidation period start time.

        Args:
            current_time: Current timestamp

        Returns:
            Next period start time
        """
        # Get current period
        period_start, period_end = self.get_period_boundaries(current_time)

        # Always return the end of current period as the next period start
        return period_end

    def get_period_label(self, period_start: datetime) -> str:
        """
        Generate human-readable period label.

        Args:
            period_start: Start of the period

        Returns:
            Human-readable label like "2025-07-02-morning"
        """
        hour = period_start.hour
        date_str = period_start.strftime("%Y-%m-%d")

        # Map hours to time of day
        if hour == 0:
            return f"{date_str}-night"
        elif hour == 6:
            return f"{date_str}-morning"
        elif hour == 12:
            return f"{date_str}-afternoon"
        elif hour == 18:
            return f"{date_str}-evening"
        else:
            return f"{date_str}-{hour:02d}"

    def get_period_id(self, period_start: datetime) -> str:
        """
        Generate a unique period ID for use in node IDs.

        Args:
            period_start: Start of the period

        Returns:
            Period ID like "20250702_06"
        """
        return period_start.strftime("%Y%m%d_%H")

    def is_period_complete(self, period_start: datetime, current_time: datetime) -> bool:
        """
        Check if a consolidation period is complete and ready for processing.

        Args:
            period_start: Start of the period to check
            current_time: Current time

        Returns:
            True if the period is complete
        """
        _, period_end = self.get_period_boundaries(period_start)
        return current_time >= period_end

    def get_periods_in_range(self, start_time: datetime, end_time: datetime) -> list[Tuple[datetime, datetime]]:
        """
        Get all consolidation periods within a time range.

        Args:
            start_time: Range start
            end_time: Range end

        Returns:
            List of (period_start, period_end) tuples
        """
        periods = []

        # Start from the first period containing start_time
        current_start, current_end = self.get_period_boundaries(start_time)

        while current_start < end_time:
            # Add this period if it overlaps with our range
            if current_end > start_time:
                periods.append((current_start, current_end))

            # Move to next period
            current_start = current_end
            current_end = current_start + self.interval

        return periods
