"""
UpdatedStatusConscience - Detects when new information arrived for an active task.

This is the 6th conscience check and runs FIRST before all others.
It checks if the task has the updated_info_available flag set, indicating
that a new observation arrived in the same channel after the task started
processing but before conscience checks completed.

When detected, it forces a PONDER override to incorporate the new information.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ciris_engine.logic.conscience.interface import ConscienceInterface
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

logger = logging.getLogger(__name__)


class UpdatedStatusConscience(ConscienceInterface):
    """
    Conscience check that detects when new observations arrived during processing.

    This check runs FIRST (before entropy, coherence, etc.) and has priority
    override capability. When a new observation arrives in the same channel as
    an active task that hasn't completed conscience yet, this check forces the
    action to PONDER with the updated context.
    """

    def __init__(self, time_service: Optional[Any] = None) -> None:
        """Initialize the updated status conscience.

        Args:
            time_service: Optional time service for timestamps
        """
        self._time_service = time_service

    async def check(self, action: ActionSelectionDMAResult, context: ConscienceCheckContext) -> ConscienceCheckResult:
        """Check if the task has new information available.

        Args:
            action: The selected action to check
            context: Typed context containing the thought and task information

        Returns:
            ConscienceCheckResult with FAILED status if update detected, PASSED otherwise
        """
        ts_datetime = self._time_service.now() if self._time_service else datetime.now(timezone.utc)

        # Get the thought from context
        thought = context.thought
        if not thought:
            # No thought in context - pass
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=ts_datetime,
                original_action=action.model_dump(),
                updated_status_detected=False,
            )

        # Get task from thought
        from ciris_engine.logic.persistence.models.tasks import get_task_by_id

        task_id = thought.source_task_id if hasattr(thought, "source_task_id") else None
        if not task_id:
            # No task ID - pass
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=ts_datetime,
                original_action=action.model_dump(),
                updated_status_detected=False,
            )

        # Fetch the task
        task = get_task_by_id(task_id)
        if not task:
            # Task not found - pass
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=ts_datetime,
                original_action=action.model_dump(),
                updated_status_detected=False,
            )

        # Check if updated_info_available flag is set
        updated_flag = getattr(task, "updated_info_available", False)
        if not updated_flag:
            # No update - pass
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=ts_datetime,
                original_action=action.model_dump(),
                updated_status_detected=False,
            )

        # Update detected! Clear the flag and force PONDER
        updated_content = getattr(task, "updated_info_content", "New observation received")

        # Get the original action description and channel info
        original_action_desc = (
            action.selected_action if isinstance(action.selected_action, str) else action.selected_action.value
        )
        channel_id = getattr(task, "channel_id", "this channel")

        # Clear the flag so this only triggers once
        from ciris_engine.logic.persistence.db import get_db_connection

        try:
            with get_db_connection() as conn:
                conn.execute("UPDATE tasks SET updated_info_available = 0 WHERE task_id = ?", (task_id,))
                conn.commit()
                logger.info(f"Cleared updated_info_available flag for task {task_id}")
        except Exception as e:
            logger.error(f"Failed to clear updated_info_available flag for task {task_id}: {e}")

        # Note: The observation is stored in ConscienceCheckResult.CIRIS_OBSERVATION_UPDATED_STATUS
        # (top-level field below) so it can be accessed by downstream processing without modifying
        # the immutable Thought object. The Thought schema does not have a 'payload' field.

        # Create PONDER questions with contextual information
        questions = [
            f"I was going to {original_action_desc} in channel {channel_id}, but a new message arrived before I could.",
            f"The new observation: {updated_content}",
            "Should I revise my action based on this new information?",
        ]

        # Create the PONDER action that will replace the original
        ponder_action = ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=questions, channel_id=channel_id),
            rationale="Updated status detected - new observation in channel requires reconsideration",
            raw_llm_response=None,
        )

        # Return FAILED status with the update reason
        # replacement_action and CIRIS_OBSERVATION_UPDATED_STATUS are now top-level fields
        return ConscienceCheckResult(
            status=ConscienceStatus.FAILED,
            passed=False,
            reason=f"New observation arrived during processing: {updated_content[:100]}...",
            replacement_action=ponder_action.model_dump(),  # Top-level field in ConscienceCheckResult
            CIRIS_OBSERVATION_UPDATED_STATUS=updated_content,  # Top-level field in ConscienceCheckResult
            check_timestamp=ts_datetime,
            original_action=action.model_dump(),
            updated_status_detected=True,
        )
