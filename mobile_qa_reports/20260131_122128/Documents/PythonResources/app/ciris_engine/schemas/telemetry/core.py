"""
Correlation schemas for service tracking and TSDB capabilities.

Provides type-safe correlation tracking without Dict[str, Any].
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ServiceCorrelationStatus(str, Enum):
    """Status values for service correlations."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class CorrelationType(str, Enum):
    """Types of correlations supported by the TSDB system."""

    SERVICE_INTERACTION = "service_interaction"

    METRIC_DATAPOINT = "metric_datapoint"
    LOG_ENTRY = "log_entry"
    TRACE_SPAN = "trace_span"
    AUDIT_EVENT = "audit_event"

    METRIC_HOURLY_SUMMARY = "metric_hourly_summary"
    METRIC_DAILY_SUMMARY = "metric_daily_summary"
    LOG_HOURLY_SUMMARY = "log_hourly_summary"


class ServiceRequestData(BaseModel):
    """Structured request data for service correlations."""

    service_type: str = Field(..., description="Type of service called")
    method_name: str = Field(..., description="Method that was called")

    # Common request fields
    thought_id: Optional[str] = Field(None, description="Associated thought ID")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    channel_id: Optional[str] = Field(None, description="Channel where request originated")

    # Parameters passed
    parameters: Dict[str, str] = Field(default_factory=dict, description="String representation of parameters")

    # Timing
    request_timestamp: datetime = Field(..., description="When request was made")
    timeout_seconds: Optional[float] = Field(None, description="Request timeout")

    model_config = ConfigDict(extra="forbid")


class ServiceResponseData(BaseModel):
    """Structured response data for service correlations."""

    success: bool = Field(..., description="Whether service call succeeded")

    # Result data
    result_summary: Optional[str] = Field(None, description="Summary of result")
    result_type: Optional[str] = Field(None, description="Type of result returned")
    result_size: Optional[int] = Field(None, description="Size of result in bytes")

    # Error information
    error_type: Optional[str] = Field(None, description="Type of error if failed")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    error_traceback: Optional[str] = Field(None, description="Stack trace if available")

    # Performance metrics
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")
    response_timestamp: datetime = Field(..., description="When response was received")

    # Resource usage
    tokens_used: Optional[int] = Field(None, description="LLM tokens used")
    memory_bytes: Optional[int] = Field(None, description="Memory consumed")

    model_config = ConfigDict(extra="forbid")


class TraceContext(BaseModel):
    """Distributed tracing context."""

    trace_id: str = Field(..., description="Trace identifier")
    span_id: str = Field(..., description="Span identifier")
    parent_span_id: Optional[str] = Field(None, description="Parent span for hierarchy")

    # Span details
    span_name: str = Field(..., description="Name of the span")
    span_kind: str = Field("internal", description="Span kind: internal, client, server")

    # Baggage
    baggage: Dict[str, str] = Field(default_factory=dict, description="Propagated context values")

    model_config = ConfigDict(extra="forbid")


class MetricData(BaseModel):
    """Metric data for correlations."""

    metric_name: str = Field(..., description="Name of the metric")
    metric_value: float = Field(..., description="Numeric value")
    metric_unit: str = Field(..., description="Unit of measurement")

    # Metric type
    metric_type: str = Field("gauge", description="gauge, counter, histogram, summary")

    # Labels/dimensions
    labels: Dict[str, str] = Field(default_factory=dict, description="Metric labels/dimensions")

    # Statistical data (for histograms/summaries)
    min_value: Optional[float] = Field(None, description="Minimum observed")
    max_value: Optional[float] = Field(None, description="Maximum observed")
    mean_value: Optional[float] = Field(None, description="Mean value")
    percentiles: Dict[str, float] = Field(default_factory=dict, description="Percentile values (e.g., p50, p95, p99)")

    model_config = ConfigDict(extra="forbid")


