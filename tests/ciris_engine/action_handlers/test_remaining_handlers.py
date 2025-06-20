import pytest
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.action_handlers.forget_handler import ForgetHandler
from ciris_engine.action_handlers.recall_handler import RecallHandler
from ciris_engine.action_handlers.observe_handler import ObserveHandler
from ciris_engine.action_handlers.reject_handler import RejectHandler
from ciris_engine.action_handlers.task_complete_handler import TaskCompleteHandler
from ciris_engine.action_handlers.tool_handler import ToolHandler, ToolResult, ToolExecutionStatus
from ciris_engine.action_handlers.base_handler import ActionHandlerDependencies
from ciris_engine.message_buses.bus_manager import BusManager
from ciris_engine.schemas.action_params_v1 import (
    ForgetParams,
    RecallParams,
    ObserveParams,
    RejectParams,
    ToolParams,
)
from ciris_engine.schemas.agent_core_schemas_v1 import Thought, Task
from ciris_engine.schemas.dma_results_v1 import ActionSelectionResult
from ciris_engine.schemas.graph_schemas_v1 import GraphScope, GraphNode, NodeType
from ciris_engine.schemas.foundational_schemas_v1 import HandlerActionType, ThoughtStatus, TaskStatus, ThoughtType, DispatchContext, ServiceType
from tests.helpers import create_test_dispatch_context
from ciris_engine.schemas.memory_schemas_v1 import MemoryOpResult, MemoryOpStatus


DEFAULT_THOUGHT_KWARGS = dict(
    thought_id="t1",
    source_task_id="task1",
    thought_type=ThoughtType.STANDARD,
    status=ThoughtStatus.PENDING,
    created_at="2025-05-28T00:00:00Z",
    updated_at="2025-05-28T00:00:00Z",
    round_number=1,
    content="content",
    context={},
    thought_depth=0,
    ponder_notes=None,
    parent_thought_id=None,
    final_action={},
)


@pytest.mark.asyncio
async def test_forget_handler_schema_driven(monkeypatch):
    mock_service_registry = AsyncMock()
    bus_manager = BusManager(mock_service_registry)
    
    # Mock the memory bus
    mock_memory_bus = AsyncMock()
    mock_memory_bus.forget = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK))
    bus_manager.memory = mock_memory_bus
    
    deps = ActionHandlerDependencies(bus_manager=bus_manager)
    
    # Mock the persistence module functions
    add_thought_mock = MagicMock()
    monkeypatch.setattr('ciris_engine.action_handlers.forget_handler.persistence.add_thought', add_thought_mock)
    
    handler = ForgetHandler(deps)

    node = GraphNode(id="USER".lower(), type=NodeType.USER, scope=GraphScope.LOCAL)
    action_result = ActionSelectionResult.model_construct(
        selected_action=HandlerActionType.FORGET,
        action_parameters=ForgetParams(node=node, reason="No longer needed"),
        rationale="r",
    )
    thought = Thought(**DEFAULT_THOUGHT_KWARGS)

    context = create_test_dispatch_context(action_type=HandlerActionType.FORGET)
    await handler.handle(action_result, thought, context)

    mock_memory_bus.forget.assert_awaited_once()
    # Check that the call had the correct node and handler_name
    call_args = mock_memory_bus.forget.call_args
    assert call_args[1]['node'].id == "user"
    assert call_args[1]['node'].type == NodeType.USER
    assert call_args[1]['node'].scope == GraphScope.LOCAL
    assert call_args[1]['handler_name'] == 'ForgetHandler'
    add_thought_mock.assert_called_once()


@pytest.mark.asyncio
async def test_recall_handler_schema_driven(monkeypatch):
    mock_service_registry = AsyncMock()
    bus_manager = BusManager(mock_service_registry)
    
    # Mock the memory bus
    mock_memory_bus = AsyncMock()
    # Create a mock GraphNode to return from recall
    mock_node = GraphNode(
        id="test_node",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes={"foo": "bar"}
    )
    mock_memory_bus.recall = AsyncMock(return_value=[mock_node])
    bus_manager.memory = mock_memory_bus
    
    deps = ActionHandlerDependencies(bus_manager=bus_manager)
    
    # Mock the persistence module functions
    add_thought_mock = MagicMock()
    monkeypatch.setattr('ciris_engine.action_handlers.recall_handler.persistence.add_thought', add_thought_mock)
    
    handler = RecallHandler(deps)

    node = GraphNode(id="USER".lower(), type=NodeType.USER, scope=GraphScope.LOCAL)
    action_result = ActionSelectionResult.model_construct(
        selected_action=HandlerActionType.RECALL,
        action_parameters=RecallParams(node=node),
        rationale="r",
    )
    thought = Thought(**DEFAULT_THOUGHT_KWARGS)

    context = create_test_dispatch_context(action_type=HandlerActionType.RECALL)
    await handler.handle(action_result, thought, context)

    mock_memory_bus.recall.assert_awaited_once()
    # Check that the call had the correct recall_query and handler_name
    call_args = mock_memory_bus.recall.call_args
    assert call_args[1]['recall_query'].node_id == "user"
    assert call_args[1]['recall_query'].scope == GraphScope.LOCAL
    assert call_args[1]['handler_name'] == 'RecallHandler'
    add_thought_mock.assert_called_once()


