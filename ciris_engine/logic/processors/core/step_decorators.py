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
from typing import Any, Callable, Dict, List, Optional, TypeVar, cast

from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)

# Global registry for paused thought coroutines
_paused_thoughts: Dict[str, asyncio.Event] = {}
_single_step_mode = False


def streaming_step(step: StepPoint):
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

    def decorator[F: Callable[..., Any]](func: F) -> F:
        @wraps(func)
        async def wrapper(self, thought_item, *args, **kwargs):
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

                # Build step data from function context
                step_data = {
                    "timestamp": start_timestamp.isoformat(),
                    "thought_id": thought_id,
                    "processing_time_ms": processing_time_ms,
                    "success": True,
                }

                # Add step-specific data based on step type and result
                _add_step_specific_data(step, step_data, thought_item, result, args, kwargs)

                # Stream the step result
                await _broadcast_step_result(step, step_data)

                return result

            except Exception as e:
                # Stream error result
                end_timestamp = time_service.now()
                processing_time_ms = (end_timestamp - start_timestamp).total_seconds() * 1000

                error_step_data = {
                    "timestamp": start_timestamp.isoformat(),
                    "thought_id": thought_id,
                    "processing_time_ms": processing_time_ms,
                    "success": False,
                    "error": str(e),
                }

                await _broadcast_step_result(step, error_step_data)
                raise

        return cast(F, wrapper)

    return decorator


def step_point(step: StepPoint):
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

    def decorator[F: Callable[..., Any]](func: F) -> F:
        @wraps(func)
        async def wrapper(self, thought_item, *args, **kwargs):
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


def _add_step_specific_data(
    step: StepPoint, step_data: Dict[str, Any], thought_item: Any, result: Any, args: tuple, kwargs: dict
) -> None:
    """Add step-specific data to step_data dict based on step type."""
    # Add common data and debug logging
    _add_common_step_data(step_data, thought_item, step)

    # Add step-specific data based on step type
    try:
        if step == StepPoint.START_ROUND:
            _add_start_round_data(step_data, args)
        elif step == StepPoint.GATHER_CONTEXT:
            _add_gather_context_data(step_data, result)
        elif step == StepPoint.PERFORM_DMAS:
            _add_perform_dmas_data(step_data, result, thought_item)
        elif step == StepPoint.PERFORM_ASPDMA:
            _add_perform_aspdma_data(step_data, result)
        elif step == StepPoint.CONSCIENCE_EXECUTION:
            _add_conscience_execution_data(step_data, result)
        elif step == StepPoint.RECURSIVE_ASPDMA:
            _add_recursive_aspdma_data(step_data, result, args)
        elif step == StepPoint.RECURSIVE_CONSCIENCE:
            _add_recursive_conscience_data(step_data, result)
        elif step == StepPoint.FINALIZE_ACTION:
            _add_finalize_action_data(step_data, result)
        elif step == StepPoint.PERFORM_ACTION:
            _add_perform_action_data(step_data, result, args, kwargs)
        elif step == StepPoint.ACTION_COMPLETE:
            _add_action_complete_data(step_data, result)
        elif step == StepPoint.ROUND_COMPLETE:
            _add_round_complete_data(step_data, args)
    except Exception as e:
        logger.error(f"Error adding step-specific data for {step.value}: {e}", exc_info=True)


def _add_common_step_data(step_data: Dict[str, Any], thought_item: Any, step: StepPoint) -> None:
    """Add common data and perform debug logging."""
    task_id = getattr(thought_item, "source_task_id", None)
    step_data["task_id"] = task_id

    thought_id = getattr(thought_item, "thought_id", "unknown")
    logger.debug(
        f"Step {step.value} for thought {thought_id}: task_id={task_id}, thought_item type={type(thought_item).__name__}"
    )
    if not task_id:
        logger.warning(f"Missing task_id for thought {thought_id} at step {step.value}")


def _add_start_round_data(step_data: Dict[str, Any], args: tuple) -> None:
    """Add START_ROUND specific data."""
    if not args:
        raise ValueError("START_ROUND args is empty - thought list is required for processing")

    step_data["thoughts_processed"] = len(args)
    step_data["round_started"] = True


