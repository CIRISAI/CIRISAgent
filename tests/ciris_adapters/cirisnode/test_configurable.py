"""
Unit tests for CIRISNode configurable adapter.

Tests the device authorization (RFC 8628) workflow for connecting
existing agents to CIRISNode.
"""

import base64
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_adapters.cirisnode.configurable import CIRISNODE_REGIONS, CIRISNodeConfigurableAdapter


class TestCIRISNodeConfigurableAdapter:
    """Tests for CIRISNodeConfigurableAdapter."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.adapter = CIRISNodeConfigurableAdapter()

    def test_initialization_defaults(self) -> None:
        """Test adapter initializes with correct defaults."""
        adapter = CIRISNodeConfigurableAdapter()

        assert adapter.config == {}
        assert adapter._applied_config is None
        assert adapter._agent_id is None
        assert adapter._signing_key_b64 is None
        assert adapter._device_code is None
        assert adapter._user_code is None
        assert adapter._portal_url is None

    def test_initialization_with_config(self) -> None:
        """Test adapter initializes with provided config."""
        config = {"base_url": "https://node.example.com"}
        adapter = CIRISNodeConfigurableAdapter(
            config=config,
            agent_id="test_agent_123",
            signing_key_b64="dGVzdF9rZXk=",
        )

        assert adapter.config == config
        assert adapter._agent_id == "test_agent_123"
        assert adapter._signing_key_b64 == "dGVzdF9rZXk="

    def test_set_agent_identity(self) -> None:
        """Test set_agent_identity updates agent identity."""
        self.adapter.set_agent_identity(
            agent_id="new_agent_456",
            signing_key_b64="bmV3X2tleQ==",
        )

        assert self.adapter._agent_id == "new_agent_456"
        assert self.adapter._signing_key_b64 == "bmV3X2tleQ=="

    def test_get_agent_info_empty(self) -> None:
        """Test _get_agent_info returns empty dict when no identity set."""
        agent_info = self.adapter._get_agent_info()

        assert agent_info == {}

    def test_get_agent_info_with_agent_id(self) -> None:
        """Test _get_agent_info includes agent_id_hash."""
        self.adapter._agent_id = "test_agent_123"

        agent_info = self.adapter._get_agent_info()

        assert "agent_id_hash" in agent_info
        # Hash should be 16 chars (first 16 of SHA-256 hex)
        assert len(agent_info["agent_id_hash"]) == 16

    def test_get_agent_info_with_signing_key(self) -> None:
        """Test _get_agent_info includes has_signing_key flag."""
        self.adapter._agent_id = "test_agent_123"
        self.adapter._signing_key_b64 = "dGVzdF9rZXk="

        agent_info = self.adapter._get_agent_info()

        assert "agent_id_hash" in agent_info
        assert agent_info.get("has_signing_key") is True

    def test_get_agent_info_hash_is_deterministic(self) -> None:
        """Test agent_id_hash is deterministic for same agent_id."""
        self.adapter._agent_id = "test_agent_123"
        hash1 = self.adapter._get_agent_info()["agent_id_hash"]

        adapter2 = CIRISNodeConfigurableAdapter(agent_id="test_agent_123")
        hash2 = adapter2._get_agent_info()["agent_id_hash"]

        assert hash1 == hash2

    def test_get_agent_info_hash_differs_for_different_agents(self) -> None:
        """Test agent_id_hash differs for different agent_ids."""
        adapter1 = CIRISNodeConfigurableAdapter(agent_id="agent_1")
        adapter2 = CIRISNodeConfigurableAdapter(agent_id="agent_2")

        hash1 = adapter1._get_agent_info()["agent_id_hash"]
        hash2 = adapter2._get_agent_info()["agent_id_hash"]

        assert hash1 != hash2


class TestCIRISNodeDiscovery:
    """Tests for CIRISNode discovery."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.adapter = CIRISNodeConfigurableAdapter()

    @pytest.mark.asyncio
    async def test_discover_regions(self) -> None:
        """Test discover returns available regions."""
        results = await self.adapter.discover("regions")

        assert len(results) == 2
        assert results[0]["id"] == "us-primary"
        assert results[1]["id"] == "eu"

    @pytest.mark.asyncio
    async def test_discover_default(self) -> None:
        """Test discover with default type returns regions."""
        results = await self.adapter.discover("default")

        assert len(results) == 2
        assert results == CIRISNODE_REGIONS

    @pytest.mark.asyncio
    async def test_discover_manual(self) -> None:
        """Test discover manual returns empty list."""
        results = await self.adapter.discover("manual")

        assert results == []

    @pytest.mark.asyncio
    async def test_discover_region_metadata(self) -> None:
        """Test discovered regions have correct metadata."""
        results = await self.adapter.discover("regions")

        us_region = results[0]
        assert us_region["label"] == "CIRIS US (Primary)"
        assert "portal_url" in us_region["metadata"]
        assert "node_url" in us_region["metadata"]
        assert us_region["metadata"]["portal_url"] == "https://portal.ciris.ai"


