"""No thought processing while a constitutional halt stands (CC 4.2.1.1, CIRISAgent#1231).

The round loop, the wakeup loop and the dream loop hold; operator resume and
single-step refuse; a shutdown proceeds without the closing dialogue. The node's
latch is mocked at `halt_latch._read_from_node`.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core import main_processor as main_processor_module
from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.processors.base import ProcessorMetrics, ProcessorServices
from ciris_engine.schemas.processors.results import ShutdownResult, WakeupResult, WorkResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState

pytestmark = pytest.mark.real_halt_latch


def _state(halted: bool, reading: AccordHaltReading, invocation_id: Any = None) -> AccordHaltState:
    return AccordHaltState(
        halted=halted, reading=reading, invocation_id=invocation_id, read_at=datetime.now(timezone.utc)
    )


HALTED = _state(True, AccordHaltReading.IN_EFFECT, "inv-hold")
NOT_HALTED = _state(False, AccordHaltReading.NOT_HALTED)


class Latch:
    def __init__(self, state: AccordHaltState) -> None:
        self.state = state

    async def read(self) -> AccordHaltState:
        return self.state


@pytest.fixture
def latch(monkeypatch):
    lt = Latch(HALTED)
    monkeypatch.setattr(halt_latch, "_read_from_node", lt.read)
    monkeypatch.setattr(halt_latch, "HALT_READ_CACHE_TTL_SECONDS", 0.0)
    monkeypatch.setattr(halt_latch, "HALT_HOLD_TICK_SECONDS", 0.01)
    return lt


@pytest.fixture
def llm():
    """An LLM the work processor calls when (and only when) a round runs."""
    service = Mock()
    service.__class__.__name__ = "MockLLMService"
    service.call_llm_structured = AsyncMock(return_value=None)
    return service


@pytest.fixture
def processor(llm):
    now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
    time_service = Mock(now=Mock(return_value=now), now_iso=Mock(return_value=now.isoformat()))
    config = Mock(spec=ConfigAccessor)
    config.get = Mock(return_value=None)
    services = ProcessorServices(
        time_service=time_service,
        telemetry_service=Mock(memorize_metric=AsyncMock()),
        memory_service=Mock(memorize=AsyncMock(), export_identity_context=AsyncMock(return_value="id")),
        identity_manager=Mock(get_identity=Mock(return_value={"name": "T"})),
        resource_monitor=Mock(spec=[]),
        llm_service=llm,
    )
    thought_processor = Mock(process_thought=AsyncMock(return_value=None))
    p = AgentProcessor(
        app_config=config,
        agent_identity=Mock(agent_id="a", name="T", purpose="p"),
        thought_processor=thought_processor,
        action_dispatcher=Mock(dispatch=AsyncMock()),
        services=services,
        startup_channel_id="c",
        time_service=time_service,
        runtime=None,
    )

    async def work_round(round_number):
        # What a real round does: pick up a thought, run it through the DMAs.
        await thought_processor.process_thought(Mock(thought_id="th-1"))
        await llm.call_llm_structured(messages=[], response_model=None)
        return WorkResult(tasks_processed=1, thoughts_processed=1, errors=0, duration_seconds=0.0)

    work = Mock(
        get_supported_states=Mock(return_value=[AgentState.WORK]),
        process=AsyncMock(side_effect=work_round),
        cleanup=Mock(return_value=True),
        get_metrics=Mock(return_value=ProcessorMetrics()),
        initialize=Mock(return_value=True),
    )
    wakeup = Mock(
        process=AsyncMock(
            return_value=WakeupResult(thoughts_processed=0, wakeup_complete=True, errors=0, duration_seconds=0.0)
        ),
        initialize=Mock(return_value=True),
        cleanup=Mock(return_value=True),
    )
    shutdown = Mock(
        process=AsyncMock(return_value=ShutdownResult(shutdown_ready=True, duration_seconds=0.0)),
        cleanup=Mock(return_value=True),
        shutdown_complete=False,
    )
    p.work_processor = work
    p.wakeup_processor = wakeup
    p.shutdown_processor = shutdown
    p.state_processors = {AgentState.WORK: work, AgentState.WAKEUP: wakeup, AgentState.SHUTDOWN: shutdown}
    p.state_manager.current_state = AgentState.WORK
    p._ensure_stop_event()
    return p


@pytest.fixture
def status_writes(monkeypatch) -> List[Any]:
    writes: List[Any] = []
    monkeypatch.setattr(
        main_processor_module.persistence, "update_thought_status", lambda *a, **k: writes.append((a, k)) or True
    )
    return writes


async def _round(p: AgentProcessor):
    return await p._process_single_round(0, 0, 5, None)


@pytest.mark.asyncio
async def test_no_thought_is_processed_and_no_llm_call_is_made_while_halted(
    latch, processor, llm, status_writes, monkeypatch
):
    monkeypatch.setattr(processor, "_handle_round_delay", AsyncMock(return_value=True))
    round_before = processor.current_round_number

    result = await _round(processor)

    assert result == (0, 0, False)
    processor.work_processor.process.assert_not_awaited()
    processor.thought_processor.process_thought.assert_not_awaited()
    llm.call_llm_structured.assert_not_awaited()
    processor.action_dispatcher.dispatch.assert_not_awaited()
    assert processor.current_round_number == round_before  # the round does not advance
    assert status_writes == []  # thoughts keep their status


@pytest.mark.asyncio
async def test_the_same_round_runs_when_no_halt_stands(latch, processor, llm, status_writes, monkeypatch):
    """Positive control: the hold is what stopped the round above."""
    monkeypatch.setattr(processor, "_handle_round_delay", AsyncMock(return_value=True))
    latch.state = NOT_HALTED
    await _round(processor)
    processor.work_processor.process.assert_awaited_once()
    llm.call_llm_structured.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_re_deliberates_from_saved_state(latch, processor, llm, monkeypatch):
    """Held rounds do nothing; the first round after the halt runs the work processor afresh."""
    monkeypatch.setattr(processor, "_handle_round_delay", AsyncMock(return_value=True))
    for _ in range(3):
        await _round(processor)
    processor.work_processor.process.assert_not_awaited()

    latch.state = _state(False, AccordHaltReading.LAPSED, "inv-hold")
    await _round(processor)
    processor.work_processor.process.assert_awaited_once()
    processor.thought_processor.process_thought.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_hold_is_not_the_operator_pause(latch, processor):
    """The halt holds a processor the operator never paused, and leaves the operator flag alone."""
    assert processor.is_paused() is False
    await _round(processor)
    processor.work_processor.process.assert_not_awaited()
    assert processor.is_paused() is False


@pytest.mark.asyncio
async def test_wakeup_loop_holds(latch, processor):
    processor.state_manager.current_state = AgentState.SHUTDOWN
    assert processor.state_manager.startup_target_state == AgentState.WAKEUP

    async def stop_soon():
        await asyncio.sleep(0.1)
        processor._stop_event.set()

    stopper = asyncio.create_task(stop_soon())
    await asyncio.wait_for(processor.start_processing(), timeout=5)
    await stopper

    processor.wakeup_processor.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_wakeup_loop_runs_once_the_halt_ends(latch, processor, monkeypatch):
    """Positive control for the wakeup hold."""
    processor.state_manager.current_state = AgentState.SHUTDOWN
    assert processor.state_manager.startup_target_state == AgentState.WAKEUP
    monkeypatch.setattr(processor, "_processing_loop", AsyncMock())
    monkeypatch.setattr(processor, "_schedule_initial_dream", AsyncMock())
    monkeypatch.setattr(processor, "_load_preload_tasks", Mock())

    async def release():
        await asyncio.sleep(0.05)
        latch.state = NOT_HALTED

    releaser = asyncio.create_task(release())
    await asyncio.wait_for(processor.start_processing(), timeout=5)
    await releaser
    processor.wakeup_processor.process.assert_awaited()


@pytest.mark.asyncio
async def test_operator_resume_refuses_while_halted(latch, processor):
    await processor.pause_processing()
    assert await processor.resume_processing() is False
    assert processor.is_paused() is True  # refused: nothing changed

    latch.state = NOT_HALTED
    assert await processor.resume_processing() is True


@pytest.mark.asyncio
async def test_single_step_refuses_while_halted(latch, processor):
    await processor.pause_processing()
    processor._pipeline_controller.execute_single_step_point = AsyncMock()
    with pytest.raises(RuntimeError, match="constitutional halt"):
        await processor.single_step()
    processor._pipeline_controller.execute_single_step_point.assert_not_awaited()


@pytest.mark.asyncio
async def test_control_service_refuses_resume_and_single_step(latch):
    from ciris_engine.logic.services.runtime.control_service.service import RuntimeControlService

    agent_processor = Mock(
        is_paused=Mock(return_value=True), resume_processing=AsyncMock(return_value=True), single_step=AsyncMock()
    )
    service = RuntimeControlService.__new__(RuntimeControlService)
    service.runtime = Mock(agent_processor=agent_processor)
    service._processor_status = "paused"
    service._record_event = AsyncMock()  # type: ignore[method-assign]
    service._now = Mock(return_value=datetime.now(timezone.utc))  # type: ignore[method-assign]
    from ciris_engine.schemas.services.core.runtime import ProcessorStatus

    service._processor_status = ProcessorStatus.PAUSED

    resumed = await service.resume_processing()
    stepped = await service.single_step()

    assert resumed.success is False and resumed.error == "accord_halt_in_effect:inv-hold"
    assert stepped.success is False and stepped.error == "accord_halt_in_effect:inv-hold"
    agent_processor.resume_processing.assert_not_awaited()
    agent_processor.single_step.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_under_the_halt_skips_the_closing_dialogue(latch):
    from ciris_engine.logic.processors.states.shutdown_processor import ShutdownProcessor

    shutdown = ShutdownProcessor.__new__(ShutdownProcessor)
    shutdown.shutdown_complete = False
    shutdown.shutdown_result = None
    shutdown._consent_evaluated = False
    shutdown.condition_evaluator = Mock(requires_consent=AsyncMock(return_value=(True, "always")))
    shutdown._create_shutdown_task = AsyncMock()  # type: ignore[method-assign]

    result = await shutdown._process_shutdown(0)

    assert result.shutdown_ready is True
    assert result.action == "shutdown_accepted"
    assert result.reason == "accord_halt_in_effect:inv-hold"
    shutdown.condition_evaluator.requires_consent.assert_not_awaited()
    shutdown._create_shutdown_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_shutdown_request_is_not_held(latch, processor, monkeypatch):
    """Anyone may turn the agent off: the round lets SHUTDOWN through to its processor."""
    monkeypatch.setattr(main_processor_module, "is_global_shutdown_requested", lambda: True)
    monkeypatch.setattr(main_processor_module, "get_global_shutdown_reason", lambda: "operator")
    monkeypatch.setattr(processor, "_handle_round_delay", AsyncMock(return_value=True))
    processor.state_manager.can_transition_to = AsyncMock(return_value=True)

    async def to_shutdown(target):
        processor.state_manager.current_state = target
        return True

    processor.state_manager.transition_to = AsyncMock(side_effect=to_shutdown)

    # The held round moves to SHUTDOWN without giving WORK one more round ...
    _, _, should_break = await _round(processor)
    assert should_break is False
    assert processor.state_manager.current_state == AgentState.SHUTDOWN
    processor.work_processor.process.assert_not_awaited()

    # ... and the next round runs the shutdown processor.
    _, _, should_break = await _round(processor)
    processor.shutdown_processor.process.assert_awaited_once()
    assert should_break is True
    processor.work_processor.process.assert_not_awaited()


@pytest.mark.asyncio
async def test_dream_loop_holds(latch):
    from ciris_engine.logic.processors.states.minimal_dream_processor import MinimalDreamProcessor

    dream = MinimalDreamProcessor.__new__(MinimalDreamProcessor)
    now = datetime.now(timezone.utc)
    dream.time_service = Mock(now=Mock(return_value=now))
    dream.process = AsyncMock()  # type: ignore[method-assign]
    dream._is_dream_complete = Mock(return_value=False)  # type: ignore[method-assign]
    dream.current_session = None
    dream.dream_metrics = {}
    dream._stop_event = asyncio.Event()

    async def stop_soon():
        await asyncio.sleep(0.1)
        dream._stop_event.set()

    stopper = asyncio.create_task(stop_soon())
    await asyncio.wait_for(dream._dream_loop(duration=3600), timeout=5)
    await stopper
    dream.process.assert_not_awaited()
