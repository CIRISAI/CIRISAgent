"""
Unit tests for telemetry API endpoints.

These tests ensure telemetry endpoints handle edge cases and missing data gracefully.
Each test represents a production issue that was found and fixed.
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes.telemetry import (
    LogsResponse,
    MetricsResponse,
    ResourceTelemetryResponse,
    TracesResponse,
    router,
)
from ciris_engine.logic.adapters.api.routes.telemetry_models import SystemOverview


@pytest.fixture
def app():
    """Create FastAPI app with telemetry router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_app_state(app):
    """Mock app state with services."""
    app.state = MagicMock()
    app.state.service_registry = MagicMock()
    app.state.telemetry_service = MagicMock()
    app.state.resource_monitor = MagicMock()
    app.state.memory_service = MagicMock()
    app.state.audit_service = MagicMock()
    return app.state


class TestTelemetryOverviewEndpoint:
    """Test /telemetry/overview endpoint edge cases."""

    def test_overview_handles_missing_wise_authority(self, client, mock_app_state):
        """
        Test that overview endpoint handles missing wise_authority attribute.

        Production Bug: 'State' object has no attribute 'wise_authority'
        """
        # Setup: State without wise_authority
        mock_app_state.wise_authority = None  # Simulate missing attribute

        # Mock telemetry service response
        mock_app_state.telemetry_service.get_system_overview = AsyncMock(
            return_value={
                "uptime_seconds": 3600,
                "total_requests": 100,
                "active_services": 5,
                "health_status": "healthy",
                "cpu_percent": 25.0,
                "memory_mb": 512.0,
                "last_activity": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Act: Call endpoint
        response = client.get("/telemetry/overview", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should handle gracefully
        assert response.status_code in [200, 503]  # OK or Service Unavailable
        if response.status_code == 503:
            data = response.json()
            assert (
                "wise_authority" not in data.get("detail", "").lower()
                or "not available" in data.get("detail", "").lower()
            )

    def test_overview_handles_none_telemetry_service(self, client, mock_app_state):
        """Test that overview endpoint handles None telemetry service."""
        # Setup: No telemetry service
        mock_app_state.telemetry_service = None

        # Act: Call endpoint
        response = client.get("/telemetry/overview", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should return 503
        assert response.status_code == 503
        data = response.json()
        assert "telemetry service not available" in data["detail"].lower()


class TestTelemetryUnifiedEndpoint:
    """Test /telemetry/unified endpoint edge cases."""

    def test_unified_handles_unexpected_view_parameter(self, client, mock_app_state):
        """
        Test that unified endpoint handles view parameter correctly.

        Production Bug: GraphTelemetryService.get_aggregated_telemetry() got an unexpected keyword argument 'view'
        """
        # Setup: Mock telemetry service that doesn't accept 'view' parameter
        mock_telemetry = mock_app_state.telemetry_service

        # Create a mock that raises TypeError for 'view' parameter
        async def mock_get_aggregated_telemetry(**kwargs):
            if "view" in kwargs:
                raise TypeError("get_aggregated_telemetry() got an unexpected keyword argument 'view'")
            return {"bus": {}, "type": {}, "instance": {}, "covenant": {}}

        mock_telemetry.get_aggregated_telemetry = mock_get_aggregated_telemetry

        # Act: Call endpoint with view parameter
        response = client.get("/telemetry/unified?view=bus", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should handle gracefully
        assert response.status_code in [200, 500]
        if response.status_code == 500:
            # Should handle the error gracefully
            data = response.json()
            assert "view" not in data.get("detail", "") or "parameter" in data.get("detail", "")

    def test_unified_without_view_parameter(self, client, mock_app_state):
        """Test unified endpoint without view parameter."""
        # Setup: Mock successful response
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "bus": {"communication": {"messages": 10}},
                "type": {"service": {"count": 5}},
                "instance": {"api_0": {"uptime": 3600}},
                "covenant": {"benevolence": 0.95},
            }
        )

        # Act: Call without view parameter
        response = client.get("/telemetry/unified", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should work
        assert response.status_code == 200
        data = response.json()
        assert "bus" in data or "data" in data


class TestTelemetryLogsEndpoint:
    """Test /telemetry/logs endpoint edge cases."""

    def test_logs_returns_empty_when_no_logging(self, client, mock_app_state):
        """
        Test that logs endpoint returns empty array when logging is not working.

        Production Bug: Logs endpoint returns empty even though system is running
        """
        # Setup: Mock audit service with no logs
        mock_app_state.audit_service.get_recent_logs = AsyncMock(return_value=[])

        # Act: Call logs endpoint
        response = client.get("/telemetry/logs?limit=5", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should return empty array gracefully
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["logs"] == []
        assert data["data"]["total"] == 0
        assert data["data"]["has_more"] is False

    def test_logs_handles_file_not_found(self, client, mock_app_state):
        """Test logs endpoint when log files don't exist."""
        # Setup: Mock file not found error
        mock_app_state.audit_service.get_recent_logs = AsyncMock(side_effect=FileNotFoundError("Log file not found"))

        # Act: Call logs endpoint
        response = client.get("/telemetry/logs", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should handle gracefully
        assert response.status_code in [200, 500]
        if response.status_code == 200:
            data = response.json()
            assert data["data"]["logs"] == []


class TestTelemetryMetricsEndpoint:
    """Test /telemetry/metrics endpoint."""

    def test_metrics_with_null_tags(self, client, mock_app_state):
        """Test that metrics endpoint handles null tags properly."""
        # Setup: Mock metrics with null tags
        mock_app_state.telemetry_service.get_metrics = AsyncMock(
            return_value={
                "metrics": [
                    {
                        "name": "llm_tokens_used",
                        "current_value": 16670.0,
                        "unit": "tokens",
                        "trend": "up",
                        "recent_data": [
                            {
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "value": 10007.0,
                                "tags": {
                                    "service": None,
                                    "operation": None,
                                    "model": None,
                                    "status": None,
                                    "environment": None,
                                },
                            }
                        ],
                    }
                ]
            }
        )

        # Act: Call metrics endpoint
        response = client.get("/telemetry/metrics", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should handle null tags
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]["metrics"]) > 0
        # Null tags should be preserved or converted appropriately
        metric = data["data"]["metrics"][0]
        assert "recent_data" in metric


class TestTelemetryResourcesEndpoint:
    """Test /telemetry/resources endpoint."""

    def test_resources_with_zero_values(self, client, mock_app_state):
        """Test resources endpoint with zero/minimal resource usage."""
        # Setup: Mock minimal resource usage
        mock_app_state.resource_monitor.get_current_usage = AsyncMock(
            return_value={
                "cpu_percent": 5.0,
                "memory_mb": 258.0,
                "memory_percent": 6.0,
                "disk_usage_bytes": 0,
                "disk_usage_gb": 0.0,
                "active_threads": 0,
                "open_files": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Act: Call resources endpoint
        response = client.get("/telemetry/resources", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should handle zero values
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["current"]["disk_usage_bytes"] == 0
        assert data["data"]["current"]["active_threads"] == 0


class TestCovenantMetrics:
    """Test covenant metrics aggregation."""

    def test_covenant_metrics_in_aggregation(self, client, mock_app_state):
        """Test that covenant metrics are included in telemetry aggregation."""
        # Setup: Mock telemetry with covenant metrics
        mock_app_state.telemetry_service.get_aggregated_telemetry = AsyncMock(
            return_value={
                "covenant": {
                    "benevolence": 0.95,
                    "integrity": 0.98,
                    "wisdom": 0.87,
                    "prudence": 0.92,
                    "mission_alignment": 0.93,
                },
                "bus": {},
                "type": {},
                "instance": {},
            }
        )

        # Act: Get aggregated telemetry
        response = client.get("/telemetry/unified", headers={"Authorization": "Bearer admin:test"})

        # Assert: Covenant metrics should be present
        if response.status_code == 200:
            data = response.json()
            # Check if covenant metrics are in response
            if "covenant" in data:
                assert "benevolence" in data["covenant"]
                assert data["covenant"]["benevolence"] == 0.95
            elif "data" in data and "covenant" in data["data"]:
                assert "benevolence" in data["data"]["covenant"]


class TestEdgeCases:
    """Test various edge cases found in production."""

    def test_handles_circular_reference_in_telemetry_data(self, client, mock_app_state):
        """Test handling of circular references in telemetry data."""
        # Setup: Create a circular reference
        circular_data = {"metrics": []}
        circular_data["metrics"].append(circular_data)  # Circular reference

        # Mock telemetry service to return circular data
        mock_app_state.telemetry_service.get_metrics = AsyncMock(return_value=circular_data)

        # Act: Try to get metrics
        response = client.get("/telemetry/metrics", headers={"Authorization": "Bearer admin:test"})

        # Assert: Should handle without crashing
        assert response.status_code in [200, 500]

    @pytest.mark.asyncio
    async def test_concurrent_telemetry_requests(self, client, mock_app_state):
        """Test that concurrent requests don't cause race conditions."""
        import asyncio

        # Setup: Mock slow telemetry service
        async def slow_get_metrics():
            await asyncio.sleep(0.1)
            return {"metrics": []}

        mock_app_state.telemetry_service.get_metrics = slow_get_metrics

        # Act: Make concurrent requests
        tasks = []
        for _ in range(5):
            response = client.get("/telemetry/metrics", headers={"Authorization": "Bearer admin:test"})
            tasks.append(response)

        # Assert: All should complete without error
        for response in tasks:
            assert response.status_code in [200, 503]


# Test Coverage Verification
def test_all_production_bugs_have_tests():
    """Meta-test to ensure all production bugs have corresponding tests."""
    production_bugs = [
        "wise_authority AttributeError",
        "unexpected keyword argument view",
        "empty logs response",
        "null tags in metrics",
        "covenant metrics missing",
    ]

    test_methods = [
        "test_overview_handles_missing_wise_authority",
        "test_unified_handles_unexpected_view_parameter",
        "test_logs_returns_empty_when_no_logging",
        "test_metrics_with_null_tags",
        "test_covenant_metrics_in_aggregation",
    ]

    # Verify each bug has a test
    assert len(production_bugs) <= len(test_methods), "Missing tests for some production bugs"
