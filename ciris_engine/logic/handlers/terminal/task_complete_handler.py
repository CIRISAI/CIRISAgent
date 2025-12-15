import logging
from typing import Dict, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
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

        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

        final_thought_status = ThoughtStatus.COMPLETED

        self.logger.info(f"Handling TASK_COMPLETE for thought {thought_id} (Task: {parent_task_id}).")

        if parent_task_id:
            is_wakeup = await self._is_wakeup_task(parent_task_id)
            self.logger.debug(f"Task {parent_task_id} is_wakeup_task: {is_wakeup}")
            if is_wakeup:
                has_speak = await self._has_speak_action_completed(parent_task_id)
                self.logger.debug(f"Task {parent_task_id} has_speak_action_completed: {has_speak}")
                if not has_speak:
                    self.logger.error(
                        f"TASK_COMPLETE rejected for wakeup task {parent_task_id}: No SPEAK action has been completed."
                    )

                    from ciris_engine.schemas.actions import PonderParams
                    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult

                    ponder_content = (
                        "WAKEUP TASK COMPLETION BLOCKED: You attempted to mark a wakeup task as complete "
                        "without first completing a SPEAK action. Each wakeup step requires you to SPEAK "
                        "an earnest affirmation before marking the task complete. Please review the task "
                        "requirements and either: 1) SPEAK an authentic affirmation if you can do so earnestly, "
                        "or 2) REJECT this task if you cannot speak earnestly about it, or 3) DEFER to human "
                        f"wisdom if you are uncertain about the requirements. Task: {parent_task_id}"
                    )

                    ponder_result = ActionSelectionDMAResult(
                        selected_action=HandlerActionType.PONDER,
                        action_parameters=PonderParams(questions=[ponder_content], channel_id=None),
                        rationale="Wakeup task requires SPEAK action before completion",
                        reasoning="Wakeup task attempted completion without first performing SPEAK action - overriding to PONDER for guidance",
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
                        thought_id=thought_id,
                        status=ThoughtStatus.FAILED,
                        final_action=ponder_result_dict,
                    )
                    # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging
                    return None

        persistence.update_thought_status(
            thought_id=thought_id,
            status=final_thought_status,
            final_action=result,
        )
        self.logger.debug(
            f"Updated original thought {thought_id} to status {final_thought_status.value} for TASK_COMPLETE."
        )

        # Brief delay to ensure database write is committed
        import asyncio

        await asyncio.sleep(0.01)  # 10ms delay

        # Check if there's a positive moment to memorize
        if hasattr(result, "action_parameters") and hasattr(result.action_parameters, "positive_moment"):
            positive_moment = result.action_parameters.positive_moment
            if positive_moment:
                await self._memorize_positive_moment(positive_moment, parent_task_id, dispatch_context)

        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

        if parent_task_id:
            if parent_task_id in PERSISTENT_TASK_IDS:
                self.logger.info(
                    f"Task {parent_task_id} is a persistent task. Not marking as COMPLETED by TaskCompleteHandler. It should be re-activated or remain PENDING/ACTIVE."
                )
            else:
                # Check for pending/processing thoughts BEFORE marking task complete
                pending = persistence.get_thoughts_by_task_id(parent_task_id)
                # Filter out the current thought we just completed
                pending_or_processing = [
                    t.thought_id
                    for t in pending
                    if t.thought_id != thought_id
                    and getattr(t, "status", None) in {ThoughtStatus.PENDING, ThoughtStatus.PROCESSING}
                ]
                if pending_or_processing:
                    error_msg = (
                        f"CRITICAL: Task {parent_task_id} cannot be marked complete - "
                        f"has {len(pending_or_processing)} thoughts still pending/processing: {pending_or_processing}. "
                        f"This indicates a handler failed to properly complete thought processing."
                    )
                    self.logger.error(error_msg)
                    raise RuntimeError(error_msg)

                # Only mark task complete if no pending thoughts
                # CRITICAL: Get the correct occurrence_id from the task itself
                # This handles all scenarios:
                # - Single-occurrence (default): agent_occurrence_id="default"
                # - Multi-occurrence unclaimed: agent_occurrence_id="__shared__"
                # - Multi-occurrence CLAIMED: agent_occurrence_id="occurrence-a" (after transfer_task_ownership)
                # Must fetch without occurrence_id filter because transferred tasks have been updated
                from ciris_engine.logic.persistence.models.tasks import get_task_by_id_any_occurrence

                task = get_task_by_id_any_occurrence(parent_task_id)
                if not task:
                    self.logger.error(f"Failed to get task {parent_task_id} - cannot mark as COMPLETED.")
                    return None

                task_occurrence_id = task.agent_occurrence_id
                self.logger.debug(
                    f"Marking task {parent_task_id} as COMPLETED with occurrence_id={task_occurrence_id} "
                    f"(task may be default, __shared__, or transferred to specific occurrence)"
                )

                task_updated = persistence.update_task_status(
                    parent_task_id, TaskStatus.COMPLETED, task_occurrence_id, self.time_service
                )
                if task_updated:
                    self.logger.info(
                        f"Marked parent task {parent_task_id} as COMPLETED due to TASK_COMPLETE action on thought {thought_id}."
                    )

                    # Purge task images unless explicitly marked for persistence
                    persist_images = False
                    if hasattr(result, "action_parameters") and hasattr(result.action_parameters, "persist_images"):
                        persist_images = result.action_parameters.persist_images

                    if not persist_images and task and task.images:
                        from ciris_engine.logic.persistence.models.tasks import clear_task_images

                        cleared = clear_task_images(parent_task_id, task_occurrence_id, self.time_service)
                        if cleared:
                            self.logger.info(
                                f"Purged {len(task.images)} images from completed task {parent_task_id} (persist_images=False)"
                            )
                        else:
                            self.logger.debug(f"No images to purge from task {parent_task_id}")

                    # Only notify on API channels where users expect feedback. Voice/home assistant
                    # and Discord channels expect silent completion (speaking is handled separately).
                    if task and task.channel_id:
                        is_api = self._is_api_channel(task.channel_id)
                        has_spoken = await self._has_speak_action_completed(parent_task_id)
                        # Check if new messages arrived after last SPEAK (safety net for bypass conscience)
                        has_unhandled_updates = getattr(task, "updated_info_available", False)

                        if is_api and (not has_spoken or has_unhandled_updates):
                            # Provide context about what the agent did before completing silently
                            has_tool = await self._has_tool_action_completed(parent_task_id)
                            if has_unhandled_updates:
                                msg = "Agent completed task but new messages arrived that weren't addressed"
                            elif has_tool:
                                msg = "Agent chose task complete without speaking after a tool call"
                            else:
                                msg = "Agent chose task complete without speaking immediately"

                            self.logger.info(
                                f"Task {parent_task_id} completed without speaking on API channel {task.channel_id} "
                                f"(has_spoken={has_spoken}, has_unhandled_updates={has_unhandled_updates}) - sending notification"
                            )
                            await self._send_notification(task.channel_id, msg)
                else:
                    self.logger.error(f"Failed to update status for parent task {parent_task_id} to COMPLETED.")
        else:
            self.logger.error(f"Could not find parent task ID for thought {thought_id} to mark as complete.")

        return None

    async def _is_wakeup_task(self, task_id: str) -> bool:
        """Check if a task is part of the wakeup sequence."""
        task = persistence.get_task_by_id(task_id)
        if not task:
            return False

        # Check if this is the root wakeup task
        if task_id == "WAKEUP_ROOT":
            return True

        # Check if parent task is the wakeup root
        if getattr(task, "parent_task_id", None) == "WAKEUP_ROOT":
            return True

        # Check if task context indicates it's a wakeup step
        if task.context and hasattr(task.context, "step_type"):
            step_type = getattr(task.context, "step_type", None)
            if step_type in [
                "VERIFY_IDENTITY",
                "VALIDATE_INTEGRITY",
                "EVALUATE_RESILIENCE",
                "ACCEPT_INCOMPLETENESS",
                "EXPRESS_GRATITUDE",
            ]:
                return True

        return False

    async def _has_speak_action_completed(self, task_id: str) -> bool:
        """Check if a SPEAK action has been successfully completed for the given task using correlation system."""
        from ciris_engine.schemas.telemetry.core import ServiceCorrelationStatus

        correlations = persistence.get_correlations_by_task_and_action(
            task_id=task_id, action_type="speak_action", status=ServiceCorrelationStatus.COMPLETED
        )

        self.logger.debug(f"Found {len(correlations)} completed SPEAK correlations for task {task_id}")

        if correlations:
            self.logger.debug(f"Found completed SPEAK action correlation for task {task_id}")
            return True

        self.logger.debug(f"No completed SPEAK action correlation found for task {task_id}")
        return False

    async def _has_tool_action_completed(self, task_id: str) -> bool:
        """Check if a TOOL action has been successfully completed for the given task using correlation system."""
        from ciris_engine.schemas.telemetry.core import ServiceCorrelationStatus

        correlations = persistence.get_correlations_by_task_and_action(
            task_id=task_id, action_type="tool_action", status=ServiceCorrelationStatus.COMPLETED
        )

        self.logger.debug(f"Found {len(correlations)} completed TOOL correlations for task {task_id}")

        if correlations:
            self.logger.debug(f"Found completed TOOL action correlation for task {task_id}")
            return True

        self.logger.debug(f"No completed TOOL action correlation found for task {task_id}")
        return False

    def _is_api_channel(self, channel_id: Optional[str]) -> bool:
        """Check if channel is an API channel (not Discord)."""
        if not channel_id:
            return False
        return channel_id.startswith("api_") or channel_id.startswith("ws:")

    async def _memorize_positive_moment(
        self, positive_moment: str, task_id: Optional[str], dispatch_context: DispatchContext
    ) -> None:
        """Memorize a positive moment as a community vibe."""
        try:
            from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

            # Create a positive vibe node
            vibe_node = GraphNode(
                id=f"positive_vibe_{int(self.time_service.timestamp())}",
                type=NodeType.CONCEPT,
                scope=GraphScope.COMMUNITY,
                attributes={
                    "vibe_type": "task_completion_joy",
                    "description": positive_moment[:500],  # Keep it brief
                    "task_id": task_id or "unknown",
                    "channel_id": dispatch_context.channel_context.channel_id or "somewhere",
                    "timestamp": self.time_service.now_iso(),
                },
            )

            # Memorize via the memory bus
            await self.bus_manager.memory.memorize(
                node=vibe_node, handler_name="task_complete_handler", metadata={"positive_vibes": True}
            )

            self.logger.info(f"✨ Memorized positive moment: {positive_moment[:100]}...")

        except Exception as e:
            # Don't let positive moment tracking break task completion
            self.logger.debug(f"Couldn't memorize positive moment: {e}")
