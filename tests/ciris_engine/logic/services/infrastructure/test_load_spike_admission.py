"""Admission sheds only enough load to stay under the critical thresholds.

Under a burst the agent used to slam shut: thoughts_active reached its CRITICAL
limit (the work loop's own batch size), SHED latched, every inbound message was
refused with a fixed Retry-After of 30 s, THROTTLE slowed the very loop that
drains active thoughts, and the hysteresis band kept admission closed after
capacity had freed. These tests pin the behaviour that replaced it, each with a
negative check of the old behaviour.
"""

import os
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.processors.states.work_processor import WorkProcessor
from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceMonitorService
from ciris_engine.logic.services.infrastructure.resource_monitor import service as rm_service
from ciris_engine.logic.services.infrastructure.resource_monitor.pressure import (
    MIN_RETRY_AFTER_SECONDS,
    SHED_RETRY_AFTER_SECONDS,
    UNMEASURED_RETRY_AFTER_SECONDS,
    ThoughtAdmission,
    actions_for_level,
    pressure_gate_of,
)
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.services.resources_core import (
    MemoryReleaseResult,
    PressureLevel,
    ResourceAction,
    ResourceBudget,
    ResourceLimit,
)


def _fake_release(trigger: str) -> MemoryReleaseResult:
    return MemoryReleaseResult(
        trigger=trigger,
        platform_call="malloc_trim",
        rss_before_mb=0,
        rss_after_mb=0,
        reclaimed_mb=0,
        gc_collected=0,
        duration_ms=0,
    )


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setattr(rm_service, "_release_process_memory", _fake_release)
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    m = ResourceMonitorService(budget=ResourceBudget(), db_path=db_path, time_service=TimeService())
    m._cpu_history.extend([0.0] * (m._cpu_history.maxlen or 0))
    yield m
    os.unlink(db_path)


async def _sample(monitor: ResourceMonitorService, thoughts: int) -> None:
    monitor.snapshot.thoughts_active = thoughts
    await monitor._check_limits()


def _gate(monitor):
    gate = pressure_gate_of(monitor)
    assert gate is not None
    return gate


def _round_delay(monitor) -> float:
    fake = SimpleNamespace(
        app_config=SimpleNamespace(mock_llm=False), services=SimpleNamespace(resource_monitor=monitor)
    )
    return AgentProcessor._calculate_round_delay(fake, AgentState.WORK)


# --------------------------------------------------------------------------- #
# THROTTLE does not apply to thoughts_active
# --------------------------------------------------------------------------- #


def test_thresholds_are_unchanged():
    limit = ResourceBudget().thoughts_active
    assert (limit.warning, limit.critical, limit.limit, limit.action) == (40, 48, 50, ResourceAction.SHED)
    assert limit.throttle_relieves is False
    assert ResourceBudget().cpu_percent.throttle_relieves is True


def test_thoughts_active_ladder_has_no_throttle():
    limit = ResourceBudget().thoughts_active
    assert actions_for_level(PressureLevel.HIGH, limit) == []
    assert actions_for_level(PressureLevel.CRITICAL, limit) == [ResourceAction.SHED]
    # negative: a resource THROTTLE does relieve keeps the rung
    relieved = limit.model_copy(update={"throttle_relieves": True})
    assert actions_for_level(PressureLevel.HIGH, relieved) == [ResourceAction.THROTTLE]


@pytest.mark.asyncio
async def test_high_thoughts_active_does_not_slow_the_loop(monitor):
    base = _round_delay(monitor)
    await _sample(monitor, 49)  # HIGH
    assert monitor.get_pressure_levels()["thoughts_active"] == PressureLevel.HIGH
    assert not _gate(monitor).is_active(ResourceAction.THROTTLE)
    assert _round_delay(monitor) == base
    await _sample(monitor, 55)  # CRITICAL: SHED, still no THROTTLE
    assert _gate(monitor).resources(ResourceAction.SHED) == ["thoughts_active"]
    assert not _gate(monitor).is_active(ResourceAction.THROTTLE)
    assert _round_delay(monitor) == base


