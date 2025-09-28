"""
Shared fixtures for API routes tests.

High-quality centralized fixtures for telemetry and OTLP testing including:
- Mock service data factories with realistic attributes
- Comprehensive telemetry data fixtures with various scenarios
- Time management for consistent test results
- Metric validation helpers for asserting OTLP format correctness
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import Mock

import pytest

from ciris_engine.schemas.services.graph.telemetry import (
    AggregatedTelemetryMetadata,
    AggregatedTelemetryResponse,
    ServiceTelemetryData,
)

# =============================================================================
# TIME FIXTURES
# =============================================================================


@pytest.fixture
def fixed_time_ns():
    """Provide consistent time in nanoseconds for OTLP tests."""
    return int(time.time() * 1e9)


@pytest.fixture
def mock_time_service():
    """Create consistent mock time service for telemetry."""
    service = Mock()
    # Fixed time for consistent testing
    fixed_time = datetime(2025, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
    service.now.return_value = fixed_time
    service.now_iso.return_value = fixed_time.isoformat()
    service.strftime.return_value = fixed_time.strftime("%Y%m%d_%H%M%S")
    return service


# =============================================================================
# SERVICE DATA FIXTURES
# =============================================================================


@pytest.fixture
def healthy_service_data():
    """Create a ServiceTelemetryData instance with all healthy metrics."""
    return ServiceTelemetryData(
        healthy=True,
        uptime_seconds=3600.0,
        error_count=0,
        requests_handled=100,
        error_rate=0.0,
        memory_mb=256.0,
        custom_metrics={"cache_hit_rate": 0.95, "response_time_ms": 15.2},
    )


@pytest.fixture
def unhealthy_service_data():
    """Create a ServiceTelemetryData instance with unhealthy/degraded metrics."""
    return ServiceTelemetryData(
        healthy=False,
        uptime_seconds=1800.0,
        error_count=15,
        requests_handled=200,
        error_rate=0.075,
        memory_mb=512.0,
        custom_metrics={"cache_hit_rate": 0.65, "response_time_ms": 45.8},
    )


@pytest.fixture
def minimal_service_data():
    """Create a ServiceTelemetryData instance with only required fields."""
    return ServiceTelemetryData(healthy=True)


@pytest.fixture
def mixed_services_data(healthy_service_data, unhealthy_service_data, minimal_service_data):
    """Create services data with mixed health states using real schemas."""
    return {
        "memory": healthy_service_data,
        "authentication": unhealthy_service_data,
        "audit": minimal_service_data,
    }


@pytest.fixture
def healthy_service_mock():
    """Create a mock service with all healthy metrics (for backward compatibility)."""
    service = Mock()
    service.healthy = True
    service.uptime_seconds = 3600
    service.error_count = 0
    service.requests_handled = 100
    service.error_rate = 0.0
    service.memory_mb = 256
    return service


@pytest.fixture
def unhealthy_service_mock():
    """Create a mock service with unhealthy/degraded metrics (for backward compatibility)."""
    service = Mock()
    service.healthy = False
    service.uptime_seconds = 1800
    service.error_count = 15
    service.requests_handled = 200
    service.error_rate = 0.075
    service.memory_mb = 512
    return service


@pytest.fixture
def minimal_service_mock():
    """Create a mock service with only basic attributes (for backward compatibility)."""
    service = Mock()
    service.healthy = True
    # No other attributes set - test defensive coding
    return service


# =============================================================================
# TELEMETRY DATA FIXTURES
# =============================================================================


@pytest.fixture
def complete_telemetry_data():
    """Create comprehensive telemetry data with all fields."""
    return {
        "environment": "production",
        "system_healthy": True,
        "services_online": 22,
        "services_total": 22,
        "overall_error_rate": 0.02,
        "overall_uptime_seconds": 7200,
        "total_errors": 5,
        "total_requests": 250,
        "covenant_metrics": {
            "wise_authority_deferrals": 3,
            "ethical_decisions": 45,
            "covenant_compliance_rate": 0.96,
            "transparency_score": 0.89,
        },
    }


@pytest.fixture
def minimal_telemetry_data():
    """Create minimal telemetry data for edge case testing."""
    return {
        "system_healthy": True,
        "services_online": 10,
        "services_total": 22,
    }


@pytest.fixture
def degraded_telemetry_data():
    """Create telemetry data representing degraded system state."""
    return {
        "environment": "staging",
        "system_healthy": False,
        "services_online": 18,
        "services_total": 22,
        "overall_error_rate": 0.15,
        "overall_uptime_seconds": 3600,
        "total_errors": 30,
        "total_requests": 200,
        "covenant_metrics": {
            "wise_authority_deferrals": 8,
            "ethical_decisions": 25,
            "covenant_compliance_rate": 0.85,
            "transparency_score": 0.72,
        },
    }


@pytest.fixture
def empty_telemetry_data():
    """Create empty telemetry data for testing defensive behavior."""
    return {}


@pytest.fixture
def aggregated_telemetry_response(complete_telemetry_data, mixed_services_data):
    """Create a full AggregatedTelemetryResponse using real schema."""
    return AggregatedTelemetryResponse(
        system_healthy=True,
        services_online=22,
        services_total=22,
        overall_error_rate=0.02,
        overall_uptime_seconds=7200,
        total_errors=5,
        total_requests=250,
        timestamp="2025-09-08T12:00:00Z",
        services=mixed_services_data,
        metadata=AggregatedTelemetryMetadata(
            collection_method="parallel", cache_ttl_seconds=30, timestamp="2025-09-08T12:00:00Z", cache_hit=False
        ),
    )


@pytest.fixture
def telemetry_with_services(complete_telemetry_data, mixed_services_data):
    """Create telemetry data that includes services information (dict format for OTLP)."""
    telemetry = complete_telemetry_data.copy()
    telemetry["services"] = mixed_services_data
    return telemetry


# =============================================================================
# COVENANT DATA FIXTURES
# =============================================================================


@pytest.fixture
def complete_covenant_data():
    """Create complete covenant metrics data matching actual service implementation."""
    return {
        "wise_authority_deferrals": 5,
        "filter_matches": 2,
        "thoughts_processed": 50,
        "self_observation_insights": 3,
    }


@pytest.fixture
def partial_covenant_data():
    """Create partial covenant metrics for testing optional fields."""
    return {
        "wise_authority_deferrals": 3,
        "thoughts_processed": 25,
    }


@pytest.fixture
def empty_covenant_data():
    """Create empty covenant data for testing edge cases."""
    return {}


# =============================================================================
# VALIDATION HELPERS
# =============================================================================


@pytest.fixture
def metric_validator():
    """Create helper functions for validating OTLP metric format."""

    class MetricValidator:
        @staticmethod
        def validate_gauge_metric(metric: Dict[str, Any]) -> bool:
            """Validate that a metric is a properly formatted gauge."""
            required_fields = ["name", "description", "unit", "gauge"]
            if not all(field in metric for field in required_fields):
                return False

            gauge = metric["gauge"]
            if "dataPoints" not in gauge or not isinstance(gauge["dataPoints"], list):
                return False

            for point in gauge["dataPoints"]:
                if "asDouble" not in point or "timeUnixNano" not in point:
                    return False

            return True

        @staticmethod
        def validate_counter_metric(metric: Dict[str, Any]) -> bool:
            """Validate that a metric is a properly formatted counter."""
            required_fields = ["name", "description", "unit", "sum"]
            if not all(field in metric for field in required_fields):
                return False

            sum_data = metric["sum"]
            required_sum_fields = ["aggregationTemporality", "isMonotonic", "dataPoints"]
            if not all(field in sum_data for field in required_sum_fields):
                return False

            for point in sum_data["dataPoints"]:
                required_point_fields = ["asDouble", "startTimeUnixNano", "timeUnixNano"]
                if not all(field in point for field in required_point_fields):
                    return False

            return True

        @staticmethod
        def validate_resource_attributes(attributes: List[Dict[str, Any]]) -> bool:
            """Validate OTLP resource attributes format."""
            required_keys = {
                "service.name",
                "service.version",
                "service.namespace",
                "telemetry.sdk.name",
                "telemetry.sdk.version",
                "telemetry.sdk.language",
            }

            found_keys = {attr["key"] for attr in attributes}
            return required_keys.issubset(found_keys)

        @staticmethod
        def validate_service_attributes(metric: Dict[str, Any]) -> bool:
            """Validate that service metrics have proper service attributes."""
            # Get data points from either gauge or sum
            data_points = None
            if "gauge" in metric:
                data_points = metric["gauge"]["dataPoints"]
            elif "sum" in metric:
                data_points = metric["sum"]["dataPoints"]

            if not data_points:
                return False

            # Check if any data point has service attribute
            for point in data_points:
                if "attributes" in point:
                    for attr in point["attributes"]:
                        if attr["key"] == "service" and "value" in attr and "stringValue" in attr["value"]:
                            return True

            return False

        @staticmethod
        def find_metric_by_name(metrics: List[Dict[str, Any]], name: str) -> Dict[str, Any]:
            """Find a metric by name in a list of metrics."""
            for metric in metrics:
                if metric.get("name") == name:
                    return metric
            raise ValueError(f"Metric '{name}' not found in metrics list")

        @staticmethod
        def count_metrics_by_type(metrics: List[Dict[str, Any]]) -> Dict[str, int]:
            """Count metrics by type (gauge, counter)."""
            counts = {"gauge": 0, "counter": 0, "other": 0}

            for metric in metrics:
                if "gauge" in metric:
                    counts["gauge"] += 1
                elif "sum" in metric:
                    counts["counter"] += 1
                else:
                    counts["other"] += 1

            return counts

    return MetricValidator()


# =============================================================================
# ERROR CASE FIXTURES
# =============================================================================


@pytest.fixture
def invalid_telemetry_inputs():
    """Provide various invalid inputs for testing error resilience."""
    return [
        "string_input",
        123,
        [1, 2, 3],
        None,
        {"invalid": "structure"},
    ]


@pytest.fixture
def service_with_invalid_attributes():
    """Create a service mock with invalid/unparseable attributes."""
    service = Mock()
    service.healthy = "not_a_boolean"  # Invalid type
    service.error_count = "not_a_number"  # Invalid type
    service.requests_handled = Mock()  # Mock object, not a number
    return service


# =============================================================================
# INTEGRATION TEST FIXTURES
# =============================================================================


@pytest.fixture
def full_otlp_test_scenario(telemetry_with_services, fixed_time_ns):
    """Create a complete scenario for testing full OTLP conversion workflow."""
    return {
        "telemetry_data": telemetry_with_services,
        "current_time_ns": fixed_time_ns,
        "service_name": "ciris",
        "service_version": "1.1.7",
        "scope_name": "ciris.telemetry",
        "scope_version": "1.0.0",
        "expected_metric_count": 15,  # Approximate based on complete data
    }


@pytest.fixture
def expected_system_metric_names():
    """Provide expected system-level metric names for validation."""
    return {
        "system.healthy",
        "services.online",
        "services.total",
        "system.error_rate",
        "system.uptime",
        "errors.total",
        "requests.total",
    }


@pytest.fixture
def expected_covenant_metric_names():
    """Provide expected covenant metric names for validation (matching actual implementation)."""
    return {
        "covenant.wise_authority.deferrals",
        "covenant.filter.matches",
        "covenant.thoughts.processed",
        "covenant.insights.generated",
    }


@pytest.fixture
def expected_service_metric_names():
    """Provide expected service-level metric names for validation."""
    return {
        "service.healthy",
        "service.uptime",
        "service.errors",
        "service.requests",
        "service.error_rate",
        "service.memory.usage",
    }
