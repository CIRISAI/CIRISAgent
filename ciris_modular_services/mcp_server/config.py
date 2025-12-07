"""
MCP Server Adapter Configuration.

Configuration for exposing CIRIS as an MCP server.
"""

import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class TransportType(str, Enum):
    """MCP server transport types."""

    STDIO = "stdio"  # For Claude Desktop, local tools
    SSE = "sse"  # Server-sent events over HTTP
    STREAMABLE_HTTP = "streamable_http"  # Full HTTP streaming
    WEBSOCKET = "websocket"  # WebSocket transport


class AuthMethod(str, Enum):
    """Authentication methods for MCP clients."""

    NONE = "none"  # No authentication (local only)
    API_KEY = "api_key"  # Simple API key
    OAUTH2 = "oauth2"  # OAuth 2.0
    JWT = "jwt"  # JWT tokens
    MTLS = "mtls"  # Mutual TLS


class MCPServerTransportConfig(BaseModel):
    """Transport-specific configuration."""

    type: TransportType = Field(TransportType.STDIO, description="Transport type")

    # HTTP/SSE/WebSocket settings
    host: str = Field("127.0.0.1", description="Host to bind to")
    port: int = Field(3000, description="Port to listen on")
    path: str = Field("/mcp", description="URL path for MCP endpoint")

    # TLS settings
    tls_enabled: bool = Field(False, description="Enable TLS")
    tls_cert_file: Optional[str] = Field(None, description="TLS certificate file")
    tls_key_file: Optional[str] = Field(None, description="TLS key file")

    # Connection limits
    max_connections: int = Field(100, description="Maximum concurrent connections")
    connection_timeout_seconds: int = Field(300, description="Connection timeout")

    model_config = ConfigDict(extra="forbid")


class MCPServerSecurityConfig(BaseModel):
    """Security configuration for MCP server."""

    # Authentication
    auth_methods: List[AuthMethod] = Field(
        default_factory=lambda: [AuthMethod.NONE],
        description="Allowed authentication methods",
    )
    require_auth: bool = Field(False, description="Require authentication")
    api_keys: List[str] = Field(default_factory=list, description="Valid API keys")

    # Client allowlist/blocklist
    allowed_clients: List[str] = Field(default_factory=list, description="Allowed client identifiers (empty = all)")
    blocked_clients: List[str] = Field(default_factory=list, description="Blocked client identifiers")

    # Rate limiting
    rate_limit_enabled: bool = Field(True, description="Enable rate limiting")
    max_requests_per_minute: int = Field(100, description="Max requests per minute per client")
    max_concurrent_requests: int = Field(10, description="Max concurrent requests per client")

    # Request validation
    validate_requests: bool = Field(True, description="Validate all requests")
    max_request_size_bytes: int = Field(1024 * 1024, description="Max request size")
    max_response_size_bytes: int = Field(10 * 1024 * 1024, description="Max response size")

    # Data protection
    redact_pii: bool = Field(False, description="Redact PII from responses")
    audit_requests: bool = Field(True, description="Audit all requests")

    # Sampling security (if server requests LLM completions from client)
    allow_sampling: bool = Field(False, description="Allow sampling requests to client")
    sampling_requires_approval: bool = Field(True, description="Require user approval for sampling")

    model_config = ConfigDict(extra="forbid")


class MCPServerExposureConfig(BaseModel):
    """Configuration for what CIRIS capabilities to expose."""

    # Tool exposure
    expose_tools: bool = Field(True, description="Expose CIRIS tools")
    tool_allowlist: List[str] = Field(default_factory=list, description="Tools to expose (empty = all allowed)")
    tool_blocklist: List[str] = Field(default_factory=list, description="Tools to never expose")

    # Resource exposure
    expose_resources: bool = Field(True, description="Expose CIRIS resources")
    resource_allowlist: List[str] = Field(default_factory=list, description="Resource URIs to expose")
    resource_blocklist: List[str] = Field(default_factory=list, description="Resource URIs to never expose")

    # Prompt exposure
    expose_prompts: bool = Field(True, description="Expose CIRIS prompts")
    prompt_allowlist: List[str] = Field(default_factory=list, description="Prompts to expose")
    prompt_blocklist: List[str] = Field(default_factory=list, description="Prompts to never expose")

    # Default tools to expose (common CIRIS operations)
    default_tools: List[str] = Field(
        default_factory=lambda: [
            "ciris_search_memory",
            "ciris_get_status",
            "ciris_submit_task",
        ],
        description="Default tools to expose",
    )

    # Default resources to expose
    default_resources: List[str] = Field(
        default_factory=lambda: [
            "ciris://status",
            "ciris://health",
        ],
        description="Default resources to expose",
    )

    # Default prompts to expose
    default_prompts: List[str] = Field(
        default_factory=lambda: [
            "guidance",
            "ethical_review",
        ],
        description="Default prompts to expose",
    )

    model_config = ConfigDict(extra="forbid")


