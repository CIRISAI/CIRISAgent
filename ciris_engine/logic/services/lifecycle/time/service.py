"""
Secure Time Service for CIRIS Trinity Architecture.

Provides centralized time operations that are:
- Mockable for testing
- Timezone-aware (always UTC)
- Consistent across the system
- No direct datetime.now() usage allowed

This replaces the time_utils.py utility with a proper service.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ciris_engine.logic.services.base_infrastructure_service import BaseInfrastructureService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.metadata import ServiceMetadata

logger = logging.getLogger(__name__)


class TimeService(BaseInfrastructureService, TimeServiceProtocol):
    """Secure time service implementation."""

    def __init__(self) -> None:
        """Initialize the time service."""
        # Initialize base class without time_service (we ARE the time service)
        super().__init__(service_name="TimeService", version="1.0.0")
        self._start_time = datetime.now(timezone.utc)

        # Metrics tracking
        self._time_requests = 0
        self._iso_requests = 0
        self._timestamp_requests = 0
        self._uptime_requests = 0

        # NTP drift monitoring
        # The last MEASURED NTP offset (server - local) in milliseconds; None until NTP has answered. Never
        # simulated: a missing measurement is reported as absent, not invented.
        self._ntp_offset_ms: Optional[float] = None
        self._ntp_last_check: Optional[datetime] = None  # Last time we checked NTP
        self._ntp_check_interval = 3600  # Check every hour
        self._ntp_check_count = 0
        self._ntp_failures = 0
        self._ntp_pools = ["pool.ntp.org", "0.pool.ntp.org", "1.pool.ntp.org", "time.nist.gov"]

    # Required abstract methods from BaseService

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.TIME

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["now", "now_iso", "timestamp"]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        # TimeService has no dependencies
        return True

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get metadata from parent's _get_metadata()
        service_metadata = self._get_metadata()

        # Set infrastructure-specific fields
        if service_metadata:
            service_metadata.category = "infrastructure"
            service_metadata.critical = True
            service_metadata.description = "Provides consistent UTC time operations"

        return ServiceCapabilities(
            service_name=self.service_name,
            actions=self._get_actions(),
            version=self._version,
            dependencies=list(self._dependencies),
            metadata=service_metadata,
        )

    # Override _now to prevent circular dependency
    def _now(self) -> datetime:
        """Get current time without using time service."""
        return datetime.now(timezone.utc)

    def _collect_custom_metrics(self) -> dict[str, float]:
        """Collect time service specific metrics."""
        metrics: Dict[str, float] = super()._collect_custom_metrics()

        # Check NTP drift if needed
        self._check_ntp_drift_if_needed()

        # Add time service metrics
        metrics.update(
            {
                "time_requests": float(self._time_requests),
                "iso_requests": float(self._iso_requests),
                "timestamp_requests": float(self._timestamp_requests),
                "uptime_requests": float(self._uptime_requests),
                "total_requests": float(
                    self._time_requests + self._iso_requests + self._timestamp_requests + self._uptime_requests
                ),
                "days_running": self.get_uptime() / 86400.0,  # Convert to days
                **self._drift_metrics(),
                "ntp_check_count": float(self._ntp_check_count),
                "ntp_failures": float(self._ntp_failures),
                "timezone_offset": 0.0,  # Always 0 for UTC
            }
        )

        return metrics

    def now(self) -> datetime:
        """
        Get current time in UTC.

        Returns:
            datetime: Current time in UTC with timezone info
        """
        self._time_requests += 1
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        """
        Get current time as ISO string.

        Returns:
            str: Current UTC time in ISO format
        """
        self._iso_requests += 1
        return self.now().isoformat()

    def timestamp(self) -> float:
        """
        Get current Unix timestamp.

        Returns:
            float: Seconds since Unix epoch
        """
        self._timestamp_requests += 1
        return self.now().timestamp()

    def get_uptime(self) -> float:
        """
        Get service uptime in seconds.

        Returns:
            float: Seconds since service started
        """
        self._uptime_requests += 1
        if self._start_time is None:
            return 0.0
        return (self.now() - self._start_time).total_seconds()

    def _check_ntp_drift_if_needed(self) -> None:
        """Check NTP drift if interval has passed."""
        current_time = datetime.now(timezone.utc)

        # Check if we need to update NTP offset
        if (
            self._ntp_last_check is None
            or (current_time - self._ntp_last_check).total_seconds() > self._ntp_check_interval
        ):
            self._update_ntp_offset()
            self._ntp_last_check = current_time

    def _update_ntp_offset(self) -> None:
        """Update NTP offset by querying NTP servers."""
        try:
            # Try to import ntplib (optional dependency)
            import ntplib
        except ImportError:
            # ntplib not available: no measurement (the last real one, if any, stands)
            return

        c = ntplib.NTPClient()

        # Try each NTP server until one works
        for server in self._ntp_pools:
            try:
                response = c.request(server, version=3, timeout=2)
                # Convert offset to milliseconds
                self._ntp_offset_ms = response.offset * 1000
                self._ntp_check_count += 1
                logger.debug(f"NTP drift check: {self._ntp_offset_ms:.2f}ms from {server}")
                return
            except Exception:
                continue

        # All servers failed
        self._ntp_failures += 1
        logger.warning("Failed to check NTP drift from all servers")
        # No new measurement: the last real one, if any, stands. Nothing is simulated.

    def _drift_metrics(self) -> Dict[str, float]:
        """``time_drift_measured`` always; ``time_drift_ms`` only once NTP has actually measured it."""
        if self._ntp_offset_ms is None:
            return {"time_drift_measured": 0.0}
        return {"time_drift_measured": 1.0, "time_drift_ms": self._ntp_offset_ms}

    def get_ntp_offset(self) -> Optional[float]:
        """The last measured NTP offset in seconds, or ``None`` when NTP has never answered.

        ntplib's convention: server time minus local time, so a POSITIVE offset means the local clock is BEHIND.
        """
        self._check_ntp_drift_if_needed()
        return None if self._ntp_offset_ms is None else self._ntp_offset_ms / 1000.0

    def get_adjusted_time(self) -> datetime:
        """The current time corrected by the measured NTP offset (``now() + offset``); ``now()`` when unmeasured."""
        from datetime import timedelta

        offset_seconds = self.get_ntp_offset()
        if offset_seconds is None:
            return self.now()
        return self.now() + timedelta(seconds=offset_seconds)

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all time service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Calculate total time queries from all tracked request types
        total_queries = self._time_requests + self._iso_requests + self._timestamp_requests + self._uptime_requests

        # Sync operations = NTP checks performed
        sync_operations = self._ntp_check_count

        # Current clock drift in milliseconds, only when NTP measured it
        self._check_ntp_drift_if_needed()

        # Service uptime in seconds
        uptime_seconds = self.get_uptime()

        # Add v1.4.3 specific time metrics
        metrics.update(
            {
                "time_queries_total": float(total_queries),
                "time_sync_operations": float(sync_operations),
                **self._drift_metrics(),
                "time_uptime_seconds": uptime_seconds,
            }
        )

        return metrics
