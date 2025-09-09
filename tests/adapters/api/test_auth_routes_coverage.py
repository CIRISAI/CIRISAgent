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
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes.auth import (
    _determine_user_role,
    _generate_api_key_and_store,
    _handle_discord_oauth,
    _handle_github_oauth,
    _handle_google_oauth,
    _load_oauth_config,
    get_oauth_callback_url,
    router,
)
from ciris_engine.schemas.api.auth import UserRole, LoginRequest


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
        
        assert store_call[1]['user_id'] == "test-user-123"
        assert store_call[1]['role'] == UserRole.ADMIN
        assert store_call[1]['description'] == "Login session"
        
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
        
        # Mock auth service
        mock_auth_service = Mock()
        mock_auth_service.store_api_key = Mock()
        mock_auth_service.revoke_api_key = Mock()
        
        response = await refresh_token(mock_auth_context, mock_auth_service)
        
        # Verify 24-hour expiration for SYSTEM_ADMIN
        store_call = mock_auth_service.store_api_key.call_args
        assert store_call[1]['description'] == "Refreshed token"
        
        # Verify old key revocation
        mock_auth_service.revoke_api_key.assert_called_once_with("old-key-123")
        
        # Verify response has shorter expiration
        assert response.expires_in == 86400  # 24 hours

    @pytest.mark.asyncio
    async def test_refresh_token_regular_role(self, mock_auth_context):
        """Test token refresh for regular role - covers lines 183-184."""
        mock_auth_context.role = UserRole.OBSERVER
        
        from ciris_engine.logic.adapters.api.routes.auth import refresh_token
        
        mock_auth_service = Mock()
        mock_auth_service.store_api_key = Mock()
        mock_auth_service.revoke_api_key = Mock()
        
        response = await refresh_token(mock_auth_context, mock_auth_service)
        
        # Verify 30-day expiration for regular users
        assert response.expires_in == 2592000  # 30 days


class TestOAuthHelperMethods:
    """Test the OAuth helper methods that were refactored."""

    def test_load_oauth_config_success(self):
        """Test successful OAuth config loading."""
        with patch.dict(os.environ, {
            'GOOGLE_OAUTH_CLIENT_ID': 'test-google-id',
            'GOOGLE_OAUTH_CLIENT_SECRET': 'test-google-secret'
        }):
            config = _load_oauth_config('google')
            
            assert config['client_id'] == 'test-google-id'
            assert config['client_secret'] == 'test-google-secret'

    def test_load_oauth_config_missing_vars(self):
        """Test OAuth config loading with missing environment variables."""
        # Clear any existing OAuth env vars
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                _load_oauth_config('google')
            
            assert exc_info.value.status_code == 500
            assert "OAuth configuration incomplete" in exc_info.value.detail

    def test_load_oauth_config_unsupported_provider(self):
        """Test OAuth config loading with unsupported provider."""
        with pytest.raises(HTTPException) as exc_info:
            _load_oauth_config('unsupported')
        
        assert exc_info.value.status_code == 400
        assert "Unsupported OAuth provider" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_handle_google_oauth_success(self):
        """Test successful Google OAuth handling."""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock token response
            mock_token_response = Mock()
            mock_token_response.json = AsyncMock(return_value={'access_token': 'test-token'})
            
            # Mock user info response  
            mock_user_response = Mock()
            mock_user_response.json = AsyncMock(return_value={
                'email': 'test@example.com',
                'name': 'Test User',
                'picture': 'https://example.com/pic.jpg'
            })
            
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_token_response
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_user_response
            
            result = await _handle_google_oauth('test-code', 'client-id', 'client-secret')
            
            assert result['email'] == 'test@example.com'
            assert result['name'] == 'Test User'
            assert result['picture'] == 'https://example.com/pic.jpg'

    @pytest.mark.asyncio
    async def test_handle_google_oauth_token_error(self):
        """Test Google OAuth with token exchange error."""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock failed token response
            mock_token_response = Mock()
            mock_token_response.json = AsyncMock(return_value={'error': 'invalid_grant'})
            
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_token_response
            
            result = await _handle_google_oauth('bad-code', 'client-id', 'client-secret')
            
            # Should return None values on error
            assert result['email'] is None
            assert result['name'] is None
            assert result['picture'] is None

    @pytest.mark.asyncio 
    async def test_handle_github_oauth_success(self):
        """Test successful GitHub OAuth handling."""
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock token response
            mock_token_response = Mock()
            mock_token_response.text = AsyncMock(return_value='access_token=test-token&token_type=bearer')
            
            # Mock user info response
            mock_user_response = Mock()
            mock_user_response.json = AsyncMock(return_value={
                'email': 'test@github.com',
                'name': 'GitHub User',
                'avatar_url': 'https://avatars.githubusercontent.com/u/123'
            })
            
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_token_response
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_user_response
            
            result = await _handle_github_oauth('test-code', 'client-id', 'client-secret')
            
            assert result['email'] == 'test@github.com'
            assert result['name'] == 'GitHub User'
            assert result['picture'] == 'https://avatars.githubusercontent.com/u/123'

    @pytest.mark.asyncio
    async def test_handle_discord_oauth_success(self):
        """Test successful Discord OAuth handling.""" 
        with patch('aiohttp.ClientSession') as mock_session:
            # Mock token response
            mock_token_response = Mock()
            mock_token_response.json = AsyncMock(return_value={'access_token': 'test-token'})
            
            # Mock user info response
            mock_user_response = Mock()
            mock_user_response.json = AsyncMock(return_value={
                'email': 'test@discord.com',
                'username': 'DiscordUser',
                'avatar': 'avatar123',
                'id': '123456789'
            })
            
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_token_response
            mock_session.return_value.__aenter__.return_value.get.return_value.__aenter__.return_value = mock_user_response
            
            result = await _handle_discord_oauth('test-code', 'client-id', 'client-secret')
            
            assert result['email'] == 'test@discord.com'
            assert result['name'] == 'DiscordUser'
            assert result['picture'] == 'https://cdn.discordapp.com/avatars/123456789/avatar123.png'

    def test_determine_user_role_admin_email(self):
        """Test user role determination for admin email."""
        role = _determine_user_role('admin@ciris.ai')
        assert role == UserRole.ADMIN

    def test_determine_user_role_regular_user(self):
        """Test user role determination for regular user.""" 
        role = _determine_user_role('user@example.com')
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
        
        api_key = _generate_api_key_and_store(mock_auth_service, mock_oauth_user, 'google')
        
        # Verify API key storage called
        mock_auth_service.store_api_key.assert_called_once()
        
        # Verify API key format
        assert api_key.startswith('ciris_observer_')


