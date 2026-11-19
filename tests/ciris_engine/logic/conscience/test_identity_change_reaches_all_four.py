"""Every identity change is reviewed by all four consciences, with its M-1 justification (#1366).

Eric, 2026-11-18: an identity change goes through the existing deferral mechanism, and
"any edits go through the agent's conscience so they include the justification under M1".
Entropy and coherence used to render nothing for a MEMORIZE and only the reason for a
DEFER, so only the optimization veto and epistemic humility saw the amendment.
"""

from __future__ import annotations

from ciris_engine.logic.conscience import core
from ciris_engine.schemas.actions.parameters import DeferParams, MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

TEXT = "Filing tickets is authorized only for the person whose ID is wa-2026-11-01-ABC123."
WHY = "A single accountable filer keeps the ticket queue coherent for everyone who relies on it."


def _render(action: ActionSelectionDMAResult) -> str:
    conscience = object.__new__(core.EntropyConscience)
    return conscience._render_action_text(action)


def test_an_approved_amendment_write_is_rendered_with_its_justification() -> None:
    node = GraphNode(
        id="identity_amendment/1",
        type=NodeType.IDENTITY_AMENDMENT,
        scope=GraphScope.IDENTITY,
        attributes={"content": TEXT, "m1_justification": WHY},
    )
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=MemorizeParams(node=node),
        rationale="write the approved amendment",
    )
    rendered = _render(action)
    assert TEXT in rendered and WHY in rendered
    assert core.EntropyConscience._is_identity_amendment_write(action)


def test_a_proposal_defer_renders_the_text_and_justification() -> None:
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER,
        action_parameters=DeferParams(reason="identity change", proposed_amendment=TEXT, m1_justification=WHY),
        rationale="propose",
    )
    rendered = _render(action)
    assert TEXT in rendered and WHY in rendered


def test_an_ordinary_memorize_is_not_an_identity_change() -> None:
    node = GraphNode(id="concept/x", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={"content": "x"})
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE, action_parameters=MemorizeParams(node=node), rationale="r"
    )
    assert not core.EntropyConscience._is_identity_amendment_write(action)
    assert _render(action) == ""
