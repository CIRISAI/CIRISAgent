"""
Response models for telemetry API endpoints.

These models provide type-safe alternatives to Dict[str, Any] return types.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .telemetry_models import MetricAggregate, MetricData, MetricTrend, ThoughtData


class TelemetryOverviewResponse(BaseModel):
    """Response from telemetry overview endpoint."""

    # Core metrics
    uptime_seconds: float = Field(..., description="System uptime")
    cognitive_state: str = Field(..., description="Current cognitive state")
    messages_processed_24h: int = Field(default=0, description="Messages in last 24h")
    thoughts_processed_24h: int = Field(default=0, description="Thoughts in last 24h")
    tasks_completed_24h: int = Field(default=0, description="Tasks completed in last 24h")
    errors_24h: int = Field(default=0, description="Errors in last 24h")

    # Resource usage
    tokens_per_hour: float = Field(default=0.0, description="Average tokens per hour")
    cost_per_hour_cents: float = Field(default=0.0, description="Average cost per hour in cents")
    carbon_per_hour_grams: float = Field(default=0.0, description="Carbon footprint per hour in grams")
    memory_mb: float = Field(default=0.0, description="Current memory usage MB")
    cpu_percent: float = Field(default=0.0, description="Current CPU percentage")

    # Service health
    healthy_services: int = Field(default=0, description="Number of healthy services")
    degraded_services: int = Field(default=0, description="Number of degraded services")
    error_rate_percent: float = Field(default=0.0, description="Error rate percentage")

    # Agent activity
    current_task: Optional[str] = Field(None, description="Current task description")
    reasoning_depth: int = Field(default=0, description="Current reasoning depth")
    active_deferrals: int = Field(default=0, description="Active deferrals")
    recent_incidents: int = Field(default=0, description="Recent incidents")

    model_config = ConfigDict(extra="allow")


class DetailedMetric(BaseModel):
    """Detailed metric with trends and breakdowns."""

    name: str = Field(..., description="Metric name")
    current_value: float = Field(..., description="Current value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    trend: MetricTrend = Field(..., description="Trend information")
    hourly_average: float = Field(default=0.0, description="Hourly average")
    daily_average: float = Field(default=0.0, description="Daily average")
    by_service: Dict[str, float] = Field(default_factory=dict, description="Values by service")
    recent_data: List[MetricData] = Field(default_factory=list, description="Recent data points")

    model_config = ConfigDict(extra="allow")


class TelemetryMetricsResponse(BaseModel):
    """Response from metrics endpoint."""

    metrics: List[DetailedMetric] = Field(..., description="Detailed metrics")
    summary: MetricAggregate = Field(..., description="Summary statistics")
    period: str = Field(..., description="Time period")

    model_config = ConfigDict(extra="allow")


class ReasoningTrace(BaseModel):
    """Reasoning trace showing thought process."""

    trace_id: str = Field(..., description="Unique trace ID")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    task_description: Optional[str] = Field(None, description="Task description")
    start_time: datetime = Field(..., description="Start time")
    duration_ms: float = Field(..., description="Duration in milliseconds")
    thought_count: int = Field(default=0, description="Number of thoughts")
    decision_count: int = Field(default=0, description="Number of decisions")
    reasoning_depth: int = Field(default=0, description="Maximum reasoning depth")
    thoughts: List[ThoughtData] = Field(default_factory=list, description="Thought details")
    outcome: Optional[str] = Field(None, description="Trace outcome")

    @field_serializer("start_time")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class TelemetryTracesResponse(BaseModel):
    """Response from traces endpoint."""

    traces: List[ReasoningTrace] = Field(..., description="Reasoning traces")
    total_count: int = Field(..., description="Total matching traces")
    has_more: bool = Field(default=False, description="More traces available")

    model_config = ConfigDict(extra="allow")


class LogEntry(BaseModel):
    """System log entry."""

    timestamp: datetime = Field(..., description="Log timestamp")
    level: str = Field(..., description="Log level: DEBUG|INFO|WARNING|ERROR|CRITICAL")
    service: str = Field(..., description="Service name")
    message: str = Field(..., description="Log message")
    trace_id: Optional[str] = Field(None, description="Associated trace ID")
    context: Dict[str, str] = Field(default_factory=dict, description="Additional context")

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class TelemetryLogsResponse(BaseModel):
    """Response from logs endpoint."""

    logs: List[LogEntry] = Field(..., description="Log entries")
    total_count: int = Field(..., description="Total matching logs")
    has_more: bool = Field(default=False, description="More logs available")

    model_config = ConfigDict(extra="allow")


class TelemetryQueryResult(BaseModel):
    """Result from a telemetry query."""

    query_type: str = Field(..., description="Type of query executed")
    total_results: int = Field(..., description="Total results found")
    returned_results: int = Field(..., description="Results returned")
    execution_time_ms: float = Field(..., description="Query execution time")

    model_config = ConfigDict(extra="allow")


class MetricsQueryResult(TelemetryQueryResult):
    """Result from metrics query."""

    metrics: List[MetricData] = Field(..., description="Metric data")
    aggregations: Optional[MetricAggregate] = Field(None, description="Aggregated statistics")


class TracesQueryResult(TelemetryQueryResult):
    """Result from traces query."""

    traces: List[ReasoningTrace] = Field(..., description="Reasoning traces")


class LogsQueryResult(TelemetryQueryResult):
    """Result from logs query."""

    logs: List[LogEntry] = Field(..., description="Log entries")


class IncidentData(BaseModel):
    """Incident information."""

    incident_id: str = Field(..., description="Incident ID")
    timestamp: datetime = Field(..., description="Incident time")
    severity: str = Field(..., description="Severity: low|medium|high|critical")
    service: str = Field(..., description="Affected service")
    message: str = Field(..., description="Incident message")
    resolved: bool = Field(..., description="Whether resolved")
    resolved_at: Optional[datetime] = Field(None, description="Resolution time")

    @field_serializer("timestamp", "resolved_at")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class IncidentsQueryResult(TelemetryQueryResult):
    """Result from incidents query."""

    incidents: List[IncidentData] = Field(..., description="Incidents")


class InsightData(BaseModel):
    """System insight."""

    insight_id: str = Field(..., description="Insight ID")
    timestamp: datetime = Field(..., description="Generation time")
    category: str = Field(..., description="Insight category")
    title: str = Field(..., description="Insight title")
    description: str = Field(..., description="Detailed description")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")
    severity: str = Field(..., description="Severity: info|warning|critical")

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class InsightsQueryResult(TelemetryQueryResult):
    """Result from insights query."""

    insights: List[InsightData] = Field(..., description="System insights")
