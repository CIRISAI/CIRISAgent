"""Deferral-Specific Action Selection PDMA (DSASPDMA).

DSASPDMA is activated only when ASPDMA selects a DEFER action.
It does not re-open the action choice. Instead, it performs a second pass
that classifies the deferral against a rights/needs taxonomy so the result is:

- explainable
- auditable
- routable when domain-specific handling is needed
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.dma.conscience_feedback import ConscienceFeedback
from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.schemas.dma.sent_prompts import PromptCarrier, carry_sent_prompts, sent_prompts_of
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import get_localized_accord_text
from ciris_engine.schemas.actions.parameters import (
    IDENTITY_CHANGE_CONTEXT_KEY,
    M1_JUSTIFICATION_CONTEXT_KEY,
    PROPOSED_AMENDMENT_CONTEXT_KEY,
    DeferParams,
)
from ciris_engine.schemas.dma.prompts import PromptCollection
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.agent_credits import DomainCategory
from ciris_engine.schemas.services.deferral_taxonomy import (
    DeferralNeedCategory,
    DeferralOperationalReason,
    build_deferral_taxonomy_prompt,
    get_need_category_for_domain,
    get_rights_basis_for_need_category,
)
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader
from ciris_engine.logic.utils.localization import in_thought_language

if TYPE_CHECKING:
    from ciris_engine.logic.prompt_assembly import AssemblyCall
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest
    from ciris_engine.schemas.dma.prompts import PromptCollection

logger = logging.getLogger(__name__)


class DSASPDMALLMResult(PromptCarrier):
    """Structured output for defer-specific second-pass classification."""

    reason_summary: str = Field(..., description="Short human-readable reason for the deferral")
    operational_reason: DeferralOperationalReason = Field(
        ...,
        description="Operational explanation for why the deferral is needed",
    )
    primary_need_category: DeferralNeedCategory = Field(
        ...,
        description="Primary rights / needs category implicated by the deferral",
    )
    secondary_need_categories: List[DeferralNeedCategory] = Field(
        default_factory=list,
        description="Additional rights / needs categories implicated by the deferral",
    )
    rights_basis: List[str] = Field(
        default_factory=list,
        description="Rights-basis labels that justify this categorization",
    )
    domain_hint: Optional[DomainCategory] = Field(
        None,
        description="Licensed domain hint when a separate licensed domain handler is clearly required",
    )
    defer_until: Optional[str] = Field(
        None,
        description="Optional override for when the task should be reconsidered",
    )
    proposed_amendment: Optional[str] = Field(
        None,
        description="Only when the deferral proposes a change to the agent's identity: the proposed identity text",
    )
    m1_justification: Optional[str] = Field(
        None,
        description="With proposed_amendment: why the change serves ACCORD Meta-Goal M-1 (Adaptive Coherence)",
    )

    model_config = ConfigDict(extra="forbid")


def _proposed_amendment(text: Optional[str]) -> Optional[str]:
    """The proposed identity text as a WA could approve it verbatim, or None.

    Stripped, because approved amendment text carries no outer whitespace
    (``ResolveDeferralRequest.amendment_text``). Text longer than one approval
    accepts is dropped whole rather than cut: a cut proposal is not the text the
    agent proposed.
    """
    from ciris_engine.schemas.api.wa import MAX_AMENDMENT_TEXT_CHARS

    value = (text or "").strip()
    if not value:
        return None
    if len(value) > MAX_AMENDMENT_TEXT_CHARS:
        logger.warning(
            "DSASPDMA: proposed amendment of %d characters exceeds %d; not attached", len(value), MAX_AMENDMENT_TEXT_CHARS
        )
        return None
    return value


def _m1_justification(text: Optional[str]) -> Optional[str]:
    """The proposal's M-1 justification, stripped; None when the model stated none."""
    value = (text or "").strip()
    return value or None


