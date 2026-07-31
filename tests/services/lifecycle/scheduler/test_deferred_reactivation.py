"""
Regression tests for CIRISAgent#865 + #934 — deferred-thought reactivation and
scheduler dead-lettering.

#865: When a thought defers itself with a ``defer_until`` timestamp, the
scheduler must, when the timer expires, transition BOTH the deferred task and
the deferred thought back to a processable state. The pre-fix code keyed the
reactivation off ``task.metadata`` — a field that does not exist on
``ScheduledTask`` (extra="forbid") — so reactivation was a silent no-op and the
agent stayed stuck in ``deferred`` forever.

#934: Three refinements on top of #865:

1. Reactivation must set the deferred task to ACTIVE, not PENDING — only the
   WORK processor promotes PENDING→ACTIVE, so a wakeup-step task re-pended
   during WAKEUP left its thought invisible (get_pending_thoughts_for_active_tasks
   filters to ACTIVE tasks) and the agent spun ~933k empty rounds over 55 days.
2. A scheduled task whose FK target row is gone is quarantined (dead-lettered)
   with ONE ERROR at the transition, instead of failing `FOREIGN KEY constraint
   failed` every 60 s forever (~80k futile inserts observed in production).
3. Any scheduled task that fails DEAD_LETTER_THRESHOLD consecutive times is
   dead-lettered and stops re-firing.
"""

import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.services.lifecycle.scheduler.service import DEAD_LETTER_THRESHOLD
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.extended import ScheduledTask

SCHEDULER_LOGGER = "ciris_engine.logic.services.lifecycle.scheduler.service"


def _make_service():
    """Build a TaskSchedulerService without running __init__."""
    from ciris_engine.logic.services.lifecycle.scheduler.service import TaskSchedulerService

    svc = TaskSchedulerService.__new__(TaskSchedulerService)
    svc._active_tasks = {}
    svc._dead_lettered_tasks = {}
    svc._task_failure_counts = {}
    svc._tasks_triggered = 0
    svc._tasks_failed = 0
    svc._tasks_completed = 0
    svc._tasks_dead_lettered = 0
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


