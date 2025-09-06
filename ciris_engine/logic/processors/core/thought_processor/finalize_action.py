"""
Action Finalization Phase - H3ERE Pipeline Step 6.

Determines the final action after all processing phases complete,
handling special cases and ensuring a valid action result.
"""

import logging
from typing import Any

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.core.step_decorators import streaming_step, step_point
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

logger = logging.getLogger(__name__)


class ActionFinalizationPhase:
    """
    Phase 6: Action Finalization
    
    Determines the final action to execute:
    - Handles edge cases and special processing
    - Ensures a valid action result exists
    - Applies any final transformations
    """

    @streaming_step(StepPoint.FINALIZE_ACTION)
    @step_point(StepPoint.FINALIZE_ACTION)
    async def _finalize_action_step(self, thought_item: ProcessingQueueItem, action_result):
        """
        Step 6: Determine final action for execution.
        
        This decorated method automatically handles:
        - Real-time streaming of finalization progress
        - Single-step pause/resume capability
        - Default action creation for edge cases
        
        Args:
            thought_item: The thought being processed
            action_result: Action result from previous phases
            
        Returns:
            Final ActionSelectionDMAResult ready for dispatch
        """
        logger.debug(f"Finalizing action for thought {thought_item.thought_id}")
        
        if not action_result:
            # If no action result, create default ponder action
            logger.warning(f"No action result for thought {thought_item.thought_id}, defaulting to PONDER")
            
            ponder_params = PonderParams(
                reason="No valid action could be determined",
                duration_minutes=1,
                should_generate_follow_up=True,
            )
            
            final_result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=ponder_params,
                rationale="Failed to determine valid action - pondering instead",
                confidence_score=0.1,
                resource_usage=None,
            )
        else:
            # Use the provided action result
            final_result = action_result
        
        # Apply any special case handling
        final_result = self._handle_special_cases(final_result, thought_item)
        
        logger.info(f"Action finalized for thought {thought_item.thought_id}: {final_result.selected_action}")
        return final_result
        
    def _handle_special_cases(self, action_result, thought_item):
        """Apply special case processing to the final action."""
        # This method handles edge cases and special transformations
        # Implementation would be based on current special case logic
        return action_result