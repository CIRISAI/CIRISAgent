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
    _trigger_billing_credit_check_if_enabled,
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

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text",
                return_value='{"google": {"client_id": "test-google-id", "client_secret": "test-google-secret"}}',
            ),
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
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text",
                return_value='{"google": {"client_id": "test-id", "client_secret": "test-secret"}}',
            ),
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

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text",
                return_value='{"google": {"client_id": "test-client-id", "client_secret": "test-secret"}}',
            ),
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "scout-test"}),
        ):
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

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch(
                "pathlib.Path.read_text",
                return_value='{"google": {"client_id": "test-client-id", "client_secret": "test-secret"}}',
            ),
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
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
        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth_handler,
        ):
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

            # Mock request
            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            # Call callback
            response = await oauth_callback(
                "google", "test-code", state, mock_request, mock_auth_service, marketing_opt_in=False
            )

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

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth_handler,
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
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

            # Mock request
            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            response = await oauth_callback("google", "test-code", state, mock_request, mock_auth_service)

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

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth_handler,
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
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

            # Mock request
            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            # Should not raise, should fall back to relative path
            response = await oauth_callback("google", "test-code", malformed_state, mock_request, mock_auth_service)

            # Should still work, using default redirect
            assert response.status_code == 302
            assert "access_token=" in response.headers["location"]

    @pytest.mark.asyncio
    async def test_oauth_callback_preserves_redirect_uri_query_params(self):
        """Test oauth_callback preserves existing query params in redirect_uri (e.g., next, return_to)."""
        import base64
        import json
        import urllib.parse

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        # Create state with redirect_uri containing existing query params
        redirect_uri = "https://scout.ciris.ai/oauth-complete.html?next=/dashboard&return_to=/profile"
        state_data = {"csrf": "test-csrf-token", "redirect_uri": redirect_uri}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth_handler,
        ):
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

            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            response = await oauth_callback(
                "google", "test-code", state, mock_request, mock_auth_service, marketing_opt_in=False
            )

            # Verify redirect includes both original params and server params
            assert response.status_code == 302
            redirect_location = response.headers["location"]

            # Parse redirect URL
            parsed = urllib.parse.urlparse(redirect_location)
            query_params = urllib.parse.parse_qs(parsed.query)

            # Verify existing query params are preserved
            assert "next" in query_params
            assert query_params["next"][0] == "/dashboard"
            assert "return_to" in query_params
            assert query_params["return_to"][0] == "/profile"

            # Verify server params are also present
            assert "access_token" in query_params
            assert "role" in query_params
            assert "user_id" in query_params

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


