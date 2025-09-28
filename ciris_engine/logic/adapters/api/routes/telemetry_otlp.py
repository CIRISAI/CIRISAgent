"""
OpenTelemetry Protocol (OTLP) JSON converter for CIRIS telemetry.

Converts CIRIS telemetry data to OTLP JSON format for export to
OpenTelemetry collectors and backends. Supports all three signals:
- Metrics
- Traces
- Logs
"""

import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from ciris_engine.constants import CIRIS_VERSION


def safe_telemetry_get(data: Dict[str, Any], key: str, default=None):
    """Safely extract value from telemetry data with type checking."""
    return data.get(key, default) if isinstance(data, dict) else default


def create_resource_attributes(
    service_name: str, service_version: str, telemetry_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Create standard resource attributes for OTLP format."""
    attributes = [
        {"key": "service.name", "value": {"stringValue": service_name}},
        {"key": "service.version", "value": {"stringValue": service_version}},
        {"key": "service.namespace", "value": {"stringValue": "ciris"}},
        {"key": "telemetry.sdk.name", "value": {"stringValue": "ciris-telemetry"}},
        {"key": "telemetry.sdk.version", "value": {"stringValue": CIRIS_VERSION}},
        {"key": "telemetry.sdk.language", "value": {"stringValue": "python"}},
    ]

    # Add deployment environment if available
    environment = safe_telemetry_get(telemetry_data, "environment")
    if environment:
        attributes.append({"key": "deployment.environment", "value": {"stringValue": environment}})

    return attributes


def add_system_metrics(telemetry_data: Dict[str, Any], current_time_ns: int) -> List[Dict[str, Any]]:
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


def add_service_metrics(services_data: Dict[str, Any], current_time_ns: int) -> List[Dict[str, Any]]:
    """Extract and create service-level metrics from services data."""
    metrics = []

    if not isinstance(services_data, dict):
        return metrics

    for service_name, service_data in services_data.items():
        service_attrs = [{"key": "service", "value": {"stringValue": service_name}}]

        # Health status
        if hasattr(service_data, "healthy"):
            metrics.append(
                _create_gauge_metric(
                    "service.healthy",
                    "Service health status",
                    "1",
                    1.0 if service_data.healthy else 0.0,
                    current_time_ns,
                    attributes=service_attrs,
                )
            )

        # Uptime
        if hasattr(service_data, "uptime_seconds") and service_data.uptime_seconds:
            metrics.append(
                _create_counter_metric(
                    "service.uptime",
                    "Service uptime in seconds",
                    "s",
                    service_data.uptime_seconds,
                    current_time_ns,
                    attributes=service_attrs,
                )
            )

        # Error count
        if hasattr(service_data, "error_count") and service_data.error_count is not None:
            try:
                metrics.append(
                    _create_counter_metric(
                        "service.errors",
                        "Service error count",
                        "1",
                        float(service_data.error_count),
                        current_time_ns,
                        attributes=service_attrs,
                    )
                )
            except (TypeError, ValueError):
                pass  # Skip invalid error_count values

        # Requests handled
        if hasattr(service_data, "requests_handled") and service_data.requests_handled is not None:
            try:
                metrics.append(
                    _create_counter_metric(
                        "service.requests",
                        "Service requests handled",
                        "1",
                        float(service_data.requests_handled or 0),
                        current_time_ns,
                        attributes=service_attrs,
                    )
                )
            except (TypeError, ValueError):
                pass  # Skip invalid requests_handled values

        # Error rate
        if hasattr(service_data, "error_rate") and service_data.error_rate is not None:
            metrics.append(
                _create_gauge_metric(
                    "service.error_rate",
                    "Service error rate",
                    "1",
                    service_data.error_rate,
                    current_time_ns,
                    attributes=service_attrs,
                )
            )

        # Memory usage
        if hasattr(service_data, "memory_mb") and service_data.memory_mb:
            metrics.append(
                _create_gauge_metric(
                    "service.memory.usage",
                    "Service memory usage",
                    "MB",
                    service_data.memory_mb,
                    current_time_ns,
                    attributes=service_attrs,
                )
            )

    return metrics


def add_covenant_metrics(covenant_data: Dict[str, Any], current_time_ns: int) -> List[Dict[str, Any]]:
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
    telemetry_data: Dict[str, Any],
    service_name: str = "ciris",
    service_version: str = CIRIS_VERSION,
    scope_name: str = "ciris.telemetry",
    scope_version: str = "1.0.0",
) -> Dict[str, Any]:
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
    otlp_json = {
        "resourceMetrics": [
            {
                "resource": {"attributes": resource_attributes},
                "scopeMetrics": [
                    {
                        "scope": {"name": scope_name, "version": scope_version, "attributes": []},
                        "metrics": metrics,
                        "schemaUrl": "https://opentelemetry.io/schemas/1.7.0",
                    }
                ],
                "schemaUrl": "https://opentelemetry.io/schemas/1.7.0",
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
    attributes: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
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
    attributes: Optional[List[Dict[str, Any]]] = None,
    start_time_ns: Optional[int] = None,
) -> Dict[str, Any]:
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
    attributes: Optional[List[Dict[str, Any]]] = None,
    start_time_ns: Optional[int] = None,
) -> Dict[str, Any]:
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


def convert_traces_to_otlp_json(
    traces_data: List[Dict[str, Any]],
    service_name: str = "ciris",
    service_version: str = CIRIS_VERSION,
    scope_name: str = "ciris.traces",
    scope_version: str = "1.0.0",
) -> Dict[str, Any]:
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
    # Build resource attributes using helper (without environment since not used for traces)
    base_resource_attrs = create_resource_attributes(service_name, service_version, {})
    # Remove service.namespace and deployment.environment attributes for traces
    resource_attributes = [
        attr for attr in base_resource_attrs if attr["key"] not in ["service.namespace", "deployment.environment"]
    ]

    spans = []

    for trace in traces_data:
        # Use provided trace_id or generate one
        if "trace_id" in trace and trace["trace_id"]:
            # Convert to 32-char hex format for OTLP
            trace_id = trace["trace_id"].replace("-", "")[:32].upper().ljust(32, "0")
        else:
            trace_id = (
                hashlib.sha256(f"{trace.get('trace_id', '')}_{trace.get('timestamp', '')}".encode())
                .hexdigest()[:32]
                .upper()
            )

        # Use provided span_id or generate one
        if "span_id" in trace and trace["span_id"]:
            span_id = trace["span_id"].replace("-", "")[:16].upper().ljust(16, "0")
        else:
            span_id = (
                hashlib.sha256(f"{trace_id}_{trace.get('operation', 'unknown')}".encode()).hexdigest()[:16].upper()
            )

        # Handle parent span ID
        parent_span_id = None
        if "parent_span_id" in trace and trace["parent_span_id"]:
            parent_span_id = trace["parent_span_id"].replace("-", "")[:16].upper().ljust(16, "0")

        # Convert timestamp
        if isinstance(trace.get("timestamp"), str):
            try:
                ts = datetime.fromisoformat(trace["timestamp"].replace("Z", "+00:00"))
                time_ns = int(ts.timestamp() * 1e9)
            except:
                time_ns = int(time.time() * 1e9)
        else:
            time_ns = int(time.time() * 1e9)

        # Calculate end time based on duration if available
        duration_ms = trace.get("duration_ms", 1.0)
        end_time_ns = time_ns + int(duration_ms * 1e6)

        # Build span attributes
        span_attrs = []

        # Add trace attributes
        if "operation" in trace:
            span_attrs.append({"key": "operation.name", "value": {"stringValue": str(trace["operation"])}})

        if "service" in trace:
            span_attrs.append({"key": "service.name", "value": {"stringValue": str(trace["service"])}})

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
            # Add the rich attributes from step streaming (already in OTLP format)
            span_attrs.extend(trace["span_attributes"])

        # Enhanced: Use trace context if available from step streaming
        trace_context = trace.get("trace_context", {})
        span_name = trace.get("span_name", trace.get("operation", "unknown_operation"))

        if trace_context and isinstance(trace_context, dict):
            # Override IDs with those from step streaming for consistency
            if "trace_id" in trace_context:
                trace_id = trace_context["trace_id"]
            if "span_id" in trace_context:
                span_id = trace_context["span_id"]
            if "parent_span_id" in trace_context:
                parent_span_id = trace_context["parent_span_id"]
            if "span_name" in trace_context:
                span_name = trace_context["span_name"]
            if "start_time_ns" in trace_context:
                time_ns = trace_context["start_time_ns"]
            if "end_time_ns" in trace_context:
                end_time_ns = trace_context["end_time_ns"]

        # Determine span kind
        span_kind = 2  # SERVER by default
        if "span_kind" in trace:
            kind_map = {"internal": 1, "server": 2, "client": 3, "producer": 4, "consumer": 5}
            span_kind = kind_map.get(trace["span_kind"], 2)
        elif trace_context and "span_kind" in trace_context:
            kind_map = {"internal": 1, "server": 2, "client": 3, "producer": 4, "consumer": 5}
            span_kind = kind_map.get(trace_context["span_kind"], 1)  # Default to internal for H3ERE steps

        # Build the span
        span = {
            "traceId": trace_id,
            "spanId": span_id,
            "name": span_name,
            "startTimeUnixNano": str(time_ns),
            "endTimeUnixNano": str(end_time_ns),
            "kind": span_kind,
            "attributes": span_attrs,
        }

        # Add parent span ID if available
        if parent_span_id:
            span["parentSpanId"] = parent_span_id

        # Add thoughts as events if present
        if "thoughts" in trace and trace["thoughts"]:
            events = []
            for idx, thought in enumerate(trace["thoughts"]):
                event = {
                    "name": f"thought.step.{idx}",
                    "timeUnixNano": str(time_ns + idx * 1000000),  # 1ms between thoughts
                    "attributes": [{"key": "thought.content", "value": {"stringValue": thought.get("content", "")}}],
                }
                events.append(event)
            span["events"] = events

        # Add status if there was an error
        if trace.get("error"):
            span["status"] = {"code": 2, "message": trace["error"]}  # ERROR
        elif trace.get("success") is False:
            span["status"] = {"code": 2, "message": "Operation failed"}  # ERROR

        spans.append(span)

    return {
        "resourceSpans": [
            {
                "resource": {"attributes": resource_attributes},
                "scopeSpans": [
                    {
                        "scope": {
                            "name": scope_name,
                            "version": scope_version,
                        },
                        "spans": spans,
                        "schemaUrl": "https://opentelemetry.io/schemas/1.7.0",
                    }
                ],
                "schemaUrl": "https://opentelemetry.io/schemas/1.7.0",
            }
        ]
    }


def convert_logs_to_otlp_json(
    logs_data: List[Dict[str, Any]],
    service_name: str = "ciris",
    service_version: str = CIRIS_VERSION,
    scope_name: str = "ciris.logs",
    scope_version: str = "1.0.0",
) -> Dict[str, Any]:
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
    # Build resource attributes using helper (without environment since not used for logs)
    base_resource_attrs = create_resource_attributes(service_name, service_version, {})
    # Remove service.namespace and deployment.environment attributes for logs
    resource_attributes = [
        attr for attr in base_resource_attrs if attr["key"] not in ["service.namespace", "deployment.environment"]
    ]

    log_records = []

    for log in logs_data:
        # Convert timestamp
        if isinstance(log.get("timestamp"), str):
            try:
                ts = datetime.fromisoformat(log["timestamp"].replace("Z", "+00:00"))
                time_ns = int(ts.timestamp() * 1e9)
            except:
                time_ns = int(time.time() * 1e9)
        else:
            time_ns = int(time.time() * 1e9)

        # Map severity levels
        severity_map = {
            "DEBUG": 5,
            "INFO": 9,
            "INFORMATION": 9,
            "WARNING": 13,
            "WARN": 13,
            "ERROR": 17,
            "CRITICAL": 21,
            "FATAL": 21,
        }

        severity_text = log.get("level", "INFO").upper()
        severity_number = severity_map.get(severity_text, 9)

        # Build log attributes
        log_attrs = []

        if "service" in log:
            log_attrs.append({"key": "service.name", "value": {"stringValue": str(log["service"])}})

        if "component" in log:
            log_attrs.append({"key": "component", "value": {"stringValue": str(log["component"])}})

        if "action" in log:
            log_attrs.append({"key": "action", "value": {"stringValue": str(log["action"])}})

        if "user_id" in log:
            log_attrs.append({"key": "user.id", "value": {"stringValue": str(log["user_id"])}})

        if "correlation_id" in log:
            log_attrs.append({"key": "correlation.id", "value": {"stringValue": str(log["correlation_id"])}})

        # Create log record
        log_record = {
            "timeUnixNano": str(time_ns),
            "observedTimeUnixNano": str(time_ns),
            "severityNumber": severity_number,
            "severityText": severity_text,
            "body": {"stringValue": log.get("message", "") or log.get("description", "")},
            "attributes": log_attrs,
        }

        # Add trace context if available
        if "trace_id" in log:
            trace_id = hashlib.sha256(str(log["trace_id"]).encode()).hexdigest()[:32].upper()
            log_record["traceId"] = trace_id

        if "span_id" in log:
            span_id = hashlib.sha256(str(log["span_id"]).encode()).hexdigest()[:16].upper()
            log_record["spanId"] = span_id

        log_records.append(log_record)

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
                        "schemaUrl": "https://opentelemetry.io/schemas/1.7.0",
                    }
                ],
                "schemaUrl": "https://opentelemetry.io/schemas/1.7.0",
            }
        ]
    }


def validate_otlp_json(otlp_data: Dict[str, Any]) -> bool:
    """
    Validate that the OTLP JSON structure is correct.

    Args:
        otlp_data: The OTLP JSON data to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        # Check top-level structure
        if "resourceMetrics" not in otlp_data:
            return False

        if not isinstance(otlp_data["resourceMetrics"], list):
            return False

        for resource_metric in otlp_data["resourceMetrics"]:
            # Check resource
            if "resource" in resource_metric:
                if "attributes" in resource_metric["resource"]:
                    if not isinstance(resource_metric["resource"]["attributes"], list):
                        return False

            # Check scope metrics
            if "scopeMetrics" not in resource_metric:
                return False

            if not isinstance(resource_metric["scopeMetrics"], list):
                return False

            for scope_metric in resource_metric["scopeMetrics"]:
                # Check metrics
                if "metrics" not in scope_metric:
                    return False

                if not isinstance(scope_metric["metrics"], list):
                    return False

                for metric in scope_metric["metrics"]:
                    # Check metric has name and at least one data type
                    if "name" not in metric:
                        return False

                    has_data = any(
                        key in metric for key in ["gauge", "sum", "histogram", "exponentialHistogram", "summary"]
                    )

                    if not has_data:
                        return False

        return True

    except (KeyError, TypeError, AttributeError):
        return False
