"""
Action Execution Phase - H3ERE Pipeline Step 7.

Handles the final execution steps including action dispatch
and completion tracking.
"""

import logging
from typing import Any

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.core.step_decorators import streaming_step, step_point
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class ActionExecutionPhase:
    """
    Phase 7: Action Execution
    
    Handles the final execution steps:
    - PERFORM_ACTION: Dispatch action to appropriate handler
    - ACTION_COMPLETE: Track completion and results
    """

    @streaming_step(StepPoint.PERFORM_ACTION)
    @step_point(StepPoint.PERFORM_ACTION)
    async def _perform_action_step(self, thought_item: ProcessingQueueItem, action_result, context: dict):
        """
        Step 7a: Dispatch action to handler for execution.
        
        This decorated method automatically handles:
        - Real-time streaming of action dispatch progress
        - Single-step pause/resume capability
        - Action preparation for handler dispatch
        
        Args:
            thought_item: The thought being processed
            action_result: Final action to execute
            context: Dispatch context
            
        Returns:
            The action result (unchanged - actual dispatch happens in base processor)
        """
        logger.debug(f"Preparing action dispatch for thought {thought_item.thought_id}")
        
        # This step is primarily for streaming and step-point functionality
        # The actual dispatch logic is handled by the base processor's dispatch_action method
        # We just pass through the result and let the orchestrator handle the actual dispatch
        
        logger.info(f"Action prepared for dispatch: {action_result.selected_action} for thought {thought_item.thought_id}")
        return action_result

    @streaming_step(StepPoint.ACTION_COMPLETE)
    @step_point(StepPoint.ACTION_COMPLETE)
    async def _action_complete_step(self, thought_item: ProcessingQueueItem, dispatch_result):
        """
        Step 7b: Mark action execution as complete.
        
        This decorated method automatically handles:
        - Real-time streaming of completion status
        - Single-step pause/resume capability
        - Final result processing
        
        Args:
            thought_item: The thought being processed
            dispatch_result: Result from action handler execution
            
        Returns:
            Completion status information
        """
        logger.debug(f"Marking action complete for thought {thought_item.thought_id}")
        
        # Process the dispatch result and create completion status
        completion_status = {
            "thought_id": thought_item.thought_id,
            "action_completed": True,
            "dispatch_success": dispatch_result.get("success", True) if isinstance(dispatch_result, dict) else True,
            "execution_time_ms": dispatch_result.get("execution_time_ms", 0.0) if isinstance(dispatch_result, dict) else 0.0,
            "handler_completed": dispatch_result.get("completed", True) if isinstance(dispatch_result, dict) else True,
            "follow_up_processing_pending": dispatch_result.get("has_follow_up", False) if isinstance(dispatch_result, dict) else False,
        }
        
        logger.info(f"Action execution completed for thought {thought_item.thought_id}")
        return completion_status