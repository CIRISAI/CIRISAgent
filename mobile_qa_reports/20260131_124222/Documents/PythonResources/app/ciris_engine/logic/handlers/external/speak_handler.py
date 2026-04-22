import logging
import uuid
from datetime import datetime
from typing import Optional

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

        # Resolve channel ID
        channel_id = self._resolve_channel_id(params, thought, dispatch_context)

        # Send the message
        content_str = self._extract_content_string(params)
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
                follow_up_content=f"SPEAK action failed for thought {thought_id}. Reason: {e}",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )
            return follow_up_id or ""  # Return empty string if None (should not happen)

    def _resolve_channel_id(self, params: SpeakParams, thought: Thought, dispatch_context: DispatchContext) -> str:
        """Resolve channel ID from params, context, or thought."""
        channel_id = None

        # First check params.channel_id
        if params.channel_id:
            channel_id = params.channel_id
            logger.info(f"SPEAK: Using channel_id '{channel_id}' from params.channel_id")

        # Second check params.channel_context
        elif params.channel_context:
            channel_id = extract_channel_id(params.channel_context)
            if channel_id:
                logger.info(f"SPEAK: Using channel_id '{channel_id}' from params.channel_context")

        # Fall back to thought/task context
        if not channel_id:
            channel_id = self._get_channel_id(thought, dispatch_context)
            if channel_id:
                logger.info(f"SPEAK: Using channel_id '{channel_id}' from thought/task context")

        if not channel_id:
            logger.error(f"CRITICAL: No channel_id found in params or thought {thought.thought_id} context")
            raise ValueError(
                f"Channel ID is required for SPEAK action - none found in params or thought {thought.thought_id}"
            )

        return _normalize_channel_id(channel_id, thought)

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
        self, thought: Thought, channel_id: str, content: str, success: bool, start_time: datetime
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
            result_summary=f"Message {'sent' if success else 'failed'} to channel {channel_id}",
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
        """Complete the speak action and create follow-up thought."""
        if success:
            follow_up_text = (
                f"CIRIS_FOLLOW_UP_THOUGHT: SPEAK SUCCESSFUL! Message delivered to channel {channel_id}. "
                "Speaking repeatedly on the same task is not useful - if you have nothing new to add, use TASK_COMPLETE. "
                "New user messages will create new tasks automatically."
            )
        else:
            follow_up_text = f"CIRIS_FOLLOW_UP_THOUGHT: SPEAK action failed for thought {thought.thought_id}."

        final_status = ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED

        follow_up_thought_id = self.complete_thought_and_create_followup(
            thought=thought, follow_up_content=follow_up_text, action_result=result, status=final_status
        )

        if not follow_up_thought_id:
            raise FollowUpCreationError("Failed to create follow-up thought")

        self._update_trace_correlation(success, f"Message {'sent' if success else 'failed'} to channel {channel_id}")

        return follow_up_thought_id