@pytest.mark.asyncio
async def test_cpu_still_throttles(monitor):
    base = _round_delay(monitor)
    monitor.snapshot.cpu_average_1m = 76  # HIGH
    await monitor._check_limits()
    assert _gate(monitor).resources(ResourceAction.THROTTLE) == ["cpu_percent"]
    assert _round_delay(monitor) > base


# --------------------------------------------------------------------------- #
# Live admission: admit below the ceiling, refuse only the excess
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_admits_up_to_the_ceiling_and_refuses_only_the_excess(monitor):
    gate = _gate(monitor)
    await _sample(monitor, 46)
    assert gate.admission.ceiling == 49  # one under CRITICAL (limit 50)

    decisions = [gate.admit_intake() for _ in range(5)]
    assert [d.admitted for d in decisions] == [True, True, True, False, False]
    assert decisions[3].shed_resources == ["thoughts_active"]
    assert gate.admission.estimate == 49  # never past the ceiling, never CRITICAL

    # admitted intakes settle into created thoughts; the estimate holds until the next sample
    for _ in range(3):
        gate.settle_intake(True)
    assert gate.admission.estimate == 49
    assert not gate.admit_intake().admitted

    # the work loop drained ten: admission reopens at once for exactly that many
    await _sample(monitor, 39)
    assert [gate.admit_intake().admitted for _ in range(11)] == [True] * 10 + [False]


@pytest.mark.asyncio
async def test_an_intake_that_creates_no_thought_frees_its_slot(monitor):
    gate = _gate(monitor)
    await _sample(monitor, 48)
    assert gate.admit_intake().admitted
    assert not gate.admit_intake().admitted
    gate.settle_intake(False)  # filtered out / failed before a thought existed
    assert gate.admit_intake().admitted


@pytest.mark.asyncio
async def test_hysteresis_does_not_hold_admission_closed(monitor):
    gate = _gate(monitor)
    await _sample(monitor, 50)  # CRITICAL -> SHED latched
    assert not gate.admit_intake().admitted

    await _sample(monitor, 48)  # still CRITICAL by hysteresis (lifts below 48)...
    assert monitor.get_pressure_levels()["thoughts_active"] == PressureLevel.CRITICAL
    assert gate.is_active(ResourceAction.SHED)
    # ...but there is headroom under the ceiling, so the next message is admitted
    assert gate.admit_intake().admitted


@pytest.mark.asyncio
async def test_another_resources_shed_still_closes_admission_outright(monitor):
    gate = _gate(monitor)
    await _sample(monitor, 0)
    monitor.snapshot.memory_mb = 5000  # memory CRITICAL -> SHED
    await monitor._check_limits()
    decision = gate.admit_intake()
    assert not decision.admitted
    assert decision.shed_resources == ["memory_mb"]
    assert decision.retry_after_seconds == SHED_RETRY_AFTER_SECONDS  # no drain measure for memory
    assert gate.activation_headroom() == 0


@pytest.mark.asyncio
async def test_before_the_first_sample_only_the_latch_decides(monitor):
    gate = _gate(monitor)
    assert gate.admission.headroom() is None
    assert gate.admit_intake().admitted
    assert gate.activation_headroom() is None


# --------------------------------------------------------------------------- #
# Retry-After from the measured drain rate
# --------------------------------------------------------------------------- #


def _admission(estimate: int, ceiling: int = 49) -> ThoughtAdmission:
    adm = ThoughtAdmission()
    adm.observe(estimate, ResourceLimit(limit=ceiling + 1, warning=40, critical=48))
    return adm


def test_retry_after_is_unmeasured_until_two_rounds_finish():
    adm = _admission(49)
    assert adm.retry_after() == UNMEASURED_RETRY_AFTER_SECONDS
    adm.note_round(50, now=100.0)  # first round: no period yet
    assert adm.retry_after() == UNMEASURED_RETRY_AFTER_SECONDS


