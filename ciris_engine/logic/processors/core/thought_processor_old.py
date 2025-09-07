"""
ThoughtProcessor: Core logic for processing a single thought in the CIRISAgent pipeline.
Coordinates DMA orchestration, context building, consciences, and pondering.
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
from ciris_engine.logic.processors.core.step_decorators import streaming_step, step_point
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class ThoughtProcessor:
    def __init__(
        self,
        dma_orchestrator: Any,
        context_builder: Any,
        conscience_registry: Any,  # Changed from conscience_orchestrator
        app_config: ConfigAccessor,
        dependencies: ActionHandlerDependencies,
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        auth_service: Optional[Any] = None,
    ) -> None:
        self.dma_orchestrator = dma_orchestrator
        self.context_builder = context_builder
        self.conscience_registry = conscience_registry  # Store registry directly
        self.app_config = app_config
        self.dependencies = dependencies
        # Settings will be retrieved from config accessor as needed
        self.telemetry_service = telemetry_service
        self._time_service = time_service
        self.auth_service = auth_service
        
        # Pipeline controller for single-stepping (injected when paused)

    async def process_thought(
        self, thought_item: ProcessingQueueItem, context: Optional[dict] = None
    ) -> Optional[ActionSelectionDMAResult]:
        """Main processing pipeline - coordinates the components."""
        logger.debug(f"process_thought START for thought {thought_item.thought_id}")
        start_time = self._time_service.now()
        # Create trace for thought processing
        trace_id = f"task_{thought_item.source_task_id or 'unknown'}_{thought_item.thought_id}"
        span_id = f"thought_processor_{thought_item.thought_id}"
        parent_span_id = f"agent_processor_{thought_item.thought_id}"

        trace_context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_name="process_thought",
            span_kind="internal",
            baggage={
                "thought_id": thought_item.thought_id,
                "task_id": thought_item.source_task_id or "",
                "thought_type": thought_item.thought_type,
            },
        )

        correlation = ServiceCorrelation(
            correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
            correlation_type=CorrelationType.TRACE_SPAN,
            service_type="thought_processor",
            handler_name="ThoughtProcessor",
            action_type="process_thought",
            created_at=start_time,
            updated_at=start_time,
            timestamp=start_time,
            trace_context=trace_context,
            status=ServiceCorrelationStatus.PENDING,
            request_data=None,
            response_data=None,
            metric_data=None,
            log_data=None,
            retention_policy="raw",
            ttl_seconds=None,
            parent_correlation_id=None,
            tags={
                "thought_id": thought_item.thought_id,
                "task_id": thought_item.source_task_id or "",
                "component_type": "thought_processor",
                "trace_depth": "2",
                "thought_type": thought_item.thought_type,
            },
        )

        # Add correlation to both persistence and telemetry service for distributed tracing
        await persistence.add_correlation_with_telemetry(correlation, self._time_service, self.telemetry_service)

        # Record thought processing start as HOT PATH
        if self.telemetry_service:
            await self.telemetry_service.record_metric(
                "thought_processing_started",
                value=1.0,
                tags={"thought_id": thought_item.thought_id, "path_type": "hot", "source_module": "thought_processor"},
            )

        # 1. Fetch the full Thought object (or use prefetched)
        prefetched_thought = context.get("prefetched_thought") if context else None
        if prefetched_thought:
            # Handle both dict and Thought object cases
            if isinstance(prefetched_thought, dict):
                # It's a dict from model_dump(), reconstruct the Thought object
                from ciris_engine.schemas.runtime.models import Thought

                thought = Thought(**prefetched_thought)
                if thought.thought_id == thought_item.thought_id:
                    logger.debug(f"Using prefetched thought {thought_item.thought_id}")
                else:
                    thought = None
            elif hasattr(prefetched_thought, "thought_id") and prefetched_thought.thought_id == thought_item.thought_id:
                thought = prefetched_thought
                logger.debug(f"Using prefetched thought {thought_item.thought_id}")
            else:
                thought = None
        else:
            thought = None

        if not thought:
            logger.debug(f"About to fetch thought {thought_item.thought_id}")
            thought = await self._fetch_thought(thought_item.thought_id)
            logger.debug(f"Fetched thought {thought_item.thought_id}")
        if not thought:
            logger.error(f"Thought {thought_item.thought_id} not found.")
            if self.telemetry_service:
                await self.telemetry_service.record_metric(
                    "thought_not_found",
                    value=1.0,
                    tags={
                        "thought_id": thought_item.thought_id,
                        "path_type": "critical",  # Critical error path
                        "source_module": "thought_processor",
                    },
                )
            # Update correlation with failure
            end_time = self._time_service.now()
            from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "error_message": "Thought not found",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, self._time_service)
            return None

        # 1.5 Verify the parent task is signed by at least an observer
        if self.auth_service:
            is_authorized = await self._verify_task_authorization(thought)
            if not is_authorized:
                logger.error(f"Thought {thought_item.thought_id} parent task is not properly signed. Rejecting.")
                if self.telemetry_service:
                    await self.telemetry_service.record_metric(
                        "thought_unauthorized",
                        value=1.0,
                        tags={
                            "thought_id": thought_item.thought_id,
                            "path_type": "critical",
                            "source_module": "thought_processor",
                        },
                    )
                # Update correlation with auth failure
                end_time = self._time_service.now()
                from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

                update_req = CorrelationUpdateRequest(
                    correlation_id=correlation.correlation_id,
                    response_data={
                        "success": "false",
                        "error_message": "Thought parent task is not properly signed",
                        "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                        "response_timestamp": end_time.isoformat(),
                    },
                    status=ServiceCorrelationStatus.FAILED,
                    metric_value=None,
                    tags=None,
                )
                persistence.update_correlation(update_req, self._time_service)
                return None

        # 2. Build context (always build proper ThoughtContext for DMA orchestrator)
        thought_context = await self._gather_context_step(thought_item, context)

        # 3. Run DMAs
        dma_results = await self._perform_dmas_step(thought_item, thought_context)

        # 4. Check for failures/escalations
        if self._has_critical_failure(dma_results):
            # Update correlation with critical failure
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

        # 5. Run action selection
        # 4. Run Action Selection (ASPDMA)
        action_result = await self._perform_aspdma_step(thought_item, thought_context, dma_results)

        # CRITICAL DEBUG: Check action_result details immediately
        if action_result:
            selected_action = getattr(action_result, "selected_action", "UNKNOWN")
            logger.info(f"ThoughtProcessor: Action selection result for {thought.thought_id}: {selected_action}")

            # Special debug for OBSERVE actions
            if selected_action == HandlerActionType.OBSERVE:
                logger.warning(
                    f"OBSERVE ACTION DEBUG: ThoughtProcessor received OBSERVE action for thought {thought.thought_id}"
                )
                logger.warning(f"OBSERVE ACTION DEBUG: action_result type: {type(action_result)}")
                logger.warning(f"OBSERVE ACTION DEBUG: action_result details: {action_result}")
        else:
            logger.error(f"ThoughtProcessor: No action result from DMA for {thought.thought_id}")
            logger.error("ThoughtProcessor: action_result is None! This is the critical issue.")
            # Update correlation with failure
            end_time = self._time_service.now()
            from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "error_message": "No action result from DMA",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, self._time_service)
            # Return early with fallback result
            return self._create_deferral_result(dma_results, thought)

        # 6. Apply consciences
        # STEP POINT: CONSCIENCE_EXECUTION
        
        logger.info(
            f"ThoughtProcessor: Applying consciences for {thought.thought_id} with action {getattr(action_result, 'selected_action', 'UNKNOWN')}"
        )
        conscience_result = await self._apply_conscience_simple(action_result, thought, dma_results, thought_context)

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

            # Re-run action selection with guidance
            # STEP POINT: RECURSIVE_ASPDMA
            
            try:
                retry_result = await self.dma_orchestrator.run_action_selection(
                    thought_item=thought_item,
                    actual_thought=thought,
                    processing_context=retry_context,
                    dma_results=dma_results,
                    profile_name=profile_name,
                )

                if retry_result:
                    # Always re-apply consciences, even if same action type (parameters may differ)
                    # STEP POINT: RECURSIVE_CONSCIENCE
                    
                    logger.info(
                        f"ThoughtProcessor: Re-running consciences on retry action {retry_result.selected_action}"
                    )
                    retry_conscience_result = await self._apply_conscience_simple(
                        retry_result, thought, dma_results, retry_context
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
            else:
                logger.warning(f"ThoughtProcessor: conscience result for {thought.thought_id} has no final_action")
        else:
            logger.error(f"ThoughtProcessor: No conscience result for {thought.thought_id}")

        # 7. Handle special cases (PONDER, DEFER overrides)
        logger.info(f"ThoughtProcessor: Handling special cases for {thought.thought_id}")
        final_result = self._handle_special_cases(conscience_result, thought, thought_context)

        # 8. Ensure we return the final result
        if final_result:
            logger.debug(
                f"ThoughtProcessor returning result for thought {thought.thought_id}: {final_result.selected_action}"
            )
        else:
            # If no final result, check if we got a conscience result we can use
            if hasattr(conscience_result, "final_action") and conscience_result.final_action:
                final_result = conscience_result.final_action
                logger.debug(f"ThoughtProcessor using conscience final_action for thought {thought.thought_id}")
            else:
                logger.warning(
                    f"ThoughtProcessor: No final result for thought {thought.thought_id} - defaulting to PONDER"
                )
                ponder_params = PonderParams(questions=["No conscience result"])
                final_result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.PONDER,
                    action_parameters=ponder_params,
                    rationale="No conscience result",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

        # STEP POINT: FINALIZE_ACTION (final action determined)
        
        # Store conscience result on the action result for later access
        # This allows handlers to access epistemic data through dispatch context
        if final_result and conscience_result:
            # Add conscience_result as a non-serialized attribute
            setattr(final_result, "_conscience_result", conscience_result)

        # Record thought processing completion and action taken
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
                        "path_type": "hot",  # Action selection is HOT PATH
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

        return final_result

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

    async def _fetch_thought(self, thought_id: str) -> Optional[Thought]:
        # Import here to avoid circular import
        from ciris_engine.logic import persistence

        return await persistence.async_get_thought_by_id(thought_id)


    # === H3ERE Pipeline Step Methods with Decorators ===
    
    @streaming_step(StepPoint.GATHER_CONTEXT)
    @step_point(StepPoint.GATHER_CONTEXT)
    async def _gather_context_step(self, thought_item: ProcessingQueueItem, context: Optional[dict] = None):
        """Step 1: Build context for DMA processing."""
        thought = await self._fetch_thought(thought_item.thought_id)
        
        batch_context_data = context.get("batch_context") if context else None
        if batch_context_data:
            logger.debug(f"Using batch context for thought {thought_item.thought_id}")
            from ciris_engine.logic.context.batch_context import build_system_snapshot_with_batch

            system_snapshot = await build_system_snapshot_with_batch(
                task=None,
                thought=thought,
                batch_data=batch_context_data,
                memory_service=self.context_builder.memory_service if self.context_builder else None,
                graphql_provider=None,
            )
            thought_context = await self.context_builder.build_thought_context(thought, system_snapshot=system_snapshot)
        else:
            logger.debug(f"Building full context for thought {thought_item.thought_id} (no batch context)")
            thought_context = await self.context_builder.build_thought_context(thought)
        
        # Store context on queue item
        if hasattr(thought_context, "model_dump"):
            thought_item.initial_context = thought_context.model_dump()
        else:
            thought_item.initial_context = thought_context
            
        return thought_context

    @streaming_step(StepPoint.PERFORM_DMAS)
    @step_point(StepPoint.PERFORM_DMAS)
    async def _perform_dmas_step(self, thought_item: ProcessingQueueItem, thought_context):
        """Step 2: Execute multi-perspective DMAs."""
        try:
            logger.debug(f"About to call dma_orchestrator.run_initial_dmas for thought {thought_item.thought_id}")
            dma_results = await self.dma_orchestrator.run_initial_dmas(
                thought_item=thought_item,
                processing_context=thought_context,
            )
            return dma_results
        except DMAFailure as dma_err:
            logger.error(
                f"DMA failure during initial processing for {thought_item.thought_id}: {dma_err}",
                exc_info=True,
            )
            # Record telemetry for critical DMA failure
            if self.telemetry_service:
                await self.telemetry_service.record_metric(
                    "dma_failure",
                    value=1.0,
                    tags={
                        "thought_id": thought_item.thought_id,
                        "error": str(dma_err)[:100],
                        "path_type": "critical",  # Critical failure
                        "source_module": "thought_processor",
                    },
                )
            # Return deferral result for DMA failures
            defer_params = DeferParams(reason="DMA timeout", context={"error": str(dma_err)}, defer_until=None)
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER,
                action_parameters=defer_params,
                rationale=f"DMA failure: {dma_err}",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

    @streaming_step(StepPoint.PERFORM_ASPDMA)
    @step_point(StepPoint.PERFORM_ASPDMA)
    async def _perform_aspdma_step(self, thought_item: ProcessingQueueItem, thought_context, dma_results):
        """Step 3: LLM-powered action selection."""
        thought = await self._fetch_thought(thought_item.thought_id)
        
        # Check for WA deferral first
        if dma_results and hasattr(dma_results, 'should_defer_to_wise_authority') and dma_results.should_defer_to_wise_authority:
            return self._create_deferral_result(dma_results, thought)

        profile_name = self._get_profile_name(thought)
        try:
            action_result = await self.dma_orchestrator.run_action_selection(
                thought_item=thought_item,
                actual_thought=thought,
                processing_context=thought_context,  # This is the ThoughtContext
                dma_results=dma_results,
                profile_name=profile_name,
            )
            return action_result
        except DMAFailure as dma_err:
            logger.error(
                f"DMA failure during action selection for {thought_item.thought_id}: {dma_err}",
                exc_info=True,
            )
            defer_params = DeferParams(reason="DMA timeout", context={"error": str(dma_err)}, defer_until=None)
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER,
                action_parameters=defer_params,
                rationale="DMA timeout",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

    @streaming_step(StepPoint.CONSCIENCE_EXECUTION)
    @step_point(StepPoint.CONSCIENCE_EXECUTION)
    async def _conscience_execution_step(self, thought_item: ProcessingQueueItem, action_result):
        """Step 4: Ethical safety validation."""
        if not action_result:
            return action_result
            
        try:
            conscience_results = await self.conscience_registry.apply_all_consciences(
                action_result, thought_item
            )
            
            # Check if conscience passed
            conscience_passed = all(result.passed for result in conscience_results)
            action_result.conscience_passed = conscience_passed
            
            return action_result, conscience_results
        except Exception as e:
            logger.error(f"Conscience execution failed for thought {thought_item.thought_id}: {e}")
            return action_result, []

    @streaming_step(StepPoint.RECURSIVE_ASPDMA)
    @step_point(StepPoint.RECURSIVE_ASPDMA, conditional=True)
    async def _recursive_aspdma_step(self, thought_item: ProcessingQueueItem, thought_context, dma_results, override_reason: str):
        """Step 3B: Optional retry action selection after conscience failure."""
        thought = await self._fetch_thought(thought_item.thought_id)
        
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
    @step_point(StepPoint.RECURSIVE_CONSCIENCE, conditional=True)
    async def _recursive_conscience_step(self, thought_item: ProcessingQueueItem, retry_result):
        """Step 4B: Optional re-validation if recursive action failed."""
        if not retry_result:
            return retry_result, []
            
        try:
            recursive_conscience_results = await self.conscience_registry.apply_all_consciences(
                retry_result, thought_item
            )
            
            # Check if recursive conscience passed
            final_conscience_passed = all(result.passed for result in recursive_conscience_results)
            retry_result.conscience_passed = final_conscience_passed
            
            return retry_result, recursive_conscience_results
        except Exception as e:
            logger.error(f"Recursive conscience execution failed for thought {thought_item.thought_id}: {e}")
            return retry_result, []

    @streaming_step(StepPoint.FINALIZE_ACTION)
    @step_point(StepPoint.FINALIZE_ACTION)
    async def _finalize_action_step(self, thought_item: ProcessingQueueItem, final_result):
        """Step 5: Final action determination."""
        if not final_result:
            # If no final result, create ponder action
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=PonderParams(
                    reason="No valid action could be determined",
                    duration_minutes=1,
                    should_generate_follow_up=True,
                ),
                rationale="Failed to determine valid action - pondering instead",
                confidence_score=0.1,
                resource_usage=None,
            )
        
        return final_result

    @streaming_step(StepPoint.PERFORM_ACTION)
    @step_point(StepPoint.PERFORM_ACTION)
    async def _perform_action_step(self, thought_item: ProcessingQueueItem, result, context: dict):
        """Step 6: Dispatch action to handler."""
        # This step is handled by base_processor dispatch_action method
        # Just pass through the result - actual dispatch happens after this
        return result

    @streaming_step(StepPoint.ACTION_COMPLETE)
    @step_point(StepPoint.ACTION_COMPLETE)
    async def _action_complete_step(self, thought_item: ProcessingQueueItem, dispatch_result):
        """Step 7: Action execution completed."""
        # This step is handled by base_processor after dispatch
        # Mark the completion status
        return {
            "thought_id": thought_item.thought_id,
            "action_completed": True,
            "dispatch_success": dispatch_result.get("success", True) if isinstance(dispatch_result, dict) else True,
            "execution_time_ms": dispatch_result.get("execution_time_ms", 0.0) if isinstance(dispatch_result, dict) else 0.0,
        }
        

    async def _verify_task_authorization(self, thought: Thought) -> bool:
        """Verify that the thought's parent task is signed by at least an observer."""
        if not self.auth_service:
            # If no auth service, allow for backward compatibility
            logger.warning("No auth service available, allowing thought processing")
            return True

        # Import here to avoid circular import
        from ciris_engine.logic import persistence

        # Get the parent task
        task = persistence.get_task_by_id(thought.source_task_id)
        if not task:
            logger.error(f"Parent task {thought.source_task_id} not found for thought {thought.thought_id}")
            return False

        # Check if task is signed
        if not task.signed_by:
            logger.error(f"Task {task.task_id} is not signed")
            return False

        # Verify the signature
        is_valid = await self.auth_service.verify_task_signature(task)
        if not is_valid:
            logger.error(f"Task {task.task_id} has invalid signature")
            return False

        # Get the WA that signed it
        signer_wa = await self.auth_service.get_wa(task.signed_by)
        if not signer_wa:
            logger.error(f"Signer WA {task.signed_by} not found")
            return False

        # Check role - must be at least observer
        from ciris_engine.schemas.services.authority_core import WARole

        allowed_roles = [WARole.OBSERVER, WARole.AUTHORITY, WARole.ROOT]
        if signer_wa.role not in allowed_roles:
            logger.error(f"Task {task.task_id} signed by {signer_wa.role.value} role, needs at least observer")
            return False

        logger.debug(f"Task {task.task_id} properly signed by {signer_wa.role.value} {task.signed_by}")
        return True

    def _describe_action(self, action_result: ActionSelectionDMAResult) -> str:
        """Generate a human-readable description of an action."""
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

    def _get_permitted_actions(self, thought: Thought) -> Optional[List[str]]:
        return getattr(thought, "permitted_actions", None)

    def _has_critical_failure(self, dma_results: Any) -> bool:
        return getattr(dma_results, "critical_failure", False)

    def _create_deferral_result(self, dma_results: Any, thought: Thought) -> ActionSelectionDMAResult:
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

    def _handle_special_cases(self, result: Any, thought: Thought, context: Any) -> Optional[ActionSelectionDMAResult]:
        """Handle special cases like PONDER and DEFER overrides."""
        # Handle both ConscienceResult and ActionSelectionDMAResult
        selected_action = None
        final_result = result

        if result is None:
            logger.error(
                "ThoughtProcessor: conscience result missing for thought %s - defaulting to PONDER",
                thought.thought_id,
            )
            ponder_params = PonderParams(questions=["conscience result missing"])
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=ponder_params,
                rationale="conscience result missing",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

        if hasattr(result, "selected_action"):
            # This is an ActionSelectionDMAResult
            selected_action = result.selected_action
            final_result = result
        elif hasattr(result, "final_action"):
            if result.final_action and hasattr(result.final_action, "selected_action"):
                # This is a ConscienceResult - extract the final_action
                selected_action = result.final_action.selected_action
                final_result = result.final_action
                logger.debug(
                    "ThoughtProcessor: Extracted final_action %s from ConscienceResult for thought %s",
                    selected_action,
                    thought.thought_id,
                )
            else:
                logger.warning(
                    "ThoughtProcessor: ConscienceResult missing final_action for thought %s - defaulting to PONDER",
                    thought.thought_id,
                )
                ponder_params = PonderParams(questions=["conscience result empty"])
                selected_action = HandlerActionType.PONDER
                final_result = ActionSelectionDMAResult(
                    selected_action=selected_action,
                    action_parameters=ponder_params,
                    rationale="conscience result empty",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )
        else:
            logger.warning(
                f"ThoughtProcessor: Unknown result type for thought {thought.thought_id}: {type(result)}. Returning result as-is."
            )
            return result  # type: ignore[no-any-return]

        # Log the action being handled
        if selected_action:
            logger.debug(
                "ThoughtProcessor handling special case for action: %s",
                selected_action,
            )
            if selected_action == HandlerActionType.OBSERVE:
                logger.debug(
                    "ThoughtProcessor: final OBSERVE action for thought %s",
                    thought.thought_id,
                )
        else:
            logger.warning(f"ThoughtProcessor: No selected_action found for thought {thought.thought_id}")
            return final_result  # type: ignore[no-any-return]

        # TASK_COMPLETE actions should be returned as-is for proper dispatch
        if selected_action == HandlerActionType.TASK_COMPLETE:
            logger.debug(f"ThoughtProcessor: Returning TASK_COMPLETE result for thought {thought.thought_id}")
            return final_result  # type: ignore[no-any-return]

        # NOTE: PONDER actions are now handled by the PonderHandler in the action dispatcher
        # No special processing needed here - just return the result for normal dispatch
        return final_result  # type: ignore[no-any-return]

    def _update_thought_status(self, thought: Thought, result: Any) -> None:
        from ciris_engine.logic import persistence

        # Update the thought status in persistence
        # Support ConscienceResult as well as ActionSelectionDMAResult
        selected_action = None
        action_parameters = None
        rationale = None
        if hasattr(result, "selected_action"):
            selected_action = result.selected_action
            action_parameters = getattr(result, "action_parameters", None)
            rationale = getattr(result, "rationale", None)
        elif hasattr(result, "final_action") and hasattr(result.final_action, "selected_action"):
            selected_action = result.final_action.selected_action
            action_parameters = getattr(result.final_action, "action_parameters", None)
            rationale = getattr(result.final_action, "rationale", None)
        new_status_val = ThoughtStatus.COMPLETED  # Default, will be overridden by specific actions
        if selected_action == HandlerActionType.DEFER:
            new_status_val = ThoughtStatus.DEFERRED
        elif selected_action == HandlerActionType.PONDER:
            new_status_val = ThoughtStatus.PENDING  # Ponder implies it goes back to pending for re-evaluation
        elif selected_action == HandlerActionType.REJECT:
            new_status_val = ThoughtStatus.FAILED  # Reject implies failure of this thought path
        # Other actions might imply ThoughtStatus.COMPLETED if they are terminal for the thought.
        final_action_details = {
            "action_type": selected_action.value if selected_action else None,
            "parameters": action_parameters,  # Pass Pydantic object directly
            "rationale": rationale,
        }
        persistence.update_thought_status(
            thought_id=thought.thought_id,
            status=new_status_val,  # Pass ThoughtStatus enum member
            final_action=final_action_details,
        )

    async def _handle_action_selection(
        self, thought: Thought, action_selection: ActionSelectionDMAResult, context: dict
    ) -> Optional[ActionSelectionDMAResult]:
        """Handles the selected action by dispatching to the appropriate handler."""
        if action_selection.selected_action == HandlerActionType.PONDER:
            ponder_questions: List[Any] = []
            if action_selection.action_parameters:
                # Handle PonderParams type
                if hasattr(action_selection.action_parameters, "questions"):
                    ponder_questions = action_selection.action_parameters.questions

            if not ponder_questions:
                ponder_questions = [
                    "What is the core issue I need to address?",
                    "What additional context would help me provide a better response?",
                    "Are there any assumptions I should reconsider?",
                ]

            ponder_params = PonderParams(questions=ponder_questions)

            max_rounds = 5  # Default max rounds for ponder handler
            ponder_handler = PonderHandler(dependencies=self.dependencies, max_rounds=max_rounds)

            # Create ActionSelectionDMAResult for ponder handler
            ponder_result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=ponder_params,
                rationale="Processing PONDER action from action selection",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Create proper DispatchContext
            # Build proper dispatch context with all required fields
            import uuid

            from ciris_engine.schemas.runtime.contexts import DispatchContext

            # Ensure we always have a channel context
            channel_context = create_channel_context(context.get("channel_id", "unknown"))
            if channel_context is None:
                channel_context = create_channel_context("unknown")
            assert channel_context is not None  # For mypy

            dispatch_ctx = DispatchContext(
                # Core identification
                channel_context=channel_context,
                author_id=context.get("author_id", "system"),
                author_name=context.get("author_name", "CIRIS System"),
                # Service references
                origin_service="thought_processor",
                handler_name="PonderHandler",
                # Action context
                action_type=HandlerActionType.PONDER,
                thought_id=thought.thought_id,
                task_id=thought.source_task_id,
                source_task_id=thought.source_task_id,
                # Event details
                event_summary=f"Processing PONDER action for thought {thought.thought_id}",
                event_timestamp=self._time_service.now().isoformat(),
                # Additional context
                wa_id=None,
                wa_authorized=False,
                wa_context=None,
                conscience_failure_context=None,
                epistemic_data=None,
                correlation_id=str(uuid.uuid4()),
                span_id=None,
                trace_id=None,
            )

            await ponder_handler.handle(result=ponder_result, thought=thought, dispatch_context=dispatch_ctx)

            if thought.status == ThoughtStatus.PENDING:
                logger.info(
                    f"Thought ID {thought.thought_id} marked as PENDING after PONDER action - will be processed in next round."
                )

        if action_selection.selected_action == HandlerActionType.OBSERVE:
            agent_mode = getattr(self.app_config, "agent_mode", "").lower()
            if agent_mode == "cli":
                import os

                try:
                    cwd = os.getcwd()
                    files = os.listdir(cwd)
                    file_list = "\n".join(sorted(files))
                    observation = f"[CLI MODE] Agent working directory: {cwd}\n\nDirectory contents:\n{file_list}\n\nNote: CIRISAgent is running in CLI mode."
                except Exception as e:
                    observation = f"[CLI MODE] Error listing working directory: {e}"
                obs_result = locals().get("final_result", None)
                if obs_result and hasattr(obs_result, "action_parameters"):
                    if isinstance(obs_result.action_parameters, dict):
                        obs_result.action_parameters["observation"] = observation
                    else:
                        try:
                            setattr(obs_result.action_parameters, "observation", observation)
                        except Exception:
                            pass
                logger.info(f"[OBSERVE] CLI observation attached for thought {thought.thought_id}")
                return obs_result

        return None
