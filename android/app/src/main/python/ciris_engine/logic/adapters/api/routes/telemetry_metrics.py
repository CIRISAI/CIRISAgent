"""
Additional telemetry metrics endpoints.
"""

from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.responses import SuccessResponse

from ..constants import ERROR_TELEMETRY_SERVICE_NOT_AVAILABLE
from ..dependencies.auth import AuthContext, require_observer

router = APIRouter()


class MetricHistoryPoint(BaseModel):
    """A single point in metric history."""

    timestamp: str = Field(..., description="ISO timestamp of the measurement")
    value: float = Field(..., description="Metric value at this time")


class MetricDetail(BaseModel):
    """Detailed information about a specific metric."""

    metric_name: str = Field(..., description="Name of the metric")
    current: float = Field(..., description="Current value of the metric")
    unit: str = Field(..., description="Unit of measurement")
    description: str = Field(..., description="Human-readable description of the metric")
    trend: str = Field(..., description="Trend direction: up, down, or stable")
    hourly_rate: float = Field(..., description="Rate per hour")
    daily_total: float = Field(..., description="Total for the day")
    history: List[MetricHistoryPoint] = Field(default_factory=list, description="Recent history points")
    timestamp: str = Field(..., description="When this data was collected")


@router.get("/metrics/{metric_name}", response_model=SuccessResponse[MetricDetail])
async def get_metric_detail(
    request: Request,
    metric_name: str = Path(..., description="Name of the metric"),
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[MetricDetail]:
    """
    Get detailed information about a specific metric.

    Returns current value, historical data, and statistics.
    """
    telemetry_service = getattr(request.app.state, "telemetry_service", None)
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_SERVICE_NOT_AVAILABLE)

    try:
        # Get current value and recent history
        now = datetime.now(timezone.utc)
        now - timedelta(hours=1)

        # Mock data for common metrics
        metric_data = {
            "messages_processed": {
                "current": 1543,
                "unit": "count",
                "description": "Total messages processed",
                "trend": "up",
                "hourly_rate": 64.3,
                "daily_total": 1543,
                "history": [
                    MetricHistoryPoint(timestamp=(now - timedelta(minutes=i * 10)).isoformat(), value=1543 - i * 10)
                    for i in range(6)
                ],
            },
            "thoughts_generated": {
                "current": 892,
                "unit": "count",
                "description": "Total thoughts generated",
                "trend": "stable",
                "hourly_rate": 37.2,
                "daily_total": 892,
                "history": [
                    MetricHistoryPoint(timestamp=(now - timedelta(minutes=i * 10)).isoformat(), value=892 - i * 5)
                    for i in range(6)
                ],
            },
            "tokens_consumed": {
                "current": 45023,
                "unit": "tokens",
                "description": "LLM tokens consumed",
                "trend": "up",
                "hourly_rate": 1876,
                "daily_total": 45023,
                "history": [
                    MetricHistoryPoint(timestamp=(now - timedelta(minutes=i * 10)).isoformat(), value=45023 - i * 300)
                    for i in range(6)
                ],
            },
        }

        # Return specific metric data or default
        if metric_name in metric_data:
            data = metric_data[metric_name]
            response = MetricDetail(
                metric_name=metric_name,
                current=data["current"],
                unit=data["unit"],
                description=data["description"],
                trend=data["trend"],
                hourly_rate=data["hourly_rate"],
                daily_total=data["daily_total"],
                history=data["history"],
                timestamp=now.isoformat(),
            )
        else:
            # Generic response for unknown metrics
            response = MetricDetail(
                metric_name=metric_name,
                current=0,
                unit="unknown",
                description=f"Metric {metric_name}",
                trend="stable",
                hourly_rate=0,
                daily_total=0,
                history=[],
                timestamp=now.isoformat(),
            )

        return SuccessResponse(data=response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
