"""
Memory message bus - handles all memory service operations
"""

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

from dataclasses import dataclass

from ciris_engine.protocols.services import MemoryService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
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
        service_registry: "ServiceRegistry",
        time_service: TimeServiceProtocol,
        audit_service: Optional[object] = None,
    ):
        super().__init__(service_type=ServiceType.MEMORY, service_registry=service_registry)
        self._time_service = time_service
        self._audit_service = audit_service

    async def memorize(
        self, node: GraphNode, handler_name: Optional[str] = None, metadata: Optional[dict] = None
    ) -> MemoryOpResult:
        """
        Memorize a node.

        Args:
            node: The graph node to memorize
            handler_name: Name of the handler making this request (for debugging only)
            metadata: Optional metadata for the operation

        This is always synchronous as handlers need the result.
        """
        # Note: handler_name is the SOURCE (who's calling), not the target service
        # We currently have only one memory service, so no routing is needed
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["memorize"])

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult(
                status=MemoryOpStatus.FAILED,
                reason="No memory service available",
                data=node.model_dump() if hasattr(node, "model_dump") else None,
            )

        try:
            result = await service.memorize(node)
            # Protocol guarantees MemoryOpResult return
            return result
        except Exception as e:
            logger.error(f"Failed to memorize node: {e}", exc_info=True)
            return MemoryOpResult(status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

    async def recall(
        self, recall_query: MemoryQuery, handler_name: Optional[str] = None, metadata: Optional[dict] = None
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
            return nodes if nodes else []
        except Exception as e:
            logger.error(f"Failed to recall nodes: {e}", exc_info=True)
            return []

    async def forget(
        self, node: GraphNode, handler_name: Optional[str] = None, metadata: Optional[dict] = None
    ) -> MemoryOpResult:
        """
        Forget a node.

        Args:
            node: The graph node to forget
            handler_name: Name of the handler making this request (for debugging only)
            metadata: Optional metadata for the operation

        This is always synchronous as handlers need the result.
        """
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["forget"])

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult(
                status=MemoryOpStatus.FAILED,
                reason="No memory service available",
                data=node.model_dump() if hasattr(node, "model_dump") else None,
            )

        try:
            result = await service.forget(node)
            # Protocol guarantees MemoryOpResult return
            return result
        except Exception as e:
            logger.error(f"Failed to forget node: {e}", exc_info=True)
            return MemoryOpResult(status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

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

            # Convert GraphNodes to MemorySearchResults
            results = []
            for node in nodes:
                # Extract content from attributes
                content = ""
                if isinstance(node.attributes, dict):
                    content = (
                        node.attributes.get("content", "") or node.attributes.get("message", "") or str(node.attributes)
                    )
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
                        created_at = node.attributes["created_at"]
                        if isinstance(created_at, str):
                            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
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
            return await service.search(query, filters)
        except Exception as e:
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
            return await service.recall_timeseries(scope, hours, correlation_types)
        except Exception as e:
            logger.error(f"Failed to recall timeseries: {e}", exc_info=True)
            return []

    async def memorize_metric(
        self,
        metric_name: str,
        value: float,
        tags: Optional[Dict[str, str]] = None,
        scope: str = "local",
        handler_name: Optional[str] = None,
    ) -> MemoryOpResult:
        """Memorize a metric as both graph node and TSDB correlation."""
        service = await self.get_service(
            handler_name=handler_name or "unknown", required_capabilities=["memorize_metric"]
        )

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult(status=MemoryOpStatus.FAILED, reason="No memory service available")

        try:
            return await service.memorize_metric(metric_name, value, tags, scope)
        except Exception as e:
            logger.error(f"Failed to memorize metric: {e}", exc_info=True)
            return MemoryOpResult(status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

    async def memorize_log(
        self,
        log_message: str,
        log_level: str = "INFO",
        tags: Optional[Dict[str, str]] = None,
        scope: str = "local",
        handler_name: Optional[str] = None,
    ) -> MemoryOpResult:
        """Memorize a log entry as both graph node and TSDB correlation."""
        service = await self.get_service(handler_name=handler_name or "unknown", required_capabilities=["memorize_log"])

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return MemoryOpResult(status=MemoryOpStatus.FAILED, reason="No memory service available")

        try:
            return await service.memorize_log(log_message, log_level, tags, scope)
        except Exception as e:
            logger.error(f"Failed to memorize log: {e}", exc_info=True)
            return MemoryOpResult(status=MemoryOpStatus.FAILED, reason=str(e), error=str(e))

    async def export_identity_context(self, handler_name: Optional[str] = None) -> str:
        """Export identity nodes as string representation."""
        service = await self.get_service(
            handler_name=handler_name or "unknown", required_capabilities=["export_identity_context"]
        )

        if not service:
            logger.error(f"No memory service available (requested by handler: {handler_name or 'unknown'})")
            return ""

        try:
            return await service.export_identity_context()
        except Exception as e:
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
        logger.warning(f"Memory operations should be synchronous, got queued message: {type(message)}")

    async def collect_telemetry(self) -> Dict[str, any]:
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
            return {
                "service_name": "memory_bus",
                "healthy": False,
                "total_nodes": 0,
                "query_count": 0,
                "provider_count": 0,
                "cache_hit_rate": 0.0,
                "error": "No memory services available",
            }

        # Create tasks to collect telemetry from all providers
        tasks = []
        for service in all_memory_services:
            if hasattr(service, "get_telemetry"):
                tasks.append(asyncio.create_task(service.get_telemetry()))

        # Collect results with timeout
        aggregated = {
            "service_name": "memory_bus",
            "healthy": True,
            "total_nodes": 0,
            "query_count": 0,
            "provider_count": len(all_memory_services),
            "cache_hit_rate": 0.0,
            "providers": [],
        }

        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=2.0, return_when=asyncio.ALL_COMPLETED)

            # Cancel timed-out tasks
            for task in pending:
                task.cancel()

            # Aggregate results
            cache_rates = []
            for task in done:
                try:
                    telemetry = task.result()
                    if telemetry:
                        aggregated["providers"].append(telemetry.get("service_name", "unknown"))
                        aggregated["total_nodes"] += telemetry.get("total_nodes", 0)
                        aggregated["query_count"] += telemetry.get("query_count", 0)

                        # Collect cache hit rates for averaging
                        if "cache_hit_rate" in telemetry:
                            cache_rates.append(telemetry["cache_hit_rate"])
                except Exception as e:
                    logger.warning(f"Failed to collect telemetry from memory provider: {e}")

            # Calculate average cache hit rate
            if cache_rates:
                aggregated["cache_hit_rate"] = sum(cache_rates) / len(cache_rates)

        return aggregated
