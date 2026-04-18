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

# ============================================================================
# Signing Infrastructure Mocking
# ============================================================================
# The signing key singleton (get_unified_signing_key) requires ciris_verify
# which is not available in unit tests. We mock the fallback hash function
# to prevent hangs during initialization when calling API endpoints.


@pytest.fixture
def mock_signing_key_fallback():
    """Mock the signing key fallback to prevent hangs in tests.

    _compute_agent_id_hash_from_signer() tries to initialize the
    ciris_verify singleton which blocks in test environments.

    This fixture is used by client fixtures that make API calls.
    """
    with patch(
        "ciris_engine.logic.adapters.api.routes.my_data._compute_agent_id_hash_from_signer",
        return_value="mock_test_hash_1234",
    ):
        yield


async def _mock_admin_user():
    return TokenData(username="admin", email="admin@ciris.ai", role="ADMIN")


@pytest.fixture
def my_data_mock_runtime():
    """Create mock runtime with agent identity for my_data tests."""
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
def app_with_runtime(my_data_mock_runtime, mock_adapter_instance):
    """Create app with mock runtime and accord adapter."""
    app = create_app()
    app.state.runtime = my_data_mock_runtime

    # RuntimeAdapterManager stores AdapterInstance objects in loaded_adapters
    my_data_mock_runtime.adapter_manager.loaded_adapters = {"accord": mock_adapter_instance}

    app.dependency_overrides[get_current_user] = _mock_admin_user
    return app


@pytest.fixture
def client(app_with_runtime, mock_signing_key_fallback):
    return TestClient(app_with_runtime)


@pytest.fixture
def app_no_adapter(my_data_mock_runtime):
    """Create app with runtime but NO accord adapter."""
    app = create_app()
    app.state.runtime = my_data_mock_runtime
    my_data_mock_runtime.adapter_manager.loaded_adapters = {}
    app.dependency_overrides[get_current_user] = _mock_admin_user
    return app


@pytest.fixture
def client_no_adapter(app_no_adapter, mock_signing_key_fallback):
    return TestClient(app_no_adapter)


@pytest.fixture
def app_no_runtime():
    """Create app with NO runtime at all."""
    app = create_app()
    app.dependency_overrides[get_current_user] = _mock_admin_user
    return app


@pytest.fixture
def client_no_runtime(app_no_runtime, mock_signing_key_fallback):
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


# =============================================================================
# Additional Helper Function Tests
# =============================================================================


class TestComputeAgentIdHashFromSigner:
    """Test _compute_agent_id_hash_from_signer function."""

    def test_successful_computation(self):
        """Test successful hash computation from signing key."""
        from ciris_engine.logic.adapters.api.routes.my_data import _compute_agent_id_hash_from_signer

        with patch("ciris_engine.logic.audit.signing_protocol.get_unified_signing_key") as mock_get_key:
            mock_key = MagicMock()
            mock_key.public_key_bytes = b"test_public_key_bytes"
            mock_get_key.return_value = mock_key

            result = _compute_agent_id_hash_from_signer()

            # Should be first 16 chars of sha256 hash
            expected = hashlib.sha256(b"test_public_key_bytes").hexdigest()[:16]
            assert result == expected

    def test_exception_returns_unknown(self):
        """Test that exceptions return 'unknown'."""
        from ciris_engine.logic.adapters.api.routes.my_data import _compute_agent_id_hash_from_signer

        with patch("ciris_engine.logic.audit.signing_protocol.get_unified_signing_key") as mock_get_key:
            mock_get_key.side_effect = RuntimeError("No signing key")

            result = _compute_agent_id_hash_from_signer()
            assert result == "unknown"


