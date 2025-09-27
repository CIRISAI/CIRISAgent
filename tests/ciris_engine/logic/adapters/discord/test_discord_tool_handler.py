"""
Unit tests for Discord tool handler with robust mocking.

Tests tool execution, result management, and correlation tracking.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.discord.discord_tool_handler import DiscordToolHandler
from ciris_engine.schemas.adapters.tool_execution import ToolExecutionArgs, ToolHandlerContext
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest
from ciris_engine.schemas.telemetry.core import CorrelationType, ServiceCorrelation, ServiceCorrelationStatus
from tests.fixtures.discord_mocks import (
    MockDiscordClient,
    MockPersistenceForDiscord,
    MockTimeService,
    MockToolDescription,
    MockToolParameter,
    MockToolRegistry,
    create_exception_tool_handler,
    create_failing_tool_handler,
    create_successful_tool_handler,
    create_tool_execution_args,
    create_tool_execution_result,
    create_tool_info,
)


class TestDiscordToolHandler:
    """Test suite for DiscordToolHandler with robust mocking."""

    @pytest.fixture(autouse=True)
    def mock_persistence_functions(self):
        """Mock persistence functions for all tests."""
        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add:
            with patch("ciris_engine.logic.persistence.update_correlation") as mock_update:
                # Set default return values
                mock_add.return_value = "test-correlation-id"
                mock_update.return_value = True
                yield mock_add, mock_update

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        return MockTimeService(fixed_time=datetime(2025, 1, 27, 12, 0, 0, tzinfo=timezone.utc))

    @pytest.fixture
    def mock_client(self):
        """Create mock Discord client."""
        return MockDiscordClient()

    @pytest.fixture
    def mock_tool_registry(self):
        """Create mock tool registry."""
        registry = MockToolRegistry()
        # Add some test tools
        registry.add_tool("echo", create_successful_tool_handler({"echoed": "test"}))
        registry.add_tool("fail", create_failing_tool_handler("Intentional failure"))
        registry.add_tool("error", create_exception_tool_handler(RuntimeError("Test error")))
        return registry

    @pytest.fixture
    def handler(self, mock_client, mock_tool_registry, mock_time_service):
        """Create DiscordToolHandler instance."""
        return DiscordToolHandler(tool_registry=mock_tool_registry, client=mock_client, time_service=mock_time_service)

    def test_initialization_without_dependencies(self):
        """Test handler initialization without dependencies."""
        handler = DiscordToolHandler()
        assert handler.tool_registry is None
        assert handler.client is None
        assert handler._time_service is not None  # Should create default TimeService
        assert handler._tool_results == {}

    def test_initialization_with_dependencies(self, mock_client, mock_tool_registry, mock_time_service):
        """Test handler initialization with all dependencies."""
        handler = DiscordToolHandler(
            tool_registry=mock_tool_registry, client=mock_client, time_service=mock_time_service
        )
        assert handler.tool_registry == mock_tool_registry
        assert handler.client == mock_client
        assert handler._time_service == mock_time_service
        assert handler._tool_results == {}

    def test_set_client(self, handler, mock_client):
        """Test setting Discord client after initialization."""
        new_client = MockDiscordClient()
        handler.set_client(new_client)
        assert handler.client == new_client
        assert handler.client != mock_client

    def test_set_tool_registry(self, handler, mock_tool_registry):
        """Test setting tool registry after initialization."""
        new_registry = MockToolRegistry()
        handler.set_tool_registry(new_registry)
        assert handler.tool_registry == new_registry
        assert handler.tool_registry != mock_tool_registry

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, handler, mock_persistence_functions):
        """Test successful tool execution."""
        mock_add_corr, mock_update_corr = mock_persistence_functions

        tool_args = create_tool_execution_args(
            correlation_id="test-corr-001", tool_specific_params={"message": "hello"}
        )

        result = await handler.execute_tool("echo", tool_args)

        assert result.tool_name == "echo"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data == {"success": True, "data": {"echoed": "test"}}
        assert result.error is None
        assert result.correlation_id == "test-corr-001"

        # Check correlation tracking
        mock_add_corr.assert_called_once()
        mock_update_corr.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_with_dict_args(self, handler, mock_persistence_functions):
        """Test tool execution with dictionary arguments."""
        mock_add_corr, mock_update_corr = mock_persistence_functions

        tool_args = {
            "correlation_id": "dict-corr-001",
            "thought_id": "thought-001",
            "task_id": "task-001",
            "channel_id": "channel-001",
            "timeout_seconds": 60.0,
            "message": "test message",
        }

        result = await handler.execute_tool("echo", tool_args)

        assert result.tool_name == "echo"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.correlation_id == "dict-corr-001"

    @pytest.mark.asyncio
    async def test_execute_tool_failure(self, handler, mock_persistence_functions):
        """Test tool execution that returns failure."""
        tool_args = create_tool_execution_args()
        result = await handler.execute_tool("fail", tool_args)

        assert result.tool_name == "fail"
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.data == {"success": False, "error": "Intentional failure"}

    @pytest.mark.asyncio
    async def test_execute_tool_exception(self, handler, mock_persistence_functions):
        """Test tool execution that raises exception."""
        tool_args = create_tool_execution_args()
        result = await handler.execute_tool("error", tool_args)

        assert result.tool_name == "error"
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Test error" in result.error
        assert result.data is None

    @pytest.mark.asyncio
    async def test_execute_tool_no_registry(self, handler):
        """Test tool execution without registry."""
        handler.tool_registry = None
        tool_args = create_tool_execution_args()

        result = await handler.execute_tool("any_tool", tool_args)

        assert result.tool_name == "any_tool"
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.error == "Tool registry not configured"

    @pytest.mark.asyncio
    async def test_execute_tool_not_found(self, handler):
        """Test tool execution when tool not found."""
        tool_args = create_tool_execution_args()

        result = await handler.execute_tool("nonexistent", tool_args)

        assert result.tool_name == "nonexistent"
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_get_tool_result_found(self, handler):
        """Test retrieving tool result by correlation ID."""
        test_result = create_tool_execution_result(correlation_id="get-001")
        handler._tool_results["get-001"] = test_result

        result = await handler.get_tool_result("get-001", timeout=1)

        assert result == test_result
        assert "get-001" not in handler._tool_results  # Should be removed after retrieval

    @pytest.mark.asyncio
    async def test_get_tool_result_timeout(self, handler):
        """Test get_tool_result timeout."""
        result = await handler.get_tool_result("nonexistent", timeout=1)
        assert result is None

    def test_get_available_tools(self, handler):
        """Test getting list of available tools."""
        tools = handler.get_available_tools()
        assert "echo" in tools
        assert "fail" in tools
        assert "error" in tools
        assert len(tools) == 3

    def test_get_available_tools_no_registry(self, handler):
        """Test getting tools when no registry."""
        handler.tool_registry = None
        tools = handler.get_available_tools()
        assert tools == []

    def test_get_tool_info_basic(self, handler):
        """Test getting tool info for existing tool."""
        info = handler.get_tool_info("echo")

        assert info is not None
        assert info.name == "echo"
        assert info.description == "Discord tool: echo"
        assert info.category == "discord"

    def test_get_tool_info_with_description(self, handler):
        """Test getting tool info with full description."""
        # Add tool with description
        tool_desc = MockToolDescription(
            name="described_tool",
            description="A well-described tool",
            category="testing",
            parameters=[
                MockToolParameter(name="param1", param_type="string", description="First parameter", required=True),
                MockToolParameter(name="param2", param_type="number", default=42, required=False),
            ],
        )
        handler.tool_registry.add_tool("described_tool", create_successful_tool_handler(), description=tool_desc)

        info = handler.get_tool_info("described_tool")

        assert info is not None
        assert info.name == "described_tool"
        assert info.description == "A well-described tool"
        assert info.category == "testing"
        assert "param1" in info.parameters.properties
        assert "param2" in info.parameters.properties
        assert "param1" in info.parameters.required

    def test_get_tool_info_not_found(self, handler):
        """Test getting tool info for non-existent tool."""
        info = handler.get_tool_info("nonexistent")
        assert info is None

    def test_get_tool_info_no_registry(self, handler):
        """Test getting tool info without registry."""
        handler.tool_registry = None
        info = handler.get_tool_info("any_tool")
        assert info is None

    @pytest.mark.asyncio
    async def test_get_all_tool_info(self, handler):
        """Test getting info for all tools."""
        tools = await handler.get_all_tool_info()

        assert len(tools) == 3
        tool_names = [t.name for t in tools]
        assert "echo" in tool_names
        assert "fail" in tool_names
        assert "error" in tool_names

    def test_validate_tool_parameters_valid(self, handler):
        """Test parameter validation with valid parameters."""
        # Add tool with schema
        schema = MagicMock()
        schema.required = ["param1"]
        handler.tool_registry.add_tool("validated", create_successful_tool_handler(), schema=schema)

        # Test with ToolExecutionArgs
        args = create_tool_execution_args(tool_specific_params={"param1": "value"})
        assert handler.validate_tool_parameters("validated", args) is True

        # Test with dict
        assert handler.validate_tool_parameters("validated", {"param1": "value"}) is True

    def test_validate_tool_parameters_invalid(self, handler):
        """Test parameter validation with invalid parameters."""
        schema = MagicMock()
        schema.required = ["param1", "param2"]
        handler.tool_registry.add_tool("strict", create_successful_tool_handler(), schema=schema)

        args = create_tool_execution_args(tool_specific_params={"param1": "value"})  # Missing param2
        assert handler.validate_tool_parameters("strict", args) is False

    def test_validate_tool_parameters_no_schema(self, handler):
        """Test parameter validation when no schema."""
        handler.tool_registry.get_schema = MagicMock(return_value=None)
        args = create_tool_execution_args()
        assert handler.validate_tool_parameters("any_tool", args) is False

    def test_validate_tool_parameters_no_registry(self, handler):
        """Test parameter validation without registry."""
        handler.tool_registry = None
        args = create_tool_execution_args()
        assert handler.validate_tool_parameters("any_tool", args) is False

    def test_validate_tool_parameters_exception(self, handler):
        """Test parameter validation when exception occurs."""
        handler.tool_registry.get_schema = MagicMock(side_effect=RuntimeError("Schema error"))
        args = create_tool_execution_args()
        assert handler.validate_tool_parameters("any_tool", args) is False

    def test_clear_tool_results(self, handler):
        """Test clearing cached tool results."""
        handler._tool_results["result1"] = create_tool_execution_result()
        handler._tool_results["result2"] = create_tool_execution_result()

        assert len(handler._tool_results) == 2
        handler.clear_tool_results()
        assert len(handler._tool_results) == 0

    def test_get_cached_result_count(self, handler):
        """Test getting count of cached results."""
        assert handler.get_cached_result_count() == 0

        handler._tool_results["result1"] = create_tool_execution_result()
        assert handler.get_cached_result_count() == 1

        handler._tool_results["result2"] = create_tool_execution_result()
        assert handler.get_cached_result_count() == 2

    def test_remove_cached_result_exists(self, handler):
        """Test removing specific cached result that exists."""
        handler._tool_results["remove-me"] = create_tool_execution_result()

        assert handler.remove_cached_result("remove-me") is True
        assert "remove-me" not in handler._tool_results

    def test_remove_cached_result_not_exists(self, handler):
        """Test removing cached result that doesn't exist."""
        assert handler.remove_cached_result("nonexistent") is False

    @pytest.mark.asyncio
    async def test_correlation_tracking_full_flow(self, handler, mock_persistence_functions, mock_time_service):
        """Test full correlation tracking flow."""
        mock_add_corr, mock_update_corr = mock_persistence_functions

        # Execute tool
        tool_args = create_tool_execution_args(
            correlation_id="track-001", thought_id="thought-001", task_id="task-001", channel_id="channel-001"
        )

        result = await handler.execute_tool("echo", tool_args)

        # Verify correlation was tracked
        assert mock_add_corr.called
        assert mock_update_corr.called

        # Check the correlation that was added
        correlation_arg = mock_add_corr.call_args[0][0]
        assert correlation_arg.correlation_id == "track-001"
        assert correlation_arg.service_type == "discord"
        assert correlation_arg.action_type == "echo"

    def test_convert_to_typed_args_from_dict(self, handler):
        """Test converting dict to ToolExecutionArgs."""
        dict_args = {
            "correlation_id": "convert-001",
            "thought_id": "thought-001",
            "task_id": "task-001",
            "channel_id": "channel-001",
            "timeout_seconds": 45.0,
            "custom_param": "value",
            "another_param": 123,
        }

        typed = handler._convert_to_typed_args(dict_args)

        assert isinstance(typed, ToolExecutionArgs)
        assert str(typed.correlation_id) == "convert-001"
        assert typed.thought_id == "thought-001"
        assert typed.task_id == "task-001"
        assert typed.channel_id == "channel-001"
        assert typed.timeout_seconds == 45.0
        assert typed.tool_specific_params["custom_param"] == "value"
        assert typed.tool_specific_params["another_param"] == 123

    def test_convert_to_typed_args_already_typed(self, handler):
        """Test converting already typed ToolExecutionArgs."""
        original = create_tool_execution_args()
        typed = handler._convert_to_typed_args(original)
        assert typed is original  # Should return same object

    def test_create_error_result(self, handler):
        """Test creating error result."""
        result = handler._create_error_result("test_tool", "Error message", "error-001")

        assert result.tool_name == "test_tool"
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.data is None
        assert result.error == "Error message"
        assert result.correlation_id == "error-001"

    def test_create_error_result_no_correlation(self, handler):
        """Test creating error result without correlation ID."""
        result = handler._create_error_result("test_tool", "Error message")

        assert result.tool_name == "test_tool"
        assert result.error == "Error message"
        assert result.correlation_id is not None  # Should generate UUID

    def test_handle_tool_error(self, handler, mock_persistence_functions):
        """Test handling tool execution error."""
        mock_add_corr, mock_update_corr = mock_persistence_functions

        error = RuntimeError("Test exception")
        result = handler._handle_tool_error("error_tool", error, "error-corr-001")

        assert result.tool_name == "error_tool"
        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.data is None
        assert "Test exception" in result.error
        assert result.correlation_id == "error-corr-001"

        # Check correlation update
        mock_update_corr.assert_called_once()
        update_req = mock_update_corr.call_args[0][0]
        assert update_req.correlation_id == "error-corr-001"
        assert update_req.status == ServiceCorrelationStatus.FAILED

    def test_process_tool_result(self, handler, mock_persistence_functions):
        """Test processing tool result."""
        mock_add_corr, mock_update_corr = mock_persistence_functions

        result_dict = {"success": True, "data": {"key": "value"}, "other": "info"}

        result = handler._process_tool_result("process_tool", result_dict, "process-001", 123.45)

        assert result.tool_name == "process_tool"
        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data == result_dict
        assert result.error is None
        assert result.correlation_id == "process-001"

        # Check result was cached
        assert "process-001" in handler._tool_results
        assert handler._tool_results["process-001"] == result

        # Check correlation update
        mock_update_corr.assert_called_once()

    def test_track_correlation_start(self, handler, mock_persistence_functions, mock_time_service):
        """Test tracking correlation at start."""
        mock_add_corr, mock_update_corr = mock_persistence_functions

        tool_args = create_tool_execution_args(
            correlation_id="start-001",
            thought_id="thought-001",
            task_id="task-001",
            channel_id="channel-001",
            timeout_seconds=60.0,
            tool_specific_params={"param1": "value1", "param2": 123},
        )

        handler._track_correlation_start("test_tool", tool_args, "start-001")

        # Check add_correlation was called
        mock_add_corr.assert_called_once()
        correlation = mock_add_corr.call_args[0][0]

        assert correlation.correlation_id == "start-001"
        assert correlation.correlation_type == CorrelationType.SERVICE_INTERACTION
        assert correlation.service_type == "discord"
        assert correlation.handler_name == "DiscordAdapter"
        assert correlation.action_type == "test_tool"
        assert correlation.status == ServiceCorrelationStatus.PENDING

        # Check request data
        assert correlation.request_data.service_type == "discord"
        assert correlation.request_data.method_name == "test_tool"
        assert correlation.request_data.thought_id == "thought-001"
        assert correlation.request_data.task_id == "task-001"
        assert correlation.request_data.channel_id == "channel-001"
        assert correlation.request_data.timeout_seconds == 60.0
        assert "param1" in correlation.request_data.parameters
        assert "param2" in correlation.request_data.parameters

    @pytest.mark.asyncio
    async def test_execute_tool_with_object_result(self, handler, mock_persistence_functions):
        """Test tool execution when handler returns object instead of dict."""
        mock_add_corr, mock_update_corr = mock_persistence_functions

        # Create handler that returns object with __dict__
        class ResultObject:
            def __init__(self):
                self.success = True
                self.data = {"object": "result"}

        async def object_handler(args):
            return ResultObject()

        handler.tool_registry.add_tool("object_tool", object_handler)

        tool_args = create_tool_execution_args()
        result = await handler.execute_tool("object_tool", tool_args)

        assert result.success is True
        assert result.data["success"] is True
        assert result.data["data"]["object"] == "result"
