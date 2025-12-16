import logging
from datetime import datetime
from typing import Any, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.schemas.actions import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.context import DeferralContext

logger = logging.getLogger(__name__)


class DeferHandler(BaseActionHandler):
    def _is_api_channel(self, channel_id: Optional[str]) -> bool:
        """Check if channel is an API channel (not Discord)."""
        if not channel_id:
            return False
        return channel_id.startswith("api_") or channel_id.startswith("ws:")

    async def _get_task_scheduler_service(self) -> Optional[Any]:
        """Get task scheduler service from registry."""
        try:
            if hasattr(self, "_service_registry") and self._service_registry:
                # Try to get from service registry
                return await self._service_registry.get_service(handler="task_scheduler", service_type="scheduler")
            else:
                logger.debug("No _service_registry available for task scheduler lookup")
        except Exception as e:
            logger.warning(f"Could not get task scheduler service: {e}")
        return None

    async def handle(
        self,
        result: ActionSelectionDMAResult,  # Updated to v1 result schema
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> Optional[str]:
        raw_params = result.action_parameters
        thought_id = thought.thought_id
        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

        final_thought_status = ThoughtStatus.DEFERRED
        action_performed_successfully = False
        follow_up_content_key_info = f"DEFER action for thought {thought_id}"

        defer_params_obj: Optional[DeferParams] = None
        try:
            # Check if params are already DeferParams
            if isinstance(raw_params, DeferParams):
                defer_params_obj = raw_params
            elif hasattr(raw_params, "model_dump"):
                # Try to convert from another Pydantic model
                defer_params_obj = DeferParams(**raw_params.model_dump())
            else:
                # Should not happen if DMA is working correctly
                raise ValueError(f"Expected DeferParams but got {type(raw_params)}")

            follow_up_content_key_info = f"Deferred thought {thought_id}. Reason: {defer_params_obj.reason}"

            # Check if this is a time-based deferral
            if defer_params_obj.defer_until:
                # Schedule the task for future reactivation
                scheduler_service = await self._get_task_scheduler_service()
                if scheduler_service:
                    try:
                        # Parse the defer_until timestamp - handle both 'Z' and '+00:00' formats
                        defer_str = defer_params_obj.defer_until
                        if defer_str.endswith("Z"):
                            defer_str = defer_str[:-1] + "+00:00"
                        defer_time = datetime.fromisoformat(defer_str)

                        # Create scheduled task
                        scheduled_task = await scheduler_service.schedule_deferred_task(
                            thought_id=thought_id,
                            task_id=thought.source_task_id,
                            defer_until=defer_params_obj.defer_until,
                            reason=defer_params_obj.reason,
                            context=defer_params_obj.context,
                        )

                        logger.info(
                            f"Created scheduled task {scheduled_task.task_id} to reactivate at {defer_params_obj.defer_until}"
                        )

                        # Add scheduled info to follow-up content
                        time_diff = defer_time - self.time_service.now()
                        hours = int(time_diff.total_seconds() / 3600)
                        minutes = int((time_diff.total_seconds() % 3600) / 60)

                        follow_up_content_key_info = (
                            f"Deferred thought {thought_id} until {defer_params_obj.defer_until} "
                            f"({hours}h {minutes}m from now). Reason: {defer_params_obj.reason}"
                        )
                    except Exception as e:
                        logger.error(f"Failed to schedule deferred task: {e}")
                        # Fall back to standard deferral

            # Use the wise authority bus for deferrals
            try:
                # Build metadata dict for additional context
                metadata = {
                    "attempted_action": getattr(dispatch_context, "attempted_action", "unknown"),
                    "max_rounds_reached": str(getattr(dispatch_context, "max_rounds_reached", False)),
                }

                if thought.source_task_id:
                    task = persistence.get_task_by_id(thought.source_task_id)
                    if task and hasattr(task, "description"):
                        metadata["task_description"] = task.description

                # Convert defer_until from ISO string to datetime if present
                defer_until_dt = None
                if defer_params_obj.defer_until:
                    defer_until_dt = datetime.fromisoformat(defer_params_obj.defer_until.replace("Z", "+00:00"))

                deferral_context = DeferralContext(
                    thought_id=thought_id,
                    task_id=thought.source_task_id,
                    reason=defer_params_obj.reason,
                    defer_until=defer_until_dt,
                    priority=getattr(defer_params_obj, "priority", "medium"),
                    metadata=metadata,
                )

                wa_sent = await self.bus_manager.wise.send_deferral(
                    context=deferral_context, handler_name=self.__class__.__name__
                )
                if not wa_sent:
                    logger.info(
                        f"Marked thought {thought_id} and task {thought.source_task_id} as deferred, but no WA service is available to deliver the deferral package"
                    )
                else:
                    logger.info(f"Successfully sent deferral to WA service for thought {thought_id}")
                action_performed_successfully = True
            except Exception as e:
                self.logger.error(f"WiseAuthorityService deferral failed for thought {thought_id}: {e}")
                # Deferral still considered processed even if WA fails

        except Exception as param_parse_error:
            self.logger.error(
                f"DEFER action params parsing error or unexpected structure. Type: {type(raw_params)}, Error: {param_parse_error}. Thought ID: {thought_id}"
            )
            follow_up_content_key_info = f"DEFER action failed: Invalid parameters ({type(raw_params)}) for thought {thought_id}. Error: {param_parse_error}"
            # Try to send deferral despite parameter error
            try:
                error_context = DeferralContext(
                    thought_id=thought_id,
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
                        f"Marked thought {thought_id} as deferred (parameter error), but no WA service is available to deliver the deferral package"
                    )
            except Exception as e_sink_fallback:
                self.logger.error(f"Fallback deferral submission failed for thought {thought_id}: {e_sink_fallback}")
                _action_performed_successfully = True

        persistence.update_thought_status(
            thought_id=thought_id,
            status=final_thought_status,  # Should be DEFERRED
            final_action=result,  # Pass the ActionSelectionDMAResult object directly
        )
        self.logger.info(
            f"Updated original thought {thought_id} to status {final_thought_status.value} for DEFER action. Info: {follow_up_content_key_info}"
        )
        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

        parent_task_id = thought.source_task_id
        # Update task status to deferred - "no kings" principle
        persistence.update_task_status(parent_task_id, TaskStatus.DEFERRED, "default", self.time_service)
        self.logger.info(f"Marked parent task {parent_task_id} as DEFERRED due to child thought deferral.")

        # Send deferral notification to API channels
        task = persistence.get_task_by_id(parent_task_id)
        if task and task.channel_id and self._is_api_channel(task.channel_id):
            self.logger.info(f"Sending deferral notification to API channel {task.channel_id}")
            await self._send_notification(
                task.channel_id, "The agent chose to defer, check the wise authority panel if you are the setup user"
            )

        return None
