"""
Unit tests for telemetry OTLP helper functions.

These tests specifically target the helper functions extracted to reduce complexity
and increase testability of the OTLP conversion logic.
"""

import time
from unittest.mock import Mock

import pytest

from ciris_engine.logic.adapters.api.routes.telemetry_otlp import (
    SEVERITY_MAP,
    SPAN_KIND_MAP,
    VALID_METRIC_DATA_TYPES,
    _apply_trace_context_overrides,
    _build_log_attributes,
    _build_span_attributes,
    _build_span_status,
    _build_thought_events,
    _convert_single_log_to_record,
    _convert_single_trace_to_span,
    _get_span_kind,
    _normalize_span_id,
    _normalize_trace_id,
    _parse_timestamp_to_ns,
    _SpanContext,
    _validate_metric,
    _validate_resource_attributes,
    _validate_resource_metric,
    _validate_scope_metric,
    add_covenant_metrics,
    add_service_metrics,
    add_system_metrics,
    create_resource_attributes,
    safe_telemetry_get,
)


class TestSafeTelemetryGet:
    """Test safe_telemetry_get helper function."""

    def test_with_dict(self):
        data = {"key1": "value1", "key2": 42, "nested": {"inner": "value"}}
        assert safe_telemetry_get(data, "key1") == "value1"
        assert safe_telemetry_get(data, "key2") == 42
        assert safe_telemetry_get(data, "nested") == {"inner": "value"}
        assert safe_telemetry_get(data, "missing") is None
        assert safe_telemetry_get(data, "missing", "default") == "default"

    def test_with_non_dict_types(self):
        assert safe_telemetry_get("string", "key") is None
        assert safe_telemetry_get(123, "key") is None
        assert safe_telemetry_get([1, 2, 3], "key") is None
        assert safe_telemetry_get(None, "key") is None

    def test_with_default_value(self):
        assert safe_telemetry_get("string", "key", "fallback") == "fallback"
        assert safe_telemetry_get(None, "key", "default") == "default"
        assert safe_telemetry_get({}, "missing", 42) == 42


class TestCreateResourceAttributes:
    """Test create_resource_attributes helper function."""

    def test_basic_attributes(self):
        result = create_resource_attributes("test-service", "1.0.0", {})

        expected_keys = {
            "service.name",
            "service.version",
            "service.namespace",
            "telemetry.sdk.name",
            "telemetry.sdk.version",
            "telemetry.sdk.language",
        }
        actual_keys = {attr["key"] for attr in result}

        assert expected_keys == actual_keys

        # Check specific values
        service_name_attr = next(attr for attr in result if attr["key"] == "service.name")
        assert service_name_attr["value"]["stringValue"] == "test-service"

        service_version_attr = next(attr for attr in result if attr["key"] == "service.version")
        assert service_version_attr["value"]["stringValue"] == "1.0.0"

    def test_with_environment(self):
        telemetry_data = {"environment": "production"}
        result = create_resource_attributes("ciris", "1.1.7", telemetry_data)

        env_attr = next((attr for attr in result if attr["key"] == "deployment.environment"), None)
        assert env_attr is not None
        assert env_attr["value"]["stringValue"] == "production"

    def test_without_environment(self):
        result = create_resource_attributes("ciris", "1.1.7", {})

        env_attr = next((attr for attr in result if attr["key"] == "deployment.environment"), None)
        assert env_attr is None

    def test_with_non_dict_telemetry_data(self):
        # Should handle non-dict telemetry data gracefully
        result = create_resource_attributes("service", "1.0", "invalid")
        assert len(result) == 6  # Only basic attributes

        env_attr = next((attr for attr in result if attr["key"] == "deployment.environment"), None)
        assert env_attr is None


