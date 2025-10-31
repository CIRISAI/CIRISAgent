"""
Unit tests for Reddit authentication failure detection and handling.

Tests cover:
1. Empty access token detection in OAuth response
2. Suspended account error detection
3. Invalid credentials error detection
4. Proper error classification (CRITICAL, non-retryable)
5. Error message formatting with helpful diagnostics
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_modular_services.reddit.error_handler import ErrorSeverity, RedditErrorHandler
from ciris_modular_services.reddit.service import RedditAPIClient
from ciris_modular_services.reddit.schemas import RedditCredentials


class TestAuthFailureDetection:
    """Test authentication failure detection in RedditAPIClient.refresh_token()"""

    @pytest.fixture
    def mock_credentials(self):
        """Create mock Reddit credentials."""
        return RedditCredentials(
            client_id="test_client_id",
            client_secret="test_secret",
            username="test_user",
            password="test_pass",
            user_agent="test_agent",
        )

    @pytest.fixture
    def api_client(self, mock_credentials):
        """Create RedditAPIClient with mock credentials."""
        client = RedditAPIClient(mock_credentials)
        return client

    @pytest.mark.asyncio
    async def test_empty_access_token_raises_auth_error(self, api_client):
        """
        GIVEN a Reddit OAuth response with empty access_token
        WHEN refresh_token() is called
        THEN it should raise RuntimeError with authentication failure message
        """
        # Mock the HTTP response with empty access_token
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "",  # Empty token
            "expires_in": "3600",
            "token_type": "bearer",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(RuntimeError) as exc_info:
                await api_client.refresh_token(force=True)

            error_msg = str(exc_info.value)
            assert "authentication failed" in error_msg.lower()
            assert "no access_token in response" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_missing_access_token_raises_auth_error(self, api_client):
        """
        GIVEN a Reddit OAuth response without access_token key
        WHEN refresh_token() is called
        THEN it should raise RuntimeError with authentication failure message
        """
        # Mock the HTTP response with missing access_token
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "expires_in": "3600",
            "token_type": "bearer",
            # No access_token key
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(RuntimeError) as exc_info:
                await api_client.refresh_token(force=True)

            error_msg = str(exc_info.value)
            assert "authentication failed" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_whitespace_only_token_raises_auth_error(self, api_client):
        """
        GIVEN a Reddit OAuth response with whitespace-only access_token
        WHEN refresh_token() is called
        THEN it should raise RuntimeError with authentication failure message
        """
        # Mock the HTTP response with whitespace token
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "   ",  # Whitespace only
            "expires_in": "3600",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(RuntimeError) as exc_info:
                await api_client.refresh_token(force=True)

            assert "authentication failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_suspended_account_error_message(self, api_client):
        """
        GIVEN a Reddit OAuth response indicating suspended account
        WHEN refresh_token() is called
        THEN error message should mention suspended account
        """
        # Mock the HTTP response with error indicating suspended account
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Account suspended",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(RuntimeError) as exc_info:
                await api_client.refresh_token(force=True)

            error_msg = str(exc_info.value)
            assert "invalid_grant" in error_msg
            assert "account suspended" in error_msg.lower()
            assert "suspended reddit account" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_invalid_credentials_error_message(self, api_client):
        """
        GIVEN a Reddit OAuth response with invalid credentials
        WHEN refresh_token() is called
        THEN error message should mention invalid credentials
        """
        # Mock the HTTP response with invalid credentials error
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Invalid username or password",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            with pytest.raises(RuntimeError) as exc_info:
                await api_client.refresh_token(force=True)

            error_msg = str(exc_info.value)
            assert "invalid_grant" in error_msg
            assert "invalid username or password" in error_msg.lower()
            assert "invalid credentials" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_valid_token_does_not_raise(self, api_client):
        """
        GIVEN a Reddit OAuth response with valid access_token
        WHEN refresh_token() is called
        THEN it should succeed without raising
        """
        # Mock the HTTP response with valid token
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "valid_token_12345",
            "expires_in": "3600",
            "token_type": "bearer",
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value.__aenter__.return_value = mock_client

            # Should not raise
            result = await api_client.refresh_token(force=True)
            assert result is True
            assert api_client._token is not None
            assert api_client._token.access_token == "valid_token_12345"


class TestErrorHandlerAuthClassification:
    """Test error handler classification of authentication failures."""

    @pytest.fixture
    def error_handler(self):
        """Create RedditErrorHandler instance."""
        return RedditErrorHandler()

    def test_auth_failure_classified_as_critical(self, error_handler):
        """
        GIVEN a RuntimeError with authentication failure message
        WHEN classify_error() is called
        THEN it should return CRITICAL severity and can_retry=False
        """
        error = RuntimeError("Reddit authentication failed: invalid_grant - Account suspended")
        error_info = error_handler.classify_error(error, operation="refresh_token")

        assert error_info.severity == ErrorSeverity.CRITICAL
        assert error_info.can_retry is False
        assert error_info.suggested_action == "check_account_status"
        assert "authentication failure" in error_info.message.lower()

    def test_suspended_account_classified_as_critical(self, error_handler):
        """
        GIVEN a RuntimeError mentioning suspended account
        WHEN classify_error() is called
        THEN it should return CRITICAL severity and can_retry=False
        """
        error = RuntimeError("Token refresh failed - suspended Reddit account")
        error_info = error_handler.classify_error(error, operation="refresh_token")

        assert error_info.severity == ErrorSeverity.CRITICAL
        assert error_info.can_retry is False
        assert error_info.suggested_action == "check_account_status"

    def test_invalid_credentials_classified_as_critical(self, error_handler):
        """
        GIVEN a RuntimeError mentioning invalid credentials
        WHEN classify_error() is called
        THEN it should return CRITICAL severity and can_retry=False
        """
        error = RuntimeError("Reddit authentication failed due to invalid credentials")
        error_info = error_handler.classify_error(error, operation="refresh_token")

        assert error_info.severity == ErrorSeverity.CRITICAL
        assert error_info.can_retry is False
        assert error_info.suggested_action == "check_account_status"

    def test_token_request_failure_classified_as_high_retryable(self, error_handler):
        """
        GIVEN a RuntimeError with token request failure (temporary)
        WHEN classify_error() is called
        THEN it should return HIGH severity and can_retry=True
        """
        error = RuntimeError("Token request failed (500): Internal Server Error")
        error_info = error_handler.classify_error(error, operation="refresh_token")

        assert error_info.severity == ErrorSeverity.HIGH
        assert error_info.can_retry is True
        assert error_info.suggested_action == "exponential_backoff"
        assert "token refresh failed" in error_info.message.lower()

    def test_generic_runtime_error_classified_as_medium(self, error_handler):
        """
        GIVEN a RuntimeError without auth-specific keywords
        WHEN classify_error() is called
        THEN it should return MEDIUM severity
        """
        error = RuntimeError("Some other runtime error")
        error_info = error_handler.classify_error(error, operation="some_operation")

        assert error_info.severity == ErrorSeverity.MEDIUM
        assert "runtime error" in error_info.message.lower()

    @pytest.mark.asyncio
    async def test_auth_failure_not_retried(self, error_handler):
        """
        GIVEN an operation that raises authentication failure
        WHEN retry_with_backoff() is called
        THEN it should immediately raise without retrying
        """
        async def failing_operation():
            raise RuntimeError("Reddit authentication failed: invalid_grant - Account suspended")

        # Should raise immediately without retrying (no backoff delay)
        with pytest.raises(RuntimeError) as exc_info:
            await error_handler.retry_with_backoff(
                failing_operation,
                max_retries=3,
                operation_name="test_auth",
            )

        # Verify it's the auth failure error
        assert "authentication failed" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_token_request_failure_retried(self, error_handler):
        """
        GIVEN an operation that raises temporary token request failure
        WHEN retry_with_backoff() is called
        THEN it should retry with exponential backoff
        """
        attempt_count = 0

        async def failing_operation():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise RuntimeError("Token request failed (503): Service Unavailable")
            return "success"

        # Should retry and eventually succeed
        result = await error_handler.retry_with_backoff(
            failing_operation,
            max_retries=3,
            operation_name="test_token_retry",
        )

        assert result == "success"
        assert attempt_count == 3  # Retried twice, succeeded on 3rd attempt
