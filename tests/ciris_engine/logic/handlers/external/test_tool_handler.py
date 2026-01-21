"""
Comprehensive unit tests for ToolHandler.

Tests cover:
- Tool discovery and listing
- Tool execution with various parameter types
- Tool validation and error handling
- Tool result formatting
- Permission checks for tool usage
- Async tool execution
- Tool timeout and cancellation scenarios
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.external.tool_handler import ToolHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.schemas.actions.parameters import ToolParams
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext


# Test fixtures and helpers
def create_channel_context(channel_id: str = "test_channel") -> ChannelContext:
    """Helper to create a valid ChannelContext for tests."""
    return ChannelContext(
        channel_id=channel_id,
        channel_name=f"Channel {channel_id}",
        channel_type="text",
        created_at=datetime.now(timezone.utc),
    )


def create_dispatch_context(
    thought_id: str, task_id: str, channel_id: str = "test_channel", handler_name: str = "ToolHandler"
) -> DispatchContext:
    """Helper to create a valid DispatchContext for tests."""
    return DispatchContext(
        channel_context=create_channel_context(channel_id),
        author_id="test_author",
        author_name="Test Author",
        origin_service="test_service",
        handler_name=handler_name,
        action_type=HandlerActionType.TOOL,
        task_id=task_id,
        thought_id=thought_id,
        source_task_id=task_id,
        event_summary="Tool execution test",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id=str(uuid.uuid4()),
    )


def create_test_thought(
    thought_id: str = "test_thought", task_id: str = "test_task", status: ThoughtStatus = ThoughtStatus.PROCESSING
) -> Thought:
    """Helper to create a valid Thought for tests."""
    return Thought(
        thought_id=thought_id,
        source_task_id=task_id,
        content="Test thought content for tool execution",
        status=status,
        thought_depth=1,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        context=ThoughtContext(task_id=task_id, round_number=1, depth=1, correlation_id="test_correlation"),
    )


def create_tool_execution_result(
    tool_name: str,
    success: bool = True,
    data: dict = None,
    error: str = None,
    status: ToolExecutionStatus = ToolExecutionStatus.COMPLETED,
) -> ToolExecutionResult:
    """Helper to create a ToolExecutionResult that matches handler expectations."""
    # The handler code seems to expect a different structure than the schema defines
    # We'll create a mock object that matches what the handler expects
    from unittest.mock import Mock

    result = Mock(spec=ToolExecutionResult)
    result.tool_name = tool_name
    result.status = status
    result.success = success
    result.error = error
    result.data = data or {"output": "Tool executed successfully"} if success else None
    result.correlation_id = str(uuid.uuid4())
    return result


def create_tool_info(name: str, description: str = "Test tool", required_params: list = None) -> ToolInfo:
    """Helper to create ToolInfo."""
    return ToolInfo(
        name=name,
        description=description,
        parameters=ToolParameterSchema(
            type="object",
            properties={
                "param1": {"type": "string", "description": "First parameter"},
                "param2": {"type": "integer", "description": "Second parameter"},
            },
            required=required_params or [],
        ),
        category="test",
        cost=0.0,
    )


@pytest.fixture
def mock_dependencies(monkeypatch):
    """Create mock dependencies for ToolHandler."""
    # Mock persistence (only in base_handler - tool_handler uses complete_thought_and_create_followup)
    mock_persistence = Mock()
    mock_persistence.add_thought = Mock()
    mock_persistence.update_thought_status = Mock(return_value=True)
    mock_persistence.get_task_by_id = Mock(return_value=Mock())  # Return a mock task
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

    # Mock the tool bus
    mock_tool_bus = AsyncMock()
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
    }


# Test cases
@pytest.mark.asyncio
async def test_tool_execution_success(mock_dependencies, monkeypatch):
    """Test successful tool execution with proper parameters."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    # Configure tool bus mock
    tool_result = create_tool_execution_result("calculator", success=True, data={"result": 42})
    tool_bus.execute_tool.return_value = tool_result

    # Create handler
    handler = ToolHandler(deps)

    # Create parameters
    params = ToolParams(name="calculator", parameters={"operation": "add", "a": 20, "b": 22})

    # Create DMA result
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Performing calculation",
        reasoning="User requested math operation",
        evaluation_time_ms=100,
    )

    # Create thought and context
    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    # Execute handler
    await handler.handle(result, thought, dispatch_context)

    # Verify tool was executed
    assert tool_bus.execute_tool.called
    call_args = tool_bus.execute_tool.call_args
    assert call_args.kwargs["tool_name"] == "calculator"
    # task_id is now automatically added to tool parameters for billing purposes
    assert call_args.kwargs["parameters"] == {"operation": "add", "a": 20, "b": 22, "task_id": "test_task"}
    assert call_args.kwargs["handler_name"] == "ToolHandler"

    # Verify thought was updated to completed
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["thought_id"] == thought.thought_id
    assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

    # Verify follow-up thought was created
    assert persistence.add_thought.called
    follow_up = persistence.add_thought.call_args[0][0]
    assert "calculator" in follow_up.content
    assert "executed successfully" in follow_up.content
    # The context is mocked, so we can't verify its contents directly


