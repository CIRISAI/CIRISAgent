"""
Bus collection helpers for TelemetryAggregator.

Contains functions for collecting telemetry from message buses and components.
"""

import logging
from typing import Any, Callable, Coroutine, Optional

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


async def collect_from_bus(
    runtime: Any,
    service_registry: Any,
    bus_name: str,
    get_fallback_metrics: Callable[[Optional[str]], ServiceTelemetryData],
) -> ServiceTelemetryData:
    """Collect telemetry from a message bus."""
    try:
        # Get the bus from runtime first, then agent/registry
        bus = None

        # Try runtime.bus_manager first
        if runtime:
            bus_manager = getattr(runtime, "bus_manager", None)
            if bus_manager:
                attr_name = BUS_ATTR_MAP.get(bus_name)
                if attr_name:
                    bus = getattr(bus_manager, attr_name, None)
                    if bus:
                        logger.debug(f"Found {bus_name} from runtime.bus_manager.{attr_name}")

        # Fall back to registry
        if not bus and hasattr(service_registry, "_agent"):
            agent = service_registry._agent
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

                    uptime_metric = UPTIME_METRIC_MAP.get(bus_name, "uptime_seconds")

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
                    return get_fallback_metrics(bus_name)
            elif hasattr(bus, "collect_telemetry"):
                result = await bus.collect_telemetry()
                # Bus collect_telemetry returns Any, assume it's ServiceTelemetryData
                return result  # type: ignore[no-any-return]
            else:
                return get_fallback_metrics(bus_name)
        else:
            return get_fallback_metrics(bus_name)

    except Exception as e:
        logger.error(f"Failed to collect from {bus_name}: {e}")
        return get_fallback_metrics(bus_name)


async def collect_from_component(
    runtime: Any,
    component_name: str,
    try_collect_metrics: Callable[[Any], Coroutine[Any, Any, Optional[ServiceTelemetryData]]],
) -> ServiceTelemetryData:
    """Collect telemetry from runtime components."""
    logger.debug(f"[TELEMETRY] Collecting from component: {component_name}")
    try:
        component = None

        # Map component names to runtime locations
        if runtime:
            if component_name == "service_registry":
                component = getattr(runtime, "service_registry", None)
                logger.debug(
                    f"[TELEMETRY] Got service_registry: {component.__class__.__name__ if component else 'None'}"
                )
            elif component_name == "agent_processor":
                component = getattr(runtime, "agent_processor", None)
                logger.debug(
                    f"[TELEMETRY] Got agent_processor: {component.__class__.__name__ if component else 'None'}"
                )

        # Try to get metrics from component
        if component:
            logger.debug(f"[TELEMETRY] Trying to collect metrics from {component.__class__.__name__}")
            metrics = await try_collect_metrics(component)
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
