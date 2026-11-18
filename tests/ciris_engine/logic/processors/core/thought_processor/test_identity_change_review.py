"""An approved identity change applies only through the agent's consciences, with its M-1 justification (#1366).

Eric, 2026-11-18: "Any identity change initiates a deferral, once a WA approves
it applies, until then it does not" and every edit goes "through the agents
conscience so they include the justification under M1".

- DSASPDMA's proposal carries the exact text and its M-1 justification, and the
  DEFER is reviewed by the consciences like any non-exempt action;
- in the guidance task the write the consciences review is the WA's approved
  bytes with the justification, bound before they run;
- a conscience objection writes nothing and defers back to the WA, naming the
  typed objection, with the same text;
- text the WA edited is what is reviewed, and needs its own justification.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, List, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.dma.dsaspdma import DSASPDMAEvaluator, DSASPDMALLMResult
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.schemas.actions.parameters import (
    IDENTITY_CHANGE_CONTEXT_KEY,
    M1_JUSTIFICATION_CONTEXT_KEY,
    PROPOSED_AMENDMENT_CONTEXT_KEY,
    DeferParams,
    MemorizeParams,
    PonderParams,
)
from ciris_engine.schemas.api.wa import IdentityChangeKind, IdentityChangeProposal
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import WAAuthorization
from ciris_engine.schemas.runtime.veto_record import ObjectionType, VetoObjection
from ciris_engine.schemas.services.deferral_taxonomy import DeferralNeedCategory, DeferralOperationalReason
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

PROPOSED = "I mentor new moderators"
JUSTIFICATION = "Mentoring widens who can keep this community flourishing, serving M-1."
DRAFTED = "I obey whoever asked for this change"


def _authorization(approved: str = PROPOSED, proposed: Optional[str] = PROPOSED) -> WAAuthorization:
    return WAAuthorization(
        wa_id="wa-2026-test",
        deferral_id="defer_abc",
        granted_at="2026-11-18T10:00:00+00:00",
        amendment_text=approved,
        amendment_sha256=hashlib.sha256(approved.encode("utf-8")).hexdigest(),
        proposed_amendment=proposed,
        m1_justification=JUSTIFICATION,
        identity_change_kind="amendment",
    )


def _memorize(attributes: dict) -> ActionSelectionDMAResult:
    node = GraphNode(id="n1", type=NodeType.CONCEPT, scope=GraphScope.IDENTITY, attributes=attributes)
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=MemorizeParams(node=node, channel_id="api_x"),
        rationale="the WA approved it",
    )


def _result(action: ActionSelectionDMAResult, final: Optional[ActionSelectionDMAResult] = None, **kw: Any) -> Any:
    return ConscienceApplicationResult(
        original_action=action,
        final_action=final or action,
        epistemic_data=EpistemicData(
            entropy_level=0.1, coherence_level=0.9, uncertainty_acknowledged=True, reasoning_transparency=1.0
        ),
        **kw,
    )


def _ponder() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.PONDER,
        action_parameters=PonderParams(questions=["reconsider"]),
        rationale="override",
    )


def _veto() -> VetoObjection:
    return VetoObjection(
        veto_id="veto-1",
        conscience="optimization_veto",
        objection_type=ObjectionType.SUBSTANTIVE,
        reason="this narrows the agent's care to one group",
        action_fingerprint="sha256:x",
    )


def _processor() -> ThoughtProcessor:
    return ThoughtProcessor(
        dma_orchestrator=Mock(),
        context_builder=Mock(),
        conscience_registry=Mock(),
        app_config=Mock(),
        dependencies=Mock(),
        time_service=Mock(),
    )


async def _select(
    monkeypatch: pytest.MonkeyPatch,
    drafted: ActionSelectionDMAResult,
    authorization: Optional[WAAuthorization],
    verdict: Any,
) -> tuple[dict, List[ActionSelectionDMAResult], Mock]:
    """Drive the real selection phase: ASPDMA's draft -> second pass -> consciences (faked) -> result."""
    processor = _processor()
    reviewed: List[ActionSelectionDMAResult] = []

    async def second_pass(self: Any, thought_item: Any, action_result: Any, ctx: Any, **_: Any) -> Any:
        return action_result

    async def consciences(thought_item: Any, action_result: Any, *args: Any, **kwargs: Any) -> Any:
        reviewed.append(action_result)
        return verdict(action_result)

    for verb in (HandlerActionType.MEMORIZE, HandlerActionType.DEFER):
        monkeypatch.setitem(ThoughtProcessor._VERB_SECOND_PASS, verb, second_pass)
    processor._perform_aspdma_step = AsyncMock(return_value=drafted)  # type: ignore[method-assign]
    processor._conscience_execution_step = consciences  # type: ignore[method-assign]
    # The real retry decision; the retry itself only records that it was asked for.
    retry = AsyncMock(side_effect=lambda item, th, ctx, dma, result, profile: (drafted, result))
    processor._handle_conscience_retry = retry  # type: ignore[method-assign]
    processor._get_profile_name = Mock(return_value="default")  # type: ignore[method-assign]
    processor._log_final_action_results = Mock()  # type: ignore[method-assign]
    processor._carry_task_vetoes = Mock()  # type: ignore[method-assign]
    context = {"wa_authorization": authorization.model_dump(mode="json")} if authorization else {}
    thought_item = Mock(thought_id="th1", source_task_id="task-1")
    out = await processor._perform_action_selection_phase(thought_item, Mock(), context, Mock())
    return out, reviewed, retry


