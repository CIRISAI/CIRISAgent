"""
Adapter collection helpers for TelemetryAggregator.

Contains functions for collecting telemetry from adapter instances.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ciris_engine.logic.utils.jsondict_helpers import get_dict
from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


async def get_control_service(runtime: Any, service_registry: Any) -> Optional[Any]:
    """Get the runtime control service."""
    if runtime and hasattr(runtime, "runtime_control_service"):
        return runtime.runtime_control_service
    elif service_registry:
        from ciris_engine.schemas.runtime.enums import ServiceType

        return await service_registry.get_service(ServiceType.RUNTIME_CONTROL)
    return None


def is_adapter_running(adapter_info: Any) -> bool:
    """Check if an adapter is running."""
    if hasattr(adapter_info, "is_running"):
        return bool(adapter_info.is_running)
    elif hasattr(adapter_info, "status"):
        from ciris_engine.schemas.services.core.runtime import AdapterStatus

        return adapter_info.status in [AdapterStatus.ACTIVE, AdapterStatus.RUNNING]
    return False


def find_adapter_instance(runtime: Any, adapter_type: str) -> Optional[Any]:
    """Find adapter instance in runtime."""
    if hasattr(runtime, "adapters"):
        for adapter in runtime.adapters:
            if adapter_type in adapter.__class__.__name__.lower():
                return adapter
    return None


async def get_adapter_metrics(adapter_instance: Any) -> Optional[JSONDict]:
    """Get metrics from adapter instance."""
    if hasattr(adapter_instance, "get_metrics"):
        if asyncio.iscoroutinefunction(adapter_instance.get_metrics):
            result = await adapter_instance.get_metrics()
            return result  # type: ignore[no-any-return]
        result = adapter_instance.get_metrics()
        return result  # type: ignore[no-any-return]
    return None


def create_telemetry_data(
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


def create_empty_telemetry(adapter_id: str, error_msg: Optional[str] = None) -> ServiceTelemetryData:
    """Create empty telemetry data for failed/unavailable adapter."""
    custom_metrics: JSONDict = {"adapter_id": adapter_id}
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


def create_running_telemetry(adapter_info: Any) -> ServiceTelemetryData:
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


async def collect_from_adapter_with_metrics(
    adapter_instance: Any, adapter_info: Optional[Any], adapter_id: str
) -> ServiceTelemetryData:
    """Collect metrics from a single adapter instance."""
    try:
        metrics = await get_adapter_metrics(adapter_instance)
        if metrics:
            return create_telemetry_data(metrics, adapter_info, adapter_id, healthy=True)
        else:
            return create_empty_telemetry(adapter_id)
    except Exception as e:
        logger.error(f"Error getting metrics from {adapter_id}: {e}")
        return create_empty_telemetry(adapter_id, str(e))


async def collect_from_control_service(
    runtime: Any, service_registry: Any, adapter_type: str
) -> Optional[Dict[str, ServiceTelemetryData]]:
    """Try to collect adapter metrics via control service."""
    if not runtime:
        return None

    try:
        control_service = await get_control_service(runtime, service_registry)
        if not control_service or not hasattr(control_service, "list_adapters"):
            return None

        all_adapters = await control_service.list_adapters()
        adapter_metrics: Dict[str, ServiceTelemetryData] = {}

        for adapter_info in all_adapters:
            if adapter_info.adapter_type != adapter_type or not is_adapter_running(adapter_info):
                continue

            adapter_instance = find_adapter_instance(runtime, adapter_type)
            if adapter_instance:
                adapter_metrics[adapter_info.adapter_id] = await collect_from_adapter_with_metrics(
                    adapter_instance, adapter_info, adapter_info.adapter_id
                )
            else:
                adapter_metrics[adapter_info.adapter_id] = create_running_telemetry(adapter_info)

        return adapter_metrics

    except Exception as e:
        logger.error(f"Failed to get adapter list from control service: {e}")
        return None


async def collect_from_bootstrap_adapters(runtime: Any, adapter_type: str) -> Dict[str, ServiceTelemetryData]:
    """Fallback: collect from bootstrap adapters directly."""
    adapter_metrics: Dict[str, ServiceTelemetryData] = {}

    if not runtime or not hasattr(runtime, "adapters"):
        return adapter_metrics

    for adapter in runtime.adapters:
        if adapter_type not in adapter.__class__.__name__.lower():
            continue

        adapter_id = f"{adapter_type}_bootstrap"
        adapter_metrics[adapter_id] = await collect_from_adapter_with_metrics(adapter, None, adapter_id)

    return adapter_metrics


async def collect_from_adapter_instances(
    runtime: Any, service_registry: Any, adapter_type: str
) -> Dict[str, ServiceTelemetryData]:
    """
    Collect telemetry from ALL active adapter instances of a given type.

    Returns a dict mapping adapter_id to telemetry data.
    Multiple instances of the same adapter type can be running simultaneously.
    """
    # Try control service first
    adapter_metrics = await collect_from_control_service(runtime, service_registry, adapter_type)
    if adapter_metrics is not None:
        return adapter_metrics

    # Fallback to bootstrap adapters
    return await collect_from_bootstrap_adapters(runtime, adapter_type)
