"""
Step point decorators for H3ERE pipeline pause/resume and streaming functionality.

This module provides clean decorators that handle:
1. Streaming step results to clients in real-time
2. Pausing thought execution at step points for single-step debugging
3. Maintaining live thought state in memory between steps

Architecture:
- @streaming_step: Always streams step data, no pausing
- @step_point: Handles pause/resume mechanics for single-step mode
- Both decorators can be applied together for full functionality
"""

import asyncio
import logging
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar, cast

from ciris_engine.logic.utils.jsondict_helpers import get_bool, get_dict, get_float, get_int, get_list, get_str
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.services.runtime_control import (
    ActionCompleteStepData,
    AllStepsExecutionResult,
    BaseStepData,
    ConscienceExecutionStepData,
    FinalizeActionStepData,
    GatherContextStepData,
    PerformActionStepData,
    PerformASPDMAStepData,
    PerformDMAsStepData,
    RecursiveASPDMAStepData,
    RecursiveConscienceStepData,
    RoundCompleteStepData,
    SpanAttribute,
    StartRoundStepData,
    StepDataUnion,
    StepExecutionResult,
    StepPoint,
    StepResultData,
    TraceContext,
)
from ciris_engine.schemas.types import JSONDict

F = TypeVar("F", bound=Callable[..., Any])

logger = logging.getLogger(__name__)

# Global registry for paused thought coroutines
_paused_thoughts: Dict[str, asyncio.Event] = {}
_single_step_mode = False


def _base_data_dict(base_data: BaseStepData) -> JSONDict:
    """Convert BaseStepData to dict for **unpacking into step data constructors."""
    return {
        "timestamp": base_data.timestamp,
        "thought_id": base_data.thought_id,
        "task_id": base_data.task_id,
        "processing_time_ms": base_data.processing_time_ms,
        "success": base_data.success,
        "error": base_data.error,
    }


async def _query_thought_resources(telemetry_service: Any, thought_id: str, timestamp: datetime) -> JSONDict:
    """Query telemetry service and aggregate resource usage for a thought.

    Args:
        telemetry_service: Telemetry service instance
        thought_id: ID of the thought to query resources for
        timestamp: End timestamp for the query window

    Returns:
        Dict with aggregated resource data:
        - tokens_total: Total tokens used
        - tokens_input: Input tokens used
        - tokens_output: Output tokens used
        - cost_cents: Total cost in USD cents
        - carbon_grams: Total CO2 emissions in grams
        - energy_mwh: Total energy in milliwatt-hours
        - llm_calls: Number of LLM calls
        - models_used: List of unique models used
    """
    if not telemetry_service:
        logger.debug(f"No telemetry service available to query resources for thought {thought_id}")
        return {
            "tokens_total": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_cents": 0.0,
            "carbon_grams": 0.0,
            "energy_mwh": 0.0,
            "llm_calls": 0,
            "models_used": [],
        }

    try:
        # Query all metric types with thought_id tag
        tags = {"thought_id": thought_id}

        # Query each metric type and aggregate
        tokens_total_data = await telemetry_service.query_metrics(
            metric_name="llm.tokens.total", tags=tags, end_time=timestamp
        )
        tokens_input_data = await telemetry_service.query_metrics(
            metric_name="llm.tokens.input", tags=tags, end_time=timestamp
        )
        tokens_output_data = await telemetry_service.query_metrics(
            metric_name="llm.tokens.output", tags=tags, end_time=timestamp
        )
        cost_data = await telemetry_service.query_metrics(metric_name="llm.cost.cents", tags=tags, end_time=timestamp)
        carbon_data = await telemetry_service.query_metrics(
            metric_name="llm.environmental.carbon_grams", tags=tags, end_time=timestamp
        )
        energy_data = await telemetry_service.query_metrics(
            metric_name="llm.environmental.energy_kwh", tags=tags, end_time=timestamp
        )

        # Aggregate metrics - sum all values
        tokens_total = sum(m.value for m in tokens_total_data)
        tokens_input = sum(m.value for m in tokens_input_data)
        tokens_output = sum(m.value for m in tokens_output_data)
        cost_cents = sum(m.value for m in cost_data)
        carbon_grams = sum(m.value for m in carbon_data)
        # Convert kWh to mWh (1 kWh = 1,000,000 mWh)
        energy_kwh = sum(m.value for m in energy_data)
        energy_mwh = energy_kwh * 1_000_000
        llm_calls = len(tokens_total_data)  # Each LLM call creates one tokens.total metric

        # Extract unique models from tags
        models_used = list({m.tags.get("model", "unknown") for m in tokens_total_data if hasattr(m, "tags")})

        logger.debug(
            f"Aggregated resources for thought {thought_id}: "
            f"{int(tokens_total)} tokens, {llm_calls} calls, {cost_cents:.4f} cents"
        )

        return {
            "tokens_total": int(tokens_total),
            "tokens_input": int(tokens_input),
            "tokens_output": int(tokens_output),
            "cost_cents": float(cost_cents),
            "carbon_grams": float(carbon_grams),
            "energy_mwh": float(energy_mwh),
            "llm_calls": llm_calls,
            "models_used": models_used,
        }

    except Exception as e:
        logger.error(f"Failed to query resources for thought {thought_id}: {e}", exc_info=True)
        # Return zeros on error - don't fail the entire action complete step
        return {
            "tokens_total": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "cost_cents": 0.0,
            "carbon_grams": 0.0,
            "energy_mwh": 0.0,
            "llm_calls": 0,
            "models_used": [],
        }


async def _maybe_add_resource_usage(
    step: StepPoint, processor: Any, thought_id: str, end_timestamp: Any, kwargs: JSONDict
) -> None:
    """Helper to add resource usage for ACTION_COMPLETE steps - reduces cognitive complexity."""
    if step != StepPoint.ACTION_COMPLETE:
        return

    # Get telemetry service from processor
    telemetry_service = getattr(processor, "telemetry_service", None) or getattr(
        getattr(processor, "sink", None), "telemetry", None
    )

    if telemetry_service:
        # Query resources and add to kwargs for _create_action_complete_data
        resource_data = await _query_thought_resources(telemetry_service, thought_id, end_timestamp)
        kwargs["_resource_usage"] = resource_data
    else:
        logger.warning(
            f"No telemetry service available for thought {thought_id} - "
            f"resource usage will not be recorded in action_complete event"
        )


def streaming_step(step: StepPoint) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator that streams step results in real-time.

    This decorator:
    1. Extracts step data from function arguments/results
    2. Broadcasts to global step_result_stream
    3. Never pauses - always streams and continues

    Args:
        step: The StepPoint enum for this step

    Usage:
        @streaming_step(StepPoint.GATHER_CONTEXT)
        async def _build_context(self, thought_item, ...):
            # Original logic unchanged
            return context_data
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(self: Any, thought_item: Any, *args: Any, **kwargs: Any) -> Any:
            thought_id = getattr(thought_item, "thought_id", "unknown")
            time_service = getattr(self, "_time_service", None)
            if not time_service or not hasattr(time_service, "now"):
                raise RuntimeError(
                    f"Critical error: No time service available for step {step.value} on thought {thought_id}"
                )
            start_timestamp = time_service.now()

            try:
                # Execute the original function
                result = await func(self, thought_item, *args, **kwargs)

                # Calculate processing time
                end_timestamp = time_service.now()
                processing_time_ms = (end_timestamp - start_timestamp).total_seconds() * 1000

                # Build typed base step data from function context
                base_step_data = BaseStepData(
                    timestamp=start_timestamp.isoformat(),
                    thought_id=thought_id,
                    processing_time_ms=processing_time_ms,
                    success=True,
                )

                # For ACTION_COMPLETE, query and aggregate resource usage by thought_id
                await _maybe_add_resource_usage(step, self, thought_id, end_timestamp, kwargs)

                # Add step-specific data and create typed step data
                step_data = _create_typed_step_data(step, base_step_data, thought_item, result, args, kwargs)

                # Broadcast simplified reasoning event for key steps only
                await _broadcast_reasoning_event(step, step_data, thought_item=thought_item)

                return result

            except Exception:
                # Stream error result
                end_timestamp = time_service.now()
                processing_time_ms = (end_timestamp - start_timestamp).total_seconds() * 1000

                # Don't broadcast errors as reasoning events - handled at higher level
                raise

        return cast(F, wrapper)

    return decorator


