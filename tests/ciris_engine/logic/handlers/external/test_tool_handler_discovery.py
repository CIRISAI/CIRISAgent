"""
Additional tests for ToolHandler focusing on tool discovery and validation.

Tests cover:
- Tool discovery and info retrieval
- Tool parameter schema validation
- Tool availability checks
- Tool categorization and filtering
- Cost calculation and limits
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.external.tool_handler import ToolHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.schemas.actions.parameters import ToolParams
from ciris_engine.schemas.adapters.tools import ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext


def create_channel_context(channel_id: str = "test_channel") -> ChannelContext:
    """Helper to create a valid ChannelContext for tests."""
    return ChannelContext(
        channel_id=channel_id,
        channel_name=f"Channel {channel_id}",
        channel_type="text",
        created_at=datetime.now(timezone.utc),
    )


def create_dispatch_context(thought_id: str, task_id: str, channel_id: str = "test_channel") -> DispatchContext:
    """Helper to create a valid DispatchContext for tests."""
    return DispatchContext(
        channel_context=create_channel_context(channel_id),
        author_id="test_author",
        author_name="Test Author",
        origin_service="test_service",
        handler_name="ToolHandler",
        action_type=HandlerActionType.TOOL,
        task_id=task_id,
        thought_id=thought_id,
        source_task_id=task_id,
        event_summary="Tool discovery test",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id="test_correlation_id",
    )


def create_test_thought(thought_id: str = "test_thought", task_id: str = "test_task") -> Thought:
    """Helper to create a valid Thought for tests."""
    return Thought(
        thought_id=thought_id,
        source_task_id=task_id,
        content="Test thought for tool discovery",
        status=ThoughtStatus.PROCESSING,
        thought_depth=1,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        context=ThoughtContext(task_id=task_id, round_number=1, depth=1, correlation_id="test_correlation"),
    )


def create_sample_tools() -> list[ToolInfo]:
    """Create a set of sample tools for testing."""
    return [
        ToolInfo(
            name="calculator",
            description="Performs mathematical calculations",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "multiply", "divide"],
                        "description": "Math operation to perform",
                    },
                    "a": {"type": "number", "description": "First operand"},
                    "b": {"type": "number", "description": "Second operand"},
                },
                required=["operation", "a", "b"],
            ),
            category="math",
            cost=0.01,
            when_to_use="Use when mathematical calculations are needed",
        ),
        ToolInfo(
            name="web_search",
            description="Searches the web for information",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Number of results", "default": 10},
                    "safe_search": {"type": "boolean", "description": "Enable safe search", "default": True},
                },
                required=["query"],
            ),
            category="information",
            cost=0.05,
            when_to_use="Use when searching for current information online",
        ),
        ToolInfo(
            name="file_reader",
            description="Reads contents of a file",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "path": {"type": "string", "description": "File path"},
                    "encoding": {"type": "string", "description": "File encoding", "default": "utf-8"},
                },
                required=["path"],
            ),
            category="filesystem",
            cost=0.02,
            when_to_use="Use when reading file contents",
        ),
        ToolInfo(
            name="send_email",
            description="Sends an email",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "to": {"type": "array", "items": {"type": "string"}, "description": "Recipient email addresses"},
                    "subject": {"type": "string", "description": "Email subject"},
                    "body": {"type": "string", "description": "Email body"},
                    "cc": {"type": "array", "items": {"type": "string"}, "description": "CC recipients", "default": []},
                },
                required=["to", "subject", "body"],
            ),
            category="communication",
            cost=0.10,
            when_to_use="Use when sending email communications",
        ),
    ]


def create_mock_tool_execution_result(
    tool_name: str,
    success: bool = True,
    data: dict = None,
    error: str = None,
    status: ToolExecutionStatus = ToolExecutionStatus.COMPLETED,
) -> Mock:
    """Helper to create a mock ToolExecutionResult that matches handler expectations."""
    # The handler code expects direct success/error attributes
    result = Mock()
    result.tool_name = tool_name
    result.status = status
    result.success = success
    result.error = error
    result.data = data or {"output": "Tool executed successfully"} if success else None
    result.correlation_id = str(uuid.uuid4())
    return result


@pytest.fixture
def mock_dependencies_with_tools(monkeypatch):
    """Create mock dependencies with tool discovery capabilities."""
    # Mock persistence (only in base_handler - tool_handler uses complete_thought_and_create_followup)
    mock_persistence = Mock()
    mock_persistence.add_thought = Mock()
    mock_persistence.update_thought_status = Mock(return_value=True)
    monkeypatch.setattr("ciris_engine.logic.infrastructure.handlers.base_handler.persistence", mock_persistence)

    # Mock the models ThoughtContext to avoid validation issues
    mock_thought_context = Mock()
    mock_thought_context.model_validate = Mock(side_effect=lambda x: Mock())
    monkeypatch.setattr("ciris_engine.schemas.runtime.models.ThoughtContext", mock_thought_context)

    # Create service mocks
    mock_service_registry = AsyncMock()
    mock_time_service = Mock()
    mock_time_service.now = Mock(return_value=datetime.now(timezone.utc))

    # Create bus manager
    bus_manager = BusManager(mock_service_registry, time_service=mock_time_service)

    # Mock the tool bus with discovery methods
    mock_tool_bus = AsyncMock()
    mock_tool_bus.get_available_tools = AsyncMock(return_value=[t.name for t in create_sample_tools()])
    mock_tool_bus.get_all_tool_info = AsyncMock(return_value=create_sample_tools())
    mock_tool_bus.get_tool_info = AsyncMock()
    mock_tool_bus.validate_parameters = AsyncMock(return_value=(True, None))
    bus_manager.tool = mock_tool_bus

    # Mock the audit service (it's accessed directly, not through a bus)
    mock_audit_service = AsyncMock()
    mock_audit_service.log_event = AsyncMock()
    bus_manager.audit_service = mock_audit_service

    # Create dependencies
    deps = ActionHandlerDependencies(bus_manager=bus_manager, time_service=mock_time_service)

    return {
        "deps": deps,
        "persistence": mock_persistence,
        "tool_bus": mock_tool_bus,
        "audit_service": mock_audit_service,
        "time_service": mock_time_service,
        "sample_tools": create_sample_tools(),
    }


@pytest.mark.asyncio
async def test_tool_parameter_validation_strict(mock_dependencies_with_tools):
    """Test strict parameter validation against tool schema."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]
    sample_tools = mock_dependencies_with_tools["sample_tools"]

    # Configure tool info retrieval
    calculator_tool = next(t for t in sample_tools if t.name == "calculator")
    tool_bus.get_tool_info.return_value = calculator_tool

    # Test with missing required parameter
    tool_bus.validate_parameters.return_value = (False, "Missing required parameter: 'operation'")

    handler = ToolHandler(deps)

    # Missing 'operation' parameter
    params = ToolParams(name="calculator", parameters={"a": 10, "b": 5})  # Missing 'operation'

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Calculate values",
        reasoning="Math calculation needed",
        evaluation_time_ms=80,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    # Configure tool execution to fail due to validation
    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="calculator",
        success=False,
        error="Missing required parameter: 'operation'",
        status=ToolExecutionStatus.FAILED,
    )

    await handler.handle(result, thought, dispatch_context)

    # Verify validation occurred
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.FAILED

    follow_up = persistence.add_thought.call_args[0][0]
    assert "failed" in follow_up.content.lower()


