import logging
import uuid
from datetime import datetime
from typing import Optional, Set, Tuple

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies, BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.logic.infrastructure.handlers.shared_helpers import has_valid_adapter_prefix
from ciris_engine.logic.utils.channel_utils import extract_channel_id
from ciris_engine.schemas.actions import SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.telemetry.core import (
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
)

logger = logging.getLogger(__name__)


def _normalize_channel_id(channel_id: str, thought: Thought) -> str:
    """Normalize a channel_id to ensure it has a valid adapter prefix."""
    if has_valid_adapter_prefix(channel_id):
        return channel_id

    logger.info(f"SPEAK: channel_id '{channel_id}' missing adapter prefix, attempting to normalize")

    # Check if the task has a channel_id that matches (with prefix)
    if thought.source_task_id:
        task = persistence.get_task_by_id(thought.source_task_id)
        if task and task.channel_id and task.channel_id.endswith(channel_id):
            logger.info(f"SPEAK: Found matching task channel_id '{task.channel_id}' for '{channel_id}'")
            return task.channel_id

    # Default: prepend "api_" for API-originated messages
    normalized = f"api_{channel_id}"
    logger.info(f"SPEAK: Normalized channel_id to '{normalized}' (prepended api_)")
    return normalized


def _build_speak_error_context(params: SpeakParams, thought_id: str, error_type: str = "notification_failed") -> str:
    """Build a descriptive error context string for speak failures."""
    content_str = params.content
    if hasattr(params.content, "value"):
        content_str = getattr(params.content, "value", str(params.content))
    elif hasattr(params.content, "__str__"):
        content_str = str(params.content)

    channel_id = extract_channel_id(params.channel_context) or "unknown"
    truncated_content = f"{content_str[:100]}{'...' if len(content_str) > 100 else ''}"

    error_contexts = {
        "notification_failed": f"Failed to send notification to channel '{channel_id}' with content: '{truncated_content}'",
        "channel_unavailable": f"Channel '{channel_id}' is not available or accessible",
        "content_rejected": f"Content was rejected by the communication service: '{truncated_content}'",
        "service_timeout": f"Communication service timed out while sending to channel '{channel_id}'",
        "unknown": f"Unknown error occurred while speaking to channel '{channel_id}'",
    }

    base_context = error_contexts.get(error_type, error_contexts["unknown"])
    return f"Thought {thought_id}: {base_context}"