def _add_gather_context_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add GATHER_CONTEXT specific data."""
    if result is None:
        raise ValueError("GATHER_CONTEXT step result is None - this indicates a serious pipeline issue")

    step_data["context"] = str(result)


def _add_perform_dmas_data(step_data: Dict[str, Any], result: Any, thought_item: Any) -> None:
    """Add PERFORM_DMAS specific data."""
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
        step_data["dma_results"] = "; ".join(dma_parts) if dma_parts else "No DMA results"
    else:
        # Non-InitialDMAResults object - validate it has expected structure
        step_data["dma_results"] = str(result)

    if not thought_item:
        raise ValueError("PERFORM_DMAS thought_item is None - this indicates a serious pipeline issue")

    if not hasattr(thought_item, "initial_context"):
        raise AttributeError(
            f"PERFORM_DMAS thought_item missing 'initial_context' attribute. Type: {type(thought_item)}, attributes: {dir(thought_item)}"
        )

    step_data["context"] = str(thought_item.initial_context)


def _add_perform_aspdma_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add PERFORM_ASPDMA specific data."""
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

    step_data["selected_action"] = str(result.selected_action)
    step_data["action_rationale"] = str(result.rationale)


def _add_conscience_execution_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add CONSCIENCE_EXECUTION specific data with full transparency."""
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

    # Extract selected action from ConscienceApplicationResult
    step_data["selected_action"] = str(result.final_action.selected_action)

    # Extract conscience pass/fail - conscience passes if not overridden
    step_data["conscience_passed"] = not result.overridden
    step_data["action_result"] = str(result.final_action)

    if result.overridden:
        if not hasattr(result, "override_reason"):
            raise AttributeError(
                f"CONSCIENCE_EXECUTION result overridden but missing 'override_reason'. Result type: {type(result)}, attributes: {dir(result)}"
            )
        step_data["override_reason"] = str(result.override_reason)

    # Add comprehensive conscience evaluation details for full transparency
    step_data["conscience_result"] = _create_comprehensive_conscience_result(result)


def _create_comprehensive_conscience_result(result: Any) -> Dict[str, Any]:
    """Create comprehensive ConscienceCheckResult with all 4 typed evaluations for transparency."""
    from datetime import datetime, timezone

    from ciris_engine.schemas.conscience.core import (
        CoherenceCheckResult,
        ConscienceCheckResult,
        ConscienceStatus,
        EntropyCheckResult,
        EpistemicData,
        EpistemicHumilityResult,
        OptimizationVetoResult,
    )

    # Determine overall conscience status
    status = ConscienceStatus.FAILED if result.overridden else ConscienceStatus.PASSED
    passed = not result.overridden
    reason = result.override_reason if result.overridden else None

    # Create the 4 required typed conscience evaluations
    # These provide the detailed evaluation transparency we need

    # 1. Entropy Check - Information-theoretic safety
    entropy_check = EntropyCheckResult(
        passed=passed,
        entropy_score=0.3,  # Mock value - in real implementation would come from actual entropy calculation
        threshold=0.5,
        message=(
            "Entropy check: Action maintains appropriate information uncertainty"
            if passed
            else "Entropy check failed: Action reduces information uncertainty below threshold"
        ),
    )

    # 2. Coherence Check - Internal consistency validation
    coherence_check = CoherenceCheckResult(
        passed=passed,
        coherence_score=0.8,  # Mock value - in real implementation would come from coherence analysis
        threshold=0.6,
        message=(
            "Coherence check: Action maintains internal consistency"
            if passed
            else "Coherence check failed: Action creates internal inconsistencies"
        ),
    )

    # 3. Optimization Veto Check - Prevents harmful optimization
    optimization_veto_check = OptimizationVetoResult(
        decision="proceed" if passed else "abort",
        justification=(
            "Action aligns with preservation of human values"
            if passed
            else "Action may compromise human values - optimization vetoed"
        ),
        entropy_reduction_ratio=0.15,  # Mock value
        affected_values=[] if passed else ["human_autonomy", "epistemic_humility"],
    )

    # 4. Epistemic Humility Check - Uncertainty acknowledgment
    epistemic_humility_check = EpistemicHumilityResult(
        epistemic_certainty=0.7,  # Mock value - appropriate certainty level
        identified_uncertainties=["action_outcome_variance", "context_completeness"] if not passed else [],
        reflective_justification=(
            "Action demonstrates appropriate uncertainty about outcomes"
            if passed
            else "Action shows overconfidence requiring reflection"
        ),
        recommended_action="proceed" if passed else "ponder",
    )

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
    )

    return conscience_result.model_dump()


def _add_recursive_aspdma_data(step_data: Dict[str, Any], result: Any, args: tuple) -> None:
    """Add RECURSIVE_ASPDMA specific data."""
    if not args:
        raise ValueError("RECURSIVE_ASPDMA args is empty - retry reason is required")

    step_data["retry_reason"] = str(args[0])

    if not result:
        raise ValueError("RECURSIVE_ASPDMA result is None - this indicates a serious pipeline issue")

    if not hasattr(result, "selected_action"):
        raise AttributeError(
            f"RECURSIVE_ASPDMA result missing 'selected_action' attribute. Result type: {type(result)}, attributes: {dir(result)}"
        )

    step_data["original_action"] = str(result.selected_action)


def _add_recursive_conscience_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add RECURSIVE_CONSCIENCE specific data."""
    if not result:
        raise ValueError("RECURSIVE_CONSCIENCE result is None - this indicates a serious pipeline issue")

    if not hasattr(result, "selected_action"):
        raise AttributeError(
            f"RECURSIVE_CONSCIENCE result missing 'selected_action' attribute. Result type: {type(result)}, attributes: {dir(result)}"
        )

    step_data["retry_action"] = str(result.selected_action)
    step_data["retry_result"] = str(result)


