import logging
import uuid
from typing import Any, Dict, Optional, Tuple, cast

from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.schemas.actions import ToolParams
from ciris_engine.schemas.adapters.tools import ToolExecutionResult
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
        # Validate parameters
        params_or_error = await self._validate_tool_params(result, thought, dispatch_context)
        if isinstance(params_or_error, str):
            return params_or_error  # Error follow-up ID
        params = params_or_error

        # Execute tool
        success, follow_up_info = await self._execute_tool(params, thought, dispatch_context)

        # Create follow-up thought
        return self._complete_tool_action(thought, result, params, success, follow_up_info)

    async def _validate_tool_params(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> ToolParams | str:
        """Validate and convert tool parameters. Returns ToolParams on success, follow_up_id on failure."""
        thought_id = thought.thought_id

        try:
            self.logger.debug(f"Raw result.action_parameters: {result.action_parameters}")
            self.logger.debug(f"Type: {type(result.action_parameters)}")

            processed_result = await self._decapsulate_secrets_in_params(result, "tool", thought_id)
            self.logger.debug(f"After decapsulation: {processed_result.action_parameters}")

            params = self._validate_and_convert_params(processed_result.action_parameters, ToolParams)

            if not isinstance(params, ToolParams):
                self.logger.error(
                    f"TOOL action params are not ToolParams model. Type: {type(params)}. Thought ID: {thought_id}"
                )
                follow_up_id = self.complete_thought_and_create_followup(
                    thought=thought,
                    follow_up_content=f"TOOL action failed: Invalid parameters type ({type(params)}) for thought {thought_id}.",
                    action_result=result,
                    status=ThoughtStatus.FAILED,
                )
                return follow_up_id or ""  # Return empty string if None (should not happen)

            return params

        except Exception as e:
            await self._handle_error(HandlerActionType.TOOL, dispatch_context, thought_id, e)
            follow_up_id = self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=f"TOOL action failed: {e}",
                action_result=result,
                status=ThoughtStatus.FAILED,
            )
            return follow_up_id or ""  # Return empty string if None (should not happen)

    async def _execute_tool(
        self, params: ToolParams, thought: Thought, dispatch_context: DispatchContext
    ) -> Tuple[bool, str]:
        """Execute the tool via tool bus. Returns (success, follow_up_info)."""
        thought_id = thought.thought_id
        _correlation_id = str(uuid.uuid4())

        try:
            self.logger.info(f"[TOOL_HANDLER] Executing tool: name={params.name}, parameters={params.parameters}")
            self.logger.info(f"[TOOL_HANDLER] Parameters type: {type(params.parameters)}")

            # Build tool parameters with channel and task context
            tool_params = self._build_tool_params(params, thought)

            # Execute via tool bus
            self.logger.info(f"[TOOL_HANDLER] Calling bus_manager.tool.execute_tool for '{params.name}'...")
            tool_result = await self.bus_manager.tool.execute_tool(
                tool_name=params.name, parameters=cast(JSONDict, tool_params), handler_name=self.__class__.__name__
            )

            self.logger.info(
                f"[TOOL_HANDLER] Tool result: success={tool_result.success}, status={tool_result.status}, error={tool_result.error}"
            )
            self._log_tool_result_data(tool_result)

            # Build result info
            if tool_result.success:
                self.logger.info(f"[TOOL_HANDLER] Tool '{params.name}' SUCCESS")
                return (
                    True,
                    f"Tool '{params.name}' executed successfully. Result: {tool_result.data or 'No result data'}",
                )
            else:
                self.logger.error(f"[TOOL_HANDLER] Tool '{params.name}' FAILED: {tool_result.error}")
                return False, f"Tool '{params.name}' failed: {tool_result.error or 'Unknown error'}"

        except Exception as e_tool:
            self.logger.error(
                f"[TOOL_HANDLER] EXCEPTION executing tool '{params.name}': {type(e_tool).__name__}: {e_tool}",
                exc_info=True,
            )
            await self._handle_error(HandlerActionType.TOOL, dispatch_context, thought_id, e_tool)
            return False, f"TOOL {params.name} execution failed: {str(e_tool)}"

    def _build_tool_params(self, params: ToolParams, thought: Thought) -> Dict[str, Any]:
        """Build tool parameters with channel and task context."""
        tool_params = dict(params.parameters)

        # Add channel_id if provided in action params but not in tool parameters
        if params.channel_id and "channel_id" not in tool_params:
            tool_params["channel_id"] = params.channel_id
            self.logger.debug(f"Added channel_id {params.channel_id} to tool parameters")

        # Add task_id for tools that need billing interaction_id (e.g., web_search)
        if thought.source_task_id and "task_id" not in tool_params:
            tool_params["task_id"] = thought.source_task_id
            self.logger.debug(f"Added task_id {thought.source_task_id} to tool parameters")

        return tool_params

    def _log_tool_result_data(self, tool_result: ToolExecutionResult) -> None:
        """Log tool result data for debugging."""
        if not tool_result.data:
            return

        import json

        try:
            data_str = json.dumps(tool_result.data, indent=2, default=str)
            self.logger.info(f"[TOOL_HANDLER] Tool result data:\n{data_str}")
        except Exception:
            self.logger.info(f"[TOOL_HANDLER] Tool result data: {tool_result.data}")

    def _complete_tool_action(
        self, thought: Thought, result: ActionSelectionDMAResult, params: ToolParams, success: bool, follow_up_info: str
    ) -> str:
        """Complete the tool action and create follow-up thought."""
        thought_id = thought.thought_id

        if success:
            follow_up_text = (
                f"CIRIS_FOLLOW_UP_THOUGHT: TOOL action {params.name} executed for thought {thought_id}. "
                f"Info: {follow_up_info}. Awaiting tool results or next steps. If task complete, use TASK_COMPLETE."
            )
        else:
            follow_up_text = (
                f"CIRIS_FOLLOW_UP_THOUGHT: TOOL action failed for thought {thought_id}. "
                f"Reason: {follow_up_info}. Review and determine next steps."
            )

        final_status = ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED

        follow_up_id = self.complete_thought_and_create_followup(
            thought=thought, follow_up_content=follow_up_text, action_result=result, status=final_status
        )

        if not follow_up_id:
            raise FollowUpCreationError("Failed to create follow-up thought")

        return follow_up_id
