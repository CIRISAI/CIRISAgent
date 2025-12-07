"""
Unit tests for HAConfigurableAdapter.

Tests the Home Assistant configurable adapter's configuration handling,
OAuth token extraction, and camera selection functionality.
"""

import os
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestHAConfigurableAdapterTokenExtraction:
    """Tests for OAuth token extraction from various config formats."""

    @pytest.fixture
    def configurable_adapter(self):
        """Create a HAConfigurableAdapter instance for testing."""
        from ciris_adapters.home_assistant.configurable import HAConfigurableAdapter

        return HAConfigurableAdapter()

    @pytest.fixture
    def mock_aiohttp_success(self):
        """Mock aiohttp to return successful response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        return mock_session

    @pytest.mark.asyncio
    async def test_validate_config_with_top_level_access_token(
        self, configurable_adapter, mock_aiohttp_success
    ) -> None:
        """Test validation passes when access_token is at top level."""
        config = {
            "base_url": "http://192.168.1.100:8123",
            "access_token": "test_access_token_123",
        }

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_success):
            valid, error = await configurable_adapter.validate_config(config)

        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_config_with_nested_oauth_tokens(self, configurable_adapter, mock_aiohttp_success) -> None:
        """Test validation passes when access_token is nested in oauth_tokens.

        This is the format used when tokens come from the OAuth flow.
        """
        config = {
            "base_url": "http://192.168.1.100:8123",
            "oauth_tokens": {
                "access_token": "test_access_token_456",
                "refresh_token": "test_refresh_token_789",
                "token_type": "Bearer",
                "expires_in": 1800,
            },
        }

        with patch("aiohttp.ClientSession", return_value=mock_aiohttp_success):
            valid, error = await configurable_adapter.validate_config(config)

        assert valid is True
        assert error is None

    @pytest.mark.asyncio
    async def test_validate_config_fails_without_access_token(self, configurable_adapter) -> None:
        """Test validation fails when no access_token is provided."""
        config = {
            "base_url": "http://192.168.1.100:8123",
        }

        valid, error = await configurable_adapter.validate_config(config)

        assert valid is False
        assert error is not None
        assert "access_token" in error.lower()

    @pytest.mark.asyncio
    async def test_validate_config_fails_without_base_url(self, configurable_adapter) -> None:
        """Test validation fails when no base_url is provided."""
        config = {
            "access_token": "test_token",
        }

        valid, error = await configurable_adapter.validate_config(config)

        assert valid is False
        assert error is not None
        assert "base_url" in error.lower()

    @pytest.mark.asyncio
    async def test_apply_config_extracts_nested_tokens(self, configurable_adapter) -> None:
        """Test apply_config correctly extracts tokens from nested oauth_tokens.

        The adapter stores config in _applied_config and sets environment variables.
        """
        config = {
            "base_url": "http://192.168.1.100:8123",
            "oauth_tokens": {
                "access_token": "extracted_access_token",
                "refresh_token": "extracted_refresh_token",
            },
        }

        result = await configurable_adapter.apply_config(config)

        assert result is True
        # Verify environment variables are set
        assert os.environ.get("HOME_ASSISTANT_URL") == "http://192.168.1.100:8123"
        assert os.environ.get("HOME_ASSISTANT_TOKEN") == "extracted_access_token"
        assert os.environ.get("HOME_ASSISTANT_REFRESH_TOKEN") == "extracted_refresh_token"
        # Verify applied config is stored
        applied = configurable_adapter.get_applied_config()
        assert applied is not None
        assert applied["base_url"] == "http://192.168.1.100:8123"

    @pytest.mark.asyncio
    async def test_apply_config_with_top_level_tokens(self, configurable_adapter) -> None:
        """Test apply_config works with top-level tokens."""
        config = {
            "base_url": "http://192.168.1.100:8123",
            "access_token": "top_level_token",
            "refresh_token": "top_level_refresh",
        }

        result = await configurable_adapter.apply_config(config)

        assert result is True
        # Verify environment variables are set
        assert os.environ.get("HOME_ASSISTANT_TOKEN") == "top_level_token"
        assert os.environ.get("HOME_ASSISTANT_REFRESH_TOKEN") == "top_level_refresh"


class TestHAConfigurableAdapterCameraSelection:
    """Tests for camera selection functionality."""

    @pytest.fixture
    def configurable_adapter(self):
        """Create a HAConfigurableAdapter instance for testing."""
        from ciris_adapters.home_assistant.configurable import HAConfigurableAdapter

        return HAConfigurableAdapter()

    @pytest.mark.asyncio
    async def test_get_config_options_cameras_with_nested_token(self, configurable_adapter) -> None:
        """Test get_config_options for cameras extracts token from oauth_tokens."""
        context = {
            "base_url": "http://192.168.1.100:8123",
            "oauth_tokens": {
                "access_token": "test_token_for_cameras",
            },
        }

        # Mock the _get_ha_cameras method to avoid actual API calls
        with patch.object(
            configurable_adapter,
            "_get_ha_cameras",
            new_callable=AsyncMock,
            return_value=[
                {"id": "camera.front_door", "label": "Front Door Camera"},
                {"id": "camera.garage", "label": "Garage Camera"},
            ],
        ) as mock_get_cameras:
            options = await configurable_adapter.get_config_options("select_cameras", context)

            # Verify _get_ha_cameras was called with correct params
            mock_get_cameras.assert_called_once_with("http://192.168.1.100:8123", "test_token_for_cameras")
            assert len(options) == 2

    @pytest.mark.asyncio
    async def test_get_config_options_cameras_with_top_level_token(self, configurable_adapter) -> None:
        """Test get_config_options for cameras uses top-level access_token."""
        context = {
            "base_url": "http://192.168.1.100:8123",
            "access_token": "top_level_camera_token",
        }

        with patch.object(
            configurable_adapter,
            "_get_ha_cameras",
            new_callable=AsyncMock,
            return_value=[],
        ) as mock_get_cameras:
            await configurable_adapter.get_config_options("select_cameras", context)

            mock_get_cameras.assert_called_once_with("http://192.168.1.100:8123", "top_level_camera_token")

    @pytest.mark.asyncio
    async def test_get_config_options_cameras_without_token_returns_empty(self, configurable_adapter) -> None:
        """Test get_config_options returns empty list when no token available."""
        context = {
            "base_url": "http://192.168.1.100:8123",
            # No access_token or oauth_tokens
        }

        options = await configurable_adapter.get_config_options("select_cameras", context)

        assert options == []

    @pytest.mark.asyncio
    async def test_get_config_options_cameras_without_base_url_returns_empty(self, configurable_adapter) -> None:
        """Test get_config_options returns empty list when no base_url available."""
        context = {
            "oauth_tokens": {
                "access_token": "test_token",
            },
            # No base_url
        }

        options = await configurable_adapter.get_config_options("select_cameras", context)

        assert options == []


class TestHAConfigurableAdapterFeatureSelection:
    """Tests for feature selection functionality."""

    @pytest.fixture
    def configurable_adapter(self):
        """Create a HAConfigurableAdapter instance for testing."""
        from ciris_adapters.home_assistant.configurable import HAConfigurableAdapter

        return HAConfigurableAdapter()

    @pytest.mark.asyncio
    async def test_get_config_options_features(self, configurable_adapter) -> None:
        """Test get_config_options returns available features."""
        context = {}

        options = await configurable_adapter.get_config_options("select_features", context)

        # Should return the AVAILABLE_FEATURES
        assert len(options) > 0
        # Each option should have id, label, description
        for opt in options:
            assert "id" in opt
            assert "label" in opt
            assert "description" in opt

    @pytest.mark.asyncio
    async def test_get_config_options_unknown_step_returns_empty(self, configurable_adapter) -> None:
        """Test get_config_options returns empty list for unknown step_id."""
        context = {}

        options = await configurable_adapter.get_config_options("unknown_step", context)

        assert options == []