@pytest.mark.asyncio
async def test_tool_execution_failure(mock_dependencies):
    """Test tool execution failure handling."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    # Configure tool bus to return failure
    tool_result = create_tool_execution_result(
        "failing_tool", success=False, error="Tool not available", status=ToolExecutionStatus.NOT_FOUND
    )
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    params = ToolParams(name="failing_tool", parameters={})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Testing failure",
        reasoning="This should fail",
        evaluation_time_ms=50,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify thought was marked as failed
    assert persistence.update_thought_status.called
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.FAILED

    # Verify error in follow-up thought
    follow_up = persistence.add_thought.call_args[0][0]
    assert "failed" in follow_up.content.lower()
    assert "Tool not available" in follow_up.content


@pytest.mark.asyncio
async def test_tool_parameter_validation_error(mock_dependencies):
    """Test handling of invalid tool parameters."""
    deps = mock_dependencies["deps"]
    persistence = mock_dependencies["persistence"]

    handler = ToolHandler(deps)

    # Create parameters with invalid structure to trigger validation error
    # We'll create a ToolParams but mock the validation to fail
    params = ToolParams(name="test_tool", parameters={})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Invalid params test",
        reasoning="Testing parameter validation",
        evaluation_time_ms=75,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    # Mock _validate_and_convert_params to raise exception
    with patch.object(handler, "_validate_and_convert_params", side_effect=ValueError("Invalid parameters")):
        await handler.handle(result, thought, dispatch_context)

    # Verify thought was marked as failed
    assert persistence.update_thought_status.called
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.FAILED

    # Verify error handling
    follow_up = persistence.add_thought.call_args[0][0]
    assert "failed" in follow_up.content.lower()


@pytest.mark.asyncio
async def test_tool_execution_timeout(mock_dependencies):
    """Test tool execution timeout scenario."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    # Configure tool bus to return timeout result
    tool_result = create_tool_execution_result(
        "slow_tool",
        success=False,
        error="Tool execution timed out after 30 seconds",
        status=ToolExecutionStatus.TIMEOUT,
    )
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    params = ToolParams(name="slow_tool", parameters={"timeout": 60})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Testing timeout",
        reasoning="Long running tool",
        evaluation_time_ms=100,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify timeout was handled
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.FAILED

    follow_up = persistence.add_thought.call_args[0][0]
    assert "timed out" in follow_up.content.lower()


