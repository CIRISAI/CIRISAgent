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
    AggregatedTelemetryMetadata,
    AggregatedTelemetryResponse,
    BehavioralData,
    ResourceData,
    ServiceTelemetryData,
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
        self.cache: Dict[str, Tuple[datetime, Dict]] = {}
        self.cache_ttl = timedelta(seconds=30)

    async def collect_all_parallel(self) -> Dict[str, Dict[str, Union[ServiceTelemetryData, Dict]]]:
        """
        Collect telemetry from all services in parallel.

        Returns hierarchical telemetry organized by category.
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

        # Execute all collections in parallel with timeout
        done, pending = await asyncio.wait(tasks, timeout=5.0, return_when=asyncio.ALL_COMPLETED)

        # Cancel any timed-out tasks
        for task in pending:
            task.cancel()

        # Organize results by category
        telemetry = {cat: {} for cat in self.CATEGORIES.keys()}
        # Add registry category for dynamic services
        telemetry["registry"] = {}

        for idx, task in enumerate(tasks):
            if idx < len(service_info):
                category, service_name = service_info[idx]

                if task in done:
                    try:
                        result = task.result()
                        # Handle adapter results that return dict of instances
                        if isinstance(result, dict) and service_name in ["api", "discord", "cli"]:
                            # Adapter returned dict of instances - add each with adapter_id
                            for adapter_id, adapter_data in result.items():
                                telemetry[category][adapter_id] = adapter_data
                        else:
                            # Normal service result
                            telemetry[category][service_name] = result
                    except Exception as e:
                        logger.warning(f"Failed to collect from {service_name}: {e}")
                        # Return empty telemetry data instead of empty dict
                        telemetry[category][service_name] = ServiceTelemetryData(
                            healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
                        )  # NO FALLBACKS
                else:
                    # Task timed out
                    telemetry[category][service_name] = self.get_fallback_metrics(service_name)

        # Compute covenant metrics from governance services
        telemetry["covenant"] = self.compute_covenant_metrics(telemetry)

        return telemetry

    def _generate_semantic_service_name(
        self, service_type: str, provider_name: str, provider_metadata: dict = None
    ) -> str:
        """
        Generate a semantic name for a dynamic service.

        For adapters: {service_type}_{adapter_type}_{adapter_id_suffix}
        For LLM providers: {service_type}_{provider_type}_{instance_id}
        For others: {service_type}_{provider_name_cleaned}
        """
        # Clean up the provider name
        provider_cleaned = provider_name.replace("Service", "").replace("Adapter", "")

        # Handle adapter services (API-COMM, CLI-TOOL, etc.)
        if "APICommunication" in provider_name:
            adapter_id = provider_metadata.get("adapter_id", "") if provider_metadata else ""
            suffix = adapter_id.split("_")[-1][:8] if adapter_id else str(id(provider_name))[-6:]
            return f"{service_type}_api_{suffix}"
        elif "CLIAdapter" in provider_name:
            adapter_id = provider_metadata.get("adapter_id", "") if provider_metadata else ""
            suffix = adapter_id.split("@")[-1][:8] if adapter_id and "@" in adapter_id else str(id(provider_name))[-6:]
            return f"{service_type}_cli_{suffix}"
        elif "DiscordAdapter" in provider_name or "Discord" in provider_name:
            adapter_id = provider_metadata.get("adapter_id", "") if provider_metadata else ""
            suffix = adapter_id.split("_")[-1][:8] if adapter_id else str(id(provider_name))[-6:]
            return f"{service_type}_discord_{suffix}"
        elif "APITool" in provider_name:
            return f"{service_type}_api_tool"
        elif "APIRuntime" in provider_name:
            return f"{service_type}_api_runtime"
        elif "SecretsToolService" in provider_name:
            return f"{service_type}_secrets"
        elif "MockLLM" in provider_name:
            return f"{service_type}_mock"
        elif "OpenAI" in provider_name or "Anthropic" in provider_name:
            # For LLM providers, include provider type and instance
            provider_type = "openai" if "OpenAI" in provider_name else "anthropic"
            instance_id = str(id(provider_name))[-6:]
            return f"{service_type}_{provider_type}_{instance_id}"
        elif "LocalGraphMemory" in provider_name:
            return f"{service_type}_local_graph"
        elif "GraphConfig" in provider_name:
            return f"{service_type}_graph"
        elif "TimeService" in provider_name:
            return f"{service_type}_time"
        elif "WiseAuthority" in provider_name:
            return f"{service_type}_wise_authority"
        else:
            # Default: use cleaned provider name with a short ID
            short_id = str(id(provider_name))[-6:]
            return f"{service_type}_{provider_cleaned.lower()}_{short_id}"

    def collect_from_registry_services(self) -> Dict[str, List]:
        """
        Collect telemetry from dynamic services registered in ServiceRegistry.

        Returns dict with 'tasks' and 'info' lists for dynamic services.
        """
        tasks = []
        service_info = []

        if not self.service_registry:
            return {"tasks": [], "info": []}

        try:
            # Get all services from registry
            provider_info = self.service_registry.get_provider_info()

            # Iterate through all service types and providers
            for service_type, providers in provider_info.get("services", {}).items():
                for provider in providers:
                    provider_name = provider.get("name", "")
                    provider_metadata = provider.get("metadata", {})

                    # Extract the class name without instance ID (e.g., "GraphConfigService_123456" -> "GraphConfigService")
                    provider_class_name = provider_name.split("_")[0] if "_" in provider_name else provider_name

                    logger.debug(
                        f"[TELEMETRY] Checking registry service: {service_type}.{provider_name} (class: {provider_class_name})"
                    )

                    # Skip if this provider is already in CATEGORIES
                    # Check both the provider name and simplified versions
                    already_collected = False

                    # Map of known core service implementations to their category names
                    # Only skip services that are ALREADY collected via CATEGORIES
                    # Do NOT skip adapter-provided services like APIToolService, CLIAdapter, etc.
                    core_service_mappings = {
                        "LocalGraphMemoryService": "memory",
                        "GraphConfigService": "config",
                        "TimeService": "time",
                        "WiseAuthorityService": "wise_authority",
                        "ConfigService": "config",  # Alternative name
                        "MemoryService": "memory",  # Alternative name
                        "TSDBConsolidationService": "tsdb_consolidation",
                        "MockLLMService": "llm",  # Mock LLM should be collected through llm, not registry
                        "SecretsToolService": "secrets_tool",  # Core secrets tool service
                        # NOTE: Do NOT add adapter services here! They should be collected dynamically
                        # APIToolService, APICommunicationService, CLIAdapter, DiscordWiseAuthority etc
                        # are all valid dynamic services that should be collected
                    }

                    # Check if this is a core service implementation (use class name without instance ID)
                    if provider_class_name in core_service_mappings:
                        already_collected = True
                        logger.debug(
                            f"[TELEMETRY] Skipping core service {provider_name} (class: {provider_class_name}) - already collected as {core_service_mappings[provider_class_name]}"
                        )
                    else:
                        # Also check if provider class name matches any service in CATEGORIES
                        for cat_services in self.CATEGORIES.values():
                            if provider_class_name.lower() in [s.lower() for s in cat_services]:
                                already_collected = True
                                logger.debug(f"[TELEMETRY] Skipping {provider_name} - already in CATEGORIES")
                                break

                    if not already_collected:
                        # Generate semantic name for the service
                        semantic_name = self._generate_semantic_service_name(
                            service_type, provider_name, provider_metadata
                        )

                        # Create a collection task for this dynamic service
                        task = asyncio.create_task(self.collect_from_registry_provider(service_type, provider_name))
                        tasks.append(task)
                        service_info.append(("registry", semantic_name))
                        logger.debug(
                            f"[TELEMETRY] Adding registry service: {semantic_name} (was: {service_type}.{provider_name})"
                        )

        except Exception as e:
            logger.warning(f"Failed to collect registry services: {e}")

        return {"tasks": tasks, "info": service_info}

    async def collect_from_registry_provider(self, service_type: str, provider_name: str) -> ServiceTelemetryData:
        """
        Collect telemetry from a specific registry provider.

        Returns ServiceTelemetryData for the provider.
        """
        try:
            # Get the provider instance from registry
            providers = self.service_registry.get_services_by_type(service_type)
            target_provider = None

            for provider in providers:
                # Extract class name from provider_name (remove instance ID)
                provider_class_name = provider_name.split("_")[0] if "_" in provider_name else provider_name
                if hasattr(provider, "__class__") and provider.__class__.__name__ == provider_class_name:
                    target_provider = provider
                    break

            if not target_provider:
                logger.debug(f"[TELEMETRY] Provider {provider_name} not found in {service_type}")
                return ServiceTelemetryData(
                    healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
                )

            # Try to get metrics from the provider
            if hasattr(target_provider, "get_metrics"):
                metrics = (
                    await target_provider.get_metrics()
                    if asyncio.iscoroutinefunction(target_provider.get_metrics)
                    else target_provider.get_metrics()
                )

                if isinstance(metrics, ServiceTelemetryData):
                    logger.debug(f"[TELEMETRY] Got metrics from {provider_name}: healthy={metrics.healthy}")
                    return metrics
                elif isinstance(metrics, dict):
                    # Convert dict to ServiceTelemetryData
                    return ServiceTelemetryData(
                        healthy=metrics.get("healthy", True),
                        uptime_seconds=metrics.get("uptime_seconds", 0.0),
                        error_count=metrics.get("error_count", 0),
                        requests_handled=metrics.get("requests_handled", 0),
                        error_rate=metrics.get("error_rate", 0.0),
                        custom_metrics=metrics.get("custom_metrics"),
                        last_health_check=metrics.get("last_health_check"),
                    )

            # If no get_metrics, check for is_healthy
            if hasattr(target_provider, "is_healthy"):
                is_healthy = (
                    await target_provider.is_healthy()
                    if asyncio.iscoroutinefunction(target_provider.is_healthy)
                    else target_provider.is_healthy()
                )
                # NO FALLBACK DATA - return actual health status with zero metrics
                return ServiceTelemetryData(
                    healthy=is_healthy,
                    uptime_seconds=0.0,  # NO FAKE UPTIME
                    error_count=0,
                    requests_handled=0,
                    error_rate=0.0,
                )

            # NO DEFAULTS - if no health check, service is unhealthy
            return ServiceTelemetryData(
                healthy=False,  # NO DEFAULT HEALTHY STATUS
                uptime_seconds=0.0,  # NO FAKE UPTIME
                error_count=0,
                requests_handled=0,
                error_rate=0.0,
            )

        except Exception as e:
            logger.warning(f"Failed to collect from registry provider {provider_name}: {e}")
            return ServiceTelemetryData(
                healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
            )

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

    def _get_service_from_runtime(self, service_name: str):
        """Get service directly from runtime attributes."""
        if not self.runtime:
            logger.debug(f"[TELEMETRY] No runtime available for service {service_name}")
            return None

        # Map service names to runtime attributes
        runtime_attrs = {
            # Graph services
            "memory": "memory_service",
            "config": "config_service",
            "telemetry": "telemetry_service",
            "audit": "audit_service",
            "incident_management": "incident_management_service",
            "tsdb_consolidation": "tsdb_consolidation_service",
            # Infrastructure services
            "time": "time_service",
            "shutdown": "shutdown_service",
            "initialization": "initialization_service",
            "authentication": "authentication_service",
            "resource_monitor": "resource_monitor",
            "database_maintenance": "maintenance_service",
            "secrets": "secrets_service",
            # Governance services
            "wise_authority": "wa_auth_system",
            "adaptive_filter": "adaptive_filter_service",
            "visibility": "visibility_service",
            "self_observation": "self_observation_service",
            "consent": "consent_service",
            # Runtime services
            "llm": "llm_service",
            "runtime_control": "runtime_control_service",
            "task_scheduler": "task_scheduler",
            # Tool services
            "secrets_tool": "core_tool_service",
        }

        attr_name = runtime_attrs.get(service_name)
        if attr_name:
            service = getattr(self.runtime, attr_name, None)
            if service:
                logger.debug(
                    f"Found {service_name} as runtime.{attr_name}: {service.__class__.__name__ if service else 'None'}"
                )
                # Extra debug - check if service has required telemetry methods
                has_get_metrics = hasattr(service, "get_metrics")
                has_collect_metrics = hasattr(service, "_collect_metrics")
                is_started = getattr(service, "_started", False)
                logger.debug(
                    f"  Service {service_name} telemetry: get_metrics={has_get_metrics}, _collect_metrics={has_collect_metrics}, _started={is_started}"
                )
                return service
            else:
                logger.debug(f"[TELEMETRY] runtime.{attr_name} is None for {service_name}")
        else:
            logger.debug(f"[TELEMETRY] No runtime attr mapping for {service_name}")
        return None

    def _get_service_from_registry(self, service_name: str):
        """Get service from runtime first, then registry by name."""
        # First try to get service directly from runtime
        if self.runtime:
            runtime_service = self._get_service_from_runtime(service_name)
            if runtime_service:
                logger.debug(
                    f"Found {service_name} directly from runtime: {runtime_service.__class__.__name__ if runtime_service else 'None'}"
                )
                return runtime_service

        # Fall back to registry lookup
        all_services = self.service_registry.get_all_services() if self.service_registry else []
        logger.debug(f"[TELEMETRY] Looking for {service_name} in {len(all_services)} registered services")

        # Map expected names to actual registered class names
        name_map = {
            # Graph services
            "memory": ["memoryservice", "localgraphmemoryservice"],
            "config": ["configservice", "graphconfigservice"],
            "telemetry": ["telemetryservice", "graphtelemetryservice"],
            "audit": ["auditservice"],
            "incident_management": ["incidentmanagementservice"],
            "tsdb_consolidation": ["tsdbconsolidationservice"],
            # Infrastructure services
            "time": ["timeservice"],
            "shutdown": ["shutdownservice"],
            "initialization": ["initializationservice"],
            "authentication": ["authenticationservice"],
            "resource_monitor": ["resourcemonitorservice"],
            "database_maintenance": ["databasemaintenanceservice"],
            "secrets": ["secretsservice"],
            # Governance services
            "wise_authority": ["wiseauthorityservice"],
            "adaptive_filter": ["adaptivefilterservice"],
            "visibility": ["visibilityservice"],
            "self_observation": ["selfobservationservice"],
            "consent": ["consentservice"],
            # Runtime services
            "llm": ["llmservice", "mockllmservice"],
            "runtime_control": ["runtimecontrolservice", "apiruntimecontrolservice"],
            "task_scheduler": ["taskschedulerservice"],
            # Tool services
            "secrets_tool": ["secretstoolservice"],
        }

        if service_name not in name_map:
            logger.debug(f"Service {service_name} not in name_map")
            return None

        # Check each service in registry
        for service in all_services:
            if hasattr(service, "__class__"):
                class_name = service.__class__.__name__.lower()
                # Check if class name matches any expected variant
                for variant in name_map[service_name]:
                    if class_name == variant:
                        logger.debug(f"Found service {service_name} as {service.__class__.__name__}")
                        return service

        logger.debug(f"Service {service_name} not found in {len(all_services)} services")
        return None

    async def _try_collect_metrics(self, service) -> Optional[ServiceTelemetryData]:
        """Try different methods to collect metrics from service."""
        if not service:
            logger.debug("[TELEMETRY] Service is None, cannot collect metrics")
            return None

        # Try get_metrics first
        if hasattr(service, "get_metrics"):
            logger.debug(f"[TELEMETRY] Service {type(service).__name__} has get_metrics method")
            try:
                # Check if get_metrics is async or sync
                if asyncio.iscoroutinefunction(service.get_metrics):
                    metrics = await service.get_metrics()
                else:
                    metrics = service.get_metrics()
                logger.debug(f"[TELEMETRY] Got metrics from {type(service).__name__}: {metrics}")
                if isinstance(metrics, ServiceTelemetryData):
                    return metrics
                elif isinstance(metrics, dict):
                    # Convert dict to ServiceTelemetryData
                    # Look for various uptime keys
                    uptime = (
                        metrics.get("uptime_seconds")
                        or metrics.get("incident_uptime_seconds")
                        or metrics.get("tsdb_uptime_seconds")
                        or metrics.get("auth_uptime_seconds")
                        or metrics.get("scheduler_uptime_seconds")
                        or 0.0
                    )

                    # If service has uptime > 0, consider it healthy unless explicitly marked unhealthy
                    healthy = metrics.get("healthy", uptime > 0)

                    logger.debug(
                        f"Converting dict metrics to ServiceTelemetryData for {type(service).__name__}: healthy={healthy}, uptime={uptime}"
                    )
                    return ServiceTelemetryData(
                        healthy=healthy,
                        uptime_seconds=uptime,
                        error_count=metrics.get("error_count", 0),
                        requests_handled=metrics.get("request_count") or metrics.get("requests_handled"),
                        error_rate=metrics.get("error_rate", 0.0),
                        memory_mb=metrics.get("memory_mb"),
                        custom_metrics=metrics,  # Pass the whole dict as custom_metrics
                    )
            except Exception as e:
                logger.error(f"Error calling get_metrics on {type(service).__name__}: {e}")
                # Don't return None here - continue to try other methods
        else:
            logger.debug(f"Service {type(service).__name__} does not have get_metrics method")

        # Try _collect_metrics
        if hasattr(service, "_collect_metrics"):
            metrics = service._collect_metrics()
            if isinstance(metrics, ServiceTelemetryData):
                return metrics
            elif isinstance(metrics, dict):
                # Convert dict to ServiceTelemetryData
                return ServiceTelemetryData(
                    healthy=metrics.get("healthy", False),
                    uptime_seconds=metrics.get("uptime_seconds"),
                    error_count=metrics.get("error_count"),
                    requests_handled=metrics.get("request_count") or metrics.get("requests_handled"),
                    error_rate=metrics.get("error_rate"),
                    memory_mb=metrics.get("memory_mb"),
                    custom_metrics=metrics.get("custom_metrics"),
                )
            return None

        # Try get_status
        if hasattr(service, "get_status"):
            status = service.get_status()
            if asyncio.iscoroutine(status):
                status = await status
            return self.status_to_telemetry(status)

        return None

    async def collect_from_bus(self, bus_name: str) -> ServiceTelemetryData:
        """Collect telemetry from a message bus."""
        try:
            # Get the bus from runtime first, then agent/registry
            bus = None

            # Try runtime.bus_manager first
            if self.runtime:
                bus_manager = getattr(self.runtime, "bus_manager", None)
                if bus_manager:
                    # Map bus names to bus_manager attributes
                    bus_attr_map = {
                        "llm_bus": "llm",
                        "memory_bus": "memory",
                        "communication_bus": "communication",
                        "wise_bus": "wise",
                        "tool_bus": "tool",
                        "runtime_control_bus": "runtime_control",
                    }
                    attr_name = bus_attr_map.get(bus_name)
                    if attr_name:
                        bus = getattr(bus_manager, attr_name, None)
                        if bus:
                            logger.debug(f"Found {bus_name} from runtime.bus_manager.{attr_name}")

            # Fall back to registry
            if not bus and hasattr(self.service_registry, "_agent"):
                agent = self.service_registry._agent
                bus = getattr(agent, bus_name, None)

            if bus:
                # Try get_metrics first (all buses have this)
                if hasattr(bus, "get_metrics"):
                    try:
                        metrics = bus.get_metrics()
                        # Convert dict to ServiceTelemetryData
                        # Buses with providers should report healthy
                        is_healthy = True
                        if hasattr(bus, "get_providers"):
                            providers = bus.get_providers()
                            is_healthy = len(providers) > 0
                        elif hasattr(bus, "providers"):
                            is_healthy = len(bus.providers) > 0

                        # Map bus names to their specific uptime metric names
                        uptime_metric_map = {
                            "llm_bus": "llm_uptime_seconds",
                            "memory_bus": "memory_uptime_seconds",
                            "communication_bus": "communication_uptime_seconds",
                            "wise_bus": "wise_uptime_seconds",
                            "tool_bus": "tool_uptime_seconds",
                            "runtime_control_bus": "runtime_control_uptime_seconds",
                        }
                        uptime_metric = uptime_metric_map.get(bus_name, "uptime_seconds")

                        return ServiceTelemetryData(
                            healthy=is_healthy,
                            uptime_seconds=metrics.get(uptime_metric, metrics.get("uptime_seconds", 0.0)),
                            error_count=metrics.get("error_count", 0),
                            requests_handled=metrics.get("request_count") or metrics.get("requests_handled", 0),
                            error_rate=metrics.get("error_rate", 0.0),
                            memory_mb=metrics.get("memory_mb"),
                            custom_metrics=metrics,
                        )
                    except Exception as e:
                        logger.error(f"Error getting metrics from {bus_name}: {e}")
                        return self.get_fallback_metrics(bus_name)
                elif hasattr(bus, "collect_telemetry"):
                    return await bus.collect_telemetry()
                else:
                    return self.get_fallback_metrics(bus_name)
            else:
                return self.get_fallback_metrics(bus_name)

        except Exception as e:
            logger.error(f"Failed to collect from {bus_name}: {e}")
            return self.get_fallback_metrics(bus_name)

    async def collect_from_component(self, component_name: str) -> ServiceTelemetryData:
        """Collect telemetry from runtime components."""
        logger.debug(f"[TELEMETRY] Collecting from component: {component_name}")
        try:
            component = None

            # Map component names to runtime locations
            if self.runtime:
                if component_name == "service_registry":
                    component = getattr(self.runtime, "service_registry", None)
                    logger.debug(
                        f"[TELEMETRY] Got service_registry: {component.__class__.__name__ if component else 'None'}"
                    )
                elif component_name == "agent_processor":
                    component = getattr(self.runtime, "agent_processor", None)
                    logger.debug(
                        f"[TELEMETRY] Got agent_processor: {component.__class__.__name__ if component else 'None'}"
                    )

            # Try to get metrics from component
            if component:
                logger.debug(f"[TELEMETRY] Trying to collect metrics from {component.__class__.__name__}")
                metrics = await self._try_collect_metrics(component)
                if metrics:
                    logger.debug(f"[TELEMETRY] Got metrics from {component_name}: healthy={metrics.healthy}")
                    return metrics
                else:
                    logger.debug(f"[TELEMETRY] No metrics from {component_name}")
            else:
                logger.debug(f"[TELEMETRY] Component {component_name} not found on runtime")

            # Return empty telemetry data
            return ServiceTelemetryData(
                healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
            )

        except Exception as e:
            logger.error(f"Failed to collect from component {component_name}: {e}")
            return ServiceTelemetryData(
                healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
            )

    async def _get_control_service(self) -> Any:
        """Get the runtime control service."""
        if self.runtime and hasattr(self.runtime, "runtime_control_service"):
            return self.runtime.runtime_control_service
        elif self.service_registry:
            from ciris_engine.schemas.runtime.enums import ServiceType

            return await self.service_registry.get_service(ServiceType.RUNTIME_CONTROL)
        return None

    def _is_adapter_running(self, adapter_info: Any) -> bool:
        """Check if an adapter is running."""
        if hasattr(adapter_info, "is_running"):
            return adapter_info.is_running
        elif hasattr(adapter_info, "status"):
            from ciris_engine.schemas.services.core.runtime import AdapterStatus

            return adapter_info.status in [AdapterStatus.ACTIVE, AdapterStatus.RUNNING]
        return False

    def _find_adapter_instance(self, adapter_type: str) -> Any:
        """Find adapter instance in runtime."""
        if hasattr(self.runtime, "adapters"):
            for adapter in self.runtime.adapters:
                if adapter_type in adapter.__class__.__name__.lower():
                    return adapter
        return None

    async def _get_adapter_metrics(self, adapter_instance: Any) -> dict:
        """Get metrics from adapter instance."""
        if hasattr(adapter_instance, "get_metrics"):
            if asyncio.iscoroutinefunction(adapter_instance.get_metrics):
                return await adapter_instance.get_metrics()
            return adapter_instance.get_metrics()
        return None

    def _create_telemetry_data(
        self, metrics: dict, adapter_info: Any = None, adapter_id: str = None, healthy: bool = True
    ) -> ServiceTelemetryData:
        """Create ServiceTelemetryData from metrics."""
        if not metrics:
            return ServiceTelemetryData(
                healthy=False,
                uptime_seconds=0.0,
                error_count=0,
                requests_handled=0,
                error_rate=0.0,
                custom_metrics={"adapter_id": adapter_id} if adapter_id else {},
            )

        custom_metrics = {"adapter_id": adapter_id} if adapter_id else {}
        if adapter_info:
            custom_metrics["adapter_type"] = (
                adapter_info.adapter_type if hasattr(adapter_info, "adapter_type") else None
            )
            if hasattr(adapter_info, "started_at") and adapter_info.started_at:
                custom_metrics["start_time"] = adapter_info.started_at.isoformat()

        custom_metrics.update(metrics.get("custom_metrics", {}))

        return ServiceTelemetryData(
            healthy=healthy,
            uptime_seconds=metrics.get("uptime_seconds", 0.0),
            error_count=metrics.get("error_count", 0),
            requests_handled=metrics.get("request_count") or metrics.get("requests_handled", 0),
            error_rate=metrics.get("error_rate", 0.0),
            memory_mb=metrics.get("memory_mb"),
            custom_metrics=custom_metrics,
        )

    async def collect_from_adapter_instances(self, adapter_type: str) -> Dict[str, ServiceTelemetryData]:
        """
        Collect telemetry from ALL active adapter instances of a given type.

        Returns a dict mapping adapter_id to telemetry data.
        Multiple instances of the same adapter type can be running simultaneously.
        """
        adapter_metrics = {}

        # Try to get adapters from runtime control service if available
        if self.runtime:
            try:
                control_service = await self._get_control_service()
                if control_service and hasattr(control_service, "list_adapters"):
                    all_adapters = await control_service.list_adapters()

                    for adapter_info in all_adapters:
                        if adapter_info.adapter_type == adapter_type and self._is_adapter_running(adapter_info):
                            adapter_instance = self._find_adapter_instance(adapter_type)

                            if adapter_instance:
                                try:
                                    metrics = await self._get_adapter_metrics(adapter_instance)
                                    adapter_metrics[adapter_info.adapter_id] = self._create_telemetry_data(
                                        metrics, adapter_info, adapter_info.adapter_id, healthy=True
                                    )
                                except Exception as e:
                                    logger.error(f"Error getting metrics from {adapter_info.adapter_id}: {e}")
                                    adapter_metrics[adapter_info.adapter_id] = ServiceTelemetryData(
                                        healthy=False,
                                        uptime_seconds=0.0,
                                        error_count=1,
                                        requests_handled=0,
                                        error_rate=1.0,
                                        custom_metrics={"error": str(e), "adapter_id": adapter_info.adapter_id},
                                    )
                            else:
                                # Adapter is running but no metrics available
                                uptime = 0
                                if hasattr(adapter_info, "started_at") and adapter_info.started_at:
                                    uptime = (datetime.now(timezone.utc) - adapter_info.started_at).total_seconds()

                                adapter_metrics[adapter_info.adapter_id] = ServiceTelemetryData(
                                    healthy=True,
                                    uptime_seconds=uptime,
                                    error_count=0,
                                    requests_handled=0,
                                    error_rate=0.0,
                                    custom_metrics={
                                        "adapter_id": adapter_info.adapter_id,
                                        "adapter_type": adapter_info.adapter_type,
                                    },
                                )

                    return adapter_metrics

            except Exception as e:
                logger.error(f"Failed to get adapter list from control service: {e}")

        # Fallback: Check bootstrap adapters directly
        if self.runtime and hasattr(self.runtime, "adapters"):
            for adapter in self.runtime.adapters:
                if adapter_type in adapter.__class__.__name__.lower():
                    adapter_id = f"{adapter_type}_bootstrap"

                    try:
                        metrics = await self._get_adapter_metrics(adapter)
                        adapter_metrics[adapter_id] = self._create_telemetry_data(
                            metrics, None, adapter_id, healthy=bool(metrics)
                        )
                    except Exception as e:
                        logger.error(f"Error getting metrics from {adapter_id}: {e}")
                        adapter_metrics[adapter_id] = ServiceTelemetryData(
                            healthy=False, uptime_seconds=0.0, error_count=1, requests_handled=0, error_rate=1.0
                        )

        return adapter_metrics

    def get_fallback_metrics(self, _service_name: Optional[str] = None, _healthy: bool = False) -> ServiceTelemetryData:
        """NO FALLBACKS. Real metrics or nothing.

        Parameters are accepted for compatibility but ignored - no fake metrics.
        """
        # NO FAKE METRICS. Services must implement get_metrics() or they get nothing.
        # Return empty telemetry data instead of empty dict
        return ServiceTelemetryData(
            healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
        )

    def status_to_telemetry(self, status: Any) -> dict:
        """Convert ServiceStatus to telemetry dict."""
        if hasattr(status, "model_dump"):
            return status.model_dump()
        elif hasattr(status, "__dict__"):
            return status.__dict__
        else:
            return {"status": str(status)}

    def _process_service_metrics(self, service_data: ServiceTelemetryData | Dict) -> tuple:
        """Process metrics for a single service."""
        # Handle both ServiceTelemetryData objects and legacy dicts
        if isinstance(service_data, ServiceTelemetryData):
            is_healthy = service_data.healthy
            errors = service_data.error_count or 0
            requests = service_data.requests_handled or 0
            error_rate = service_data.error_rate or 0.0
            uptime = service_data.uptime_seconds or 0
        else:
            # Legacy dict handling (for backwards compatibility during migration)
            is_healthy = service_data.get("healthy", False) or service_data.get("available", False)
            errors = service_data.get("error_count", 0)
            requests = service_data.get("request_count", 0)
            error_rate = service_data.get("error_rate", 0.0)
            uptime = service_data.get("uptime_seconds", 0)

        return is_healthy, errors, requests, error_rate, uptime

    def _aggregate_service_metrics(self, telemetry: Dict[str, Dict[str, Union[ServiceTelemetryData, Dict]]]) -> tuple:
        """Aggregate metrics from all services."""
        total_services = 0
        healthy_services = 0
        total_errors = 0
        total_requests = 0
        min_uptime = float("inf")
        error_rates = []

        for category_name, category_data in telemetry.items():
            # Skip covenant category as it contains computed metrics, not service data
            if category_name == "covenant":
                continue

            for service_data in category_data.values():
                total_services += 1
                is_healthy, errors, requests, error_rate, uptime = self._process_service_metrics(service_data)

                if is_healthy:
                    healthy_services += 1

                total_errors += errors
                total_requests += requests

                if error_rate > 0:
                    error_rates.append(error_rate)

                if uptime > 0 and uptime < min_uptime:
                    min_uptime = uptime

        return total_services, healthy_services, total_errors, total_requests, min_uptime, error_rates

    def _extract_metric_value(self, metrics_obj: Any, metric_name: str, default: Any = 0) -> Any:
        """Extract a metric value from ServiceTelemetryData or dict."""
        if isinstance(metrics_obj, ServiceTelemetryData):
            if metrics_obj.custom_metrics:
                return metrics_obj.custom_metrics.get(metric_name, default)
        elif isinstance(metrics_obj, dict):
            return metrics_obj.get(metric_name, default)
        return default

    def _extract_governance_metrics(
        self, telemetry: Dict, service_name: str, metric_mappings: Dict[str, str]
    ) -> Dict[str, Any]:
        """Extract metrics from a governance service."""
        results = {}
        if "governance" in telemetry and service_name in telemetry["governance"]:
            metrics = telemetry["governance"][service_name]
            for covenant_key, service_key in metric_mappings.items():
                results[covenant_key] = self._extract_metric_value(metrics, service_key)
        return results

    def compute_covenant_metrics(
        self, telemetry: Dict[str, Dict[str, Union[ServiceTelemetryData, Dict]]]
    ) -> Dict[str, Union[float, int, str]]:
        """
        Compute covenant/ethics metrics from governance services.

        These metrics track ethical decision-making and covenant compliance.
        """
        covenant_metrics = {
            "wise_authority_deferrals": 0,
            "filter_matches": 0,
            "thoughts_processed": 0,
            "self_observation_insights": 0,
        }

        try:
            # Extract metrics from each governance service
            wa_metrics = self._extract_governance_metrics(
                telemetry,
                "wise_authority",
                {"wise_authority_deferrals": "deferral_count", "thoughts_processed": "guidance_requests"},
            )
            covenant_metrics.update(wa_metrics)

            filter_metrics = self._extract_governance_metrics(
                telemetry, "adaptive_filter", {"filter_matches": "filter_actions"}
            )
            covenant_metrics.update(filter_metrics)

            so_metrics = self._extract_governance_metrics(
                telemetry, "self_observation", {"self_observation_insights": "insights_generated"}
            )
            covenant_metrics.update(so_metrics)

        except Exception as e:
            logger.error(f"Failed to compute covenant metrics: {e}")

        return covenant_metrics

    def calculate_aggregates(
        self, telemetry: Dict[str, Dict[str, Union[ServiceTelemetryData, Dict]]]
    ) -> Dict[str, Union[bool, int, float, str]]:
        """Calculate system-wide aggregate metrics."""
        # Get aggregated metrics
        total_services, healthy_services, total_errors, total_requests, min_uptime, error_rates = (
            self._aggregate_service_metrics(telemetry)
        )

        # Calculate overall metrics
        overall_error_rate = sum(error_rates) / len(error_rates) if error_rates else 0.0

        return {
            "system_healthy": healthy_services >= (total_services * 0.9),
            "services_online": healthy_services,
            "services_total": total_services,
            "overall_error_rate": round(overall_error_rate, 4),
            "overall_uptime_seconds": int(min_uptime) if min_uptime != float("inf") else 0,
            "total_errors": total_errors,
            "total_requests": total_requests,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


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
        self._runtime = runtime
        # Re-create aggregator if it exists to include runtime
        if self._telemetry_aggregator and self._service_registry:
            self._telemetry_aggregator = TelemetryAggregator(
                service_registry=self._service_registry, time_service=self._time_service, runtime=self._runtime
            )

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
                await self._store_telemetry_metrics(telemetry_data, thought_id, task_id)
                results.memories_created += 1

            # 2. Store resource usage - Note: no current_round_resources in SystemSnapshot
            # Resource data would come from telemetry_summary if needed

            # 3. Store behavioral data (task/thought summaries)
            if snapshot.current_task_details:
                behavioral_data = BehavioralData(
                    data_type="task",
                    content=(
                        snapshot.current_task_details.model_dump() if hasattr(snapshot.current_task_details, "model_dump") else {}
                    ),
                    metadata={"thought_id": thought_id},
                )
                await self._store_behavioral_data(behavioral_data, "task", thought_id)
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
                "user_profiles": [p.model_dump() for p in user_profiles],
                "channel_context": channel_context.model_dump() if channel_context else None,
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
            # Query different metric types - use actual metric names that exist
            metric_types = [
                ("llm.tokens.total", "tokens"),
                ("llm_tokens_used", "tokens"),  # Legacy metric name
                ("llm.tokens.input", "tokens"),
                ("llm.tokens.output", "tokens"),
                ("llm.cost.cents", "cost"),
                ("llm.environmental.carbon_grams", "carbon"),
                ("llm.environmental.energy_kwh", "energy"),
                ("llm.latency.ms", "latency"),
                ("thought_processing_completed", "thoughts"),
                ("thought_processing_started", "thoughts"),
                ("action_selected_task_complete", "tasks"),
                ("handler_invoked_total", "messages"),  # Use handler invocations as proxy for messages
                ("error.occurred", "errors"),  # This might not exist yet
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

            # Calculate average thought depth from database
            avg_thought_depth = 0.0
            try:
                from ciris_engine.logic.persistence import get_db_connection

                # Get the memory service to access its db_path
                memory_service = await self._memory_bus.get_service(handler_name="telemetry_service")
                if memory_service:
                    db_path = getattr(memory_service, "db_path", None)
                    with get_db_connection(db_path=db_path) as conn:
                        cursor = conn.cursor()
                        # Query thoughts from the last 24 hours and calculate average thought_depth
                        cursor.execute(
                            """
                            SELECT AVG(thought_depth) as avg_depth
                            FROM thoughts
                            WHERE created_at >= datetime('now', '-24 hours')
                        """
                        )
                        result = cursor.fetchone()
                        if result and result[0] is not None:
                            avg_thought_depth = float(result[0])
                        logger.debug(f"Calculated average thought depth: {avg_thought_depth}")
            except Exception as e:
                logger.warning(f"Failed to calculate average thought depth: {e}")
                avg_thought_depth = 1.5  # Fallback value

            # Calculate queue saturation from runtime control service
            queue_saturation = 0.0
            try:
                # Access runtime control service via bus manager if available
                runtime_control_bus = getattr(self, "_runtime_control_bus", None)
                if runtime_control_bus:
                    runtime_control = await runtime_control_bus.get_service(handler_name="telemetry_service")
                    if runtime_control:
                        processor_queue_status = await runtime_control.get_processor_queue_status()
                        if processor_queue_status and processor_queue_status.max_size > 0:
                            queue_saturation = processor_queue_status.queue_size / processor_queue_status.max_size
                            queue_saturation = min(1.0, max(0.0, queue_saturation))  # Clamp to 0-1 range
                            logger.debug(
                                f"Calculated queue saturation: {queue_saturation:.3f} ({processor_queue_status.queue_size}/{processor_queue_status.max_size})"
                            )
                        else:
                            logger.debug("Processor queue status not available or max_size is 0")
                    else:
                        logger.debug("Runtime control service not available")
                else:
                    logger.debug("Runtime control bus not available")
            except Exception as e:
                logger.warning(f"Failed to calculate queue saturation: {e}")
                queue_saturation = 0.0  # Fallback value

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
                avg_thought_depth=avg_thought_depth,
                queue_saturation=queue_saturation,
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

            self._telemetry_aggregator = TelemetryAggregator(
                service_registry=self._service_registry, time_service=self._time_service, runtime=self._runtime
            )

    def _check_cache(self, cache_key: str, now: datetime) -> Optional[AggregatedTelemetryResponse]:
        """Check cache for valid telemetry data."""
        if cache_key in self._telemetry_aggregator.cache:
            cached_time, cached_data = self._telemetry_aggregator.cache[cache_key]
            if now - cached_time < self._telemetry_aggregator.cache_ttl:
                if isinstance(cached_data, AggregatedTelemetryResponse):
                    if cached_data.metadata:
                        cached_data.metadata.cache_hit = True
                    return cached_data
                return cached_data
        return None

    def _convert_telemetry_to_services(self, telemetry: Dict) -> Dict[str, ServiceTelemetryData]:
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

    async def _store_correlation(self, correlation: "ServiceCorrelation") -> None:
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
            attributes = {
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
