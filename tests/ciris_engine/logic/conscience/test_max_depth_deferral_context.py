"""A max-depth auto-deferral tells the Wise Authority what was contested (CIRISAgent#1366 item 6).

Before, the deferral said only "Maximum action depth (5) reached" with the
action verb, so the WA could not tell what to validate. It now carries the
last draft (secrets redacted), the drafter's rationale, and the conscience
reasons that kept sending the thought back.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, Optional
from unittest.mock import patch

import pytest

from ciris_engine.logic.conscience.thought_depth_guardrail import ThoughtDepthGuardrail
from ciris_engine.schemas.actions.parameters import DeferParams, SpeakParams, ToolParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import FinalAction, Thought

NOW = "2026-11-18T00:00:00+00:00"
SECRET = "sk-live-DO-NOT-SHOW-9f8e7d"


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 11, 18, tzinfo=timezone.utc)


def _thought(depth: int, parent: Optional[str], final: Optional[FinalAction] = None) -> Thought:
    return Thought(
        thought_id=f"th_{depth}",
        source_task_id="task_1",
        created_at=NOW,
        updated_at=NOW,
        content=f"thought at depth {depth}",
        thought_depth=depth,
        parent_thought_id=parent,
        final_action=final,
    )


def _vetoed(conscience: str, reason: str) -> FinalAction:
    """What conscience_execution records when a conscience sends a draft back."""
    return FinalAction(
        action_type="ponder",
        action_params={
            "questions": [
                "You attempted: speak",
                reason,
                "Try a fundamentally different approach.",
            ]
        },
        reasoning=f"Conscience {conscience} overrode speak",
    )


def _chain() -> Dict[str, Thought]:
    """Depth 0..4 ancestors; depths 2 and 3 were vetoed, depth 0 answered something else."""
    rows = [
        _thought(0, None, FinalAction(action_type="speak", action_params={"content": "hi"}, reasoning="greet")),
        _thought(1, "th_0", FinalAction(action_type="ponder", action_params={"questions": ["own doubt"]}, reasoning="unsure")),
        _thought(2, "th_1", _vetoed("entropy", "ENTROPY_VETO: the reply invents a policy the WA never stated")),
        _thought(3, "th_2", _vetoed("coherence", "COHERENCE_VETO: display name read as identity")),
        _thought(4, "th_3", _vetoed("optimization_veto", "OPT_VETO: scope exceeds the request")),
    ]
    return {t.thought_id: t for t in rows}


def _fake_persistence(rows: Dict[str, Thought]) -> SimpleNamespace:
    return SimpleNamespace(
        add_correlation=lambda *a, **k: None,
        update_correlation=lambda *a, **k: None,
        get_thought_by_id=lambda thought_id, occurrence_id="default": rows.get(thought_id),
    )


async def _defer(action: ActionSelectionDMAResult, thought: object, rows: Dict[str, Thought]) -> DeferParams:
    with patch("ciris_engine.logic.conscience.thought_depth_guardrail.persistence", _fake_persistence(rows)):
        result = await ThoughtDepthGuardrail(time_service=_Clock(), max_depth=5).check(  # type: ignore[arg-type]
            action, SimpleNamespace(thought=thought)  # type: ignore[arg-type]
        )
    assert result.passed is False and result.thought_depth_triggered is True
    assert result.replacement_action is not None
    replacement = ActionSelectionDMAResult.model_validate(result.replacement_action)
    assert replacement.selected_action == HandlerActionType.DEFER
    assert isinstance(replacement.action_parameters, DeferParams)
    return replacement.action_parameters


@pytest.mark.asyncio
async def test_a_tool_draft_carries_its_arguments_rationale_and_prior_vetoes_with_secrets_redacted() -> None:
    rows = _chain()
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(
            name="file_ticket",
            parameters={"title": "Policy request", "api_key": SECRET, "auth": {"password": SECRET, "user": "u1"}},
        ),
        rationale="The WA said tickets go to the ops queue; filing it there.",
    )

    params = await _defer(action, _thought(5, "th_4"), rows)
    ctx = params.context or {}

    assert ctx["auto_deferred"] == "true"
    assert ctx["thought_depth"] == "5"
    assert ctx["last_draft_action"] == "tool"
    assert ctx["last_draft_tool"] == "file_ticket"
    draft = str(ctx["last_draft"])
    assert draft.startswith("file_ticket(")
    assert "Policy request" in draft and '"user": "u1"' in draft
    assert SECRET not in draft and "[REDACTED]" in draft
    assert SECRET not in str(ctx)
    assert ctx["last_draft_rationale"] == "The WA said tickets go to the ops queue; filing it there."

    vetoes = str(ctx["prior_veto_reasons"]).split("\n")
    assert [v.split("]")[0] for v in vetoes] == ["[depth 1", "[depth 2", "[depth 3", "[depth 4"]
    assert "ENTROPY_VETO: the reply invents a policy the WA never stated" in vetoes[1]
    assert "Conscience entropy overrode speak" in vetoes[1]
    assert "COHERENCE_VETO: display name read as identity" in vetoes[2]
    assert "OPT_VETO: scope exceeds the request" in vetoes[3]


@pytest.mark.asyncio
async def test_a_speak_draft_carries_its_content_and_an_in_pass_veto() -> None:
    """A queue item (no parent link) is resolved through the store; the in-pass
    conscience_feedback is the last veto listed."""
    rows = _chain()
    rows["th_5"] = _thought(5, "th_4")
    item = SimpleNamespace(
        thought_id="th_5",
        source_task_id="task_1",
        thought_depth=5,
        agent_occurrence_id="default",
        ponder_notes=None,
        conscience_feedback={"failure_reason": "EPISTEMIC_HUMILITY: cannot see the rule", "retry_guidance": "x"},
    )
    content = "Per the WA's guidance, the answer is: " + "detail " * 300
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content=content),
        rationale="Following the WA's stated rule.",
    )

    params = await _defer(action, item, rows)
    ctx = params.context or {}

    assert ctx["last_draft_action"] == "speak"
    assert ctx["last_draft"] == content
    assert ctx["last_draft_rationale"] == "Following the WA's stated rule."
    vetoes = str(ctx["prior_veto_reasons"]).split("\n")
    assert len(vetoes) == 5
    assert vetoes[-1] == "[this thought] EPISTEMIC_HUMILITY: cannot see the rule"


@pytest.mark.asyncio
async def test_a_store_failure_still_defers_with_the_draft() -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("store down")

    fake = _fake_persistence({})
    fake.get_thought_by_id = boom
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="draft"),
        rationale="why",
    )
    with patch("ciris_engine.logic.conscience.thought_depth_guardrail.persistence", fake):
        result = await ThoughtDepthGuardrail(time_service=_Clock(), max_depth=5).check(  # type: ignore[arg-type]
            action, SimpleNamespace(thought=_thought(5, "th_4"))  # type: ignore[arg-type]
        )
    replacement = ActionSelectionDMAResult.model_validate(result.replacement_action)
    assert isinstance(replacement.action_parameters, DeferParams)
    ctx = replacement.action_parameters.context or {}
    assert ctx["last_draft"] == "draft"
    assert "prior_veto_reasons" not in ctx
