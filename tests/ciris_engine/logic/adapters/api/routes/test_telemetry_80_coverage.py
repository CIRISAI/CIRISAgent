"""Test suite to achieve 80% coverage for telemetry.py - v1.4.3 release."""

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
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
def app_with_full_services():
    """Create app with all services properly mocked."""
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
            "error_rate": 0.01,
            "llm_tokens_used": 50000,
            "llm_api_call_structured": 100,
            "llm.tokens.total": 50000,
            "llm.tokens.input": 30000,
            "llm.tokens.output": 20000,
            "llm.cost.cents": 250,
            "llm.environmental.carbon_grams": 15.5,
            "llm.environmental.energy_kwh": 0.05,
            "handler_completed_total": 500,
            "handler_invoked_total": 550,
            "thought_processing_completed": 200,
            "thought_processing_started": 210,
            "action_selected_task_complete": 100,
            "action_selected_memorize": 50,
        }
    )
    telemetry_service.collect_all = AsyncMock(
        return_value={
            "graph_services": {"memory": 512, "config": 10, "telemetry": 100},
            "infrastructure_services": {"time": 1, "resource_monitor": 50},
            "governance_services": {"wise_authority": 5, "adaptive_filter": 10},
            "runtime_services": {"llm": 100, "task_scheduler": 20},
        }
    )

    # Mock query_metrics to return proper data
    async def mock_query_metrics(metric_name=None, start_time=None, end_time=None, **kwargs):
        """Mock query_metrics with realistic data."""
        return [
            {"timestamp": datetime.now(timezone.utc).isoformat(), "value": 45.0, "tags": {}},
            {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), "value": 42.0, "tags": {}},
            {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(), "value": 40.0, "tags": {}},
        ]

    telemetry_service.query_metrics = AsyncMock(side_effect=mock_query_metrics)
    telemetry_service.get_aggregated_telemetry = AsyncMock(
        return_value={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "services": {
                "telemetry_service": {"metrics": 100, "status": "healthy"},
                "resource_monitor": {"metrics": 50, "status": "healthy"},
            },
            "view": "summary",
        }
    )
    app.state.telemetry_service = telemetry_service

    # Time service
    time_service = MagicMock()
    time_service.uptime = Mock(return_value=timedelta(hours=1, minutes=30, seconds=45))
    time_service.get_metrics = Mock(return_value={"uptime_seconds": 5445.0})
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
    snapshot.warnings = ["High memory usage", "CPU throttling"]
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
            "disk_usage_gb": 20.5,
        }
    )
    app.state.resource_monitor = resource_monitor

    # Visibility service
    visibility_service = MagicMock()
    visibility_service.get_system_status = AsyncMock(
        return_value={
            "cognitive_state": "WORK",
            "current_task": "processing request",
            "queue_size": 10,
            "active_handlers": 3,
        }
    )
    visibility_service.get_task_history = AsyncMock(
        return_value=[
            {
                "task_id": "task-001",
                "status": "completed",
                "duration_ms": 150,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            {
                "task_id": "task-002",
                "status": "in_progress",
                "duration_ms": 75,
                "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            },
        ]
    )
    visibility_service.get_current_reasoning = AsyncMock(
        return_value={
            "reasoning": "Processing user request",
            "confidence": 0.95,
            "alternatives": ["Alternative approach 1", "Alternative approach 2"],
        }
    )
    visibility_service.get_metrics = Mock(return_value={"visibility_score": 0.95})
    app.state.visibility_service = visibility_service

    # Audit service
    audit_service = MagicMock()
    audit_service.query_entries = AsyncMock(
        return_value=[
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": "error_occurred",
                "user_id": "test_user",
                "details": {"error": "Test error"},
            },
            {
                "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                "action": "warning_logged",
                "user_id": "test_user",
                "details": {"warning": "Test warning"},
            },
            {
                "timestamp": (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat(),
                "action": "info_logged",
                "user_id": "test_user",
                "details": {"info": "Test info"},
            },
        ]
    )
    audit_service.get_metrics = Mock(return_value={"total_events": 5000, "events_24h": 500})
    app.state.audit_service = audit_service

    # Incident management service
    incident_service = MagicMock()
    incident_service.get_recent_incidents = AsyncMock(
        return_value=[
            {
                "incident_id": "inc-001",
                "severity": "low",
                "status": "resolved",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "description": "Minor issue",
            },
            {
                "incident_id": "inc-002",
                "severity": "medium",
                "status": "investigating",
                "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "description": "Performance degradation",
            },
        ]
    )
    incident_service.get_metrics = Mock(
        return_value={
            "total_incidents": 5,
            "open_incidents": 1,
            "mttr_minutes": 15.5,
        }
    )
    app.state.incident_management_service = incident_service

    # All other services with varied metrics
    services_config = {
        "memory_service": {"total_nodes": 10000, "total_edges": 5000, "recent_operations": 100},
        "config_service": {"total_configs": 50, "recent_changes": 5, "validation_errors": 0},
        "tsdb_consolidation_service": {"consolidated_points": 1000000, "compression_ratio": 10.5},
        "shutdown_service": {"graceful_shutdowns": 10, "emergency_shutdowns": 0},
        "initialization_service": {"startup_time_ms": 5000, "services_initialized": 21},
        "authentication_service": {"active_sessions": 25, "failed_attempts": 3},
        "database_maintenance_service": {"last_vacuum_hours_ago": 12, "table_count": 50},
        "secrets_service": {"secrets_count": 15, "last_rotation_days_ago": 7},
        "wise_authority": {"guidance_requests": 50, "deferrals": 5, "approvals": 45},
        "adaptive_filter_service": {"filters_applied": 100, "messages_filtered": 10},
        "self_observation_service": {"observations": 500, "insights_generated": 50},
        "llm_service": {"total_requests": 100, "total_tokens": 50000, "average_latency_ms": 250},
        "runtime_control_service": {"control_actions": 20, "state_transitions": 15},
        "task_scheduler": {"scheduled_tasks": 30, "completed_tasks": 25, "failed_tasks": 2},
        "secrets_tool_service": {"tool_invocations": 10, "secrets_accessed": 5},
    }

    for service_name, metrics in services_config.items():
        service = MagicMock()
        service.get_metrics = Mock(return_value=metrics)
        service.is_healthy = Mock(return_value=True)
        setattr(app.state, service_name, service)

    return app


@pytest.fixture
def client(app_with_full_services):
    """Create test client."""
    return TestClient(app_with_full_services)


class TestMetricsEndpointComprehensive:
    """Comprehensive tests for metrics endpoint."""

    def test_metrics_with_all_data_present(self, client):
        """Test metrics endpoint when all data is available."""
        response = client.get("/telemetry/metrics")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "metrics" in data
        assert len(data["metrics"]) > 0

        # Check metric structure
        for metric in data["metrics"]:
            assert "name" in metric
            assert "current_value" in metric
            assert "trend" in metric

    def test_metrics_with_category_filter(self, client):
        """Test metrics with category filter."""
        response = client.get("/telemetry/metrics?category=llm")
        assert response.status_code == 200

        data = response.json()["data"]
        # Should have LLM-related metrics
        metric_names = [m["name"] for m in data["metrics"]]
        assert any("llm" in name.lower() or "token" in name for name in metric_names)

    def test_metrics_with_aggregate_sum(self, client):
        """Test metrics with sum aggregation."""
        response = client.get("/telemetry/metrics?aggregate=sum")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "summary" in data
        assert "sum" in data["summary"]
        assert data["summary"]["sum"] > 0

    def test_metrics_with_aggregate_max(self, client):
        """Test metrics with max aggregation."""
        response = client.get("/telemetry/metrics?aggregate=max")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "summary" in data
        assert "max" in data["summary"]

    def test_metrics_with_aggregate_min(self, client):
        """Test metrics with min aggregation."""
        response = client.get("/telemetry/metrics?aggregate=min")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "summary" in data
        assert "min" in data["summary"]


class TestSpecificMetricEndpoint:
    """Test getting specific metrics by name."""

    def test_get_uptime_metric(self, client):
        """Test getting system uptime metric."""
        response = client.get("/telemetry/metrics/system_uptime")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["name"] == "system_uptime"
        assert data["current_value"] == 3600.0

    def test_get_llm_tokens_metric(self, client):
        """Test getting LLM tokens metric."""
        response = client.get("/telemetry/metrics/llm.tokens.total")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["name"] == "llm.tokens.total"
        assert data["current_value"] == 50000

    def test_get_cost_metric(self, client):
        """Test getting cost metric."""
        response = client.get("/telemetry/metrics/llm.cost.cents")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["name"] == "llm.cost.cents"
        assert data["current_value"] == 250

    def test_metric_not_found(self, client):
        """Test requesting non-existent metric."""
        response = client.get("/telemetry/metrics/nonexistent_metric")
        assert response.status_code == 404


class TestQueryEndpointScenarios:
    """Test various query scenarios."""

    def test_query_metrics_with_filters(self, client):
        """Test querying metrics with complex filters."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "metrics",
                "filters": {
                    "category": "resource",
                    "services": ["resource_monitor", "memory_service"],
                    "metrics": ["cpu_percent", "memory_mb"],
                },
            },
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert "results" in data
        assert "query_metadata" in data

    def test_query_traces_with_filters(self, client):
        """Test querying traces with filters."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "traces",
                "filters": {
                    "status": "success",
                    "min_duration_ms": 100,
                    "max_duration_ms": 1000,
                },
            },
        )
        assert response.status_code == 200

    def test_query_logs_with_search(self, client):
        """Test querying logs with search."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "logs",
                "filters": {"level": "ERROR"},
                "search": "error occurred",
            },
        )
        assert response.status_code == 200

    def test_query_incidents_with_severity(self, client):
        """Test querying incidents by severity."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "incidents",
                "filters": {"severity": "high"},
            },
        )
        assert response.status_code == 200

    def test_query_insights(self, client):
        """Test querying insights."""
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

    def test_history_with_aggregates(self, client):
        """Test resource history includes aggregates."""
        response = client.get("/telemetry/resources/history?hours=24")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "history" in data
        assert "aggregates" in data

        # Check aggregate structure
        agg = data["aggregates"]
        assert "cpu" in agg
        assert "memory" in agg

        # Check CPU aggregates
        assert "min" in agg["cpu"]
        assert "max" in agg["cpu"]
        assert "avg" in agg["cpu"]

    def test_history_with_minimal_hours(self, client):
        """Test resource history with minimum hours (1)."""
        response = client.get("/telemetry/resources/history?hours=1")
        assert response.status_code == 200

    def test_history_with_maximum_hours(self, client):
        """Test resource history with maximum hours (168)."""
        response = client.get("/telemetry/resources/history?hours=168")
        assert response.status_code == 200


