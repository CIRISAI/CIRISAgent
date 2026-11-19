"""
Thought depth conscience that enforces maximum action chain length.

When a thought reaches the maximum allowed depth, this conscience
overrides the action to DEFER, ensuring proper escalation to humans.
"""

import logging
from typing import Dict, List, Optional, Union

from ciris_engine.logic import persistence
from ciris_engine.logic.conscience.interface import ConscienceInterface
from ciris_engine.logic.utils.deferral_text import clip_deferral_text, redacted_json
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions import DeferParams
from ciris_engine.schemas.actions.parameters import SpeakParams, ToolParams
from ciris_engine.schemas.conscience.context import ConscienceCheckContext
from ciris_engine.schemas.conscience.core import ConscienceCheckResult, ConscienceStatus
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)

logger = logging.getLogger(__name__)

# A veto line per earlier thought; each is clipped so one long rationale cannot
# crowd the others out of the deferral.
_VETO_LINE_MAX_CHARS = 800


def _verb(selected_action: object) -> str:
    """The action verb as a plain string ("speak"), whether given as enum or str."""
    return str(getattr(selected_action, "value", selected_action))


def _last_draft_context(action: ActionSelectionDMAResult) -> Dict[str, Union[str, List[str]]]:
    """The draft the depth limit stopped, as the WA should read it.

    A SPEAK is its content; a TOOL is its name and its arguments with secrets
    redacted; anything else is its parameters, redacted the same way.
    """
    draft: Dict[str, Union[str, List[str]]] = {"last_draft_action": _verb(action.selected_action)}
    params = action.action_parameters
    if isinstance(params, SpeakParams):
        draft["last_draft"] = clip_deferral_text(params.content)
    elif isinstance(params, ToolParams):
        draft["last_draft_tool"] = params.name
        draft["last_draft"] = clip_deferral_text(f"{params.name}({redacted_json(params.parameters)})")
    elif params is not None and hasattr(params, "model_dump"):
        draft["last_draft"] = clip_deferral_text(redacted_json(params.model_dump(mode="json", exclude_none=True)))
    if action.rationale:
        draft["last_draft_rationale"] = clip_deferral_text(action.rationale)
    return draft


def _veto_line(depth: object, reasoning: str, questions: List[str]) -> str:
    text = reasoning.strip()
    detail = " | ".join(q.strip() for q in questions if q and q.strip())
    if detail:
        text = f"{text}: {detail}" if text else detail
    return clip_deferral_text(f"[depth {depth}] {text}", _VETO_LINE_MAX_CHARS)


def _current_feedback_reason(thought: object) -> Optional[str]:
    """The veto behind this pass's conscience retry, if the thought item carries one."""
    feedback = getattr(thought, "conscience_feedback", None)
    if isinstance(feedback, dict):
        reason = feedback.get("failure_reason")
    else:
        reason = getattr(feedback, "failure_reason", None) or getattr(feedback, "override_reason", None)
    return str(reason) if reason else None


def _prior_veto_reasons(thought: object) -> List[str]:
    """Why each earlier thought in this chain was sent back, oldest first.

    A conscience veto ends a thought in a PONDER whose questions carry the
    veto reason and whose rationale names the conscience
    (conscience_execution); the ponder handler then opens the next thought one
    depth deeper. So the reasons are the PONDER final actions recorded on this
    thought's ancestors, read from the store by ``parent_thought_id``. A
    drafter's own PONDER is recorded the same way and listed too: it is also
    part of what the WA needs to see. Ponder notes and an in-pass conscience
    retry are added when present. Never raises: a deferral without the
    history is still a deferral.
    """
    lines: List[str] = []
    try:
        occurrence = str(getattr(thought, "agent_occurrence_id", "default") or "default")
        start: object = thought
        if not isinstance(start, Thought):
            # A ProcessingQueueItem carries no parent link; read the stored row.
            thought_id = getattr(thought, "thought_id", None)
            start = persistence.get_thought_by_id(thought_id, occurrence) if isinstance(thought_id, str) else None
        ancestors: List[Thought] = []
        parent_id = start.parent_thought_id if isinstance(start, Thought) else None
        seen: set[str] = set()
        while isinstance(parent_id, str) and parent_id and parent_id not in seen and len(ancestors) < 16:
            seen.add(parent_id)
            parent = persistence.get_thought_by_id(parent_id, occurrence)
            if not isinstance(parent, Thought):
                break
            ancestors.append(parent)
            parent_id = parent.parent_thought_id
        for ancestor in reversed(ancestors):
            final = ancestor.final_action
            if final is None or final.action_type.lower() != HandlerActionType.PONDER.value:
                continue
            raw_questions = final.action_params.get("questions")
            questions = [str(q) for q in raw_questions] if isinstance(raw_questions, list) else []
            lines.append(_veto_line(ancestor.thought_depth, final.reasoning, questions))
        notes = getattr(thought, "ponder_notes", None) or (start.ponder_notes if isinstance(start, Thought) else None)
        if isinstance(notes, list):
            lines.extend(clip_deferral_text(f"[ponder note] {note}", _VETO_LINE_MAX_CHARS) for note in notes if note)
    except Exception as e:  # noqa: BLE001 - the deferral must still happen
        logger.warning(f"ThoughtDepthGuardrail: could not read prior veto reasons: {e}")
    current = _current_feedback_reason(thought)
    if current:
        lines.append(clip_deferral_text(f"[this thought] {current}", _VETO_LINE_MAX_CHARS))
    return lines


