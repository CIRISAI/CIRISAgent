"""
Memory message bus - handles all memory service operations
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.infrastructure.base import ServiceRegistryProtocol

from dataclasses import dataclass

from ciris_engine.logic.utils.jsondict_helpers import get_float, get_int, get_str
from ciris_engine.protocols.services import MemoryService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.base import BusMetrics
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.memory import MemorySearchResult, TimeSeriesDataPoint
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus, MemoryQuery

from .base_bus import BaseBus, BusMessage

logger = logging.getLogger(__name__)


@dataclass
class MemorizeBusMessage(BusMessage):
    """Bus message to memorize a node"""

    node: GraphNode


@dataclass
class RecallBusMessage(BusMessage):
    """Bus message to recall a node"""

    node: GraphNode


@dataclass
class ForgetBusMessage(BusMessage):
    """Bus message to forget a node"""

    node: GraphNode


class MemoryBus(BaseBus[MemoryService]):
    """
    Message bus for all memory operations.

    Handles:
    - memorize
    - recall
    - forget
    """

    def __init__(
        self,
        service_registry: "ServiceRegistryProtocol",
        time_service: TimeServiceProtocol,
        audit_service: Optional[object] = None,
        telemetry_service: Optional[object] = None,
    ):
        super().__init__(service_type=ServiceType.MEMORY, service_registry=service_registry)
        self._time_service = time_service
        self._start_time = time_service.now() if time_service else None
        self._audit_service = audit_service

        # Memory bus specific metrics
        self._operation_count = 0
        self._broadcast_count = 0
        self._error_count = 0

    async def memorize(
        self, node: GraphNode, handler_name: Optional[str] = None, metadata: Optional[JSONDict] = None
    ) -> "MemoryOpResult[GraphNode]":
        """
        Memorize a node.

        Args:
            node: The graph node to memorize
            handler_name: Name of the handler making this request (for debugging only)
            metadata: Optional metadata for the operation

        Returns:
            MemoryOpResult[GraphNode] with the stored node in data field

        This is always synchronous as handlers need the result.
        """
        # Note: handler_name is the SOURCE (who's calling), not the target service
        # We currently have only one memory service, so no routing is needed
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["memorize"])

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult[GraphNode](
                status=MemoryOpStatus.FAILED,
                reason="No memory service available",
                data=None,
            )

        try:
            result = await service.memorize(node)
            # Increment operation counter on success
            self._operation_count += 1
            # Protocol guarantees MemoryOpResult[GraphNode] return
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to memorize node: {e}", exc_info=True)
            return MemoryOpResult[GraphNode](status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

    async def recall(
        self, recall_query: MemoryQuery, handler_name: Optional[str] = None, metadata: Optional[JSONDict] = None
    ) -> List[GraphNode]:
        """
        Recall nodes based on query.

        Args:
            recall_query: The memory query
            handler_name: Name of the handler making this request (for debugging only)
            metadata: Optional metadata for the operation

        This is always synchronous as handlers need the result.
        """
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["recall"])

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return []

        try:
            nodes = await service.recall(recall_query)
            # Increment operation counter on success
            self._operation_count += 1
            return nodes if nodes else []
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to recall nodes: {e}", exc_info=True)
            return []

    async def forget(
        self, node: GraphNode, handler_name: Optional[str] = None, metadata: Optional[JSONDict] = None
    ) -> "MemoryOpResult[GraphNode]":
        """
        Forget a node.

        Args:
            node: The graph node to forget
            handler_name: Name of the handler making this request (for debugging only)
            metadata: Optional metadata for the operation

        Returns:
            MemoryOpResult[GraphNode] with the forgotten node in data field

        This is always synchronous as handlers need the result.
        """
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["forget"])

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult[GraphNode](
                status=MemoryOpStatus.FAILED,
                reason="No memory service available",
                data=None,
            )

        try:
            result = await service.forget(node)
            # Increment operation counter on success
            self._operation_count += 1
            # Protocol guarantees MemoryOpResult[GraphNode] return
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to forget node: {e}", exc_info=True)
            return MemoryOpResult[GraphNode](status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

    async def search_memories(
        self, query: str, scope: str = "default", limit: int = 10, handler_name: Optional[str] = None
    ) -> List[MemorySearchResult]:
        """Search memories using text query."""
        service = await self.get_service(
            handler_name=handler_name or "unknown", required_capabilities=["search_memories"]
        )

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return []

        try:
            # Use search to find memories by text
            from ciris_engine.schemas.services.graph_core import GraphScope

            # MemorySearchFilter already imported at the top of the file
            # Convert scope string to GraphScope enum
            try:
                graph_scope = GraphScope(scope) if scope != "default" else GraphScope.LOCAL
            except ValueError:
                graph_scope = GraphScope.LOCAL

            # Create search filter
            search_filter = MemorySearchFilter(scope=graph_scope, limit=limit)

            nodes = await service.search(query, search_filter)

            # Increment operation counter on success
            self._operation_count += 1

            # Convert GraphNodes to MemorySearchResults
            results = []
            for node in nodes:
                # Extract content from attributes
                content = ""
                if isinstance(node.attributes, dict):
                    content_val = node.attributes.get("content") or node.attributes.get("message")
                    if isinstance(content_val, str):
                        content = content_val
                    else:
                        content = str(node.attributes)
                else:
                    content = (
                        getattr(node.attributes, "content", "")
                        or getattr(node.attributes, "message", "")
                        or str(node.attributes)
                    )

                # Extract created_at
                created_at = datetime.now(timezone.utc)
                if isinstance(node.attributes, dict):
                    if "created_at" in node.attributes:
                        created_at_val = node.attributes["created_at"]
                        if isinstance(created_at_val, str):
                            created_at = datetime.fromisoformat(created_at_val.replace("Z", "+00:00"))
                        elif isinstance(created_at_val, datetime):
                            created_at = created_at_val
                elif hasattr(node.attributes, "created_at"):
                    created_at = node.attributes.created_at

                results.append(
                    MemorySearchResult(
                        node_id=node.id,
                        content=content,
                        node_type=node.type.value if hasattr(node.type, "value") else str(node.type),
                        relevance_score=0.8,  # Default score since we don't have actual relevance
                        created_at=created_at,
                        metadata={},
                    )
                )

            return results
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to search memories: {e}", exc_info=True)
            return []

    async def search(
        self, query: str, filters: Optional["MemorySearchFilter"] = None, handler_name: Optional[str] = None
    ) -> List[GraphNode]:
        """Search graph nodes with flexible filters."""
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["search"])

        if not service:
            logger.error(f"No memory service with search capability available for {handler_name}")
            return []

        try:
            result = await service.search(query, filters)
            # Increment operation counter on success
            self._operation_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to search graph nodes: {e}", exc_info=True)
            return []

    async def recall_timeseries(
        self,
        scope: str = "default",
        hours: int = 24,
        correlation_types: Optional[List[str]] = None,
        handler_name: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[TimeSeriesDataPoint]:
        """Recall time-series data."""
        service = await self.get_service(
            handler_name=handler_name or "unknown", required_capabilities=["recall_timeseries"]
        )

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return []

        try:
            result = await service.recall_timeseries(scope, hours, correlation_types)
            # Increment operation counter on success
            self._operation_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to recall timeseries: {e}", exc_info=True)
            return []

    async def memorize_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
        scope: str = "local",
        handler_name: Optional[str] = None,
    ) -> "MemoryOpResult[GraphNode]":
        """
        Memorize a metric as both graph node and TSDB correlation.

        Returns:
            MemoryOpResult[GraphNode] with the metric node in data field
        """
        service = await self.get_service(
            handler_name=handler_name or "unknown", required_capabilities=["memorize_metric"]
        )

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult[GraphNode](status=MemoryOpStatus.FAILED, reason="No memory service available")

        try:
            result = await service.memorize_metric(metric_name, value, tags, scope)
            # Increment operation counter on success
            self._operation_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to memorize metric: {e}", exc_info=True)
            return MemoryOpResult[GraphNode](status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

    async def memorize_log(
        self,
        log_message: str,
        log_level: str = "INFO",
        tags: Optional[Dict[str, str]] = None,
        scope: str = "local",
        handler_name: Optional[str] = None,
    ) -> "MemoryOpResult[GraphNode]":
        """
        Memorize a log entry as both graph node and TSDB correlation.

        Returns:
            MemoryOpResult[GraphNode] with the log node in data field
        """
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["memorize_log"])

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult[GraphNode](status=MemoryOpStatus.FAILED, reason="No memory service available")

        try:
            result = await service.memorize_log(log_message, log_level, tags, scope)
            # Increment operation counter on success
            self._operation_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to memorize log: {e}", exc_info=True)
            return MemoryOpResult[GraphNode](status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

    async def export_identity_context(self, handler_name: Optional[str] = None) -> str:
        """Export identity nodes as string representation."""
        service = await self.get_service(
            handler_name=handler_name or "unknown", required_capabilities=["export_identity_context"]
        )

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return ""

        try:
            result = await service.export_identity_context()
            # Increment operation counter on success
            self._operation_count += 1
            return result
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to export identity context: {e}", exc_info=True)
            return ""

    async def is_healthy(self, handler_name: str = "default") -> bool:
        """Check if memory service is healthy."""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return False
        try:
            return await service.is_healthy()
        except Exception as e:
            logger.error(f"Failed to check health: {e}")
            return False

    async def get_capabilities(self, handler_name: str = "default") -> List[str]:
        """Get memory service capabilities."""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return []
        try:
            capabilities = service.get_capabilities()
            return capabilities.supports_operation_list if hasattr(capabilities, "supports_operation_list") else []
        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            return []

    async def _process_message(self, message: BusMessage) -> None:
        """Process a memory message"""
        # For now, all memory operations are synchronous
        # This bus mainly exists for consistency and future async operations
        # Increment broadcast counter when messages are processed
        self._broadcast_count += 1
        logger.warning(f"Memory operations should be synchronous, got queued message: {type(message)}")

    def _create_empty_telemetry(self) -> JSONDict:
        """Create empty telemetry response when no services available."""
        return {
            "service_name": "memory_bus",
            "healthy": False,
            "total_nodes": 0,
            "query_count": 0,
            "provider_count": 0,
            "cache_hit_rate": 0.0,
            "error": "No memory services available",
        }

    def _create_telemetry_tasks(self, services: List[Any]) -> List[Any]:
        """Create telemetry collection tasks for all services."""
        import asyncio

        tasks = []
        for service in services:
            if hasattr(service, "get_telemetry"):
                tasks.append(asyncio.create_task(service.get_telemetry()))
        return tasks

    def _aggregate_telemetry_result(self, telemetry: JSONDict, aggregated: JSONDict, cache_rates: List[float]) -> None:
        """Aggregate a single telemetry result into the combined metrics."""
        if telemetry:
            service_name = get_str(telemetry, "service_name", "unknown")
            providers_list = aggregated["providers"]
            if isinstance(providers_list, list):
                providers_list.append(service_name)

            total_nodes = aggregated["total_nodes"]
            if isinstance(total_nodes, int):
                aggregated["total_nodes"] = total_nodes + get_int(telemetry, "total_nodes", 0)

            query_count = aggregated["query_count"]
            if isinstance(query_count, int):
                aggregated["query_count"] = query_count + get_int(telemetry, "query_count", 0)

            if "cache_hit_rate" in telemetry:
                cache_hit_rate = get_float(telemetry, "cache_hit_rate", 0.0)
                cache_rates.append(cache_hit_rate)

    async def collect_telemetry(self) -> JSONDict:
        """
        Collect telemetry from all memory providers in parallel.

        Returns aggregated metrics including:
        - total_nodes: Total nodes across all providers
        - query_count: Total queries processed
        - provider_count: Number of active providers
        - cache_hit_rate: Average cache hit rate
        """
        import asyncio

        all_memory_services = self.service_registry.get_services_by_type(ServiceType.MEMORY)

        if not all_memory_services:
            return self._create_empty_telemetry()

        # Create tasks to collect telemetry from all providers
        tasks = self._create_telemetry_tasks(all_memory_services)

        # Initialize aggregated metrics
        aggregated: JSONDict = {
            "service_name": "memory_bus",
            "healthy": True,
            "total_nodes": 0,
            "query_count": 0,
            "provider_count": len(all_memory_services),
            "cache_hit_rate": 0.0,
            "providers": [],
        }

        if not tasks:
            return aggregated

        # Collect results with timeout
        done, pending = await asyncio.wait(tasks, timeout=2.0, return_when=asyncio.ALL_COMPLETED)

        # Cancel timed-out tasks
        for task in pending:
            task.cancel()

        # Aggregate results
        cache_rates: List[float] = []
        for task in done:
            try:
                telemetry = task.result()
                self._aggregate_telemetry_result(telemetry, aggregated, cache_rates)
            except Exception as e:
                logger.warning(f"Failed to collect telemetry from memory provider: {e}")

        # Calculate average cache hit rate
        if cache_rates:
            aggregated["cache_hit_rate"] = sum(cache_rates) / len(cache_rates)

        return aggregated

    def _collect_metrics(self) -> Dict[str, float]:
        """Collect base metrics for the memory bus."""
        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        return {
            "memory_operations_total": float(self._operation_count),
            "memory_errors_total": float(self._error_count),
            "memory_broadcasts": float(self._broadcast_count),
            "memory_uptime_seconds": uptime_seconds,
        }

    def get_metrics(self) -> BusMetrics:
        """
        Get all memory bus metrics as typed BusMetrics schema.

        Returns BusMetrics with:
        - messages_sent: Total memory operations performed
        - messages_received: Same as sent (synchronous operations)
        - messages_dropped: Currently 0 (no drop tracking yet)
        - average_latency_ms: Currently 0.0 (no latency tracking yet)
        - active_subscriptions: Number of registered memory services
        - queue_depth: Current message queue size
        - errors_last_hour: Error count (no time-window yet, total errors)
        - additional_metrics: Bus-specific metrics including uptime

        Uses real values from bus state, not zeros.
        """
        # Get subscriber count (registered memory services)
        memory_services = self.service_registry.get_services_by_type(ServiceType.MEMORY)
        subscriber_count = len(memory_services) if memory_services else 0

        # Calculate uptime for additional_metrics
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        # Map to BusMetrics schema
        return BusMetrics(
            messages_sent=self._operation_count,  # All successful memory operations
            messages_received=self._operation_count,  # Synchronous, same as sent
            messages_dropped=0,  # Not tracked yet
            average_latency_ms=0.0,  # Not tracked yet
            active_subscriptions=subscriber_count,
            queue_depth=self.get_queue_size(),
            errors_last_hour=self._error_count,  # Total errors (not windowed yet)
            busiest_service=None,  # Could track which service gets most calls
            additional_metrics={
                "memory_operations_total": self._operation_count,
                "memory_broadcasts": self._broadcast_count,
                "memory_uptime_seconds": uptime_seconds,
            },
        )
