import logging
import uuid
from typing import Any, Dict, Optional, Tuple, cast

from ciris_engine.logic.infrastructure.authorization.envelope_reader import resolve_envelope_for_task_id
from ciris_engine.logic.infrastructure.authorization.reviewed_action import (
    resolve_tool_name_via_bus,
    reviewed_action_fingerprint,
)
from ciris_engine.logic.infrastructure.handlers.base_handler import BaseActionHandler
from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError
from ciris_engine.schemas.actions import ToolParams
from ciris_engine.schemas.adapters.tools import ToolExecutionResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.task_envelope import ToolCallOrigin, ToolInvocationSubject
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)



#: The result summary stored with a tool thought for the task's action record:
#: enough for a ticket id or a short answer, never a whole payload.
_OUTCOME_MAX_CHARS = 400

class ToolHandler(BaseActionHandler):
    TOOL_RESULT_TIMEOUT = 30

    async def handle(
        self, result: ActionSelectionDMAResult, thought: Thought, dispatch_context: DispatchContext
    ) -> Optional[str]:
        # Execute only what was reviewed (#1366 item 10) — before decapsulation,
        # so the comparison is over secret references, as the consciences saw.
        refusal = self._refuse_if_changed_since_review(result, thought)
        if refusal is not None:
            return refusal

        # Validate parameters
        params_or_error = await self._validate_tool_params(result, thought, dispatch_context)
        if isinstance(params_or_error, str):
            return params_or_error  # Error follow-up ID
        params = params_or_error

        # Execute tool
        success, follow_up_info = await self._execute_tool(params, thought, dispatch_context)

        # Create follow-up thought
        return self._complete_tool_action(thought, result, params, success, follow_up_info)

    def _refuse_if_changed_since_review(self, result: ActionSelectionDMAResult, thought: Thought) -> Optional[str]:
        """Refuse a TOOL call that is not the call the consciences reviewed (#1366 item 10).

        Recomputes ``reviewed_action_fingerprint`` over what is about to run —
        with the tool name the bus would actually dispatch to, so an alias
        registered after review counts as a change — and compares it with the
        stamp the thought processor set when the consciences passed. Absent
        stamp (nothing was reviewed) or any difference refuses, fail-closed.

        Checked BEFORE secret decapsulation (references are what was reviewed)
        and BEFORE ``_build_tool_params`` adds ``channel_id`` (already hashed as
        ``ToolParams.channel_id``) and the handler-authoritative ``task_id``.

        The contract for a legitimate post-review change is refuse-and-re-review:
        the thought fails with a follow-up saying why, and that follow-up thought
        goes back through action selection and the consciences, which review the
        call as it now stands. Nothing here re-reviews in place.

        Returns the follow-up thought id on refusal, ``None`` to proceed.
        """
        reviewed = result.reviewed_action_hash
        params = result.action_parameters
        name = params.name if isinstance(params, ToolParams) else None
        resolved = resolve_tool_name_via_bus(self.bus_manager, name) if name is not None else None
        current = reviewed_action_fingerprint(result, resolved_tool_name=resolved)
        if reviewed is not None and current == reviewed:
            return None

        if reviewed is None:
            why = "this tool call was never passed by the consciences (no review fingerprint)"
        elif current is None:
            why = "the action is no longer a reviewable tool call"
        elif resolved != name:
            why = f"tool '{name}' now resolves to '{resolved}', which is not the tool that was reviewed"
        else:
            why = "the tool, arguments or target changed after the consciences reviewed it"
        self.logger.error(
            "REVIEW-INTEGRITY: REFUSED tool %r for thought %s (task %s): %s. reviewed=%s executing=%s. "
            "Not executed; the follow-up thought re-reviews the call as it stands.",
            name,
            thought.thought_id,
            thought.source_task_id,
            why,
            reviewed,
            current,
        )
        follow_up_id = self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=self._localized_followup(
                "tool_action_failed_with_reason",
                default=f"TOOL action failed: {why}",
                reason=f"not executed — {why}. Re-decide the action; it will be reviewed again.",
            ),
            action_result=result,
            status=ThoughtStatus.FAILED,
        )
        return follow_up_id or ""

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
                    follow_up_content=self._localized_followup(
                        "tool_invalid_params",
                        default=f"TOOL action failed: Invalid parameters type ({type(params)}) for thought {thought_id}.",
                        params_type=str(type(params)),
                        thought_id=thought_id,
                    ),
                    action_result=result,
                    status=ThoughtStatus.FAILED,
                )
                return follow_up_id or ""  # Return empty string if None (should not happen)

            return params

        except Exception as e:
            await self._handle_error(HandlerActionType.TOOL, dispatch_context, thought_id, e)
            follow_up_id = self.complete_thought_and_create_followup(
                thought=thought,
                follow_up_content=self._localized_followup(
                    "tool_action_failed_with_reason",
                    default=f"TOOL action failed: {e}",
                    reason=str(e),
                ),
                action_result=result,
                status=ThoughtStatus.FAILED,
            )
            return follow_up_id or ""  # Return empty string if None (should not happen)

    def _build_invocation_subject(
        self, thought: Thought, dispatch_context: DispatchContext
    ) -> ToolInvocationSubject:
        """Build the authorization subject for this tool call (CIRISAgent#938).

        This is the last point before ``ToolBus.execute_tool`` at which task and
        thought identity are available — and until now they were dropped here.
        The envelope is *read*, never minted: ``resolve_envelope_for_task_id``
        has no minting surface, and a missing envelope resolves to ``None``,
        which is a denial to Phase 2 rather than "unconstrained".
        """
        task_id = thought.source_task_id or dispatch_context.task_id
        envelope = resolve_envelope_for_task_id(task_id, thought.agent_occurrence_id)
        if envelope is None:
            self.logger.debug(
                "[TOOL_HANDLER] No task envelope bound to task %s; tool call proceeds unauthorized "
                "(Phase 1 has no gate — see CIRISAgent#938).",
                task_id,
            )
        return ToolInvocationSubject.for_task(
            task_id=task_id,
            thought_id=thought.thought_id,
            handler_name=self.__class__.__name__,
            origin=ToolCallOrigin.REASONING,
            agent_occurrence_id=thought.agent_occurrence_id,
            envelope=envelope,
        )

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

            # The subject the Phase 2 tool gate will authorize (CIRISAgent#938).
            subject = self._build_invocation_subject(thought, dispatch_context)

            # Execute via tool bus
            self.logger.info(f"[TOOL_HANDLER] Calling bus_manager.tool.execute_tool for '{params.name}'...")
            tool_result = await self.bus_manager.tool.execute_tool(
                tool_name=params.name,
                parameters=cast(JSONDict, tool_params),
                handler_name=self.__class__.__name__,
                subject=subject,
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
        """Build tool parameters with channel and task context.

        **Task identity is handler-authoritative** (CIRISAgent#938). It used to
        be injected only ``if "task_id" not in tool_params``, which meant a
        model-authored ``task_id`` was never overwritten — the model could name
        whichever task it liked, and consumers that key on it (``authorize_spend``
        reads ``task_id`` from tool parameters) were reading a model-supplied
        value. The whole premise of the task envelope is that the enforcement
        point can key policy on a *trustworthy* task identity, so the handler
        now always sets it and logs any attempt to supply one.

        When the thought has no source task there is nothing to vouch for, so a
        model-supplied ``task_id`` is dropped rather than passed through: an
        unverifiable identity is worse than none for anything that authorizes on
        it.
        """
        tool_params = dict(params.parameters)

        # Add channel_id if provided in action params but not in tool parameters
        if params.channel_id and "channel_id" not in tool_params:
            tool_params["channel_id"] = params.channel_id
            self.logger.debug(f"Added channel_id {params.channel_id} to tool parameters")

        model_supplied_task_id = tool_params.get("task_id")
        if thought.source_task_id:
            if model_supplied_task_id is not None and model_supplied_task_id != thought.source_task_id:
                self.logger.warning(
                    "[TOOL_HANDLER] Tool call supplied task_id=%r; overriding with the handler-authoritative "
                    "source task %r (CIRISAgent#938 — task identity is never model-authored).",
                    model_supplied_task_id,
                    thought.source_task_id,
                )
            tool_params["task_id"] = thought.source_task_id
        elif model_supplied_task_id is not None:
            self.logger.warning(
                "[TOOL_HANDLER] Tool call supplied task_id=%r but thought %s has no source task; "
                "dropping it rather than passing an unverifiable identity (CIRISAgent#938).",
                model_supplied_task_id,
                thought.thought_id,
            )
            tool_params.pop("task_id", None)

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
            follow_up_text = self._localized_followup(
                "tool_followup_success",
                default=(
                    f"TOOL action {params.name} executed for thought {thought_id}. "
                    f"Result summary: {follow_up_info}. Awaiting tool results or next steps. If task complete, use TASK_COMPLETE."
                ),
                tool_name=params.name,
                thought_id=thought_id,
                summary=follow_up_info,
            )
        else:
            follow_up_text = self._localized_followup(
                "tool_followup_failure",
                default=(
                    f"TOOL action failed for thought {thought_id}. "
                    f"Reason: {follow_up_info}. Review and determine next steps."
                ),
                thought_id=thought_id,
                reason=follow_up_info,
            )

        final_status = ThoughtStatus.COMPLETED if success else ThoughtStatus.FAILED

        follow_up_id = self.complete_thought_and_create_followup(
            thought=thought,
            follow_up_content=follow_up_text,
            action_result=result,
            status=final_status,
            outcome=follow_up_info[:_OUTCOME_MAX_CHARS],
        )

        if not follow_up_id:
            raise FollowUpCreationError("Failed to create follow-up thought")

        return follow_up_id