class TestEnvironmentVariableFallbacks:
    """Test environment variable fallback logic."""

    def test_oauth_callback_url_default(self):
        """Test OAuth callback URL with default base - covers lines 54-56."""
        with patch.dict(os.environ, {'CIRIS_AGENT_ID': 'datum'}, clear=True):
            url = get_oauth_callback_url('google')
            assert url == 'https://agents.ciris.ai/v1/auth/oauth/datum/google/callback'

    def test_oauth_callback_url_custom_base(self):
        """Test OAuth callback URL with custom base."""
        with patch.dict(os.environ, {'OAUTH_CALLBACK_BASE_URL': 'https://custom.domain', 'CIRIS_AGENT_ID': 'datum'}):
            url = get_oauth_callback_url('github')
            assert url == 'https://custom.domain/v1/auth/oauth/datum/github/callback'

    def test_oauth_callback_url_explicit_base(self):
        """Test OAuth callback URL with explicit base parameter."""
        with patch.dict(os.environ, {'CIRIS_AGENT_ID': 'datum'}):
            url = get_oauth_callback_url('discord', base_url='https://test.local')
            assert url == 'https://test.local/v1/auth/oauth/datum/discord/callback'


class TestOAuthErrorPaths:
    """Test error paths in OAuth callback handling."""

    @pytest.mark.asyncio
    async def test_oauth_callback_missing_code(self):
        """Test OAuth callback without code parameter."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback
        
        mock_request = Mock()
        mock_auth_service = Mock()
        
        with pytest.raises(HTTPException) as exc_info:
            await oauth_callback('google', None, mock_request, mock_auth_service)
        
        assert exc_info.value.status_code == 400
        assert "Authorization code is required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_oauth_callback_invalid_provider(self):
        """Test OAuth callback with invalid provider."""
        from ciris_engine.logic.adapters.api.routes.auth import oauth_callback
        
        mock_request = Mock()
        mock_auth_service = Mock()
        
        # This should trigger the _load_oauth_config error for unsupported provider
        with pytest.raises(HTTPException) as exc_info:
            await oauth_callback('invalid', 'test-code', mock_request, mock_auth_service)
        
        assert exc_info.value.status_code == 400
        assert "Unsupported OAuth provider" in exc_info.value.detail