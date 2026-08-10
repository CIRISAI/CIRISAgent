"""Memorize-Specific Action Selection PDMA (MSASPDMA).

A second look after ASPDMA selects MEMORIZE, giving the agent the graph's
addressing conventions and the nodes that already exist before it writes.

See ``ciris_engine/schemas/dma/msaspdma.py`` for the failure this exists to
prevent. In short: the agent wrote a user fact to a freshly-minted UUID node,
which nothing ever queries, so the fact would have been stored and permanently
unreachable — and the write also carried a system-managed attribute, so it was
refused and the agent looped.

NO HEALING. Nothing here rewrites the agent's selection. The evaluator is handed
the conventions and the candidate nodes and re-decides, exactly as TSASPDMA is
handed ToolInfo. Silently repairing a bad node id would hide a model that does
not know the conventions and leave it inventing ids wherever this does not run.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.formatters import format_system_prompt_blocks
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import get_localized_accord_text
from ciris_engine.schemas.actions.parameters import MemorizeParams, PonderParams, SpeakParams
from ciris_engine.schemas.dma.msaspdma import CandidateNode
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ciris_engine.schemas.dma.prompts import PromptCollection

logger = logging.getLogger(__name__)


class MSASPDMALLMResult(BaseModel):
    """Structured output for the memorize-specific second pass."""

    final_action: str = Field(..., description="MEMORIZE, SPEAK or PONDER")
    node_id: Optional[str] = Field(None, description="Node id to write to (required for MEMORIZE)")
    node_type: Optional[str] = Field(None, description="Node type (required for MEMORIZE)")
    node_scope: Optional[str] = Field(None, description="Graph scope (required for MEMORIZE)")
    attributes: Dict[str, str] = Field(default_factory=dict, description="Attributes to store")
    message: Optional[str] = Field(None, description="What to say (required for SPEAK)")
    questions: List[str] = Field(default_factory=list, description="What to reconsider (PONDER)")
    reasoning: str = Field("", description="Why this addressing is correct, or why the switch")

    model_config = ConfigDict(extra="forbid")


class MSASPDMAEvaluator(BaseDMA[ProcessingQueueItem, ActionSelectionDMAResult]):
    """Second-pass memorize evaluator: addressing conventions + existing nodes."""

    def __init__(
        self,
        service_registry: ServiceRegistry,
        model_name: Optional[str] = None,
        max_retries: int = 2,
        prompt_overrides: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            service_registry=service_registry,
            model_name=model_name,
            max_retries=max_retries,
            prompt_overrides=prompt_overrides,
            **kwargs,
        )
        self._prompt_template_name = "msaspdma"
        self.last_user_prompt: Optional[str] = None
        self.last_system_prompt: Optional[str] = None
        self._explicit_language: Optional[str] = None

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        return get_prompt_loader(language=self._explicit_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    # ------------------------------------------------------------------ inputs

    @staticmethod
    def candidate_nodes_from_context(context: Optional[Any]) -> List[CandidateNode]:
        """Candidate nodes from the system snapshot — option (a), no extra query.

        The snapshot already carries the user profiles (and channel context) for
        the thought being processed, so the nodes the agent is most likely to
        want are already in hand. Offering them is what turns "invent an id"
        into "pick one".
        """
        snapshot = getattr(context, "system_snapshot", None) if context else None
        if snapshot is None and isinstance(context, dict):
            snapshot = context.get("system_snapshot")
        if snapshot is None:
            return []

        candidates: List[CandidateNode] = []

        profiles = getattr(snapshot, "user_profiles", None) or []
        for profile in profiles:
            user_id = getattr(profile, "user_id", None)
            if not user_id:
                continue
            known = getattr(profile, "memorized_attributes", {}) or {}
            candidates.append(
                CandidateNode(
                    node_id=f"user/{user_id}",
                    node_type=NodeType.USER.value,
                    scope=GraphScope.LOCAL.value,
                    description=(
                        f"Profile for {getattr(profile, 'display_name', None) or user_id}. "
                        "Facts about this person belong here."
                    ),
                    existing_attributes=sorted(known.keys()),
                )
            )

        channel_id = getattr(snapshot, "channel_id", None)
        if channel_id:
            candidates.append(
                CandidateNode(
                    node_id=f"channel/{channel_id}",
                    node_type=NodeType.CHANNEL.value,
                    scope=GraphScope.LOCAL.value,
                    description="This conversation's channel. Facts about the place, not the people.",
                    existing_attributes=[],
                )
            )

        return candidates

    @staticmethod
    def system_owned_attributes() -> Dict[str, str]:
        """Attribute -> why the agent may not author it.

        Sourced from the same table the memorize handler enforces, so the
        guidance and the guard cannot drift apart.
        """
        from ciris_engine.logic.infrastructure.handlers.shared_helpers import MANAGED_USER_ATTRIBUTES

        return dict(MANAGED_USER_ATTRIBUTES)

    # ----------------------------------------------------------------- prompts

    def _format_candidates(self, candidates: List[CandidateNode]) -> str:
        if not candidates:
            return "(none available for this thought — construct an id using the conventions)"
        lines = []
        for c in candidates:
            attrs = ", ".join(c.existing_attributes) if c.existing_attributes else "none yet"
            lines.append(f"  {c.node_id}  [type={c.node_type}, scope={c.scope}]\n" f"      {c.description}\n" f"      already stored: {attrs}")
        return "\n".join(lines)

    @staticmethod
    def _format_system_owned(managed: Dict[str, str]) -> str:
        return "\n".join(f"  {name}: {why}" for name, why in sorted(managed.items()))

    def compose_messages(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
    ) -> List[JSONDict]:
        """Compose the MSASPDMA prompt message list."""
        self._sync_language_from_context(context)

        params = aspdma_result.action_parameters
        if not isinstance(params, MemorizeParams):
            raise TypeError(f"MSASPDMA expects MemorizeParams, got {type(params)}")

        node = params.node
        attrs = node.attributes if isinstance(node.attributes, dict) else {}

        system_message = format_system_prompt_blocks(
            self._require_prompt_value("system_guidance_header"),
            self._require_prompt_value("evaluation_steps"),
            self._require_prompt_value("response_format"),
            self._require_prompt_value("closing_reminder"),
        )

        original_thought_content = getattr(getattr(original_thought, "content", None), "text", "") or ""
        candidates = self.candidate_nodes_from_context(context)

        context_block = self._require_prompt_value("context_integration")
        user_message = context_block.format(
            original_thought_content=original_thought_content,
            aspdma_reasoning=aspdma_result.rationale or "",
            proposed_node_id=node.id,
            proposed_node_type=getattr(node.type, "value", str(node.type)),
            proposed_node_scope=getattr(node.scope, "value", str(node.scope)),
            proposed_attributes=", ".join(sorted(attrs)) or "(none)",
            candidate_nodes=self._format_candidates(candidates),
            system_owned_attributes=self._format_system_owned(self.system_owned_attributes()),
            memory_guide=self._require_prompt_value("memory_guide"),
        )

        self.last_system_prompt = system_message
        self.last_user_prompt = user_message

        messages: List[JSONDict] = []
        accord_text = get_localized_accord_text(self.prompt_loader.language)
        if accord_text:
            messages.append({"role": "system", "content": accord_text})
        from ciris_engine.logic.utils.localization import get_language_guidance

        lang_guidance = get_language_guidance(self.prompt_loader.language)
        if lang_guidance:
            messages.append({"role": "system", "content": lang_guidance})
        messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": user_message})
        return messages

    def _sync_language_from_context(self, context: Optional[Any]) -> None:
        """Adopt the thought's language so the guide renders localized."""
        lang = None
        if context is not None:
            lang = getattr(context, "preferred_language", None)
            if lang is None and isinstance(context, dict):
                lang = context.get("preferred_language")
        self._explicit_language = lang

    # ----------------------------------------------------------------- results

    def _convert_result(
        self,
        llm_result: MSASPDMALLMResult,
        original_params: MemorizeParams,
        resource_usage: Optional[JSONDict] = None,
    ) -> ActionSelectionDMAResult:
        """Turn the second-pass verdict into a typed action.

        An unparseable or under-specified MEMORIZE becomes PONDER rather than
        being patched: this evaluator does not heal, and a write it cannot
        validate is exactly the write that caused the incident.
        """
        action = (llm_result.final_action or "").strip().upper()

        if action == "SPEAK" and llm_result.message:
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.SPEAK,
                action_parameters=SpeakParams(
                    channel_id=original_params.channel_id,
                    content=llm_result.message,
                ),
                rationale=f"MSASPDMA: {llm_result.reasoning}",
                resource_usage=resource_usage,
            )

        if action == "PONDER":
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=PonderParams(
                    questions=llm_result.questions or [llm_result.reasoning or "Reconsider this memorize."],
                ),
                rationale=f"MSASPDMA: {llm_result.reasoning}",
                resource_usage=resource_usage,
            )

        if action == "MEMORIZE" and llm_result.node_id:
            node = GraphNode(
                id=llm_result.node_id,
                type=self._coerce_node_type(llm_result.node_type, original_params.node.type),
                scope=self._coerce_scope(llm_result.node_scope, original_params.node.scope),
                attributes=dict(llm_result.attributes),
            )
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.MEMORIZE,
                action_parameters=MemorizeParams(channel_id=original_params.channel_id, node=node),
                rationale=f"MSASPDMA: {llm_result.reasoning}",
                resource_usage=resource_usage,
            )

        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=PonderParams(
                questions=[
                    "The memorize second pass did not produce a usable node.",
                    f"It returned final_action={llm_result.final_action!r}.",
                    "Which existing node should this fact attach to?",
                ],
            ),
            rationale="MSASPDMA: unusable second-pass result — not patching, reconsidering",
            resource_usage=resource_usage,
        )

    # ---------------------------------------------------------------- evaluate

    async def evaluate_memorize_action(
        self,
        aspdma_result: ActionSelectionDMAResult,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
    ) -> ActionSelectionDMAResult:
        """Give a proposed MEMORIZE a second look against the graph conventions."""
        if aspdma_result.selected_action != HandlerActionType.MEMORIZE:
            raise ValueError(f"MSASPDMA requires MEMORIZE action, got {aspdma_result.selected_action}")

        current_params = aspdma_result.action_parameters
        if not isinstance(current_params, MemorizeParams):
            raise TypeError(f"MSASPDMA expects MemorizeParams, got {type(current_params)}")

        messages = self.compose_messages(original_thought, aspdma_result, context=context)
        llm_result, resource_usage = await self.call_llm_structured(
            messages=messages,
            response_model=MSASPDMALLMResult,
            max_tokens=8192,
            temperature=0.0,
            thought_id=original_thought.thought_id,
            task_id=original_thought.source_task_id,
        )
        return self._convert_result(llm_result, current_params, resource_usage)

    async def evaluate(
        self,
        input_data: ProcessingQueueItem,
        *args: Any,
        **kwargs: Any,
    ) -> ActionSelectionDMAResult:
        """BaseDMA entry point — delegates to the memorize-specific evaluation."""
        aspdma_result = kwargs.get("aspdma_result") or (args[0] if args else None)
        if aspdma_result is None:
            raise ValueError("MSASPDMA.evaluate requires an aspdma_result")
        return await self.evaluate_memorize_action(
            aspdma_result=aspdma_result,
            original_thought=input_data,
            context=kwargs.get("context"),
        )

    @staticmethod
    def _coerce_node_type(value: Optional[str], fallback: NodeType) -> NodeType:
        try:
            return NodeType(value) if value else fallback
        except ValueError:
            logger.warning("MSASPDMA: unknown node_type %r, keeping %s", value, fallback)
            return fallback

    @staticmethod
    def _coerce_scope(value: Optional[str], fallback: GraphScope) -> GraphScope:
        try:
            return GraphScope(value) if value else fallback
        except ValueError:
            logger.warning("MSASPDMA: unknown scope %r, keeping %s", value, fallback)
            return fallback


__all__ = ["MSASPDMAEvaluator", "MSASPDMALLMResult"]