class TestBillingIntegration:
    """Test billing credit check integration with OAuth callback."""

    @pytest.mark.asyncio
    async def test_trigger_billing_credit_check_enabled_success(self):
        """Test billing credit check when billing is enabled and check succeeds."""
        # Mock request with resource_monitor configured
        mock_request = Mock()
        mock_resource_monitor = Mock()
        mock_credit_provider = Mock()
        mock_credit_provider.__class__.__name__ = "CIRISBillingProvider"
        mock_resource_monitor.credit_provider = mock_credit_provider

        # Mock successful credit check
        from ciris_engine.schemas.services.credit_gate import CreditCheckResult

        mock_credit_result = CreditCheckResult(has_credit=True, credits_remaining=10)
        mock_resource_monitor.check_credit = AsyncMock(return_value=mock_credit_result)

        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_request.app.state.resource_monitor = mock_resource_monitor

        # Mock OAuth user with role attribute
        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "google:12345"
        mock_oauth_user.provider = "google"
        mock_oauth_user.external_id = "12345"
        mock_oauth_user.role = UserRole.OBSERVER  # Add role attribute

        # Call the function
        await _trigger_billing_credit_check_if_enabled(mock_request, mock_oauth_user)

        # Verify credit check was called
        mock_resource_monitor.check_credit.assert_called_once()
        call_args = mock_resource_monitor.check_credit.call_args

        # Verify account and context parameters
        account = call_args[0][0]
        context = call_args[0][1]

        assert account.provider == "oauth:google"
        assert account.account_id == "12345"
        assert account.authority_id == "google:12345"
        assert context.channel_id == "oauth:callback"
        assert context.agent_id == "datum"
        # Note: email and marketing_opt_in are no longer passed via CreditContext.metadata
        # They are passed directly in API calls to billing backend

    @pytest.mark.asyncio
    async def test_trigger_billing_credit_check_no_resource_monitor(self):
        """Test billing credit check when resource_monitor is not configured."""
        # Mock request without resource_monitor
        mock_request = Mock()
        mock_request.app = Mock()
        mock_request.app.state = Mock(spec=[])  # Empty state, no resource_monitor

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "google:12345"
        mock_oauth_user.provider = "google"
        mock_oauth_user.external_id = "12345"

        # Should not raise, just log and return
        await _trigger_billing_credit_check_if_enabled(mock_request, mock_oauth_user)

        # No assertions needed - function should return gracefully

    @pytest.mark.asyncio
    async def test_trigger_billing_credit_check_no_credit_provider(self):
        """Test billing credit check when credit_provider is not configured."""
        # Mock request with resource_monitor but no credit_provider
        mock_request = Mock()
        mock_resource_monitor = Mock()
        mock_resource_monitor.credit_provider = None  # No credit provider

        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_request.app.state.resource_monitor = mock_resource_monitor

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "google:12345"
        mock_oauth_user.provider = "google"
        mock_oauth_user.external_id = "12345"

        # Should not raise, just log and return
        await _trigger_billing_credit_check_if_enabled(mock_request, mock_oauth_user)

        # No assertions needed - function should return gracefully

    @pytest.mark.asyncio
    async def test_trigger_billing_credit_check_failure_non_blocking(self):
        """Test billing credit check failure does not block OAuth login."""
        # Mock request with resource_monitor that raises an exception
        mock_request = Mock()
        mock_resource_monitor = Mock()
        mock_credit_provider = Mock()
        mock_credit_provider.__class__.__name__ = "CIRISBillingProvider"
        mock_resource_monitor.credit_provider = mock_credit_provider

        # Mock credit check that raises an exception
        mock_resource_monitor.check_credit = AsyncMock(side_effect=Exception("Billing backend unavailable"))

        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_request.app.state.resource_monitor = mock_resource_monitor

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "google:12345"
        mock_oauth_user.provider = "google"
        mock_oauth_user.external_id = "12345"
        mock_oauth_user.role = UserRole.OBSERVER  # Add role attribute

        # Should not raise - error should be logged but OAuth should succeed
        await _trigger_billing_credit_check_if_enabled(mock_request, mock_oauth_user)

        # Verify credit check was attempted
        mock_resource_monitor.check_credit.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_billing_credit_check_simple_provider(self):
        """Test billing credit check with SimpleCreditProvider."""
        # Mock request with SimpleCreditProvider
        mock_request = Mock()
        mock_resource_monitor = Mock()
        mock_credit_provider = Mock()
        mock_credit_provider.__class__.__name__ = "SimpleCreditProvider"
        mock_resource_monitor.credit_provider = mock_credit_provider

        # Mock credit check
        from ciris_engine.schemas.services.credit_gate import CreditCheckResult

        mock_credit_result = CreditCheckResult(has_credit=True, credits_remaining=1)
        mock_resource_monitor.check_credit = AsyncMock(return_value=mock_credit_result)

        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_request.app.state.resource_monitor = mock_resource_monitor

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "github:67890"
        mock_oauth_user.provider = "github"
        mock_oauth_user.external_id = "67890"
        mock_oauth_user.role = UserRole.OBSERVER  # Add role attribute

        # Call the function
        await _trigger_billing_credit_check_if_enabled(mock_request, mock_oauth_user)

        # Verify credit check was called
        mock_resource_monitor.check_credit.assert_called_once()

    @pytest.mark.asyncio
    async def test_trigger_billing_credit_check_no_email(self):
        """Test billing credit check when user has no email."""
        # Mock request with resource_monitor
        mock_request = Mock()
        mock_resource_monitor = Mock()
        mock_credit_provider = Mock()
        mock_resource_monitor.credit_provider = mock_credit_provider

        from ciris_engine.schemas.services.credit_gate import CreditCheckResult

        mock_credit_result = CreditCheckResult(has_credit=True, credits_remaining=5)
        mock_resource_monitor.check_credit = AsyncMock(return_value=mock_credit_result)

        mock_request.app = Mock()
        mock_request.app.state = Mock()
        mock_request.app.state.resource_monitor = mock_resource_monitor

        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "discord:99999"
        mock_oauth_user.provider = "discord"
        mock_oauth_user.external_id = "99999"
        mock_oauth_user.role = UserRole.OBSERVER  # Add role attribute

        # Call function
        await _trigger_billing_credit_check_if_enabled(mock_request, mock_oauth_user)

        # Verify credit check was called
        mock_resource_monitor.check_credit.assert_called_once()
        call_args = mock_resource_monitor.check_credit.call_args
        context = call_args[0][1]
        # Note: email is no longer passed via CreditContext.metadata
        # It's passed directly to billing backend via API calls
        assert context.channel_id == "oauth:callback"

    @pytest.mark.asyncio
    async def test_oauth_callback_with_billing_integration(self):
        """Test that oauth_callback triggers billing credit check."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        # Create state
        state_data = {"csrf": "test-csrf-token"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        # Mock OAuth config and handlers
        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth_handler,
            patch(
                "ciris_engine.logic.adapters.api.routes.auth._trigger_billing_credit_check_if_enabled"
            ) as mock_billing_check,
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
            mock_config.return_value = {"client_id": "test-id", "client_secret": "test-secret"}

            mock_oauth_handler.return_value = {
                "external_id": "12345",
                "email": "test@example.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
            }

            # Mock auth service
            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "google:12345"
            mock_oauth_user.provider = "google"
            mock_oauth_user.external_id = "12345"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            # Mock request
            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            # Call callback with marketing_opt_in
            response = await oauth_callback(
                "google", "test-code", state, mock_request, mock_auth_service, marketing_opt_in=True
            )

            # Verify billing check was called
            mock_billing_check.assert_called_once()
            call_args = mock_billing_check.call_args

            # Verify parameters passed to billing check (email and marketing_opt_in removed)
            assert call_args[0][0] == mock_request  # request
            assert call_args[0][1] == mock_oauth_user  # oauth_user
            # Note: email and marketing_opt_in are no longer passed to this function
            # They are already stored in oauth_user object

            # Verify OAuth succeeded
            assert response.status_code == 302


class TestLogoutEndpoint:
    """Test the logout endpoint that revokes API keys."""

    @pytest.mark.asyncio
    async def test_logout_with_api_key_id(self):
        """Test logout when api_key_id is present - covers lines 147-152."""
        from ciris_engine.logic.adapters.api.routes.auth import logout
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.api_key_id = "key-to-revoke-123"
        mock_auth.user_id = "user-123"

        mock_auth_service = Mock()
        mock_auth_service.revoke_api_key = Mock()

        result = await logout(mock_auth, mock_auth_service)

        mock_auth_service.revoke_api_key.assert_called_once_with("key-to-revoke-123")
        assert result is None

    @pytest.mark.asyncio
    async def test_logout_without_api_key_id(self):
        """Test logout when api_key_id is None."""
        from ciris_engine.logic.adapters.api.routes.auth import logout
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.api_key_id = None
        mock_auth.user_id = "user-123"

        mock_auth_service = Mock()
        mock_auth_service.revoke_api_key = Mock()

        result = await logout(mock_auth, mock_auth_service)

        mock_auth_service.revoke_api_key.assert_not_called()
        assert result is None


class TestGetCurrentUserEndpoint:
    """Test the /auth/me endpoint - covers lines 166-172."""

    @pytest.mark.asyncio
    async def test_get_current_user_with_user_found(self):
        """Test get_current_user when user exists in auth service."""
        from ciris_engine.logic.adapters.api.routes.auth import get_current_user
        from ciris_engine.schemas.api.auth import AuthContext, Permission

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"
        mock_auth.role = UserRole.ADMIN
        mock_auth.permissions = [Permission.VIEW_MESSAGES, Permission.MANAGE_CONFIG]
        mock_auth.authenticated_at = datetime.now(timezone.utc)

        # Mock user returned from auth service
        mock_user = Mock()
        mock_user.name = "John Doe"

        mock_auth_service = Mock()
        mock_auth_service.get_user = Mock(return_value=mock_user)

        result = await get_current_user(mock_auth, mock_auth_service)

        assert result.user_id == "user-123"
        assert result.username == "John Doe"
        assert result.role == UserRole.ADMIN
        assert "view_messages" in result.permissions
        assert "manage_config" in result.permissions

    @pytest.mark.asyncio
    async def test_get_current_user_user_not_found(self):
        """Test get_current_user when user not found - fallback to user_id."""
        from ciris_engine.logic.adapters.api.routes.auth import get_current_user
        from ciris_engine.schemas.api.auth import AuthContext, Permission

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"
        mock_auth.role = UserRole.OBSERVER
        mock_auth.permissions = [Permission.VIEW_MESSAGES]
        mock_auth.authenticated_at = datetime.now(timezone.utc)

        mock_auth_service = Mock()
        mock_auth_service.get_user = Mock(return_value=None)

        result = await get_current_user(mock_auth, mock_auth_service)

        assert result.user_id == "user-123"
        assert result.username == "user-123"  # Fallback to user_id


class TestRefreshTokenNoAuth:
    """Test refresh token without authentication."""

    @pytest.mark.asyncio
    async def test_refresh_token_no_auth(self):
        """Test token refresh without authentication - covers line 198."""
        from ciris_engine.logic.adapters.api.routes.auth import refresh_token
        from ciris_engine.schemas.api.auth import TokenRefreshRequest

        mock_auth_service = Mock()
        refresh_request = TokenRefreshRequest(refresh_token="dummy-token")

        with pytest.raises(HTTPException) as exc_info:
            await refresh_token(refresh_request, None, mock_auth_service)

        assert exc_info.value.status_code == 401
        assert "Authentication required" in exc_info.value.detail


class TestOAuthProviderEndpoints:
    """Test OAuth provider management endpoints - covers lines 257-366."""

    @pytest.mark.asyncio
    async def test_list_oauth_providers_success(self):
        """Test listing OAuth providers - covers lines 257-289."""
        from ciris_engine.logic.adapters.api.routes.auth import list_oauth_providers
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_request = Mock()
        mock_request.headers = {"x-forwarded-proto": "https", "host": "agents.ciris.ai"}

        config_json = '{"google": {"client_id": "google-id", "created": "2024-01-01T00:00:00Z", "metadata": {}}}'

        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.read_text", return_value=config_json):
            response = await list_oauth_providers(mock_request, mock_auth)

        assert len(response.providers) == 1
        assert response.providers[0].provider == "google"
        assert response.providers[0].client_id == "google-id"

    @pytest.mark.asyncio
    async def test_list_oauth_providers_no_config(self):
        """Test listing OAuth providers with no config file."""
        from ciris_engine.logic.adapters.api.routes.auth import list_oauth_providers
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_request = Mock()

        with patch("pathlib.Path.exists", return_value=False):
            response = await list_oauth_providers(mock_request, mock_auth)

        assert len(response.providers) == 0

    @pytest.mark.asyncio
    async def test_list_oauth_providers_read_error(self):
        """Test listing OAuth providers with read error - covers lines 287-289."""
        from ciris_engine.logic.adapters.api.routes.auth import list_oauth_providers
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_request = Mock()

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", side_effect=IOError("Read error")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await list_oauth_providers(mock_request, mock_auth)

            assert exc_info.value.status_code == 500
            assert "Failed to read OAuth configuration" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_configure_oauth_provider_success(self):
        """Test configuring OAuth provider - covers lines 323-366."""
        from ciris_engine.logic.adapters.api.routes.auth import ConfigureOAuthProviderRequest, configure_oauth_provider
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "admin-user"
        mock_request = Mock()
        mock_request.headers = {"x-forwarded-proto": "https", "host": "agents.ciris.ai"}

        body = ConfigureOAuthProviderRequest(
            provider="google", client_id="new-client-id", client_secret="new-client-secret", metadata={}
        )

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.parent") as mock_parent,
            patch("pathlib.Path.write_text") as mock_write,
            patch("pathlib.Path.chmod"),
        ):
            mock_parent.mkdir = Mock()

            response = await configure_oauth_provider(body, mock_request, mock_auth)

        assert response.provider == "google"
        assert "configured successfully" in response.message

    @pytest.mark.asyncio
    async def test_configure_oauth_provider_write_error(self):
        """Test configuring OAuth provider with write error - covers lines 364-366."""
        from ciris_engine.logic.adapters.api.routes.auth import ConfigureOAuthProviderRequest, configure_oauth_provider
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "admin-user"
        mock_request = Mock()

        body = ConfigureOAuthProviderRequest(provider="google", client_id="client-id", client_secret="client-secret")

        with (
            patch("pathlib.Path.exists", return_value=False),
            patch("pathlib.Path.parent") as mock_parent,
            patch("pathlib.Path.write_text", side_effect=IOError("Write error")),
        ):
            mock_parent.mkdir = Mock()

            with pytest.raises(HTTPException) as exc_info:
                await configure_oauth_provider(body, mock_request, mock_auth)

            assert exc_info.value.status_code == 500
            assert "Failed to save OAuth configuration" in exc_info.value.detail


class TestOAuthLoginProviders:
    """Test OAuth login for different providers - covers lines 445-475."""

    @pytest.mark.asyncio
    async def test_oauth_login_github(self):
        """Test OAuth login for GitHub provider - covers lines 445-452."""
        import urllib.parse

        from ciris_engine.logic.adapters.api.routes.auth import oauth_login

        mock_request = Mock()
        mock_request.headers = {"x-forwarded-proto": "https", "host": "agents.ciris.ai"}
        mock_request.url = Mock(scheme="https")

        config_json = '{"github": {"client_id": "github-client-id", "client_secret": "secret"}}'

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value=config_json),
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
            response = await oauth_login("github", mock_request)

        assert response.status_code == 302
        assert "github.com/login/oauth/authorize" in response.headers["location"]
        # URL-decode and check for scope (read:user is URL-encoded as read%3Auser)
        decoded_url = urllib.parse.unquote(response.headers["location"])
        assert "read:user" in decoded_url  # GitHub scope

    @pytest.mark.asyncio
    async def test_oauth_login_discord(self):
        """Test OAuth login for Discord provider - covers lines 453-461."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_login

        mock_request = Mock()
        mock_request.headers = {"x-forwarded-proto": "https", "host": "agents.ciris.ai"}
        mock_request.url = Mock(scheme="https")

        config_json = '{"discord": {"client_id": "discord-client-id", "client_secret": "secret"}}'

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", return_value=config_json),
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
            response = await oauth_login("discord", mock_request)

        assert response.status_code == 302
        assert "discord.com/api/oauth2/authorize" in response.headers["location"]
        assert "identify" in response.headers["location"]  # Discord scope

    @pytest.mark.asyncio
    async def test_oauth_login_unsupported_provider(self):
        """Test OAuth login for unsupported provider - covers lines 462-463, 473-475.

        Note: The unsupported provider exception is wrapped in a generic exception
        handler that returns 500, so we expect 500 with "Failed to initiate OAuth login".
        """
        from ciris_engine.logic.adapters.api.routes.auth import oauth_login

        mock_request = Mock()
        mock_request.headers = {"x-forwarded-proto": "https", "host": "agents.ciris.ai"}
        mock_request.url = Mock(scheme="https")

        config_json = '{"custom": {"client_id": "custom-id", "client_secret": "secret"}}'

        with patch("pathlib.Path.exists", return_value=True), patch("pathlib.Path.read_text", return_value=config_json):
            with pytest.raises(HTTPException) as exc_info:
                await oauth_login("custom", mock_request)

            # The HTTPException from unsupported provider is wrapped in the outer
            # exception handler which returns 500
            assert exc_info.value.status_code == 500
            assert "Failed to initiate OAuth login" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_oauth_login_exception(self):
        """Test OAuth login exception handling - covers lines 473-475."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_login

        mock_request = Mock()
        mock_request.headers = {"x-forwarded-proto": "https", "host": "agents.ciris.ai"}
        mock_request.url = Mock(scheme="https")

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("pathlib.Path.read_text", side_effect=Exception("Unexpected error")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await oauth_login("google", mock_request)

            assert exc_info.value.status_code == 500
            assert "Failed to initiate OAuth login" in exc_info.value.detail


class TestGitHubOAuthErrors:
    """Test GitHub OAuth error paths - covers lines 534, 564, 578, 588-596."""

    @pytest.mark.asyncio
    async def test_github_oauth_token_error(self):
        """Test GitHub OAuth token exchange error - covers line 564."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_token_response = Mock()
            mock_token_response.status_code = 400
            mock_token_response.text = "Bad Request"

            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _handle_github_oauth("bad-code", "client-id", "client-secret")

            assert exc_info.value.status_code == 400
            assert "Failed to exchange code for token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_github_oauth_user_info_error(self):
        """Test GitHub OAuth user info fetch error - covers line 578."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test-token"}

            mock_user_response = Mock()
            mock_user_response.status_code = 401

            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_context.get = AsyncMock(return_value=mock_user_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _handle_github_oauth("test-code", "client-id", "client-secret")

            assert exc_info.value.status_code == 400
            assert "Failed to fetch user info" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_github_oauth_private_email_fetch(self):
        """Test GitHub OAuth private email fetch - covers lines 588-596."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test-token"}

            mock_user_response = Mock()
            mock_user_response.status_code = 200
            mock_user_response.json.return_value = {
                "id": 123,
                "email": None,  # Private email
                "name": "GitHub User",
                "avatar_url": "https://example.com/avatar.png",
                "login": "githubuser",
            }

            mock_emails_response = Mock()
            mock_emails_response.status_code = 200
            mock_emails_response.json.return_value = [
                {"email": "secondary@example.com", "primary": False},
                {"email": "primary@example.com", "primary": True},
            ]

            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_context.get = AsyncMock(side_effect=[mock_user_response, mock_emails_response])
            mock_client.return_value.__aenter__.return_value = mock_context

            result = await _handle_github_oauth("test-code", "client-id", "client-secret")

            assert result["email"] == "primary@example.com"
            assert result["name"] == "GitHub User"


