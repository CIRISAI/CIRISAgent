"""Tests for telemetry metrics API routes."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes.telemetry_metrics import router


@pytest.fixture
def mock_telemetry_service() -> MagicMock:
    """Create mock telemetry service."""
    return MagicMock()


@pytest.fixture
def mock_auth_context() -> MagicMock:
    """Create mock auth context."""
    return MagicMock(user_id="test-user", role="observer")


@pytest.fixture
def app(mock_telemetry_service: MagicMock, mock_auth_context: MagicMock) -> FastAPI:
    """Create test FastAPI app with telemetry metrics router."""
    from ciris_engine.logic.adapters.api.dependencies.auth import require_observer

    app = FastAPI()
    app.include_router(router, prefix="/telemetry")

    # Set up app state
    app.state.telemetry_service = mock_telemetry_service

    # Override auth dependency
    app.dependency_overrides[require_observer] = lambda: mock_auth_context

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestGetMetricDetail:
    """Tests for get_metric_detail endpoint."""

    def test_get_known_metric_messages_processed(self, client: TestClient) -> None:
        """Test getting messages_processed metric."""
        response = client.get("/telemetry/metrics/messages_processed")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["metric_name"] == "messages_processed"
        assert data["unit"] == "count"
        assert data["description"] == "Total messages processed"
        assert data["trend"] == "up"
        assert data["current"] == 1543
        assert len(data["history"]) == 6

    def test_get_known_metric_thoughts_generated(self, client: TestClient) -> None:
        """Test getting thoughts_generated metric."""
        response = client.get("/telemetry/metrics/thoughts_generated")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["metric_name"] == "thoughts_generated"
        assert data["unit"] == "count"
        assert data["trend"] == "stable"

    def test_get_known_metric_tokens_consumed(self, client: TestClient) -> None:
        """Test getting tokens_consumed metric."""
        response = client.get("/telemetry/metrics/tokens_consumed")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["metric_name"] == "tokens_consumed"
        assert data["unit"] == "tokens"
        assert data["trend"] == "up"

    def test_get_unknown_metric(self, client: TestClient) -> None:
        """Test getting an unknown metric returns generic response."""
        response = client.get("/telemetry/metrics/unknown_metric")

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["metric_name"] == "unknown_metric"
        assert data["unit"] == "unknown"
        assert data["current"] == 0
        assert data["history"] == []

    def test_metric_history_has_timestamps(self, client: TestClient) -> None:
        """Test that metric history includes ISO timestamps."""
        response = client.get("/telemetry/metrics/messages_processed")

        assert response.status_code == 200
        history = response.json()["data"]["history"]
        assert len(history) > 0
        for point in history:
            assert "timestamp" in point
            assert "value" in point
            # Verify timestamp is ISO format
            assert "T" in point["timestamp"]

    def test_service_not_available(self, app: FastAPI, mock_auth_context: MagicMock) -> None:
        """Test error when telemetry service not available."""
        from ciris_engine.logic.adapters.api.dependencies.auth import require_observer

        # Create new app without telemetry service
        app_no_service = FastAPI()
        app_no_service.include_router(router, prefix="/telemetry")
        app_no_service.dependency_overrides[require_observer] = lambda: mock_auth_context
        # Don't set telemetry_service in app state

        client = TestClient(app_no_service)
        response = client.get("/telemetry/metrics/messages_processed")

        assert response.status_code == 503


class TestMetricModels:
    """Tests for metric Pydantic models."""

    def test_metric_history_point_fields(self, client: TestClient) -> None:
        """Test MetricHistoryPoint has expected fields."""
        response = client.get("/telemetry/metrics/messages_processed")

        history = response.json()["data"]["history"]
        point = history[0]
        assert "timestamp" in point
        assert "value" in point
        assert isinstance(point["value"], (int, float))

    def test_metric_detail_fields(self, client: TestClient) -> None:
        """Test MetricDetail has all expected fields."""
        response = client.get("/telemetry/metrics/messages_processed")

        data = response.json()["data"]
        expected_fields = [
            "metric_name",
            "current",
            "unit",
            "description",
            "trend",
            "hourly_rate",
            "daily_total",
            "history",
            "timestamp",
        ]
        for field in expected_fields:
            assert field in data, f"Missing field: {field}"
