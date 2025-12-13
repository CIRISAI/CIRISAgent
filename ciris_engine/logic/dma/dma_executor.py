import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, AsyncGenerator, Awaitable, Callable, Dict, Optional, Union

# Python 3.10 compatibility: asyncio.timeout was added in Python 3.11
if sys.version_info >= (3, 11):
    _async_timeout = asyncio.timeout
else:

    @asynccontextmanager
    async def _async_timeout(delay: float) -> AsyncGenerator[None, None]:
        """Python 3.10 compatible timeout context manager."""
        loop = asyncio.get_event_loop()
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("No current task")

        timed_out = False

        def timeout_callback() -> None:
            nonlocal timed_out
            timed_out = True
            task.cancel()  # type: ignore[union-attr]

        handle = loop.call_later(delay, timeout_callback)
        try:
            yield
        except asyncio.CancelledError:
            handle.cancel()
            if timed_out:
                raise asyncio.TimeoutError() from None
            else:
                raise  # Re-raise CancelledError if not from timeout
        else:
            handle.cancel()


from ciris_engine.logic import persistence
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.support.thought_escalation import escalate_dma_failure
from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.system_context import ThoughtState
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)
from ciris_engine.schemas.types import JSONDict

from .action_selection_pdma import ActionSelectionPDMAEvaluator
from .csdma import CSDMAEvaluator
from .dsdma_base import BaseDSDMA
from .exceptions import DMAFailure
from .pdma import EthicalPDMAEvaluator

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

DMA_RETRY_LIMIT = 3


async def run_dma_with_retries(
    run_fn: Callable[..., Awaitable[Any]],
    *args: Any,
    retry_limit: int = DMA_RETRY_LIMIT,
    timeout_seconds: float = 30.0,
    time_service: Optional["TimeServiceProtocol"] = None,
    **kwargs: Any,
) -> Any:
    """Run a DMA function with retry logic."""
    attempt = 0
    last_error: Optional[Exception] = None
    while attempt < retry_limit:
        try:
            async with _async_timeout(timeout_seconds):
                # Pass time_service if the function expects it
                if time_service and "time_service" not in kwargs:
                    kwargs["time_service"] = time_service
                return await run_fn(*args, **kwargs)
        except TimeoutError as e:
            last_error = e
            attempt += 1
            logger.error("DMA %s timed out after %.1f seconds on attempt %s", run_fn.__name__, timeout_seconds, attempt)
        except Exception as e:  # noqa: BLE001
            last_error = e
            attempt += 1
            # Only log full details on first failure
            if attempt == 1:
                logger.warning(
                    "DMA %s attempt %s failed: %s", run_fn.__name__, attempt, str(e).replace("\n", " ")[:200]
                )
            elif attempt == retry_limit:
                logger.warning(
                    "DMA %s final attempt %s failed (same error repeated %s times)",
                    run_fn.__name__,
                    attempt,
                    attempt - 1,
                )

            # Add small delay between retries to reduce log spam
            if attempt < retry_limit:
                await asyncio.sleep(0.1)  # 100ms delay

    thought_arg = next(
        (arg for arg in args if isinstance(arg, (Thought, ProcessingQueueItem))),
        None,
    )

    if thought_arg is not None and last_error is not None and time_service is not None:
        escalate_dma_failure(thought_arg, run_fn.__name__, last_error, retry_limit, time_service)

    raise DMAFailure(f"{run_fn.__name__} failed after {retry_limit} attempts: {last_error}")


async def run_pdma(
    evaluator: EthicalPDMAEvaluator,
    thought: ProcessingQueueItem,
    context: Optional[ThoughtState] = None,
    time_service: Optional["TimeServiceProtocol"] = None,
) -> EthicalDMAResult:
    """Run the Ethical PDMA for the given thought."""
    logger.debug(f"[DEBUG TIMING] run_pdma START for thought {thought.thought_id}")
    if not time_service:
        raise RuntimeError("TimeService is required for DMA execution")
    start_time = time_service.now()

    # Create trace for PDMA execution
    trace_id = f"task_{thought.source_task_id or 'unknown'}_{thought.thought_id}"
    span_id = f"pdma_{thought.thought_id}"
    parent_span_id = f"thought_processor_{thought.thought_id}"

    trace_context = TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        span_name="run_ethical_pdma",
        span_kind="internal",
        baggage={"thought_id": thought.thought_id, "task_id": thought.source_task_id or "", "dma_type": "ethical_pdma"},
    )

    correlation = ServiceCorrelation(
        correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
        correlation_type=CorrelationType.TRACE_SPAN,
        service_type="dma",
        handler_name="EthicalPDMAEvaluator",
        action_type="evaluate",
        created_at=start_time,
        updated_at=start_time,
        timestamp=start_time,
        trace_context=trace_context,
        tags={
            "thought_id": thought.thought_id,
            "task_id": thought.source_task_id or "",
            "component_type": "dma",
            "dma_type": "ethical_pdma",
            "trace_depth": "3",
        },
        request_data=None,
        response_data=None,
        status=ServiceCorrelationStatus.PENDING,
        metric_data=None,
        log_data=None,
        retention_policy="raw",
        ttl_seconds=None,
        parent_correlation_id=None,
    )

    # Add correlation
    if time_service:
        persistence.add_correlation(correlation, time_service)

    try:
        ctx = context
        if ctx is None:
            context_data = getattr(thought, "context", None)
            if context_data is None:
                context_data = getattr(thought, "initial_context", None)

            if context_data is None:
                raise DMAFailure(f"No context available for thought {thought.thought_id}")

            if isinstance(context_data, ThoughtState):
                ctx = context_data
            elif isinstance(context_data, dict):
                try:
                    ctx = ThoughtState.model_validate(context_data)
                except Exception as e:  # noqa: BLE001
                    raise DMAFailure(f"Invalid context for thought {thought.thought_id}: {e}") from e
            else:
                raise DMAFailure(f"Unsupported context type {type(context_data)} for thought {thought.thought_id}")

        logger.debug(f"[DEBUG TIMING] About to call evaluator.evaluate for PDMA on thought {thought.thought_id}")
        result = await evaluator.evaluate(thought, context=ctx)

        # Update correlation with success
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": f"Ethical evaluation completed: stakeholders={result.stakeholders}, conflicts={result.conflicts}",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)

        return result

    except Exception as e:
        # Update correlation with failure
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "error_message": str(e),
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)
        raise


