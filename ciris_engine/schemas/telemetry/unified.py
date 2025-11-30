"""
Unified telemetry response schemas for v1.4.3.

This provides typed response models for all telemetry endpoints,
replacing Dict[str, Any] returns with proper Pydantic models.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_serializer

# ============================================================================
# RESOURCE METRICS - Fixes the duplicate ResourceMetricData issue
# ============================================================================


class MetricDataPoint(BaseModel):
    """Single metric data point for time series."""

    timestamp: datetime = Field(..., description="When metric was recorded")
    value: float = Field(..., description="Metric value")
    tags: Optional[Dict[str, str]] = Field(default=None, description="Metric tags")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> str:
        return timestamp.isoformat()


class ResourceMetricWithStats(BaseModel):
    """Resource metric with statistics - replaces dict format."""

    data: List[MetricDataPoint] = Field(..., description="Time series data points")
    stats: Dict[str, float] = Field(..., description="Statistical summary")
    unit: str = Field(..., description="Metric unit")


class ResourceTimeSeriesData(BaseModel):
    """Time series data for resource metrics - unified model."""

    metric_name: str = Field(..., description="Name of the metric")
    data_points: List[MetricDataPoint] = Field(..., description="Time series data")
    unit: str = Field(..., description="Metric unit")

    # Statistics
    current: float = Field(..., description="Current/latest value")
    average: float = Field(..., description="Average over period")
    min: float = Field(..., description="Minimum value in period")
    max: float = Field(..., description="Maximum value in period")
    percentile_95: float = Field(..., description="95th percentile")
    trend: str = Field(..., description="Trend: up, down, or stable")


# Export the specific models needed by telemetry.py
__all__ = [
    "MetricDataPoint",
    "ResourceMetricWithStats",
    "ResourceTimeSeriesData",
]
