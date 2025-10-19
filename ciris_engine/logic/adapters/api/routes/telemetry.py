"""
Telemetry & Observability endpoints for CIRIS API v1.

Consolidated metrics, traces, logs, and insights from all system components.
"""

import logging
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.api.auth import AuthContext
from ciris_engine.schemas.api.responses import ResponseMetadata, SuccessResponse
from ciris_engine.schemas.api.telemetry import (
    APIResponseThoughtStep,
    LogContext,
    MetricTags,
    QueryResult,
    ServiceMetricValue,
    TelemetryQueryFilters,
)
from ciris_engine.schemas.types import JSONDict

from ..constants import (
    DESC_CURRENT_COGNITIVE_STATE,
    DESC_END_TIME,
    DESC_START_TIME,
    ERROR_TELEMETRY_SERVICE_NOT_AVAILABLE,
)
from ..dependencies.auth import require_admin, require_observer

# Error message constants to avoid duplication
ERROR_TELEMETRY_NOT_INITIALIZED = "Critical system failure: Telemetry service not initialized"
ERROR_AUDIT_NOT_INITIALIZED = "Critical system failure: Audit service not initialized"

# Import extracted modules
from .telemetry_converters import convert_to_graphite, convert_to_prometheus
from .telemetry_helpers import get_telemetry_from_service
from .telemetry_models import (
    LogEntry,
    MetricData,
    ResourceDataPoint,
    ResourceHistoryResponse,
    ResourceMetricData,
    ResourceMetricStats,
    ResourceUsage,
    ServiceHealth,
    SystemOverview,
    TimePeriod,
)
from .telemetry_otlp import convert_logs_to_otlp_json, convert_to_otlp_json, convert_traces_to_otlp_json
from .telemetry_resource_helpers import (
    MetricValueExtractor,
    ResourceDataPointBuilder,
    ResourceMetricBuilder,
    ResourceMetricsCollector,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])

# Additional request/response schemas not in telemetry_models.py


class DetailedMetric(BaseModel):
    """Detailed metric information."""

    name: str = Field(..., description="Metric name")
    current_value: float = Field(..., description="Current value")
    unit: Optional[str] = Field(None, description="Metric unit")
    trend: str = Field("stable", description="Trend: up|down|stable")
    hourly_average: float = Field(0.0, description="Average over last hour")
    daily_average: float = Field(0.0, description="Average over last day")
    by_service: List[ServiceMetricValue] = Field(default_factory=list, description="Values by service")
    recent_data: List[MetricData] = Field(default_factory=list, description="Recent data points")


class MetricAggregate(BaseModel):
    """Aggregated metric statistics."""

    min: float = Field(0.0, description="Minimum value")
    max: float = Field(0.0, description="Maximum value")
    avg: float = Field(0.0, description="Average value")
    sum: float = Field(0.0, description="Sum of values")
    count: int = Field(0, description="Number of data points")
    p50: Optional[float] = Field(None, description="50th percentile")
    p95: Optional[float] = Field(None, description="95th percentile")
    p99: Optional[float] = Field(None, description="99th percentile")


class MetricsResponse(BaseModel):
    """Detailed metrics response."""

    metrics: List[DetailedMetric] = Field(..., description="Detailed metrics")
    summary: MetricAggregate = Field(..., description="Summary statistics")
    period: str = Field(..., description="Time period")
    timestamp: datetime = Field(..., description="Response timestamp")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None


class ReasoningTraceData(BaseModel):
    """Reasoning trace information."""

    trace_id: str = Field(..., description="Unique trace ID")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    task_description: Optional[str] = Field(None, description="Task description")
    start_time: datetime = Field(..., description="Trace start time")
    duration_ms: float = Field(..., description="Total duration")
    thought_count: int = Field(0, description="Number of thoughts")
    decision_count: int = Field(0, description="Number of decisions")
    reasoning_depth: int = Field(0, description="Maximum reasoning depth")
    thoughts: List[APIResponseThoughtStep] = Field(default_factory=list, description="Thought steps")
    outcome: Optional[str] = Field(None, description="Final outcome")

    @field_serializer("start_time")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None


class TracesResponse(BaseModel):
    """Reasoning traces response."""

    traces: List[ReasoningTraceData] = Field(..., description="Recent reasoning traces")
    total: int = Field(..., description="Total trace count")
    has_more: bool = Field(False, description="More traces available")


class LogEntryResponse(BaseModel):
    """System log entry."""

    timestamp: datetime = Field(..., description="Log timestamp")
    level: str = Field(..., description="Log level: DEBUG|INFO|WARNING|ERROR|CRITICAL")
    service: str = Field(..., description="Source service")
    message: str = Field(..., description="Log message")
    context: LogContext = Field(default_factory=lambda: LogContext.model_validate({}), description="Additional context")
    trace_id: Optional[str] = Field(None, description="Associated trace ID")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None


class LogsResponse(BaseModel):
    """System logs response."""

    logs: List[LogEntryResponse] = Field(..., description="Log entries")
    total: int = Field(..., description="Total matching logs")
    has_more: bool = Field(False, description="More logs available")


class TelemetryQuery(BaseModel):
    """Custom telemetry query."""

    query_type: str = Field(..., description="Query type: metrics|traces|logs|incidents|insights")
    filters: TelemetryQueryFilters = Field(
        default_factory=lambda: TelemetryQueryFilters.model_validate({}), description="Query filters"
    )
    aggregations: Optional[List[str]] = Field(None, description="Aggregations to apply")
    start_time: Optional[datetime] = Field(None, description="Query start time")
    end_time: Optional[datetime] = Field(None, description="Query end time")
    limit: int = Field(100, ge=1, le=1000, description="Result limit")

    @field_serializer("start_time", "end_time")
    def serialize_times(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class QueryResponse(BaseModel):
    """Custom query response."""

    query_type: str = Field(..., description="Query type executed")
    results: List[QueryResult] = Field(..., description="Query results")
    total: int = Field(..., description="Total results found")
    execution_time_ms: float = Field(..., description="Query execution time")


# Helper functions


async def _update_telemetry_summary(overview: SystemOverview, telemetry_service: Any) -> None:
    """Update overview with telemetry summary metrics."""
    if telemetry_service and hasattr(telemetry_service, "get_telemetry_summary"):
        try:
            summary = await telemetry_service.get_telemetry_summary()
            overview.messages_processed_24h = summary.messages_processed_24h
            overview.thoughts_processed_24h = summary.thoughts_processed_24h
            overview.tasks_completed_24h = summary.tasks_completed_24h
            overview.errors_24h = summary.errors_24h
            overview.tokens_last_hour = summary.tokens_last_hour
            overview.cost_last_hour_cents = summary.cost_last_hour_cents
            overview.carbon_last_hour_grams = summary.carbon_last_hour_grams
            overview.energy_last_hour_kwh = summary.energy_last_hour_kwh
            overview.tokens_24h = summary.tokens_24h
            overview.cost_24h_cents = summary.cost_24h_cents
            overview.carbon_24h_grams = summary.carbon_24h_grams
            overview.energy_24h_kwh = summary.energy_24h_kwh
            overview.error_rate_percent = summary.error_rate_percent
        except Exception as e:
            logger.warning(
                f"Telemetry metric retrieval failed for telemetry summary: {type(e).__name__}: {str(e)} - Returning default/empty value"
            )


async def _update_visibility_state(overview: SystemOverview, visibility_service: Any) -> None:
    """Update overview with visibility state information."""
    if visibility_service:
        try:
            snapshot = await visibility_service.get_current_state()
            if snapshot:
                overview.reasoning_depth = snapshot.reasoning_depth
                if snapshot.current_task:
                    overview.current_task = snapshot.current_task.description
        except Exception as e:
            logger.warning(
                f"Telemetry metric retrieval failed for visibility state: {type(e).__name__}: {str(e)} - Returning default/empty value"
            )


def _create_empty_system_overview() -> SystemOverview:
    """Create a SystemOverview with default values."""
    return SystemOverview(
        uptime_seconds=0.0,
        cognitive_state="UNKNOWN",
        messages_processed_24h=0,
        thoughts_processed_24h=0,
        tasks_completed_24h=0,
        errors_24h=0,
        tokens_last_hour=0.0,
        cost_last_hour_cents=0.0,
        carbon_last_hour_grams=0.0,
        energy_last_hour_kwh=0.0,
        tokens_24h=0.0,
        cost_24h_cents=0.0,
        carbon_24h_grams=0.0,
        energy_24h_kwh=0.0,
        memory_mb=0.0,
        cpu_percent=0.0,
        healthy_services=0,
        degraded_services=0,
        error_rate_percent=0.0,
        current_task=None,
        reasoning_depth=0,
        active_deferrals=0,
        recent_incidents=0,
        total_metrics=0,
        active_services=0,
    )


def _validate_critical_services(telemetry_service: Any, time_service: Any) -> None:
    """Validate that critical services are available."""
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_NOT_INITIALIZED)
    if not time_service:
        raise HTTPException(status_code=503, detail="Critical system failure: Time service not initialized")


