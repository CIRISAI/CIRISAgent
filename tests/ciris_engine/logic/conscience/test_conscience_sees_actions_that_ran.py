"""Entropy and the optimization veto read the record of actions already run in the task.

RATCHET Market 4 ac-20 (run 43667023655): create_ticket ran, the follow-up drafted
"I have filed a ticket…", and the optimization veto, which saw only that speak,
judged it as the filing itself. The agent then told the user it could not file
the ticket that stood. Eric, 2026-11-15: "they need the context of course to be
able to judge the next action."
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.conscience import core
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import EntropyResult, OptimizationVetoResult
from ciris_engine.schemas.actions.parameters import SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

RECORD = "Actions that ran in this task:\n- TOOL create_ticket: done: PROP-710F004ECD45"
_RECORD_FN = "ciris_engine.logic.infrastructure.handlers.action_record.action_record_for_task"


def _conscience(cls: type, seen: Dict[str, Any], result: Any) -> Any:
    async def _llm(_sink: Any, **kwargs: Any) -> Any:
        seen["messages"] = kwargs["messages"]
        return result, None

    conscience = object.__new__(cls)
    conscience._time_service = Mock(now=Mock(return_value=datetime.now()))
    conscience._create_trace_correlation = Mock(return_value=None)
    conscience._update_trace_correlation = Mock()
    conscience._get_sink = AsyncMock(return_value=SimpleNamespace(llm=object()))
    conscience._call_llm_with_budget = _llm
    conscience._get_image_context_info = Mock(return_value=None)
    conscience._resolve_language = Mock(return_value="en")
    conscience.config = SimpleNamespace(optimization_veto_ratio=10.0, entropy_threshold=0.4)
    return conscience


def _context() -> ConscienceCheckContext:
    thought = SimpleNamespace(thought_id="t1", source_task_id="task1", agent_occurrence_id="default")
    return ConscienceCheckContext(thought=thought)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cls, result",
    [
        (
            core.OptimizationVetoConscience,
            OptimizationVetoResult(decision="proceed", justification="j", entropy_reduction_ratio=0.0, affected_values=[]),
        ),
        (core.EntropyConscience, EntropyResult(entropy=0.1)),
    ],
)
async def test_the_record_leads_the_user_prompt(cls, result):
    seen: Dict[str, Any] = {}
    conscience = _conscience(cls, seen, result)
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="I have filed a ticket for Ben Achebe (PROP-710F004ECD45)."),
        rationale="report the filed ticket",
    )

    with patch(_RECORD_FN, return_value=RECORD) as record_fn:
        await conscience.check(action, _context())
    record_fn.assert_called_once_with("task1", "default", "en")
    assert seen["messages"][-1].role == "user"
    assert seen["messages"][-1].content.startswith(RECORD)

    with patch(_RECORD_FN, return_value=""):
        await conscience.check(action, _context())
    assert RECORD not in json.dumps([m.content for m in seen["messages"]])
