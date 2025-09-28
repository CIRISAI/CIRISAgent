"""Unit tests for OTLP telemetry converters."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.adapters.api.routes.telemetry_otlp import (
    convert_logs_to_otlp_json,
    convert_to_otlp_json,
    convert_traces_to_otlp_json,
    validate_otlp_json,
)
from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData


class TestOTLPMetricsConverter:
    """Test metrics conversion to OTLP format."""

    def test_convert_basic_metrics(self):
        """Test basic metrics conversion."""
        telemetry_data = {
            "system_healthy": True,
            "services_online": 10,
            "services_total": 12,
            "overall_error_rate": 0.05,
            "overall_uptime_seconds": 3600,
            "total_errors": 5,
            "total_requests": 100,
        }

        result = convert_to_otlp_json(telemetry_data)

        # Check structure
        assert "resourceMetrics" in result
        assert len(result["resourceMetrics"]) == 1

        resource_metric = result["resourceMetrics"][0]
        assert "resource" in resource_metric
        assert "scopeMetrics" in resource_metric

        # Check resource attributes
        attributes = resource_metric["resource"]["attributes"]
        service_name_attr = next((a for a in attributes if a["key"] == "service.name"), None)
        assert service_name_attr is not None
        assert service_name_attr["value"]["stringValue"] == "ciris"

        # Check metrics
        metrics = resource_metric["scopeMetrics"][0]["metrics"]
        assert len(metrics) == 7  # All basic metrics

        # Check specific metric
        system_healthy_metric = next((m for m in metrics if m["name"] == "system.healthy"), None)
        assert system_healthy_metric is not None
        assert system_healthy_metric["gauge"]["dataPoints"][0]["asDouble"] == 1.0

    def test_convert_service_metrics(self):
        """Test conversion of service-level metrics."""
        service_data = MagicMock()
        service_data.healthy = True
        service_data.uptime_seconds = 1000.0
        service_data.error_count = 2
        service_data.requests_handled = 50
        service_data.error_rate = 0.04
        service_data.memory_mb = 256.5

        telemetry_data = {"services": {"test_service": service_data}}

        result = convert_to_otlp_json(telemetry_data)

        metrics = result["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]

        # Check service metrics exist
        service_metrics = [m for m in metrics if "service." in m["name"]]
        assert len(service_metrics) == 6  # All service metrics

        # Check service attribute is added
        healthy_metric = next((m for m in metrics if m["name"] == "service.healthy"), None)
        assert healthy_metric is not None
        attrs = healthy_metric["gauge"]["dataPoints"][0].get("attributes", [])
        service_attr = next((a for a in attrs if a["key"] == "service"), None)
        assert service_attr is not None
        assert service_attr["value"]["stringValue"] == "test_service"

    def test_convert_covenant_metrics(self):
        """Test conversion of covenant metrics."""
        telemetry_data = {
            "covenant_metrics": {
                "wise_authority_deferrals": 3,
                "filter_matches": 5,
                "thoughts_processed": 10,
                "self_observation_insights": 2,
            }
        }

        result = convert_to_otlp_json(telemetry_data)

        metrics = result["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]

        # Check covenant metrics
        covenant_metrics = [m for m in metrics if "covenant." in m["name"]]
        assert len(covenant_metrics) == 4

        # Check specific covenant metric
        deferrals_metric = next((m for m in metrics if m["name"] == "covenant.wise_authority.deferrals"), None)
        assert deferrals_metric is not None
        assert deferrals_metric["sum"]["dataPoints"][0]["asDouble"] == 3.0

    def test_validate_metrics_otlp(self):
        """Test OTLP validation for metrics."""
        telemetry_data = {"system_healthy": True}
        result = convert_to_otlp_json(telemetry_data)

        assert validate_otlp_json(result) is True


class TestOTLPTracesConverter:
    """Test traces conversion to OTLP format."""

    def test_convert_basic_trace(self):
        """Test basic trace conversion."""
        traces_data = [
            {
                "trace_id": "test_trace_001",
                "timestamp": "2025-01-21T10:00:00Z",
                "operation": "thought_processing",
                "cognitive_state": "WORK",
                "agent_id": "test_agent",
            }
        ]

        result = convert_traces_to_otlp_json(traces_data)

        # Check structure
        assert "resourceSpans" in result
        assert len(result["resourceSpans"]) == 1

        resource_span = result["resourceSpans"][0]
        assert "resource" in resource_span
        assert "scopeSpans" in resource_span

        # Check spans
        spans = resource_span["scopeSpans"][0]["spans"]
        assert len(spans) == 1

        span = spans[0]
        assert "traceId" in span
        assert "spanId" in span
        assert span["name"] == "thought_processing"

        # Check attributes
        attrs = span["attributes"]
        operation_attr = next((a for a in attrs if a["key"] == "operation.name"), None)
        assert operation_attr is not None
        assert operation_attr["value"]["stringValue"] == "thought_processing"

    def test_convert_trace_with_thoughts(self):
        """Test trace conversion with thought steps."""
        traces_data = [
            {
                "trace_id": "test_trace_002",
                "timestamp": "2025-01-21T10:00:00Z",
                "operation": "decision_making",
                "thoughts": [
                    {"content": "Analyzing input"},
                    {"content": "Evaluating options"},
                    {"content": "Making decision"},
                ],
            }
        ]

        result = convert_traces_to_otlp_json(traces_data)

        span = result["resourceSpans"][0]["scopeSpans"][0]["spans"][0]

        # Check events (thought steps)
        assert "events" in span
        assert len(span["events"]) == 3

        # Check first thought
        first_event = span["events"][0]
        assert first_event["name"] == "thought.step.0"
        thought_attr = first_event["attributes"][0]
        assert thought_attr["key"] == "thought.content"
        assert thought_attr["value"]["stringValue"] == "Analyzing input"

    def test_multiple_traces(self):
        """Test conversion of multiple traces."""
        traces_data = [
            {"trace_id": "trace_1", "operation": "op1", "timestamp": "2025-01-21T10:00:00Z"},
            {"trace_id": "trace_2", "operation": "op2", "timestamp": "2025-01-21T10:01:00Z"},
        ]

        result = convert_traces_to_otlp_json(traces_data)

        spans = result["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(spans) == 2
        assert spans[0]["name"] == "op1"
        assert spans[1]["name"] == "op2"


class TestOTLPLogsConverter:
    """Test logs conversion to OTLP format."""

    def test_convert_basic_log(self):
        """Test basic log conversion."""
        logs_data = [
            {
                "timestamp": "2025-01-21T10:00:00Z",
                "level": "INFO",
                "message": "Test log message",
                "service": "test_service",
                "component": "test_component",
            }
        ]

        result = convert_logs_to_otlp_json(logs_data)

        # Check structure
        assert "resourceLogs" in result
        assert len(result["resourceLogs"]) == 1

        resource_log = result["resourceLogs"][0]
        assert "resource" in resource_log
        assert "scopeLogs" in resource_log

        # Check log records
        log_records = resource_log["scopeLogs"][0]["logRecords"]
        assert len(log_records) == 1

        log_record = log_records[0]
        assert "timeUnixNano" in log_record
        assert log_record["severityNumber"] == 9  # INFO level
        assert log_record["severityText"] == "INFO"
        assert log_record["body"]["stringValue"] == "Test log message"

    def test_convert_log_with_trace_context(self):
        """Test log conversion with trace context."""
        logs_data = [
            {
                "timestamp": "2025-01-21T10:00:00Z",
                "level": "ERROR",
                "message": "Error occurred",
                "trace_id": "trace_123",
                "span_id": "span_456",
                "correlation_id": "corr_789",
            }
        ]

        result = convert_logs_to_otlp_json(logs_data)

        log_record = result["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]

        # Check trace context
        assert "traceId" in log_record
        assert "spanId" in log_record

        # Check correlation ID in attributes
        attrs = log_record["attributes"]
        corr_attr = next((a for a in attrs if a["key"] == "correlation.id"), None)
        assert corr_attr is not None
        assert corr_attr["value"]["stringValue"] == "corr_789"

    def test_log_severity_mapping(self):
        """Test log severity level mapping."""
        severity_tests = [
            ("DEBUG", 5),
            ("INFO", 9),
            ("WARNING", 13),
            ("ERROR", 17),
            ("CRITICAL", 21),
            ("FATAL", 21),
        ]

        for level, expected_number in severity_tests:
            logs_data = [{"level": level, "message": "Test"}]
            result = convert_logs_to_otlp_json(logs_data)
            log_record = result["resourceLogs"][0]["scopeLogs"][0]["logRecords"][0]
            assert log_record["severityNumber"] == expected_number
            assert log_record["severityText"] == level.upper()

    def test_multiple_logs(self):
        """Test conversion of multiple logs."""
        logs_data = [
            {"message": "Log 1", "level": "INFO"},
            {"message": "Log 2", "level": "ERROR"},
            {"message": "Log 3", "level": "DEBUG"},
        ]

        result = convert_logs_to_otlp_json(logs_data)

        log_records = result["resourceLogs"][0]["scopeLogs"][0]["logRecords"]
        assert len(log_records) == 3
        assert log_records[0]["body"]["stringValue"] == "Log 1"
        assert log_records[1]["body"]["stringValue"] == "Log 2"
        assert log_records[2]["body"]["stringValue"] == "Log 3"


class TestOTLPValidation:
    """Test OTLP JSON validation."""

    def test_validate_valid_metrics(self):
        """Test validation of valid metrics OTLP."""
        valid_otlp = {
            "resourceMetrics": [
                {
                    "resource": {"attributes": []},
                    "scopeMetrics": [
                        {"metrics": [{"name": "test_metric", "gauge": {"dataPoints": [{"asDouble": 1.0}]}}]}
                    ],
                }
            ]
        }

        assert validate_otlp_json(valid_otlp) is True

    def test_validate_invalid_structure(self):
        """Test validation of invalid OTLP structure."""
        invalid_cases = [
            {},  # Empty
            {"wrong_key": []},  # Wrong top-level key
            {"resourceMetrics": "not_a_list"},  # Not a list
            {"resourceMetrics": [{"scopeMetrics": "not_a_list"}]},  # Nested not a list
            {"resourceMetrics": [{"scopeMetrics": [{"metrics": [{"name": "test"}]}]}]},  # No data
        ]

        for invalid_otlp in invalid_cases:
            assert validate_otlp_json(invalid_otlp) is False

    def test_validate_with_all_metric_types(self):
        """Test validation with different metric types."""
        valid_otlp = {
            "resourceMetrics": [
                {
                    "scopeMetrics": [
                        {
                            "metrics": [
                                {"name": "gauge", "gauge": {"dataPoints": []}},
                                {"name": "sum", "sum": {"dataPoints": []}},
                                {"name": "histogram", "histogram": {"dataPoints": []}},
                            ]
                        }
                    ]
                }
            ]
        }

        assert validate_otlp_json(valid_otlp) is True


class TestOTLPIntegration:
    """Integration tests for OTLP conversion."""

    def test_full_telemetry_conversion(self):
        """Test conversion of complete telemetry data."""
        # Create comprehensive telemetry data
        service_mock = MagicMock()
        service_mock.healthy = True
        service_mock.uptime_seconds = 3600
        service_mock.error_count = 5
        service_mock.requests_handled = 1000
        service_mock.error_rate = 0.005
        service_mock.memory_mb = 512

        telemetry_data = {
            "system_healthy": True,
            "services_online": 20,
            "services_total": 21,
            "overall_error_rate": 0.01,
            "overall_uptime_seconds": 7200,
            "total_errors": 10,
            "total_requests": 2000,
            "services": {
                "memory_service": service_mock,
                "telemetry_service": service_mock,
            },
            "covenant_metrics": {
                "wise_authority_deferrals": 5,
                "ethical_decisions": 100,
                "covenant_compliance_rate": 0.98,
                "transparency_score": 0.92,
            },
        }

        result = convert_to_otlp_json(telemetry_data)

        # Validate structure
        assert validate_otlp_json(result) is True

        # Check we have all metrics
        metrics = result["resourceMetrics"][0]["scopeMetrics"][0]["metrics"]

        # System metrics (7) + Service metrics (6 * 2 services) + Covenant metrics (4)
        assert len(metrics) >= 19

        # Verify JSON serializable
        json_str = json.dumps(result)
        assert len(json_str) > 0

        # Verify can parse back
        parsed = json.loads(json_str)
        assert parsed == result
