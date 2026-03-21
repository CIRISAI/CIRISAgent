"""
Tests for My Data DSAR self-service endpoints.

Covers:
- GET /v1/my-data/lens-identifier - View hashed agent ID
- DELETE /v1/my-data/lens-traces - Request trace deletion from CIRISLens
- GET /v1/my-data/accord-settings - View accord adapter settings
- PUT /v1/my-data/accord-settings - Update accord adapter settings
"""

import hashlib
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.auth import get_current_user
from ciris_engine.logic.adapters.api.models import TokenData


async def _mock_admin_user():
    return TokenData(username="admin", email="admin@ciris.ai", role="ADMIN")


@pytest.fixture
def mock_runtime():
    """Create mock runtime with agent identity."""
    runtime = MagicMock()
    runtime.agent_identity = MagicMock()
    runtime.agent_identity.agent_id = "test-agent-001"
    runtime.adapter_manager = MagicMock()
    # RuntimeAdapterManager uses loaded_adapters, not _adapters
    runtime.adapter_manager.loaded_adapters = {}
    return runtime


@pytest.fixture
def mock_accord_adapter():
    """Create mock accord metrics adapter."""
    adapter = MagicMock()
    adapter.__class__.__name__ = "AccordMetricsAdapter"
    adapter._consent_given = True
    adapter._consent_timestamp = "2026-01-15T10:00:00+00:00"

    svc = MagicMock()
    svc.get_metrics.return_value = {
        "consent_given": True,
        "trace_level": "generic",
        "events_received": 42,
        "events_sent": 38,
        "events_failed": 0,
        "events_queued": 2,
        "last_send_time": "2026-03-20T09:00:00+00:00",
        "traces_active": 1,
        "traces_completed": 37,
        "traces_signed": 37,
        "signer_key_id": "test-key-123",
        "has_signing_key": True,
        "agent_id_hash": hashlib.sha256(b"test-agent-001").hexdigest()[:16],
    }
    svc._endpoint_url = "https://lens.ciris-services-1.ai/lens-api/api/v1"
    adapter.metrics_service = svc

    return adapter


@pytest.fixture
def mock_adapter_instance(mock_accord_adapter):
    """Wrap the mock adapter in an AdapterInstance-like object."""
    instance = MagicMock()
    instance.adapter = mock_accord_adapter
    return instance


@pytest.fixture
def app_with_runtime(mock_runtime, mock_adapter_instance):
    """Create app with mock runtime and accord adapter."""
    app = create_app()
    app.state.runtime = mock_runtime

    # RuntimeAdapterManager stores AdapterInstance objects in loaded_adapters
    mock_runtime.adapter_manager.loaded_adapters = {"accord": mock_adapter_instance}

    app.dependency_overrides[get_current_user] = _mock_admin_user
    return app


@pytest.fixture
def client(app_with_runtime):
    return TestClient(app_with_runtime)


@pytest.fixture
def app_no_adapter(mock_runtime):
    """Create app with runtime but NO accord adapter."""
    app = create_app()
    app.state.runtime = mock_runtime
    mock_runtime.adapter_manager.loaded_adapters = {}
    app.dependency_overrides[get_current_user] = _mock_admin_user
    return app


@pytest.fixture
def client_no_adapter(app_no_adapter):
    return TestClient(app_no_adapter)


@pytest.fixture
def app_no_runtime():
    """Create app with NO runtime at all."""
    app = create_app()
    app.dependency_overrides[get_current_user] = _mock_admin_user
    return app


@pytest.fixture
def client_no_runtime(app_no_runtime):
    return TestClient(app_no_runtime)


