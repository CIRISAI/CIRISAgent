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
from typing import Any, Dict, List, Optional

from ciris_engine.logic.formatters import (
    format_system_prompt_blocks,
    format_system_snapshot,
    format_user_profiles,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import COVENANT_TEXT
from ciris_engine.protocols.dma.base import IDMAProtocol
from ciris_engine.schemas.dma.results import IDMAResult
from ciris_engine.schemas.runtime.models import ImageContent
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import get_prompt_loader

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

        # Load prompts from YAML file
        self.prompt_loader = get_prompt_loader()
        self.prompt_template_data = self.prompt_loader.load_prompt_template("idma")

        # Store last user prompt for debugging/streaming
        self.last_user_prompt: Optional[str] = None

        logger.info(f"IDMAEvaluator initialized with model: {self.model_name}")

    def _create_idma_messages(
        self,
        thought_content: str,
        context_summary: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        prior_dma_context: str,
        images: Optional[List[ImageContent]] = None,
    ) -> List[JSONDict]:
        """Assemble prompt messages for IDMA evaluation."""
        messages: List[JSONDict] = []

        # Add covenant if configured
        if self.prompt_loader.uses_covenant_header(self.prompt_template_data):
            messages.append({"role": "system", "content": COVENANT_TEXT})

        # Get system message from prompt template
        system_message = self.prompt_loader.get_system_message(
            self.prompt_template_data,
            context_summary=context_summary,
            original_thought_content=thought_content,
        )

        # Format with standard blocks
        formatted_system = format_system_prompt_blocks(
            "",  # identity block - not needed for IDMA
            "",  # additional context
            system_snapshot_block,
            user_profiles_block,
            None,
            system_message,
        )
        messages.append({"role": "system", "content": formatted_system})

        # Get user message from template
        user_message_text = self.prompt_loader.get_user_message(
            self.prompt_template_data,
            context_summary=context_summary,
            original_thought_content=thought_content,
            prior_dma_context=prior_dma_context,
        )

        # Build multimodal content if images are present
        images_list = images or []
        if images_list:
            logger.info(f"[VISION] IDMA building multimodal content with {len(images_list)} images")
        user_content = self.build_multimodal_content(user_message_text, images_list)
        messages.append({"role": "user", "content": user_content})

        return messages

    def _extract_context_data(self, context: Optional[Any]) -> tuple[str, str, str]:
        """Extract context strings from context object."""
        system_snapshot_str = ""
        user_profiles_str = ""
        context_summary = "CIRIS AI Agent - evaluating information diversity"

        if not context:
            return system_snapshot_str, user_profiles_str, context_summary

        if hasattr(context, "system_snapshot") and context.system_snapshot:
            system_snapshot_str = format_system_snapshot(context.system_snapshot)
            if hasattr(context.system_snapshot, "user_profiles") and context.system_snapshot.user_profiles:
                user_profiles_str = format_user_profiles(context.system_snapshot.user_profiles)

            agent_identity = getattr(context.system_snapshot, "agent_identity", None)
            if agent_identity:
                agent_id = getattr(agent_identity, "agent_id", "Unknown")
                context_summary = f"{agent_id} - evaluating information diversity and source independence"
        elif hasattr(context, "user_profiles") and context.user_profiles:
            user_profiles_str = format_user_profiles(context.user_profiles)

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
            context_parts.append(f"=== Ethical PDMA Analysis ===\n"
                                 f"Stakeholders: {getattr(ethical_result, 'stakeholders', 'N/A')}\n"
                                 f"Conflicts: {getattr(ethical_result, 'conflicts', 'N/A')}\n"
                                 f"Reasoning: {getattr(ethical_result, 'reasoning', 'N/A')}")

        if csdma_result:
            context_parts.append(f"=== Common Sense Analysis ===\n"
                                 f"Plausibility: {getattr(csdma_result, 'plausibility_score', 'N/A')}\n"
                                 f"Flags: {getattr(csdma_result, 'flags', [])}\n"
                                 f"Reasoning: {getattr(csdma_result, 'reasoning', 'N/A')}")

        if dsdma_result:
            context_parts.append(f"=== Domain-Specific Analysis ===\n"
                                 f"Domain: {getattr(dsdma_result, 'domain', 'N/A')}\n"
                                 f"Alignment: {getattr(dsdma_result, 'domain_alignment', 'N/A')}\n"
                                 f"Reasoning: {getattr(dsdma_result, 'reasoning', 'N/A')}")

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
        task_context_str = self.format_task_context(original_task, thought_depth)

        # Extract context data
        system_snapshot_str, user_profiles_str, context_summary = self._extract_context_data(context)

        # Build prior DMA context for analysis
        prior_dma_context = self._build_prior_dma_context(ethical_result, csdma_result, dsdma_result)

        # Prepend task context to system snapshot
        task_context_block = f"=== ORIGINAL TASK ===\n{task_context_str}\n\n"
        combined_snapshot_block = task_context_block + system_snapshot_str + user_profiles_str

        # Get images from thought item
        thought_images = getattr(thought_item, "images", []) or []

        messages = self._create_idma_messages(
            thought_content_str,
            context_summary,
            system_snapshot_block=combined_snapshot_block,
            user_profiles_block="",
            prior_dma_context=prior_dma_context,
            images=thought_images,
        )

        # Store user prompt for streaming/debugging
        user_messages = [m for m in messages if m.get("role") == "user"]
        content = user_messages[-1]["content"] if user_messages else None
        self.last_user_prompt = str(content) if content is not None else None

        logger.debug(
            "IDMA input to LLM for thought %s:\nContext Summary: %s",
            thought_item.thought_id,
            context_summary,
        )

        try:
            result_tuple = await self.call_llm_structured(
                messages=messages,
                response_model=IDMAResult,
                max_tokens=4096,
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