class TestAddSystemMetrics:
    """Test add_system_metrics helper function."""

    def test_all_system_metrics(self):
        current_time_ns = int(time.time() * 1e9)
        telemetry_data = {
            "system_healthy": True,
            "services_online": 22,
            "services_total": 22,
            "overall_error_rate": 0.05,
            "overall_uptime_seconds": 3600,
            "total_errors": 10,
            "total_requests": 200,
        }

        result = add_system_metrics(telemetry_data, current_time_ns)
        assert len(result) == 7

        # Check metric names
        metric_names = {metric["name"] for metric in result}
        expected_names = {
            "system.healthy",
            "services.online",
            "services.total",
            "system.error_rate",
            "system.uptime",
            "errors.total",
            "requests.total",
        }
        assert metric_names == expected_names

    def test_partial_system_metrics(self):
        current_time_ns = int(time.time() * 1e9)
        telemetry_data = {
            "system_healthy": False,
            "services_online": 20,
            "services_total": 22,
        }

        result = add_system_metrics(telemetry_data, current_time_ns)
        assert len(result) == 3

        # Check system health metric
        health_metric = next(metric for metric in result if metric["name"] == "system.healthy")
        assert health_metric["gauge"]["dataPoints"][0]["asDouble"] == 0.0

    def test_empty_telemetry_data(self):
        current_time_ns = int(time.time() * 1e9)
        result = add_system_metrics({}, current_time_ns)
        assert result == []

    def test_non_dict_telemetry_data(self):
        current_time_ns = int(time.time() * 1e9)
        result = add_system_metrics("invalid", current_time_ns)
        assert result == []

    def test_system_healthy_false(self):
        current_time_ns = int(time.time() * 1e9)
        telemetry_data = {"system_healthy": False}

        result = add_system_metrics(telemetry_data, current_time_ns)
        assert len(result) == 1

        health_metric = result[0]
        assert health_metric["name"] == "system.healthy"
        assert health_metric["gauge"]["dataPoints"][0]["asDouble"] == 0.0


class TestAddServiceMetrics:
    """Test add_service_metrics helper function."""

    def test_complete_service_data(self, healthy_service_mock, unhealthy_service_mock, fixed_time_ns):
        """Test service metrics with mixed healthy/unhealthy services using fixtures."""
        services_data = {"service1": healthy_service_mock, "service2": unhealthy_service_mock}

        result = add_service_metrics(services_data, fixed_time_ns)

        # Should have metrics for services with valid data
        assert len(result) >= 6  # At least some metrics generated

        # Check that metrics have proper structure
        for metric in result:
            # Validate metric has required fields
            assert "name" in metric
            assert "description" in metric
            assert "unit" in metric

            # Check data points structure
            data_points = None
            if "gauge" in metric:
                data_points = metric["gauge"]["dataPoints"]
            elif "sum" in metric:
                data_points = metric["sum"]["dataPoints"]

            assert data_points is not None
            assert len(data_points) > 0

    def test_service_with_minimal_data(self, minimal_service_mock, fixed_time_ns):
        """Test service metrics with minimal mock data."""
        services_data = {"minimal_service": minimal_service_mock}

        result = add_service_metrics(services_data, fixed_time_ns)
        assert len(result) >= 1  # At least healthy metric for minimal service

        metric = result[0]
        assert metric["name"] == "service.healthy"
        assert metric["gauge"]["dataPoints"][0]["asDouble"] == 1.0

    def test_empty_services_data(self):
        current_time_ns = int(time.time() * 1e9)
        result = add_service_metrics({}, current_time_ns)
        assert result == []

    def test_non_dict_services_data(self):
        current_time_ns = int(time.time() * 1e9)
        result = add_service_metrics("invalid", current_time_ns)
        assert result == []

        result = add_service_metrics(None, current_time_ns)
        assert result == []

    def test_service_attributes_format(self, healthy_service_mock, fixed_time_ns):
        """Test service attribute format using fixtures."""
        services_data = {"test_service": healthy_service_mock}

        result = add_service_metrics(services_data, fixed_time_ns)
        metric = result[0]  # Get first metric

        # Check service attribute format
        attributes = metric["gauge"]["dataPoints"][0]["attributes"]
        assert len(attributes) == 1
        assert attributes[0]["key"] == "service"
        assert attributes[0]["value"]["stringValue"] == "test_service"