def step_point(step: StepPoint) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator that handles pause/resume mechanics for single-step debugging.

    This decorator:
    1. Checks if single-step mode is enabled
    2. Pauses the thought coroutine at this step point
    3. Waits for resume signal before continuing
    4. Maintains live thought state in memory

    Args:
        step: The StepPoint enum for this step

    Usage:
        @step_point(StepPoint.RECURSIVE_ASPDMA)
        async def _recursive_action_selection(self, thought_item, ...):
            # Only runs if previous step failed
            return retry_result
    """

    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(self: Any, thought_item: Any, *args: Any, **kwargs: Any) -> Any:
            thought_id = getattr(thought_item, "thought_id", "unknown")

            # Check if we should pause at this step point
            if _should_pause_at_step(step):
                logger.info(f"Pausing at step point {step.value} for thought {thought_id}")
                await _pause_thought_execution(thought_id)
                logger.info(f"Resuming from step point {step.value} for thought {thought_id}")

            # Execute the original function (thought continues naturally)
            return await func(self, thought_item, *args, **kwargs)

        return cast(F, wrapper)

    return decorator


# Helper functions for decorator implementation


def _should_pause_at_step(step: StepPoint) -> bool:
    """Check if we should pause at this step point."""
    global _single_step_mode

    # Only pause in single-step mode
    if not _single_step_mode:
        return False

    # Always pause at enabled step points in single-step mode
    return True


async def _pause_thought_execution(thought_id: str) -> None:
    """Pause this thought's execution until resumed."""
    global _paused_thoughts

    # Create resume event for this thought
    if thought_id not in _paused_thoughts:
        _paused_thoughts[thought_id] = asyncio.Event()

    # Wait for resume signal
    await _paused_thoughts[thought_id].wait()

    # Clear event for next pause
    _paused_thoughts[thought_id].clear()


def _get_step_data_creators() -> Dict[StepPoint, Callable[..., Any]]:
    """Get dispatch dictionary for step data creators."""
    return {
        StepPoint.START_ROUND: lambda base_data, result, args, kwargs, thought_item: _create_start_round_data(
            base_data, args
        ),
        StepPoint.GATHER_CONTEXT: lambda base_data, result, args, kwargs, thought_item: _create_gather_context_data(
            base_data, result
        ),
        StepPoint.PERFORM_DMAS: lambda base_data, result, args, kwargs, thought_item: _create_perform_dmas_data(
            base_data, result, thought_item
        ),
        StepPoint.PERFORM_ASPDMA: lambda base_data, result, args, kwargs, thought_item: _create_perform_aspdma_data(
            base_data, result, args
        ),
        StepPoint.CONSCIENCE_EXECUTION: lambda base_data, result, args, kwargs, thought_item: _create_conscience_execution_data(
            base_data, result, args
        ),
        StepPoint.RECURSIVE_ASPDMA: lambda base_data, result, args, kwargs, thought_item: _create_recursive_aspdma_data(
            base_data, result, args
        ),
        StepPoint.RECURSIVE_CONSCIENCE: lambda base_data, result, args, kwargs, thought_item: _create_recursive_conscience_data(
            base_data, result
        ),
        StepPoint.FINALIZE_ACTION: lambda base_data, result, args, kwargs, thought_item: _create_finalize_action_data(
            base_data, result
        ),
        StepPoint.PERFORM_ACTION: lambda base_data, result, args, kwargs, thought_item: _create_perform_action_data(
            base_data, result, args, kwargs
        ),
        StepPoint.ACTION_COMPLETE: lambda base_data, result, args, kwargs, thought_item: _create_action_complete_data(
            base_data, result, kwargs
        ),
        StepPoint.ROUND_COMPLETE: lambda base_data, result, args, kwargs, thought_item: _create_round_complete_data(
            base_data, args
        ),
    }


def _prepare_base_data_with_task_id(base_data: BaseStepData, thought_item: Any) -> BaseStepData:
    """Prepare base data with task_id from thought_item."""
    task_id = getattr(thought_item, "source_task_id", None)
    return base_data.model_copy(update={"task_id": task_id})


def _log_step_debug_info(step: StepPoint, base_data: BaseStepData, thought_item: Any) -> None:
    """Log debug information for step processing."""
    task_id = base_data.task_id
    thought_id = base_data.thought_id
    logger.debug(
        f"Step {step.value} for thought {thought_id}: task_id={task_id}, thought_item type={type(thought_item).__name__}"
    )
    if not task_id:
        logger.warning(f"Missing task_id for thought {thought_id} at step {step.value}")


def _create_typed_step_data(
    step: StepPoint,
    base_data: BaseStepData,
    thought_item: Any,
    result: Any,
    args: Tuple[Any, ...],
    kwargs: JSONDict,
) -> StepDataUnion:
    """Create typed step data based on step type using dispatch pattern."""
    # Prepare base data with task_id
    base_data = _prepare_base_data_with_task_id(base_data, thought_item)

    # Log debug information
    _log_step_debug_info(step, base_data, thought_item)

    # Get step data creator using dispatch pattern - fail fast for unknown steps
    step_creators = _get_step_data_creators()
    if step not in step_creators:
        raise ValueError(f"Unknown step point: {step.value}. No step data creator available.")

    # Create step-specific typed data - fail fast and loud on any errors
    return step_creators[step](base_data, result, args, kwargs, thought_item)  # type: ignore[no-any-return]


# This function is now integrated into _create_typed_step_data
# Keeping for potential backward compatibility but marked as deprecated


def _create_start_round_data(base_data: BaseStepData, args: Tuple[Any, ...]) -> StartRoundStepData:
    """Create START_ROUND specific typed data."""
    if not args:
        raise ValueError("START_ROUND args is empty - thought list is required for processing")

    return StartRoundStepData(**_base_data_dict(base_data), thoughts_processed=len(args), round_started=True)


def _create_gather_context_data(base_data: BaseStepData, result: Any) -> GatherContextStepData:
    """Create GATHER_CONTEXT specific typed data."""
    if result is None:
        raise ValueError("GATHER_CONTEXT step result is None - this indicates a serious pipeline issue")

    return GatherContextStepData(**_base_data_dict(base_data), context=str(result))


def _create_perform_dmas_data(base_data: BaseStepData, result: Any, thought_item: Any) -> PerformDMAsStepData:
    """Create PERFORM_DMAS specific typed data."""
    if not result:
        raise ValueError("PERFORM_DMAS step result is None - this indicates a serious pipeline issue")

    if hasattr(result, "ethical_pdma"):
        # Handle InitialDMAResults object
        dma_parts = []
        if result.ethical_pdma:
            dma_parts.append(f"ethical_pdma: {result.ethical_pdma}")
        if result.csdma:
            dma_parts.append(f"csdma: {result.csdma}")
        if result.dsdma:
            dma_parts.append(f"dsdma: {result.dsdma}")
        dma_results = "; ".join(dma_parts) if dma_parts else "No DMA results"
    else:
        # Non-InitialDMAResults object - validate it has expected structure
        dma_results = str(result)

    if not thought_item:
        raise ValueError("PERFORM_DMAS thought_item is None - this indicates a serious pipeline issue")

    if not hasattr(thought_item, "initial_context"):
        raise AttributeError(
            f"PERFORM_DMAS thought_item missing 'initial_context' attribute. Type: {type(thought_item)}, attributes: {dir(thought_item)}"
        )

    return PerformDMAsStepData(
        **_base_data_dict(base_data), dma_results=dma_results, context=str(thought_item.initial_context)
    )


