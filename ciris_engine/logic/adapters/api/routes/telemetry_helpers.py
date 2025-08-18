"""
Telemetry helper functions - extracted from telemetry.py to reduce file size.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

from ciris_engine.logic.services.graph.telemetry_service import TelemetryAggregator


async def get_telemetry_from_service(
    telemetry_service, view: str, category: Optional[str], format: str, live: bool
) -> Dict:
    """Get telemetry from the service's built-in aggregator."""
    # The telemetry service's get_aggregated_telemetry() doesn't accept parameters
    # Get the raw data and apply filtering in the API layer
    result = await telemetry_service.get_aggregated_telemetry()

    # Add metadata about the requested view and category
    result["_metadata"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "view": view,
        "category": category,
        "cached": not live,
        "format": format,
    }

    # Apply view filtering if needed (handled by the API layer)
    # The actual view filtering is done by the endpoint after this function returns

    return result


async def get_telemetry_fallback(app_state, view: str, category: Optional[str]) -> Dict:
    """Fallback method to get telemetry using TelemetryAggregator."""
    # Get required services from app state
    service_registry = getattr(app_state, "service_registry", None)
    time_service = getattr(app_state, "time_service", None)

    # If we don't have the required services, return a minimal response
    if not service_registry or not time_service:
        return {
            "error": "Service registry or time service not available",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "view": view,
            "category": category,
            "services": {},
            "_metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "view": view,
                "category": category,
                "cached": False,
                "format": "json",
            },
        }

    aggregator = TelemetryAggregator(service_registry, time_service)
    telemetry_data = await aggregator.collect_all_parallel()
    result = aggregator.calculate_aggregates(telemetry_data)

    if view != "detailed":
        result = aggregator.apply_view_filter(result, view)

    result["_metadata"] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "view": view,
        "category": category,
        "cached": False,
        "format": "json",
    }

    return result