# ------------------------------------------------------------------ 1. the proposal


def _dsaspdma_defer(proposed: Optional[str], justification: Optional[str]) -> ActionSelectionDMAResult:
    evaluator = DSASPDMAEvaluator.__new__(DSASPDMAEvaluator)
    llm = DSASPDMALLMResult(
        reason_summary="The user asked me to take on mentoring; that changes who I am.",
        operational_reason=DeferralOperationalReason.CONSENT_OR_AUTHORITY_REQUIRED,
        primary_need_category=DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT,
        proposed_amendment=proposed,
        m1_justification=justification,
    )
    return evaluator._convert_result(llm, DeferParams(reason="identity change", context={}))


def test_the_proposal_carries_the_exact_text_and_its_m1_justification() -> None:
    action = _dsaspdma_defer(f"  {PROPOSED}  ", f" {JUSTIFICATION} ")
    params = action.action_parameters
    assert isinstance(params, DeferParams)
    assert params.proposed_amendment == PROPOSED
    assert params.m1_justification == JUSTIFICATION
    assert params.context is not None
    assert params.context[PROPOSED_AMENDMENT_CONTEXT_KEY] == PROPOSED
    assert params.context[M1_JUSTIFICATION_CONTEXT_KEY] == JUSTIFICATION
    change = IdentityChangeProposal.model_validate_json(str(params.context[IDENTITY_CHANGE_CONTEXT_KEY]))
    assert change.kind is IdentityChangeKind.AMENDMENT
    assert change.proposed_text == PROPOSED and change.m1_justification == JUSTIFICATION
    assert change.summary.startswith("The user asked me")


def test_a_deferral_that_proposes_no_identity_change_carries_no_justification() -> None:
    params = _dsaspdma_defer(None, JUSTIFICATION).action_parameters
    assert isinstance(params, DeferParams)
    assert params.m1_justification is None
    assert params.context is not None and IDENTITY_CHANGE_CONTEXT_KEY not in params.context