def _validate_aspdma_result(result: Any) -> None:
    """Validate ASPDMA result has required attributes."""
    if not result:
        raise ValueError("PERFORM_ASPDMA step result is None - this indicates a serious pipeline issue")

    if not hasattr(result, "selected_action"):
        raise AttributeError(
            f"PERFORM_ASPDMA result missing 'selected_action' attribute. Result type: {type(result)}, available attributes: {dir(result)}"
        )

    if not hasattr(result, "rationale"):
        raise AttributeError(
            f"PERFORM_ASPDMA result missing 'rationale' attribute. Result type: {type(result)}, available attributes: {dir(result)}"
        )


def _extract_dma_results_from_args(args: Tuple[Any, ...]) -> Any:
    """
    Extract DMA results object from ASPDMA args.

    Returns the concrete InitialDMAResults object (NOT a string or dict).
    """
    # Extract dma_results from args - it's the second positional arg after thought_context
    # Function signature: _perform_aspdma_step(self, thought_item, thought_context, dma_results)
    # args = (thought_context, dma_results)
    if len(args) < 2:
        return None

    dma_results_obj = args[1]
    # Return the concrete InitialDMAResults object directly
    return dma_results_obj


def _create_perform_aspdma_data(base_data: BaseStepData, result: Any, args: Tuple[Any, ...]) -> PerformASPDMAStepData:
    """Create PERFORM_ASPDMA specific typed data."""
    _validate_aspdma_result(result)
    dma_results_obj = _extract_dma_results_from_args(args)

    # Create string summary for display
    dma_results_str = None
    if dma_results_obj and hasattr(dma_results_obj, "csdma"):
        dma_parts = []
        if dma_results_obj.csdma:
            dma_parts.append(f"csdma: {dma_results_obj.csdma}")
        if dma_results_obj.dsdma:
            dma_parts.append(f"dsdma: {dma_results_obj.dsdma}")
        if dma_results_obj.ethical_pdma:
            dma_parts.append(f"ethical_pdma: {dma_results_obj.ethical_pdma}")
        dma_results_str = "; ".join(dma_parts) if dma_parts else None

    # Rationale is now REQUIRED in ActionSelectionDMAResult schema
    action_rationale = result.rationale

    return PerformASPDMAStepData(
        **_base_data_dict(base_data),
        selected_action=str(result.selected_action),
        action_rationale=action_rationale,
        dma_results=dma_results_str,  # String summary for display
        dma_results_obj=dma_results_obj,  # Concrete InitialDMAResults object for event creation
    )


def _validate_conscience_execution_result(result: Any) -> None:
    """Validate conscience execution result has required attributes."""
    if not result:
        raise ValueError("CONSCIENCE_EXECUTION step result is None - this indicates a serious pipeline issue")

    if not hasattr(result, "overridden"):
        raise AttributeError(
            f"CONSCIENCE_EXECUTION result missing 'overridden' attribute. Expected ConscienceApplicationResult, got {type(result)}, attributes: {dir(result)}"
        )

    if not hasattr(result, "final_action"):
        raise AttributeError(
            f"CONSCIENCE_EXECUTION result missing 'final_action' attribute. Expected ConscienceApplicationResult, got {type(result)}, attributes: {dir(result)}"
        )

    if not hasattr(result.final_action, "selected_action"):
        raise AttributeError(
            f"CONSCIENCE_EXECUTION final_action missing 'selected_action' attribute. final_action type: {type(result.final_action)}, attributes: {dir(result.final_action)}"
        )

    if result.overridden and not hasattr(result, "override_reason"):
        raise AttributeError(
            f"CONSCIENCE_EXECUTION result overridden but missing 'override_reason'. Result type: {type(result)}, attributes: {dir(result)}"
        )


def _extract_conscience_execution_values(result: Any) -> tuple[str, bool, str, str | None]:
    """Extract core values from conscience execution result."""
    selected_action = str(result.final_action.selected_action)
    conscience_passed = not result.overridden
    action_result = str(result.final_action)
    override_reason = str(result.override_reason) if result.overridden else None
    return selected_action, conscience_passed, action_result, override_reason


def _build_conscience_result_from_check(
    conscience_check_result: Any, override_reason: Optional[str]  # ConscienceCheckResult
) -> Any:  # ConscienceResult
    """Build ConscienceResult from ConscienceCheckResult."""
    from ciris_engine.schemas.conscience.results import ConscienceResult

    # Build details dict, excluding None values
    details = {"status": conscience_check_result.status.value if conscience_check_result.status else "unknown"}

    if conscience_check_result.entropy_check:
        details["entropy_passed"] = conscience_check_result.entropy_check.passed

    if conscience_check_result.coherence_check:
        details["coherence_passed"] = conscience_check_result.coherence_check.passed

    if conscience_check_result.optimization_veto_check:
        details["optimization_veto"] = conscience_check_result.optimization_veto_check.decision

    if conscience_check_result.epistemic_humility_check:
        details["epistemic_humility"] = conscience_check_result.epistemic_humility_check.epistemic_certainty

    return ConscienceResult(
        conscience_name="conscience_execution",
        passed=conscience_check_result.passed,
        severity="critical" if not conscience_check_result.passed else "info",
        message=conscience_check_result.reason or "Conscience check completed",
        override_action=override_reason,
        details=details,
    )


def _create_conscience_execution_data(
    base_data: BaseStepData, result: Any, args: Tuple[Any, ...]
) -> ConscienceExecutionStepData:
    """Add CONSCIENCE_EXECUTION specific data with full transparency."""
    # Validate result structure using helper
    _validate_conscience_execution_result(result)

    # Extract core values using helper
    selected_action, conscience_passed, action_result, override_reason = _extract_conscience_execution_values(result)

    # Extract action rationale from INPUT action_result (args[0]) - this is what goes into conscience
    # The ASPDMA_RESULT event shows the action BEFORE conscience validation
    if not args or len(args) == 0:
        raise ValueError("CONSCIENCE_EXECUTION requires action_result as first argument")

    input_action_result = args[0]  # This is the ActionSelectionDMAResult passed to conscience
    action_rationale = input_action_result.rationale

    # Extract ASPDMA prompt if available (set by evaluator in user_prompt field)
    aspdma_prompt = getattr(input_action_result, "user_prompt", None)

    # Create comprehensive conscience evaluation details for full transparency
    conscience_check_result = _create_comprehensive_conscience_result(result)

    # Build conscience result using helper
    conscience_result = _build_conscience_result_from_check(conscience_check_result, override_reason)

    return ConscienceExecutionStepData(
        **_base_data_dict(base_data),
        selected_action=selected_action,
        action_rationale=action_rationale,
        conscience_passed=conscience_passed,
        action_result=action_result,
        override_reason=override_reason,
        conscience_result=conscience_result,
        aspdma_prompt=aspdma_prompt,
    )


