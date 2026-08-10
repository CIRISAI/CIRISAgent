"""MSASPDMA: the memorize second pass supplies conventions and does NOT heal.

The incident: the agent wrote a user fact to a freshly-minted UUID node. Nothing
queries such a node (user enrichment reads `user/{user_id}` and only that), so
the fact would have been stored and permanently unreachable — and the write also
carried a system-managed attribute, so it was refused and the agent looped.

Two properties matter and are asserted here:

  1. The evaluator HANDS OVER the conventions — the candidate nodes that already
     exist, the system-owned attribute list, and the nodes-vs-edges rule — so the
     agent can address the write correctly.

  2. It does NOT repair the agent's choice. A second pass that silently rewrote a
     bad node id would hide a model that does not know the conventions and leave
     it inventing ids everywhere MSASPDMA does not run. An unusable verdict
     becomes PONDER, not a patched write.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ciris_engine.logic.dma.msaspdma import MSASPDMAEvaluator, MSASPDMALLMResult
from ciris_engine.schemas.actions.parameters import MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

# The exact id from the incident.
ORPHANED_ID = "c6482c1b-4654-49fe-a97a-e5e037e9d0b5"
CANONICAL_ID = "user/alice"


def _memorize(node_id: str, **attrs: Any) -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=MemorizeParams(
            channel_id="api_x",
            node=GraphNode(
                id=node_id, type=NodeType.USER, scope=GraphScope.LOCAL, attributes=dict(attrs)
            ),
        ),
        rationale="user told me their favorite color",
    )


def _params(result: ActionSelectionDMAResult) -> MemorizeParams:
    assert isinstance(result.action_parameters, MemorizeParams)
    return result.action_parameters


def _evaluator() -> MSASPDMAEvaluator:
    return MSASPDMAEvaluator.__new__(MSASPDMAEvaluator)  # no service registry needed


# ------------------------------------------------------- handing over the rules


def test_candidate_nodes_offer_the_canonical_user_node() -> None:
    """Turning "invent an id" into "pick one" is the whole mechanism."""
    context = SimpleNamespace(
        system_snapshot=SimpleNamespace(
            user_profiles=[
                SimpleNamespace(user_id="alice", display_name="Alice", memorized_attributes={"pronouns": "they/them"})
            ],
            channel_id="api_x",
        )
    )
    candidates = MSASPDMAEvaluator.candidate_nodes_from_context(context)
    ids = [c.node_id for c in candidates]

    assert CANONICAL_ID in ids, f"the canonical user node was not offered: {ids}"
    assert "channel/api_x" in ids
    user = next(c for c in candidates if c.node_id == CANONICAL_ID)
    assert "pronouns" in user.existing_attributes, "the agent must see what is already stored"


def test_no_snapshot_yields_no_candidates_rather_than_raising() -> None:
    assert MSASPDMAEvaluator.candidate_nodes_from_context(None) == []
    assert MSASPDMAEvaluator.candidate_nodes_from_context(SimpleNamespace()) == []


def test_system_owned_attributes_come_from_the_guard_itself() -> None:
    """Guidance and enforcement must not drift apart."""
    from ciris_engine.logic.infrastructure.handlers.shared_helpers import MANAGED_USER_ATTRIBUTES

    exposed = MSASPDMAEvaluator.system_owned_attributes()
    assert exposed == MANAGED_USER_ATTRIBUTES
    assert "created_at" in exposed, "the attribute that caused the observed loop"
    assert exposed["created_at"], "each must carry a reason the agent can act on"


def test_the_guide_states_the_rules_the_agent_got_wrong() -> None:
    """The prompt is the deliverable; assert it says the load-bearing things."""
    import pathlib

    import yaml

    guide = yaml.safe_load(
        pathlib.Path("ciris_engine/logic/dma/prompts/msaspdma.yml").read_text()
    )["memory_guide"]

    assert "user/{user_id}" in guide, "must state the addressing convention"
    assert "UUID" in guide, "must warn against the exact mistake that was made"
    assert "cannot create an edge" in guide, "must resolve nodes-vs-edges"
    assert "DREAM" in guide, "must say where edges actually come from"
    assert "memorized_attributes" in guide, "must say how a stored fact comes back"


# ------------------------------------------------------------------- no healing


def test_a_corrected_node_is_the_MODEL_s_decision_not_a_rewrite() -> None:
    """MSASPDMA carries the model's choice through — it does not compute one."""
    result = _evaluator()._convert_result(
        MSASPDMALLMResult(
            final_action="MEMORIZE",
            node_id=CANONICAL_ID,
            node_type="user",
            node_scope="local",
            attributes={"favorite_color": "chartreuse"},
            reasoning="a bare UUID is unreadable; this belongs on the user node",
        ),
        original_params=_params(_memorize(ORPHANED_ID, favorite_color="chartreuse")),
    )

    assert result.selected_action == HandlerActionType.MEMORIZE
    assert _params(result).node.id == CANONICAL_ID
    assert _params(result).node.attributes == {"favorite_color": "chartreuse"}


def test_an_unusable_verdict_becomes_PONDER_not_a_patched_write() -> None:
    """The no-healing rule, at its sharpest.

    A MEMORIZE verdict with no node id cannot be repaired into a correct write —
    guessing the id here is exactly the silent-correction this design rejects.
    """
    result = _evaluator()._convert_result(
        MSASPDMALLMResult(final_action="MEMORIZE", node_id=None, reasoning="unsure"),
        original_params=_params(_memorize(ORPHANED_ID)),
    )

    assert result.selected_action == HandlerActionType.PONDER, (
        "an unusable second pass was patched into a write instead of reconsidered"
    )


def test_the_original_orphaned_node_is_never_silently_kept() -> None:
    """If the model does not confirm an address, we must not fall back to the bad one."""
    result = _evaluator()._convert_result(
        MSASPDMALLMResult(final_action="", reasoning=""),
        original_params=_params(_memorize(ORPHANED_ID)),
    )
    assert result.selected_action == HandlerActionType.PONDER
    assert not isinstance(result.action_parameters, MemorizeParams)


@pytest.mark.parametrize(
    "verdict,expected",
    [
        (MSASPDMALLMResult(final_action="SPEAK", message="Which profile?", reasoning="ambiguous"),
         HandlerActionType.SPEAK),
        (MSASPDMALLMResult(final_action="PONDER", questions=["Is this worth storing?"], reasoning="maybe not"),
         HandlerActionType.PONDER),
    ],
)
def test_it_can_switch_action_like_tsaspdma(verdict: MSASPDMALLMResult, expected: HandlerActionType) -> None:
    result = _evaluator()._convert_result(verdict, original_params=_params(_memorize(ORPHANED_ID)))
    assert result.selected_action == expected


def test_unknown_type_or_scope_falls_back_instead_of_raising() -> None:
    result = _evaluator()._convert_result(
        MSASPDMALLMResult(
            final_action="MEMORIZE", node_id=CANONICAL_ID, node_type="nonsense",
            node_scope="nonsense", attributes={"favorite_color": "chartreuse"}, reasoning="x",
        ),
        original_params=_params(_memorize(ORPHANED_ID)),
    )
    assert _params(result).node.type == NodeType.USER
    assert _params(result).node.scope == GraphScope.LOCAL
