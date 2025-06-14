"""Special case handlers for Action Selection PDMA."""

import logging
from typing import Dict, Any, Optional
from ciris_engine.schemas.dma_results_v1 import ActionSelectionResult
from ciris_engine.schemas.action_params_v1 import PonderParams
from ciris_engine.schemas.foundational_schemas_v1 import HandlerActionType

logger = logging.getLogger(__name__)


class ActionSelectionSpecialCases:
    """Handles special cases in action selection evaluation."""
    
    @staticmethod
    async def handle_ponder_force(triaged_inputs: Dict[str, Any]) -> Optional[ActionSelectionResult]:
        """Handle forced ponder case."""
        processing_context_data = triaged_inputs.get("processing_context")
        original_thought = triaged_inputs["original_thought"]
        
        # Check the original message content from the task context
        original_message_content = None
        if (
            processing_context_data
            and hasattr(processing_context_data, "initial_task_context")
            and processing_context_data.initial_task_context
        ):
            original_message_content = getattr(
                processing_context_data.initial_task_context, "content", None
            )

        if (
            original_message_content
            and original_message_content.strip().lower() == "ponder"
        ):
            logger.info(
                f"ActionSelectionPDMA: Detected 'ponder' keyword in original message for thought ID {original_thought.thought_id}. Forcing PONDER action."
            )
            ponder_params = PonderParams(
                questions=[
                    "Forced ponder: What are the key ambiguities?",
                    "Forced ponder: How can this be clarified?",
                ]
            )
            return ActionSelectionResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=ponder_params,
                rationale="Forced PONDER for testing ponder loop.",
                confidence=None,
                raw_llm_response=None,
            )
        
        return None
    
    @staticmethod
    async def handle_wakeup_task_speak_requirement(triaged_inputs: Dict[str, Any]) -> Optional[ActionSelectionResult]:
        """Handle wakeup task SPEAK requirement."""
        original_thought = triaged_inputs["original_thought"]
        task_id = original_thought.source_task_id
        
        if not task_id or not ActionSelectionSpecialCases._is_wakeup_task(task_id):
            return None
        
        logger.debug(f"ActionSelectionPDMA: Processing wakeup task {task_id}")
        
        llm_response_internal = triaged_inputs.get("llm_response_internal")
        if (
            llm_response_internal 
            and hasattr(llm_response_internal, "selected_action")
            and llm_response_internal.selected_action == HandlerActionType.TASK_COMPLETE
        ):
            if not ActionSelectionSpecialCases._task_has_successful_speak(task_id):
                logger.info(
                    f"ActionSelectionPDMA: Wakeup task {task_id} attempted TASK_COMPLETE without prior SPEAK. Converting to PONDER."
                )
                ponder_params = PonderParams(
                    questions=[
                        "This wakeup step requires a SPEAK action before task completion.",
                        "What affirmation should I speak for this wakeup ritual step?",
                    ]
                )
                return ActionSelectionResult(
                    selected_action=HandlerActionType.PONDER,
                    action_parameters=ponder_params,
                    rationale="Wakeup task requires SPEAK action before TASK_COMPLETE",
                    confidence=0.95,
                    raw_llm_response="Converted TASK_COMPLETE to PONDER due to missing SPEAK requirement",
                )
        
        return None
    
    @staticmethod
    def _is_wakeup_task(task_id: str) -> bool:
        """Check if a task is a wakeup task."""
        try:
            from ciris_engine import persistence

            task = persistence.get_task_by_id(task_id)
            if not task:
                return False

            # Check if parent task is WAKEUP_ROOT (secure check)
            if task.parent_task_id == "WAKEUP_ROOT":
                return True

            # Also check if the task context has step_type (wakeup tasks have this)
            if task.context and task.context.get("step_type"):
                return True

            return False
        except Exception:
            return False

    @staticmethod
    def _task_has_successful_speak(task_id: str) -> bool:
        """Check if a task has had a successful SPEAK action."""
        try:
            from ciris_engine import persistence
            from ciris_engine.schemas.foundational_schemas_v1 import (
                ThoughtStatus,
                HandlerActionType,
            )

            thoughts = persistence.get_thoughts_by_task_id(task_id)
            if not thoughts:
                return False

            for thought in thoughts:
                if (
                    thought.status == ThoughtStatus.COMPLETED
                    and hasattr(thought, "final_action")
                    and thought.final_action
                    and hasattr(thought.final_action, "selected_action")
                    and thought.final_action.selected_action == HandlerActionType.SPEAK
                ):
                    return True

            return False
        except Exception:
            return False