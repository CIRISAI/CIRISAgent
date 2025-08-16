"""Comprehensive test suite for telemetry API to achieve 80% coverage - v1.4.3 release."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI, HTTPException
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
def complete_app():
    """Create app with comprehensive service mocking."""
    app = FastAPI()

    # Override auth
    app.dependency_overrides[require_observer] = override_auth
    app.dependency_overrides[require_admin] = override_admin_auth

    # Include router
    app.include_router(router)

    # Initialize ALL services with comprehensive mocking

    # Telemetry service with all methods
    telemetry_service = MagicMock()
    telemetry_service.get_metrics = Mock(
        return_value={
            "system_uptime": 3600.0,
            "total_requests": 1000,
            "error_count": 10,
            "llm.tokens.total": 50000,
            "llm.cost.cents": 250,
        }
    )
    telemetry_service.collect_all = AsyncMock(
        return_value={
            "graph_services": {"memory": 512, "config": 10},
            "infrastructure_services": {"time": 1, "resource_monitor": 50},
        }
    )
    telemetry_service.query_metrics = AsyncMock(
        return_value=[
            {"timestamp": datetime.now(timezone.utc).isoformat(), "value": 45.0, "tags": {}},
            {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), "value": 42.0, "tags": {}},
        ]
    )
    telemetry_service.get_aggregated_telemetry = AsyncMock(
        return_value={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {
                "telemetry_service": {"metrics": 100, "status": "healthy"},
                "resource_monitor": {"metrics": 50, "status": "healthy"},
            },
        }
    )
    app.state.telemetry_service = telemetry_service

    # Time service
    time_service = MagicMock()
    time_service.uptime = Mock(return_value=timedelta(hours=1))
    time_service.get_metrics = Mock(return_value={"uptime_seconds": 3600.0})
    app.state.time_service = time_service

    # Resource monitor with comprehensive data
    resource_monitor = MagicMock()
    snapshot = MagicMock()
    snapshot.cpu_percent = 45.5
    snapshot.memory_mb = 512.0
    snapshot.memory_percent = 25.0
    snapshot.disk_usage_bytes = 20500000000
    snapshot.active_threads = 50
    snapshot.open_files = 100
    snapshot.timestamp = datetime.now(timezone.utc).isoformat()
    snapshot.warnings = ["High memory usage"]
    resource_monitor.snapshot = snapshot
    resource_monitor.budget = MagicMock(
        max_memory_mb=2048.0,
        max_cpu_percent=100.0,
        max_disk_bytes=100000000000,
    )
    resource_monitor.get_metrics = Mock(
        return_value={
            "cpu_percent": 45.5,
            "memory_mb": 512.0,
        }
    )
    app.state.resource_monitor = resource_monitor

    # Visibility service
    visibility_service = MagicMock()
    visibility_service.get_system_status = AsyncMock(
        return_value={
            "cognitive_state": "WORK",
            "current_task": "processing",
            "queue_size": 10,
        }
    )
    visibility_service.get_task_history = AsyncMock(
        return_value=[{"task_id": "task-1", "status": "completed", "duration_ms": 150}]
    )
    visibility_service.get_current_reasoning = AsyncMock(return_value={"reasoning": "Processing user request"})
    visibility_service.get_metrics = Mock(return_value={"visibility_score": 0.95})
    app.state.visibility_service = visibility_service

    # Audit service
    audit_service = MagicMock()
    audit_service.query_entries = AsyncMock(
        return_value=[
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "test_action",
                "user_id": "test_user",
                "details": {"key": "value"},
            }
        ]
    )
    audit_service.get_metrics = Mock(return_value={"total_events": 5000})
    app.state.audit_service = audit_service

    # Incident management service
    incident_service = MagicMock()
    incident_service.get_recent_incidents = AsyncMock(
        return_value=[
            {
                "incident_id": "inc-1",
                "severity": "low",
                "status": "resolved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ]
    )
    incident_service.get_metrics = Mock(return_value={"total_incidents": 5})
    app.state.incident_management_service = incident_service

    # All other services with basic mocking
    for service_name in [
        "memory_service",
        "config_service",
        "tsdb_consolidation_service",
        "shutdown_service",
        "initialization_service",
        "authentication_service",
        "database_maintenance_service",
        "secrets_service",
        "wise_authority",
        "adaptive_filter_service",
        "self_observation_service",
        "llm_service",
        "runtime_control_service",
        "task_scheduler",
        "secrets_tool_service",
    ]:
        service = MagicMock()
        service.get_metrics = Mock(return_value={f"{service_name}_metric": 100})
        service.is_healthy = Mock(return_value=True)
        setattr(app.state, service_name, service)

    return app


@pytest.fixture
def client(complete_app):
    """Create test client."""
    return TestClient(complete_app)


class TestServiceEndpoint:
    """Test the /services endpoint comprehensively."""

    def test_list_services_success(self, client):
        """Test successful service listing."""
        response = client.get("/telemetry/services")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "services" in data
        assert len(data["services"]) > 0

        # Check service structure
        for service in data["services"]:
            assert "name" in service
            assert "status" in service
            assert "metrics_count" in service

    def test_get_specific_service(self, client):
        """Test getting a specific service's telemetry."""
        response = client.get("/telemetry/services/telemetry_service")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["name"] == "telemetry_service"
        assert "status" in data
        assert "metrics" in data

    def test_service_not_found(self, client):
        """Test requesting non-existent service."""
        response = client.get("/telemetry/services/nonexistent_service")
        assert response.status_code == 404


