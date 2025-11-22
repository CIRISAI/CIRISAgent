"""
Unit tests for setup wizard API routes.

Tests all setup endpoints including:
- Setup status checking
- LLM provider/template/adapter listing
- LLM validation
- Setup completion with dual password support
- Configuration retrieval and updating
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import status

from ciris_engine.logic.adapters.api.routes.setup import (
    LLMProvider,
    LLMValidationRequest,
    SetupCompleteRequest,
    _get_agent_templates,
    _get_available_adapters,
    _get_llm_providers,
    _is_setup_allowed_without_auth,
    _validate_llm_connection,
)
from ciris_engine.schemas.api.auth import UserRole


class TestSetupStatusEndpoint:
    """Test GET /v1/setup/status endpoint."""

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    @patch("ciris_engine.logic.adapters.api.routes.setup.get_default_config_path")
    def test_get_setup_status_first_run(self, mock_config_path, mock_first_run, client):
        """Test status endpoint when this is first run."""
        mock_first_run.return_value = True
        mock_config_path.return_value = Path("/home/user/.ciris/.env")

        response = client.get("/v1/setup/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["is_first_run"] is True
        assert data["config_exists"] is False
        assert data["setup_required"] is True
        assert data["config_path"] is None

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    @patch("ciris_engine.logic.adapters.api.routes.setup.get_default_config_path")
    def test_get_setup_status_already_configured(self, mock_config_path, mock_first_run, client, tmp_path):
        """Test status endpoint when already configured."""
        mock_first_run.return_value = False
        config_file = tmp_path / ".env"
        config_file.write_text("CIRIS_CONFIGURED=true")
        mock_config_path.return_value = config_file

        response = client.get("/v1/setup/status")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["is_first_run"] is False
        assert data["config_exists"] is True
        assert data["setup_required"] is False
        assert data["config_path"] == str(config_file)

    def test_setup_status_no_auth_required(self, client):
        """Test that setup status doesn't require authentication."""
        # Should work without auth headers
        response = client.get("/v1/setup/status")
        # Should not return 401
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


class TestProvidersEndpoint:
    """Test GET /v1/setup/providers endpoint."""

    def test_list_providers(self, client):
        """Test listing LLM providers."""
        response = client.get("/v1/setup/providers")

        assert response.status_code == status.HTTP_200_OK
        providers = response.json()["data"]
        assert isinstance(providers, list)
        assert len(providers) == 3  # openai, local, other

        # Check OpenAI provider
        openai = next(p for p in providers if p["id"] == "openai")
        assert openai["name"] == "OpenAI"
        assert openai["requires_api_key"] is True
        assert openai["requires_base_url"] is False

        # Check local LLM provider
        local = next(p for p in providers if p["id"] == "local")
        assert local["name"] == "Local LLM"
        assert local["requires_base_url"] is True
        assert local["default_base_url"] == "http://localhost:11434"
        assert local["default_model"] == "llama3"

        # Check other provider
        other = next(p for p in providers if p["id"] == "other")
        assert other["name"] == "OpenAI-Compatible Provider"
        assert other["requires_api_key"] is True
        assert other["requires_base_url"] is True
        assert other["requires_model"] is True

    def test_providers_no_auth_required(self, client):
        """Test that providers list doesn't require authentication."""
        response = client.get("/v1/setup/providers")
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


