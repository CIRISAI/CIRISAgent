"""
Telemetry API response schemas - fully typed replacements for Dict[str, Any].
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.types import JSONDict


class MetricTags(BaseModel):
    """Standard metric tags."""

    service: Optional[str] = Field(None, description="Source service")
    operation: Optional[str] = Field(None, description="Operation name")
    model: Optional[str] = Field(None, description="Model used (for LLM metrics)")
    status: Optional[str] = Field(None, description="Operation status")
    environment: Optional[str] = Field(None, description="Environment (prod/dev)")


class ServiceMetricValue(BaseModel):
    """Metric value broken down by service."""

    service_name: str = Field(..., description="Service name")
    value: float = Field(..., description="Metric value")
    percentage: Optional[float] = Field(None, description="Percentage of total")


class APIResponseThoughtStep(BaseModel):
    """Individual thought step in API reasoning response."""

    step: int = Field(..., description="Step number")
    content: str = Field(..., description="Thought content")
    timestamp: datetime = Field(..., description="When thought occurred")
    depth: int = Field(0, description="Reasoning depth")
    action: Optional[str] = Field(None, description="Action taken")
    confidence: Optional[float] = Field(None, description="Confidence level")


# Backward compatibility alias - will be removed in future
ThoughtStep = APIResponseThoughtStep


class LogContext(BaseModel):
    """Structured log context."""

    trace_id: Optional[str] = Field(None, description="Trace ID for correlation")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    entity_id: Optional[str] = Field(None, description="Entity being operated on")
    error_details: Optional[JSONDict] = Field(None, description="Error specifics if error log")
    metadata: Optional[JSONDict] = Field(None, description="Additional metadata")


class QueryFilter(BaseModel):
    """Structured query filter."""

    field: str = Field(..., description="Field to filter on")
    operator: str = Field("eq", description="Filter operator (eq, gt, lt, contains, etc)")
    value: str = Field(..., description="Filter value")


class TelemetryQueryFilters(BaseModel):
    """Telemetry query filters."""

    metric_names: Optional[List[str]] = Field(None, description="Metrics to query")
    metrics: Optional[List[str]] = Field(None, description="Metrics to query (alias)")
    services: Optional[List[str]] = Field(None, description="Services to include")
    tags: Optional[Dict[str, str]] = Field(None, description="Tag filters")
    severity: Optional[str] = Field(None, description="Log severity filter")
    status: Optional[str] = Field(None, description="Status filter for incidents")
    category: Optional[str] = Field(None, description="Category filter")
    aggregation: Optional[str] = Field(None, description="Aggregation method")
    limit: Optional[int] = Field(None, description="Result limit override")


class QueryResult(BaseModel):
    """Individual query result."""

    id: str = Field(..., description="Result ID")
    type: str = Field(..., description="Result type")
    timestamp: datetime = Field(..., description="Result timestamp")
    data: JSONDict = Field(..., description="Result data (type-specific)")


class TimeSyncStatus(BaseModel):
    """Time synchronization status."""

    synchronized: bool = Field(..., description="Whether time is synchronized")
    drift_ms: float = Field(..., description="Time drift in milliseconds")
    last_sync: datetime = Field(..., description="Last sync timestamp")
    sync_source: str = Field(..., description="Sync source (system/mock/ntp)")

    @field_serializer("last_sync")
    def serialize_last_sync(self, dt: datetime, _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class ServiceMetrics(BaseModel):
    """Service-specific metrics."""

    uptime_seconds: Optional[float] = Field(None, description="Service uptime")
    requests_handled: Optional[int] = Field(None, description="Total requests")
    error_count: Optional[int] = Field(None, description="Error count")
    avg_response_time_ms: Optional[float] = Field(None, description="Average response time")
    memory_mb: Optional[float] = Field(None, description="Memory usage")
    custom_metrics: Optional[JSONDict] = Field(None, description="Service-specific metrics")