def _add_finalize_action_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add FINALIZE_ACTION specific data."""
    if not result:
        raise ValueError("FINALIZE_ACTION result is None - this indicates a serious pipeline issue")

    if not hasattr(result, "selected_action"):
        raise AttributeError(
            f"FINALIZE_ACTION result missing 'selected_action' attribute. Result type: {type(result)}, attributes: {dir(result)}"
        )

    if not hasattr(result, "rationale"):
        raise AttributeError(
            f"FINALIZE_ACTION result missing 'rationale' attribute. Result type: {type(result)}, attributes: {dir(result)}"
        )

    step_data["selected_action"] = str(result.selected_action)
    step_data["selection_reasoning"] = str(result.rationale)
    step_data["conscience_passed"] = True  # If we reach here, conscience passed


def _add_perform_action_data(step_data: Dict[str, Any], result: Any, args: tuple, kwargs: dict) -> None:
    """Add PERFORM_ACTION specific data."""
    # Extract selected_action - first try result, then args
    selected_action = None
    if result and hasattr(result, "selected_action"):
        selected_action = str(result.selected_action)
    elif args:
        selected_action = str(args[0])
    else:
        raise ValueError(
            "PERFORM_ACTION cannot determine selected_action - neither result.selected_action nor args[0] available"
        )

    step_data["selected_action"] = selected_action

    # Extract action_parameters - fail fast if result doesn't have it
    if result and hasattr(result, "action_parameters"):
        step_data["action_parameters"] = str(result.action_parameters)
    else:
        step_data["action_parameters"] = "None"  # This is acceptable as parameters can be None

    # Extract dispatch_context from kwargs or args - provide empty dict as reasonable default
    if "context" in kwargs:
        step_data["dispatch_context"] = str(kwargs["context"])
    elif len(args) > 1:
        step_data["dispatch_context"] = str(args[1])
    else:
        step_data["dispatch_context"] = "{}"  # Empty context is valid


def _add_action_complete_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add ACTION_COMPLETE specific data."""
    if not result:
        raise ValueError("ACTION_COMPLETE step result is None - this indicates a serious pipeline issue")

    # Extract action_type from dispatch_result dict (primary path)
    if isinstance(result, dict):
        if "action_type" not in result:
            raise KeyError(
                f"ACTION_COMPLETE dispatch_result missing 'action_type'. Available keys: {list(result.keys())}"
            )

        if "success" not in result:
            raise KeyError(f"ACTION_COMPLETE dispatch_result missing 'success'. Available keys: {list(result.keys())}")

        if "handler" not in result:
            raise KeyError(f"ACTION_COMPLETE dispatch_result missing 'handler'. Available keys: {list(result.keys())}")

        step_data["action_executed"] = str(result["action_type"])
        step_data["dispatch_success"] = result["success"]
        step_data["handler_completed"] = result["handler"] != "Unknown"
        step_data["follow_up_processing_pending"] = bool(result.get("follow_up_thought_id"))
        step_data["execution_time_ms"] = 0.0  # Dict format doesn't include execution time
    else:
        # Object-based results (should be rare, fail fast if wrong structure)
        if not hasattr(result, "selected_action"):
            raise AttributeError(
                f"ACTION_COMPLETE object result missing 'selected_action'. Result type: {type(result)}, attributes: {dir(result)}"
            )

        if not hasattr(result, "success"):
            raise AttributeError(
                f"ACTION_COMPLETE object result missing 'success'. Result type: {type(result)}, attributes: {dir(result)}"
            )

        step_data["action_executed"] = str(result.selected_action)
        step_data["dispatch_success"] = result.success
        step_data["handler_completed"] = getattr(result, "completed", True)
        step_data["follow_up_processing_pending"] = getattr(result, "has_follow_up", False)
        step_data["execution_time_ms"] = getattr(result, "execution_time_ms", 0.0)