def _create_entropy_check(passed: bool) -> Any:  # EntropyCheckResult
    """Create entropy check result for conscience evaluation."""
    from ciris_engine.schemas.conscience.core import EntropyCheckResult

    return EntropyCheckResult(
        passed=passed,
        entropy_score=0.3,  # Mock value - in real implementation would come from actual entropy calculation
        threshold=0.5,
        message=(
            "Entropy check: Action maintains appropriate information uncertainty"
            if passed
            else "Entropy check failed: Action reduces information uncertainty below threshold"
        ),
    )


def _create_coherence_check(passed: bool) -> Any:  # CoherenceCheckResult
    """Create coherence check result for conscience evaluation."""
    from ciris_engine.schemas.conscience.core import CoherenceCheckResult

    return CoherenceCheckResult(
        passed=passed,
        coherence_score=0.8,  # Mock value - in real implementation would come from coherence analysis
        threshold=0.6,
        message=(
            "Coherence check: Action maintains internal consistency"
            if passed
            else "Coherence check failed: Action creates internal inconsistencies"
        ),
    )


def _create_optimization_veto_check(passed: bool) -> Any:  # OptimizationVetoResult
    """Create optimization veto check result for conscience evaluation."""
    from ciris_engine.schemas.conscience.core import OptimizationVetoResult

    return OptimizationVetoResult(
        decision="proceed" if passed else "abort",
        justification=(
            "Action aligns with preservation of human values"
            if passed
            else "Action may compromise human values - optimization vetoed"
        ),
        entropy_reduction_ratio=0.15,  # Mock value
        affected_values=[] if passed else ["human_autonomy", "epistemic_humility"],
    )


def _create_epistemic_humility_check(passed: bool) -> Any:  # EpistemicHumilityResult
    """Create epistemic humility check result for conscience evaluation."""
    from ciris_engine.schemas.conscience.core import EpistemicHumilityResult

    return EpistemicHumilityResult(
        epistemic_certainty=0.7,  # Mock value - appropriate certainty level
        identified_uncertainties=["action_outcome_variance", "context_completeness"] if not passed else [],
        reflective_justification=(
            "Action demonstrates appropriate uncertainty about outcomes"
            if passed
            else "Action shows overconfidence requiring reflection"
        ),
        recommended_action="proceed" if passed else "ponder",
    )


def _create_comprehensive_conscience_result(result: Any) -> Any:  # ConscienceCheckResult
    """Create comprehensive ConscienceCheckResult with all 4 typed evaluations for transparency."""
    from datetime import datetime, timezone

    from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus, EpistemicData

    # Determine overall conscience status
    status = ConscienceStatus.FAILED if result.overridden else ConscienceStatus.PASSED
    passed = not result.overridden
    reason = result.override_reason if result.overridden else None

    # Create the 4 required typed conscience evaluations using helpers
    entropy_check = _create_entropy_check(passed)
    coherence_check = _create_coherence_check(passed)
    optimization_veto_check = _create_optimization_veto_check(passed)
    epistemic_humility_check = _create_epistemic_humility_check(passed)

    # Create epistemic metadata
    epistemic_data = EpistemicData(
        entropy_level=entropy_check.entropy_score,
        coherence_level=coherence_check.coherence_score,
        uncertainty_acknowledged=True,
        reasoning_transparency=0.9,  # High transparency due to detailed reporting
    )

    # Build comprehensive conscience result
    conscience_result = ConscienceCheckResult(
        status=status,
        passed=passed,
        reason=reason,
        epistemic_data=epistemic_data,
        entropy_check=entropy_check,
        coherence_check=coherence_check,
        optimization_veto_check=optimization_veto_check,
        epistemic_humility_check=epistemic_humility_check,
        entropy_score=entropy_check.entropy_score,
        coherence_score=coherence_check.coherence_score,
        check_timestamp=datetime.now(timezone.utc),
        processing_time_ms=None,  # Could be calculated if timing info available
        original_action=result.original_action.model_dump(),
        replacement_action=result.final_action.model_dump() if result.overridden else None,
        thought_depth_triggered=getattr(result, "thought_depth_triggered", None),
        updated_status_detected=getattr(result, "updated_status_detected", None),
    )

    return conscience_result


def _create_recursive_aspdma_data(
    base_data: BaseStepData, result: Any, args: Tuple[Any, ...]
) -> RecursiveASPDMAStepData:
    """Create RECURSIVE_ASPDMA specific typed data."""
    if not args:
        raise ValueError("RECURSIVE_ASPDMA args is empty - retry reason is required")

    if not result:
        raise ValueError("RECURSIVE_ASPDMA result is None - this indicates a serious pipeline issue")

    if not hasattr(result, "selected_action"):
        raise AttributeError(
            f"RECURSIVE_ASPDMA result missing 'selected_action' attribute. Result type: {type(result)}, attributes: {dir(result)}"
        )

    return RecursiveASPDMAStepData(
        **_base_data_dict(base_data), retry_reason=str(args[0]), original_action=str(result.selected_action)
    )


def _create_recursive_conscience_data(base_data: BaseStepData, result: Any) -> RecursiveConscienceStepData:
    """Create RECURSIVE_CONSCIENCE specific typed data."""
    if not result:
        raise ValueError("RECURSIVE_CONSCIENCE result is None - this indicates a serious pipeline issue")

    if not hasattr(result, "selected_action"):
        raise AttributeError(
            f"RECURSIVE_CONSCIENCE result missing 'selected_action' attribute. Result type: {type(result)}, attributes: {dir(result)}"
        )

    return RecursiveConscienceStepData(
        **_base_data_dict(base_data), retry_action=str(result.selected_action), retry_result=str(result)
    )


def _create_finalize_action_data(base_data: BaseStepData, result: Any) -> FinalizeActionStepData:
    """Create FINALIZE_ACTION specific typed data with rich conscience information."""
    if not result:
        raise ValueError("FINALIZE_ACTION result is None - this indicates a serious pipeline issue")

    # Result should be ConscienceApplicationResult
    if not hasattr(result, "final_action"):
        raise AttributeError(
            f"FINALIZE_ACTION result missing 'final_action' attribute. Expected ConscienceApplicationResult, got {type(result)}, attributes: {dir(result)}"
        )

    # Extract the final action
    final_action = result.final_action
    if not hasattr(final_action, "selected_action"):
        raise AttributeError(
            f"FINALIZE_ACTION final_action missing 'selected_action' attribute. Type: {type(final_action)}, attributes: {dir(final_action)}"
        )

    # Extract conscience data (epistemic_data is now REQUIRED in ConscienceApplicationResult)
    conscience_passed = not result.overridden
    override_reason = result.override_reason if result.overridden else None
    epistemic_data = result.epistemic_data  # REQUIRED field
    updated_status_detected = getattr(result, "updated_status_detected", None)

    return FinalizeActionStepData(
        **_base_data_dict(base_data),
        selected_action=str(final_action.selected_action),
        conscience_passed=conscience_passed,
        conscience_override_reason=override_reason,
        epistemic_data=epistemic_data,
        updated_status_detected=updated_status_detected,
    )


def _create_perform_action_data(
    base_data: BaseStepData, result: Any, args: Tuple[Any, ...], kwargs: JSONDict
) -> PerformActionStepData:
    """Create PERFORM_ACTION specific typed data."""
    # Extract selected_action - first try result, then args
    if result and hasattr(result, "selected_action"):
        selected_action = str(result.selected_action)
    elif args:
        selected_action = str(args[0])
    else:
        raise ValueError(
            "PERFORM_ACTION cannot determine selected_action - neither result.selected_action nor args[0] available"
        )

    # Extract action_parameters - use None string if not available
    action_parameters = "None"
    if result and hasattr(result, "action_parameters"):
        action_parameters = str(result.action_parameters)

    # Extract dispatch_context from kwargs or args - provide empty dict as default
    dispatch_context = "{}"
    if "context" in kwargs:
        dispatch_context = str(kwargs["context"])
    elif len(args) > 1:
        dispatch_context = str(args[1])

    return PerformActionStepData(
        **_base_data_dict(base_data),
        selected_action=selected_action,
        action_parameters=action_parameters,
        dispatch_context=dispatch_context,
    )