class LogData(BaseModel):
    """Log data for correlations."""

    log_level: str = Field(..., description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    log_message: str = Field(..., description="Log message")

    # Source information
    logger_name: str = Field(..., description="Name of the logger")
    module_name: str = Field(..., description="Module that logged")
    function_name: str = Field(..., description="Function that logged")
    line_number: int = Field(..., description="Line number")

    # Structured data
    extra_fields: Dict[str, str] = Field(default_factory=dict, description="Additional structured log fields")

    model_config = ConfigDict(extra="forbid")


class ServiceCorrelation(BaseModel):
    """Record correlating service requests and responses with TSDB capabilities."""

    # Identity
    correlation_id: str = Field(..., description="Unique correlation identifier")
    correlation_type: CorrelationType = Field(CorrelationType.SERVICE_INTERACTION, description="Type of correlation")

    # Service information
    service_type: str = Field(..., description="Type of service")
    handler_name: str = Field(..., description="Handler that processed")
    action_type: str = Field(..., description="Action type performed")

    # Structured data (no Dict[str, Any]!)
    request_data: Optional[ServiceRequestData] = Field(None, description="Request details")
    response_data: Optional[ServiceResponseData] = Field(None, description="Response details")

    # Status tracking
    status: ServiceCorrelationStatus = Field(ServiceCorrelationStatus.PENDING, description="Current status")

    # Timestamps
    created_at: datetime = Field(..., description="When correlation was created")
    updated_at: datetime = Field(..., description="Last update time")
    timestamp: datetime = Field(..., description="Primary timestamp for TSDB indexing")

    # TSDB-specific data based on correlation type
    metric_data: Optional[MetricData] = Field(None, description="For metric correlations")
    log_data: Optional[LogData] = Field(None, description="For log correlations")
    trace_context: Optional[TraceContext] = Field(None, description="For distributed tracing")

    # Flexible tagging for queries
    tags: Dict[str, str] = Field(default_factory=dict, description="Tags for filtering/grouping")

    # Retention and storage
    retention_policy: str = Field("raw", description="raw, hourly_summary, daily_summary")
    ttl_seconds: Optional[int] = Field(None, description="Time to live in seconds")

    # Relationships
    parent_correlation_id: Optional[str] = Field(None, description="Parent correlation if nested")
    child_correlation_ids: List[str] = Field(default_factory=list, description="Child correlations")

    model_config = ConfigDict(extra="forbid")


class CorrelationQuery(BaseModel):
    """Query for finding correlations."""

    # Time range
    start_time: Optional[datetime] = Field(None, description="Start of time range")
    end_time: Optional[datetime] = Field(None, description="End of time range")

    # Filters
    correlation_types: Optional[List[CorrelationType]] = Field(None, description="Types to include")
    service_types: Optional[List[str]] = Field(None, description="Service types to include")
    statuses: Optional[List[ServiceCorrelationStatus]] = Field(None, description="Statuses to include")

    # Tag filters
    required_tags: Dict[str, str] = Field(default_factory=dict, description="Tags that must match")
    excluded_tags: List[str] = Field(default_factory=list, description="Tag keys to exclude")

    # Trace context
    trace_id: Optional[str] = Field(None, description="Find by trace ID")

    # Pagination
    limit: int = Field(100, description="Maximum results")
    offset: int = Field(0, description="Skip this many results")

    # Ordering
    order_by: str = Field("timestamp", description="Field to order by")
    order_desc: bool = Field(True, description="Descending order")

    model_config = ConfigDict(extra="forbid")


class CorrelationSummary(BaseModel):
    """Summary of correlations for a time period."""

    period_start: datetime = Field(..., description="Start of period")
    period_end: datetime = Field(..., description="End of period")

    # Counts by type
    total_correlations: int = Field(..., description="Total correlations")
    correlations_by_type: Dict[str, int] = Field(..., description="Count by type")
    correlations_by_status: Dict[str, int] = Field(..., description="Count by status")

    # Service metrics
    service_calls: Dict[str, int] = Field(..., description="Calls by service type")
    failed_calls: Dict[str, int] = Field(..., description="Failed calls by service")

    # Performance metrics
    avg_execution_time_ms: float = Field(..., description="Average execution time")
    p95_execution_time_ms: float = Field(..., description="95th percentile execution time")
    p99_execution_time_ms: float = Field(..., description="99th percentile execution time")

    # Resource usage
    total_tokens_used: int = Field(0, description="Total LLM tokens")
    total_memory_bytes: int = Field(0, description="Total memory used")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ServiceCorrelationStatus",
    "CorrelationType",
    "ServiceRequestData",
    "ServiceResponseData",
    "TraceContext",
    "MetricData",
    "LogData",
    "ServiceCorrelation",
    "CorrelationQuery",
    "CorrelationSummary",
]
