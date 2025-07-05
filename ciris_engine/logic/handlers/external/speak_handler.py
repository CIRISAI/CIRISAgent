import logging
from typing import Optional

from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.actions import SpeakParams
from ciris_engine.schemas.runtime.enums import ThoughtStatus, HandlerActionType
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.logic import persistence
from ciris_engine.logic.utils.channel_utils import extract_channel_id
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler, ActionHandlerDependencies
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError

logger = logging.getLogger(__name__)

def _build_speak_error_context(params: SpeakParams, thought_id: str, error_type: str = "notification_failed") -> str:
    """Build a descriptive error context string for speak failures."""
    # Use attribute access for content if it's a GraphNode
    content_str = params.content
    if hasattr(params.content, 'value'):
        content_str = getattr(params.content, 'value', str(params.content))
    elif hasattr(params.content, '__str__'):
        content_str = str(params.content)
    channel_id = extract_channel_id(params.channel_context) or "unknown"
    error_contexts = {
        "notification_failed": f"Failed to send notification to channel '{channel_id}' with content: '{content_str[:100]}{'...' if len(content_str) > 100 else ''}'",
        "channel_unavailable": f"Channel '{channel_id}' is not available or accessible",
        "content_rejected": f"Content was rejected by the communication service: '{content_str[:100]}{'...' if len(content_str) > 100 else ''}'",
        "service_timeout": f"Communication service timed out while sending to channel '{channel_id}'",
        "unknown": f"Unknown error occurred while speaking to channel '{channel_id}'"
    }

    base_context = error_contexts.get(error_type, error_contexts["unknown"])
    return f"Thought {thought_id}: {base_context}"

class SpeakHandler(BaseActionHandler):
    def __init__(self, dependencies: ActionHandlerDependencies) -> None:
        super().__init__(dependencies)

    async def handle(
        self,
        result: ActionSelectionDMAResult,  # Updated to v1 result schema
        thought: Thought,
        dispatch_context: DispatchContext
    ) -> Optional[str]:
        thought_id = thought.thought_id
        
        # Create trace correlation for handler execution
        self._create_trace_correlation(dispatch_context, HandlerActionType.SPEAK)

        try:
            # Auto-decapsulate any secrets in the action parameters
            processed_result = await self._decapsulate_secrets_in_params(result, "speak", thought.thought_id)
            
            # Debug: Check what channel_context we received
            if isinstance(processed_result.action_parameters, dict):
                channel_ctx = processed_result.action_parameters.get('channel_context', 'None')
                logger.info(f"SPEAK: Received action_parameters dict with channel_context: {channel_ctx}")
                if isinstance(channel_ctx, dict):
                    logger.info(f"SPEAK: channel_context dict contains: {channel_ctx}")

            params: SpeakParams = await self._validate_and_convert_params(processed_result.action_parameters, SpeakParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.SPEAK, dispatch_context, thought_id, e)
            persistence.update_thought_status(
                thought_id=thought_id,
                status=ThoughtStatus.FAILED,
                final_action=result,
            )
            follow_up_text = f"SPEAK action failed for thought {thought_id}. Reason: {e}"
            # Update trace correlation with failure
            self._update_trace_correlation(False, f"Parameter validation failed: {str(e)}")
            try:
                fu = create_follow_up_thought(parent=thought, time_service=self.time_service, content=follow_up_text)
                # Simple: ensure channel_id is in the thought context
                if fu.context and not fu.context.channel_id:
                    # Extract channel_id from params.channel_context if available
                    extracted_channel_id = extract_channel_id(params.channel_context) or "unknown"
                    fu.context.channel_id = extracted_channel_id
                persistence.add_thought(fu)
                return fu.thought_id
            except Exception as fe:
                await self._handle_error(HandlerActionType.SPEAK, dispatch_context, thought_id, fe)
                raise FollowUpCreationError from fe

        # Get channel ID - first check params, then fall back to thought/task context
        channel_id = None
        
        # First, check if channel is specified in params
        if params.channel_context:
            channel_id = extract_channel_id(params.channel_context)
            if channel_id:
                logger.info(f"SPEAK: Using channel_id '{channel_id}' from params.channel_context")
        
        # Fall back to thought/task context if not in params
        if not channel_id:
            channel_id = await self._get_channel_id(thought, dispatch_context)
            if channel_id:
                logger.info(f"SPEAK: Using channel_id '{channel_id}' from thought/task context")
        
        if not channel_id:
            logger.error(f"CRITICAL: No channel_id found in params or thought {thought_id} context")
            raise ValueError(f"Channel ID is required for SPEAK action - none found in params or thought {thought_id}")

        event_summary = params.content
        await self._audit_log(
            HandlerActionType.SPEAK,
            dispatch_context.model_copy(update={"thought_id": thought_id, "event_summary": event_summary}),
            outcome="start",
        )

        # Extract string from GraphNode for notification
        content_str = params.content.attributes.get('text', str(params.content)) if hasattr(params.content, 'attributes') else str(params.content)
        success = await self._send_notification(channel_id, content_str)

        final_thought_status = ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED

        # Build error context if needed
        assert isinstance(params, SpeakParams)  # Type assertion - validated earlier
        _follow_up_error_context = None if success else _build_speak_error_context(params, thought_id)

        # Get the actual task content instead of just the ID
        task = persistence.get_task_by_id(thought.source_task_id)
        _task_description = task.description if task else f"task {thought.source_task_id}"

        # Create correlation for tracking action completion
        from ciris_engine.schemas.telemetry.core import (
            ServiceCorrelation, ServiceCorrelationStatus,
            ServiceRequestData, ServiceResponseData
        )
        import uuid

        now = self.time_service.now()

        # Create proper request data
        request_data = ServiceRequestData(
            service_type="communication",
            method_name="send_message",
            thought_id=thought_id,
            task_id=thought.source_task_id,
            channel_id=channel_id,
            parameters={"content": str(params.content)},
            request_timestamp=now
        )

        # Create proper response data
        response_data = ServiceResponseData(
            success=success,
            result_summary=f"Message {'sent' if success else 'failed'} to channel {channel_id}",
            execution_time_ms=100.0,  # TODO: Track actual execution time
            response_timestamp=now
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
            timestamp=now  # Required for TSDB indexing
        )
        persistence.add_correlation(correlation, self.time_service)

        follow_up_text = (
            f"CIRIS_FOLLOW_UP_THOUGHT: Message sent successfully to channel {channel_id}."
            if success
            else f"CIRIS_FOLLOW_UP_THOUGHT: SPEAK action failed for thought {thought_id}."
        )

        # Use centralized method for both success and failure cases
        follow_up_thought_id = await self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=follow_up_text,
            action_result=result,
            status=final_thought_status
        )
        
        if not follow_up_thought_id:
            await self._handle_error(HandlerActionType.SPEAK, dispatch_context, thought_id, Exception("Failed to create follow-up thought"))
            raise FollowUpCreationError("Failed to create follow-up thought")
            
        await self._audit_log(
            HandlerActionType.SPEAK,
            dispatch_context.model_copy(update={"thought_id": thought_id, "event_summary": event_summary}),
            outcome="success" if success else "failed",
        )

        # Update trace correlation with success
        self._update_trace_correlation(
            success, 
            f"Message {'sent' if success else 'failed'} to channel {channel_id}"
        )

        return follow_up_thought_id