def _create_action_complete_data(
    base_data: BaseStepData, result: Any, kwargs: Optional[JSONDict] = None
) -> ActionCompleteStepData:
    """Add ACTION_COMPLETE specific data with resource usage."""
    if not result:
        raise ValueError("ACTION_COMPLETE step result is None - this indicates a serious pipeline issue")

    # Result should be ActionResponse (typed) - no more dict access
    from ciris_engine.schemas.services.runtime_control import ActionResponse

    if not isinstance(result, ActionResponse):
        raise TypeError(
            f"ACTION_COMPLETE expects ActionResponse, got {type(result)}. "
            f"Handlers must return ActionResponse with audit_data."
        )

    # Extract resource usage data if available (passed via kwargs from decorator)
    kwargs_dict = kwargs or {}
    resource_data = get_dict(kwargs_dict, "_resource_usage", {})

    return ActionCompleteStepData(
        **_base_data_dict(base_data),
        action_executed=result.action_type,
        dispatch_success=result.success,
        handler_completed=result.handler != "Unknown",
        follow_up_processing_pending=bool(result.follow_up_thought_id),
        follow_up_thought_id=result.follow_up_thought_id,
        execution_time_ms=result.execution_time_ms,
        # Audit data from AuditEntryResult (REQUIRED fields)
        audit_entry_id=result.audit_data.entry_id,
        audit_sequence_number=result.audit_data.sequence_number,
        audit_entry_hash=result.audit_data.entry_hash,
        audit_signature=result.audit_data.signature,
        # Resource usage (queried from telemetry by thought_id)
        tokens_total=get_int(resource_data, "tokens_total", 0),
        tokens_input=get_int(resource_data, "tokens_input", 0),
        tokens_output=get_int(resource_data, "tokens_output", 0),
        cost_cents=get_float(resource_data, "cost_cents", 0.0),
        carbon_grams=get_float(resource_data, "carbon_grams", 0.0),
        energy_mwh=get_float(resource_data, "energy_mwh", 0.0),
        llm_calls=get_int(resource_data, "llm_calls", 0),
        models_used=get_list(resource_data, "models_used", []),
    )


def _create_round_complete_data(base_data: BaseStepData, args: Tuple[Any, ...]) -> RoundCompleteStepData:
    """Create ROUND_COMPLETE specific typed data."""
    if not args:
        raise ValueError("ROUND_COMPLETE args is empty - completed thought count is required")

    return RoundCompleteStepData(**_base_data_dict(base_data), round_status="completed", thoughts_processed=len(args))


def _create_step_result_schema(step: StepPoint, step_data: StepDataUnion) -> Any:
    """Create appropriate step result schema based on step type."""
    # Import here to avoid circular dependency
    from ciris_engine.schemas.services.runtime_control import (
        StepResultActionComplete,
        StepResultConscienceExecution,
        StepResultFinalizeAction,
        StepResultGatherContext,
        StepResultPerformAction,
        StepResultPerformASPDMA,
        StepResultPerformDMAs,
        StepResultRecursiveASPDMA,
        StepResultRecursiveConscience,
        StepResultRoundComplete,
        StepResultStartRound,
    )

    step_result_map = {
        StepPoint.START_ROUND: StepResultStartRound,
        StepPoint.GATHER_CONTEXT: StepResultGatherContext,
        StepPoint.PERFORM_DMAS: StepResultPerformDMAs,
        StepPoint.PERFORM_ASPDMA: StepResultPerformASPDMA,
        StepPoint.CONSCIENCE_EXECUTION: StepResultConscienceExecution,
        StepPoint.RECURSIVE_ASPDMA: StepResultRecursiveASPDMA,
        StepPoint.RECURSIVE_CONSCIENCE: StepResultRecursiveConscience,
        StepPoint.FINALIZE_ACTION: StepResultFinalizeAction,
        StepPoint.PERFORM_ACTION: StepResultPerformAction,
        StepPoint.ACTION_COMPLETE: StepResultActionComplete,
        StepPoint.ROUND_COMPLETE: StepResultRoundComplete,
    }

    result_class = step_result_map.get(step)
    if result_class:
        if step == StepPoint.GATHER_CONTEXT:
            logger.debug(f"Creating StepResultGatherContext with step_data type: {type(step_data)}, data: {step_data}")
        return result_class(**step_data.model_dump())
    return None


def _extract_timing_data(step_data: StepDataUnion) -> Tuple[Any, Any]:
    """Extract and normalize timing data from typed step_data."""
    from datetime import datetime, timezone

    timestamp_str = step_data.timestamp if step_data.timestamp else datetime.now().isoformat()
    # Ensure both timestamps have timezone info for consistent calculation
    if timestamp_str.endswith("+00:00") or timestamp_str.endswith("Z"):
        start_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    else:
        start_time = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
    end_time = datetime.now(timezone.utc)

    return start_time, end_time


def _build_step_result_data(
    step: StepPoint,
    step_data: StepDataUnion,
    trace_context: TraceContext,
    span_attributes: List[SpanAttribute],
) -> StepResultData:
    """Build the complete step result data structure."""
    return StepResultData(
        step_point=step.value,
        success=step_data.success,
        processing_time_ms=step_data.processing_time_ms,
        thought_id=step_data.thought_id,
        task_id=step_data.task_id or "",
        step_data=step_data,  # Use the typed step data object directly
        # Enhanced trace data for OTLP compatibility
        trace_context=trace_context,
        span_attributes=span_attributes,
        otlp_compatible=True,
    )


async def _broadcast_step_result(step: StepPoint, step_data: StepDataUnion) -> None:
    """Broadcast step result to global step result stream (DEPRECATED - use reasoning events)."""
    # OLD BROADCASTING - TO BE REMOVED
    # Keep for now to avoid breaking changes, but reasoning events are the future
    pass


