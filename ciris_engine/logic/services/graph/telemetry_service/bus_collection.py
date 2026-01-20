"""
Bus collection helpers for TelemetryAggregator.

Contains functions for collecting telemetry from message buses and components.
"""

import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData

logger = logging.getLogger(__name__)


# Map bus names to bus_manager attributes
BUS_ATTR_MAP = {
    "llm_bus": "llm",
    "memory_bus": "memory",
    "communication_bus": "communication",
    "wise_bus": "wise",
    "tool_bus": "tool",
    "runtime_control_bus": "runtime_control",
}

# Map bus names to their specific uptime metric names
UPTIME_METRIC_MAP = {
    "llm_bus": "llm_uptime_seconds",
    "memory_bus": "memory_uptime_seconds",
    "communication_bus": "communication_uptime_seconds",
    "wise_bus": "wise_uptime_seconds",
    "tool_bus": "tool_uptime_seconds",
    "runtime_control_bus": "runtime_control_uptime_seconds",
}


def _find_bus_from_runtime(runtime: Any, bus_name: str) -> Optional[Any]:
    """Find bus from runtime.bus_manager."""
    if not runtime:
        return None
    bus_manager = getattr(runtime, "bus_manager", None)
    if not bus_manager:
        return None
    attr_name = BUS_ATTR_MAP.get(bus_name)
    if not attr_name:
        return None
    bus = getattr(bus_manager, attr_name, None)
    if bus:
        logger.debug(f"Found {bus_name} from runtime.bus_manager.{attr_name}")
    return bus


def _find_bus_from_registry(service_registry: Any, bus_name: str) -> Optional[Any]:
    """Find bus from service registry's agent."""
    if not hasattr(service_registry, "_agent"):
        return None
    agent = service_registry._agent
    return getattr(agent, bus_name, None)


def _extract_metrics_dict(bus: Any) -> Dict[str, Any]:
    """Extract metrics dict from bus, handling Pydantic models."""
    metrics_result = bus.get_metrics()
    if hasattr(metrics_result, "model_dump"):
        metrics: Dict[str, Any] = metrics_result.model_dump()
        # Merge additional_metrics into top-level for backward compatibility
        if "additional_metrics" in metrics:
            additional = metrics.pop("additional_metrics")
            metrics.update(additional)
        return metrics
    # metrics_result is already a dict
    return dict(metrics_result) if metrics_result else {}


def _determine_bus_health(bus: Any) -> bool:
    """Determine if bus is healthy based on provider count."""
    if hasattr(bus, "get_providers"):
        return len(bus.get_providers()) > 0
    if hasattr(bus, "providers"):
        return len(bus.providers) > 0
    return True


def _build_telemetry_from_metrics(metrics: Dict[str, Any], bus_name: str, is_healthy: bool) -> ServiceTelemetryData:
    """Build ServiceTelemetryData from metrics dict."""
    uptime_metric = UPTIME_METRIC_MAP.get(bus_name, "uptime_seconds")
    filtered_metrics = {k: v for k, v in metrics.items() if v is not None and isinstance(v, (int, float, str))}

    return ServiceTelemetryData(
        healthy=is_healthy,
        uptime_seconds=metrics.get(uptime_metric, metrics.get("uptime_seconds", 0.0)),
        error_count=metrics.get("error_count", 0) or metrics.get("errors_last_hour", 0),
        requests_handled=metrics.get("request_count") or metrics.get("requests_handled", 0) or metrics.get("messages_sent", 0),
        error_rate=metrics.get("error_rate", 0.0),
        memory_mb=metrics.get("memory_mb"),
        custom_metrics=filtered_metrics,
    )


async def _collect_from_bus_with_metrics(bus: Any, bus_name: str) -> ServiceTelemetryData:
    """Collect telemetry from bus using get_metrics()."""
    metrics = _extract_metrics_dict(bus)
    is_healthy = _determine_bus_health(bus)
    return _build_telemetry_from_metrics(metrics, bus_name, is_healthy)


async def collect_from_bus(
    runtime: Any,
    service_registry: Any,
    bus_name: str,
    get_fallback_metrics: Callable[[Optional[str]], ServiceTelemetryData],
) -> ServiceTelemetryData:
    """Collect telemetry from a message bus."""
    try:
        bus = _find_bus_from_runtime(runtime, bus_name)
        if not bus:
            bus = _find_bus_from_registry(service_registry, bus_name)

        if not bus:
            return get_fallback_metrics(bus_name)

        if hasattr(bus, "get_metrics"):
            try:
                return await _collect_from_bus_with_metrics(bus, bus_name)
            except Exception as e:
                logger.error(f"Error getting metrics from {bus_name}: {e}")
                return get_fallback_metrics(bus_name)

        if hasattr(bus, "collect_telemetry"):
            result = await bus.collect_telemetry()
            return result  # type: ignore[no-any-return]

        return get_fallback_metrics(bus_name)

    except Exception as e:
        logger.error(f"Failed to collect from {bus_name}: {e}")
        return get_fallback_metrics(bus_name)


def _get_empty_telemetry() -> ServiceTelemetryData:
    """Return empty telemetry data for unavailable components."""
    return ServiceTelemetryData(healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0)


def _find_component(runtime: Any, component_name: str) -> Optional[Any]:
    """Find component on runtime by name."""
    if not runtime:
        return None
    component = getattr(runtime, component_name, None)
    if component:
        logger.debug(f"[TELEMETRY] Got {component_name}: {component.__class__.__name__}")
    else:
        logger.debug(f"[TELEMETRY] Component {component_name} not found on runtime")
    return component


async def collect_from_component(
    runtime: Any,
    component_name: str,
    try_collect_metrics: Callable[[Any], Coroutine[Any, Any, Optional[ServiceTelemetryData]]],
) -> ServiceTelemetryData:
    """Collect telemetry from runtime components."""
    logger.debug(f"[TELEMETRY] Collecting from component: {component_name}")
    try:
        component = _find_component(runtime, component_name)
        if not component:
            return _get_empty_telemetry()

        logger.debug(f"[TELEMETRY] Trying to collect metrics from {component.__class__.__name__}")
        metrics = await try_collect_metrics(component)
        if metrics:
            logger.debug(f"[TELEMETRY] Got metrics from {component_name}: healthy={metrics.healthy}")
            return metrics

        logger.debug(f"[TELEMETRY] No metrics from {component_name}")
        return _get_empty_telemetry()

    except Exception as e:
        logger.error(f"Failed to collect from component {component_name}: {e}")
        return _get_empty_telemetry()