class MCPServerAdapterConfig(BaseModel):
    """Main configuration for MCP server adapter."""

    # Server identification
    server_id: str = Field("ciris-mcp-server", description="Server identifier")
    server_name: str = Field("CIRIS MCP Server", description="Human-readable server name")
    server_version: str = Field("1.0.0", description="Server version")
    server_description: str = Field(
        "CIRIS Agent exposed via Model Context Protocol",
        description="Server description",
    )

    # Protocol settings
    protocol_version: str = Field("2024-11-05", description="MCP protocol version")

    # Transport configuration
    transport: MCPServerTransportConfig = Field(
        default_factory=MCPServerTransportConfig,
        description="Transport configuration",
    )

    # Security configuration
    security: MCPServerSecurityConfig = Field(
        default_factory=MCPServerSecurityConfig,
        description="Security configuration",
    )

    # Exposure configuration
    exposure: MCPServerExposureConfig = Field(
        default_factory=MCPServerExposureConfig,
        description="What to expose",
    )

    # Server behavior
    enabled: bool = Field(True, description="Whether server is enabled")
    auto_start: bool = Field(True, description="Start server on adapter start")

    # Telemetry
    enable_telemetry: bool = Field(True, description="Enable telemetry")
    log_level: str = Field("INFO", description="Log level")

    # Graph config key
    config_key_prefix: str = Field("mcp_server", description="Config key prefix for graph storage")

    model_config = ConfigDict(extra="forbid")

    def load_env_vars(self) -> None:
        """Load configuration from environment variables."""
        # Server settings
        if os.environ.get("MCP_SERVER_ID"):
            self.server_id = os.environ["MCP_SERVER_ID"]

        if os.environ.get("MCP_SERVER_NAME"):
            self.server_name = os.environ["MCP_SERVER_NAME"]

        # Transport settings
        if os.environ.get("MCP_SERVER_TRANSPORT"):
            try:
                self.transport.type = TransportType(os.environ["MCP_SERVER_TRANSPORT"])
            except ValueError:
                logger.warning(f"Invalid transport type: {os.environ['MCP_SERVER_TRANSPORT']}")

        if os.environ.get("MCP_SERVER_HOST"):
            self.transport.host = os.environ["MCP_SERVER_HOST"]

        if os.environ.get("MCP_SERVER_PORT"):
            try:
                self.transport.port = int(os.environ["MCP_SERVER_PORT"])
            except ValueError:
                logger.warning(f"Invalid port: {os.environ['MCP_SERVER_PORT']}")

        # Security settings
        if os.environ.get("MCP_SERVER_REQUIRE_AUTH") == "true":
            self.security.require_auth = True

        if os.environ.get("MCP_SERVER_API_KEYS"):
            self.security.api_keys = os.environ["MCP_SERVER_API_KEYS"].split(",")

        if os.environ.get("MCP_SERVER_ALLOWED_CLIENTS"):
            self.security.allowed_clients = os.environ["MCP_SERVER_ALLOWED_CLIENTS"].split(",")

    def get_exposed_tools(self, available_tools: List[str]) -> List[str]:
        """Get list of tools to expose based on configuration.

        Args:
            available_tools: All available tools

        Returns:
            List of tool names to expose
        """
        if not self.exposure.expose_tools:
            return []

        # Start with allowlist or all available
        if self.exposure.tool_allowlist:
            tools = [t for t in available_tools if t in self.exposure.tool_allowlist]
        else:
            tools = available_tools.copy()

        # Add defaults
        for tool in self.exposure.default_tools:
            if tool in available_tools and tool not in tools:
                tools.append(tool)

        # Apply blocklist
        tools = [t for t in tools if t not in self.exposure.tool_blocklist]

        return tools


__all__ = [
    "TransportType",
    "AuthMethod",
    "MCPServerTransportConfig",
    "MCPServerSecurityConfig",
    "MCPServerExposureConfig",
    "MCPServerAdapterConfig",
]
