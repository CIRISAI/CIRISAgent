"""Tests for the module types listing API endpoint.

This tests the /system/adapters/types endpoint which returns both core
adapters and modular services with their typed configuration schemas.
"""

from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.system.adapters import (
    _get_core_adapter_info,
    _parse_manifest_to_module_info,
)
from ciris_engine.schemas.runtime.adapter_management import ModuleConfigParameter, ModuleTypeInfo, ModuleTypesResponse


class TestModuleConfigParameter:
    """Tests for ModuleConfigParameter schema."""

    def test_required_fields(self) -> None:
        """Test required fields are validated."""
        param = ModuleConfigParameter(
            name="test_param",
            param_type="string",
            description="Test parameter",
        )
        assert param.name == "test_param"
        assert param.param_type == "string"
        assert param.description == "Test parameter"
        assert param.required is True  # default

    def test_optional_fields(self) -> None:
        """Test optional fields can be set."""
        param = ModuleConfigParameter(
            name="api_key",
            param_type="string",
            description="API key for authentication",
            env_var="MY_API_KEY",
            required=True,
            sensitivity="HIGH",
            default=None,
        )
        assert param.env_var == "MY_API_KEY"
        assert param.sensitivity == "HIGH"
        assert param.default is None

    def test_with_default_value(self) -> None:
        """Test parameter with default value."""
        param = ModuleConfigParameter(
            name="port",
            param_type="integer",
            description="Port number",
            default=8000,
            required=False,
        )
        assert param.default == 8000
        assert param.required is False


class TestModuleTypeInfo:
    """Tests for ModuleTypeInfo schema."""

    def test_core_module(self) -> None:
        """Test creating a core module info."""
        info = ModuleTypeInfo(
            module_id="api",
            name="API Adapter",
            version="1.0.0",
            description="REST API adapter",
            author="CIRIS Team",
            module_source="core",
            service_types=["COMMUNICATION", "TOOL"],
            capabilities=["communication:send_message"],
        )
        assert info.module_id == "api"
        assert info.module_source == "core"
        assert not info.is_mock
        assert len(info.service_types) == 2

    def test_adapter(self) -> None:
        """Test creating a modular service info."""
        info = ModuleTypeInfo(
            module_id="reddit",
            name="Reddit Adapter",
            version="1.0.0",
            description="Reddit integration",
            author="CIRIS Team",
            module_source="modular",
            service_types=["COMMUNICATION", "TOOL"],
            capabilities=["tool:reddit"],
            requires_external_deps=True,
            external_dependencies={"httpx": ">=0.25.0"},
            safe_domain="community_outreach",
            prohibited=["medical"],
        )
        assert info.module_source == "modular"
        assert info.requires_external_deps
        assert "httpx" in info.external_dependencies
        assert info.safe_domain == "community_outreach"
        assert "medical" in info.prohibited

    def test_mock_module(self) -> None:
        """Test mock module info."""
        info = ModuleTypeInfo(
            module_id="mock_llm",
            name="Mock LLM Service",
            version="1.0.0",
            description="Mock LLM for testing",
            author="CIRIS Team",
            module_source="modular",
            is_mock=True,
        )
        assert info.is_mock is True


class TestModuleTypesResponse:
    """Tests for ModuleTypesResponse schema."""

    def test_response_structure(self) -> None:
        """Test response structure is correct."""
        core = ModuleTypeInfo(
            module_id="api",
            name="API",
            version="1.0.0",
            description="API adapter",
            author="CIRIS Team",
            module_source="core",
        )
        modular = ModuleTypeInfo(
            module_id="reddit",
            name="Reddit",
            version="1.0.0",
            description="Reddit adapter",
            author="CIRIS Team",
            module_source="modular",
        )
        response = ModuleTypesResponse(
            core_modules=[core],
            adapters=[modular],
            total_core=1,
            total_adapters=1,
        )
        assert len(response.core_modules) == 1
        assert len(response.adapters) == 1
        assert response.total_core == 1
        assert response.total_adapters == 1


class TestGetCoreAdapterInfo:
    """Tests for _get_core_adapter_info helper function."""

    def test_api_adapter(self) -> None:
        """Test API adapter info is correct."""
        info = _get_core_adapter_info("api")
        assert info.module_id == "api"
        assert info.name == "API Adapter"
        assert info.module_source == "core"
        assert "COMMUNICATION" in info.service_types
        assert "TOOL" in info.service_types
        assert len(info.configuration_schema) > 0

        # Check specific config params
        param_names = [p.name for p in info.configuration_schema]
        assert "host" in param_names
        assert "port" in param_names

    def test_cli_adapter(self) -> None:
        """Test CLI adapter info is correct."""
        info = _get_core_adapter_info("cli")
        assert info.module_id == "cli"
        assert info.name == "CLI Adapter"
        assert "COMMUNICATION" in info.service_types
        assert not info.requires_external_deps

    def test_discord_adapter(self) -> None:
        """Test Discord adapter info is correct."""
        info = _get_core_adapter_info("discord")
        assert info.module_id == "discord"
        assert info.name == "Discord Adapter"
        assert "COMMUNICATION" in info.service_types
        assert info.requires_external_deps
        assert "discord.py" in info.external_dependencies

        # Check sensitive config param
        token_param = next(
            (p for p in info.configuration_schema if p.name == "discord_token"),
            None,
        )
        assert token_param is not None
        assert token_param.sensitivity == "HIGH"
        assert token_param.required is True

    def test_unknown_adapter(self) -> None:
        """Test handling of unknown adapter type."""
        info = _get_core_adapter_info("unknown")
        assert info.module_id == "unknown"
        assert info.module_source == "core"


