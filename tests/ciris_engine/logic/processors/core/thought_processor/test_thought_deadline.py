"""One deadline per pipeline pass (CIRISAgent#1186).

process_thought starts a Deadline of the budget's thought_budget_s on the
queue item; the DMA stage, the conscience stage and the conscience-retry pass
(ASPDMA + second conscience stage) all spend from that same deadline. A new
process_thought call -- e.g. a PONDER follow-up thought -- starts a new one.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.config import llm_budget
from ciris_engine.logic.config.llm_budget import Deadline
from ciris_engine.logic.processors.core.thought_processor.conscience_execution import ConscienceExecutionPhase
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.logic.conscience.registry import conscienceRegistry
from ciris_engine.schemas.actions.parameters import PonderParams, SpeakParams
from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus, EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def budget_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    table: dict[str, str] = {}
    monkeypatch.setattr(llm_budget, "get_env_var", lambda name, default=None: table.get(name, default))
    return table


def _item() -> ProcessingQueueItem:
    return ProcessingQueueItem(
        thought_id="th_deadline",
        source_task_id="task_deadline",
        thought_type=ThoughtType.STANDARD,
        content=ThoughtContent(text="hello"),
        thought_depth=0,
    )


def _speak() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="hello"),
        rationale="test",
    )


def _overridden() -> ConscienceApplicationResult:
    return ConscienceApplicationResult(
        original_action=_speak(),
        final_action=ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=["reconsider"]),
            rationale="conscience override",
        ),
        overridden=True,
        override_reason="entropy too high",
        epistemic_data=EpistemicData(
            entropy_level=0.8, coherence_level=0.5, uncertainty_acknowledged=True, reasoning_transparency=1.0
        ),
    )


def _bare_processor() -> ThoughtProcessor:
    proc = ThoughtProcessor.__new__(ThoughtProcessor)
    proc._time_service = Mock(now=Mock(return_value=datetime.now(timezone.utc)))
    return proc


@pytest.mark.asyncio
@pytest.mark.parametrize("env, budget", [({}, 190.0), ({"CIRIS_LLM_BUDGET_PROFILE": "local"}, 890.0)])
async def test_process_thought_starts_one_deadline_per_pass(budget_env, env, budget) -> None:
    budget_env.update(env)
    proc = _bare_processor()
    proc._initialize_correlation = Mock(return_value=Mock())  # type: ignore[method-assign]
    proc._fetch_and_validate_thought = AsyncMock(return_value=None)  # type: ignore[method-assign]
    item = _item()

    await proc.process_thought(item)
    first = item.deadline
    assert isinstance(first, Deadline)
    assert budget - 5 < first.remaining() <= budget

    # A later pass (a PONDER follow-up is a new thought and a new pass) gets a
    # fresh deadline; the previous pass's is not reused.
    await proc.process_thought(item)
    assert item.deadline is not first


@pytest.mark.asyncio
async def test_conscience_retry_spends_the_remainder_not_a_fresh_budget() -> None:
    clock = FakeClock()
    deadline = Deadline(190.0, clock=clock)
    item = _item()
    item.start_deadline(deadline)
    clock.now = 120.0  # DMAs + ASPDMA + the first conscience pass took 120s

    seen: List[Any] = []

    async def aspdma_retry(**kwargs: Any) -> ActionSelectionDMAResult:
        seen.append(("aspdma", kwargs["thought_item"].deadline, kwargs["thought_item"].deadline.remaining()))
        clock.now += 30.0
        return _speak()

    async def conscience_again(thought_item: Any, *_: Any, **__: Any) -> ConscienceApplicationResult:
        seen.append(("conscience", thought_item.deadline, thought_item.deadline.remaining()))
        return ConscienceApplicationResult(
            original_action=_speak(),
            final_action=_speak(),
            overridden=False,
            epistemic_data=EpistemicData(
                entropy_level=0.1, coherence_level=0.9, uncertainty_acknowledged=True, reasoning_transparency=1.0
            ),
        )

    proc = _bare_processor()
    proc.dma_orchestrator = SimpleNamespace(run_action_selection=AsyncMock(side_effect=aspdma_retry))
    proc._prepare_conscience_retry_context = Mock(return_value=SimpleNamespace())  # type: ignore[method-assign]
    proc._conscience_execution_step = AsyncMock(side_effect=conscience_again)  # type: ignore[method-assign]

    thought = Mock(thought_id="th_deadline")
    action, result = await proc._handle_conscience_retry(item, thought, {}, {}, _overridden(), "default")

    assert result.overridden is False
    assert [s[0] for s in seen] == ["aspdma", "conscience"]
    assert all(s[1] is deadline for s in seen), "the retry pass must use the thought's deadline, not a new one"
    assert seen[0][2] == pytest.approx(70.0)
    assert seen[1][2] == pytest.approx(40.0)


class _Recorder:
    def __init__(self) -> None:
        self.contexts: List[Any] = []

    async def check(self, action: Any, context: Any) -> ConscienceCheckResult:
        self.contexts.append(context)
        return ConscienceCheckResult(status=ConscienceStatus.PASSED, passed=True)


@pytest.mark.asyncio
async def test_conscience_stage_hands_the_thought_deadline_to_every_shard() -> None:
    step = ConscienceExecutionPhase._conscience_execution_step.__wrapped__.__wrapped__  # below the streaming envelope
    recorders = [_Recorder(), _Recorder()]
    registry = conscienceRegistry()
    for priority, (name, rec) in enumerate(zip(["entropy", "coherence"], recorders)):
        registry.register_conscience(name=name, conscience=rec, priority=priority)
    phase = ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)
    phase.conscience_registry = registry
    phase._describe_action = Mock(return_value="speak 'hello'")  # type: ignore[method-assign]

    item = _item()
    deadline = Deadline(100.0)
    item.start_deadline(deadline)
    await step(phase, item, _speak(), thought=None, dma_results=None, processing_context=None)

    assert all(r.contexts and r.contexts[0].deadline is deadline for r in recorders)


@pytest.mark.asyncio
async def test_conscience_stage_without_a_deadline_passes_none() -> None:
    """Callers outside process_thought (tests, tools) carry no deadline: the
    shards then run the static per-try x attempts."""
    step = ConscienceExecutionPhase._conscience_execution_step.__wrapped__.__wrapped__
    rec = _Recorder()
    registry = conscienceRegistry()
    registry.register_conscience(name="entropy", conscience=rec, priority=0)
    phase = ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)
    phase.conscience_registry = registry
    phase._describe_action = MagicMock(return_value="speak")  # type: ignore[method-assign]

    await step(phase, SimpleNamespace(thought_id="th_x"), _speak(), thought=None, dma_results=None, processing_context=None)
    assert rec.contexts[0].deadline is None