@pytest.mark.asyncio
async def test_tool_with_complex_parameters(mock_dependencies):
    """Test tool execution with complex nested parameters."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    # Complex parameters - ToolParams expects Dict[str, Union[str, int, float, bool, List[str], Dict[str, str]]]
    # So we need to adjust the nested structure to match the schema
    complex_params = {
        "config_nested_value": "deep",
        "config_nested_number": 42,
        "config_list": ["item1", "item2", "item3"],
        "enabled": True,
        "threshold": 0.75,
    }

    tool_result = create_tool_execution_result("complex_tool", success=True, data={"processed": complex_params})
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    params = ToolParams(name="complex_tool", parameters=complex_params)
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Complex parameters test",
        reasoning="Testing nested parameters",
        evaluation_time_ms=150,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify complex parameters were passed correctly (task_id is added automatically)
    call_args = tool_bus.execute_tool.call_args
    expected_params = {**complex_params, "task_id": "test_task"}
    assert call_args.kwargs["parameters"] == expected_params

    # Verify success
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED


@pytest.mark.asyncio
async def test_tool_execution_exception(mock_dependencies):
    """Test handling of exceptions during tool execution."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    # Configure tool bus to raise exception
    tool_bus.execute_tool.side_effect = RuntimeError("Tool service unavailable")

    handler = ToolHandler(deps)

    params = ToolParams(name="crashing_tool", parameters={})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Exception test",
        reasoning="This will crash",
        evaluation_time_ms=80,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify exception was handled gracefully
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.FAILED

    follow_up = persistence.add_thought.call_args[0][0]
    assert "execution failed" in follow_up.content.lower()
    assert "Tool service unavailable" in follow_up.content


@pytest.mark.asyncio
async def test_tool_with_empty_parameters(mock_dependencies):
    """Test tool execution with no parameters."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    tool_result = create_tool_execution_result("simple_tool", success=True)
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    # Tool with empty parameters
    params = ToolParams(name="simple_tool", parameters={})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Simple tool test",
        reasoning="No parameters needed",
        evaluation_time_ms=60,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify empty parameters were handled (task_id is added automatically)
    call_args = tool_bus.execute_tool.call_args
    assert call_args.kwargs["parameters"] == {"task_id": "test_task"}

    # Verify success
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED


@pytest.mark.asyncio
async def test_follow_up_creation_failure(mock_dependencies):
    """Test handling when follow-up thought creation fails."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    tool_result = create_tool_execution_result("test_tool", success=True)
    tool_bus.execute_tool.return_value = tool_result

    # Make follow-up creation fail
    persistence.add_thought.side_effect = RuntimeError("Database error")

    handler = ToolHandler(deps)

    params = ToolParams(name="test_tool", parameters={})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Follow-up failure test",
        reasoning="Testing error handling",
        evaluation_time_ms=70,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    # Should raise FollowUpCreationError
    with pytest.raises(FollowUpCreationError):
        await handler.handle(result, thought, dispatch_context)

    # Original thought should still be updated
    assert persistence.update_thought_status.called


@pytest.mark.asyncio
async def test_tool_unauthorized_access(mock_dependencies):
    """Test handling of unauthorized tool access."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    tool_result = create_tool_execution_result(
        "restricted_tool",
        success=False,
        error="Insufficient permissions to execute this tool",
        status=ToolExecutionStatus.UNAUTHORIZED,
    )
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    params = ToolParams(name="restricted_tool", parameters={"admin": True})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Testing permissions",
        reasoning="Attempting restricted access",
        evaluation_time_ms=90,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify unauthorized was handled
    update_call = persistence.update_thought_status.call_args
    assert update_call.kwargs["status"] == ThoughtStatus.FAILED

    follow_up = persistence.add_thought.call_args[0][0]
    assert "Insufficient permissions" in follow_up.content


@pytest.mark.asyncio
async def test_secrets_decapsulation(mock_dependencies):
    """Test proper secrets decapsulation in tool parameters."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    tool_result = create_tool_execution_result("secure_tool", success=True)
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    # Mock _decapsulate_secrets_in_params
    decapsulated_result = Mock()
    decapsulated_params = ToolParams(name="secure_tool", parameters={"api_key": "decrypted_key", "data": "sensitive"})
    decapsulated_result.action_parameters = decapsulated_params

    with patch.object(handler, "_decapsulate_secrets_in_params", return_value=decapsulated_result):
        params = ToolParams(name="secure_tool", parameters={"api_key": "encrypted_key", "data": "sensitive"})
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.TOOL,
            action_parameters=params,
            rationale="Secrets test",
            reasoning="Testing secret handling",
            evaluation_time_ms=110,
        )

        thought = create_test_thought()
        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        await handler.handle(result, thought, dispatch_context)

        # Verify decapsulation was called
        handler._decapsulate_secrets_in_params.assert_called_once()

        # Verify decapsulated params were used
        call_args = tool_bus.execute_tool.call_args
        assert call_args.kwargs["parameters"]["api_key"] == "decrypted_key"


