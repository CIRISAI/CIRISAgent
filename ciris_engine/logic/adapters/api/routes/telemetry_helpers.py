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
    return await telemetry_service.get_aggregated_telemetry(view=view, category=category, format=format, live=live)


async def get_telemetry_fallback(app_state, view: str, category: Optional[str]) -> Dict:
    """Fallback method to get telemetry using TelemetryAggregator."""
    aggregator = TelemetryAggregator(app_state)
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
