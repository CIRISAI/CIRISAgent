"""
Telemetry data models - extracted from telemetry.py to reduce file size.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.api.telemetry import MetricTags
from ciris_engine.schemas.types import JSONDict

# Field description constants
DESC_SERVICE_NAME = "Service name"


class MetricData(BaseModel):
    """Single metric data point."""

    timestamp: datetime = Field(..., description="When metric was recorded")
    value: float = Field(..., description="Metric value")
    tags: MetricTags = Field(default_factory=lambda: MetricTags.model_validate({}), description="Metric tags")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None


class MetricSeries(BaseModel):
    """Time series data for a metric."""

    metric_name: str = Field(..., description="Name of the metric")
    data_points: List[MetricData] = Field(..., description="Time series data")
    unit: Optional[str] = Field(None, description="Metric unit")
    description: Optional[str] = Field(None, description="Metric description")


class SystemOverview(BaseModel):
    """System overview combining all observability data."""

    # Core metrics
    uptime_seconds: float = Field(..., description="System uptime")
    cognitive_state: str = Field(..., description="Current cognitive state")
    messages_processed_24h: int = Field(0, description="Messages in last 24 hours")
    thoughts_processed_24h: int = Field(0, description="Thoughts in last 24 hours")
    tasks_completed_24h: int = Field(0, description="Tasks completed in last 24 hours")
    errors_24h: int = Field(0, description="Errors in last 24 hours")

    # Resource usage (last hour actuals)
    tokens_last_hour: float = Field(0.0, description="Total tokens in last hour")
    cost_last_hour_cents: float = Field(0.0, description="Total cost in last hour (cents)")
    carbon_last_hour_grams: float = Field(0.0, description="Total carbon in last hour (grams)")
    energy_last_hour_kwh: float = Field(0.0, description="Total energy in last hour (kWh)")

    # Resource usage (24 hour totals)
    tokens_24h: float = Field(0.0, description="Total tokens in last 24 hours")
    cost_24h_cents: float = Field(0.0, description="Total cost in last 24 hours (cents)")
    carbon_24h_grams: float = Field(0.0, description="Total carbon in last 24 hours (grams)")
    energy_24h_kwh: float = Field(0.0, description="Total energy in last 24 hours (kWh)")
    memory_mb: float = Field(0.0, description="Current memory usage")
    cpu_percent: float = Field(0.0, description="Current CPU usage")

    # Service health
    healthy_services: int = Field(0, description="Number of healthy services")
    degraded_services: int = Field(0, description="Number of degraded services")
    error_rate_percent: float = Field(0.0, description="System error rate")

    # Agent activity
    current_task: Optional[str] = Field(None, description="Current task description")
    reasoning_depth: int = Field(0, description="Current reasoning depth")
    active_deferrals: int = Field(0, description="Pending WA deferrals")
    recent_incidents: int = Field(0, description="Incidents in last hour")

    # Telemetry metrics
    total_metrics: int = Field(0, description="Total metrics collected")
    active_services: int = Field(0, description="Number of active services reporting telemetry")
    metrics_per_second: float = Field(0.0, description="Current metric ingestion rate")
    cache_hit_rate: float = Field(0.0, description="Telemetry cache hit rate")


class ServiceHealth(BaseModel):
    """Health status of a single service."""

    service_name: str = Field(..., description=DESC_SERVICE_NAME)
    status: str = Field(..., description="Health status: healthy, degraded, or error")
    latency_ms: float = Field(..., description="Average latency in milliseconds")
    error_rate: float = Field(..., description="Error rate percentage")
    last_seen: datetime = Field(..., description="Last heartbeat")
    circuit_breaker: str = Field("closed", description="Circuit breaker status")
    details: Optional[str] = Field(None, description="Additional details")

    @field_serializer("last_seen")
    def serialize_last_seen(self, last_seen: datetime, _info: Any) -> Optional[str]:
        return last_seen.isoformat() if last_seen else None


class ServiceHealthOverview(BaseModel):
    """System-wide service health overview."""

    total_services: int = Field(..., description="Total number of services")
    healthy: int = Field(..., description="Number of healthy services")
    degraded: int = Field(..., description="Number of degraded services")
    error: int = Field(..., description="Number of services in error state")
    services: List[ServiceHealth] = Field(..., description="Individual service health")


class LogEntry(BaseModel):
    """Single log entry."""

    timestamp: datetime = Field(..., description="Log timestamp")
    level: str = Field(..., description="Log level")
    message: str = Field(..., description="Log message")
    service: str = Field(..., description=DESC_SERVICE_NAME)
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    user_id: Optional[str] = Field(None, description="User ID")
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None


class TraceSpan(BaseModel):
    """Single trace span."""

    span_id: str = Field(..., description="Span ID")
    parent_id: Optional[str] = Field(None, description="Parent span ID")
    trace_id: str = Field(..., description="Trace ID")
    operation: str = Field(..., description="Operation name")
    service: str = Field(..., description=DESC_SERVICE_NAME)
    start_time: datetime = Field(..., description="Start time")
    duration_ms: float = Field(..., description="Duration in milliseconds")
    status: str = Field(..., description="Status: ok or error")
    tags: JSONDict = Field(default_factory=dict, description="Span tags")

    @field_serializer("start_time")
    def serialize_start_time(self, start_time: datetime, _info: Any) -> Optional[str]:
        return start_time.isoformat() if start_time else None


class ResourceMetricStats(BaseModel):
    """Resource usage statistics."""

    min: float = Field(..., description="Minimum value")
    max: float = Field(..., description="Maximum value")
    avg: float = Field(..., description="Average value")
    current: float = Field(..., description="Current value")


class ResourceDataPoint(BaseModel):
    """Resource data point."""

    timestamp: str = Field(..., description="ISO timestamp")
    value: float = Field(..., description="Measured value")


class ResourceMetricData(BaseModel):
    """Resource usage metric data with time series and stats."""

    data: List[ResourceDataPoint] = Field(..., description="Time series data points")
    stats: ResourceMetricStats = Field(..., description="Statistical summary")
    unit: str = Field(..., description="Unit of measurement")


class ResourceUsage(BaseModel):
    """Current resource usage."""

    cpu: ResourceMetricData = Field(..., description="CPU usage percentage")
    memory: ResourceMetricData = Field(..., description="Memory usage in MB")
    disk: ResourceMetricData = Field(..., description="Disk usage in GB")
    network_in_mbps: float = Field(..., description="Network input in Mbps")
    network_out_mbps: float = Field(..., description="Network output in Mbps")
    open_connections: int = Field(..., description="Number of open connections")


class TimePeriod(BaseModel):
    """Time period for historical data."""

    start: str = Field(..., description="Start time (ISO format)")
    end: str = Field(..., description="End time (ISO format)")
    hours: int = Field(..., description="Period length in hours")


class ResourceHistoryResponse(BaseModel):
    """Historical resource usage response."""

    period: TimePeriod = Field(..., description="Time period covered")
    cpu: ResourceMetricData = Field(..., description="CPU usage data")
    memory: ResourceMetricData = Field(..., description="Memory usage data")
    disk: ResourceMetricData = Field(..., description="Disk usage data")
