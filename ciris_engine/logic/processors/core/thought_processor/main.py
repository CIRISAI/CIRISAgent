"""
ThoughtProcessor: Core orchestration logic for H3ERE pipeline.
Main coordinator that executes the 7 phases of ethical reasoning.
"""

import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.handlers.control.ponder_handler import PonderHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError
from ciris_engine.logic.utils.channel_utils import create_channel_context
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import DeferParams, PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought, ThoughtStatus
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)

from .action_execution import ActionExecutionPhase
from .conscience_execution import ConscienceExecutionPhase
from .finalize_action import ActionFinalizationPhase
from .gather_context import ContextGatheringPhase
from .perform_aspdma import ActionSelectionPhase
from .perform_dmas import DMAExecutionPhase
from .recursive_processing import RecursiveProcessingPhase
from .round_complete import RoundCompletePhase

# Import phase mixins
from .start_round import RoundInitializationPhase

logger = logging.getLogger(__name__)


class ThoughtProcessor(
    RoundInitializationPhase,
    ContextGatheringPhase,
    DMAExecutionPhase,
    ActionSelectionPhase,
    ConscienceExecutionPhase,
    RecursiveProcessingPhase,
    ActionFinalizationPhase,
    ActionExecutionPhase,
    RoundCompletePhase,
):
    """
    Main orchestrator for the H3ERE (Hyper3 Ethical Recursive Engine) pipeline.

    Inherits phase-specific methods from mixin classes and coordinates
    the 7-step ethical reasoning process:
    1. GATHER_CONTEXT - Build processing context
    2. PERFORM_DMAS - Multi-perspective analysis
    3. PERFORM_ASPDMA - Action selection
    4. CONSCIENCE_EXECUTION - Ethical validation
    5. RECURSIVE_* - Retry logic (optional)
    6. FINALIZE_ACTION - Final action determination
    7. ACTION_* - Action dispatch and completion
    """

    def __init__(
        self,
        dma_orchestrator: Any,
        context_builder: Any,
        conscience_registry: Any,
        app_config: ConfigAccessor,
        dependencies: ActionHandlerDependencies,
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        auth_service: Optional[Any] = None,
    ) -> None:
        self.dma_orchestrator = dma_orchestrator
        self.context_builder = context_builder
        self.conscience_registry = conscience_registry
        self.app_config = app_config
        self.dependencies = dependencies
        self._time_service = time_service
        self.telemetry_service = telemetry_service
        self.auth_service = auth_service
        self._pipeline_controller = None  # Will be deprecated

    async def process_thought(
        self, thought_item: ProcessingQueueItem, context: Optional[dict] = None
    ) -> Optional[ActionSelectionDMAResult]:
        """
        Main H3ERE pipeline orchestration.

        Executes all 7 phases using decorated step methods that handle
        streaming and single-step pause/resume automatically.
        """
        logger.info(
            f"ThoughtProcessor.process_thought: ENTRY - thought_id={thought_item.thought_id}, context={'present' if context else 'None'}"
        )
        start_time = self._time_service.now()

        # Initialize correlation for tracking
        correlation = ServiceCorrelation(
            correlation_id=f"thought_processing_{thought_item.thought_id}_{start_time.timestamp()}",
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            service_type="ThoughtProcessor",
            handler_name="process_thought",
            action_type="PROCESS_THOUGHT",
            created_at=start_time,
            updated_at=start_time,
            timestamp=start_time,
        )
        persistence.add_correlation(correlation, self._time_service)

        # Fetch the actual thought
        logger.info(f"ThoughtProcessor.process_thought: About to fetch thought_id={thought_item.thought_id}")
        thought = await self._fetch_thought(thought_item.thought_id)
        logger.info(
            f"ThoughtProcessor.process_thought: Fetch completed for thought_id={thought_item.thought_id}, result={'present' if thought else 'None'}"
        )
        if not thought:
            logger.warning(f"ThoughtProcessor: Could not fetch thought {thought_item.thought_id}")
            return None

        # 0. START_ROUND - Initialize processing round
        await self._start_round_step(thought_item, context)

        # 1. GATHER_CONTEXT - Build processing context
        thought_context = await self._gather_context_step(thought_item, context)

        # 2. PERFORM_DMAS - Multi-perspective analysis
        dma_results = await self._perform_dmas_step(thought_item, thought_context)

        # 2a. If DMA step returned an ActionSelectionDMAResult (due to failure), return it directly
        if isinstance(dma_results, ActionSelectionDMAResult):
            logger.info(
                f"DMA step returned ActionSelectionDMAResult for thought {thought_item.thought_id}: {dma_results.selected_action}"
            )
            return dma_results

        # 3. Check for failures/escalations
        if self._has_critical_failure(dma_results):
            end_time = self._time_service.now()
            from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "error_message": "Critical DMA failure",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, self._time_service)
            return self._create_deferral_result(dma_results, thought)

        # 4. PERFORM_ASPDMA - LLM-powered action selection
        action_result = await self._perform_aspdma_step(thought_item, thought_context, dma_results)

        # Get profile name for potential conscience retry
        profile_name = self._get_profile_name(thought)

        # Debug logging for action result
        if action_result:
            selected_action = getattr(action_result, "selected_action", "UNKNOWN")
            logger.info(f"ThoughtProcessor: Action selection result for {thought.thought_id}: {selected_action}")

            if selected_action == HandlerActionType.OBSERVE:
                logger.warning(
                    f"OBSERVE ACTION DEBUG: ThoughtProcessor received OBSERVE action for thought {thought.thought_id}"
                )
        else:
            logger.error(f"ThoughtProcessor: No action result for thought {thought.thought_id}")

        # 5. CONSCIENCE_EXECUTION - Apply ethical safety validation
        conscience_result = await self._conscience_execution_step(
            thought_item, action_result, thought, dma_results, thought_context
        )

        # 6a. If consciences overrode to PONDER, try action selection once more with guidance
        if (
            conscience_result
            and conscience_result.overridden
            and conscience_result.final_action.selected_action == HandlerActionType.PONDER
        ):

            logger.info(
                f"ThoughtProcessor: conscience override to PONDER for {thought.thought_id}. Attempting re-run with guidance."
            )

            # Extract the conscience feedback
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

            try:
                # Re-run action selection with guidance
                retry_result = await self.dma_orchestrator.run_action_selection(
                    thought_item=thought_item,
                    actual_thought=thought,
                    processing_context=retry_context,
                    dma_results=dma_results,
                    profile_name=profile_name,
                )

                if retry_result:
                    # Always re-apply consciences, even if same action type (parameters may differ)

                    logger.info(
                        f"ThoughtProcessor: Re-running consciences on retry action {retry_result.selected_action}"
                    )
                    retry_conscience_result = await self._conscience_execution_step(
                        thought_item, retry_result, thought, dma_results, retry_context
                    )

                    # If the retry passes consciences, use it
                    if not retry_conscience_result.overridden:
                        logger.info(f"ThoughtProcessor: Retry action {retry_result.selected_action} passed consciences")
                        conscience_result = retry_conscience_result
                        action_result = retry_result
                    else:
                        # Log details about what failed
                        logger.info(
                            f"ThoughtProcessor: Retry action {retry_result.selected_action} also failed consciences"
                        )
                        if retry_result.selected_action == conscience_result.original_action.selected_action:
                            logger.info("ThoughtProcessor: Same action type but with different parameters still failed")
                        logger.info("ThoughtProcessor: Proceeding with PONDER")
                else:
                    logger.info("ThoughtProcessor: Retry failed to produce a result, proceeding with PONDER")

            except Exception as e:
                logger.error(f"Error during action selection retry: {e}", exc_info=True)
                # Continue with original PONDER if retry fails

        if action_result.selected_action == HandlerActionType.OBSERVE:
            logger.debug(
                "ThoughtProcessor: OBSERVE action after consciences for thought %s",
                thought.thought_id,
            )

        # DEBUG: Log conscience result details
        if conscience_result:
            if hasattr(conscience_result, "final_action") and conscience_result.final_action:
                final_action = getattr(conscience_result.final_action, "selected_action", "UNKNOWN")
                logger.info(
                    f"ThoughtProcessor: conscience result for {thought.thought_id}: final_action={final_action}"
                )

        # 6. FINALIZE_ACTION - Determine final result
        action_from_conscience = self._handle_special_cases(conscience_result, thought, thought_context)
        final_result = await self._finalize_action_step(thought_item, action_from_conscience)

        # Record successful completion
        if self.telemetry_service:
            await self.telemetry_service.record_metric(
                "thought_processing_completed",
                value=1.0,
                tags={"thought_id": thought.thought_id, "path_type": "hot", "source_module": "thought_processor"},
            )
            if final_result:
                action_metric = f"action_selected_{final_result.selected_action.value}"
                await self.telemetry_service.record_metric(
                    action_metric,
                    value=1.0,
                    tags={
                        "thought_id": thought.thought_id,
                        "action": final_result.selected_action.value,
                        "path_type": "hot",
                        "source_module": "thought_processor",
                    },
                )

        # Update correlation with success
        end_time = self._time_service.now()
        from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

        update_req = CorrelationUpdateRequest(
            correlation_id=correlation.correlation_id,
            response_data={
                "success": "true",
                "result_summary": f"Successfully processed thought with action: {final_result.selected_action if final_result else 'none'}",
                "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                "response_timestamp": end_time.isoformat(),
            },
            status=ServiceCorrelationStatus.COMPLETED,
            metric_value=None,
            tags=None,
        )
        persistence.update_correlation(update_req, self._time_service)

        # 7. ROUND_COMPLETE - Finalize the processing round
        final_result = await self._round_complete_step(thought_item, final_result)

        return final_result

    # Helper methods that will remain in main.py
    async def _fetch_thought(self, thought_id: str) -> Optional[Thought]:
        """Fetch thought from persistence layer."""
        import asyncio

        from ciris_engine.logic import persistence

        logger.info(f"ThoughtProcessor._fetch_thought: Starting fetch for thought_id={thought_id}")

        try:
            # Add timeout protection to prevent CI hangs
            thought = await asyncio.wait_for(
                persistence.async_get_thought_by_id(thought_id), timeout=30.0  # 30 second timeout
            )
            logger.info(
                f"ThoughtProcessor._fetch_thought: Successfully fetched thought_id={thought_id}, thought={'present' if thought else 'None'}"
            )
            return thought
        except asyncio.TimeoutError:
            logger.error(f"ThoughtProcessor._fetch_thought: TIMEOUT after 30s fetching thought_id={thought_id}")
            raise
        except Exception as e:
            logger.error(
                f"ThoughtProcessor._fetch_thought: ERROR fetching thought_id={thought_id}: {type(e).__name__}: {e}"
            )
            raise

    def _has_critical_failure(self, dma_results) -> bool:
        """Check if DMA results indicate critical failure requiring escalation."""
        if not dma_results:
            return True

        # Check for specific failure indicators
        if hasattr(dma_results, "critical_failure") and dma_results.critical_failure:
            return True

        if hasattr(dma_results, "should_escalate") and dma_results.should_escalate:
            return True

        return False

    def _create_deferral_result(self, dma_results, thought) -> ActionSelectionDMAResult:
        """Create a deferral result for failed processing."""
        from ciris_engine.logic.utils.constants import DEFAULT_WA

        defer_reason = "Critical DMA failure or conscience override."
        # Convert dma_results to string representation for context
        dma_results_str = str(dma_results) if not isinstance(dma_results, str) else dma_results
        defer_params = DeferParams(
            reason=defer_reason,
            context={
                "original_thought_id": thought.thought_id,
                "dma_results_summary": dma_results_str,
                "target_wa_ual": str(DEFAULT_WA) if DEFAULT_WA else "",
            },
            defer_until=None,
        )

        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=defer_params,
            rationale=defer_reason,
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

    def _get_profile_name(self, thought: Thought) -> str:
        """Extract profile name from thought context or use default."""
        profile_name = None
        if hasattr(thought, "context") and thought.context:
            context = thought.context
            if hasattr(context, "agent_profile_name"):
                profile_name = context.agent_profile_name
        if not profile_name and hasattr(self.app_config, "agent_profiles"):
            for name, profile in self.app_config.agent_profiles.items():
                if name != "default" and profile:
                    profile_name = name
                    break
        if not profile_name and hasattr(self.app_config, "default_profile"):
            profile_name = self.app_config.default_profile
        if not profile_name:
            profile_name = "default"
        logger.debug(f"Determined profile name '{profile_name}' for thought {thought.thought_id}")
        return profile_name

    def _describe_action(self, action_result) -> str:
        """Generate a human-readable description of an action."""
        if not hasattr(action_result, "selected_action"):
            return "unknown action"

        action_type = action_result.selected_action
        params = action_result.action_parameters

        descriptions = {
            HandlerActionType.SPEAK: lambda p: (
                f"speak: '{p.content[:50]}...'"
                if hasattr(p, "content") and len(str(p.content)) > 50
                else f"speak: '{p.content}'" if hasattr(p, "content") else "speak"
            ),
            HandlerActionType.TOOL: lambda p: f"use tool '{p.tool_name}'" if hasattr(p, "tool_name") else "use a tool",
            HandlerActionType.OBSERVE: lambda p: (
                f"observe channel '{p.channel_id}'" if hasattr(p, "channel_id") else "observe"
            ),
            HandlerActionType.MEMORIZE: lambda p: "memorize information",
            HandlerActionType.RECALL: lambda p: "recall information",
            HandlerActionType.FORGET: lambda p: "forget information",
        }

        desc_func = descriptions.get(action_type, lambda p: f"{action_type.value}")
        try:
            return desc_func(params)
        except Exception as e:
            logger.warning(
                f"Failed to generate action description for {action_type.value}: {e}. Using default description."
            )
            return f"{action_type.value}"

    async def _apply_conscience_simple(
        self,
        action_result: ActionSelectionDMAResult,
        thought: Thought,
        dma_results_dict: dict,
        processing_context: Optional[Any] = None,
    ) -> Any:
        """Simple conscience application without orchestrator."""
        # Import ConscienceApplicationResult here to avoid circular imports
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult

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

        context = {"thought": thought, "dma_results": dma_results_dict}

        final_action = action_result
        overridden = False
        override_reason = None
        epistemic_data: Dict[str, str] = {}

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
                epistemic_data[entry.name] = result.epistemic_data.model_dump()

            if not result.passed:
                overridden = True
                override_reason = result.reason

                # Check if the conscience provides a replacement action
                if (
                    result.epistemic_data
                    and hasattr(result.epistemic_data, "get")
                    and "replacement_action" in result.epistemic_data
                ):
                    # Use the conscience's suggested replacement action
                    replacement_data = result.epistemic_data["replacement_action"]
                    final_action = ActionSelectionDMAResult.model_validate(replacement_data)
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
        return result

    def _handle_special_cases(self, conscience_result, thought, thought_context):
        """Handle special processing cases (PONDER, DEFER overrides)."""
        # This method handles edge cases and will be kept in main.py
        # Implementation would go here based on current logic
        if conscience_result and hasattr(conscience_result, "final_action"):
            return conscience_result.final_action
        return None