class TestDiscordOAuthErrors:
    """Test Discord OAuth error paths - covers lines 625, 639."""

    @pytest.mark.asyncio
    async def test_discord_oauth_token_error(self):
        """Test Discord OAuth token exchange error - covers line 625."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_token_response = Mock()
            mock_token_response.status_code = 400
            mock_token_response.text = "Bad Request"

            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _handle_discord_oauth("bad-code", "client-id", "client-secret")

            assert exc_info.value.status_code == 400
            assert "Failed to exchange code for token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_discord_oauth_user_info_error(self):
        """Test Discord OAuth user info fetch error - covers line 639."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test-token"}

            mock_user_response = Mock()
            mock_user_response.status_code = 401

            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_context.get = AsyncMock(return_value=mock_user_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _handle_discord_oauth("test-code", "client-id", "client-secret")

            assert exc_info.value.status_code == 400
            assert "Failed to fetch user info" in exc_info.value.detail


class TestFirstUserDetection:
    """Test first user detection for SYSTEM_ADMIN role - covers lines 678-679."""

    def test_determine_user_role_first_user(self):
        """Test that first OAuth user gets SYSTEM_ADMIN role."""
        mock_auth_service = Mock()
        mock_auth_service._oauth_users = {}  # Empty = first user

        role = _determine_user_role("user@example.com", mock_auth_service)

        assert role == UserRole.SYSTEM_ADMIN

    def test_determine_user_role_subsequent_user(self):
        """Test that subsequent OAuth users get OBSERVER role."""
        mock_auth_service = Mock()
        mock_auth_service._oauth_users = {"existing:user": Mock()}  # Non-empty

        role = _determine_user_role("user@example.com", mock_auth_service)

        assert role == UserRole.OBSERVER


class TestProfileStorage:
    """Test OAuth profile storage - covers lines 690, 693-697."""

    def test_store_oauth_profile_no_picture(self):
        """Test profile storage with no picture - covers line 690."""
        from ciris_engine.logic.adapters.api.routes.auth import _store_oauth_profile

        mock_auth_service = Mock()

        # Should return early when picture is None
        _store_oauth_profile(mock_auth_service, "user-123", "Test User", None)

        mock_auth_service.get_user.assert_not_called()

    def test_store_oauth_profile_with_valid_picture(self):
        """Test profile storage with valid picture - covers lines 693-697."""
        from ciris_engine.logic.adapters.api.routes.auth import _store_oauth_profile

        mock_user = Mock()
        mock_auth_service = Mock()
        mock_auth_service.get_user = Mock(return_value=mock_user)
        mock_auth_service._users = {}

        with patch("ciris_engine.logic.adapters.api.routes.auth.validate_oauth_picture_url", return_value=True):
            _store_oauth_profile(mock_auth_service, "user-123", "Test User", "https://example.com/valid.jpg")

        assert mock_user.oauth_name == "Test User"
        assert mock_user.oauth_picture == "https://example.com/valid.jpg"

    def test_store_oauth_profile_with_invalid_picture(self):
        """Test profile storage with invalid picture URL."""
        from ciris_engine.logic.adapters.api.routes.auth import _store_oauth_profile

        mock_auth_service = Mock()

        with patch("ciris_engine.logic.adapters.api.routes.auth.validate_oauth_picture_url", return_value=False):
            _store_oauth_profile(mock_auth_service, "user-123", "Test User", "javascript:alert('xss')")

        mock_auth_service.get_user.assert_not_called()


class TestOAuthFrontendURL:
    """Test OAUTH_FRONTEND_URL environment variable - covers lines 791-792."""

    def test_build_redirect_response_with_frontend_url(self):
        """Test redirect with OAUTH_FRONTEND_URL configured.

        Note: We need to patch the module-level variable since it's read at import time.
        """
        mock_oauth_user = Mock()
        mock_oauth_user.user_id = "user-123"
        mock_oauth_user.role = UserRole.OBSERVER

        # Patch the module-level variable directly
        with (
            patch("ciris_engine.logic.adapters.api.routes.auth.OAUTH_FRONTEND_URL", "https://scout.ciris.ai"),
            patch("ciris_engine.logic.adapters.api.routes.auth.OAUTH_FRONTEND_PATH", "/oauth-complete.html"),
        ):
            response = _build_redirect_response(
                api_key="test-key", oauth_user=mock_oauth_user, provider="google", redirect_uri=None
            )

        assert response.status_code == 302
        redirect_location = response.headers["location"]
        assert redirect_location.startswith("https://scout.ciris.ai/oauth-complete.html?")


class TestMarketingOptInParsing:
    """Test marketing_opt_in parsing from redirect_uri - covers lines 907, 909."""

    @pytest.mark.asyncio
    async def test_oauth_callback_marketing_opt_in_true(self):
        """Test parsing marketing_opt_in=true from redirect_uri."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        redirect_uri = "https://scout.ciris.ai/callback?marketing_opt_in=true"
        state_data = {"csrf": "test", "redirect_uri": redirect_uri}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth,
        ):
            mock_config.return_value = {"client_id": "id", "client_secret": "secret"}
            mock_oauth.return_value = {
                "external_id": "123",
                "email": "test@example.com",
                "name": "Test",
                "picture": None,
            }

            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "user-123"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            response = await oauth_callback("google", "code", state, mock_request, mock_auth_service)

            # Verify create_oauth_user was called with marketing_opt_in=True
            call_kwargs = mock_auth_service.create_oauth_user.call_args[1]
            assert call_kwargs["marketing_opt_in"] is True

    @pytest.mark.asyncio
    async def test_oauth_callback_marketing_opt_in_false(self):
        """Test parsing marketing_opt_in=false from redirect_uri."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        redirect_uri = "https://scout.ciris.ai/callback?marketing_opt_in=false"
        state_data = {"csrf": "test", "redirect_uri": redirect_uri}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth,
        ):
            mock_config.return_value = {"client_id": "id", "client_secret": "secret"}
            mock_oauth.return_value = {
                "external_id": "123",
                "email": "test@example.com",
                "name": "Test",
                "picture": None,
            }

            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "user-123"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            response = await oauth_callback("google", "code", state, mock_request, mock_auth_service)

            call_kwargs = mock_auth_service.create_oauth_user.call_args[1]
            assert call_kwargs["marketing_opt_in"] is False