async def run_csdma(
    evaluator: CSDMAEvaluator,
    thought: ProcessingQueueItem,
    context: Optional[Any] = None,  # Accept Any - CSDMA handles its own context internally
    time_service: Optional["TimeServiceProtocol"] = None,
) -> CSDMAResult:
    """Run the CSDMA for the given thought."""
    if not time_service:
        raise RuntimeError("TimeService is required for DMA execution")
    start_time = time_service.now()

    # Create trace for CSDMA execution
    trace_id = f"task_{thought.source_task_id or 'unknown'}_{thought.thought_id}"
    span_id = f"csdma_{thought.thought_id}"
    parent_span_id = f"thought_processor_{thought.thought_id}"

    trace_context = TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        span_name="run_csdma",
        span_kind="internal",
        baggage={"thought_id": thought.thought_id, "task_id": thought.source_task_id or "", "dma_type": "csdma"},
    )

    correlation = ServiceCorrelation(
        correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
        correlation_type=CorrelationType.TRACE_SPAN,
        service_type="dma",
        handler_name="CSDMAEvaluator",
        action_type="evaluate_thought",
        created_at=start_time,
        updated_at=start_time,
        timestamp=start_time,
        trace_context=trace_context,
        tags={
            "thought_id": thought.thought_id,
            "task_id": thought.source_task_id or "",
            "component_type": "dma",
            "dma_type": "csdma",
            "trace_depth": "3",
        },
        request_data=None,
        response_data=None,
        status=ServiceCorrelationStatus.PENDING,
        metric_data=None,
        log_data=None,
        retention_policy="raw",
        ttl_seconds=None,
        parent_correlation_id=None,
    )

    # Add correlation
    if time_service:
        persistence.add_correlation(correlation, time_service)

    try:
        # Pass context through to CSDMA evaluate() - it handles its own context internally
        result = await evaluator.evaluate(thought, context=context)

        # Update correlation with success
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": "CSDMA evaluation completed",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)

        return result

    except Exception as e:
        # Update correlation with failure
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "error_message": str(e),
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)
        raise


async def run_dsdma(
    dsdma: BaseDSDMA,
    thought: ProcessingQueueItem,
    context: Optional[JSONDict] = None,
    time_service: Optional["TimeServiceProtocol"] = None,
) -> DSDMAResult:
    """Run the domain-specific DMA using profile-driven configuration."""
    if not time_service:
        raise RuntimeError("TimeService is required for DMA execution")
    start_time = time_service.now()

    # Create trace for DSDMA execution
    trace_id = f"task_{thought.source_task_id or 'unknown'}_{thought.thought_id}"
    span_id = f"dsdma_{thought.thought_id}"
    parent_span_id = f"thought_processor_{thought.thought_id}"

    trace_context = TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        span_name="run_dsdma",
        span_kind="internal",
        baggage={"thought_id": thought.thought_id, "task_id": thought.source_task_id or "", "dma_type": "dsdma"},
    )

    correlation = ServiceCorrelation(
        correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
        correlation_type=CorrelationType.TRACE_SPAN,
        service_type="dma",
        handler_name="BaseDSDMA",
        action_type="evaluate",
        created_at=start_time,
        updated_at=start_time,
        timestamp=start_time,
        trace_context=trace_context,
        tags={
            "thought_id": thought.thought_id,
            "task_id": thought.source_task_id or "",
            "component_type": "dma",
            "dma_type": "dsdma",
            "trace_depth": "3",
        },
        request_data=None,
        response_data=None,
        status=ServiceCorrelationStatus.PENDING,
        metric_data=None,
        log_data=None,
        retention_policy="raw",
        ttl_seconds=None,
        parent_correlation_id=None,
    )

    # Add correlation
    if time_service:
        persistence.add_correlation(correlation, time_service)

    try:
        # Use evaluate method which handles JSONDict to DMAInputData conversion
        result = await dsdma.evaluate(thought, current_context=context)

        # Update correlation with success
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": "DSDMA evaluation completed",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)

        return result

    except Exception as e:
        # Update correlation with failure
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "error_message": str(e),
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)
        raise


