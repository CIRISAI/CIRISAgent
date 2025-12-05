"""Tests for MCP server adapter configuration."""

import os
from unittest.mock import patch

import pytest

from ciris_engine.logic.adapters.mcp_server.config import (
    AuthMethod,
    MCPServerAdapterConfig,
    MCPServerExposureConfig,
    MCPServerSecurityConfig,
    MCPServerTransportConfig,
    TransportType,
)


class TestTransportType:
    """Tests for TransportType enum."""

    def test_transport_types(self) -> None:
        """Test all transport types are defined."""
        assert TransportType.STDIO == "stdio"
        assert TransportType.SSE == "sse"
        assert TransportType.STREAMABLE_HTTP == "streamable_http"
        assert TransportType.WEBSOCKET == "websocket"


class TestAuthMethod:
    """Tests for AuthMethod enum."""

    def test_auth_methods(self) -> None:
        """Test all auth methods are defined."""
        assert AuthMethod.NONE == "none"
        assert AuthMethod.API_KEY == "api_key"
        assert AuthMethod.OAUTH2 == "oauth2"
        assert AuthMethod.JWT == "jwt"


class TestMCPServerTransportConfig:
    """Tests for MCPServerTransportConfig model."""

    def test_default_values(self) -> None:
        """Test default transport values."""
        config = MCPServerTransportConfig()
        assert config.type == TransportType.STDIO
        assert config.host == "127.0.0.1"
        assert config.port == 3000
        assert config.path == "/mcp"
        assert config.tls_enabled is False

    def test_http_config(self) -> None:
        """Test HTTP transport configuration."""
        config = MCPServerTransportConfig(
            type=TransportType.SSE,
            host="0.0.0.0",
            port=8080,
            tls_enabled=True,
            tls_cert_file="/path/to/cert.pem",
            tls_key_file="/path/to/key.pem",
        )
        assert config.type == TransportType.SSE
        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.tls_enabled is True


class TestMCPServerSecurityConfig:
    """Tests for MCPServerSecurityConfig model."""

    def test_default_values(self) -> None:
        """Test default security values."""
        config = MCPServerSecurityConfig()
        assert config.require_auth is False
        assert config.rate_limit_enabled is True
        assert config.max_requests_per_minute == 100
        assert config.validate_requests is True
        assert config.audit_requests is True

    def test_with_api_keys(self) -> None:
        """Test config with API keys."""
        config = MCPServerSecurityConfig(
            require_auth=True,
            auth_methods=[AuthMethod.API_KEY],
            api_keys=["key1", "key2"],
        )
        assert config.require_auth is True
        assert AuthMethod.API_KEY in config.auth_methods
        assert len(config.api_keys) == 2

    def test_with_client_allowlist(self) -> None:
        """Test config with client allowlist."""
        config = MCPServerSecurityConfig(
            allowed_clients=["claude-desktop", "cursor"],
            blocked_clients=["malicious-client"],
        )
        assert "claude-desktop" in config.allowed_clients
        assert "malicious-client" in config.blocked_clients


class TestMCPServerExposureConfig:
    """Tests for MCPServerExposureConfig model."""

    def test_default_values(self) -> None:
        """Test default exposure values."""
        config = MCPServerExposureConfig()
        assert config.expose_tools is True
        assert config.expose_resources is True
        assert config.expose_prompts is True
        assert len(config.default_tools) > 0
        assert len(config.default_resources) > 0
        assert len(config.default_prompts) > 0

    def test_with_allowlist(self) -> None:
        """Test exposure with allowlists."""
        config = MCPServerExposureConfig(
            tool_allowlist=["safe_tool_1", "safe_tool_2"],
            resource_blocklist=["ciris://secret"],
        )
        assert len(config.tool_allowlist) == 2
        assert "ciris://secret" in config.resource_blocklist

    def test_disabled_exposure(self) -> None:
        """Test disabling exposure."""
        config = MCPServerExposureConfig(
            expose_tools=False,
            expose_resources=False,
            expose_prompts=False,
        )
        assert config.expose_tools is False
        assert config.expose_resources is False
        assert config.expose_prompts is False


class TestMCPServerAdapterConfig:
    """Tests for MCPServerAdapterConfig model."""

    def test_default_values(self) -> None:
        """Test default adapter values."""
        config = MCPServerAdapterConfig()
        assert config.server_id == "ciris-mcp-server"
        assert config.server_name == "CIRIS MCP Server"
        assert config.enabled is True
        assert config.auto_start is True

    def test_custom_config(self) -> None:
        """Test custom adapter configuration."""
        config = MCPServerAdapterConfig(
            server_id="custom-server",
            server_name="Custom MCP Server",
            server_version="2.0.0",
            transport=MCPServerTransportConfig(
                type=TransportType.SSE,
                port=9000,
            ),
            security=MCPServerSecurityConfig(
                require_auth=True,
            ),
        )
        assert config.server_id == "custom-server"
        assert config.transport.type == TransportType.SSE
        assert config.transport.port == 9000
        assert config.security.require_auth is True

    def test_get_exposed_tools(self) -> None:
        """Test getting exposed tools based on config."""
        config = MCPServerAdapterConfig(
            exposure=MCPServerExposureConfig(
                expose_tools=True,
                tool_allowlist=["allowed_tool"],
                tool_blocklist=["blocked_tool"],
            ),
        )

        available = ["allowed_tool", "blocked_tool", "other_tool"]
        exposed = config.get_exposed_tools(available)

        assert "allowed_tool" in exposed
        assert "blocked_tool" not in exposed
        assert "other_tool" not in exposed  # Not in allowlist

    def test_get_exposed_tools_no_allowlist(self) -> None:
        """Test getting exposed tools without allowlist."""
        config = MCPServerAdapterConfig(
            exposure=MCPServerExposureConfig(
                expose_tools=True,
                tool_allowlist=[],  # Empty = all allowed
                tool_blocklist=["blocked_tool"],
            ),
        )

        available = ["tool1", "tool2", "blocked_tool"]
        exposed = config.get_exposed_tools(available)

        assert "tool1" in exposed
        assert "tool2" in exposed
        assert "blocked_tool" not in exposed

    def test_get_exposed_tools_disabled(self) -> None:
        """Test getting exposed tools when disabled."""
        config = MCPServerAdapterConfig(
            exposure=MCPServerExposureConfig(expose_tools=False),
        )

        available = ["tool1", "tool2"]
        exposed = config.get_exposed_tools(available)

        assert len(exposed) == 0

    @patch.dict(os.environ, {
        "MCP_SERVER_ID": "env-server",
        "MCP_SERVER_NAME": "Environment Server",
        "MCP_SERVER_TRANSPORT": "sse",
        "MCP_SERVER_HOST": "0.0.0.0",
        "MCP_SERVER_PORT": "8080",
        "MCP_SERVER_REQUIRE_AUTH": "true",
        "MCP_SERVER_API_KEYS": "key1,key2,key3",
    })
    def test_load_env_vars(self) -> None:
        """Test loading configuration from environment variables."""
        config = MCPServerAdapterConfig()
        config.load_env_vars()

        assert config.server_id == "env-server"
        assert config.server_name == "Environment Server"
        assert config.transport.type == TransportType.SSE
        assert config.transport.host == "0.0.0.0"
        assert config.transport.port == 8080
        assert config.security.require_auth is True
        assert len(config.security.api_keys) == 3