def test_retry_after_is_the_time_to_drain_the_excess():
    adm = _admission(49)
    adm.note_round(50, now=100.0)
    adm.note_round(50, now=110.0)  # 5 thoughts/s
    assert adm.drain_per_second == pytest.approx(5.0)
    assert adm.retry_after(now=200.0) == 1  # excess 1 -> 0.2 s, bounded below at 1
    adm.observe(68, ResourceLimit(limit=50, warning=40, critical=48))
    assert adm.retry_after(now=200.0) == 4  # excess 20 at 5/s
    assert adm.retry_after(now=200.0) != SHED_RETRY_AFTER_SECONDS  # negative: not the old fixed 30


def test_retry_after_counts_the_callers_already_waiting():
    adm = _admission(49)
    adm.note_round(50, now=100.0)
    adm.note_round(50, now=125.0)  # 2 thoughts/s
    assert adm.retry_after(now=200.0) == 1  # nobody waiting: one slot at 2/s
    for i in range(20):  # twenty clients refused within the last second
        adm.note_refusal(now=200.0 + i * 0.01)
    # negative: counting only the excess said 1 s, so all twenty came back every second
    assert adm.retry_after(now=200.5) == 6  # (1 + 20 / 2) / 2 -> 5.5 -> 6
    # they retry once per period, so the waiting count holds steady, not inflating
    for i in range(20):
        adm.note_refusal(now=206.0 + i * 0.01)
    assert adm.retry_after(now=206.5) == 6
    # once they stop coming the count decays with the window
    assert adm.retry_after(now=260.0) == 1


def test_retry_after_is_bounded():
    slow = _admission(49)
    slow.note_round(1, now=0.0)
    slow.note_round(1, now=1000.0)  # 0.001/s
    assert slow.retry_after() == SHED_RETRY_AFTER_SECONDS
    fast = _admission(49)
    fast.note_round(500, now=0.0)
    fast.note_round(500, now=1.0)
    assert fast.retry_after() == MIN_RETRY_AFTER_SECONDS


def test_drain_rate_is_smoothed():
    adm = _admission(49)
    adm.note_round(10, now=0.0)
    adm.note_round(10, now=10.0)  # 1/s
    adm.note_round(100, now=20.0)  # 10/s
    assert 1.0 < adm.drain_per_second < 10.0


@pytest.mark.asyncio
async def test_refusal_carries_the_measured_retry_after(monitor):
    gate = _gate(monitor)
    gate.admission.note_round(50, now=0.0)
    gate.admission.note_round(50, now=25.0)  # 2/s
    await _sample(monitor, 55)
    decision = gate.admit_intake()
    assert not decision.admitted
    assert decision.retry_after_seconds == 4  # excess 7 at 2/s -> 3.5 -> 4


# --------------------------------------------------------------------------- #
# The work loop takes the same headroom
# --------------------------------------------------------------------------- #


async def _activate(monitor, task_manager) -> int:
    fake = SimpleNamespace(
        resource_monitor=monitor, task_manager=task_manager, _discover_incomplete_tickets=AsyncMock(return_value=0)
    )
    _tickets, activated = await WorkProcessor._admit_new_work(fake)
    return activated


@pytest.mark.asyncio
async def test_task_activation_is_limited_to_the_headroom(monitor):
    task_manager = Mock(activate_pending_tasks=Mock(return_value=3))
    await _sample(monitor, 46)
    assert await _activate(monitor, task_manager) == 3
    task_manager.activate_pending_tasks.assert_called_once_with(limit=3)

    task_manager.activate_pending_tasks.reset_mock()
    await _sample(monitor, 49)  # at the ceiling: nothing new, no SHED needed
    assert not _gate(monitor).is_active(ResourceAction.SHED)
    assert await _activate(monitor, task_manager) == 0
    task_manager.activate_pending_tasks.assert_not_called()


