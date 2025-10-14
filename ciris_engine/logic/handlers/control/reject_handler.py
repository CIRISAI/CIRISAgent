import logging
from typing import Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.utils.channel_utils import extract_channel_id
from ciris_engine.schemas.actions import RejectParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought

logger = logging.getLogger(__name__)


class RejectHandler(BaseActionHandler):
    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        raw_params = result.action_parameters
        thought_id = thought.thought_id
        parent_task_id = thought.source_task_id
        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging
        original_event_channel_id = extract_channel_id(dispatch_context.channel_context)

        final_thought_status = ThoughtStatus.FAILED
        _action_performed_successfully = False
        follow_up_content_key_info = f"REJECT action for thought {thought_id}"

        try:
            params: RejectParams = self._validate_and_convert_params(raw_params, RejectParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.REJECT, dispatch_context, thought_id, e)
            # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging
            persistence.update_thought_status(
                thought_id=thought_id,
                status=final_thought_status,
                final_action=result,
            )
            return None

        follow_up_content_key_info = f"Rejected thought {thought_id}. Reason: {params.reason}"

        # Send rejection notification to API channels
        if original_event_channel_id and self._is_api_channel(original_event_channel_id):
            self.logger.info(f"Sending rejection notification to API channel {original_event_channel_id}")
            await self._send_notification(original_event_channel_id, "Agent rejected the message")

        persistence.update_thought_status(
            thought_id=thought_id,
            status=final_thought_status,
            final_action=result,
        )
        if parent_task_id:
            persistence.update_task_status(parent_task_id, TaskStatus.REJECTED, "default", self.time_service)
        self.logger.info(
            f"Updated original thought {thought_id} to status {final_thought_status.value} for REJECT action. Info: {follow_up_content_key_info}"
        )

        # Handle adaptive filtering if requested
        if isinstance(params, RejectParams) and params.create_filter:
            await self._create_adaptive_filter(params, thought, dispatch_context)

        # REJECT is a terminal action - no follow-up thoughts should be created
        self.logger.info(f"REJECT action completed for thought {thought_id}. This is a terminal action.")
        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

        return None

    def _is_api_channel(self, channel_id: Optional[str]) -> bool:
        """Check if channel is an API channel (not Discord)."""
        if not channel_id:
            return False
        return channel_id.startswith("api_") or channel_id.startswith("ws:")

    async def _create_adaptive_filter(
        self, params: RejectParams, thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Create an adaptive filter based on the rejected content."""
        # TODO: Implement filter bus when needed
        self.logger.info("Adaptive filter creation not implemented in new bus architecture")
