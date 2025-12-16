import logging
import uuid
from typing import Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.schemas.actions import ToolParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class ToolHandler(BaseActionHandler):
    TOOL_RESULT_TIMEOUT = 30

    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        thought_id = thought.thought_id
        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging
        final_thought_status = ThoughtStatus.COMPLETED
        follow_up_content_key_info = f"TOOL action for thought {thought_id}"
        action_performed_successfully = False
        new_follow_up = None

        params: Optional[ToolParams] = None
        try:
            # Debug logging
            self.logger.debug(f"Raw result.action_parameters: {result.action_parameters}")
            self.logger.debug(f"Type: {type(result.action_parameters)}")

            processed_result = await self._decapsulate_secrets_in_params(result, "tool", thought_id)

            self.logger.debug(f"After decapsulation: {processed_result.action_parameters}")

            params = self._validate_and_convert_params(processed_result.action_parameters, ToolParams)
        except Exception as e:
            await self._handle_error(HandlerActionType.TOOL, dispatch_context, thought_id, e)
            final_thought_status = ThoughtStatus.FAILED
            follow_up_content_key_info = f"TOOL action failed: {e}"
            params = None

        # Tool handler will use the tool bus to execute tools
        if not isinstance(params, ToolParams):
            self.logger.error(
                f"TOOL action params are not ToolParams model. Type: {type(params)}. Thought ID: {thought_id}"
            )
            final_thought_status = ThoughtStatus.FAILED
            follow_up_content_key_info = (
                f"TOOL action failed: Invalid parameters type ({type(params)}) for thought {thought_id}."
            )
        else:
            _correlation_id = str(uuid.uuid4())
            try:
                # Debug logging
                self.logger.info(f"[TOOL_HANDLER] Executing tool: name={params.name}, parameters={params.parameters}")
                self.logger.info(f"[TOOL_HANDLER] Parameters type: {type(params.parameters)}")

                # If channel_id is provided in action params but not in tool parameters, add it
                # This helps tools that need channel context
                from typing import cast

                tool_params = dict(params.parameters)
                if params.channel_id and "channel_id" not in tool_params:
                    tool_params["channel_id"] = params.channel_id
                    self.logger.debug(f"Added channel_id {params.channel_id} to tool parameters")

                # Add task_id for tools that need billing interaction_id (e.g., web_search)
                if thought.source_task_id and "task_id" not in tool_params:
                    tool_params["task_id"] = thought.source_task_id
                    self.logger.debug(f"Added task_id {thought.source_task_id} to tool parameters")

                # Use the tool bus to execute the tool
                self.logger.info(f"[TOOL_HANDLER] Calling bus_manager.tool.execute_tool for '{params.name}'...")
                tool_result = await self.bus_manager.tool.execute_tool(
                    tool_name=params.name, parameters=cast(JSONDict, tool_params), handler_name=self.__class__.__name__
                )
                self.logger.info(
                    f"[TOOL_HANDLER] Tool result: success={tool_result.success}, status={tool_result.status}, error={tool_result.error}"
                )
                # Log full tool result data for debugging
                if tool_result.data:
                    import json

                    try:
                        data_str = json.dumps(tool_result.data, indent=2, default=str)
                        self.logger.info(f"[TOOL_HANDLER] Tool result data:\n{data_str}")
                    except Exception:
                        self.logger.info(f"[TOOL_HANDLER] Tool result data: {tool_result.data}")

                # tool_result is now ToolExecutionResult per protocol
                if tool_result.success:
                    action_performed_successfully = True
                    follow_up_content_key_info = (
                        f"Tool '{params.name}' executed successfully. Result: {tool_result.data or 'No result data'}"
                    )
                    self.logger.info(f"[TOOL_HANDLER] Tool '{params.name}' SUCCESS")
                else:
                    final_thought_status = ThoughtStatus.FAILED
                    follow_up_content_key_info = f"Tool '{params.name}' failed: {tool_result.error or 'Unknown error'}"
                    self.logger.error(f"[TOOL_HANDLER] Tool '{params.name}' FAILED: {tool_result.error}")
            except Exception as e_tool:
                self.logger.error(
                    f"[TOOL_HANDLER] EXCEPTION executing tool '{params.name}': {type(e_tool).__name__}: {e_tool}",
                    exc_info=True,
                )
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
                thought_type=ThoughtType.FOLLOW_UP,
            )
            persistence.add_thought(follow_up)
            follow_up_id: Optional[str] = follow_up.thought_id
        else:
            # Use centralized method for successful cases
            follow_up_id = self.complete_thought_and_create_followup(
                thought=thought, follow_up_content=follow_up_text, action_result=result
            )

        # NOTE: Audit logging removed - action_dispatcher handles centralized audit logging

        if not follow_up_id:
            raise FollowUpCreationError("Failed to create follow-up thought")

        return follow_up_id
