"""Critical tests for telemetry API endpoints - v1.4.3 release.

These tests verify:
1. All services MUST be initialized (no graceful degradation)
2. Correct error handling when services are missing
3. Basic functionality of key endpoints
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_admin, require_observer
from ciris_engine.logic.adapters.api.routes.telemetry import router


def override_auth():
    """Override authentication dependency."""
    return Mock(user_id="test_user", role="OBSERVER")


def override_admin_auth():
    """Override admin authentication dependency."""
    return Mock(user_id="test_admin", role="ADMIN")


@pytest.fixture
def fully_initialized_app(complete_api_telemetry_setup):
    """Create app with ALL services properly initialized using centralized fixtures."""
    app = FastAPI()

    # Override auth
    app.dependency_overrides[require_observer] = override_auth
    app.dependency_overrides[require_admin] = override_admin_auth

    # Include router
    app.include_router(router)

    # Use centralized fixtures for telemetry-critical services
    app.state.telemetry_service = complete_api_telemetry_setup["telemetry_service"]
    app.state.visibility_service = complete_api_telemetry_setup["visibility_service"]
    app.state.time_service = complete_api_telemetry_setup["time_service"]
    app.state.resource_monitor = complete_api_telemetry_setup["resource_monitor"]
    app.state.incident_management_service = complete_api_telemetry_setup["incident_management_service"]
    app.state.wise_authority_service = complete_api_telemetry_setup["wise_authority_service"]
    app.state.wise_authority = complete_api_telemetry_setup["wise_authority_service"]  # Alias

    # Other services still use MagicMock (not accessed by overview endpoint)
    app.state.memory_service = MagicMock()
    app.state.config_service = MagicMock()
    app.state.audit_service = MagicMock()
    app.state.audit_service.query_entries = AsyncMock(return_value=[])
    app.state.tsdb_consolidation_service = MagicMock()
    app.state.shutdown_service = MagicMock()
    app.state.initialization_service = MagicMock()
    app.state.authentication_service = MagicMock()
    app.state.database_maintenance_service = MagicMock()
    app.state.secrets_service = MagicMock()
    app.state.adaptive_filter_service = MagicMock()
    app.state.self_observation_service = MagicMock()
    app.state.llm_service = MagicMock()
    app.state.runtime_control_service = MagicMock()
    app.state.task_scheduler = MagicMock()
    app.state.secrets_tool_service = MagicMock()

    return app


@pytest.fixture
def client(fully_initialized_app):
    """Create test client with fully initialized app."""
    return TestClient(fully_initialized_app)


class TestCriticalServiceRequirements:
    """Test that all services MUST be initialized."""

    def test_telemetry_service_required(self, fully_initialized_app):
        """Test that telemetry service is required."""
        fully_initialized_app.state.telemetry_service = None
        client = TestClient(fully_initialized_app)

        response = client.get("/telemetry/overview")
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.json()}")
        assert response.status_code == 503
        assert "Critical system failure" in response.json()["detail"]
        assert "Telemetry service not initialized" in response.json()["detail"]

    def test_time_service_required(self, fully_initialized_app):
        """Test that time service is required for overview."""
        fully_initialized_app.state.time_service = None
        client = TestClient(fully_initialized_app)

        response = client.get("/telemetry/overview")
        assert response.status_code == 503
        assert "Critical system failure" in response.json()["detail"]
        assert "Time service not initialized" in response.json()["detail"]

    def test_resource_monitor_required(self, fully_initialized_app):
        """Test that resource monitor is required for resources endpoint."""
        fully_initialized_app.state.resource_monitor = None
        client = TestClient(fully_initialized_app)

        response = client.get("/telemetry/resources")
        assert response.status_code == 503
        assert "Critical system failure" in response.json()["detail"]
        assert "Resource monitor service not initialized" in response.json()["detail"]

    def test_visibility_service_required_for_traces(self, fully_initialized_app):
        """Test that visibility service is required for traces."""
        fully_initialized_app.state.visibility_service = None
        client = TestClient(fully_initialized_app)

        response = client.get("/telemetry/traces")
        assert response.status_code == 503
        assert "Critical system failure" in response.json()["detail"]
        assert "Visibility service not initialized" in response.json()["detail"]

    def test_audit_service_required_for_logs(self, fully_initialized_app):
        """Test that audit service is required for logs."""
        fully_initialized_app.state.audit_service = None
        client = TestClient(fully_initialized_app)

        response = client.get("/telemetry/logs")
        assert response.status_code == 503
        assert "Critical system failure" in response.json()["detail"]
        assert "Audit service not initialized" in response.json()["detail"]


class TestBasicFunctionality:
    """Test basic functionality with all services initialized."""

    def test_overview_success(self, fully_initialized_app):
        """Test successful overview retrieval."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/overview")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "uptime_seconds" in data
        assert "cognitive_state" in data
        assert "memory_mb" in data
        assert "cpu_percent" in data

    def test_resources_success(self, fully_initialized_app):
        """Test successful resource telemetry retrieval."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/resources")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "current" in data
        assert "limits" in data
        assert "health" in data

        # Verify our bug fixes worked
        assert data["current"]["cpu_percent"] == 45.5
        assert data["current"]["memory_mb"] == 512.0
        assert data["limits"]["max_memory_mb"] == 2048.0
        assert data["health"]["status"] in ["healthy", "warning", "critical"]

    def test_metrics_success(self, fully_initialized_app):
        """Test successful metrics retrieval."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/metrics")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "metrics" in data
        assert "summary" in data

    def test_traces_success(self, fully_initialized_app):
        """Test successful traces retrieval."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/traces")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "traces" in data
        assert "total" in data
        assert "has_more" in data

    def test_logs_success(self, fully_initialized_app):
        """Test successful logs retrieval."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/logs")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "logs" in data
        assert "total" in data  # Changed from total_count to match actual API
        assert "has_more" in data  # Added has_more field


