import inspect
import logging
from typing import Awaitable, Callable, Dict, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.runtime_control import StepPoint

from . import BaseActionHandler

logger = logging.getLogger(__name__)


class ActionDispatcher:
    def __init__(
        self,
        handlers: Dict[HandlerActionType, BaseActionHandler],
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        time_service=None,
        audit_service=None,
    ) -> None:
        """
        Initializes the ActionDispatcher with a map of action types to their handler instances.

        Args:
            handlers: A dictionary mapping HandlerActionType to an instance of a BaseActionHandler subclass.
            telemetry_service: Optional telemetry service for metrics collection.
            time_service: Optional time service for step decorators.
            audit_service: Optional audit service for centralized action auditing.
        """
        self.handlers: Dict[HandlerActionType, BaseActionHandler] = handlers
        self.action_filter: Optional[Callable[[ActionSelectionDMAResult, dict], Awaitable[bool] | bool]] = None
        self.telemetry_service = telemetry_service
        self._time_service = time_service
        self.audit_service = audit_service

        # If no time service provided, use a simple fallback
        if not self._time_service:
            from datetime import datetime

            class SimpleTimeService:
                def now(self):
                    return datetime.now()

            self._time_service = SimpleTimeService()

        for action_type, handler_instance in self.handlers.items():
            logger.info(
                f"ActionDispatcher: Registered handler for {action_type.value}: {handler_instance.__class__.__name__}"
            )

    def get_handler(self, action_type: HandlerActionType) -> Optional[BaseActionHandler]:
        """Get a handler by action type."""
        return self.handlers.get(action_type)

    @streaming_step(StepPoint.PERFORM_ACTION)
    @step_point(StepPoint.PERFORM_ACTION)
    async def _perform_action_step(self, thought_item: ProcessingQueueItem, result, context: dict):
        """Step 9: Dispatch action to handler - streaming decorator for visibility."""
        # This is a pass-through that just enables streaming
        # The actual dispatch happens in the dispatch method
        return result

    @streaming_step(StepPoint.ACTION_COMPLETE)
    @step_point(StepPoint.ACTION_COMPLETE)
    async def _action_complete_step(self, thought_item: ProcessingQueueItem, dispatch_result):
        """Step 10: Action execution completed - streaming decorator for visibility."""
        # This marks the completion of action execution
        return dispatch_result

    async def dispatch(
        self,
        action_selection_result: ActionSelectionDMAResult,
        thought: Thought,  # The original thought that led to this action
        dispatch_context: DispatchContext,  # Context from the caller (e.g., channel_id, author_name, services)
        # Services are now expected to be part of ActionHandlerDependencies,
        # but dispatch_context can still carry event-specific data.
    ) -> None:
        """
        Dispatches the selected action to its registered handler.
        The handler is responsible for executing the action, updating thought status,
        and creating follow-up thoughts.
        """

        # Get the action type (already typed as HandlerActionType in schema)
        action_type = action_selection_result.selected_action

        if self.action_filter:
            try:
                # Convert DispatchContext to dict for action_filter compatibility
                context_dict = (
                    dispatch_context.model_dump() if hasattr(dispatch_context, "model_dump") else vars(dispatch_context)
                )
                should_skip = self.action_filter(action_selection_result, context_dict)
                if inspect.iscoroutine(should_skip):
                    should_skip = await should_skip
                if should_skip:
                    logger.info(
                        f"ActionDispatcher: action {action_type.value} for thought {thought.thought_id} skipped by filter"
                    )
                    return
            except Exception as filter_ex:
                logger.error(f"Action filter error for action {action_type.value}: {filter_ex}")

        handler_instance = self.handlers.get(action_type)

        if not handler_instance:
            logger.error(
                f"No handler registered for action type: {action_type.value}. Thought ID: {thought.thought_id}"
            )
            # Fallback: Mark thought as FAILED
            try:
                persistence.update_thought_status(
                    thought_id=thought.thought_id,
                    status=ThoughtStatus.FAILED,
                    final_action={
                        "error": f"No handler for action {action_type.value}",
                        "original_result": action_selection_result,
                    },
                )
                # Consider creating a follow-up error thought here if handlers normally do
            except Exception as e_persist:
                logger.error(
                    f"Failed to update thought {thought.thought_id} to FAILED after no handler found: {e_persist}"
                )
            return

        logger.info(
            f"Dispatching action {action_type.value} for thought {thought.thought_id} to handler {handler_instance.__class__.__name__}"
        )

        # Wait for service registry readiness before invoking the handler
        dependencies = getattr(handler_instance, "dependencies", None)
        if dependencies and hasattr(dependencies, "wait_registry_ready"):
            ready = await dependencies.wait_registry_ready(timeout=getattr(dispatch_context, "registry_timeout", 30.0))
            if not ready:
                logger.error(
                    f"Service registry not ready for handler {handler_instance.__class__.__name__}; action aborted"
                )
                return
        # Logging handled by logger.info above

        # Create a ProcessingQueueItem for step streaming
        # Always use from_thought since it's a classmethod
        thought_item = ProcessingQueueItem.from_thought(thought)

        # Step 9: PERFORM_ACTION - Signal that we're dispatching the action
        await self._perform_action_step(
            thought_item,
            action_selection_result,
            dispatch_context.model_dump() if hasattr(dispatch_context, "model_dump") else {},
        )

        try:
            # Record handler invocation as HOT PATH
            if self.telemetry_service:
                await self.telemetry_service.record_metric(
                    f"handler_invoked_{action_type.value}",
                    value=1.0,
                    tags={
                        "handler": handler_instance.__class__.__name__,
                        "action": action_type.value,
                        "path_type": "hot",
                        "source_module": "action_dispatcher",
                    },
                )
                await self.telemetry_service.record_metric(
                    "handler_invoked_total",
                    value=1.0,
                    tags={
                        "handler": handler_instance.__class__.__name__,
                        "path_type": "hot",
                        "source_module": "action_dispatcher",
                    },
                )

            # The handler's `handle` method will take care of everything.
            follow_up_thought_id = await handler_instance.handle(action_selection_result, thought, dispatch_context)

            # Create centralized audit entry for this action completion
            audit_result = None
            if self.audit_service:
                try:
                    from ciris_engine.schemas.audit.core import AuditEventType

                    audit_result = await self.audit_service.log_event(
                        event_type=str(AuditEventType(f"handler_action_{action_type.value}")),
                        event_data={
                            "handler_name": handler_instance.__class__.__name__,
                            "thought_id": thought.thought_id,
                            "task_id": dispatch_context.task_id if hasattr(dispatch_context, 'task_id') else None,
                            "action": action_type.value,
                            "outcome": "success",
                            "follow_up_thought_id": follow_up_thought_id,
                        },
                    )
                    logger.info(f"Created audit entry {audit_result.entry_id} for action {action_type.value}")
                except Exception as audit_error:
                    logger.error(f"Failed to create audit entry for action {action_type.value}: {audit_error}")

            # Step 10: ACTION_COMPLETE - Signal that action execution is complete
            dispatch_result = {
                "follow_up_thought_id": follow_up_thought_id,
                "action_type": action_type.value,
                "handler": handler_instance.__class__.__name__,
                "success": True,
                "audit_entry_id": audit_result.entry_id if audit_result else None,
                "audit_sequence_number": audit_result.sequence_number if audit_result else None,
                "audit_entry_hash": audit_result.entry_hash if audit_result else None,
                "audit_signature": audit_result.signature if audit_result else None,
            }
            await self._action_complete_step(thought_item, dispatch_result)

            # Log completion with follow-up thought ID if available
            import datetime

            timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            completion_msg = f"[{timestamp}] [DISPATCHER] Handler {handler_instance.__class__.__name__} completed for action {action_type.value} on thought {thought.thought_id}"
            if follow_up_thought_id:
                completion_msg += f" - created follow-up thought {follow_up_thought_id}"
            print(completion_msg)

            # Record successful handler completion
            if self.telemetry_service:
                await self.telemetry_service.record_metric(f"handler_completed_{action_type.value}")
                await self.telemetry_service.record_metric("handler_completed_total")
        except Exception as e:
            logger.exception(
                f"Error executing handler {handler_instance.__class__.__name__} for action {action_type.value} on thought {thought.thought_id}: {e}"
            )

            # Create centralized audit entry for failed action
            audit_result = None
            if self.audit_service:
                try:
                    from ciris_engine.schemas.audit.core import AuditEventType

                    audit_result = await self.audit_service.log_event(
                        event_type=str(AuditEventType(f"handler_action_{action_type.value}")),
                        event_data={
                            "handler_name": handler_instance.__class__.__name__,
                            "thought_id": thought.thought_id,
                            "task_id": dispatch_context.task_id if hasattr(dispatch_context, 'task_id') else None,
                            "action": action_type.value,
                            "outcome": f"error:{type(e).__name__}",
                            "error": str(e),
                        },
                    )
                    logger.info(f"Created audit entry {audit_result.entry_id} for failed action {action_type.value}")
                except Exception as audit_error:
                    logger.error(f"Failed to create audit entry for failed action {action_type.value}: {audit_error}")

            # Step 10: ACTION_COMPLETE - Signal that action execution failed
            dispatch_result = {
                "follow_up_thought_id": None,
                "action_type": action_type.value,
                "handler": handler_instance.__class__.__name__,
                "success": False,
                "error": str(e),
                "audit_entry_id": audit_result.entry_id if audit_result else None,
                "audit_sequence_number": audit_result.sequence_number if audit_result else None,
                "audit_entry_hash": audit_result.entry_hash if audit_result else None,
                "audit_signature": audit_result.signature if audit_result else None,
            }
            await self._action_complete_step(thought_item, dispatch_result)

            # Record handler error
            if self.telemetry_service:
                await self.telemetry_service.record_metric(f"handler_error_{action_type.value}")
                await self.telemetry_service.record_metric("handler_error_total")
            try:
                persistence.update_thought_status(
                    thought_id=thought.thought_id,
                    status=ThoughtStatus.FAILED,
                    final_action={
                        "error": f"Handler {handler_instance.__class__.__name__} failed: {str(e)}",
                        "original_result": action_selection_result,
                    },
                )
            except Exception as e_persist:
                logger.error(
                    f"Failed to update thought {thought.thought_id} to FAILED after handler exception: {e_persist}"
                )