def _update_uptime(overview: SystemOverview, time_service: Any) -> None:
    """Update overview with system uptime."""
    if not time_service:
        return

    try:
        uptime = time_service.get_uptime()
        overview.uptime_seconds = uptime
    except Exception as e:
        logger.warning(
            f"Telemetry metric retrieval failed for uptime: {type(e).__name__}: {str(e)} - Returning default/empty value"
        )


def _update_cognitive_state(overview: SystemOverview, request: Request) -> None:
    """Update overview with cognitive state from runtime."""
    runtime = getattr(request.app.state, "runtime", None)
    if runtime and hasattr(runtime, "state_manager"):
        overview.cognitive_state = runtime.state_manager.current_state


def _update_resource_usage(overview: SystemOverview, resource_monitor: Any) -> None:
    """Update overview with resource usage metrics."""
    if not resource_monitor:
        return

    try:
        # Access the snapshot directly
        if hasattr(resource_monitor, "snapshot"):
            overview.memory_mb = float(resource_monitor.snapshot.memory_mb)
            overview.cpu_percent = float(resource_monitor.snapshot.cpu_percent)
    except Exception as e:
        logger.warning(
            f"Telemetry metric retrieval failed for resource usage: {type(e).__name__}: {str(e)} - Returning default/empty value"
        )


def _get_service_health_counts(request: Request) -> tuple[int, int]:
    """Count healthy and degraded services (22 core services + API consent_manager)."""
    services = [
        # Graph Services (6)
        "memory_service",
        "config_service",
        "telemetry_service",
        "audit_service",
        "incident_management_service",
        "tsdb_consolidation_service",
        # Infrastructure Services (8)
        "time_service",
        "shutdown_service",
        "initialization_service",
        "authentication_service",
        "resource_monitor",
        "database_maintenance_service",
        "secrets_service",
        "consent_manager",  # API-specific consent service
        # Governance Services (4)
        "wise_authority_service",
        "adaptive_filter_service",
        "visibility_service",
        "self_observation_service",
        # Runtime Services (3)
        "llm_service",
        "runtime_control_service",
        "task_scheduler",
        # Tool Services (1)
        "secrets_tool_service",
    ]

    healthy = 0
    degraded = 0
    for service_attr in services:
        if getattr(request.app.state, service_attr, None):
            healthy += 1
        else:
            degraded += 1

    return healthy, degraded


async def _update_incident_count(overview: SystemOverview, incident_service: Any) -> None:
    """Update overview with recent incident count."""
    if not incident_service:
        return

    try:
        # Get count of incidents from the last hour
        overview.recent_incidents = await incident_service.get_incident_count(hours=1)
    except Exception as e:
        logger.warning(
            f"Telemetry metric retrieval failed for incident count: {type(e).__name__}: {str(e)} - Returning default/empty value"
        )


async def _update_deferral_count(overview: SystemOverview, wise_authority: Any) -> None:
    """Update overview with active deferral count."""
    if not wise_authority:
        return

    try:
        deferrals = await wise_authority.get_pending_deferrals()
        overview.active_deferrals = len(deferrals) if deferrals else 0
    except Exception as e:
        logger.warning(
            f"Telemetry metric retrieval failed for deferral count: {type(e).__name__}: {str(e)} - Returning default/empty value"
        )


async def _update_metrics_count(overview: SystemOverview, telemetry_service: Any, healthy_services: int) -> None:
    """Update overview with telemetry metrics count."""
    if not telemetry_service:
        return

    try:
        # Count total metrics collected
        if hasattr(telemetry_service, "get_metric_count"):
            overview.total_metrics = await telemetry_service.get_metric_count()
        elif hasattr(telemetry_service, "query_metrics"):
            overview.total_metrics = await _estimate_metrics_count(telemetry_service)

        # Count active services (services that have reported metrics)
        overview.active_services = healthy_services  # Use healthy services count as proxy

    except Exception as e:
        logger.warning(
            f"Telemetry metric retrieval failed for metrics count: {type(e).__name__}: {str(e)} - Returning default/empty value"
        )


async def _estimate_metrics_count(telemetry_service: Any) -> int:
    """Estimate total metrics count from common metric queries."""
    metric_names = [
        "llm.tokens.total",  # Total tokens used
        "llm_tokens_used",  # Legacy token metric
        "thought_processing_completed",  # Thoughts completed
        "action_selected_task_complete",  # Tasks completed
        "handler_invoked_total",  # Total handler invocations
        "action_selected_memorize",  # Memory operations
    ]

    total = 0
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)

    for metric in metric_names:
        try:
            data = await telemetry_service.query_metrics(metric_name=metric, start_time=day_ago, end_time=now)
            if data:
                total += len(data)
        except (AttributeError, TypeError, ValueError, RuntimeError) as e:
            logger.debug(f"Failed to query metric '{metric}': {type(e).__name__}: {str(e)}")

    return total


async def _get_system_overview(request: Request) -> SystemOverview:
    """Build comprehensive system overview from all services."""
    # Get core services - THESE MUST EXIST
    telemetry_service = request.app.state.telemetry_service
    visibility_service = request.app.state.visibility_service
    time_service = request.app.state.time_service
    resource_monitor = request.app.state.resource_monitor
    incident_service = request.app.state.incident_management_service
    wise_authority = request.app.state.wise_authority_service

    # Validate critical services
    _validate_critical_services(telemetry_service, time_service)

    # Initialize overview with default values
    overview = _create_empty_system_overview()

    # Update overview with data from various services
    _update_uptime(overview, time_service)
    await _update_telemetry_summary(overview, telemetry_service)
    _update_cognitive_state(overview, request)
    await _update_visibility_state(overview, visibility_service)
    _update_resource_usage(overview, resource_monitor)

    # Update service health counts
    healthy, degraded = _get_service_health_counts(request)
    overview.healthy_services = healthy
    overview.degraded_services = degraded

    # Update incident and deferral counts
    await _update_incident_count(overview, incident_service)
    await _update_deferral_count(overview, wise_authority)
    await _update_metrics_count(overview, telemetry_service, healthy)

    return overview


# Endpoints


async def _export_otlp_metrics(telemetry_service: Any) -> JSONDict:
    """Export metrics in OTLP format."""
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_SERVICE_NOT_AVAILABLE)

    # Get aggregated telemetry
    aggregated = await telemetry_service.get_aggregated_telemetry()

    # Convert to dict for OTLP conversion
    telemetry_dict = {
        "system_healthy": aggregated.system_healthy,
        "services_online": aggregated.services_online,
        "services_total": aggregated.services_total,
        "overall_error_rate": aggregated.overall_error_rate,
        "overall_uptime_seconds": aggregated.overall_uptime_seconds,
        "total_errors": aggregated.total_errors,
        "total_requests": aggregated.total_requests,
        "services": aggregated.services,
    }

    # Add covenant metrics if available
    if hasattr(aggregated, "covenant_metrics"):
        telemetry_dict["covenant_metrics"] = aggregated.covenant_metrics

    return convert_to_otlp_json(telemetry_dict)


