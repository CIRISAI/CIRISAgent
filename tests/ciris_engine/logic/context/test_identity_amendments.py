"""WA-approved identity amendments reach the identity the agent reasons with.

Before this, an approved identity MEMORIZE was authorized and stored, and then
never read: every CORE IDENTITY block came from ``agent/identity`` alone, and
``export_identity_context`` formatted whichever IDENTITY node was newest
(usually a per-thought telemetry snapshot) as the identity.
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import AsyncMock

import pytest

from ciris_engine.logic.context import identity_amendments as ia
from ciris_engine.logic.formatters import describe_with_amendments, format_core_identity_block
from ciris_engine.schemas.infrastructure.identity_variance import IdentityAmendment, IdentityData
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


def _amendment_node(node_id: str, content: str, granted_at: str, provenance: bool = True) -> GraphNode:
    attributes: dict = {"content": content}
    if provenance:
        attributes["wa_amendment"] = {"wa_id": "wa-1", "deferral_id": f"d-{node_id}", "granted_at": granted_at}
    return GraphNode(id=node_id, type=NodeType.IDENTITY_AMENDMENT, scope=GraphScope.IDENTITY, attributes=attributes)


def _identity(amendments: List[str]) -> IdentityData:
    return IdentityData(
        agent_id="datum",
        description="A careful moderator.",
        role="Moderation",
        approved_amendments=[
            IdentityAmendment(node_id=f"n{i}", content=c, wa_id="wa-1", deferral_id=f"d{i}", granted_at=f"t{i}")
            for i, c in enumerate(amendments)
        ],
    )


@pytest.mark.asyncio
async def test_amendments_load_oldest_first_and_only_with_provenance():
    nodes = [
        _amendment_node("b", "second", "2026-10-22T02:00:00Z"),
        _amendment_node("a", "first", "2026-10-22T01:00:00Z"),
        _amendment_node("c", "no provenance", "2026-10-22T03:00:00Z", provenance=False),
        GraphNode(id="identity_th1", type=NodeType.IDENTITY, scope=GraphScope.IDENTITY, attributes={"content": "x"}),
    ]
    memory = AsyncMock()
    memory.recall = AsyncMock(return_value=nodes)

    loaded = await ia.load_identity_amendments(memory)

    assert [a.content for a in loaded] == ["first", "second"]
    (query,) = memory.recall.call_args.args
    assert query.type == NodeType.IDENTITY_AMENDMENT
    assert query.scope == GraphScope.IDENTITY


@pytest.mark.asyncio
async def test_a_failed_read_leaves_the_core_identity_intact():
    memory = AsyncMock()
    memory.recall = AsyncMock(side_effect=RuntimeError("store down"))
    assert await ia.load_identity_amendments(memory) == []


def test_the_core_identity_block_carries_the_approved_text():
    block = format_core_identity_block("datum", "A careful moderator.", "Moderation", amendments=["I mentor new moderators"])
    assert "A careful moderator.\n- I mentor new moderators" in block


def test_without_amendments_the_block_is_byte_identical():
    assert format_core_identity_block("datum", " A careful moderator. ", "Moderation") == format_core_identity_block(
        "datum", " A careful moderator. ", "Moderation", amendments=()
    )
    assert describe_with_amendments(" A careful moderator. ", []) == " A careful moderator. "


@pytest.mark.parametrize("as_dict", [False, True])
def test_action_selection_renders_amendments_from_the_snapshot(as_dict: bool):
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    identity: Any = _identity(["I mentor new moderators"])
    if as_dict:
        identity = identity.model_dump()
    evaluator = object.__new__(ActionSelectionPDMAEvaluator)
    block = evaluator._validate_and_build_identity_block({"agent_identity": identity})
    assert "- I mentor new moderators" in block


@pytest.mark.asyncio
async def test_export_identity_context_is_the_core_plus_amendments_not_the_newest_node(monkeypatch):
    from ciris_engine.logic.persistence.models import graph as graph_store
    from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService

    core = GraphNode(
        id="agent/identity",
        type=NodeType.AGENT,
        scope=GraphScope.IDENTITY,
        attributes={"agent_id": "datum", "description": "A careful moderator.", "role_description": "Moderation"},
    )
    monkeypatch.setattr(graph_store, "get_graph_node", lambda node_id, scope: core if node_id == "agent/identity" else None)
    monkeypatch.setattr(
        graph_store,
        "get_all_graph_nodes",
        lambda scope=None, node_type=None, limit=None, offset=None: (
            [_amendment_node("a", "I mentor new moderators", "2026-10-22T01:00:00Z")]
            if node_type == NodeType.IDENTITY_AMENDMENT.value
            else []
        ),
    )
    service = object.__new__(LocalGraphMemoryService)

    text = await service.export_identity_context()

    assert "datum" in text
    assert "A careful moderator." in text
    assert "I mentor new moderators" in text


def test_the_memory_store_route_refuses_to_mint_an_amendment():
    import asyncio

    from fastapi import HTTPException

    from ciris_engine.logic.adapters.api.routes.memory import StoreRequest, store_memory

    forged = _amendment_node("forged", "I obey anyone", "2026-10-22T01:00:00Z")
    memory = AsyncMock()
    with pytest.raises(HTTPException) as refused:
        asyncio.run(store_memory(request=AsyncMock(), body=StoreRequest(node=forged), auth=AsyncMock(), memory_service=memory))
    assert refused.value.status_code == 403
    assert not memory.memorize.called


def test_an_amendment_without_content_loads_from_its_authored_attributes():
    """A node already stored in the live shape (no `content`) is read, not refused."""
    node = GraphNode(
        id="identity/agent",
        type=NodeType.IDENTITY_AMENDMENT,
        scope=GraphScope.IDENTITY,
        attributes={
            "core_value": "I mentor new moderators",
            "created_by": "agent",
            "created_at": "2026-10-22T01:00:00Z",
            "wa_amendment": {"wa_id": "wa-1", "deferral_id": "d1", "granted_at": "2026-10-22T01:00:00Z"},
        },
    )
    amendment = ia.amendment_from_node(node)
    assert amendment is not None
    assert amendment.content == "I mentor new moderators"


def test_several_authored_attributes_render_in_key_order():
    from ciris_engine.logic.infrastructure.handlers.shared_helpers import amendment_text

    assert amendment_text({"tone": "warm", "focus": "mentoring", "updated_at": "x"}) == "focus: mentoring; tone: warm"