def test_task_manager_honours_the_limit(monkeypatch):
    from ciris_engine.logic.processors.support import task_manager as tm_module

    pending = [SimpleNamespace(task_id=f"t{i}", priority=0) for i in range(8)]
    asked = {}

    def _pending(occurrence, limit):
        asked["limit"] = limit
        return pending[:limit]

    monkeypatch.setattr(tm_module.persistence, "count_active_tasks", lambda occ: 0)
    monkeypatch.setattr(tm_module.persistence, "get_pending_tasks_for_activation", _pending)
    monkeypatch.setattr(tm_module.persistence, "update_task_status", lambda *a: True)
    manager = tm_module.TaskManager(max_active_tasks=10, time_service=Mock(), agent_occurrence_id="o")
    assert manager.activate_pending_tasks(limit=2) == 2
    assert asked["limit"] == 2
    assert manager.activate_pending_tasks() == 8  # unbounded: the configured max applies
    assert asked["limit"] == 10


# --------------------------------------------------------------------------- #
# THROTTLE rests only as long as brings CPU back under its lift point
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cpu_throttle_is_proportional_to_the_overshoot(monitor):
    from ciris_engine.logic.services.infrastructure.resource_monitor.pressure import (
        MAX_THROTTLE_EXTRA_SECONDS,
        MIN_THROTTLE_EXTRA_SECONDS,
    )

    gate = _gate(monitor)
    monitor.snapshot.cpu_average_1m = 90  # HIGH (threshold 75)
    await monitor._check_limits()
    assert gate.throttle_extra_delay(3.0) == 3.0  # no round measured yet: the old doubling
    gate.note_round(49, 10.0)
    assert gate.throttle_extra_delay(3.0) == pytest.approx(10.0 * (90 / 75 - 1))  # 2.0 s, not a fixed 3+
    monitor.snapshot.cpu_average_1m = 100
    await monitor._check_limits()
    gate.note_round(49, 60.0)
    assert gate.throttle_extra_delay(3.0) == MAX_THROTTLE_EXTRA_SECONDS
    monitor.snapshot.cpu_average_1m = 72  # still HIGH by hysteresis, under the threshold
    await monitor._check_limits()
    gate.note_round(49, 1.0)
    assert gate.throttle_extra_delay(3.0) == MIN_THROTTLE_EXTRA_SECONDS


@pytest.mark.asyncio
async def test_no_throttle_no_rest(monitor):
    gate = _gate(monitor)
    gate.note_round(49, 10.0)
    assert gate.throttle_extra_delay(3.0) == 0.0


# --------------------------------------------------------------------------- #
# The WORK delay is an idle poll, not a pause under backlog
# --------------------------------------------------------------------------- #


def _work_delay(monitor, last_round_processed: int) -> float:
    fake = SimpleNamespace(
        app_config=SimpleNamespace(mock_llm=False),
        services=SimpleNamespace(resource_monitor=monitor),
        _last_round_processed=last_round_processed,
    )
    return AgentProcessor._calculate_round_delay(fake, AgentState.WORK)


def test_no_poll_delay_after_a_round_that_did_work(monitor):
    assert _work_delay(monitor, 0) == 3.0  # idle: poll interval
    assert _work_delay(monitor, 49) == 0.0  # backlog: next round at once


@pytest.mark.asyncio
async def test_throttle_still_slows_a_busy_loop(monitor):
    monitor.snapshot.cpu_average_1m = 84
    await monitor._check_limits()
    assert _work_delay(monitor, 49) > 0.0


@pytest.mark.asyncio
async def test_admission_transition_lines_are_rate_limited(monitor, caplog):
    import logging

    caplog.set_level(logging.INFO, logger="ciris_engine.logic.services.infrastructure.resource_monitor.pressure")
    gate = _gate(monitor)
    for _ in range(20):  # flapping at the ceiling, many times a round
        await _sample(monitor, 49)
        assert not gate.admit_intake().admitted
        await _sample(monitor, 40)
        assert gate.admit_intake().admitted
        gate.settle_intake(False)
    lines = [r for r in caplog.records if r.getMessage().startswith("Admission: ")]
    assert len(lines) == 1  # negative: one line per flip (40) before
    assert gate.admission.refused_total == 20  # every refusal still counted
