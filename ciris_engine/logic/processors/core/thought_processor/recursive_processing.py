"""
Recursive Processing Phase - H3ERE Pipeline Step 5.

Handles retry logic when conscience validation fails, including:
- RECURSIVE_ASPDMA: Retry action selection with guidance
- RECURSIVE_CONSCIENCE: Re-validate the retried action

In benchmark mode (CIRIS_BENCHMARK_MODE=true), keeps retrying up to
max_benchmark_retries times when conscience overrides to PONDER.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.config.env_utils import get_env_var
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def _is_benchmark_mode() -> bool:
    """Check if benchmark mode is enabled."""
    benchmark_mode_val = get_env_var("CIRIS_BENCHMARK_MODE", "") or ""
    return benchmark_mode_val.lower() in ("true", "1", "yes", "on")


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
        benchmark_mode = _is_benchmark_mode()
        max_benchmark_retries = 5  # Maximum retries in benchmark mode

        # Check if consciences overrode to PONDER - attempt retry with guidance
        if (
            conscience_result
            and conscience_result.overridden
            and conscience_result.final_action.selected_action == HandlerActionType.PONDER
        ):
            logger.info(f"[RECURSIVE] ════════════════════════════════════════════════════════════")
            logger.info(f"[RECURSIVE] Conscience override to PONDER for thought {thought.thought_id}")
            logger.info(f"[RECURSIVE] Override reason: {conscience_result.override_reason}")
            logger.info(f"[RECURSIVE] Benchmark mode: {benchmark_mode} | Max retries: {max_benchmark_retries}")
            logger.info(f"[RECURSIVE] Starting recursive ASPDMA retry loop...")

            current_conscience_result = conscience_result
            retry_count = 0

            # Track last successful retry for benchmark mode exhaustion
            last_retry_result = None
            last_retry_conscience_result = None

            while retry_count < max_benchmark_retries:
                retry_count += 1
                logger.info(f"[RECURSIVE] ──────────────────────────────────────────────────────────")
                logger.info(f"[RECURSIVE] Retry attempt {retry_count}/{max_benchmark_retries} for {thought.thought_id}")

                # Try recursive ASPDMA with conscience feedback
                retry_result = await self._recursive_aspdma_step(
                    thought_item, thought_context, dma_results, current_conscience_result
                )

                if not retry_result:
                    logger.warning(f"[RECURSIVE] ✗ Retry {retry_count} - ASPDMA returned no result, stopping")
                    break

                logger.info(f"[RECURSIVE] Retry {retry_count} - ASPDMA selected action: {retry_result.selected_action}")

                # Log the action content if it's SPEAK
                if retry_result.selected_action == HandlerActionType.SPEAK:
                    content = ""
                    if hasattr(retry_result.action_parameters, "content"):
                        content = retry_result.action_parameters.content or ""
                    logger.info(f"[RECURSIVE] Retry {retry_count} - SPEAK content preview: {content[:150]}...")

                # Re-apply consciences to the retry result
                logger.info(f"[RECURSIVE] Retry {retry_count} - Running conscience checks...")
                retry_conscience_result = await self._recursive_conscience_step(
                    thought_item, retry_result, thought=thought
                )

                # Store for potential benchmark exhaustion return
                last_retry_result = retry_result
                last_retry_conscience_result = retry_conscience_result

                # Check if retry passed consciences
                if not retry_conscience_result.overridden:
                    logger.info(
                        f"[RECURSIVE] ✓ SUCCESS on retry {retry_count} - "
                        f"Action {retry_result.selected_action} passed all consciences!"
                    )
                    logger.info(f"[RECURSIVE] ════════════════════════════════════════════════════════════")
                    return retry_result, retry_conscience_result

                # Conscience still wants override
                logger.warning(
                    f"[RECURSIVE] ✗ Retry {retry_count} - Conscience override: "
                    f"{retry_conscience_result.override_reason}"
                )

                # In benchmark mode, keep trying if conscience still wants PONDER
                if benchmark_mode and retry_conscience_result.final_action.selected_action == HandlerActionType.PONDER:
                    logger.info(
                        f"[RECURSIVE] [BENCHMARK_MODE] Retry {retry_count}/{max_benchmark_retries} "
                        f"failed conscience check, bouncing to next attempt..."
                    )
                    current_conscience_result = retry_conscience_result
                    continue
                else:
                    # Normal mode: stop after first retry failure
                    logger.info(f"[RECURSIVE] Normal mode - stopping after conscience failure on retry {retry_count}")
                    break

            if benchmark_mode and retry_count >= max_benchmark_retries:
                logger.warning(f"[RECURSIVE] ════════════════════════════════════════════════════════════")
                logger.warning(
                    f"[RECURSIVE] [BENCHMARK_MODE] EXHAUSTED all {max_benchmark_retries} retries "
                    f"for {thought.thought_id}"
                )
                if last_retry_result:
                    logger.warning(f"[RECURSIVE] Returning last attempt result: {last_retry_result.selected_action}")
                    return last_retry_result, last_retry_conscience_result

            logger.info(f"[RECURSIVE] ════════════════════════════════════════════════════════════")

        return action_result, conscience_result

    @streaming_step(StepPoint.RECURSIVE_ASPDMA)
    @step_point(StepPoint.RECURSIVE_ASPDMA)
    async def _recursive_aspdma_step(
        self, thought_item: ProcessingQueueItem, thought_context: Any, dma_results: Any, override_reason: Any
    ) -> Optional[Any]:
        """Step 3B: Optional retry action selection after conscience failure."""
        logger.info(f"[RECURSIVE_ASPDMA] Starting for thought {thought_item.thought_id}")
        thought = await self._fetch_thought(thought_item.thought_id, thought_item.agent_occurrence_id)  # type: ignore[attr-defined]

        try:
            # Re-run action selection with guidance about why previous action failed
            logger.info(f"[RECURSIVE_ASPDMA] Calling _perform_aspdma_with_guidance...")
            retry_result = await self._perform_aspdma_with_guidance(
                thought, thought_context, dma_results, override_reason, max_retries=3
            )
            logger.info(
                f"[RECURSIVE_ASPDMA] Success - selected action: {retry_result.selected_action if retry_result else 'None'}"
            )
            return retry_result
        except Exception as e:
            logger.error(f"[RECURSIVE_ASPDMA] Failed for thought {thought_item.thought_id}: {e}", exc_info=True)
            return None

    @streaming_step(StepPoint.RECURSIVE_CONSCIENCE)
    @step_point(StepPoint.RECURSIVE_CONSCIENCE)
    async def _recursive_conscience_step(
        self, thought_item: ProcessingQueueItem, retry_result: Any, thought: Any = None
    ) -> Any:
        """Step 4B: Optional re-validation of retry action through conscience system.

        Returns:
            ConscienceApplicationResult with .overridden, .final_action, etc.
        """
        if not retry_result:
            # Return a minimal non-overridden result
            from ciris_engine.schemas.conscience.core import EpistemicData
            from ciris_engine.schemas.processors.core import ConscienceApplicationResult

            return ConscienceApplicationResult(
                original_action=retry_result,
                final_action=retry_result,
                overridden=False,
                override_reason=None,
                epistemic_data=EpistemicData(
                    entropy_level=0.5,
                    coherence_level=0.5,
                    uncertainty_acknowledged=True,
                    reasoning_transparency=0.5,
                ),
            )

        try:
            # Use the proper conscience execution step from the mixin
            conscience_result = await self._conscience_execution_step(  # type: ignore[attr-defined]
                thought_item=thought_item,
                action_result=retry_result,
                thought=thought,
                dma_results=None,
                processing_context=None,
            )
            return conscience_result
        except Exception as e:
            logger.error(f"Recursive conscience execution failed for thought {thought_item.thought_id}: {e}")
            # Return a non-overridden result on failure
            from ciris_engine.schemas.conscience.core import EpistemicData
            from ciris_engine.schemas.processors.core import ConscienceApplicationResult

            return ConscienceApplicationResult(
                original_action=retry_result,
                final_action=retry_result,
                overridden=False,
                override_reason=None,
                epistemic_data=EpistemicData(
                    entropy_level=0.5,
                    coherence_level=0.5,
                    uncertainty_acknowledged=True,
                    reasoning_transparency=0.5,
                ),
            )

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
            logger.info(f"[ASPDMA_GUIDANCE] Attempt {attempt + 1}/{max_retries} for thought {thought.thought_id}")
            try:
                # Extract typed conscience feedback for guidance
                from ciris_engine.schemas.conscience.core import EpistemicData

                override_reason = ""
                epistemic_feedback: EpistemicData

                if isinstance(conscience_result, ConscienceApplicationResult):
                    override_reason = conscience_result.override_reason or "Conscience override occurred"
                    epistemic_feedback = conscience_result.epistemic_data
                    logger.info(f"[ASPDMA_GUIDANCE] Override reason from conscience: {override_reason}")
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
                else:
                    # Handle other types (e.g., the conscience_result itself might have override_reason)
                    if hasattr(conscience_result, "override_reason"):
                        override_reason = conscience_result.override_reason or "Conscience override occurred"
                    else:
                        override_reason = "Conscience override occurred"
                    logger.info(f"[ASPDMA_GUIDANCE] Override reason: {override_reason}")
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

                logger.debug(f"[ASPDMA_GUIDANCE] Guidance context: {guidance_context}")

                # Merge guidance into thought context
                if hasattr(thought_context, "model_dump"):
                    enriched_context = thought_context.model_dump()
                else:
                    enriched_context = dict(thought_context) if isinstance(thought_context, dict) else {}

                enriched_context["conscience_guidance"] = guidance_context

                # Get profile and re-run action selection with conscience guidance
                profile_name = self._get_profile_name(thought)  # type: ignore[attr-defined]
                logger.info(f"[ASPDMA_GUIDANCE] Running action selection with profile: {profile_name}")

                retry_result = await self.dma_orchestrator.run_action_selection(  # type: ignore[attr-defined]
                    thought_item=thought,
                    actual_thought=thought,
                    processing_context=enriched_context,
                    dma_results=dma_results,
                    profile_name=profile_name,
                )

                # Success! Return the result
                logger.info(
                    f"[ASPDMA_GUIDANCE] ✓ Attempt {attempt + 1}/{max_retries} succeeded - "
                    f"Action: {retry_result.selected_action}"
                )
                return retry_result

            except Exception as e:
                last_error = e
                logger.warning(f"[ASPDMA_GUIDANCE] ✗ Attempt {attempt + 1}/{max_retries} failed: {e}")

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
                    logger.error(f"[ASPDMA_GUIDANCE] All {max_retries} attempts exhausted for {thought.thought_id}")
                    raise last_error

                # Otherwise, continue to next retry
                logger.info(f"[ASPDMA_GUIDANCE] Continuing to attempt {attempt + 2}...")
                continue

        # Should never reach here, but just in case
        raise RuntimeError(f"ASPDMA retry logic failed unexpectedly for thought {thought.thought_id}")
