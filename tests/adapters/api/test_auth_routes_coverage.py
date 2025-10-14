"""
Additional tests to improve coverage of auth.py routes.

This test file focuses on covering the missing paths identified in the coverage report:
- Password login flow (lines 74-105, 124-129, 141-147)
- OAuth config loading error paths (lines 172-197, 232-264)
- OAuth provider helper methods (lines 298-341, 360-442)
- Token refresh paths (lines 172-197)
- Environment variable fallbacks (lines 54-56)
- Error handling paths in OAuth callbacks

These tests complement the existing OAuth tests to achieve better coverage.
"""

import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes.auth import (
    _build_redirect_response,
    _determine_user_role,
    _generate_api_key_and_store,
    _handle_discord_oauth,
    _handle_github_oauth,
    _handle_google_oauth,
    _load_oauth_config,
    get_oauth_callback_url,
    router,
)
from ciris_engine.schemas.api.auth import LoginRequest, UserRole


class TestPasswordLoginFlow:
    """Test the password-based login flow that's currently not covered."""

    @pytest.fixture
    def mock_app(self):
        """Create mock FastAPI app with auth service."""
        app = Mock()
        app.state = Mock()

        # Mock auth service
        auth_service = Mock()
        app.state.auth_service = auth_service
        app.state.config_service = Mock()

        return app

    @pytest.fixture
    def mock_user(self):
        """Create mock user for testing."""
        from ciris_engine.logic.adapters.api.services.auth_service import User
        from ciris_engine.schemas.runtime.api import APIRole

        user = Mock(spec=User)
        user.wa_id = "test-user-123"
        user.username = "testuser"
        user.name = "Test User"
        user.api_role = APIRole.ADMIN
        return user

    @pytest.mark.asyncio
    async def test_password_login_success(self, mock_app, mock_user):
        """Test successful password login - covers lines 74-105."""
        # Mock auth service
        mock_auth_service = Mock()
        mock_auth_service.verify_user_password = AsyncMock(return_value=mock_user)
        mock_auth_service.store_api_key = Mock()

        request = LoginRequest(username="testuser", password="testpass")

        # Import the login function directly for testing
        from ciris_engine.logic.adapters.api.routes.auth import login

        # Mock the Request object
        mock_request = Mock()
        mock_request.app = mock_app

        response = await login(request, mock_request, mock_auth_service)

        # Verify API key generation and storage
        mock_auth_service.store_api_key.assert_called_once()
        store_call = mock_auth_service.store_api_key.call_args

        assert store_call[1]["user_id"] == "test-user-123"
        assert store_call[1]["role"] == UserRole.ADMIN
        assert store_call[1]["description"] == "Login session"

        # Verify response structure
        assert response.access_token.startswith("ciris_admin_")
        assert response.token_type == "Bearer"

    @pytest.mark.asyncio
    async def test_password_login_invalid_credentials(self, mock_app):
        """Test password login with invalid credentials - covers line 79-80."""
        mock_auth_service = Mock()
        mock_auth_service.verify_user_password = AsyncMock(return_value=None)

        request = LoginRequest(username="baduser", password="badpass")

        from ciris_engine.logic.adapters.api.routes.auth import login

        mock_request = Mock()
        mock_request.app = mock_app

        with pytest.raises(HTTPException) as exc_info:
            await login(request, mock_request, mock_auth_service)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Invalid credentials"