def _extract_basic_trace_fields(correlation: Any) -> JSONDict:
    """Extract basic trace fields from correlation object."""
    return {
        "trace_id": (correlation.trace_context.trace_id if correlation.trace_context else correlation.correlation_id),
        "span_id": (correlation.trace_context.span_id if correlation.trace_context else str(uuid.uuid4())),
        "parent_span_id": (correlation.trace_context.parent_span_id if correlation.trace_context else None),
        "timestamp": (
            correlation.timestamp.isoformat() if correlation.timestamp else datetime.now(timezone.utc).isoformat()
        ),
        "operation": correlation.action_type or "unknown",
        "service": correlation.service_type,
        "handler": correlation.handler_name,
        "status": (correlation.status.value if hasattr(correlation.status, "value") else str(correlation.status)),
    }


def _extract_request_data_fields(correlation: Any, trace_data: JSONDict) -> None:
    """Extract task/thought linkage from request data."""
    if not correlation.request_data:
        return

    if hasattr(correlation.request_data, "task_id") and correlation.request_data.task_id:
        trace_data["task_id"] = correlation.request_data.task_id
    if hasattr(correlation.request_data, "thought_id") and correlation.request_data.thought_id:
        trace_data["thought_id"] = correlation.request_data.thought_id


def _extract_response_data_fields(correlation: Any, trace_data: JSONDict) -> None:
    """Extract performance data from response data."""
    if not correlation.response_data:
        return

    if hasattr(correlation.response_data, "execution_time_ms"):
        trace_data["duration_ms"] = correlation.response_data.execution_time_ms
    if hasattr(correlation.response_data, "success"):
        trace_data["success"] = correlation.response_data.success
    if hasattr(correlation.response_data, "error_message"):
        trace_data["error"] = correlation.response_data.error_message


def _extract_span_attributes(correlation: Any, trace_data: JSONDict) -> None:
    """Extract span attributes from trace context."""
    if not correlation.trace_context:
        return

    trace_data["span_name"] = (
        correlation.trace_context.span_name
        if hasattr(correlation.trace_context, "span_name")
        else correlation.action_type
    )
    trace_data["span_kind"] = (
        correlation.trace_context.span_kind if hasattr(correlation.trace_context, "span_kind") else "internal"
    )


def _build_trace_data_from_correlation(correlation: Any) -> JSONDict:
    """Build trace data dictionary from correlation object."""
    trace_data = _extract_basic_trace_fields(correlation)
    _extract_request_data_fields(correlation, trace_data)
    _extract_response_data_fields(correlation, trace_data)
    _extract_span_attributes(correlation, trace_data)
    return trace_data


