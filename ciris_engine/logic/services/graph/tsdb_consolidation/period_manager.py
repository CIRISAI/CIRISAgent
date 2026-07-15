"""Period cadence math for TSDB consolidation.

Pure 6-hour-window boundary calculations. This is agent-side scheduling
state only — all consolidation compute lives in the persist substrate.
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple


class PeriodManager:
    """Aligns timestamps to consolidation period boundaries."""

    def __init__(self, consolidation_interval_hours: int = 6):
        """
        Initialize period manager.

        Args:
            consolidation_interval_hours: Hours per consolidation period (default: 6)
        """
        self.interval = timedelta(hours=consolidation_interval_hours)
        self.interval_hours = consolidation_interval_hours

    def get_period_boundaries(self, timestamp: datetime) -> Tuple[datetime, datetime]:
        """Get the (period_start, period_end) boundaries containing `timestamp`."""
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        aligned_hour = (timestamp.hour // self.interval_hours) * self.interval_hours
        period_start = timestamp.replace(hour=aligned_hour, minute=0, second=0, microsecond=0)
        return period_start, period_start + self.interval

    def get_period_start(self, timestamp: datetime) -> datetime:
        """Get the start of the period containing `timestamp`."""
        period_start, _ = self.get_period_boundaries(timestamp)
        return period_start

    def get_next_period_start(self, current_time: datetime) -> datetime:
        """Get the start of the period after the one containing `current_time`."""
        _, period_end = self.get_period_boundaries(current_time)
        return period_end