@pytest.mark.asyncio
async def test_observe_handler_passive(monkeypatch):
    update_status = MagicMock()
    add_thought = MagicMock()
    monkeypatch.setattr("ciris_engine.persistence.update_thought_status", update_status)
    monkeypatch.setattr("ciris_engine.persistence.add_thought", add_thought)

    from ciris_engine.schemas.graph_schemas_v1 import GraphNode, NodeType, GraphScope
    params = ObserveParams(active=False, context={"source": "test"})  # Changed to passive
    action_result = ActionSelectionResult.model_construct(
        selected_action=HandlerActionType.OBSERVE,
        action_parameters=params,
        rationale="r",
    )
    thought = Thought(**DEFAULT_THOUGHT_KWARGS)
    mock_service_registry = AsyncMock()
    bus_manager = BusManager(mock_service_registry)
    handler = ObserveHandler(ActionHandlerDependencies(bus_manager=bus_manager))
    context = create_test_dispatch_context(action_type=HandlerActionType.OBSERVE)
    await handler.handle(action_result, thought, context)

    # For passive observe, it should just complete without fetching messages
    update_status.assert_called_once()
    # No follow-up thought should be created for passive observe
    add_thought.assert_not_called()


@pytest.mark.asyncio
async def test_reject_handler_schema_driven(monkeypatch):
    update_status = MagicMock()
    add_thought = MagicMock()
    update_task_status = MagicMock()
    monkeypatch.setattr("ciris_engine.persistence.update_thought_status", update_status)
    monkeypatch.setattr("ciris_engine.persistence.add_thought", add_thought)
    monkeypatch.setattr("ciris_engine.persistence.update_task_status", update_task_status)

    mock_service_registry = AsyncMock()
    bus_manager = BusManager(mock_service_registry)
    
    # Mock the communication bus
    mock_communication_bus = AsyncMock()
    mock_communication_bus.send_message = AsyncMock()
    bus_manager.communication = mock_communication_bus
    
    deps = ActionHandlerDependencies(bus_manager=bus_manager)
    handler = RejectHandler(deps)

    action_result = ActionSelectionResult.model_construct(
        selected_action=HandlerActionType.REJECT,
        action_parameters=RejectParams(reason="Not relevant to the task"),
        rationale="r",
    )
    thought = Thought(**DEFAULT_THOUGHT_KWARGS)

    context = create_test_dispatch_context(channel_id="chan", action_type=HandlerActionType.REJECT)
    await handler.handle(action_result, thought, context)

    # Check the communication bus send_message was called
    mock_communication_bus.send_message.assert_awaited_once()
    call_args = mock_communication_bus.send_message.call_args
    assert call_args[1]['channel_id'] == "chan"
    assert call_args[1]['content'] == "Unable to proceed: Not relevant to the task"
    assert call_args[1]['handler_name'] == 'RejectHandler'
    
    update_status.assert_called_once()
    # REJECT is a terminal action, so no follow-up thought should be created
    add_thought.assert_not_called()
    assert update_status.call_args.kwargs["status"] == ThoughtStatus.FAILED


@pytest.mark.asyncio
async def test_task_complete_handler_schema_driven(monkeypatch):
    update_thought_status = MagicMock()
    update_task_status = MagicMock(return_value=True)
    get_task_by_id = MagicMock(return_value=Task(
        task_id="task1",
        description="desc",
        status=TaskStatus.ACTIVE,
        priority=0,
        created_at="now",
        updated_at="now",
        context={},
        outcome={},
    ))
    monkeypatch.setattr("ciris_engine.persistence.update_thought_status", update_thought_status)
    monkeypatch.setattr("ciris_engine.persistence.update_task_status", update_task_status)
    monkeypatch.setattr("ciris_engine.persistence.get_task_by_id", get_task_by_id)

    mock_service_registry = AsyncMock()
    bus_manager = BusManager(mock_service_registry)
    deps = ActionHandlerDependencies(bus_manager=bus_manager)
    handler = TaskCompleteHandler(deps)

    action_result = ActionSelectionResult(
        selected_action=HandlerActionType.TASK_COMPLETE,
        action_parameters={},
        rationale="r",
    )
    thought = Thought(**DEFAULT_THOUGHT_KWARGS)

    context = create_test_dispatch_context(channel_id="chan", action_type=HandlerActionType.TASK_COMPLETE)
    await handler.handle(action_result, thought, context)

    update_thought_status.assert_called_once()
    update_task_status.assert_called_once_with("task1", TaskStatus.COMPLETED)


@pytest.mark.asyncio
async def test_tool_handler_schema_driven(monkeypatch):
    update_status = MagicMock()
    add_thought = MagicMock()
    monkeypatch.setattr("ciris_engine.persistence.update_thought_status", update_status)
    monkeypatch.setattr("ciris_engine.persistence.add_thought", add_thought)

    class DummyToolService:
        async def execute_tool(self, name, parameters):
            return {"ok": True}
        async def get_available_tools(self):
            return ["echo"]
        async def get_tool_result(self, cid, timeout=30.0):
            return {"result": "done"}
        async def validate_parameters(self, name, params):
            return True

    mock_service_registry = AsyncMock()
    bus_manager = BusManager(mock_service_registry)
    deps = ActionHandlerDependencies(bus_manager=bus_manager)
    audit_service = MagicMock()
    audit_service.log_action = AsyncMock()
    async def get_service(handler, service_type, **kwargs):
        if service_type == ServiceType.TOOL:
            return DummyToolService()
        if service_type == ServiceType.AUDIT:
            return audit_service
        return None
    deps.get_service = AsyncMock(side_effect=get_service)
    handler = ToolHandler(deps)

    params = ToolParams(name="test_tool", parameters={})
    action_result = ActionSelectionResult.model_construct(
        selected_action=HandlerActionType.TOOL,
        action_parameters=params,
        rationale="r",
    )
    thought = Thought(**DEFAULT_THOUGHT_KWARGS)

    context = create_test_dispatch_context(action_type=HandlerActionType.TOOL)
    await handler.handle(action_result, thought, context)

    update_status.assert_called_once()
    add_thought.assert_called_once()