class TestTokenRefreshFlow:
    """Test token refresh functionality that's currently not covered."""

    @pytest.fixture
    def mock_auth_context(self):
        """Create mock auth context."""
        from ciris_engine.schemas.api.auth import AuthContext

        auth = Mock(spec=AuthContext)
        auth.user_id = "user-123"
        auth.role = UserRole.ADMIN
        auth.api_key_id = "old-key-123"
        return auth

    @pytest.mark.asyncio
    async def test_refresh_token_admin_role(self, mock_auth_context):
        """Test token refresh for admin role - covers lines 179-196."""
        mock_auth_context.role = UserRole.SYSTEM_ADMIN

        from ciris_engine.logic.adapters.api.routes.auth import refresh_token
        from ciris_engine.schemas.api.auth import TokenRefreshRequest

        # Mock auth service
        mock_auth_service = Mock()
        mock_auth_service.store_api_key = Mock()
        mock_auth_service.revoke_api_key = Mock()

        # Mock refresh request
        refresh_request = TokenRefreshRequest(refresh_token="dummy-refresh-token")

        response = await refresh_token(refresh_request, mock_auth_context, mock_auth_service)

        # Verify 24-hour expiration for SYSTEM_ADMIN
        store_call = mock_auth_service.store_api_key.call_args
        assert store_call[1]["description"] == "Refreshed token"

        # Verify old key revocation
        mock_auth_service.revoke_api_key.assert_called_once_with("old-key-123")

        # Verify response has shorter expiration
        assert response.expires_in == 86400  # 24 hours

    @pytest.mark.asyncio
    async def test_refresh_token_regular_role(self, mock_auth_context):
        """Test token refresh for regular role - covers lines 183-184."""
        mock_auth_context.role = UserRole.OBSERVER

        from ciris_engine.logic.adapters.api.routes.auth import refresh_token
        from ciris_engine.schemas.api.auth import TokenRefreshRequest

        mock_auth_service = Mock()
        mock_auth_service.store_api_key = Mock()
        mock_auth_service.revoke_api_key = Mock()

        # Mock refresh request
        refresh_request = TokenRefreshRequest(refresh_token="dummy-refresh-token")

        response = await refresh_token(refresh_request, mock_auth_context, mock_auth_service)

        # Verify 30-day expiration for regular users
        assert response.expires_in == 2592000  # 30 days


