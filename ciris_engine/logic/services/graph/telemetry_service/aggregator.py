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

from ciris_engine.logic.utils.jsondict_helpers import get_bool, get_dict, get_float, get_str
from ciris_engine.schemas.services.graph.telemetry import (
    AggregatedTelemetryResponse,
    ServiceTelemetryData,
)
from ciris_engine.schemas.types import JSONDict

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
        """
        Generate a semantic name for a dynamic service.

        For adapters: {service_type}_{adapter_type}_{adapter_id_suffix}
        For LLM providers: {service_type}_{provider_type}_{instance_id}
        For others: {service_type}_{provider_name_cleaned}
        """

        def _extract_adapter_suffix(adapter_id: str, separator: str = "_") -> str:
            """Extract suffix from adapter ID."""
            if adapter_id and separator in adapter_id:
                return adapter_id.split(separator)[-1][:8]
            return str(id(provider_name))[-6:]

        def _get_instance_id() -> str:
            """Get short instance ID."""
            return str(id(provider_name))[-6:]

        # Dispatch table for known provider patterns
        if "APICommunication" in provider_name:
            adapter_id = get_str(provider_metadata, "adapter_id", "") if provider_metadata else ""
            suffix = _extract_adapter_suffix(adapter_id, "_")
            return f"{service_type}_api_{suffix}"

        if "CLIAdapter" in provider_name:
            adapter_id = get_str(provider_metadata, "adapter_id", "") if provider_metadata else ""
            suffix = _extract_adapter_suffix(adapter_id, "@") if "@" in adapter_id else _get_instance_id()
            return f"{service_type}_cli_{suffix}"

        if "DiscordAdapter" in provider_name or "Discord" in provider_name:
            adapter_id = get_str(provider_metadata, "adapter_id", "") if provider_metadata else ""
            suffix = _extract_adapter_suffix(adapter_id, "_")
            return f"{service_type}_discord_{suffix}"

        # Simple pattern matches (no complex logic)
        simple_patterns = {
            "APITool": "api_tool",
            "APIRuntime": "api_runtime",
            "SecretsToolService": "secrets",
            "MockLLM": "mock",
            "LocalGraphMemory": "local_graph",
            "GraphConfig": "graph",
            "TimeService": "time",
            "WiseAuthority": "wise_authority",
        }

        for pattern, suffix in simple_patterns.items():
            if pattern in provider_name:
                return f"{service_type}_{suffix}"

        # LLM providers
        if "OpenAI" in provider_name or "Anthropic" in provider_name:
            provider_type = "openai" if "OpenAI" in provider_name else "anthropic"
            return f"{service_type}_{provider_type}_{_get_instance_id()}"

        # Default fallback
        provider_cleaned = provider_name.replace("Service", "").replace("Adapter", "")
        return f"{service_type}_{provider_cleaned.lower()}_{_get_instance_id()}"

    def collect_from_registry_services(self) -> Dict[str, List[Any]]:
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
            # Get the provider instance from registry using provider_info to match exact instance
            provider_info = self.service_registry.get_provider_info()
            target_provider = None

            # Find the exact provider by matching the full provider_name (which includes instance ID)
            # This ensures we get the correct instance when multiple instances of the same class exist
            for service_providers in provider_info.get("services", {}).get(service_type, []):
                if service_providers.get("name") == provider_name:
                    # Now get the actual provider instance from the services list
                    providers = self.service_registry.get_services_by_type(service_type)
                    for provider in providers:
                        # Match by checking if the provider's id matches the one in provider_name
                        provider_full_name = f"{provider.__class__.__name__}_{id(provider)}"
                        if provider_full_name == provider_name:
                            target_provider = provider
                            break
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

    def _get_service_from_runtime(self, service_name: str) -> Any:
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
            "secrets_tool": "secrets_tool_service",
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

    def _get_service_from_registry(self, service_name: str) -> Any:
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

    def _convert_dict_to_telemetry(self, metrics: JSONDict, service_name: str) -> ServiceTelemetryData:
        """Convert dict metrics to ServiceTelemetryData with proper uptime detection."""
        # Look for various uptime keys
        uptime = (
            get_float(metrics, "uptime_seconds", 0.0)
            or get_float(metrics, "incident_uptime_seconds", 0.0)
            or get_float(metrics, "tsdb_uptime_seconds", 0.0)
            or get_float(metrics, "auth_uptime_seconds", 0.0)
            or get_float(metrics, "scheduler_uptime_seconds", 0.0)
            or 0.0
        )

        # If service has uptime > 0, consider it healthy unless explicitly marked unhealthy
        healthy = get_bool(metrics, "healthy", uptime > 0.0)

        logger.debug(
            f"Converting dict metrics to ServiceTelemetryData for {service_name}: healthy={healthy}, uptime={uptime}"
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

    async def _try_get_metrics_method(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try to collect metrics via get_metrics() method."""
        if not hasattr(service, "get_metrics"):
            logger.debug(f"Service {type(service).__name__} does not have get_metrics method")
            return None

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
                return self._convert_dict_to_telemetry(metrics, type(service).__name__)

            return None
        except Exception as e:
            logger.error(f"Error calling get_metrics on {type(service).__name__}: {e}")
            return None

    def _try_collect_metrics_method(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try to collect metrics via _collect_metrics() method."""
        if not hasattr(service, "_collect_metrics"):
            return None

        try:
            metrics = service._collect_metrics()
            if isinstance(metrics, ServiceTelemetryData):
                return metrics
            elif isinstance(metrics, dict):
                return ServiceTelemetryData(
                    healthy=metrics.get("healthy", False),
                    uptime_seconds=metrics.get("uptime_seconds"),
                    error_count=metrics.get("error_count"),
                    requests_handled=metrics.get("request_count") or metrics.get("requests_handled"),
                    error_rate=metrics.get("error_rate"),
                    memory_mb=metrics.get("memory_mb"),
                    custom_metrics=metrics.get("custom_metrics"),
                )
        except Exception as e:
            logger.error(f"Error calling _collect_metrics on {type(service).__name__}: {e}")

        return None

    async def _try_get_status_method(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try to collect metrics via get_status() method."""
        if not hasattr(service, "get_status"):
            return None

        try:
            status = service.get_status()
            if asyncio.iscoroutine(status):
                status = await status
            # status_to_telemetry returns dict, not ServiceTelemetryData
            # Return None as we can't convert properly here
            return None
        except Exception as e:
            logger.error(f"Error calling get_status on {type(service).__name__}: {e}")
            return None

    async def _try_collect_metrics(self, service: Any) -> Optional[ServiceTelemetryData]:
        """Try different methods to collect metrics from service."""
        if not service:
            logger.debug("[TELEMETRY] Service is None, cannot collect metrics")
            return None

        # Try get_metrics first (most common)
        result = await self._try_get_metrics_method(service)
        if result:
            return result

        # Try _collect_metrics (fallback)
        result = self._try_collect_metrics_method(service)
        if result:
            return result

        # Try get_status (last resort)
        return await self._try_get_status_method(service)

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
                        metrics_result = bus.get_metrics()
                        # Convert BusMetrics (Pydantic model) to dict
                        # Buses now return typed BusMetrics instead of Dict[str, float]
                        if hasattr(metrics_result, "model_dump"):
                            metrics = metrics_result.model_dump()
                            # Merge additional_metrics into top-level for backward compatibility
                            if "additional_metrics" in metrics:
                                additional = metrics.pop("additional_metrics")
                                metrics.update(additional)
                        else:
                            # Fallback for any remaining dict returns
                            metrics = metrics_result

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

                        # Filter custom_metrics to only include valid types (int, float, str) and exclude None
                        filtered_metrics = {
                            k: v for k, v in metrics.items() if v is not None and isinstance(v, (int, float, str))
                        }

                        return ServiceTelemetryData(
                            healthy=is_healthy,
                            uptime_seconds=metrics.get(uptime_metric, metrics.get("uptime_seconds", 0.0)),
                            error_count=metrics.get("error_count", 0) or metrics.get("errors_last_hour", 0),
                            requests_handled=metrics.get("request_count")
                            or metrics.get("requests_handled", 0)
                            or metrics.get("messages_sent", 0),
                            error_rate=metrics.get("error_rate", 0.0),
                            memory_mb=metrics.get("memory_mb"),
                            custom_metrics=filtered_metrics,
                        )
                    except Exception as e:
                        logger.error(f"Error getting metrics from {bus_name}: {e}")
                        return self.get_fallback_metrics(bus_name)
                elif hasattr(bus, "collect_telemetry"):
                    result = await bus.collect_telemetry()
                    # Bus collect_telemetry returns Any, assume it's ServiceTelemetryData
                    return result  # type: ignore[no-any-return]
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
            return bool(adapter_info.is_running)
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

    async def _get_adapter_metrics(self, adapter_instance: Any) -> Optional[JSONDict]:
        """Get metrics from adapter instance."""
        if hasattr(adapter_instance, "get_metrics"):
            if asyncio.iscoroutinefunction(adapter_instance.get_metrics):
                result = await adapter_instance.get_metrics()
                return result  # type: ignore[no-any-return]
            result = adapter_instance.get_metrics()
            return result  # type: ignore[no-any-return]
        return None

    def _create_telemetry_data(
        self,
        metrics: JSONDict,
        adapter_info: Optional[Any] = None,
        adapter_id: Optional[str] = None,
        healthy: bool = True,
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

        custom_metrics: JSONDict = {"adapter_id": adapter_id} if adapter_id else {}
        if adapter_info:
            adapter_type_value: Any = adapter_info.adapter_type if hasattr(adapter_info, "adapter_type") else None
            if adapter_type_value is not None:  # Only add if not None
                custom_metrics["adapter_type"] = adapter_type_value
            if hasattr(adapter_info, "started_at") and adapter_info.started_at:
                custom_metrics["start_time"] = adapter_info.started_at.isoformat()

        # Update with custom_metrics from metrics, filtering out None values
        raw_custom_metrics = get_dict(metrics, "custom_metrics", {})
        if isinstance(raw_custom_metrics, dict):
            custom_metrics.update(
                {k: v for k, v in raw_custom_metrics.items() if v is not None and isinstance(v, (int, float, str))}
            )

        # Final filter to ensure all values are valid types (int, float, str) and not None
        filtered_custom_metrics = {
            k: v for k, v in custom_metrics.items() if v is not None and isinstance(v, (int, float, str))
        }

        return ServiceTelemetryData(
            healthy=healthy,
            uptime_seconds=metrics.get("uptime_seconds", 0.0),
            error_count=metrics.get("error_count", 0),
            requests_handled=metrics.get("request_count") or metrics.get("requests_handled", 0),
            error_rate=metrics.get("error_rate", 0.0),
            memory_mb=metrics.get("memory_mb"),
            custom_metrics=filtered_custom_metrics,
        )

    def _create_empty_telemetry(self, adapter_id: str, error_msg: Optional[str] = None) -> ServiceTelemetryData:
        """Create empty telemetry data for failed/unavailable adapter."""
        custom_metrics = {"adapter_id": adapter_id}
        if error_msg:
            custom_metrics["error"] = error_msg
            return ServiceTelemetryData(
                healthy=False,
                uptime_seconds=0.0,
                error_count=1,
                requests_handled=0,
                error_rate=1.0,
                custom_metrics=custom_metrics,
            )
        return ServiceTelemetryData(
            healthy=False,
            uptime_seconds=0.0,
            error_count=0,
            requests_handled=0,
            error_rate=0.0,
            custom_metrics=custom_metrics,
        )

    def _create_running_telemetry(self, adapter_info: Any) -> ServiceTelemetryData:
        """Create telemetry for running adapter without metrics."""
        uptime = 0.0
        if hasattr(adapter_info, "started_at") and adapter_info.started_at:
            uptime = (datetime.now(timezone.utc) - adapter_info.started_at).total_seconds()

        return ServiceTelemetryData(
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

    async def _collect_from_adapter_with_metrics(
        self, adapter_instance: Any, adapter_info: Any, adapter_id: str
    ) -> ServiceTelemetryData:
        """Collect metrics from a single adapter instance."""
        try:
            metrics = await self._get_adapter_metrics(adapter_instance)
            if metrics:
                return self._create_telemetry_data(metrics, adapter_info, adapter_id, healthy=True)
            else:
                return self._create_empty_telemetry(adapter_id)
        except Exception as e:
            logger.error(f"Error getting metrics from {adapter_id}: {e}")
            return self._create_empty_telemetry(adapter_id, str(e))

    async def _collect_from_control_service(self, adapter_type: str) -> Optional[Dict[str, ServiceTelemetryData]]:
        """Try to collect adapter metrics via control service."""
        if not self.runtime:
            return None

        try:
            control_service = await self._get_control_service()
            if not control_service or not hasattr(control_service, "list_adapters"):
                return None

            all_adapters = await control_service.list_adapters()
            adapter_metrics = {}

            for adapter_info in all_adapters:
                if adapter_info.adapter_type != adapter_type or not self._is_adapter_running(adapter_info):
                    continue

                adapter_instance = self._find_adapter_instance(adapter_type)
                if adapter_instance:
                    adapter_metrics[adapter_info.adapter_id] = await self._collect_from_adapter_with_metrics(
                        adapter_instance, adapter_info, adapter_info.adapter_id
                    )
                else:
                    adapter_metrics[adapter_info.adapter_id] = self._create_running_telemetry(adapter_info)

            return adapter_metrics

        except Exception as e:
            logger.error(f"Failed to get adapter list from control service: {e}")
            return None

    async def _collect_from_bootstrap_adapters(self, adapter_type: str) -> Dict[str, ServiceTelemetryData]:
        """Fallback: collect from bootstrap adapters directly."""
        adapter_metrics: Dict[str, ServiceTelemetryData] = {}

        if not self.runtime or not hasattr(self.runtime, "adapters"):
            return adapter_metrics

        for adapter in self.runtime.adapters:
            if adapter_type not in adapter.__class__.__name__.lower():
                continue

            adapter_id = f"{adapter_type}_bootstrap"
            adapter_metrics[adapter_id] = await self._collect_from_adapter_with_metrics(adapter, None, adapter_id)

        return adapter_metrics

    async def collect_from_adapter_instances(self, adapter_type: str) -> Dict[str, ServiceTelemetryData]:
        """
        Collect telemetry from ALL active adapter instances of a given type.

        Returns a dict mapping adapter_id to telemetry data.
        Multiple instances of the same adapter type can be running simultaneously.
        """
        # Try control service first
        adapter_metrics = await self._collect_from_control_service(adapter_type)
        if adapter_metrics is not None:
            return adapter_metrics

        # Fallback to bootstrap adapters
        return await self._collect_from_bootstrap_adapters(adapter_type)

    def get_fallback_metrics(self, _service_name: Optional[str] = None, _healthy: bool = False) -> ServiceTelemetryData:
        """NO FALLBACKS. Real metrics or nothing.

        Parameters are accepted for compatibility but ignored - no fake metrics.
        """
        # NO FAKE METRICS. Services must implement get_metrics() or they get nothing.
        # Return empty telemetry data instead of empty dict
        return ServiceTelemetryData(
            healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
        )

    def status_to_telemetry(self, status: Any) -> JSONDict:
        """Convert ServiceStatus to telemetry dict."""
        if hasattr(status, "model_dump"):
            result = status.model_dump()
            return result  # type: ignore[no-any-return]
        elif hasattr(status, "__dict__"):
            result = status.__dict__
            return result  # type: ignore[no-any-return]
        else:
            return {"status": str(status)}

    def _process_service_metrics(self, service_data: ServiceTelemetryData) -> Tuple[bool, int, int, float, float]:
        """Process metrics for a single service."""
        is_healthy = service_data.healthy
        errors = service_data.error_count or 0
        requests = service_data.requests_handled or 0
        error_rate = service_data.error_rate or 0.0
        uptime = service_data.uptime_seconds or 0

        return is_healthy, errors, requests, error_rate, uptime

    def _aggregate_service_metrics(
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
    ) -> Tuple[int, int, int, int, float, List[float]]:
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
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]], service_name: str, metric_mappings: Dict[str, str]
    ) -> Dict[str, Union[float, int, str]]:
        """Extract metrics from a governance service."""
        results = {}
        if "governance" in telemetry and service_name in telemetry["governance"]:
            metrics = telemetry["governance"][service_name]
            for covenant_key, service_key in metric_mappings.items():
                results[covenant_key] = self._extract_metric_value(metrics, service_key)
        return results

    def compute_covenant_metrics(
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
    ) -> Dict[str, Union[float, int, str]]:
        """
        Compute covenant/ethics metrics from governance services.

        These metrics track ethical decision-making and covenant compliance.
        """
        covenant_metrics: Dict[str, Union[float, int, str]] = {
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
        self, telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
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
