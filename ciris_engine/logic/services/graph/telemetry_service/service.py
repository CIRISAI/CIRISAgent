"""
Graph-based TelemetryService that stores all metrics as memories in the graph.

This implements the "Graph Memory as Identity Architecture" patent by routing
all telemetry data through the memory system as TSDBGraphNodes.

Consolidates functionality from:
- GraphTelemetryService (graph-based metrics)
- AdapterTelemetryService (system snapshots)
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union

from ciris_engine.schemas.types import JSONDict

# Optional import for psutil
try:
    import psutil  # type: ignore[import,unused-ignore]

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore[assignment,no-redef,unused-ignore]
    PSUTIL_AVAILABLE = False

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.base_graph_service import BaseGraphService
from ciris_engine.protocols.infrastructure.base import RegistryAwareServiceProtocol, ServiceRegistryProtocol
from ciris_engine.protocols.runtime.base import GraphServiceProtocol as TelemetryServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.protocols_core import MetricDataPoint, ResourceLimits
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.runtime.system_context import ChannelContext as SystemChannelContext
from ciris_engine.schemas.runtime.system_context import ContinuitySummary, SystemSnapshot, TelemetrySummary, UserProfile
from ciris_engine.schemas.services.core import ServiceStatus
from ciris_engine.schemas.services.graph.telemetry import (
    AggregatedTelemetryMetadata,
    AggregatedTelemetryResponse,
    BehavioralData,
    MetricRecord,
    ResourceData,
    ServiceTelemetryData,
    TelemetryData,
    TelemetrySnapshotResult,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus
from ciris_engine.schemas.telemetry.core import ServiceCorrelation

# Import from modular components
from .aggregator import ConsolidationCandidate, GracePolicy, MemoryType, TelemetryAggregator
from .storage import (
    store_behavioral_data,
    store_identity_context,
    store_resource_usage,
    store_social_context,
    store_telemetry_metrics,
)

logger = logging.getLogger(__name__)


class GraphTelemetryService(BaseGraphService, TelemetryServiceProtocol, RegistryAwareServiceProtocol):
    """
    Consolidated TelemetryService that stores all metrics as graph memories.

    This service implements the vision where "everything is a memory" by
    converting telemetry data into TSDBGraphNodes stored in the memory graph.

    Features:
    - Processes SystemSnapshot data from adapters
    - Records operational metrics and resource usage
    - Stores behavioral, social, and identity context
    - Applies grace-based wisdom to memory consolidation
    """

    def __init__(
        self, memory_bus: Optional[MemoryBus] = None, time_service: Optional[Any] = None  # TimeServiceProtocol
    ) -> None:
        # Initialize BaseGraphService
        super().__init__(memory_bus=memory_bus, time_service=time_service)

        self._service_registry: Optional[Any] = None
        self._resource_limits = ResourceLimits(
            max_memory_mb=4096,
            max_cpu_percent=80.0,
            max_disk_gb=100.0,
            max_api_calls_per_minute=1000,
            max_concurrent_operations=50,
        )
        # Cache for recent metrics (for quick status queries)
        self._recent_metrics: dict[str, list[MetricDataPoint]] = {}
        self._max_cached_metrics = 100

        # Cache for telemetry summaries to avoid slamming persistence
        self._summary_cache: dict[str, tuple[datetime, TelemetrySummary]] = {}
        self._summary_cache_ttl_seconds = 60  # Cache for 1 minute

        # Memory tracking
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

        # Consolidation settings

        # Enterprise telemetry aggregator
        self._telemetry_aggregator: Optional[TelemetryAggregator] = None
        self._runtime: Optional[Any] = None  # Store runtime reference for aggregator

    def _set_runtime(self, runtime: object) -> None:
        """Set the runtime reference for accessing core services directly (internal method)."""
        logger.debug(f"[TELEMETRY] _set_runtime called, runtime={runtime is not None}")
        self._runtime = runtime
        logger.debug(
            f"[TELEMETRY] Aggregator exists: {self._telemetry_aggregator is not None}, Registry exists: {self._service_registry is not None}"
        )
        # Re-create aggregator if it exists to include runtime
        if self._telemetry_aggregator and self._service_registry:
            logger.debug("[TELEMETRY] Recreating aggregator with runtime")
            self._telemetry_aggregator = TelemetryAggregator(
                service_registry=self._service_registry, time_service=self._time_service, runtime=self._runtime
            )
        else:
            logger.debug("[TELEMETRY] Aggregator will be created later with runtime when first needed")

    async def attach_registry(self, registry: "ServiceRegistryProtocol") -> None:
        """
        Attach service registry for bus and service discovery.

        Implements RegistryAwareServiceProtocol to enable proper initialization
        of memory bus and time service dependencies.

        Args:
            registry: Service registry providing access to buses and services
        """
        self._service_registry = registry
        if not self._memory_bus and registry:
            # Try to get memory bus from registry
            try:
                from ciris_engine.logic.buses import MemoryBus
                from ciris_engine.logic.registries.base import ServiceRegistry

                if isinstance(registry, ServiceRegistry) and self._time_service is not None:
                    self._memory_bus = MemoryBus(registry, self._time_service)
            except Exception as e:
                logger.error(f"Failed to initialize memory bus: {e}")

        # Get time service from registry if not provided
        if not self._time_service and registry:
            from ciris_engine.schemas.runtime.enums import ServiceType

            time_services: List[Any] = getattr(registry, "get_services_by_type", lambda x: [])(ServiceType.TIME)
            if time_services:
                self._time_service = time_services[0]

    def _now(self) -> datetime:
        """Get current time from time service."""
        if not self._time_service:
            raise RuntimeError("FATAL: TimeService not available! This is a critical system failure.")
        if hasattr(self._time_service, "now"):
            result = self._time_service.now()
            if isinstance(result, datetime):
                return result
        return datetime.now()

    async def record_metric(
        self,
        metric_name: str,
        value: float = 1.0,
        tags: Optional[Dict[str, str]] = None,
        handler_name: Optional[str] = None,  # Accept extra parameter
        **kwargs: Any,  # Accept telemetry-specific parameters
    ) -> None:
        """
        Record a metric by storing it as a memory in the graph.

        This creates a TSDBGraphNode and stores it via the MemoryService,
        implementing the unified telemetry flow.
        """
        try:
            if not self._memory_bus:
                logger.error("Memory bus not available for telemetry storage")
                return

            # Add standard telemetry tags
            metric_tags = tags or {}
            metric_tags.update(
                {"source": "telemetry", "metric_type": "operational", "timestamp": self._now().isoformat()}
            )

            # Add handler_name to tags if provided
            if handler_name:
                metric_tags["handler"] = handler_name

            # Store as memory via the bus
            result = await self._memory_bus.memorize_metric(
                metric_name=metric_name,
                value=value,
                tags=metric_tags,
                scope="local",  # Operational metrics use local scope
                handler_name="telemetry_service",
            )

            # Cache for quick access
            data_point = MetricDataPoint(
                metric_name=metric_name,
                value=value,
                timestamp=self._now(),
                tags=metric_tags,
                service_name="telemetry_service",
            )

            if metric_name not in self._recent_metrics:
                self._recent_metrics[metric_name] = []

            self._recent_metrics[metric_name].append(data_point)

            # Trim cache
            if len(self._recent_metrics[metric_name]) > self._max_cached_metrics:
                self._recent_metrics[metric_name] = self._recent_metrics[metric_name][-self._max_cached_metrics :]

            if result.status != MemoryOpStatus.OK:
                logger.error(f"Failed to store metric: {result}")

        except Exception as e:
            logger.error(f"Failed to record metric {metric_name}: {e}")

    async def _record_resource_usage(self, service_name: str, usage: ResourceUsage) -> None:
        """
        Record resource usage as multiple metrics in the graph (internal method).

        Each aspect of resource usage becomes a separate memory node,
        allowing for fine-grained introspection.
        """
        try:
            # Record each resource metric separately
            if usage.tokens_used:
                await self.record_metric(
                    f"{service_name}.tokens_used",
                    float(usage.tokens_used),
                    {"service": service_name, "resource_type": "tokens"},
                )

            if usage.tokens_input:
                await self.record_metric(
                    f"{service_name}.tokens_input",
                    float(usage.tokens_input),
                    {"service": service_name, "resource_type": "tokens", "direction": "input"},
                )

            if usage.tokens_output:
                await self.record_metric(
                    f"{service_name}.tokens_output",
                    float(usage.tokens_output),
                    {"service": service_name, "resource_type": "tokens", "direction": "output"},
                )

            if usage.cost_cents:
                await self.record_metric(
                    f"{service_name}.cost_cents",
                    usage.cost_cents,
                    {"service": service_name, "resource_type": "cost", "unit": "cents"},
                )

            if usage.carbon_grams:
                await self.record_metric(
                    f"{service_name}.carbon_grams",
                    usage.carbon_grams,
                    {"service": service_name, "resource_type": "carbon", "unit": "grams"},
                )

            if usage.energy_kwh:
                await self.record_metric(
                    f"{service_name}.energy_kwh",
                    usage.energy_kwh,
                    {"service": service_name, "resource_type": "energy", "unit": "kilowatt_hours"},
                )

        except Exception as e:
            logger.error(f"Failed to record resource usage for {service_name}: {e}")

    async def query_metrics(
        self,
        metric_name: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[MetricRecord]:
        """Query metrics from the graph memory.

        This uses the MemoryService's recall_timeseries capability to
        retrieve historical metric data.

        Args:
            metric_name: Name of metric to query
            start_time: Start of time window (optional)
            end_time: End of time window (optional)
            tags: Filter by tags (optional)

        Returns:
            List of typed MetricRecord objects

        Raises:
            MemoryBusUnavailableError: If memory bus not available
            MetricCollectionError: If query fails
        """
        from ciris_engine.logic.services.graph.telemetry_service.exceptions import (
            MemoryBusUnavailableError,
            MetricCollectionError,
        )
        from ciris_engine.logic.services.graph.telemetry_service.helpers import (
            calculate_query_time_window,
            convert_to_metric_record,
            filter_by_metric_name,
            filter_by_tags,
            filter_by_time_range,
        )
        from ciris_engine.schemas.services.graph.telemetry import MetricRecord

        if not self._memory_bus:
            raise MemoryBusUnavailableError("Memory bus not available for metric queries")

        try:
            # Calculate hours from time range using helper
            hours = calculate_query_time_window(start_time, end_time, self._now())

            # Recall time series data from memory
            timeseries_data = await self._memory_bus.recall_timeseries(
                scope="local",  # Operational metrics are in local scope
                hours=hours,
                start_time=start_time,
                end_time=end_time,
                handler_name="telemetry_service",
            )

            # Filter and convert to typed MetricRecord objects using helpers
            results: List[MetricRecord] = []
            for data in timeseries_data:
                # Apply filters using helper functions
                if not filter_by_metric_name(data, metric_name):
                    continue
                if not filter_by_tags(data, tags):
                    continue
                if not filter_by_time_range(data, start_time, end_time):
                    continue

                # Convert to MetricRecord using helper
                record = convert_to_metric_record(data)
                if record:
                    results.append(record)

            return results

        except (MemoryBusUnavailableError, MetricCollectionError):
            raise  # Re-raise our exceptions
        except Exception as e:
            raise MetricCollectionError(f"Failed to query metrics: {e}") from e

    async def get_metric_summary(self, metric_name: str, window_minutes: int = 60) -> Dict[str, float]:
        """Get metric summary statistics."""
        try:
            # Calculate time window
            end_time = self._now()
            start_time = end_time - timedelta(minutes=window_minutes)

            # Query metrics for the window
            metrics = await self.query_metrics(metric_name=metric_name, start_time=start_time, end_time=end_time)

            if not metrics:
                return {"count": 0.0, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}

            # Calculate summary statistics (MetricRecord objects now)
            values = [m.value for m in metrics if isinstance(m.value, (int, float))]

            return {
                "count": float(len(values)),
                "sum": float(sum(values)),
                "min": float(min(values)) if values else 0.0,
                "max": float(max(values)) if values else 0.0,
                "avg": float(sum(values) / len(values)) if values else 0.0,
            }

        except Exception as e:
            logger.error(f"Failed to get metric summary for {metric_name}: {e}")
            return {"count": 0.0, "sum": 0.0, "min": 0.0, "max": 0.0, "avg": 0.0}

    async def _get_service_status(
        self, service_name: Optional[str] = None
    ) -> Union[ServiceStatus, Dict[str, ServiceStatus]]:
        """
        Get service status by analyzing recent metrics from the graph (internal method).

        This demonstrates the agent's ability to introspect its own
        operational state through the unified memory system.
        """
        try:
            if service_name:
                # Get status for specific service
                recent_metrics = self._recent_metrics.get(f"{service_name}.tokens_used", [])
                last_metric = recent_metrics[-1] if recent_metrics else None

                return ServiceStatus(
                    service_name=service_name,
                    service_type="telemetry",
                    is_healthy=bool(last_metric),
                    uptime_seconds=0.0,  # Uptime tracked at service level
                    last_error=None,
                    metrics={"recent_tokens": last_metric.value if last_metric else 0.0},
                    custom_metrics=None,
                    last_health_check=last_metric.timestamp if last_metric else None,
                )
            else:
                # Get status for all services
                all_status: Dict[str, ServiceStatus] = {}

                # Extract unique service names from cached metrics
                service_names = set()
                for metric_name in self._recent_metrics.keys():
                    if "." in metric_name:
                        service_name = metric_name.split(".")[0]
                        service_names.add(service_name)

                for svc_name in service_names:
                    status = await self._get_service_status(svc_name)
                    if isinstance(status, ServiceStatus):
                        all_status[svc_name] = status

                return all_status

        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            if service_name:
                return ServiceStatus(
                    service_name=service_name,
                    service_type="telemetry",
                    is_healthy=False,
                    uptime_seconds=0.0,
                    last_error=str(e),
                    metrics={},
                    custom_metrics=None,
                    last_health_check=None,
                )
            else:
                # Return empty dict for all services case
                return {}

    def _get_resource_limits(self) -> ResourceLimits:
        """Get resource limits configuration (internal method)."""
        return self._resource_limits

    async def _process_system_snapshot(
        self, snapshot: SystemSnapshot, thought_id: str, task_id: Optional[str] = None
    ) -> TelemetrySnapshotResult:
        """
        Process a SystemSnapshot and convert it to graph memories (internal method).

        This is the main entry point for the unified telemetry flow from adapters.
        """
        try:
            if not self._memory_bus:
                logger.error("Memory bus not available for telemetry storage")
                return TelemetrySnapshotResult(
                    memories_created=0,
                    errors=["Memory bus not available"],
                    consolidation_triggered=False,
                    consolidation_result=None,
                    error="Memory bus not available",
                )

            results = TelemetrySnapshotResult(
                memories_created=0, errors=[], consolidation_triggered=False, consolidation_result=None, error=None
            )

            # 1. Store operational metrics from telemetry summary
            if snapshot.telemetry_summary:
                # Convert telemetry summary to telemetry data format
                telemetry_data = TelemetryData(
                    metrics={
                        "messages_processed_24h": snapshot.telemetry_summary.messages_processed_24h,
                        "thoughts_processed_24h": snapshot.telemetry_summary.thoughts_processed_24h,
                        "tasks_completed_24h": snapshot.telemetry_summary.tasks_completed_24h,
                        "errors_24h": snapshot.telemetry_summary.errors_24h,
                        "messages_current_hour": snapshot.telemetry_summary.messages_current_hour,
                        "thoughts_current_hour": snapshot.telemetry_summary.thoughts_current_hour,
                        "errors_current_hour": snapshot.telemetry_summary.errors_current_hour,
                        "tokens_last_hour": snapshot.telemetry_summary.tokens_last_hour,
                        "cost_last_hour_cents": snapshot.telemetry_summary.cost_last_hour_cents,
                        "carbon_last_hour_grams": snapshot.telemetry_summary.carbon_last_hour_grams,
                        "energy_last_hour_kwh": snapshot.telemetry_summary.energy_last_hour_kwh,
                        "error_rate_percent": snapshot.telemetry_summary.error_rate_percent,
                        "avg_thought_depth": snapshot.telemetry_summary.avg_thought_depth,
                        "queue_saturation": snapshot.telemetry_summary.queue_saturation,
                    },
                    events={},
                    # Remove counters field - not in TelemetryData schema
                )
                await store_telemetry_metrics(self, telemetry_data, thought_id, task_id)
                results.memories_created += 1

            # 2. Store resource usage - Note: no current_round_resources in SystemSnapshot
            # Resource data would come from telemetry_summary if needed

            # 3. Store behavioral data (task/thought summaries)
            if snapshot.current_task_details:
                behavioral_data = BehavioralData(
                    data_type="task",
                    content=(
                        snapshot.current_task_details.model_dump()
                        if hasattr(snapshot.current_task_details, "model_dump")
                        else {}
                    ),
                    metadata={"thought_id": thought_id},
                )
                await store_behavioral_data(self, behavioral_data, "task", thought_id)
                results.memories_created += 1

            if snapshot.current_thought_summary:
                behavioral_data = BehavioralData(
                    data_type="thought",
                    content=(
                        snapshot.current_thought_summary.model_dump()
                        if hasattr(snapshot.current_thought_summary, "model_dump")
                        else {}
                    ),
                    metadata={"thought_id": thought_id},
                )
                await store_behavioral_data(self, behavioral_data, "thought", thought_id)
                results.memories_created += 1

            # 4. Store social context (user profiles, channel info)
            if snapshot.user_profiles:
                await store_social_context(self, snapshot.user_profiles, snapshot.channel_context, thought_id)
                results.memories_created += 1

            # 5. Store identity context
            if snapshot.agent_identity or snapshot.identity_purpose:
                await store_identity_context(self, snapshot, thought_id)
                results.memories_created += 1

            # Consolidation is now handled by TSDBConsolidationService

            return results

        except Exception as e:
            logger.error(f"Failed to process system snapshot: {e}")
            return TelemetrySnapshotResult(
                memories_created=0,
                errors=[str(e)],
                consolidation_triggered=False,
                consolidation_result=None,
                error=str(e),
            )

    # Storage delegation methods for backward compatibility
    async def _store_telemetry_metrics(self, telemetry: TelemetryData, thought_id: str, task_id: Optional[str]) -> None:
        """Store telemetry data as operational memories."""
        await store_telemetry_metrics(self, telemetry, thought_id, task_id)

    async def _store_resource_usage(self, resources: ResourceData) -> None:
        """Store resource usage as operational memories."""
        await store_resource_usage(self, resources)

    async def _store_behavioral_data(self, data: BehavioralData, data_type: str, thought_id: str) -> None:
        """Store behavioral data (tasks/thoughts) as memories."""
        await store_behavioral_data(self, data, data_type, thought_id)

    async def _store_social_context(
        self, user_profiles: List[UserProfile], channel_context: Optional[SystemChannelContext], thought_id: str
    ) -> None:
        """Store social context as memories."""
        await store_social_context(self, user_profiles, channel_context, thought_id)

    async def _store_identity_context(self, snapshot: SystemSnapshot, thought_id: str) -> None:
        """Store identity-related context as memories."""
        await store_identity_context(self, snapshot, thought_id)

    async def start(self) -> None:
        """Start the telemetry service."""
        from datetime import datetime, timezone

        # Don't call super() as BaseService has async start
        self._started = True
        self._start_time = datetime.now(timezone.utc)
        logger.debug("GraphTelemetryService started - routing all metrics through memory graph")

    async def stop(self) -> None:
        """Stop the telemetry service."""
        # Mark as stopped first to prevent new operations
        self._started = False

        # Try to store a final metric, but don't block shutdown if it fails
        try:
            # Use a short timeout to avoid hanging
            await asyncio.wait_for(
                self.record_metric(
                    "telemetry_service.shutdown", 1.0, {"event": "service_stop", "timestamp": self._now().isoformat()}
                ),
                timeout=1.0,
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug(f"Could not record shutdown metric: {e}")

        logger.debug("GraphTelemetryService stopped")

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect telemetry-specific metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate cache size
        cache_size_mb = 0.0
        try:
            # Estimate size of cached metrics
            cache_size = sys.getsizeof(self._recent_metrics) + sys.getsizeof(self._summary_cache)
            cache_size_mb = cache_size / 1024 / 1024
        except Exception:
            pass

        # Calculate metrics statistics
        total_metrics_stored = sum(len(metrics_list) for metrics_list in self._recent_metrics.values())
        unique_metric_types = len(self._recent_metrics.keys())

        # Get recent metric activity
        recent_metrics_per_minute = 0.0
        if self._recent_metrics:
            # Count metrics from last minute
            now = self._now()
            one_minute_ago = now - timedelta(minutes=1)
            for metric_list in self._recent_metrics.values():
                for metric in metric_list:
                    if hasattr(metric, "timestamp") and metric.timestamp >= one_minute_ago:
                        recent_metrics_per_minute += 1.0

        # Add telemetry-specific metrics
        metrics.update(
            {
                "total_metrics_cached": float(total_metrics_stored),
                "unique_metric_types": float(unique_metric_types),
                "summary_cache_entries": float(len(self._summary_cache)),
                "metrics_per_minute": recent_metrics_per_minute,
                "cache_size_mb": cache_size_mb,
                "max_cached_metrics_per_type": float(self._max_cached_metrics),
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all telemetry service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Calculate telemetry-specific metrics using real service state

        # Total metrics collected from cached metrics
        total_metrics_collected = sum(len(metrics_list) for metrics_list in self._recent_metrics.values())

        # Number of services monitored (from telemetry aggregator if available)
        services_monitored = 0
        if self._telemetry_aggregator:
            # Count total services across all categories
            for category, services_list in self._telemetry_aggregator.CATEGORIES.items():
                services_monitored += len(services_list)
        else:
            # Fallback: count unique services from cached metrics
            unique_services = set()
            for metric_list in self._recent_metrics.values():
                for metric in metric_list:
                    if hasattr(metric, "tags") and metric.tags and "service" in metric.tags:
                        unique_services.add(metric.tags["service"])
            services_monitored = len(unique_services)

        # Cache hits from summary cache
        cache_hits = len(self._summary_cache)

        # Collection errors from error count
        collection_errors = metrics.get("error_count", 0.0)

        # Service uptime in seconds
        uptime_seconds = metrics.get("uptime_seconds", 0.0)

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "telemetry_metrics_collected": float(total_metrics_collected),
                "telemetry_services_monitored": float(services_monitored),
                "telemetry_cache_hits": float(cache_hits),
                "telemetry_collection_errors": float(collection_errors),
                "telemetry_uptime_seconds": float(uptime_seconds),
            }
        )

        return metrics

    def get_node_type(self) -> str:
        """Get the type of nodes this service manages."""
        return "TELEMETRY"

    async def get_metric_count(self) -> int:
        """Get the total count of metrics stored in the system.

        This counts metrics from TSDB_DATA nodes in the graph which stores
        all telemetry data points.
        """
        try:
            if not self._memory_bus:
                logger.debug("Memory bus not available, returning 0 metric count")
                return 0

            # Query the database directly to count TSDB_DATA nodes
            from ciris_engine.logic.persistence import get_db_connection

            # Get the memory service to access its db_path
            memory_service = await self._memory_bus.get_service(handler_name="telemetry_service")
            if not memory_service:
                logger.debug("Memory service not available, returning 0 metric count")
                return 0

            db_path = getattr(memory_service, "db_path", None)
            with get_db_connection(db_path=db_path) as conn:
                cursor = conn.cursor()
                # Count all TSDB_DATA nodes
                cursor.execute("SELECT COUNT(*) as cnt FROM graph_nodes WHERE node_type = 'tsdb_data'")
                result = cursor.fetchone()
                # Handle both dict (PostgreSQL RealDictCursor) and tuple (SQLite Row) formats
                if result is None:
                    count = 0
                elif isinstance(result, dict):
                    count = result.get("cnt", 0)
                else:
                    count = result[0]

                logger.debug(f"Total metric count from graph nodes: {count}")
                return count

        except Exception as e:
            logger.error(f"Failed to get metric count: {type(e).__name__}: {e}", exc_info=True)
            return 0

    async def get_telemetry_summary(self) -> "TelemetrySummary":
        """Get aggregated telemetry summary for system snapshot.

        Uses intelligent caching to avoid overloading the persistence layer:
        - Current task metrics: No cache (always fresh)
        - Hour metrics: 1 minute cache
        - Day metrics: 5 minute cache

        Raises:
            MemoryBusUnavailableError: If memory bus not available
            MetricCollectionError: If metric collection fails
            ServiceStartTimeUnavailableError: If start_time not set
            NoThoughtDataError: If no thought data available (may be acceptable during startup)
            RuntimeControlBusUnavailableError: If runtime control bus not available
            QueueStatusUnavailableError: If queue status cannot be retrieved
        """
        from ciris_engine.logic.services.graph.telemetry_service.exceptions import (
            MemoryBusUnavailableError,
            NoThoughtDataError,
            QueueStatusUnavailableError,
            RuntimeControlBusUnavailableError,
        )
        from ciris_engine.logic.services.graph.telemetry_service.helpers import (
            METRIC_TYPES,
            build_telemetry_summary,
            calculate_average_latencies,
            calculate_error_rate,
            check_summary_cache,
            collect_circuit_breaker_state,
            collect_metric_aggregates,
            get_average_thought_depth,
            get_queue_saturation,
            get_service_uptime,
            store_summary_cache,
        )

        now = self._now()

        # Always collect fresh circuit breaker state (not cacheable, changes rapidly)
        circuit_breaker_state = collect_circuit_breaker_state(self._runtime)
        if not circuit_breaker_state:
            circuit_breaker_state = {}

        # Check cache
        cached: TelemetrySummary | None = check_summary_cache(
            self._summary_cache, "telemetry_summary", now, self._summary_cache_ttl_seconds
        )
        if cached:
            logger.debug("Returning cached telemetry summary with fresh circuit breaker data")
            # Update cached summary with fresh circuit breaker state
            cached.circuit_breaker = circuit_breaker_state
            return cached

        # Fail fast if memory bus not available
        if not self._memory_bus:
            raise MemoryBusUnavailableError("Memory bus not available for telemetry queries")

        # Define time windows
        window_end = now
        window_start_24h = now - timedelta(hours=24)
        window_start_1h = now - timedelta(hours=1)

        # Collect metrics (raises on error, no fallbacks)
        aggregates = await collect_metric_aggregates(self, METRIC_TYPES, window_start_24h, window_start_1h, window_end)

        # Get external data (may raise exceptions - caller must handle)
        try:
            avg_thought_depth = await get_average_thought_depth(self._memory_bus, window_start_24h)
        except NoThoughtDataError:
            # Acceptable during startup or low-activity periods
            logger.info("No thought data available in last 24h - setting to 0.0")
            avg_thought_depth = 0.0

        try:
            queue_saturation = await get_queue_saturation(getattr(self, "_runtime_control_bus", None))
        except (RuntimeControlBusUnavailableError, QueueStatusUnavailableError) as e:
            # Acceptable if runtime control not available
            logger.info(f"Queue saturation unavailable: {e} - setting to 0.0")
            queue_saturation = 0.0

        uptime = get_service_uptime(self._start_time if hasattr(self, "_start_time") else None, now)

        # Calculate derived metrics
        error_rate = calculate_error_rate(
            aggregates.errors_24h, aggregates.messages_24h + aggregates.thoughts_24h + aggregates.tasks_24h
        )
        service_latency_ms = calculate_average_latencies(aggregates.service_latency)

        # circuit_breaker_state already collected above (before cache check)

        # Build result
        summary = build_telemetry_summary(
            window_start_24h,
            window_end,
            uptime,
            aggregates,
            error_rate,
            avg_thought_depth,
            queue_saturation,
            service_latency_ms,
            circuit_breaker=circuit_breaker_state,
        )

        # Cache and return
        store_summary_cache(self._summary_cache, "telemetry_summary", now, summary)
        return summary

    async def get_continuity_summary(self) -> Optional[ContinuitySummary]:
        """Get continuity awareness summary from startup/shutdown lifecycle events.

        Queries memory service for all startup and shutdown nodes tagged with
        'continuity_awareness' and builds a complete continuity history.

        Returns:
            ContinuitySummary with lifecycle metrics, or None if memory service unavailable
        """
        from ciris_engine.logic.services.graph.telemetry_service.helpers import (
            build_continuity_summary_from_memory,
            check_summary_cache,
            store_summary_cache,
        )

        now = self._now()

        # Check cache
        cached = check_summary_cache(self._summary_cache, "continuity_summary", now, self._summary_cache_ttl_seconds)
        if cached:
            logger.debug("Returning cached continuity summary")
            return cached  # type: ignore[no-any-return]

        # Build from memory nodes
        continuity = await build_continuity_summary_from_memory(
            self._memory_bus, self._time_service if hasattr(self, "_time_service") else None, self._start_time
        )

        # Cache and return
        if continuity:
            store_summary_cache(self._summary_cache, "continuity_summary", now, continuity)

        return continuity

    # Required methods for BaseGraphService

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.TELEMETRY

    def _init_telemetry_aggregator(self) -> None:
        """Initialize telemetry aggregator with debug logging."""
        if self._service_registry:
            logger.debug(f"[TELEMETRY] Creating TelemetryAggregator with registry {id(self._service_registry)}")
            try:
                all_services = self._service_registry.get_all_services()
                service_count = len(all_services) if hasattr(all_services, "__len__") else 0
                logger.debug(f"[TELEMETRY] Registry has {service_count} services")
                service_names = [s.__class__.__name__ for s in all_services] if all_services else []
                logger.debug(f"[TELEMETRY] Services in registry: {service_names}")
            except (TypeError, AttributeError):
                logger.debug("[TELEMETRY] Registry is mock/test mode")

            logger.debug(f"[TELEMETRY] Runtime available: {self._runtime is not None}")
            if self._runtime:
                logger.debug(f"[TELEMETRY] Runtime has bus_manager: {hasattr(self._runtime, 'bus_manager')}")
                logger.debug(f"[TELEMETRY] Runtime has memory_service: {hasattr(self._runtime, 'memory_service')}")
            else:
                logger.debug("[TELEMETRY] Runtime is None when creating aggregator!")

            self._telemetry_aggregator = TelemetryAggregator(
                service_registry=self._service_registry, time_service=self._time_service, runtime=self._runtime
            )
            logger.debug(f"[TELEMETRY] TelemetryAggregator created with runtime={self._runtime is not None}")

    def _check_cache(self, cache_key: str, now: datetime) -> Optional[AggregatedTelemetryResponse]:
        """Check cache for valid telemetry data."""
        if self._telemetry_aggregator and cache_key in self._telemetry_aggregator.cache:
            cached_time, cached_data = self._telemetry_aggregator.cache[cache_key]
            if now - cached_time < self._telemetry_aggregator.cache_ttl:
                # Mark cached response as cache hit
                if isinstance(cached_data, AggregatedTelemetryResponse):
                    if cached_data.metadata:
                        cached_data.metadata.cache_hit = True
                    return cached_data
                return cached_data
        return None

    def _convert_telemetry_to_services(
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
    ) -> Dict[str, ServiceTelemetryData]:
        """Convert nested telemetry dict to flat service dict."""
        services_data = {}
        for category, services in telemetry.items():
            if isinstance(services, dict):
                for service_name, service_info in services.items():
                    if isinstance(service_info, ServiceTelemetryData):
                        services_data[service_name] = service_info
                    elif isinstance(service_info, dict):
                        services_data[service_name] = ServiceTelemetryData(
                            healthy=service_info.get("healthy", False),
                            uptime_seconds=service_info.get("uptime_seconds"),
                            error_count=service_info.get("error_count"),
                            requests_handled=service_info.get("request_count"),
                            error_rate=service_info.get("error_rate"),
                            memory_mb=service_info.get("memory_mb"),
                            custom_metrics=service_info.get("custom_metrics"),
                        )
        return services_data

    async def get_aggregated_telemetry(self) -> AggregatedTelemetryResponse:
        """
        Get aggregated telemetry from all services using parallel collection.

        Returns enterprise telemetry with all service metrics collected in parallel.
        """
        # Initialize aggregator if needed
        if not self._telemetry_aggregator and self._service_registry:
            self._init_telemetry_aggregator()

        if not self._telemetry_aggregator:
            logger.warning("No telemetry aggregator available")
            return AggregatedTelemetryResponse(
                system_healthy=False,
                services_online=0,
                services_total=0,
                overall_error_rate=0.0,
                overall_uptime_seconds=0,
                total_errors=0,
                total_requests=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                error="Telemetry aggregator not initialized",
            )

        # Check cache first
        cache_key = "aggregated_telemetry"
        now = datetime.now(timezone.utc)

        cached_result = self._check_cache(cache_key, now)
        if cached_result:
            # Cache returns AggregatedTelemetryResponse
            return cached_result

        # Collect from all services in parallel
        telemetry = await self._telemetry_aggregator.collect_all_parallel()

        # Calculate aggregates
        aggregates = self._telemetry_aggregator.calculate_aggregates(telemetry)

        # Convert nested telemetry dict to flat service dict
        services_data = self._convert_telemetry_to_services(telemetry)

        # Combine telemetry and aggregates into typed response
        result = AggregatedTelemetryResponse(
            system_healthy=aggregates.get("system_healthy", False),
            services_online=aggregates.get("services_online", 0),
            services_total=aggregates.get("services_total", 0),
            overall_error_rate=aggregates.get("overall_error_rate", 0.0),
            overall_uptime_seconds=aggregates.get("overall_uptime_seconds", 0),
            total_errors=aggregates.get("total_errors", 0),
            total_requests=aggregates.get("total_requests", 0),
            timestamp=aggregates.get("timestamp", now.isoformat()),
            services=services_data,
            metadata=AggregatedTelemetryMetadata(
                collection_method="parallel", cache_ttl_seconds=30, timestamp=now.isoformat()
            ),
        )

        # Cache the result
        self._telemetry_aggregator.cache[cache_key] = (now, result)

        return result

    async def _store_correlation(self, correlation: ServiceCorrelation) -> None:
        """
        Store a service correlation (trace span) in the memory graph.

        Correlations are always linked to tasks/thoughts unless they're edge observations
        that the adaptive filter chose not to create a task for.
        """
        try:
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            # Extract task and thought IDs from the correlation's request data if available
            task_id = None
            thought_id = None

            if correlation.request_data:
                # Try to extract from request data
                if hasattr(correlation.request_data, "task_id"):
                    task_id = correlation.request_data.task_id
                if hasattr(correlation.request_data, "thought_id"):
                    thought_id = correlation.request_data.thought_id
                elif isinstance(correlation.request_data, dict):
                    task_id = correlation.request_data.get("task_id")
                    thought_id = correlation.request_data.get("thought_id")

            # Create a graph node for the correlation
            node_id = f"correlation/{correlation.correlation_id}"

            # Build attributes including task/thought linkage
            attributes: JSONDict = {
                "correlation_id": correlation.correlation_id,
                "correlation_type": (
                    correlation.correlation_type.value
                    if hasattr(correlation.correlation_type, "value")
                    else str(correlation.correlation_type)
                ),
                "service_type": correlation.service_type,
                "handler_name": correlation.handler_name,
                "action_type": correlation.action_type,
                "status": correlation.status.value if hasattr(correlation.status, "value") else str(correlation.status),
                "timestamp": correlation.timestamp.isoformat() if correlation.timestamp else self._now().isoformat(),
                "task_id": task_id,  # Link to task if available
                "thought_id": thought_id,  # Link to thought if available
            }

            # Add trace context if available
            if correlation.trace_context:
                trace_ctx = correlation.trace_context
                attributes.update(
                    {
                        "trace_id": trace_ctx.trace_id if hasattr(trace_ctx, "trace_id") else None,
                        "span_id": trace_ctx.span_id if hasattr(trace_ctx, "span_id") else None,
                        "parent_span_id": trace_ctx.parent_span_id if hasattr(trace_ctx, "parent_span_id") else None,
                        "span_name": trace_ctx.span_name if hasattr(trace_ctx, "span_name") else None,
                        "span_kind": trace_ctx.span_kind if hasattr(trace_ctx, "span_kind") else None,
                    }
                )

            # Add response data if available
            if correlation.response_data:
                resp = correlation.response_data
                if hasattr(resp, "execution_time_ms"):
                    attributes["execution_time_ms"] = resp.execution_time_ms
                if hasattr(resp, "success"):
                    attributes["success"] = resp.success
                if hasattr(resp, "error_message"):
                    attributes["error_message"] = resp.error_message

            # Don't store as graph node - telemetry correlations go in correlations DB
            # Just keep in recent cache for quick access

            # Keep a recent cache for quick access
            if not hasattr(self, "_recent_correlations"):
                self._recent_correlations = []

            self._recent_correlations.append(correlation)
            # Keep only last 1000 correlations in memory
            if len(self._recent_correlations) > 1000:
                self._recent_correlations = self._recent_correlations[-1000:]

        except Exception as e:
            logger.error(f"Failed to store correlation {correlation.correlation_id}: {e}")
            # Don't raise - we don't want telemetry failures to break the application

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return [
            "record_metric",
            "query_metrics",
            "get_metric_summary",
            "get_metric_count",
            "get_telemetry_summary",
            "process_system_snapshot",
            "get_resource_usage",
            "get_telemetry_status",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        # Check parent dependencies (memory bus)
        if not super()._check_dependencies():
            return False

        # Telemetry has no additional required dependencies beyond memory bus
        return True
