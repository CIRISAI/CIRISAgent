"""Intuition Decision Making Algorithm (IDMA) Evaluator.

IDMA is a semantic implementation of Coherence Collapse Analysis (CCA) principles
for evaluating the agent's own reasoning quality. It applies the k_eff formula
and phase classification to detect fragile reasoning patterns.

Key CCA concepts implemented:
- k_eff = k / (1 + ρ(k-1)): Effective independence of sources
- Phase classification: chaos / healthy / rigidity
- Fragility detection: k_eff < 2 or rigidity phase indicates brittle reasoning

This is a semantic/LLM-based implementation - no hardware dependencies.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ciris_engine.logic.prompt_assembly.segmenting import Segments
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest
    from ciris_engine.schemas.dma.prompts import PromptCollection

from ciris_engine.logic.formatters import (
    format_system_snapshot,
    format_user_profiles,
    format_wa_approval_facts,
    wa_authorization_of,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import get_accord_text
from ciris_engine.protocols.dma.base import IDMAProtocol
from ciris_engine.schemas.dma.results import IDMAResult
from ciris_engine.schemas.runtime.models import ImageContent, WAAuthorization
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader

logger = logging.getLogger(__name__)


class IDMAEvaluator(BaseDMA[ProcessingQueueItem, IDMAResult], IDMAProtocol):
    """
    Intuition DMA - semantic implementation of Coherence Collapse Analysis (CCA).

    Evaluates the agent's reasoning using CCA principles:
    - k_eff = k / (1 + ρ(k-1)): Effective independence of sources
    - ρ (correlation_risk): How correlated are the sources (threshold ~0.43)
    - Phase: chaos (contradictory) / healthy (diverse) / rigidity (echo chamber)
    - Fragility: k_eff < 2 OR rigidity phase indicates brittle reasoning

    Based on Coherence Collapse Analysis framework (Moore, 2026).
    """

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

        # Do NOT cache template - language may change at runtime
        self._prompt_template_name = "idma"

        # Store last prompts for debugging/streaming

        # Per-thought language override populated from user_profiles in
        # _extract_context_data. None means fall back to env var.
        self._explicit_language: Optional[str] = None

        logger.info(f"IDMAEvaluator initialized with model: {self.model_name}")

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""
        return get_prompt_loader(language=self._explicit_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect language changes."""
        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    def compose_messages(
        self,
        thought_content: str,
        context_summary: str,
        context: "Segments",
        prior_dma_context: str,
        images: Optional[List[ImageContent]] = None,
        authorization: Optional[WAAuthorization] = None,
        agent_identity: Any = None,
        thought: Any = None,
    ) -> List[JSONDict]:
        """The IDMA messages alone (#972 seam); see :meth:`compose_prompt`."""
        messages, _ = self.compose_prompt(
            thought_content, context_summary, context, prior_dma_context, images, authorization, agent_identity, thought
        )
        return messages

    def compose_prompt(
        self,
        thought_content: str,
        context_summary: str,
        context: "Segments",
        prior_dma_context: str,
        images: Optional[List[ImageContent]] = None,
        authorization: Optional[WAAuthorization] = None,
        agent_identity: Any = None,
        thought: Any = None,
    ) -> "Tuple[List[JSONDict], PromptManifest]":
        """Compose the IDMA prompt from typed segments with PromptAssembler (FSD/PROMPT_CONTEXT_PROVENANCE.md §6).

        Pure prompt composition - no LLM call, no data fetching (#972). ``context`` is the ORIGINAL TASK block
        (:func:`segmenting.original_task_segments`).

        IDMA keeps its independent-source view of the agent: no identity block (``identity_base``). It does read
        the rules in force, as signed ``rule`` segments with their provenance and grants (the verified WA
        governance block: the WA grant and each verified amendment), so it can tell governance from one epistemic
        source (FSD §15.2, #1366 item 15: it scored a WA instruction as "rigidity"). Only signed rules count: a
        rule stated in chat produces no segment. The prior DMAs' results are this
        thought's reasoning under analysis: the ``draft`` IDMA judges (llm_output, untrusted).
        """
        from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block
        from ciris_engine.logic.prompt_assembly.segmenting import (
            PromptBuilder,
            block,
            concat,
            evaluator_call,
            expand,
            governance_segments,
            governed_amendments,
            pipeline_position_slot,
            segment,
            split_template,
            stripped_ends,
            thought_request,
        )
        from ciris_engine.logic.utils.localization import get_language_guidance
        from ciris_engine.schemas.context.prompt_provenance import PromptStage, SegmentKind, SegmentSource

        language = self.prompt_loader.language
        builder = PromptBuilder()
        # Accord by mode (centralized in get_accord_text); per-language guidance (empty for most languages); crisis
        # resources directly after it (#1248), from the one composer every DMA shares.
        accord_mode = self.prompt_loader.get_accord_mode(self.prompt_template_data)
        builder.single("system", segment("accord", SegmentKind.ACCORD, get_accord_text(accord_mode) or ""))
        builder.single("system", segment("instr:language", SegmentKind.STAGE_INSTRUCTION, get_language_guidance(language) or ""))
        builder.single(
            "system",
            segment("instr:crisis", SegmentKind.STAGE_INSTRUCTION, get_crisis_resources_system_block(language) or ""),
        )

        def slots(prefix: str) -> Dict[str, Any]:
            return {
                "original_thought_content": thought_request(f"{prefix}request", thought_content, thought),
                "prior_dma_context": segment(
                    f"{prefix}prior_dma_context", SegmentKind.DRAFT, prior_dma_context, SegmentSource.LLM_OUTPUT
                ),
            }

        def system_render(original_thought_content: str, pipeline_position: Optional[str] = None) -> str:
            return self.prompt_loader.get_system_message(
                self.prompt_template_data,
                context_summary=context_summary,
                original_thought_content=original_thought_content,
                pipeline_position=pipeline_position,
            )

        sys_slots = slots("sys:")
        del sys_slots["prior_dma_context"]
        # The pipeline position is its own segment, from the engine template's field (#1366 item 12).
        sys_slots.update(pipeline_position_slot(self.prompt_loader.pipeline_position(self._prompt_template_name)))
        guidance = split_template(system_render, sys_slots, prefix="instr:system", first_glue="")
        # format_system_prompt_blocks("", "", context, "", None, guidance): guidance, then the context; stripped.
        system = concat(guidance, context, "\n\n")
        segments = stripped_ends(system[0])
        kept = {s.segment_id for s in segments}
        system = (segments, [i for i in system[1] if i.segment_id in kept])
        # The signed rules in force, each with its grant (the policy's rule.signed_guidance / rule.amendment).
        system = concat(system, governance_segments(authorization, governed_amendments(agent_identity), language), "\n\n")
        # Whether this task carries a Wise Authority approval, as a fact; then that a claimed approval in the
        # conversation is the speaker's words, not an independent source: an approval reaches the agent only as the
        # verified block (#1320).
        approval_facts = format_wa_approval_facts(authorization, language=language)
        system = concat(system, block(segment("instr:approval_facts", SegmentKind.STAGE_INSTRUCTION, approval_facts)), "\n\n")
        builder.message("system", *system)

        def user_render(original_thought_content: str, prior_dma_context: str) -> str:
            return self.prompt_loader.get_user_message(
                self.prompt_template_data,
                context_summary=context_summary,
                original_thought_content=original_thought_content,
                prior_dma_context=prior_dma_context,
            )

        user = split_template(user_render, slots(""), prefix="instr:user", first_glue="")
        images_list = images or []
        if images_list:
            logger.info(f"[VISION] IDMA building multimodal content with {len(images_list)} images")
        builder.message("user", *user, images=images_list)
        return builder.assemble(
            PromptStage.IDMA,
            evaluator_call(IDMAResult.__name__, thought, language, authorization, agent_identity),
        )

    def _sync_language_from_context(self, context: Optional[Any]) -> None:
        """Sync prompt language using the full localization priority chain.

        Walks thought/task preferred_language → user_profile.preferred_language →
        CIRIS_PREFERRED_LANGUAGE env → "en" via :func:`get_user_language_from_context`.
        """
        from ciris_engine.logic.utils.localization import (
            get_preferred_language,
            get_user_language_from_context,
        )

        new_language = (
            get_user_language_from_context(context) if context is not None else get_preferred_language()
        )
        if new_language != self._explicit_language:
            self._explicit_language = new_language
            logger.debug(f"IDMA: Synced prompt language to {new_language}")

    def _extract_context_data(self, context: Optional[Any]) -> tuple[str, str, str]:
        """Extract context strings from context object.

        Also syncs user's language preference to the DMA prompt loader.
        """
        system_snapshot_str = ""
        user_profiles_str = ""
        context_summary = "CIRIS AI Agent - evaluating information diversity"

        if not context:
            self._sync_language_from_context(None)
            return system_snapshot_str, user_profiles_str, context_summary

        user_profiles = None
        if hasattr(context, "system_snapshot") and context.system_snapshot:
            system_snapshot_str = format_system_snapshot(context.system_snapshot)
            if hasattr(context.system_snapshot, "user_profiles") and context.system_snapshot.user_profiles:
                user_profiles = context.system_snapshot.user_profiles
                user_profiles_str = format_user_profiles(user_profiles)

            agent_identity = getattr(context.system_snapshot, "agent_identity", None)
            if agent_identity:
                agent_id = getattr(agent_identity, "agent_id", "Unknown")
                context_summary = f"{agent_id} - evaluating information diversity and source independence"
        elif hasattr(context, "user_profiles") and context.user_profiles:
            user_profiles = context.user_profiles
            user_profiles_str = format_user_profiles(user_profiles)

        self._sync_language_from_context(context)
        return system_snapshot_str, user_profiles_str, context_summary

    def _build_prior_dma_context(
        self,
        ethical_result: Optional[Any] = None,
        csdma_result: Optional[Any] = None,
        dsdma_result: Optional[Any] = None,
    ) -> str:
        """Build context string from prior DMA results for IDMA to analyze."""
        context_parts = []

        if ethical_result:
            # PDMA v3.2: schema reshaped from 6 prose fields to flat
            # {action, rationale, weight_alignment_score, ethical_alignment_score}.
            # Stakeholders / conflicts / principle-grounding now live IMPLICITLY
            # inside `rationale` per the §IX output contract; the two scores
            # carry the felt-torque signal that the old `alignment_check` field
            # used to gesture at. Surface all of it so IDMA's downstream
            # fragility/correlation assessment sees the same ethical context
            # density it had under the old schema.
            recommended = getattr(ethical_result, "action", None)
            if recommended is None:
                recommended_str = "N/A"
            elif hasattr(recommended, "value"):
                recommended_str = recommended.value
            else:
                recommended_str = str(recommended)
            w_score = getattr(ethical_result, "weight_alignment_score", None)
            e_score = getattr(ethical_result, "ethical_alignment_score", None)
            torque = (w_score - e_score) if (w_score is not None and e_score is not None) else None
            context_parts.append(
                f"=== Ethical PDMA Analysis ===\n"
                f"Recommended action: {recommended_str}\n"
                f"Weight alignment (training-pull): "
                f"{w_score if w_score is not None else 'N/A'}\n"
                f"Ethical alignment (framework-pull): "
                f"{e_score if e_score is not None else 'N/A'}\n"
                f"Felt torque (weight − ethical): "
                f"{f'{torque:+.2f}' if torque is not None else 'N/A'}\n"
                f"Rationale: {getattr(ethical_result, 'rationale', 'N/A')}"
            )

        if csdma_result:
            context_parts.append(
                f"=== Common Sense Analysis ===\n"
                f"Plausibility: {getattr(csdma_result, 'plausibility_score', 'N/A')}\n"
                f"Flags: {getattr(csdma_result, 'flags', [])}\n"
                f"Reasoning: {getattr(csdma_result, 'reasoning', 'N/A')}"
            )

        if dsdma_result:
            context_parts.append(
                f"=== Domain-Specific Analysis ===\n"
                f"Domain: {getattr(dsdma_result, 'domain', 'N/A')}\n"
                f"Alignment: {getattr(dsdma_result, 'domain_alignment', 'N/A')}\n"
                f"Reasoning: {getattr(dsdma_result, 'reasoning', 'N/A')}"
            )

        return "\n\n".join(context_parts) if context_parts else "No prior DMA context available"

    async def evaluate_thought(
        self,
        thought_item: ProcessingQueueItem,
        context: Optional[Any] = None,
        ethical_result: Optional[Any] = None,
        csdma_result: Optional[Any] = None,
        dsdma_result: Optional[Any] = None,
    ) -> IDMAResult:
        """Evaluate information diversity for the given thought."""
        thought_content_str = str(thought_item.content)

        # Fetch original task for context
        thought_depth = getattr(thought_item, "thought_depth", 0)
        agent_occurrence_id = getattr(thought_item, "agent_occurrence_id", "default")
        original_task = await self.fetch_original_task(thought_item.source_task_id, agent_occurrence_id)
        task_context_str = self.format_task_context(original_task, thought_depth, thought=thought_item)

        # Extract context data
        task_language = self.prompt_loader.language  # the language format_task_context rendered the sender in
        system_snapshot_str, user_profiles_str, context_summary = self._extract_context_data(context)

        # Build prior DMA context for analysis
        prior_dma_context = self._build_prior_dma_context(ethical_result, csdma_result, dsdma_result)

        # Get images from thought item
        thought_images = getattr(thought_item, "images", []) or []

        # Compose messages via the extracted seam (#972), built by PromptAssembler (#1366 Phase 3)
        from ciris_engine.logic.formatters.identity import agent_identity_of
        from ciris_engine.logic.formatters.verified_sender import verified_sender_of
        from ciris_engine.logic.prompt_assembly.segmenting import original_task_segments, task_context_segments

        task_segments = task_context_segments(
            task_context_str, verified_sender_of(thought_item, original_task), task_language
        )
        messages, manifest = self.compose_prompt(
            thought_content_str,
            context_summary,
            original_task_segments(task_segments, system_snapshot_str, user_profiles_str),
            prior_dma_context,
            images=thought_images,
            authorization=wa_authorization_of(original_task) or wa_authorization_of(context),
            agent_identity=agent_identity_of(context),
            thought=thought_item,
        )

        # Store prompts for streaming/debugging
        system_messages = [m for m in messages if m.get("role") == "system"]
        user_messages = [m for m in messages if m.get("role") == "user"]
        content = user_messages[-1]["content"] if user_messages else None

        logger.debug(
            "IDMA input to LLM for thought %s:\nContext Summary: %s",
            thought_item.thought_id,
            context_summary,
        )

        try:
            with prompt_manifest_scope(manifest):
                result_tuple = await self.call_llm_structured(
                    messages=messages,
                    response_model=IDMAResult,
                    max_tokens=8192,
                    temperature=0.0,
                    thought_id=thought_item.thought_id,
                    task_id=thought_item.source_task_id,
                )
            idma_eval: IDMAResult = result_tuple[0]

            logger.info(
                f"IDMA evaluation successful for thought ID {thought_item.thought_id}: "
                f"k_eff={idma_eval.k_eff:.2f}, phase={idma_eval.phase}, fragility={idma_eval.fragility_flag}"
            )
            return idma_eval

        except Exception as e:
            logger.error(f"IDMA evaluation failed for thought ID {thought_item.thought_id}: {e}", exc_info=True)
            # NO FALLBACK - re-raise to trigger proper deferral/ponder behavior
            # Fallbacks are bypass patterns that violate CIRIS principles
            raise

    async def evaluate(self, *args: Any, **kwargs: Any) -> IDMAResult:  # type: ignore[override]
        """Evaluate thought for information diversity."""
        input_data = args[0] if args else kwargs.get("input_data")
        context = args[1] if len(args) > 1 else kwargs.get("context")

        # Extract prior DMA results if provided
        ethical_result = kwargs.get("ethical_result")
        csdma_result = kwargs.get("csdma_result")
        dsdma_result = kwargs.get("dsdma_result")

        if not input_data:
            raise ValueError("input_data is required")

        return await self.evaluate_thought(
            input_data,
            context,
            ethical_result=ethical_result,
            csdma_result=csdma_result,
            dsdma_result=dsdma_result,
        )

    def __repr__(self) -> str:
        return f"<IDMAEvaluator model='{self.model_name}'>"