class TestAddCovenantMetrics:
    """Test add_covenant_metrics helper function."""

    def test_all_covenant_metrics(self):
        current_time_ns = int(time.time() * 1e9)
        covenant_data = {
            "wise_authority_deferrals": 5,
            "filter_matches": 2,
            "thoughts_processed": 50,
            "self_observation_insights": 3,
        }

        result = add_covenant_metrics(covenant_data, current_time_ns)
        assert len(result) == 4

        metric_names = {metric["name"] for metric in result}
        expected_names = {
            "covenant.wise_authority.deferrals",
            "covenant.filter.matches",
            "covenant.thoughts.processed",
            "covenant.insights.generated",
        }
        assert metric_names == expected_names

    def test_partial_covenant_metrics(self):
        current_time_ns = int(time.time() * 1e9)
        covenant_data = {
            "wise_authority_deferrals": 3,
            "thoughts_processed": 25,
        }

        result = add_covenant_metrics(covenant_data, current_time_ns)
        assert len(result) == 2

        metric_names = {metric["name"] for metric in result}
        assert "covenant.wise_authority.deferrals" in metric_names
        assert "covenant.thoughts.processed" in metric_names

    def test_empty_covenant_data(self):
        current_time_ns = int(time.time() * 1e9)
        result = add_covenant_metrics({}, current_time_ns)
        assert result == []

    def test_non_dict_covenant_data(self):
        current_time_ns = int(time.time() * 1e9)
        result = add_covenant_metrics("invalid", current_time_ns)
        assert result == []

        result = add_covenant_metrics(None, current_time_ns)
        assert result == []

    def test_metric_types(self):
        current_time_ns = int(time.time() * 1e9)
        covenant_data = {
            "wise_authority_deferrals": 5,
            "filter_matches": 2,
            "thoughts_processed": 50,
            "self_observation_insights": 3,
        }

        result = add_covenant_metrics(covenant_data, current_time_ns)

        # Check that all covenant metrics are counter metrics (counts of events)
        deferrals_metric = next(m for m in result if m["name"] == "covenant.wise_authority.deferrals")
        assert "sum" in deferrals_metric  # Counter metric

        filter_metric = next(m for m in result if m["name"] == "covenant.filter.matches")
        assert "sum" in filter_metric  # Counter metric


class TestHelperFunctionIntegration:
    """Integration tests showing how helper functions work together."""

    def test_full_metrics_workflow(self):
        """Test a complete workflow using all helper functions."""
        current_time_ns = int(time.time() * 1e9)

        # Simulate telemetry data
        telemetry_data = {
            "environment": "production",
            "system_healthy": True,
            "services_online": 22,
            "services_total": 22,
            "covenant_metrics": {
                "wise_authority_deferrals": 2,
                "thoughts_processed": 25,
            },
        }

        # Mock service data
        service = Mock()
        service.healthy = True
        service.error_count = 0
        services_data = {"test_service": service}

        # Use helper functions
        resource_attrs = create_resource_attributes("ciris", "1.1.7", telemetry_data)
        system_metrics = add_system_metrics(telemetry_data, current_time_ns)
        service_metrics = add_service_metrics(services_data, current_time_ns)
        covenant_metrics = add_covenant_metrics(telemetry_data["covenant_metrics"], current_time_ns)

        # Verify results
        assert len(resource_attrs) == 7  # Including environment
        assert len(system_metrics) == 3  # Only 3 fields: system_healthy, services_online, services_total
        assert len(service_metrics) >= 1  # At least healthy metric, mock objects may add more
        assert len(covenant_metrics) == 2  # partial data: deferrals and thoughts_processed

        # Check environment attribute
        env_attr = next(attr for attr in resource_attrs if attr["key"] == "deployment.environment")
        assert env_attr["value"]["stringValue"] == "production"

    def test_error_resilience(self):
        """Test that helper functions handle errors gracefully."""
        current_time_ns = int(time.time() * 1e9)

        # Test with various types of invalid data
        invalid_inputs = ["string", 123, [1, 2, 3], None, {"invalid": "structure"}]

        for invalid_input in invalid_inputs:
            # None of these should raise exceptions
            system_result = add_system_metrics(invalid_input, current_time_ns)
            service_result = add_service_metrics(invalid_input, current_time_ns)
            covenant_result = add_covenant_metrics(invalid_input, current_time_ns)

            # Most should return empty lists for non-dict inputs
            if not isinstance(invalid_input, dict):
                assert system_result == []
                assert service_result == []
                assert covenant_result == []

    def test_safe_telemetry_get_integration(self):
        """Test safe_telemetry_get with realistic telemetry data."""
        telemetry_data = {
            "system_healthy": True,
            "services": {"service1": {"healthy": True}},
            "covenant_metrics": {"wise_authority_deferrals": 5},
            "environment": "staging",
        }

        # Test accessing nested and top-level data
        assert safe_telemetry_get(telemetry_data, "system_healthy") is True
        assert safe_telemetry_get(telemetry_data, "services") == {"service1": {"healthy": True}}
        assert safe_telemetry_get(telemetry_data, "missing_key") is None
        assert safe_telemetry_get(telemetry_data, "missing_key", "default") == "default"