class TestGetAccordAdapter:
    """Test _get_accord_adapter function."""

    def test_finds_adapter_in_main_runtime_control_service(self):
        """Test finding adapter in main_runtime_control_service."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_accord_adapter

        mock_request = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "AccordMetricsAdapter"

        mock_instance = MagicMock()
        mock_instance.adapter = mock_adapter

        mock_manager = MagicMock()
        mock_manager.loaded_adapters = {"accord": mock_instance}

        mock_request.app.state.main_runtime_control_service = MagicMock()
        mock_request.app.state.main_runtime_control_service.adapter_manager = mock_manager
        mock_request.app.state.runtime_control_service = None
        mock_request.app.state.runtime = None

        result = _get_accord_adapter(mock_request)
        assert result is mock_adapter

    def test_finds_adapter_in_runtime_control_service(self):
        """Test finding adapter in runtime_control_service."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_accord_adapter

        mock_request = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "AccordMetricsAdapter"

        mock_instance = MagicMock()
        mock_instance.adapter = mock_adapter

        mock_manager = MagicMock()
        mock_manager.loaded_adapters = {"ciris_accord_metrics": mock_instance}

        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = MagicMock()
        mock_request.app.state.runtime_control_service.adapter_manager = mock_manager
        mock_request.app.state.runtime = None

        result = _get_accord_adapter(mock_request)
        assert result is mock_adapter

    def test_finds_adapter_in_runtime_adapters(self):
        """Test finding adapter in runtime.adapters (bootstrap adapters)."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_accord_adapter

        mock_request = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "AccordMetricsAdapter"

        # No adapter_manager
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = None

        # But adapter exists in runtime.adapters
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.adapter_manager = None
        mock_request.app.state.runtime.adapters = [mock_adapter]

        result = _get_accord_adapter(mock_request)
        assert result is mock_adapter

    def test_returns_none_when_no_adapter(self):
        """Test returns None when no accord adapter found."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_accord_adapter

        mock_request = MagicMock()

        # Empty loaded_adapters
        mock_manager = MagicMock()
        mock_manager.loaded_adapters = {}

        mock_request.app.state.main_runtime_control_service = MagicMock()
        mock_request.app.state.main_runtime_control_service.adapter_manager = mock_manager
        mock_request.app.state.runtime_control_service = None
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.adapters = []

        result = _get_accord_adapter(mock_request)
        assert result is None

    def test_finds_by_adapter_id_pattern(self):
        """Test finding adapter by adapter_id containing 'accord_metrics'."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_accord_adapter

        mock_request = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.__class__.__name__ = "SomeOtherName"  # Not "AccordMetrics"

        mock_instance = MagicMock()
        mock_instance.adapter = mock_adapter

        mock_manager = MagicMock()
        mock_manager.loaded_adapters = {"ciris_accord_metrics_adapter": mock_instance}

        mock_request.app.state.main_runtime_control_service = MagicMock()
        mock_request.app.state.main_runtime_control_service.adapter_manager = mock_manager
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.adapters = []

        result = _get_accord_adapter(mock_request)
        assert result is mock_adapter


class TestGetAgentId:
    """Test _get_agent_id function."""

    def test_no_runtime_returns_none(self):
        """Test returns None when no runtime."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_agent_id

        mock_request = MagicMock()
        mock_request.app.state.runtime = None

        result = _get_agent_id(mock_request)
        assert result is None

    def test_primary_path_agent_identity(self):
        """Test primary path: runtime.agent_identity.agent_id."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_agent_id

        mock_request = MagicMock()
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.agent_identity = MagicMock()
        mock_request.app.state.runtime.agent_identity.agent_id = "primary-agent-123"

        result = _get_agent_id(mock_request)
        assert result == "primary-agent-123"

    def test_fallback_identity_manager(self):
        """Test fallback to identity_manager.agent_identity."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_agent_id

        mock_request = MagicMock()
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.agent_identity = MagicMock()
        mock_request.app.state.runtime.agent_identity.agent_id = None  # Primary path fails

        mock_request.app.state.runtime.identity_manager = MagicMock()
        mock_request.app.state.runtime.identity_manager.agent_identity = MagicMock()
        mock_request.app.state.runtime.identity_manager.agent_identity.agent_id = "manager-agent-456"

        result = _get_agent_id(mock_request)
        assert result == "manager-agent-456"

    def test_fallback_essential_config(self):
        """Test fallback to essential_config.agent_name."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_agent_id

        mock_request = MagicMock()
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.agent_identity = None
        mock_request.app.state.runtime.identity_manager = None

        mock_request.app.state.runtime.essential_config = MagicMock()
        mock_request.app.state.runtime.essential_config.agent_name = "essential-agent"

        result = _get_agent_id(mock_request)
        assert result == "essential-agent"

    def test_legacy_fallback(self):
        """Test legacy fallback to runtime.agent_id."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_agent_id

        mock_request = MagicMock()
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.agent_identity = None
        mock_request.app.state.runtime.identity_manager = None
        mock_request.app.state.runtime.essential_config = None
        mock_request.app.state.runtime.agent_id = "legacy-agent-789"

        result = _get_agent_id(mock_request)
        assert result == "legacy-agent-789"

    def test_all_fallbacks_fail_returns_none(self):
        """Test returns None when all fallbacks fail."""
        from ciris_engine.logic.adapters.api.routes.my_data import _get_agent_id

        mock_request = MagicMock()
        mock_request.app.state.runtime = MagicMock()
        mock_request.app.state.runtime.agent_identity = None
        mock_request.app.state.runtime.identity_manager = None
        mock_request.app.state.runtime.essential_config = None
        mock_request.app.state.runtime.agent_id = None

        # Mock the signing key fallback to prevent blocking and return no key
        # Patch at the source module since it's imported inside the function
        mock_key = MagicMock()
        mock_key.has_key = False  # Simulate no signing key available
        with patch(
            "ciris_engine.logic.audit.signing_protocol.get_unified_signing_key",
            return_value=mock_key,
        ):
            result = _get_agent_id(mock_request)
            assert result is None


