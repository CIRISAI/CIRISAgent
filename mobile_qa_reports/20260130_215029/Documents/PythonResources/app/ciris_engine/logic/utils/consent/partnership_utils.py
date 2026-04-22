"""
Partnership utilities for Consensual Evolution Protocol.

Helper functions for managing bilateral consent for PARTNERED stream upgrades.
Creates tasks that the agent can approve through thought system (REJECT/DEFER/TASK_COMPLETE).

Note: This is NOT a handler - it's a utility class used by ConsentService.
"""

import logging
import uuid
from typing import Any, Optional

from ciris_engine.logic import persistence
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext

logger = logging.getLogger(__name__)


class PartnershipRequestHandler:
    """Utility class for creating and checking partnership consent tasks.

    This is NOT a handler - it's a helper used by ConsentService to create
    tasks that actual handlers (REJECT/DEFER/TASK_COMPLETE) will process.
    """

    def __init__(self, time_service: TimeServiceProtocol, auth_service: Optional[object] = None):
        self.time_service = time_service
        self.auth_service = auth_service

    def create_partnership_task(
        self,
        user_id: str,
        categories: list[str],
        reason: Optional[str] = None,
        channel_id: Optional[str] = None,
    ) -> Task:
        """
        Create a task for the agent to approve/reject partnership request.

        Similar to shutdown tasks, the agent can:
        - TASK_COMPLETE: Accept partnership
        - REJECT: Decline partnership with reason
        - DEFER: Request more information or delay decision

        Args:
            user_id: User requesting partnership
            categories: Consent categories requested
            reason: User's reason for requesting partnership
            channel_id: Channel where request originated

        Returns:
            Created task for agent processing
        """
        now_iso = self.time_service.now().isoformat()
        task_id = f"partnership_{user_id}_{uuid.uuid4().hex[:8]}"

        # Format categories for description
        category_str = ", ".join(categories) if categories else "all categories"

        # Build task description
        description = f"Partnership request from {user_id} for {category_str}."
        if reason:
            description += f" Reason: {reason}"
        description += (
            "\n\nThis is a request for PARTNERED consent - mutual growth agreement. "
            "You may:\n"
            "- Accept (TASK_COMPLETE): Form partnership for mutual learning\n"
            "- Reject (REJECT): Decline with reason\n"
            "- Defer (DEFER): Request more information or time to consider"
        )

        # Create task context
        context = TaskContext(
            channel_id=channel_id or "",
            user_id=user_id,
            correlation_id=f"consent_partnership_{uuid.uuid4().hex[:8]}",
            parent_task_id=None,
        )

        # Create the task
        task = Task(
            task_id=task_id,
            channel_id=channel_id or "",
            description=description,
            priority=5,  # Medium priority
            status=TaskStatus.ACTIVE,
            created_at=now_iso,
            updated_at=now_iso,
            context=context,
            parent_task_id=None,
        )

        # Add task directly to persistence (like observers do)
        persistence.add_task(task)
        logger.info(f"Created partnership request task {task_id} for user {user_id}")

        return task

    def check_task_outcome(self, task_id: str) -> tuple[str, Optional[str]]:
        """
        Check the outcome of a partnership request task.

        Returns:
            Tuple of (outcome, reason) where outcome is:
            - "pending": Still being processed
            - "accepted": Partnership approved (TASK_COMPLETE)
            - "rejected": Partnership declined (REJECT action)
            - "deferred": More information needed (DEFER action)
            - "failed": Task failed for technical reasons
        """
        task = persistence.get_task_by_id(task_id)
        if not task:
            return ("failed", "Task not found")

        # Map simple status cases
        outcome = self._map_task_status(task.status)
        if outcome[0] != "check_thoughts":
            return outcome

        # For FAILED status, check thoughts for actual outcome
        return self._check_thoughts_for_outcome(task_id)

    def _map_task_status(self, status: TaskStatus) -> tuple[str, Optional[str]]:
        """Map task status to outcome, returning special marker for complex cases."""
        status_map = {
            TaskStatus.PENDING: ("pending", None),
            TaskStatus.ACTIVE: ("pending", None),
            TaskStatus.COMPLETED: ("accepted", "Partnership approved by agent"),
            TaskStatus.REJECTED: ("rejected", "Request was rejected"),
            TaskStatus.DEFERRED: ("deferred", "Request was deferred"),
            TaskStatus.FAILED: ("check_thoughts", None),  # Special marker
        }
        return status_map.get(status, ("pending", None))

    def _check_thoughts_for_outcome(self, task_id: str) -> tuple[str, Optional[str]]:
        """Check thoughts to determine outcome for failed tasks."""
        thoughts = persistence.get_thoughts_by_task_id(task_id)
        if not thoughts:
            return ("failed", "Task failed without clear reason")

        for thought in reversed(thoughts):
            outcome = self._extract_action_from_thought(thought)
            if outcome:
                return outcome

        return ("failed", "Task failed without clear reason")

    def _extract_action_from_thought(self, thought: Any) -> Optional[tuple[str, str]]:
        """Extract action outcome from a single thought."""
        if not hasattr(thought, "final_action") or not thought.final_action:
            return None

        action = thought.final_action

        if action.action_type == "REJECT":
            reason = self._extract_reason_from_params(action.action_params, "No reason provided")
            return ("rejected", reason)

        if action.action_type == "DEFER":
            reason = self._extract_reason_from_params(action.action_params, "More information needed")
            return ("deferred", reason)

        return None

    def _extract_reason_from_params(self, params: Any, default: str) -> str:
        """Extract reason from action params safely."""
        if isinstance(params, dict):
            return str(params.get("reason", default))
        return default
