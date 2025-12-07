"""
MCP Adapter Schemas.

Schemas for MCP server configuration that can be stored in the graph.
These schemas enable agent self-configuration of MCP servers.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MCPTransportType(str, Enum):
    """MCP transport types."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"
    WEBSOCKET = "websocket"


class MCPBusType(str, Enum):
    """Bus types that MCP servers can bind to."""

    TOOL = "tool"
    COMMUNICATION = "communication"
    WISE = "wise"


class MCPPermissionLevel(str, Enum):
    """Permission levels for MCP server capabilities."""

    READ_ONLY = "read_only"
    EXECUTE = "execute"
    FULL = "full"
    SANDBOXED = "sandboxed"


class MCPBusBindingSchema(BaseModel):
    """Schema for MCP bus binding configuration."""

    bus_type: MCPBusType = Field(..., description="Which bus to bind to")
    enabled: bool = Field(True, description="Whether this binding is active")
    priority: int = Field(50, ge=0, le=100, description="Priority for this binding")
    capability_filter: List[str] = Field(default_factory=list, description="Filter to specific capabilities")

    model_config = ConfigDict(extra="forbid")


class MCPSecurityConfigSchema(BaseModel):
    """Schema for MCP server security configuration."""

    pin_version: Optional[str] = Field(None, description="Pin to specific version")
    allow_version_updates: bool = Field(False, description="Allow version updates")
    permission_level: MCPPermissionLevel = Field(MCPPermissionLevel.SANDBOXED, description="Permission level")
    allowed_tools: List[str] = Field(default_factory=list, description="Whitelist of allowed tools")
    blocked_tools: List[str] = Field(default_factory=list, description="Blacklist of blocked tools")
    validate_inputs: bool = Field(True, description="Validate inputs")
    validate_outputs: bool = Field(True, description="Validate outputs")
    max_input_size_bytes: int = Field(1048576, description="Max input size")
    max_output_size_bytes: int = Field(10485760, description="Max output size")
    detect_tool_poisoning: bool = Field(True, description="Detect tool poisoning")
    max_calls_per_minute: int = Field(60, description="Rate limit")
    max_concurrent_calls: int = Field(5, description="Concurrent limit")
    sandbox_enabled: bool = Field(True, description="Enable sandboxing")
    network_access: bool = Field(False, description="Allow network access")

    model_config = ConfigDict(extra="forbid")


class MCPServerConfigSchema(BaseModel):
    """Schema for MCP server configuration stored in graph.

    This schema enables agent self-configuration of MCP servers
    through the config service.
    """

    server_id: str = Field(..., description="Unique server identifier")
    name: str = Field(..., description="Human-readable name")
    description: str = Field("", description="Server description")
    transport: MCPTransportType = Field(MCPTransportType.STDIO, description="Transport type")
    command: Optional[str] = Field(None, description="Command for stdio")
    args: List[str] = Field(default_factory=list, description="Command arguments")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment vars")
    url: Optional[str] = Field(None, description="URL for HTTP transports")
    bus_bindings: List[MCPBusBindingSchema] = Field(default_factory=list, description="Bus bindings")
    security: MCPSecurityConfigSchema = Field(default_factory=MCPSecurityConfigSchema, description="Security config")
    enabled: bool = Field(True, description="Server enabled")
    auto_start: bool = Field(True, description="Auto-start on adapter start")
    source: str = Field("graph", description="Configuration source")
    tags: List[str] = Field(default_factory=list, description="Tags")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation time",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Last update time",
    )

    model_config = ConfigDict(extra="forbid")


class MCPServerStatus(BaseModel):
    """Status of an MCP server connection."""

    server_id: str = Field(..., description="Server identifier")
    connected: bool = Field(..., description="Whether connected")
    healthy: bool = Field(..., description="Whether healthy")
    connected_at: Optional[datetime] = Field(None, description="Connection time")
    last_activity: Optional[datetime] = Field(None, description="Last activity")
    tools_available: int = Field(0, description="Number of tools")
    prompts_available: int = Field(0, description="Number of prompts")
    resources_available: int = Field(0, description="Number of resources")
    error: Optional[str] = Field(None, description="Error message if unhealthy")

    model_config = ConfigDict(extra="forbid")


class MCPAdapterTelemetry(BaseModel):
    """Telemetry data for the MCP adapter."""

    adapter_id: str = Field(..., description="Adapter identifier")
    running: bool = Field(..., description="Whether adapter is running")
    servers_configured: int = Field(..., description="Configured servers")
    servers_connected: int = Field(..., description="Connected servers")
    total_tool_executions: int = Field(0, description="Tool executions")
    total_guidance_requests: int = Field(0, description="Guidance requests")
    total_messages: int = Field(0, description="Messages sent/received")
    total_errors: int = Field(0, description="Total errors")
    total_blocked: int = Field(0, description="Blocked operations")
    uptime_seconds: float = Field(0.0, description="Adapter uptime")
    security_violations: int = Field(0, description="Security violations")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "MCPTransportType",
    "MCPBusType",
    "MCPPermissionLevel",
    "MCPBusBindingSchema",
    "MCPSecurityConfigSchema",
    "MCPServerConfigSchema",
    "MCPServerStatus",
    "MCPAdapterTelemetry",
]