# --- New tests for extracted trace/log/validation helpers ---


class TestNormalizeTraceId:
    """Test _normalize_trace_id helper function."""

    def test_with_valid_trace_id(self):
        trace = {"trace_id": "abc123", "timestamp": "2025-01-01T00:00:00Z"}
        result = _normalize_trace_id("abc-def-123", trace)
        assert len(result) == 32
        assert result == result.upper()
        assert "-" not in result

    def test_with_none_trace_id_generates_from_trace(self):
        trace = {"trace_id": "test-id", "timestamp": "2025-01-01T00:00:00Z"}
        result = _normalize_trace_id(None, trace)
        assert len(result) == 32
        assert result == result.upper()

    def test_pads_short_ids(self):
        trace = {}
        result = _normalize_trace_id("abc", trace)
        assert len(result) == 32
        assert result.startswith("ABC")

    def test_truncates_long_ids(self):
        long_id = "a" * 100
        trace = {}
        result = _normalize_trace_id(long_id, trace)
        assert len(result) == 32


class TestNormalizeSpanId:
    """Test _normalize_span_id helper function."""

    def test_with_valid_span_id(self):
        result = _normalize_span_id("abc-123", "traceid", "operation")
        assert len(result) == 16
        assert result == result.upper()

    def test_with_none_generates_from_context(self):
        result = _normalize_span_id(None, "traceid", "operation")
        assert len(result) == 16
        assert result == result.upper()

    def test_pads_short_ids(self):
        result = _normalize_span_id("ab", "traceid", "operation")
        assert len(result) == 16
        assert result.startswith("AB")


class TestParseTimestampToNs:
    """Test _parse_timestamp_to_ns helper function."""

    def test_valid_iso_timestamp(self):
        result = _parse_timestamp_to_ns("2025-01-15T12:00:00Z")
        assert isinstance(result, int)
        assert result > 0

    def test_valid_iso_timestamp_with_offset(self):
        result = _parse_timestamp_to_ns("2025-01-15T12:00:00+00:00")
        assert isinstance(result, int)
        assert result > 0

    def test_invalid_timestamp_returns_current_time(self):
        before = int(time.time() * 1e9)
        result = _parse_timestamp_to_ns("invalid")
        after = int(time.time() * 1e9)
        assert before <= result <= after

    def test_none_timestamp_returns_current_time(self):
        before = int(time.time() * 1e9)
        result = _parse_timestamp_to_ns(None)
        after = int(time.time() * 1e9)
        assert before <= result <= after


class TestBuildSpanAttributes:
    """Test _build_span_attributes helper function."""

    def test_with_all_fields(self):
        trace = {
            "operation": "test-op",
            "service": "test-service",
            "handler": "test-handler",
            "status": "success",
            "task_id": "task-123",
            "thought_id": "thought-456",
            "success": True,
            "error": "test error",
        }
        result = _build_span_attributes(trace)
        keys = [attr["key"] for attr in result]
        assert "operation.name" in keys
        assert "service.name" in keys
        assert "handler.name" in keys
        assert "span.status" in keys
        assert "ciris.task_id" in keys
        assert "ciris.thought_id" in keys
        assert "span.success" in keys
        assert "error.message" in keys

    def test_with_minimal_fields(self):
        trace = {"operation": "test-op"}
        result = _build_span_attributes(trace)
        assert len(result) == 1
        assert result[0]["key"] == "operation.name"

    def test_with_span_attributes_list(self):
        trace = {"span_attributes": [{"key": "custom.attr", "value": {"stringValue": "custom"}}]}
        result = _build_span_attributes(trace)
        assert len(result) == 1
        assert result[0]["key"] == "custom.attr"

    def test_empty_trace(self):
        result = _build_span_attributes({})
        assert result == []