class TestUnifiedEndpoint:
    """Test the unified telemetry endpoint."""

    def test_unified_json_format(self, fully_initialized_app):
        """Test unified endpoint with JSON format."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/unified?format=json")
        assert response.status_code == 200

        data = response.json()
        assert "timestamp" in data
        assert "services" in data

    def test_unified_prometheus_format(self, fully_initialized_app):
        """Test unified endpoint with Prometheus format."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/unified?format=prometheus")
        assert response.status_code == 200

        content = response.text
        assert "# HELP" in content
        assert "# TYPE" in content
        assert "ciris_" in content  # Metrics should be prefixed

    def test_unified_graphite_format(self, fully_initialized_app):
        """Test unified endpoint with Graphite format."""
        client = TestClient(fully_initialized_app)
        response = client.get("/telemetry/unified?format=graphite")
        assert response.status_code == 200

        content = response.text
        assert "ciris." in content


class TestErrorHandling:
    """Test error handling."""

    def test_internal_error_handling(self, fully_initialized_app):
        """Test handling of internal errors."""
        # Make a service method raise an exception
        fully_initialized_app.state.telemetry_service.query_metrics = AsyncMock(side_effect=Exception("Internal error"))
        client = TestClient(fully_initialized_app)

        response = client.get("/telemetry/metrics")
        assert response.status_code == 500

    def test_auth_required(self):
        """Test that authentication is required."""
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/telemetry/overview")
        # Should fail without auth service initialized - returns 500 with "Auth service not initialized"
        assert response.status_code == 500
        assert "Auth service not initialized" in response.json()["detail"]


class TestBugFixes:
    """Test that our bug fixes are working correctly."""

    def test_resource_limits_bug_fixed(self, client):
        """Test that ResourceLimits bug is fixed."""
        # This used to fail with: limits.memory_mb.limit
        response = client.get("/telemetry/resources")
        assert response.status_code == 200

        data = response.json()["data"]
        # Should correctly access max_memory_mb
        assert data["limits"]["max_memory_mb"] == 2048.0

    def test_resource_health_warnings_bug_fixed(self, client):
        """Test that ResourceHealthStatus warnings bug is fixed."""
        # This used to fail when accessing current_usage.warnings directly
        response = client.get("/telemetry/resources")
        assert response.status_code == 200

        data = response.json()["data"]
        # Should have warnings as empty list
        assert "warnings" in data["health"]
        assert isinstance(data["health"]["warnings"], list)