class TestOAuthCallbackProviders:
    """Test OAuth callback for different providers - covers lines 929-934, 945."""

    @pytest.mark.asyncio
    async def test_oauth_callback_github(self):
        """Test OAuth callback for GitHub provider."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        state_data = {"csrf": "test"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_github_oauth") as mock_oauth,
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
            mock_config.return_value = {"client_id": "id", "client_secret": "secret"}
            mock_oauth.return_value = {
                "external_id": "456",
                "email": "github@example.com",
                "name": "GitHub User",
                "picture": None,
            }

            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "github:456"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            response = await oauth_callback("github", "code", state, mock_request, mock_auth_service)

            mock_oauth.assert_called_once()
            assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_oauth_callback_discord(self):
        """Test OAuth callback for Discord provider."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        state_data = {"csrf": "test"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_discord_oauth") as mock_oauth,
            patch.dict(os.environ, {"CIRIS_AGENT_ID": "datum"}),
        ):
            mock_config.return_value = {"client_id": "id", "client_secret": "secret"}
            mock_oauth.return_value = {
                "external_id": "789",
                "email": "discord@example.com",
                "name": "Discord User",
                "picture": None,
            }

            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "discord:789"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()

            mock_request = Mock()
            mock_request.app = Mock()
            mock_request.app.state = Mock()

            response = await oauth_callback("discord", "code", state, mock_request, mock_auth_service)

            mock_oauth.assert_called_once()
            assert response.status_code == 302

    @pytest.mark.asyncio
    async def test_oauth_callback_unsupported_provider(self):
        """Test OAuth callback for unsupported provider - covers lines 934."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        state_data = {"csrf": "test"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config:
            mock_config.return_value = {"client_id": "id", "client_secret": "secret"}

            mock_auth_service = Mock()
            mock_request = Mock()

            with pytest.raises(HTTPException) as exc_info:
                await oauth_callback("unsupported", "code", state, mock_request, mock_auth_service)

            assert exc_info.value.status_code == 400
            assert "Unsupported OAuth provider" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_oauth_callback_missing_external_id(self):
        """Test OAuth callback with missing external_id - covers line 945."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        state_data = {"csrf": "test"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth,
        ):
            mock_config.return_value = {"client_id": "id", "client_secret": "secret"}
            mock_oauth.return_value = {
                "external_id": None,  # Missing external_id
                "email": "test@example.com",
                "name": "Test",
                "picture": None,
            }

            mock_auth_service = Mock()
            mock_request = Mock()

            with pytest.raises(HTTPException) as exc_info:
                await oauth_callback("google", "code", state, mock_request, mock_auth_service)

            assert exc_info.value.status_code == 400
            assert "did not return user ID" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_oauth_callback_exception(self):
        """Test OAuth callback exception handling - covers lines 984-986."""
        import base64
        import json

        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback

        state_data = {"csrf": "test"}
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config,
            patch("ciris_engine.logic.adapters.api.routes.auth._handle_google_oauth") as mock_oauth,
        ):
            mock_config.return_value = {"client_id": "id", "client_secret": "secret"}
            mock_oauth.side_effect = RuntimeError("Unexpected error")

            mock_auth_service = Mock()
            mock_request = Mock()

            with pytest.raises(HTTPException) as exc_info:
                await oauth_callback("google", "code", state, mock_request, mock_auth_service)

            assert exc_info.value.status_code == 500
            assert "OAuth callback failed" in exc_info.value.detail


