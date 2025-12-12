"""Tests for MCP common protocol utilities."""

import pytest

from ciris_adapters.mcp_common.protocol import (
    MCPCapability,
    MCPError,
    MCPErrorCode,
    MCPMessage,
    MCPMessageType,
    MCPProtocolVersion,
    create_error_response,
    create_notification,
    create_request,
    create_success_response,
    validate_mcp_message,
)


class TestMCPProtocolVersion:
    """Tests for MCPProtocolVersion enum."""

    def test_versions(self) -> None:
        """Test protocol versions are defined."""
        assert MCPProtocolVersion.V1_0 == "1.0"
        assert MCPProtocolVersion.V2024_11_05 == "2024-11-05"
        assert MCPProtocolVersion.V2025_03_26 == "2025-03-26"


class TestMCPMessageType:
    """Tests for MCPMessageType enum."""

    def test_lifecycle_types(self) -> None:
        """Test lifecycle message types."""
        assert MCPMessageType.INITIALIZE == "initialize"
        assert MCPMessageType.INITIALIZED == "initialized"
        assert MCPMessageType.SHUTDOWN == "shutdown"

    def test_tool_types(self) -> None:
        """Test tool message types."""
        assert MCPMessageType.TOOLS_LIST == "tools/list"
        assert MCPMessageType.TOOLS_CALL == "tools/call"

    def test_resource_types(self) -> None:
        """Test resource message types."""
        assert MCPMessageType.RESOURCES_LIST == "resources/list"
        assert MCPMessageType.RESOURCES_READ == "resources/read"

    def test_prompt_types(self) -> None:
        """Test prompt message types."""
        assert MCPMessageType.PROMPTS_LIST == "prompts/list"
        assert MCPMessageType.PROMPTS_GET == "prompts/get"


class TestMCPErrorCode:
    """Tests for MCPErrorCode enum."""

    def test_standard_errors(self) -> None:
        """Test standard JSON-RPC errors."""
        assert MCPErrorCode.PARSE_ERROR == -32700
        assert MCPErrorCode.INVALID_REQUEST == -32600
        assert MCPErrorCode.METHOD_NOT_FOUND == -32601
        assert MCPErrorCode.INVALID_PARAMS == -32602
        assert MCPErrorCode.INTERNAL_ERROR == -32603

    def test_mcp_specific_errors(self) -> None:
        """Test MCP-specific errors."""
        assert MCPErrorCode.RESOURCE_NOT_FOUND == -32001
        assert MCPErrorCode.TOOL_NOT_FOUND == -32002
        assert MCPErrorCode.UNAUTHORIZED == -32004
        assert MCPErrorCode.RATE_LIMITED == -32005


class TestMCPMessage:
    """Tests for MCPMessage model."""

    def test_request_message(self) -> None:
        """Test creating a request message."""
        msg = MCPMessage(
            jsonrpc="2.0",
            id=1,
            method="tools/list",
            params={},
        )
        assert msg.is_request() is True
        assert msg.is_notification() is False
        assert msg.is_response() is False

    def test_notification_message(self) -> None:
        """Test creating a notification message."""
        msg = MCPMessage(
            jsonrpc="2.0",
            method="notifications/cancelled",
        )
        assert msg.is_request() is False
        assert msg.is_notification() is True
        assert msg.is_response() is False

    def test_response_message(self) -> None:
        """Test creating a response message."""
        msg = MCPMessage(
            jsonrpc="2.0",
            id=1,
            result={"tools": []},
        )
        assert msg.is_request() is False
        assert msg.is_notification() is False
        assert msg.is_response() is True

    def test_error_response(self) -> None:
        """Test creating an error response."""
        msg = MCPMessage(
            jsonrpc="2.0",
            id=1,
            error=MCPError(
                code=MCPErrorCode.METHOD_NOT_FOUND,
                message="Method not found",
            ),
        )
        assert msg.is_response() is True
        assert msg.error is not None
        assert msg.error.code == MCPErrorCode.METHOD_NOT_FOUND


class TestValidateMCPMessage:
    """Tests for validate_mcp_message function."""

    def test_valid_request(self) -> None:
        """Test validating a valid request."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is True
        assert error is None

    def test_valid_response(self) -> None:
        """Test validating a valid response."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"tools": []},
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is True
        assert error is None

    def test_valid_notification(self) -> None:
        """Test validating a valid notification."""
        data = {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is True
        assert error is None

    def test_missing_jsonrpc(self) -> None:
        """Test validation fails for missing jsonrpc."""
        data = {
            "id": 1,
            "method": "tools/list",
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is False
        assert "jsonrpc" in error.lower()

    def test_wrong_jsonrpc_version(self) -> None:
        """Test validation fails for wrong version."""
        data = {
            "jsonrpc": "1.0",
            "id": 1,
            "method": "tools/list",
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is False

    def test_no_method_or_result(self) -> None:
        """Test validation fails with no method or result."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is False

    def test_request_with_result(self) -> None:
        """Test validation fails for request with result."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "result": {},
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is False

    def test_response_with_both_result_and_error(self) -> None:
        """Test validation fails for response with both."""
        data = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {},
            "error": {"code": -32600, "message": "Error"},
        }
        is_valid, error = validate_mcp_message(data)
        assert is_valid is False


class TestMessageCreators:
    """Tests for message creation functions."""

    def test_create_success_response(self) -> None:
        """Test creating a success response."""
        msg = create_success_response(1, {"tools": []})
        assert msg.jsonrpc == "2.0"
        assert msg.id == 1
        assert msg.result == {"tools": []}
        assert msg.error is None

    def test_create_error_response(self) -> None:
        """Test creating an error response."""
        msg = create_error_response(
            1,
            MCPErrorCode.METHOD_NOT_FOUND,
            "Method not found",
            {"available": ["tools/list"]},
        )
        assert msg.jsonrpc == "2.0"
        assert msg.id == 1
        assert msg.error is not None
        assert msg.error.code == MCPErrorCode.METHOD_NOT_FOUND
        assert msg.error.message == "Method not found"
        assert msg.error.data == {"available": ["tools/list"]}

    def test_create_error_response_no_data(self) -> None:
        """Test creating an error response without data."""
        msg = create_error_response(None, MCPErrorCode.PARSE_ERROR, "Parse error")
        assert msg.id is None
        assert msg.error is not None
        assert msg.error.data is None

    def test_create_notification(self) -> None:
        """Test creating a notification."""
        msg = create_notification(
            "notifications/progress",
            {"progressToken": "abc", "progress": 50},
        )
        assert msg.jsonrpc == "2.0"
        assert msg.id is None
        assert msg.method == "notifications/progress"
        assert msg.params == {"progressToken": "abc", "progress": 50}

    def test_create_request(self) -> None:
        """Test creating a request."""
        msg = create_request(
            1,
            "tools/call",
            {"name": "weather", "arguments": {"city": "NYC"}},
        )
        assert msg.jsonrpc == "2.0"
        assert msg.id == 1
        assert msg.method == "tools/call"
        assert msg.params["name"] == "weather"