class TestCIRISNodeConfigOptions:
    """Tests for get_config_options."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.adapter = CIRISNodeConfigurableAdapter()

    @pytest.mark.asyncio
    async def test_get_config_options_select_region(self) -> None:
        """Test get_config_options returns regions for select_region step."""
        options = await self.adapter.get_config_options("select_region", {})

        assert options == CIRISNODE_REGIONS

    @pytest.mark.asyncio
    async def test_get_config_options_unknown_step(self) -> None:
        """Test get_config_options returns empty list for unknown step."""
        options = await self.adapter.get_config_options("unknown_step", {})

        assert options == []


class TestCIRISNodeValidation:
    """Tests for CIRISNode configuration validation."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.adapter = CIRISNodeConfigurableAdapter()

    @pytest.mark.asyncio
    async def test_validate_config_empty(self) -> None:
        """Test validation fails for empty config."""
        valid, error = await self.adapter.validate_config({})

        assert valid is False
        assert "empty" in error.lower()

    @pytest.mark.asyncio
    async def test_validate_config_no_device_auth_result(self) -> None:
        """Test validation fails without device_auth_result."""
        valid, error = await self.adapter.validate_config({"some_field": "value"})

        assert valid is False
        assert "device authorization" in error.lower()

    @pytest.mark.asyncio
    async def test_validate_config_no_signing_key(self) -> None:
        """Test validation fails without signing key."""
        config = {
            "device_auth_result": {
                "node_url": "https://node.example.com",
            }
        }

        valid, error = await self.adapter.validate_config(config)

        assert valid is False
        assert "signing key" in error.lower()

    @pytest.mark.asyncio
    async def test_validate_config_no_node_url(self) -> None:
        """Test validation fails without node_url."""
        config = {
            "device_auth_result": {
                "signing_key_b64": "dGVzdF9rZXk=",
            }
        }

        valid, error = await self.adapter.validate_config(config)

        assert valid is False
        assert "node" in error.lower()


