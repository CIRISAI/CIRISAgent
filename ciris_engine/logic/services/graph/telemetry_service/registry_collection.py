"""
Registry collection helpers for TelemetryAggregator.

Contains functions for collecting telemetry from dynamic services
registered in ServiceRegistry.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic.utils.jsondict_helpers import get_str
from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def generate_semantic_service_name(
    service_type: str, provider_name: str, provider_metadata: Optional[JSONDict] = None
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


def collect_from_registry_services(
    service_registry: Any,
    categories: Dict[str, List[str]],
    collect_from_registry_provider_coro: Any,
) -> Dict[str, List[Any]]:
    """
    Collect telemetry from dynamic services registered in ServiceRegistry.

    Returns dict with 'tasks' and 'info' lists for dynamic services.

    Args:
        service_registry: The service registry instance
        categories: The CATEGORIES dict from TelemetryAggregator
        collect_from_registry_provider_coro: Coroutine function to collect from a provider
    """
    tasks: List[Any] = []
    service_info: List[tuple[str, str]] = []

    if not service_registry:
        return {"tasks": [], "info": []}

    try:
        # Get all services from registry
        provider_info = service_registry.get_provider_info()

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
                    for cat_services in categories.values():
                        if provider_class_name.lower() in [s.lower() for s in cat_services]:
                            already_collected = True
                            logger.debug(f"[TELEMETRY] Skipping {provider_name} - already in CATEGORIES")
                            break

                if not already_collected:
                    # Generate semantic name for the service
                    semantic_name = generate_semantic_service_name(service_type, provider_name, provider_metadata)

                    # Create a collection task for this dynamic service
                    task = asyncio.create_task(collect_from_registry_provider_coro(service_type, provider_name))
                    tasks.append(task)
                    service_info.append(("registry", semantic_name))
                    logger.debug(
                        f"[TELEMETRY] Adding registry service: {semantic_name} (was: {service_type}.{provider_name})"
                    )

    except Exception as e:
        logger.warning(f"Failed to collect registry services: {e}")

    return {"tasks": tasks, "info": service_info}


async def collect_from_registry_provider(
    service_registry: Any, service_type: str, provider_name: str
) -> ServiceTelemetryData:
    """
    Collect telemetry from a specific registry provider.

    Returns ServiceTelemetryData for the provider.
    """
    try:
        # Get the provider instance from registry using provider_info to match exact instance
        provider_info = service_registry.get_provider_info()
        target_provider = None

        # Find the exact provider by matching the full provider_name (which includes instance ID)
        # This ensures we get the correct instance when multiple instances of the same class exist
        for service_providers in provider_info.get("services", {}).get(service_type, []):
            if service_providers.get("name") == provider_name:
                # Now get the actual provider instance from the services list
                providers = service_registry.get_services_by_type(service_type)
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