async def _export_otlp_traces(visibility_service: Any, limit: int) -> JSONDict:
    """Export traces in OTLP format."""
    if not visibility_service:
        raise HTTPException(status_code=503, detail="Visibility service not available")

    traces = []
    try:
        # Get service correlations (trace spans)
        correlations = await visibility_service.get_recent_traces(limit=limit)

        for correlation in correlations:
            trace_data = _build_trace_data_from_correlation(correlation)
            traces.append(trace_data)

    except Exception as e:
        print(f"ERROR in get_otlp_telemetry traces: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()

    return convert_traces_to_otlp_json(traces)


def _build_log_data_from_entry(log_entry: Any) -> JSONDict:
    """Build log data dictionary from log entry."""
    log_data = {
        "timestamp": log_entry.timestamp.isoformat(),
        "level": log_entry.level,
        "message": log_entry.message,
        "service": log_entry.service,
    }

    # Add context data if available - handle both LogEntry formats
    # LogEntryResponse has nested context object, telemetry_models.LogEntry has top-level fields
    if hasattr(log_entry, "context") and log_entry.context:
        if hasattr(log_entry.context, "correlation_id") and log_entry.context.correlation_id:
            log_data["correlation_id"] = log_entry.context.correlation_id
        if hasattr(log_entry.context, "trace_id") and log_entry.context.trace_id:
            log_data["trace_id"] = log_entry.context.trace_id
        if hasattr(log_entry.context, "user_id") and log_entry.context.user_id:
            log_data["user_id"] = log_entry.context.user_id
        if hasattr(log_entry.context, "entity_id") and log_entry.context.entity_id:
            log_data["entity_id"] = log_entry.context.entity_id
    else:
        # Handle flat LogEntry format from telemetry_models
        if hasattr(log_entry, "correlation_id") and log_entry.correlation_id:
            log_data["correlation_id"] = log_entry.correlation_id
        if hasattr(log_entry, "user_id") and log_entry.user_id:
            log_data["user_id"] = log_entry.user_id

    # Add trace ID at top level if available
    if hasattr(log_entry, "trace_id") and log_entry.trace_id:
        log_data["trace_id"] = log_entry.trace_id

    return log_data


async def _export_otlp_logs(limit: int, start_time: Optional[datetime], end_time: Optional[datetime]) -> JSONDict:
    """Export logs in OTLP format."""
    logs = []
    try:
        from .telemetry_logs_reader import log_reader

        # Read actual log files including incidents
        file_logs = log_reader.read_logs(
            level=None,  # Get all levels
            service=None,  # Get all services
            limit=limit,
            start_time=start_time if start_time else None,  # Don't default to 1 hour ago
            end_time=end_time if end_time else None,  # Don't default to now
            include_incidents=True,  # Include incident logs (WARNING/ERROR/CRITICAL)
        )

        # Convert LogEntry objects to dict format for OTLP
        for log_entry in file_logs:
            log_data = _build_log_data_from_entry(log_entry)
            logs.append(log_data)

    except ImportError:
        # Log reader module not available
        logger.warning("Log reader not available for OTLP logs export")
    except Exception as e:
        logger.warning(f"Failed to read log files for OTLP: {e}")

    return convert_logs_to_otlp_json(logs)


@router.get("/otlp/{signal}", response_model=None)
async def get_otlp_telemetry(
    signal: str,
    request: Request,
    auth: AuthContext = Depends(require_observer),
    limit: int = Query(100, ge=1, le=1000, description="Maximum items to return"),
    start_time: Optional[datetime] = Query(None, description=DESC_START_TIME),
    end_time: Optional[datetime] = Query(None, description=DESC_END_TIME),
) -> JSONDict:
    """
    OpenTelemetry Protocol (OTLP) JSON export.

    Export telemetry data in OTLP JSON format for OpenTelemetry collectors.

    Supported signals:
    - metrics: System and service metrics
    - traces: Distributed traces with spans
    - logs: Structured log records

    Returns OTLP JSON formatted data compatible with OpenTelemetry v1.7.0 specification.
    """

    if signal not in ["metrics", "traces", "logs"]:
        raise HTTPException(
            status_code=400, detail=f"Invalid signal type: {signal}. Must be one of: metrics, traces, logs"
        )

    try:
        if signal == "metrics":
            return await _export_otlp_metrics(request.app.state.telemetry_service)
        elif signal == "traces":
            return await _export_otlp_traces(request.app.state.visibility_service, limit)
        else:  # signal == "logs" - already validated above
            return await _export_otlp_logs(limit, start_time, end_time)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OTLP export failed for {signal}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export {signal} in OTLP format")


@router.get("/overview", response_model=SuccessResponse[SystemOverview])
async def get_telemetry_overview(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[SystemOverview]:
    """
    System metrics summary.

    Comprehensive overview combining telemetry, visibility, incidents, and resource usage.
    """
    try:
        overview = await _get_system_overview(request)
        return SuccessResponse(
            data=overview,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )
    except HTTPException:
        # Re-raise HTTPException as-is to preserve status code
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ResourceUsageData(BaseModel):
    """Current resource usage data."""

    cpu_percent: float = Field(..., description="CPU usage percentage")
    memory_mb: float = Field(..., description="Memory usage in MB")
    memory_percent: float = Field(..., description="Memory usage percentage")
    disk_usage_bytes: int = Field(0, description="Disk usage in bytes")
    disk_usage_gb: float = Field(0.0, description="Disk usage in GB")
    active_threads: int = Field(0, description="Number of active threads")
    open_files: int = Field(0, description="Number of open files")
    timestamp: str = Field(..., description="Timestamp of measurement")


class ResourceLimits(BaseModel):
    """Resource usage limits."""

    max_memory_mb: float = Field(..., description="Maximum memory in MB")
    max_cpu_percent: float = Field(100.0, description="Maximum CPU percentage")
    max_disk_bytes: int = Field(0, description="Maximum disk usage in bytes")


class ResourceHistoryPoint(BaseModel):
    """Historical resource usage point."""

    timestamp: datetime = Field(..., description="Timestamp of measurement")
    cpu_percent: float = Field(..., description="CPU usage percentage")
    memory_mb: float = Field(..., description="Memory usage in MB")


class ResourceHealthStatus(BaseModel):
    """Resource health status."""

    status: str = Field(..., description="Health status: healthy|warning|critical")
    warnings: List[str] = Field(default_factory=list, description="Warning messages")


class ResourceTelemetryResponse(BaseModel):
    """Complete resource telemetry response."""

    current: ResourceUsageData = Field(..., description="Current resource usage")
    limits: ResourceLimits = Field(..., description="Resource limits")
    history: List[ResourceHistoryPoint] = Field(default_factory=list, description="Historical data")
    health: ResourceHealthStatus = Field(..., description="Health status")


@router.get("/resources", response_model=SuccessResponse[ResourceTelemetryResponse])
async def get_resource_telemetry(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ResourceTelemetryResponse]:
    """
    Get current resource usage telemetry.

    Returns CPU, memory, disk, and other resource metrics.
    """
    # These services MUST exist - if they don't, we have a critical failure
    resource_monitor = request.app.state.resource_monitor
    telemetry_service = request.app.state.telemetry_service

    if not resource_monitor:
        raise HTTPException(status_code=503, detail="Critical system failure: Resource monitor service not initialized")
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_NOT_INITIALIZED)

    try:
        # Get current resource usage
        current_usage = resource_monitor.snapshot

        # Get resource limits
        limits = resource_monitor.budget

        # Get historical data if available
        history_points = []
        if telemetry_service and hasattr(telemetry_service, "query_metrics"):
            now = datetime.now(timezone.utc)
            hour_ago = now - timedelta(hours=1)

            # Query CPU history
            cpu_history = await telemetry_service.query_metrics(
                metric_name="cpu_percent", start_time=hour_ago, end_time=now
            )

            # Query memory history
            memory_history = await telemetry_service.query_metrics(
                metric_name="memory_mb", start_time=hour_ago, end_time=now
            )

            # Build history points
            for i in range(min(len(cpu_history), len(memory_history))):
                history_points.append(
                    ResourceHistoryPoint(
                        timestamp=cpu_history[i].timestamp,
                        cpu_percent=float(cpu_history[i].value),
                        memory_mb=float(memory_history[i].value),
                    )
                )

        # Convert disk bytes to GB for the response
        disk_bytes = getattr(current_usage, "disk_usage_bytes", 0)
        disk_gb = disk_bytes / (1024 * 1024 * 1024) if disk_bytes > 0 else 0.0

        response = ResourceTelemetryResponse(
            current=ResourceUsageData(
                cpu_percent=current_usage.cpu_percent,
                memory_mb=current_usage.memory_mb,
                memory_percent=current_usage.memory_percent,
                disk_usage_bytes=disk_bytes,
                disk_usage_gb=disk_gb,
                active_threads=getattr(current_usage, "active_threads", 0),
                open_files=getattr(current_usage, "open_files", 0),
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
            limits=ResourceLimits(
                max_memory_mb=getattr(limits, "max_memory_mb", 2048.0),
                max_cpu_percent=getattr(limits, "max_cpu_percent", 100.0),
                max_disk_bytes=getattr(limits, "max_disk_bytes", 0),
            ),
            history=history_points[-60:],  # Last hour of data
            health=ResourceHealthStatus(
                status="healthy" if current_usage.memory_percent < 80 and current_usage.cpu_percent < 80 else "warning",
                warnings=getattr(current_usage, "warnings", []),
            ),
        )

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        # Re-raise HTTPException as-is to preserve status code
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _get_metric_unit(metric_name: str) -> Optional[str]:
    """Determine unit from metric name."""
    if "tokens" in metric_name:
        return "tokens"
    elif "time" in metric_name or "latency" in metric_name or "ms" in metric_name:
        return "ms"
    elif "percent" in metric_name or "rate" in metric_name or "cpu" in metric_name:
        return "%"
    elif "mb" in metric_name or "memory" in metric_name:
        return "MB"
    elif "cents" in metric_name:
        return "cents"
    elif "grams" in metric_name:
        return "g"
    elif "kwh" in metric_name:
        return "kWh"
    return "count"


def _calculate_trend(values: List[float]) -> str:
    """Calculate trend from a list of values."""
    if len(values) <= 1:
        return "stable"

    recent_avg = sum(values[-5:]) / len(values[-5:])
    older_avg = sum(values[:-5]) / len(values[:-5]) if len(values) > 5 else values[0]

    if recent_avg > older_avg * 1.1:
        return "up"
    elif recent_avg < older_avg * 0.9:
        return "down"
    return "stable"


async def _process_metric_data(telemetry_service: Any, metric_name: str, now: datetime) -> Optional[DetailedMetric]:
    """Process metric data for a single metric name."""
    if not hasattr(telemetry_service, "query_metrics"):
        return None

    day_ago = now - timedelta(hours=24)
    hour_ago = now - timedelta(hours=1)

    # Get hourly data
    hourly_data = await telemetry_service.query_metrics(metric_name=metric_name, start_time=hour_ago, end_time=now)

    # Get daily data
    daily_data = await telemetry_service.query_metrics(metric_name=metric_name, start_time=day_ago, end_time=now)

    if not (hourly_data or daily_data):
        return None

    # Calculate averages and trends
    hourly_values = [float(dp.value) for dp in hourly_data] if hourly_data else [0.0]
    daily_values = [float(dp.value) for dp in daily_data] if daily_data else [0.0]

    hourly_avg = sum(hourly_values) / len(hourly_values) if hourly_values else 0.0
    daily_avg = sum(daily_values) / len(daily_values) if daily_values else 0.0
    current_value = hourly_values[-1] if hourly_values else 0.0

    # Determine trend
    trend = _calculate_trend(hourly_values)
    unit = _get_metric_unit(metric_name)

    return DetailedMetric(
        name=metric_name,
        current_value=current_value,
        unit=unit,
        trend=trend,
        hourly_average=hourly_avg,
        daily_average=daily_avg,
        by_service=[],  # Could aggregate by service if tags available
        recent_data=[
            MetricData(
                timestamp=dp.timestamp,
                value=float(dp.value),
                tags=MetricTags(**dp.tags) if dp.tags else MetricTags(),
            )
            for dp in (hourly_data[-10:] if hourly_data else [])
        ],
    )


async def _get_legacy_metrics(telemetry_service: Any) -> List[DetailedMetric]:
    """Get metrics from legacy get_metrics method."""
    metrics: List[DetailedMetric] = []
    if not (hasattr(telemetry_service, "get_metrics") and not hasattr(telemetry_service, "query_metrics")):
        return metrics

    legacy_metrics = await telemetry_service.get_metrics()
    if not legacy_metrics:
        return metrics

    for metric_name, value in legacy_metrics.items():
        unit = _get_metric_unit(metric_name)
        metrics.append(
            DetailedMetric(
                name=metric_name,
                current_value=float(value),
                unit=unit,
                trend="stable",  # Default trend when no history
                hourly_average=float(value),
                daily_average=float(value),
                by_service=[],
                recent_data=[],
            )
        )
    return metrics


def _calculate_metrics_summary(metrics: List[DetailedMetric]) -> MetricAggregate:
    """Calculate summary statistics across all metrics."""
    all_values = []
    for metric in metrics:
        if metric.recent_data:
            all_values.extend([dp.value for dp in metric.recent_data])

    if all_values:
        return MetricAggregate(
            min=min(all_values),
            max=max(all_values),
            avg=sum(all_values) / len(all_values),
            sum=sum(all_values),
            count=len(all_values),
        )
    else:
        return MetricAggregate(min=0.0, max=0.0, avg=0.0, sum=0.0, count=0)


@router.get("/metrics", response_model=SuccessResponse[MetricsResponse])
async def get_detailed_metrics(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[MetricsResponse]:
    """
    Detailed metrics.

    Get detailed metrics with trends and breakdowns by service.
    """
    # Telemetry service MUST exist - if it doesn't, we have a critical failure
    telemetry_service = request.app.state.telemetry_service
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_NOT_INITIALIZED)

    try:
        # Common metrics to query - use actual metric names that exist in TSDB nodes
        metric_names = [
            "llm_tokens_used",  # Legacy LLM token usage
            "llm_api_call_structured",  # Legacy LLM API calls
            "llm.tokens.total",  # New format: total tokens
            "llm.tokens.input",  # New format: input tokens
            "llm.tokens.output",  # New format: output tokens
            "llm.cost.cents",  # Cost tracking
            "llm.environmental.carbon_grams",  # Carbon footprint
            "llm.environmental.energy_kwh",  # Energy usage
            "handler_completed_total",  # Handler completions
            "handler_invoked_total",  # Handler invocations
            "thought_processing_completed",  # Thought completion
            "thought_processing_started",  # Thought starts
            "action_selected_task_complete",  # Task completions
            "action_selected_memorize",  # Memory operations
        ]

        metrics = []
        now = datetime.now(timezone.utc)

        # Process metrics with query_metrics method
        for metric_name in metric_names:
            metric = await _process_metric_data(telemetry_service, metric_name, now)
            if metric:
                metrics.append(metric)

        # Fallback to legacy get_metrics if needed
        if not metrics:
            metrics = await _get_legacy_metrics(telemetry_service)

        # Calculate summary statistics
        summary = _calculate_metrics_summary(metrics)

        response = MetricsResponse(metrics=metrics, summary=summary, period="24h", timestamp=now)

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        # Re-raise HTTPException as-is to preserve status code
        raise
    except Exception as e:
        import traceback

        logger.error(f"Error in get_detailed_metrics: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_trace_from_task(task: Any, visibility_service: Any) -> Optional[ReasoningTraceData]:
    """Extract a reasoning trace from a task via visibility service."""
    if not hasattr(visibility_service, "get_reasoning_trace"):
        return None

    trace = await visibility_service.get_reasoning_trace(task.task_id)
    if not trace:
        return None

    return ReasoningTraceData(
        trace_id=f"trace_{task.task_id}",
        task_id=task.task_id,
        task_description=task.description,
        start_time=(datetime.fromisoformat(task.created_at) if isinstance(task.created_at, str) else task.created_at),
        duration_ms=0,  # TaskOutcome doesn't have completion timestamp
        thought_count=len(trace.thought_steps),
        decision_count=len(trace.decisions) if hasattr(trace, "decisions") else 0,
        reasoning_depth=len(trace.thought_steps) if hasattr(trace, "thought_steps") else 0,
        thoughts=[
            APIResponseThoughtStep(
                step=i,
                content=getattr(thought, "content", str(thought)),
                timestamp=getattr(thought, "timestamp", datetime.now(timezone.utc)),
                depth=getattr(thought, "depth", 0),
                action=getattr(thought, "action", None),
                confidence=getattr(thought, "confidence", None),
            )
            for i, thought in enumerate(trace.thought_steps)
        ],
        outcome=trace.outcome if hasattr(trace, "outcome") else None,
    )


async def _get_traces_from_task_history(visibility_service: Any, limit: int) -> List[ReasoningTraceData]:
    """Get traces from task history via visibility service."""
    traces: List[ReasoningTraceData] = []
    if not hasattr(visibility_service, "get_task_history"):
        return traces

    task_history = await visibility_service.get_task_history(limit=limit)

    for task in task_history:
        trace_data = await _get_trace_from_task(task, visibility_service)
        if trace_data:
            traces.append(trace_data)

    return traces


async def _get_current_reasoning_trace(visibility_service: Any) -> Optional[ReasoningTraceData]:
    """Get current reasoning trace via visibility service."""
    if not hasattr(visibility_service, "get_current_reasoning"):
        return None

    current = await visibility_service.get_current_reasoning()
    if not current:
        return None

    return ReasoningTraceData(
        trace_id="trace_current",
        task_id=current.get("task_id"),
        task_description=current.get("task_description"),
        start_time=datetime.now(timezone.utc),
        duration_ms=0,
        thought_count=len(current.get("thoughts", [])),
        decision_count=0,
        reasoning_depth=current.get("depth", 0),
        thoughts=[_convert_thought_to_api_response(i, t) for i, t in enumerate(current.get("thoughts", []))],
        outcome=None,
    )


def _extract_content_from_thought_data(thought_data: Any) -> str:
    """Extract content from thought data with fallbacks."""
    if hasattr(thought_data, "thought") and hasattr(thought_data.thought, "content"):
        return str(thought_data.thought.content)
    if isinstance(thought_data, dict):
        return str(thought_data.get("content", ""))
    return str(thought_data)


def _extract_timestamp_from_thought_data(thought_data: Any) -> datetime:
    """Extract timestamp from thought data with fallbacks."""
    if hasattr(thought_data, "thought") and hasattr(thought_data.thought, "timestamp"):
        ts = thought_data.thought.timestamp
        if isinstance(ts, datetime):
            return ts
        return datetime.now(timezone.utc)
    if isinstance(thought_data, dict):
        ts_str = thought_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        if isinstance(ts_str, str):
            return datetime.fromisoformat(ts_str)
    return datetime.now(timezone.utc)


def _extract_depth_from_thought_data(thought_data: Any) -> int:
    """Extract depth from thought data with fallbacks."""
    if hasattr(thought_data, "thought") and hasattr(thought_data.thought, "depth"):
        depth = thought_data.thought.depth
        return int(depth) if depth is not None else 0
    if isinstance(thought_data, dict):
        depth = thought_data.get("depth", 0)
        return int(depth) if depth is not None else 0
    return 0


def _extract_action_from_thought_data(thought_data: Any) -> Optional[str]:
    """Extract action from thought data with fallbacks."""
    if hasattr(thought_data, "thought") and hasattr(thought_data.thought, "action"):
        action = thought_data.thought.action
        return str(action) if action is not None else None
    if isinstance(thought_data, dict):
        action = thought_data.get("action")
        return str(action) if action is not None else None
    return None


def _extract_confidence_from_thought_data(thought_data: Any) -> Optional[float]:
    """Extract confidence from thought data with fallbacks."""
    if hasattr(thought_data, "thought") and hasattr(thought_data.thought, "confidence"):
        conf = thought_data.thought.confidence
        return float(conf) if conf is not None else None
    if isinstance(thought_data, dict):
        conf = thought_data.get("confidence")
        return float(conf) if conf is not None else None
    return None


def _convert_thought_to_api_response(step_index: int, thought_data: Any) -> APIResponseThoughtStep:
    """Convert thought data to APIResponseThoughtStep."""
    return APIResponseThoughtStep(
        step=step_index,
        content=_extract_content_from_thought_data(thought_data),
        timestamp=_extract_timestamp_from_thought_data(thought_data),
        depth=_extract_depth_from_thought_data(thought_data),
        action=_extract_action_from_thought_data(thought_data),
        confidence=_extract_confidence_from_thought_data(thought_data),
    )


async def _get_traces_from_visibility_service(visibility_service: Any, limit: int) -> List[ReasoningTraceData]:
    """Get reasoning traces from visibility service."""
    traces = await _get_traces_from_task_history(visibility_service, limit)

    # If no task history, try current reasoning
    if not traces:
        current_trace = await _get_current_reasoning_trace(visibility_service)
        if current_trace:
            traces.append(current_trace)

    return traces


def _parse_timestamp(timestamp_value: Any) -> datetime:
    """Parse timestamp from various formats."""
    if isinstance(timestamp_value, str):
        return datetime.fromisoformat(timestamp_value)
    elif isinstance(timestamp_value, datetime):
        return timestamp_value
    else:
        return datetime.now(timezone.utc)


async def _get_traces_from_audit_service(
    audit_service: Any, start_time: Optional[datetime], end_time: Optional[datetime], limit: int
) -> List[ReasoningTraceData]:
    """Get reasoning traces from audit service as fallback."""
    # Query audit entries related to reasoning using the actual audit service method
    from ciris_engine.schemas.services.graph.audit import AuditQuery

    query = AuditQuery(
        start_time=start_time,
        end_time=end_time,
        event_type="handler_action_ponder",
        limit=limit * 10,  # Get more to group
    )
    entries = await audit_service.query_audit_trail(query)

    # Group by correlation ID or time window
    trace_groups = defaultdict(list)
    for entry in entries:
        # AuditEntry objects have .context attribute which is AuditEntryContext
        context_data = entry.context.additional_data or {}
        timestamp = entry.timestamp
        trace_key = context_data.get("task_id", timestamp.strftime("%Y%m%d%H%M"))
        trace_groups[trace_key].append(entry)

    traces = []
    for trace_id, entries in list(trace_groups.items())[:limit]:
        if entries:
            trace_data = _build_trace_from_audit_entries(trace_id, entries)
            traces.append(trace_data)

    return traces


def _build_trace_from_audit_entries(trace_id: str, entries: List[Any]) -> ReasoningTraceData:
    """Build a ReasoningTraceData from audit entries."""
    # Sort entries by timestamp - AuditEntry objects have .timestamp attribute
    entries.sort(key=lambda e: e.timestamp)

    start_timestamp = entries[0].timestamp
    end_timestamp = entries[-1].timestamp

    return ReasoningTraceData(
        trace_id=f"trace_{trace_id}",
        task_id=trace_id if trace_id != start_timestamp.strftime("%Y%m%d%H%M") else None,
        task_description=None,
        start_time=start_timestamp,
        duration_ms=(end_timestamp - start_timestamp).total_seconds() * 1000,
        thought_count=len(entries),
        decision_count=sum(1 for e in entries if "decision" in e.action.lower()),
        reasoning_depth=(max((e.context.additional_data or {}).get("depth", 0) for e in entries) if entries else 0),
        thoughts=[
            APIResponseThoughtStep(
                step=i,
                content=(e.context.additional_data or {}).get("thought", e.action),
                timestamp=e.timestamp,
                depth=(e.context.additional_data or {}).get("depth", 0),
                action=(e.context.additional_data or {}).get("action"),
                confidence=(e.context.additional_data or {}).get("confidence"),
            )
            for i, e in enumerate(entries)
        ],
        outcome=None,
    )


@router.get("/traces", response_model=SuccessResponse[TracesResponse])
async def get_reasoning_traces(
    request: Request,
    auth: AuthContext = Depends(require_observer),
    limit: int = Query(10, ge=1, le=100, description="Maximum traces to return"),
    start_time: Optional[datetime] = Query(None, description=DESC_START_TIME),
    end_time: Optional[datetime] = Query(None, description=DESC_END_TIME),
) -> SuccessResponse[TracesResponse]:
    """
    Reasoning traces.

    Get reasoning traces showing agent thought processes and decision-making.
    """
    # These services MUST exist
    visibility_service = request.app.state.visibility_service
    audit_service = request.app.state.audit_service

    if not visibility_service:
        raise HTTPException(status_code=503, detail="Critical system failure: Visibility service not initialized")
    if not audit_service:
        raise HTTPException(status_code=503, detail=ERROR_AUDIT_NOT_INITIALIZED)

    traces = []

    # Try to get from visibility service first
    try:
        traces = await _get_traces_from_visibility_service(visibility_service, limit)
    except Exception as e:
        logger.warning(
            f"Telemetry metric retrieval failed for reasoning traces from visibility service: {type(e).__name__}: {str(e)} - Returning default/empty value"
        )

    # Fallback to audit-based traces
    if not traces:
        try:
            traces = await _get_traces_from_audit_service(audit_service, start_time, end_time, limit)
        except Exception as e:
            logger.warning(
                f"Telemetry metric retrieval failed for reasoning traces from audit service: {type(e).__name__}: {str(e)} - Returning default/empty value"
            )

    response = TracesResponse(traces=traces, total=len(traces), has_more=len(traces) == limit)

    return SuccessResponse(
        data=response,
        metadata=ResponseMetadata(timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0),
    )


def _validate_audit_service(audit_service: Any) -> None:
    """Validate that audit service is available."""
    if not audit_service:
        raise HTTPException(status_code=503, detail=ERROR_AUDIT_NOT_INITIALIZED)


def _determine_log_level(action: str) -> str:
    """Determine log level from audit action."""
    action_lower = action.lower()
    if "critical" in action_lower or "fatal" in action_lower:
        return "CRITICAL"
    elif "error" in action_lower or "fail" in action_lower:
        return "ERROR"
    elif "warning" in action_lower or "warn" in action_lower:
        return "WARNING"
    elif "debug" in action_lower:
        return "DEBUG"
    return "INFO"


def _extract_service_name(actor: str) -> str:
    """Extract service name from actor string."""
    return actor.split(".")[0] if "." in actor else actor


def _should_include_log(
    log_level: str, log_service: str, level_filter: Optional[str], service_filter: Optional[str]
) -> bool:
    """Check if log entry should be included based on filters."""
    if level_filter and log_level != level_filter.upper():
        return False
    if service_filter and log_service.lower() != service_filter.lower():
        return False
    return True


def _build_log_entry(entry: Any, log_level: str, log_service: str) -> LogEntryResponse:
    """Build LogEntry from audit entry."""
    # AuditEntry.context is AuditEntryContext with .additional_data dict
    context_data = entry.context.additional_data or {}

    return LogEntryResponse(
        timestamp=entry.timestamp,
        level=log_level,
        service=log_service,
        message=f"{entry.action}: {context_data.get('description', '')}".strip(": "),
        context=LogContext(
            trace_id=entry.context.correlation_id,
            correlation_id=entry.context.correlation_id,
            user_id=entry.context.user_id,
            entity_id=context_data.get("entity_id"),
            error_details=context_data.get("error_details", {}) if "error" in log_level.lower() else None,
            metadata=context_data,
        ),
        trace_id=entry.context.correlation_id,
    )


async def _get_logs_from_audit_service(
    audit_service: Any,
    start_time: Optional[datetime],
    end_time: Optional[datetime],
    level: Optional[str],
    service: Optional[str],
    limit: int,
) -> List[LogEntryResponse]:
    """Get logs from audit service with filtering."""
    logs = []
    try:
        from ciris_engine.schemas.services.graph.audit import AuditQuery

        audit_query = AuditQuery(start_time=start_time, end_time=end_time, limit=limit * 2)  # Get extra for filtering
        entries = await audit_service.query_audit_trail(audit_query)

        for entry in entries:
            log_level = _determine_log_level(entry.action)
            log_service = _extract_service_name(entry.actor)

            if not _should_include_log(log_level, log_service, level, service):
                continue

            log = _build_log_entry(entry, log_level, log_service)
            logs.append(log)

            if len(logs) >= limit:
                break
    except Exception as e:
        logger.warning(f"Failed to get logs from audit service: {e}")

    return logs


async def _get_logs_from_file_reader(
    level: Optional[str],
    service: Optional[str],
    limit: int,
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> List[LogEntryResponse]:
    """Get logs from file reader if available."""
    try:
        from .telemetry_logs_reader import log_reader

        # The log_reader returns List[LogEntry] from telemetry_models, need to convert
        logs = log_reader.read_logs(
            level=level,
            service=service,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            include_incidents=True,
        )
        # Convert LogEntry to LogEntryResponse (they are the same structure now)
        return [LogEntryResponse(**log.model_dump()) for log in logs]
    except ImportError:
        logger.debug("Log reader not available, using audit entries only")
        return []
    except Exception as e:
        logger.warning(f"Failed to read log files: {e}, using audit entries only")
        return []


@router.get("/logs", response_model=SuccessResponse[LogsResponse])
async def get_system_logs(
    request: Request,
    auth: AuthContext = Depends(require_observer),
    start_time: Optional[datetime] = Query(None, description=DESC_START_TIME),
    end_time: Optional[datetime] = Query(None, description=DESC_END_TIME),
    level: Optional[str] = Query(None, description="Log level filter"),
    service: Optional[str] = Query(None, description="Service filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum logs to return"),
) -> SuccessResponse[LogsResponse]:
    """
    System logs.

    Get system logs from all services with filtering capabilities.
    """
    audit_service = request.app.state.audit_service
    _validate_audit_service(audit_service)

    # Get logs from audit service
    logs = await _get_logs_from_audit_service(audit_service, start_time, end_time, level, service, limit)

    # Add file logs if we haven't reached the limit
    if len(logs) < limit:
        file_logs = await _get_logs_from_file_reader(level, service, limit - len(logs), start_time, end_time)
        logs.extend(file_logs)

    response = LogsResponse(logs=logs[:limit], total=len(logs), has_more=len(logs) > limit)

    return SuccessResponse(
        data=response,
        metadata=ResponseMetadata(timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0),
    )


async def _query_metrics(telemetry_service: Any, query: TelemetryQuery) -> List[QueryResult]:
    """Query metrics data."""
    results: List[QueryResult] = []
    if not (telemetry_service and hasattr(telemetry_service, "query_metrics")):
        return results

    metric_names = query.filters.metric_names or []
    for metric_name in metric_names:
        data_points = await telemetry_service.query_metrics(
            metric_name=metric_name, start_time=query.start_time, end_time=query.end_time
        )
        if data_points:
            results.append(
                QueryResult(
                    id=f"metric_{metric_name}",
                    type="metric",
                    timestamp=datetime.now(timezone.utc),
                    data={
                        "metric_name": metric_name,
                        "data_points": data_points,
                        "count": len(data_points),
                    },
                )
            )
    return results


async def _query_traces(visibility_service: Any, query: TelemetryQuery) -> List[QueryResult]:
    """Query reasoning traces."""
    results: List[QueryResult] = []
    if not visibility_service:
        return results

    trace_limit = query.filters.limit or query.limit
    traces = []

    if hasattr(visibility_service, "query_traces"):
        traces = await visibility_service.query_traces(
            start_time=query.start_time, end_time=query.end_time, limit=trace_limit
        )

    for trace in traces:
        results.append(
            QueryResult(
                id=trace.trace_id,
                type="trace",
                timestamp=trace.start_time,
                data={
                    "trace_id": trace.trace_id,
                    "task_id": trace.task_id,
                    "duration_ms": trace.duration_ms,
                    "thought_count": trace.thought_count,
                },
            )
        )
    return results


def _should_include_log_entry(entry: Any, filters: Any) -> bool:
    """Check if log entry should be included based on filters."""
    if not filters:
        return True

    if filters.services and entry.actor not in filters.services:
        return False

    if filters.severity:
        # Infer level from action
        if "error" in entry.action.lower() and filters.severity.upper() != "ERROR":
            return False

    return True


async def _query_logs(audit_service: Any, query: TelemetryQuery) -> List[QueryResult]:
    """Query logs data."""
    results: List[QueryResult] = []
    if not audit_service:
        return results

    from ciris_engine.schemas.services.graph.audit import AuditQuery

    audit_query = AuditQuery(start_time=query.start_time, end_time=query.end_time, limit=query.limit)
    log_entries = await audit_service.query_audit_trail(audit_query)

    for entry in log_entries:
        if not _should_include_log_entry(entry, query.filters):
            continue

        results.append(
            QueryResult(
                id=f"log_{entry.timestamp.timestamp()}_{entry.actor}",
                type="log",
                timestamp=entry.timestamp,
                data={
                    "timestamp": entry.timestamp.isoformat(),
                    "service": entry.actor,
                    "action": entry.action,
                    "context": entry.context.model_dump() if hasattr(entry.context, "model_dump") else entry.context,
                },
            )
        )
    return results


async def _query_incidents(incident_service: Any, query: TelemetryQuery) -> List[QueryResult]:
    """Query incidents data."""
    results: List[QueryResult] = []
    if not incident_service:
        return results

    incidents = await incident_service.query_incidents(
        start_time=query.start_time,
        end_time=query.end_time,
        severity=query.filters.severity,
        status=getattr(query.filters, "status", None),
    )

    for incident in incidents:
        results.append(
            QueryResult(
                id=incident.id,
                type="incident",
                timestamp=getattr(incident, "created_at", incident.detected_at),
                data={
                    "incident_id": incident.id,
                    "severity": incident.severity,
                    "status": incident.status,
                    "description": incident.description,
                    "created_at": getattr(incident, "created_at", incident.detected_at).isoformat(),
                },
            )
        )
    return results


async def _query_insights(incident_service: Any, query: TelemetryQuery) -> List[QueryResult]:
    """Query adaptation insights."""
    results: List[QueryResult] = []
    if not (incident_service and hasattr(incident_service, "get_insights")):
        return results

    insights = await incident_service.get_insights(
        start_time=query.start_time, end_time=query.end_time, limit=query.limit
    )

    for insight in insights:
        results.append(
            QueryResult(
                id=insight.id,
                type="insight",
                timestamp=getattr(insight, "created_at", insight.analysis_timestamp),
                data={
                    "insight_id": insight.id,
                    "insight_type": insight.insight_type,
                    "summary": insight.summary,
                    "details": insight.details,
                    "created_at": getattr(insight, "created_at", insight.analysis_timestamp).isoformat(),
                },
            )
        )
    return results


def _apply_aggregations(
    results: List[QueryResult], aggregations: Optional[List[str]], query_type: str
) -> List[QueryResult]:
    """Apply aggregations to query results."""
    if not aggregations:
        return results

    for agg in aggregations:
        if agg == "count":
            # Return count as a QueryResult
            return [
                QueryResult(
                    id="aggregation_count",
                    type="aggregation",
                    timestamp=datetime.now(timezone.utc),
                    data={"aggregation": "count", "value": len(results)},
                )
            ]
        elif agg == "group_by_service" and query_type == "logs":
            # Group logs by service
            grouped: Dict[str, int] = defaultdict(int)
            for r in results:
                # Access service from the data field
                service_val = r.data.get("service", "unknown")
                service = str(service_val) if service_val is not None else "unknown"
                grouped[service] += 1

            # Convert grouped results to QueryResult objects
            return [
                QueryResult(
                    id=f"aggregation_service_{k}",
                    type="aggregation",
                    timestamp=datetime.now(timezone.utc),
                    data={"service": k, "count": v},
                )
                for k, v in grouped.items()
            ]
    return results


def _validate_query_services(
    telemetry_service: Any, visibility_service: Any, audit_service: Any, incident_service: Any
) -> None:
    """Validate that all required services are available for queries."""
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_NOT_INITIALIZED)
    if not visibility_service:
        raise HTTPException(status_code=503, detail="Critical system failure: Visibility service not initialized")
    if not audit_service:
        raise HTTPException(status_code=503, detail=ERROR_AUDIT_NOT_INITIALIZED)
    if not incident_service:
        raise HTTPException(status_code=503, detail="Critical system failure: Incident service not initialized")


async def _route_query_to_handler(
    query: TelemetryQuery, telemetry_service: Any, visibility_service: Any, audit_service: Any, incident_service: Any
) -> List[QueryResult]:
    """Route query to appropriate handler based on query type."""
    if query.query_type == "metrics":
        return await _query_metrics(telemetry_service, query)
    elif query.query_type == "traces":
        return await _query_traces(visibility_service, query)
    elif query.query_type == "logs":
        return await _query_logs(audit_service, query)
    elif query.query_type == "incidents":
        return await _query_incidents(incident_service, query)
    elif query.query_type == "insights":
        return await _query_insights(incident_service, query)
    return []


def _build_query_response(
    query: TelemetryQuery, results: List[QueryResult], execution_time_ms: float
) -> SuccessResponse[QueryResponse]:
    """Build the final query response."""
    response = QueryResponse(
        query_type=query.query_type,
        results=results[: query.limit],
        total=len(results),
        execution_time_ms=execution_time_ms,
    )

    return SuccessResponse(
        data=response,
        metadata=ResponseMetadata(timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0),
    )


@router.post("/query", response_model=SuccessResponse[QueryResponse])
async def query_telemetry(
    request: Request, query: TelemetryQuery, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[QueryResponse]:
    """
    Custom telemetry queries.

    Execute custom queries against telemetry data including metrics, traces, logs, incidents, and insights.
    Requires ADMIN role.
    """
    start_time = datetime.now(timezone.utc)

    # Get and validate services
    telemetry_service = request.app.state.telemetry_service
    visibility_service = request.app.state.visibility_service
    audit_service = request.app.state.audit_service
    incident_service = request.app.state.incident_management_service

    _validate_query_services(telemetry_service, visibility_service, audit_service, incident_service)

    try:
        # Route query to appropriate handler
        results = await _route_query_to_handler(
            query, telemetry_service, visibility_service, audit_service, incident_service
        )

        # Apply aggregations if specified
        results = _apply_aggregations(results, query.aggregations, query.query_type)

        # Calculate execution time and build response
        execution_time = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        return _build_query_response(query, results, execution_time)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{metric_name}", response_model=SuccessResponse[DetailedMetric])
async def get_detailed_metric(
    request: Request,
    metric_name: str,
    auth: AuthContext = Depends(require_observer),
    hours: int = Query(24, ge=1, le=168, description="Hours of history to include"),
) -> SuccessResponse[DetailedMetric]:
    """
    Get detailed information about a specific metric.

    Returns current value, trends, and historical data for the specified metric.
    """
    # Telemetry service MUST exist - if it doesn't, we have a critical failure
    telemetry_service = request.app.state.telemetry_service
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_NOT_INITIALIZED)

    try:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        # Get metric data
        data_points = []
        if hasattr(telemetry_service, "query_metrics"):
            data_points = await telemetry_service.query_metrics(
                metric_name=metric_name, start_time=start_time, end_time=now
            )

        if not data_points:
            raise HTTPException(status_code=404, detail=f"Metric '{metric_name}' not found")

        # Calculate statistics
        values = [float(dp.value) for dp in data_points]
        current_value = values[-1] if values else 0.0
        hourly_avg = sum(values[-60:]) / len(values[-60:]) if len(values) > 60 else sum(values) / len(values)
        daily_avg = sum(values) / len(values)

        # Determine trend
        trend = "stable"
        if len(values) > 10:
            recent = sum(values[-10:]) / 10
            older = sum(values[-20:-10]) / 10
            if recent > older * 1.1:
                trend = "up"
            elif recent < older * 0.9:
                trend = "down"

        # Determine unit
        unit = None
        if "tokens" in metric_name:
            unit = "tokens"
        elif "time" in metric_name or "latency" in metric_name:
            unit = "ms"
        elif "percent" in metric_name or "rate" in metric_name:
            unit = "%"
        elif "bytes" in metric_name or "memory" in metric_name:
            unit = "bytes"
        elif "count" in metric_name or "total" in metric_name:
            unit = "count"

        metric = DetailedMetric(
            name=metric_name,
            current_value=current_value,
            unit=unit,
            trend=trend,
            hourly_average=hourly_avg,
            daily_average=daily_avg,
            by_service=[],  # Could be populated if service tags are available
            recent_data=[
                MetricData(
                    timestamp=dp.timestamp,
                    value=float(dp.value),
                    tags=MetricTags(**dp.tags) if dp.tags else MetricTags(),
                )
                for dp in data_points[-100:]  # Last 100 data points
            ],
        )

        return SuccessResponse(
            data=metric,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        # Re-raise HTTPException as-is to preserve status code
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# All resource metric models are now in telemetry_models.py with proper type safety


# Helper functions moved to telemetry_helpers.py


@router.get("/unified", response_model=None)
async def get_unified_telemetry(
    request: Request,
    auth: AuthContext = Depends(require_observer),
    view: str = Query("summary", description="View type: summary|health|operational|detailed|performance|reliability"),
    category: Optional[str] = Query(
        None, description="Filter by category: buses|graph|infrastructure|governance|runtime|adapters|components|all"
    ),
    format: str = Query("json", description="Output format: json|prometheus|graphite"),
    live: bool = Query(False, description="Force live collection (bypass cache)"),
) -> JSONDict | Response:
    """
    Unified enterprise telemetry endpoint.

    This single endpoint replaces 78+ individual telemetry routes by intelligently
    aggregating metrics from all 22 required services using parallel collection.

    Features:
    - Parallel collection from all services (10x faster than sequential)
    - Smart caching with 30-second TTL
    - Multiple views for different stakeholders
    - System health and reliability scoring
    - Export formats for monitoring tools

    Examples:
    - /telemetry/unified?view=summary - Executive dashboard
    - /telemetry/unified?view=health - Quick health check
    - /telemetry/unified?view=operational&live=true - Live ops data
    - /telemetry/unified?view=reliability - System reliability metrics
    - /telemetry/unified?category=buses - Just bus metrics
    - /telemetry/unified?format=prometheus - Prometheus export
    """
    try:
        # Get the telemetry service
        telemetry_service = getattr(request.app.state, "telemetry_service", None)
        if not telemetry_service:
            raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_SERVICE_NOT_AVAILABLE)

        # Get telemetry data - NO FALLBACKS, fail FAST and LOUD per CIRIS philosophy
        if not hasattr(telemetry_service, "get_aggregated_telemetry"):
            raise HTTPException(
                status_code=503,
                detail="CRITICAL: Telemetry service does not have get_aggregated_telemetry method - NO FALLBACKS!",
            )
        result = await get_telemetry_from_service(telemetry_service, view, category, format, live)

        # Handle export formats
        if format == "prometheus":
            content = convert_to_prometheus(result)
            return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")
        elif format == "graphite":
            content = convert_to_graphite(result)
            return Response(content=content, media_type="text/plain; charset=utf-8")

        return result

    except HTTPException:
        # Re-raise HTTPException as-is to preserve status code
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources/history", response_model=SuccessResponse)
async def get_resource_history(
    request: Request,
    auth: AuthContext = Depends(require_observer),
    hours: int = Query(24, ge=1, le=168, description="Hours of history"),
) -> SuccessResponse[ResourceHistoryResponse]:
    """
    Get historical resource usage data.

    Returns time-series data for resource usage over the specified period.
    """
    # Telemetry service MUST exist - if it doesn't, we have a critical failure
    telemetry_service = request.app.state.telemetry_service
    if not telemetry_service:
        raise HTTPException(status_code=503, detail=ERROR_TELEMETRY_NOT_INITIALIZED)

    try:
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        # Use helper classes for clean separation of concerns
        collector = ResourceMetricsCollector()
        extractor = MetricValueExtractor()
        builder = ResourceMetricBuilder()

        # Fetch all metrics concurrently
        cpu_data, memory_data, disk_data = await collector.fetch_all_resource_metrics(
            telemetry_service, start_time, now
        )

        # Extract values for statistics
        cpu_values, memory_values, disk_values = extractor.extract_all_values(cpu_data, memory_data, disk_data)

        # Build data points
        default_timestamp = now.isoformat()
        point_builder = ResourceDataPointBuilder()
        cpu_points, memory_points, disk_points = point_builder.build_all_data_points(
            cpu_data, memory_data, disk_data, default_timestamp
        )

        # Build complete metrics with stats
        cpu_metric, memory_metric, disk_metric = builder.build_all_metrics(
            cpu_points, cpu_values, memory_points, memory_values, disk_points, disk_values
        )

        # Create properly typed response using Pydantic models
        response = ResourceHistoryResponse(
            period=TimePeriod(start=start_time.isoformat(), end=now.isoformat(), hours=hours),
            cpu=cpu_metric,
            memory=memory_metric,
            disk=disk_metric,
        )

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        # Re-raise HTTPException as-is to preserve status code
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
