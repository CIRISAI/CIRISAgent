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
from typing import Any, Callable, Dict, Optional, TypeVar, cast

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
    if step == StepPoint.START_ROUND:
        _add_start_round_data(step_data, args)
    elif step == StepPoint.GATHER_CONTEXT:
        _add_gather_context_data(step_data, result)
    elif step == StepPoint.PERFORM_DMAS:
        _add_perform_dmas_data(step_data, result, thought_item)
    elif step == StepPoint.PERFORM_ASPDMA:
        _add_perform_aspdma_data(step_data, result)
    elif step == StepPoint.CONSCIENCE_EXECUTION:
        _add_conscience_execution_data(step_data, result, args)
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
    step_data["thoughts_processed"] = len(args) if args else 1
    step_data["round_started"] = True


def _add_gather_context_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add GATHER_CONTEXT specific data."""
    step_data["context"] = str(result) if result else None


def _add_perform_dmas_data(step_data: Dict[str, Any], result: Any, thought_item: Any) -> None:
    """Add PERFORM_DMAS specific data."""
    step_data["dma_results"] = str(result) if result else None
    step_data["context"] = str(thought_item.initial_context) if thought_item.initial_context else ""


def _add_perform_aspdma_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add PERFORM_ASPDMA specific data."""
    if hasattr(result, "selected_action"):
        step_data["selected_action"] = str(result.selected_action)
    if hasattr(result, "rationale"):
        step_data["action_rationale"] = str(result.rationale)


def _add_conscience_execution_data(step_data: Dict[str, Any], result: Any, args: tuple) -> None:
    """Add CONSCIENCE_EXECUTION specific data."""
    step_data["selected_action"] = str(getattr(result, "selected_action", args[0] if args else "UNKNOWN"))
    step_data["conscience_passed"] = getattr(result, "conscience_passed", True)


def _add_recursive_aspdma_data(step_data: Dict[str, Any], result: Any, args: tuple) -> None:
    """Add RECURSIVE_ASPDMA specific data."""
    step_data["retry_reason"] = str(args[0]) if args else "retry_required"
    step_data["original_action"] = str(getattr(result, "selected_action", "UNKNOWN"))


def _add_recursive_conscience_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add RECURSIVE_CONSCIENCE specific data."""
    step_data["retry_action"] = str(getattr(result, "selected_action", "UNKNOWN"))
    step_data["retry_result"] = str(result) if result else None


def _add_finalize_action_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add FINALIZE_ACTION specific data."""
    step_data["selected_action"] = str(getattr(result, "selected_action", "UNKNOWN"))
    step_data["selection_reasoning"] = getattr(result, "rationale", "")
    step_data["conscience_passed"] = True  # If we reach here, conscience passed


def _add_perform_action_data(step_data: Dict[str, Any], result: Any, args: tuple, kwargs: dict) -> None:
    """Add PERFORM_ACTION specific data."""
    step_data["selected_action"] = str(getattr(result, "selected_action", args[0] if args else "UNKNOWN"))
    step_data["action_parameters"] = str(getattr(result, "action_parameters", None))
    step_data["dispatch_context"] = str(kwargs.get("context", args[1] if len(args) > 1 else {}))


def _add_action_complete_data(step_data: Dict[str, Any], result: Any) -> None:
    """Add ACTION_COMPLETE specific data."""
    step_data["action_executed"] = str(getattr(result, "selected_action", "UNKNOWN"))
    step_data["dispatch_success"] = getattr(result, "success", True)
    step_data["execution_time_ms"] = getattr(result, "execution_time_ms", 0.0)
    step_data["handler_completed"] = getattr(result, "completed", True)
    step_data["follow_up_processing_pending"] = getattr(result, "has_follow_up", False)


def _add_round_complete_data(step_data: Dict[str, Any], args: tuple) -> None:
    """Add ROUND_COMPLETE specific data."""
    step_data["round_status"] = "completed"
    step_data["thoughts_processed"] = len(args) if args else 1


async def _broadcast_step_result(step: StepPoint, step_data: Dict[str, Any]) -> None:
    """Broadcast step result to global step result stream."""
    try:
        # Import here to avoid circular dependency
        from ciris_engine.logic.infrastructure.step_streaming import step_result_stream
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

        # Create appropriate step result schema
        step_result = None

        if step == StepPoint.START_ROUND:
            step_result = StepResultStartRound(**step_data)
        elif step == StepPoint.GATHER_CONTEXT:
            step_result = StepResultGatherContext(**step_data)
        elif step == StepPoint.PERFORM_DMAS:
            step_result = StepResultPerformDMAs(**step_data)
        elif step == StepPoint.PERFORM_ASPDMA:
            step_result = StepResultPerformASPDMA(**step_data)
        elif step == StepPoint.CONSCIENCE_EXECUTION:
            step_result = StepResultConscienceExecution(**step_data)
        elif step == StepPoint.RECURSIVE_ASPDMA:
            step_result = StepResultRecursiveASPDMA(**step_data)
        elif step == StepPoint.RECURSIVE_CONSCIENCE:
            step_result = StepResultRecursiveConscience(**step_data)
        elif step == StepPoint.FINALIZE_ACTION:
            step_result = StepResultFinalizeAction(**step_data)
        elif step == StepPoint.PERFORM_ACTION:
            step_result = StepResultPerformAction(**step_data)
        elif step == StepPoint.ACTION_COMPLETE:
            step_result = StepResultActionComplete(**step_data)
        elif step == StepPoint.ROUND_COMPLETE:
            step_result = StepResultRoundComplete(**step_data)

        if step_result:
            await step_result_stream.broadcast_step_result(step_result.model_dump())

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
