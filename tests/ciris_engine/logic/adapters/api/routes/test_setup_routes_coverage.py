"""Additional tests for setup routes to increase coverage.

Covers uncovered helper functions:
- _validate_api_key_for_provider
- _classify_llm_connection_error
- _validate_setup_passwords
- _log_oauth_linking_skip
- _get_llm_providers
- _get_available_adapters
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.setup import (
    LLMValidationRequest,
    SetupCompleteRequest,
    _classify_llm_connection_error,
    _get_available_adapters,
    _get_llm_providers,
    _log_oauth_linking_skip,
    _validate_api_key_for_provider,
    _validate_setup_passwords,
)


class TestValidateApiKeyForProvider:
    """Tests for _validate_api_key_for_provider helper."""

    def test_openai_invalid_placeholder_key(self):
        """OpenAI provider with placeholder API key returns error."""
        config = LLMValidationRequest(
            provider="openai",
            api_key="your_openai_api_key_here",
        )
        result = _validate_api_key_for_provider(config)
        assert result is not None
        assert result.valid is False
        assert "Invalid API key" in result.message

    def test_openai_empty_api_key(self):
        """OpenAI provider with empty API key returns error."""
        config = LLMValidationRequest(
            provider="openai",
            api_key="",
        )
        result = _validate_api_key_for_provider(config)
        assert result is not None
        assert result.valid is False

    def test_openai_valid_api_key(self):
        """OpenAI provider with valid API key returns None (valid)."""
        config = LLMValidationRequest(
            provider="openai",
            api_key="sk-test-key-12345",
        )
        result = _validate_api_key_for_provider(config)
        assert result is None  # None means valid

    def test_local_provider_no_api_key_required(self):
        """Local provider doesn't require API key."""
        config = LLMValidationRequest(
            provider="local",
            api_key="",
            base_url="http://localhost:11434",
        )
        result = _validate_api_key_for_provider(config)
        assert result is None  # Valid

    def test_other_provider_missing_api_key(self):
        """Other providers require API key."""
        config = LLMValidationRequest(
            provider="other",
            api_key="",
            base_url="https://api.example.com",
        )
        result = _validate_api_key_for_provider(config)
        assert result is not None
        assert result.valid is False
        assert "API key required" in result.message

    def test_other_provider_with_api_key(self):
        """Other provider with API key is valid."""
        config = LLMValidationRequest(
            provider="other",
            api_key="test-api-key",
            base_url="https://api.example.com",
        )
        result = _validate_api_key_for_provider(config)
        assert result is None  # Valid


class TestClassifyLLMConnectionError:
    """Tests for _classify_llm_connection_error helper."""

    def test_unauthorized_401_error(self):
        """401 error is classified as authentication failed."""
        error = Exception("Error: 401 Unauthorized")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Authentication failed" in result.message
        assert "Invalid API key" in result.error

    def test_unauthorized_text_error(self):
        """Unauthorized text is classified as authentication failed."""
        error = Exception("Unauthorized access")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Authentication failed" in result.message

    def test_not_found_404_error(self):
        """404 error is classified as endpoint not found."""
        error = Exception("Error: 404 Not Found")
        result = _classify_llm_connection_error(error, "https://api.example.com/v1")
        assert result.valid is False
        assert "Endpoint not found" in result.message
        assert "api.example.com/v1" in result.error

    def test_not_found_text_error(self):
        """Not Found text is classified as endpoint not found."""
        error = Exception("Not Found: page does not exist")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Endpoint not found" in result.message

    def test_timeout_error(self):
        """Timeout error is classified appropriately."""
        error = Exception("Connection timeout while waiting for response")
        result = _classify_llm_connection_error(error, "http://localhost:11434")
        assert result.valid is False
        assert "Connection timeout" in result.message
        assert "Could not connect" in result.error

    def test_generic_error(self):
        """Generic error is classified as connection failed."""
        error = Exception("Some other network error")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Connection failed" in result.message
        assert "Some other network error" in result.error


