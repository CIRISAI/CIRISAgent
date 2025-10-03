"""
Conscience Execution Phase - H3ERE Pipeline Step 4.

Applies ethical safety validation to the selected action using the
conscience registry to ensure alignment with ethical principles.
"""

import logging
from typing import Any, Dict, Optional

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class ConscienceExecutionPhase:
    """
    Phase 4: Conscience Execution

    Applies ethical safety validation through conscience registry:
    - Validates selected action against ethical principles
    - Can override actions that fail safety checks
    - Provides guidance for retry attempts
    """

    @streaming_step(StepPoint.CONSCIENCE_EXECUTION)
    @step_point(StepPoint.CONSCIENCE_EXECUTION)
    async def _conscience_execution_step(
        self, thought_item: ProcessingQueueItem, action_result, thought=None, dma_results=None, processing_context=None
    ):
        """Step 4: Ethical safety validation matching _apply_conscience_simple expectations."""
        # Import ConscienceApplicationResult here to avoid circular imports
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult

        if not action_result:
            return action_result

        # Check if this is a conscience retry
        is_conscience_retry = (
            processing_context is not None
            and hasattr(processing_context, "is_conscience_retry")
            and processing_context.is_conscience_retry
        )

        # If this is a conscience retry, unset the flag to prevent loops
        if is_conscience_retry and processing_context is not None:
            processing_context.is_conscience_retry = False

        # Exempt actions that shouldn't be overridden
        exempt_actions = {
            HandlerActionType.TASK_COMPLETE.value,
            HandlerActionType.DEFER.value,
            HandlerActionType.REJECT.value,
        }

        if action_result.selected_action in exempt_actions:
            return ConscienceApplicationResult(
                original_action=action_result, final_action=action_result, overridden=False, override_reason=None
            )

        context = {"thought": thought or thought_item, "dma_results": dma_results or {}}

        final_action = action_result
        overridden = False
        override_reason = None
        epistemic_data: Dict[str, str] = {}
        thought_depth_triggered: Optional[bool] = None
        updated_status_detected: Optional[bool] = None

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
            except CircuitBreakerError as e:
                logger.warning(f"conscience {entry.name} unavailable: {e}")
                continue
            except Exception as e:  # noqa: BLE001
                logger.error(f"conscience {entry.name} error: {e}", exc_info=True)
                if cb:
                    cb.record_failure()
                continue

            # Store epistemic data if available
            if result.epistemic_data:
                epistemic_data[entry.name] = result.epistemic_data.model_dump_json()

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

        result = ConscienceApplicationResult(
            original_action=action_result,
            final_action=final_action,
            overridden=overridden,
            override_reason=override_reason,
        )
        if epistemic_data:
            result.epistemic_data = epistemic_data
        if thought_depth_triggered is not None:
            result.thought_depth_triggered = thought_depth_triggered
        if updated_status_detected is not None:
            result.updated_status_detected = updated_status_detected
        return result