class TestLensIdentifier:
    """Test GET /v1/my-data/lens-identifier."""

    def test_returns_agent_id_hash(self, client):
        response = client.get("/v1/my-data/lens-identifier")
        assert response.status_code == 200

        data = response.json()["data"]
        expected_hash = hashlib.sha256(b"test-agent-001").hexdigest()[:16]
        assert data["agent_id_hash"] == expected_hash
        assert data["agent_id"] == "test-agent-001"

    def test_includes_consent_status(self, client):
        response = client.get("/v1/my-data/lens-identifier")
        data = response.json()["data"]
        assert data["consent_given"] is True
        assert data["consent_timestamp"] == "2026-01-15T10:00:00+00:00"

    def test_includes_trace_level(self, client):
        response = client.get("/v1/my-data/lens-identifier")
        data = response.json()["data"]
        assert data["trace_level"] == "generic"

    def test_includes_traces_sent_count(self, client):
        response = client.get("/v1/my-data/lens-identifier")
        data = response.json()["data"]
        assert data["traces_sent"] == 38

    def test_includes_endpoint_url(self, client):
        response = client.get("/v1/my-data/lens-identifier")
        data = response.json()["data"]
        assert "lens.ciris-services-1.ai" in data["endpoint_url"]

    def test_no_runtime_returns_404(self, client_no_runtime):
        response = client_no_runtime.get("/v1/my-data/lens-identifier")
        assert response.status_code == 404

    def test_no_adapter_still_returns_hash(self, client_no_adapter):
        """Even without adapter, should return the hash (user needs it for manual DSAR)."""
        response = client_no_adapter.get("/v1/my-data/lens-identifier")
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["agent_id_hash"] is not None
        assert data["consent_given"] is False

    def test_hash_matches_accord_service_algorithm(self, client):
        """Verify hash is computed identically to AccordMetricsService._anonymize_agent_id."""
        response = client.get("/v1/my-data/lens-identifier")
        data = response.json()["data"]

        # Same algorithm as services.py:545
        expected = hashlib.sha256("test-agent-001".encode()).hexdigest()[:16]
        assert data["agent_id_hash"] == expected