def _regular_scheduled_task() -> ScheduledTask:
    """A regular (non-reactivation) one-time scheduled task."""
    return ScheduledTask(
        task_id="task_1780753242.616828",
        name="Regular scheduled task",
        goal_description="Do the thing",
        trigger_prompt="Do the thing now",
        origin_thought_id="th_origin_1",
        created_at=datetime(2026, 6, 6, tzinfo=timezone.utc),
        defer_until=datetime(2026, 6, 6, 14, 0, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_reactivation_activates_task_and_repends_thought():
    """#865/#934: due deferred task -> task ACTIVE + thought PENDING, in the
    task row's own occurrence (not hard-coded "default")."""
    svc = _make_service()
    task = _deferred_scheduled_task()

    deferred_row = MagicMock()
    deferred_row.agent_occurrence_id = "occurrence-1"

    with patch(
        "ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=deferred_row
    ) as mock_get, patch(
        "ciris_engine.logic.persistence.update_task_status", return_value=True
    ) as mock_task_status, patch(
        "ciris_engine.logic.persistence.update_thought_status", return_value=True
    ) as mock_thought_status, patch.object(
        svc, "_update_task_triggered"
    ), patch.object(
        svc, "_complete_task"
    ):
        await svc._trigger_task(task)

    # Guard checked the REAL deferred task id (not the synthetic scheduler id),
    # across ALL occurrences (wakeup steps live on the claiming occurrence).
    mock_get.assert_called_once_with("VALIDATE_INTEGRITY_abc")
    # Task: deferred -> ACTIVE (#934 layer B — PENDING is invisible in WAKEUP:
    # nothing promotes it and get_pending_thoughts_for_active_tasks filters on
    # ACTIVE, so PENDING left the agent spinning empty wakeup rounds forever).
    mock_task_status.assert_called_once_with("VALIDATE_INTEGRITY_abc", TaskStatus.ACTIVE, "occurrence-1")
    # Thought: the missing transition that #865 is about.
    mock_thought_status.assert_called_once_with(
        thought_id="th_std_deferred_1", status=ThoughtStatus.PENDING, occurrence_id="occurrence-1"
    )
    # Not dead-lettered; failure streak clear.
    assert task.task_id not in svc._dead_lettered_tasks
    assert svc._task_failure_counts == {}


@pytest.mark.asyncio
async def test_reactivation_missing_row_dead_letters_and_names_wakeup_step(caplog):
    """#934: if the deferred WAKEUP-step task row is gone, re-activation is
    impossible — quarantine with ONE ERROR that names the wakeup step, create
    no orphan thought (the #863-C FK violation), and stop re-firing."""
    svc = _make_service()
    task = _deferred_scheduled_task()
    svc._active_tasks[task.task_id] = task

    with caplog.at_level(logging.ERROR, logger=SCHEDULER_LOGGER), patch(
        "ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=None
    ), patch(
        "ciris_engine.logic.persistence.update_task_status"
    ) as mock_task_status, patch(
        "ciris_engine.logic.persistence.update_thought_status"
    ) as mock_thought_status, patch(
        "ciris_engine.logic.services.lifecycle.scheduler.service.add_thought"
    ) as mock_add_thought:
        await svc._trigger_task(task)

    mock_task_status.assert_not_called()
    mock_thought_status.assert_not_called()
    # Crucially: no orphan thought inserted against a missing task.
    mock_add_thought.assert_not_called()

    # Dead-lettered: removed from active, quarantined as FAILED, stops re-firing.
    assert task.task_id not in svc._active_tasks
    assert svc._dead_lettered_tasks[task.task_id] is task
    assert task.status == "FAILED"
    assert svc._get_due_tasks(datetime(2026, 6, 7, tzinfo=timezone.utc)) == []

    # Exactly ONE transition ERROR, and it names the wakeup step LOUDLY.
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "Dead-lettered" in errors[0].getMessage()
    assert "VALIDATE_INTEGRITY" in errors[0].getMessage()
    assert "wakeup" in errors[0].getMessage().lower()


@pytest.mark.asyncio
async def test_orphan_regular_task_quarantined_at_trigger(caplog):
    """#934: a regular scheduled task whose source task row is gone would FK-fail
    on every trigger — quarantine immediately with one ERROR, no insert attempt."""
    svc = _make_service()
    task = _regular_scheduled_task()
    svc._active_tasks[task.task_id] = task

    with caplog.at_level(logging.ERROR, logger=SCHEDULER_LOGGER), patch(
        "ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=None
    ), patch(
        "ciris_engine.logic.services.lifecycle.scheduler.service.add_thought"
    ) as mock_add_thought:
        await svc._trigger_task(task)

    mock_add_thought.assert_not_called()
    assert task.task_id not in svc._active_tasks
    assert task.task_id in svc._dead_lettered_tasks
    assert task.status == "FAILED"

    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "Dead-lettered" in errors[0].getMessage()
    assert "foreign key" in errors[0].getMessage().lower()


@pytest.mark.asyncio
async def test_repeated_trigger_failures_dead_letter_after_threshold(caplog):
    """#934: a task whose trigger keeps raising (e.g. a deterministic
    IntegrityError from the persistence substrate) is dead-lettered after
    DEAD_LETTER_THRESHOLD consecutive failures with ONE transition ERROR,
    and never fires again."""
    svc = _make_service()
    task = _regular_scheduled_task()
    svc._active_tasks[task.task_id] = task

    source_row = MagicMock()
    source_row.agent_occurrence_id = "default"

    with caplog.at_level(logging.ERROR, logger=SCHEDULER_LOGGER), patch(
        "ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=source_row
    ), patch(
        "ciris_engine.logic.services.lifecycle.scheduler.service.add_thought",
        side_effect=Exception("FOREIGN KEY constraint failed"),
    ) as mock_add_thought:
        for _ in range(DEAD_LETTER_THRESHOLD):
            await svc._trigger_task(task)

        assert mock_add_thought.call_count == DEAD_LETTER_THRESHOLD

        # Quarantined after N consecutive failures; the streak bookkeeping is gone.
        assert task.task_id not in svc._active_tasks
        assert task.task_id in svc._dead_lettered_tasks
        assert task.status == "FAILED"
        assert task.task_id not in svc._task_failure_counts

        # It must stop re-firing: not due anymore, and another scheduler pass
        # performs zero further insert attempts.
        assert svc._get_due_tasks(datetime(2026, 6, 7, tzinfo=timezone.utc)) == []
        await svc._run_scheduled_task()
        assert mock_add_thought.call_count == DEAD_LETTER_THRESHOLD

    # Exactly ONE dead-letter transition ERROR (plus N-1 per-attempt errors).
    dead_letter_errors = [
        r for r in caplog.records if r.levelno == logging.ERROR and "Dead-lettered" in r.getMessage()
    ]
    assert len(dead_letter_errors) == 1
    # Root cause is included at the transition.
    assert "consecutive" in dead_letter_errors[0].getMessage()


@pytest.mark.asyncio
async def test_success_resets_consecutive_failure_streak():
    """#934: dead-letter counts CONSECUTIVE failures — a success in between resets."""
    svc = _make_service()
    task = _regular_scheduled_task()
    task.schedule_cron = "* * * * *"  # recurring so success does not complete it
    task.defer_until = None
    svc._active_tasks[task.task_id] = task

    source_row = MagicMock()
    source_row.agent_occurrence_id = "default"

    with patch(
        "ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=source_row
    ), patch(
        "ciris_engine.logic.services.lifecycle.scheduler.service.add_thought",
        side_effect=[Exception("boom"), Exception("boom"), None, Exception("boom")],
    ):
        await svc._trigger_task(task)
        await svc._trigger_task(task)
        assert svc._task_failure_counts[task.task_id] == 2
        await svc._trigger_task(task)  # success — streak resets
        assert task.task_id not in svc._task_failure_counts
        await svc._trigger_task(task)  # first failure of a NEW streak
        assert svc._task_failure_counts[task.task_id] == 1

    assert task.task_id in svc._active_tasks
    assert task.task_id not in svc._dead_lettered_tasks


@pytest.mark.asyncio
async def test_dead_lettered_tasks_visible_and_clearable():
    """#934: dead-lettered tasks surface via get_scheduled_tasks() (status
    FAILED) and metrics, and cancel_task() clears them."""
    svc = _make_service()
    task = _regular_scheduled_task()
    svc._active_tasks[task.task_id] = task

    svc._dead_letter_task(task, "test quarantine")

    infos = await svc.get_scheduled_tasks()
    assert [t.task_id for t in infos] == [task.task_id]
    assert infos[0].status == "FAILED"
    assert svc._tasks_dead_lettered == 1

    assert await svc.cancel_task(task.task_id) is True
    assert svc._dead_lettered_tasks == {}
    assert await svc.get_scheduled_tasks() == []


def test_legacy_blind_retry_layer_is_gone():
    """#934 item 1: the legacy `_retry_execute` wrapper retried deterministic
    sqlite3.IntegrityError (FK violations) as if transient. That layer was
    deleted with the ciris-persist substrate migration (#896) — retry
    classification is owned by the substrate. Lock that in so an agent-side
    blind retry wrapper does not quietly come back."""
    from ciris_engine.logic.persistence.db import core as db_core

    assert not hasattr(db_core, "_retry_execute")
    assert not hasattr(db_core, "get_db_connection")
