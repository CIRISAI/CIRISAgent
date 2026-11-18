"""Forget-Specific Action Selection PDMA (FSASPDMA).

The second pass after ASPDMA selects FORGET (#1027). ASPDMA chooses the verb
and nothing else; this step is shown how the graph is addressed and which nodes
already exist, and names the node to remove.

Why FORGET needed one more than any other verb: it is the destructive memory
verb, and it shared MEMORIZE's addressing problem. A FORGET removes a whole
node and its edges. Aimed at an invented id it removes nothing and the memory
service still reports success, so the agent tells a person their information is
gone when it is not. ASPDMA also had no way to state the node's scope — the
conversion hardcoded ``local`` — so a node stored anywhere else could not be
reached at all.

Returns the same ActionSelectionDMAResult as ASPDMA: FORGET with a node, SPEAK,
or PONDER. NO HEALING, as in MSASPDMA: a FORGET with no node becomes a PONDER,
never a guessed id.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from pydantic import ConfigDict, Field

from ciris_engine.logic.formatters.wa_approval import (
    format_wa_approval_block,
    format_wa_approval_facts,
    wa_authorization_of,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.actions.parameters import (
    ForgetParams,
    PonderParams,
    SpeakParams,
)
from ciris_engine.schemas.dma.msaspdma import CandidateNode
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.dma.sent_prompts import PromptCarrier, carry_sent_prompts
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import (
    GraphNode,
    GraphNodeAttributes,
    GraphScope,
    NodeType,
)
from ciris_engine.schemas.types import JSONDict

from .msaspdma import MSASPDMAEvaluator

logger = logging.getLogger(__name__)


class FSASPDMALLMResult(PromptCarrier):
    """Structured output for the forget-specific second pass."""

    final_action: str = Field(..., description="FORGET, SPEAK or PONDER")
    node_id: Optional[str] = Field(None, description="Node id to remove (required for FORGET)")
    node_scope: Optional[str] = Field(None, description="Graph scope the node is stored in (required for FORGET)")
    reason: Optional[str] = Field(None, description="Why this node is being forgotten (required for FORGET)")
    message: Optional[str] = Field(None, description="What to say (required for SPEAK)")
    questions: List[str] = Field(default_factory=list, description="What to reconsider (PONDER)")
    reasoning: str = Field("", description="Why this is the right node, or why the switch")

    model_config = ConfigDict(extra="forbid")


class FSASPDMAEvaluator(MSASPDMAEvaluator):
    """Second-pass forget evaluator: the shared graph guide + the nodes that exist."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prompt_template_name = "fsaspdma"

    def compose_messages(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
    ) -> List[JSONDict]:
        """Compose the FSASPDMA prompt message list."""
        self._sync_language_from_context(context)
        authorization = wa_authorization_of(context)
        system_message = "\n\n".join(
            filter(
                None,
                (
                    self._require_prompt_value("system_guidance_header"),
                    self._graph_block("memory_model"),
                    self._graph_block("addressing_convention"),
                    self._graph_block("scope_convention"),
                    self._require_prompt_value("memory_prohibitions"),
                    self._require_prompt_value("evaluation_steps"),
                    self._require_prompt_value("response_format"),
                    self._require_prompt_value("closing_reminder"),
                    # The identity/environment prohibition is decidable only with
                    # the approval, or the fact that there is none, in view —
                    # the same two blocks MSASPDMA carries (#1320).
                    format_wa_approval_block(authorization, language=self.prompt_loader.language),
                    format_wa_approval_facts(authorization, language=self.prompt_loader.language),
                ),
            )
        ).strip()
        user_message = self._require_prompt_value("context_integration").format(
            original_thought_content=getattr(getattr(original_thought, "content", None), "text", "") or "",
            aspdma_reasoning=aspdma_result.rationale or "",
            candidate_nodes=self._format_candidates(self.candidate_nodes_from_context(context)),
        )
        return self._frame_messages(system_message, user_message)

    def _convert_forget(
        self,
        llm_result: FSASPDMALLMResult,
        channel_id: Optional[str],
        candidates: List[CandidateNode],
        resource_usage: Optional[JSONDict] = None,
    ) -> ActionSelectionDMAResult:
        """Turn the second-pass verdict into a typed action."""
        action = (llm_result.final_action or "").strip().upper()
        rationale = f"FSASPDMA: {llm_result.reasoning}"

        if action == "SPEAK" and llm_result.message:
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.SPEAK,
                action_parameters=SpeakParams(channel_id=channel_id, content=llm_result.message),
                rationale=rationale,
                resource_usage=resource_usage,
            )

        if action == "FORGET" and llm_result.node_id:
            # A node that exists is forgotten as it is stored. The verdict's own
            # scope is used only for a node the snapshot did not list.
            known = next((c for c in candidates if c.node_id == llm_result.node_id), None)
            node = GraphNode(
                id=llm_result.node_id,
                type=self._coerce_node_type(known.node_type if known else None, NodeType.OBSERVATION),
                scope=self._coerce_scope(known.scope if known else llm_result.node_scope, GraphScope.LOCAL),
                attributes=GraphNodeAttributes(created_by="agent"),
            )
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.FORGET,
                action_parameters=ForgetParams(
                    channel_id=channel_id,
                    node=node,
                    reason=llm_result.reason or llm_result.reasoning or "No reason provided",
                ),
                rationale=rationale,
                resource_usage=resource_usage,
            )

        questions = llm_result.questions if action == "PONDER" else []
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(
                questions=questions
                or [
                    "The forget second pass did not name a node.",
                    f"It returned final_action={llm_result.final_action!r}.",
                    "Which existing node holds what should be forgotten?",
                ],
            ),
            rationale=(rationale if action == "PONDER" else "FSASPDMA: unusable second-pass result — reconsidering"),
            resource_usage=resource_usage,
        )

    async def evaluate_forget_action(
        self,
        aspdma_result: ActionSelectionDMAResult,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
    ) -> ActionSelectionDMAResult:
        """Name the node a selected FORGET removes."""
        if aspdma_result.selected_action != HandlerActionType.FORGET:
            raise ValueError(f"FSASPDMA requires FORGET action, got {aspdma_result.selected_action}")

        messages = self.compose_messages(original_thought, aspdma_result, context=context)
        llm_result, resource_usage = await self.call_llm_structured(
            messages=messages,
            response_model=FSASPDMALLMResult,
            max_tokens=8192,
            temperature=0.0,
            thought_id=original_thought.thought_id,
            task_id=original_thought.source_task_id,
        )
        usage: Optional[JSONDict] = (
            resource_usage.model_dump() if hasattr(resource_usage, "model_dump") else resource_usage
        )
        channel_id = getattr(aspdma_result.action_parameters, "channel_id", None)
        candidates = self.candidate_nodes_from_context(context)
        return carry_sent_prompts(llm_result, self._convert_forget(llm_result, channel_id, candidates, usage))

    async def evaluate(
        self,
        input_data: ProcessingQueueItem,
        *args: Any,
        **kwargs: Any,
    ) -> ActionSelectionDMAResult:
        """BaseDMA entry point — delegates to the forget-specific evaluation."""
        aspdma_result = kwargs.get("aspdma_result") or (args[0] if args else None)
        if aspdma_result is None:
            raise ValueError("FSASPDMA.evaluate requires an aspdma_result")
        return await self.evaluate_forget_action(
            aspdma_result=aspdma_result,
            original_thought=input_data,
            context=kwargs.get("context"),
        )


__all__ = ["FSASPDMAEvaluator", "FSASPDMALLMResult"]
