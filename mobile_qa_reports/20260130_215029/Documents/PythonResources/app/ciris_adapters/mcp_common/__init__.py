"""
MCP Common Utilities.

Shared code between MCP client and MCP server adapters:
- Protocol helpers
- Transport abstractions
- Schema converters
"""

import logging

from .protocol import (
    MCPCapability,
    MCPError,
    MCPErrorCode,
    MCPMessage,
    MCPMessageType,
    MCPProtocolVersion,
    create_error_response,
    create_success_response,
    validate_mcp_message,
)
from .schemas import MCPPromptArgument, MCPPromptInfo, MCPResourceInfo, MCPToolInfo, MCPToolInputSchema

logger = logging.getLogger(__name__)

__all__ = [
    # Protocol
    "MCPProtocolVersion",
    "MCPMessageType",
    "MCPCapability",
    "MCPMessage",
    "MCPError",
    "MCPErrorCode",
    "validate_mcp_message",
    "create_success_response",
    "create_error_response",
    # Schemas
    "MCPToolInfo",
    "MCPToolInputSchema",
    "MCPResourceInfo",
    "MCPPromptInfo",
    "MCPPromptArgument",
]