class TestNativeGoogleTokenExchange:
    """Test native Google token exchange - covers lines 1021-1171."""

    @pytest.mark.asyncio
    async def test_verify_google_id_token_success(self):
        """Test successful Google ID token verification via API with full security validation."""
        import time

        from ciris_engine.logic.adapters.api.routes.auth import _verify_google_id_token

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_load_config,
            patch("httpx.AsyncClient") as mock_client,
        ):
            # Mock OAuth config with expected client ID
            mock_load_config.return_value = {"client_id": "test-client-id.apps.googleusercontent.com"}

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "sub": "google-user-123",
                "email": "test@gmail.com",
                "name": "Test User",
                "picture": "https://example.com/pic.jpg",
                "aud": "test-client-id.apps.googleusercontent.com",  # Must match config
                "iss": "accounts.google.com",  # Valid issuer
                "exp": str(int(time.time()) + 3600),  # Not expired (1 hour in future)
                "email_verified": "true",
            }

            mock_context = Mock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            result = await _verify_google_id_token("valid-id-token")

            assert result["external_id"] == "google-user-123"
            assert result["email"] == "test@gmail.com"

    @pytest.mark.asyncio
    async def test_verify_google_id_token_api_failure_no_fallback(self):
        """Test that API failure returns 401 with no fallback (security fix)."""
        from ciris_engine.logic.adapters.api.routes.auth import _verify_google_id_token

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_load_config,
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_load_config.return_value = {"client_id": "test-client-id"}

            mock_response = Mock()
            mock_response.status_code = 400  # API failure
            mock_response.text = "Invalid token"

            mock_context = Mock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            # No fallback - should raise 401
            with pytest.raises(HTTPException) as exc_info:
                await _verify_google_id_token("invalid-token")

            assert exc_info.value.status_code == 401
            assert "Google could not verify" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_google_id_token_audience_mismatch(self):
        """Test error when token audience doesn't match configured client ID (security)."""
        import time

        from ciris_engine.logic.adapters.api.routes.auth import _verify_google_id_token

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_load_config,
            patch("httpx.AsyncClient") as mock_client,
        ):
            # Our expected client ID
            mock_load_config.return_value = {"client_id": "our-client-id.apps.googleusercontent.com"}

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "sub": "attacker-user",
                "email": "attacker@example.com",
                "aud": "different-client-id.apps.googleusercontent.com",  # Wrong audience!
                "iss": "accounts.google.com",
                "exp": str(int(time.time()) + 3600),
            }

            mock_context = Mock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _verify_google_id_token("token-with-wrong-audience")

            assert exc_info.value.status_code == 401
            assert "audience mismatch" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_google_id_token_invalid_issuer(self):
        """Test error when token issuer is not Google (security)."""
        import time

        from ciris_engine.logic.adapters.api.routes.auth import _verify_google_id_token

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_load_config,
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_load_config.return_value = {"client_id": "test-client-id"}

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "sub": "user-123",
                "email": "test@example.com",
                "aud": "test-client-id",
                "iss": "malicious-issuer.com",  # Wrong issuer!
                "exp": str(int(time.time()) + 3600),
            }

            mock_context = Mock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _verify_google_id_token("token-with-wrong-issuer")

            assert exc_info.value.status_code == 401
            assert "issuer mismatch" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_google_id_token_expired(self):
        """Test error when token is expired (security)."""
        import time

        from ciris_engine.logic.adapters.api.routes.auth import _verify_google_id_token

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_load_config,
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_load_config.return_value = {"client_id": "test-client-id"}

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "sub": "user-123",
                "email": "test@example.com",
                "aud": "test-client-id",
                "iss": "accounts.google.com",
                "exp": str(int(time.time()) - 3600),  # Expired 1 hour ago!
            }

            mock_context = Mock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _verify_google_id_token("expired-token")

            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_google_id_token_missing_sub(self):
        """Test error when token is missing 'sub' claim."""
        import time

        from ciris_engine.logic.adapters.api.routes.auth import _verify_google_id_token

        with (
            patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_load_config,
            patch("httpx.AsyncClient") as mock_client,
        ):
            mock_load_config.return_value = {"client_id": "test-client-id"}

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "email": "test@example.com",  # Missing 'sub'!
                "aud": "test-client-id",
                "iss": "accounts.google.com",
                "exp": str(int(time.time()) + 3600),
            }

            mock_context = Mock()
            mock_context.get = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _verify_google_id_token("token-without-sub")

            assert exc_info.value.status_code == 401
            assert "sub claim" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_verify_google_id_token_oauth_not_configured(self):
        """Test on-device mode when Google OAuth is not configured.

        When OAuth is not configured, the function should:
        1. Catch the 404 HTTPException and return None for allowed_audiences
        2. Skip audience validation (on-device mode)
        3. Proceed with Google's tokeninfo API verification
        4. Return 401 if Google rejects the token
        """
        from ciris_engine.logic.adapters.api.routes.auth import _verify_google_id_token

        with patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_load_config:
            mock_load_config.side_effect = HTTPException(
                status_code=404, detail="OAuth provider 'google' not configured"
            )

            # Mock httpx to return a 401 from Google (token invalid)
            with patch("httpx.AsyncClient") as mock_client:
                mock_response = Mock()
                mock_response.status_code = 401
                mock_response.text = "Invalid token"
                mock_context = Mock()
                mock_context.get = AsyncMock(return_value=mock_response)
                mock_client.return_value.__aenter__.return_value = mock_context

                with pytest.raises(HTTPException) as exc_info:
                    await _verify_google_id_token("any-token")

                # In on-device mode, Google rejects invalid tokens with 401
                assert exc_info.value.status_code == 401
                assert "could not verify" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_native_google_token_exchange_success(self):
        """Test successful native Google token exchange."""
        from ciris_engine.logic.adapters.api.routes.auth import NativeTokenRequest, native_google_token_exchange

        request = NativeTokenRequest(id_token="valid-id-token", provider="google")

        with patch("ciris_engine.logic.adapters.api.routes.auth._verify_google_id_token") as mock_verify:
            mock_verify.return_value = {
                "external_id": "google-123",
                "email": "native@example.com",
                "name": "Native User",
                "picture": None,
            }

            mock_auth_service = Mock()
            mock_oauth_user = Mock()
            mock_oauth_user.user_id = "google:google-123"
            mock_oauth_user.role = UserRole.OBSERVER
            mock_auth_service.create_oauth_user = Mock(return_value=mock_oauth_user)
            mock_auth_service.get_user = Mock(return_value=None)
            mock_auth_service.store_api_key = Mock()
            mock_auth_service._oauth_users = {"existing": Mock()}  # Not first user

            response = await native_google_token_exchange(request, mock_auth_service)

            assert response.user_id == "google:google-123"
            assert response.role == "OBSERVER"
            assert response.email == "native@example.com"

    @pytest.mark.asyncio
    async def test_native_google_token_exchange_unsupported_provider(self):
        """Test native token exchange with unsupported provider."""
        from ciris_engine.logic.adapters.api.routes.auth import NativeTokenRequest, native_google_token_exchange

        request = NativeTokenRequest(id_token="token", provider="facebook")
        mock_auth_service = Mock()

        with pytest.raises(HTTPException) as exc_info:
            await native_google_token_exchange(request, mock_auth_service)

        assert exc_info.value.status_code == 400
        assert "Only 'google' provider is currently supported" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_native_google_token_exchange_missing_external_id(self):
        """Test native token exchange when external_id is missing."""
        from ciris_engine.logic.adapters.api.routes.auth import NativeTokenRequest, native_google_token_exchange

        request = NativeTokenRequest(id_token="token", provider="google")

        with patch("ciris_engine.logic.adapters.api.routes.auth._verify_google_id_token") as mock_verify:
            mock_verify.return_value = {
                "external_id": None,
                "email": "test@example.com",
                "name": "Test",
                "picture": None,
            }

            mock_auth_service = Mock()

            with pytest.raises(HTTPException) as exc_info:
                await native_google_token_exchange(request, mock_auth_service)

            assert exc_info.value.status_code == 400
            assert "did not contain user ID" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_native_google_token_exchange_exception(self):
        """Test native token exchange exception handling."""
        from ciris_engine.logic.adapters.api.routes.auth import NativeTokenRequest, native_google_token_exchange

        request = NativeTokenRequest(id_token="token", provider="google")

        with patch("ciris_engine.logic.adapters.api.routes.auth._verify_google_id_token") as mock_verify:
            mock_verify.side_effect = RuntimeError("Unexpected error")

            mock_auth_service = Mock()

            with pytest.raises(HTTPException) as exc_info:
                await native_google_token_exchange(request, mock_auth_service)

            assert exc_info.value.status_code == 500
            assert "Native token exchange failed" in exc_info.value.detail