class TestGetSpanKind:
    """Test _get_span_kind helper function."""

    def test_span_kind_from_trace(self):
        trace = {"span_kind": "client"}
        result = _get_span_kind(trace, {})
        assert result == SPAN_KIND_MAP["client"]

    def test_span_kind_from_context(self):
        trace = {}
        trace_context = {"span_kind": "producer"}
        result = _get_span_kind(trace, trace_context)
        assert result == SPAN_KIND_MAP["producer"]

    def test_default_span_kind(self):
        result = _get_span_kind({}, {})
        assert result == 2  # SERVER

    def test_trace_takes_precedence_over_context(self):
        trace = {"span_kind": "client"}
        trace_context = {"span_kind": "server"}
        result = _get_span_kind(trace, trace_context)
        assert result == SPAN_KIND_MAP["client"]


class TestBuildThoughtEvents:
    """Test _build_thought_events helper function."""

    def test_with_dict_thoughts(self):
        thoughts = [
            {"content": "First thought"},
            {"content": "Second thought"},
        ]
        time_ns = 1000000000
        result = _build_thought_events(thoughts, time_ns)
        assert len(result) == 2
        assert result[0]["name"] == "thought.step.0"
        assert result[1]["name"] == "thought.step.1"
        assert result[0]["attributes"][0]["value"]["stringValue"] == "First thought"

    def test_with_non_dict_thoughts(self):
        thoughts = ["string thought", 123]
        time_ns = 1000000000
        result = _build_thought_events(thoughts, time_ns)
        assert len(result) == 2
        assert result[0]["attributes"][0]["value"]["stringValue"] == ""

    def test_empty_thoughts(self):
        result = _build_thought_events([], 1000000000)
        assert result == []

    def test_timestamp_increments(self):
        thoughts = [{"content": "1"}, {"content": "2"}, {"content": "3"}]
        time_ns = 1000000000
        result = _build_thought_events(thoughts, time_ns)
        times = [int(e["timeUnixNano"]) for e in result]
        assert times[1] > times[0]
        assert times[2] > times[1]


class TestBuildSpanStatus:
    """Test _build_span_status helper function."""

    def test_with_error_string(self):
        trace = {"error": "Something went wrong"}
        result = _build_span_status(trace)
        assert result is not None
        assert result["code"] == 2
        assert result["message"] == "Something went wrong"

    def test_with_success_false(self):
        trace = {"success": False}
        result = _build_span_status(trace)
        assert result is not None
        assert result["code"] == 2
        assert result["message"] == "Operation failed"

    def test_with_success_true(self):
        trace = {"success": True}
        result = _build_span_status(trace)
        assert result is None

    def test_with_no_error_no_success(self):
        trace = {}
        result = _build_span_status(trace)
        assert result is None

    def test_error_takes_precedence(self):
        trace = {"error": "Custom error", "success": False}
        result = _build_span_status(trace)
        assert result["message"] == "Custom error"


class TestSpanContext:
    """Test _SpanContext class."""

    def test_initialization(self):
        ctx = _SpanContext("trace1", "span1", "parent1", "op", 1000, 2000)
        assert ctx.trace_id == "trace1"
        assert ctx.span_id == "span1"
        assert ctx.parent_span_id == "parent1"
        assert ctx.span_name == "op"
        assert ctx.time_ns == 1000
        assert ctx.end_time_ns == 2000

    def test_with_none_parent(self):
        ctx = _SpanContext("trace1", "span1", None, "op", 1000, 2000)
        assert ctx.parent_span_id is None


