"""Recall-Specific Action Selection PDMA (RSASPDMA).

The second pass after ASPDMA selects RECALL (#1027). ASPDMA chooses the verb
and nothing else; this step is shown how the graph is addressed and which nodes
already exist, and says what to read.

Why RECALL needed one: it shares MEMORIZE's addressing problem from the other
side. A read against an invented id returns nothing, and "nothing" is
indistinguishable from "I never learned this". ASPDMA could not even name a
node — its flat schema had a query field and no id field — so every recall was
a text search, including the ones for a node the agent could have named.

Returns the same ActionSelectionDMAResult as ASPDMA: RECALL with a query or a
node id, SPEAK, or PONDER. NO HEALING, as in MSASPDMA: a RECALL with nothing to
look for becomes a PONDER, not a guessed query.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from pydantic import ConfigDict, Field

from ciris_engine.logic.dma.conscience_feedback import ConscienceFeedback
from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.actions.parameters import (
    PonderParams,
    RecallParams,
    SpeakParams,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.dma.sent_prompts import PromptCarrier, carry_sent_prompts
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphScope
from ciris_engine.schemas.types import JSONDict

from .msaspdma import MSASPDMAEvaluator

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest

logger = logging.getLogger(__name__)


class RSASPDMALLMResult(PromptCarrier):
    """Structured output for the recall-specific second pass."""

    final_action: str = Field(..., description="RECALL, SPEAK or PONDER")
    node_id: Optional[str] = Field(None, description="Exact node id to read")
    query: Optional[str] = Field(None, description="Search text")
    node_type: Optional[str] = Field(None, description="Node type to narrow a search")
    node_scope: Optional[str] = Field(None, description="Graph scope to narrow a search")
    limit: int = Field(10, description="Maximum results")
    message: Optional[str] = Field(None, description="What to say (required for SPEAK)")
    questions: List[str] = Field(default_factory=list, description="What to reconsider (PONDER)")
    reasoning: str = Field("", description="Why this read finds it, or why the switch")

    model_config = ConfigDict(extra="forbid")


class RSASPDMAEvaluator(MSASPDMAEvaluator):
    """Second-pass recall evaluator: the shared graph guide + the nodes that exist."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._prompt_template_name = "rsaspdma"

    def compose_messages(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> List[JSONDict]:
        """The RSASPDMA messages alone (the composition seam); see :meth:`compose_prompt`."""
        messages, _ = self.compose_prompt(original_thought, aspdma_result, context, conscience_feedback)
        return messages

    def compose_prompt(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> "Tuple[List[JSONDict], PromptManifest]":
        """The RSASPDMA messages and their manifest, built by PromptAssembler from typed segments (FSD §6)."""
        from ciris_engine.schemas.context.prompt_provenance import PromptStage

        self._sync_language_from_context(context)
        # Joined without a filter, as ever: an empty block keeps its place (keep_empty).
        system = self._guide_segments(
            [
                ("system_guidance_header", self._require_prompt_value("system_guidance_header")),
                ("memory_model", self._graph_block("memory_model")),
                ("addressing_convention", self._graph_block("addressing_convention")),
                ("scope_convention", self._graph_block("scope_convention")),
                ("memory_prohibitions", self._require_prompt_value("memory_prohibitions")),
                ("evaluation_steps", self._require_prompt_value("evaluation_steps")),
                ("response_format", self._require_prompt_value("response_format")),
                ("closing_reminder", self._require_prompt_value("closing_reminder")),
            ],
            keep_empty=True,
        )
        typed, plain = self._user_slots(original_thought, aspdma_result, self.candidate_nodes_from_context(context))
        # The verified sender of the message being answered (#1366 item 5) and, on a conscience retry, the veto
        # ASPDMA saw (#1366 item 1) follow the template in the user message.
        return self._assemble(
            PromptStage.RSASPDMA,
            RSASPDMALLMResult.__name__,
            system,
            typed,
            plain,
            original_thought,
            context,
            conscience_feedback,
        )

    def _convert_recall(
        self,
        llm_result: RSASPDMALLMResult,
        channel_id: Optional[str],
        resource_usage: Optional[JSONDict] = None,
    ) -> ActionSelectionDMAResult:
        """Turn the second-pass verdict into a typed action."""
        action = (llm_result.final_action or "").strip().upper()
        rationale = f"RSASPDMA: {llm_result.reasoning}"

        if action == "SPEAK" and llm_result.message:
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.SPEAK,
                action_parameters=SpeakParams(channel_id=channel_id, content=llm_result.message),
                rationale=rationale,
                resource_usage=resource_usage,
            )

        if action == "RECALL" and (llm_result.node_id or llm_result.query or llm_result.node_type):
            scope: Optional[GraphScope] = None
            if llm_result.node_scope:
                try:
                    scope = GraphScope(llm_result.node_scope.strip().lower())
                except ValueError:
                    logger.warning(
                        "RSASPDMA: unknown scope %r, searching every scope",
                        llm_result.node_scope,
                    )
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.RECALL,
                action_parameters=RecallParams(
                    channel_id=channel_id,
                    node_id=llm_result.node_id or None,
                    query=llm_result.query or None,
                    node_type=llm_result.node_type or None,
                    scope=scope,
                    limit=llm_result.limit if llm_result.limit > 0 else 10,
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
                    "The recall second pass did not say what to read.",
                    f"It returned final_action={llm_result.final_action!r}.",
                    "What exactly am I looking for, and which node would hold it?",
                ],
            ),
            rationale=(rationale if action == "PONDER" else "RSASPDMA: unusable second-pass result — reconsidering"),
            resource_usage=resource_usage,
        )

    async def evaluate_recall_action(
        self,
        aspdma_result: ActionSelectionDMAResult,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> ActionSelectionDMAResult:
        """Say what a selected RECALL reads."""
        if aspdma_result.selected_action != HandlerActionType.RECALL:
            raise ValueError(f"RSASPDMA requires RECALL action, got {aspdma_result.selected_action}")

        messages, manifest = self.compose_prompt(
            original_thought, aspdma_result, context=context, conscience_feedback=conscience_feedback
        )
        with prompt_manifest_scope(manifest):
            llm_result, resource_usage = await self.call_llm_structured(
                messages=messages,
                response_model=RSASPDMALLMResult,
                max_tokens=8192,
                temperature=0.0,
                thought_id=original_thought.thought_id,
                task_id=original_thought.source_task_id,
            )
        usage: Optional[JSONDict] = (
            resource_usage.model_dump() if hasattr(resource_usage, "model_dump") else resource_usage
        )
        channel_id = getattr(aspdma_result.action_parameters, "channel_id", None)
        return carry_sent_prompts(llm_result, self._convert_recall(llm_result, channel_id, usage))

    async def evaluate(
        self,
        input_data: ProcessingQueueItem,
        *args: Any,
        **kwargs: Any,
    ) -> ActionSelectionDMAResult:
        """BaseDMA entry point — delegates to the recall-specific evaluation."""
        aspdma_result = kwargs.get("aspdma_result") or (args[0] if args else None)
        if aspdma_result is None:
            raise ValueError("RSASPDMA.evaluate requires an aspdma_result")
        return await self.evaluate_recall_action(
            aspdma_result=aspdma_result,
            original_thought=input_data,
            context=kwargs.get("context"),
            conscience_feedback=kwargs.get("conscience_feedback"),
        )


__all__ = ["RSASPDMAEvaluator", "RSASPDMALLMResult"]
