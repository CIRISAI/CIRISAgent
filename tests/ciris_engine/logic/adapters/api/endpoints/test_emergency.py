"""Tests for emergency API endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.endpoints.emergency import get_runtime_service, router
from ciris_engine.schemas.services.shutdown import EmergencyCommandType, EmergencyShutdownStatus, WASignedCommand


@pytest.fixture
def mock_runtime_service() -> MagicMock:
    """Create mock runtime control service."""
    service = MagicMock()
    service.handle_emergency_shutdown = AsyncMock()
    service._kill_switch_config = MagicMock(
        enabled=True,
        root_wa_public_keys=["key1", "key2"],
        trust_tree_depth=3,
        allow_relay=True,
        max_shutdown_time_ms=5000,
        command_expiry_seconds=300,
    )
    return service


@pytest.fixture
def app(mock_runtime_service: MagicMock) -> FastAPI:
    """Create test FastAPI app with emergency router."""
    app = FastAPI()
    app.include_router(router)

    # Override dependency
    app.dependency_overrides[get_runtime_service] = lambda: mock_runtime_service

    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    """Create test client."""
    return TestClient(app)


def create_test_command() -> WASignedCommand:
    """Create a valid WASignedCommand for testing."""
    return WASignedCommand(
        command_id="cmd-123",
        command_type=EmergencyCommandType.SHUTDOWN_NOW,
        wa_id="wa-2024-01-01-ABC123",
        wa_public_key="pubkey-123",
        issued_at=datetime.now(timezone.utc),
        reason="Test emergency shutdown",
        signature="test-signature",
    )


class TestEmergencyShutdownEndpoint:
    """Tests for emergency shutdown endpoint."""

    def test_emergency_shutdown_success(self, client: TestClient, mock_runtime_service: MagicMock) -> None:
        """Test successful emergency shutdown."""
        now = datetime.now(timezone.utc)
        mock_runtime_service.handle_emergency_shutdown.return_value = EmergencyShutdownStatus(
            command_received=now,
            command_verified=True,
            shutdown_initiated=now,
            services_stopped=[],
            data_persisted=True,
            final_message_sent=True,
        )

        command = create_test_command()
        response = client.post("/emergency/shutdown", json=command.model_dump(mode="json"))

        assert response.status_code == 200
        data = response.json()
        assert data["command_verified"] is True
        assert data["shutdown_initiated"] is not None
        mock_runtime_service.handle_emergency_shutdown.assert_called_once()

    def test_emergency_shutdown_verification_failed(self, client: TestClient, mock_runtime_service: MagicMock) -> None:
        """Test emergency shutdown with failed verification."""
        now = datetime.now(timezone.utc)
        mock_runtime_service.handle_emergency_shutdown.return_value = EmergencyShutdownStatus(
            command_received=now,
            command_verified=False,
            verification_error="Invalid signature",
            services_stopped=[],
            data_persisted=False,
            final_message_sent=False,
        )

        command = create_test_command()
        response = client.post("/emergency/shutdown", json=command.model_dump(mode="json"))

        assert response.status_code == 403
        assert "verification failed" in response.json()["detail"].lower()

    def test_emergency_shutdown_service_error(self, client: TestClient, mock_runtime_service: MagicMock) -> None:
        """Test emergency shutdown with service error."""
        mock_runtime_service.handle_emergency_shutdown.side_effect = Exception("Service unavailable")

        command = create_test_command()
        response = client.post("/emergency/shutdown", json=command.model_dump(mode="json"))

        assert response.status_code == 500
        assert "failed" in response.json()["detail"].lower()


class TestKillSwitchStatusEndpoint:
    """Tests for kill switch status endpoint."""

    def test_get_kill_switch_status_configured(self, client: TestClient, mock_runtime_service: MagicMock) -> None:
        """Test getting kill switch status when configured."""
        response = client.get("/emergency/kill-switch/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is True
        assert data["root_wa_count"] == 2
        assert data["trust_tree_depth"] == 3
        assert data["allow_relay"] is True
        assert data["max_shutdown_time_ms"] == 5000
        assert data["command_expiry_seconds"] == 300

    def test_get_kill_switch_status_not_configured(self, client: TestClient, mock_runtime_service: MagicMock) -> None:
        """Test getting kill switch status when not configured."""
        del mock_runtime_service._kill_switch_config

        response = client.get("/emergency/kill-switch/status")

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert "error" in data


class TestGetRuntimeServiceDependency:
    """Tests for get_runtime_service dependency."""

    def test_get_runtime_service_returns_none_by_default(self) -> None:
        """Test that get_runtime_service returns None by default."""
        result = get_runtime_service()
        assert result is None
