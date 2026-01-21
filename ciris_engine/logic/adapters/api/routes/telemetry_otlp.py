"""
OpenTelemetry Protocol (OTLP) JSON converter for CIRIS telemetry.

Converts CIRIS telemetry data to OTLP JSON format for export to
OpenTelemetry collectors and backends. Supports all three signals:
- Metrics
- Traces
- Logs

SERIALIZATION BOUNDARY: This module uses JSONDict appropriately as it converts
between internal CIRIS telemetry formats and the external OTLP JSON protocol.
The input is untyped telemetry data from various sources, and the output must
conform to the OTLP JSON specification (https://opentelemetry.io/docs/specs/otlp/).
"""

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union, cast

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_int, get_str, get_str_optional
from ciris_engine.schemas.types import JSONDict

# OTLP attribute key constants
SERVICE_NAME_KEY = "service.name"
SERVICE_NAMESPACE_KEY = "service.namespace"
DEPLOYMENT_ENVIRONMENT_KEY = "deployment.environment"

# OTLP schema URL
OTLP_SCHEMA_URL = "https://opentelemetry.io/schemas/1.7.0"


def safe_telemetry_get(data: JSONDict, key: str, default: Any = None) -> Any:
    """Safely extract value from telemetry data with type checking."""
    return data.get(key, default) if isinstance(data, dict) else default