class TestAPIKeyManagement:
    """Test API key management endpoints - covers lines 1192-1272."""

    @pytest.mark.asyncio
    async def test_create_api_key(self):
        """Test creating an API key - covers lines 1192-1209."""
        from ciris_engine.logic.adapters.api.routes.auth import create_api_key
        from ciris_engine.schemas.api.auth import APIKeyCreateRequest, AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"
        mock_auth.role = UserRole.ADMIN

        mock_auth_service = Mock()
        mock_auth_service.store_api_key = Mock()

        request = APIKeyCreateRequest(expires_in_minutes=60, description="Test API key")

        response = await create_api_key(request, mock_auth, mock_auth_service)

        mock_auth_service.store_api_key.assert_called_once()
        assert response.api_key.startswith("ciris_admin_")
        assert response.role == UserRole.ADMIN
        assert response.description == "Test API key"

    @pytest.mark.asyncio
    async def test_list_api_keys(self):
        """Test listing API keys - covers lines 1229-1246."""
        from ciris_engine.logic.adapters.api.routes.auth import list_api_keys
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"

        # Create mock stored keys
        mock_key1 = Mock()
        mock_key1.key_id = "key-1"
        mock_key1.role = UserRole.ADMIN
        mock_key1.expires_at = datetime.now(timezone.utc)
        mock_key1.description = "Key 1"
        mock_key1.created_at = datetime.now(timezone.utc)
        mock_key1.created_by = "user-123"
        mock_key1.last_used = None
        mock_key1.is_active = True

        mock_key2 = Mock()
        mock_key2.key_id = "key-2"
        mock_key2.role = UserRole.OBSERVER
        mock_key2.expires_at = datetime.now(timezone.utc)
        mock_key2.description = "Key 2"
        mock_key2.created_at = datetime.now(timezone.utc)
        mock_key2.created_by = "user-123"
        mock_key2.last_used = datetime.now(timezone.utc)
        mock_key2.is_active = False

        mock_auth_service = Mock()
        mock_auth_service.list_user_api_keys = Mock(return_value=[mock_key1, mock_key2])

        response = await list_api_keys(mock_auth, mock_auth_service)

        assert response.total == 2
        assert len(response.api_keys) == 2
        assert response.api_keys[0].key_id == "key-1"
        assert response.api_keys[1].key_id == "key-2"

    @pytest.mark.asyncio
    async def test_delete_api_key_success(self):
        """Test deleting an API key - covers lines 1261-1272."""
        from ciris_engine.logic.adapters.api.routes.auth import delete_api_key
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"

        mock_key = Mock()
        mock_key.key_id = "key-to-delete"

        mock_auth_service = Mock()
        mock_auth_service.list_user_api_keys = Mock(return_value=[mock_key])
        mock_auth_service.revoke_api_key = Mock()

        result = await delete_api_key("key-to-delete", mock_auth, mock_auth_service)

        mock_auth_service.revoke_api_key.assert_called_once_with("key-to-delete")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self):
        """Test deleting a non-existent API key."""
        from ciris_engine.logic.adapters.api.routes.auth import delete_api_key
        from ciris_engine.schemas.api.auth import AuthContext

        mock_auth = Mock(spec=AuthContext)
        mock_auth.user_id = "user-123"

        mock_auth_service = Mock()
        mock_auth_service.list_user_api_keys = Mock(return_value=[])  # No keys

        with pytest.raises(HTTPException) as exc_info:
            await delete_api_key("non-existent-key", mock_auth, mock_auth_service)

        assert exc_info.value.status_code == 404
        assert "API key not found" in exc_info.value.detail


class TestGoogleOAuthUserInfoError:
    """Test Google OAuth user info fetch error - covers line 534."""

    @pytest.mark.asyncio
    async def test_google_oauth_user_info_error(self):
        """Test Google OAuth user info fetch error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_token_response = Mock()
            mock_token_response.status_code = 200
            mock_token_response.json.return_value = {"access_token": "test-token"}

            mock_user_response = Mock()
            mock_user_response.status_code = 401  # User info fetch failed

            mock_context = Mock()
            mock_context.post = AsyncMock(return_value=mock_token_response)
            mock_context.get = AsyncMock(return_value=mock_user_response)
            mock_client.return_value.__aenter__.return_value = mock_context

            with pytest.raises(HTTPException) as exc_info:
                await _handle_google_oauth("test-code", "client-id", "client-secret")

            assert exc_info.value.status_code == 400
            assert "Failed to fetch user info" in exc_info.value.detail
