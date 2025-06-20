"""
Task Scheduler Service

This service manages scheduled tasks and proactive goals for CIRIS agents.
It integrates with the time-based DEFER system to enable agents to schedule
their own future actions with human approval.

"I defer to tomorrow what I cannot complete today" - Agent self-management
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Set
import json

from ciris_engine.adapters.base import Service
from ciris_engine.schemas.foundational_schemas_v1 import ServiceType, ThoughtStatus, ThoughtType
from ciris_engine.schemas.identity_schemas_v1 import ScheduledTask, ShutdownContext
from ciris_engine.schemas.deferral_schemas_v1 import DeferralPackage, DeferralReason
from ciris_engine.schemas.agent_core_schemas_v1 import Thought, Task
from ciris_engine.schemas.action_params_v1 import DeferParams
from ciris_engine.persistence import (
    get_db_connection,
    add_thought,
    get_thought_by_id,
    update_thought_status,
    update_task_status
)

logger = logging.getLogger(__name__)

# Try to import croniter for cron scheduling support
try:
    from croniter import croniter  # type: ignore[import-untyped]
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False
    logger.warning("croniter not installed. Cron scheduling will be disabled.")


class TaskSchedulerService(Service):
    """
    Manages scheduled tasks and integrates with the DEFER system.
    
    This service enables agents to be proactive by scheduling future actions,
    either through one-time deferrals or recurring schedules.
    """
    
    def __init__(
        self,
        db_path: str,
        check_interval_seconds: int = 60
    ):
        super().__init__()
        self.db_path = db_path
        self.conn = None
        self.check_interval = check_interval_seconds
        self._scheduler_task: Optional[asyncio.Task] = None
        self._active_tasks: Dict[str, ScheduledTask] = {}
        self._shutdown_event = asyncio.Event()
        
    async def start(self) -> None:
        """Start the scheduler service."""
        await super().start()
        
        # Load active tasks from database
        await self._load_active_tasks()
        
        # Start the scheduler loop
        self._scheduler_task = asyncio.create_task(self._scheduler_loop())
        
        logger.info(
            f"TaskSchedulerService started with {len(self._active_tasks)} active tasks"
        )
        
    async def stop(self) -> None:
        """Stop the scheduler service gracefully."""
        self._shutdown_event.set()
        
        if self._scheduler_task:
            await self._scheduler_task
            
        await super().stop()
        logger.info("TaskSchedulerService stopped")
        
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
        schedule_cron: Optional[str] = None
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
            created_at=datetime.now(timezone.utc).isoformat(),
            last_triggered_at=None,
            deferral_count=0,
            deferral_history=[]
        )
        
    async def _scheduler_loop(self) -> None:
        """Main scheduler loop that checks for due tasks."""
        while not self._shutdown_event.is_set():
            try:
                # Check for due tasks
                now = datetime.now(timezone.utc)
                due_tasks = self._get_due_tasks(now)
                
                for task in due_tasks:
                    await self._trigger_task(task)
                    
                # Wait for next check interval
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(self.check_interval)
                
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
            defer_time = datetime.fromisoformat(task.defer_until.replace('Z', '+00:00'))
            return current_time >= defer_time
            
        # Cron-style recurring task
        if task.schedule_cron:
            return self._should_trigger_cron(task, current_time)
            
        return False
    
    def _should_trigger_cron(self, task: ScheduledTask, current_time: datetime) -> bool:
        """Check if a cron-scheduled task should trigger."""
        if not CRONITER_AVAILABLE:
            logger.warning(
                f"Cron scheduling requested for task {task.task_id} but croniter not installed"
            )
            return False
            
        try:
            # If never triggered, use creation time as base
            if not task.last_triggered_at:
                base_time = datetime.fromisoformat(task.created_at.replace('Z', '+00:00'))
            else:
                base_time = datetime.fromisoformat(task.last_triggered_at.replace('Z', '+00:00'))
            
            # Create croniter instance
            cron = croniter(task.schedule_cron, base_time)
            
            # Get next scheduled time
            next_time = cron.get_next(datetime)
            
            # Check if we've passed the next scheduled time
            # Add a small buffer (1 second) to avoid missing triggers due to timing
            return bool(current_time >= next_time - timedelta(seconds=1))
            
        except Exception as e:
            logger.error(
                f"Invalid cron expression '{task.schedule_cron}' for task {task.task_id}: {e}"
            )
            return False
        
    async def _trigger_task(self, task: ScheduledTask) -> None:
        """Trigger a scheduled task by creating a new thought."""
        try:
            logger.info(f"Triggering scheduled task: {task.name} ({task.task_id})")
            
            # Create a new thought for this task
            thought = Thought(
                thought_id=f"thought_{datetime.now(timezone.utc).timestamp()}",
                content=task.trigger_prompt,
                status=ThoughtStatus.PENDING,
                thought_type=ThoughtType.SCHEDULED,
                source_task_id=task.task_id,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                final_action={
                    "scheduled_task_id": task.task_id,
                    "scheduled_task_name": task.name,
                    "goal_description": task.goal_description,
                    "trigger_type": "scheduled"
                }
            )
            
            # Add thought to database
            add_thought(thought, db_path=self.db_path)
            
            # Update scheduled task status
            await self._update_task_triggered(task)
            
            # If one-time task, mark as complete
            if task.defer_until and not task.schedule_cron:
                await self._complete_task(task)
                
        except Exception as e:
            logger.error(f"Failed to trigger task {task.task_id}: {e}")
            
    async def _update_task_triggered(self, task: ScheduledTask) -> None:
        """Update task after triggering."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        
        # Update in-memory task
        task.last_triggered_at = now_iso
        if task.schedule_cron:
            task.status = "ACTIVE"
            # Calculate and log next trigger time for recurring tasks
            if CRONITER_AVAILABLE:
                try:
                    cron = croniter(task.schedule_cron, now)
                    next_time = cron.get_next(datetime)
                    logger.info(
                        f"Task {task.name} will next trigger at {next_time.isoformat()}"
                    )
                except Exception as e:
                    logger.error(f"Failed to calculate next trigger time: {e}")
            
    async def _complete_task(self, task: ScheduledTask) -> None:
        """Mark a task as complete."""
        task.status = "COMPLETE"
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
        schedule_cron: Optional[str] = None
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
                
        task_id = f"task_{datetime.now(timezone.utc).timestamp()}"
        
        task = self._create_scheduled_task(
            task_id=task_id,
            name=name,
            goal_description=goal_description,
            trigger_prompt=trigger_prompt,
            origin_thought_id=origin_thought_id,
            defer_until=defer_until,
            schedule_cron=schedule_cron
        )
        
        # Add to active tasks
        self._active_tasks[task_id] = task
        
        # Log scheduling details
        if defer_until:
            logger.info(f"Scheduled one-time task: {name} ({task_id}) for {defer_until}")
        elif schedule_cron:
            next_run = self._get_next_cron_time(schedule_cron)
            logger.info(
                f"Scheduled recurring task: {name} ({task_id}) with cron '{schedule_cron}'. "
                f"Next run: {next_run}"
            )
        else:
            logger.info(f"Scheduled task: {name} ({task_id})")
            
        return task
        
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
        
    async def get_active_tasks(self) -> List[ScheduledTask]:
        """Get all active scheduled tasks."""
        return list(self._active_tasks.values())
        
    async def defer_task(
        self,
        task_id: str,
        defer_until: str,
        reason: str
    ) -> bool:
        """
        Defer a task to a later time.
        
        Args:
            task_id: ID of the task to defer
            defer_until: New ISO timestamp for execution
            reason: Reason for deferral
            
        Returns:
            True if task was deferred, False if not found
        """
        if task_id in self._active_tasks:
            task = self._active_tasks[task_id]
            task.defer_until = defer_until
            task.deferral_count += 1
            task.deferral_history.append({
                "deferred_at": datetime.now(timezone.utc).isoformat(),
                "deferred_until": defer_until,
                "reason": reason
            })
            logger.info(f"Deferred task: {task.name} ({task_id}) until {defer_until}")
            return True
            
        return False
        
    async def handle_shutdown(self, context: ShutdownContext) -> None:
        """
        Handle graceful shutdown by preserving scheduled tasks.
        
        Args:
            context: Shutdown context with reason and reactivation info
        """
        logger.info(f"Handling shutdown for {len(self._active_tasks)} active tasks")
        
        # Save active tasks to database or file for persistence
        # This would be implemented based on the persistence strategy
        
        # If expected reactivation, log when tasks should resume
        if context.expected_reactivation:
            logger.info(
                f"Agent expected to reactivate at {context.expected_reactivation}. "
                f"Tasks will resume at that time."
            )
            
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
            now = datetime.now(timezone.utc)
            cron = croniter(cron_expr, now)
            next_time = cron.get_next(datetime)
            return str(next_time.isoformat())
        except Exception as e:
            logger.error(f"Failed to calculate next cron time: {e}")
            return "unknown"