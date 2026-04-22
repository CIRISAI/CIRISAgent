"""
Recursive Processing Phase - H3ERE Pipeline Step 5.

Handles retry logic when conscience validation fails, including:
- RECURSIVE_ASPDMA: Retry action selection with guidance
- RECURSIVE_CONSCIENCE: Re-validate the retried action
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.types import JSONDict

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
        thought = await self._fetch_thought(thought_item.thought_id, thought_item.agent_occurrence_id)  # type: ignore[attr-defined]

        try:
            # Re-run action selection with guidance about why previous action failed
            retry_result = await self._perform_aspdma_with_guidance(
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

    async def _perform_aspdma_with_guidance(
        self,
        thought: Any,
        thought_context: Any,
        dma_results: Any,
        conscience_result: Any,
        max_retries: int = 3,
    ) -> Any:
        """
        Retry action selection with conscience guidance, with exponential backoff.

        Args:
            thought: The thought being processed
            thought_context: Processing context (contains conscience feedback)
            dma_results: Results from initial DMA execution
            conscience_result: Conscience result with override_reason explaining why original action failed
            max_retries: Maximum retry attempts (default: 3)

        Returns:
            ActionSelectionDMAResult with guidance-informed action selection

        Note:
            Implements retry logic with cumulative guidance - each retry gets feedback
            from all previous attempts to improve action selection quality.
        """
        from ciris_engine.schemas.conscience.core import ConscienceCheckResult
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult

        last_error = None
        retry_history: List[JSONDict] = []

        for attempt in range(max_retries):
            try:
                # Extract typed conscience feedback for guidance
                from ciris_engine.schemas.conscience.core import EpistemicData

                override_reason = ""
                epistemic_feedback: EpistemicData

                if isinstance(conscience_result, ConscienceApplicationResult):
                    override_reason = conscience_result.override_reason or "Conscience override occurred"
                    epistemic_feedback = conscience_result.epistemic_data
                elif isinstance(conscience_result, dict):
                    # Legacy dict path - should not happen with typed schemas
                    override_reason = conscience_result.get("override_reason", "Conscience override occurred")
                    epistemic_data_dict = conscience_result.get("epistemic_data", {})
                    # Convert dict to EpistemicData if needed
                    if isinstance(epistemic_data_dict, EpistemicData):
                        epistemic_feedback = epistemic_data_dict
                    else:
                        # Fallback: create safe default EpistemicData
                        epistemic_feedback = EpistemicData(
                            entropy_level=0.5,
                            coherence_level=0.5,
                            uncertainty_acknowledged=False,
                            reasoning_transparency=0.5,
                        )

                # Build guidance context with typed conscience results + retry history
                guidance_context = {
                    "retry_attempt": attempt + 1,
                    "max_retries": max_retries,
                    "original_action_failed_because": override_reason,
                    "conscience_feedback": {
                        "epistemic_data": epistemic_feedback,
                        "override_detected": True,
                    },
                    "retry_history": retry_history,  # Cumulative feedback from previous attempts
                }

                # Merge guidance into thought context
                if hasattr(thought_context, "model_dump"):
                    enriched_context = thought_context.model_dump()
                else:
                    enriched_context = dict(thought_context) if isinstance(thought_context, dict) else {}

                enriched_context["conscience_guidance"] = guidance_context

                # Get profile and re-run action selection with conscience guidance
                profile_name = self._get_profile_name(thought)  # type: ignore[attr-defined]

                retry_result = await self.dma_orchestrator.run_action_selection(  # type: ignore[attr-defined]
                    thought_item=thought,
                    actual_thought=thought,
                    processing_context=enriched_context,
                    dma_results=dma_results,
                    profile_name=profile_name,
                )

                # Success! Return the result
                logger.info(
                    f"ASPDMA retry attempt {attempt + 1}/{max_retries} succeeded for thought {thought.thought_id}"
                )
                return retry_result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"ASPDMA retry attempt {attempt + 1}/{max_retries} failed for thought {thought.thought_id}: {e}"
                )

                # Add this attempt to retry history for next iteration
                retry_history.append(
                    {
                        "attempt": attempt + 1,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

                # If this was the last attempt, raise the error
                if attempt == max_retries - 1:
                    logger.error(f"All {max_retries} ASPDMA retry attempts exhausted for thought {thought.thought_id}")
                    raise last_error

                # Otherwise, continue to next retry
                continue

        # Should never reach here, but just in case
        raise RuntimeError(f"ASPDMA retry logic failed unexpectedly for thought {thought.thought_id}")
