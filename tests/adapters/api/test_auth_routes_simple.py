"""
Simple unit tests for auth.py routes focusing on uncovered lines.

This test file focuses on directly testing individual functions that were
identified as having low coverage, without complex integration testing.
"""

import os
import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.auth import (
    _determine_user_role,
    _load_oauth_config,
    get_oauth_callback_url,
)
from ciris_engine.schemas.api.auth import UserRole


class TestOAuthConfig:
    """Test OAuth configuration loading functions."""

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_load_oauth_config_google_success(self, mock_read_text, mock_exists):
        """Test successful OAuth config loading for Google."""
        mock_exists.return_value = True
        mock_read_text.return_value = '{"google": {"client_id": "test-google-id", "client_secret": "test-google-secret"}}'
        
        config = _load_oauth_config('google')
        
        assert config['client_id'] == 'test-google-id'
        assert config['client_secret'] == 'test-google-secret'

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text') 
    def test_load_oauth_config_github_success(self, mock_read_text, mock_exists):
        """Test successful OAuth config loading for GitHub."""
        mock_exists.return_value = True
        mock_read_text.return_value = '{"github": {"client_id": "test-github-id", "client_secret": "test-github-secret"}}'
        
        config = _load_oauth_config('github')
        
        assert config['client_id'] == 'test-github-id'
        assert config['client_secret'] == 'test-github-secret'

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_load_oauth_config_discord_success(self, mock_read_text, mock_exists):
        """Test successful OAuth config loading for Discord."""
        mock_exists.return_value = True
        mock_read_text.return_value = '{"discord": {"client_id": "test-discord-id", "client_secret": "test-discord-secret"}}'
        
        config = _load_oauth_config('discord')
        
        assert config['client_id'] == 'test-discord-id'
        assert config['client_secret'] == 'test-discord-secret'

    @patch('pathlib.Path.exists')
    def test_load_oauth_config_file_not_found(self, mock_exists):
        """Test OAuth config loading when config file doesn't exist."""
        mock_exists.return_value = False
        
        with pytest.raises(HTTPException) as exc_info:
            _load_oauth_config('google')
        
        assert exc_info.value.status_code == 404
        assert "OAuth provider 'google' not configured" in exc_info.value.detail

    @patch('pathlib.Path.exists')
    @patch('pathlib.Path.read_text')
    def test_load_oauth_config_provider_not_in_config(self, mock_read_text, mock_exists):
        """Test OAuth config loading when provider not in config file."""
        mock_exists.return_value = True
        mock_read_text.return_value = '{"github": {"client_id": "test-id", "client_secret": "test-secret"}}'
        
        with pytest.raises(HTTPException) as exc_info:
            _load_oauth_config('google')
        
        assert exc_info.value.status_code == 404
        assert "OAuth provider 'google' not configured" in exc_info.value.detail


class TestUserRoleDetermination:
    """Test user role determination logic."""

    def test_determine_user_role_admin_email(self):
        """Test user role determination for admin email."""
        # The function checks for @ciris.ai domain, not ADMIN_EMAIL env var
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

    def test_determine_user_role_empty_string(self):
        """Test user role determination with empty string email."""
        role = _determine_user_role('')
        assert role == UserRole.OBSERVER


class TestOAuthCallbackUrl:
    """Test OAuth callback URL generation."""

    def test_oauth_callback_url_default_agent(self):
        """Test OAuth callback URL with default agent ID.""" 
        # Test with default environment (no custom base URL)
        url = get_oauth_callback_url('google')
        # Should be exactly this URL with default agent ID 'datum'
        assert url == 'https://agents.ciris.ai/v1/auth/oauth/datum/google/callback'

    def test_oauth_callback_url_custom_base(self):
        """Test OAuth callback URL with custom base."""
        with patch.dict(os.environ, {'OAUTH_CALLBACK_BASE_URL': 'https://custom.domain'}):
            url = get_oauth_callback_url('github')
            assert url == 'https://custom.domain/v1/auth/oauth/datum/github/callback'

    def test_oauth_callback_url_explicit_base(self):
        """Test OAuth callback URL with explicit base parameter."""
        url = get_oauth_callback_url('discord', base_url='https://test.local')
        assert url == 'https://test.local/v1/auth/oauth/datum/discord/callback'

    def test_oauth_callback_url_different_providers(self):
        """Test OAuth callback URL for different providers."""
        for provider in ['google', 'github', 'discord']:
            url = get_oauth_callback_url(provider)
            assert provider in url
            assert '/callback' in url


class TestEnvironmentHandling:
    """Test environment variable handling and fallbacks."""

    def test_oauth_config_missing_env_vars(self):
        """Test OAuth config with missing environment variables."""
        # Clear environment completely for this provider
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                _load_oauth_config('google')
            
            assert exc_info.value.status_code == 404

    def test_oauth_config_partial_env_vars(self):
        """Test OAuth config with only client_id set."""
        with patch.dict(os.environ, {
            'GOOGLE_OAUTH_CLIENT_ID': 'test-id'
            # Missing GOOGLE_OAUTH_CLIENT_SECRET
        }, clear=True):
            with pytest.raises(HTTPException) as exc_info:
                _load_oauth_config('google')
            
            assert exc_info.value.status_code == 404

    def test_default_callback_base_url(self):
        """Test default callback base URL when env var not set."""
        with patch.dict(os.environ, {}, clear=False):
            if 'OAUTH_CALLBACK_BASE_URL' in os.environ:
                del os.environ['OAUTH_CALLBACK_BASE_URL']
            
            url = get_oauth_callback_url('google')
            # Should use default base URL
            assert 'agents.ciris.ai' in url or url.startswith('https://')