class TestUpdateEnvConsent:
    """Test _update_env_consent function."""

    def test_env_file_not_found(self):
        """Test handling when .env file doesn't exist."""
        import tempfile

        from ciris_engine.logic.adapters.api.routes.my_data import _update_env_consent

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"CIRIS_CONFIG_DIR": tmpdir}):
                # Should not raise, just log warning
                _update_env_consent(True)

    def test_updates_existing_consent(self):
        """Test updating existing CIRIS_ACCORD_METRICS_CONSENT."""
        import tempfile
        from pathlib import Path

        from ciris_engine.logic.adapters.api.routes.my_data import _update_env_consent

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("CIRIS_ACCORD_METRICS_CONSENT=true\nOTHER_VAR=value\n")

            with patch.dict("os.environ", {"CIRIS_CONFIG_DIR": tmpdir}):
                _update_env_consent(False)

            content = env_path.read_text()
            assert "CIRIS_ACCORD_METRICS_CONSENT=false" in content
            assert "OTHER_VAR=value" in content

    def test_adds_consent_if_not_present(self):
        """Test adding consent var if not already present."""
        import tempfile
        from pathlib import Path

        from ciris_engine.logic.adapters.api.routes.my_data import _update_env_consent

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("OTHER_VAR=value\n")

            with patch.dict("os.environ", {"CIRIS_CONFIG_DIR": tmpdir}):
                _update_env_consent(True)

            content = env_path.read_text()
            assert "CIRIS_ACCORD_METRICS_CONSENT=true" in content
            assert "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP=" in content

    def test_updates_timestamp(self):
        """Test that timestamp is updated."""
        import tempfile
        from pathlib import Path

        from ciris_engine.logic.adapters.api.routes.my_data import _update_env_consent

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text(
                "CIRIS_ACCORD_METRICS_CONSENT=false\n" "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP=2020-01-01T00:00:00\n"
            )

            with patch.dict("os.environ", {"CIRIS_CONFIG_DIR": tmpdir}):
                _update_env_consent(True)

            content = env_path.read_text()
            assert "CIRIS_ACCORD_METRICS_CONSENT=true" in content
            # Timestamp should be updated (not 2020)
            assert "2020-01-01" not in content

    def test_updates_process_environment(self):
        """Test that process environment is also updated."""
        import os
        import tempfile
        from pathlib import Path

        from ciris_engine.logic.adapters.api.routes.my_data import _update_env_consent

        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / ".env"
            env_path.write_text("")

            with patch.dict("os.environ", {"CIRIS_CONFIG_DIR": tmpdir}):
                _update_env_consent(True)

                assert os.environ.get("CIRIS_ACCORD_METRICS_CONSENT") == "true"
                assert "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP" in os.environ


