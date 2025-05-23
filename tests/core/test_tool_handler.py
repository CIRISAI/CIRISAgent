import pytest
from unittest.mock import AsyncMock
from types import SimpleNamespace

from ciris_engine.core.agent_core_schemas import (
    Thought,
    ActionSelectionPDMAResult,
    ActParams,
)
from ciris_engine.core.foundational_schemas import HandlerActionType
from ciris_engine.core.action_handlers.tool_handler import ToolHandler
from ciris_engine.core.action_handlers.base_handler import ActionHandlerDependencies
from ciris_engine.core import persistence

class DummyTool:
    def __init__(self):
        self.execute_tool = AsyncMock()

@pytest.mark.asyncio
async def test_handle_tool(monkeypatch):
    t = Thought(thought_id="t", source_task_id="task", created_at="", updated_at="", round_created=0, content="")
    tool = DummyTool()
    deps = ActionHandlerDependencies(action_sink=SimpleNamespace(run_tool=tool.execute_tool))
    handler = ToolHandler(deps)
    added = []
    monkeypatch.setattr(persistence, "add_thought", lambda th: added.append(th))
    monkeypatch.setattr(persistence, "update_thought_status", lambda **k: None)
    params = ActParams(tool_name="x", arguments={"a": 1})
    result = ActionSelectionPDMAResult(
        context_summary_for_action_selection="c",
        action_alignment_check={},
        selected_handler_action=HandlerActionType.TOOL,
        action_parameters=params,
        action_selection_rationale="r",
        monitoring_for_selected_action="m",
    )
    await handler.handle(result, t, {})
    tool.execute_tool.assert_awaited_with("x", {"a": 1})
    assert added and added[0].related_thought_id == t.thought_id
