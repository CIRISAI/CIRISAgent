"""
Base Graph Service - Common implementation for all graph services.

Provides default implementations of GraphServiceProtocol methods.
All graph services use the MemoryBus for actual persistence operations.
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.protocols.runtime.base import GraphServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.services.operations import MemoryOpStatus, MemoryQuery

if TYPE_CHECKING:
    from ciris_engine.logic.buses import MemoryBus

logger = logging.getLogger(__name__)


class BaseGraphService(ABC, GraphServiceProtocol):
    """Base class for all graph services providing common functionality.

    Graph services store their data through the MemoryBus, which provides:
    - Multiple backend support (Neo4j, ArangoDB, in-memory)
    - Secret detection and encryption
    - Audit trail integration
    - Typed schema validation
    """

    def __init__(
        self, memory_bus: Optional["MemoryBus"] = None, time_service: Optional[TimeServiceProtocol] = None
    ) -> None:
        """Initialize base graph service.

        Args:
            memory_bus: MemoryBus for graph persistence operations
            time_service: TimeService for consistent timestamps
        """
        self.service_name = self.__class__.__name__
        self._memory_bus = memory_bus
        self._time_service = time_service
        self._telemetry_service = None  # Will be set after instantiation if needed
        self._request_count = 0
        self._error_count = 0
        self._total_response_time = 0.0
        self._start_time: Optional[datetime] = None

    def _set_memory_bus(self, memory_bus: "MemoryBus") -> None:
        """Set the memory bus for graph operations."""
        self._memory_bus = memory_bus

    def _set_time_service(self, time_service: TimeServiceProtocol) -> None:
        """Set the time service for timestamps."""
        self._time_service = time_service

    async def start(self) -> None:
        """Start the service."""
        self._start_time = datetime.now()
        # Initialize telemetry if available
        if hasattr(self, "_telemetry_service") and self._telemetry_service:
            from ciris_engine.schemas.api.telemetry import ServiceMetrics

            metrics = ServiceMetrics(
                service_name=self.service_name,
                healthy=True,
                uptime_seconds=0.0,
                memory_usage_mb=0.0,
                cpu_usage_percent=0.0,
                request_count=0,
                error_count=0,
                avg_response_time_ms=0.0,
            )
            self._telemetry_service.update_service_metrics(metrics)
        logger.info(f"{self.service_name} started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info(f"{self.service_name} stopped")

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name=self.service_name,
            actions=["store_in_graph", "query_graph", self.get_node_type()],
            version="1.0.0",
        )

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        return self._memory_bus is not None

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect graph service specific metrics."""
        return {
            "memory_bus_available": 1.0 if self._memory_bus else 0.0,
            "time_service_available": 1.0 if self._time_service else 0.0,
            "graph_operations_total": float(self._request_count),
            "graph_errors_total": float(self._error_count),
        }

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return ["store_in_graph", "query_graph", self.get_node_type()]

    def _track_request(self, response_time_ms: float) -> None:
        """Track a successful request."""
        self._request_count += 1
        self._total_response_time += response_time_ms
        if self._telemetry_service:
            self._update_telemetry()

    def _track_error(self) -> None:
        """Track an error."""
        self._error_count += 1
        if self._telemetry_service:
            self._update_telemetry()

    def _update_telemetry(self) -> None:
        """Update telemetry metrics."""
        if not self._telemetry_service:
            return

        import psutil

        from ciris_engine.schemas.api.telemetry import ServiceMetrics

        # Get process info
        process = psutil.Process()
        memory_info = process.memory_info()

        # Calculate uptime
        uptime = (datetime.now() - self._start_time).total_seconds() if self._start_time else 0.0

        # Calculate average response time
        avg_response_time = self._total_response_time / self._request_count if self._request_count > 0 else 0.0

        metrics = ServiceMetrics(
            service_name=self.service_name,
            healthy=self._check_dependencies(),
            uptime_seconds=uptime,
            memory_usage_mb=memory_info.rss / 1024 / 1024,
            cpu_usage_percent=process.cpu_percent(),
            request_count=self._request_count,
            error_count=self._error_count,
            avg_response_time_ms=avg_response_time,
        )
        self._telemetry_service.update_service_metrics(metrics)

    async def store_in_graph(self, node: GraphNode) -> str:
        """Store a node in the graph using MemoryBus.

        Args:
            node: GraphNode to store (or any object with to_graph_node method)

        Returns:
            Node ID if successful, empty string if failed
        """
        if not self._memory_bus:
            raise RuntimeError(f"{self.service_name}: Memory bus not available")

        # Convert to GraphNode if it has a to_graph_node method
        if hasattr(node, "to_graph_node") and callable(getattr(node, "to_graph_node")):
            graph_node = node.to_graph_node()
        else:
            graph_node = node

        result = await self._memory_bus.memorize(graph_node)
        return graph_node.id if result.status == MemoryOpStatus.OK else ""

    async def query_graph(self, query: MemoryQuery) -> List[GraphNode]:
        """Query the graph using MemoryBus.

        Args:
            query: MemoryQuery with filters and options

        Returns:
            List of matching GraphNodes
        """
        if not self._memory_bus:
            logger.warning(f"{self.service_name}: Memory bus not available for query")
            return []

        result = await self._memory_bus.recall(query)

        # Handle different result types
        if hasattr(result, "status") and hasattr(result, "data"):
            # It's a MemoryOpResult
            if result.status == MemoryOpStatus.OK and result.data:
                if isinstance(result.data, list):
                    return result.data
                else:
                    return [result.data]
        elif isinstance(result, list):
            # Direct list of nodes
            return result

        return []

    @abstractmethod
    def get_node_type(self) -> str:
        """Get the type of nodes this service manages - must be implemented by subclass."""
        raise NotImplementedError
