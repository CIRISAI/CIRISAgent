"""
Action Sequence Conscience - prevents repeated SPEAK actions without intervening actions.

When a SPEAK action is attempted after a prior completed SPEAK with no intervening
completed action, this conscience bounces the action back to recursive ASPDMA
with guidance to reconsider.
"""

import logging
from typing import List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.conscience.interface import ConscienceInterface
from ciris_engine.logic.persistence.models.thoughts import get_thoughts_by_task_id
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)

logger = logging.getLogger(__name__)

# Guidance message for repeated SPEAK attempts
REPEATED_SPEAK_GUIDANCE = (
    "You already spoke in response to this task, do not speak twice unless your "
    "first utterance was so grossly inadequate you must correct yourself, and if so, "
    "start with, 'I apologize'"
)

class ActionSequenceConscience(ConscienceInterface):
    """Prevents back-to-back SPEAK with no intervening action.

    Rule: block only if the immediately-prior completed action was SPEAK.
    Any other action (PONDER, TOOL, OBSERVE, MEMORIZE, RECALL, FORGET, DEFER,
    REJECT, TASK_COMPLETE) counts as intervening — the agent has done
    something since its last utterance, so a new SPEAK is legitimate.

    Earlier versions kept a whitelist (OBSERVE/DEFER/MEMORIZE/REJECT/PONDER)
    and walked backward through history treating TOOL/RECALL/FORGET/
    TASK_COMPLETE as transparent. That misfired in two ways:
      1. The reversed-walk hit the most-recent SPEAK first and blocked
         before considering prior PONDERs (production datum WAKEUP livelock).
      2. [SPEAK, TOOL, attempt-SPEAK] would block, even though the agent
         used a tool — making productive tool→speak chains impossible.

    The simpler rule (immediate-prior only) matches the v3.2 ponder
    principle: ponder = "try a new approach"; the new approach is the
    next SPEAK. If the bounce gate or another conscience rejects the
    content, that's the right layer — not this sequence-shape check.

    If the rule is violated, bounces back to recursive ASPDMA with guidance.
    """

    def __init__(self, time_service: TimeServiceProtocol):
        """Initialize with time service for tracing."""
        self._time_service = time_service
        logger.info("ActionSequenceConscience initialized")

    def _get_completed_action_sequence(
        self,
        task_id: str,
        current_thought_id: str,
        occurrence_id: str = "default",
    ) -> List[str]:
        """Get the sequence of completed action types for a task.

        Args:
            task_id: The task ID to query
            current_thought_id: The current thought ID (to exclude)
            occurrence_id: The agent occurrence ID

        Returns:
            List of action type strings in chronological order
        """
        try:
            thoughts = get_thoughts_by_task_id(task_id, occurrence_id)

            # Filter to completed thoughts with final actions, excluding current thought
            completed_actions: List[str] = []
            for thought in thoughts:
                if (
                    thought.thought_id != current_thought_id
                    and thought.status == ThoughtStatus.COMPLETED
                    and thought.final_action is not None
                ):
                    completed_actions.append(thought.final_action.action_type)

            return completed_actions

        except Exception as e:
            logger.warning(f"[action_sequence] Error getting action history: {e}")
            return []

    async def check(
        self,
        action: ActionSelectionDMAResult,
        context: ConscienceCheckContext,
    ) -> ConscienceCheckResult:
        """Check if SPEAK action violates the no-repeat rule.

        Rule: If SPEAK is attempted after a prior completed SPEAK with no
        intervening completed action, bounce back to recursive ASPDMA.
        """
        start_time = self._time_service.now()
        timestamp = self._time_service.now()

        # Get thought details from context
        thought = context.thought
        thought_id = thought.thought_id if thought and hasattr(thought, "thought_id") else "unknown"
        task_id = thought.source_task_id if thought and hasattr(thought, "source_task_id") else "unknown"
        occurrence_id = (
            thought.agent_occurrence_id if thought and hasattr(thought, "agent_occurrence_id") else "default"
        )

        # Create trace for conscience execution
        trace_id = f"task_{task_id}_{thought_id}"
        span_id = f"action_sequence_conscience_{thought_id}"
        parent_span_id = f"thought_processor_{thought_id}"

        trace_context = TraceContext(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            span_name="action_sequence_conscience_check",
            span_kind="internal",
            baggage={
                "thought_id": thought_id,
                "task_id": task_id,
                "conscience_type": "action_sequence",
                "current_action": action.selected_action,
            },
        )

        correlation = ServiceCorrelation(
            correlation_id=f"trace_{span_id}_{start_time.timestamp()}",
            correlation_type=CorrelationType.TRACE_SPAN,
            service_type="conscience",
            handler_name="ActionSequenceConscience",
            action_type="check",
            created_at=start_time,
            updated_at=start_time,
            timestamp=start_time,
            trace_context=trace_context,
            tags={
                "thought_id": thought_id,
                "task_id": task_id,
                "component_type": "conscience",
                "conscience_type": "action_sequence",
                "trace_depth": "4",
            },
        )

        # Add correlation
        persistence.add_correlation(correlation, self._time_service)

        # Only check SPEAK actions
        if action.selected_action != HandlerActionType.SPEAK.value:
            end_time = self._time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": f"Action {action.selected_action} is not SPEAK - skipping check",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=timestamp,
                reason=f"Action {action.selected_action} is not SPEAK - no sequence check needed",
                original_action=action.model_dump(),
                action_sequence_triggered=False,
            )

        # No thought context - can't check history
        if not thought:
            logger.warning("[action_sequence] No thought provided - allowing SPEAK")
            end_time = self._time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "true",
                    "result_summary": "No thought context - allowing SPEAK",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=timestamp,
                reason="No thought context available - allowing SPEAK",
                original_action=action.model_dump(),
                action_sequence_triggered=False,
            )

        # Get completed action sequence for this task
        completed_actions = self._get_completed_action_sequence(
            task_id=task_id,
            current_thought_id=thought_id,
            occurrence_id=occurrence_id,
        )

        logger.info(
            f"[action_sequence] Task {task_id}: completed_actions={completed_actions}, "
            f"attempting={action.selected_action}"
        )

        # Block only if the immediately-prior action was SPEAK. See class
        # docstring for the rationale and the datum-livelock motivation.
        prior_action = completed_actions[-1] if completed_actions else None
        found_speak_since_valid_action = prior_action == HandlerActionType.SPEAK.value

        if found_speak_since_valid_action:
            # Already spoke since last valid action (like OBSERVE), blocking repeat
            logger.info(
                f"[action_sequence] Blocking repeated SPEAK for task {task_id}. "
                f"Prior actions: {completed_actions}. TOOL doesn't reset SPEAK allowance."
            )

            end_time = self._time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "result_summary": "Repeated SPEAK blocked - bouncing to recursive ASPDMA",
                    "prior_actions": ",".join(completed_actions[-5:]),  # Last 5 for context
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
            )
            persistence.update_correlation(update_req, self._time_service)

            return ConscienceCheckResult(
                status=ConscienceStatus.FAILED,
                passed=False,
                check_timestamp=timestamp,
                reason=REPEATED_SPEAK_GUIDANCE,
                original_action=action.model_dump(),
                action_sequence_triggered=True,
                # No replacement_action - let recursive ASPDMA decide
            )

        # SPEAK is allowed - either first SPEAK or has valid intervening action
        reason = (
            "First SPEAK for this task"
            if HandlerActionType.SPEAK.value not in completed_actions
            else "SPEAK allowed - valid intervening action (OBSERVE/DEFER/etc.) since last SPEAK"
        )
        logger.info(f"[action_sequence] PASSED for task {task_id}: {reason}")

        end_time = self._time_service.now()
        update_req = CorrelationUpdateRequest(
            correlation_id=correlation.correlation_id,
            response_data={
                "success": "true",
                "result_summary": reason,
                "prior_actions": ",".join(completed_actions[-5:]) if completed_actions else "none",
                "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                "response_timestamp": end_time.isoformat(),
            },
            status=ServiceCorrelationStatus.COMPLETED,
        )
        persistence.update_correlation(update_req, self._time_service)

        return ConscienceCheckResult(
            status=ConscienceStatus.PASSED,
            passed=True,
            check_timestamp=timestamp,
            reason=reason,
            original_action=action.model_dump(),
            action_sequence_triggered=False,
        )
