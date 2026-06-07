"""
Regression tests for CIRISAgent#865 — deferred-thought reactivation.

When a thought defers itself with a ``defer_until`` timestamp, the scheduler
must, when the timer expires, transition BOTH the deferred task and the
deferred thought back to a processable state. The pre-fix code keyed the
reactivation off ``task.metadata`` — a field that does not exist on
``ScheduledTask`` (extra="forbid") — so reactivation was a silent no-op and the
agent stayed stuck in ``deferred`` forever.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.extended import ScheduledTask


def _make_service():
    """Build a TaskSchedulerService without running __init__."""
    from ciris_engine.logic.services.lifecycle.scheduler.service import TaskSchedulerService

    svc = TaskSchedulerService.__new__(TaskSchedulerService)
    svc._active_tasks = {}
    svc._tasks_triggered = 0
    svc._tasks_failed = 0
    svc._tasks_completed = 0
    svc._time_service = MagicMock()
    svc._time_service.now.return_value = datetime(2026, 6, 7, tzinfo=timezone.utc)
    return svc


def _deferred_scheduled_task() -> ScheduledTask:
    """A one-time reactivation task as produced by schedule_deferred_task()."""
    return ScheduledTask(
        task_id="SCHED_reactivate_1",
        name="Reactivate task VALIDATE_INTEGRITY_abc",
        goal_description="Reactivate deferred task: investigate",
        trigger_prompt="Task VALIDATE_INTEGRITY_abc scheduled for reactivation",
        origin_thought_id="th_std_deferred_1",
        created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        defer_until=datetime(2026, 6, 6, 14, 0, tzinfo=timezone.utc),
        deferral_count=1,
        deferral_history=[
            {
                "deferred_task_id": "VALIDATE_INTEGRITY_abc",
                "deferral_reason": "investigate",
                "deferred_at": "2026-06-06T13:40:46Z",
            }
        ],
    )


@pytest.mark.asyncio
async def test_reactivation_repends_task_and_thought():
    """#865: due deferred task -> both task AND thought return to PENDING."""
    svc = _make_service()
    task = _deferred_scheduled_task()

    with patch("ciris_engine.logic.persistence.get_task_by_id", return_value=MagicMock()) as mock_get, patch(
        "ciris_engine.logic.persistence.update_task_status"
    ) as mock_task_status, patch(
        "ciris_engine.logic.persistence.update_thought_status"
    ) as mock_thought_status, patch.object(
        svc, "_update_task_triggered"
    ), patch.object(
        svc, "_complete_task"
    ):
        await svc._trigger_task(task)

    # Guard checked the REAL deferred task id (not the synthetic scheduler id).
    mock_get.assert_called_once_with("VALIDATE_INTEGRITY_abc", "default")
    # Task: deferred -> pending.
    mock_task_status.assert_called_once_with("VALIDATE_INTEGRITY_abc", TaskStatus.PENDING, "default")
    # Thought: the missing transition that #865 is about.
    mock_thought_status.assert_called_once_with(
        thought_id="th_std_deferred_1", status=ThoughtStatus.PENDING
    )


@pytest.mark.asyncio
async def test_reactivation_skips_when_deferred_task_gone():
    """If the deferred task was deleted, do not reactivate and do not create an
    orphan thought (the #863-C FK violation)."""
    svc = _make_service()
    task = _deferred_scheduled_task()

    with patch("ciris_engine.logic.persistence.get_task_by_id", return_value=None), patch(
        "ciris_engine.logic.persistence.update_task_status"
    ) as mock_task_status, patch(
        "ciris_engine.logic.persistence.update_thought_status"
    ) as mock_thought_status, patch(
        "ciris_engine.logic.persistence.add_thought"
    ) as mock_add_thought, patch.object(
        svc, "_update_task_triggered"
    ), patch.object(
        svc, "_complete_task"
    ):
        await svc._trigger_task(task)

    mock_task_status.assert_not_called()
    mock_thought_status.assert_not_called()
    # Crucially: no orphan thought inserted against a missing task.
    mock_add_thought.assert_not_called()
