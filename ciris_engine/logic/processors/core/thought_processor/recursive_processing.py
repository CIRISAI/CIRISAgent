"""
Recursive Processing Phase - H3ERE Pipeline Step 5.

Handles retry logic when conscience validation fails, including:
- RECURSIVE_ASPDMA: Retry action selection with guidance
- RECURSIVE_CONSCIENCE: Re-validate the retried action
"""

import logging
from typing import Any, Optional, Tuple

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.core.step_decorators import streaming_step, step_point
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.runtime.enums import HandlerActionType

logger = logging.getLogger(__name__)


class RecursiveProcessingPhase:
    """
    Phase 5: Recursive Processing (Optional)
    
    Handles retry logic when initial action selection fails conscience validation:
    - RECURSIVE_ASPDMA: Retry action selection with conscience guidance
    - RECURSIVE_CONSCIENCE: Re-validate the retry attempt
    """

    async def _handle_recursive_processing(
        self, thought_item, thought, thought_context, dma_results, conscience_result, action_result
    ) -> Tuple[Optional[Any], Optional[Any]]:
        """
        Coordinate recursive processing if conscience validation failed.
        
        Args:
            thought_item: The thought being processed
            thought: Full thought object
            thought_context: Processing context
            dma_results: Results from DMA execution
            conscience_result: Result from conscience validation
            action_result: Original action selection result
            
        Returns:
            Tuple of (final_result, final_conscience_result)
        """
        # Check if consciences overrode to PONDER - attempt retry with guidance
        if (
            conscience_result
            and conscience_result.overridden
            and conscience_result.final_action.selected_action == HandlerActionType.PONDER
        ):
            logger.info(f"Conscience override to PONDER for {thought.thought_id}. Attempting retry with guidance.")
            
            # Try recursive ASPDMA with conscience feedback
            retry_result = await self._recursive_aspdma_step(
                thought_item, thought_context, dma_results, conscience_result
            )
            
            if retry_result:
                # Re-apply consciences to the retry result
                retry_conscience_result = await self._recursive_conscience_step(
                    thought_item, retry_result
                )
                
                # Check if retry passed consciences
                if not retry_conscience_result.overridden:
                    logger.info(f"Retry action {retry_result.selected_action} passed consciences")
                    return retry_result, retry_conscience_result
                else:
                    logger.info(f"Retry action also failed consciences, proceeding with original")
            
        return action_result, conscience_result

    @streaming_step(StepPoint.RECURSIVE_ASPDMA)
    @step_point(StepPoint.RECURSIVE_ASPDMA, conditional=True)
    async def _recursive_aspdma_step(self, thought_item, thought_context, dma_results, conscience_result):
        """
        Step 5a: Retry action selection with conscience guidance (conditional).
        
        This decorated method automatically handles:
        - Real-time streaming of retry progress
        - Single-step pause/resume capability (conditional execution)
        - Conscience feedback integration
        
        Args:
            thought_item: The thought being processed
            thought_context: Processing context
            dma_results: Original DMA results
            conscience_result: Failed conscience validation with guidance
            
        Returns:
            New ActionSelectionDMAResult or None if retry fails
        """
        try:
            # Extract conscience feedback for guidance
            override_reason = conscience_result.override_reason or "Action failed conscience checks"
            attempted_action = self._describe_action(conscience_result.original_action)

            # Create enhanced context with conscience feedback
            retry_context = thought_context
            if hasattr(thought_context, "model_copy"):
                retry_context = thought_context.model_copy()

            # Set flag indicating this is a conscience retry
            retry_context.is_conscience_retry = True

            # Add conscience guidance to the thought item
            setattr(
                thought_item,
                "conscience_feedback",
                {
                    "failed_action": attempted_action,
                    "failure_reason": override_reason,
                    "retry_guidance": (
                        f"Your previous attempt to {attempted_action} was rejected because: {override_reason}. "
                        "Please select a DIFFERENT action that better aligns with ethical principles and safety guidelines. "
                        "Consider: Is there a more cautious approach? Should you gather more information first? "
                        "Can this task be marked as complete without further action? "
                        "Remember: DEFER only if the task MUST be done AND requires human approval."
                    ),
                },
            )

            logger.debug(f"Attempting recursive ASPDMA for thought {thought_item.thought_id}")
            
            # Re-run action selection with guidance
            retry_result = await self._perform_aspdma_with_retry(
                thought_item, retry_context, dma_results, max_retries=1
            )
            
            logger.info(f"Recursive ASPDMA completed for thought {thought_item.thought_id}")
            return retry_result
            
        except Exception as e:
            logger.error(f"Recursive ASPDMA failed for thought {thought_item.thought_id}: {e}")
            return None

    @streaming_step(StepPoint.RECURSIVE_CONSCIENCE)
    @step_point(StepPoint.RECURSIVE_CONSCIENCE, conditional=True)
    async def _recursive_conscience_step(self, thought_item, retry_result):
        """
        Step 5b: Re-validate retry action with consciences (conditional).
        
        This decorated method automatically handles:
        - Real-time streaming of re-validation progress
        - Single-step pause/resume capability (conditional execution)
        - Final conscience decision
        
        Args:
            thought_item: The thought being processed
            retry_result: Action result from recursive ASPDMA
            
        Returns:
            Conscience result for the retry attempt
        """
        try:
            logger.debug(f"Re-applying consciences to retry for thought {thought_item.thought_id}")
            
            conscience_results = await self.conscience_registry.apply_all_consciences(
                retry_result, thought_item
            )
            
            logger.info(f"Recursive conscience validation completed for thought {thought_item.thought_id}")
            return conscience_results
            
        except Exception as e:
            logger.error(f"Recursive conscience execution failed for thought {thought_item.thought_id}: {e}")
            return retry_result

    async def _perform_aspdma_with_retry(self, thought_item, thought_context, dma_results, max_retries=3):
        """Helper method for ASPDMA execution with retry logic."""
        # This would contain the retry logic implementation
        # For now, delegate to the main ASPDMA step
        return await self._perform_aspdma_step(thought_item, thought_context, dma_results)