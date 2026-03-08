"""Tests for auth.py attestation helper functions."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.auth import (
    _build_attestation_response,
    _get_infra_auth_service,
    _handle_no_cached_attestation,
    _trigger_background_attestation,
)


class TestBuildAttestationResponse:
    """Tests for _build_attestation_response helper."""

    def test_builds_default_response(self):
        """Should build response with default values."""
        result = _build_attestation_response("verified")
        assert result["data"]["attestation_status"] == "verified"
        assert result["data"]["loaded"] is True
        assert result["data"]["error"] is None
        assert result["data"]["max_level"] == 0
        assert result["data"]["level_pending"] is True

    def test_builds_error_response(self):
        """Should build response with error details."""
        result = _build_attestation_response("not_attempted", loaded=False, error="Service unavailable")
        assert result["data"]["attestation_status"] == "not_attempted"
        assert result["data"]["loaded"] is False
        assert result["data"]["error"] == "Service unavailable"

    def test_builds_response_with_level_info(self):
        """Should include level information."""
        result = _build_attestation_response("verified", max_level=3, level_pending=False)
        assert result["data"]["max_level"] == 3
        assert result["data"]["level_pending"] is False


class TestGetInfraAuthService:
    """Tests for _get_infra_auth_service helper."""

    def test_returns_error_when_no_auth_service(self):
        """Should return error when auth_service not in app state."""
        mock_request = MagicMock()
        mock_request.app.state = MagicMock(spec=[])  # No auth_service attr

        service, error_response = _get_infra_auth_service(mock_request)

        assert service is None
        assert error_response is not None
        assert "Authentication service not available" in error_response["data"]["error"]

    def test_returns_error_when_no_infra_auth_service(self):
        """Should return error when _auth_service not in auth_service."""
        mock_request = MagicMock()
        mock_auth_service = MagicMock(spec=[])  # No _auth_service attr
        mock_request.app.state.auth_service = mock_auth_service

        service, error_response = _get_infra_auth_service(mock_request)

        assert service is None
        assert error_response is not None
        assert "Infrastructure authentication service not available" in error_response["data"]["error"]

    def test_returns_error_when_no_attestation_caching(self):
        """Should return error when service lacks attestation caching."""
        mock_request = MagicMock()
        mock_infra_service = MagicMock(spec=[])  # No get_cached_attestation
        mock_auth_service = MagicMock()
        mock_auth_service._auth_service = mock_infra_service
        mock_request.app.state.auth_service = mock_auth_service

        service, error_response = _get_infra_auth_service(mock_request)

        assert service is None
        assert error_response is not None
        assert "Attestation caching not supported" in error_response["data"]["error"]

    def test_returns_service_when_all_available(self):
        """Should return service when all components available."""
        mock_request = MagicMock()
        mock_infra_service = MagicMock()
        mock_infra_service.get_cached_attestation = MagicMock()
        mock_auth_service = MagicMock()
        mock_auth_service._auth_service = mock_infra_service
        mock_request.app.state.auth_service = mock_auth_service

        service, error_response = _get_infra_auth_service(mock_request)

        assert service is mock_infra_service
        assert error_response is None


class TestTriggerBackgroundAttestation:
    """Tests for _trigger_background_attestation helper."""

    def test_returns_false_when_no_run_attestation(self):
        """Should return False when service lacks run_attestation."""
        mock_service = MagicMock(spec=[])  # No run_attestation

        result = _trigger_background_attestation(mock_service)

        assert result is False

    @pytest.mark.asyncio
    async def test_triggers_attestation_successfully(self):
        """Should trigger attestation and return True."""
        mock_service = MagicMock()
        mock_service.run_attestation = AsyncMock()
        mock_service._background_tasks = set()

        # Need event loop for create_task
        result = _trigger_background_attestation(mock_service)

        assert result is True

    @pytest.mark.asyncio
    async def test_force_refresh_invalidates_cache(self):
        """Should invalidate cache when force_refresh=True."""
        mock_service = MagicMock()
        mock_service.run_attestation = AsyncMock()
        mock_service.invalidate_attestation_cache = MagicMock()
        mock_service._background_tasks = set()

        result = _trigger_background_attestation(mock_service, force_refresh=True)

        assert result is True
        mock_service.invalidate_attestation_cache.assert_called_once()

    def test_handles_exception_gracefully(self, caplog):
        """Should return False and log warning on exception."""
        mock_service = MagicMock()
        mock_service.run_attestation = MagicMock(side_effect=RuntimeError("Failed"))

        result = _trigger_background_attestation(mock_service)

        assert result is False
        assert "Failed to trigger attestation" in caplog.text


class TestHandleNoCachedAttestation:
    """Tests for _handle_no_cached_attestation helper."""

    def test_returns_in_progress_when_attestation_running(self):
        """Should return in_progress when attestation already running."""
        mock_service = MagicMock()
        mock_service.is_attestation_in_progress.return_value = True

        result = _handle_no_cached_attestation(mock_service)

        assert result["data"]["attestation_status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_triggers_attestation_when_not_running(self):
        """Should trigger attestation when not in progress."""
        import ciris_engine.logic.adapters.api.routes.auth as auth_module

        # Reset global flag
        original_flag = auth_module._attestation_triggered_from_endpoint
        auth_module._attestation_triggered_from_endpoint = False

        mock_service = MagicMock()
        mock_service.is_attestation_in_progress.return_value = False
        mock_service.run_attestation = AsyncMock()
        mock_service._background_tasks = set()

        try:
            result = _handle_no_cached_attestation(mock_service)
            assert result["data"]["attestation_status"] == "in_progress"
        finally:
            auth_module._attestation_triggered_from_endpoint = original_flag

    def test_returns_in_progress_when_already_triggered(self):
        """Should return in_progress when already triggered previously."""
        import ciris_engine.logic.adapters.api.routes.auth as auth_module

        # Set flag to simulate already triggered
        original_flag = auth_module._attestation_triggered_from_endpoint
        auth_module._attestation_triggered_from_endpoint = True

        mock_service = MagicMock()
        mock_service.is_attestation_in_progress.return_value = False

        try:
            result = _handle_no_cached_attestation(mock_service)
            assert result["data"]["attestation_status"] == "in_progress"
        finally:
            auth_module._attestation_triggered_from_endpoint = original_flag

    def test_returns_not_attempted_when_trigger_fails(self):
        """Should return not_attempted when trigger fails and never triggered."""
        import ciris_engine.logic.adapters.api.routes.auth as auth_module

        original_flag = auth_module._attestation_triggered_from_endpoint
        auth_module._attestation_triggered_from_endpoint = False

        mock_service = MagicMock(spec=["is_attestation_in_progress"])  # No run_attestation
        mock_service.is_attestation_in_progress.return_value = False

        try:
            result = _handle_no_cached_attestation(mock_service)
            assert result["data"]["attestation_status"] == "not_attempted"
            assert "No cached attestation" in result["data"]["error"]
        finally:
            auth_module._attestation_triggered_from_endpoint = original_flag