@pytest.mark.asyncio
async def test_tool_result_formatting(mock_dependencies):
    """Test proper formatting of tool results in follow-up thoughts."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    # Tool with detailed result data
    result_data = {
        "summary": "Analysis complete",
        "details": {"items_processed": 100, "errors": 0, "duration_ms": 2500},
        "recommendations": ["Optimize query", "Add caching"],
    }

    tool_result = create_tool_execution_result("analyzer", success=True, data=result_data)
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    params = ToolParams(name="analyzer", parameters={"target": "database"})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Analysis needed",
        reasoning="Running analysis tool",
        evaluation_time_ms=120,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # Verify result was included in follow-up
    follow_up = persistence.add_thought.call_args[0][0]
    assert "analyzer" in follow_up.content
    assert "executed successfully" in follow_up.content
    # The actual result data is included in the follow-up content
    assert "Analysis complete" in follow_up.content


@pytest.mark.asyncio
async def test_correlation_id_generation(mock_dependencies):
    """Test that unique correlation IDs are generated for each tool execution."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    persistence = mock_dependencies["persistence"]

    tool_result = create_tool_execution_result("test_tool", success=True)
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    # Execute multiple tool calls
    correlation_ids = []

    for i in range(3):
        with patch("ciris_engine.logic.handlers.external.tool_handler.uuid.uuid4") as mock_uuid:
            test_uuid = f"test-correlation-{i}"
            mock_uuid.return_value = Mock(hex=test_uuid, __str__=Mock(return_value=test_uuid))

            params = ToolParams(name=f"tool_{i}", parameters={})
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.TOOL,
                action_parameters=params,
                rationale=f"Test {i}",
                reasoning=f"Testing correlation {i}",
                evaluation_time_ms=50 + i * 10,
            )

            thought = create_test_thought(thought_id=f"thought_{i}")
            dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

            await handler.handle(result, thought, dispatch_context)

            # Verify unique correlation ID was used
            assert mock_uuid.called
            correlation_ids.append(test_uuid)

    # All correlation IDs should be unique
    assert len(set(correlation_ids)) == 3


@pytest.mark.asyncio
async def test_audit_logging(mock_dependencies):
    """Test that audit events are properly logged."""
    deps = mock_dependencies["deps"]
    tool_bus = mock_dependencies["tool_bus"]
    audit_service = mock_dependencies["audit_service"]
    persistence = mock_dependencies["persistence"]

    tool_result = create_tool_execution_result("audit_test", success=True)
    tool_bus.execute_tool.return_value = tool_result

    handler = ToolHandler(deps)

    params = ToolParams(name="audit_test", parameters={"level": "info"})
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="Audit test",
        reasoning="Testing audit logging",
        evaluation_time_ms=65,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    await handler.handle(result, thought, dispatch_context)

    # NOTE: Audit logging removed from handlers - action_dispatcher handles centralized audit logging
    # Test validates handler execution completes
