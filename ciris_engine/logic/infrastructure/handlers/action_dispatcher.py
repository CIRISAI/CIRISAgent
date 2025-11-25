import inspect
import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.types import JSONDict

from . import BaseActionHandler

logger = logging.getLogger(__name__)


class ActionDispatcher:
    def __init__(
        self,
        handlers: Dict[HandlerActionType, BaseActionHandler],
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        time_service: Any = None,
        audit_service: Any = None,
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
        self.action_filter: Optional[Callable[[ActionSelectionDMAResult, JSONDict], Awaitable[bool] | bool]] = None
        self.telemetry_service = telemetry_service
        self._time_service = time_service
        self.audit_service = audit_service

        # If no time service provided, use a simple fallback
        if not self._time_service:
            from datetime import datetime

            class SimpleTimeService:
                def now(self) -> datetime:
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
    async def _perform_action_step(self, thought_item: ProcessingQueueItem, result: Any, context: JSONDict) -> Any:
        """Step 9: Dispatch action to handler - streaming decorator for visibility."""
        # This is a pass-through that just enables streaming
        # The actual dispatch happens in the dispatch method
        return result

    @streaming_step(StepPoint.ACTION_COMPLETE)
    @step_point(StepPoint.ACTION_COMPLETE)
    async def _action_complete_step(self, thought_item: ProcessingQueueItem, dispatch_result: Any) -> Any:
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
    ) -> "ActionResponse":  # type: ignore[name-defined]
        """
        Dispatches the selected action to its registered handler.
        The handler is responsible for executing the action, updating thought status,
        and creating follow-up thoughts.
        """

        # Get the action type and extract final action
        # Handle both ConscienceApplicationResult (has final_action) and ActionSelectionDMAResult (has selected_action)
        if hasattr(action_selection_result, "final_action"):
            # Extract final_action from ConscienceApplicationResult
            final_action_result = action_selection_result.final_action
            action_type = final_action_result.selected_action
        else:
            # Already an ActionSelectionDMAResult
            final_action_result = action_selection_result
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
                    raise RuntimeError(
                        f"Action {action_type.value} for thought {thought.thought_id} was filtered. "
                        f"This should not happen - action_filter configuration error."
                    )
            except Exception as filter_ex:
                logger.error(f"Action filter error for action {action_type.value}: {filter_ex}")

        handler_instance = self.handlers.get(action_type)

        if not handler_instance:
            raise RuntimeError(
                f"No handler registered for action type: {action_type.value}. "
                f"This is a critical configuration error - all 10 HandlerActionType values MUST have handlers. "
                f"Registered handlers: {list(self.handlers.keys())}"
            )

        logger.info(
            f"Dispatching action {action_type.value} for thought {thought.thought_id} to handler {handler_instance.__class__.__name__}"
        )

        # Wait for service registry readiness before invoking the handler
        dependencies = getattr(handler_instance, "dependencies", None)
        if dependencies and hasattr(dependencies, "wait_registry_ready"):
            ready = await dependencies.wait_registry_ready(timeout=getattr(dispatch_context, "registry_timeout", 30.0))
            if not ready:
                # Service registry not ready - create failure audit and response
                from ciris_engine.schemas.runtime.audit import AuditActionContext
                from ciris_engine.schemas.services.runtime_control import ActionResponse

                if not self.audit_service:
                    raise RuntimeError(
                        f"Audit service not available for registry timeout on action {action_type.value}. "
                        f"All actions MUST be audited for production integrity."
                    )

                # Extract additional context for specific action types
                import json

                timeout_parameters = {
                    "error": "Service registry not ready",
                    "timeout": str(getattr(dispatch_context, "registry_timeout", 30.0)),
                }

                # For TOOL actions, include the tool name AND parameters in audit entry for searchability
                if action_type == HandlerActionType.TOOL and hasattr(final_action_result.action_parameters, "name"):
                    from ciris_engine.schemas.actions.parameters import ToolParams

                    if isinstance(final_action_result.action_parameters, ToolParams):
                        timeout_parameters["tool_name"] = final_action_result.action_parameters.name
                        timeout_parameters["tool_parameters"] = json.dumps(
                            final_action_result.action_parameters.parameters
                        )

                audit_context = AuditActionContext(
                    thought_id=thought.thought_id,
                    task_id=dispatch_context.task_id if hasattr(dispatch_context, "task_id") else "unknown",
                    handler_name=handler_instance.__class__.__name__,
                    parameters=timeout_parameters,
                )
                audit_result = await self.audit_service.log_action(
                    action_type=action_type, context=audit_context, outcome="error:RegistryNotReady"
                )
                logger.error(
                    f"Service registry not ready for handler {handler_instance.__class__.__name__}; action aborted. "
                    f"Created audit entry {audit_result.entry_id}"
                )

                return ActionResponse(
                    success=False,
                    handler=handler_instance.__class__.__name__,
                    action_type=action_type.value,
                    follow_up_thought_id=None,
                    execution_time_ms=0.0,
                    audit_data=audit_result,
                )
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

        # Capture start time for execution timing
        start_time = self._time_service.now()

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
            # Pass the final_action_result (ActionSelectionDMAResult) to the handler
            follow_up_thought_id = await handler_instance.handle(final_action_result, thought, dispatch_context)

            # Calculate execution time in milliseconds
            end_time = self._time_service.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000.0

            # Create centralized audit entry for this action completion (REQUIRED)
            from ciris_engine.schemas.runtime.audit import AuditActionContext
            from ciris_engine.schemas.services.runtime_control import ActionResponse

            if not self.audit_service:
                raise RuntimeError(
                    f"Audit service not available for action {action_type.value}. "
                    f"All actions MUST be audited for production integrity."
                )

            # Extract additional context for specific action types
            import json

            audit_parameters = {"follow_up_thought_id": follow_up_thought_id} if follow_up_thought_id else {}

            # For TOOL actions, include the tool name AND parameters in audit entry for searchability
            if action_type == HandlerActionType.TOOL and hasattr(final_action_result.action_parameters, "name"):
                from ciris_engine.schemas.actions.parameters import ToolParams

                if isinstance(final_action_result.action_parameters, ToolParams):
                    audit_parameters["tool_name"] = final_action_result.action_parameters.name
                    # JSON-serialize tool parameters for AuditActionContext (Dict[str, str] requirement)
                    audit_parameters["tool_parameters"] = json.dumps(final_action_result.action_parameters.parameters)
                    logger.debug(
                        f"Added tool info to audit: name={audit_parameters['tool_name']}, params={final_action_result.action_parameters.parameters}"
                    )
                else:
                    logger.debug(
                        f"action_parameters is not ToolParams, type: {type(final_action_result.action_parameters)}"
                    )
            elif action_type == HandlerActionType.TOOL:
                logger.debug("TOOL action but no 'name' attribute on action_parameters")

            logger.debug(f"Creating audit context with parameters: {audit_parameters}")

            audit_context = AuditActionContext(
                thought_id=thought.thought_id,
                task_id=dispatch_context.task_id if hasattr(dispatch_context, "task_id") else "unknown",
                handler_name=handler_instance.__class__.__name__,
                parameters=audit_parameters,
            )
            audit_result = await self.audit_service.log_action(
                action_type=action_type, context=audit_context, outcome="success"
            )
            logger.info(f"Created audit entry {audit_result.entry_id} for action {action_type.value}")

            # Step 10: ACTION_COMPLETE - Create typed ActionResponse
            dispatch_result = ActionResponse(
                success=True,
                handler=handler_instance.__class__.__name__,
                action_type=action_type.value,
                follow_up_thought_id=follow_up_thought_id,
                execution_time_ms=execution_time_ms,
                audit_data=audit_result,
            )
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

            # Return the success ActionResponse
            return dispatch_result

        except Exception as e:
            # Calculate execution time even for errors
            end_time = self._time_service.now()
            execution_time_ms = (end_time - start_time).total_seconds() * 1000.0

            logger.exception(
                f"Error executing handler {handler_instance.__class__.__name__} for action {action_type.value} on thought {thought.thought_id}: {e}"
            )

            # Create centralized audit entry for failed action (REQUIRED)
            from ciris_engine.schemas.runtime.audit import AuditActionContext
            from ciris_engine.schemas.services.runtime_control import ActionResponse

            if not self.audit_service:
                raise RuntimeError(
                    f"Audit service not available for failed action {action_type.value}. "
                    f"All actions MUST be audited, especially failures."
                )

            # Extract additional context for specific action types
            import json

            error_parameters = {"error": str(e), "error_type": type(e).__name__}

            # For TOOL actions, include the tool name AND parameters in audit entry for searchability
            if action_type == HandlerActionType.TOOL and hasattr(final_action_result.action_parameters, "name"):
                from ciris_engine.schemas.actions.parameters import ToolParams

                if isinstance(final_action_result.action_parameters, ToolParams):
                    error_parameters["tool_name"] = final_action_result.action_parameters.name
                    error_parameters["tool_parameters"] = json.dumps(final_action_result.action_parameters.parameters)

            audit_context = AuditActionContext(
                thought_id=thought.thought_id,
                task_id=dispatch_context.task_id if hasattr(dispatch_context, "task_id") else "unknown",
                handler_name=handler_instance.__class__.__name__,
                parameters=error_parameters,
            )
            audit_result = await self.audit_service.log_action(
                action_type=action_type, context=audit_context, outcome=f"error:{type(e).__name__}"
            )
            logger.info(f"Created audit entry {audit_result.entry_id} for failed action {action_type.value}")

            # Step 10: ACTION_COMPLETE - Create typed ActionResponse for failure
            dispatch_result = ActionResponse(
                success=False,
                handler=handler_instance.__class__.__name__,
                action_type=action_type.value,
                follow_up_thought_id=None,
                execution_time_ms=execution_time_ms,
                audit_data=audit_result,
            )
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

            # Return the failure ActionResponse
            return dispatch_result
