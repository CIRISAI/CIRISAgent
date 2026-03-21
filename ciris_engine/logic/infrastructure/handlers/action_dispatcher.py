import datetime
import inspect
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.audit import AuditActionContext
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.runtime_control import ActionResponse, StepPoint
from ciris_engine.schemas.types import JSONDict

from . import BaseActionHandler
from .shared_helpers import extract_audit_parameters

logger = logging.getLogger(__name__)


class ActionDispatcher:
    def __init__(
        self,
        handlers: Dict[HandlerActionType, BaseActionHandler],
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        time_service: Any = None,
        audit_service: Any = None,
    ) -> None:
        """Initialize the ActionDispatcher with handler mappings and services."""
        self.handlers: Dict[HandlerActionType, BaseActionHandler] = handlers
        self.action_filter: Optional[Callable[[ActionSelectionDMAResult, JSONDict], Awaitable[bool] | bool]] = None
        self.telemetry_service = telemetry_service
        self._time_service = time_service or self._create_simple_time_service()
        self.audit_service = audit_service

        for action_type, handler_instance in self.handlers.items():
            logger.info(
                f"ActionDispatcher: Registered handler for {action_type.value}: {handler_instance.__class__.__name__}"
            )

    @staticmethod
    def _create_simple_time_service() -> Any:
        """Create a simple fallback time service."""

        class SimpleTimeService:
            def now(self) -> datetime.datetime:
                return datetime.datetime.now()

        return SimpleTimeService()

    def get_handler(self, action_type: HandlerActionType) -> Optional[BaseActionHandler]:
        """Get a handler by action type."""
        return self.handlers.get(action_type)

    @streaming_step(StepPoint.PERFORM_ACTION)
    @step_point(StepPoint.PERFORM_ACTION)
    async def _perform_action_step(self, thought_item: ProcessingQueueItem, result: Any, context: JSONDict) -> Any:
        """Step 9: Dispatch action to handler - streaming decorator for visibility."""
        return result

    @streaming_step(StepPoint.ACTION_COMPLETE)
    @step_point(StepPoint.ACTION_COMPLETE)
    async def _action_complete_step(
        self, thought_item: ProcessingQueueItem, dispatch_result: Any, **kwargs: Any
    ) -> Any:
        """Step 10: Action execution completed - streaming decorator for visibility.

        Accepts _coherence_data via kwargs for propagation to CIRISLens traces.
        """
        return dispatch_result

    @staticmethod
    def _extract_coherence_data(action_selection_result: Any) -> Dict[str, Any]:
        """Extract coherence data from ConscienceApplicationResult for trace propagation.

        Returns a dict with coherence/entropy check results, or empty dict for exempt actions
        or non-ConscienceApplicationResult inputs.
        """
        coherence_data: Dict[str, Any] = {}

        # Check if this is a ConscienceApplicationResult with conscience check data
        if not hasattr(action_selection_result, "coherence_check"):
            return coherence_data

        # Extract coherence check results
        coherence_check = getattr(action_selection_result, "coherence_check", None)
        if coherence_check:
            coherence_data["coherence_passed"] = getattr(coherence_check, "passed", None)
            coherence_data["coherence_score"] = getattr(coherence_check, "coherence_score", None)
            coherence_data["coherence_threshold"] = getattr(coherence_check, "threshold", None)
            coherence_data["coherence_reason"] = getattr(coherence_check, "message", None)

        # Extract entropy check results
        entropy_check = getattr(action_selection_result, "entropy_check", None)
        if entropy_check:
            coherence_data["entropy_passed"] = getattr(entropy_check, "passed", None)
            coherence_data["entropy_score"] = getattr(entropy_check, "entropy_score", None)
            coherence_data["entropy_threshold"] = getattr(entropy_check, "threshold", None)
            coherence_data["entropy_reason"] = getattr(entropy_check, "message", None)

        return coherence_data

    async def dispatch(
        self,
        action_selection_result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
    ) -> ActionResponse:
        """Dispatch the selected action to its registered handler."""
        # Extract action type and final action result
        final_action_result, action_type = self._extract_action_info(action_selection_result)

        # Apply action filter if configured
        await self._apply_action_filter(action_selection_result, dispatch_context, action_type, thought)

        # Get and validate handler
        handler = self._get_validated_handler(action_type)

        logger.info(
            f"Dispatching action {action_type.value} for thought {thought.thought_id} to handler {handler.__class__.__name__}"
        )

        # Wait for service registry readiness
        registry_failure = await self._check_registry_readiness(
            handler, dispatch_context, action_type, thought, final_action_result
        )
        if registry_failure:
            return registry_failure

        # Create processing queue item and signal action start
        thought_item = ProcessingQueueItem.from_thought(thought)
        await self._perform_action_step(
            thought_item,
            action_selection_result,
            dispatch_context.model_dump() if hasattr(dispatch_context, "model_dump") else {},
        )

        start_time = self._time_service.now()

        try:
            return await self._execute_handler(
                handler,
                final_action_result,
                thought,
                dispatch_context,
                action_type,
                thought_item,
                start_time,
                action_selection_result,
            )
        except Exception as e:
            return await self._handle_execution_error(
                e,
                handler,
                final_action_result,
                thought,
                dispatch_context,
                action_type,
                thought_item,
                start_time,
                action_selection_result,
            )

    def _extract_action_info(
        self, action_selection_result: ActionSelectionDMAResult
    ) -> Tuple[ActionSelectionDMAResult, HandlerActionType]:
        """Extract final action result and action type from result."""
        if hasattr(action_selection_result, "final_action"):
            final_action_result = action_selection_result.final_action
            action_type = final_action_result.selected_action
        else:
            final_action_result = action_selection_result
            action_type = action_selection_result.selected_action
        return final_action_result, action_type

    async def _apply_action_filter(
        self,
        result: ActionSelectionDMAResult,
        context: DispatchContext,
        action_type: HandlerActionType,
        thought: Thought,
    ) -> None:
        """Apply action filter if configured."""
        if not self.action_filter:
            return

        try:
            context_dict = context.model_dump() if hasattr(context, "model_dump") else vars(context)
            should_skip = self.action_filter(result, context_dict)
            if inspect.iscoroutine(should_skip):
                should_skip = await should_skip
            if should_skip:
                raise RuntimeError(
                    f"Action {action_type.value} for thought {thought.thought_id} was filtered. "
                    f"This should not happen - action_filter configuration error."
                )
        except Exception as filter_ex:
            logger.error(f"Action filter error for action {action_type.value}: {filter_ex}")

    def _get_validated_handler(self, action_type: HandlerActionType) -> BaseActionHandler:
        """Get handler and validate it exists."""
        handler = self.handlers.get(action_type)
        if not handler:
            raise RuntimeError(
                f"No handler registered for action type: {action_type.value}. "
                f"This is a critical configuration error - all 10 HandlerActionType values MUST have handlers. "
                f"Registered handlers: {list(self.handlers.keys())}"
            )
        return handler

    async def _check_registry_readiness(
        self,
        handler: BaseActionHandler,
        dispatch_context: DispatchContext,
        action_type: HandlerActionType,
        thought: Thought,
        final_action_result: ActionSelectionDMAResult,
    ) -> Optional[ActionResponse]:
        """Check service registry readiness. Returns failure response if not ready."""
        dependencies = getattr(handler, "dependencies", None)
        if not dependencies or not hasattr(dependencies, "wait_registry_ready"):
            return None

        ready = await dependencies.wait_registry_ready(timeout=getattr(dispatch_context, "registry_timeout", 30.0))
        if ready:
            return None

        # Registry not ready - create failure response
        self._ensure_audit_service(action_type, "registry timeout")

        timeout_params = extract_audit_parameters(action_type, final_action_result.action_parameters)
        timeout_params["error"] = "Service registry not ready"
        timeout_params["timeout"] = str(getattr(dispatch_context, "registry_timeout", 30.0))

        audit_context = AuditActionContext(
            thought_id=thought.thought_id,
            task_id=getattr(dispatch_context, "task_id", "unknown"),
            handler_name=handler.__class__.__name__,
            parameters=timeout_params,
        )
        audit_result = await self.audit_service.log_action(
            action_type=action_type, context=audit_context, outcome="error:RegistryNotReady"
        )
        logger.error(
            f"Service registry not ready for handler {handler.__class__.__name__}; action aborted. "
            f"Created audit entry {audit_result.entry_id}"
        )

        return ActionResponse(
            success=False,
            handler=handler.__class__.__name__,
            action_type=action_type.value,
            follow_up_thought_id=None,
            execution_time_ms=0.0,
            audit_data=audit_result,
        )

    async def _execute_handler(
        self,
        handler: BaseActionHandler,
        final_action_result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
        action_type: HandlerActionType,
        thought_item: ProcessingQueueItem,
        start_time: datetime.datetime,
        action_selection_result: Any = None,
    ) -> ActionResponse:
        """Execute the handler and create success response."""
        # Record telemetry
        await self._record_handler_invocation(action_type, handler)

        # Execute handler
        follow_up_thought_id = await handler.handle(final_action_result, thought, dispatch_context)

        # Calculate execution time
        execution_time_ms = (self._time_service.now() - start_time).total_seconds() * 1000.0

        # Determine outcome by checking the thought's final status
        # The handler updates the thought status to FAILED if execution fails
        outcome = "success"
        try:
            updated_thought = persistence.get_thought_by_id(
                thought.thought_id, occurrence_id=thought.agent_occurrence_id
            )
            if updated_thought and updated_thought.status == ThoughtStatus.FAILED:
                # Extract error message from follow-up info if available
                outcome = f"failure:{action_type.value}"
                logger.info(f"Thought {thought.thought_id} marked as FAILED, audit outcome: {outcome}")
        except Exception as e:
            logger.warning(f"Could not check thought status for audit outcome: {e}")

        # Create audit entry
        self._ensure_audit_service(action_type, "completion")
        audit_params = extract_audit_parameters(
            action_type, final_action_result.action_parameters, follow_up_thought_id
        )

        # For TOOL actions, capture the result from the follow-up thought's content
        if action_type == HandlerActionType.TOOL and follow_up_thought_id:
            try:
                follow_up_thought = persistence.get_thought_by_id(
                    follow_up_thought_id, occurrence_id=thought.agent_occurrence_id
                )
                if follow_up_thought and follow_up_thought.content:
                    follow_up_content = follow_up_thought.content
                    # Extract result from pattern: "Info: Tool '...' executed successfully. Result: ..."
                    if "Result:" in follow_up_content:
                        result_part = follow_up_content.split("Result:", 1)[-1].strip()
                        # Clean up trailing context
                        if ". Awaiting" in result_part:
                            result_part = result_part.split(". Awaiting", 1)[0].strip()
                        # Truncate if too long for audit
                        if len(result_part) > 500:
                            result_part = result_part[:500] + "..."
                        audit_params["tool_result"] = result_part
                        logger.debug(f"Captured tool_result from follow-up: {result_part[:100]}...")
                    elif "failed:" in follow_up_content.lower():
                        # Capture error message - extract from "Reason: ..." pattern
                        if "Reason:" in follow_up_content:
                            error_part = follow_up_content.split("Reason:", 1)[-1].strip()
                            if ". Review" in error_part:
                                error_part = error_part.split(". Review", 1)[0].strip()
                            audit_params["tool_result"] = f"FAILED: {error_part}"
                        else:
                            audit_params["tool_result"] = "FAILED: See follow-up thought for details"
            except Exception as e:
                logger.warning(f"Could not get follow-up thought for tool_result: {e}")

        audit_context = AuditActionContext(
            thought_id=thought.thought_id,
            task_id=getattr(dispatch_context, "task_id", "unknown"),
            handler_name=handler.__class__.__name__,
            parameters=audit_params,
        )
        audit_result = await self.audit_service.log_action(
            action_type=action_type, context=audit_context, outcome=outcome
        )
        logger.info(
            f"Created audit entry {audit_result.entry_id} for action {action_type.value} with outcome={outcome}"
        )

        # Build response
        action_params_dict = self._extract_action_params_dict(final_action_result)
        dispatch_result = ActionResponse(
            success=True,
            handler=handler.__class__.__name__,
            action_type=action_type.value,
            follow_up_thought_id=follow_up_thought_id,
            execution_time_ms=execution_time_ms,
            action_parameters=action_params_dict,
            audit_data=audit_result,
        )

        # Extract coherence data from conscience result for CIRISLens trace propagation
        coherence_data = self._extract_coherence_data(action_selection_result)
        await self._action_complete_step(thought_item, dispatch_result, _coherence_data=coherence_data)
        self._log_completion(handler, action_type, thought, follow_up_thought_id)
        await self._record_handler_completion(action_type)

        return dispatch_result

    async def _handle_execution_error(
        self,
        error: Exception,
        handler: BaseActionHandler,
        final_action_result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext,
        action_type: HandlerActionType,
        thought_item: ProcessingQueueItem,
        start_time: datetime.datetime,
        action_selection_result: ActionSelectionDMAResult,
    ) -> ActionResponse:
        """Handle handler execution error and create failure response."""
        execution_time_ms = (self._time_service.now() - start_time).total_seconds() * 1000.0

        logger.exception(
            f"Error executing handler {handler.__class__.__name__} for action {action_type.value} "
            f"on thought {thought.thought_id}: {error}"
        )

        # Create audit entry for failure
        self._ensure_audit_service(action_type, "failure")
        error_params = extract_audit_parameters(action_type, final_action_result.action_parameters, error=error)

        audit_context = AuditActionContext(
            thought_id=thought.thought_id,
            task_id=getattr(dispatch_context, "task_id", "unknown"),
            handler_name=handler.__class__.__name__,
            parameters=error_params,
        )
        audit_result = await self.audit_service.log_action(
            action_type=action_type, context=audit_context, outcome=f"error:{type(error).__name__}"
        )
        logger.info(f"Created audit entry {audit_result.entry_id} for failed action {action_type.value}")

        # Build failure response
        dispatch_result = ActionResponse(
            success=False,
            handler=handler.__class__.__name__,
            action_type=action_type.value,
            follow_up_thought_id=None,
            execution_time_ms=execution_time_ms,
            audit_data=audit_result,
        )

        # Extract coherence data from conscience result for CIRISLens trace propagation
        coherence_data = self._extract_coherence_data(action_selection_result)
        await self._action_complete_step(thought_item, dispatch_result, _coherence_data=coherence_data)
        await self._record_handler_error(action_type)
        self._update_thought_status_on_error(thought, handler, error, action_selection_result)

        return dispatch_result

    def _ensure_audit_service(self, action_type: HandlerActionType, context: str) -> None:
        """Ensure audit service is available."""
        if not self.audit_service:
            raise RuntimeError(
                f"Audit service not available for action {action_type.value} {context}. "
                f"All actions MUST be audited for production integrity."
            )

    def _extract_action_params_dict(self, result: ActionSelectionDMAResult) -> Dict[str, Any]:
        """Extract action parameters as a dict."""
        if not hasattr(result, "action_parameters") or not result.action_parameters:
            return {}

        ap = result.action_parameters
        if hasattr(ap, "model_dump"):
            return ap.model_dump()
        elif hasattr(ap, "dict"):
            return ap.dict()
        elif isinstance(ap, dict):
            return ap
        return {}

    def _log_completion(
        self, handler: BaseActionHandler, action_type: HandlerActionType, thought: Thought, follow_up_id: Optional[str]
    ) -> None:
        """Log handler completion."""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        msg = f"[{timestamp}] [DISPATCHER] Handler {handler.__class__.__name__} completed for action {action_type.value} on thought {thought.thought_id}"
        if follow_up_id:
            msg += f" - created follow-up thought {follow_up_id}"
        print(msg)

    async def _record_handler_invocation(self, action_type: HandlerActionType, handler: BaseActionHandler) -> None:
        """Record telemetry for handler invocation."""
        if not self.telemetry_service:
            return

        await self.telemetry_service.record_metric(
            f"handler_invoked_{action_type.value}",
            value=1.0,
            tags={
                "handler": handler.__class__.__name__,
                "action": action_type.value,
                "path_type": "hot",
                "source_module": "action_dispatcher",
            },
        )
        await self.telemetry_service.record_metric(
            "handler_invoked_total",
            value=1.0,
            tags={
                "handler": handler.__class__.__name__,
                "path_type": "hot",
                "source_module": "action_dispatcher",
            },
        )

    async def _record_handler_completion(self, action_type: HandlerActionType) -> None:
        """Record telemetry for handler completion."""
        if not self.telemetry_service:
            return
        await self.telemetry_service.record_metric(f"handler_completed_{action_type.value}")
        await self.telemetry_service.record_metric("handler_completed_total")

    async def _record_handler_error(self, action_type: HandlerActionType) -> None:
        """Record telemetry for handler error."""
        if not self.telemetry_service:
            return
        await self.telemetry_service.record_metric(f"handler_error_{action_type.value}")
        await self.telemetry_service.record_metric("handler_error_total")

    def _update_thought_status_on_error(
        self, thought: Thought, handler: BaseActionHandler, error: Exception, result: ActionSelectionDMAResult
    ) -> None:
        """Update thought status to FAILED on handler error."""
        try:
            persistence.update_thought_status(
                thought_id=thought.thought_id,
                status=ThoughtStatus.FAILED,
                final_action={
                    "error": f"Handler {handler.__class__.__name__} failed: {error}",
                    "original_result": result,
                },
            )
        except Exception as e_persist:
            logger.error(
                f"Failed to update thought {thought.thought_id} to FAILED after handler exception: {e_persist}"
            )
