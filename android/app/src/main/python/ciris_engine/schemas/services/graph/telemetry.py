"""
Telemetry operations schemas for graph telemetry service.

Provides typed schemas for telemetry service operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ciris_engine.schemas.types import JSONDict


class TelemetrySnapshotResult(BaseModel):
    """Result of processing a system snapshot for telemetry."""

    memories_created: int = Field(0, description="Number of memory nodes created")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")
    consolidation_triggered: bool = Field(False, description="Whether consolidation was triggered")
    consolidation_result: Optional["TelemetryConsolidationResult"] = Field(
        None, description="Consolidation result if triggered"
    )
    error: Optional[str] = Field(None, description="Main error if processing failed")


class TelemetryData(BaseModel):
    """Structured telemetry data."""

    metrics: Dict[str, Union[int, float]] = Field(default_factory=dict, description="Numeric metrics")
    events: Dict[str, str] = Field(default_factory=dict, description="Event data")
    timestamps: Dict[str, datetime] = Field(default_factory=dict, description="Timestamps")


class ResourceData(BaseModel):
    """Structured resource usage data."""

    llm: Optional[Dict[str, Union[int, float]]] = Field(None, description="LLM resource usage")
    memory: Optional[Dict[str, float]] = Field(None, description="Memory usage")
    compute: Optional[Dict[str, float]] = Field(None, description="Compute usage")


class BehavioralData(BaseModel):
    """Structured behavioral data (tasks/thoughts)."""

    data_type: str = Field(..., description="Type: task or thought")
    content: JSONDict = Field(..., description="Behavioral content")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")


# UserProfile imported from system_context
# ChannelContext imported from system_context


class TelemetryConsolidationResult(BaseModel):
    """Result of memory consolidation."""

    status: str = Field(..., description="Consolidation status")
    grace_applied: int = Field(0, description="Number of grace applications")
    timestamp: str = Field(..., description="Consolidation timestamp")
    memories_consolidated: int = Field(0, description="Number of memories consolidated")
    errors: List[str] = Field(default_factory=list, description="Any errors during consolidation")


class CustomMetrics(BaseModel):
    """Custom metrics for telemetry service status."""

    cache_hit_rate: Optional[float] = Field(None, description="Cache hit rate percentage")
    metrics_per_second: Optional[float] = Field(None, description="Metrics processed per second")
    average_processing_time_ms: Optional[float] = Field(None, description="Average processing time")
    queue_depth: Optional[int] = Field(None, description="Current queue depth")
    error_rate: Optional[float] = Field(None, description="Error rate percentage")
    additional_metrics: Dict[str, float] = Field(default_factory=dict, description="Other custom metrics")


class TelemetryServiceStatus(BaseModel):
    """Status of the telemetry service."""

    healthy: bool = Field(..., description="Whether service is healthy")
    cached_metrics: int = Field(0, description="Number of metrics in cache")
    metric_types: List[str] = Field(default_factory=list, description="Types of metrics being tracked")
    memory_bus_available: bool = Field(False, description="Whether memory bus is available")
    last_consolidation: Optional[datetime] = Field(None, description="Last consolidation time")
    memory_mb: float = Field(0.0, description="Memory usage in MB")
    cache_size_mb: float = Field(0.0, description="Size of cached data in MB")
    custom_metrics: Optional[CustomMetrics] = Field(None, description="Typed custom metrics")


class GraphQuery(BaseModel):
    """Query parameters for graph operations."""

    hours: int = Field(24, description="Hours of data to query")
    node_types: List[str] = Field(default_factory=list, description="Types of nodes to query")
    tags: Dict[str, str] = Field(default_factory=dict, description="Tags to filter by")
    limit: Optional[int] = Field(None, description="Maximum results to return")


class LLMUsageData(BaseModel):
    """Structured LLM usage data."""

    tokens_used: Optional[int] = Field(None, description="Total tokens used")
    tokens_input: Optional[int] = Field(None, description="Input tokens")
    tokens_output: Optional[int] = Field(None, description="Output tokens")
    cost_cents: Optional[float] = Field(None, description="Cost in cents")
    carbon_grams: Optional[float] = Field(None, description="Carbon emissions in grams")
    energy_kwh: Optional[float] = Field(None, description="Energy usage in kWh")
    model_used: Optional[str] = Field(None, description="Model name used")

    model_config = ConfigDict(protected_namespaces=())


class TelemetryKwargs(BaseModel):
    """Structured kwargs for telemetry operations."""

    handler_name: Optional[str] = Field(None, description="Handler name for the operation")
    trace_id: Optional[str] = Field(None, description="Trace ID for correlation")
    parent_id: Optional[str] = Field(None, description="Parent operation ID")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    channel_id: Optional[str] = Field(None, description="Channel ID if applicable")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(default_factory=dict, description="Additional metadata")


class ServiceTelemetryData(BaseModel):
    """Telemetry data for a single service."""

    healthy: bool = Field(..., description="Whether service is healthy")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime in seconds")
    error_count: Optional[int] = Field(None, description="Number of errors")
    requests_handled: Optional[int] = Field(None, description="Total requests handled")
    error_rate: Optional[float] = Field(None, description="Error rate percentage")
    memory_mb: Optional[float] = Field(None, description="Memory usage in MB")
    custom_metrics: Optional[Dict[str, Union[int, float, str]]] = Field(None, description="Service-specific metrics")


class AggregatedTelemetryMetadata(BaseModel):
    """Metadata for aggregated telemetry response."""

    collection_method: str = Field("parallel", description="How data was collected")
    cache_ttl_seconds: int = Field(30, description="Cache TTL in seconds")
    timestamp: str = Field(..., description="Collection timestamp")
    cache_hit: Optional[bool] = Field(None, description="Whether this was a cache hit")


class MetricRecord(BaseModel):
    """Single metric record from persistence layer.

    Used by query_metrics() to return typed data.
    """

    metric_name: str = Field(..., description="Name of the metric")
    value: Union[int, float] = Field(..., description="Numeric metric value")
    timestamp: datetime = Field(..., description="When the metric was recorded")
    tags: Dict[str, str] = Field(default_factory=dict, description="Metric tags (service, etc.)")

    @field_validator("timestamp")
    @classmethod
    def ensure_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v


class CircuitBreakerState(BaseModel):
    """Circuit breaker state for a single service."""

    state: str = Field(..., description="Circuit breaker state (open/closed/half_open/unknown)")
    failure_count: int = Field(0, description="Consecutive failures")
    success_count: int = Field(0, description="Consecutive successes")
    total_requests: int = Field(0, description="Total requests")
    failed_requests: int = Field(0, description="Failed requests")
    consecutive_failures: int = Field(0, description="Consecutive failures")
    failure_rate: str = Field("0.00%", description="Failure rate percentage")

    model_config = ConfigDict(extra="forbid")


class MetricAggregates(BaseModel):
    """Aggregated metrics across time windows.

    Holds all counters during metric collection in get_telemetry_summary.
    Replaces scattered local variables with structured data.
    """

    # 24-hour window counters
    tokens_24h: int = Field(0, description="Total tokens in 24h")
    cost_24h_cents: float = Field(0.0, description="Total cost in 24h (cents)")
    carbon_24h_grams: float = Field(0.0, description="Total carbon in 24h (grams)")
    energy_24h_kwh: float = Field(0.0, description="Total energy in 24h (kWh)")
    messages_24h: int = Field(0, description="Messages processed in 24h")
    thoughts_24h: int = Field(0, description="Thoughts processed in 24h")
    tasks_24h: int = Field(0, description="Tasks completed in 24h")
    errors_24h: int = Field(0, description="Errors in 24h")

    # 1-hour window counters
    tokens_1h: int = Field(0, description="Total tokens in 1h")
    cost_1h_cents: float = Field(0.0, description="Total cost in 1h (cents)")
    carbon_1h_grams: float = Field(0.0, description="Total carbon in 1h (grams)")
    energy_1h_kwh: float = Field(0.0, description="Total energy in 1h (kWh)")
    messages_1h: int = Field(0, description="Messages processed in 1h")
    thoughts_1h: int = Field(0, description="Thoughts processed in 1h")
    errors_1h: int = Field(0, description="Errors in 1h")

    # Service-level tracking
    service_calls: Dict[str, int] = Field(default_factory=dict, description="Calls per service")
    service_errors: Dict[str, int] = Field(default_factory=dict, description="Errors per service")
    service_latency: Dict[str, List[float]] = Field(default_factory=dict, description="Latency values per service")


class AggregatedTelemetryResponse(BaseModel):
    """Response from get_aggregated_telemetry()."""

    # System-wide aggregates
    system_healthy: bool = Field(..., description="Overall system health")
    services_online: int = Field(..., description="Number of healthy services")
    services_total: int = Field(..., description="Total number of services")
    overall_error_rate: float = Field(..., description="System-wide error rate")
    overall_uptime_seconds: int = Field(..., description="Minimum uptime across services")
    total_errors: int = Field(..., description="Total errors across all services")
    total_requests: int = Field(..., description="Total requests handled")
    timestamp: str = Field(..., description="Response timestamp")

    # Per-service telemetry data
    services: Dict[str, ServiceTelemetryData] = Field(default_factory=dict, description="Per-service telemetry")

    # Metadata
    metadata: Optional[AggregatedTelemetryMetadata] = Field(None, description="Response metadata")

    # Optional error info if aggregation failed
    error: Optional[str] = Field(None, description="Error message if collection failed")


__all__ = [
    "TelemetrySnapshotResult",
    "TelemetryData",
    "ResourceData",
    "BehavioralData",
    "TelemetryConsolidationResult",
    "TelemetryServiceStatus",
    "GraphQuery",
    "LLMUsageData",
    "TelemetryKwargs",
    "CustomMetrics",
    "ServiceTelemetryData",
    "AggregatedTelemetryMetadata",
    "AggregatedTelemetryResponse",
    "MetricRecord",
    "MetricAggregates",
    "CircuitBreakerState",
]
