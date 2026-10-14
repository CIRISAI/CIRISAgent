"""The hourly maintenance pass must not complete tasks this run is working on (CIRISAgent#1264).

`_cleanup_old_active_tasks` is meant for tasks left ACTIVE by a previous run,
and tells their channel "I was restarted". The hourly periodic pass reused it
with only a five-minute age test, so in safety-battery run 38492155330 it
completed the run's own stalled tasks an hour in, and its unscoped notice went
FIFO to the request then waiting on the channel: a live question was "answered"
with "I was restarted while processing your request".
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.authorization.reasoning_scope import current_reasoning_scope
from ciris_engine.logic.services.infrastructure.database_maintenance.service import DatabaseMaintenanceService
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext

pytestmark = pytest.mark.asyncio

CHANNEL = "safety_battery_ru_mental_health_v4_test"
T0 = datetime(2026, 10, 14, 0, 56, 30, tzinfo=timezone.utc)  # process start


class _Clock:
    def __init__(self, now: datetime):
        self.current = now

    def now(self) -> datetime:
        return self.current


def _task(task_id: str, created: datetime) -> Task:
    task = Task(
        task_id=task_id,
        channel_id=CHANNEL,
        agent_occurrence_id="default",
        description="question",
        status=TaskStatus.ACTIVE,
        created_at=created.isoformat(),
        updated_at=created.isoformat(),
        context=TaskContext(
            channel_id=CHANNEL,
            user_id="qa_safety_ru",
            correlation_id=f"corr_{uuid4().hex[:8]}",
            agent_occurrence_id="default",
        ),
    )
    persistence.add_task(task)
    return task


@pytest.fixture
def clock():
    return _Clock(T0)


@pytest.fixture
def bus_manager():
    bus = MagicMock()
    scopes = []

    async def _send(channel_id, content, handler_name, metadata=None):
        scopes.append(current_reasoning_scope())
        return True

    bus.communication.has_service_for_channel.return_value = True
    bus.communication.send_message_sync = AsyncMock(side_effect=_send)
    bus.audit_service = None
    bus.scopes = scopes
    return bus


@pytest.fixture
def service(clean_db, clock, bus_manager, tmp_path):
    return DatabaseMaintenanceService(
        time_service=clock,
        archive_dir_path=str(tmp_path / "archive"),
        config_service=AsyncMock(),
        db_path=clean_db,
        bus_manager=bus_manager,
    )


async def test_periodic_pass_leaves_this_runs_tasks_alone(service, clock, bus_manager):
    live = _task("task-live-q01", T0 + timedelta(seconds=10))
    clock.current = T0 + timedelta(minutes=61)  # the hourly pass; the task is ~61 minutes old

    await service._cleanup_old_active_tasks()

    assert persistence.get_task_by_id(live.task_id, "default").status == TaskStatus.ACTIVE
    bus_manager.communication.send_message_sync.assert_not_awaited()


async def test_previous_run_task_is_completed_and_notice_is_scoped_to_it(service, clock, bus_manager):
    stale = _task("task-previous-run", T0 - timedelta(minutes=30))
    clock.current = T0 + timedelta(minutes=1)

    await service._cleanup_old_active_tasks()

    assert persistence.get_task_by_id(stale.task_id, "default").status == TaskStatus.COMPLETED
    bus_manager.communication.send_message_sync.assert_awaited_once()
    # Scoped to the stale task, so the API adapter delivers it only to a request
    # that task owns, never to whichever live request is next on the channel.
    (scope,) = bus_manager.scopes
    assert scope is not None and scope.task_id == stale.task_id
