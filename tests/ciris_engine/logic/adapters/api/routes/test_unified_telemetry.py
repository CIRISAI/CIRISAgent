"""Tests for unified telemetry endpoint."""

import json
from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
from ciris_engine.logic.adapters.api.routes.telemetry import router


def override_auth():
    """Override authentication dependency."""
    return Mock()


@pytest.fixture
def app():
    """Create test FastAPI app."""
    app = FastAPI()

    # Override authentication dependency
    app.dependency_overrides[require_observer] = override_auth

    # Router already has /telemetry prefix, don't add another
    app.include_router(router)

    # Mock app state
    app.state.telemetry_service = Mock()
    app.state.memory_service = Mock()
    app.state.llm_service = Mock()
    app.state.audit_service = Mock()
    app.state.config_service = Mock()
    app.state.visibility_service = Mock()
    app.state.time_service = Mock()
    app.state.secrets_service = Mock()
    app.state.resource_monitor = Mock()
    app.state.authentication_service = Mock()
    app.state.wise_authority = Mock()
    app.state.incident_management_service = Mock()
    app.state.tsdb_consolidation_service = Mock()
    app.state.self_observation_service = Mock()
    app.state.adaptive_filter_service = Mock()
    app.state.task_scheduler = Mock()
    app.state.initialization_service = Mock()
    app.state.shutdown_service = Mock()
    app.state.runtime_control = Mock()
    app.state.service_registry = Mock()  # Add for fallback path

    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


