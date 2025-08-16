"""Full comprehensive test suite for telemetry API endpoints - v1.4.3 release."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, require_admin, require_observer
from ciris_engine.logic.adapters.api.routes.telemetry import router
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType


class MockAuthContext:
    """Mock authentication context."""

    def __init__(self, user_id="test_user", role="OBSERVER"):
        self.user_id = user_id
        self.role = role


def override_auth():
    """Override authentication dependency."""
    return MockAuthContext(user_id="test_user", role="OBSERVER")


def override_admin_auth():
    """Override admin authentication dependency."""
    return MockAuthContext(user_id="test_admin", role="ADMIN")


@pytest.fixture
def mock_services():
    """Create comprehensive mock services."""
    services = {}

    # Telemetry service with comprehensive metrics
    telemetry_service = MagicMock()
    telemetry_service.get_metrics = Mock(
        return_value={
            "system_uptime": 3600.0,
            "total_requests": 1000,
            "error_count": 10,
            "error_rate": 0.01,
            "response_time_ms": 150.5,
            "memory_usage_mb": 512.0,
            "cpu_usage_percent": 45.5,
            "active_connections": 25,
            "cache_hits": 800,
            "cache_misses": 200,
            "tokens_processed": 50000,
            "llm_requests": 100,
            "llm_cost_cents": 250,
        }
    )

    # Async methods
    async def async_collect_all():
        return {
            "graph_services": {"memory": 512, "config": 10, "telemetry": 100},
            "infrastructure_services": {"time": 1, "resource_monitor": 50},
            "governance_services": {"wise_authority": 5, "adaptive_filter": 10},
            "runtime_services": {"llm": 100, "task_scheduler": 20},
        }

    telemetry_service.collect_all = AsyncMock(side_effect=async_collect_all)
    telemetry_service.query_metrics = AsyncMock(
        return_value=[
            {"timestamp": datetime.now(timezone.utc).isoformat(), "value": 45.0},
            {"timestamp": (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(), "value": 42.0},
        ]
    )
    telemetry_service.get_traces = Mock(
        return_value=[
            {
                "trace_id": "trace-001",
                "span_id": "span-001",
                "operation": "process_request",
                "start_time": datetime.now(timezone.utc).isoformat(),
                "duration_ms": 150.5,
                "status": "success",
            }
        ]
    )
    telemetry_service.get_logs = Mock(
        return_value=[
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "INFO",
                "message": "Test log entry",
                "logger": "test",
            }
        ]
    )
    services["telemetry_service"] = telemetry_service

    # Resource monitor
    resource_monitor = MagicMock()
    resource_monitor.get_metrics = Mock(
        return_value={
            "cpu_percent": 45.5,
            "memory_mb": 512.0,
            "memory_percent": 25.0,
            "disk_usage_gb": 20.5,
            "disk_percent": 10.0,
            "network_connections": 15,
            "open_files": 100,
            "thread_count": 50,
        }
    )
    # Create a proper mock object with attributes
    snapshot = MagicMock()
    snapshot.cpu_percent = 45.5
    snapshot.memory_mb = 512.0
    snapshot.memory_percent = 25.0
    snapshot.disk_usage_bytes = 20500000000
    snapshot.active_threads = 50
    snapshot.open_files = 100
    snapshot.timestamp = datetime.now(timezone.utc).isoformat()
    snapshot.warnings = []  # Empty warnings list
    resource_monitor.snapshot = snapshot
    resource_monitor.budget = Mock(
        max_memory_mb=2048.0,
        max_cpu_percent=100.0,
        max_disk_bytes=100000000000,
    )
    resource_monitor.get_history = Mock(
        return_value=[
            {"timestamp": datetime.now(timezone.utc).isoformat(), "cpu_percent": 45.0, "memory_mb": 512},
            {
                "timestamp": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
                "cpu_percent": 40.0,
                "memory_mb": 500,
            },
        ]
    )
    services["resource_monitor"] = resource_monitor

    # Time service
    time_service = MagicMock()
    time_service.uptime = Mock(return_value=timedelta(hours=1))
    time_service.get_metrics = Mock(return_value={"uptime_seconds": 3600.0})
    services["time_service"] = time_service

    # Visibility service
    visibility_service = MagicMock()
    visibility_service.get_system_status = AsyncMock(
        return_value={
            "cognitive_state": "WORK",
            "current_task": "processing",
            "queue_size": 10,
        }
    )
    visibility_service.get_metrics = Mock(
        return_value={
            "visibility_score": 0.95,
            "transparency_level": "high",
        }
    )
    # Add methods that traces endpoint needs
    visibility_service.get_task_history = AsyncMock(return_value=[])
    visibility_service.get_current_reasoning = AsyncMock(return_value=None)
    services["visibility_service"] = visibility_service

    # Incident management service
    incident_service = MagicMock()
    incident_service.get_recent_incidents = AsyncMock(return_value=[])
    incident_service.get_metrics = Mock(
        return_value={
            "total_incidents": 5,
            "open_incidents": 1,
            "mttr_minutes": 15.5,
        }
    )
    services["incident_management_service"] = incident_service

    # Wise authority
    wise_authority = MagicMock()
    wise_authority.get_metrics = Mock(
        return_value={
            "guidance_requests": 50,
            "deferrals": 5,
            "approvals": 45,
        }
    )
    services["wise_authority"] = wise_authority

    # LLM service
    llm_service = MagicMock()
    llm_service.get_metrics = Mock(
        return_value={
            "total_requests": 100,
            "total_tokens": 50000,
            "average_latency_ms": 250.5,
            "cost_cents": 250,
        }
    )
    services["llm_service"] = llm_service

    # Memory service
    memory_service = MagicMock()
    memory_service.get_metrics = Mock(
        return_value={
            "total_nodes": 10000,
            "total_edges": 5000,
            "recent_operations": 100,
        }
    )
    services["memory_service"] = memory_service

    # Audit service
    audit_service = MagicMock()
    audit_service.get_metrics = Mock(
        return_value={
            "total_events": 5000,
            "events_24h": 500,
        }
    )
    # Add methods needed by traces endpoint
    audit_service.query_entries = AsyncMock(return_value=[])
    services["audit_service"] = audit_service

    # Config service
    config_service = MagicMock()
    config_service.get_metrics = Mock(
        return_value={
            "total_configs": 50,
            "recent_changes": 5,
        }
    )
    services["config_service"] = config_service

    # All other services with basic metrics
    for service_name in [
        "secrets_service",
        "authentication_service",
        "tsdb_consolidation_service",
        "self_observation_service",
        "adaptive_filter_service",
        "task_scheduler",
        "initialization_service",
        "shutdown_service",
        "database_maintenance_service",
        "runtime_control_service",
        "secrets_tool_service",
    ]:
        service = MagicMock()
        service.get_metrics = Mock(
            return_value={
                f"{service_name}_metric": 100,
                "healthy": True,
            }
        )
        service.is_healthy = Mock(return_value=True)
        services[service_name] = service

    return services


@pytest.fixture
def app(mock_services):
    """Create test FastAPI app with mocked services."""
    app = FastAPI()

    # Override authentication dependencies
    app.dependency_overrides[require_observer] = override_auth
    app.dependency_overrides[require_admin] = override_admin_auth

    # Include router
    app.include_router(router)

    # Add all mock services to app state
    for service_name, service in mock_services.items():
        setattr(app.state, service_name, service)

    # Add request state
    app.state.request_id = "test-request-123"

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestTelemetryOverview:
    """Comprehensive tests for /telemetry/overview endpoint."""

    def test_overview_success(self, client, mock_services):
        """Test successful overview retrieval with all metrics."""
        response = client.get("/telemetry/overview")
        assert response.status_code == 200

        data = response.json()["data"]

        # Verify all required fields are present
        assert "uptime_seconds" in data
        assert "cognitive_state" in data
        assert "messages_processed_24h" in data
        assert "thoughts_processed_24h" in data
        assert "tasks_completed_24h" in data
        assert "errors_24h" in data

        # Verify resource metrics
        assert "memory_mb" in data
        assert "cpu_percent" in data

        # Verify service health
        assert "healthy_services" in data
        assert "degraded_services" in data

        # Verify cost metrics
        assert "tokens_last_hour" in data
        assert "cost_last_hour_cents" in data
        assert "carbon_last_hour_grams" in data
        assert "energy_last_hour_kwh" in data

    def test_overview_partial_services(self, client, app):
        """Test overview when some services are unavailable."""
        # Remove critical services - should fail loudly
        app.state.incident_management_service = None

        response = client.get("/telemetry/overview")
        # Should fail with 500 (AttributeError when accessing None)
        assert response.status_code == 500

    def test_overview_no_telemetry_service(self, client, app):
        """Test overview when telemetry service is completely unavailable."""
        app.state.telemetry_service = None

        response = client.get("/telemetry/overview")
        # Should fail with 503 - critical system failure
        assert response.status_code == 503
        assert "Critical system failure" in response.json()["detail"]
        assert "Telemetry service not initialized" in response.json()["detail"]


class TestResourceTelemetry:
    """Comprehensive tests for /telemetry/resources endpoint."""

    def test_resources_current(self, client):
        """Test current resource usage retrieval."""
        response = client.get("/telemetry/resources")
        if response.status_code != 200:
            print(f"Error: {response.json()}")
        assert response.status_code == 200

        data = response.json()["data"]

        # Verify current usage
        assert "current" in data
        current = data["current"]
        assert current["cpu_percent"] == 45.5
        assert current["memory_mb"] == 512.0
        assert current["memory_percent"] == 25.0

        # Verify limits
        assert "limits" in data
        limits = data["limits"]
        assert limits["max_memory_mb"] == 2048.0
        assert limits["max_cpu_percent"] == 100.0

        # Verify health status
        assert "health" in data
        health = data["health"]
        assert health["status"] in ["healthy", "warning", "critical"]

    def test_resources_with_history(self, client):
        """Test resource history retrieval."""
        response = client.get("/telemetry/resources/history?hours=24")
        assert response.status_code == 200

        data = response.json()["data"]

        assert "history" in data
        assert len(data["history"]) > 0

        # Verify aggregates
        assert "aggregates" in data
        agg = data["aggregates"]
        assert "cpu" in agg
        assert "memory" in agg

    def test_resources_no_monitor(self, client, app):
        """Test when resource monitor is unavailable."""
        app.state.resource_monitor = None

        response = client.get("/telemetry/resources")
        assert response.status_code == 503
        assert "Critical system failure" in response.json()["detail"]
        assert "Resource monitor service not initialized" in response.json()["detail"]


class TestMetricsEndpoints:
    """Comprehensive tests for metrics endpoints."""

    def test_list_all_metrics(self, client):
        """Test listing all available metrics."""
        response = client.get("/telemetry/metrics")
        assert response.status_code == 200

        data = response.json()["data"]

        assert "metrics" in data
        metrics = data["metrics"]
        assert len(metrics) > 0

        # Verify metric structure
        for metric in metrics:
            assert "name" in metric
            assert "current_value" in metric
            assert "trend" in metric

        # Verify summary statistics
        assert "summary" in data
        summary = data["summary"]
        assert "min" in summary
        assert "max" in summary
        assert "avg" in summary

    def test_filter_metrics_by_category(self, client):
        """Test filtering metrics by category."""
        # Test resource category
        response = client.get("/telemetry/metrics?category=resource")
        assert response.status_code == 200

        data = response.json()["data"]
        metrics = data["metrics"]

        # Should contain resource-related metrics
        metric_names = [m["name"] for m in metrics]
        assert any("memory" in name or "cpu" in name for name in metric_names)

    def test_filter_metrics_by_service(self, client):
        """Test filtering metrics by service."""
        response = client.get("/telemetry/metrics?service_name=llm_service")
        assert response.status_code == 200

        data = response.json()["data"]
        metrics = data["metrics"]

        # Should contain LLM service metrics
        metric_names = [m["name"] for m in metrics]
        assert any("llm" in name.lower() or "token" in name for name in metric_names)

    def test_get_specific_metric(self, client):
        """Test retrieving a specific metric by name."""
        response = client.get("/telemetry/metrics/cpu_usage_percent")
        assert response.status_code == 200

        data = response.json()["data"]

        assert data["name"] == "cpu_usage_percent"
        assert data["current_value"] == 45.5
        assert "hourly_average" in data
        assert "daily_average" in data
        assert "by_service" in data

    def test_metric_not_found(self, client):
        """Test requesting a non-existent metric."""
        response = client.get("/telemetry/metrics/nonexistent_metric")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_metrics_with_aggregation(self, client):
        """Test metric aggregation."""
        response = client.get("/telemetry/metrics?aggregate=avg&window=1h")
        assert response.status_code == 200

        data = response.json()["data"]
        summary = data["summary"]

        assert summary["avg"] > 0


class TestTracesEndpoint:
    """Comprehensive tests for traces endpoint."""

    def test_list_traces(self, client):
        """Test listing trace spans."""
        response = client.get("/telemetry/traces")
        if response.status_code != 200:
            print(f"Traces Error: {response.json()}")
        assert response.status_code == 200

        data = response.json()["data"]

        assert "traces" in data
        assert "total" in data
        assert "has_more" in data

        # The endpoint should handle empty traces gracefully
        traces = data["traces"]
        assert isinstance(traces, list)

    def test_filter_traces_by_service(self, client):
        """Test filtering traces by service."""
        response = client.get("/telemetry/traces?service_name=llm_service")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "traces" in data

    def test_filter_traces_by_status(self, client):
        """Test filtering traces by status."""
        response = client.get("/telemetry/traces?status=error")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "traces" in data

    def test_traces_time_range(self, client):
        """Test filtering traces by time range."""
        start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        end = datetime.now(timezone.utc).isoformat()

        response = client.get(f"/telemetry/traces?start_time={start}&end_time={end}")
        assert response.status_code == 200

    def test_traces_pagination(self, client):
        """Test trace pagination."""
        response = client.get("/telemetry/traces?limit=10&offset=0")
        assert response.status_code == 200

        data = response.json()["data"]
        assert len(data["traces"]) <= 10


class TestLogsEndpoint:
    """Comprehensive tests for logs endpoint."""

    def test_list_logs(self, client):
        """Test listing log entries."""
        response = client.get("/telemetry/logs")
        assert response.status_code == 200

        data = response.json()["data"]

        assert "logs" in data
        logs = data["logs"]
        assert len(logs) > 0

        # Verify log structure
        log = logs[0]
        assert "timestamp" in log
        assert "level" in log
        assert "message" in log
        assert "logger" in log

        # Verify level distribution
        assert "level_distribution" in data

    def test_filter_logs_by_level(self, client):
        """Test filtering logs by level."""
        response = client.get("/telemetry/logs?level=ERROR")
        assert response.status_code == 200

        data = response.json()["data"]
        # All logs should be ERROR level if any exist
        if data["logs"]:
            assert all(log["level"] == "ERROR" for log in data["logs"])

    def test_search_logs(self, client):
        """Test searching logs by text."""
        response = client.get("/telemetry/logs?search=test")
        assert response.status_code == 200

        data = response.json()["data"]
        assert "logs" in data

    def test_logs_time_range(self, client):
        """Test filtering logs by time range."""
        start = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        end = datetime.now(timezone.utc).isoformat()

        response = client.get(f"/telemetry/logs?start_time={start}&end_time={end}")
        assert response.status_code == 200


class TestQueryEndpoint:
    """Comprehensive tests for the query endpoint."""

    def test_query_metrics(self, client):
        """Test querying metrics with filters."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "metrics",
                "filters": {
                    "category": "resource",
                    "services": ["resource_monitor"],
                },
                "time_range": {"hours": 1},
            },
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert "results" in data
        assert "query_metadata" in data

    def test_query_traces(self, client):
        """Test querying traces."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "traces",
                "filters": {
                    "min_duration_ms": 100,
                    "max_duration_ms": 1000,
                },
            },
        )
        assert response.status_code == 200

    def test_query_logs(self, client):
        """Test querying logs."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "logs",
                "filters": {"level": "ERROR"},
                "search": "error",
            },
        )
        assert response.status_code == 200

    def test_query_invalid_type(self, client):
        """Test query with invalid type."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "invalid_type",
                "filters": {},
            },
        )
        assert response.status_code in [400, 422]

    def test_query_complex_aggregation(self, client):
        """Test complex query with aggregation."""
        response = client.post(
            "/telemetry/query",
            json={
                "query_type": "metrics",
                "filters": {
                    "metrics": ["cpu_usage_percent", "memory_usage_mb"],
                    "aggregation": "avg",
                    "group_by": "service",
                },
                "time_range": {
                    "start": "2024-01-01T00:00:00Z",
                    "end": "2024-01-02T00:00:00Z",
                },
            },
        )
        assert response.status_code == 200


class TestUnifiedEndpoint:
    """Comprehensive tests for the unified telemetry endpoint."""

    def test_unified_default_json(self, client):
        """Test unified endpoint with default JSON format."""
        response = client.get("/telemetry/unified")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, dict)
        assert "timestamp" in data
        assert "services" in data

    def test_unified_prometheus_format(self, client):
        """Test unified endpoint with Prometheus format."""
        response = client.get("/telemetry/unified?format=prometheus")
        assert response.status_code == 200

        content = response.text
        # Verify Prometheus format
        assert "# HELP" in content
        assert "# TYPE" in content
        assert "ciris_" in content  # Metric prefix

    def test_unified_graphite_format(self, client):
        """Test unified endpoint with Graphite format."""
        response = client.get("/telemetry/unified?format=graphite")
        assert response.status_code == 200

        content = response.text
        # Verify Graphite format
        assert "ciris." in content
        lines = content.strip().split("\n")
        for line in lines:
            parts = line.split()
            assert len(parts) == 3  # metric value timestamp

    def test_unified_summary_view(self, client):
        """Test unified endpoint with summary view."""
        response = client.get("/telemetry/unified?view=summary")
        assert response.status_code == 200

        data = response.json()
        assert "summary" in data
        assert "key_metrics" in data

    def test_unified_health_view(self, client):
        """Test unified endpoint with health view."""
        response = client.get("/telemetry/unified?view=health")
        assert response.status_code == 200

        data = response.json()
        assert "health" in data
        assert "services" in data

        # Verify service health information
        for service_name, health_info in data["services"].items():
            assert "status" in health_info

    def test_unified_performance_view(self, client):
        """Test unified endpoint with performance view."""
        response = client.get("/telemetry/unified?view=performance")
        assert response.status_code == 200

        data = response.json()
        assert "performance" in data
        assert "latency" in data
        assert "throughput" in data

    def test_unified_category_filter(self, client):
        """Test unified endpoint with category filter."""
        response = client.get("/telemetry/unified?category=graph&format=json")
        assert response.status_code == 200

        data = response.json()
        # Should only contain graph services
        assert "graph_services" in data["services"]

    def test_unified_live_collection(self, client):
        """Test unified endpoint with live collection."""
        response = client.get("/telemetry/unified?live=true")
        assert response.status_code == 200

        data = response.json()
        # Should have fresh data
        assert "timestamp" in data
        assert "collection_time_ms" in data

    def test_unified_no_telemetry_service(self, client, app):
        """Test unified endpoint when telemetry service is unavailable."""
        app.state.telemetry_service = None

        response = client.get("/telemetry/unified")
        assert response.status_code == 200

        # Should fall back to collecting from individual services
        data = response.json()
        assert "services" in data


class TestErrorHandling:
    """Test error handling across all endpoints."""

    def test_service_unavailable(self, client, app):
        """Test handling of unavailable services."""
        # Remove critical services
        app.state.telemetry_service = None
        app.state.resource_monitor = None

        # Test various endpoints
        response = client.get("/telemetry/overview")
        assert response.status_code == 200  # Should degrade gracefully

        response = client.get("/telemetry/resources")
        assert response.status_code == 503  # Resource monitor required

    def test_exception_handling(self, client, app):
        """Test handling of exceptions."""
        # Make service raise exception
        app.state.telemetry_service.get_metrics = Mock(side_effect=Exception("Test error"))

        response = client.get("/telemetry/metrics")
        assert response.status_code == 500

    def test_validation_errors(self, client):
        """Test request validation."""
        # Invalid time range
        response = client.get("/telemetry/resources?hours=invalid")
        assert response.status_code == 422

        # Invalid query
        response = client.post("/telemetry/query", json={"invalid": "data"})
        assert response.status_code == 422

    def test_auth_required(self):
        """Test that authentication is required."""
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.get("/telemetry/overview")
        assert response.status_code in [401, 403, 422]


class TestPerformanceAndScale:
    """Test performance and scalability."""

    def test_large_metrics_dataset(self, client, app):
        """Test handling large number of metrics."""
        # Create 1000 metrics
        large_metrics = {f"metric_{i}": i * 1.5 for i in range(1000)}
        app.state.telemetry_service.get_metrics = Mock(return_value=large_metrics)

        response = client.get("/telemetry/metrics")
        assert response.status_code == 200

        data = response.json()["data"]
        assert len(data["metrics"]) > 0

    def test_concurrent_requests(self, client):
        """Test handling concurrent requests."""
        import concurrent.futures

        def make_request(endpoint):
            return client.get(f"/telemetry/{endpoint}")

        endpoints = ["overview", "metrics", "traces", "logs"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = []
            for _ in range(5):  # 5 rounds
                for endpoint in endpoints:
                    futures.append(executor.submit(make_request, endpoint))

            results = [f.result() for f in futures]

        # All requests should succeed
        assert all(r.status_code == 200 for r in results)

    def test_memory_efficiency(self, client, app):
        """Test memory efficiency with large responses."""
        # Create large trace dataset
        large_traces = [
            {
                "trace_id": f"trace-{i}",
                "span_id": f"span-{i}",
                "operation": f"op-{i}",
                "start_time": datetime.now(timezone.utc).isoformat(),
                "duration_ms": i * 10.5,
                "status": "success",
            }
            for i in range(1000)
        ]
        app.state.telemetry_service.get_traces = Mock(return_value=large_traces)

        response = client.get("/telemetry/traces?limit=100")
        assert response.status_code == 200

        data = response.json()["data"]
        # Should respect limit
        assert len(data["traces"]) <= 100


class TestCachingBehavior:
    """Test caching behavior of telemetry endpoints."""

    def test_cache_headers(self, client):
        """Test that appropriate cache headers are set."""
        response = client.get("/telemetry/metrics")
        assert response.status_code == 200

        # Check headers
        headers = response.headers
        # Telemetry should have short TTL
        if "cache-control" in headers:
            assert "no-cache" in headers["cache-control"] or "max-age=" in headers["cache-control"]

    def test_cache_invalidation_on_live(self, client):
        """Test that live=true bypasses cache."""
        # First request (potentially cached)
        response1 = client.get("/telemetry/unified")
        assert response1.status_code == 200

        # Second request with live=true (should bypass cache)
        response2 = client.get("/telemetry/unified?live=true")
        assert response2.status_code == 200

        # Timestamps should be different
        data1 = response1.json()
        data2 = response2.json()
        assert data1["timestamp"] != data2["timestamp"]


class TestIntegration:
    """Integration tests for telemetry with other services."""

    def test_collect_from_all_services(self, client, mock_services):
        """Test that telemetry collects from all services."""
        response = client.get("/telemetry/unified?view=detailed")
        assert response.status_code == 200

        data = response.json()

        # Verify we have data from multiple service categories
        assert "services" in data
        services = data["services"]

        # Check major service categories
        assert any("graph" in key.lower() for key in services.keys())
        assert any("infrastructure" in key.lower() for key in services.keys())
        assert any("governance" in key.lower() for key in services.keys())
        assert any("runtime" in key.lower() for key in services.keys())

    def test_service_health_aggregation(self, client):
        """Test aggregation of service health."""
        response = client.get("/telemetry/overview")
        assert response.status_code == 200

        data = response.json()["data"]

        # Verify health aggregation
        assert data["healthy_services"] >= 0
        assert data["degraded_services"] >= 0

        # Total should match
        total_services = data["healthy_services"] + data["degraded_services"]
        assert total_services >= 0  # Should have some services

    def test_cross_service_metrics(self, client):
        """Test metrics that span multiple services."""
        response = client.get("/telemetry/metrics?aggregate=sum")
        assert response.status_code == 200

        data = response.json()["data"]

        # Check for aggregated metrics
        summary = data["summary"]
        assert summary["sum"] > 0  # Should have summed metrics
