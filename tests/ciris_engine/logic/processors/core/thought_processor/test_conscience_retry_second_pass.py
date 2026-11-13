"""A conscience retry runs the chosen verb's second pass before its conscience check.

RATCHET Market 4, run 43453725789 on v2.21.0: every failed create_ticket call
("goal_description (str) is required", 7 calls in 6 episodes) was a TOOL picked
on a conscience retry and sent with parameters {}. ``_handle_conscience_retry``
re-ran action selection and went straight to the consciences; only the
recursive path ran the second pass (#1027).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.schemas.actions.parameters import PonderParams, SpeakParams, ToolParams
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

_EP = EpistemicData(entropy_level=0.1, coherence_level=0.9, uncertainty_acknowledged=True, reasoning_transparency=1.0)


def _tool(params: dict) -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name="create_ticket", parameters=params),
        rationale="file it",
    )


def _overridden() -> ConscienceApplicationResult:
    speak = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK, action_parameters=SpeakParams(content="hi"), rationale="r"
    )
    return ConscienceApplicationResult(
        original_action=speak,
        final_action=ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=["reconsider"]),
            rationale="override",
        ),
        overridden=True,
        override_reason="hallucinated constraint",
        epistemic_data=_EP,
    )


@pytest.mark.asyncio
async def test_retried_tool_gets_its_parameters_before_the_conscience() -> None:
    proc = ThoughtProcessor.__new__(ThoughtProcessor)
    proc._time_service = Mock(now=Mock(return_value=datetime.now(timezone.utc)))
    proc.dma_orchestrator = SimpleNamespace(run_action_selection=AsyncMock(return_value=_tool({})))
    proc._prepare_conscience_retry_context = Mock(return_value=SimpleNamespace())  # type: ignore[method-assign]
    filled = _tool({"goal_description": "renew the certificate"})
    proc._run_verb_second_pass = AsyncMock(return_value=filled)  # type: ignore[method-assign]

    checked: List[Any] = []

    async def conscience(thought_item: Any, action: Any, *_: Any, **__: Any) -> ConscienceApplicationResult:
        checked.append(action)
        return ConscienceApplicationResult(original_action=action, final_action=action, overridden=False, epistemic_data=_EP)

    proc._conscience_execution_step = AsyncMock(side_effect=conscience)  # type: ignore[method-assign]

    action, result = await proc._handle_conscience_retry(
        Mock(), Mock(thought_id="th_retry"), {}, {}, _overridden(), "default"
    )

    proc._run_verb_second_pass.assert_awaited_once()
    assert checked and checked[0].action_parameters.parameters == {"goal_description": "renew the certificate"}
    assert result.final_action.action_parameters.parameters == {"goal_description": "renew the certificate"}
