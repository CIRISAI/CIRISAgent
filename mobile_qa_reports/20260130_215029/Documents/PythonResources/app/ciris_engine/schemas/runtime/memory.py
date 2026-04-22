"""
Memory protocol schemas.

Type-safe schemas for memory service operations.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class MemorySearchResult(BaseModel):
    """Result from memory search operation."""

    node_id: str = Field(..., description="Unique identifier of the memory node")
    content: str = Field(..., description="Memory content")
    node_type: str = Field(..., description="Type of memory node")
    relevance_score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0.0-1.0)")
    created_at: datetime = Field(..., description="When the memory was created")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(extra="forbid")


class TimeSeriesDataPoint(BaseModel):
    """A time-series data point from memory correlations."""

    timestamp: datetime = Field(..., description="Time of the data point")
    metric_name: str = Field(..., description="Name of the metric")
    value: float = Field(..., description="Metric value")
    correlation_type: str = Field(..., description="Type of correlation (e.g., METRIC_DATAPOINT)")
    tags: Dict[str, str] = Field(default_factory=dict, description="Optional tags")
    source: Optional[str] = Field(None, description="Source of the data")

    model_config = ConfigDict(extra="forbid")


class IdentityUpdateRequest(BaseModel):
    """Request to update identity graph."""

    node_id: Optional[str] = Field(None, description="Specific node to update")
    updates: Dict[str, Union[str, int, float, bool]] = Field(..., description="Fields to update")
    source: str = Field(..., description="Source of the update (e.g., 'wa_feedback')")
    reason: Optional[str] = Field(None, description="Reason for the update")

    model_config = ConfigDict(extra="forbid")


class EnvironmentUpdateRequest(BaseModel):
    """Request to update environment graph."""

    adapter_type: str = Field(..., description="Type of adapter providing update")
    environment_data: Dict[str, str] = Field(..., description="Environment data to merge")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When update occurred")

    model_config = ConfigDict(extra="forbid")


__all__ = ["MemorySearchResult", "TimeSeriesDataPoint", "IdentityUpdateRequest", "EnvironmentUpdateRequest"]
