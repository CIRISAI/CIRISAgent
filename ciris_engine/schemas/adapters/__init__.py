"""
Adapter-specific schemas.

These schemas are used for adapter registration and management.
"""

from .registration import AdapterServiceRegistration
from .runtime_context import AdapterStartupContext
from .mcp import (
    MCPAdapterTelemetry,
    MCPBusBindingSchema,
    MCPBusType,
    MCPPermissionLevel,
    MCPSecurityConfigSchema,
    MCPServerConfigSchema,
    MCPServerStatus,
    MCPTransportType,
)

__all__ = [
    "AdapterServiceRegistration",
    "AdapterStartupContext",
    # MCP schemas
    "MCPTransportType",
    "MCPBusType",
    "MCPPermissionLevel",
    "MCPBusBindingSchema",
    "MCPSecurityConfigSchema",
    "MCPServerConfigSchema",
    "MCPServerStatus",
    "MCPAdapterTelemetry",
]
