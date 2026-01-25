"""
MCP Server Adapter for CIRIS.

Exposes CIRIS as an MCP server with 3 simple tools:
- status: Get agent status
- message: Send a message to user's channel
- history: Get message history

Supports stdio transport for Claude Desktop integration
and HTTP/SSE for web applications.
"""

import logging

from .adapter import Adapter
from .config import MCPServerConfig, MCPTransportType
from .handlers import MCPServerHandler, TOOLS

logger = logging.getLogger(__name__)

__all__ = [
    # Main adapter
    "Adapter",
    # Configuration
    "MCPServerConfig",
    "MCPTransportType",
    # Handler
    "MCPServerHandler",
    "TOOLS",
]