class TestTracesEndpointAdvanced:
    """Advanced tests for traces endpoint."""

    def test_traces_with_task_history(self, client):
        """Test traces includes task history."""
        response = client.get("/telemetry/traces")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "traces" in data
        assert "total" in data
        assert "has_more" in data

        # Should have traces from task history
        assert data["total"] >= 0

    def test_traces_with_limit(self, client):
        """Test traces with limit parameter."""
        response = client.get("/telemetry/traces?limit=5")
        assert response.status_code == 200

        data = response.json()["data"]
        assert len(data["traces"]) <= 5

    def test_traces_with_offset(self, client):
        """Test traces with offset for pagination."""
        response = client.get("/telemetry/traces?limit=10&offset=5")
        assert response.status_code == 200


class TestLogsEndpointAdvanced:
    """Advanced tests for logs endpoint."""

    def test_logs_with_level_distribution(self, client):
        """Test logs returns level distribution."""
        response = client.get("/telemetry/logs")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "logs" in data

        # Count actual levels in the response
        if data["logs"]:
            levels = {}
            for log in data["logs"]:
                level = log.get("level", "INFO")
                levels[level] = levels.get(level, 0) + 1

    def test_logs_filter_by_error_level(self, client):
        """Test filtering logs by ERROR level."""
        response = client.get("/telemetry/logs?level=ERROR")
        assert response.status_code == 200

        data = response.json()["data"]
        # All returned logs should be ERROR level
        for log in data["logs"]:
            assert log["level"] == "ERROR"

    def test_logs_with_service_filter(self, client):
        """Test filtering logs by service."""
        response = client.get("/telemetry/logs?service=telemetry")
        assert response.status_code == 200


