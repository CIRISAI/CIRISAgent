"""
Registry collection helpers for TelemetryAggregator.

Contains functions for collecting telemetry from dynamic services
registered in ServiceRegistry.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.utils.jsondict_helpers import get_str
from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


# Simple pattern matches for service name generation (no complex logic)
_SIMPLE_PATTERNS: Dict[str, str] = {
    "APITool": "api_tool",
    "APIRuntime": "api_runtime",
    "SecretsToolService": "secrets",
    "MockLLM": "mock",
    "LocalGraphMemory": "local_graph",
    "GraphConfig": "graph",
    "TimeService": "time",
    "WiseAuthority": "wise_authority",
}


def _extract_adapter_suffix(adapter_id: str, separator: str, fallback_id: str) -> str:
    """Extract suffix from adapter ID or return fallback."""
    if adapter_id and separator in adapter_id:
        return adapter_id.split(separator)[-1][:8]
    return fallback_id


def _get_instance_id(provider_name: str) -> str:
    """Get short instance ID from provider name."""
    return str(id(provider_name))[-6:]


def _get_adapter_id(provider_metadata: Optional[JSONDict]) -> str:
    """Extract adapter_id from provider metadata."""
    return get_str(provider_metadata, "adapter_id", "") if provider_metadata else ""


def _handle_adapter_pattern(
    service_type: str, provider_name: str, provider_metadata: Optional[JSONDict]
) -> Optional[str]:
    """Handle adapter-specific naming patterns. Returns None if no match."""
    adapter_id = _get_adapter_id(provider_metadata)
    instance_id = _get_instance_id(provider_name)

    if "APICommunication" in provider_name:
        suffix = _extract_adapter_suffix(adapter_id, "_", instance_id)
        return f"{service_type}_api_{suffix}"

    if "CLIAdapter" in provider_name:
        suffix = _extract_adapter_suffix(adapter_id, "@", instance_id) if "@" in adapter_id else instance_id
        return f"{service_type}_cli_{suffix}"

    if "DiscordAdapter" in provider_name or "Discord" in provider_name:
        suffix = _extract_adapter_suffix(adapter_id, "_", instance_id)
        return f"{service_type}_discord_{suffix}"

    return None


def _handle_simple_pattern(service_type: str, provider_name: str) -> Optional[str]:
    """Handle simple pattern matches. Returns None if no match."""
    for pattern, suffix in _SIMPLE_PATTERNS.items():
        if pattern in provider_name:
            return f"{service_type}_{suffix}"
    return None


def _handle_llm_pattern(service_type: str, provider_name: str) -> Optional[str]:
    """Handle LLM provider patterns. Returns None if no match."""
    if "OpenAI" in provider_name:
        return f"{service_type}_openai_{_get_instance_id(provider_name)}"
    if "Anthropic" in provider_name:
        return f"{service_type}_anthropic_{_get_instance_id(provider_name)}"
    return None


def generate_semantic_service_name(
    service_type: str, provider_name: str, provider_metadata: Optional[JSONDict] = None
) -> str:
    """
    Generate a semantic name for a dynamic service.

    For adapters: {service_type}_{adapter_type}_{adapter_id_suffix}
    For LLM providers: {service_type}_{provider_type}_{instance_id}
    For others: {service_type}_{provider_name_cleaned}
    """
    # Try adapter patterns first
    result = _handle_adapter_pattern(service_type, provider_name, provider_metadata)
    if result:
        return result

    # Try simple patterns
    result = _handle_simple_pattern(service_type, provider_name)
    if result:
        return result

    # Try LLM patterns
    result = _handle_llm_pattern(service_type, provider_name)
    if result:
        return result

    # Default fallback
    provider_cleaned = provider_name.replace("Service", "").replace("Adapter", "")
    return f"{service_type}_{provider_cleaned.lower()}_{_get_instance_id(provider_name)}"


# Map of known core service implementations to their category names
# Only skip services that are ALREADY collected via CATEGORIES
# Do NOT skip adapter-provided services like APIToolService, CLIAdapter, etc.
_CORE_SERVICE_MAPPINGS: Dict[str, str] = {
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


def _extract_provider_class_name(provider_name: str) -> str:
    """Extract class name without instance ID (e.g., 'GraphConfigService_123456' -> 'GraphConfigService')."""
    return provider_name.split("_")[0] if "_" in provider_name else provider_name


def _is_core_service(provider_class_name: str) -> Tuple[bool, Optional[str]]:
    """Check if provider is a core service. Returns (is_core, category_name)."""
    if provider_class_name in _CORE_SERVICE_MAPPINGS:
        return True, _CORE_SERVICE_MAPPINGS[provider_class_name]
    return False, None


def _is_in_categories(provider_class_name: str, categories: Dict[str, List[str]]) -> bool:
    """Check if provider class name matches any service in CATEGORIES."""
    provider_lower = provider_class_name.lower()
    for cat_services in categories.values():
        if provider_lower in [s.lower() for s in cat_services]:
            return True
    return False


def _check_already_collected(
    provider_name: str, provider_class_name: str, categories: Dict[str, List[str]]
) -> bool:
    """Check if provider is already collected via CATEGORIES or core service mappings."""
    is_core, category_name = _is_core_service(provider_class_name)
    if is_core:
        logger.debug(
            f"[TELEMETRY] Skipping core service {provider_name} (class: {provider_class_name}) "
            f"- already collected as {category_name}"
        )
        return True

    if _is_in_categories(provider_class_name, categories):
        logger.debug(f"[TELEMETRY] Skipping {provider_name} - already in CATEGORIES")
        return True

    return False


def _process_provider(
    service_type: str,
    provider: Dict[str, Any],
    categories: Dict[str, List[str]],
    collect_from_registry_provider_coro: Any,
    tasks: List[Any],
    service_info: List[Tuple[str, str]],
) -> None:
    """Process a single provider, adding collection task if not already collected."""
    provider_name = provider.get("name", "")
    provider_metadata = provider.get("metadata", {})
    provider_class_name = _extract_provider_class_name(provider_name)

    logger.debug(
        f"[TELEMETRY] Checking registry service: {service_type}.{provider_name} (class: {provider_class_name})"
    )

    if _check_already_collected(provider_name, provider_class_name, categories):
        return

    semantic_name = generate_semantic_service_name(service_type, provider_name, provider_metadata)
    task = asyncio.create_task(collect_from_registry_provider_coro(service_type, provider_name))
    tasks.append(task)
    service_info.append(("registry", semantic_name))
    logger.debug(f"[TELEMETRY] Adding registry service: {semantic_name} (was: {service_type}.{provider_name})")


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
    if not service_registry:
        return {"tasks": [], "info": []}

    tasks: List[Any] = []
    service_info: List[Tuple[str, str]] = []

    try:
        provider_info = service_registry.get_provider_info()
        for service_type, providers in provider_info.get("services", {}).items():
            for provider in providers:
                _process_provider(
                    service_type, provider, categories, collect_from_registry_provider_coro, tasks, service_info
                )
    except Exception as e:
        logger.warning(f"Failed to collect registry services: {e}")

    return {"tasks": tasks, "info": service_info}


def _create_unhealthy_telemetry() -> ServiceTelemetryData:
    """Create telemetry data for unhealthy/not-found provider."""
    return ServiceTelemetryData(
        healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
    )


def _find_target_provider(
    service_registry: Any, service_type: str, provider_name: str
) -> Optional[Any]:
    """Find the exact provider instance by matching the full provider_name."""
    provider_info = service_registry.get_provider_info()
    service_providers_list = provider_info.get("services", {}).get(service_type, [])

    for service_providers in service_providers_list:
        if service_providers.get("name") != provider_name:
            continue
        # Found matching name, now get the actual provider instance
        providers = service_registry.get_services_by_type(service_type)
        for provider in providers:
            provider_full_name = f"{provider.__class__.__name__}_{id(provider)}"
            if provider_full_name == provider_name:
                return provider
        break

    return None


def _convert_dict_to_telemetry(metrics: Dict[str, Any]) -> ServiceTelemetryData:
    """Convert dict metrics to ServiceTelemetryData."""
    return ServiceTelemetryData(
        healthy=metrics.get("healthy", True),
        uptime_seconds=metrics.get("uptime_seconds", 0.0),
        error_count=metrics.get("error_count", 0),
        requests_handled=metrics.get("requests_handled", 0),
        error_rate=metrics.get("error_rate", 0.0),
        custom_metrics=metrics.get("custom_metrics"),
        last_health_check=metrics.get("last_health_check"),
    )


async def _get_metrics_from_provider(
    provider: Any, provider_name: str
) -> Optional[ServiceTelemetryData]:
    """Try to get metrics from provider's get_metrics method."""
    if not hasattr(provider, "get_metrics"):
        return None

    metrics = (
        await provider.get_metrics()
        if asyncio.iscoroutinefunction(provider.get_metrics)
        else provider.get_metrics()
    )

    if isinstance(metrics, ServiceTelemetryData):
        logger.debug(f"[TELEMETRY] Got metrics from {provider_name}: healthy={metrics.healthy}")
        return metrics
    if isinstance(metrics, dict):
        return _convert_dict_to_telemetry(metrics)

    return None


