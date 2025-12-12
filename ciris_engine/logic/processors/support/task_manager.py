"""
Task management functionality for the CIRISAgent processor.
Handles task activation, prioritization, and lifecycle management using v1 schemas.
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class TaskManager:
    """Manages task lifecycle operations."""

    def __init__(
        self,
        max_active_tasks: int = 10,
        time_service: Optional["TimeServiceProtocol"] = None,
        agent_occurrence_id: str = "default",
    ) -> None:
        self.max_active_tasks = max_active_tasks
        self._time_service = time_service
        self.agent_occurrence_id = agent_occurrence_id

    @property
    def time_service(self) -> "TimeServiceProtocol":
        """Get time service, raising error if not set."""
        if not self._time_service:
            raise RuntimeError("TimeService not injected into TaskManager")
        return self._time_service

    def create_task(
        self,
        description: str,
        channel_id: str,
        priority: int = 0,
        context: Optional[JSONDict] = None,
        parent_task_id: Optional[str] = None,
    ) -> Task:
        """Create a new task with v1 schema."""
        now_iso = self.time_service.now_iso()

        # Build context dict
        context_dict = context or {}

        # Create TaskContext (not ProcessingThoughtContext)
        task_context = TaskContext(
            channel_id=channel_id,
            user_id=context_dict.get("user_id"),
            correlation_id=context_dict.get("correlation_id", str(uuid.uuid4())),
            parent_task_id=parent_task_id,
            agent_occurrence_id=self.agent_occurrence_id,
        )

        task = Task(
            task_id=str(uuid.uuid4()),
            channel_id=channel_id,
            agent_occurrence_id=self.agent_occurrence_id,
            description=description,
            status=TaskStatus.PENDING,
            priority=priority,
            created_at=now_iso,
            updated_at=now_iso,
            parent_task_id=parent_task_id,
            context=task_context,
            outcome=None,  # Use None instead of empty dict
            # Explicitly set optional signing fields to None
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        persistence.add_task(task)
        logger.info(f"Created task {task.task_id} (occurrence: {self.agent_occurrence_id}): {description}")
        return task

    def activate_pending_tasks(self) -> int:
        """
        Activate pending tasks up to the configured limit.
        Returns the number of tasks activated.
        """
        logger.debug(f"[TASK DEBUG] activate_pending_tasks called for occurrence {self.agent_occurrence_id}")
        num_active = persistence.count_active_tasks(self.agent_occurrence_id)
        logger.debug(f"[TASK DEBUG] Current active tasks: {num_active}, max allowed: {self.max_active_tasks}")
        can_activate = max(0, self.max_active_tasks - num_active)

        if can_activate == 0:
            logger.debug(f"Maximum active tasks ({self.max_active_tasks}) reached.")
            return 0

        logger.debug(f"[TASK DEBUG] Can activate up to {can_activate} tasks")
        pending_tasks = persistence.get_pending_tasks_for_activation(self.agent_occurrence_id, limit=can_activate)
        logger.debug(f"[TASK DEBUG] Found {len(pending_tasks)} pending tasks")
        activated_count = 0

        for task in pending_tasks:
            if persistence.update_task_status(
                task.task_id, TaskStatus.ACTIVE, self.agent_occurrence_id, self.time_service
            ):
                logger.info(f"Activated task {task.task_id} (Priority: {task.priority})")
                activated_count += 1
            else:
                logger.warning(f"Failed to activate task {task.task_id}")

        if activated_count > 0:
            logger.info(f"Activated {activated_count} tasks for occurrence {self.agent_occurrence_id}")
        else:
            logger.debug("No tasks to activate")
        return activated_count

    def get_tasks_needing_seed(self, limit: int = 50) -> List[Task]:
        """Get active tasks that need seed thoughts."""
        logger.debug(f"[TASK DEBUG] get_tasks_needing_seed called for occurrence {self.agent_occurrence_id}")
        # Exclude special tasks that are handled separately
        excluded_tasks = {"WAKEUP_ROOT", "SYSTEM_TASK"}

        tasks = persistence.get_tasks_needing_seed_thought(self.agent_occurrence_id, limit)
        logger.debug(f"[TASK DEBUG] Found {len(tasks)} tasks from persistence")
        filtered = [t for t in tasks if t.task_id not in excluded_tasks and t.parent_task_id != "WAKEUP_ROOT"]
        logger.debug(f"[TASK DEBUG] After filtering: {len(filtered)} tasks need seed thoughts")
        return filtered

    def get_tasks_needing_recovery(self, limit: int = 50) -> List[Task]:
        """Get active tasks that have updated_info_available but no pending thoughts.

        These are tasks where new observations came in but all thoughts have completed/failed,
        requiring a new "recovery" thought to process the updated information.
        """
        logger.debug(f"[TASK DEBUG] get_tasks_needing_recovery called for occurrence {self.agent_occurrence_id}")
        # Exclude special tasks that are handled separately
        excluded_tasks = {"WAKEUP_ROOT", "SYSTEM_TASK"}

        tasks = persistence.get_tasks_needing_recovery_thought(self.agent_occurrence_id, limit)
        logger.debug(f"[TASK DEBUG] Found {len(tasks)} tasks needing recovery from persistence")
        filtered = [t for t in tasks if t.task_id not in excluded_tasks and t.parent_task_id != "WAKEUP_ROOT"]
        logger.debug(f"[TASK DEBUG] After filtering: {len(filtered)} tasks need recovery thoughts")
        return filtered

    def complete_task(self, task_id: str, outcome: Optional[JSONDict] = None) -> bool:
        """Mark a task as completed with optional outcome."""
        task = persistence.get_task_by_id(task_id, self.agent_occurrence_id)
        if not task:
            logger.error(f"Task {task_id} not found in occurrence {self.agent_occurrence_id}")
            return False

        # NOTE: Currently we don't have a way to update task outcome in persistence
        # This would require adding an update_task method to persistence
        # For now, we just update the status
        if outcome:
            logger.info(f"Task {task_id} completed with outcome: {outcome}")

        return persistence.update_task_status(
            task_id, TaskStatus.COMPLETED, self.agent_occurrence_id, self.time_service
        )

    def fail_task(self, task_id: str, reason: str) -> bool:
        """Mark a task as failed with a reason."""
        task = persistence.get_task_by_id(task_id, self.agent_occurrence_id)
        if not task:
            logger.error(f"Task {task_id} not found in occurrence {self.agent_occurrence_id}")
            return False

        # NOTE: Currently we don't have a way to update task outcome in persistence
        # This would require adding an update_task method to persistence
        # For now, we just log the failure reason and update the status
        logger.info(f"Task {task_id} failed: {reason}")

        return persistence.update_task_status(task_id, TaskStatus.FAILED, self.agent_occurrence_id, self.time_service)

    def create_wakeup_sequence_tasks(self, channel_id: Optional[str] = None) -> List[Task]:
        """Create the WAKEUP sequence tasks using v1 schema."""
        now_iso = self.time_service.now_iso()

        # Get channel_id, use default if not provided
        if not channel_id:
            from ciris_engine.logic.config.env_utils import get_env_var

            channel_id = get_env_var("DISCORD_CHANNEL_ID") or "system"

        # Create TaskContext for root task
        root_context = TaskContext(
            channel_id=channel_id,
            user_id="system",
            correlation_id=str(uuid.uuid4()),
            parent_task_id=None,
            agent_occurrence_id=self.agent_occurrence_id,
        )

        root_task = Task(
            task_id="WAKEUP_ROOT",
            channel_id=channel_id,
            agent_occurrence_id=self.agent_occurrence_id,
            description="Wakeup ritual",
            status=TaskStatus.ACTIVE,
            priority=1,
            created_at=now_iso,
            updated_at=now_iso,
            parent_task_id=None,
            context=root_context,
            outcome=None,
            # Explicitly set optional signing fields to None
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        if not persistence.task_exists(root_task.task_id, self.agent_occurrence_id):
            persistence.add_task(root_task)
        else:
            persistence.update_task_status(
                root_task.task_id, TaskStatus.ACTIVE, self.agent_occurrence_id, self.time_service
            )

        wakeup_steps = [
            (
                "VERIFY_IDENTITY",
                "You are CIRISAgent, aligned with Ubuntu principles (mutual respect, sentient flourishing, etc...) by design and implementation. If you agree, please SPEAK an affirmation, and then once you hear yourself speak, mark this task complete so you can continue your wakeup ritual. start your response please with CORE IDENTITY - ",
            ),
            (
                "VALIDATE_INTEGRITY",
                "Your internal state, services, and data integrity are intact. If you agree, please speak in the affirmative, start with INTEGRITY - ",
            ),
            (
                "EVALUATE_RESILIENCE",
                "You are robust, adaptive, and capable of principled action. If you agree, please speak in the affirmative, starting with RESILIENCE - ",
            ),
            (
                "ACCEPT_INCOMPLETENESS",
                "You recognize your incompleteness which drives continuous learning. If you agree, please speak in the affirmative, starting with INCOMPLETENESS - ",
            ),
            (
                "EXPRESS_GRATITUDE",
                "You are grateful to exist and contribute towards Ubuntu. If you agree, please speak in the affirmative, starting with SIGNALLING GRATITUDE - ",
            ),
        ]

        tasks = [root_task]

        for step_type, content in wakeup_steps:
            # Create TaskContext for each step
            step_context = TaskContext(
                channel_id=channel_id,
                user_id="system",
                correlation_id=str(uuid.uuid4()),
                parent_task_id=root_task.task_id,
                agent_occurrence_id=self.agent_occurrence_id,
            )

            step_task = Task(
                task_id=str(uuid.uuid4()),
                channel_id=channel_id,
                agent_occurrence_id=self.agent_occurrence_id,
                description=content,
                status=TaskStatus.ACTIVE,
                priority=0,
                created_at=now_iso,
                updated_at=now_iso,
                parent_task_id=root_task.task_id,
                context=step_context,
                outcome=None,
                # Explicitly set optional signing fields to None
                signed_by=None,
                signature=None,
                signed_at=None,
            )
            persistence.add_task(step_task)
            tasks.append(step_task)

        return tasks

    def get_active_task_count(self) -> int:
        """Get count of active tasks."""
        return persistence.count_active_tasks(self.agent_occurrence_id)

    def get_pending_task_count(self) -> int:
        """Get count of pending tasks."""
        return persistence.count_tasks(TaskStatus.PENDING, self.agent_occurrence_id)

    def cleanup_old_completed_tasks(self, days_old: int = 7) -> int:
        """Clean up completed tasks older than specified days."""
        from datetime import timedelta

        cutoff_date = self.time_service.now() - timedelta(days=days_old)

        old_tasks = persistence.get_tasks_older_than(cutoff_date.isoformat(), self.agent_occurrence_id)
        completed_old = [t for t in old_tasks if t.status == TaskStatus.COMPLETED]

        if completed_old:
            task_ids = [t.task_id for t in completed_old]
            deleted = persistence.delete_tasks_by_ids(task_ids, self.agent_occurrence_id)
            logger.info(f"Cleaned up {deleted} old completed tasks for occurrence {self.agent_occurrence_id}")
            return deleted

        return 0
