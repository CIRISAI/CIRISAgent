import logging
from datetime import datetime
from typing import Any, Optional

from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.actions import DeferParams
from ciris_engine.schemas.runtime.enums import ThoughtStatus, TaskStatus, HandlerActionType
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.services.context import DeferralContext
from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought

logger = logging.getLogger(__name__)

class DeferHandler(BaseActionHandler):
    async def _get_task_scheduler_service(self) -> Optional[Any]:
        """Get task scheduler service from registry."""
        try:
            if hasattr(self, '_service_registry') and self._service_registry:
                # Try to get from service registry
                return self._service_registry.get_service(
                    handler="task_scheduler",
                    service_type="scheduler"
                )
        except Exception as e:
            logger.warning(f"Could not get task scheduler service: {e}")
        return None
    
    async def handle(
        self,
        result: ActionSelectionDMAResult,  # Updated to v1 result schema
        thought: Thought,
        dispatch_context: DispatchContext
    ) -> None:
        raw_params = result.action_parameters
        thought_id = thought.thought_id
        await self._audit_log(HandlerActionType.DEFER, dispatch_context.model_copy(update={"thought_id": thought_id}), outcome="start")

        final_thought_status = ThoughtStatus.DEFERRED
        action_performed_successfully = False
        follow_up_content_key_info = f"DEFER action for thought {thought_id}"
        
        defer_params_obj: Optional[DeferParams] = None
        try:
            if isinstance(raw_params, dict):
                defer_params_obj = DeferParams(**raw_params)
            elif isinstance(raw_params, DeferParams): # Should not happen if ActionSelectionDMAResult.action_parameters is always dict
                defer_params_obj = raw_params
            else:
                raise ValueError(f"Unexpected type for deferral parameters: {type(raw_params)}")

            follow_up_content_key_info = f"Deferred thought {thought_id}. Reason: {defer_params_obj.reason}"

            # Check if this is a time-based deferral
            if defer_params_obj.defer_until:
                # Schedule the task for future reactivation
                scheduler_service = await self._get_task_scheduler_service()
                if scheduler_service:
                    try:
                        # Parse the defer_until timestamp - handle both 'Z' and '+00:00' formats
                        defer_str = defer_params_obj.defer_until
                        if defer_str.endswith('Z'):
                            defer_str = defer_str[:-1] + '+00:00'
                        defer_time = datetime.fromisoformat(defer_str)
                        
                        # Create scheduled task
                        scheduled_task = await scheduler_service.schedule_deferred_task(
                            thought_id=thought_id,
                            task_id=thought.source_task_id,
                            defer_until=defer_params_obj.defer_until,
                            reason=defer_params_obj.reason,
                            context=defer_params_obj.context
                        )
                        
                        logger.info(f"Created scheduled task {scheduled_task.task_id} to reactivate at {defer_params_obj.defer_until}")
                        
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
                    "attempted_action": getattr(dispatch_context, 'attempted_action', 'unknown'),
                    "max_rounds_reached": str(getattr(dispatch_context, 'max_rounds_reached', False))
                }
                
                if thought.source_task_id:
                    task = persistence.get_task_by_id(thought.source_task_id)
                    if task and hasattr(task, 'description'):
                        metadata["task_description"] = task.description
                
                deferral_context = DeferralContext(
                    thought_id=thought_id,
                    task_id=thought.source_task_id,
                    reason=defer_params_obj.reason,
                    defer_until=defer_params_obj.defer_until,
                    priority=getattr(defer_params_obj, 'priority', 'medium'),
                    metadata=metadata
                )
                
                await self.bus_manager.wise.send_deferral(
                    context=deferral_context,
                    handler_name=self.__class__.__name__
                )
            except Exception as e:
                self.logger.error(f"WiseAuthorityService deferral failed for thought {thought_id}: {e}")
                # Deferral still considered processed even if WA fails
                action_performed_successfully = True

        except Exception as param_parse_error:
            self.logger.error(f"DEFER action params parsing error or unexpected structure. Type: {type(raw_params)}, Error: {param_parse_error}. Thought ID: {thought_id}")
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
                        "attempted_action": getattr(dispatch_context, 'attempted_action', 'defer')
                    }
                )
                await self.bus_manager.wise.send_deferral(
                    context=error_context,
                    handler_name=self.__class__.__name__
                )
            except Exception as e_sink_fallback:
                self.logger.error(
                    f"Fallback deferral submission failed for thought {thought_id}: {e_sink_fallback}"
                )
                action_performed_successfully = True

        persistence.update_thought_status(
            thought_id=thought_id,
            status=final_thought_status,  # Should be DEFERRED
            final_action=result,  # Pass the ActionSelectionDMAResult object directly
        )
        self.logger.info(f"Updated original thought {thought_id} to status {final_thought_status.value} for DEFER action. Info: {follow_up_content_key_info}")
        await self._audit_log(HandlerActionType.DEFER, dispatch_context.model_copy(update={"thought_id": thought_id}), outcome="success")

        parent_task_id = thought.source_task_id
        if parent_task_id not in ["WAKEUP_ROOT", "SYSTEM_TASK", "DREAM_TASK"]:
            persistence.update_task_status(parent_task_id, TaskStatus.DEFERRED, self.time_service)
            self.logger.info(f"Marked parent task {parent_task_id} as DEFERRED due to child thought deferral.")

