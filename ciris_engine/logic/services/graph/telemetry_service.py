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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

# Optional import for psutil
try:
    import psutil  # type: ignore[import,unused-ignore]

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore[assignment,no-redef,unused-ignore]
    PSUTIL_AVAILABLE = False

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.base_graph_service import BaseGraphService
from ciris_engine.protocols.runtime.base import GraphServiceProtocol as TelemetryServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.protocols_core import MetricDataPoint, ResourceLimits
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.runtime.system_context import ChannelContext as SystemChannelContext
from ciris_engine.schemas.runtime.system_context import SystemSnapshot, TelemetrySummary, UserProfile
from ciris_engine.schemas.services.core import ServiceStatus
from ciris_engine.schemas.services.graph.telemetry import (
    BehavioralData,
    ResourceData,
    TelemetryData,
    TelemetrySnapshotResult,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus

logger = logging.getLogger(__name__)


class MemoryType(str, Enum):
    """Types of memories in the unified system."""

    OPERATIONAL = "operational"  # Metrics, logs, performance data
    BEHAVIORAL = "behavioral"  # Actions, decisions, patterns
    SOCIAL = "social"  # Interactions, relationships, gratitude
    IDENTITY = "identity"  # Self-knowledge, capabilities, values
    WISDOM = "wisdom"  # Learned principles, insights


class GracePolicy(str, Enum):
    """Policies for applying grace in memory consolidation."""

    FORGIVE_ERRORS = "forgive_errors"  # Consolidate errors into learning
    EXTEND_PATIENCE = "extend_patience"  # Allow more time before judging
    ASSUME_GOOD_INTENT = "assume_good_intent"  # Interpret ambiguity positively
    RECIPROCAL_GRACE = "reciprocal_grace"  # Mirror the grace we receive


@dataclass
class ConsolidationCandidate:
    """A set of memories that could be consolidated."""

    memory_ids: List[str]
    memory_type: MemoryType
    time_span: timedelta
    total_size: int
    grace_applicable: bool
    grace_reasons: List[str]


class GraphTelemetryService(BaseGraphService, TelemetryServiceProtocol):
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
        self._recent_metrics: Dict[str, List[MetricDataPoint]] = {}
        self._max_cached_metrics = 100

        # Cache for telemetry summaries to avoid slamming persistence
        self._summary_cache: Dict[str, Tuple[datetime, TelemetrySummary]] = {}
        self._summary_cache_ttl_seconds = 60  # Cache for 1 minute

        # Memory tracking
        self._process = psutil.Process() if PSUTIL_AVAILABLE else None

        # Consolidation settings

    def _set_service_registry(self, registry: object) -> None:
        """Set the service registry for accessing memory bus and time service (internal method)."""
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
    ) -> List[Dict[str, Union[str, float, datetime, Dict[str, str]]]]:
        """
        Query metrics from the graph memory.

        This uses the MemoryService's recall_timeseries capability to
        retrieve historical metric data.
        """
        try:
            if not self._memory_bus:
                logger.error("Memory bus not available for metric queries")
                return []

            # Calculate hours from time range
            hours = 24  # Default
            if start_time and end_time:
                hours = int((end_time - start_time).total_seconds() / 3600)
            elif start_time:
                hours = int((self._now() - start_time).total_seconds() / 3600)

            # Recall time series data from memory
            # Pass actual start/end times for precise filtering
            timeseries_data = await self._memory_bus.recall_timeseries(
                scope="local",  # Operational metrics are in local scope
                hours=hours,
                start_time=start_time,
                end_time=end_time,
                handler_name="telemetry_service",
            )

            # Convert to dict format
            results: List[Dict[str, Union[str, float, datetime, Dict[str, str]]]] = []
            for data in timeseries_data:
                # Filter by metric name
                if data.metric_name != metric_name:
                    continue

                # Filter by tags if specified
                if tags:
                    data_tags = data.tags or {}
                    if not all(data_tags.get(k) == v for k, v in tags.items()):
                        continue

                # Filter by time range
                if data.timestamp:
                    # timestamp is always a datetime per TimeSeriesDataPoint type
                    ts = data.timestamp

                    if ts is not None:

                        if start_time and ts < start_time:
                            continue
                        if end_time and ts > end_time:
                            continue

                # Create result dict
                if data.metric_name and data.value is not None:
                    results.append(
                        {
                            "metric_name": data.metric_name,
                            "value": data.value,
                            "timestamp": data.timestamp,
                            "tags": data.tags or {},
                        }
                    )

            return results

        except Exception as e:
            logger.error(f"Failed to query metrics: {e}")
            return []

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

            # Calculate summary statistics
            values = [m["value"] for m in metrics if isinstance(m["value"], (int, float))]

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
                await self._store_telemetry_metrics(telemetry_data, thought_id, task_id)
                results.memories_created += 1

            # 2. Store resource usage - Note: no current_round_resources in SystemSnapshot
            # Resource data would come from telemetry_summary if needed

            # 3. Store behavioral data (task/thought summaries)
            if snapshot.current_task_details:
                behavioral_data = BehavioralData(
                    data_type="task",
                    content=(
                        snapshot.current_task_details.dict() if hasattr(snapshot.current_task_details, "dict") else {}
                    ),
                    metadata={"thought_id": thought_id},
                )
                await self._store_behavioral_data(behavioral_data, "task", thought_id)
                results.memories_created += 1

            if snapshot.current_thought_summary:
                behavioral_data = BehavioralData(
                    data_type="thought",
                    content=(
                        snapshot.current_thought_summary.dict()
                        if hasattr(snapshot.current_thought_summary, "dict")
                        else {}
                    ),
                    metadata={"thought_id": thought_id},
                )
                await self._store_behavioral_data(behavioral_data, "thought", thought_id)
                results.memories_created += 1

            # 4. Store social context (user profiles, channel info)
            if snapshot.user_profiles:
                await self._store_social_context(snapshot.user_profiles, snapshot.channel_context, thought_id)
                results.memories_created += 1

            # 5. Store identity context
            if snapshot.agent_identity or snapshot.identity_purpose:
                await self._store_identity_context(snapshot, thought_id)
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

    async def _store_telemetry_metrics(self, telemetry: TelemetryData, thought_id: str, task_id: Optional[str]) -> None:
        """Store telemetry data as operational memories."""
        # Process metrics
        for key, value in telemetry.metrics.items():
            await self.record_metric(
                f"telemetry.{key}",
                float(value),
                {"thought_id": thought_id, "task_id": task_id or "", "memory_type": MemoryType.OPERATIONAL.value},
            )

        # Process events
        for event_key, event_value in telemetry.events.items():
            await self.record_metric(
                f"telemetry.event.{event_key}",
                1.0,  # Event occurrence
                {
                    "thought_id": thought_id,
                    "task_id": task_id or "",
                    "memory_type": MemoryType.OPERATIONAL.value,
                    "event_value": str(event_value),
                },
            )

    async def _store_resource_usage(self, resources: ResourceData, thought_id: str, task_id: Optional[str]) -> None:
        """Store resource usage as operational memories."""
        if resources.llm:
            # Extract only the fields that ResourceUsage expects
            from ciris_engine.schemas.services.graph.telemetry import LLMUsageData

            # Convert dict to LLMUsageData first
            llm_data = LLMUsageData(
                tokens_used=(
                    resources.llm.get("tokens_used")
                    if isinstance(resources.llm.get("tokens_used"), (int, float))
                    else None
                ),
                tokens_input=(
                    resources.llm.get("tokens_input")
                    if isinstance(resources.llm.get("tokens_input"), (int, float))
                    else None
                ),
                tokens_output=(
                    resources.llm.get("tokens_output")
                    if isinstance(resources.llm.get("tokens_output"), (int, float))
                    else None
                ),
                cost_cents=(
                    resources.llm.get("cost_cents")
                    if isinstance(resources.llm.get("cost_cents"), (int, float))
                    else None
                ),
                carbon_grams=(
                    resources.llm.get("carbon_grams")
                    if isinstance(resources.llm.get("carbon_grams"), (int, float))
                    else None
                ),
                energy_kwh=(
                    resources.llm.get("energy_kwh")
                    if isinstance(resources.llm.get("energy_kwh"), (int, float))
                    else None
                ),
                model_used=(
                    resources.llm.get("model_used") if isinstance(resources.llm.get("model_used"), str) else None
                ),
            )

            # Create ResourceUsage directly with proper types
            usage = ResourceUsage(
                tokens_used=int(llm_data.tokens_used) if llm_data.tokens_used is not None else 0,
                tokens_input=int(llm_data.tokens_input) if llm_data.tokens_input is not None else 0,
                tokens_output=int(llm_data.tokens_output) if llm_data.tokens_output is not None else 0,
                cost_cents=float(llm_data.cost_cents) if llm_data.cost_cents is not None else 0.0,
                carbon_grams=float(llm_data.carbon_grams) if llm_data.carbon_grams is not None else 0.0,
                energy_kwh=float(llm_data.energy_kwh) if llm_data.energy_kwh is not None else 0.0,
                model_used=llm_data.model_used if llm_data.model_used is not None else None,
            )
            await self._record_resource_usage("llm_service", usage)

    async def _store_behavioral_data(self, data: BehavioralData, data_type: str, thought_id: str) -> None:
        """Store behavioral data (tasks/thoughts) as memories."""
        node = GraphNode(
            id=f"behavioral_{thought_id}_{data_type}",
            type=NodeType.BEHAVIORAL,
            scope=GraphScope.LOCAL,
            updated_by="telemetry_service",
            updated_at=self._now(),
            attributes={
                "data_type": data.data_type,
                "thought_id": thought_id,
                "content": data.content,
                "metadata": data.metadata,
                "memory_type": MemoryType.BEHAVIORAL.value,
                "tags": {"thought_id": thought_id, "data_type": data_type},
            },
        )

        if self._memory_bus:
            await self._memory_bus.memorize(node=node, handler_name="telemetry_service", metadata={"behavioral": True})

    async def _store_social_context(
        self, user_profiles: List[UserProfile], channel_context: Optional[SystemChannelContext], thought_id: str
    ) -> None:
        """Store social context as memories."""
        node = GraphNode(
            id=f"social_{thought_id}",
            type=NodeType.SOCIAL,
            scope=GraphScope.LOCAL,
            updated_by="telemetry_service",
            updated_at=self._now(),
            attributes={
                "user_profiles": [p.dict() for p in user_profiles],
                "channel_context": channel_context.dict() if channel_context else None,
                "memory_type": MemoryType.SOCIAL.value,
                "tags": {"thought_id": thought_id, "user_count": str(len(user_profiles))},
            },
        )

        if self._memory_bus:
            await self._memory_bus.memorize(node=node, handler_name="telemetry_service", metadata={"social": True})

    async def _store_identity_context(self, snapshot: SystemSnapshot, thought_id: str) -> None:
        """Store identity-related context as memories."""
        # Extract agent name from identity data if available
        agent_name = None
        if snapshot.agent_identity and isinstance(snapshot.agent_identity, dict):
            agent_name = snapshot.agent_identity.get("name") or snapshot.agent_identity.get("agent_name")

        node = GraphNode(
            id=f"identity_{thought_id}",
            type=NodeType.IDENTITY,
            scope=GraphScope.IDENTITY,
            updated_by="telemetry_service",
            updated_at=self._now(),
            attributes={
                "agent_name": agent_name,
                "identity_purpose": snapshot.identity_purpose,
                "identity_capabilities": snapshot.identity_capabilities,
                "identity_restrictions": snapshot.identity_restrictions,
                "memory_type": MemoryType.IDENTITY.value,
                "tags": {"thought_id": thought_id, "has_purpose": str(bool(snapshot.identity_purpose))},
            },
        )

        if self._memory_bus:
            await self._memory_bus.memorize(node=node, handler_name="telemetry_service", metadata={"identity": True})

    async def start(self) -> None:
        """Start the telemetry service."""
        # Don't call super() as BaseService has async start
        self._started = True
        logger.info("GraphTelemetryService started - routing all metrics through memory graph")

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

        logger.info("GraphTelemetryService stopped")

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
                cursor.execute("SELECT COUNT(*) FROM graph_nodes WHERE node_type = 'tsdb_data'")
                result = cursor.fetchone()
                count = result[0] if result else 0

                logger.debug(f"Total metric count from graph nodes: {count}")
                return count

        except Exception as e:
            logger.error(f"Failed to get metric count: {e}")
            return 0

    async def get_telemetry_summary(self) -> TelemetrySummary:
        """Get aggregated telemetry summary for system snapshot.

        Uses intelligent caching to avoid overloading the persistence layer:
        - Current task metrics: No cache (always fresh)
        - Hour metrics: 1 minute cache
        - Day metrics: 5 minute cache
        """
        now = self._now()

        # Check cache first for expensive queries
        cache_key = "telemetry_summary"
        if cache_key in self._summary_cache:
            cached_time, cached_summary = self._summary_cache[cache_key]
            if (now - cached_time).total_seconds() < self._summary_cache_ttl_seconds:
                logger.debug("Returning cached telemetry summary")
                return cached_summary

        # If memory bus is not available yet (during startup), return empty summary
        if not self._memory_bus:
            logger.debug("Memory bus not available yet, returning empty telemetry summary")
            return TelemetrySummary(
                window_start=now - timedelta(hours=24),
                window_end=now,
                uptime_seconds=0.0,
                messages_processed_24h=0,
                thoughts_processed_24h=0,
                tasks_completed_24h=0,
                errors_24h=0,
                messages_current_hour=0,
                thoughts_current_hour=0,
                errors_current_hour=0,
                tokens_last_hour=0.0,
                cost_last_hour_cents=0.0,
                carbon_last_hour_grams=0.0,
                energy_last_hour_kwh=0.0,
                tokens_24h=0.0,
                cost_24h_cents=0.0,
                carbon_24h_grams=0.0,
                energy_24h_kwh=0.0,
                error_rate_percent=0.0,
                avg_thought_depth=0.0,
                queue_saturation=0.0,
            )

        # Window boundaries
        window_end = now
        window_start_24h = now - timedelta(hours=24)
        window_start_1h = now - timedelta(hours=1)

        # Initialize counters
        tokens_24h = 0
        tokens_1h = 0
        cost_24h_cents = 0.0
        cost_1h_cents = 0.0
        carbon_24h_grams = 0.0
        carbon_1h_grams = 0.0
        energy_24h_kwh = 0.0
        energy_1h_kwh = 0.0

        messages_24h = 0
        messages_1h = 0
        thoughts_24h = 0
        thoughts_1h = 0
        tasks_24h = 0
        errors_24h = 0
        errors_1h = 0

        service_calls: Dict[str, int] = {}
        service_errors: Dict[str, int] = {}
        service_latency: Dict[str, List[float]] = {}

        try:
            # Query different metric types
            metric_types = [
                ("llm.tokens.total", "tokens"),
                ("llm.cost.cents", "cost"),
                ("llm.environmental.carbon_grams", "carbon"),
                ("llm.environmental.energy_kwh", "energy"),
                ("llm.latency.ms", "latency"),
                ("message.processed", "messages"),
                ("thought.processed", "thoughts"),
                ("task.completed", "tasks"),
                ("error.occurred", "errors"),
            ]

            for metric_name, metric_type in metric_types:
                # Get 24h data
                day_metrics = await self.query_metrics(
                    metric_name=metric_name, start_time=window_start_24h, end_time=window_end
                )

                for metric in day_metrics:
                    raw_value = metric.get("value", 0)
                    # Ensure value is numeric
                    if not isinstance(raw_value, (int, float)):
                        continue
                    value: Union[int, float] = raw_value

                    timestamp = metric.get("timestamp")
                    tags_raw = metric.get("tags", {})
                    tags: Dict[str, str] = tags_raw if isinstance(tags_raw, dict) else {}

                    # Convert timestamp to datetime if needed
                    dt_timestamp: Optional[datetime] = None
                    if isinstance(timestamp, datetime):
                        dt_timestamp = timestamp
                        # Ensure timezone awareness
                        if dt_timestamp.tzinfo is None:
                            dt_timestamp = dt_timestamp.replace(tzinfo=timezone.utc)
                    elif isinstance(timestamp, str):
                        try:
                            dt_timestamp = datetime.fromisoformat(timestamp)
                            # Ensure timezone awareness
                            if dt_timestamp.tzinfo is None:
                                dt_timestamp = dt_timestamp.replace(tzinfo=timezone.utc)
                        except Exception:
                            continue
                    else:
                        continue  # Skip if timestamp is invalid

                    # Aggregate by time window
                    if metric_type == "tokens":
                        tokens_24h += int(value)
                        if dt_timestamp and dt_timestamp >= window_start_1h:
                            tokens_1h += int(value)
                    elif metric_type == "cost":
                        cost_24h_cents += float(value)
                        if dt_timestamp and dt_timestamp >= window_start_1h:
                            cost_1h_cents += float(value)
                    elif metric_type == "carbon":
                        carbon_24h_grams += float(value)
                        if dt_timestamp and dt_timestamp >= window_start_1h:
                            carbon_1h_grams += float(value)
                    elif metric_type == "energy":
                        energy_24h_kwh += float(value)
                        if dt_timestamp and dt_timestamp >= window_start_1h:
                            energy_1h_kwh += float(value)
                    elif metric_type == "messages":
                        messages_24h += int(value)
                        if dt_timestamp and dt_timestamp >= window_start_1h:
                            messages_1h += int(value)
                    elif metric_type == "thoughts":
                        thoughts_24h += int(value)
                        if dt_timestamp and dt_timestamp >= window_start_1h:
                            thoughts_1h += int(value)
                    elif metric_type == "tasks":
                        tasks_24h += int(value)
                    elif metric_type == "errors":
                        errors_24h += int(value)
                        if dt_timestamp and dt_timestamp >= window_start_1h:
                            errors_1h += int(value)
                        # Track errors by service
                        service = tags.get("service", "unknown")
                        service_errors[service] = service_errors.get(service, 0) + 1
                    elif metric_type == "latency":
                        service = tags.get("service", "unknown")
                        if service not in service_latency:
                            service_latency[service] = []
                        service_latency[service].append(float(value))

                    # Track service calls
                    if "service" in tags:
                        service = tags["service"]
                        service_calls[service] = service_calls.get(service, 0) + 1

            # Use actual values for the last hour
            tokens_last_hour = tokens_1h
            cost_last_hour_cents = cost_1h_cents
            carbon_last_hour_grams = carbon_1h_grams
            energy_last_hour_kwh = energy_1h_kwh

            # Calculate error rate
            total_operations = messages_24h + thoughts_24h + tasks_24h
            error_rate_percent = (errors_24h / total_operations * 100) if total_operations > 0 else 0.0

            # Calculate average latencies
            service_latency_ms = {}
            for service, latencies in service_latency.items():
                if latencies:
                    service_latency_ms[service] = sum(latencies) / len(latencies)

            # Get system uptime
            uptime_seconds = 0.0
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (now - self._start_time).total_seconds()
            else:
                # Fallback: assume service started 24h ago
                uptime_seconds = 86400.0

            # Create summary
            summary = TelemetrySummary(
                window_start=window_start_24h,
                window_end=window_end,
                uptime_seconds=uptime_seconds,
                messages_processed_24h=messages_24h,
                thoughts_processed_24h=thoughts_24h,
                tasks_completed_24h=tasks_24h,
                errors_24h=errors_24h,
                messages_current_hour=messages_1h,
                thoughts_current_hour=thoughts_1h,
                errors_current_hour=errors_1h,
                service_calls=service_calls,
                service_errors=service_errors,
                service_latency_ms=service_latency_ms,
                tokens_last_hour=float(tokens_last_hour),
                cost_last_hour_cents=cost_last_hour_cents,
                carbon_last_hour_grams=carbon_last_hour_grams,
                energy_last_hour_kwh=energy_last_hour_kwh,
                tokens_24h=float(tokens_24h),
                cost_24h_cents=cost_24h_cents,
                carbon_24h_grams=carbon_24h_grams,
                energy_24h_kwh=energy_24h_kwh,
                error_rate_percent=error_rate_percent,
                avg_thought_depth=1.5,  # TODO: Calculate from thought data
                queue_saturation=0.0,  # TODO: Calculate from queue metrics
            )

            # Cache the result
            self._summary_cache[cache_key] = (now, summary)

            return summary

        except Exception as e:
            logger.error(f"Failed to generate telemetry summary: {e}")
            # Return empty summary on error
            return TelemetrySummary(
                window_start=window_start_24h,
                window_end=window_end,
                uptime_seconds=0.0,
                messages_processed_24h=0,
                thoughts_processed_24h=0,
                tasks_completed_24h=0,
                errors_24h=0,
                messages_current_hour=0,
                thoughts_current_hour=0,
                errors_current_hour=0,
                tokens_last_hour=0.0,
                cost_last_hour_cents=0.0,
                carbon_last_hour_grams=0.0,
                energy_last_hour_kwh=0.0,
                tokens_24h=0.0,
                cost_24h_cents=0.0,
                carbon_24h_grams=0.0,
                energy_24h_kwh=0.0,
                error_rate_percent=0.0,
                avg_thought_depth=0.0,
                queue_saturation=0.0,
            )

    # Required methods for BaseGraphService

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.TELEMETRY

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
