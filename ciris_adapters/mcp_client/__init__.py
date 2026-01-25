"""
MCP (Model Context Protocol) Client Adapter for CIRIS.

This adapter enables integration with MCP servers as a pure tool service,
providing tool execution capabilities via ToolBus.

Security features implemented based on:
- https://modelcontextprotocol.io/specification/draft/basic/security_best_practices
- https://www.redhat.com/en/blog/model-context-protocol-mcp-understanding-security-risks-and-controls
- https://www.pillar.security/blog/the-security-risks-of-model-context-protocol-mcp

Features:
- Tool poisoning detection (hidden instruction patterns)
- Input/output validation with size limits
- Version pinning to prevent malicious updates
- Permission sandboxing with configurable levels
- Rate limiting per server
- Blocklist/allowlist for tools
- Graph-based configuration for agent self-configuration
"""

import logging

from .adapter import Adapter
from .config import (
    MCPAdapterConfig,
    MCPBusBinding,
    MCPBusType,
    MCPPermissionLevel,
    MCPSecurityConfig,
    MCPServerConfig,
    MCPTransportType,
)
from .configurable import MCPClientConfigurableAdapter
from .mcp_tool_service import MCPToolService
from .schemas import MCPAdapterTelemetry, MCPBusBindingSchema
from .schemas import MCPBusType as MCPBusTypeSchema
from .schemas import MCPPermissionLevel as MCPPermissionLevelSchema
from .schemas import MCPSecurityConfigSchema, MCPServerConfigSchema, MCPServerStatus
from .schemas import MCPTransportType as MCPTransportTypeSchema
from .security import MCPSecurityManager, RateLimiter, SecurityViolation, SecurityViolationType, ToolPoisoningDetector

logger = logging.getLogger(__name__)

__all__ = [
    # Main adapter
    "Adapter",
    # Configurable adapter
    "MCPClientConfigurableAdapter",
    # Configuration
    "MCPAdapterConfig",
    "MCPServerConfig",
    "MCPBusBinding",
    "MCPBusType",
    "MCPTransportType",
    "MCPPermissionLevel",
    "MCPSecurityConfig",
    # Services
    "MCPToolService",
    # Security
    "MCPSecurityManager",
    "SecurityViolation",
    "SecurityViolationType",
    "ToolPoisoningDetector",
    "RateLimiter",
    # Schemas (for backwards compatibility)
    "MCPAdapterTelemetry",
    "MCPBusBindingSchema",
    "MCPBusTypeSchema",
    "MCPPermissionLevelSchema",
    "MCPSecurityConfigSchema",
    "MCPServerConfigSchema",
    "MCPServerStatus",
    "MCPTransportTypeSchema",
]
