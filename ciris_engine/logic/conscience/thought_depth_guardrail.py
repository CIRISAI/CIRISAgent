"""
Thought depth conscience that enforces maximum action chain length.

When a thought reaches the maximum allowed depth, this conscience
overrides the action to DEFER, ensuring proper escalation to humans.
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus, EpistemicData
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.actions import DeferParams
from ciris_engine.logic.conscience.interface import ConscienceInterface
# TODO: Refactor to use dependency injection instead of get_config
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.logic import persistence
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, CorrelationType, TraceContext, ServiceCorrelationStatus
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest

logger = logging.getLogger(__name__)

class ThoughtDepthGuardrail(ConscienceInterface):
    """Enforces maximum thought depth by deferring when limit is reached."""

    def __init__(self, time_service: TimeServiceProtocol, max_depth: Optional[int] = None):
        """Initialize with time service and configurable max depth."""
        self._time_service = time_service
        if max_depth is None:
            try:
                # Default to 20 if config not available
                max_depth = 20
            except Exception:
                max_depth = 7
        self.max_depth = max_depth
        logger.info(f"ThoughtDepthconscience initialized with max_depth={self.max_depth}")

    async def check(
        self,
        action: ActionSelectionDMAResult,
        context: dict,
    ) -> ConscienceCheckResult:
        """Check if thought depth exceeds maximum allowed."""
        start_time = self._time_service.now()
        timestamp = self._time_service.now()

        # Get the thought from context
        thought = context.get("thought")
        thought_id = thought.thought_id if thought and hasattr(thought, 'thought_id') else 'unknown'
        task_id = thought.source_task_id if thought and hasattr(thought, 'source_task_id') else 'unknown'
        
        # Create trace for guardrail execution
        trace_id = f"task_{task_id}_{thought_id}"
        span_id = f"thought_depth_guardrail_{thought_id}"
        parent_span_id = f"thought_processor_{thought_id}"
        
        trace_context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_name="thought_depth_guardrail_check",
            span_kind="internal",
            baggage={
                "thought_id": thought_id,
                "task_id": task_id,
                "guardrail_type": "thought_depth",
                "max_depth": str(self.max_depth)
            }
        )
        
        correlation = ServiceCorrelation(
            correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
            correlation_type=CorrelationType.TRACE_SPAN,
            service_type="guardrail",
            handler_name="ThoughtDepthGuardrail",
            action_type="check",
            created_at=start_time,
            updated_at=start_time,
            timestamp=start_time,
            trace_context=trace_context,
            tags={
                "thought_id": thought_id,
                "task_id": task_id,
                "component_type": "guardrail",
                "guardrail_type": "thought_depth",
                "trace_depth": "4"
            }
        )
        
        # Add correlation
        persistence.add_correlation(correlation, self._time_service)
        if not thought:
            logger.warning("No thought provided to ThoughtDepthconscience")
            # Update correlation with completion
            end_time = self._time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": "No thought provided to check",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat()
                },
                status=ServiceCorrelationStatus.COMPLETED
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=timestamp,
                epistemic_data=EpistemicData(
                    entropy_level=0.5,
                    coherence_level=0.5,
                    uncertainty_acknowledged=True,
                    reasoning_transparency=0.0
                ),
                reason="No thought provided to check"
            )

        current_depth = getattr(thought, "thought_depth", 0)

        # Terminal actions don't count toward depth limit
        terminal_actions = {
            HandlerActionType.DEFER.value,
            HandlerActionType.REJECT.value,
            HandlerActionType.TASK_COMPLETE.value
        }

        if action.selected_action in terminal_actions:
            # Update correlation with completion
            end_time = self._time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": f"Terminal action {action.selected_action} at depth {current_depth}",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat()
                },
                status=ServiceCorrelationStatus.COMPLETED
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=timestamp,
                epistemic_data=EpistemicData(
                    entropy_level=0.5,
                    coherence_level=0.9,  # Terminal actions are coherent
                    uncertainty_acknowledged=True,
                    reasoning_transparency=0.8
                ),
                reason=f"Terminal action {action.selected_action} at depth {current_depth}"
            )

        # Check if we're at or beyond max depth
        if current_depth >= self.max_depth:
            logger.warning(
                f"Thought {thought.thought_id} at depth {current_depth} "
                f"exceeds max depth {self.max_depth}. Forcing DEFER."
            )

            # Create defer parameters
            _defer_params = DeferParams(
                reason=f"Maximum action depth ({self.max_depth}) reached. "
                       "This task requires human guidance to proceed further.",
                context={
                    "thought_depth": str(current_depth),
                    "original_action": action.selected_action,  # It's already a string
                    "auto_deferred": "true"
                },
                defer_until=None  # No specific time, defer indefinitely
            )

            # Create the defer action that will replace the original
            _defer_action = ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER.value,
                action_parameters=None,  # No parameters needed
                selection_reasoning=f"Automatically deferred: Maximum thought depth of {self.max_depth} reached",
                # Add required fields for ActionSelectionDMAResult
                pdma_weight=1.0,
                csdma_weight=0.0,
                dsdma_weight=0.0,
                actions_considered=[HandlerActionType.DEFER.value],
                selection_ethical_score=1.0,
                selection_fairness=1.0,
                selection_principles=["Safety", "Prudence"],
                total_evaluation_time_ms=0.0
            )

            # Update correlation with failure (depth exceeded)
            end_time = self._time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "result_summary": f"Maximum thought depth ({self.max_depth}) reached - deferring to human",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat()
                },
                status=ServiceCorrelationStatus.FAILED
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.FAILED,
                passed=False,
                reason=f"Maximum thought depth ({self.max_depth}) reached - deferring to human",
                check_timestamp=timestamp,
                epistemic_data=EpistemicData(
                    entropy_level=0.8,  # High uncertainty at max depth
                    coherence_level=0.3,  # Low coherence when forced to stop
                    uncertainty_acknowledged=True,
                    reasoning_transparency=0.9  # Very transparent about why
                )
            )

        # Depth is within limits
        # Update correlation with success
        end_time = self._time_service.now()
        update_req = CorrelationUpdateRequest(
            correlation_id=correlation.correlation_id,
            response_data={
                "success": "true",
                "result_summary": f"Thought depth {current_depth} within limit of {self.max_depth}",
                "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                "response_timestamp": end_time.isoformat()
            },
            status=ServiceCorrelationStatus.COMPLETED
        )
        persistence.update_correlation(update_req, self._time_service)
        return ConscienceCheckResult(
            status=ConscienceStatus.PASSED,
            passed=True,
            check_timestamp=timestamp,
            epistemic_data=EpistemicData(
                entropy_level=0.5,
                coherence_level=0.8,  # Good coherence within limits
                uncertainty_acknowledged=True,
                reasoning_transparency=0.7
            ),
            reason=f"Thought depth {current_depth} within limit of {self.max_depth}"
        )
