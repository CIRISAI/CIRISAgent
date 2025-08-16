"""Test that managed user attributes are protected from memorize operations."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler
from ciris_engine.schemas.actions import MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@pytest.mark.asyncio
async def test_managed_user_attributes_blocked():
    """Test that managed user attributes cannot be memorized."""

    # Create handler with mocked dependencies
    dependencies = MagicMock()
    dependencies.bus_manager = MagicMock()
    dependencies.bus_manager.memory = AsyncMock()
    dependencies.time_service = MagicMock()
    dependencies.time_service.now = MagicMock(return_value=datetime.now())

    handler = MemorizeHandler(dependencies)
    handler._audit_log = AsyncMock()
    handler.complete_thought_and_create_followup = MagicMock(return_value="followup_id")

    # Create a thought
    thought = Thought(
        thought_id="test_thought",
        source_task_id="test_task",
        content="Test memorize user attribute",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )

    # Test each managed attribute
    managed_attrs = [
        "last_seen",
        "last_interaction",
        "created_at",
        "first_seen",
        "trust_level",
        "is_wa",
        "permissions",
        "restrictions",
    ]

    for attr_name in managed_attrs:
        print(f"\nTesting managed attribute: {attr_name}")

        # Create a user node with a managed attribute
        node = GraphNode(
            id=f"user/123",
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={
                attr_name: (
                    "2024-09-16T[insert current time]Z"
                    if "seen" in attr_name or "created" in attr_name
                    else "test_value"
                )
            },
        )

        # Create memorize params
        params = MemorizeParams(node=node)

        # Create action result
        result = ActionSelectionDMAResult(
            selected_action="MEMORIZE", action_parameters=params, rationale="Test memorize"
        )

        # Create channel context
        channel_context = ChannelContext(channel_id="test_channel", channel_type="test", created_at=datetime.now())

        # Create dispatch context with all required fields
        context = DispatchContext(
            channel_context=channel_context,
            author_id="test_user",
            author_name="Test User",
            origin_service="test_service",
            handler_name="MemorizeHandler",
            action_type=HandlerActionType.MEMORIZE,
            thought_id=thought.thought_id,
            task_id=thought.source_task_id,
            source_task_id=thought.source_task_id,
            event_summary="Test memorize managed attribute",
            event_timestamp=datetime.now().isoformat(),
            wa_authorized=False,
        )

        # Call handler - should fail
        result = await handler.handle(result, thought, context)

        # Verify it was blocked
        assert handler.complete_thought_and_create_followup.called
        call_args = handler.complete_thought_and_create_followup.call_args

        # Check that it failed with the right message
        assert call_args.kwargs["status"] == ThoughtStatus.FAILED
        assert "MEMORIZE BLOCKED" in call_args.kwargs["follow_up_content"]
        assert f"managed user attribute '{attr_name}'" in call_args.kwargs["follow_up_content"]
        assert "Wise Authority assistance" in call_args.kwargs["follow_up_content"]

        # Verify audit log was called with blocked outcome
        audit_calls = [call for call in handler._audit_log.call_args_list if "blocked_managed_attribute" in str(call)]
        assert len(audit_calls) > 0

        print(f"✓ {attr_name} properly blocked")

        # Reset mocks for next iteration
        handler.complete_thought_and_create_followup.reset_mock()
        handler._audit_log.reset_mock()

    print("\n✅ All managed user attributes are properly protected!")
