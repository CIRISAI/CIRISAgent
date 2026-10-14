"""Held tasks are not swept, and missed schedules coalesce (CC 4.2.1.1, CIRISAgent#1231)."""

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.infrastructure.database_maintenance.service import DatabaseMaintenanceService
from ciris_engine.logic.services.lifecycle.scheduler.service import TaskSchedulerService
from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState
from ciris_engine.schemas.runtime.extended import ScheduledTask

pytestmark = pytest.mark.real_halt_latch


def _state(halted: bool, reading: AccordHaltReading, invocation_id: Any = None) -> AccordHaltState:
    return AccordHaltState(
        halted=halted, reading=reading, invocation_id=invocation_id, read_at=datetime.now(timezone.utc)
    )


HALTED = _state(True, AccordHaltReading.IN_EFFECT, "inv-sweep")
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
    return lt


def _maintenance() -> Any:
    svc = DatabaseMaintenanceService.__new__(DatabaseMaintenanceService)
    svc._vacuum_runs = 0
    svc._invoke_persist_maintenance = AsyncMock()  # type: ignore[method-assign]
    svc._cleanup_stale_wakeup_tasks = AsyncMock()  # type: ignore[method-assign]
    svc._cleanup_old_active_tasks = AsyncMock()  # type: ignore[method-assign]
    return svc


@pytest.mark.asyncio
async def test_held_tasks_are_not_swept_while_halted(latch):
    svc = _maintenance()
    await svc._perform_periodic_maintenance()
    svc._cleanup_stale_wakeup_tasks.assert_not_awaited()
    svc._cleanup_old_active_tasks.assert_not_awaited()
    svc._invoke_persist_maintenance.assert_awaited_once()  # generic DB upkeep is not the agent's act


@pytest.mark.asyncio
async def test_sweeps_run_when_no_halt_stands(latch):
    """Positive control for the sweep exemption."""
    latch.state = NOT_HALTED
    svc = _maintenance()
    await svc._perform_periodic_maintenance()
    svc._cleanup_stale_wakeup_tasks.assert_awaited_once()
    svc._cleanup_old_active_tasks.assert_awaited_once()


class Clock:
    def __init__(self, now: datetime) -> None:
        self.t = now

    def now(self) -> datetime:
        return self.t


@pytest.mark.asyncio
async def test_missed_recurring_schedules_coalesce_to_one_fire(latch):
    start = datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc)
    clock = Clock(start)
    scheduler = TaskSchedulerService(db_path=":memory:", time_service=clock, check_interval_seconds=60)  # type: ignore[arg-type]
    created = []
    scheduler._create_scheduled_thought = lambda task: created.append(task.task_id) or True  # type: ignore[method-assign]
    scheduler._active_tasks["hourly"] = ScheduledTask(
        task_id="hourly",
        name="hourly check-in",
        goal_description="g",
        status="ACTIVE",
        schedule_cron="0 * * * *",
        trigger_prompt="p",
        origin_thought_id="th-0",
        created_at=start,
    )

    # Twelve hourly fires pass under the halt: none fire.
    for hour in range(1, 13):
        clock.t = start + timedelta(hours=hour, minutes=1)
        await scheduler._run_scheduled_task()
    assert created == []

    # The halt ends: ONE fire, however many were missed, and not again this hour.
    latch.state = NOT_HALTED
    await scheduler._run_scheduled_task()
    clock.t += timedelta(minutes=1)
    await scheduler._run_scheduled_task()
    assert created == ["hourly"]


# --------------------------------------------------------------------------- #
# Restart under a standing halt: the startup old-task sweep waits for the latch
# --------------------------------------------------------------------------- #

UNREACHABLE = _state(True, AccordHaltReading.NODE_UNREACHABLE)


@pytest.mark.asyncio
async def test_startup_sweep_runs_inline_when_no_halt_stands(latch):
    latch.state = NOT_HALTED
    svc = _maintenance()
    await svc._sweep_old_active_tasks_at_startup()
    svc._cleanup_old_active_tasks.assert_awaited_once()
    assert halt_latch._unhalted_hooks == []


@pytest.mark.asyncio
async def test_startup_sweep_waits_for_the_boot_window_and_then_runs(latch):
    """Node not answering yet: deferred; the first clear reading runs it, before that read returns."""
    latch.state = UNREACHABLE
    svc = _maintenance()
    await svc._sweep_old_active_tasks_at_startup()
    svc._cleanup_old_active_tasks.assert_not_awaited()

    latch.state = NOT_HALTED
    assert (await halt_latch.read_halt_latch()).halted is False
    svc._cleanup_old_active_tasks.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("via", ["held_then_released", "lapsed_while_down"])
async def test_held_tasks_survive_a_restart_under_the_halt(latch, via):
    latch.state = UNREACHABLE
    svc = _maintenance()
    await svc._sweep_old_active_tasks_at_startup()

    if via == "held_then_released":
        latch.state = HALTED
        await halt_latch.read_halt_latch()  # the restarted agent finds the halt standing
        latch.state = NOT_HALTED
    else:
        latch.state = _state(False, AccordHaltReading.LAPSED, "inv-sweep")
    await halt_latch.read_halt_latch()

    svc._cleanup_old_active_tasks.assert_not_awaited()  # they were held, not abandoned
    assert halt_latch._unhalted_hooks == []  # and the deferral is spent


@pytest.mark.asyncio
async def test_startup_cleanup_uses_the_deferring_sweep(monkeypatch, latch):
    """perform_startup_cleanup routes the old-task sweep through the halt-aware path."""
    from ciris_engine.logic.services.infrastructure.database_maintenance import service as maint

    for name in (
        "get_tasks_by_status",
        "get_thoughts_by_status",
        "get_thoughts_older_than",
    ):
        monkeypatch.setattr(maint, name, lambda *a, **k: [])
    svc = _maintenance()
    svc.time_service = Mock(now=Mock(return_value=datetime.now(timezone.utc)))
    svc.archive_dir = Mock()
    svc.archive_older_than_hours = 24
    svc._cleanup_runs = 0
    for step in (
        "_reclaim_orphaned_processing_thoughts",
        "_cleanup_invalid_thoughts",
        "_cleanup_runtime_config",
        "_dedupe_adapter_configs",
        "_cleanup_non_persistent_adapters",
        "_check_legacy_covenant_config",
        "_cleanup_duplicate_temporal_edges",
    ):
        setattr(svc, step, AsyncMock())
    latch.state = UNREACHABLE
    await svc.perform_startup_cleanup()
    svc._cleanup_stale_wakeup_tasks.assert_awaited_once()  # #1069: ceremony sweep is never deferred
    svc._cleanup_old_active_tasks.assert_not_awaited()
    assert len(halt_latch._unhalted_hooks) == 1