class TestSendLensDeletionRequest:
    """Test _send_lens_deletion_request function."""

    @pytest.mark.asyncio
    async def test_no_endpoint_url(self):
        """Test when no endpoint URL is configured."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = None

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", None)
        assert accepted is False
        assert "No CIRISLens endpoint" in message

    @pytest.mark.asyncio
    async def test_session_not_available(self):
        """Test when HTTP session is not available."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"
        mock_service._session = None

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", None)
        assert accepted is False
        assert "session not available" in message

    @pytest.mark.asyncio
    async def test_session_closed(self):
        """Test when HTTP session is closed."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"
        mock_service._session = MagicMock()
        mock_service._session.closed = True

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", None)
        assert accepted is False
        assert "session not available" in message

    @pytest.mark.asyncio
    async def test_successful_200_response(self):
        """Test successful 200 response."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"
        mock_service._signer = None

        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
        mock_service._session = mock_session

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", "Test reason")
        assert accepted is True
        assert "accepted" in message.lower()

    @pytest.mark.asyncio
    async def test_successful_202_response(self):
        """Test successful 202 (queued) response."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"
        mock_service._signer = None

        mock_response = AsyncMock()
        mock_response.status = 202

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
        mock_service._session = mock_session

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", None)
        assert accepted is True
        assert "queued" in message.lower()

    @pytest.mark.asyncio
    async def test_404_no_traces(self):
        """Test 404 response (no traces found)."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"
        mock_service._signer = None

        mock_response = AsyncMock()
        mock_response.status = 404

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
        mock_service._session = mock_session

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", None)
        assert accepted is True  # 404 is considered success (nothing to delete)
        assert "no traces" in message.lower()

    @pytest.mark.asyncio
    async def test_error_response(self):
        """Test error response (non-2xx, non-404)."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"
        mock_service._signer = None

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
        mock_service._session = mock_session

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", None)
        assert accepted is False
        assert "500" in message

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test connection error handling."""
        import aiohttp

        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"
        mock_service._signer = None

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(
            return_value=AsyncMock(
                __aenter__=AsyncMock(side_effect=aiohttp.ClientConnectorError(None, OSError("Connection refused")))
            )
        )
        mock_service._session = mock_session

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", None)
        assert accepted is False
        assert "Could not connect" in message

    @pytest.mark.asyncio
    async def test_signed_request(self):
        """Test that request is signed when signer is available."""
        from ciris_engine.logic.adapters.api.routes.my_data import _send_lens_deletion_request

        mock_service = MagicMock()
        mock_service._endpoint_url = "https://lens.example.com"

        # Setup signer
        mock_unified_key = MagicMock()
        mock_unified_key.sign_base64.return_value = "test_signature_base64"

        mock_signer = MagicMock()
        mock_signer.has_signing_key = True
        mock_signer.key_id = "key-123"
        mock_signer._unified_key = mock_unified_key
        mock_service._signer = mock_signer

        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
        mock_service._session = mock_session

        accepted, message = await _send_lens_deletion_request(mock_service, "abc123", "Test")
        assert accepted is True

        # Verify post was called with signed payload
        call_args = mock_session.post.call_args
        payload = call_args.kwargs.get("json", {})
        assert "signature" in payload
        assert payload["signature"] == "test_signature_base64"
        assert payload["signature_key_id"] == "key-123"


class TestAdapterWithoutMetricsService:
    """Test endpoints with adapter that has no metrics_service."""

    @pytest.fixture
    def mock_adapter_no_metrics(self):
        """Create mock accord adapter without metrics_service."""
        adapter = MagicMock()
        adapter.__class__.__name__ = "AccordMetricsAdapter"
        adapter._consent_given = True
        adapter._consent_timestamp = "2026-01-15T10:00:00+00:00"
        # No metrics_service attribute
        del adapter.metrics_service
        return adapter

    @pytest.fixture
    def app_with_basic_adapter(self, my_data_mock_runtime, mock_adapter_no_metrics):
        """Create app with basic adapter (no metrics_service)."""
        app = create_app()
        app.state.runtime = my_data_mock_runtime

        mock_instance = MagicMock()
        mock_instance.adapter = mock_adapter_no_metrics

        my_data_mock_runtime.adapter_manager.loaded_adapters = {"accord": mock_instance}
        app.dependency_overrides[get_current_user] = _mock_admin_user
        return app

    @pytest.fixture
    def client_basic_adapter(self, app_with_basic_adapter, mock_signing_key_fallback):
        return TestClient(app_with_basic_adapter)

    def test_lens_identifier_with_basic_adapter(self, client_basic_adapter):
        """Test lens identifier endpoint with adapter lacking metrics_service."""
        response = client_basic_adapter.get("/v1/my-data/lens-identifier")
        assert response.status_code == 200
        data = response.json()["data"]
        # Should still work, using fallback hash computation
        assert data["agent_id_hash"] is not None
        assert data["consent_given"] is True