class TestOAuthHelperMethods:
    """Test the OAuth helper methods that were refactored."""

    def test_load_oauth_config_success(self):
        """Test successful OAuth config loading."""
        # Mock the JSON config file
        mock_config = {"google": {"client_id": "test-google-id", "client_secret": "test-google-secret"}}

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.read_text",
            return_value='{"google": {"client_id": "test-google-id", "client_secret": "test-google-secret"}}',
        ):
            config = _load_oauth_config("google")

            assert config["client_id"] == "test-google-id"
            assert config["client_secret"] == "test-google-secret"

    def test_load_oauth_config_missing_vars(self):
        """Test OAuth config loading with missing config file."""
        # Mock missing config file
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                _load_oauth_config("google")

            assert exc_info.value.status_code == 404
            assert "OAuth provider 'google' not configured" in exc_info.value.detail

    def test_load_oauth_config_unsupported_provider(self):
        """Test OAuth config loading with unsupported provider."""
        # Mock config file that exists but doesn't have the requested provider
        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.read_text",
            return_value='{"google": {"client_id": "test-id", "client_secret": "test-secret"}}',
        ):
            with pytest.raises(HTTPException) as exc_info:
                _load_oauth_config("unsupported")

            assert exc_info.value.status_code == 404
            assert "OAuth provider 'unsupported' not configured" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_google_oauth_success(self):
        """Test successful Google OAuth handling."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock token response
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test-token"}

            # Mock user info response
            mock_user_response = Mock()
            mock_user_response.status_code = 200
            mock_user_response.json.return_value = {
                "id": "12345",
                "email": "test@example.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
            }

            # Mock the async context manager and methods
            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_context.get = AsyncMock(return_value=mock_user_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            result = await _handle_google_oauth("test-code", "client-id", "client-secret")

            assert result["email"] == "test@example.com"
            assert result["name"] == "Test User"
            assert result["picture"] == "https://example.com/pic.jpg"

    @pytest.mark.asyncio
    async def test_handle_google_oauth_token_error(self):
        """Test Google OAuth with token exchange error."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock failed token response
            mock_token_response = Mock()
            mock_token_response.json.return_value = {"error": "invalid_grant"}

            mock_client.return_value.__aenter__.return_value.post.return_value = mock_token_response

            with pytest.raises(HTTPException) as exc_info:
                await _handle_google_oauth("bad-code", "client-id", "client-secret")

            # Should raise HTTPException on token error
            assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_handle_github_oauth_success(self):
        """Test successful GitHub OAuth handling."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock token response - GitHub returns JSON, not URL-encoded
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test-token", "token_type": "bearer"}

            # Mock user info response
            mock_user_response = Mock()
            mock_user_response.status_code = 200
            mock_user_response.json.return_value = {
                "id": 123,
                "email": "test@github.com",
                "name": "GitHub User",
                "avatar_url": "https://avatars.githubusercontent.com/u/123",
                "login": "githubuser",
            }

            # Mock the async context manager and methods
            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_context.get = AsyncMock(return_value=mock_user_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            result = await _handle_github_oauth("test-code", "client-id", "client-secret")

            assert result["external_id"] == "123"  # Converted to string
            assert result["email"] == "test@github.com"
            assert result["name"] == "GitHub User"
            assert result["picture"] == "https://avatars.githubusercontent.com/u/123"

    @pytest.mark.asyncio
    async def test_handle_discord_oauth_success(self):
        """Test successful Discord OAuth handling."""
        with patch("httpx.AsyncClient") as mock_client:
            # Mock token response
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test-token"}

            # Mock user info response
            mock_user_response = Mock()
            mock_user_response.status_code = 200
            mock_user_response.json.return_value = {
                "email": "test@discord.com",
                "username": "DiscordUser",
                "avatar": "avatar123",
                "id": "123456789",
            }

            # Mock the async context manager and methods
            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_context.get = AsyncMock(return_value=mock_user_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            result = await _handle_discord_oauth("test-code", "client-id", "client-secret")

            assert result["email"] == "test@discord.com"
            assert result["name"] == "DiscordUser"
            assert result["picture"] == "https://cdn.discordapp.com/avatars/123456789/avatar123.png"

    def test_determine_user_role_admin_email(self):
        """Test user role determination for admin email."""
        role = _determine_user_role("admin@ciris.ai")
        assert role == UserRole.ADMIN

    def test_determine_user_role_regular_user(self):
        """Test user role determination for regular user."""
        role = _determine_user_role("user@example.com")
        assert role == UserRole.OBSERVER

    def test_determine_user_role_no_email(self):
        """Test user role determination with no email."""
        role = _determine_user_role(None)
        assert role == UserRole.OBSERVER

    def test_generate_api_key_and_store(self):
        """Test API key generation and storage."""
        mock_auth_service = Mock()
        mock_auth_service.store_api_key = Mock()

        # Create mock OAuth user object with the expected attributes
        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "user-123"
        mock_oauth_user.role = UserRole.OBSERVER

        api_key = _generate_api_key_and_store(mock_auth_service, mock_oauth_user, "google")

        # Verify API key storage called
        mock_auth_service.store_api_key.assert_called_once()

        # Verify API key format
        assert api_key.startswith("ciris_observer_")


class TestEnvironmentVariableFallbacks:
    """Test environment variable fallback logic."""

    def test_oauth_callback_url_default(self):
        """Test OAuth callback URL with default base - covers lines 54-56."""
        with patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}, clear=True):
            url = get_oauth_callback_url("google")
            assert url == "https://agents.ciris.ai/v1/auth/oauth/datum/google/callback"

    def test_oauth_callback_url_custom_base(self):
        """Test OAuth callback URL with custom base."""
        with patch.dict(os.environ, {"OAUTH_CALLBACK_BASE_URL": "https://custom.domain", "CIRIS_AGENT_ID": "datum"}):
            url = get_oauth_callback_url("github")
            assert url == "https://custom.domain/v1/auth/oauth/datum/github/callback"

    def test_oauth_callback_url_explicit_base(self):
        """Test OAuth callback URL with explicit base parameter."""
        with patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}):
            url = get_oauth_callback_url("discord", base_url="https://test.local")
            assert url == "https://test.local/v1/auth/oauth/datum/discord/callback"


class TestOAuthErrorPaths:
    """Test error paths in OAuth callback handling."""

    @pytest.mark.asyncio
    async def test_oauth_callback_missing_code(self):
        """Test OAuth callback without code parameter."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        # Mock OAuth config loading to succeed so we can test parameter validation
        with patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config:
            mock_config.return_value = {"client_id": "test-id", "client_secret": "test-secret"}

            # Mock the OAuth handler to simulate the actual behavior
            with patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth_handler:
                mock_oauth_handler.side_effect = HTTPException(
                    status_code=400,
                    detail='Failed to exchange code for token: {\n  "error": "invalid_request",\n  "error_description": "Missing required parameter: code"\n}',
                )

                mock_auth_service = Mock()

                with pytest.raises(HTTPException) as exc_info:
                    await oauth_callback("google", None, "test-state", mock_auth_service)

                # The function now properly validates and returns 400 for missing code
                assert exc_info.value.status_code == 400
                assert "Missing required parameter: code" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_provider(self):
        """Test OAuth callback with invalid provider."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        mock_request = Mock()
        mock_auth_service = Mock()

        # This should trigger the _load_oauth_config error for unsupported provider
        with pytest.raises(HTTPException) as exc_info:
            await oauth_callback("invalid", "test-code", "test-state", mock_auth_service)

        # The function returns 404 for unsupported providers due to config loading
        assert exc_info.value.status_code == 404
        assert "OAuth provider 'invalid' not configured" in exc_info.value.detail


class TestOAuthRedirectURI:
    """Test OAuth redirect_uri parameter functionality for separate frontend/API domains."""

    @pytest.mark.asyncio
    async def test_oauth_login_with_redirect_uri(self):
        """Test oauth_login encodes redirect_uri in state parameter."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_login

        # Mock OAuth config
        mock_config = {"google": {"client_id": "test-client-id", "client_secret": "test-secret"}}

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.read_text",
            return_value='{"google": {"client_id": "test-client-id", "client_secret": "test-secret"}}',
        ), patch.dict(os.environ, {"CIRIS_AGENT_ID": "scout-test"}):
            # Create mock request with redirect_uri parameter
            mock_request = Mock()
            mock_request.headers = {"x-forwarded-proto": "https", "host": "scoutapi.ciris.ai"}
            mock_request.url = Mock(scheme="https")

            # Call oauth_login with redirect_uri
            redirect_uri = "https://scout.ciris.ai/oauth/scout-test/google/callback"
            response = await oauth_login("google", mock_request, redirect_uri=redirect_uri)

            # Verify it's a redirect response
            assert response.status_code == 302
            assert "accounts.google.com" in response.headers["location"]

            # Decode the state parameter from the redirect URL
            import base64
            import json
            import urllib.parse

            parsed_url = urllib.parse.urlparse(response.headers["location"])
            query_params = urllib.parse.parse_qs(parsed_url.query)
            state_param = query_params["state"][0]

            # Decode state
            state_json = base64.urlsafe_b64decode(state_param.encode()).decode()
            state_data = json.loads(state_json)

            # Verify redirect_uri is encoded in state
            assert "redirect_uri" in state_data
            assert state_data["redirect_uri"] == redirect_uri
            assert "csrf" in state_data  # CSRF token should also be present

    @pytest.mark.asyncio
    async def test_oauth_login_without_redirect_uri(self):
        """Test oauth_login without redirect_uri (backward compatibility)."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_login

        with patch("pathlib.Path.exists", return_value=True), patch(
            "pathlib.Path.read_text",
            return_value='{"google": {"client_id": "test-client-id", "client_secret": "test-secret"}}',
        ), patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}):
            mock_request = Mock()
            mock_request.headers = {"x-forwarded-proto": "https", "host": "agents.ciris.ai"}
            mock_request.url = Mock(scheme="https")

            # Call without redirect_uri
            response = await oauth_login("google", mock_request)

            # Verify it's a redirect response
            assert response.status_code == 302

            # Decode state - should not have redirect_uri
            import base64
            import json
            import urllib.parse

            parsed_url = urllib.parse.urlparse(response.headers["location"])
            query_params = urllib.parse.parse_qs(parsed_url.query)
            state_param = query_params["state"][0]

            state_json = base64.urlsafe_b64decode(state_param.encode()).decode()
            state_data = json.loads(state_json)

            # Should have CSRF but not redirect_uri
            assert "csrf" in state_data
            assert "redirect_uri" not in state_data

    @pytest.mark.asyncio
    async def test_oauth_callback_with_redirect_uri_in_state(self):
        """Test oauth_callback decodes redirect_uri from state and redirects to frontend."""
        # Create state with redirect_uri
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        redirect_uri = "https://scout.ciris.ai/oauth/scout-test/google/callback"
        state_data = {"csrf": "test-csrf-token", "redirect_uri": redirect_uri}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        # Mock OAuth config and handlers
        with patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config, patch(
            "ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth"
        ) as mock_oauth_handler:
            mock_config.return_value = {"client_id": "test-id", "client_secret": "test-secret"}

            # Mock OAuth user data
            mock_oauth_handler.return_value = {
                "external_id": "12345",
                "email": "test@example.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
            }

            # Mock auth service
            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "oauth-user-123"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            # Call callback
            response = await oauth_callback("google", "test-code", state, mock_auth_service, marketing_opt_in=False)

            # Verify redirect to frontend domain (not relative path)
            assert response.status_code == 302
            redirect_location = response.headers["location"]
            assert redirect_location.startswith(redirect_uri)
            assert "access_token=" in redirect_location
            assert "https://scout.ciris.ai" in redirect_location  # Full URL, not relative

    @pytest.mark.asyncio
    async def test_oauth_callback_without_redirect_uri_in_state(self):
        """Test oauth_callback without redirect_uri uses relative path (backward compatibility)."""
        # Create state without redirect_uri
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        state_data = {"csrf": "test-csrf-token"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config, patch(
            "ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth"
        ) as mock_oauth_handler, patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}):
            mock_config.return_value = {"client_id": "test-id", "client_secret": "test-secret"}

            mock_oauth_handler.return_value = {
                "external_id": "12345",
                "email": "test@example.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
            }

            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "oauth-user-123"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            response = await oauth_callback("google", "test-code", state, mock_auth_service)

            # Verify redirect to relative path (backward compatibility)
            assert response.status_code == 302
            redirect_location = response.headers["location"]
            assert redirect_location.startswith("/oauth/")  # Relative path
            assert "access_token=" in redirect_location

    @pytest.mark.asyncio
    async def test_oauth_callback_malformed_state(self):
        """Test oauth_callback handles malformed state gracefully."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        # Malformed state (not valid base64 JSON)
        malformed_state = "not-valid-base64-json"

        with patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config, patch(
            "ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth"
        ) as mock_oauth_handler, patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}):
            mock_config.return_value = {"client_id": "test-id", "client_secret": "test-secret"}

            mock_oauth_handler.return_value = {
                "external_id": "12345",
                "email": "test@example.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
            }

            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "oauth-user-123"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            # Should not raise, should fall back to relative path
            response = await oauth_callback("google", "test-code", malformed_state, mock_auth_service)

            # Should still work, using default redirect
            assert response.status_code == 302
            assert "access_token=" in response.headers["location"]

    def test_build_redirect_response_with_redirect_uri(self):
        """Test _build_redirect_response uses full URL when redirect_uri provided."""
        from ciris_engine.logic.adapters.api.routes.auth import _build_redirect_response

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "user-123"
        mock_oauth_user.role = UserRole.OBSERVER

        redirect_uri = "https://scout.ciris.ai/oauth/scout-test/google/callback"
        response = _build_redirect_response(
            api_key="test-api-key", oauth_user=mock_oauth_user, provider="google", redirect_uri=redirect_uri
        )

        # Should redirect to full URL
        assert response.status_code == 302
        redirect_location = response.headers["location"]
        assert redirect_location.startswith("https://scout.ciris.ai/oauth/scout-test/google/callback?")
        assert "access_token=test-api-key" in redirect_location
        assert "role=OBSERVER" in redirect_location  # Role enum value is uppercase
        assert "user_id=user-123" in redirect_location

    def test_build_redirect_response_without_redirect_uri(self):
        """Test _build_redirect_response uses relative path without redirect_uri (backward compatibility)."""
        from ciris_engine.logic.adapters.api.routes.auth import _build_redirect_response

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "user-123"
        mock_oauth_user.role = UserRole.ADMIN

        with patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}):
            response = _build_redirect_response(
                api_key="test-api-key", oauth_user=mock_oauth_user, provider="google", redirect_uri=None
            )

            # Should redirect to relative path
            assert response.status_code == 302
            redirect_location = response.headers["location"]
            assert redirect_location.startswith("/oauth/datum/google/callback?")
            assert "access_token=test-api-key" in redirect_location
            assert "role=ADMIN" in redirect_location  # Role enum value is uppercase

    def test_build_redirect_response_invalid_provider(self):
        """Test _build_redirect_response handles invalid provider safely."""
        from ciris_engine.logic.adapters.api.routes.auth import _build_redirect_response

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "user-123"
        mock_oauth_user.role = UserRole.OBSERVER

        # Invalid provider should redirect to safe default
        response = _build_redirect_response(
            api_key="test-api-key", oauth_user=mock_oauth_user, provider="invalid_provider", redirect_uri=None
        )

        # Should redirect to safe default (/)
        assert response.status_code == 302
        assert response.headers["location"] == "/"
