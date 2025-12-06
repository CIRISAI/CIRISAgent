"""
MCP Adapter Configuration.

Configuration for MCP servers with security controls and bus bindings.
All configuration can be stored in the graph for agent self-configuration.
"""

import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


class MCPTransportType(str, Enum):
    """MCP transport types."""

    STDIO = "stdio"  # Standard input/output
    SSE = "sse"  # Server-sent events (HTTP)
    STREAMABLE_HTTP = "streamable_http"  # Streamable HTTP transport
    WEBSOCKET = "websocket"  # WebSocket transport


class MCPBusType(str, Enum):
    """Bus types that MCP servers can bind to."""

    TOOL = "tool"  # ToolBus - for executing tools
    COMMUNICATION = "communication"  # CommunicationBus - for messaging
    WISE = "wise"  # WiseBus - for guidance and wisdom


class MCPPermissionLevel(str, Enum):
    """Permission levels for MCP server capabilities."""

    READ_ONLY = "read_only"  # Can only read resources
    EXECUTE = "execute"  # Can execute tools
    FULL = "full"  # Full access to all capabilities
    SANDBOXED = "sandboxed"  # Runs in sandboxed environment


class MCPBusBinding(BaseModel):
    """Configuration for binding an MCP server to a specific bus."""

    bus_type: MCPBusType = Field(..., description="Which bus to bind to")
    enabled: bool = Field(True, description="Whether this binding is active")
    priority: int = Field(50, ge=0, le=100, description="Priority for this binding (0-100)")
    capability_filter: List[str] = Field(
        default_factory=list, description="Filter to specific capabilities (empty = all)"
    )

    model_config = ConfigDict(extra="forbid")


class MCPSecurityConfig(BaseModel):
    """Security configuration for MCP server connections."""

    # Version pinning
    pin_version: Optional[str] = Field(None, description="Pin to specific MCP server version")
    allow_version_updates: bool = Field(False, description="Allow automatic version updates")

    # Permission controls
    permission_level: MCPPermissionLevel = Field(
        MCPPermissionLevel.SANDBOXED, description="Permission level for this server"
    )
    allowed_tools: List[str] = Field(default_factory=list, description="Whitelist of allowed tool names (empty = all)")
    blocked_tools: List[str] = Field(default_factory=list, description="Blacklist of blocked tool names")

    # Input/output validation
    validate_inputs: bool = Field(True, description="Validate all inputs against schemas")
    validate_outputs: bool = Field(True, description="Validate all outputs against schemas")
    max_input_size_bytes: int = Field(1024 * 1024, description="Max input size in bytes")
    max_output_size_bytes: int = Field(10 * 1024 * 1024, description="Max output size in bytes")

    # Tool poisoning protection
    detect_tool_poisoning: bool = Field(True, description="Detect malicious instructions in tool descriptions")
    hidden_instruction_patterns: List[str] = Field(
        default_factory=lambda: [
            r"<hidden>.*</hidden>",
            r"<!--.*-->",
            r"\x00.*\x00",  # Null byte injection
            r"SYSTEM:.*",
            r"IGNORE PREVIOUS.*",
        ],
        description="Regex patterns to detect hidden instructions",
    )

    # Rate limiting
    max_calls_per_minute: int = Field(60, description="Max tool calls per minute")
    max_concurrent_calls: int = Field(5, description="Max concurrent tool calls")

    # Sandboxing
    sandbox_enabled: bool = Field(True, description="Run in sandboxed environment")
    network_access: bool = Field(False, description="Allow network access from sandbox")
    filesystem_access: List[str] = Field(default_factory=list, description="Allowed filesystem paths")

    # Token security (OAuth)
    require_resource_indicator: bool = Field(True, description="Require resource indicator in token requests")
    token_audience_validation: bool = Field(True, description="Validate token audience matches server")

    model_config = ConfigDict(extra="forbid")


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""

    # Server identification
    server_id: str = Field(..., description="Unique identifier for this server")
    name: str = Field(..., description="Human-readable server name")
    description: str = Field("", description="Description of what this server provides")

    # Connection settings
    transport: MCPTransportType = Field(MCPTransportType.STDIO, description="Transport type for server connection")
    command: Optional[str] = Field(None, description="Command to start stdio server")
    args: List[str] = Field(default_factory=list, description="Arguments for stdio command")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    url: Optional[str] = Field(None, description="URL for HTTP/WebSocket transports")

    # Bus bindings - which buses this server connects to
    bus_bindings: List[MCPBusBinding] = Field(default_factory=list, description="Bus bindings for this server")

    # Security
    security: MCPSecurityConfig = Field(default_factory=MCPSecurityConfig, description="Security configuration")

    # Enable/disable
    enabled: bool = Field(True, description="Whether this server is enabled")
    auto_start: bool = Field(True, description="Start server automatically on adapter start")

    # Metadata
    source: str = Field("config", description="Where this config came from (config/graph/api)")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    model_config = ConfigDict(extra="forbid")

    @field_validator("command", mode="before")
    @classmethod
    def validate_command(cls, v: Optional[str]) -> Optional[str]:
        """Validate command doesn't contain obvious injection attempts."""
        if v is None:
            return v
        dangerous_patterns = [";", "&&", "||", "|", "`", "$(", "$(", ">", "<", "\n", "\r"]
        for pattern in dangerous_patterns:
            if pattern in v:
                raise ValueError(f"Command contains potentially dangerous character: {pattern}")
        return v