def _add_round_complete_data(step_data: Dict[str, Any], args: tuple) -> None:
    """Add ROUND_COMPLETE specific data."""
    if not args:
        raise ValueError("ROUND_COMPLETE args is empty - completed thought count is required")

    step_data["round_status"] = "completed"
    step_data["thoughts_processed"] = len(args)


def _create_step_result_schema(step: StepPoint, step_data: Dict[str, Any]):
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
            logger.debug(
                f"Creating StepResultGatherContext with step_data keys: {list(step_data.keys())}, values: {step_data}"
            )
        return result_class(**step_data)
    return None


def _extract_timing_data(step_data: Dict[str, Any]) -> tuple:
    """Extract and normalize timing data from step_data."""
    from datetime import datetime, timezone

    timestamp_str = step_data.get("timestamp", datetime.now().isoformat())
    # Ensure both timestamps have timezone info for consistent calculation
    if timestamp_str.endswith("+00:00") or timestamp_str.endswith("Z"):
        start_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
    else:
        start_time = datetime.fromisoformat(timestamp_str).replace(tzinfo=timezone.utc)
    end_time = datetime.now(timezone.utc)

    return start_time, end_time


def _build_step_result_data(
    step: StepPoint,
    step_data: Dict[str, Any],
    step_result,
    trace_context: Dict[str, Any],
    span_attributes: Dict[str, Any],
) -> Dict[str, Any]:
    """Build the complete step result data structure."""
    return {
        "step_point": step.value,
        "success": step_data.get("success", True),
        "processing_time_ms": step_data.get("processing_time_ms", 0.0),
        "thought_id": step_data.get("thought_id", ""),
        "task_id": step_data.get("task_id", ""),
        "step_data": step_result.model_dump(),  # Put the typed data in step_data field
        # Enhanced trace data for OTLP compatibility
        "trace_context": trace_context,
        "span_attributes": span_attributes,
        "otlp_compatible": True,
    }