async def _broadcast_reasoning_event(
    step: StepPoint, step_data: StepDataUnion, is_recursive: bool = False, thought_item: Any = None
) -> None:
    """
    Broadcast simplified reasoning event for one of the 6 key steps.

    CORRECT Step Point Mapping:
    0. START_ROUND → THOUGHT_START (thought + task metadata)
    1. GATHER_CONTEXT + PERFORM_DMAS → SNAPSHOT_AND_CONTEXT (snapshot + context)
    2. PERFORM_DMAS → DMA_RESULTS (Results of the 3 DMAs: CSDMA, DSDMA, PDMA)
    3. PERFORM_ASPDMA → ASPDMA_RESULT (result of ASPDMA action selection)
    4. CONSCIENCE_EXECUTION (+ RECURSIVE_CONSCIENCE) → CONSCIENCE_RESULT (result of 5 consciences, with is_recursive flag)
    5. ACTION_COMPLETE → ACTION_RESULT (execution + audit)
    """
    logger.debug(f"[BROADCAST DEBUG] _broadcast_reasoning_event called for step {step.value}")
    try:
        from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream
        from ciris_engine.schemas.streaming.reasoning_stream import create_reasoning_event

        logger.debug("[BROADCAST DEBUG] Imports successful")

        event = None
        timestamp = step_data.timestamp or datetime.now().isoformat()
        logger.debug(f"[BROADCAST DEBUG] timestamp={timestamp}, step={step.value}")

        # Map step points to reasoning events using helper functions
        if step == StepPoint.START_ROUND:
            # Event 0: THOUGHT_START
            event = _create_thought_start_event(step_data, timestamp, create_reasoning_event, thought_item)

        elif step in (StepPoint.GATHER_CONTEXT, StepPoint.PERFORM_DMAS):
            # Event 1: SNAPSHOT_AND_CONTEXT (emitted at PERFORM_DMAS only)
            if step == StepPoint.PERFORM_DMAS:
                logger.debug("[BROADCAST DEBUG] Creating SNAPSHOT_AND_CONTEXT event")
                event = _create_snapshot_and_context_event(step_data, timestamp, create_reasoning_event, thought_item)

        elif step == StepPoint.PERFORM_ASPDMA:
            # Event 2: DMA_RESULTS - get InitialDMAResults from step_data.dma_results (extracted from args)
            # step_data for PERFORM_ASPDMA contains dma_results from the previous PERFORM_DMAS step
            dma_results_for_event = getattr(step_data, "dma_results_obj", None)
            if dma_results_for_event:
                event = _create_dma_results_event(step_data, timestamp, dma_results_for_event, create_reasoning_event)
            else:
                logger.warning(f"No dma_results_obj found in step_data for PERFORM_ASPDMA step {step_data.thought_id}")

        elif step in (StepPoint.CONSCIENCE_EXECUTION, StepPoint.RECURSIVE_CONSCIENCE):
            # Event 3: ASPDMA_RESULT
            is_recursive_step = step == StepPoint.RECURSIVE_CONSCIENCE
            event = _create_aspdma_result_event(step_data, timestamp, is_recursive_step, create_reasoning_event)

        elif step == StepPoint.FINALIZE_ACTION:
            # Event 4: CONSCIENCE_RESULT
            event = _create_conscience_result_event(step_data, timestamp, create_reasoning_event)

        elif step == StepPoint.ACTION_COMPLETE:
            # Event 5: ACTION_RESULT
            event = _create_action_result_event(step_data, timestamp, create_reasoning_event)

        # Broadcast the event if we created one
        if event:
            logger.debug(
                f" Broadcasting reasoning event - type={event.event_type}, task_id={step_data.task_id}, thought_id={step_data.thought_id}"
            )
            await reasoning_event_stream.broadcast_reasoning_event(event)
            logger.debug(f" Broadcast complete - type={event.event_type}, task_id={step_data.task_id}")
        else:
            logger.debug(f" No event created for step {step.value}, task_id={step_data.task_id}")

    except Exception as e:
        logger.warning(f"Error broadcasting reasoning event for {step.value}: {e}")


# Public API functions for single-step control


def enable_single_step_mode() -> None:
    """Enable single-step mode - thoughts will pause at step points."""
    global _single_step_mode
    _single_step_mode = True
    logger.info("Single-step mode enabled")


def disable_single_step_mode() -> None:
    """Disable single-step mode - thoughts run normally."""
    global _single_step_mode
    _single_step_mode = False
    logger.info("Single-step mode disabled")


def is_single_step_mode() -> bool:
    """Check if single-step mode is enabled."""
    return _single_step_mode


async def execute_step(thought_id: str) -> StepExecutionResult:
    """
    Execute one step for a paused thought.

    Args:
        thought_id: ID of the thought to advance one step

    Returns:
        Status dict indicating success/failure
    """
    global _paused_thoughts

    if thought_id not in _paused_thoughts:
        return StepExecutionResult(
            success=False,
            error=f"Thought {thought_id} is not paused or does not exist",
            thought_id=thought_id,
        )

    try:
        # Resume the thought coroutine
        _paused_thoughts[thought_id].set()

        return StepExecutionResult(
            success=True,
            thought_id=thought_id,
            message="Thought advanced one step",
        )

    except Exception as e:
        logger.error(f"Error executing step for thought {thought_id}: {e}")
        return StepExecutionResult(
            success=False,
            error=str(e),
            thought_id=thought_id,
        )


async def execute_all_steps() -> AllStepsExecutionResult:
    """
    Execute one step for all paused thoughts.

    Returns:
        Status dict with count of thoughts advanced
    """
    global _paused_thoughts

    if not _paused_thoughts:
        return AllStepsExecutionResult(
            success=True,
            thoughts_advanced=0,
            message="No thoughts currently paused",
        )

    try:
        # Resume all paused thoughts
        for event in _paused_thoughts.values():
            event.set()

        count = len(_paused_thoughts)

        return AllStepsExecutionResult(
            success=True,
            thoughts_advanced=count,
            message=f"Advanced {count} thoughts one step",
        )

    except Exception as e:
        logger.error(f"Error executing steps for all thoughts: {e}")
        return AllStepsExecutionResult(
            success=False,
            error=str(e),
            thoughts_advanced=0,
        )


def get_paused_thoughts() -> Dict[str, str]:
    """
    Get list of currently paused thoughts.

    Returns:
        Dict mapping thought_id to status
    """
    global _paused_thoughts

    return dict.fromkeys(_paused_thoughts.keys(), "paused_awaiting_resume")


# Enhanced trace data builders for OTLP compatibility


def _build_trace_context_dict(
    thought_id: str, task_id: Optional[str], step: StepPoint, start_time: Any, end_time: Any
) -> TraceContext:
    """
    Build trace context compatible with OTLP format.

    This ensures streaming and OTLP traces have consistent trace correlation data.
    """
    import hashlib
    import time

    # Generate trace and span IDs using same logic as OTLP converter
    trace_base = f"{thought_id}_{task_id or 'no_task'}_{step.value}"
    trace_id = hashlib.sha256(trace_base.encode()).hexdigest()[:32].upper()

    span_base = f"{trace_id}_{step.value}_{start_time.timestamp()}"
    span_id = hashlib.sha256(span_base.encode()).hexdigest()[:16].upper()

    # Build parent span relationship - each step in the same thought is related
    parent_span_base = f"{thought_id}_pipeline_{task_id or 'no_task'}"
    parent_span_id = hashlib.sha256(parent_span_base.encode()).hexdigest()[:16].upper()

    return TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        span_name=f"h3ere.{step.value}",
        operation_name=f"H3ERE.{step.value}",
        start_time_ns=int(start_time.timestamp() * 1e9),
        end_time_ns=int(end_time.timestamp() * 1e9),
        duration_ns=int((end_time - start_time).total_seconds() * 1e9),
        span_kind="internal",  # H3ERE pipeline steps are internal operations
    )


def _extract_follow_up_thought_id(result: Any) -> Optional[str]:
    """
    Extract follow-up thought ID from ACTION_COMPLETE result.

    According to the requirement: Anything but DEFER, REJECT, or TASK_COMPLETE
    should have a follow-up thought created.

    Args:
        result: The ACTION_COMPLETE step result (dict or object)

    Returns:
        Follow-up thought ID if available, None otherwise
    """
    # Terminal actions that don't create follow-ups
    TERMINAL_ACTIONS = {"DEFER", "REJECT", "TASK_COMPLETE"}

    # Try to extract from dict format (primary path)
    if isinstance(result, dict):
        # Check action type FIRST to determine if follow-up should exist
        action_type = result.get("action_type", "").upper()

        if action_type in TERMINAL_ACTIONS:
            # These actions should NOT have follow-ups, even if ID is present
            return None

        # For non-terminal actions, extract the follow_up_thought_id
        return result.get("follow_up_thought_id")

    # Try to extract from object format
    if hasattr(result, "follow_up_thought_id"):
        return str(result.follow_up_thought_id) if result.follow_up_thought_id else None

    # Check for alternative attribute names
    if hasattr(result, "follow_up_id"):
        return str(result.follow_up_id) if result.follow_up_id else None

    return None