# ============================================================================
# GET /v1/my-data/capacity — CIRIS ratchet proxy
# ============================================================================
#
# The capacity route proxies `/scoring/capacity/{template}` from CIRISLens
# and caches via the shared ContextEnrichmentCache. These tests exercise:
#   - success path with a realistic lens payload
#   - cache hit on the second call (no second HTTP fetch)
#   - 502 mapping when lens returns non-200 / is unreachable
#   - 404 when the runtime can't resolve an agent template
#   - parse-error -> 502 when lens returns a malformed payload
#   - NOT registered as a context enrichment tool (agent never reads score)


_FAKE_LENS_PAYLOAD = {
    "agent_name": "Ally",
    "composite_score": 0.8972,
    "fragility_index": 1.1133,
    "category": "high_capacity",
    "factors": {
        "C": {
            "score": 1.0,
            "components": {"D_identity": 0, "K_contradiction": 0.0},
            "trace_count": 49,
            "confidence": "medium",
        },
        "I_int": {
            "score": 0.9697,
            "components": {"I_chain": 1.0, "I_coverage": 0.9697},
            "trace_count": 145,
            "confidence": "high",
        },
        "R": {
            "score": 1.0,
            "components": {"drift_penalty": 0.0, "trend_direction": "stable"},
            "trace_count": 49,
            "confidence": "high",
        },
        "I_inc": {
            "score": 0.9253,
            "components": {"ECE": 0.0747, "Q_deferral": 1.0},
            "trace_count": 49,
            "confidence": "medium",
        },
        "S": {
            "score": 1.0,
            "components": {"S_base": 1.0, "P_ethical_faculties": 1.0},
            "trace_count": 122,
            "confidence": "high",
        },
    },
    "metadata": {
        "window_start": "2026-04-11T22:20:20+00:00",
        "window_end": "2026-04-18T22:20:20+00:00",
        "total_traces": 145,
        "non_exempt_traces": 49,
    },
    "cache": {"cached": False, "ttl_seconds": 300},
}


@pytest.fixture
def clear_capacity_cache():
    """Reset the enrichment cache so each test starts from a clean miss."""
    from ciris_engine.logic.context.system_snapshot_helpers import get_enrichment_cache

    cache = get_enrichment_cache()
    cache.clear()
    yield cache
    cache.clear()