class TestTemplatesEndpoint:
    """Test GET /v1/setup/templates endpoint."""

    def test_list_templates(self, client):
        """Test listing agent templates from ciris_templates directory."""
        response = client.get("/v1/setup/templates")

        assert response.status_code == status.HTTP_200_OK
        templates = response.json()["data"]
        assert isinstance(templates, list)
        assert len(templates) >= 1  # At least one template should exist

        # All templates should have required fields
        for template in templates:
            assert "id" in template
            assert "name" in template
            assert "description" in template
            assert "identity" in template
            assert "supported_sops" in template
            assert "stewardship_tier" in template
            assert "creator_id" in template
            assert "signature" in template

            # Stewardship tier should be 1-5
            assert 1 <= template["stewardship_tier"] <= 5

            # All templates should have DSAR SOPs
            assert "DSAR_ACCESS" in template["supported_sops"]
            assert "DSAR_DELETE" in template["supported_sops"]
            assert "DSAR_EXPORT" in template["supported_sops"]
            assert "DSAR_RECTIFY" in template["supported_sops"]

        # Check default template exists
        default = next((t for t in templates if t["id"] == "default"), None)
        assert default is not None
        assert default["name"] == "Datum"

    def test_templates_no_auth_required(self, client):
        """Test that templates list doesn't require authentication."""
        response = client.get("/v1/setup/templates")
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


class TestAdaptersEndpoint:
    """Test GET /v1/setup/adapters endpoint."""

    def test_list_adapters(self, client):
        """Test listing available adapters."""
        response = client.get("/v1/setup/adapters")

        assert response.status_code == status.HTTP_200_OK
        adapters = response.json()["data"]
        assert isinstance(adapters, list)
        assert len(adapters) == 4  # api, cli, discord, reddit

        # Check API adapter
        api = next(a for a in adapters if a["id"] == "api")
        assert api["name"] == "Web API"
        assert api["enabled_by_default"] is True

        # Check Discord adapter
        discord = next(a for a in adapters if a["id"] == "discord")
        assert discord["name"] == "Discord Bot"
        assert "DISCORD_BOT_TOKEN" in discord["required_env_vars"]

        # Check Reddit adapter
        reddit = next(a for a in adapters if a["id"] == "reddit")
        assert "CIRIS_REDDIT_CLIENT_ID" in reddit["required_env_vars"]
        assert len(reddit["required_env_vars"]) == 4  # client_id, client_secret, username, password

    def test_adapters_no_auth_required(self, client):
        """Test that adapters list doesn't require authentication."""
        response = client.get("/v1/setup/adapters")
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