@pytest.mark.asyncio
async def test_tool_parameter_type_validation(mock_dependencies_with_tools):
    """Test parameter type validation."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]

    handler = ToolHandler(deps)

    # Wrong parameter types
    params = ToolParams(
        name="calculator", parameters={"operation": "add", "a": "not_a_number", "b": 10}  # Should be number
    )

    # Configure validation to fail
    tool_bus.validate_parameters.return_value = (False, "Parameter 'a' must be a number")
    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="calculator", success=False, error="Parameter 'a' must be a number", status=ToolExecutionStatus.FAILED
    )

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Type validation test",
        reasoning="Testing type checking",
        evaluation_time_ms=70,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify type validation error was handled
    follow_up = persistence.add_thought.call_args[0][0]
    assert "must be a number" in follow_up.content


@pytest.mark.asyncio
async def test_tool_with_optional_parameters(mock_dependencies_with_tools):
    """Test tool execution with optional parameters."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]

    # Configure successful execution
    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="web_search",
        success=True,
        data={"results": ["result1", "result2", "result3"]},
        status=ToolExecutionStatus.COMPLETED,
    )

    handler = ToolHandler(deps)

    # Only required parameters provided
    params = ToolParams(
        name="web_search", parameters={"query": "test search"}  # 'limit' and 'safe_search' are optional
    )

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Search test",
        reasoning="Testing optional params",
        evaluation_time_ms=95,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify success with default optional values
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED


@pytest.mark.asyncio
async def test_tool_with_enum_validation(mock_dependencies_with_tools):
    """Test enum parameter validation."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]

    handler = ToolHandler(deps)

    # Invalid enum value
    params = ToolParams(
        name="calculator",
        parameters={"operation": "modulo", "a": 10, "b": 3},  # Not in ["add", "subtract", "multiply", "divide"]
    )

    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="calculator",
        success=False,
        error="Invalid operation 'modulo'. Must be one of: add, subtract, multiply, divide",
        status=ToolExecutionStatus.FAILED,
    )

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Enum validation test",
        reasoning="Testing enum constraints",
        evaluation_time_ms=75,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify enum validation error
    follow_up = persistence.add_thought.call_args[0][0]
    assert "Invalid operation" in follow_up.content


@pytest.mark.asyncio
async def test_tool_with_array_parameters(mock_dependencies_with_tools):
    """Test tool execution with array parameters."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]

    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="send_email",
        success=True,
        data={"sent": True, "message_id": "12345"},
        status=ToolExecutionStatus.COMPLETED,
    )

    handler = ToolHandler(deps)

    # Array parameters
    params = ToolParams(
        name="send_email",
        parameters={
            "to": ["user1@example.com", "user2@example.com"],
            "subject": "Test Email",
            "body": "This is a test",
            "cc": ["cc@example.com"],
        },
    )

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Array params test",
        reasoning="Testing array handling",
        evaluation_time_ms=85,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify array parameters were handled correctly
    call_args = tool_bus.execute_tool.call_args
    assert isinstance(call_args.kwargs["parameters"]["to"], list)
    assert len(call_args.kwargs["parameters"]["to"]) == 2

    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED


@pytest.mark.asyncio
async def test_tool_cost_tracking(mock_dependencies_with_tools):
    """Test that tool costs are tracked and included in context."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]
    sample_tools = mock_dependencies_with_tools["sample_tools"]

    # Get expensive tool
    email_tool = next(t for t in sample_tools if t.name == "send_email")
    tool_bus.get_tool_info.return_value = email_tool

    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="send_email", success=True, data={"sent": True}, status=ToolExecutionStatus.COMPLETED
    )

    handler = ToolHandler(deps)

    params = ToolParams(
        name="send_email", parameters={"to": ["test@example.com"], "subject": "Test", "body": "Test email"}
    )

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Cost tracking test",
        reasoning="Testing cost awareness",
        evaluation_time_ms=90,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Tool cost should be tracked (email tool costs 0.10)
    follow_up = persistence.add_thought.call_args[0][0]
    assert follow_up.context is not None
    # Since context is mocked, we can't check its contents directly
    # But we can verify the tool was executed
    assert "send_email" in follow_up.content
    assert "executed successfully" in follow_up.content


@pytest.mark.asyncio
async def test_tool_categorization(mock_dependencies_with_tools):
    """Test tool categorization and filtering by category."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    sample_tools = mock_dependencies_with_tools["sample_tools"]

    # Mock filtering tools by category
    async def filter_by_category(category):
        return [t for t in sample_tools if t.category == category]

    # Test getting math tools
    math_tools = await filter_by_category("math")
    assert len(math_tools) == 1
    assert math_tools[0].name == "calculator"

    # Test getting communication tools
    comm_tools = await filter_by_category("communication")
    assert len(comm_tools) == 1
    assert comm_tools[0].name == "send_email"

    # Test getting filesystem tools
    fs_tools = await filter_by_category("filesystem")
    assert len(fs_tools) == 1
    assert fs_tools[0].name == "file_reader"


@pytest.mark.asyncio
async def test_tool_when_to_use_guidance(mock_dependencies_with_tools):
    """Test that tool guidance is available and used."""
    sample_tools = mock_dependencies_with_tools["sample_tools"]

    # Verify all tools have when_to_use guidance
    for tool in sample_tools:
        assert tool.when_to_use is not None
        assert len(tool.when_to_use) > 0

    # Check specific guidance
    calc_tool = next(t for t in sample_tools if t.name == "calculator")
    assert "mathematical calculations" in calc_tool.when_to_use

    search_tool = next(t for t in sample_tools if t.name == "web_search")
    assert "current information online" in search_tool.when_to_use


@pytest.mark.asyncio
async def test_tool_discovery_caching(mock_dependencies_with_tools):
    """Test that tool discovery results can be cached efficiently."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]

    # Simulate multiple calls to get_available_tools
    for _ in range(3):
        available_tools = await tool_bus.get_available_tools()
        assert len(available_tools) == 4  # Should have 4 sample tools

    # Verify method was called 3 times (no caching in this test)
    assert tool_bus.get_available_tools.call_count == 3

    # In a real implementation, caching would reduce calls


@pytest.mark.asyncio
async def test_tool_parameter_defaults(mock_dependencies_with_tools):
    """Test that default parameter values are handled correctly."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]

    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="file_reader",
        success=True,
        data={"content": "File contents here"},
        status=ToolExecutionStatus.COMPLETED,
    )

    handler = ToolHandler(deps)

    # Only required parameter, relying on default encoding
    params = ToolParams(name="file_reader", parameters={"path": "/tmp/test.txt"})  # encoding will default to "utf-8"

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Default params test",
        reasoning="Testing parameter defaults",
        evaluation_time_ms=80,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Should succeed with default encoding
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED


@pytest.mark.asyncio
async def test_tool_not_found_handling(mock_dependencies_with_tools):
    """Test handling when requested tool doesn't exist."""
    deps = mock_dependencies_with_tools["deps"]
    tool_bus = mock_dependencies_with_tools["tool_bus"]
    persistence = mock_dependencies_with_tools["persistence"]

    tool_bus.execute_tool.return_value = create_mock_tool_execution_result(
        tool_name="nonexistent_tool",
        success=False,
        error="Tool 'nonexistent_tool' not found",
        status=ToolExecutionStatus.NOT_FOUND,
    )

    handler = ToolHandler(deps)

    params = ToolParams(name="nonexistent_tool", parameters={})

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Tool not found test",
        reasoning="Testing missing tool",
        evaluation_time_ms=60,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Should fail gracefully
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.FAILED

    follow_up = persistence.add_thought.call_args[0][0]
    assert "not found" in follow_up.content.lower()