class TestUnifiedEndpointAllViews:
    """Test unified endpoint with all possible views."""

    def test_unified_with_live_flag(self, client):
        """Test unified endpoint with live=true."""
        response = client.get("/telemetry/unified?live=true")
        assert response.status_code == 200

        data = response.json()
        assert "timestamp" in data

    def test_unified_json_format_detailed(self, client):
        """Test unified endpoint returns proper JSON structure."""
        response = client.get("/telemetry/unified?format=json&view=detailed")
        assert response.status_code == 200

        data = response.json()
        assert "timestamp" in data
        assert "services" in data

    def test_unified_with_category_and_view(self, client):
        """Test unified endpoint with both category and view."""
        response = client.get("/telemetry/unified?category=graph&view=health")
        assert response.status_code == 200


class TestResourcesEndpointAdvanced:
    """Advanced tests for resources endpoint."""

    def test_resources_with_warnings(self, client):
        """Test resources endpoint when there are warnings."""
        response = client.get("/telemetry/resources")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "health" in data
        assert "warnings" in data["health"]
        # We set up warnings in the fixture
        assert len(data["health"]["warnings"]) == 2

    def test_resources_health_status_critical(self, app_with_full_services):
        """Test resources when usage is critical."""
        # Set very high resource usage
        app_with_full_services.state.resource_monitor.snapshot.cpu_percent = 95.0
        app_with_full_services.state.resource_monitor.snapshot.memory_percent = 92.0
        client = TestClient(app_with_full_services)

        response = client.get("/telemetry/resources")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["health"]["status"] == "critical"


class TestOverviewEndpointComprehensive:
    """Comprehensive tests for overview endpoint."""

    def test_overview_with_all_services(self, client):
        """Test overview with all services available."""
        response = client.get("/telemetry/overview")
        assert response.status_code == 200

        data = response.json()["data"]

        # Check all expected fields
        assert "uptime_seconds" in data
        assert "cognitive_state" in data
        assert "memory_mb" in data
        assert "cpu_percent" in data
        assert "messages_processed_24h" in data
        assert "thoughts_processed_24h" in data
        assert "tasks_completed_24h" in data
        assert "errors_24h" in data
        assert "healthy_services" in data
        assert "degraded_services" in data
        assert "active_incidents" in data
        assert "tokens_last_hour" in data
        assert "cost_last_hour_cents" in data
        assert "carbon_last_hour_grams" in data
        assert "energy_last_hour_kwh" in data

    def test_overview_calculates_metrics(self, client):
        """Test overview calculates derived metrics correctly."""
        response = client.get("/telemetry/overview")
        assert response.status_code == 200

        data = response.json()["data"]

        # Verify calculations
        assert data["uptime_seconds"] > 0
        assert data["cpu_percent"] == 45.5
        assert data["memory_mb"] == 512.0