class TestApplyTraceContextOverrides:
    """Test _apply_trace_context_overrides helper function."""

    def test_all_overrides(self):
        ctx = _SpanContext("orig_trace", "orig_span", None, "orig_name", 1000, 2000)
        trace_context = {
            "trace_id": "new_trace",
            "span_id": "new_span",
            "parent_span_id": "new_parent",
            "span_name": "new_name",
            "start_time_ns": 3000,
            "end_time_ns": 4000,
        }
        _apply_trace_context_overrides(ctx, trace_context)
        assert ctx.trace_id == "new_trace"
        assert ctx.span_id == "new_span"
        assert ctx.parent_span_id == "new_parent"
        assert ctx.span_name == "new_name"
        assert ctx.time_ns == 3000
        assert ctx.end_time_ns == 4000

    def test_partial_overrides(self):
        ctx = _SpanContext("orig_trace", "orig_span", None, "orig_name", 1000, 2000)
        trace_context = {"span_name": "new_name"}
        _apply_trace_context_overrides(ctx, trace_context)
        assert ctx.trace_id == "orig_trace"  # Not overridden
        assert ctx.span_name == "new_name"  # Overridden

    def test_empty_context(self):
        ctx = _SpanContext("orig_trace", "orig_span", None, "orig_name", 1000, 2000)
        _apply_trace_context_overrides(ctx, {})
        assert ctx.trace_id == "orig_trace"
        assert ctx.span_name == "orig_name"


class TestConvertSingleTraceToSpan:
    """Test _convert_single_trace_to_span helper function."""

    def test_basic_trace(self):
        trace = {
            "trace_id": "abc123",
            "span_id": "def456",
            "operation": "test-operation",
            "timestamp": "2025-01-15T12:00:00Z",
            "duration_ms": 100.0,
        }
        result = _convert_single_trace_to_span(trace)
        assert "traceId" in result
        assert "spanId" in result
        assert result["name"] == "test-operation"
        assert "startTimeUnixNano" in result
        assert "endTimeUnixNano" in result

    def test_with_thoughts(self):
        trace = {
            "operation": "test",
            "thoughts": [{"content": "Thought 1"}, {"content": "Thought 2"}],
        }
        result = _convert_single_trace_to_span(trace)
        assert "events" in result
        assert len(result["events"]) == 2

    def test_with_error(self):
        trace = {"operation": "test", "error": "Something failed"}
        result = _convert_single_trace_to_span(trace)
        assert "status" in result
        assert result["status"]["code"] == 2


class TestBuildLogAttributes:
    """Test _build_log_attributes helper function."""

    def test_with_all_fields(self):
        log = {
            "service": "test-service",
            "component": "test-component",
            "action": "test-action",
            "user_id": "user-123",
            "correlation_id": "corr-456",
        }
        result = _build_log_attributes(log)
        keys = [attr["key"] for attr in result]
        assert "service.name" in keys
        assert "component" in keys
        assert "action" in keys
        assert "user.id" in keys
        assert "correlation.id" in keys

    def test_with_minimal_fields(self):
        log = {"service": "test"}
        result = _build_log_attributes(log)
        assert len(result) == 1

    def test_empty_log(self):
        result = _build_log_attributes({})
        assert result == []


class TestConvertSingleLogToRecord:
    """Test _convert_single_log_to_record helper function."""

    def test_basic_log(self):
        log = {
            "timestamp": "2025-01-15T12:00:00Z",
            "level": "INFO",
            "message": "Test message",
        }
        result = _convert_single_log_to_record(log)
        assert "timeUnixNano" in result
        assert result["severityText"] == "INFO"
        assert result["severityNumber"] == SEVERITY_MAP["INFO"]
        assert result["body"]["stringValue"] == "Test message"

    def test_with_trace_context(self):
        log = {
            "level": "ERROR",
            "message": "Error occurred",
            "trace_id": "trace123",
            "span_id": "span456",
        }
        result = _convert_single_log_to_record(log)
        assert "traceId" in result
        assert "spanId" in result

    def test_severity_mapping(self):
        for level, expected_number in SEVERITY_MAP.items():
            log = {"level": level.lower(), "message": "test"}
            result = _convert_single_log_to_record(log)
            assert result["severityNumber"] == expected_number


