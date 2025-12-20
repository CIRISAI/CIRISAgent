"""
Task Scheduler Service

This service manages scheduled tasks and proactive goals for CIRIS agents.
It integrates with the time-based DEFER system to enable agents to schedule
their own future actions with human approval.

"I defer to tomorrow what I cannot complete today" - Agent self-management
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.logic.persistence import add_thought, get_db_connection
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.protocols.services import ServiceProtocol as TaskSchedulerServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.extended import ScheduledTask, ScheduledTaskInfo, ShutdownContext
from ciris_engine.schemas.runtime.models import FinalAction, Thought
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Try to import croniter for cron scheduling support
try:
    from croniter import croniter

    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    logger.warning("croniter not installed. Cron scheduling will be disabled.")


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

        # Task tracking metrics
        self._tasks_scheduled = 0
        self._tasks_triggered = 0
        self._tasks_completed = 0
        self._tasks_failed = 0
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
        """Load all active tasks from the database."""
        try:
            if not self.conn:
                self.conn = get_db_connection(self.db_path)  # type: ignore[assignment]

            # For now, we'll use the existing thought/task tables
            # In the future, this could be a dedicated scheduled_tasks table
            logger.info("Loading active scheduled tasks")

        except Exception as e:
            logger.error(f"Failed to load active tasks: {e}")

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
            logger.warning(f"Cron scheduling requested for task {task.task_id} but croniter not installed")
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

        except Exception as e:
            logger.error(f"Invalid cron expression '{task.schedule_cron}' for task {task.task_id}: {e}")
            return False

    async def _trigger_task(self, task: ScheduledTask) -> None:
        """Trigger a scheduled task by creating a new thought or reactivating a deferred task."""
        try:
            logger.info(f"Triggering scheduled task: {task.name} ({task.task_id})")

            # Increment triggered counter
            self._tasks_triggered += 1

            # Check if this is a deferred task reactivation
            if hasattr(task, "metadata") and task.metadata and "deferred_task_id" in task.metadata:
                # Reactivate the deferred task
                deferred_task_id = task.metadata["deferred_task_id"]
                logger.info(f"Reactivating deferred task {deferred_task_id}")

                # Update the task status from 'deferred' to 'pending'
                from ciris_engine.logic.persistence import update_task_status
                from ciris_engine.schemas.runtime.enums import TaskStatus

                if self._time_service:
                    update_task_status(deferred_task_id, TaskStatus.PENDING, "default", self._time_service)
                else:
                    # If no time service available, skip updating the task
                    logger.warning(f"Cannot update task {deferred_task_id} status: no time service available")

                logger.info(f"Task {deferred_task_id} reactivated and marked as pending")

            else:
                # Create a new thought for regular scheduled tasks
                thought = Thought(
                    thought_id=f"thought_{(self._time_service.now() if self._time_service else datetime.now(timezone.utc)).timestamp()}",
                    content=task.trigger_prompt,
                    status=ThoughtStatus.PENDING,
                    thought_type=ThoughtType.SCHEDULED,
                    source_task_id=task.task_id,
                    agent_occurrence_id="default",  # Scheduled tasks run on default occurrence
                    created_at=(
                        self._time_service.now() if self._time_service else datetime.now(timezone.utc)
                    ).isoformat(),
                    updated_at=(
                        self._time_service.now() if self._time_service else datetime.now(timezone.utc)
                    ).isoformat(),
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

                # Add thought to database
                add_thought(thought, db_path=self.db_path)

            # Update scheduled task status
            await self._update_task_triggered(task)

            # If one-time task, mark as complete
            if task.defer_until and not task.schedule_cron:
                await self._complete_task(task)

        except Exception as e:
            # Increment failed counter
            self._tasks_failed += 1
            logger.error(f"Failed to trigger task {task.task_id}: {e}")

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

        # Log scheduling details
        if defer_until:
            logger.info(f"Scheduled one-time task: {name} ({task_id}) for {defer_until}")
        elif schedule_cron:
            next_run = self._get_next_cron_time(schedule_cron)
            logger.info(
                f"Scheduled recurring task: {name} ({task_id}) with cron '{schedule_cron}'. " f"Next run: {next_run}"
            )
        else:
            logger.info(f"Scheduled task: {name} ({task_id})")

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

        logger.info(f"Scheduled deferred task {task_id} for reactivation at {defer_until}")

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
            logger.info(f"Cancelled task: {task.name} ({task_id})")
            return True

        return False

    async def get_scheduled_tasks(self) -> List[ScheduledTaskInfo]:
        """Get all scheduled tasks."""
        tasks = []
        for task in self._active_tasks.values():
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
            logger.info(f"Deferred task: {task.name} ({task_id}) until {defer_until}")
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
                "tasks_pending": float(len(self._active_tasks)),
                "scheduler_uptime_seconds": self._calculate_uptime(),
            }
        )

        return metrics

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return bool(self._task and not self._shutdown_event.is_set())