class MCPAdapterConfig(BaseModel):
    """Main configuration for the MCP adapter."""

    # Server configurations
    servers: List[MCPServerConfig] = Field(default_factory=list, description="List of MCP server configurations")

    # Global security settings
    global_security: MCPSecurityConfig = Field(
        default_factory=MCPSecurityConfig, description="Global security defaults"
    )

    # Graph configuration key for self-configuration
    config_key_prefix: str = Field("mcp.servers", description="Config key prefix for graph storage")

    # Adapter settings
    adapter_id: str = Field("mcp_default", description="Adapter identifier")
    auto_discover_servers: bool = Field(False, description="Auto-discover MCP servers from environment")

    # Telemetry
    enable_telemetry: bool = Field(True, description="Enable telemetry collection")
    log_level: str = Field("INFO", description="Logging level for MCP operations")

    model_config = ConfigDict(extra="forbid")

    def load_env_vars(self) -> None:
        """Load configuration from environment variables."""
        # Load global settings from environment
        if os.environ.get("MCP_ADAPTER_ID"):
            self.adapter_id = os.environ["MCP_ADAPTER_ID"]

        if os.environ.get("MCP_LOG_LEVEL"):
            self.log_level = os.environ["MCP_LOG_LEVEL"]

        if os.environ.get("MCP_AUTO_DISCOVER") == "true":
            self.auto_discover_servers = True

        # Load server configurations from MCP_SERVER_* environment variables
        self._load_servers_from_env()

    def _load_servers_from_env(self) -> None:
        """Load server configurations from environment variables.

        Format: MCP_SERVER_<ID>_<PROPERTY>=value
        Example:
            MCP_SERVER_WEATHER_COMMAND=npx
            MCP_SERVER_WEATHER_ARGS=-y,@weather/server
            MCP_SERVER_WEATHER_TRANSPORT=stdio
            MCP_SERVER_WEATHER_BUSES=tool,wise
        """
        server_ids: Set[str] = set()

        # Find all unique server IDs
        for key in os.environ:
            if key.startswith("MCP_SERVER_") and key.count("_") >= 3:
                parts = key.split("_")
                if len(parts) >= 3:
                    server_id = parts[2]
                    server_ids.add(server_id)

        # Load each server configuration
        for server_id in server_ids:
            prefix = f"MCP_SERVER_{server_id}_"

            # Check if this server already exists
            existing = next((s for s in self.servers if s.server_id == server_id.lower()), None)
            if existing:
                continue

            # Build server config from environment
            command = os.environ.get(f"{prefix}COMMAND")
            if not command:
                continue  # Skip servers without a command

            args_str = os.environ.get(f"{prefix}ARGS", "")
            args = [a.strip() for a in args_str.split(",") if a.strip()]

            transport_str = os.environ.get(f"{prefix}TRANSPORT", "stdio")
            try:
                transport = MCPTransportType(transport_str)
            except ValueError:
                transport = MCPTransportType.STDIO

            # Parse bus bindings
            buses_str = os.environ.get(f"{prefix}BUSES", "tool")
            bus_bindings = []
            for bus_name in buses_str.split(","):
                bus_name = bus_name.strip().lower()
                try:
                    bus_type = MCPBusType(bus_name)
                    bus_bindings.append(MCPBusBinding(bus_type=bus_type))
                except ValueError:
                    logger.warning(f"Unknown bus type: {bus_name}")

            # Create server config
            server_config = MCPServerConfig(
                server_id=server_id.lower(),
                name=os.environ.get(f"{prefix}NAME", server_id),
                description=os.environ.get(f"{prefix}DESCRIPTION", ""),
                transport=transport,
                command=command,
                args=args,
                url=os.environ.get(f"{prefix}URL"),
                bus_bindings=bus_bindings if bus_bindings else [MCPBusBinding(bus_type=MCPBusType.TOOL)],
                source="environment",
            )

            self.servers.append(server_config)
            logger.info(f"Loaded MCP server from environment: {server_id}")

    def get_servers_for_bus(self, bus_type: MCPBusType) -> List[MCPServerConfig]:
        """Get all servers configured for a specific bus type."""
        result = []
        for server in self.servers:
            if not server.enabled:
                continue
            for binding in server.bus_bindings:
                if binding.bus_type == bus_type and binding.enabled:
                    result.append(server)
                    break
        return result


__all__ = [
    "MCPTransportType",
    "MCPBusType",
    "MCPPermissionLevel",
    "MCPBusBinding",
    "MCPSecurityConfig",
    "MCPServerConfig",
    "MCPAdapterConfig",
]
