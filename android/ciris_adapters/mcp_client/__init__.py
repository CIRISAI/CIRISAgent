"""
MCP (Model Context Protocol) Modular Adapter for CIRIS.

This adapter enables integration with MCP servers, providing:
- Tool service integration (execute MCP tools) via ToolBus
- Communication service integration (MCP resources as messages) via CommunicationBus
- Wise Authority service integration (MCP prompts for guidance) via WiseBus

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
- Dynamic bus binding reconfiguration
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
from .mcp_communication_service import MCPCommunicationService
from .mcp_tool_service import MCPToolService
from .mcp_wise_service import MCPWiseService
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
    "MCPWiseService",
    "MCPCommunicationService",
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
