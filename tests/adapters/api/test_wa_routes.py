"""Tests for Wise Authority API routes."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, require_authority, require_observer
from ciris_engine.logic.adapters.api.routes.wa import (
    create_wa_success_response,
    get_wa_service,
    raise_wa_error,
    sanitize_for_log,
)
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.api.wa import WAStatusResponse

# ============================================================================
# Fixtures
# ============================================================================


def _make_observer_auth() -> AuthContext:
    """Create observer-level AuthContext for testing."""
    return AuthContext(
        user_id="test-observer",
        role=UserRole.AUTHORITY,
        permissions=set(),
        api_key_id=None,
        authenticated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def wa_client():
    """Create test client with WA service and auth overrides."""
    app = create_app()

    # Override auth dependencies
    app.dependency_overrides[require_observer] = _make_observer_auth
    app.dependency_overrides[require_authority] = _make_observer_auth

    # Mock WA service
    mock_wa = AsyncMock()
    mock_wa.get_pending_deferrals = AsyncMock(return_value=[])
    mock_wa.list_permissions = AsyncMock(return_value=[])
    mock_wa.is_healthy = AsyncMock(return_value=True)
    mock_wa.resolve_deferral = AsyncMock(return_value=True)
    app.state.wise_authority_service = mock_wa

    client = TestClient(app)
    client._mock_wa = mock_wa

    yield client

    app.dependency_overrides.clear()


@pytest.fixture
def wa_client_no_service():
    """Create test client WITHOUT WA service (tests 503 path)."""
    app = create_app()
    app.dependency_overrides[require_observer] = _make_observer_auth
    app.dependency_overrides[require_authority] = _make_observer_auth

    # Explicitly ensure no WA service
    if hasattr(app.state, "wise_authority_service"):
        delattr(app.state, "wise_authority_service")

    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestHelperFunctions:
    """Test wa.py helper functions directly."""

    def test_sanitize_for_log_removes_newlines(self):
        """Test that newlines and tabs are replaced with spaces."""
        assert sanitize_for_log("hello\nworld\ttab\rreturn") == "hello world tab return"

    def test_sanitize_for_log_preserves_printable(self):
        """Test that printable characters are preserved."""
        assert sanitize_for_log("hello world 123") == "hello world 123"

    def test_sanitize_for_log_removes_control_chars(self):
        """Test that non-printable control characters are replaced."""
        result = sanitize_for_log("hello\x00world\x07bell")
        assert "\x00" not in result
        assert "\x07" not in result

    def test_raise_wa_error_500(self):
        """Test raise_wa_error with default 500 status."""
        with pytest.raises(Exception) as exc_info:
            raise_wa_error("Test error")
        assert exc_info.value.status_code == 500

    def test_raise_wa_error_custom_status(self):
        """Test raise_wa_error with custom status code."""
        with pytest.raises(Exception) as exc_info:
            raise_wa_error("Bad request", status_code=400)
        assert exc_info.value.status_code == 400

    def test_create_wa_success_response(self):
        """Test create_wa_success_response wraps data correctly."""
        mock_data = WAStatusResponse(
            service_healthy=True,
            active_was=1,
            pending_deferrals=0,
            deferrals_24h=0,
            average_resolution_time_minutes=0.0,
            timestamp=datetime.now(timezone.utc),
        )
        response = create_wa_success_response(mock_data)
        assert response.data == mock_data
        assert response.metadata is not None
        assert response.metadata.request_id is not None

    def test_get_wa_service_raises_503_when_missing(self):
        """Test get_wa_service raises 503 when service not in app state."""
        mock_request = MagicMock()
        del mock_request.app.state.wise_authority_service  # Ensure attribute missing
        mock_request.app.state.__dict__.pop("wise_authority_service", None)
        mock_request.app.state.configure_mock(**{})
        # hasattr on MagicMock always returns True, so test via endpoint instead
        # (covered by TestServiceUnavailable)


# ============================================================================
# Endpoint Tests - Service Available
# ============================================================================


class TestDeferralsEndpoint:
    """Test GET /deferrals endpoint."""

    def test_list_deferrals_empty(self, wa_client):
        """Test listing deferrals when none exist."""
        response = wa_client.get("/v1/wa/deferrals")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["total"] == 0
        assert data["data"]["deferrals"] == []

    def test_list_deferrals_with_wa_id_filter(self, wa_client):
        """Test listing deferrals with WA ID filter."""
        response = wa_client.get("/v1/wa/deferrals?wa_id=test-wa")
        assert response.status_code == status.HTTP_200_OK
        wa_client._mock_wa.get_pending_deferrals.assert_called_with(wa_id="test-wa")

    def test_list_deferrals_service_error(self, wa_client):
        """Test listing deferrals when service raises exception."""
        wa_client._mock_wa.get_pending_deferrals.side_effect = RuntimeError("DB error")
        response = wa_client.get("/v1/wa/deferrals")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestResolveDeferralEndpoint:
    """Test POST /deferrals/{id}/resolve endpoint."""

    def test_resolve_deferral_success(self, wa_client):
        """Test successful deferral resolution."""
        response = wa_client.post(
            "/v1/wa/deferrals/def-123/resolve",
            json={"resolution": "approve", "guidance": "Approved by WA"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["success"] is True
        assert data["data"]["deferral_id"] == "def-123"

    def test_resolve_deferral_reject(self, wa_client):
        """Test rejecting a deferral."""
        response = wa_client.post(
            "/v1/wa/deferrals/def-456/resolve",
            json={"resolution": "reject", "guidance": "Not appropriate"},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_resolve_deferral_already_resolved(self, wa_client):
        """Test resolving an already-resolved deferral."""
        wa_client._mock_wa.resolve_deferral.return_value = False
        response = wa_client.post(
            "/v1/wa/deferrals/def-789/resolve",
            json={"resolution": "approve", "guidance": "Test"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_resolve_deferral_service_error(self, wa_client):
        """Test resolution when service raises exception."""
        wa_client._mock_wa.resolve_deferral.side_effect = RuntimeError("Service error")
        response = wa_client.post(
            "/v1/wa/deferrals/def-err/resolve",
            json={"resolution": "approve", "guidance": "Test"},
        )
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestPermissionsEndpoint:
    """Test GET /permissions endpoint."""

    def test_get_permissions_default_user(self, wa_client):
        """Test getting permissions for current user."""
        response = wa_client.get("/v1/wa/permissions")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["wa_id"] == "test-observer"

    def test_get_permissions_specific_user(self, wa_client):
        """Test getting permissions for specific WA ID."""
        response = wa_client.get("/v1/wa/permissions?wa_id=other-wa")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["wa_id"] == "other-wa"

    def test_get_permissions_service_error(self, wa_client):
        """Test permissions when service raises exception."""
        wa_client._mock_wa.list_permissions.side_effect = RuntimeError("Error")
        response = wa_client.get("/v1/wa/permissions")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestStatusEndpoint:
    """Test GET /status endpoint."""

    def test_get_status_healthy(self, wa_client):
        """Test getting status when service is healthy."""
        response = wa_client.get("/v1/wa/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["service_healthy"] is True
        assert data["data"]["active_was"] == 1

    def test_get_status_unhealthy(self, wa_client):
        """Test getting status when service is unhealthy."""
        wa_client._mock_wa.is_healthy.return_value = False
        response = wa_client.get("/v1/wa/status")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["data"]["service_healthy"] is False
        assert data["data"]["active_was"] == 0

    def test_get_status_service_error(self, wa_client):
        """Test status when service raises exception."""
        wa_client._mock_wa.is_healthy.side_effect = RuntimeError("Error")
        response = wa_client.get("/v1/wa/status")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGuidanceEndpoint:
    """Test POST /guidance endpoint."""

    def test_guidance_ethical_topic(self, wa_client):
        """Test guidance request with ethical topic."""
        response = wa_client.post(
            "/v1/wa/guidance",
            json={"topic": "Is it ethical to do X?", "context": "Some context"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "Ubuntu" in data["data"]["guidance"]
        assert data["data"]["confidence"] == 0.85

    def test_guidance_technical_topic(self, wa_client):
        """Test guidance request with technical topic."""
        response = wa_client.post(
            "/v1/wa/guidance",
            json={"topic": "Database optimization strategy"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "technical" in data["data"]["guidance"].lower()
        assert data["data"]["confidence"] == 0.75

    def test_guidance_with_urgency(self, wa_client):
        """Test guidance request with urgency field."""
        response = wa_client.post(
            "/v1/wa/guidance",
            json={"topic": "Should we do this?", "urgency": "high"},
        )
        assert response.status_code == status.HTTP_200_OK


# ============================================================================
# Service Unavailable (503) Tests
# ============================================================================


class TestServiceUnavailable:
    """Test 503 responses when WA service is not available."""

    def test_deferrals_503(self, wa_client_no_service):
        """Test deferrals returns 503 when service missing."""
        response = wa_client_no_service.get("/v1/wa/deferrals")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_resolve_503(self, wa_client_no_service):
        """Test resolve returns 503 when service missing."""
        response = wa_client_no_service.post(
            "/v1/wa/deferrals/def-123/resolve",
            json={"resolution": "approve", "guidance": "Test"},
        )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_permissions_503(self, wa_client_no_service):
        """Test permissions returns 503 when service missing."""
        response = wa_client_no_service.get("/v1/wa/permissions")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_status_503(self, wa_client_no_service):
        """Test status returns 503 when service missing."""
        response = wa_client_no_service.get("/v1/wa/status")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_guidance_503(self, wa_client_no_service):
        """Test guidance returns 503 when service missing."""
        response = wa_client_no_service.post(
            "/v1/wa/guidance",
            json={"topic": "Test topic"},
        )
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
