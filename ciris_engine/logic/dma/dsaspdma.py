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
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.formatters import format_system_prompt_blocks
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import get_localized_accord_text
from ciris_engine.schemas.actions.parameters import DeferParams
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

if TYPE_CHECKING:
    from ciris_engine.schemas.dma.prompts import PromptCollection

logger = logging.getLogger(__name__)


class DSASPDMALLMResult(BaseModel):
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

    model_config = ConfigDict(extra="forbid")


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
        self.last_user_prompt: Optional[str] = None
        self.last_system_prompt: Optional[str] = None
        # Per-thought language override; populated by _sync_language_from_context.
        # When None, the loader falls back to env var (CIRIS_PREFERRED_LANGUAGE).
        self._explicit_language: Optional[str] = None

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""

        return get_prompt_loader(language=self._explicit_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect runtime language changes."""

        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    def _sync_language_from_context(self, context: Optional[Any]) -> None:
        """Sync prompt language from the current user context.

        Always assigns _explicit_language to the value derived from THIS
        thought — including None when no profile data is available — so a
        reused evaluator instance never inherits a previous thought's
        language. Without this reset, thought A in `am` followed by thought
        B with no profile would silently keep loading Amharic prompts.
        """

        preferred_language: Optional[str] = None
        user_profiles: Optional[Any] = None

        if context:
            if hasattr(context, "system_snapshot") and getattr(context, "system_snapshot", None):
                system_snapshot = getattr(context, "system_snapshot")
                user_profiles = getattr(system_snapshot, "user_profiles", None)
            elif isinstance(context, dict):
                system_snapshot = context.get("system_snapshot")
                if isinstance(system_snapshot, dict):
                    user_profiles = system_snapshot.get("user_profiles")
                elif system_snapshot is not None:
                    user_profiles = getattr(system_snapshot, "user_profiles", None)

        if user_profiles:
            first_profile = user_profiles[0]
            preferred_language = (
                first_profile.get("preferred_language")
                if isinstance(first_profile, dict)
                else getattr(first_profile, "preferred_language", None)
            )

        if preferred_language != self._explicit_language:
            # The prompt_loader property reads _explicit_language on next
            # access and returns the per-language cached loader. No global
            # mutation, no cross-thread bleed for concurrent thoughts.
            self._explicit_language = preferred_language
            if preferred_language:
                logger.debug(f"DSASPDMA: Synced prompt language to {preferred_language}")
            else:
                logger.debug("DSASPDMA: Cleared prompt language (no profile/context)")

    def _get_prompt_value(self, key: str) -> Optional[str]:
        """Read a prompt block from PromptCollection or dict overrides."""

        template = self.prompt_template_data
        if isinstance(template, PromptCollection):
            return template.get_prompt(key)
        if isinstance(template, dict):
            value = template.get(key)
            return str(value) if isinstance(value, str) else None
        return None

    def _require_prompt_value(self, key: str) -> str:
        """Read a required prompt block or fail loudly during prompt construction."""

        value = self._get_prompt_value(key)
        if value is None:
            raise ValueError(f"DSASPDMA prompt template missing required key: {key}")
        return value

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

    def _create_messages(
        self,
        original_thought: ProcessingQueueItem,
        aspdma_result: ActionSelectionDMAResult,
        context: Optional[Any] = None,
    ) -> List[JSONDict]:
        """Create localized messages for DSASPDMA evaluation."""

        self._sync_language_from_context(context)

        current_params = aspdma_result.action_parameters
        if not isinstance(current_params, DeferParams):
            raise TypeError(f"DSASPDMA expects DeferParams, got {type(current_params)}")

        system_message = format_system_prompt_blocks(
            self._require_prompt_value("system_guidance_header"),
            self._require_prompt_value("evaluation_steps"),
            self._require_prompt_value("response_format"),
            self._require_prompt_value("closing_reminder"),
        )

        original_thought_content = getattr(getattr(original_thought, "content", None), "text", "") or ""
        taxonomy_text = self._get_prompt_value("taxonomy_text") or build_deferral_taxonomy_prompt(
            self.prompt_loader.language
        )
        context_block = self._get_prompt_value("context_integration") or (
            "Original thought:\n{original_thought_content}\n\n"
            "ASPDMA reasoning:\n{aspdma_reasoning}\n\n"
            "Current deferral reason:\n{current_reason}\n\n"
            "Current context:\n{current_context}\n\n"
            "{taxonomy_text}"
        )
        user_message = context_block.format(
            original_thought_content=original_thought_content,
            aspdma_reasoning=aspdma_result.rationale,
            current_reason=current_params.reason,
            current_context=self._format_original_context(current_params),
            current_defer_until=current_params.defer_until or "none",
            current_domain_hint=self._get_original_domain_hint(current_params),
            taxonomy_text=taxonomy_text,
            domain_hint_options=", ".join(domain.value for domain in DomainCategory),
        )

        self.last_system_prompt = system_message
        self.last_user_prompt = user_message

        messages: List[JSONDict] = []
        accord_text = get_localized_accord_text(self.prompt_loader.language)
        if accord_text:
            messages.append({"role": "system", "content": accord_text})
        messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": user_message})
        return messages

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
        )
        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale=f"DSASPDMA: {llm_result.reason_summary}",
            raw_llm_response=llm_result.model_dump_json(),
            resource_usage=resource_usage,
            user_prompt=self.last_user_prompt,
        )

    async def evaluate_deferral_action(
        self,
        aspdma_result: ActionSelectionDMAResult,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
    ) -> ActionSelectionDMAResult:
        """Evaluate a DEFER action and classify it against the rights taxonomy."""

        if aspdma_result.selected_action != HandlerActionType.DEFER:
            raise ValueError(f"DSASPDMA requires DEFER action, got {aspdma_result.selected_action}")

        current_params = aspdma_result.action_parameters
        if not isinstance(current_params, DeferParams):
            raise TypeError(f"DSASPDMA expects DeferParams, got {type(current_params)}")

        messages = self._create_messages(original_thought, aspdma_result, context=context)
        llm_result, resource_usage = await self.call_llm_structured(
            messages=messages,
            response_model=DSASPDMALLMResult,
            max_tokens=16384,
            temperature=0.0,
            thought_id=original_thought.thought_id,
            task_id=original_thought.source_task_id,
        )

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
            )

        result = self._convert_result(llm_result, current_params, resource_usage=resource_usage)
        return ActionSelectionDMAResult(
            selected_action=result.selected_action,
            action_parameters=result.action_parameters,
            rationale=result.rationale,
            raw_llm_response=result.raw_llm_response,
            reasoning=aspdma_result.reasoning,
            evaluation_time_ms=aspdma_result.evaluation_time_ms,
            resource_usage=result.resource_usage,
            user_prompt=result.user_prompt,
        )

    async def evaluate(self, *args: Any, **kwargs: Any) -> ActionSelectionDMAResult:
        """Generic interface wrapper for consistency with other DMAs."""

        return await self.evaluate_deferral_action(*args, **kwargs)

    def __repr__(self) -> str:
        return f"<DSASPDMAEvaluator model='{self.model_name}'>"
