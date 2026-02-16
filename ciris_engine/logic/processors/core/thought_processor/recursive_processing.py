"""
Recursive Processing Phase - H3ERE Pipeline Step 5.

Handles retry logic when conscience validation fails, including:
- RECURSIVE_ASPDMA: Retry action selection with guidance
- RECURSIVE_CONSCIENCE: Re-validate the retried action

In benchmark mode (CIRIS_BENCHMARK_MODE=true), keeps retrying up to
max_benchmark_retries times when conscience overrides to PONDER.
"""

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from ciris_engine.logic.config.env_utils import get_env_var
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

# Constants for logging separators
_LOG_SEPARATOR_MAJOR = "════════════════════════════════════════════════════════════"
_LOG_SEPARATOR_MINOR = "──────────────────────────────────────────────────────────"
_DEFAULT_OVERRIDE_REASON = "Conscience override occurred"


@dataclass
class RetryAttemptResult:
    """Result from a single retry attempt."""

    action_result: Optional[Any]
    conscience_result: Any
    passed: bool


def _is_benchmark_mode() -> bool:
    """Check if benchmark mode is enabled."""
    benchmark_mode_val = get_env_var("CIRIS_BENCHMARK_MODE", "") or ""
    return benchmark_mode_val.lower() in ("true", "1", "yes", "on")


def _is_ponder_override(conscience_result: Any) -> bool:
    """Check if conscience result is an override to PONDER action."""
    return (
        conscience_result
        and conscience_result.overridden
        and conscience_result.final_action.selected_action == HandlerActionType.PONDER
    )


def _create_neutral_conscience_result(action_result: Any) -> ConscienceApplicationResult:
    """Create a non-overridden conscience result for fallback cases."""
    return ConscienceApplicationResult(
        original_action=action_result,
        final_action=action_result,
        overridden=False,
        override_reason=None,
        epistemic_data=EpistemicData.create_neutral(),
    )


def _log_speak_content(retry_result: Any, retry_count: int) -> None:
    """Log SPEAK action content preview if applicable."""
    if retry_result.selected_action != HandlerActionType.SPEAK:
        return
    content = ""
    if hasattr(retry_result.action_parameters, "content"):
        content = retry_result.action_parameters.content or ""
    logger.info(f"[RECURSIVE] Retry {retry_count} - SPEAK content preview: {content[:150]}...")


