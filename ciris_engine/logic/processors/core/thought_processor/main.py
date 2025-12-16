"""
ThoughtProcessor: Core orchestration logic for H3ERE pipeline.
Main coordinator that executes the 7 phases of ethical reasoning.
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from ciris_engine.logic import persistence
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.handlers.control.ponder_handler import PonderHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError
from ciris_engine.logic.utils.channel_utils import create_channel_context
from ciris_engine.logic.utils.jsondict_helpers import get_bool, get_dict
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import DeferParams, PonderParams
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.processors.core import (
    ConscienceApplicationResult,
    ConscienceCheckInternalResult,
    SingleConscienceCheckResult,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)
from ciris_engine.schemas.types import JSONDict

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
        self, thought_item: ProcessingQueueItem, context: Optional[JSONDict] = None
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
        correlation = self._initialize_correlation(thought_item, start_time)

        # Fetch and validate thought
        thought = await self._fetch_and_validate_thought(thought_item)
        if not thought:
            return None

        # Execute pipeline phases
        pipeline_result = await self._execute_pipeline_phases(thought_item, thought, context, correlation, start_time)

        # Record completion and finalize
        await self._record_processing_completion(thought, pipeline_result)
        await self._finalize_correlation(correlation, pipeline_result, start_time)

        # Complete the round
        final_result = await self._round_complete_step(thought_item, pipeline_result)
        # _round_complete_step returns the same type as pipeline_result (ConscienceApplicationResult or ActionSelectionDMAResult)
        return final_result  # type: ignore[no-any-return]

    def _initialize_correlation(self, thought_item: ProcessingQueueItem, start_time: Any) -> ServiceCorrelation:
        """Initialize correlation tracking for the thought processing."""
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
        return correlation

    async def _fetch_and_validate_thought(self, thought_item: ProcessingQueueItem) -> Optional[Thought]:
        """Fetch and validate thought exists."""
        logger.info(f"ThoughtProcessor.process_thought: About to fetch thought_id={thought_item.thought_id}")
        thought = await self._fetch_thought(thought_item.thought_id, thought_item.agent_occurrence_id)
        logger.info(
            f"ThoughtProcessor.process_thought: Fetch completed for thought_id={thought_item.thought_id}, result={'present' if thought else 'None'}"
        )
        if not thought:
            logger.warning(f"ThoughtProcessor: Could not fetch thought {thought_item.thought_id}")
        return thought

    async def _execute_pipeline_phases(
        self,
        thought_item: ProcessingQueueItem,
        thought: Thought,
        context: Optional[JSONDict],
        correlation: ServiceCorrelation,
        start_time: Any,
    ) -> ConscienceApplicationResult:
        """Execute the main H3ERE pipeline phases."""
        # Phase 0: Initialize processing round
        await self._start_round_step(thought_item, context)

        # Phase 1: Gather context
        thought_context = await self._gather_context_step(thought_item, context)

        # Phase 2: DMA analysis
        dma_results = await self._perform_dmas_step(thought_item, thought_context)

        # Check for early DMA result return
        if isinstance(dma_results, ActionSelectionDMAResult):
            logger.info(
                f"DMA step returned ActionSelectionDMAResult for thought {thought_item.thought_id}: {dma_results.selected_action}"
            )
            # Wrap in ConscienceApplicationResult before returning
            return ConscienceApplicationResult(
                original_action=dma_results,
                final_action=dma_results,
                overridden=False,
                override_reason=None,
                epistemic_data=EpistemicData(
                    entropy_level=0.0,  # Exempt action - no uncertainty
                    coherence_level=1.0,  # Fully coherent
                    uncertainty_acknowledged=True,  # System knows this is exempt
                    reasoning_transparency=1.0,  # Fully transparent (DEFER/REJECT)
                ),
            )

        # Check for critical failures
        if self._has_critical_failure(dma_results):
            await self._handle_critical_failure(correlation, start_time)
            deferral_result = self._create_deferral_result(dma_results, thought)
            # Wrap in ConscienceApplicationResult before returning
            return ConscienceApplicationResult(
                original_action=deferral_result,
                final_action=deferral_result,
                overridden=False,
                override_reason=None,
                epistemic_data=EpistemicData(
                    entropy_level=1.0,  # Maximum uncertainty due to failure
                    coherence_level=0.0,  # No coherence - system failed
                    uncertainty_acknowledged=True,  # System knows failure occurred
                    reasoning_transparency=1.0,  # Transparent about failure
                ),
            )

        # Phase 3: Action selection
        action_result_dict = await self._perform_action_selection_phase(
            thought_item, thought, thought_context, dma_results
        )

        # Phase 4: Finalize action
        # conscience_result is already a ConscienceApplicationResult object, not a dict
        conscience_result_raw = action_result_dict.get("conscience_result")
        # Type assertion: we know this is ConscienceApplicationResult from _perform_action_selection_phase
        conscience_result: Optional[ConscienceApplicationResult] = (
            conscience_result_raw if isinstance(conscience_result_raw, ConscienceApplicationResult) else None
        )
        action_from_conscience = self._handle_special_cases(conscience_result)
        final_result = await self._finalize_action_step(thought_item, action_from_conscience)

        # _finalize_action_step returns ConscienceApplicationResult based on conscience_result input
        return final_result  # type: ignore[no-any-return]

    async def _perform_action_selection_phase(
        self, thought_item: ProcessingQueueItem, thought: Thought, thought_context: Any, dma_results: Any
    ) -> JSONDict:
        """Execute action selection and conscience validation phases."""
        # Phase 4: PERFORM_ASPDMA - LLM-powered action selection
        action_result = await self._perform_aspdma_step(thought_item, thought_context, dma_results)
        profile_name = self._get_profile_name(thought)

        self._log_action_selection_result(action_result, thought)

        # Phase 5: CONSCIENCE_EXECUTION - Apply ethical safety validation
        conscience_result = await self._conscience_execution_step(
            thought_item, action_result, thought, dma_results, thought_context
        )

        # Phase 6: Handle conscience overrides (retry logic)
        if self._should_retry_with_conscience_guidance(conscience_result):
            action_result, conscience_result = await self._handle_conscience_retry(
                thought_item, thought, thought_context, dma_results, conscience_result, profile_name
            )

        self._log_final_action_results(action_result, conscience_result, thought)

        return {"action_result": action_result, "conscience_result": conscience_result}

    def _log_action_selection_result(self, action_result: Any, thought: Thought) -> None:
        """Log action selection results."""
        if action_result:
            selected_action = getattr(action_result, "selected_action", "UNKNOWN")
            logger.info(f"ThoughtProcessor: Action selection result for {thought.thought_id}: {selected_action}")

            if selected_action == HandlerActionType.OBSERVE:
                logger.warning(
                    f"OBSERVE ACTION DEBUG: ThoughtProcessor received OBSERVE action for thought {thought.thought_id}"
                )
        else:
            logger.error(f"ThoughtProcessor: No action result for thought {thought.thought_id}")

    def _should_retry_with_conscience_guidance(self, conscience_result: Optional[ConscienceApplicationResult]) -> bool:
        """Check if we should retry action selection with conscience guidance."""
        return (
            conscience_result is not None
            and conscience_result.overridden
            and conscience_result.final_action.selected_action == HandlerActionType.PONDER
        )

    async def _handle_conscience_retry(
        self,
        thought_item: ProcessingQueueItem,
        thought: Thought,
        thought_context: Any,
        dma_results: Any,
        conscience_result: ConscienceApplicationResult,
        profile_name: str,
    ) -> Tuple[Any, ConscienceApplicationResult]:
        """Handle conscience retry logic when PONDER override occurs."""
        logger.info(
            f"ThoughtProcessor: conscience override to PONDER for {thought.thought_id}. Attempting re-run with guidance."
        )

        # Prepare retry context
        retry_context = self._prepare_conscience_retry_context(thought_item, thought_context, conscience_result)

        try:
            # Attempt retry
            retry_result = await self.dma_orchestrator.run_action_selection(
                thought_item=thought_item,
                actual_thought=thought,
                processing_context=retry_context,
                dma_results=dma_results,
                profile_name=profile_name,
            )

            if retry_result:
                return await self._process_conscience_retry_result(
                    thought_item, thought, dma_results, retry_context, retry_result, conscience_result
                )
            else:
                logger.info("ThoughtProcessor: Retry failed to produce a result, proceeding with PONDER")

        except Exception as e:
            logger.error(f"Error during action selection retry: {e}", exc_info=True)

        return conscience_result.original_action, conscience_result

    def _prepare_conscience_retry_context(
        self, thought_item: ProcessingQueueItem, thought_context: Any, conscience_result: ConscienceApplicationResult
    ) -> Any:
        """Prepare context for conscience retry."""
        override_reason = conscience_result.override_reason or "Action failed conscience checks"
        attempted_action = self._describe_action(conscience_result.original_action)

        # Log what we received from conscience
        logger.info(f"[CONSCIENCE_RETRY] Preparing retry context for thought {thought_item.thought_id}")
        logger.info(f"[CONSCIENCE_RETRY] Override reason: {override_reason[:200]}...")
        logger.info(f"[CONSCIENCE_RETRY] Original action was: {attempted_action}")

        # Check if this is an updated status override (new observation arrived)
        # The conscience result may have CIRIS_OBSERVATION_UPDATED_STATUS with the new message
        updated_observation = None
        if hasattr(conscience_result, "epistemic_data") and conscience_result.epistemic_data:
            # Check epistemic_data for updated status
            ep_data = conscience_result.epistemic_data
            if hasattr(ep_data, "CIRIS_OBSERVATION_UPDATED_STATUS"):
                updated_observation = ep_data.CIRIS_OBSERVATION_UPDATED_STATUS
                if updated_observation:
                    logger.info(
                        f"[CONSCIENCE_RETRY] Found CIRIS_OBSERVATION_UPDATED_STATUS in epistemic_data: {updated_observation[:100]}..."
                    )

        # Also check the final_action's parameters for the new observation
        if conscience_result.final_action and hasattr(conscience_result.final_action, "action_parameters"):
            params = conscience_result.final_action.action_parameters
            if params and hasattr(params, "questions"):
                logger.info(f"[CONSCIENCE_RETRY] PONDER questions from conscience: {params.questions}")

        # Create enhanced context with conscience feedback
        retry_context = thought_context
        if hasattr(thought_context, "model_copy"):
            retry_context = thought_context.model_copy()
            retry_context.is_conscience_retry = True
        elif isinstance(thought_context, dict):
            retry_context = thought_context.copy()
            retry_context["is_conscience_retry"] = True
        elif hasattr(retry_context, "is_conscience_retry"):
            retry_context.is_conscience_retry = True

        # Build retry guidance - CRITICAL: Include the new observation if present
        base_guidance = (
            f"Your previous attempt to {attempted_action} was rejected because: {override_reason}. "
            "Please select a DIFFERENT action that better aligns with ethical principles and safety guidelines. "
        )

        if updated_observation:
            # This is the key fix - include the new observation in the retry guidance
            retry_guidance = (
                f"IMPORTANT: A NEW MESSAGE arrived from the user while you were processing: '{updated_observation}'. "
                f"You must now respond to THIS new message, not complete the old task. "
                f"{base_guidance}"
                "The user is waiting for a response to their new message. Use SPEAK to respond or use a TOOL if needed."
            )
            logger.info(f"[CONSCIENCE_RETRY] Including new observation in retry_guidance")
        else:
            retry_guidance = (
                f"{base_guidance}"
                "Consider: Is there a more cautious approach? Should you gather more information first? "
                "Can this task be marked as complete without further action? "
                "Remember: DEFER only if the task MUST be done AND requires human approval."
            )

        # Add conscience guidance to the thought item
        conscience_feedback = {
            "failed_action": attempted_action,
            "failure_reason": override_reason,
            "retry_guidance": retry_guidance,
        }

        # If there's a new observation, add it explicitly to the feedback
        if updated_observation:
            conscience_feedback["new_observation"] = updated_observation
            conscience_feedback["updated_status_detected"] = "true"

        setattr(thought_item, "conscience_feedback", conscience_feedback)

        logger.info(f"[CONSCIENCE_RETRY] Set conscience_feedback with keys: {list(conscience_feedback.keys())}")
        logger.info(f"[CONSCIENCE_RETRY] retry_guidance preview: {retry_guidance[:150]}...")

        return retry_context

    async def _process_conscience_retry_result(
        self,
        thought_item: ProcessingQueueItem,
        thought: Thought,
        dma_results: Any,
        retry_context: Any,
        retry_result: Any,
        original_conscience_result: ConscienceApplicationResult,
    ) -> Tuple[Any, ConscienceApplicationResult]:
        """Process the result of a conscience retry."""
        logger.info(f"ThoughtProcessor: Re-running consciences on retry action {retry_result.selected_action}")

        retry_conscience_result = await self._conscience_execution_step(
            thought_item, retry_result, thought, dma_results, retry_context
        )

        if not retry_conscience_result.overridden:
            logger.info(f"ThoughtProcessor: Retry action {retry_result.selected_action} passed consciences")
            return retry_result, retry_conscience_result
        else:
            self._log_retry_failure(retry_result, original_conscience_result)
            return original_conscience_result.original_action, original_conscience_result

    def _log_retry_failure(self, retry_result: Any, original_conscience_result: ConscienceApplicationResult) -> None:
        """Log details when retry also fails consciences."""
        logger.info(f"ThoughtProcessor: Retry action {retry_result.selected_action} also failed consciences")
        if retry_result.selected_action == original_conscience_result.original_action.selected_action:
            logger.info("ThoughtProcessor: Same action type but with different parameters still failed")
        logger.info("ThoughtProcessor: Proceeding with PONDER")

    def _log_final_action_results(
        self, action_result: Any, conscience_result: Optional[ConscienceApplicationResult], thought: Thought
    ) -> None:
        """Log final action and conscience results."""
        if action_result.selected_action == HandlerActionType.OBSERVE:
            logger.debug("ThoughtProcessor: OBSERVE action after consciences for thought %s", thought.thought_id)

        if conscience_result:
            if hasattr(conscience_result, "final_action") and conscience_result.final_action:
                final_action = getattr(conscience_result.final_action, "selected_action", "UNKNOWN")
                logger.info(
                    f"ThoughtProcessor: conscience result for {thought.thought_id}: final_action={final_action}"
                )

    async def _handle_critical_failure(self, correlation: ServiceCorrelation, start_time: Any) -> None:
        """Handle critical DMA failure."""
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

    async def _record_processing_completion(
        self, thought: Thought, final_result: Optional[ConscienceApplicationResult]
    ) -> None:
        """Record telemetry for successful processing completion."""
        if not self.telemetry_service:
            return

        await self.telemetry_service.record_metric(
            "thought_processing_completed",
            value=1.0,
            tags={"thought_id": thought.thought_id, "path_type": "hot", "source_module": "thought_processor"},
        )

        if final_result:
            action_metric = f"action_selected_{final_result.final_action.selected_action.value}"
            await self.telemetry_service.record_metric(
                action_metric,
                value=1.0,
                tags={
                    "thought_id": thought.thought_id,
                    "action": final_result.final_action.selected_action.value,
                    "path_type": "hot",
                    "source_module": "thought_processor",
                },
            )

    async def _finalize_correlation(
        self, correlation: ServiceCorrelation, final_result: Optional[ConscienceApplicationResult], start_time: Any
    ) -> None:
        """Update correlation with final success status."""
        end_time = self._time_service.now()
        from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

        update_req = CorrelationUpdateRequest(
            correlation_id=correlation.correlation_id,
            response_data={
                "success": "true",
                "result_summary": f"Successfully processed thought with action: {final_result.final_action.selected_action if final_result else 'none'}",
                "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                "response_timestamp": end_time.isoformat(),
            },
            status=ServiceCorrelationStatus.COMPLETED,
            metric_value=None,
            tags=None,
        )
        persistence.update_correlation(update_req, self._time_service)

    # Helper methods that will remain in main.py
    async def _fetch_thought(self, thought_id: str, occurrence_id: str = "default") -> Optional[Thought]:
        """Fetch thought from persistence layer."""
        import asyncio

        from ciris_engine.logic import persistence

        logger.info(
            f"ThoughtProcessor._fetch_thought: Starting fetch for thought_id={thought_id}, occurrence_id={occurrence_id}"
        )

        try:
            # Add timeout protection to prevent CI hangs
            thought = await asyncio.wait_for(
                persistence.async_get_thought_by_id(thought_id, occurrence_id), timeout=30.0  # 30 second timeout
            )
            logger.info(
                f"ThoughtProcessor._fetch_thought: Successfully fetched thought_id={thought_id}, occurrence_id={occurrence_id}, thought={'present' if thought else 'None'}"
            )
            return thought
        except asyncio.TimeoutError:
            logger.error(
                f"ThoughtProcessor._fetch_thought: TIMEOUT after 30s fetching thought_id={thought_id}, occurrence_id={occurrence_id}"
            )
            raise
        except Exception as e:
            logger.error(
                f"ThoughtProcessor._fetch_thought: ERROR fetching thought_id={thought_id}: {type(e).__name__}: {e}"
            )
            raise

    def _has_critical_failure(self, dma_results: Any) -> bool:
        """Check if DMA results indicate critical failure requiring escalation."""
        if not dma_results:
            return True

        # Check for specific failure indicators
        if hasattr(dma_results, "critical_failure") and dma_results.critical_failure:
            return True

        return False

    def _create_deferral_result(self, dma_results: Any, thought: Thought) -> ActionSelectionDMAResult:
        """Create a deferral result for failed processing."""
        defer_reason = "Critical DMA failure or conscience override."
        # Convert dma_results to string representation for context
        dma_results_str = str(dma_results) if not isinstance(dma_results, str) else dma_results
        defer_params = DeferParams(
            reason=defer_reason,
            context={
                "original_thought_id": thought.thought_id,
                "dma_results_summary": dma_results_str,
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
        if thought and hasattr(thought, "context") and thought.context:
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
        # CRITICAL: Defensive logging - thought can be None in some error paths
        thought_id = thought.thought_id if thought else "unknown"
        logger.debug(f"Determined profile name '{profile_name}' for thought {thought_id}")
        return profile_name

    def _describe_action(self, action_result: Any) -> str:
        """Generate a human-readable description of an action."""
        if not hasattr(action_result, "selected_action"):
            return "unknown action"

        action_type = action_result.selected_action
        params = action_result.action_parameters

        descriptions: Dict[HandlerActionType, Callable[[Any], str]] = {
            HandlerActionType.SPEAK: lambda p: self._format_speak_description(p),
            HandlerActionType.TOOL: lambda p: f"use tool '{p.tool_name}'" if hasattr(p, "tool_name") else "use a tool",
            HandlerActionType.OBSERVE: lambda p: (
                f"observe channel '{p.channel_id}'" if hasattr(p, "channel_id") else "observe"
            ),
            HandlerActionType.MEMORIZE: lambda p: "memorize information",
            HandlerActionType.RECALL: lambda p: "recall information",
            HandlerActionType.FORGET: lambda p: "forget information",
        }

        desc_func: Callable[[Any], str] = descriptions.get(action_type, lambda p: str(action_type.value))
        try:
            result = desc_func(params)
            return str(result)
        except Exception as e:
            logger.warning(
                f"Failed to generate action description for {action_type.value}: {e}. Using default description."
            )
            return str(action_type.value)

    async def _apply_conscience_simple(
        self,
        action_result: ActionSelectionDMAResult,
        thought: Thought,
        dma_results_dict: JSONDict,
        processing_context: Optional[Any] = None,
    ) -> ConscienceApplicationResult:
        """Simple conscience application without orchestrator."""
        is_conscience_retry = self._check_and_clear_conscience_retry_flag(processing_context)

        # Create typed context for conscience checks (needed for both bypass and normal)
        context = ConscienceCheckContext(
            thought=thought,
            dma_results=dma_results_dict,  # extra="allow" accepts additional fields
        )

        # CRITICAL: Run bypass consciences FIRST, even for exempt actions
        # This allows UpdatedStatusConscience to detect new messages before TASK_COMPLETE
        bypass_result = await self._run_bypass_conscience_checks(action_result, context)
        if bypass_result.overridden:
            logger.info(
                f"Bypass conscience overrode action {action_result.selected_action} -> "
                f"{bypass_result.final_action.selected_action}: {bypass_result.override_reason}"
            )
            return self._create_conscience_application_result(action_result, bypass_result)

        # Now check if action is exempt from normal conscience checks
        if self._is_exempt_from_conscience_checks(action_result):
            return ConscienceApplicationResult(
                original_action=action_result,
                final_action=action_result,
                overridden=False,
                override_reason=None,
                epistemic_data=EpistemicData(
                    entropy_level=0.0,  # Exempt actions have no uncertainty
                    coherence_level=1.0,  # Fully coherent
                    uncertainty_acknowledged=True,  # System knows this is exempt
                    reasoning_transparency=1.0,  # Fully transparent (exempt)
                ),
                # Propagate any detection flags from bypass checks
                updated_status_detected=bypass_result.updated_status_detected,
            )

        # Run normal conscience checks
        conscience_result = await self._run_normal_conscience_checks(action_result, context)

        if is_conscience_retry and not conscience_result.overridden:
            conscience_result = self._handle_conscience_retry_without_override(conscience_result)

        return self._create_conscience_application_result(action_result, conscience_result)

    def _check_and_clear_conscience_retry_flag(self, processing_context: Optional[Any]) -> bool:
        """Check if this is a conscience retry and clear the flag to prevent loops."""
        is_conscience_retry = (
            processing_context is not None
            and hasattr(processing_context, "is_conscience_retry")
            and processing_context.is_conscience_retry
        )

        if is_conscience_retry and processing_context is not None:
            processing_context.is_conscience_retry = False

        return is_conscience_retry

    def _is_exempt_from_conscience_checks(self, action_result: ActionSelectionDMAResult) -> bool:
        """Check if action is exempt from conscience override."""
        exempt_actions = {
            HandlerActionType.TASK_COMPLETE.value,
            HandlerActionType.DEFER.value,
            HandlerActionType.REJECT.value,
        }
        return action_result.selected_action in exempt_actions

    async def _run_bypass_conscience_checks(
        self, action_result: ActionSelectionDMAResult, context: ConscienceCheckContext
    ) -> ConscienceCheckInternalResult:
        """Run bypass conscience checks that run even for exempt actions.

        These are critical checks like UpdatedStatusConscience that must run
        even for TASK_COMPLETE, DEFER, REJECT actions.
        """
        return await self._run_conscience_entries(
            self.conscience_registry.get_bypass_consciences(),
            action_result,
            context,
        )

    async def _run_normal_conscience_checks(
        self, action_result: ActionSelectionDMAResult, context: ConscienceCheckContext
    ) -> ConscienceCheckInternalResult:
        """Run normal conscience checks that respect exemption."""
        return await self._run_conscience_entries(
            self.conscience_registry.get_normal_consciences(),
            action_result,
            context,
        )

    async def _run_conscience_checks(
        self, action_result: ActionSelectionDMAResult, context: ConscienceCheckContext
    ) -> ConscienceCheckInternalResult:
        """Run all conscience checks and return the results."""
        return await self._run_conscience_entries(
            self.conscience_registry.get_consciences(),
            action_result,
            context,
        )

    async def _run_conscience_entries(
        self,
        entries: List[Any],
        action_result: ActionSelectionDMAResult,
        context: ConscienceCheckContext,
    ) -> ConscienceCheckInternalResult:
        """Run a list of conscience entries and return aggregated results."""
        final_action = action_result
        overridden = False
        override_reason: Optional[str] = None
        epistemic_data: Optional[EpistemicData] = None
        thought_depth_triggered: Optional[bool] = None
        updated_status_detected: Optional[bool] = None

        for entry in entries:
            conscience_result = await self._check_single_conscience(entry, final_action, context)

            if conscience_result.skip:
                continue

            # Take the first epistemic data we find (consciences run in order)
            if conscience_result.epistemic_data and not epistemic_data:
                epistemic_data = conscience_result.epistemic_data

            if conscience_result.thought_depth_triggered is not None:
                thought_depth_triggered = conscience_result.thought_depth_triggered

            if conscience_result.updated_status_detected is not None:
                updated_status_detected = conscience_result.updated_status_detected

            if not conscience_result.passed:
                overridden = True
                override_reason = conscience_result.reason
                final_action = conscience_result.replacement_action or action_result
                break

        return ConscienceCheckInternalResult(
            final_action=final_action,
            overridden=overridden,
            override_reason=override_reason,
            epistemic_data=epistemic_data,
            thought_depth_triggered=thought_depth_triggered,
            updated_status_detected=updated_status_detected,
        )

    async def _check_single_conscience(
        self, entry: Any, action_result: ActionSelectionDMAResult, context: ConscienceCheckContext
    ) -> SingleConscienceCheckResult:
        """Check a single conscience and handle errors."""
        conscience = entry.conscience
        cb = entry.circuit_breaker

        try:
            if cb:
                cb.check_and_raise()
            result = await conscience.check(action_result, context)
            if cb:
                cb.record_success()
        except CircuitBreakerError as e:
            logger.warning(f"conscience {entry.name} unavailable: {e}")
            return SingleConscienceCheckResult(skip=True)
        except Exception as e:  # noqa: BLE001
            logger.error(f"conscience {entry.name} error: {e}", exc_info=True)
            if cb:
                cb.record_failure()
            return SingleConscienceCheckResult(skip=True)

        replacement_action = self._create_replacement_action(result, action_result, entry.name)

        return SingleConscienceCheckResult(
            skip=False,
            passed=result.passed,
            reason=result.reason,
            epistemic_data=result.epistemic_data,  # Already an EpistemicData instance or None
            replacement_action=replacement_action,
            thought_depth_triggered=result.thought_depth_triggered,
            updated_status_detected=result.updated_status_detected,
        )

    def _create_replacement_action(
        self, conscience_result: Any, original_action: ActionSelectionDMAResult, conscience_name: str
    ) -> ActionSelectionDMAResult:
        """Create replacement action based on conscience result."""
        if not conscience_result.passed:
            # Check for replacement_action on ConscienceCheckResult (top-level field)
            if conscience_result.replacement_action:
                return ActionSelectionDMAResult.model_validate(conscience_result.replacement_action)
            else:
                return self._create_ponder_replacement(original_action, conscience_result, conscience_name)
        return original_action

    def _create_ponder_replacement(
        self, action_result: ActionSelectionDMAResult, conscience_result: Any, conscience_name: str
    ) -> ActionSelectionDMAResult:
        """Create PONDER action as replacement."""
        attempted_action_desc = self._describe_action(action_result)
        questions = [
            f"I attempted to {attempted_action_desc}",
            conscience_result.reason or "conscience failed",
            "What alternative approach would better align with my principles?",
        ]

        ponder_params = PonderParams(questions=questions)

        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=ponder_params,
            rationale=f"Overridden by {conscience_name}: Need to reconsider {attempted_action_desc}",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

    def _handle_conscience_retry_without_override(
        self, conscience_result: ConscienceCheckInternalResult
    ) -> ConscienceCheckInternalResult:
        """Handle conscience retry when no override occurred."""
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
            return ConscienceCheckInternalResult(
                final_action=final_action,
                overridden=True,
                override_reason="Conscience retry - forcing PONDER to prevent loops",
                epistemic_data=conscience_result.epistemic_data,
                thought_depth_triggered=conscience_result.thought_depth_triggered,
                updated_status_detected=conscience_result.updated_status_detected,
            )

        return conscience_result

    def _create_conscience_application_result(
        self, action_result: ActionSelectionDMAResult, conscience_result: ConscienceCheckInternalResult
    ) -> ConscienceApplicationResult:
        """Create the final ConscienceApplicationResult."""
        # epistemic_data is REQUIRED - use safe fallback if not provided
        epistemic_data = conscience_result.epistemic_data or EpistemicData(
            entropy_level=0.5,  # Moderate uncertainty when no data
            coherence_level=0.5,  # Moderate coherence
            uncertainty_acknowledged=True,  # System knows data is missing
            reasoning_transparency=1.0,  # Transparent about the issue
        )

        return ConscienceApplicationResult(
            original_action=action_result,
            final_action=conscience_result.final_action,
            overridden=conscience_result.overridden,
            override_reason=conscience_result.override_reason,
            epistemic_data=epistemic_data,
            thought_depth_triggered=conscience_result.thought_depth_triggered,
            updated_status_detected=conscience_result.updated_status_detected,
        )

    def _format_speak_description(self, params: Any) -> str:
        """Format description for SPEAK action parameters."""
        if not hasattr(params, "content"):
            return "speak"

        content_str = str(params.content)
        # Use 200 chars to provide more context for conscience evaluation
        if len(content_str) > 200:
            return f"speak: '{content_str[:200]}...'"
        else:
            return f"speak: '{content_str}'"

    def _handle_special_cases(
        self, conscience_result: Optional[ConscienceApplicationResult]
    ) -> Optional[ConscienceApplicationResult]:
        """Handle special processing cases (PONDER, DEFER overrides)."""
        # Return the full ConscienceApplicationResult to preserve all conscience data
        # The full result includes epistemic_data, override_reason, etc.
        return conscience_result