class TestCIRISNodeApplyConfig:
    """Tests for applying CIRISNode configuration."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.adapter = CIRISNodeConfigurableAdapter()

    def test_get_applied_config_none(self) -> None:
        """Test get_applied_config returns None when not configured."""
        assert self.adapter.get_applied_config() is None

    @pytest.mark.asyncio
    async def test_apply_config_without_signing_key(self) -> None:
        """Test apply_config succeeds even without signing key (stores config only)."""
        config = {
            "device_auth_result": {
                "node_url": "https://node.example.com",
                "org_id": "org_123",
                # No signing_key_b64
            }
        }

        result = await self.adapter.apply_config(config)

        # Should return True since it stores the config even without key
        assert result is True
        assert self.adapter._applied_config == config

    @pytest.mark.asyncio
    async def test_apply_config_stores_applied_config(self) -> None:
        """Test apply_config stores the configuration."""
        config = {
            "device_auth_result": {
                "node_url": "https://node.example.com",
                "org_id": "org_123",
            }
        }

        await self.adapter.apply_config(config)

        applied = self.adapter.get_applied_config()
        assert applied == config


class TestCIRISNodeRegions:
    """Tests for CIRISNODE_REGIONS constant."""

    def test_regions_structure(self) -> None:
        """Test CIRISNODE_REGIONS has correct structure."""
        assert len(CIRISNODE_REGIONS) == 2

        for region in CIRISNODE_REGIONS:
            assert "id" in region
            assert "label" in region
            assert "description" in region
            assert "metadata" in region
            assert "portal_url" in region["metadata"]
            assert "node_url" in region["metadata"]
            assert "region" in region["metadata"]

    def test_us_region(self) -> None:
        """Test US region has correct values."""
        us_region = CIRISNODE_REGIONS[0]

        assert us_region["id"] == "us-primary"
        assert "US" in us_region["label"]
        assert us_region["metadata"]["portal_url"] == "https://portal.ciris.ai"
        assert us_region["metadata"]["node_url"] == "https://node.ciris-services-1.ai"

    def test_eu_region(self) -> None:
        """Test EU region has correct values."""
        eu_region = CIRISNODE_REGIONS[1]

        assert eu_region["id"] == "eu"
        assert "EU" in eu_region["label"]
        assert eu_region["metadata"]["portal_url"] == "https://portal.ciris.ai"
        assert eu_region["metadata"]["node_url"] == "https://node.ciris-services-2.ai"


class TestDeviceAuthConfigSchema:
    """Tests for AdapterDeviceAuthConfig schema used by CIRISNode."""

    def test_device_auth_config_creation(self) -> None:
        """Test AdapterDeviceAuthConfig schema creation."""
        from ciris_engine.schemas.runtime.manifest import AdapterDeviceAuthConfig

        config = AdapterDeviceAuthConfig(
            provider_name="CIRISPortal",
            device_authorize_path="/api/device/authorize",
            device_token_path="/api/device/token",
            poll_interval=5,
            expires_in=900,
        )

        assert config.provider_name == "CIRISPortal"
        assert config.device_authorize_path == "/api/device/authorize"
        assert config.device_token_path == "/api/device/token"
        assert config.poll_interval == 5
        assert config.expires_in == 900

    def test_device_auth_config_defaults(self) -> None:
        """Test AdapterDeviceAuthConfig default values."""
        from ciris_engine.schemas.runtime.manifest import AdapterDeviceAuthConfig

        config = AdapterDeviceAuthConfig(provider_name="TestProvider")

        assert config.device_authorize_path == "/api/device/authorize"
        assert config.device_token_path == "/api/device/token"
        assert config.poll_interval == 5
        assert config.expires_in == 900

    def test_configuration_step_device_auth_type(self) -> None:
        """Test ConfigurationStep accepts device_auth step type."""
        from ciris_engine.schemas.runtime.manifest import ConfigurationStep

        step = ConfigurationStep(
            step_id="device_auth_step",
            step_type="device_auth",
            title="Authorize Device",
            description="Complete device authorization with CIRISPortal",
        )

        assert step.step_type == "device_auth"

    def test_configuration_step_device_auth_config_field(self) -> None:
        """Test ConfigurationStep has device_auth_config field."""
        from ciris_engine.schemas.runtime.manifest import AdapterDeviceAuthConfig, ConfigurationStep

        step = ConfigurationStep(
            step_id="device_auth_step",
            step_type="device_auth",
            title="Authorize Device",
            description="Complete device authorization",
            device_auth_config=AdapterDeviceAuthConfig(
                provider_name="CIRISPortal",
                poll_interval=10,
            ),
        )

        assert step.device_auth_config is not None
        assert step.device_auth_config.provider_name == "CIRISPortal"
        assert step.device_auth_config.poll_interval == 10