def _extract_conscience_feedback(conscience_result: Any) -> Tuple[str, EpistemicData]:
    """Extract override reason and epistemic data from conscience result.

    Returns:
        Tuple of (override_reason, epistemic_data)
    """
    # Import here to avoid circular imports
    from ciris_engine.schemas.processors.core import ConscienceApplicationResult as CAR

    if isinstance(conscience_result, CAR):
        return (
            conscience_result.override_reason or _DEFAULT_OVERRIDE_REASON,
            conscience_result.epistemic_data,
        )

    if isinstance(conscience_result, dict):
        override_reason = conscience_result.get("override_reason", _DEFAULT_OVERRIDE_REASON)
        epistemic_data = conscience_result.get("epistemic_data")
        if isinstance(epistemic_data, EpistemicData):
            return override_reason, epistemic_data
        return override_reason, EpistemicData.create_neutral()

    # Handle objects with override_reason attribute
    if hasattr(conscience_result, "override_reason"):
        return (
            conscience_result.override_reason or _DEFAULT_OVERRIDE_REASON,
            EpistemicData.create_neutral(),
        )

    return _DEFAULT_OVERRIDE_REASON, EpistemicData.create_neutral()


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

        Returns:
            Tuple of (final_result, final_conscience_result)
        """
        if not _is_ponder_override(conscience_result):
            return action_result, conscience_result

        benchmark_mode = _is_benchmark_mode()
        max_retries = 5

        self._log_retry_start(thought.thought_id, conscience_result, benchmark_mode, max_retries)

        result = await self._execute_retry_loop(
            thought_item, thought, thought_context, dma_results,
            conscience_result, benchmark_mode, max_retries
        )

        logger.info(f"[RECURSIVE] {_LOG_SEPARATOR_MAJOR}")
        return result if result else (action_result, conscience_result)

    def _log_retry_start(
        self, thought_id: str, conscience_result: Any, benchmark_mode: bool, max_retries: int
    ) -> None:
        """Log the start of recursive retry processing."""
        logger.info(f"[RECURSIVE] {_LOG_SEPARATOR_MAJOR}")
        logger.info(f"[RECURSIVE] Conscience override to PONDER for thought {thought_id}")
        logger.info(f"[RECURSIVE] Override reason: {conscience_result.override_reason}")
        logger.info(f"[RECURSIVE] Benchmark mode: {benchmark_mode} | Max retries: {max_retries}")
        logger.info("[RECURSIVE] Starting recursive ASPDMA retry loop...")

    async def _execute_retry_loop(
        self,
        thought_item: Any,
        thought: Any,
        thought_context: Any,
        dma_results: Any,
        initial_conscience_result: Any,
        benchmark_mode: bool,
        max_retries: int,
    ) -> Optional[Tuple[Any, Any]]:
        """Execute the retry loop, returning successful result or None."""
        current_conscience = initial_conscience_result
        last_attempt: Optional[RetryAttemptResult] = None

        for retry_count in range(1, max_retries + 1):
            logger.info(f"[RECURSIVE] {_LOG_SEPARATOR_MINOR}")
            logger.info(f"[RECURSIVE] Retry attempt {retry_count}/{max_retries} for {thought.thought_id}")

            attempt = await self._execute_single_retry(
                thought_item, thought, thought_context, dma_results, current_conscience, retry_count
            )

            if attempt is None:
                break

            last_attempt = attempt

            if attempt.passed:
                logger.info(
                    f"[RECURSIVE] ✓ SUCCESS on retry {retry_count} - "
                    f"Action {attempt.action_result.selected_action} passed all consciences!"
                )
                return attempt.action_result, attempt.conscience_result

            # Handle retry failure
            if not self._should_continue_retrying(attempt.conscience_result, benchmark_mode, retry_count, max_retries):
                break
            current_conscience = attempt.conscience_result

        # Handle benchmark mode exhaustion
        if benchmark_mode and last_attempt and last_attempt.action_result:
            logger.warning(f"[RECURSIVE] [BENCHMARK_MODE] EXHAUSTED all {max_retries} retries")
            logger.warning(f"[RECURSIVE] Returning last attempt result: {last_attempt.action_result.selected_action}")
            return last_attempt.action_result, last_attempt.conscience_result

        return None

    async def _execute_single_retry(
        self,
        thought_item: Any,
        thought: Any,
        thought_context: Any,
        dma_results: Any,
        current_conscience: Any,
        retry_count: int,
    ) -> Optional[RetryAttemptResult]:
        """Execute a single retry attempt, returning the result or None on failure."""
        retry_result = await self._recursive_aspdma_step(
            thought_item, thought_context, dma_results, current_conscience
        )

        if not retry_result:
            logger.warning(f"[RECURSIVE] ✗ Retry {retry_count} - ASPDMA returned no result, stopping")
            return None

        logger.info(f"[RECURSIVE] Retry {retry_count} - ASPDMA selected action: {retry_result.selected_action}")
        _log_speak_content(retry_result, retry_count)

        logger.info(f"[RECURSIVE] Retry {retry_count} - Running conscience checks...")
        conscience_result = await self._recursive_conscience_step(thought_item, retry_result, thought=thought)

        passed = not conscience_result.overridden
        if not passed:
            logger.warning(f"[RECURSIVE] ✗ Retry {retry_count} - Conscience override: {conscience_result.override_reason}")

        return RetryAttemptResult(
            action_result=retry_result,
            conscience_result=conscience_result,
            passed=passed,
        )

    def _should_continue_retrying(
        self, conscience_result: Any, benchmark_mode: bool, retry_count: int, max_retries: int
    ) -> bool:
        """Determine if we should continue retrying after a failed attempt."""
        if benchmark_mode and _is_ponder_override(conscience_result):
            logger.info(
                f"[RECURSIVE] [BENCHMARK_MODE] Retry {retry_count}/{max_retries} "
                "failed conscience check, bouncing to next attempt..."
            )
            return True
        logger.info(f"[RECURSIVE] Normal mode - stopping after conscience failure on retry {retry_count}")
        return False

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
    ) -> ConscienceApplicationResult:
        """Step 4B: Optional re-validation of retry action through conscience system.

        Returns:
            ConscienceApplicationResult with .overridden, .final_action, etc.
        """
        if not retry_result:
            return _create_neutral_conscience_result(retry_result)

        try:
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
            return _create_neutral_conscience_result(retry_result)

    async def _perform_aspdma_with_guidance(
        self,
        thought: Any,
        thought_context: Any,
        dma_results: Any,
        conscience_result: Any,
        max_retries: int = 3,
    ) -> Any:
        """Retry action selection with conscience guidance and cumulative feedback."""
        last_error: Optional[Exception] = None
        retry_history: List[JSONDict] = []

        for attempt in range(max_retries):
            logger.info(f"[ASPDMA_GUIDANCE] Attempt {attempt + 1}/{max_retries} for thought {thought.thought_id}")
            try:
                retry_result = await self._execute_guided_action_selection(
                    thought, thought_context, dma_results, conscience_result, attempt, max_retries, retry_history
                )
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

    async def _execute_guided_action_selection(
        self,
        thought: Any,
        thought_context: Any,
        dma_results: Any,
        conscience_result: Any,
        attempt: int,
        max_retries: int,
        retry_history: List[JSONDict],
    ) -> Any:
        """Execute a single guided action selection attempt."""
        override_reason, epistemic_feedback = _extract_conscience_feedback(conscience_result)
        logger.info(f"[ASPDMA_GUIDANCE] Override reason: {override_reason}")

        guidance_context = {
            "retry_attempt": attempt + 1,
            "max_retries": max_retries,
            "original_action_failed_because": override_reason,
            "conscience_feedback": {
                "epistemic_data": epistemic_feedback,
                "override_detected": True,
            },
            "retry_history": retry_history,
        }
        logger.debug(f"[ASPDMA_GUIDANCE] Guidance context: {guidance_context}")

        enriched_context = self._build_enriched_context(thought_context, guidance_context)

        profile_name = self._get_profile_name(thought)  # type: ignore[attr-defined]
        logger.info(f"[ASPDMA_GUIDANCE] Running action selection with profile: {profile_name}")

        return await self.dma_orchestrator.run_action_selection(  # type: ignore[attr-defined]
            thought_item=thought,
            actual_thought=thought,
            processing_context=enriched_context,
            dma_results=dma_results,
            profile_name=profile_name,
        )

    def _build_enriched_context(self, thought_context: Any, guidance_context: JSONDict) -> JSONDict:
        """Build enriched context by merging guidance into thought context."""
        if hasattr(thought_context, "model_dump"):
            enriched_context: JSONDict = thought_context.model_dump()
        elif isinstance(thought_context, dict):
            enriched_context = dict(thought_context)
        else:
            enriched_context = {}
        enriched_context["conscience_guidance"] = guidance_context
        return enriched_context
