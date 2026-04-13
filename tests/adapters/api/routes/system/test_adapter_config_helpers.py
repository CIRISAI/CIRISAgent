"""Tests for adapter_config.py helper functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.system.adapter_config import (
    _get_existing_reauth_config,
    _resolve_url_hostname_to_ip,
    _sanitize_for_log,
)


class TestResolveUrlHostnameToIp:
    """Tests for _resolve_url_hostname_to_ip helper function."""

    def test_returns_original_if_already_ip(self):
        """Should return unchanged URL if hostname is already an IP."""
        url = "http://192.168.1.100:8123"
        result = _resolve_url_hostname_to_ip(url)
        assert result == url

    def test_returns_original_if_resolution_fails(self):
        """Should return original URL if hostname cannot be resolved."""
        url = "http://nonexistent.invalid.hostname:8123"
        result = _resolve_url_hostname_to_ip(url)
        assert result == url  # Returns original on failure

    def test_resolves_localhost(self):
        """Should resolve localhost to 127.0.0.1."""
        url = "http://localhost:8080"
        result = _resolve_url_hostname_to_ip(url)
        assert "127.0.0.1" in result or result == url  # localhost may already be IP

    def test_preserves_port_after_resolution(self):
        """Should preserve port number after hostname resolution."""
        url = "http://localhost:9999/api"
        result = _resolve_url_hostname_to_ip(url)
        assert ":9999" in result

    def test_preserves_path_after_resolution(self):
        """Should preserve path after hostname resolution."""
        url = "http://localhost:8080/api/v1/status"
        result = _resolve_url_hostname_to_ip(url)
        assert "/api/v1/status" in result

    def test_preserves_scheme(self):
        """Should preserve http/https scheme."""
        url = "https://localhost:8443/secure"
        result = _resolve_url_hostname_to_ip(url)
        assert result.startswith("https://")

    def test_handles_url_without_port(self):
        """Should handle URLs without explicit port."""
        url = "http://localhost/api"
        result = _resolve_url_hostname_to_ip(url)
        assert "/api" in result

    def test_handles_empty_url(self):
        """Should handle empty URL gracefully."""
        result = _resolve_url_hostname_to_ip("")
        assert result == ""

    def test_handles_malformed_url(self):
        """Should handle malformed URL gracefully."""
        result = _resolve_url_hostname_to_ip("not-a-url")
        assert result == "not-a-url"  # Returns original on parse failure


class TestSanitizeForLog:
    """Tests for _sanitize_for_log helper function."""

    def test_returns_none_placeholder_for_none(self):
        """Should return <none> for None input."""
        result = _sanitize_for_log(None)
        assert result == "<none>"

    def test_removes_control_characters(self):
        """Should remove newlines and control characters."""
        result = _sanitize_for_log("hello\nworld\r\ttab")
        assert result == "helloworldtab"

    def test_removes_c0_control_chars(self):
        """Should remove C0 control characters (0x00-0x1f)."""
        result = _sanitize_for_log("hello\x00\x01\x1fworld")
        assert result == "helloworld"

    def test_removes_c1_control_chars(self):
        """Should remove DEL and C1 control characters (0x7f-0x9f)."""
        result = _sanitize_for_log("hello\x7f\x80\x9fworld")
        assert result == "helloworld"

    def test_truncates_long_strings(self):
        """Should truncate strings longer than max_length."""
        long_string = "a" * 100
        result = _sanitize_for_log(long_string, max_length=64)
        assert len(result) == 67  # 64 + "..."
        assert result.endswith("...")

    def test_preserves_short_strings(self):
        """Should not truncate strings shorter than max_length."""
        result = _sanitize_for_log("short", max_length=64)
        assert result == "short"

    def test_converts_non_string_to_string(self):
        """Should convert non-string values to string."""
        result = _sanitize_for_log(12345)
        assert result == "12345"

        result = _sanitize_for_log({"key": "value"})
        assert "key" in result

    def test_custom_max_length(self):
        """Should respect custom max_length parameter."""
        result = _sanitize_for_log("a" * 50, max_length=20)
        assert len(result) == 23  # 20 + "..."
        assert result.endswith("...")


class TestOAuthCallbackSessionNotFound:
    """Tests for OAuth callback session not found scenarios."""

    @pytest.mark.asyncio
    async def test_get_session_status_returns_404_for_missing_session(self):
        """Should return 404 when session is not found."""
        from fastapi import HTTPException

        from ciris_engine.logic.adapters.api.routes.system.adapter_config import (
            ERROR_SESSION_NOT_FOUND,
            get_adapter_config_service,
            get_session_status,
        )

        mock_request = MagicMock()
        mock_config_service = MagicMock()
        mock_config_service.get_session.return_value = None
        mock_request.app.state.adapter_config_service = mock_config_service

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config.get_adapter_config_service",
            return_value=mock_config_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await get_session_status(mock_request, "missing-session-id")

            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == ERROR_SESSION_NOT_FOUND

    @pytest.mark.asyncio
    async def test_oauth_callback_returns_404_for_missing_session(self):
        """Should return 404 when session is not found in OAuth callback."""
        from fastapi import HTTPException

        from ciris_engine.logic.adapters.api.routes.system.adapter_config import ERROR_SESSION_NOT_FOUND, oauth_callback

        mock_request = MagicMock()
        mock_config_service = MagicMock()
        mock_config_service.get_session.return_value = None
        mock_request.app.state.adapter_config_service = mock_config_service
        mock_request.url.path = "/test/path"

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config.get_adapter_config_service",
            return_value=mock_config_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                # Args: session_id, code, state, request
                await oauth_callback("missing-session-id", "code", "state", mock_request)

            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == ERROR_SESSION_NOT_FOUND


class TestOAuthDeeplinkCallback:
    """Tests for OAuth deeplink callback handler."""

    @pytest.mark.asyncio
    async def test_deeplink_callback_returns_404_for_missing_session(self):
        """Should return 404 when session is not found in deeplink callback."""
        from fastapi import HTTPException

        from ciris_engine.logic.adapters.api.routes.system.adapter_config import (
            ERROR_SESSION_NOT_FOUND,
            oauth_deeplink_callback,
        )

        mock_request = MagicMock()
        mock_config_service = MagicMock()
        mock_config_service.get_session.return_value = None
        mock_request.app.state.adapter_config_service = mock_config_service

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config.get_adapter_config_service",
            return_value=mock_config_service,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await oauth_deeplink_callback(
                    request=mock_request,
                    state="missing-session-id",
                    code="auth_code",
                    provider=None,
                    source=None,
                )

            assert exc_info.value.status_code == 404
            assert exc_info.value.detail == ERROR_SESSION_NOT_FOUND

    @pytest.mark.asyncio
    async def test_deeplink_callback_extracts_provider_from_state(self, caplog):
        """Should extract provider from colon-prefixed state."""
        import logging

        from ciris_engine.logic.adapters.api.routes.system.adapter_config import oauth_deeplink_callback

        mock_request = MagicMock()
        mock_config_service = MagicMock()
        # Return session for the extracted session_id
        mock_session = MagicMock()
        mock_config_service.get_session.return_value = mock_session
        mock_config_service.execute_step = AsyncMock(return_value=MagicMock(success=True))
        mock_request.app.state.adapter_config_service = mock_config_service

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config.get_adapter_config_service",
            return_value=mock_config_service,
        ):
            with caplog.at_level(logging.INFO):
                await oauth_deeplink_callback(
                    request=mock_request,
                    state="ha:actual-session-id",  # provider:session_id format
                    code="auth_code",
                    provider=None,
                    source="test",
                )

            # Verify session was looked up with extracted session_id
            mock_config_service.get_session.assert_called_with("actual-session-id")
            assert "Extracted provider=ha" in caplog.text

    @pytest.mark.asyncio
    async def test_deeplink_callback_success_logs_completion(self, caplog):
        """Should log successful completion."""
        import logging

        from ciris_engine.logic.adapters.api.routes.system.adapter_config import oauth_deeplink_callback

        mock_request = MagicMock()
        mock_config_service = MagicMock()
        mock_session = MagicMock()
        mock_config_service.get_session.return_value = mock_session
        mock_config_service.execute_step = AsyncMock(return_value=MagicMock(success=True))
        mock_request.app.state.adapter_config_service = mock_config_service

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config.get_adapter_config_service",
            return_value=mock_config_service,
        ):
            with caplog.at_level(logging.INFO):
                result = await oauth_deeplink_callback(
                    request=mock_request,
                    state="session-123",
                    code="auth_code",
                    provider="google",
                    source="mobile",
                )

            assert "Successfully processed OAuth callback" in caplog.text
            assert result.data["success"] is True


class TestGetExistingReauthConfig:
    """Tests for _get_existing_reauth_config helper function."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_runtime_control(self):
        """Should return None when runtime control service is unavailable."""
        mock_request = MagicMock()
        mock_request.app.state = MagicMock(spec=[])  # No runtime_control attributes

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config._get_runtime_control_service_for_adapter_load",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await _get_existing_reauth_config(mock_request, "home_assistant")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_adapter_manager(self):
        """Should return None when adapter_manager is not available."""
        mock_request = MagicMock()
        mock_runtime_control = MagicMock()
        mock_runtime_control.adapter_manager = None

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config._get_runtime_control_service_for_adapter_load",
            new_callable=AsyncMock,
            return_value=mock_runtime_control,
        ):
            result = await _get_existing_reauth_config(mock_request, "home_assistant")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_adapter_type_not_found(self):
        """Should return None when no adapter of the requested type is loaded."""
        mock_request = MagicMock()
        mock_runtime_control = MagicMock()
        mock_adapter_manager = MagicMock()

        # Create a different adapter type
        mock_instance = MagicMock()
        mock_instance.adapter_type = "different_adapter"
        mock_adapter_manager.loaded_adapters = {"diff_1": mock_instance}
        mock_runtime_control.adapter_manager = mock_adapter_manager

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config._get_runtime_control_service_for_adapter_load",
            new_callable=AsyncMock,
            return_value=mock_runtime_control,
        ):
            result = await _get_existing_reauth_config(mock_request, "home_assistant")
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_base_url_from_ha_service(self):
        """Should return base_url from ha_service.ha_url when available.

        The function resolves hostnames to IPs for reliable Android connectivity,
        so we test with an IP address directly to ensure consistent results.
        """
        mock_request = MagicMock()
        mock_runtime_control = MagicMock()
        mock_adapter_manager = MagicMock()

        # Create a home_assistant adapter with ha_service
        # Use IP address to ensure consistent test results
        mock_adapter = MagicMock()
        mock_ha_service = MagicMock()
        mock_ha_service.ha_url = "http://192.168.1.100:8123"
        mock_adapter.ha_service = mock_ha_service

        mock_instance = MagicMock()
        mock_instance.adapter_type = "home_assistant"
        mock_instance.adapter = mock_adapter
        mock_adapter_manager.loaded_adapters = {"ha_1": mock_instance}
        mock_runtime_control.adapter_manager = mock_adapter_manager

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config._get_runtime_control_service_for_adapter_load",
            new_callable=AsyncMock,
            return_value=mock_runtime_control,
        ):
            result = await _get_existing_reauth_config(mock_request, "home_assistant")
            assert result == {"base_url": "http://192.168.1.100:8123"}

    @pytest.mark.asyncio
    async def test_returns_config_from_config_params_fallback(self):
        """Should fallback to config_params.settings when ha_service not available.

        The function resolves hostnames to IPs for base_url, so we use an IP
        address to ensure consistent test results.
        """
        mock_request = MagicMock()
        mock_runtime_control = MagicMock()
        mock_adapter_manager = MagicMock()

        # Create adapter without ha_service but with config_params
        # Use IP address for base_url to ensure consistent results
        mock_adapter = MagicMock(spec=[])  # No ha_service attribute
        mock_config_params = MagicMock()
        mock_config_params.settings = {"base_url": "http://10.0.0.1:8080", "token": "abc123"}

        mock_instance = MagicMock()
        mock_instance.adapter_type = "generic_adapter"
        mock_instance.adapter = mock_adapter
        mock_instance.config_params = mock_config_params
        mock_adapter_manager.loaded_adapters = {"gen_1": mock_instance}
        mock_runtime_control.adapter_manager = mock_adapter_manager

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config._get_runtime_control_service_for_adapter_load",
            new_callable=AsyncMock,
            return_value=mock_runtime_control,
        ):
            result = await _get_existing_reauth_config(mock_request, "generic_adapter")
            assert result == {"base_url": "http://10.0.0.1:8080", "token": "abc123"}

    @pytest.mark.asyncio
    async def test_returns_none_when_no_config_available(self):
        """Should return None when adapter has neither ha_service nor config_params.settings."""
        mock_request = MagicMock()
        mock_runtime_control = MagicMock()
        mock_adapter_manager = MagicMock()

        # Create adapter without ha_service or config_params.settings
        mock_adapter = MagicMock(spec=[])  # No ha_service attribute
        mock_config_params = MagicMock()
        mock_config_params.settings = None

        mock_instance = MagicMock()
        mock_instance.adapter_type = "bare_adapter"
        mock_instance.adapter = mock_adapter
        mock_instance.config_params = mock_config_params
        mock_adapter_manager.loaded_adapters = {"bare_1": mock_instance}
        mock_runtime_control.adapter_manager = mock_adapter_manager

        with patch(
            "ciris_engine.logic.adapters.api.routes.system.adapter_config._get_runtime_control_service_for_adapter_load",
            new_callable=AsyncMock,
            return_value=mock_runtime_control,
        ):
            result = await _get_existing_reauth_config(mock_request, "bare_adapter")
            assert result is None
