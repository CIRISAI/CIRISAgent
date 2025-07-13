import logging
from typing import Optional

from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.actions import ToolParams
from ciris_engine.schemas.runtime.enums import ThoughtStatus, HandlerActionType
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
import uuid

logger = logging.getLogger(__name__)

class ToolHandler(BaseActionHandler):
    TOOL_RESULT_TIMEOUT = 30

    async def handle(
        self,
        result: ActionSelectionDMAResult,
        thought: Thought,
        dispatch_context: DispatchContext
    ) -> Optional[str]:
        thought_id = thought.thought_id
        await self._audit_log(HandlerActionType.TOOL, dispatch_context, outcome="start")
        final_thought_status = ThoughtStatus.COMPLETED
        follow_up_content_key_info = f"TOOL action for thought {thought_id}"
        action_performed_successfully = False
        new_follow_up = None

        try:
            # Debug logging
            self.logger.debug(f"Raw result.action_parameters: {result.action_parameters}")
            self.logger.debug(f"Type: {type(result.action_parameters)}")
            
            processed_result = await self._decapsulate_secrets_in_params(result, "tool", thought_id)
            
            self.logger.debug(f"After decapsulation: {processed_result.action_parameters}")

            params: ToolParams = await self._validate_and_convert_params(processed_result.action_parameters, ToolParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.TOOL, dispatch_context, thought_id, e)
            final_thought_status = ThoughtStatus.FAILED
            follow_up_content_key_info = f"TOOL action failed: {e}"
            params = None

        # Tool handler will use the tool bus to execute tools
        if not isinstance(params, ToolParams):
            self.logger.error(
                f"TOOL action params are not ToolParams model. Type: {type(params)}. Thought ID: {thought_id}")
            final_thought_status = ThoughtStatus.FAILED
            follow_up_content_key_info = (
                f"TOOL action failed: Invalid parameters type ({type(params)}) for thought {thought_id}.")
        else:
            _correlation_id = str(uuid.uuid4())
            try:
                # Debug logging
                self.logger.debug(f"Executing tool: name={params.name}, parameters={params.parameters}")
                self.logger.info(f"[TOOL_HANDLER] Parameters type: {type(params.parameters)}")
                
                # Use the tool bus to execute the tool
                tool_result = await self.bus_manager.tool.execute_tool(
                    tool_name=params.name,
                    parameters=params.parameters,
                    handler_name=self.__class__.__name__
                )

                # tool_result is now ToolExecutionResult per protocol
                if tool_result.success:
                    action_performed_successfully = True
                    follow_up_content_key_info = (
                        f"Tool '{params.name}' executed successfully. Result: {tool_result.data or 'No result data'}"
                    )
                else:
                    final_thought_status = ThoughtStatus.FAILED
                    follow_up_content_key_info = f"Tool '{params.name}' failed: {tool_result.error or 'Unknown error'}"
            except Exception as e_tool:
                await self._handle_error(HandlerActionType.TOOL, dispatch_context, thought_id, e_tool)
                final_thought_status = ThoughtStatus.FAILED
                follow_up_content_key_info = f"TOOL {params.name} execution failed: {str(e_tool)}"

        follow_up_text = ""
        if action_performed_successfully and isinstance(params, ToolParams):
            follow_up_text = f"CIRIS_FOLLOW_UP_THOUGHT: TOOL action {params.name} executed for thought {thought_id}. Info: {follow_up_content_key_info}. Awaiting tool results or next steps. If task complete, use TASK_COMPLETE."
        else:
            follow_up_text = f"CIRIS_FOLLOW_UP_THOUGHT: TOOL action failed for thought {thought_id}. Reason: {follow_up_content_key_info}. Review and determine next steps."
        
        # If tool failed, update thought status to FAILED before creating follow-up
        if final_thought_status == ThoughtStatus.FAILED:
            persistence.update_thought_status(thought.thought_id, ThoughtStatus.FAILED)
            # Create follow-up manually since complete_thought_and_create_followup sets to COMPLETED
            from ciris_engine.logic.infrastructure.handlers.helpers import create_follow_up_thought
            from ciris_engine.schemas.runtime.enums import ThoughtType
            follow_up = create_follow_up_thought(
                parent=thought,
                time_service=self.time_service,
                content=follow_up_text,
                thought_type=ThoughtType.FOLLOW_UP
            )
            persistence.add_thought(follow_up)
            follow_up_id: Optional[str] = follow_up.thought_id
        else:
            # Use centralized method for successful cases
            follow_up_id = await self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=follow_up_text,
                action_result=result
            )
        
        await self._audit_log(HandlerActionType.TOOL, dispatch_context, outcome="success" if action_performed_successfully else "failed")
        
        if not follow_up_id:
            raise FollowUpCreationError("Failed to create follow-up thought")
        
        return follow_up_id