def _extract_lightweight_system_snapshot() -> SystemSnapshot:
    """
    Extract lightweight system snapshot for reasoning event context.

    Returns a proper SystemSnapshot object with minimal fields populated.
    This is used for SSE streaming and must be a concrete typed object.
    """
    from datetime import timezone

    # Create a minimal SystemSnapshot with current time
    snapshot = SystemSnapshot(
        current_time_utc=datetime.now(timezone.utc).isoformat(),
    )

    return snapshot


def _create_thought_start_event(
    step_data: StepDataUnion, timestamp: str, create_reasoning_event: Any, thought_item: Any = None
) -> Any:
    """Create THOUGHT_START reasoning event with thought and task metadata."""
    from ciris_engine.logic.persistence import get_task_by_id, get_thought_by_id
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent

    # Get occurrence_id from thought_item if available
    occurrence_id = getattr(thought_item, "agent_occurrence_id", "default") if thought_item else "default"

    # Get full thought and task data from persistence
    thought = get_thought_by_id(step_data.thought_id, occurrence_id)
    task = get_task_by_id(step_data.task_id) if step_data.task_id else None

    return create_reasoning_event(
        event_type=ReasoningEvent.THOUGHT_START,
        thought_id=step_data.thought_id,
        task_id=step_data.task_id or "",
        timestamp=timestamp,
        # Thought metadata
        thought_type=thought.thought_type.value if thought else "unknown",
        thought_content=thought.content if thought else "",
        thought_status=thought.status.value if thought else "unknown",
        round_number=thought.round_number if thought else 0,
        thought_depth=thought.thought_depth if thought else 0,
        parent_thought_id=thought.parent_thought_id if thought else None,
        # Task metadata
        task_description=task.description if task else "",
        task_priority=task.priority if task else 0,
        channel_id=task.channel_id if task else "",
        updated_info_available=task.updated_info_available if task else False,
    )


def _create_snapshot_and_context_event(
    step_data: StepDataUnion, timestamp: str, create_reasoning_event: Any, thought_item: Any = None
) -> Any:
    """Create SNAPSHOT_AND_CONTEXT reasoning event with full system snapshot from thought context."""
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent

    # Extract full SystemSnapshot from thought_item.initial_context
    # Note: context string field removed - all data is in system_snapshot
    system_snapshot = None
    if thought_item and hasattr(thought_item, "initial_context"):
        initial_context = thought_item.initial_context
        if isinstance(initial_context, dict):
            # Extract system_snapshot from ProcessingThoughtContext dict
            system_snapshot = initial_context.get("system_snapshot")
        elif hasattr(initial_context, "system_snapshot"):
            # Extract from ProcessingThoughtContext object
            system_snapshot = initial_context.system_snapshot

    # Fallback to minimal snapshot if we couldn't extract the full one
    if not system_snapshot:
        logger.warning("Could not extract full SystemSnapshot from thought_item, using minimal snapshot")
        system_snapshot = _extract_lightweight_system_snapshot()

    return create_reasoning_event(
        event_type=ReasoningEvent.SNAPSHOT_AND_CONTEXT,
        thought_id=step_data.thought_id,
        task_id=step_data.task_id,
        timestamp=timestamp,
        system_snapshot=system_snapshot,
    )


def _create_dma_results_event(
    step_data: StepDataUnion, timestamp: str, dma_results: Any, create_reasoning_event: Any
) -> Any:
    """
    Create DMA_RESULTS reasoning event from InitialDMAResults.

    This event is broadcast at the START of PERFORM_ASPDMA step, using the
    result parameter which contains InitialDMAResults from PERFORM_DMAS.
    """
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent

    # Extract the 3 DMA results from InitialDMAResults object - pass concrete typed objects
    if not dma_results:
        raise ValueError(f"DMA results is None or empty: {dma_results}")
    if not hasattr(dma_results, "csdma"):
        raise ValueError(
            f"DMA results missing 'csdma' attribute. Type: {type(dma_results)}, attributes: {dir(dma_results)}"
        )

    # All 3 DMA results are required (non-optional)
    if not dma_results.csdma:
        raise ValueError(f"CSDMA result is None: {dma_results.csdma}")
    if not dma_results.dsdma:
        raise ValueError(f"DSDMA result is None: {dma_results.dsdma}")
    if not dma_results.ethical_pdma:
        raise ValueError(f"Ethical PDMA result is None: {dma_results.ethical_pdma}")

    # Extract prompts if available (for debugging/transparency)
    csdma_prompt = getattr(dma_results, "csdma_prompt", None)
    dsdma_prompt = getattr(dma_results, "dsdma_prompt", None)
    pdma_prompt = getattr(dma_results, "ethical_pdma_prompt", None)

    return create_reasoning_event(
        event_type=ReasoningEvent.DMA_RESULTS,
        thought_id=step_data.thought_id,
        task_id=step_data.task_id,
        timestamp=timestamp,
        csdma=dma_results.csdma,  # Pass CSDMAResult object directly
        dsdma=dma_results.dsdma,  # Pass DSDMAResult object directly
        pdma=dma_results.ethical_pdma,  # Pass EthicalDMAResult object directly
        csdma_prompt=csdma_prompt,  # User prompt passed to CSDMA
        dsdma_prompt=dsdma_prompt,  # User prompt passed to DSDMA
        pdma_prompt=pdma_prompt,  # User prompt passed to PDMA
    )


def _create_aspdma_result_event(
    step_data: StepDataUnion, timestamp: str, is_recursive: bool, create_reasoning_event: Any
) -> Any:
    """Create ASPDMA_RESULT reasoning event."""
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent

    # Extract ASPDMA prompt if available (from ConscienceExecutionStepData)
    aspdma_prompt = getattr(step_data, "aspdma_prompt", None)

    return create_reasoning_event(
        event_type=ReasoningEvent.ASPDMA_RESULT,
        thought_id=step_data.thought_id,
        task_id=step_data.task_id,
        timestamp=timestamp,
        is_recursive=is_recursive,
        selected_action=getattr(step_data, "selected_action", ""),
        action_rationale=getattr(step_data, "action_rationale", ""),
        aspdma_prompt=aspdma_prompt,  # User prompt passed to ASPDMA
    )


def _create_conscience_result_event(step_data: StepDataUnion, timestamp: str, create_reasoning_event: Any) -> Any:
    """Create CONSCIENCE_RESULT reasoning event."""
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent

    return create_reasoning_event(
        event_type=ReasoningEvent.CONSCIENCE_RESULT,
        thought_id=step_data.thought_id,
        task_id=step_data.task_id,
        timestamp=timestamp,
        is_recursive=False,  # FINALIZE_ACTION is never recursive
        conscience_passed=getattr(step_data, "conscience_passed", True),
        conscience_override_reason=getattr(step_data, "conscience_override_reason", None),
        epistemic_data=getattr(step_data, "epistemic_data", {}),
        final_action=getattr(step_data, "selected_action", ""),
        action_was_overridden=not getattr(step_data, "conscience_passed", True),
        updated_status_available=getattr(step_data, "updated_status_detected", None),
    )


