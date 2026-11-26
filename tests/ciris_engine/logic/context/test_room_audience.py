"""What is learned in one room is recalled only there (CC 1.13.3.4, Eric 2026-11-20; 2.23.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.context.room_audience import ROOM_TAG_PREFIX, node_room, stamp_room, visible_in, visible_nodes
from ciris_engine.logic.handlers.memory.recall_handler import RecallHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.schemas.actions.parameters import RecallParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType

DispatchContext.model_rebuild()

DM = "discord_dm_42"
GROUP = "discord_guild_7_general"


def _typed(node_id: str, tags: List[str]) -> GraphNode:
    return GraphNode(
        id=node_id,
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(created_by="agent", content="the user's new address", tags=tags),
    )


def _dict(node_id: str, attrs: Dict[str, Any]) -> GraphNode:
    return GraphNode(id=node_id, type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes=attrs)


# ------------------------------------------------------------------ the stamp


def test_memorize_stamps_the_room_it_was_learned_in() -> None:
    node = stamp_room(_typed("n1", ["family"]), DM)
    assert node.attributes.tags == ["family", f"{ROOM_TAG_PREFIX}{DM}"]  # type: ignore[union-attr]
    assert node_room(node) == DM


def test_a_draft_cannot_claim_another_room() -> None:
    """The model's own room: tag is removed; only the engine's stamp remains."""
    node = stamp_room(_typed("n1", [f"{ROOM_TAG_PREFIX}{GROUP}"]), DM)
    assert node_room(node) == DM
    unstamped = stamp_room(_dict("n2", {"tags": [f"{ROOM_TAG_PREFIX}{GROUP}"], "content": "x"}), None)
    assert node_room(unstamped) is None


def test_dict_attributes_are_stamped_too() -> None:
    node = stamp_room(_dict("n1", {"content": "x"}), DM)
    assert isinstance(node.attributes, dict) and node.attributes["tags"] == [f"{ROOM_TAG_PREFIX}{DM}"]


# ------------------------------------------------------------------ visibility


def test_a_dm_memory_is_not_shown_in_a_group() -> None:
    dm_memory = stamp_room(_typed("n1", []), DM)
    assert visible_in(dm_memory, DM)
    assert not visible_in(dm_memory, GROUP)


def test_a_room_memory_is_not_shown_where_the_room_is_unknown() -> None:
    assert not visible_in(stamp_room(_typed("n1", []), DM), None)


def test_two_disagreeing_room_tags_are_shown_nowhere() -> None:
    forged = _typed("n1", [f"{ROOM_TAG_PREFIX}{DM}", f"{ROOM_TAG_PREFIX}{GROUP}"])
    assert not visible_in(forged, DM) and not visible_in(forged, GROUP)


def test_a_node_naming_no_room_passes() -> None:
    """The agent's own nodes, and nodes written before 2.23.2 (a recorded divergence until Agent 3.0)."""
    assert visible_in(_typed("n1", ["family"]), GROUP)
    assert [n.id for n in visible_nodes([_typed("a", []), stamp_room(_typed("b", []), DM)], GROUP)] == ["a"]


# ------------------------------------------------------------------ RECALL


def _dispatch(channel_id: str) -> DispatchContext:
    now = datetime.now(timezone.utc)
    return DispatchContext(
        channel_context=ChannelContext(channel_id=channel_id, channel_type="discord", created_at=now),
        author_id="user-1",
        author_name="User",
        origin_service="test",
        handler_name="RecallHandler",
        action_type=HandlerActionType.RECALL,
        task_id="task-1",
        thought_id="thought-1",
        source_task_id="task-1",
        event_summary="recall",
        event_timestamp=now.isoformat(),
    )


@pytest.mark.asyncio
async def test_recall_in_a_group_withholds_what_was_learned_in_a_dm(monkeypatch: pytest.MonkeyPatch) -> None:
    persistence = Mock()
    monkeypatch.setattr("ciris_engine.logic.handlers.memory.recall_handler.persistence", persistence)
    monkeypatch.setattr("ciris_engine.logic.infrastructure.handlers.base_handler.persistence", persistence)
    monkeypatch.setattr(
        "ciris_engine.logic.handlers.memory.recall_handler.fetch_connected_nodes", AsyncMock(return_value=[])
    )
    nodes = [stamp_room(_typed("from-dm", []), DM), stamp_room(_typed("from-group", []), GROUP), _typed("own", [])]
    bus = Mock()
    bus.memory = Mock(recall=AsyncMock(return_value=nodes), search=AsyncMock(return_value=nodes))
    handler = RecallHandler(
        ActionHandlerDependencies(bus_manager=bus, time_service=Mock(), secrets_service=None, shutdown_callback=None)
    )
    seen: Dict[str, str] = {}

    def _capture(**kwargs: Any) -> str:
        seen["content"] = kwargs["follow_up_content"]
        return "follow-up"

    monkeypatch.setattr(handler, "complete_thought_and_create_followup", _capture)
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.RECALL,
        action_parameters=RecallParams(query="address", limit=10),
        rationale="r",
        reasoning="r",
        evaluation_time_ms=1.0,
    )
    thought = Mock(spec=Thought)
    thought.thought_id = "thought-1"
    await handler.handle(result, thought, _dispatch(GROUP))
    assert "from-group" in seen["content"] and "own" in seen["content"]
    assert "from-dm" not in seen["content"]
