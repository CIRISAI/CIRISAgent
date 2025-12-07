"""
MCP Protocol Helpers.

Common protocol utilities for MCP client and server implementations.
Based on MCP specification: https://modelcontextprotocol.io/specification
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class MCPProtocolVersion(str, Enum):
    """Supported MCP protocol versions."""

    V1_0 = "1.0"
    V2024_11_05 = "2024-11-05"  # Current stable
    V2025_03_26 = "2025-03-26"  # Latest draft with streamable HTTP


class MCPMessageType(str, Enum):
    """MCP message types."""

    # Lifecycle
    INITIALIZE = "initialize"
    INITIALIZED = "initialized"
    SHUTDOWN = "shutdown"

    # Tools
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"

    # Resources
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    RESOURCES_SUBSCRIBE = "resources/subscribe"
    RESOURCES_UNSUBSCRIBE = "resources/unsubscribe"

    # Prompts
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"

    # Sampling (server -> client)
    SAMPLING_CREATE_MESSAGE = "sampling/createMessage"

    # Logging
    LOGGING_SET_LEVEL = "logging/setLevel"

    # Notifications
    NOTIFICATION_CANCELLED = "notifications/cancelled"
    NOTIFICATION_PROGRESS = "notifications/progress"
    NOTIFICATION_RESOURCES_UPDATED = "notifications/resources/updated"
    NOTIFICATION_RESOURCES_LIST_CHANGED = "notifications/resources/list_changed"
    NOTIFICATION_TOOLS_LIST_CHANGED = "notifications/tools/list_changed"
    NOTIFICATION_PROMPTS_LIST_CHANGED = "notifications/prompts/list_changed"

    # Completion
    COMPLETION_COMPLETE = "completion/complete"

    # Roots
    ROOTS_LIST = "roots/list"

    # Ping
    PING = "ping"


class MCPCapability(str, Enum):
    """MCP server/client capabilities."""

    # Server capabilities
    TOOLS = "tools"
    RESOURCES = "resources"
    PROMPTS = "prompts"
    LOGGING = "logging"
    EXPERIMENTAL = "experimental"

    # Client capabilities
    SAMPLING = "sampling"
    ROOTS = "roots"


class MCPErrorCode(int, Enum):
    """MCP error codes (JSON-RPC 2.0 compatible)."""

    # Standard JSON-RPC errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603

    # MCP-specific errors
    RESOURCE_NOT_FOUND = -32001
    TOOL_NOT_FOUND = -32002
    PROMPT_NOT_FOUND = -32003
    UNAUTHORIZED = -32004
    RATE_LIMITED = -32005
    REQUEST_CANCELLED = -32006


class MCPError(BaseModel):
    """MCP error response."""

    code: MCPErrorCode = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional error data")

    model_config = ConfigDict(extra="forbid")


class MCPMessage(BaseModel):
    """Base MCP message structure (JSON-RPC 2.0)."""

    jsonrpc: str = Field("2.0", description="JSON-RPC version")
    id: Optional[Union[str, int]] = Field(None, description="Request ID")
    method: Optional[str] = Field(None, description="Method name")
    params: Optional[Dict[str, Any]] = Field(None, description="Method parameters")
    result: Optional[Any] = Field(None, description="Result for responses")
    error: Optional[MCPError] = Field(None, description="Error for error responses")

    model_config = ConfigDict(extra="forbid")

    def is_request(self) -> bool:
        """Check if this is a request message."""
        return self.method is not None and self.id is not None

    def is_notification(self) -> bool:
        """Check if this is a notification (request without id)."""
        return self.method is not None and self.id is None

    def is_response(self) -> bool:
        """Check if this is a response message."""
        return self.method is None and (self.result is not None or self.error is not None)


def validate_mcp_message(data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
    """Validate an MCP message structure.

    Args:
        data: Raw message data

    Returns:
        (is_valid, error_message) tuple
    """
    # Check JSON-RPC version
    if data.get("jsonrpc") != "2.0":
        return False, "Invalid or missing jsonrpc version"

    # Must have either method (request/notification) or result/error (response)
    has_method = "method" in data
    has_result = "result" in data
    has_error = "error" in data

    if not has_method and not has_result and not has_error:
        return False, "Message must have method, result, or error"

    if has_method and (has_result or has_error):
        return False, "Request/notification cannot have result or error"

    if has_result and has_error:
        return False, "Response cannot have both result and error"

    # Validate error structure if present
    if has_error:
        error = data["error"]
        if not isinstance(error, dict):
            return False, "Error must be an object"
        if "code" not in error or "message" not in error:
            return False, "Error must have code and message"

    return True, None


def create_success_response(request_id: Union[str, int], result: Any) -> MCPMessage:
    """Create a success response message.

    Args:
        request_id: ID from the request
        result: Result data

    Returns:
        MCPMessage with result
    """
    return MCPMessage(
        jsonrpc="2.0",
        id=request_id,
        result=result,
    )


def create_error_response(
    request_id: Optional[Union[str, int]],
    code: MCPErrorCode,
    message: str,
    data: Optional[Dict[str, Any]] = None,
) -> MCPMessage:
    """Create an error response message.

    Args:
        request_id: ID from the request (None for parse errors)
        code: Error code
        message: Error message
        data: Additional error data

    Returns:
        MCPMessage with error
    """
    return MCPMessage(
        jsonrpc="2.0",
        id=request_id,
        error=MCPError(code=code, message=message, data=data),
    )


def create_notification(method: str, params: Optional[Dict[str, Any]] = None) -> MCPMessage:
    """Create a notification message (no response expected).

    Args:
        method: Notification method
        params: Notification parameters

    Returns:
        MCPMessage notification
    """
    return MCPMessage(
        jsonrpc="2.0",
        method=method,
        params=params,
    )


def create_request(request_id: Union[str, int], method: str, params: Optional[Dict[str, Any]] = None) -> MCPMessage:
    """Create a request message.

    Args:
        request_id: Unique request ID
        method: Method to call
        params: Method parameters

    Returns:
        MCPMessage request
    """
    return MCPMessage(
        jsonrpc="2.0",
        id=request_id,
        method=method,
        params=params,
    )


class ServerCapabilities(BaseModel):
    """MCP server capabilities declaration."""

    tools: Optional[Dict[str, Any]] = Field(None, description="Tool capabilities")
    resources: Optional[Dict[str, Any]] = Field(None, description="Resource capabilities")
    prompts: Optional[Dict[str, Any]] = Field(None, description="Prompt capabilities")
    logging: Optional[Dict[str, Any]] = Field(None, description="Logging capabilities")
    experimental: Optional[Dict[str, Any]] = Field(None, description="Experimental features")

    model_config = ConfigDict(extra="forbid")


class ClientCapabilities(BaseModel):
    """MCP client capabilities declaration."""

    sampling: Optional[Dict[str, Any]] = Field(None, description="Sampling capabilities")
    roots: Optional[Dict[str, Any]] = Field(None, description="Roots capabilities")
    experimental: Optional[Dict[str, Any]] = Field(None, description="Experimental features")

    model_config = ConfigDict(extra="forbid")


class InitializeParams(BaseModel):
    """Parameters for initialize request."""

    protocolVersion: str = Field(..., description="Protocol version")
    capabilities: ClientCapabilities = Field(..., description="Client capabilities")
    clientInfo: Dict[str, str] = Field(..., description="Client information")

    model_config = ConfigDict(extra="forbid")


class InitializeResult(BaseModel):
    """Result for initialize request."""

    protocolVersion: str = Field(..., description="Negotiated protocol version")
    capabilities: ServerCapabilities = Field(..., description="Server capabilities")
    serverInfo: Dict[str, str] = Field(..., description="Server information")
    instructions: Optional[str] = Field(None, description="Usage instructions")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "MCPProtocolVersion",
    "MCPMessageType",
    "MCPCapability",
    "MCPErrorCode",
    "MCPError",
    "MCPMessage",
    "validate_mcp_message",
    "create_success_response",
    "create_error_response",
    "create_notification",
    "create_request",
    "ServerCapabilities",
    "ClientCapabilities",
    "InitializeParams",
    "InitializeResult",
]