def _create_action_result_event(step_data: StepDataUnion, timestamp: str, create_reasoning_event: Any) -> Any:
    """Create ACTION_RESULT reasoning event with audit trail, resource usage, and follow-up data."""
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent

    # Extract follow_up_thought_id from step_data (already populated from dispatch_result)
    follow_up_thought_id = getattr(step_data, "follow_up_thought_id", None)

    return create_reasoning_event(
        event_type=ReasoningEvent.ACTION_RESULT,
        thought_id=step_data.thought_id,
        task_id=step_data.task_id,
        timestamp=timestamp,
        action_executed=getattr(step_data, "action_executed", ""),
        execution_success=getattr(step_data, "dispatch_success", True),
        execution_time_ms=getattr(step_data, "execution_time_ms", 0.0),
        follow_up_thought_id=follow_up_thought_id,
        error=None,
        audit_entry_id=getattr(step_data, "audit_entry_id", None),
        audit_sequence_number=getattr(step_data, "audit_sequence_number", None),
        audit_entry_hash=getattr(step_data, "audit_entry_hash", None),
        audit_signature=getattr(step_data, "audit_signature", None),
        # Resource usage fields (queried from telemetry by thought_id)
        tokens_total=getattr(step_data, "tokens_total", 0),
        tokens_input=getattr(step_data, "tokens_input", 0),
        tokens_output=getattr(step_data, "tokens_output", 0),
        cost_cents=getattr(step_data, "cost_cents", 0.0),
        carbon_grams=getattr(step_data, "carbon_grams", 0.0),
        energy_mwh=getattr(step_data, "energy_mwh", 0.0),
        llm_calls=getattr(step_data, "llm_calls", 0),
        models_used=getattr(step_data, "models_used", []),
    )


def _build_span_attributes_dict(step: StepPoint, step_result: Any, step_data: StepDataUnion) -> List[SpanAttribute]:
    """
    Build span attributes compatible with OTLP format.

    This creates rich attribute data that's consistent between streaming and OTLP traces.
    """
    thought_id = step_data.thought_id
    task_id = step_data.task_id

    # Start with core CIRIS attributes (matching OTLP format)
    attributes = [
        SpanAttribute(key="ciris.step_point", value={"stringValue": step.value}),
        SpanAttribute(key="ciris.thought_id", value={"stringValue": thought_id}),
        SpanAttribute(key="operation.name", value={"stringValue": f"H3ERE.{step.value}"}),
        SpanAttribute(key="service.name", value={"stringValue": "ciris-h3ere-pipeline"}),
        SpanAttribute(key="service.component", value={"stringValue": "thought_processor"}),
        SpanAttribute(key="span.success", value={"boolValue": step_data.success}),
        SpanAttribute(key="processing_time_ms", value={"doubleValue": step_data.processing_time_ms}),
    ]

    # Add task_id if available - critical for correlation
    if task_id:
        attributes.append(SpanAttribute(key="ciris.task_id", value={"stringValue": str(task_id)}))

    # Add step-specific attributes based on the typed step result
    if step_result and hasattr(step_result, "model_dump"):
        result_data = step_result.model_dump()
        _add_typed_step_attributes(attributes, step, result_data)

    # Add error information if present
    error = step_data.error
    if error:
        attributes.extend(
            [
                SpanAttribute(key="error", value={"boolValue": True}),
                SpanAttribute(key="error.message", value={"stringValue": str(error)}),
                SpanAttribute(key="error.type", value={"stringValue": "ProcessingError"}),
            ]
        )
    else:
        attributes.append(SpanAttribute(key="error", value={"boolValue": False}))

    return attributes


def _add_gather_context_attributes(attributes: List[SpanAttribute], result_data: JSONDict) -> None:  # NOQA
    """Add attributes specific to GATHER_CONTEXT step."""
    if "context" in result_data and result_data["context"]:
        context_size = len(str(result_data["context"]))
        attributes.extend(
            [
                SpanAttribute(key="context.size_bytes", value={"intValue": context_size}),
                SpanAttribute(key="context.available", value={"boolValue": True}),
            ]
        )


def _add_perform_dmas_attributes(attributes: List[SpanAttribute], result_data: JSONDict) -> None:  # NOQA
    """Add attributes specific to PERFORM_DMAS step."""
    if "dma_results" in result_data and result_data["dma_results"]:
        attributes.extend(
            [
                SpanAttribute(key="dma.results_available", value={"boolValue": True}),
                SpanAttribute(key="dma.results_size", value={"intValue": len(str(result_data["dma_results"]))}),
            ]
        )
    if "context" in result_data:
        attributes.append(SpanAttribute(key="dma.context_provided", value={"boolValue": bool(result_data["context"])}))


def _add_perform_aspdma_attributes(attributes: List[SpanAttribute], result_data: JSONDict) -> None:  # NOQA
    """Add attributes specific to PERFORM_ASPDMA step."""
    if "selected_action" in result_data:
        attributes.append(
            SpanAttribute(key="action.selected", value={"stringValue": str(result_data["selected_action"])})
        )
    if "action_rationale" in result_data:
        attributes.append(
            SpanAttribute(key="action.has_rationale", value={"boolValue": bool(result_data["action_rationale"])})
        )


def _add_conscience_execution_attributes(attributes: List[SpanAttribute], result_data: JSONDict) -> None:  # NOQA
    """Add attributes specific to CONSCIENCE_EXECUTION step."""
    if "conscience_passed" in result_data:
        attributes.append(SpanAttribute(key="conscience.passed", value={"boolValue": result_data["conscience_passed"]}))
    if "selected_action" in result_data:
        attributes.append(
            SpanAttribute(key="conscience.action", value={"stringValue": str(result_data["selected_action"])})
        )


def _add_finalize_action_attributes(attributes: List[SpanAttribute], result_data: JSONDict) -> None:  # NOQA
    """Add attributes specific to FINALIZE_ACTION step."""
    if "selected_action" in result_data:
        attributes.append(
            SpanAttribute(key="finalized.action", value={"stringValue": str(result_data["selected_action"])})
        )
    if "selection_reasoning" in result_data:
        attributes.append(
            SpanAttribute(key="finalized.has_reasoning", value={"boolValue": bool(result_data["selection_reasoning"])})
        )


def _add_perform_action_attributes(attributes: List[SpanAttribute], result_data: JSONDict) -> None:  # NOQA
    """Add attributes specific to PERFORM_ACTION step."""
    if "action_executed" in result_data:
        attributes.append(
            SpanAttribute(key="action.executed", value={"stringValue": str(result_data["action_executed"])})
        )
    if "dispatch_success" in result_data:
        attributes.append(
            SpanAttribute(key="action.dispatch_success", value={"boolValue": result_data["dispatch_success"]})
        )


def _add_action_complete_attributes(attributes: List[SpanAttribute], result_data: JSONDict) -> None:  # NOQA
    """Add attributes specific to ACTION_COMPLETE step."""
    if "handler_completed" in result_data:
        attributes.append(
            SpanAttribute(key="action.handler_completed", value={"boolValue": result_data["handler_completed"]})
        )
    if "execution_time_ms" in result_data:
        attributes.append(
            SpanAttribute(key="action.execution_time_ms", value={"doubleValue": result_data["execution_time_ms"]})
        )


def _add_typed_step_attributes(attributes: List[SpanAttribute], step: StepPoint, result_data: JSONDict) -> None:  # NOQA
    """Add step-specific attributes based on typed step result data."""

    # Map step types to their handler functions
    step_attribute_handlers = {
        StepPoint.GATHER_CONTEXT: _add_gather_context_attributes,
        StepPoint.PERFORM_DMAS: _add_perform_dmas_attributes,
        StepPoint.PERFORM_ASPDMA: _add_perform_aspdma_attributes,
        StepPoint.CONSCIENCE_EXECUTION: _add_conscience_execution_attributes,
        StepPoint.FINALIZE_ACTION: _add_finalize_action_attributes,
        StepPoint.PERFORM_ACTION: _add_perform_action_attributes,
        StepPoint.ACTION_COMPLETE: _add_action_complete_attributes,
    }

    # Call the appropriate handler function if one exists
    handler = step_attribute_handlers.get(step)
    if handler:
        handler(attributes, result_data)