class TestValidateSetupPasswords:
    """Tests for _validate_setup_passwords helper."""

    def test_oauth_user_without_password_generates_random(self):
        """OAuth user without password gets a generated one."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password=None,
            oauth_provider="google",
        )
        result = _validate_setup_passwords(setup, is_oauth_user=True)
        assert len(result) > 8  # Generated password should be long

    def test_oauth_user_with_empty_password_generates_random(self):
        """OAuth user with empty password gets a generated one."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="",
            oauth_provider="google",
        )
        result = _validate_setup_passwords(setup, is_oauth_user=True)
        assert len(result) > 8

    def test_non_oauth_user_without_password_raises_error(self):
        """Non-OAuth user without password raises HTTPException."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_setup_passwords(setup, is_oauth_user=False)
        assert exc_info.value.status_code == 400
        assert "at least 8 characters" in exc_info.value.detail

    def test_password_too_short_raises_error(self):
        """Password shorter than 8 characters raises HTTPException."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="short",
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_setup_passwords(setup, is_oauth_user=False)
        assert exc_info.value.status_code == 400
        assert "at least 8 characters" in exc_info.value.detail

    def test_valid_password_returns_same(self):
        """Valid password is returned unchanged."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="validpassword123",
        )
        result = _validate_setup_passwords(setup, is_oauth_user=False)
        assert result == "validpassword123"

    def test_system_admin_password_too_short_raises_error(self):
        """System admin password too short raises HTTPException."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="validpassword123",
            system_admin_password="short",
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_setup_passwords(setup, is_oauth_user=False)
        assert exc_info.value.status_code == 400
        assert "System admin password" in exc_info.value.detail


class TestLogOAuthLinkingSkip:
    """Tests for _log_oauth_linking_skip helper."""

    def test_logs_missing_provider(self):
        """Logs reason when oauth_provider is missing."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="password123",
            oauth_provider=None,
            oauth_external_id="12345",
        )
        # Should not raise, just logs
        _log_oauth_linking_skip(setup)

    def test_logs_missing_external_id(self):
        """Logs reason when oauth_external_id is missing."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="password123",
            oauth_provider="google",
            oauth_external_id=None,
        )
        # Should not raise, just logs
        _log_oauth_linking_skip(setup)


class TestGetLLMProviders:
    """Tests for _get_llm_providers helper."""

    def test_returns_list_of_providers(self):
        """Returns a list of LLM providers."""
        providers = _get_llm_providers()
        assert isinstance(providers, list)
        assert len(providers) >= 3  # At least openai, local, other

    def test_provider_ids(self):
        """Providers have expected IDs."""
        providers = _get_llm_providers()
        provider_ids = {p.id for p in providers}
        assert "openai" in provider_ids
        assert "local" in provider_ids
        assert "other" in provider_ids

    def test_openai_provider_config(self):
        """OpenAI provider has correct configuration."""
        providers = _get_llm_providers()
        openai = next(p for p in providers if p.id == "openai")
        assert openai.requires_api_key is True
        assert openai.requires_base_url is False
        assert openai.default_model == "gpt-4"

    def test_local_provider_config(self):
        """Local provider has correct configuration."""
        providers = _get_llm_providers()
        local = next(p for p in providers if p.id == "local")
        assert local.requires_api_key is False
        assert local.requires_base_url is True
        assert local.requires_model is True
        assert "11434" in local.default_base_url


class TestGetAvailableAdapters:
    """Tests for _get_available_adapters helper."""

    def test_returns_list_of_adapters(self):
        """Returns a list of adapters."""
        adapters = _get_available_adapters()
        assert isinstance(adapters, list)
        assert len(adapters) >= 2  # At least api, cli

    def test_adapter_ids(self):
        """Adapters have expected IDs."""
        adapters = _get_available_adapters()
        adapter_ids = {a.id for a in adapters}
        assert "api" in adapter_ids
        assert "cli" in adapter_ids

    def test_api_adapter_enabled_by_default(self):
        """API adapter is enabled by default."""
        adapters = _get_available_adapters()
        api = next(a for a in adapters if a.id == "api")
        assert api.enabled_by_default is True

    def test_discord_adapter_requires_env_vars(self):
        """Discord adapter requires DISCORD_BOT_TOKEN."""
        adapters = _get_available_adapters()
        discord = next((a for a in adapters if a.id == "discord"), None)
        if discord:
            assert "DISCORD_BOT_TOKEN" in discord.required_env_vars
