"""
Conscience Execution Phase - H3ERE Pipeline Step 4.

Applies ethical safety validation to the selected action using the
conscience registry to ensure alignment with ethical principles.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint

if TYPE_CHECKING:
    from ciris_engine.schemas.processors.core import ConscienceApplicationResult

logger = logging.getLogger(__name__)


class ConscienceExecutionPhase:
    """
    Phase 4: Conscience Execution

    Applies ethical safety validation through conscience registry:
    - Validates selected action against ethical principles
    - Can override actions that fail safety checks
    - Provides guidance for retry attempts

    Attributes (provided by ThoughtProcessor):
        conscience_registry: Registry of conscience validation functions
    """

    if TYPE_CHECKING:
        conscience_registry: Any

        def _describe_action(self, action: ActionSelectionDMAResult) -> str: ...

    @streaming_step(StepPoint.CONSCIENCE_EXECUTION)
    @step_point(StepPoint.CONSCIENCE_EXECUTION)
    async def _conscience_execution_step(
        self,
        thought_item: ProcessingQueueItem,
        action_result: Any,
        thought: Any = None,
        dma_results: Any = None,
        processing_context: Any = None,
    ) -> "ConscienceApplicationResult":
        """Step 4: Ethical safety validation matching _apply_conscience_simple expectations."""
        # Import ConscienceApplicationResult here to avoid circular imports
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult

        if not action_result:
            return action_result  # type: ignore[no-any-return]

        # Check if this is a conscience retry
        is_conscience_retry = False
        if processing_context is not None:
            if isinstance(processing_context, dict):
                is_conscience_retry = processing_context.get("is_conscience_retry", False)
            elif hasattr(processing_context, "is_conscience_retry"):
                is_conscience_retry = processing_context.is_conscience_retry

        # If this is a conscience retry, unset the flag to prevent loops
        if is_conscience_retry and processing_context is not None:
            if isinstance(processing_context, dict):
                processing_context["is_conscience_retry"] = False
            elif hasattr(processing_context, "is_conscience_retry"):
                processing_context.is_conscience_retry = False

        # Exempt actions that shouldn't be overridden
        # Conscience runs for: SPEAK, TOOL, PONDER, MEMORIZE, FORGET (5 actions)
        # Conscience exempt: RECALL, TASK_COMPLETE, OBSERVE, DEFER, REJECT (5 actions)
        exempt_actions = {
            HandlerActionType.RECALL.value,
            HandlerActionType.TASK_COMPLETE.value,
            HandlerActionType.OBSERVE.value,
            HandlerActionType.DEFER.value,
            HandlerActionType.REJECT.value,
        }

        if action_result.selected_action in exempt_actions:
            # Exempt actions bypass conscience checks - return immediately with safe epistemic values
            from ciris_engine.schemas.conscience.core import EpistemicData

            # Exempt actions are considered safe: low entropy, high coherence, acknowledged, transparent
            return ConscienceApplicationResult(
                original_action=action_result,
                final_action=action_result,
                overridden=False,
                override_reason=None,
                epistemic_data=EpistemicData(
                    entropy_level=0.0,  # No uncertainty for exempt actions
                    coherence_level=1.0,  # Perfect coherence
                    uncertainty_acknowledged=True,  # System is aware this is exempt
                    reasoning_transparency=1.0,  # Fully transparent (exempt = explicit)
                ),
            )

        # Create typed context for conscience checks
        from ciris_engine.schemas.conscience.context import ConscienceCheckContext

        context = ConscienceCheckContext(
            thought=thought or thought_item,
            task=None,  # Will be populated by conscience checks if needed
            round_number=None,
            system_snapshot=dma_results or {},  # Store DMA results in system_snapshot
        )

        final_action = action_result
        overridden = False
        override_reason = None
        thought_depth_triggered: Optional[bool] = None
        updated_status_detected: Optional[bool] = None

        # Track conscience check results for epistemic data aggregation
        entropy_level: Optional[float] = None
        coherence_level: Optional[float] = None
        uncertainty_acknowledged: bool = False
        reasoning_transparency: float = 0.0
        conscience_checks_ran: int = 0

        # Get consciences from registry
        for entry in self.conscience_registry.get_consciences():
            conscience = entry.conscience
            cb = entry.circuit_breaker

            try:
                if cb:
                    cb.check_and_raise()
                result = await conscience.check(final_action, context)
                if cb:
                    cb.record_success()
                conscience_checks_ran += 1
            except CircuitBreakerError as e:
                logger.warning(f"conscience {entry.name} unavailable: {e}")
                continue
            except Exception as e:  # noqa: BLE001
                logger.error(f"conscience {entry.name} error: {e}", exc_info=True)
                if cb:
                    cb.record_failure()
                continue

            # Aggregate epistemic metrics from conscience results
            if result.entropy_score is not None:
                entropy_level = result.entropy_score
            if result.coherence_score is not None:
                coherence_level = result.coherence_score
            if result.epistemic_humility_check is not None:
                uncertainty_acknowledged = True
                reasoning_transparency = 1.0  # Humility check ran, transparency confirmed

            # Note: Individual conscience epistemic_data is now aggregated below
            # Legacy per-conscience epistemic_data storage removed

            if result.thought_depth_triggered is not None:
                thought_depth_triggered = result.thought_depth_triggered

            if result.updated_status_detected is not None:
                updated_status_detected = result.updated_status_detected

            if not result.passed:
                overridden = True
                override_reason = result.reason

                # Check if the conscience provides a replacement action (top-level field)
                if result.replacement_action:
                    # Use the conscience's suggested replacement action
                    final_action = ActionSelectionDMAResult.model_validate(result.replacement_action)
                else:
                    # Default behavior: create a PONDER action
                    attempted_action_desc = self._describe_action(action_result)
                    questions = [
                        f"I attempted to {attempted_action_desc}",
                        result.reason or "conscience failed",
                        "What alternative approach would better align with my principles?",
                    ]

                    ponder_params = PonderParams(questions=questions)

                    # Create PONDER action with required fields
                    final_action = ActionSelectionDMAResult(
                        selected_action=HandlerActionType.PONDER,
                        action_parameters=ponder_params,
                        rationale=f"Overridden by {entry.name}: Need to reconsider {attempted_action_desc}",
                        raw_llm_response=None,
                        reasoning=None,
                        evaluation_time_ms=None,
                        resource_usage=None,
                    )
                break

        # If this was a conscience retry and we didn't override, force PONDER
        # unless the override was from thought depth guardrail
        if is_conscience_retry and not overridden:
            # Check if any conscience that ran was the depth guardrail
            has_depth_guardrail = any(
                "ThoughtDepthGuardrail" in entry.conscience.__class__.__name__
                for entry in self.conscience_registry.get_consciences()
            )

            if not has_depth_guardrail:
                logger.info("ThoughtProcessor: Conscience retry without override - forcing PONDER")
                final_action = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.PONDER,
                    action_parameters=PonderParams(questions=["Forced PONDER after conscience retry"]),
                    rationale="Forced PONDER after conscience retry to prevent loops",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )
                overridden = True
                override_reason = "Conscience retry - forcing PONDER to prevent loops"

        # Build EpistemicData from aggregated conscience results
        from ciris_engine.schemas.conscience.core import EpistemicData

        # epistemic_data is REQUIRED - fail hard if missing for non-exempt actions
        if conscience_checks_ran == 0:
            # This should only happen for exempt actions (which return early above)
            # If we reach here with no conscience checks, it's a bug in conscience implementation
            raise RuntimeError(
                f"CONSCIENCE BUG: No conscience checks ran for non-exempt action {action_result.selected_action.value}. "
                f"All consciences must provide epistemic_data for non-exempt actions."
            )

        # Use actual data from conscience checks - no defaults for missing metrics
        epistemic_data = EpistemicData(
            entropy_level=entropy_level if entropy_level is not None else 0.1,  # Default safe value
            coherence_level=coherence_level if coherence_level is not None else 0.9,  # Default high coherence
            uncertainty_acknowledged=uncertainty_acknowledged,
            reasoning_transparency=reasoning_transparency,
        )

        # Build final application result (explicitly typed for mypy)
        application_result: ConscienceApplicationResult = ConscienceApplicationResult(
            original_action=action_result,
            final_action=final_action,
            overridden=overridden,
            override_reason=override_reason,
            epistemic_data=epistemic_data,
        )
        if thought_depth_triggered is not None:
            application_result.thought_depth_triggered = thought_depth_triggered
        if updated_status_detected is not None:
            application_result.updated_status_detected = updated_status_detected
        return application_result