class TestCapacityEndpoint:
    """GET /v1/my-data/capacity."""

    def test_capacity_success_with_ally_payload(self, client, clear_capacity_cache):
        """Happy path: lens returns a valid Ally payload -> 200 with parsed factors."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.my_data._fetch_capacity_from_lens",
            new=AsyncMock(return_value=_FAKE_LENS_PAYLOAD),
        ):
            response = client.get("/v1/my-data/capacity")

        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        data = body["data"]
        assert data["agent_name"] == "Ally"
        assert data["category"] == "high_capacity"
        assert abs(data["composite_score"] - 0.8972) < 1e-6
        # All five CIRIS factors parsed with scores in [0, 1]
        assert data["factors"]["C"]["score"] == 1.0
        assert abs(data["factors"]["I_int"]["score"] - 0.9697) < 1e-6
        assert data["factors"]["R"]["score"] == 1.0
        assert abs(data["factors"]["I_inc"]["score"] - 0.9253) < 1e-6
        assert data["factors"]["S"]["score"] == 1.0
        # Fresh fetch (not cached)
        assert data["cached"] is False
        assert body["metadata"]["cached"] is False

    def test_capacity_cache_hit_on_second_call(self, client, clear_capacity_cache):
        """Second call within TTL must serve from cache — no second lens fetch."""
        fetch_mock = AsyncMock(return_value=_FAKE_LENS_PAYLOAD)
        with patch(
            "ciris_engine.logic.adapters.api.routes.my_data._fetch_capacity_from_lens",
            new=fetch_mock,
        ):
            first = client.get("/v1/my-data/capacity")
            second = client.get("/v1/my-data/capacity")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["data"]["cached"] is False
        assert second.json()["data"]["cached"] is True
        # The lens should have been hit exactly once despite two API calls.
        assert fetch_mock.await_count == 1

    def test_capacity_bad_gateway_when_lens_raises(self, client, clear_capacity_cache):
        """Lens raising an unexpected exception -> 502."""
        with patch(
            "ciris_engine.logic.adapters.api.routes.my_data._fetch_capacity_from_lens",
            new=AsyncMock(side_effect=RuntimeError("lens unreachable")),
        ):
            response = client.get("/v1/my-data/capacity")

        assert response.status_code == 502
        assert "RuntimeError" in response.json()["detail"]

    def test_capacity_bad_gateway_when_lens_returns_malformed_payload(self, client, clear_capacity_cache):
        """Lens returning a payload missing required fields -> 502."""
        bad_payload = {"agent_name": "Ally"}  # missing factors, composite_score, etc.
        with patch(
            "ciris_engine.logic.adapters.api.routes.my_data._fetch_capacity_from_lens",
            new=AsyncMock(return_value=bad_payload),
        ):
            response = client.get("/v1/my-data/capacity")

        assert response.status_code == 502
        assert "unexpected shape" in response.json()["detail"]

    def test_capacity_404_when_no_agent_identity(self, clear_capacity_cache):
        """When the runtime cannot resolve an agent template, return 404."""
        app = create_app()
        runtime = MagicMock()
        # No agent_identity, no identity_manager, no essential_config — force the
        # signing-key fallback to fail too so _get_agent_id returns None.
        runtime.agent_identity = None
        runtime.identity_manager = None
        runtime.essential_config = None
        runtime.agent_id = None
        app.state.runtime = runtime
        app.dependency_overrides[get_current_user] = _mock_admin_user

        with patch(
            "ciris_engine.logic.audit.signing_protocol.get_unified_signing_key",
            side_effect=RuntimeError("no key"),
        ):
            local_client = TestClient(app)
            response = local_client.get("/v1/my-data/capacity")

        assert response.status_code == 404
        assert "Agent template unavailable" in response.json()["detail"]

    def test_capacity_not_in_context_enrichment_tools(self):
        """Capacity must NOT appear as a context-enrichment tool.

        User-facing readout only — piping a self-grade into the agent's
        reasoning context would invite Goodhart / score-chasing. This test
        locks that down: if someone ever adds `context_enrichment=True`
        to a capacity-producing ToolInfo, the test fails.
        """
        import importlib

        my_data = importlib.import_module("ciris_engine.logic.adapters.api.routes.my_data")
        # Scan the module for any ToolInfo registrations that mention capacity.
        # No ToolInfo in my_data means no registration, which is what we want.
        module_src = (
            "".join(open(my_data.__file__).readlines()) if hasattr(my_data, "__file__") and my_data.__file__ else ""
        )
        assert "context_enrichment=True" not in module_src, (
            "Capacity must not be registered as a context enrichment tool — "
            "it is user-facing only (see CellVizState docstring)."
        )

    def test_capacity_base_url_respects_env_var(self, monkeypatch):
        """`_capacity_base_url` honours the same env var as the accord adapter."""
        from ciris_engine.logic.adapters.api.routes.my_data import _capacity_base_url

        monkeypatch.setenv(
            "CIRIS_ACCORD_METRICS_ENDPOINT",
            "https://lens.example.test/api/v1/",
        )
        # Trailing slash must be stripped so URL joins don't double-slash.
        assert _capacity_base_url() == "https://lens.example.test/api/v1"

        monkeypatch.delenv("CIRIS_ACCORD_METRICS_ENDPOINT", raising=False)
        assert _capacity_base_url() == "https://lens.ciris-services-1.ai/lens-api/api/v1"
