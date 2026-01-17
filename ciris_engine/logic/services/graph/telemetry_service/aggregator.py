"""
TelemetryAggregator for enterprise telemetry collection.

Collects metrics from all 22 required services in parallel and
provides aggregated views for different stakeholders.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from ciris_engine.schemas.services.graph.telemetry import (
    AggregatedTelemetryResponse,
    ServiceTelemetryData,
)
from ciris_engine.schemas.types import JSONDict

# Import helper modules
from .adapter_collection import (
    collect_from_adapter_instances as _collect_from_adapter_instances,
    collect_from_bootstrap_adapters as _collect_from_bootstrap_adapters,
    collect_from_control_service as _collect_from_control_service,
    create_empty_telemetry,
    create_running_telemetry,
    create_telemetry_data,
    find_adapter_instance,
    get_adapter_metrics,
    get_control_service,
    is_adapter_running,
)
from .bus_collection import (
    collect_from_bus as _collect_from_bus,
    collect_from_component as _collect_from_component,
)
from .metrics_helpers import (
    aggregate_service_metrics,
    calculate_aggregates,
    compute_covenant_metrics,
    convert_dict_to_telemetry,
    extract_governance_metrics,
    extract_metric_value,
    get_fallback_metrics,
    process_service_metrics,
    status_to_telemetry,
    try_collect_metrics,
    try_collect_metrics_method,
    try_get_metrics_method,
    try_get_status_method,
)
from .registry_collection import (
    collect_from_registry_provider as _collect_from_registry_provider,
    collect_from_registry_services as _collect_from_registry_services,
    generate_semantic_service_name,
)
from .service_lookup import (
    NAME_MAP,
    RUNTIME_ATTRS,
    get_service_from_registry,
    get_service_from_runtime,
)

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


class TelemetryAggregator:
    """
    Enterprise telemetry aggregation for unified monitoring.

    Collects metrics from all 22 required services in parallel and
    provides aggregated views for different stakeholders.
    """

    # Service mappings - v1.4.6 validated (37 real source types with ConsentService)
    CATEGORIES = {
        "buses": ["llm_bus", "memory_bus", "communication_bus", "wise_bus", "tool_bus", "runtime_control_bus"],
        "graph": ["memory", "config", "telemetry", "audit", "incident_management", "tsdb_consolidation"],
        "infrastructure": [
            "time",
            "shutdown",
            "initialization",
            "authentication",
            "resource_monitor",
            "database_maintenance",  # Has get_metrics() now
            "secrets",  # SecretsService (not SecretsToolService)
        ],
        "governance": ["wise_authority", "adaptive_filter", "visibility", "self_observation", "consent"],
        "runtime": ["llm", "runtime_control", "task_scheduler"],
        "tools": ["secrets_tool"],  # Separated from runtime for clarity
        "adapters": ["api", "discord", "cli"],  # Each can spawn multiple instances
        "components": [
            "service_registry",
            "agent_processor",  # Has get_metrics() now
        ],
        # New v1.4.3: Covenant/Ethics metrics (computed, not from services)
        "covenant": [],  # Will be computed from governance services
    }

    def __init__(self, service_registry: Any, time_service: Any, runtime: Any = None):
        """Initialize the aggregator with service registry, time service, and optional runtime."""
        self.service_registry = service_registry
        self.time_service = time_service
        self.runtime = runtime  # Direct access to runtime for core services
        self.cache: Dict[str, Tuple[datetime, AggregatedTelemetryResponse]] = {}
        self.cache_ttl = timedelta(seconds=30)

    def _create_collection_tasks(self) -> tuple[list[Any], list[tuple[str, str]]]:
        """Create collection tasks for all services.

        Returns:
            Tuple of (tasks, service_info)
        """
        tasks = []
        service_info = []

        # Create collection tasks for all services
        for category, services in self.CATEGORIES.items():
            for service_name in services:
                task = asyncio.create_task(self.collect_service(service_name))
                tasks.append(task)
                service_info.append((category, service_name))

        # Also collect from dynamic registry services
        registry_tasks = self.collect_from_registry_services()
        tasks.extend(registry_tasks["tasks"])
        service_info.extend(registry_tasks["info"])

        return tasks, service_info

    def _process_task_result(
        self, result: Any, service_name: str, category: str, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
    ) -> None:
        """Process a single task result and add to telemetry dict.

        Args:
            result: Task result from collect_service
            service_name: Name of the service
            category: Category of the service
            telemetry: Telemetry dict to update
        """
        # Handle adapter results that return dict of instances
        if isinstance(result, dict) and service_name in ["api", "discord", "cli"]:
            # Adapter returned dict of instances - add each with adapter_id
            for adapter_id, adapter_data in result.items():
                telemetry[category][adapter_id] = adapter_data
        elif isinstance(result, ServiceTelemetryData):
            # Normal service result
            telemetry[category][service_name] = result
        else:
            # Unexpected type - convert to ServiceTelemetryData
            logger.warning(f"Unexpected result type for {service_name}: {type(result)}")
            telemetry[category][service_name] = ServiceTelemetryData(
                healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
            )

    def _process_completed_tasks(
        self,
        tasks: list[Any],
        service_info: list[tuple[str, str]],
        done: set[Any],
        telemetry: Dict[str, Dict[str, ServiceTelemetryData]],
    ) -> None:
        """Process completed tasks and populate telemetry dict.

        Args:
            tasks: List of all tasks
            service_info: List of (category, service_name) tuples
            done: Set of completed tasks
            telemetry: Telemetry dict to update
        """
        for idx, task in enumerate(tasks):
            if idx >= len(service_info):
                continue

            category, service_name = service_info[idx]

            if task in done:
                try:
                    result = task.result()
                    self._process_task_result(result, service_name, category, telemetry)
                except Exception as e:
                    logger.warning(f"Failed to collect from {service_name}: {e}")
                    # Return empty telemetry data instead of empty dict
                    telemetry[category][service_name] = ServiceTelemetryData(
                        healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
                    )  # NO FALLBACKS
            else:
                # Task timed out
                telemetry[category][service_name] = self.get_fallback_metrics(service_name)

    async def collect_all_parallel(self) -> Dict[str, Dict[str, ServiceTelemetryData]]:
        """
        Collect telemetry from all services in parallel.

        Returns hierarchical telemetry organized by category.
        """
        # Create collection tasks
        tasks, service_info = self._create_collection_tasks()

        # Execute all collections in parallel with timeout
        done, pending = await asyncio.wait(tasks, timeout=5.0, return_when=asyncio.ALL_COMPLETED)

        # Cancel any timed-out tasks
        for task in pending:
            task.cancel()

        # Organize results by category
        telemetry: Dict[str, Dict[str, ServiceTelemetryData]] = {cat: {} for cat in self.CATEGORIES.keys()}
        # Add registry category for dynamic services
        telemetry["registry"] = {}

        # Process completed tasks
        self._process_completed_tasks(tasks, service_info, done, telemetry)

        # Compute covenant metrics from governance services
        covenant_metrics_data = self.compute_covenant_metrics(telemetry)
        # Wrap covenant metrics in ServiceTelemetryData using custom_metrics
        telemetry["covenant"]["covenant_metrics"] = ServiceTelemetryData(
            healthy=True,
            uptime_seconds=0.0,
            error_count=0,
            requests_handled=0,
            error_rate=0.0,
            memory_mb=0.0,
            custom_metrics=covenant_metrics_data,
        )

        return telemetry

    def _generate_semantic_service_name(
        self, service_type: str, provider_name: str, provider_metadata: Optional[JSONDict] = None
    ) -> str:
        """Generate a semantic name for a dynamic service."""
        return generate_semantic_service_name(service_type, provider_name, provider_metadata)

    def collect_from_registry_services(self) -> Dict[str, List[Any]]:
        """Collect telemetry from dynamic services registered in ServiceRegistry."""
        return _collect_from_registry_services(
            self.service_registry,
            self.CATEGORIES,
            self.collect_from_registry_provider,
        )

    async def collect_from_registry_provider(self, service_type: str, provider_name: str) -> ServiceTelemetryData:
        """Collect telemetry from a specific registry provider."""
        return await _collect_from_registry_provider(self.service_registry, service_type, provider_name)

    async def collect_service(self, service_name: str) -> ServiceTelemetryData | dict[str, ServiceTelemetryData]:
        """Collect telemetry from a single service or multiple adapter instances."""
        logger.debug(f"[TELEMETRY] Starting collection for service: {service_name}")
        try:
            # Special handling for buses
            if service_name.endswith("_bus"):
                logger.debug(f"[TELEMETRY] Collecting from bus: {service_name}")
                return await self.collect_from_bus(service_name)

            # Special handling for adapters - collect from ALL instances
            if service_name in ["api", "discord", "cli"]:
                logger.debug(f"[TELEMETRY] Collecting from adapter: {service_name}")
                return await self.collect_from_adapter_instances(service_name)

            # Special handling for components
            if service_name in [
                "service_registry",
                "agent_processor",
            ]:
                logger.debug(f"[TELEMETRY] Collecting from component: {service_name}")
                return await self.collect_from_component(service_name)

            # Get service from registry
            service = self._get_service_from_registry(service_name)
            logger.debug(f"[TELEMETRY] Got service {service_name}: {service.__class__.__name__ if service else 'None'}")

            # Try different collection methods
            metrics = await self._try_collect_metrics(service)
            if metrics is not None:
                logger.debug(
                    f"[TELEMETRY] Collected from {service_name}: healthy={metrics.healthy}, uptime={metrics.uptime_seconds}"
                )
                return metrics
            # Return empty telemetry data instead of empty dict
            logger.debug(f"[TELEMETRY] No metrics collected from {service_name}, returning unhealthy")
            return ServiceTelemetryData(
                healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
            )  # NO FALLBACKS

        except Exception as e:
            logger.error(f"Failed to collect from {service_name}: {e}")
            # Return empty telemetry data instead of empty dict
            return ServiceTelemetryData(
                healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
            )  # NO FALLBACKS - service failed

    def _get_service_from_runtime(self, service_name: str) -> Any:
        """Get service directly from runtime attributes."""
        return get_service_from_runtime(self.runtime, service_name)

    def _get_service_from_registry(self, service_name: str) -> Any:
        """Get service from runtime first, then registry by name."""
        return get_service_from_registry(self.runtime, self.service_registry, service_name)

    def _convert_dict_to_telemetry(self, metrics: JSONDict, service_name: str) -> ServiceTelemetryData:
        """Convert dict metrics to ServiceTelemetryData with proper uptime detection."""
        return convert_dict_to_telemetry(metrics, service_name)

    async def _try_get_metrics_method(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try to collect metrics via get_metrics() method."""
        return await try_get_metrics_method(service)

    def _try_collect_metrics_method(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try to collect metrics via _collect_metrics() method."""
        return try_collect_metrics_method(service)

    async def _try_get_status_method(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try to collect metrics via get_status() method."""
        return await try_get_status_method(service)

    async def _try_collect_metrics(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try different methods to collect metrics from service."""
        return await try_collect_metrics(service)

    async def collect_from_bus(self, bus_name: str) -> ServiceTelemetryData:
        """Collect telemetry from a message bus."""
        return await _collect_from_bus(
            self.runtime, self.service_registry, bus_name, self.get_fallback_metrics
        )

    async def collect_from_component(self, component_name: str) -> ServiceTelemetryData:
        """Collect telemetry from runtime components."""
        return await _collect_from_component(self.runtime, component_name, self._try_collect_metrics)

    async def _get_control_service(self) -> Any:
        """Get the runtime control service."""
        return await get_control_service(self.runtime, self.service_registry)

    def _is_adapter_running(self, adapter_info: Any) -> bool:
        """Check if an adapter is running."""
        return is_adapter_running(adapter_info)

    def _find_adapter_instance(self, adapter_type: str) -> Any:
        """Find adapter instance in runtime."""
        return find_adapter_instance(self.runtime, adapter_type)

    async def _get_adapter_metrics(self, adapter_instance: Any) -> Optional[JSONDict]:
        """Get metrics from adapter instance."""
        return await get_adapter_metrics(adapter_instance)

    def _create_telemetry_data(
        self,
        metrics: JSONDict,
        adapter_info: Optional[Any] = None,
        adapter_id: Optional[str] = None,
        healthy: bool = True,
    ) -> ServiceTelemetryData:
        """Create ServiceTelemetryData from metrics."""
        return create_telemetry_data(metrics, adapter_info, adapter_id, healthy)

    def _create_empty_telemetry(self, adapter_id: str, error_msg: Optional[str] = None) -> ServiceTelemetryData:
        """Create empty telemetry data for failed/unavailable adapter."""
        return create_empty_telemetry(adapter_id, error_msg)

    def _create_running_telemetry(self, adapter_info: Any) -> ServiceTelemetryData:
        """Create telemetry for running adapter without metrics."""
        return create_running_telemetry(adapter_info)

    async def _collect_from_adapter_with_metrics(
        self, adapter_instance: Any, adapter_info: Any, adapter_id: str
    ) -> ServiceTelemetryData:
        """Collect metrics from a single adapter instance."""
        from .adapter_collection import collect_from_adapter_with_metrics as _collect_from_adapter_with_metrics

        return await _collect_from_adapter_with_metrics(adapter_instance, adapter_info, adapter_id)

    async def _collect_from_control_service(self, adapter_type: str) -> Optional[Dict[str, ServiceTelemetryData]]:
        """Try to collect adapter metrics via control service."""
        return await _collect_from_control_service(self.runtime, self.service_registry, adapter_type)

    async def _collect_from_bootstrap_adapters(self, adapter_type: str) -> Dict[str, ServiceTelemetryData]:
        """Fallback: collect from bootstrap adapters directly."""
        return await _collect_from_bootstrap_adapters(self.runtime, adapter_type)

    async def collect_from_adapter_instances(self, adapter_type: str) -> Dict[str, ServiceTelemetryData]:
        """Collect telemetry from ALL active adapter instances of a given type."""
        return await _collect_from_adapter_instances(self.runtime, self.service_registry, adapter_type)

    def get_fallback_metrics(self, _service_name: Optional[str] = None, _healthy: bool = False) -> ServiceTelemetryData:
        """NO FALLBACKS. Real metrics or nothing."""
        return get_fallback_metrics(_service_name, _healthy)

    def status_to_telemetry(self, status: Any) -> JSONDict:
        """Convert ServiceStatus to telemetry dict."""
        return status_to_telemetry(status)

    def _process_service_metrics(self, service_data: ServiceTelemetryData) -> Tuple[bool, int, int, float, float]:
        """Process metrics for a single service."""
        return process_service_metrics(service_data)

    def _aggregate_service_metrics(
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
    ) -> Tuple[int, int, int, int, float, List[float]]:
        """Aggregate metrics from all services."""
        return aggregate_service_metrics(telemetry)

    def _extract_metric_value(self, metrics_obj: Any, metric_name: str, default: Any = 0) -> Any:
        """Extract a metric value from ServiceTelemetryData or dict."""
        return extract_metric_value(metrics_obj, metric_name, default)

    def _extract_governance_metrics(
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]], service_name: str, metric_mappings: Dict[str, str]
    ) -> Dict[str, Union[float, int, str]]:
        """Extract metrics from a governance service."""
        return extract_governance_metrics(telemetry, service_name, metric_mappings)

    def compute_covenant_metrics(
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
    ) -> Dict[str, Union[float, int, str]]:
        """Compute covenant/ethics metrics from governance services."""
        return compute_covenant_metrics(telemetry)

    def calculate_aggregates(
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
    ) -> Dict[str, Union[bool, int, float, str]]:
        """Calculate system-wide aggregate metrics."""
        return calculate_aggregates(telemetry)
