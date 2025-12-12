"""
MCP Server Adapter for CIRIS.

Exposes CIRIS capabilities as an MCP server, allowing external
AI agents and applications to interact with CIRIS via the
Model Context Protocol.

Features:
- Expose CIRIS tools as MCP tools
- Expose agent state/data as MCP resources
- Expose guidance prompts as MCP prompts
- Multiple transport support (stdio, SSE, HTTP)
- Authentication and authorization
- Rate limiting and request validation
"""

import logging

from .adapter import Adapter
from .config import (
    MCPServerAdapterConfig,
    MCPServerExposureConfig,
    MCPServerSecurityConfig,
    MCPServerTransportConfig,
    TransportType,
)
from .configurable import MCPServerConfigurableAdapter
from .security import MCPServerAuthenticator, MCPServerRateLimiter, MCPServerSecurityManager

logger = logging.getLogger(__name__)

__all__ = [
    # Main adapter
    "Adapter",
    # Configuration
    "MCPServerAdapterConfig",
    "MCPServerExposureConfig",
    "MCPServerSecurityConfig",
    "MCPServerTransportConfig",
    "TransportType",
    # Configurable
    "MCPServerConfigurableAdapter",
    # Security
    "MCPServerSecurityManager",
    "MCPServerAuthenticator",
    "MCPServerRateLimiter",
]
