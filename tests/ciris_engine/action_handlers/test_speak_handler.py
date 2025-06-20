import pytest
from unittest.mock import AsyncMock, MagicMock

from ciris_engine.action_handlers.speak_handler import SpeakHandler
from ciris_engine.schemas.action_params_v1 import SpeakParams
from ciris_engine.schemas.agent_core_schemas_v1 import Thought
from ciris_engine.schemas.dma_results_v1 import ActionSelectionResult
from ciris_engine.schemas.foundational_schemas_v1 import HandlerActionType, ThoughtStatus, ThoughtType
from ciris_engine.action_handlers.base_handler import ActionHandlerDependencies
from ciris_engine.registries.base import ServiceRegistry, Priority
from ciris_engine.message_buses import BusManager
from ciris_engine.schemas.graph_schemas_v1 import GraphNode
from ciris_engine.schemas.graph_schemas_v1 import NodeType, GraphScope
from tests.helpers import create_test_dispatch_context
from ciris_engine.utils.channel_utils import create_channel_context

@pytest.mark.asyncio
async def test_speak_handler_schema_driven(monkeypatch):
    service_registry = ServiceRegistry()
    bus_manager = BusManager(service_registry)
    
    # Mock the communication bus send_message method directly
    bus_manager.communication.send_message = AsyncMock(return_value=True)
    
    deps = ActionHandlerDependencies(bus_manager=bus_manager)
    handler = SpeakHandler(deps)

    action_result = ActionSelectionResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="Hello world!", channel_context=create_channel_context("123")),
        rationale="r",
    )
    thought = Thought(
        thought_id="t1",
        source_task_id="s1",
        thought_type=ThoughtType.STANDARD,
        status=ThoughtStatus.PENDING,
        created_at="2025-05-28T00:00:00Z",
        updated_at="2025-05-28T00:00:00Z",
        round_number=1,
        content="Say hi",
        context={},
        thought_depth=0,
        ponder_notes=None,
        parent_thought_id=None,
        final_action={}
    )

    update_thought = MagicMock()
    add_thought = MagicMock()
    add_correlation = MagicMock()
    get_task_by_id = MagicMock()
    get_task_by_id.return_value = MagicMock(description="Test task")
    monkeypatch.setattr("ciris_engine.persistence.update_thought_status", update_thought)
    monkeypatch.setattr("ciris_engine.persistence.add_thought", add_thought)
    monkeypatch.setattr("ciris_engine.persistence.add_correlation", add_correlation)
    monkeypatch.setattr("ciris_engine.persistence.get_task_by_id", get_task_by_id)

    dispatch_context = create_test_dispatch_context(channel_id="123")
    await handler.handle(action_result, thought, dispatch_context)

    # Check that send_message was called through the bus
    bus_manager.communication.send_message.assert_awaited_once()
    call_args = bus_manager.communication.send_message.call_args
    assert call_args[1]['channel_id'] == "123"
    assert call_args[1]['content'] == "Hello world!"
    assert call_args[1]['handler_name'] == 'SpeakHandler'
    update_thought.assert_called_once()
    assert update_thought.call_args.kwargs["status"] == ThoughtStatus.COMPLETED
    add_thought.assert_called_once()


@pytest.mark.asyncio
async def test_speak_handler_missing_params(monkeypatch):
    service_registry = ServiceRegistry()
    bus_manager = BusManager(service_registry)
    
    # Mock the communication bus send_message method directly
    bus_manager.communication.send_message = AsyncMock(return_value=True)
    
    deps = ActionHandlerDependencies(bus_manager=bus_manager)
    handler = SpeakHandler(deps)

    action_result = ActionSelectionResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters={},
        rationale="r",
    )
    thought = Thought(
        thought_id="t2",
        source_task_id="s2",
        thought_type=ThoughtType.STANDARD,
        status=ThoughtStatus.PENDING,
        created_at="2025-05-28T00:00:00Z",
        updated_at="2025-05-28T00:00:00Z",
        round_number=1,
        content="Say hi",
        context={},
        thought_depth=0,
        ponder_notes=None,
        parent_thought_id=None,
        final_action={},
    )

    update_thought = MagicMock()
    add_thought = MagicMock()
    monkeypatch.setattr("ciris_engine.persistence.update_thought_status", update_thought)
    monkeypatch.setattr("ciris_engine.persistence.add_thought", add_thought)

    dispatch_context = create_test_dispatch_context(channel_id="")
    await handler.handle(action_result, thought, dispatch_context)

    bus_manager.communication.send_message.assert_not_awaited()
    update_thought.assert_called_once()
    assert update_thought.call_args.kwargs["status"] == ThoughtStatus.FAILED
    add_thought.assert_called_once()
