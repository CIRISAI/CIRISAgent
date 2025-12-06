"""
Protocol for TSDB Consolidation Service.

This service consolidates time-series telemetry data into permanent summaries
for long-term memory (1000+ years).
"""

from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Optional, Protocol, runtime_checkable

from ...runtime.base import GraphServiceProtocol

if TYPE_CHECKING:
    from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
    from ciris_engine.schemas.services.graph.consolidation import TSDBPeriodSummary
    from ciris_engine.schemas.services.graph_core import NodeType


@runtime_checkable
class TSDBConsolidationServiceProtocol(GraphServiceProtocol, Protocol):
    """Protocol for TSDB consolidation service.

    Consolidates TSDB telemetry nodes into 6-hour summaries for permanent storage.
    Runs every 6 hours and deletes raw nodes older than 24 hours.
    """

    @abstractmethod
    async def start(self) -> None:
        """Start the consolidation service and begin periodic consolidation."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the consolidation service gracefully, running final consolidation."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the service is healthy.

        Returns:
            True if service is running and has required dependencies
        """
        ...

    @abstractmethod
    def get_capabilities(self) -> "ServiceCapabilities":
        """Get service capabilities.

        Returns:
            ServiceCapabilities with actions, version, dependencies, and metadata
        """
        ...

    @abstractmethod
    def get_status(self) -> "ServiceStatus":
        """Get service status.

        Returns:
            ServiceStatus with health, uptime, metrics, and last consolidation info
        """
        ...

    @abstractmethod
    def get_node_type(self) -> "NodeType":
        """Get the node type this service manages.

        Returns:
            NodeType.TSDB_SUMMARY
        """
        ...

    @abstractmethod
    async def get_summary_for_period(
        self, period_start: datetime, period_end: datetime
    ) -> Optional["TSDBPeriodSummary"]:
        """Get the summary for a specific period.

        Args:
            period_start: Start of the period
            period_end: End of the period

        Returns:
            TSDBPeriodSummary containing summary data if found, or None if not found
        """
        ...
