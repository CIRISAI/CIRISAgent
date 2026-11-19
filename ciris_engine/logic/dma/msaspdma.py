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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.dma.conscience_feedback import ConscienceFeedback
from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.schemas.dma.sent_prompts import PromptCarrier, carry_sent_prompts, sent_prompts_of
from ciris_engine.logic.formatters.wa_approval import (
    format_wa_approval_block,
    format_wa_approval_facts,
    wa_authorization_of,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import get_localized_accord_text
from ciris_engine.schemas.actions.parameters import MemorizeParams, PonderParams, SpeakParams
from ciris_engine.schemas.dma.msaspdma import CandidateNode
from ciris_engine.schemas.dma.results import UNADDRESSED_NODE_ID, ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader
from ciris_engine.logic.utils.localization import in_thought_language

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ciris_engine.logic.prompt_assembly import AssemblyCall
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest
    from ciris_engine.schemas.dma.prompts import PromptCollection

logger = logging.getLogger(__name__)

#: Shown where the prompt lists what action selection proposed and it proposed nothing.
_NOT_CHOSEN = "(not chosen yet — choose below)"


def _seg(segment_id: str, kind: str, text: str, source: str = "engine") -> Any:
    """A prompt segment (kinds and sources by their policy names)."""
    from ciris_engine.schemas.context.prompt_provenance import PromptSegment, SegmentKind, SegmentSource

    return PromptSegment(segment_id=segment_id, kind=SegmentKind(kind), source=SegmentSource(source), text=text)


class MSASPDMALLMResult(PromptCarrier):
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

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        return get_prompt_loader(language=self.thought_language)

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
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> List[JSONDict]:
        """The MSASPDMA messages alone (the composition seam); see :meth:`compose_prompt`."""
        messages, _ = self.compose_prompt(original_thought, aspdma_result, context, conscience_feedback)
        return messages

    @in_thought_language("original_thought", "context")
    def compose_prompt(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> "Tuple[List[JSONDict], PromptManifest]":
        """The MSASPDMA messages and their manifest, built by PromptAssembler from typed segments (FSD §6)."""
        from ciris_engine.schemas.context.prompt_provenance import PromptStage

        params = aspdma_result.action_parameters
        if not isinstance(params, MemorizeParams):
            raise TypeError(f"MSASPDMA expects MemorizeParams, got {type(params)}")

        node = params.node
        unaddressed = node.id == UNADDRESSED_NODE_ID
        attrs = node.attributes if isinstance(node.attributes, dict) else {}
        # The grant the memorize writes under: on the processing context, else on the thought's own context.
        authorization = wa_authorization_of(context) or wa_authorization_of(original_thought)

        # Each block is composed as its OWN message so it stays single-class on
        # the wire. Bundling them back into one system string would recreate the
        # mixed block the split exists to remove — the gate would see one body
        # carrying ontological, procedural, deontic and pragmatic content.
        # ONE system message, joined the way format_system_prompt_blocks joins
        # (\n\n, stripped). That formatter takes a fixed 4-6 canonical blocks and
        # this guide has nine, so the join is explicit — but the SHAPE is what
        # matters: the dump splits a joined system message back into its recorded
        # parts, so every block stays individually labelled and annotated.
        # Composing them as separate messages instead left them unmatched, and
        # the gate saw one mixed body it had no disposition for.
        guide = [
            ("system_guidance_header", self._require_prompt_value("system_guidance_header")),
            # #1366 item 12: the pipeline position, then the rest of the header.
            *self._position_entries(),
        ] + [
            (key, self._require_prompt_value(key))
            for key in (
                "memory_model",
                "addressing_convention",
                "attribute_convention",
                "scope_convention",
                "memory_prohibitions",
                "evaluation_steps",
                "response_format",
                "closing_reminder",
            )
        ]
        # "Do not write to identity scope without Wise Authority approval"
        # (memory_prohibitions) is decidable only if the approval is in front of
        # it (formatters/wa_approval.py). With no grant, the fact that there is
        # none (the no-grant case rendered nothing here before, and a model
        # filled the gap with a person's claimed approval); then the rule that
        # an approval exists only as that verified block (#1320).
        system = self._guide_segments(guide) + self._approval_segments(authorization)
        # The agent's identity first: the memorize that writes an amendment must see the identity it changes. The
        # Wise Authority's signed guidance rides in the approval block above, as a signed rule with its grant (#1366).
        identity = self._identity(context)

        candidates = self.candidate_nodes_from_context(context)
        # ASPDMA selects the verb and the scope, not the node (#1027), so
        # there is normally no proposed id or type to show.
        proposed: Dict[str, str] = {
            "proposed_node_id": _NOT_CHOSEN if unaddressed else node.id,
            "proposed_node_type": (_NOT_CHOSEN if unaddressed else getattr(node.type, "value", str(node.type))),
            "proposed_node_scope": getattr(node.scope, "value", str(node.scope)),
            "proposed_attributes": ", ".join(sorted(attrs)) or "(none)",
        }
        typed, plain = self._user_slots(original_thought, aspdma_result, candidates)
        for name, value in proposed.items():
            if value in (_NOT_CHOSEN, "(none)"):
                plain[name] = value  # the engine's own placeholder, not ASPDMA's output
            else:
                typed[name] = _seg(f"slot:{name}", "dma_output", value, "llm_output")
        plain["system_owned_attributes"] = self._format_system_owned(self.system_owned_attributes())
        return self._assemble(
            PromptStage.MSASPDMA,
            MSASPDMALLMResult.__name__,
            system,
            typed,
            plain,
            original_thought,
            context,
            conscience_feedback,
            identity=identity,
        )

    # ----------------------------------------------------- prompt assembly (#1366)

    @staticmethod
    def _guide_segments(guide: "List[Tuple[str, str]]", keep_empty: bool = False) -> List[Any]:
        """The guide's blocks as stage instructions (``keep_empty``: the join did not filter empty blocks)."""
        from ciris_engine.logic.prompt_assembly.segmenting import pipeline_position_segment

        # The pipeline position is its own segment, from its own template field (#1366 item 12).
        return [
            (
                pipeline_position_segment(text)
                if key == "pipeline_position"
                else _seg(f"instr:{key}", "stage_instruction", text)
            )
            for key, text in guide
            if text or keep_empty
        ]

    def _approval_segments(self, authorization: Any) -> List[Any]:
        """The WA approval (the grant as ``rule.signed_guidance`` with its authz, then its rule) and the facts."""
        from ciris_engine.logic.formatters.wa_approval import format_wa_approval_rule
        from ciris_engine.logic.prompt_assembly.segmenting import signed_guidance_segment

        language = self.prompt_loader.language
        out: List[Any] = []
        block = format_wa_approval_block(authorization, language=language)
        if block and authorization is not None:
            rule = format_wa_approval_rule(authorization, language=language)
            if rule and block.endswith("\n\n" + rule):
                out.append(signed_guidance_segment("rule:wa_grant", block[: -len(rule) - 2], authorization))
                out.append(_seg("instr:wa_approval_rule", "stage_instruction", rule))
            else:
                out.append(_seg("instr:wa_approval", "stage_instruction", block))
        facts = format_wa_approval_facts(authorization, language=language)
        if facts:
            out.append(_seg("instr:approval_facts", "stage_instruction", facts))
        return out

    def _identity(self, context: Optional[Any]) -> "Tuple[Any, Any]":
        """The identity block's (segments, layout); empty when the context carries no identity."""
        from ciris_engine.logic.formatters.identity import agent_identity_of
        from ciris_engine.logic.prompt_assembly.segmenting import identity_segments

        return identity_segments(agent_identity_of(context), self.prompt_loader.language)

    def _user_slots(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        candidates: List[CandidateNode],
    ) -> "Tuple[Dict[str, Any], Dict[str, str]]":
        """(typed slots, plain slots) the three memory second passes share in ``context_integration``.

        The request (model text on a follow-up thought), ASPDMA's reasoning and the candidate nodes (read from
        the snapshot's profiles, display names included: history) are typed; engine placeholders stay plain.
        """
        typed: Dict[str, Any] = {}
        plain: Dict[str, str] = {}
        content = getattr(getattr(original_thought, "content", None), "text", "") or ""
        depth = getattr(original_thought, "thought_depth", 0)
        follow_up = isinstance(depth, int) and depth > 0
        if content:
            typed["original_thought_content"] = _seg(
                "request", "request", content, "llm_output" if follow_up else "user_input"
            )
        else:
            plain["original_thought_content"] = ""
        reasoning = aspdma_result.rationale or ""
        if reasoning:
            typed["aspdma_reasoning"] = _seg("aspdma_reasoning", "dma_output", reasoning, "llm_output")
        else:
            plain["aspdma_reasoning"] = ""
        rendered = self._format_candidates(candidates)
        if candidates:
            typed["candidate_nodes"] = _seg("candidate_nodes", "history", rendered)
        else:
            plain["candidate_nodes"] = rendered
        return typed, plain

    def _assemble(
        self,
        stage: Any,
        response_model: str,
        system: List[Any],
        typed: Dict[str, Any],
        plain: Dict[str, str],
        original_thought: ProcessingQueueItem,
        context: Optional[Any],
        conscience_feedback: Optional[ConscienceFeedback],
        identity: "Optional[Tuple[Any, Any]]" = None,
    ) -> "Tuple[List[JSONDict], PromptManifest]":
        """Frame and assemble: accord, language guidance, crisis resources, the guide, the user message.

        The user message is ``context_integration`` with its slots typed, the VERIFIED SENDER block of the
        message being answered (#1366 item 5) and, on a conscience retry, the veto ASPDMA saw (#1366 item 1).
        """
        from ciris_engine.logic.dma.conscience_feedback import conscience_feedback_segment
        from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block
        from ciris_engine.logic.formatters.verified_sender import verified_sender_of
        from ciris_engine.logic.prompt_assembly.assembler import LayoutItem
        from ciris_engine.logic.prompt_assembly.segmenting import (
            PromptBuilder,
            items,
            sender_block_segments,
            split_template,
            stripped_ends,
        )
        from ciris_engine.logic.utils.localization import get_language_guidance

        language = self.prompt_loader.language
        builder = PromptBuilder()
        # The frame every memory second pass shares, so the three cannot drift apart on what precedes their guide.
        builder.single("system", _seg("accord", "accord", get_localized_accord_text(language) or ""))
        builder.single("system", _seg("instr:language", "stage_instruction", get_language_guidance(language) or ""))
        # Crisis resources ride directly after language guidance (#1248) — the
        # locale's verified numbers, from the one composer every DMA shares.
        builder.single(
            "system", _seg("instr:crisis", "stage_instruction", get_crisis_resources_system_block(language) or "")
        )
        system = stripped_ends(system)
        layout = items(system, "\n\n", "")
        if identity is not None and identity[0]:
            # The identity block leads the guide.
            head, head_layout = identity
            layout = list(head_layout) + ([layout[0].model_copy(update={"glue": "\n\n"})] + layout[1:] if layout else [])
            system = list(head) + system
        builder.message("system", system, layout)

        template = self._require_prompt_value("context_integration")
        user, user_items = split_template(
            lambda **values: template.format(**values), typed, prefix="instr:user", plain=plain
        )
        sender = verified_sender_of(original_thought, context)
        if sender is not None:
            sender_segs, sender_items = sender_block_segments(sender, include_display_name=True, language=language)
            user, user_items = user + sender_segs, user_items + sender_items
        feedback = conscience_feedback_segment(conscience_feedback)
        if feedback is not None:
            user.append(feedback)
            user_items.append(LayoutItem(segment_id=feedback.segment_id))
        builder.message("user", user, user_items)
        return builder.assemble(stage, self._assembly_call(original_thought, context, response_model, feedback is not None))

    def _assembly_call(
        self, original_thought: Any, context: Optional[Any], response_model: str, retry: bool
    ) -> "AssemblyCall":
        """The manifest's call facts, from trusted state only (the verified grant, verified amendments)."""
        from ciris_engine.logic.formatters.identity import agent_identity_of
        from ciris_engine.logic.prompt_assembly import AssemblyCall
        from ciris_engine.logic.prompt_assembly.segmenting import policy_facts
        from ciris_engine.schemas.context.prompt_provenance import ManifestThoughtKind

        authorization = wa_authorization_of(context)
        depth = getattr(original_thought, "thought_depth", 0)
        kind = (
            ManifestThoughtKind.GUIDANCE
            if authorization is not None
            else ManifestThoughtKind.FOLLOWUP if isinstance(depth, int) and depth > 0 else ManifestThoughtKind.SEED
        )
        task_id = getattr(original_thought, "source_task_id", None)
        thought_id = getattr(original_thought, "thought_id", None)
        return AssemblyCall(
            task_id=task_id if isinstance(task_id, str) else None,
            thought_id=thought_id if isinstance(thought_id, str) else None,
            thought_kind=kind,
            retry_index=1 if retry else 0,
            response_model=response_model,
            facts=policy_facts(authorization, agent_identity_of(context), id_scoped=False),
            language=self.prompt_loader.language,
        )

    def _graph_block(self, key: str) -> str:
        """A block of the shared graph guide, read from msaspdma.yml in this thought's language.

        What the graph is and how it is addressed is one description, used by
        all three memory second passes. RSASPDMA and FSASPDMA read it from here
        rather than carry a copy that could disagree with it.
        """
        value = self.prompt_loader.load_prompt_template("msaspdma").get_prompt(key)
        if value is None:
            raise ValueError(f"msaspdma prompt template missing required key: {key}")
        return value

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

    @in_thought_language("original_thought", "context")
    async def evaluate_memorize_action(
        self,
        aspdma_result: ActionSelectionDMAResult,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> ActionSelectionDMAResult:
        """Give a proposed MEMORIZE a second look against the graph conventions."""
        if aspdma_result.selected_action != HandlerActionType.MEMORIZE:
            raise ValueError(f"MSASPDMA requires MEMORIZE action, got {aspdma_result.selected_action}")

        current_params = aspdma_result.action_parameters
        if not isinstance(current_params, MemorizeParams):
            raise TypeError(f"MSASPDMA expects MemorizeParams, got {type(current_params)}")

        messages, manifest = self.compose_prompt(
            original_thought, aspdma_result, context=context, conscience_feedback=conscience_feedback
        )
        with prompt_manifest_scope(manifest):
            llm_result, resource_usage = await self.call_llm_structured(
                messages=messages,
                response_model=MSASPDMALLMResult,
                max_tokens=8192,
                temperature=0.0,
                thought_id=original_thought.thought_id,
                task_id=original_thought.source_task_id,
            )
        # ActionSelectionDMAResult.resource_usage is a JSONDict; the LLM bus
        # returns a ResourceUsage model. Passing the model failed validation, so
        # EVERY verdict this pass produced was discarded and the original action
        # ran instead (seen once the mock answered it: run 39677251620, 16x).
        # DSASPDMA converts the same way.
        usage: Optional[JSONDict] = (
            resource_usage.model_dump() if hasattr(resource_usage, "model_dump") else resource_usage
        )
        return carry_sent_prompts(llm_result, self._convert_result(llm_result, current_params, usage))

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
            conscience_feedback=kwargs.get("conscience_feedback"),
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
