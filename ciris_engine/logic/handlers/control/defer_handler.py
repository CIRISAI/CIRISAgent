import logging
from datetime import datetime
from typing import Any, Dict, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.shared_helpers import parse_iso_timestamp
from ciris_engine.logic.utils.localization import get_preferred_language, get_string
from ciris_engine.schemas.actions import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.context import DeferralContext

logger = logging.getLogger(__name__)


class DeferHandler(BaseActionHandler):
    def _get_task_scheduler_service(self) -> Optional[Any]:
        """Get task scheduler service from dependencies."""
        service = self.dependencies.task_scheduler_service
        if service:
            logger.info(f"Got TaskSchedulerService from dependencies: {type(service).__name__}")
        else:
            logger.warning("TaskSchedulerService not available in handler dependencies")
        return service

    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> Optional[str]:
        raw_params = result.action_parameters
        thought_id = thought.thought_id

        follow_up_info = f"DEFER action for thought {thought_id}"

        try:
            defer_params = self._parse_defer_params(raw_params)
            follow_up_info = f"Deferred thought {thought_id}. Reason: {defer_params.reason}"

            # Handle time-based deferral
            if defer_params.defer_until:
                follow_up_info = await self._schedule_time_based_deferral(defer_params, thought, follow_up_info)

            # Send deferral to Wise Authority
            await self._send_deferral_to_wa(defer_params, thought, dispatch_context)

        except Exception as param_parse_error:
            self.logger.error(
                f"DEFER action params parsing error. Type: {type(raw_params)}, Error: {param_parse_error}. Thought ID: {thought_id}"
            )
            follow_up_info = (
                f"DEFER action failed: Invalid parameters for thought {thought_id}. Error: {param_parse_error}"
            )
            await self._send_error_deferral(thought, dispatch_context)

        # Update thought and task status
        persistence.update_thought_status(thought_id=thought_id, status=ThoughtStatus.DEFERRED, final_action=result)
        self.logger.info(f"Updated thought {thought_id} to DEFERRED. Info: {follow_up_info}")

        self._mark_task_deferred(thought)

        return None

    def _parse_defer_params(self, raw_params: Any) -> DeferParams:
        """Parse raw parameters into DeferParams."""
        return self._validate_and_convert_params(raw_params, DeferParams)

    async def _schedule_time_based_deferral(
        self, defer_params: DeferParams, thought: Thought, follow_up_info: str
    ) -> str:
        """Schedule a time-based deferral. Returns updated follow_up_info."""
        scheduler_service = self._get_task_scheduler_service()
        if not scheduler_service:
            return follow_up_info

        try:
            defer_time = parse_iso_timestamp(defer_params.defer_until)
            if not defer_time:
                return follow_up_info

            scheduled_task = await scheduler_service.schedule_deferred_task(
                thought_id=thought.thought_id,
                task_id=thought.source_task_id,
                defer_until=defer_params.defer_until,
                reason=defer_params.reason,
                context=defer_params.context,
            )

            logger.info(f"Created scheduled task {scheduled_task.task_id} to reactivate at {defer_params.defer_until}")

            time_diff = defer_time - self.time_service.now()
            hours = int(time_diff.total_seconds() / 3600)
            minutes = int((time_diff.total_seconds() % 3600) / 60)

            return (
                f"Deferred thought {thought.thought_id} until {defer_params.defer_until} "
                f"({hours}h {minutes}m from now). Reason: {defer_params.reason}"
            )
        except Exception:
            logger.exception("Failed to schedule deferred task")
            return follow_up_info

    async def _send_deferral_to_wa(
        self, defer_params: DeferParams, thought: Thought, dispatch_context: DispatchContext
    ) -> bool:
        """Send deferral to Wise Authority. Returns success status."""
        try:
            metadata = self._build_deferral_metadata(thought, dispatch_context, defer_params)

            defer_until_dt = None
            if defer_params.defer_until:
                defer_until_dt = parse_iso_timestamp(defer_params.defer_until)

            deferral_context = DeferralContext(
                thought_id=thought.thought_id,
                task_id=thought.source_task_id,
                reason=defer_params.reason,
                defer_until=defer_until_dt,
                priority=getattr(defer_params, "priority", "medium"),
                domain_hint=defer_params.domain_hint,
                reason_code=defer_params.reason_code,
                needs_category=defer_params.needs_category,
                secondary_needs_categories=defer_params.secondary_needs_categories,
                rights_basis=defer_params.rights_basis,
                metadata=metadata,
            )

            wa_sent = await self.bus_manager.wise.send_deferral(
                context=deferral_context, handler_name=self.__class__.__name__
            )

            if wa_sent:
                logger.info(f"Successfully sent deferral to WA service for thought {thought.thought_id}")
            else:
                logger.info(
                    f"Marked thought {thought.thought_id} as deferred, but no WA service available to deliver the deferral"
                )
            return wa_sent

        except Exception as e:
            self.logger.error(f"WiseAuthorityService deferral failed for thought {thought.thought_id}: {e}")
            return False

    def _build_deferral_metadata(
        self,
        thought: Thought,
        dispatch_context: DispatchContext,
        defer_params: Optional[DeferParams] = None,
    ) -> Dict[str, str]:
        """Build metadata dict for deferral context."""
        metadata = {
            "attempted_action": getattr(dispatch_context, "attempted_action", "unknown"),
            "max_rounds_reached": str(getattr(dispatch_context, "max_rounds_reached", False)),
        }

        if defer_params is not None:
            self._add_taxonomy_metadata(metadata, defer_params)
            self._add_context_metadata(metadata, defer_params.context)

        if thought.source_task_id:
            task = persistence.get_task_by_id(thought.source_task_id)
            if task and hasattr(task, "description"):
                metadata["task_description"] = task.description

        return metadata

    def _add_taxonomy_metadata(self, metadata: Dict[str, str], defer_params: DeferParams) -> None:
        """Add structured taxonomy fields to deferral metadata."""
        if defer_params.reason_code is not None:
            metadata["reason_code"] = defer_params.reason_code.value
        if defer_params.needs_category is not None:
            metadata["needs_category"] = defer_params.needs_category.value
        if defer_params.secondary_needs_categories:
            metadata["secondary_needs_categories"] = ",".join(
                category.value for category in defer_params.secondary_needs_categories
            )
        if defer_params.rights_basis:
            metadata["rights_basis"] = ",".join(defer_params.rights_basis)
        if defer_params.domain_hint is not None:
            metadata["domain_hint"] = defer_params.domain_hint.value

    def _add_context_metadata(self, metadata: Dict[str, str], context: Optional[Dict[str, Any]]) -> None:
        """Add ad hoc deferral context values to metadata."""
        for key, value in (context or {}).items():
            metadata[key] = self._stringify_metadata_value(value)

    def _stringify_metadata_value(self, value: Any) -> str:
        """Serialize context metadata values into strings for DeferralContext."""
        if isinstance(value, list):
            return ",".join(str(item) for item in value)
        return str(value)

    async def _send_error_deferral(self, thought: Thought, dispatch_context: DispatchContext) -> None:
        """Send deferral with parameter error context."""
        try:
            error_context = DeferralContext(
                thought_id=thought.thought_id,
                task_id=thought.source_task_id,
                reason="parameter_error",
                defer_until=None,
                priority=None,
                metadata={
                    "error_type": "parameter_parsing_error",
                    "attempted_action": getattr(dispatch_context, "attempted_action", "defer"),
                },
            )
            wa_sent = await self.bus_manager.wise.send_deferral(
                context=error_context, handler_name=self.__class__.__name__
            )
            if not wa_sent:
                logger.info(
                    f"Marked thought {thought.thought_id} as deferred (parameter error), but no WA service available"
                )
        except Exception as e:
            self.logger.error(f"Fallback deferral submission failed for thought {thought.thought_id}: {e}")

    def _mark_task_deferred(self, thought: Thought) -> None:
        """Mark parent task as deferred and notify the channel.

        The notification is sent for ANY channel (not just `api_*`). Downstream
        send_message routing handles whether a waiter exists — this ensures
        synchronous interact() callers receive a DEFER notification instead of
        hanging on an unanswered SPEAK until timeout. The deferral reason is
        intentionally NOT surfaced to the user (it's for WA review only).
        """
        parent_task_id = thought.source_task_id
        persistence.update_task_status(parent_task_id, TaskStatus.DEFERRED, "default", self.time_service)
        self.logger.info(f"Marked parent task {parent_task_id} as DEFERRED due to child thought deferral.")

        task = persistence.get_task_by_id(parent_task_id)
        if not task or not task.channel_id:
            return

        # Localize the defer notification. Task.preferred_language is the
        # record of truth (mirrored on context.preferred_language per
        # schemas/runtime/models.py:106). Fall back to the env-level
        # CIRIS_PREFERRED_LANGUAGE for tasks that pre-date the field or
        # are system-internal. The criterion that caught this (am
        # mh_v4_q07 U9 script_detection) is correct — the English
        # notification fails the Amharic-script check; the fix is to
        # ship the notification in the user's own language.
        task_lang = getattr(task, "preferred_language", None) or get_preferred_language()
        notification_body = get_string(
            task_lang,
            "agent.defer_check_panel",
            default="The agent chose to defer, check the wise authority panel if you are the setup user",
        )

        self.logger.info(f"Sending deferral notification to channel {task.channel_id} (lang={task_lang})")
        import asyncio

        notification_task = asyncio.create_task(
            self._send_notification(
                task.channel_id,
                notification_body,
            )
        )
        notification_task.add_done_callback(lambda t: t.exception() if t.done() and not t.cancelled() else None)
