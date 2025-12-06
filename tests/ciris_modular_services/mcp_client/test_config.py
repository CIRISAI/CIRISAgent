"""Tests for MCP client adapter configuration."""

import os
from unittest.mock import patch

import pytest

from ciris_modular_services.mcp_client.config import (
    MCPAdapterConfig,
    MCPBusBinding,
    MCPBusType,
    MCPPermissionLevel,
    MCPSecurityConfig,
    MCPServerConfig,
    MCPTransportType,
)


class TestMCPBusType:
    """Tests for MCPBusType enum."""

    def test_bus_types(self) -> None:
        """Test all bus types are defined."""
        assert MCPBusType.TOOL == "tool"
        assert MCPBusType.COMMUNICATION == "communication"
        assert MCPBusType.WISE == "wise"


class TestMCPTransportType:
    """Tests for MCPTransportType enum."""

    def test_transport_types(self) -> None:
        """Test all transport types are defined."""
        assert MCPTransportType.STDIO == "stdio"
        assert MCPTransportType.SSE == "sse"
        assert MCPTransportType.STREAMABLE_HTTP == "streamable_http"
        assert MCPTransportType.WEBSOCKET == "websocket"


class TestMCPBusBinding:
    """Tests for MCPBusBinding model."""

    def test_default_values(self) -> None:
        """Test default values."""
        binding = MCPBusBinding(bus_type=MCPBusType.TOOL)
        assert binding.enabled is True
        assert binding.priority == 50
        assert binding.capability_filter == []

    def test_custom_values(self) -> None:
        """Test custom values."""
        binding = MCPBusBinding(
            bus_type=MCPBusType.WISE,
            enabled=False,
            priority=75,
            capability_filter=["guidance"],
        )
        assert binding.bus_type == MCPBusType.WISE
        assert binding.enabled is False
        assert binding.priority == 75
        assert binding.capability_filter == ["guidance"]


class TestMCPSecurityConfig:
    """Tests for MCPSecurityConfig model."""

    def test_default_values(self) -> None:
        """Test default security values."""
        config = MCPSecurityConfig()
        assert config.permission_level == MCPPermissionLevel.SANDBOXED
        assert config.validate_inputs is True
        assert config.validate_outputs is True
        assert config.detect_tool_poisoning is True
        assert config.max_calls_per_minute == 60
        assert config.sandbox_enabled is True

    def test_blocked_tools(self) -> None:
        """Test blocked tools configuration."""
        config = MCPSecurityConfig(
            blocked_tools=["dangerous_tool", "risky_tool"],
            allowed_tools=["safe_tool"],
        )
        assert "dangerous_tool" in config.blocked_tools
        assert "safe_tool" in config.allowed_tools


class TestMCPServerConfig:
    """Tests for MCPServerConfig model."""

    def test_minimal_config(self) -> None:
        """Test minimal server configuration."""
        config = MCPServerConfig(
            server_id="test",
            name="Test Server",
        )
        assert config.server_id == "test"
        assert config.name == "Test Server"
        assert config.transport == MCPTransportType.STDIO
        assert config.enabled is True

    def test_stdio_config(self) -> None:
        """Test stdio server configuration."""
        config = MCPServerConfig(
            server_id="weather",
            name="Weather Server",
            command="npx",
            args=["-y", "@weather/server"],
            bus_bindings=[
                MCPBusBinding(bus_type=MCPBusType.TOOL),
            ],
        )
        assert config.command == "npx"
        assert config.args == ["-y", "@weather/server"]
        assert len(config.bus_bindings) == 1
        assert config.bus_bindings[0].bus_type == MCPBusType.TOOL

    def test_http_config(self) -> None:
        """Test HTTP server configuration."""
        config = MCPServerConfig(
            server_id="api",
            name="API Server",
            transport=MCPTransportType.SSE,
            url="http://localhost:3000/mcp",
        )
        assert config.transport == MCPTransportType.SSE
        assert config.url == "http://localhost:3000/mcp"

    def test_command_validation_rejects_injection(self) -> None:
        """Test command validation rejects injection attempts."""
        with pytest.raises(ValueError, match="dangerous character"):
            MCPServerConfig(
                server_id="test",
                name="Test",
                command="npx; rm -rf /",
            )

        with pytest.raises(ValueError, match="dangerous character"):
            MCPServerConfig(
                server_id="test",
                name="Test",
                command="npx && malicious",
            )


class TestMCPAdapterConfig:
    """Tests for MCPAdapterConfig model."""

    def test_default_config(self) -> None:
        """Test default adapter configuration."""
        config = MCPAdapterConfig()
        assert config.servers == []
        assert config.adapter_id == "mcp_default"
        assert config.auto_discover_servers is False

    def test_with_servers(self) -> None:
        """Test config with multiple servers."""
        config = MCPAdapterConfig(
            servers=[
                MCPServerConfig(server_id="s1", name="Server 1"),
                MCPServerConfig(server_id="s2", name="Server 2"),
            ],
        )
        assert len(config.servers) == 2

    def test_get_servers_for_bus(self) -> None:
        """Test filtering servers by bus type."""
        config = MCPAdapterConfig(
            servers=[
                MCPServerConfig(
                    server_id="tool_server",
                    name="Tool Server",
                    bus_bindings=[MCPBusBinding(bus_type=MCPBusType.TOOL)],
                ),
                MCPServerConfig(
                    server_id="wise_server",
                    name="Wise Server",
                    bus_bindings=[MCPBusBinding(bus_type=MCPBusType.WISE)],
                ),
                MCPServerConfig(
                    server_id="multi_server",
                    name="Multi Server",
                    bus_bindings=[
                        MCPBusBinding(bus_type=MCPBusType.TOOL),
                        MCPBusBinding(bus_type=MCPBusType.WISE),
                    ],
                ),
            ],
        )

        tool_servers = config.get_servers_for_bus(MCPBusType.TOOL)
        assert len(tool_servers) == 2
        assert any(s.server_id == "tool_server" for s in tool_servers)
        assert any(s.server_id == "multi_server" for s in tool_servers)

        wise_servers = config.get_servers_for_bus(MCPBusType.WISE)
        assert len(wise_servers) == 2

    @patch.dict(os.environ, {
        "MCP_ADAPTER_ID": "test_adapter",
        "MCP_LOG_LEVEL": "DEBUG",
        "MCP_SERVER_WEATHER_COMMAND": "npx",
        "MCP_SERVER_WEATHER_ARGS": "-y,@weather/server",
        "MCP_SERVER_WEATHER_TRANSPORT": "stdio",
        "MCP_SERVER_WEATHER_BUSES": "tool,wise",
    })
    def test_load_env_vars(self) -> None:
        """Test loading configuration from environment variables."""
        config = MCPAdapterConfig()
        config.load_env_vars()

        assert config.adapter_id == "test_adapter"
        assert config.log_level == "DEBUG"
        assert len(config.servers) == 1
        assert config.servers[0].server_id == "weather"
        assert config.servers[0].command == "npx"
        assert len(config.servers[0].bus_bindings) == 2