async def run_action_selection_pdma(
    evaluator: ActionSelectionPDMAEvaluator,
    triaged_inputs: Union[JSONDict, EnhancedDMAInputs],
    time_service: Optional["TimeServiceProtocol"] = None,
) -> ActionSelectionDMAResult:
    """Select the next handler action using the triaged DMA results."""

    if not time_service:
        raise RuntimeError("TimeService is required for DMA execution")
    start_time = time_service.now()

    # Handle both dict and EnhancedDMAInputs
    if isinstance(triaged_inputs, EnhancedDMAInputs):
        original_thought = triaged_inputs.original_thought
    else:
        original_thought = triaged_inputs.get("original_thought", {})

    thought_id = original_thought.thought_id if hasattr(original_thought, "thought_id") else "unknown"
    task_id = original_thought.source_task_id if hasattr(original_thought, "source_task_id") else "unknown"

    logger.debug(f"run_action_selection_pdma: Starting evaluation for thought {thought_id}")

    # Create trace for action selection PDMA execution
    trace_id = f"task_{task_id}_{thought_id}"
    span_id = f"action_selection_pdma_{thought_id}"
    parent_span_id = f"thought_processor_{thought_id}"

    trace_context = TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        parent_span_id=parent_span_id,
        span_name="run_action_selection_pdma",
        span_kind="internal",
        baggage={"thought_id": thought_id, "task_id": task_id, "dma_type": "action_selection_pdma"},
    )

    correlation = ServiceCorrelation(
        correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
        correlation_type=CorrelationType.TRACE_SPAN,
        service_type="dma",
        handler_name="ActionSelectionPDMAEvaluator",
        action_type="evaluate",
        created_at=start_time,
        updated_at=start_time,
        timestamp=start_time,
        trace_context=trace_context,
        tags={
            "thought_id": thought_id,
            "task_id": task_id,
            "component_type": "dma",
            "dma_type": "action_selection_pdma",
            "trace_depth": "3",
        },
        request_data=None,
        response_data=None,
        status=ServiceCorrelationStatus.PENDING,
        metric_data=None,
        log_data=None,
        retention_policy="raw",
        ttl_seconds=None,
        parent_correlation_id=None,
    )

    # Add correlation
    if time_service:
        persistence.add_correlation(correlation, time_service)

    try:
        # Handle both dict and EnhancedDMAInputs
        if isinstance(triaged_inputs, EnhancedDMAInputs):
            enhanced_inputs = triaged_inputs
        else:
            # Convert dict to EnhancedDMAInputs
            enhanced_inputs = EnhancedDMAInputs(
                original_thought=triaged_inputs["original_thought"],
                ethical_pdma_result=triaged_inputs["ethical_pdma_result"],
                csdma_result=triaged_inputs["csdma_result"],
                dsdma_result=triaged_inputs.get("dsdma_result"),
                current_thought_depth=triaged_inputs["current_thought_depth"],
                max_rounds=triaged_inputs["max_rounds"],
                processing_context=triaged_inputs.get("processing_context"),
                permitted_actions=triaged_inputs.get("permitted_actions", []),
                agent_identity=triaged_inputs.get("agent_identity", {}),
                faculty_evaluations=triaged_inputs.get("faculty_evaluations"),
                faculty_enhanced=triaged_inputs.get("faculty_enhanced", False),
                recursive_evaluation=triaged_inputs.get("recursive_evaluation", False),
                conscience_feedback=triaged_inputs.get("conscience_feedback"),
                images=triaged_inputs.get("images", []),  # Pass through images for vision
            )

        result = await evaluator.evaluate(enhanced_inputs)

        logger.debug(f"run_action_selection_pdma: Evaluation completed. Result type: {type(result)}, Result: {result}")
        if hasattr(result, "selected_action"):
            logger.debug(f"run_action_selection_pdma: Selected action: {result.selected_action}")
            if result.selected_action == HandlerActionType.OBSERVE:
                logger.debug("OBSERVE ACTION: run_action_selection_pdma returning OBSERVE action successfully")

        # Update correlation with success
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": f"Action selected: {result.selected_action if result and hasattr(result, 'selected_action') else 'none'}",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)

        return result

    except Exception as e:
        # Update correlation with failure
        if time_service:
            end_time = time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "error_message": str(e),
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
                metric_value=None,
                tags=None,
            )
            persistence.update_correlation(update_req, time_service)
        raise