class TestValidateResourceAttributes:
    """Test _validate_resource_attributes helper function."""

    def test_valid_attributes(self):
        resource = {"attributes": [{"key": "test", "value": {"stringValue": "value"}}]}
        assert _validate_resource_attributes(resource) is True

    def test_invalid_attributes_not_list(self):
        resource = {"attributes": "not a list"}
        assert _validate_resource_attributes(resource) is False

    def test_no_attributes(self):
        resource = {}
        assert _validate_resource_attributes(resource) is True


class TestValidateMetric:
    """Test _validate_metric helper function."""

    def test_valid_gauge_metric(self):
        metric = {"name": "test.metric", "gauge": {"dataPoints": []}}
        assert _validate_metric(metric) is True

    def test_valid_sum_metric(self):
        metric = {"name": "test.metric", "sum": {"dataPoints": []}}
        assert _validate_metric(metric) is True

    def test_missing_name(self):
        metric = {"gauge": {"dataPoints": []}}
        assert _validate_metric(metric) is False

    def test_missing_data_type(self):
        metric = {"name": "test.metric"}
        assert _validate_metric(metric) is False


class TestValidateScopeMetric:
    """Test _validate_scope_metric helper function."""

    def test_valid_scope_metric(self):
        scope_metric = {
            "metrics": [
                {"name": "m1", "gauge": {}},
                {"name": "m2", "sum": {}},
            ]
        }
        assert _validate_scope_metric(scope_metric) is True

    def test_missing_metrics(self):
        scope_metric = {}
        assert _validate_scope_metric(scope_metric) is False

    def test_metrics_not_list(self):
        scope_metric = {"metrics": "not a list"}
        assert _validate_scope_metric(scope_metric) is False

    def test_invalid_metric_in_list(self):
        scope_metric = {
            "metrics": [
                {"name": "valid", "gauge": {}},
                {"no_name": True},  # Invalid - no name
            ]
        }
        assert _validate_scope_metric(scope_metric) is False


class TestValidateResourceMetric:
    """Test _validate_resource_metric helper function."""

    def test_valid_resource_metric(self):
        resource_metric = {
            "resource": {"attributes": []},
            "scopeMetrics": [{"metrics": [{"name": "test", "gauge": {}}]}],
        }
        assert _validate_resource_metric(resource_metric) is True

    def test_missing_scope_metrics(self):
        resource_metric = {"resource": {"attributes": []}}
        assert _validate_resource_metric(resource_metric) is False

    def test_scope_metrics_not_list(self):
        resource_metric = {
            "resource": {},
            "scopeMetrics": "not a list",
        }
        assert _validate_resource_metric(resource_metric) is False

    def test_invalid_resource_attributes(self):
        resource_metric = {
            "resource": {"attributes": "not a list"},
            "scopeMetrics": [{"metrics": [{"name": "test", "gauge": {}}]}],
        }
        assert _validate_resource_metric(resource_metric) is False


class TestConstants:
    """Test that constants are defined correctly."""

    def test_span_kind_map(self):
        assert SPAN_KIND_MAP["internal"] == 1
        assert SPAN_KIND_MAP["server"] == 2
        assert SPAN_KIND_MAP["client"] == 3
        assert SPAN_KIND_MAP["producer"] == 4
        assert SPAN_KIND_MAP["consumer"] == 5

    def test_severity_map(self):
        assert SEVERITY_MAP["DEBUG"] == 5
        assert SEVERITY_MAP["INFO"] == 9
        assert SEVERITY_MAP["WARNING"] == 13
        assert SEVERITY_MAP["ERROR"] == 17
        assert SEVERITY_MAP["CRITICAL"] == 21

    def test_valid_metric_data_types(self):
        assert "gauge" in VALID_METRIC_DATA_TYPES
        assert "sum" in VALID_METRIC_DATA_TYPES
        assert "histogram" in VALID_METRIC_DATA_TYPES
        assert "exponentialHistogram" in VALID_METRIC_DATA_TYPES
        assert "summary" in VALID_METRIC_DATA_TYPES