class TestQueryEndpoint:
    """Test the query endpoint with various scenarios."""

    def test_query_with_metrics_type(self, client):
        """Test query with metrics type."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "metrics",
                "filters": {"category": "resource"},
            },
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert "results" in data

    def test_query_with_traces_type(self, client):
        """Test query with traces type."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "traces",
                "filters": {"status": "success"},
            },
        )
        assert response.status_code == 200

    def test_query_with_logs_type(self, client):
        """Test query with logs type."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "logs",
                "filters": {"level": "ERROR"},
            },
        )
        assert response.status_code == 200

    def test_query_with_incidents_type(self, client):
        """Test query with incidents type."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "incidents",
                "filters": {"severity": "high"},
            },
        )
        assert response.status_code == 200

    def test_query_with_insights_type(self, client):
        """Test query with insights type."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "insights",
                "filters": {},
            },
        )
        assert response.status_code == 200


class TestResourceHistoryEndpoint:
    """Test resource history endpoint."""

    def test_resource_history_default(self, client):
        """Test default resource history (24 hours)."""
        response = client.get("/telemetry/resources/history")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "history" in data
        assert "aggregates" in data

    def test_resource_history_custom_hours(self, client):
        """Test resource history with custom hours."""
        response = client.get("/telemetry/resources/history?hours=48")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "history" in data

    def test_resource_history_max_hours(self, client):
        """Test resource history with maximum hours."""
        response = client.get("/telemetry/resources/history?hours=168")
        assert response.status_code == 200


class TestIncidentsEndpoint:
    """Test incidents endpoint."""

    def test_list_incidents(self, client):
        """Test listing incidents."""
        response = client.get("/telemetry/incidents")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "incidents" in data
        assert "summary" in data

    def test_incidents_with_severity_filter(self, client):
        """Test incidents with severity filter."""
        response = client.get("/telemetry/incidents?severity=high")
        assert response.status_code == 200

    def test_incidents_with_time_range(self, client):
        """Test incidents with time range."""
        start = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        end = datetime.now(timezone.utc).isoformat()
        response = client.get(f"/telemetry/incidents?start_time={start}&end_time={end}")
        assert response.status_code == 200


class TestInsightsEndpoint:
    """Test insights endpoint."""

    def test_get_insights(self, client):
        """Test getting system insights."""
        response = client.get("/telemetry/insights")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "insights" in data
        assert "generated_at" in data

        # Check insight structure
        for insight in data["insights"]:
            assert "category" in insight
            assert "severity" in insight
            assert "message" in insight
            assert "recommendation" in insight


class TestUnifiedEndpointViews:
    """Test unified endpoint with different views."""

    def test_unified_summary_view(self, client):
        """Test unified endpoint with summary view."""
        response = client.get("/telemetry/unified?view=summary")
        assert response.status_code == 200

    def test_unified_health_view(self, client):
        """Test unified endpoint with health view."""
        response = client.get("/telemetry/unified?view=health")
        assert response.status_code == 200

    def test_unified_operational_view(self, client):
        """Test unified endpoint with operational view."""
        response = client.get("/telemetry/unified?view=operational")
        assert response.status_code == 200

    def test_unified_detailed_view(self, client):
        """Test unified endpoint with detailed view."""
        response = client.get("/telemetry/unified?view=detailed")
        assert response.status_code == 200

    def test_unified_performance_view(self, client):
        """Test unified endpoint with performance view."""
        response = client.get("/telemetry/unified?view=performance")
        assert response.status_code == 200

    def test_unified_reliability_view(self, client):
        """Test unified endpoint with reliability view."""
        response = client.get("/telemetry/unified?view=reliability")
        assert response.status_code == 200


class TestUnifiedEndpointCategories:
    """Test unified endpoint with category filters."""

    def test_unified_buses_category(self, client):
        """Test unified endpoint with buses category."""
        response = client.get("/telemetry/unified?category=buses")
        assert response.status_code == 200

    def test_unified_graph_category(self, client):
        """Test unified endpoint with graph category."""
        response = client.get("/telemetry/unified?category=graph")
        assert response.status_code == 200

    def test_unified_infrastructure_category(self, client):
        """Test unified endpoint with infrastructure category."""
        response = client.get("/telemetry/unified?category=infrastructure")
        assert response.status_code == 200

    def test_unified_governance_category(self, client):
        """Test unified endpoint with governance category."""
        response = client.get("/telemetry/unified?category=governance")
        assert response.status_code == 200

    def test_unified_runtime_category(self, client):
        """Test unified endpoint with runtime category."""
        response = client.get("/telemetry/unified?category=runtime")
        assert response.status_code == 200


class TestExportFormats:
    """Test all export formats."""

    def test_export_json(self, client):
        """Test JSON export format."""
        response = client.get("/telemetry/export?format=json")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")

    def test_export_csv(self, client):
        """Test CSV export format."""
        response = client.get("/telemetry/export?format=csv")
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"

    def test_export_prometheus(self, client):
        """Test Prometheus export format."""
        response = client.get("/telemetry/export?format=prometheus")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "# HELP" in response.text
        assert "# TYPE" in response.text

    def test_export_graphite(self, client):
        """Test Graphite export format."""
        response = client.get("/telemetry/export?format=graphite")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]
        assert "ciris." in response.text


class TestMetricsEndpointFilters:
    """Test metrics endpoint with various filters."""

    def test_metrics_filter_by_category(self, client):
        """Test filtering metrics by category."""
        response = client.get("/telemetry/metrics?category=resource")
        assert response.status_code == 200

    def test_metrics_filter_by_service(self, client):
        """Test filtering metrics by service."""
        response = client.get("/telemetry/metrics?service_name=telemetry_service")
        assert response.status_code == 200

    def test_metrics_with_aggregation(self, client):
        """Test metrics with aggregation."""
        response = client.get("/telemetry/metrics?aggregate=avg")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "summary" in data
        assert "avg" in data["summary"]


class TestSpecificMetricEndpoint:
    """Test getting specific metrics."""

    def test_get_specific_metric_success(self, client):
        """Test getting a specific metric that exists."""
        response = client.get("/telemetry/metrics/system_uptime")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["name"] == "system_uptime"
        assert "current_value" in data

    def test_get_llm_tokens_metric(self, client):
        """Test getting LLM tokens metric."""
        response = client.get("/telemetry/metrics/llm.tokens.total")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["name"] == "llm.tokens.total"
        assert data["current_value"] == 50000


class TestTracesEndpointFilters:
    """Test traces endpoint with filters."""

    def test_traces_filter_by_operation(self, client):
        """Test filtering traces by operation."""
        response = client.get("/telemetry/traces?operation=process_request")
        assert response.status_code == 200

    def test_traces_with_duration_filter(self, client):
        """Test filtering traces by duration."""
        response = client.get("/telemetry/traces?min_duration=100&max_duration=1000")
        assert response.status_code == 200

    def test_traces_with_pagination(self, client):
        """Test traces with pagination."""
        response = client.get("/telemetry/traces?limit=5&offset=10")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "has_more" in data


class TestLogsEndpointFilters:
    """Test logs endpoint with various filters."""

    def test_logs_filter_by_logger(self, client):
        """Test filtering logs by logger."""
        response = client.get("/telemetry/logs?logger=telemetry")
        assert response.status_code == 200

    def test_logs_with_search(self, client):
        """Test searching logs."""
        response = client.get("/telemetry/logs?search=error")
        assert response.status_code == 200

    def test_logs_with_multiple_levels(self, client):
        """Test filtering logs by multiple levels."""
        response = client.get("/telemetry/logs?level=ERROR&level=WARNING")
        assert response.status_code == 200


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_telemetry_service(self, complete_app):
        """Test when telemetry service returns empty data."""
        complete_app.state.telemetry_service.get_metrics = Mock(return_value={})
        complete_app.state.telemetry_service.collect_all = AsyncMock(return_value={})
        client = TestClient(complete_app)

        response = client.get("/telemetry/overview")
        assert response.status_code == 200

    def test_service_with_warnings(self, complete_app):
        """Test when resource monitor has warnings."""
        complete_app.state.resource_monitor.snapshot.warnings = ["High memory usage", "CPU throttling detected"]
        client = TestClient(complete_app)

        response = client.get("/telemetry/resources")
        assert response.status_code == 200

        data = response.json()["data"]
        assert len(data["health"]["warnings"]) == 2

    def test_no_incidents(self, complete_app):
        """Test when there are no incidents."""
        complete_app.state.incident_management_service.get_recent_incidents = AsyncMock(return_value=[])
        client = TestClient(complete_app)

        response = client.get("/telemetry/incidents")
        assert response.status_code == 200

        data = response.json()["data"]
        assert len(data["incidents"]) == 0

    def test_malformed_query(self, client):
        """Test malformed query request."""
        response = client.post("/telemetry/query", json={"query_type": "invalid_type", "filters": "not_a_dict"})
        assert response.status_code in [400, 422]


class TestConcurrentAccess:
    """Test concurrent access to endpoints."""

    def test_concurrent_reads(self, client):
        """Test multiple concurrent read operations."""
        import concurrent.futures

        endpoints = [
            "/telemetry/overview",
            "/telemetry/metrics",
            "/telemetry/resources",
            "/telemetry/traces",
            "/telemetry/logs",
        ]

        def fetch_endpoint(endpoint):
            return client.get(endpoint)

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_endpoint, ep) for ep in endpoints]
            results = [f.result() for f in futures]

        # All should succeed
        assert all(r.status_code == 200 for r in results)


class TestLiveCollection:
    """Test live collection feature."""

    def test_live_collection_flag(self, client):
        """Test live=true flag forces fresh collection."""
        # First request (potentially cached)
        response1 = client.get("/telemetry/unified")
        assert response1.status_code == 200

        # Second request with live=true
        response2 = client.get("/telemetry/unified?live=true")
        assert response2.status_code == 200

        # Both should succeed
        data2 = response2.json()
        assert "timestamp" in data2


class TestAdminOnlyEndpoints:
    """Test admin-only endpoints."""

    def test_reset_metrics_requires_admin(self, complete_app):
        """Test that reset metrics requires admin role."""
        # Override with non-admin user
        complete_app.dependency_overrides[require_admin] = lambda: Mock(user_id="user", role="OBSERVER")
        client = TestClient(complete_app)

        response = client.post("/telemetry/reset")
        # Should fail with 403 or similar
        assert response.status_code in [403, 401, 422]
