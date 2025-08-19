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
    # Try to pass parameters if the method accepts them (for mocked services in tests)
    # Otherwise fall back to calling without parameters (for real service)
    try:
        # Try calling with parameters first (for mocked services that accept them)
        import inspect

        sig = inspect.signature(telemetry_service.get_aggregated_telemetry)
        if len(sig.parameters) > 0:
            # Method accepts parameters, pass them
            result = await telemetry_service.get_aggregated_telemetry(
                view=view, category=category, format=format, live=live
            )
        else:
            # Method doesn't accept parameters, call without them
            result = await telemetry_service.get_aggregated_telemetry()
    except TypeError:
        # Fallback if signature inspection fails
        result = await telemetry_service.get_aggregated_telemetry()

    # Convert Pydantic model to dict if needed
    from pydantic import BaseModel

    if isinstance(result, BaseModel):
        result = result.model_dump()

    # Ensure the view is included in the result (for backward compatibility)
    if "view" not in result:
        result["view"] = view

    # Add or update metadata about the requested view and category
    if "_metadata" not in result:
        result["_metadata"] = {}

    result["_metadata"].update(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "view": view,
            "category": category,
            "cached": not live,
            "format": format,
        }
    )

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