class TestParseManifestToModuleInfo:
    """Tests for _parse_manifest_to_module_info helper function."""

    def test_basic_manifest(self) -> None:
        """Test parsing a basic manifest."""
        manifest = {
            "module": {
                "name": "test_module",
                "version": "1.0.0",
                "description": "Test module",
                "author": "Test Author",
            },
            "services": [{"type": "TOOL", "class": "test.TestService"}],
            "capabilities": ["test:capability"],
        }
        info = _parse_manifest_to_module_info(manifest, "test_module")
        assert info.module_id == "test_module"
        assert info.name == "test_module"
        assert info.version == "1.0.0"
        assert info.module_source == "modular"
        assert "TOOL" in info.service_types
        assert "test:capability" in info.capabilities

    def test_manifest_with_config(self) -> None:
        """Test parsing manifest with configuration."""
        manifest = {
            "module": {
                "name": "config_module",
                "version": "2.0.0",
                "description": "Module with config",
                "author": "CIRIS Team",
            },
            "services": [],
            "configuration": {
                "api_key": {
                    "type": "string",
                    "description": "API key",
                    "env": "MY_API_KEY",
                    "sensitivity": "HIGH",
                },
                "timeout": {
                    "type": "integer",
                    "default": 30,
                    "description": "Request timeout",
                    "required": False,
                },
            },
        }
        info = _parse_manifest_to_module_info(manifest, "config_module")
        assert len(info.configuration_schema) == 2

        api_key_param = next((p for p in info.configuration_schema if p.name == "api_key"), None)
        assert api_key_param is not None
        assert api_key_param.sensitivity == "HIGH"
        assert api_key_param.env_var == "MY_API_KEY"

        timeout_param = next((p for p in info.configuration_schema if p.name == "timeout"), None)
        assert timeout_param is not None
        assert timeout_param.default == 30
        assert timeout_param.required is False

    def test_manifest_with_external_deps(self) -> None:
        """Test parsing manifest with external dependencies."""
        manifest = {
            "module": {
                "name": "deps_module",
                "version": "1.0.0",
                "description": "Module with deps",
                "author": "CIRIS Team",
            },
            "services": [],
            "dependencies": {"external": {"httpx": ">=0.25.0", "pydantic": ">=2.0.0"}},
        }
        info = _parse_manifest_to_module_info(manifest, "deps_module")
        assert info.requires_external_deps
        assert "httpx" in info.external_dependencies
        assert info.external_dependencies["httpx"] == ">=0.25.0"

    def test_manifest_with_metadata(self) -> None:
        """Test parsing manifest with metadata."""
        manifest = {
            "module": {
                "name": "meta_module",
                "version": "1.0.0",
                "description": "Module with metadata",
                "author": "CIRIS Team",
            },
            "services": [],
            "metadata": {
                "safe_domain": "external_tools",
                "prohibited": ["medical", "financial"],
                "api": "External API",
            },
        }
        info = _parse_manifest_to_module_info(manifest, "meta_module")
        assert info.safe_domain == "external_tools"
        assert "medical" in info.prohibited
        assert "financial" in info.prohibited
        assert info.metadata is not None
        assert info.metadata.get("api") == "External API"

    def test_mock_module_manifest(self) -> None:
        """Test parsing MOCK module manifest."""
        manifest = {
            "module": {
                "name": "mock_service",
                "version": "1.0.0",
                "description": "Mock service",
                "author": "CIRIS Team",
                "MOCK": True,
            },
            "services": [],
        }
        info = _parse_manifest_to_module_info(manifest, "mock_service")
        assert info.is_mock is True

    def test_multiple_services(self) -> None:
        """Test parsing manifest with multiple services."""
        manifest = {
            "module": {
                "name": "multi_module",
                "version": "1.0.0",
                "description": "Multi-service module",
                "author": "CIRIS Team",
            },
            "services": [
                {"type": "TOOL", "class": "multi.ToolService"},
                {"type": "COMMUNICATION", "class": "multi.CommService"},
                {"type": "WISE_AUTHORITY", "class": "multi.WiseService"},
            ],
        }
        info = _parse_manifest_to_module_info(manifest, "multi_module")
        assert len(info.service_types) == 3
        assert "TOOL" in info.service_types
        assert "COMMUNICATION" in info.service_types
        assert "WISE_AUTHORITY" in info.service_types


class TestModuleTypesIntegration:
    """Integration tests for module types functionality."""

    def test_core_adapters_complete(self) -> None:
        """Test all core adapters return valid info."""
        core_types = ["api", "cli", "discord"]
        for adapter_type in core_types:
            info = _get_core_adapter_info(adapter_type)
            assert info.module_id == adapter_type
            assert info.module_source == "core"
            assert info.version
            assert info.description

    def test_modular_manifest_real(self) -> None:
        """Test parsing a real manifest file if available."""
        import json
        from pathlib import Path

        manifest_path = Path("ciris_adapters/mcp_client/manifest.json")
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest_data = json.load(f)

            info = _parse_manifest_to_module_info(manifest_data, "mcp_client")
            assert info.module_id == "mcp_client"
            assert info.module_source == "modular"
            assert "TOOL" in info.service_types or len(info.service_types) > 0
            assert len(info.capabilities) > 0