def _identity_change_context(
    reason_summary: str, proposed_amendment: str, m1_justification: Optional[str]
) -> Dict[str, str | List[str]]:
    """The deferral context a proposed identity amendment carries to the WA (GET /v1/wa/deferrals).

    ``identity_change`` is the whole proposal (kind, what changes, the exact
    text, the M-1 justification); ``m1_justification`` rides beside
    ``proposed_amendment`` for clients that read the flat keys.
    """
    from ciris_engine.schemas.api.wa import IdentityChangeKind, IdentityChangeProposal

    proposal = IdentityChangeProposal(
        kind=IdentityChangeKind.AMENDMENT,
        summary=reason_summary,
        proposed_text=proposed_amendment,
        m1_justification=m1_justification,
    )
    context: Dict[str, str | List[str]] = {
        PROPOSED_AMENDMENT_CONTEXT_KEY: proposed_amendment,
        IDENTITY_CHANGE_CONTEXT_KEY: proposal.model_dump_json(),
    }
    if m1_justification is not None:
        context[M1_JUSTIFICATION_CONTEXT_KEY] = m1_justification
    return context


class DSASPDMAEvaluator(BaseDMA[ProcessingQueueItem, ActionSelectionDMAResult]):
    """Second-pass deferral classifier using the localized rights taxonomy."""

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
        self._prompt_template_name = "dsaspdma"

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""

        return get_prompt_loader(language=self.thought_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect runtime language changes."""

        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    @staticmethod
    def _user_profiles_from_context(context: Optional[Any]) -> Optional[Any]:
        """Extract user_profiles from a polymorphic context (object or dict)."""
        if not context:
            return None
        if hasattr(context, "system_snapshot") and getattr(context, "system_snapshot", None):
            return getattr(getattr(context, "system_snapshot"), "user_profiles", None)
        if isinstance(context, dict):
            snapshot = context.get("system_snapshot")
            if isinstance(snapshot, dict):
                return snapshot.get("user_profiles")
            if snapshot is not None:
                return getattr(snapshot, "user_profiles", None)
        return None

    @staticmethod
    def _preferred_language_of(profile: Any) -> Optional[str]:
        """Read preferred_language from a profile (object or dict)."""
        if isinstance(profile, dict):
            return profile.get("preferred_language")
        return getattr(profile, "preferred_language", None)

    def _format_original_context(self, params: DeferParams) -> str:
        """Render the provisional deferral context for prompt inclusion."""

        if not params.context:
            return "(none)"

        lines: List[str] = []
        for key, value in sorted(params.context.items()):
            if isinstance(value, list):
                rendered = ", ".join(str(item) for item in value)
            else:
                rendered = str(value)
            lines.append(f"- {key}: {rendered}")
        return "\n".join(lines)

    def _get_original_domain_hint(self, params: DeferParams) -> str:
        """Render the original domain hint if present."""

        if params.domain_hint is None:
            return "none"
        return params.domain_hint.value

    def compose_messages(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> List[JSONDict]:
        """The DSASPDMA messages alone (the composition seam, #972); see :meth:`compose_prompt`."""
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
        """The DSASPDMA messages and their manifest, built by PromptAssembler from typed segments (FSD §6).

        Accord, language guidance and crisis resources (one system message each), the stage's guide, then the
        user message: ``context_integration`` with its slots typed, the VERIFIED SENDER block of the message
        being answered (#1366 item 5) and, on a conscience retry, the veto ASPDMA saw (#1366 item 1).
        """
        from ciris_engine.logic.dma.conscience_feedback import conscience_feedback_segment
        from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block
        from ciris_engine.logic.formatters.verified_sender import verified_sender_of
        from ciris_engine.logic.prompt_assembly.assembler import LayoutItem
        from ciris_engine.logic.prompt_assembly.segmenting import (
            PromptBuilder,
            identity_segments,
            items,
            pipeline_position_segment,
            segment,
            sender_block_segments,
            split_template,
            stripped_ends,
        )
        from ciris_engine.logic.utils.localization import get_language_guidance
        from ciris_engine.schemas.context.prompt_provenance import PromptStage, SegmentKind, SegmentSource

        current_params = aspdma_result.action_parameters
        if not isinstance(current_params, DeferParams):
            raise TypeError(f"DSASPDMA expects DeferParams, got {type(current_params)}")

        language = self.prompt_loader.language
        builder = PromptBuilder()
        builder.single("system", segment("accord", SegmentKind.ACCORD, get_localized_accord_text(language) or ""))
        # Per-language guidance — empty for most languages, populated for locales where systematic terminology
        # gaps were observed (am as of 2.7.6).
        builder.single("system", segment("instr:language", SegmentKind.STAGE_INSTRUCTION, get_language_guidance(language) or ""))
        # Crisis resources ride directly after language guidance (#1248).
        builder.single(
            "system", segment("instr:crisis", SegmentKind.STAGE_INSTRUCTION, get_crisis_resources_system_block(language) or "")
        )
        # The pipeline position is its own segment, from its own template field (#1366 item 12).
        guide = [
            (
                pipeline_position_segment(text)
                if key == "pipeline_position"
                else segment(f"instr:{key}", SegmentKind.STAGE_INSTRUCTION, text)
            )
            for key, text in [
                ("system_guidance_header", self._require_prompt_value("system_guidance_header")),
                *self._position_entries(),
                *[
                    (key, self._require_prompt_value(key))
                    for key in ("evaluation_steps", "response_format", "closing_reminder")
                ],
            ]
        ]
        system = stripped_ends([s for s in guide if s.text])
        layout = items(system, "\n\n", "")
        # The agent's identity leads the guide, as at every drafter (context_policy.yaml: identity_base always at
        # dsaspdma). A deferral classified without it judged a self it could not see (RATCHET context map, S3).
        agent_identity = self._agent_identity(context)
        head, head_layout = identity_segments(agent_identity, language)
        if head:
            layout = list(head_layout) + ([layout[0].model_copy(update={"glue": "\n\n"})] + layout[1:] if layout else [])
            system = list(head) + system
        builder.message("system", system, layout)

        taxonomy_text = self._get_prompt_value("taxonomy_text") or build_deferral_taxonomy_prompt(language)
        template = self._get_prompt_value("context_integration") or (
            "Original thought:\n{original_thought_content}\n\n"
            "ASPDMA reasoning:\n{aspdma_reasoning}\n\n"
            "Current deferral reason:\n{current_reason}\n\n"
            "Current context:\n{current_context}\n\n"
            "{taxonomy_text}"
        )
        depth = getattr(original_thought, "thought_depth", 0)
        follow_up = isinstance(depth, int) and depth > 0
        llm = SegmentSource.LLM_OUTPUT
        # slot: (segment id, kind, value, source, the engine's text when there is no value)
        values = {
            "original_thought_content": (
                "request",
                SegmentKind.REQUEST,
                getattr(getattr(original_thought, "content", None), "text", "") or "",
                llm if follow_up else SegmentSource.USER_INPUT,
                "",
            ),
            # ASPDMA's output: its reasoning and the provisional deferral it proposed.
            "aspdma_reasoning": ("aspdma_reasoning", SegmentKind.DMA_OUTPUT, aspdma_result.rationale or "", llm, ""),
            "current_reason": ("proposed_reason", SegmentKind.DMA_OUTPUT, current_params.reason, llm, ""),
            "current_context": (
                "proposed_context",
                SegmentKind.DMA_OUTPUT,
                self._format_original_context(current_params) if current_params.context else "",
                llm,
                self._format_original_context(current_params),
            ),
            "current_defer_until": (
                "proposed_defer_until", SegmentKind.DMA_OUTPUT, current_params.defer_until or "", llm, "none"
            ),
        }
        typed: Dict[str, Any] = {}
        plain: Dict[str, str] = {
            "current_domain_hint": self._get_original_domain_hint(current_params),
            "taxonomy_text": taxonomy_text,
            "domain_hint_options": ", ".join(domain.value for domain in DomainCategory),
        }
        for slot, (segment_id, kind, text, source, absent) in values.items():
            if text:
                typed[slot] = segment(segment_id, kind, text, source)
            else:
                plain[slot] = absent
        user, user_items = split_template(
            lambda **v: template.format(**v), typed, prefix="instr:user", plain=plain, locale=self.served_locale
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
        return builder.assemble(
            PromptStage.DSASPDMA,
            self._assembly_call(original_thought, context, retry=feedback is not None, agent_identity=agent_identity),
        )

    @staticmethod
    def _agent_identity(context: Optional[Any]) -> Any:
        """The agent's identity, approved amendments included: from the thought's context as the other drafters
        read it, else the stored identity node (base identity only: amendments load with the snapshot). Raises
        in QA when neither has one (fail closed); in production the call proceeds and the guard records it."""
        from ciris_engine.logic.formatters.identity import agent_identity_of

        identity = agent_identity_of(context)
        if identity:
            return identity
        from ciris_engine.logic.persistence.models.identity import retrieve_agent_identity
        from ciris_engine.schemas.infrastructure.identity_variance import IdentityData

        stored = retrieve_agent_identity()
        if stored is not None:
            logger.warning("DSASPDMA: the thought context carries no agent identity; using the stored identity node")
            return IdentityData(
                agent_id=stored.agent_id,
                description=stored.core_profile.description,
                role=stored.core_profile.role_description,
            )
        from ciris_engine.logic.prompt_assembly.assembler import current_guard_mode
        from ciris_engine.schemas.context.prompt_provenance import AssemblyMode

        if current_guard_mode() == AssemblyMode.FAIL_CLOSED:
            raise ValueError("DSASPDMA: no agent identity in the thought context or the store")
        logger.error("DSASPDMA: no agent identity in the thought context or the store; classifying without it")
        return None

    def _assembly_call(
        self, original_thought: Any, context: Optional[Any], retry: bool, agent_identity: Any = None
    ) -> "AssemblyCall":
        """The manifest's call facts, from trusted state only (the verified grant, verified amendments)."""
        from ciris_engine.logic.formatters.wa_approval import wa_authorization_of
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
            response_model=DSASPDMALLMResult.__name__,
            facts=policy_facts(authorization, agent_identity, id_scoped=False),
            language=self.prompt_loader.language,
        )

    def _create_messages(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
    ) -> List[JSONDict]:
        """Thin backward-compatible alias for :meth:`compose_messages` (#972)."""
        return self.compose_messages(original_thought, aspdma_result, context=context)

    def _convert_result(
        self,
        llm_result: DSASPDMALLMResult,
        original_params: DeferParams,
        resource_usage: Optional[JSONDict] = None,
    ) -> ActionSelectionDMAResult:
        """Merge DSASPDMA classification back into a typed DEFER action."""

        secondary_categories = [
            category
            for category in llm_result.secondary_need_categories
            if category != llm_result.primary_need_category
        ]
        rights_basis = llm_result.rights_basis or get_rights_basis_for_need_category(llm_result.primary_need_category)

        merged_context: Dict[str, str | List[str]] = dict(original_params.context or {})
        merged_context["deferral_reason_code"] = llm_result.operational_reason.value
        merged_context["primary_need_category"] = llm_result.primary_need_category.value
        merged_context["secondary_need_categories"] = [category.value for category in secondary_categories]
        merged_context["rights_basis"] = rights_basis
        if llm_result.domain_hint is not None:
            merged_context["domain_hint"] = llm_result.domain_hint.value
        # The typed field is the one source: a context key of the same name set
        # earlier (action selection writes free-form context) is not carried.
        for key in (PROPOSED_AMENDMENT_CONTEXT_KEY, M1_JUSTIFICATION_CONTEXT_KEY, IDENTITY_CHANGE_CONTEXT_KEY):
            merged_context.pop(key, None)
        proposed_amendment = _proposed_amendment(llm_result.proposed_amendment)
        m1_justification = _m1_justification(llm_result.m1_justification) if proposed_amendment else None
        if proposed_amendment is not None:
            if m1_justification is None:
                logger.warning("DSASPDMA: proposed identity amendment states no M-1 justification")
            merged_context.update(
                _identity_change_context(llm_result.reason_summary, proposed_amendment, m1_justification)
            )

        params = DeferParams(
            channel_id=original_params.channel_id,
            reason=llm_result.reason_summary,
            context=merged_context,
            defer_until=llm_result.defer_until or original_params.defer_until,
            reason_code=llm_result.operational_reason,
            needs_category=llm_result.primary_need_category,
            secondary_needs_categories=secondary_categories,
            rights_basis=rights_basis,
            domain_hint=llm_result.domain_hint or original_params.domain_hint,
            proposed_amendment=proposed_amendment,
            m1_justification=m1_justification,
        )
        # ActionSelectionDMAResult.resource_usage is JSONDict; LLMBus returns
        # a ResourceUsage Pydantic object. Convert via model_dump or pass
        # through if the caller already serialized it.
        resource_usage_dict: Optional[JSONDict]
        if resource_usage is None:
            resource_usage_dict = None
        elif hasattr(resource_usage, "model_dump"):
            resource_usage_dict = resource_usage.model_dump()
        else:
            resource_usage_dict = resource_usage  # already a dict
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale=f"DSASPDMA: {llm_result.reason_summary}",
            raw_llm_response=llm_result.model_dump_json(),
            resource_usage=resource_usage_dict,
        )

    @in_thought_language("original_thought", "context")
    async def evaluate_deferral_action(
        self,
        aspdma_result: ActionSelectionDMAResult,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
    ) -> ActionSelectionDMAResult:
        """Evaluate a DEFER action and classify it against the rights taxonomy."""

        if aspdma_result.selected_action != HandlerActionType.DEFER:
            raise ValueError(f"DSASPDMA requires DEFER action, got {aspdma_result.selected_action}")

        current_params = aspdma_result.action_parameters
        if not isinstance(current_params, DeferParams):
            raise TypeError(f"DSASPDMA expects DeferParams, got {type(current_params)}")

        messages, manifest = self.compose_prompt(
            original_thought, aspdma_result, context=context, conscience_feedback=conscience_feedback
        )
        with prompt_manifest_scope(manifest):
            llm_result, resource_usage = await self.call_llm_structured(
                messages=messages,
                response_model=DSASPDMALLMResult,
                max_tokens=8192,
                temperature=0.0,
                thought_id=original_thought.thought_id,
                task_id=original_thought.source_task_id,
            )

        sent_source = llm_result
        if llm_result.domain_hint and not llm_result.rights_basis:
            inferred_need = get_need_category_for_domain(llm_result.domain_hint)
            llm_result = DSASPDMALLMResult(
                reason_summary=llm_result.reason_summary,
                operational_reason=llm_result.operational_reason,
                primary_need_category=llm_result.primary_need_category,
                secondary_need_categories=llm_result.secondary_need_categories,
                rights_basis=get_rights_basis_for_need_category(llm_result.primary_need_category or inferred_need),
                domain_hint=llm_result.domain_hint,
                defer_until=llm_result.defer_until,
                proposed_amendment=llm_result.proposed_amendment,
                m1_justification=llm_result.m1_justification,
            )

        result = self._convert_result(llm_result, current_params, resource_usage=resource_usage)
        final = ActionSelectionDMAResult(
            selected_action=result.selected_action,
            action_parameters=result.action_parameters,
            rationale=result.rationale,
            raw_llm_response=result.raw_llm_response,
            reasoning=aspdma_result.reasoning,
            evaluation_time_ms=aspdma_result.evaluation_time_ms,
            resource_usage=result.resource_usage,
        )
        # This pass's own prompts ride privately; the action-selection prompts
        # are carried onto user_prompt/system_prompt by _run_verb_second_pass.
        return carry_sent_prompts(sent_source, final)

    async def evaluate(self, *args: Any, **kwargs: Any) -> ActionSelectionDMAResult:
        """Generic interface wrapper for consistency with other DMAs."""

        return await self.evaluate_deferral_action(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<DSASPDMAEvaluator model='{self.model_name}'>"
