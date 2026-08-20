import asyncio
import logging
from typing import Dict, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.shared_helpers import is_api_channel
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought

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
            blocked = await self._validate_wakeup_completion(parent_task_id, thought_id)
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

    async def _validate_wakeup_completion(self, task_id: str, thought_id: str) -> bool:
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
            task_id, TaskStatus.COMPLETED, task_occurrence_id
        )

        if not task_updated:
            self.logger.error(f"Failed to update status for parent task {task_id} to COMPLETED.")
            return

        self.logger.info(
            f"Marked parent task {task_id} as COMPLETED due to TASK_COMPLETE action on thought {thought_id}."
        )

        # Handle post-completion tasks
        await self._handle_post_completion(task, task_id, task_occurrence_id, result)

    #: Sibling states that mean AN OBLIGATION IS STILL OUTSTANDING, so the task
    #: cannot honestly be called complete.
    #:
    #: Keyed on what the state MEANS, not on which names the predicate happened
    #: to list (NULLWORKS RC3 finding F4). The guard used to name PENDING and
    #: PROCESSING only, so a DEFERRED sibling — a thought whose disposition was
    #: handed to a human who has not answered yet — coexisted with a COMPLETED
    #: write. Their COMPLETE-01 campaign reproduced exactly that.
    #:
    #: DEFERRED is the case that matters. `defer_handler` sets it when a decision
    #: is escalated to a Wise Authority; it means "a human owes an answer". A task
    #: that reports COMPLETED while a human is still holding one of its questions
    #: is making a false statement about itself, and every downstream consumer —
    #: audit, telemetry, the operator reading a dashboard — inherits it.
    #:
    #: FAILED is deliberately NOT here, and that is a judgement worth stating.
    #: A failed thought is settled: it will not proceed, and nobody owes anything.
    #: Blocking on it would strand tasks forever with no resolution path, since
    #: nothing re-opens a FAILED thought. It is recorded on the completion instead
    #: (see below), so the completion is honest about being qualified rather than
    #: clean — which is the part that was actually missing.
    _OBLIGATION_OUTSTANDING = {
        ThoughtStatus.PENDING,
        ThoughtStatus.PROCESSING,
        ThoughtStatus.DEFERRED,
    }

    def _verify_no_pending_thoughts(self, task_id: str, current_thought_id: str) -> None:
        """Refuse completion while any sibling obligation is unresolved."""
        siblings = [
            t for t in persistence.get_thoughts_by_task_id(task_id) if t.thought_id != current_thought_id
        ]
        outstanding = [
            t.thought_id for t in siblings if getattr(t, "status", None) in self._OBLIGATION_OUTSTANDING
        ]

        if outstanding:
            deferred = [
                t.thought_id for t in siblings if getattr(t, "status", None) == ThoughtStatus.DEFERRED
            ]
            # Name the DEFERRED ones separately: they need a human, not a retry,
            # and telling an operator to look for "a handler that failed" when the
            # truth is "a person has not answered" sends them to the wrong place.
            detail = (
                f" Of these, {len(deferred)} are DEFERRED and awaiting a Wise Authority "
                f"resolution: {deferred}."
                if deferred
                else " This indicates a handler failed to properly complete thought processing."
            )
            error_msg = (
                f"CRITICAL: Task {task_id} cannot be marked complete - "
                f"has {len(outstanding)} thoughts with unresolved obligations: {outstanding}.{detail}"
            )
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Settled, but not silently. A task completing over failed sub-thoughts is
        # a QUALIFIED completion; saying so is the difference between a record that
        # is true and one that is merely not false.
        failed = [t.thought_id for t in siblings if getattr(t, "status", None) == ThoughtStatus.FAILED]
        if failed:
            self.logger.warning(
                "Task %s is completing with %d FAILED sibling thought(s): %s. Completion is allowed "
                "because a FAILED thought is settled and nothing re-opens it, but this is a qualified "
                "completion — if those thoughts carried mandatory obligations, the obligation is now "
                "unmet and unrecorded anywhere else.",
                task_id,
                len(failed),
                failed,
            )

    async def _handle_post_completion(
        self, task: Task, task_id: str, task_occurrence_id: str, result: ActionSelectionDMAResult
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

    async def _handle_completion_notification(self, task: Task, task_id: str) -> None:
        """Send notification for API channel completions with unhandled updates.

        Note: Silent completion (without SPEAK) is expected behavior when tool actions
        are performed. We only notify when new messages arrived that weren't addressed.
        """
        if not is_api_channel(task.channel_id):
            return

        has_unhandled_updates = getattr(task, "updated_info_available", False)

        # Only notify if there are unhandled updates (new messages arrived during processing)
        # Silent completion without speaking is expected behavior - tool actions are shown in timeline
        if not has_unhandled_updates:
            return

        msg = "Agent completed task but new messages arrived that weren't addressed"

        self.logger.info(
            f"Task {task_id} completed with unhandled updates on API channel {task.channel_id} - sending notification"
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