class ThoughtDepthGuardrail(ConscienceInterface):
    """Enforces maximum thought depth by deferring when limit is reached."""

    def __init__(self, time_service: TimeServiceProtocol, max_depth: Optional[int] = None):
        """Initialize with time service and configurable max depth."""
        self._time_service = time_service
        if max_depth is None:
            # Match EssentialConfig.security.max_thought_depth default (5 since 2.7.1).
            # Successful resolutions cap at depth 5; depth 6+ chains historically
            # spoke without completing or DEFERred anyway. See essential.py:75.
            max_depth = 5
        self.max_depth = max_depth
        logger.info(f"ThoughtDepthconscience initialized with max_depth={self.max_depth}")

    async def check(
        self,
        action: ActionSelectionDMAResult,
        context: ConscienceCheckContext,
    ) -> ConscienceCheckResult:
        """Check if thought depth exceeds maximum allowed."""
        start_time = self._time_service.now()
        timestamp = self._time_service.now()

        # Get the thought from context
        thought = context.thought
        thought_id = thought.thought_id if thought and hasattr(thought, "thought_id") else "unknown"
        task_id = thought.source_task_id if thought and hasattr(thought, "source_task_id") else "unknown"

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
                "max_depth": str(self.max_depth),
            },
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
                "trace_depth": "4",
            },
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
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=timestamp,
                reason="No thought provided to check",
                original_action=action.model_dump(),
                thought_depth_triggered=False,
            )

        # CRITICAL: thought_depth must NEVER default - it must be explicitly set
        if not hasattr(thought, "thought_depth"):
            raise ValueError(
                f"GUARDRAIL BUG: thought object {type(thought).__name__} missing thought_depth. "
                "thought_depth must always be explicitly set, never defaulted."
            )
        current_depth = thought.thought_depth

        # Terminal actions don't count toward depth limit
        terminal_actions = {
            HandlerActionType.DEFER.value,
            HandlerActionType.REJECT.value,
            HandlerActionType.TASK_COMPLETE.value,
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
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.COMPLETED,
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.PASSED,
                passed=True,
                check_timestamp=timestamp,
                reason=f"Terminal action {action.selected_action} at depth {current_depth}",
                original_action=action.model_dump(),
                thought_depth_triggered=False,
            )

        # Check if we're at or beyond max depth
        if current_depth >= self.max_depth:
            logger.warning(
                f"Thought {thought.thought_id} at depth {current_depth} "
                f"exceeds max depth {self.max_depth}. Forcing DEFER."
            )

            # Create defer parameters. The context carries what was contested
            # (CIRISAgent#1366 item 6): the draft the depth limit stopped, why
            # the drafter chose it, and the conscience reasons that kept
            # sending it back. Without them the WA reads only "Maximum action
            # depth reached" and cannot tell what to validate.
            defer_context: Dict[str, Union[str, List[str]]] = {
                "thought_depth": str(current_depth),
                "original_action": _verb(action.selected_action),
                "auto_deferred": "true",
            }
            defer_context.update(_last_draft_context(action))
            veto_reasons = _prior_veto_reasons(thought)
            if veto_reasons:
                defer_context["prior_veto_reasons"] = clip_deferral_text("\n".join(veto_reasons))
            _defer_params = DeferParams(
                reason=f"Maximum action depth ({self.max_depth}) reached. "
                "This task requires human guidance to proceed further.",
                context=defer_context,
                defer_until=None,  # No specific time, defer indefinitely
            )

            # Create the defer action that will replace the original
            defer_action = ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER.value,
                action_parameters=_defer_params,
                rationale=f"Automatically deferred: Maximum thought depth of {self.max_depth} reached",
            )

            # Update correlation with failure (depth exceeded)
            end_time = self._time_service.now()
            update_req = CorrelationUpdateRequest(
                correlation_id=correlation.correlation_id,
                response_data={
                    "success": "false",
                    "result_summary": f"Maximum thought depth ({self.max_depth}) reached - deferring to human",
                    "execution_time_ms": str((end_time - start_time).total_seconds() * 1000),
                    "response_timestamp": end_time.isoformat(),
                },
                status=ServiceCorrelationStatus.FAILED,
            )
            persistence.update_correlation(update_req, self._time_service)
            return ConscienceCheckResult(
                status=ConscienceStatus.FAILED,
                passed=False,
                reason=f"Maximum thought depth ({self.max_depth}) reached - deferring to human",
                check_timestamp=timestamp,
                replacement_action=defer_action.model_dump(),  # Top-level field in ConscienceCheckResult
                original_action=action.model_dump(),
                thought_depth_triggered=True,
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
                "response_timestamp": end_time.isoformat(),
            },
            status=ServiceCorrelationStatus.COMPLETED,
        )
        persistence.update_correlation(update_req, self._time_service)
        return ConscienceCheckResult(
            status=ConscienceStatus.PASSED,
            passed=True,
            check_timestamp=timestamp,
            reason=f"Thought depth {current_depth} within limit of {self.max_depth}",
            original_action=action.model_dump(),
            thought_depth_triggered=False,
        )