def create_resource_attributes(service_name: str, service_version: str, telemetry_data: JSONDict) -> List[Any]:
    """Create standard resource attributes for OTLP format."""
    attributes: List[Any] = [
        {"key": SERVICE_NAME_KEY, "value": {"stringValue": service_name}},
        {"key": "service.version", "value": {"stringValue": service_version}},
        {"key": SERVICE_NAMESPACE_KEY, "value": {"stringValue": "ciris"}},
        {"key": "telemetry.sdk.name", "value": {"stringValue": "ciris-telemetry"}},
        {"key": "telemetry.sdk.version", "value": {"stringValue": CIRIS_VERSION}},
        {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
    ]

    # Add deployment environment if available
    environment = safe_telemetry_get(telemetry_data, "environment")
    if environment:
        attributes.append({"key": DEPLOYMENT_ENVIRONMENT_KEY, "value": {"stringValue": environment}})

    return attributes


def add_system_metrics(telemetry_data: JSONDict, current_time_ns: int) -> List[JSONDict]:
    """Extract and create system-level metrics from telemetry data."""
    metrics = []

    if not isinstance(telemetry_data, dict):
        return metrics

    # System health status
    if "system_healthy" in telemetry_data:
        metrics.append(
            _create_gauge_metric(
                "system.healthy",
                "System health status",
                "1",
                1.0 if telemetry_data["system_healthy"] else 0.0,
                current_time_ns,
            )
        )

    # Services online count
    services_online = safe_telemetry_get(telemetry_data, "services_online")
    if services_online is not None:
        metrics.append(
            _create_gauge_metric(
                "services.online",
                "Number of services online",
                "1",
                float(services_online),
                current_time_ns,
            )
        )

    # Total services count
    services_total = safe_telemetry_get(telemetry_data, "services_total")
    if services_total is not None:
        metrics.append(
            _create_gauge_metric(
                "services.total",
                "Total number of services",
                "1",
                float(services_total),
                current_time_ns,
            )
        )

    # Error rate
    error_rate = safe_telemetry_get(telemetry_data, "overall_error_rate")
    if error_rate is not None:
        metrics.append(
            _create_gauge_metric(
                "system.error_rate",
                "Overall system error rate",
                "1",
                error_rate,
                current_time_ns,
            )
        )

    # Uptime
    uptime_seconds = safe_telemetry_get(telemetry_data, "overall_uptime_seconds")
    if uptime_seconds is not None:
        metrics.append(
            _create_counter_metric(
                "system.uptime",
                "System uptime in seconds",
                "s",
                uptime_seconds,
                current_time_ns,
            )
        )

    # Total errors
    total_errors = safe_telemetry_get(telemetry_data, "total_errors")
    if total_errors is not None:
        metrics.append(
            _create_counter_metric(
                "errors.total",
                "Total number of errors",
                "1",
                float(total_errors),
                current_time_ns,
            )
        )

    # Total requests
    total_requests = safe_telemetry_get(telemetry_data, "total_requests")
    if total_requests is not None:
        metrics.append(
            _create_counter_metric(
                "requests.total",
                "Total number of requests",
                "1",
                float(total_requests),
                current_time_ns,
            )
        )

    return metrics


def _add_service_gauge_metric(
    metrics: List[JSONDict],
    service_data: Any,
    field_name: str,
    metric_name: str,
    description: str,
    unit: str,
    current_time_ns: int,
    service_attrs: List[Any],
    transform_value: Any = None,
) -> None:
    """Helper to add a gauge metric for a service field."""
    if hasattr(service_data, field_name):
        value = getattr(service_data, field_name)
        if value is not None:
            if transform_value:
                value = transform_value(value)
            metrics.append(
                _create_gauge_metric(metric_name, description, unit, value, current_time_ns, attributes=service_attrs)
            )


def _add_service_counter_metric(
    metrics: List[JSONDict],
    service_data: Any,
    field_name: str,
    metric_name: str,
    description: str,
    unit: str,
    current_time_ns: int,
    service_attrs: List[Any],
    safe_convert: bool = False,
) -> None:
    """Helper to add a counter metric for a service field."""
    if hasattr(service_data, field_name):
        value = getattr(service_data, field_name)
        if value is not None:
            if safe_convert:
                try:
                    value = float(value or 0)
                    metrics.append(
                        _create_counter_metric(
                            metric_name, description, unit, value, current_time_ns, attributes=service_attrs
                        )
                    )
                except (TypeError, ValueError):
                    pass  # Skip invalid values
            else:
                metrics.append(
                    _create_counter_metric(
                        metric_name, description, unit, value, current_time_ns, attributes=service_attrs
                    )
                )


def add_service_metrics(services_data: JSONDict, current_time_ns: int) -> List[JSONDict]:
    """Extract and create service-level metrics from services data."""
    metrics: List[JSONDict] = []

    if not isinstance(services_data, dict):
        return metrics

    for service_name, service_data in services_data.items():
        service_attrs: List[Any] = [{"key": "service", "value": {"stringValue": service_name}}]

        # Health status
        _add_service_gauge_metric(
            metrics,
            service_data,
            "healthy",
            "service.healthy",
            "Service health status",
            "1",
            current_time_ns,
            service_attrs,
            transform_value=lambda x: 1.0 if x else 0.0,
        )

        # Uptime
        _add_service_counter_metric(
            metrics,
            service_data,
            "uptime_seconds",
            "service.uptime",
            "Service uptime in seconds",
            "s",
            current_time_ns,
            service_attrs,
        )

        # Error count
        _add_service_counter_metric(
            metrics,
            service_data,
            "error_count",
            "service.errors",
            "Service error count",
            "1",
            current_time_ns,
            service_attrs,
            safe_convert=True,
        )

        # Requests handled
        _add_service_counter_metric(
            metrics,
            service_data,
            "requests_handled",
            "service.requests",
            "Service requests handled",
            "1",
            current_time_ns,
            service_attrs,
            safe_convert=True,
        )

        # Error rate
        _add_service_gauge_metric(
            metrics,
            service_data,
            "error_rate",
            "service.error_rate",
            "Service error rate",
            "1",
            current_time_ns,
            service_attrs,
        )

        # Memory usage
        _add_service_gauge_metric(
            metrics,
            service_data,
            "memory_mb",
            "service.memory.usage",
            "Service memory usage",
            "MB",
            current_time_ns,
            service_attrs,
        )

    return metrics


def add_covenant_metrics(covenant_data: JSONDict, current_time_ns: int) -> List[JSONDict]:
    """Extract and create covenant-related metrics from covenant data."""
    metrics = []

    if not isinstance(covenant_data, dict):
        return metrics

    # Wise Authority deferrals
    deferrals = safe_telemetry_get(covenant_data, "wise_authority_deferrals")
    if deferrals is not None:
        metrics.append(
            _create_counter_metric(
                "covenant.wise_authority.deferrals",
                "Number of decisions deferred to Wise Authority",
                "1",
                float(deferrals),
                current_time_ns,
            )
        )

    # Filter matches
    filter_matches = safe_telemetry_get(covenant_data, "filter_matches")
    if filter_matches is not None:
        metrics.append(
            _create_counter_metric(
                "covenant.filter.matches",
                "Number of safety filter matches",
                "1",
                float(filter_matches),
                current_time_ns,
            )
        )

    # Thoughts processed
    thoughts_processed = safe_telemetry_get(covenant_data, "thoughts_processed")
    if thoughts_processed is not None:
        metrics.append(
            _create_counter_metric(
                "covenant.thoughts.processed",
                "Number of thoughts processed",
                "1",
                float(thoughts_processed),
                current_time_ns,
            )
        )

    # Self-observation insights
    insights = safe_telemetry_get(covenant_data, "self_observation_insights")
    if insights is not None:
        metrics.append(
            _create_counter_metric(
                "covenant.insights.generated",
                "Number of self-observation insights generated",
                "1",
                float(insights),
                current_time_ns,
            )
        )

    return metrics


def convert_to_otlp_json(
    telemetry_data: JSONDict,
    service_name: str = "ciris",
    service_version: str = CIRIS_VERSION,
    scope_name: str = "ciris.telemetry",
    scope_version: str = "1.0.0",
) -> JSONDict:
    """
    Convert CIRIS telemetry data to OTLP JSON format.

    Args:
        telemetry_data: Raw telemetry data from CIRIS services
        service_name: Name of the service (default: "ciris")
        service_version: Version of the service
        scope_name: Instrumentation scope name
        scope_version: Instrumentation scope version

    Returns:
        OTLP JSON formatted metrics data
    """
    # Get current time in nanoseconds
    current_time_ns = int(time.time() * 1e9)

    # Build resource attributes using helper
    resource_attributes = create_resource_attributes(service_name, service_version, telemetry_data)

    # Build metrics array using helper functions
    metrics = []

    # System-level metrics
    metrics.extend(add_system_metrics(telemetry_data, current_time_ns))

    # Service-level metrics
    services_data = safe_telemetry_get(telemetry_data, "services")
    if services_data:
        metrics.extend(add_service_metrics(services_data, current_time_ns))

    # Covenant metrics if present
    covenant_data = safe_telemetry_get(telemetry_data, "covenant_metrics")
    if covenant_data:
        metrics.extend(add_covenant_metrics(covenant_data, current_time_ns))

    # Build the OTLP JSON structure
    otlp_json: JSONDict = {
        "resourceMetrics": [
            {
                "resource": {"attributes": resource_attributes},
                "scopeMetrics": [
                    {
                        "scope": {"name": scope_name, "version": scope_version, "attributes": []},
                        "metrics": metrics,
                        "schemaUrl": OTLP_SCHEMA_URL,
                    }
                ],
                "schemaUrl": OTLP_SCHEMA_URL,
            }
        ]
    }

    return otlp_json


def _create_gauge_metric(
    name: str,
    description: str,
    unit: str,
    value: float,
    time_ns: int,
    attributes: Optional[List[Any]] = None,
) -> JSONDict:
    """Create a gauge metric in OTLP format."""
    data_point = {"asDouble": value, "timeUnixNano": str(time_ns)}

    if attributes:
        data_point["attributes"] = attributes

    return {"name": name, "description": description, "unit": unit, "gauge": {"dataPoints": [data_point]}}


def _create_counter_metric(
    name: str,
    description: str,
    unit: str,
    value: float,
    time_ns: int,
    attributes: Optional[List[Any]] = None,
    start_time_ns: Optional[int] = None,
) -> JSONDict:
    """Create a counter/sum metric in OTLP format."""
    # Use provided start time or assume counter started 1 hour ago
    if start_time_ns is None:
        start_time_ns = int(time_ns - (3600 * 1e9))  # 1 hour ago, converted to int

    data_point = {"asDouble": value, "startTimeUnixNano": str(start_time_ns), "timeUnixNano": str(time_ns)}

    if attributes:
        data_point["attributes"] = attributes

    return {
        "name": name,
        "description": description,
        "unit": unit,
        "sum": {"aggregationTemporality": 2, "isMonotonic": True, "dataPoints": [data_point]},  # CUMULATIVE
    }


def _create_histogram_metric(
    name: str,
    description: str,
    unit: str,
    count: int,
    sum_value: float,
    bucket_counts: List[int],
    explicit_bounds: List[float],
    time_ns: int,
    attributes: Optional[List[Any]] = None,
    start_time_ns: Optional[int] = None,
) -> JSONDict:
    """Create a histogram metric in OTLP format."""
    if start_time_ns is None:
        start_time_ns = int(time_ns - (3600 * 1e9))  # 1 hour ago, converted to int

    data_point = {
        "startTimeUnixNano": str(start_time_ns),
        "timeUnixNano": str(time_ns),
        "count": count,
        "sum": sum_value,
        "bucketCounts": bucket_counts,
        "explicitBounds": explicit_bounds,
    }

    if attributes:
        data_point["attributes"] = attributes

    return {
        "name": name,
        "description": description,
        "unit": unit,
        "histogram": {"aggregationTemporality": 2, "dataPoints": [data_point]},  # CUMULATIVE
    }


# Span kind mapping for OTLP
SPAN_KIND_MAP = {"internal": 1, "server": 2, "client": 3, "producer": 4, "consumer": 5}


def _normalize_trace_id(trace_id_raw: Optional[str], trace: JSONDict) -> str:
    """Normalize a trace ID to 32-char hex OTLP format."""
    if trace_id_raw:
        return trace_id_raw.replace("-", "")[:32].upper().ljust(32, "0")
    return hashlib.sha256(f"{trace.get('trace_id', '')}_{trace.get('timestamp', '')}".encode()).hexdigest()[:32].upper()


def _normalize_span_id(span_id_raw: Optional[str], trace_id: str, operation: str) -> str:
    """Normalize a span ID to 16-char hex OTLP format."""
    if span_id_raw:
        return span_id_raw.replace("-", "")[:16].upper().ljust(16, "0")
    return hashlib.sha256(f"{trace_id}_{operation}".encode()).hexdigest()[:16].upper()


def _parse_timestamp_to_ns(timestamp_str: Optional[str]) -> int:
    """Parse timestamp string to nanoseconds, defaulting to current time."""
    if timestamp_str:
        try:
            ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            return int(ts.timestamp() * 1e9)
        except ValueError:
            pass
    return int(time.time() * 1e9)


def _build_span_attributes(trace: JSONDict) -> List[Any]:
    """Build span attributes from trace data."""
    span_attrs: List[Any] = []

    # Add trace attributes
    if "operation" in trace:
        span_attrs.append({"key": "operation.name", "value": {"stringValue": str(trace["operation"])}})

    if "service" in trace:
        span_attrs.append({"key": SERVICE_NAME_KEY, "value": {"stringValue": str(trace["service"])}})

    if "handler" in trace:
        span_attrs.append({"key": "handler.name", "value": {"stringValue": str(trace["handler"])}})

    if "status" in trace:
        span_attrs.append({"key": "span.status", "value": {"stringValue": str(trace["status"])}})

    # Add task/thought linkage - CRITICAL for CIRIS tracing
    if "task_id" in trace and trace["task_id"]:
        span_attrs.append({"key": "ciris.task_id", "value": {"stringValue": str(trace["task_id"])}})

    if "thought_id" in trace and trace["thought_id"]:
        span_attrs.append({"key": "ciris.thought_id", "value": {"stringValue": str(trace["thought_id"])}})

    # Add success/error information
    if "success" in trace:
        span_attrs.append({"key": "span.success", "value": {"boolValue": bool(trace["success"])}})

    if "error" in trace and trace["error"]:
        span_attrs.append({"key": "error.message", "value": {"stringValue": str(trace["error"])}})

    # Enhanced: Use rich span attributes if available from step streaming
    if "span_attributes" in trace and isinstance(trace["span_attributes"], list):
        span_attrs.extend(trace["span_attributes"])

    return span_attrs


def _get_span_kind(trace: JSONDict, trace_context: JSONDict) -> int:
    """Determine span kind from trace or context."""
    span_kind_str = get_str_optional(trace, "span_kind")
    if span_kind_str:
        return SPAN_KIND_MAP.get(span_kind_str, 2)  # Default to SERVER

    span_kind_ctx_str = get_str_optional(trace_context, "span_kind")
    if span_kind_ctx_str:
        return SPAN_KIND_MAP.get(span_kind_ctx_str, 1)  # Default to internal for H3ERE steps

    return 2  # SERVER by default


def _build_thought_events(thoughts: List[Any], time_ns: int) -> List[JSONDict]:
    """Build OTLP events from thought list."""
    events: List[JSONDict] = []
    for idx, thought in enumerate(thoughts):
        if isinstance(thought, dict):
            content = get_str(thought, "content", "")
        else:
            content = ""
        events.append(
            {
                "name": f"thought.step.{idx}",
                "timeUnixNano": str(time_ns + idx * 1000000),  # 1ms between thoughts
                "attributes": [{"key": "thought.content", "value": {"stringValue": content}}],
            }
        )
    return events


def _build_span_status(trace: JSONDict) -> Optional[JSONDict]:
    """Build span status from trace error/success info."""
    error_value = trace.get("error")
    if error_value and isinstance(error_value, str):
        return {"code": 2, "message": error_value}  # ERROR
    if trace.get("success") is False:
        return {"code": 2, "message": "Operation failed"}  # ERROR
    return None


class _SpanContext:
    """Mutable container for span context during conversion."""

    def __init__(
        self, trace_id: str, span_id: str, parent_span_id: Optional[str], span_name: str, time_ns: int, end_time_ns: int
    ) -> None:
        self.trace_id = trace_id
        self.span_id = span_id
        self.parent_span_id = parent_span_id
        self.span_name = span_name
        self.time_ns = time_ns
        self.end_time_ns = end_time_ns


def _apply_trace_context_overrides(ctx: _SpanContext, trace_context: JSONDict) -> None:
    """Apply trace context overrides from step streaming."""
    trace_id_ctx = get_str_optional(trace_context, "trace_id")
    if trace_id_ctx:
        ctx.trace_id = trace_id_ctx
    span_id_ctx = get_str_optional(trace_context, "span_id")
    if span_id_ctx:
        ctx.span_id = span_id_ctx
    parent_span_id_ctx = get_str_optional(trace_context, "parent_span_id")
    if parent_span_id_ctx:
        ctx.parent_span_id = parent_span_id_ctx
    span_name_ctx = get_str_optional(trace_context, "span_name")
    if span_name_ctx:
        ctx.span_name = span_name_ctx
    start_time_ns_ctx = get_int(trace_context, "start_time_ns", 0)
    if start_time_ns_ctx:
        ctx.time_ns = start_time_ns_ctx
    end_time_ns_ctx = get_int(trace_context, "end_time_ns", 0)
    if end_time_ns_ctx:
        ctx.end_time_ns = end_time_ns_ctx


def _convert_single_trace_to_span(trace: JSONDict) -> JSONDict:
    """Convert a single trace entry to an OTLP span."""
    # Normalize IDs
    trace_id = _normalize_trace_id(get_str_optional(trace, "trace_id"), trace)
    span_id = _normalize_span_id(get_str_optional(trace, "span_id"), trace_id, trace.get("operation", "unknown"))

    # Handle parent span ID
    parent_span_id = None
    parent_span_id_raw = get_str_optional(trace, "parent_span_id")
    if parent_span_id_raw:
        parent_span_id = parent_span_id_raw.replace("-", "")[:16].upper().ljust(16, "0")

    # Parse timestamp and calculate end time
    time_ns = _parse_timestamp_to_ns(get_str_optional(trace, "timestamp"))
    duration_ms = get_float(trace, "duration_ms", 1.0)
    end_time_ns = time_ns + int(duration_ms * 1e6)

    # Get span name
    span_name_opt = get_str_optional(trace, "span_name") or get_str_optional(trace, "operation")
    span_name = span_name_opt if span_name_opt else "unknown_operation"

    # Create mutable context and apply trace context overrides
    ctx = _SpanContext(trace_id, span_id, parent_span_id, span_name, time_ns, end_time_ns)
    trace_context = get_dict(trace, "trace_context", {})
    if trace_context:
        _apply_trace_context_overrides(ctx, trace_context)

    # Build span attributes and kind
    span_attrs = _build_span_attributes(trace)
    span_kind = _get_span_kind(trace, trace_context)

    # Build the span
    span: JSONDict = {
        "traceId": ctx.trace_id,
        "spanId": ctx.span_id,
        "name": ctx.span_name,
        "startTimeUnixNano": str(ctx.time_ns),
        "endTimeUnixNano": str(ctx.end_time_ns),
        "kind": span_kind,
        "attributes": span_attrs,
    }

    # Add parent span ID if available
    if ctx.parent_span_id:
        span["parentSpanId"] = ctx.parent_span_id

    # Add thoughts as events if present
    thoughts_value = trace.get("thoughts")
    if thoughts_value and isinstance(thoughts_value, list):
        span["events"] = _build_thought_events(thoughts_value, ctx.time_ns)

    # Add status if there was an error
    status = _build_span_status(trace)
    if status:
        span["status"] = status

    return span


def convert_traces_to_otlp_json(
    traces_data: List[JSONDict],
    service_name: str = "ciris",
    service_version: str = CIRIS_VERSION,
    scope_name: str = "ciris.traces",
    scope_version: str = "1.0.0",
) -> JSONDict:
    """
    Convert CIRIS traces to OTLP JSON format.

    Args:
        traces_data: List of trace data from CIRIS
        service_name: Name of the service
        service_version: Version of the service
        scope_name: Instrumentation scope name
        scope_version: Instrumentation scope version

    Returns:
        OTLP JSON formatted trace data
    """
    # Build resource attributes (without namespace/environment for traces)
    base_resource_attrs = create_resource_attributes(service_name, service_version, {})
    resource_attributes = [
        attr for attr in base_resource_attrs if attr["key"] not in [SERVICE_NAMESPACE_KEY, DEPLOYMENT_ENVIRONMENT_KEY]
    ]

    # Convert each trace to a span using the helper function
    spans = [_convert_single_trace_to_span(trace) for trace in traces_data]

    return {
        "resourceSpans": [
            {
                "resource": {"attributes": resource_attributes},
                "scopeSpans": [
                    {
                        "scope": {"name": scope_name, "version": scope_version},
                        "spans": spans,
                        "schemaUrl": OTLP_SCHEMA_URL,
                    }
                ],
                "schemaUrl": OTLP_SCHEMA_URL,
            }
        ]
    }


# Severity level mapping for OTLP logs
SEVERITY_MAP = {
    "DEBUG": 5,
    "INFO": 9,
    "INFORMATION": 9,
    "WARNING": 13,
    "WARN": 13,
    "ERROR": 17,
    "CRITICAL": 21,
    "FATAL": 21,
}


def _build_log_attributes(log: JSONDict) -> List[Any]:
    """Build OTLP log attributes from log entry."""
    log_attrs: List[Any] = []

    if "service" in log:
        log_attrs.append({"key": SERVICE_NAME_KEY, "value": {"stringValue": str(log["service"])}})

    if "component" in log:
        log_attrs.append({"key": "component", "value": {"stringValue": str(log["component"])}})

    if "action" in log:
        log_attrs.append({"key": "action", "value": {"stringValue": str(log["action"])}})

    if "user_id" in log:
        log_attrs.append({"key": "user.id", "value": {"stringValue": str(log["user_id"])}})

    if "correlation_id" in log:
        log_attrs.append({"key": "correlation.id", "value": {"stringValue": str(log["correlation_id"])}})

    return log_attrs


def _convert_single_log_to_record(log: JSONDict) -> JSONDict:
    """Convert a single log entry to an OTLP log record."""
    # Parse timestamp
    time_ns = _parse_timestamp_to_ns(get_str_optional(log, "timestamp"))

    # Get severity
    level_str = get_str(log, "level", "INFO")
    severity_text = level_str.upper()
    severity_number = SEVERITY_MAP.get(severity_text, 9)

    # Build log record
    log_record: JSONDict = {
        "timeUnixNano": str(time_ns),
        "observedTimeUnixNano": str(time_ns),
        "severityNumber": severity_number,
        "severityText": severity_text,
        "body": {"stringValue": log.get("message", "") or log.get("description", "")},
        "attributes": _build_log_attributes(log),
    }

    # Add trace context if available
    if "trace_id" in log:
        log_record["traceId"] = hashlib.sha256(str(log["trace_id"]).encode()).hexdigest()[:32].upper()

    if "span_id" in log:
        log_record["spanId"] = hashlib.sha256(str(log["span_id"]).encode()).hexdigest()[:16].upper()

    return log_record


def convert_logs_to_otlp_json(
    logs_data: List[JSONDict],
    service_name: str = "ciris",
    service_version: str = CIRIS_VERSION,
    scope_name: str = "ciris.logs",
    scope_version: str = "1.0.0",
) -> JSONDict:
    """
    Convert CIRIS logs to OTLP JSON format.

    Args:
        logs_data: List of log entries from CIRIS
        service_name: Name of the service
        service_version: Version of the service
        scope_name: Instrumentation scope name
        scope_version: Instrumentation scope version

    Returns:
        OTLP JSON formatted log data
    """
    # Build resource attributes (without namespace/environment for logs)
    base_resource_attrs = create_resource_attributes(service_name, service_version, {})
    resource_attributes = [
        attr for attr in base_resource_attrs if attr["key"] not in [SERVICE_NAMESPACE_KEY, DEPLOYMENT_ENVIRONMENT_KEY]
    ]

    # Convert each log to a record using the helper function
    log_records = [_convert_single_log_to_record(log) for log in logs_data]

    return {
        "resourceLogs": [
            {
                "resource": {"attributes": resource_attributes},
                "scopeLogs": [
                    {
                        "scope": {
                            "name": scope_name,
                            "version": scope_version,
                        },
                        "logRecords": log_records,
                        "schemaUrl": OTLP_SCHEMA_URL,
                    }
                ],
                "schemaUrl": OTLP_SCHEMA_URL,
            }
        ]
    }


# Valid metric data type keys for OTLP
VALID_METRIC_DATA_TYPES = frozenset(["gauge", "sum", "histogram", "exponentialHistogram", "summary"])


def _validate_resource_attributes(resource: Any) -> bool:
    """Validate resource attributes structure."""
    if "attributes" in resource:
        if not isinstance(resource["attributes"], list):
            return False
    return True


def _validate_metric(metric: Any) -> bool:
    """Validate a single OTLP metric has required fields."""
    if "name" not in metric:
        return False
    return any(key in metric for key in VALID_METRIC_DATA_TYPES)


def _validate_scope_metric(scope_metric: Any) -> bool:
    """Validate a scope metric structure and its metrics."""
    if "metrics" not in scope_metric:
        return False
    if not isinstance(scope_metric["metrics"], list):
        return False
    return all(_validate_metric(metric) for metric in scope_metric["metrics"])


def _validate_resource_metric(resource_metric: Any) -> bool:
    """Validate a resource metric structure."""
    # Check resource attributes if present
    if "resource" in resource_metric:
        if not _validate_resource_attributes(resource_metric["resource"]):
            return False

    # Check scope metrics
    if "scopeMetrics" not in resource_metric:
        return False
    if not isinstance(resource_metric["scopeMetrics"], list):
        return False

    return all(_validate_scope_metric(sm) for sm in resource_metric["scopeMetrics"])


def validate_otlp_json(otlp_data: JSONDict) -> bool:
    """
    Validate that the OTLP JSON structure is correct.

    Args:
        otlp_data: The OTLP JSON data to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        if "resourceMetrics" not in otlp_data:
            return False
        if not isinstance(otlp_data["resourceMetrics"], list):
            return False
        return all(_validate_resource_metric(rm) for rm in otlp_data["resourceMetrics"])
    except (KeyError, TypeError, AttributeError):
        return False