class TestDeleteLensTraces:
    """Test DELETE /v1/my-data/lens-traces."""

    def test_requires_confirmation(self, client):
        response = client.request(
            "DELETE",
            "/v1/my-data/lens-traces",
            json={"confirm": False},
        )
        assert response.status_code == 400

    def test_successful_deletion_request(self, client, mock_accord_adapter):
        """When CIRISLens accepts, no retry is needed."""
        # Patch _send_lens_deletion_request to simulate successful lens response
        with patch(
            "ciris_engine.logic.adapters.api.routes.my_data._send_lens_deletion_request",
            return_value=(True, "CIRISLens accepted the deletion request."),
        ):
            response = client.request(
                "DELETE",
                "/v1/my-data/lens-traces",
                json={"confirm": True, "reason": "Testing deletion"},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["local_consent_revoked"] is True
        assert data["lens_request_accepted"] is True
        # Lens accepted → request_lens_deletion=False (no retry needed)
        mock_accord_adapter.update_consent.assert_called_with(False, request_lens_deletion=False)

    def test_deletion_queues_retry_on_lens_failure(self, client, mock_accord_adapter):
        """When CIRISLens API fails, deletion event should be queued for retry."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.my_data._send_lens_deletion_request",
            return_value=(False, "Could not connect to CIRISLens."),
        ):
            response = client.request(
                "DELETE",
                "/v1/my-data/lens-traces",
                json={"confirm": True},
            )

        assert response.status_code == 200
        data = response.json()["data"]
        assert data["lens_request_accepted"] is False
        # Lens rejected → request_lens_deletion=True (queue for retry)
        mock_accord_adapter.update_consent.assert_called_with(False, request_lens_deletion=True)

    def test_deletion_without_adapter(self, client_no_adapter):
        response = client_no_adapter.request(
            "DELETE",
            "/v1/my-data/lens-traces",
            json={"confirm": True},
        )
        # Should still succeed - just notes no adapter
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["local_consent_revoked"] is False
        assert data["lens_request_accepted"] is False

    def test_no_runtime_returns_404(self, client_no_runtime):
        response = client_no_runtime.request(
            "DELETE",
            "/v1/my-data/lens-traces",
            json={"confirm": True},
        )
        assert response.status_code == 404


class TestAccordSettings:
    """Test GET/PUT /v1/my-data/accord-settings."""

    def test_get_settings(self, client):
        response = client.get("/v1/my-data/accord-settings")
        assert response.status_code == 200

        data = response.json()["data"]
        assert data["consent_given"] is True
        assert data["trace_level"] == "generic"
        assert data["events_sent"] == 38
        assert data["agent_id_hash"] is not None

    def test_get_settings_no_adapter_returns_404(self, client_no_adapter):
        response = client_no_adapter.get("/v1/my-data/accord-settings")
        assert response.status_code == 404

    def test_update_consent(self, client, mock_accord_adapter):
        response = client.put(
            "/v1/my-data/accord-settings",
            json={"consent_given": False},
        )
        assert response.status_code == 200
        mock_accord_adapter.update_consent.assert_called_with(False)

    def test_update_trace_level(self, client, mock_accord_adapter):
        response = client.put(
            "/v1/my-data/accord-settings",
            json={"trace_level": "detailed"},
        )
        assert response.status_code == 200
        assert "trace_level=detailed" in str(response.json()["data"]["changes"])

    def test_invalid_trace_level_rejected(self, client):
        response = client.put(
            "/v1/my-data/accord-settings",
            json={"trace_level": "invalid_level"},
        )
        assert response.status_code == 422  # Pydantic validation

    def test_empty_update_rejected(self, client):
        response = client.put(
            "/v1/my-data/accord-settings",
            json={},
        )
        assert response.status_code == 400

    def test_update_no_adapter_returns_404(self, client_no_adapter):
        response = client_no_adapter.put(
            "/v1/my-data/accord-settings",
            json={"consent_given": True},
        )
        assert response.status_code == 404


class TestHashConsistency:
    """Verify the hash computation stays in sync with the accord metrics service."""

    def test_hash_algorithm_matches_service(self):
        """The hash in my_data.py must produce the same output as services.py."""
        from ciris_engine.logic.adapters.api.routes.my_data import _compute_agent_id_hash

        test_ids = [
            "test-agent-001",
            "echo-speculative-4fc6ru",
            "datum",
            "a" * 100,
            "",
        ]

        for agent_id in test_ids:
            expected = hashlib.sha256(agent_id.encode()).hexdigest()[:16]
            assert _compute_agent_id_hash(agent_id) == expected


class TestConsentRevocationDeletionHook:
    """Test that consent revocation can trigger lens deletion."""

    def test_queue_lens_deletion_on_revoke(self):
        """Test the service method that queues deletion when consent is revoked."""
        from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

        svc = AccordMetricsService.__new__(AccordMetricsService)
        svc._agent_id_hash = "abc123def456"
        svc._event_queue = []

        svc.queue_lens_deletion_on_revoke()

        assert len(svc._event_queue) == 1
        event = svc._event_queue[0]
        assert event["event_type"] == "consent_revoked_deletion_requested"
        assert event["agent_id_hash"] == "abc123def456"
        assert event["deletion_requested"] is True

    def test_queue_deletion_no_agent_id(self):
        """Should not queue if no agent_id_hash is set."""
        from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

        svc = AccordMetricsService.__new__(AccordMetricsService)
        svc._agent_id_hash = None
        svc._event_queue = []

        svc.queue_lens_deletion_on_revoke()

        assert len(svc._event_queue) == 0


class TestLateConsentInitialization:
    """Test that granting consent after start initializes HTTP session + flush."""

    def test_set_consent_true_creates_session(self):
        """set_consent(True) should create HTTP session if none exists."""
        from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

        svc = AccordMetricsService.__new__(AccordMetricsService)
        svc._consent_given = False
        svc._consent_timestamp = None
        svc._session = None
        svc._flush_task = None
        svc._flush_interval = 60.0
        svc._endpoint_url = "https://example.com/api/v1"
        svc._batch_size = 10
        svc._event_queue = []

        mock_session = MagicMock()
        mock_session.closed = False

        # Patch asyncio.get_running_loop (returns mock loop), aiohttp.ClientSession, and asyncio.create_task
        with patch("ciris_adapters.ciris_accord_metrics.services.asyncio.get_running_loop", return_value=MagicMock()):
            with patch("ciris_adapters.ciris_accord_metrics.services.aiohttp.ClientSession", return_value=mock_session):
                with patch("ciris_adapters.ciris_accord_metrics.services.asyncio.create_task") as mock_create_task:
                    mock_create_task.return_value = MagicMock(done=MagicMock(return_value=False))
                    svc.set_consent(True)

        assert svc._consent_given is True
        assert svc._session is mock_session
        # Flush task should have been created
        mock_create_task.assert_called_once()

    def test_set_consent_false_does_not_create_session(self):
        """set_consent(False) should not create an HTTP session."""
        from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

        svc = AccordMetricsService.__new__(AccordMetricsService)
        svc._consent_given = True
        svc._consent_timestamp = None
        svc._session = None
        svc._flush_task = None

        svc.set_consent(False)

        assert svc._consent_given is False
        assert svc._session is None
