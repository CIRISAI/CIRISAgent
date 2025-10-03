"""
Recursive Processing Phase - H3ERE Pipeline Step 5.

Handles retry logic when conscience validation fails, including:
- RECURSIVE_ASPDMA: Retry action selection with guidance
- RECURSIVE_CONSCIENCE: Re-validate the retried action
"""

import logging
from typing import Any, Optional, Tuple

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class RecursiveProcessingPhase:
    """
    Phase 5: Recursive Processing (Optional)

    Handles retry logic when initial action selection fails conscience validation:
    - RECURSIVE_ASPDMA: Retry action selection with conscience guidance
    - RECURSIVE_CONSCIENCE: Re-validate the retry attempt
    """

    async def _handle_recursive_processing(
        self,
        thought_item: Any,
        thought: Any,
        thought_context: Any,
        dma_results: Any,
        conscience_result: Any,
        action_result: Any,
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
                retry_conscience_result = await self._recursive_conscience_step(thought_item, retry_result)

                # Check if retry passed consciences
                if not retry_conscience_result.overridden:
                    logger.info(f"Retry action {retry_result.selected_action} passed consciences")
                    return retry_result, retry_conscience_result
                else:
                    logger.info(f"Retry action also failed consciences, proceeding with original")

        return action_result, conscience_result

    @streaming_step(StepPoint.RECURSIVE_ASPDMA)
    @step_point(StepPoint.RECURSIVE_ASPDMA)
    async def _recursive_aspdma_step(
        self, thought_item: ProcessingQueueItem, thought_context: Any, dma_results: Any, override_reason: str
    ) -> Optional[Any]:
        """Step 3B: Optional retry action selection after conscience failure."""
        thought = await self._fetch_thought(thought_item.thought_id)  # type: ignore[attr-defined]

        try:
            # Re-run action selection with guidance about why previous action failed
            retry_result = await self._perform_aspdma_with_guidance(  # type: ignore[attr-defined]
                thought, thought_context, dma_results, override_reason, max_retries=3
            )
            return retry_result
        except Exception as e:
            logger.error(f"Recursive ASPDMA failed for thought {thought_item.thought_id}: {e}")
            return None

    @streaming_step(StepPoint.RECURSIVE_CONSCIENCE)
    @step_point(StepPoint.RECURSIVE_CONSCIENCE)
    async def _recursive_conscience_step(self, thought_item: ProcessingQueueItem, retry_result: Any) -> Tuple[Any, Any]:
        """Step 4B: Optional re-validation if recursive action failed."""
        if not retry_result:
            return retry_result, []

        try:
            recursive_conscience_results = await self.conscience_registry.apply_all_consciences(  # type: ignore[attr-defined]
                retry_result, thought_item
            )

            # Check if recursive conscience passed
            final_conscience_passed = all(result.passed for result in recursive_conscience_results)
            retry_result.conscience_passed = final_conscience_passed

            return retry_result, recursive_conscience_results
        except Exception as e:
            logger.error(f"Recursive conscience execution failed for thought {thought_item.thought_id}: {e}")
            return retry_result, []

    async def _perform_aspdma_with_retry(
        self, thought_item: Any, thought_context: Any, dma_results: Any, max_retries: int = 3
    ) -> Any:
        """Helper method for ASPDMA execution with retry logic."""
        # This would contain the retry logic implementation
        # For now, delegate to the main ASPDMA step
        return await self._perform_aspdma_step(thought_item, thought_context, dma_results)  # type: ignore[attr-defined]