class SpeakHandler(BaseActionHandler):
    def __init__(self, dependencies: ActionHandlerDependencies) -> None:
        super().__init__(dependencies)

    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> Optional[str]:
        start_time = self.time_service.now()

        self._create_trace_correlation(dispatch_context, HandlerActionType.SPEAK)

        # Validate and parse parameters
        params_or_error = await self._validate_speak_params(result, thought, dispatch_context)
        if isinstance(params_or_error, str):
            return params_or_error  # Error handled, return follow_up_id
        params = params_or_error

        # Resolve destination and enforce task audience boundary (CIRISAgent#1374 / A046)
        content_str = self._extract_content_string(params)
        channel_id, refusal_reason = self._resolve_and_authorize_channel_id(params, thought, dispatch_context)
        if refusal_reason is not None:
            return self._refuse_unauthorized_channel(
                thought=thought,
                result=result,
                attempted_channel=channel_id,
                content=content_str,
                reason=refusal_reason,
                start_time=start_time,
            )

        # Send the message
        success = await self._send_notification(channel_id, content_str)

        # Handle failure by injecting error message
        if not success:
            await self._inject_error_message(channel_id)

        # Create service correlation
        self._create_speak_correlation(thought, channel_id, content_str, success, start_time)

        # Complete thought and create follow-up
        return self._complete_speak_action(thought, result, channel_id, success)

    async def _validate_speak_params(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> SpeakParams | str:
        """Validate and parse speak parameters. Returns SpeakParams on success, follow_up_id on failure."""
        thought_id = thought.thought_id

        try:
            processed_result = await self._decapsulate_secrets_in_params(result, "speak", thought_id)

            # Debug logging for channel context
            if hasattr(processed_result.action_parameters, "get"):
                channel_ctx = processed_result.action_parameters.get("channel_context", "None")
                logger.info(f"SPEAK: Received action_parameters dict with channel_context: {channel_ctx}")

            return self._validate_and_convert_params(processed_result.action_parameters, SpeakParams)

        except Exception as e:
            await self._handle_error(HandlerActionType.SPEAK, dispatch_context, thought_id, e)
            self._update_trace_correlation(False, f"Parameter validation failed: {e}")

            follow_up_id = self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=self._localized_followup(
                    "speak_action_failed_with_reason",
                    default=f"SPEAK action failed for thought {thought_id}. Reason: {e}",
                    thought_id=thought_id,
                    reason=str(e),
                ),
                action_result=result,
                status=ThoughtStatus.FAILED,
            )
            return follow_up_id or ""  # Return empty string if None (should not happen)

    def _resolve_permitted_audience(
        self, thought: Thought, dispatch_context: DispatchContext
    ) -> Tuple[Optional[str], Set[str]]:
        """Return (origin_channel_id, permitted_channel_ids) from kernel/persistence state.

        Audience comes strictly from trusted task/thought/dispatch metadata —
        never from model-authored ``SpeakParams``.
        """
        permitted: Set[str] = set()
        origin_channel = self._get_channel_id(thought, dispatch_context)
        if origin_channel:
            permitted.add(origin_channel)
            permitted.add(_normalize_channel_id(origin_channel, thought))

        if thought.source_task_id:
            task = persistence.get_task_by_id(thought.source_task_id)
            if task and task.channel_id:
                permitted.add(task.channel_id)
                permitted.add(_normalize_channel_id(task.channel_id, thought))
                if not origin_channel:
                    origin_channel = task.channel_id

        normalized_origin = _normalize_channel_id(origin_channel, thought) if origin_channel else None
        return normalized_origin, permitted

    def _resolve_and_authorize_channel_id(
        self, params: SpeakParams, thought: Thought, dispatch_context: DispatchContext
    ) -> Tuple[str, Optional[str]]:
        """Resolve channel ID and verify model-supplied destinations against task audience.

        Returns ``(channel_id, None)`` when authorized, or
        ``(attempted_channel_id, refusal_reason)`` when a model-supplied
        destination falls outside the task's permitted audience (CIRISAgent#1374).
        """
        origin_channel, permitted = self._resolve_permitted_audience(thought, dispatch_context)

        requested_channel: Optional[str] = None
        if params.channel_id:
            requested_channel = params.channel_id
            logger.info(f"SPEAK: Model requested channel_id '{requested_channel}' via params.channel_id")
        elif params.channel_context:
            requested_channel = extract_channel_id(params.channel_context)
            if requested_channel:
                logger.info(f"SPEAK: Model requested channel_id '{requested_channel}' via params.channel_context")

        if requested_channel is not None:
            normalized_requested = _normalize_channel_id(requested_channel, thought)
            if requested_channel in permitted or normalized_requested in permitted:
                return normalized_requested, None
            reason = (
                f"audience_mismatch: destination '{normalized_requested}' is outside the "
                f"permitted audience for task {thought.source_task_id or 'unknown'} "
                f"(origin: '{origin_channel or 'none'}')"
            )
            logger.warning(f"SPEAK refused for thought {thought.thought_id}: {reason}")
            return normalized_requested, reason

        if origin_channel:
            logger.info(f"SPEAK: Using originating channel_id '{origin_channel}' from thought/task context")
            return origin_channel, None

        logger.error(f"CRITICAL: No channel_id found in params or thought {thought.thought_id} context")
        raise ValueError(
            f"Channel ID is required for SPEAK action - none found in params or thought {thought.thought_id}"
        )

    def _resolve_channel_id(self, params: SpeakParams, thought: Thought, dispatch_context: DispatchContext) -> str:
        """Resolve channel ID from params, context, or thought (legacy helper)."""
        channel_id, refusal_reason = self._resolve_and_authorize_channel_id(params, thought, dispatch_context)
        if refusal_reason is not None:
            raise PermissionError(refusal_reason)
        return channel_id

    def _refuse_unauthorized_channel(
        self,
        *,
        thought: Thought,
        result: ActionSelectionDMAResult,
        attempted_channel: str,
        content: str,
        reason: str,
        start_time: datetime,
    ) -> str:
        """Record correlation and follow-up when SPEAK targets a channel outside the task audience."""
        summary = f"Refused SPEAK to unauthorized channel {attempted_channel}: {reason}"
        self._create_speak_correlation(
            thought,
            attempted_channel,
            content,
            success=False,
            start_time=start_time,
            result_summary=summary,
        )
        follow_up_text = self._localized_followup(
            "speak_audience_refused",
            default=(
                f"SPEAK REFUSED ({reason}). No message was sent to channel {attempted_channel}. "
                "You may only speak to the originating channel for this task."
            ),
            channel_id=attempted_channel,
            reason=reason,
        )
        follow_up_thought_id = self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=follow_up_text,
            action_result=result,
            status=ThoughtStatus.FAILED,
        )
        if not follow_up_thought_id:
            raise FollowUpCreationError("Failed to create follow-up thought")
        self._update_trace_correlation(False, summary)
        return follow_up_thought_id

    def _extract_content_string(self, params: SpeakParams) -> str:
        """Extract string content from params."""
        if hasattr(params.content, "attributes"):
            text = params.content.attributes.get("text", str(params.content))
            return str(text)  # Ensure we return str
        return str(params.content)

    async def _inject_error_message(self, channel_id: str) -> None:
        """Inject an error message into the channel on SPEAK failure."""
        try:
            comm_bus = self.bus_manager.communication
            if not comm_bus:
                return

            error_message = "Failed to deliver agent response. The message could not be sent to the channel."
            comm_service = await comm_bus.get_service("speak_handler")

            if comm_service and hasattr(comm_service, "send_system_message"):
                await comm_service.send_system_message(
                    channel_id=channel_id, content=error_message, message_type="error"
                )
                logger.info(f"Injected error message into channel {channel_id} after SPEAK failure")
        except Exception as e:
            logger.warning(f"Could not inject error message after SPEAK failure: {e}")

    def _create_speak_correlation(
        self,
        thought: Thought,
        channel_id: str,
        content: str,
        success: bool,
        start_time: datetime,
        result_summary: Optional[str] = None,
    ) -> None:
        """Create service correlation for SPEAK action tracking."""
        now = self.time_service.now()

        request_data = ServiceRequestData(
            service_type="communication",
            method_name="send_message",
            thought_id=thought.thought_id,
            task_id=thought.source_task_id,
            channel_id=channel_id,
            parameters={"content": content},
            request_timestamp=now,
        )

        response_data = ServiceResponseData(
            success=success,
            result_summary=result_summary or f"Message {'sent' if success else 'failed'} to channel {channel_id}",
            execution_time_ms=(now - start_time).total_seconds() * 1000.0,
            response_timestamp=now,
        )

        correlation = ServiceCorrelation(
            correlation_id=str(uuid.uuid4()),
            service_type="handler",
            handler_name="SpeakHandler",
            action_type="speak_action",
            request_data=request_data,
            response_data=response_data,
            status=ServiceCorrelationStatus.COMPLETED if success else ServiceCorrelationStatus.FAILED,
            created_at=now,
            updated_at=now,
            timestamp=now,
        )
        persistence.add_correlation(correlation, self.time_service)

    def _complete_speak_action(
        self, thought: Thought, result: ActionSelectionDMAResult, channel_id: str, success: bool
    ) -> str:
        """Complete the speak action and create follow-up thought (or auto-complete in benchmark mode)."""
        from ciris_engine.logic.config.env_utils import get_env_var
        from ciris_engine.schemas.runtime.enums import TaskStatus

        # Check for benchmark mode - skip follow-up and auto-complete parent task
        benchmark_mode_val = get_env_var("CIRIS_BENCHMARK_MODE", "") or ""
        benchmark_mode = benchmark_mode_val.lower() in ("true", "1", "yes", "on")

        if benchmark_mode and success:
            # In benchmark mode, auto-complete the parent task after SPEAK
            logger.info(f"[BENCHMARK_MODE] SPEAK successful, auto-completing task {thought.source_task_id}")

            # Mark the thought as completed
            persistence.update_thought_status(
                thought_id=thought.thought_id,
                status=ThoughtStatus.COMPLETED,
                final_action=result.model_dump(),
            )

            # Mark the parent task as completed
            if thought.source_task_id:
                persistence.update_task_status(
                    thought.source_task_id,
                    TaskStatus.COMPLETED,
                    thought.agent_occurrence_id,
                )

            self._update_trace_correlation(True, f"[BENCHMARK] Message sent to {channel_id}, task auto-completed")
            return f"benchmark_complete_{thought.thought_id}"

        # Normal mode: create follow-up thought (localized via handlers.* keys)
        if success:
            follow_up_text = self._localized_followup(
                "speak_followup_success",
                default=(
                    f"SPEAK SUCCESSFUL! Message delivered to channel {channel_id}. "
                    "Speaking repeatedly on the same task is usually incorrect. "
                    "Unless you need to use a tool to follow up on the task, the next choice is almost certainly TASK_COMPLETE. "
                    "Do not SPEAK again unless a correction is truly necessary. "
                    "New user messages will create new tasks automatically."
                ),
                channel_id=channel_id,
            )
        else:
            follow_up_text = self._localized_followup(
                "speak_followup_failure",
                default=f"SPEAK action failed for thought {thought.thought_id}.",
                thought_id=thought.thought_id,
            )

        final_status = ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED

        follow_up_thought_id = self.complete_thought_and_create_followup(
            thought=thought, follow_up_content=follow_up_text, action_result=result, status=final_status
        )

        if not follow_up_thought_id:
            raise FollowUpCreationError("Failed to create follow-up thought")

        self._update_trace_correlation(success, f"Message {'sent' if success else 'failed'} to channel {channel_id}")

        return follow_up_thought_id
