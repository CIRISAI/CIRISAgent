"""Tests for adapter_config.py helper functions."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.system.adapter_config import _sanitize_for_log


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