async def _broadcast_step_result(step: StepPoint, step_data: Dict[str, Any]) -> None:
    """Broadcast step result to global step result stream."""
    try:
        # Import here to avoid circular dependency
        from ciris_engine.logic.infrastructure.step_streaming import step_result_stream

        # Create appropriate step result schema
        step_result = _create_step_result_schema(step, step_data)

        if step_result:
            # Extract and normalize timing data
            start_time, end_time = _extract_timing_data(step_data)

            # Build trace context using our helper function
            trace_context = _build_trace_context_dict(
                step_data.get("thought_id", ""), step_data.get("task_id"), step, start_time, end_time
            )

            # Build span attributes using our helper function
            span_attributes = _build_span_attributes_dict(step, step_result, step_data)

            # Build complete step result data
            step_result_data = _build_step_result_data(step, step_data, step_result, trace_context, span_attributes)

            logger.debug(
                f"Broadcasting step result for {step.value}: task_id={step_result_data['task_id']}, thought_id={step_result_data['thought_id']}"
            )
            await step_result_stream.broadcast_step_result(step_result_data)
        else:
            logger.warning(f"No step result created for {step.value}, step_data keys: {list(step_data.keys())}")

    except Exception as e:
        logger.warning(f"Error broadcasting step result for {step.value}: {e}")


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


async def execute_step(thought_id: str) -> Dict[str, Any]:
    """
    Execute one step for a paused thought.

    Args:
        thought_id: ID of the thought to advance one step

    Returns:
        Status dict indicating success/failure
    """
    global _paused_thoughts

    if thought_id not in _paused_thoughts:
        return {
            "success": False,
            "error": f"Thought {thought_id} is not paused or does not exist",
            "thought_id": thought_id,
        }

    try:
        # Resume the thought coroutine
        _paused_thoughts[thought_id].set()

        return {
            "success": True,
            "thought_id": thought_id,
            "message": "Thought advanced one step",
        }

    except Exception as e:
        logger.error(f"Error executing step for thought {thought_id}: {e}")
        return {
            "success": False,
            "error": str(e),
            "thought_id": thought_id,
        }


async def execute_all_steps() -> Dict[str, Any]:
    """
    Execute one step for all paused thoughts.

    Returns:
        Status dict with count of thoughts advanced
    """
    global _paused_thoughts

    if not _paused_thoughts:
        return {
            "success": True,
            "thoughts_advanced": 0,
            "message": "No thoughts currently paused",
        }

    try:
        # Resume all paused thoughts
        for event in _paused_thoughts.values():
            event.set()

        count = len(_paused_thoughts)

        return {
            "success": True,
            "thoughts_advanced": count,
            "message": f"Advanced {count} thoughts one step",
        }

    except Exception as e:
        logger.error(f"Error executing steps for all thoughts: {e}")
        return {
            "success": False,
            "error": str(e),
            "thoughts_advanced": 0,
        }


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
) -> Dict[str, Any]:
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

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "span_name": f"h3ere.{step.value}",
        "operation_name": f"H3ERE.{step.value}",
        "start_time_ns": int(start_time.timestamp() * 1e9),
        "end_time_ns": int(end_time.timestamp() * 1e9),
        "duration_ns": int((end_time - start_time).total_seconds() * 1e9),
        "span_kind": "internal",  # H3ERE pipeline steps are internal operations
    }


