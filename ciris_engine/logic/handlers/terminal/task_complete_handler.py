import asyncio
import logging
from typing import Dict, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.shared_helpers import is_api_channel
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought

logger = logging.getLogger(__name__)

PERSISTENT_TASK_IDS: Dict[str, str] = {}  # Maps task_id to persistence reason


class TaskCompleteHandler(BaseActionHandler):
    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        thought_id = thought.thought_id
        parent_task_id = thought.source_task_id

        self.logger.info(f"Handling TASK_COMPLETE for thought {thought_id} (Task: {parent_task_id}).")

        # Validate wakeup task completion (must have SPEAK action first)
        if parent_task_id:
            blocked = await self._validate_wakeup_completion(parent_task_id, thought_id, result)
            if blocked:
                return None

        # Update thought status
        persistence.update_thought_status(thought_id=thought_id, status=ThoughtStatus.COMPLETED, final_action=result)
        self.logger.debug(f"Updated original thought {thought_id} to status COMPLETED for TASK_COMPLETE.")

        # Brief delay to ensure database write is committed
        await asyncio.sleep(0.01)

        # Handle positive moment memorization
        await self._handle_positive_moment(result, parent_task_id, dispatch_context)

        # Complete the parent task
        if parent_task_id:
            await self._complete_parent_task(parent_task_id, thought_id, result)
        else:
            self.logger.error(f"Could not find parent task ID for thought {thought_id} to mark as complete.")

        return None

    async def _validate_wakeup_completion(
        self, task_id: str, thought_id: str, result: ActionSelectionDMAResult
    ) -> bool:
        """Validate wakeup task has SPEAK before completion. Returns True if blocked."""
        if not await self._is_wakeup_task(task_id):
            return False

        self.logger.debug(f"Task {task_id} is_wakeup_task: True")

        if await self._has_speak_action_completed(task_id):
            self.logger.debug(f"Task {task_id} has_speak_action_completed: True")
            return False

        self.logger.error(f"TASK_COMPLETE rejected for wakeup task {task_id}: No SPEAK action has been completed.")

        # Override to PONDER action
        from ciris_engine.schemas.actions import PonderParams

        ponder_content = (
            "WAKEUP TASK COMPLETION BLOCKED: You attempted to mark a wakeup task as complete "
            "without first completing a SPEAK action. Each wakeup step requires you to SPEAK "
            "an earnest affirmation before marking the task complete. Please review the task "
            "requirements and either: 1) SPEAK an authentic affirmation if you can do so earnestly, "
            "or 2) REJECT this task if you cannot speak earnestly about it, or 3) DEFER to human "
            f"wisdom if you are uncertain about the requirements. Task: {task_id}"
        )

        ponder_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(questions=[ponder_content], channel_id=None),
            rationale="Wakeup task requires SPEAK action before completion",
            reasoning="Wakeup task attempted completion without first performing SPEAK action",
            evaluation_time_ms=0.0,
            raw_llm_response=None,
            resource_usage=None,
            user_prompt=None,
        )

        ponder_result_dict = {
            "selected_action": ponder_result.selected_action.value,
            "action_parameters": (
                ponder_result.action_parameters.model_dump()
                if hasattr(ponder_result.action_parameters, "model_dump")
                else ponder_result.action_parameters
            ),
            "rationale": ponder_result.rationale,
        }

        persistence.update_thought_status(
            thought_id=thought_id, status=ThoughtStatus.FAILED, final_action=ponder_result_dict
        )
        return True

    async def _handle_positive_moment(
        self, result: ActionSelectionDMAResult, task_id: Optional[str], dispatch_context: DispatchContext
    ) -> None:
        """Memorize positive moment if present in result."""
        if not hasattr(result, "action_parameters"):
            return

        params = result.action_parameters
        if not hasattr(params, "positive_moment"):
            return

        positive_moment = params.positive_moment
        if positive_moment:
            await self._memorize_positive_moment(positive_moment, task_id, dispatch_context)

    async def _complete_parent_task(self, task_id: str, thought_id: str, result: ActionSelectionDMAResult) -> None:
        """Mark parent task as complete and handle notifications."""
        # Skip persistent tasks
        if task_id in PERSISTENT_TASK_IDS:
            self.logger.info(f"Task {task_id} is a persistent task. Not marking as COMPLETED.")
            return

        # Check for pending thoughts
        self._verify_no_pending_thoughts(task_id, thought_id)

        # Get task with correct occurrence_id
        from ciris_engine.logic.persistence.models.tasks import get_task_by_id_any_occurrence

        task = get_task_by_id_any_occurrence(task_id)
        if not task:
            self.logger.error(f"Failed to get task {task_id} - cannot mark as COMPLETED.")
            return

        task_occurrence_id = task.agent_occurrence_id
        self.logger.debug(f"Marking task {task_id} as COMPLETED with occurrence_id={task_occurrence_id}")

        task_updated = persistence.update_task_status(
            task_id, TaskStatus.COMPLETED, task_occurrence_id, self.time_service
        )

        if not task_updated:
            self.logger.error(f"Failed to update status for parent task {task_id} to COMPLETED.")
            return

        self.logger.info(
            f"Marked parent task {task_id} as COMPLETED due to TASK_COMPLETE action on thought {thought_id}."
        )

        # Handle post-completion tasks
        await self._handle_post_completion(task, task_id, task_occurrence_id, result)

    def _verify_no_pending_thoughts(self, task_id: str, current_thought_id: str) -> None:
        """Verify no pending/processing thoughts exist before completing task."""
        pending = persistence.get_thoughts_by_task_id(task_id)
        pending_or_processing = [
            t.thought_id
            for t in pending
            if t.thought_id != current_thought_id
            and getattr(t, "status", None) in {ThoughtStatus.PENDING, ThoughtStatus.PROCESSING}
        ]

        if pending_or_processing:
            error_msg = (
                f"CRITICAL: Task {task_id} cannot be marked complete - "
                f"has {len(pending_or_processing)} thoughts still pending/processing: {pending_or_processing}. "
                f"This indicates a handler failed to properly complete thought processing."
            )
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def _handle_post_completion(
        self, task, task_id: str, task_occurrence_id: str, result: ActionSelectionDMAResult
    ) -> None:
        """Handle post-completion tasks: image purging and notifications."""
        # Purge images unless persist_images is set
        persist_images = False
        if hasattr(result, "action_parameters") and hasattr(result.action_parameters, "persist_images"):
            persist_images = result.action_parameters.persist_images

        if not persist_images and task and task.images:
            from ciris_engine.logic.persistence.models.tasks import clear_task_images

            cleared = clear_task_images(task_id, task_occurrence_id, self.time_service)
            if cleared:
                self.logger.info(f"Purged {len(task.images)} images from completed task {task_id}")

        # Handle completion notification for API channels
        if task and task.channel_id:
            await self._handle_completion_notification(task, task_id)

    async def _handle_completion_notification(self, task, task_id: str) -> None:
        """Send notification for API channel completions without SPEAK."""
        if not is_api_channel(task.channel_id):
            return

        has_spoken = await self._has_speak_action_completed(task_id)
        has_unhandled_updates = getattr(task, "updated_info_available", False)

        if has_spoken and not has_unhandled_updates:
            return

        # Build notification message
        has_tool = await self._has_tool_action_completed(task_id)
        if has_unhandled_updates:
            msg = "Agent completed task but new messages arrived that weren't addressed"
        elif has_tool:
            msg = "Agent chose task complete without speaking after a tool call"
        else:
            msg = "Agent chose task complete without speaking immediately"

        self.logger.info(
            f"Task {task_id} completed without speaking on API channel {task.channel_id} "
            f"(has_spoken={has_spoken}, has_unhandled_updates={has_unhandled_updates}) - sending notification"
        )
        await self._send_notification(task.channel_id, msg)

    async def _is_wakeup_task(self, task_id: str) -> bool:
        """Check if a task is part of the wakeup sequence."""
        task = persistence.get_task_by_id(task_id)
        if not task:
            return False

        if task_id == "WAKEUP_ROOT":
            return True

        if getattr(task, "parent_task_id", None) == "WAKEUP_ROOT":
            return True

        if task.context and hasattr(task.context, "step_type"):
            step_type = getattr(task.context, "step_type", None)
            wakeup_steps = [
                "VERIFY_IDENTITY",
                "VALIDATE_INTEGRITY",
                "EVALUATE_RESILIENCE",
                "ACCEPT_INCOMPLETENESS",
                "EXPRESS_GRATITUDE",
            ]
            if step_type in wakeup_steps:
                return True

        return False

    async def _has_speak_action_completed(self, task_id: str) -> bool:
        """Check if a SPEAK action has been successfully completed for the given task."""
        from ciris_engine.schemas.telemetry.core import ServiceCorrelationStatus

        correlations = persistence.get_correlations_by_task_and_action(
            task_id=task_id, action_type="speak_action", status=ServiceCorrelationStatus.COMPLETED
        )
        self.logger.debug(f"Found {len(correlations)} completed SPEAK correlations for task {task_id}")
        return bool(correlations)

    async def _has_tool_action_completed(self, task_id: str) -> bool:
        """Check if a TOOL action has been successfully completed for the given task."""
        from ciris_engine.schemas.telemetry.core import ServiceCorrelationStatus

        correlations = persistence.get_correlations_by_task_and_action(
            task_id=task_id, action_type="tool_action", status=ServiceCorrelationStatus.COMPLETED
        )
        self.logger.debug(f"Found {len(correlations)} completed TOOL correlations for task {task_id}")
        return bool(correlations)

    async def _memorize_positive_moment(
        self, positive_moment: str, task_id: Optional[str], dispatch_context: DispatchContext
    ) -> None:
        """Memorize a positive moment as a community vibe."""
        try:
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            vibe_node = GraphNode(
                id=f"positive_vibe_{int(self.time_service.timestamp())}",
                type=NodeType.CONCEPT,
                scope=GraphScope.COMMUNITY,
                attributes={
                    "vibe_type": "task_completion_joy",
                    "description": positive_moment[:500],
                    "task_id": task_id or "unknown",
                    "channel_id": dispatch_context.channel_context.channel_id or "somewhere",
                    "timestamp": self.time_service.now_iso(),
                },
            )

            await self.bus_manager.memory.memorize(
                node=vibe_node, handler_name="task_complete_handler", metadata={"positive_vibes": True}
            )
            self.logger.info(f"Memorized positive moment: {positive_moment[:100]}...")

        except Exception as e:
            self.logger.debug(f"Couldn't memorize positive moment: {e}")
