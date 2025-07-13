from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.actions import ForgetParams
from ciris_engine.schemas.services.graph_core import GraphScope
from ciris_engine.logic.services.memory_service import MemoryOpStatus
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from typing import Any, Optional
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.logic import persistence
import logging
from pydantic import ValidationError

logger = logging.getLogger(__name__)

class ForgetHandler(BaseActionHandler):
    async def handle(self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext) -> Optional[str]:
        raw_params = result.action_parameters
        thought_id = thought.thought_id
        await self._audit_log(HandlerActionType.FORGET, dispatch_context.model_copy(update={"thought_id": thought_id}), outcome="start")
        params = raw_params
        if not isinstance(params, ForgetParams):
            try:
                # Try to convert from another Pydantic model
                if hasattr(params, 'model_dump'):
                    params = ForgetParams(**params.model_dump())
                else:
                    # Should not happen if DMA is working correctly
                    raise ValueError(f"Expected ForgetParams but got {type(params)}")
            except (ValidationError, ValueError) as e:
                logger.error(f"ForgetHandler: Invalid params dict: {e}")
                follow_up_content = f"This is a follow-up thought from a FORGET action performed on parent task {thought.source_task_id}. FORGET action failed: Invalid parameters. {e}. If the task is now resolved, the next step may be to mark the parent task complete with COMPLETE_TASK."
                
                # Use the proper method to complete thought and create follow-up
                follow_up_id = await self.complete_thought_and_create_followup(
                    thought=thought,
                    follow_up_content=follow_up_content,
                    action_result=result,
                    status=ThoughtStatus.FAILED
                )
                
                await self._audit_log(HandlerActionType.FORGET, dispatch_context.model_copy(update={"thought_id": thought_id}), outcome="failed")
                return follow_up_id
        if not self._can_forget(params, dispatch_context):
            logger.info("ForgetHandler: Permission denied or WA required for forget operation. Creating deferral.")
            follow_up_content = f"This is a follow-up thought from a FORGET action performed on parent task {thought.source_task_id}. FORGET action was not permitted. If the task is now resolved, the next step may be to mark the parent task complete with COMPLETE_TASK."
            
            # Use the proper method to complete thought and create follow-up
            follow_up_id = await self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=follow_up_content,
                action_result=result,
                status=ThoughtStatus.FAILED
            )
            
            await self._audit_log(
                HandlerActionType.FORGET,
                dispatch_context.model_copy(update={"thought_id": thought_id}),
                outcome="wa_denied"
            )
            return follow_up_id
        # Memory operations will use the memory bus

        node = params.node
        scope = node.scope
        if scope in (GraphScope.IDENTITY, GraphScope.ENVIRONMENT) and not getattr(dispatch_context, 'wa_authorized', False):
            follow_up_content = "FORGET action denied: WA authorization required"
            
            # Use the proper method to complete thought and create follow-up
            follow_up_id = await self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=follow_up_content,
                action_result=result,
                status=ThoughtStatus.FAILED
            )
            
            await self._audit_log(
                HandlerActionType.FORGET,
                dispatch_context,
                outcome="wa_denied",
            )
            return follow_up_id

        forget_result = await self.bus_manager.memory.forget(
            node=node,
            handler_name=self.__class__.__name__
        )
        await self._audit_forget_operation(params, dispatch_context, forget_result)
        success = forget_result.status == MemoryOpStatus.OK

        if success:
            follow_up_content = (
                f"CIRIS_FOLLOW_UP_THOUGHT: This is a follow-up thought from a FORGET action performed on parent task {thought.source_task_id}. Successfully forgot key '{node.id}' in scope {node.scope.value}. If the task is now resolved, the next step may be to mark the parent task complete with COMPLETE_TASK."
            )
        else:
            follow_up_content = (
                f"CIRIS_FOLLOW_UP_THOUGHT: This is a follow-up thought from a FORGET action performed on parent task {thought.source_task_id}. Failed to forget key '{node.id}' in scope {node.scope.value}. If the task is now resolved, the next step may be to mark the parent task complete with COMPLETE_TASK."
            )
        
        # Use the proper method to complete thought and create follow-up
        follow_up_id = await self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=follow_up_content,
            action_result=result,
            status=ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED
        )
        
        await self._audit_log(
            HandlerActionType.FORGET,
            dispatch_context.model_copy(update={"thought_id": thought_id}),
            outcome="success" if success else "failed",
        )
        
        return follow_up_id

    def _can_forget(self, params: ForgetParams, dispatch_context: DispatchContext) -> bool:
        if hasattr(params, 'node') and hasattr(params.node, 'scope'):
            scope = params.node.scope
            if scope in (GraphScope.IDENTITY, GraphScope.ENVIRONMENT):
                return getattr(dispatch_context, 'wa_authorized', False)
        return True

    async def _audit_forget_operation(self, params: ForgetParams, dispatch_context: DispatchContext, result: Any) -> None:
        if hasattr(params, 'no_audit') and params.no_audit:
            return

        audit_data = {
            "forget_key": params.node.id,
            "forget_scope": params.node.scope.value,
            "operation_result": str(result.status) if hasattr(result, 'status') else str(result),
            "timestamp": getattr(dispatch_context, 'event_timestamp', None),
            "thought_id": getattr(dispatch_context, 'thought_id', None)
        }

        await self._audit_log(
            HandlerActionType.FORGET,
            dispatch_context.model_copy(update=audit_data),
            outcome="forget_executed"
        )