class TestValidateLLMEndpoint:
    """Test POST /v1/setup/validate-llm endpoint."""

    @pytest.mark.asyncio
    async def test_validate_openai_success(self, client):
        """Test successful OpenAI validation."""
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_models = AsyncMock()
            mock_models.data = ["gpt-4", "gpt-3.5-turbo"]
            mock_client.models.list = AsyncMock(return_value=mock_models)
            mock_openai.return_value = mock_client

            response = client.post(
                "/v1/setup/validate-llm",
                json={
                    "provider": "openai",
                    "api_key": "sk-test123",
                    "base_url": None,
                    "model": None,
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()["data"]
            assert data["valid"] is True
            assert "successful" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_openai_invalid_key(self, client):
        """Test OpenAI validation with invalid key."""
        response = client.post(
            "/v1/setup/validate-llm",
            json={
                "provider": "openai",
                "api_key": "",
                "base_url": None,
                "model": None,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["valid"] is False
        assert "api key" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_validate_local_llm_success(self, client):
        """Test successful local LLM validation."""
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_models = AsyncMock()
            mock_models.data = ["llama3"]
            mock_client.models.list = AsyncMock(return_value=mock_models)
            mock_openai.return_value = mock_client

            response = client.post(
                "/v1/setup/validate-llm",
                json={
                    "provider": "local",
                    "api_key": "local",
                    "base_url": "http://localhost:11434",
                    "model": "llama3",
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()["data"]
            assert data["valid"] is True

    @pytest.mark.asyncio
    async def test_validate_llm_connection_timeout(self, client):
        """Test LLM validation with connection timeout."""
        with patch("openai.AsyncOpenAI") as mock_openai:
            mock_client = AsyncMock()
            mock_client.models.list = AsyncMock(side_effect=Exception("timeout"))
            mock_openai.return_value = mock_client

            response = client.post(
                "/v1/setup/validate-llm",
                json={
                    "provider": "local",
                    "api_key": "local",
                    "base_url": "http://localhost:11434",
                    "model": "llama3",
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()["data"]
            assert data["valid"] is False

    def test_validate_llm_no_auth_required(self, client):
        """Test that LLM validation doesn't require authentication during first-run."""
        response = client.post(
            "/v1/setup/validate-llm",
            json={
                "provider": "openai",
                "api_key": "sk-test",
                "base_url": None,
                "model": None,
            },
        )
        # Should not return 401 during first-run
        assert response.status_code != status.HTTP_401_UNAUTHORIZED


class TestCompleteSetupEndpoint:
    """Test POST /v1/setup/complete endpoint."""

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    @patch("ciris_engine.logic.adapters.api.routes.setup.get_default_config_path")
    @patch("ciris_engine.logic.adapters.api.routes.setup._save_setup_config")
    def test_complete_setup_success(self, mock_save, mock_config_path, mock_first_run, client, tmp_path):
        """Test successful setup completion."""
        mock_first_run.return_value = True
        mock_config_path.return_value = tmp_path / ".env"

        response = client.post(
            "/v1/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-test123",
                "llm_base_url": None,
                "llm_model": None,
                "template_id": "general",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": "admin",
                "admin_password": "secure_password_123",
                "agent_port": 8080,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "completed"
        assert "successful" in data["message"].lower()
        mock_save.assert_called_once()

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    def test_complete_setup_password_too_short(self, mock_first_run, client):
        """Test setup completion with password too short."""
        mock_first_run.return_value = True

        response = client.post(
            "/v1/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-test123",
                "llm_base_url": None,
                "llm_model": None,
                "template_id": "general",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": "admin",
                "admin_password": "short",  # Only 5 characters
                "agent_port": 8080,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "8 characters" in response.json()["detail"]

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    def test_complete_setup_already_configured(self, mock_first_run, client):
        """Test setup completion when already configured."""
        mock_first_run.return_value = False  # Already configured

        response = client.post(
            "/v1/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-test123",
                "llm_base_url": None,
                "llm_model": None,
                "template_id": "general",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": "admin",
                "admin_password": "secure_password_123",
                "agent_port": 8080,
            },
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "already completed" in response.json()["detail"]

    def test_complete_setup_no_auth_required_during_first_run(self, client):
        """Test that setup completion doesn't require auth during first-run."""
        with patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run", return_value=False):
            response = client.post(
                "/v1/setup/complete",
                json={
                    "llm_provider": "openai",
                    "llm_api_key": "sk-test",
                    "admin_username": "admin",
                    "admin_password": "password123",
                },
            )
            # After first-run, should require auth (403, not 401 because setup is done)
            assert response.status_code == status.HTTP_403_FORBIDDEN


class TestGetConfigEndpoint:
    """Test GET /v1/setup/config endpoint."""

    @patch("ciris_engine.logic.adapters.api.routes.setup._is_setup_allowed_without_auth")
    def test_get_config_during_first_run(self, mock_allowed, client):
        """Test getting config during first-run (no auth required)."""
        mock_allowed.return_value = True  # First-run, no auth required

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_MODEL": "gpt-4",
                "CIRIS_API_PORT": "8080",
            },
        ):
            response = client.get("/v1/setup/config")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()["data"]
            assert data["llm_api_key_set"] is True
            assert data["llm_model"] == "gpt-4"
            assert data["agent_port"] == 8080

    @patch("ciris_engine.logic.adapters.api.routes.setup._is_setup_allowed_without_auth")
    def test_get_config_after_setup_requires_auth(self, mock_allowed, client):
        """Test that getting config after setup requires authentication."""
        mock_allowed.return_value = False  # Setup completed, auth required

        response = client.get("/v1/setup/config")

        # Should return 401 because no auth provided and setup is completed
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestUpdateConfigEndpoint:
    """Test PUT /v1/setup/config endpoint."""

    def test_update_config_requires_auth(self, client):
        """Test that config update always requires authentication."""
        response = client.put(
            "/v1/setup/config",
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-new-key",
                "llm_base_url": None,
                "llm_model": "gpt-4",
                "template_id": "general",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": "admin",
                "admin_password": "new_password_123",
                "agent_port": 8080,
            },
        )

        # Should require auth
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("ciris_engine.logic.adapters.api.routes.setup.get_default_config_path")
    @patch("ciris_engine.logic.adapters.api.routes.setup._save_setup_config")
    def test_update_config_with_admin_auth(self, mock_save, mock_config_path, client, auth_headers, tmp_path):
        """Test config update with admin authentication."""
        mock_config_path.return_value = tmp_path / ".env"

        response = client.put(
            "/v1/setup/config",
            headers=auth_headers,
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-new-key",
                "llm_base_url": None,
                "llm_model": "gpt-4",
                "template_id": "general",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": "admin",
                "admin_password": "new_password_123",
                "agent_port": 8080,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "updated"
        mock_save.assert_called_once()


class TestHelperFunctions:
    """Test setup route helper functions."""

    def test_get_llm_providers(self):
        """Test _get_llm_providers helper."""
        providers = _get_llm_providers()

        assert len(providers) == 3
        assert all(isinstance(p, LLMProvider) for p in providers)

        openai = next(p for p in providers if p.id == "openai")
        assert openai.requires_api_key is True

    def test_get_agent_templates(self):
        """Test _get_agent_templates helper loads from ciris_templates directory."""
        templates = _get_agent_templates()

        assert len(templates) >= 1  # At least one template should exist
        # All templates should have stewardship info
        assert all(t.stewardship_tier >= 1 and t.stewardship_tier <= 5 for t in templates)
        assert all(t.creator_id is not None for t in templates)
        assert all(t.signature is not None for t in templates)
        # All templates should have DSAR SOPs
        assert all("DSAR_ACCESS" in t.supported_sops for t in templates)
        assert all("DSAR_DELETE" in t.supported_sops for t in templates)

    def test_get_available_adapters(self):
        """Test _get_available_adapters helper."""
        adapters = _get_available_adapters()

        assert len(adapters) == 4
        assert all(a.id in ["api", "cli", "discord", "reddit"] for a in adapters)

        api = next(a for a in adapters if a.id == "api")
        assert api.enabled_by_default is True

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    def test_is_setup_allowed_without_auth_first_run(self, mock_first_run):
        """Test _is_setup_allowed_without_auth during first-run."""
        mock_first_run.return_value = True
        assert _is_setup_allowed_without_auth() is True

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    def test_is_setup_allowed_without_auth_after_setup(self, mock_first_run):
        """Test _is_setup_allowed_without_auth after setup completed."""
        mock_first_run.return_value = False
        assert _is_setup_allowed_without_auth() is False


class TestDualPasswordSupport:
    """Test dual password support (new user + system admin)."""

    @patch("ciris_engine.logic.adapters.api.routes.setup.is_first_run")
    @patch("ciris_engine.logic.adapters.api.routes.setup.get_default_config_path")
    @patch("ciris_engine.logic.adapters.api.routes.setup._save_setup_config")
    def test_setup_creates_new_user_and_updates_admin(
        self, mock_save, mock_config_path, mock_first_run, client, tmp_path
    ):
        """Test that setup creates new user and updates system admin password."""
        mock_first_run.return_value = True
        mock_config_path.return_value = tmp_path / ".env"

        response = client.post(
            "/v1/setup/complete",
            json={
                "llm_provider": "openai",
                "llm_api_key": "sk-test123",
                "llm_base_url": None,
                "llm_model": None,
                "template_id": "general",
                "enabled_adapters": ["api"],
                "adapter_config": {},
                "admin_username": "newuser",  # New user (not "admin")
                "admin_password": "user_password_123",  # New user's password
                "system_admin_password": "system_admin_password_123",  # System admin password
                "agent_port": 8080,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()["data"]
        assert data["status"] == "completed"

        # TODO: Verify user creation and admin password update when implemented
