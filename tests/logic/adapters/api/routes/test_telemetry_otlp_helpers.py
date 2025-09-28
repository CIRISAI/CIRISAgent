"""
Unit tests for telemetry OTLP helper functions.

These tests specifically target the helper functions extracted to reduce complexity
and increase testability of the OTLP conversion logic.
"""

import time
from unittest.mock import Mock

import pytest

from ciris_engine.logic.adapters.api.routes.telemetry_otlp import (
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