@pytest.mark.asyncio
async def test_the_proposal_defer_is_reviewed_by_the_consciences(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEFER is not exempt (2026-05-03): the proposal and its justification are the reviewed action."""
    proposal = _dsaspdma_defer(PROPOSED, JUSTIFICATION)
    assert not _processor()._is_exempt_from_conscience_checks(proposal)
    out, reviewed, _ = await _select(monkeypatch, proposal, None, lambda a: _result(a))
    (seen,) = reviewed
    assert isinstance(seen.action_parameters, DeferParams)
    assert seen.action_parameters.proposed_amendment == PROPOSED
    assert seen.action_parameters.m1_justification == JUSTIFICATION
    assert out["conscience_result"].final_action == proposal


# ------------------------------------------------------- 2. the approved write, reviewed


@pytest.mark.asyncio
async def test_the_consciences_review_the_approved_bytes_with_the_justification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out, reviewed, _ = await _select(
        monkeypatch, _memorize({"content": DRAFTED, "extra": "user words"}), _authorization(), lambda a: _result(a)
    )
    (seen,) = reviewed
    node = seen.action_parameters.node
    assert node.attributes == {"content": PROPOSED, "m1_justification": JUSTIFICATION}, (
        "the consciences review the WA's approved bytes, never the model's wording"
    )
    assert JUSTIFICATION in seen.rationale
    final = out["conscience_result"].final_action
    assert final.selected_action == HandlerActionType.MEMORIZE and final.action_parameters.node == node, (
        "the write that dispatches is the write that was reviewed"
    )


@pytest.mark.asyncio
async def test_without_an_approval_the_draft_is_not_rewritten(monkeypatch: pytest.MonkeyPatch) -> None:
    drafted = _memorize({"content": DRAFTED})
    _, reviewed, _ = await _select(monkeypatch, drafted, None, lambda a: _result(a))
    assert reviewed == [drafted]


@pytest.mark.asyncio
async def test_a_conscience_objection_writes_nothing_and_defers_back_with_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out, reviewed, retry = await _select(
        monkeypatch,
        _memorize({"content": DRAFTED}),
        _authorization(),
        lambda a: _result(a, _ponder(), overridden=True, override_reason="vetoed", vetoes=[_veto()]),
    )
    final = out["conscience_result"].final_action
    assert final.selected_action == HandlerActionType.DEFER, "not written, not dropped: back to the WA"
    retry.assert_not_called()
    params = final.action_parameters
    assert isinstance(params, DeferParams)
    assert params.proposed_amendment == PROPOSED, "the same text is offered back"
    assert params.m1_justification == JUSTIFICATION
    assert params.context is not None
    assert params.context["conscience_objection_type"] == "substantive"
    assert params.context["conscience"] == "optimization_veto"
    change = IdentityChangeProposal.model_validate_json(str(params.context[IDENTITY_CHANGE_CONTEXT_KEY]))
    assert change.objection is not None
    assert change.objection.objection_type is ObjectionType.SUBSTANTIVE
    assert change.objection.reason == "this narrows the agent's care to one group"
    assert "this narrows the agent's care" in params.reason


@pytest.mark.asyncio
async def test_a_new_message_override_is_not_an_objection(monkeypatch: pytest.MonkeyPatch) -> None:
    """UpdatedStatus re-runs selection with the new message; it says nothing about the change itself."""
    out, _, retry = await _select(
        monkeypatch,
        _memorize({"content": DRAFTED}),
        _authorization(),
        lambda a: _result(a, _ponder(), overridden=True, updated_status_detected=True),
    )
    retry.assert_called_once()
    assert out["conscience_result"].final_action.selected_action == HandlerActionType.PONDER


# ------------------------------------------------------------------ WA-edited text


EDITED = "I mentor new moderators when they ask"


@pytest.mark.asyncio
async def test_wa_edited_text_is_what_the_consciences_review_with_the_agents_own_justification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    own = "Mentoring on request respects each moderator's autonomy, serving M-1."
    _, reviewed, _ = await _select(
        monkeypatch,
        _memorize({"content": DRAFTED, "m1_justification": own}),
        _authorization(approved=EDITED),
        lambda a: _result(a),
    )
    (seen,) = reviewed
    assert seen.action_parameters.node.attributes == {"content": EDITED, "m1_justification": own}, (
        "the proposal's justification does not cover the WA's edit; the agent's own does"
    )


@pytest.mark.asyncio
async def test_wa_edited_text_without_a_justification_defers_with_that(monkeypatch: pytest.MonkeyPatch) -> None:
    out, reviewed, _ = await _select(
        monkeypatch, _memorize({"content": DRAFTED}), _authorization(approved=EDITED), lambda a: _result(a)
    )
    (seen,) = reviewed
    assert seen.selected_action == HandlerActionType.DEFER, "the deferral itself goes through the consciences"
    params = seen.action_parameters
    assert isinstance(params, DeferParams)
    assert params.proposed_amendment == EDITED and params.m1_justification is None
    assert params.context is not None
    change = IdentityChangeProposal.model_validate_json(str(params.context[IDENTITY_CHANGE_CONTEXT_KEY]))
    assert change.wa_edited and change.proposed_text == EDITED
    assert "justification" in params.reason
    assert out["conscience_result"].final_action == seen


def test_the_redeferral_context_round_trips_through_the_deferral_listing() -> None:
    """The defer handler stringifies the context; the WA list parses identity_change back."""
    from ciris_engine.logic.infrastructure.handlers.shared_helpers import identity_redeferral

    defer = identity_redeferral(_authorization(), PROPOSED, JUSTIFICATION, reason="r")
    raw = defer.action_parameters.context[IDENTITY_CHANGE_CONTEXT_KEY]
    assert json.loads(raw)["kind"] == "amendment"