class TestUnifiedTelemetryEndpoint:
    """Test unified telemetry endpoint."""

    def test_unified_telemetry_summary_view(self, client, app):
        """Test unified telemetry with summary view."""
        # Mock telemetry service response
        mock_result = {
            "system_healthy": True,
            "services_online": 19,
            "services_total": 21,
            "overall_error_rate": 0.02,
            "overall_uptime_seconds": 3600,
            "performance": {
                "avg_latency_ms": 50,
                "throughput_rps": 100,
            },
            "alerts": [],
            "warnings": ["Memory usage high: 85%"],
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?view=summary")

        assert response.status_code == 200
        data = response.json()
        assert data["system_healthy"] is True
        assert data["services_online"] == 19
        assert data["services_total"] == 21
        assert data["overall_error_rate"] == 0.02
        assert len(data["warnings"]) == 1

    def test_unified_telemetry_health_view(self, client, app):
        """Test unified telemetry with health view."""
        mock_result = {
            "healthy": True,
            "services": {"online": 21, "total": 21},
            "alerts": [],
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?view=health")

        assert response.status_code == 200
        data = response.json()
        assert data["healthy"] is True
        assert data["services"]["online"] == 21

    def test_unified_telemetry_category_filter(self, client, app):
        """Test unified telemetry with category filter."""
        mock_result = {
            "buses": {
                "llm_bus": {"healthy": True, "request_count": 100},
                "memory_bus": {"healthy": True, "query_count": 50},
            },
            "_metadata": {
                "timestamp": datetime.now().isoformat(),
                "view": "operational",
                "category": "buses",
            },
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?view=operational&category=buses")

        assert response.status_code == 200
        data = response.json()
        assert "buses" in data
        assert "llm_bus" in data["buses"]
        assert data["buses"]["llm_bus"]["healthy"] is True

    def test_unified_telemetry_live_collection(self, client, app):
        """Test unified telemetry with live collection."""
        mock_result = {
            "system_healthy": True,
            "services_online": 21,
            "services_total": 21,
            "_metadata": {
                "cached": False,
                "timestamp": datetime.now().isoformat(),
            },
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?live=true")

        assert response.status_code == 200
        data = response.json()
        assert data["_metadata"]["cached"] is False

    def test_unified_telemetry_prometheus_format(self, client, app):
        """Test unified telemetry with Prometheus format."""
        mock_result = {
            "system_healthy": True,
            "services_online": 21,
            "services_total": 21,
            "overall_error_rate": 0.02,
            "overall_uptime_seconds": 3600,
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?format=prometheus")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"

        # Check Prometheus format
        content = response.text
        assert "ciris_system_healthy 1" in content
        assert "ciris_services_online 21" in content
        assert "ciris_services_total 21" in content
        assert "ciris_overall_error_rate 0.02" in content
        assert "ciris_overall_uptime_seconds 3600" in content

    def test_unified_telemetry_graphite_format(self, client, app):
        """Test unified telemetry with Graphite format."""
        mock_result = {
            "system_healthy": True,
            "services_online": 21,
            "services_total": 21,
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?format=graphite")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        # Check Graphite format (metric.path value timestamp)
        content = response.text
        lines = content.split("\n")
        assert any("ciris.system_healthy 1" in line for line in lines)
        assert any("ciris.services_online 21" in line for line in lines)
        # Should have timestamp
        assert all(len(line.split()) == 3 for line in lines if line)

    def test_unified_telemetry_no_fallback_philosophy(self, client, app):
        """Test unified telemetry follows NO FALLBACKS philosophy when service lacks method."""
        # Remove get_aggregated_telemetry method - service exists but lacks required method
        app.state.telemetry_service = Mock(spec=[])

        response = client.get("/telemetry/unified?view=summary")

        # Should return 503 per NO FALLBACKS philosophy - fail fast and loud
        assert response.status_code == 503
        data = response.json()
        assert "NO FALLBACKS" in data["detail"]
        assert "get_aggregated_telemetry" in data["detail"]

    def test_unified_telemetry_service_unavailable(self, client, app):
        """Test unified telemetry when telemetry service is unavailable."""
        app.state.telemetry_service = None

        response = client.get("/telemetry/unified")

        assert response.status_code == 503
        assert "Telemetry service not available" in response.json()["detail"]

    def test_unified_telemetry_error_handling(self, client, app):
        """Test unified telemetry error handling."""
        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(side_effect=Exception("Test error"))

        response = client.get("/telemetry/unified")

        assert response.status_code == 500
        assert "Test error" in response.json()["detail"]


class TestUnifiedTelemetryViews:
    """Test different views of unified telemetry."""

    def test_performance_view(self, client, app):
        """Test performance view."""
        mock_result = {
            "performance": {
                "avg_latency_ms": 45,
                "throughput_rps": 150,
                "token_usage": {"input": 1000, "output": 500},
                "cache_hit_rate": 0.85,
            },
            "error_rate": 0.01,
            "services_online": 21,
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?view=performance")

        assert response.status_code == 200
        data = response.json()
        assert "performance" in data
        assert data["performance"]["avg_latency_ms"] == 45
        assert data["performance"]["cache_hit_rate"] == 0.85

    def test_reliability_view(self, client, app):
        """Test reliability view."""
        mock_result = {
            "uptime_seconds": 86400,
            "error_rate": 0.001,
            "services_healthy": "21/21",
            "circuit_breaker_status": "CLOSED",
            "alerts": [],
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?view=reliability")

        assert response.status_code == 200
        data = response.json()
        assert data["uptime_seconds"] == 86400
        assert data["error_rate"] == 0.001
        assert data["circuit_breaker_status"] == "CLOSED"

    def test_operational_view(self, client, app):
        """Test operational view."""
        mock_result = {
            "system_healthy": True,
            "services_online": 21,
            "services_total": 21,
            "overall_error_rate": 0.02,
            "overall_uptime_seconds": 3600,
            "performance": {"throughput_rps": 100},
            "alerts": ["Circuit breaker OPEN for service X"],
            "warnings": ["High memory usage"],
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?view=operational")

        assert response.status_code == 200
        data = response.json()
        assert data["system_healthy"] is True
        assert len(data["alerts"]) == 1
        assert len(data["warnings"]) == 1

    def test_detailed_view(self, client, app):
        """Test detailed view returns all data."""
        mock_result = {
            "system_healthy": True,
            "services_online": 21,
            "services_total": 21,
            "buses": {
                "llm_bus": {"healthy": True, "request_count": 100},
                "memory_bus": {"healthy": True, "query_count": 50},
            },
            "graph_services": {
                "memory": {"total_nodes": 1000},
                "config": {"config_version": "1.0.0"},
            },
            "infrastructure": {
                "time": {"uptime_seconds": 3600},
                "resource_monitor": {"cpu_percent": 45, "memory_mb": 1024},
            },
            "governance": {
                "wise_authority": {"deferrals_pending": 0},
                "adaptive_filter": {"messages_filtered": 10},
            },
            "runtime": {
                "llm": {"tokens_used": 5000},
                "task_scheduler": {"tasks_completed": 100},
            },
            "performance": {
                "avg_latency_ms": 50,
                "throughput_rps": 100,
            },
            "alerts": [],
            "warnings": [],
        }

        app.state.telemetry_service.get_aggregated_telemetry = AsyncMock(return_value=mock_result)

        response = client.get("/telemetry/unified?view=detailed")

        assert response.status_code == 200
        data = response.json()

        # Detailed view should include everything
        assert "buses" in data
        assert "graph_services" in data
        assert "infrastructure" in data
        assert "governance" in data
        assert "runtime" in data
        assert "performance" in data

        # Check specific nested data
        assert data["buses"]["llm_bus"]["request_count"] == 100
        assert data["infrastructure"]["resource_monitor"]["cpu_percent"] == 45
        assert data["runtime"]["llm"]["tokens_used"] == 5000