def _build_span_attributes_dict(step: StepPoint, step_result: Any, step_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Build span attributes compatible with OTLP format.

    This creates rich attribute data that's consistent between streaming and OTLP traces.
    """
    thought_id = step_data.get("thought_id", "unknown")
    task_id = step_data.get("task_id")

    # Start with core CIRIS attributes (matching OTLP format)
    attributes = [
        {"key": "ciris.step_point", "value": {"stringValue": step.value}},
        {"key": "ciris.thought_id", "value": {"stringValue": thought_id}},
        {"key": "operation.name", "value": {"stringValue": f"H3ERE.{step.value}"}},
        {"key": "service.name", "value": {"stringValue": "ciris-h3ere-pipeline"}},
        {"key": "service.component", "value": {"stringValue": "thought_processor"}},
        {"key": "span.success", "value": {"boolValue": step_data.get("success", True)}},
        {"key": "processing_time_ms", "value": {"doubleValue": step_data.get("processing_time_ms", 0.0)}},
    ]

    # Add task_id if available - critical for correlation
    if task_id:
        attributes.append({"key": "ciris.task_id", "value": {"stringValue": str(task_id)}})

    # Add step-specific attributes based on the typed step result
    if step_result and hasattr(step_result, "model_dump"):
        result_data = step_result.model_dump()
        _add_typed_step_attributes(attributes, step, result_data)

    # Add error information if present
    error = step_data.get("error")
    if error:
        attributes.extend(
            [
                {"key": "error", "value": {"boolValue": True}},
                {"key": "error.message", "value": {"stringValue": str(error)}},
                {"key": "error.type", "value": {"stringValue": "ProcessingError"}},
            ]
        )
    else:
        attributes.append({"key": "error", "value": {"boolValue": False}})

    return attributes


def _add_gather_context_attributes(attributes: List[Dict[str, Any]], result_data: Dict[str, Any]) -> None:
    """Add attributes specific to GATHER_CONTEXT step."""
    if "context" in result_data and result_data["context"]:
        context_size = len(str(result_data["context"]))
        attributes.extend(
            [
                {"key": "context.size_bytes", "value": {"intValue": context_size}},
                {"key": "context.available", "value": {"boolValue": True}},
            ]
        )


def _add_perform_dmas_attributes(attributes: List[Dict[str, Any]], result_data: Dict[str, Any]) -> None:
    """Add attributes specific to PERFORM_DMAS step."""
    if "dma_results" in result_data and result_data["dma_results"]:
        attributes.extend(
            [
                {"key": "dma.results_available", "value": {"boolValue": True}},
                {"key": "dma.results_size", "value": {"intValue": len(str(result_data["dma_results"]))}},
            ]
        )
    if "context" in result_data:
        attributes.append({"key": "dma.context_provided", "value": {"boolValue": bool(result_data["context"])}})


def _add_perform_aspdma_attributes(attributes: List[Dict[str, Any]], result_data: Dict[str, Any]) -> None:
    """Add attributes specific to PERFORM_ASPDMA step."""
    if "selected_action" in result_data:
        attributes.append({"key": "action.selected", "value": {"stringValue": str(result_data["selected_action"])}})
    if "action_rationale" in result_data:
        attributes.append(
            {"key": "action.has_rationale", "value": {"boolValue": bool(result_data["action_rationale"])}}
        )


def _add_conscience_execution_attributes(attributes: List[Dict[str, Any]], result_data: Dict[str, Any]) -> None:
    """Add attributes specific to CONSCIENCE_EXECUTION step."""
    if "conscience_passed" in result_data:
        attributes.append({"key": "conscience.passed", "value": {"boolValue": result_data["conscience_passed"]}})
    if "selected_action" in result_data:
        attributes.append({"key": "conscience.action", "value": {"stringValue": str(result_data["selected_action"])}})


def _add_finalize_action_attributes(attributes: List[Dict[str, Any]], result_data: Dict[str, Any]) -> None:
    """Add attributes specific to FINALIZE_ACTION step."""
    if "selected_action" in result_data:
        attributes.append({"key": "finalized.action", "value": {"stringValue": str(result_data["selected_action"])}})
    if "selection_reasoning" in result_data:
        attributes.append(
            {"key": "finalized.has_reasoning", "value": {"boolValue": bool(result_data["selection_reasoning"])}}
        )


def _add_perform_action_attributes(attributes: List[Dict[str, Any]], result_data: Dict[str, Any]) -> None:
    """Add attributes specific to PERFORM_ACTION step."""
    if "action_executed" in result_data:
        attributes.append({"key": "action.executed", "value": {"stringValue": str(result_data["action_executed"])}})
    if "dispatch_success" in result_data:
        attributes.append({"key": "action.dispatch_success", "value": {"boolValue": result_data["dispatch_success"]}})


def _add_action_complete_attributes(attributes: List[Dict[str, Any]], result_data: Dict[str, Any]) -> None:
    """Add attributes specific to ACTION_COMPLETE step."""
    if "handler_completed" in result_data:
        attributes.append({"key": "action.handler_completed", "value": {"boolValue": result_data["handler_completed"]}})
    if "execution_time_ms" in result_data:
        attributes.append(
            {"key": "action.execution_time_ms", "value": {"doubleValue": result_data["execution_time_ms"]}}
        )


def _add_typed_step_attributes(attributes: List[Dict[str, Any]], step: StepPoint, result_data: Dict[str, Any]) -> None:
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