async def _get_health_from_provider(provider: Any) -> Optional[ServiceTelemetryData]:
    """Try to get health status from provider's is_healthy method."""
    if not hasattr(provider, "is_healthy"):
        return None

    is_healthy = (
        await provider.is_healthy()
        if asyncio.iscoroutinefunction(provider.is_healthy)
        else provider.is_healthy()
    )
    return ServiceTelemetryData(
        healthy=is_healthy,
        uptime_seconds=0.0,
        error_count=0,
        requests_handled=0,
        error_rate=0.0,
    )


async def collect_from_registry_provider(
    service_registry: Any, service_type: str, provider_name: str
) -> ServiceTelemetryData:
    """
    Collect telemetry from a specific registry provider.

    Returns ServiceTelemetryData for the provider.
    """
    try:
        target_provider = _find_target_provider(service_registry, service_type, provider_name)
        if not target_provider:
            logger.debug(f"[TELEMETRY] Provider {provider_name} not found in {service_type}")
            return _create_unhealthy_telemetry()

        # Try get_metrics first
        result = await _get_metrics_from_provider(target_provider, provider_name)
        if result:
            return result

        # Fall back to is_healthy
        result = await _get_health_from_provider(target_provider)
        if result:
            return result

        # NO DEFAULTS - if no health check, service is unhealthy
        return _create_unhealthy_telemetry()

    except Exception as e:
        logger.warning(f"Failed to collect from registry provider {provider_name}: {e}")
        return _create_unhealthy_telemetry()
