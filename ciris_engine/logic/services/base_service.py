"""
Base Service Class for CIRIS - Maximum clarity and simplicity.

Design Principles:
1. No Untyped Dicts, No Bypass Patterns, No Exceptions - All typed with Pydantic
2. Clear separation between required and optional functionality
3. Dependency injection for all external services
4. Comprehensive lifecycle management
5. Built-in observability (metrics, health, status)
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from ciris_engine.protocols.runtime.base import ServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.metadata import ServiceMetadata


class BaseService(ABC, ServiceProtocol):
    """
    Base class for all CIRIS services.

    Provides:
    - Lifecycle management (start/stop)
    - Health checking
    - Status reporting
    - Metrics collection
    - Dependency tracking
    - Error tracking

    Subclasses MUST implement:
    - get_service_type() -> ServiceType
    - _get_actions() -> List[str]
    - _check_dependencies() -> bool

    Subclasses MAY override:
    - _on_start() -> None (for custom startup logic)
    - _on_stop() -> None (for custom cleanup)
    - _collect_custom_metrics() -> Dict[str, float]
    - _get_metadata() -> ServiceMetadata
    """

    def __init__(
        self,
        *,  # Force keyword-only arguments for clarity
        time_service: Optional[TimeServiceProtocol] = None,
        service_name: Optional[str] = None,
        version: str = "1.0.0",
    ) -> None:
        """
        Initialize base service.

        Args:
            time_service: Time service for consistent timestamps (optional)
            service_name: Override service name (defaults to class name)
            version: Service version string
        """
        # Core state
        self._started = False
        self._start_time: Optional[datetime] = None
        self.service_name = service_name or self.__class__.__name__
        self._version = version

        # Dependencies
        self._time_service = time_service
        self._logger = logging.getLogger(f"ciris_engine.services.{self.service_name}")

        # Metrics and observability
        self._metrics: Dict[str, float] = {}
        self._last_error: Optional[str] = None
        self._last_health_check: Optional[datetime] = None
        self._request_count = 0
        self._error_count = 0

        # Dependency tracking
        self._dependencies: Set[str] = set()
        self._register_dependencies()

    # Required abstract methods

    @abstractmethod
    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        ...

    @abstractmethod
    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        ...

    @abstractmethod
    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        ...

    # Optional override points

    async def _on_start(self) -> None:
        """Custom startup logic - override in subclass if needed."""
        pass

    async def _on_stop(self) -> None:
        """Custom cleanup logic - override in subclass if needed."""
        pass

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect service-specific metrics - override in subclass."""
        return {}

    def _get_metadata(self) -> ServiceMetadata:
        """Get service-specific metadata - override in subclass."""
        return ServiceMetadata()

    def _register_dependencies(self) -> None:
        """Register service dependencies - override in subclass."""
        if self._time_service:
            self._dependencies.add("TimeService")

    # ServiceProtocol implementation

    async def start(self) -> None:
        """Start the service."""
        if self._started:
            self._logger.warning(f"{self.service_name} already started")
            return

        try:
            # Check dependencies first
            if not self._check_dependencies():
                raise RuntimeError(f"{self.service_name}: Required dependencies not available")

            # Set start time
            self._start_time = self._now()

            # Call custom startup logic
            await self._on_start()

            # Mark as started
            self._started = True
            self._logger.info(f"{self.service_name} started successfully")

        except Exception as e:
            self._last_error = str(e)
            self._logger.error(f"{self.service_name} failed to start: {e}")
            raise

    async def stop(self) -> None:
        """Stop the service."""
        if not self._started:
            self._logger.warning(f"{self.service_name} not started")
            return

        try:
            # Call custom cleanup logic
            await self._on_stop()

            # Mark as stopped
            self._started = False
            self._logger.info(f"{self.service_name} stopped successfully")

        except Exception as e:
            self._last_error = str(e)
            self._logger.error(f"{self.service_name} error during stop: {e}")
            raise

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        self._last_health_check = self._now()
        return self._started and self._check_dependencies()

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name=self.service_name,
            actions=self._get_actions(),
            version=self._version,
            dependencies=list(self._dependencies),
            metadata=self._get_metadata(),
        )

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        return ServiceStatus(
            service_name=self.service_name,
            service_type=self.get_service_type().value,
            is_healthy=self._started and self._check_dependencies(),
            uptime_seconds=self._calculate_uptime(),
            metrics=self._collect_metrics(),
            last_error=self._last_error,
            last_health_check=self._last_health_check,
        )

    # Helper methods

    def _now(self) -> datetime:
        """Get current time using time service if available."""
        if self._time_service:
            return self._time_service.now()
        return datetime.now(timezone.utc)

    def _calculate_uptime(self) -> float:
        """Calculate service uptime in seconds."""
        if not self._started or not self._start_time:
            return 0.0
        return (self._now() - self._start_time).total_seconds()

    def _collect_metrics(self) -> Dict[str, float]:
        """Collect all metrics including custom ones."""
        base_metrics = {
            "uptime_seconds": self._calculate_uptime(),
            "request_count": float(self._request_count),
            "error_count": float(self._error_count),
            "error_rate": float(self._error_count) / max(1, self._request_count),
            "healthy": 1.0 if self._started else 0.0,
        }

        # Add custom metrics
        custom_metrics = self._collect_custom_metrics()
        base_metrics.update(custom_metrics)

        return base_metrics

    async def get_metrics(self) -> Dict[str, float]:
        """
        Public async method to get all service metrics.

        Returns combined base metrics and custom metrics.
        This is the standard interface for metric collection.
        """
        return self._collect_metrics()

    # Request tracking helpers (for services that handle requests)

    def _track_request(self) -> None:
        """Track a request for metrics."""
        self._request_count += 1

    def _track_error(self, error: Exception) -> None:
        """Track an error for metrics."""
        self._error_count += 1
        self._last_error = str(error)
        self._logger.error(f"{self.service_name} error: {error}")
