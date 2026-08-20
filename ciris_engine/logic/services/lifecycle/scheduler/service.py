"""
Task Scheduler Service

This service manages scheduled tasks and proactive goals for CIRIS agents.
It integrates with the time-based DEFER system to enable agents to schedule
their own future actions with human approval.

"I defer to tomorrow what I cannot complete today" - Agent self-management
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, FrozenSet, List, Optional

from ciris_engine.logic.persistence import add_thought
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.protocols.services import ServiceProtocol as TaskSchedulerServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType, TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.extended import ScheduledTask, ScheduledTaskInfo, ShutdownContext
from ciris_engine.schemas.runtime.models import FinalAction, Thought
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def _sanitize_for_log(value: str, max_length: int = 64) -> str:
    """Sanitize a value for safe inclusion in log messages.

    Prevents log injection (CWE-117) by:
    1. Removing newlines and carriage returns (prevent log forging)
    2. Removing control characters
    3. Truncating to max length
    4. Using allowlist of safe characters

    Args:
        value: Raw value to sanitize
        max_length: Maximum length of output

    Returns:
        Sanitized value safe for logging
    """
    if not value:
        return "unnamed"
    # Remove newlines, carriage returns, and other control characters
    sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", value)
    # Truncate to max length
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length] + "..."
    return sanitized or "unnamed"


# Try to import croniter for cron scheduling support
try:
    from croniter import croniter

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    logger.warning("croniter not installed. Cron scheduling will be disabled.")


# Wakeup step-task prefixes (mirrors database_maintenance._is_wakeup_or_shutdown_task
# and the wakeup processor's step sequence). Used to NAME the wakeup step in the
# single ERROR emitted when a wakeup-step re-activation cannot proceed (#934) —
# a silently-skipped step leaves the agent spinning empty wakeup rounds forever
# while reporting healthy.
WAKEUP_STEP_PREFIXES = (
    "VERIFY_IDENTITY_",
    "VALIDATE_INTEGRITY_",
    "EVALUATE_RESILIENCE_",
    "ACCEPT_INCOMPLETENESS_",
    "EXPRESS_GRATITUDE_",
)

# Consecutive identical trigger failures before a scheduled task is dead-lettered
# (#934). Deterministic failures (missing FK target detected at trigger time) skip
# the count and quarantine immediately — retrying a constraint violation can never
# succeed (~80k futile re-fires observed on one production agent over 8 weeks).
DEAD_LETTER_THRESHOLD = 3

# Task statuses that mean this deferral has ALREADY BEEN ANSWERED, so an
# expiring timer must not resurrect the row (NULLWORKS RC3 finding F2).
#
# `WiseAuthorityService.resolve_deferral` marks the original deferred task
# COMPLETED for BOTH outcomes — an approval and a rejection — records the
# outcome on the row, and (only when approved) carries the work forward on a
# NEW `[WA GUIDANCE]` task that holds the freshly issued approval envelope.
# Without this set, a stale one-time timer firing after a human answered would
# flip that COMPLETED row back to ACTIVE and re-pend its thought: a rejection
# silently re-entering the pipeline, or an approval re-run on the old task,
# which by construction does NOT hold the approval envelope. Time may prompt
# reconsideration; it must never overturn — or stand in for — a human's answer.
RESOLVED_TASK_STATUSES: FrozenSet[TaskStatus] = frozenset(
    {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REJECTED}
)


class TaskSchedulerService(BaseScheduledService, TaskSchedulerServiceProtocol):
    """
    Manages scheduled tasks and integrates with the DEFER system.

    This service enables agents to be proactive by scheduling future actions,
    either through one-time deferrals or recurring schedules.
    """

    def __init__(self, db_path: str, time_service: TimeServiceProtocol, check_interval_seconds: int = 60) -> None:
        super().__init__(run_interval_seconds=float(check_interval_seconds), time_service=time_service)
        self.db_path = db_path
        self.conn = None
        self.check_interval = check_interval_seconds
        self._active_tasks: Dict[str, ScheduledTask] = {}
        self._shutdown_event = asyncio.Event()

        # Dead-letter quarantine (#934): tasks that deterministically fail
        # (missing FK target) or fail DEAD_LETTER_THRESHOLD consecutive times
        # are moved here — they stop re-firing and stay visible via
        # get_scheduled_tasks() / the /v1/scheduler API with status FAILED.
        self._dead_lettered_tasks: Dict[str, ScheduledTask] = {}
        self._task_failure_counts: Dict[str, int] = {}

        # Task tracking metrics
        self._tasks_scheduled = 0
        self._tasks_triggered = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
        self._tasks_dead_lettered = 0
        self._recurring_tasks = 0
        self._oneshot_tasks = 0

    def get_service_type(self) -> ServiceType:
        """Get service type."""
        return ServiceType.MAINTENANCE

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["schedule_task", "cancel_task", "get_scheduled_tasks"]

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are available."""
        return True  # Only needs time service which is provided

    async def _on_start(self) -> None:
        """Called when service starts."""
        await super()._on_start()

        # Load active tasks from database
        await self._load_active_tasks()

        logger.info(f"TaskSchedulerService started with {len(self._active_tasks)} active tasks")

    async def _on_stop(self) -> None:
        """Called when service stops."""
        self._shutdown_event.set()
        await super()._on_stop()

    async def _load_active_tasks(self) -> None:
        """Load all active tasks.

        Scheduled tasks are currently held in-memory in `self._active_tasks`.
        Persistence through ciris-persist's `scheduled_task_*` substrate
        is wired separately (CIRISAgent#763 / 2.9.0 absorption); legacy
        raw-sqlite3 path is removed to avoid a second libsqlite writer
        on `ciris_engine.db`.
        """
        logger.info("Loading active scheduled tasks (in-memory state)")

    def _create_scheduled_task(
        self,
        task_id: str,
        name: str,
        goal_description: str,
        trigger_prompt: str,
        origin_thought_id: str,
        defer_until: Optional[str] = None,
        schedule_cron: Optional[str] = None,
    ) -> ScheduledTask:
        """Create a new scheduled task."""
        return ScheduledTask(
            task_id=task_id,
            name=name,
            goal_description=goal_description,
            status="PENDING",
            defer_until=defer_until,
            schedule_cron=schedule_cron,
            trigger_prompt=trigger_prompt,
            origin_thought_id=origin_thought_id,
            created_at=(self._time_service.now() if self._time_service else datetime.now(timezone.utc)).isoformat(),
            last_triggered_at=None,
            deferral_count=0,
            deferral_history=[],
        )

    async def _run_scheduled_task(self) -> None:
        """Check for due tasks and trigger them."""
        # Check for due tasks
        now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        due_tasks = self._get_due_tasks(now)

        for task in due_tasks:
            await self._trigger_task(task)

    def _get_due_tasks(self, current_time: datetime) -> List[ScheduledTask]:
        """Get all tasks that are due for execution."""
        due_tasks = []

        for task in self._active_tasks.values():
            if self._is_task_due(task, current_time):
                due_tasks.append(task)

        return due_tasks

    def _is_task_due(self, task: ScheduledTask, current_time: datetime) -> bool:
        """Check if a task is due for execution."""
        # One-time deferred task
        if task.defer_until:
            # defer_until is always a datetime per the type annotation
            return current_time >= task.defer_until

        # Cron-style recurring task
        if task.schedule_cron:
            return self._should_trigger_cron(task, current_time)

        return False

    def _should_trigger_cron(self, task: ScheduledTask, current_time: datetime) -> bool:
        """Check if a cron-scheduled task should trigger."""
        if not CRONITER_AVAILABLE:
            # Sanitize task_id for logging (CWE-117)
            safe_task_id = _sanitize_for_log(task.task_id)
            logger.warning(f"Cron scheduling requested for task {safe_task_id} but croniter not installed")
            return False

        try:
            # If never triggered, use creation time as base
            if not task.last_triggered_at:
                # created_at is always a datetime per the type annotation
                base_time = task.created_at
            else:
                # last_triggered_at is always a datetime per the type annotation
                base_time = task.last_triggered_at

            # Create croniter instance
            cron = croniter(task.schedule_cron, base_time)

            # Get next scheduled time
            next_time = cron.get_next(datetime)

            # Check if we've passed the next scheduled time
            # Add a small buffer (1 second) to avoid missing triggers due to timing
            return bool(current_time >= next_time - timedelta(seconds=1))

        except Exception:
            # Sanitize for logging (CWE-117) - don't log exception details
            safe_task_id = _sanitize_for_log(task.task_id)
            logger.error(f"Invalid cron expression for task {safe_task_id}: parse error")
            return False

    def _wakeup_step_name(self, task_id: str) -> Optional[str]:
        """Return the wakeup step name if task_id is a wakeup step task, else None."""
        for prefix in WAKEUP_STEP_PREFIXES:
            if task_id.startswith(prefix):
                return prefix.rstrip("_")
        return None

    def _dead_letter_task(self, task: ScheduledTask, root_cause: str) -> None:
        """Quarantine a scheduled task that can never (or will no longer) succeed (#934).

        The task stops re-firing, is marked FAILED, and remains visible via
        get_scheduled_tasks() / the scheduler API. Exactly ONE ERROR is emitted
        at the transition — not one per minute forever.
        """
        task.status = "FAILED"
        self._active_tasks.pop(task.task_id, None)
        self._task_failure_counts.pop(task.task_id, None)
        self._dead_lettered_tasks[task.task_id] = task
        self._tasks_dead_lettered += 1
        # Single transition ERROR: task_id + name + origin thought (the closest
        # thing a ScheduledTask has to a correlation id) + root cause.
        logger.error(
            f"Dead-lettered scheduled task {_sanitize_for_log(task.task_id)} "
            f"({_sanitize_for_log(task.name)}): {_sanitize_for_log(root_cause, max_length=256)} "
            f"[origin_thought_id={_sanitize_for_log(task.origin_thought_id)}]. "
            "Task will not re-fire; inspect via /v1/scheduler/tasks?status=FAILED."
        )

    def _reactivate_deferred_task(self, task: ScheduledTask, deferred_task_id: str) -> bool:
        """Re-activate a self-deferred task + its deferred thought.

        Returns True when reactivation proceeded (normal completion follows);
        False when the task was dead-lettered (caller must stop).

        The re-activation deliberately touches ONLY rows that already exist —
        it never inserts a thought FK'd to the synthetic scheduled-task id
        (the #934 `FOREIGN KEY constraint failed` loop that kept a production
        agent spinning ~933k empty wakeup rounds over 55 days).

        **What the timer grants, and what it does not** (NULLWORKS RC3, F2).
        Two things are easy to conflate here and are deliberately kept apart:

        * *Reconsideration* — the agent may look at this work again. That is
          exactly what an expiring `defer_until` buys, and it is why this method
          sets the task ACTIVE rather than PENDING (see (1) below).
        * *Execution* — the deferred consequential action may proceed. A timer
          buys none of this, and nothing on this path grants it.

        The separation holds structurally rather than by a flag checked here,
        which is why there is no approval bit in this method to look for:

        * A tool declaring ``ToolDMAGuidance(requires_approval=True)`` executes
          only when the **task's** ``TaskEnvelope`` was issued by an approval
          authority (``WISE_AUTHORITY``/``NODE_OWNER``) and names that tool —
          ``ThoughtProcessor._enforce_tool_approval`` ->
          ``authorization.tool_approval.envelope_approves_tool``. Absence of an
          envelope is denial; a DEPLOYMENT_RESOLVED envelope is denial even when
          it enumerates the tool.
        * Approval is **issuance, never widening**. ``TaskEnvelope`` is frozen
          and has no widening method, and the only producer of an approval
          envelope is ``WiseAuthorityService.resolve_deferral``, which mints it
          onto the **new** ``[WA GUIDANCE]`` task it creates when a human says
          yes — never onto the row this method touches.

        So a task resurrected by the clock alone re-enters the pipeline holding
        exactly the envelope it already had, which is not an approval; the gate
        denies the tool and defers again. The clock buys another round of
        thinking. Only a human buys the action. Locked by
        ``tests/ciris_engine/logic/infrastructure/authorization/test_timed_deferral_is_not_approval.py``.
        """
        from ciris_engine.logic.persistence import (
            get_task_by_id_any_occurrence,
            update_task_status,
            update_thought_status,
        )

        safe_deferred_id = _sanitize_for_log(deferred_task_id)
        logger.info(f"Reactivating deferred task {safe_deferred_id}")

        # Resolve the REAL deferred task row across occurrences — wakeup step
        # tasks live on the claiming occurrence, not necessarily "default".
        deferred_task = get_task_by_id_any_occurrence(deferred_task_id)
        if deferred_task is None:
            step_name = self._wakeup_step_name(deferred_task_id)
            if step_name:
                root_cause = (
                    f"wakeup step {step_name} cannot be re-activated: deferred task row "
                    "no longer exists — the wakeup sequence cannot complete"
                )
            else:
                root_cause = "deferred task row no longer exists — nothing to reactivate"
            self._dead_letter_task(task, root_cause)
            return False

        # (0) A human's answer outranks the clock (NULLWORKS RC3 F2). If the WA
        # resolved this deferral while the timer was still running, the task row
        # is already COMPLETED with its outcome recorded — approved work moved on
        # to a fresh [WA GUIDANCE] task, rejected work stopped. Flipping that row
        # back to ACTIVE would let an expiring timer re-open a question a human
        # has closed, and re-pend the very thought a WA refused. Not a
        # dead-letter: the deferral was answered, so the one-time scheduled task
        # retires normally on the caller's happy path.
        if deferred_task.status in RESOLVED_TASK_STATUSES:
            resolved_status = getattr(deferred_task.status, "value", deferred_task.status)
            logger.info(
                f"Reactivate {safe_deferred_id}: skipped — task is already "
                f"{_sanitize_for_log(str(resolved_status), 32)}, which means this deferral was "
                "resolved before the timer expired. A timer does not re-open a question a "
                "wise authority already answered."
            )
            return True

        occurrence_id = deferred_task.agent_occurrence_id

        # (1) Task: deferred -> ACTIVE. PENDING is NOT sufficient: only the
        # WORK processor promotes PENDING→ACTIVE (activate_pending_tasks), the
        # wakeup processor skips non-ACTIVE steps, and
        # get_pending_thoughts_for_active_tasks() filters thoughts to ACTIVE
        # tasks — so a task re-pended during WAKEUP left its thought invisible
        # and the agent kept spinning empty rounds (#934 layer B).
        if not update_task_status(deferred_task_id, TaskStatus.ACTIVE, occurrence_id):
            raise RuntimeError(f"failed to set deferred task {deferred_task_id} ACTIVE")

        # (2) Thought: re-pend the deferred thought. Setting the task ACTIVE
        # alone is NOT enough — get_tasks_needing_seed_thought only seeds
        # tasks that have ZERO thoughts, and the original deferred thought
        # still exists, so without this the thought stays DEFERRED forever
        # and the agent never reconsiders (the missing transition of #865).
        if task.origin_thought_id:
            if not update_thought_status(
                thought_id=task.origin_thought_id,
                status=ThoughtStatus.PENDING,
                occurrence_id=occurrence_id,
            ):
                logger.warning(
                    f"Reactivate {safe_deferred_id}: deferred thought "
                    f"{_sanitize_for_log(task.origin_thought_id)} not found to re-pend; "
                    "task is ACTIVE — processor will generate a fresh thought"
                )
            else:
                logger.info(
                    f"Reactivated deferred task {safe_deferred_id}: task ACTIVE + thought "
                    f"{_sanitize_for_log(task.origin_thought_id)} re-pended"
                )
        else:
            logger.info(
                f"Reactivated deferred task {safe_deferred_id}: task ACTIVE "
                "(no origin thought; a fresh seed thought will be generated)"
            )
        return True

    def _create_scheduled_thought(self, task: ScheduledTask) -> bool:
        """Create the trigger thought for a regular scheduled task.

        Returns True when the thought was created (normal completion follows);
        False when the task was dead-lettered because its FK target is gone.
        """
        from ciris_engine.logic.persistence import get_task_by_id_any_occurrence

        # Validate the FK target BEFORE inserting. A ScheduledTask can outlive
        # its task row (cleanup, data wipe, a one-time defer whose task already
        # completed); creating a thought with a dangling source_task_id violates
        # the thoughts→tasks foreign key ("FOREIGN KEY constraint failed") —
        # deterministically, on every trigger, forever. Quarantine instead (#934).
        source_task = get_task_by_id_any_occurrence(task.task_id)
        if source_task is None:
            self._dead_letter_task(
                task,
                "source task row does not exist — creating its thought would "
                "violate the thoughts→tasks foreign key on every trigger",
            )
            return False

        now_iso = (self._time_service.now() if self._time_service else datetime.now(timezone.utc)).isoformat()
        thought = Thought(
            thought_id=f"thought_{(self._time_service.now() if self._time_service else datetime.now(timezone.utc)).timestamp()}",
            content=task.trigger_prompt,
            status=ThoughtStatus.PENDING,
            thought_type=ThoughtType.SCHEDULED,
            source_task_id=task.task_id,
            agent_occurrence_id=source_task.agent_occurrence_id,
            created_at=now_iso,
            updated_at=now_iso,
            final_action=FinalAction(
                action_type="SCHEDULED_TASK",
                action_params={
                    "scheduled_task_id": task.task_id,
                    "scheduled_task_name": task.name,
                    "goal_description": task.goal_description,
                    "trigger_type": "scheduled",
                },
                reasoning=f"Scheduled task '{task.name}' triggered",
            ),
        )
        add_thought(thought)
        return True

    async def _trigger_task(self, task: ScheduledTask) -> None:
        """Trigger a scheduled task by creating a new thought or reactivating a deferred task."""
        # Sanitize for logging (CWE-117)
        safe_name = _sanitize_for_log(task.name)
        safe_task_id = _sanitize_for_log(task.task_id)
        try:
            logger.info(f"Triggering scheduled task: {safe_name} ({safe_task_id})")

            # Increment triggered counter
            self._tasks_triggered += 1

            # Check if this is a deferred task reactivation. The deferred task id
            # lives in deferral_history — ScheduledTask sets extra="forbid" and
            # has NO `.metadata` attribute, so the old `task.metadata` check was
            # dead code that silently never reactivated anything (#865). The
            # deferring thought is task.origin_thought_id.
            deferred_task_id: Optional[str] = None
            if task.deferral_history:
                last_entry = task.deferral_history[-1]
                if isinstance(last_entry, dict):
                    deferred_task_id = last_entry.get("deferred_task_id")

            if deferred_task_id:
                if not self._reactivate_deferred_task(task, deferred_task_id):
                    return  # dead-lettered — must not re-fire or count as triggered success
            else:
                if not self._create_scheduled_thought(task):
                    return  # dead-lettered

            # Update scheduled task status
            await self._update_task_triggered(task)

            # If one-time task, mark as complete
            if task.defer_until and not task.schedule_cron:
                await self._complete_task(task)

            # Success clears the consecutive-failure streak.
            self._task_failure_counts.pop(task.task_id, None)

        except Exception as trigger_error:
            # Increment failed counter
            self._tasks_failed += 1
            # Track CONSECUTIVE failures per task; after DEAD_LETTER_THRESHOLD
            # the task is quarantined with one ERROR instead of re-firing
            # every interval forever (#934).
            failures = self._task_failure_counts.get(task.task_id, 0) + 1
            self._task_failure_counts[task.task_id] = failures
            if failures >= DEAD_LETTER_THRESHOLD:
                self._dead_letter_task(
                    task,
                    f"{failures} consecutive trigger failures; last: "
                    f"{type(trigger_error).__name__}: {trigger_error}",
                )
            else:
                # Sanitize task_id for logging (CWE-117) - don't log exception details
                logger.error(
                    f"Failed to trigger task {safe_task_id}: task execution error "
                    f"(consecutive failure {failures}/{DEAD_LETTER_THRESHOLD})"
                )

    async def _update_task_triggered(self, task: ScheduledTask) -> None:
        """Update task after triggering."""
        now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        now_iso = now.isoformat()

        # Update in-memory task
        task.last_triggered_at = now
        if task.schedule_cron:
            task.status = "ACTIVE"
            # Calculate and log next trigger time for recurring tasks
            if CRONITER_AVAILABLE:
                try:
                    cron = croniter(task.schedule_cron, now)
                    next_time = cron.get_next(datetime)
                    logger.info(f"Task {task.name} will next trigger at {next_time.isoformat()}")
                except Exception as e:
                    logger.error(f"Failed to calculate next trigger time: {e}")

    async def _complete_task(self, task: ScheduledTask) -> None:
        """Mark a task as complete."""
        task.status = "COMPLETE"

        # Increment completed counter
        self._tasks_completed += 1

        # Remove from active tasks
        if task.task_id in self._active_tasks:
            del self._active_tasks[task.task_id]

    async def schedule_task(
        self,
        name: str,
        goal_description: str,
        trigger_prompt: str,
        origin_thought_id: str,
        defer_until: Optional[str] = None,
        schedule_cron: Optional[str] = None,
    ) -> ScheduledTask:
        """
        Schedule a new task.

        Args:
            name: Human-readable task name
            goal_description: What the task aims to achieve
            trigger_prompt: Prompt to use when creating the thought
            origin_thought_id: ID of the thought that created this task
            defer_until: ISO timestamp for one-time execution
            schedule_cron: Cron expression for recurring tasks (e.g. '0 9 * * *' for daily at 9am)

        Returns:
            The created ScheduledTask
        """
        # Validate cron expression if provided
        if schedule_cron:
            if not self._validate_cron_expression(schedule_cron):
                raise ValueError(f"Invalid cron expression: {schedule_cron}")

        task_id = f"task_{(self._time_service.now() if self._time_service else datetime.now(timezone.utc)).timestamp()}"

        task = self._create_scheduled_task(
            task_id=task_id,
            name=name,
            goal_description=goal_description,
            trigger_prompt=trigger_prompt,
            origin_thought_id=origin_thought_id,
            defer_until=defer_until,
            schedule_cron=schedule_cron,
        )

        # Add to active tasks
        self._active_tasks[task_id] = task

        # Increment task counters
        self._tasks_scheduled += 1
        if schedule_cron:
            self._recurring_tasks += 1
        else:
            self._oneshot_tasks += 1

        # Log scheduling details - sanitize user-controlled data to prevent log injection (CWE-117)
        safe_name = _sanitize_for_log(name)
        safe_task_id = _sanitize_for_log(task_id)
        if defer_until:
            # defer_until is validated datetime string, but sanitize anyway for defense in depth
            safe_defer = _sanitize_for_log(defer_until, max_length=30)
            logger.info(f"Scheduled one-time task: {safe_name} ({safe_task_id}) for {safe_defer}")
        elif schedule_cron:
            next_run = self._get_next_cron_time(schedule_cron)
            # schedule_cron is validated above, next_run is computed datetime
            logger.info(f"Scheduled recurring task: {safe_name} ({safe_task_id}). Next run: {next_run}")
        else:
            logger.info(f"Scheduled task: {safe_name} ({safe_task_id})")

        return task

    async def schedule_deferred_task(
        self, thought_id: str, task_id: str, defer_until: str, reason: str, context: Optional[JSONDict] = None
    ) -> ScheduledTask:
        """
        Schedule a deferred task for future reactivation.

        This is specifically for the DEFER handler to schedule tasks
        that should be reactivated at a specific time.

        Args:
            thought_id: ID of the thought that deferred
            task_id: ID of the task being deferred
            defer_until: ISO timestamp when to reactivate
            reason: Reason for deferral
            context: Additional context for the deferral

        Returns:
            The created ScheduledTask
        """
        name = f"Reactivate task {task_id}"
        goal_description = f"Reactivate deferred task: {reason}"
        trigger_prompt = f"Task {task_id} scheduled for reactivation"

        # Create the scheduled task
        scheduled_task = await self.schedule_task(
            name=name,
            goal_description=goal_description,
            trigger_prompt=trigger_prompt,
            origin_thought_id=thought_id,
            defer_until=defer_until,
            schedule_cron=None,  # One-time execution
        )

        # Store the deferral information in the deferral_history
        scheduled_task.deferral_count += 1
        scheduled_task.deferral_history.append(
            {
                "deferred_task_id": task_id,
                "deferral_reason": reason,
                "deferred_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        # Sanitize for logging (CWE-117)
        safe_task_id = _sanitize_for_log(task_id)
        safe_defer = _sanitize_for_log(defer_until, max_length=30)
        logger.info(f"Scheduled deferred task {safe_task_id} for reactivation at {safe_defer}")

        return scheduled_task

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a scheduled task.

        Args:
            task_id: ID of the task to cancel

        Returns:
            True if task was cancelled, False if not found
        """
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task.status = "CANCELLED"
            del self._active_tasks[task_id]
            self._task_failure_counts.pop(task_id, None)
            # Sanitize task name and ID for logging to prevent log injection (CWE-117)
            safe_name = _sanitize_for_log(task.name)
            safe_id = _sanitize_for_log(task_id)
            logger.info(f"Cancelled task: {safe_name} ({safe_id})")
            return True

        if task_id in self._dead_lettered_tasks:
            task = self._dead_lettered_tasks.pop(task_id)
            task.status = "CANCELLED"
            safe_name = _sanitize_for_log(task.name)
            safe_id = _sanitize_for_log(task_id)
            logger.info(f"Cleared dead-lettered task: {safe_name} ({safe_id})")
            return True

        return False

    async def get_scheduled_tasks(self) -> List[ScheduledTaskInfo]:
        """Get all scheduled tasks, including dead-lettered (status FAILED) ones."""
        tasks = []
        for task in list(self._active_tasks.values()) + list(self._dead_lettered_tasks.values()):
            tasks.append(
                ScheduledTaskInfo(
                    task_id=task.task_id,
                    name=task.name,
                    goal_description=task.goal_description,
                    status=task.status,
                    defer_until=task.defer_until.isoformat() if task.defer_until else None,
                    schedule_cron=task.schedule_cron,
                    created_at=(
                        task.created_at.isoformat() if isinstance(task.created_at, datetime) else task.created_at
                    ),
                    last_triggered_at=(
                        task.last_triggered_at.isoformat()
                        if task.last_triggered_at and isinstance(task.last_triggered_at, datetime)
                        else task.last_triggered_at
                    ),
                    deferral_count=task.deferral_count,
                )
            )
        return tasks

    async def _defer_task(self, task_id: str, defer_until: str, reason: str) -> bool:
        """
        Defer a task to a later time (internal method).

        Args:
            task_id: ID of the task to defer
            defer_until: New ISO timestamp for execution
            reason: Reason for deferral

        Returns:
            True if task was deferred, False if not found
        """
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            # Convert ISO string to datetime
            from datetime import datetime

            task.defer_until = datetime.fromisoformat(defer_until.replace("Z", "+00:00"))
            task.deferral_count += 1
            task.deferral_history.append(
                {
                    "deferred_at": (
                        self._time_service.now() if self._time_service else datetime.now(timezone.utc)
                    ).isoformat(),
                    "deferred_until": defer_until,
                    "reason": reason,
                }
            )
            # Sanitize for logging (CWE-117)
            safe_name = _sanitize_for_log(task.name)
            safe_task_id = _sanitize_for_log(task_id)
            safe_defer = _sanitize_for_log(defer_until, max_length=30)
            logger.info(f"Deferred task: {safe_name} ({safe_task_id}) until {safe_defer}")
            return True

        return False

    async def _handle_shutdown(self, context: ShutdownContext) -> None:
        """
        Handle graceful shutdown by preserving scheduled tasks (internal method).

        Args:
            context: Shutdown context with reason and reactivation info
        """
        logger.info(f"Handling shutdown for {len(self._active_tasks)} active tasks")

        # Save active tasks to database or file for persistence
        # This would be implemented based on the persistence strategy

        # If expected reactivation, log when tasks should resume
        if context.expected_reactivation:
            logger.info(
                f"Agent expected to reactivate at {context.expected_reactivation}. " "Tasks will resume at that time."
            )

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get base capabilities
        capabilities = super().get_capabilities()

        # Add custom metadata using model_copy
        if capabilities.metadata:
            capabilities.metadata = capabilities.metadata.model_copy(
                update={
                    "features": ["cron_scheduling", "one_time_defer", "task_persistence"],
                    "cron_support": CRONITER_AVAILABLE,
                    "description": "Task scheduling and deferral service",
                }
            )

        return capabilities

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect enhanced task scheduler metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate task success rate
        success_rate = 0.0
        total_finished = self._tasks_completed + self._tasks_failed
        if total_finished > 0:
            success_rate = self._tasks_completed / total_finished

        # Count recurring vs one-shot
        recurring = 0
        oneshot = 0
        for task in self._active_tasks.values():
            if task.schedule_cron:
                recurring += 1
            else:
                oneshot += 1

        metrics.update(
            {
                "active_tasks": float(len(self._active_tasks)),
                "check_interval": float(self.check_interval),
                "tasks_scheduled": float(self._tasks_scheduled),
                "tasks_triggered": float(self._tasks_triggered),
                "tasks_completed": float(self._tasks_completed),
                "tasks_failed": float(self._tasks_failed),
                "tasks_dead_lettered": float(len(self._dead_lettered_tasks)),
                "task_success_rate": success_rate,
                "recurring_tasks": float(recurring),
                "oneshot_tasks": float(oneshot),
            }
        )

        return metrics

    def _validate_cron_expression(self, cron_expr: str) -> bool:
        """
        Validate a cron expression.

        Args:
            cron_expr: Cron expression to validate

        Returns:
            True if valid, False otherwise
        """
        if not CRONITER_AVAILABLE:
            logger.warning("Cannot validate cron expression without croniter")
            return False

        try:
            # Try to create a croniter instance to validate
            croniter(cron_expr)
            return True
        except Exception as e:
            logger.debug(f"Invalid cron expression '{cron_expr}': {e}")
            return False

    def _get_next_cron_time(self, cron_expr: str) -> str:
        """
        Get the next scheduled time for a cron expression.

        Args:
            cron_expr: Cron expression

        Returns:
            ISO timestamp of next scheduled time, or 'unknown' if error
        """
        if not CRONITER_AVAILABLE:
            return "unknown (croniter not installed)"

        try:
            now = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            cron = croniter(cron_expr, now)
            next_time = cron.get_next(datetime)
            return str(next_time.isoformat())
        except Exception as e:
            logger.error(f"Failed to calculate next cron time: {e}")
            return "unknown"

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all task scheduler service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Add v1.4.3 specific scheduler metrics
        metrics.update(
            {
                "tasks_scheduled_total": float(self._tasks_scheduled),
                "tasks_completed_total": float(self._tasks_completed),
                "tasks_failed_total": float(self._tasks_failed),
                "tasks_dead_lettered": float(len(self._dead_lettered_tasks)),
                "tasks_pending": float(len(self._active_tasks)),
                "scheduler_uptime_seconds": self._calculate_uptime(),
            }
        )

        return metrics

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return bool(self._task and not self._shutdown_event.is_set())
