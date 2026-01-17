"""
Metrics helpers for TelemetryAggregator.

Contains functions for metrics conversion, extraction, and aggregation.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple, Union

from ciris_engine.logic.utils.jsondict_helpers import get_bool, get_float
from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def convert_dict_to_telemetry(metrics: JSONDict, service_name: str) -> ServiceTelemetryData:
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


async def try_get_metrics_method(service: Any) -> Optional[ServiceTelemetryData]:
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
            return convert_dict_to_telemetry(metrics, type(service).__name__)

        return None
    except Exception as e:
        logger.error(f"Error calling get_metrics on {type(service).__name__}: {e}")
        return None


def try_collect_metrics_method(service: Any) -> Optional[ServiceTelemetryData]:
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


async def try_get_status_method(service: Any) -> Optional[ServiceTelemetryData]:
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


async def try_collect_metrics(service: Any) -> Optional[ServiceTelemetryData]:
    """Try different methods to collect metrics from service."""
    if not service:
        logger.debug("[TELEMETRY] Service is None, cannot collect metrics")
        return None

    # Try get_metrics first (most common)
    result = await try_get_metrics_method(service)
    if result:
        return result

    # Try _collect_metrics (fallback)
    result = try_collect_metrics_method(service)
    if result:
        return result

    # Try get_status (last resort)
    return await try_get_status_method(service)


def get_fallback_metrics(_service_name: Optional[str] = None, _healthy: bool = False) -> ServiceTelemetryData:
    """NO FALLBACKS. Real metrics or nothing.

    Parameters are accepted for compatibility but ignored - no fake metrics.
    """
    # NO FAKE METRICS. Services must implement get_metrics() or they get nothing.
    # Return empty telemetry data instead of empty dict
    return ServiceTelemetryData(
        healthy=False, uptime_seconds=0.0, error_count=0, requests_handled=0, error_rate=0.0
    )


def status_to_telemetry(status: Any) -> JSONDict:
    """Convert ServiceStatus to telemetry dict."""
    if hasattr(status, "model_dump"):
        result = status.model_dump()
        return result  # type: ignore[no-any-return]
    elif hasattr(status, "__dict__"):
        result = status.__dict__
        return result  # type: ignore[no-any-return]
    else:
        return {"status": str(status)}


def process_service_metrics(service_data: ServiceTelemetryData) -> Tuple[bool, int, int, float, float]:
    """Process metrics for a single service."""
    is_healthy = service_data.healthy
    errors = service_data.error_count or 0
    requests = service_data.requests_handled or 0
    error_rate = service_data.error_rate or 0.0
    uptime = service_data.uptime_seconds or 0

    return is_healthy, errors, requests, error_rate, uptime


def aggregate_service_metrics(
    telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
) -> Tuple[int, int, int, int, float, List[float]]:
    """Aggregate metrics from all services."""
    total_services = 0
    healthy_services = 0
    total_errors = 0
    total_requests = 0
    min_uptime = float("inf")
    error_rates: List[float] = []

    for category_name, category_data in telemetry.items():
        # Skip covenant category as it contains computed metrics, not service data
        if category_name == "covenant":
            continue

        for service_data in category_data.values():
            total_services += 1
            is_healthy, errors, requests, error_rate, uptime = process_service_metrics(service_data)

            if is_healthy:
                healthy_services += 1

            total_errors += errors
            total_requests += requests

            if error_rate > 0:
                error_rates.append(error_rate)

            if uptime > 0 and uptime < min_uptime:
                min_uptime = uptime

    return total_services, healthy_services, total_errors, total_requests, min_uptime, error_rates


def extract_metric_value(metrics_obj: Any, metric_name: str, default: Any = 0) -> Any:
    """Extract a metric value from ServiceTelemetryData or dict."""
    if isinstance(metrics_obj, ServiceTelemetryData):
        if metrics_obj.custom_metrics:
            return metrics_obj.custom_metrics.get(metric_name, default)
    elif isinstance(metrics_obj, dict):
        return metrics_obj.get(metric_name, default)
    return default


def extract_governance_metrics(
    telemetry: Dict[str, Dict[str, ServiceTelemetryData]], service_name: str, metric_mappings: Dict[str, str]
) -> Dict[str, Union[float, int, str]]:
    """Extract metrics from a governance service."""
    results: Dict[str, Union[float, int, str]] = {}
    if "governance" in telemetry and service_name in telemetry["governance"]:
        metrics = telemetry["governance"][service_name]
        for covenant_key, service_key in metric_mappings.items():
            results[covenant_key] = extract_metric_value(metrics, service_key)
    return results


def compute_covenant_metrics(
    telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
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
        wa_metrics = extract_governance_metrics(
            telemetry,
            "wise_authority",
            {"wise_authority_deferrals": "deferral_count", "thoughts_processed": "guidance_requests"},
        )
        covenant_metrics.update(wa_metrics)

        filter_metrics = extract_governance_metrics(
            telemetry, "adaptive_filter", {"filter_matches": "filter_actions"}
        )
        covenant_metrics.update(filter_metrics)

        so_metrics = extract_governance_metrics(
            telemetry, "self_observation", {"self_observation_insights": "insights_generated"}
        )
        covenant_metrics.update(so_metrics)

    except Exception as e:
        logger.error(f"Failed to compute covenant metrics: {e}")

    return covenant_metrics


def calculate_aggregates(
    telemetry: Dict[str, Dict[str, ServiceTelemetryData]]
) -> Dict[str, Union[bool, int, float, str]]:
    """Calculate system-wide aggregate metrics."""
    from datetime import datetime, timezone

    # Get aggregated metrics
    total_services, healthy_services, total_errors, total_requests, min_uptime, error_rates = (
        aggregate_service_metrics(telemetry)
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
