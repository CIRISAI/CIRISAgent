import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.logic.formatters import (
    format_system_prompt_blocks,
    format_system_snapshot,
    format_user_profiles,
    get_escalation_guidance,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import COVENANT_TEXT
from ciris_engine.protocols.dma.base import DSDMAProtocol
from ciris_engine.schemas.dma.core import DMAInputData
from ciris_engine.schemas.dma.results import DSDMAResult

from .base_dma import BaseDMA
from .prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)


class BaseDSDMA(BaseDMA, DSDMAProtocol):
    """
    Abstract Base Class for Domain-Specific Decision-Making Algorithms.
    Handles instructor client patching based on global config.
    """

    DEFAULT_TEMPLATE: Optional[str] = (
        "You are a domain-specific evaluator for the '{domain_name}' domain. "
        "Your primary goal is to assess how well a given 'thought' aligns with the specific rules, "
        "objectives, and knowledge pertinent to this domain. "
        "Consider the provided domain rules: '{rules_summary_str}' and the general platform context: '{context_str}'. "
        "Additionally, user profile information and system snapshot details will be provided with the thought for background awareness. "
        "When evaluating thoughts that might lead to TOOL actions, consider whether the tools available "
        "are appropriate for the domain and whether their use aligns with domain-specific best practices. "
        "Focus your evaluation on domain alignment."
    )

    def __init__(
        self,
        domain_name: str,
        service_registry: ServiceRegistry,
        model_name: Optional[str] = None,
        domain_specific_knowledge: Optional[Dict[str, Any]] = None,
        prompt_template: Optional[str] = None,
        **kwargs: Any,
    ) -> None:

        # Use provided model name or default
        resolved_model = model_name or "gpt-4"

        super().__init__(service_registry=service_registry, model_name=resolved_model, max_retries=2, **kwargs)

        self.domain_name = domain_name
        self.domain_specific_knowledge = domain_specific_knowledge if domain_specific_knowledge else {}

        self.prompt_loader = get_prompt_loader()
        try:
            prompt_collection = self.prompt_loader.load_prompt_template("dsdma_base")
            self.prompt_template_data = prompt_collection
            # Get system guidance header from the collection
            system_guidance = prompt_collection.get_prompt("system_guidance_header")
            if prompt_template is not None:
                self.prompt_template = prompt_template
            elif system_guidance:
                self.prompt_template = system_guidance  # get_prompt returns a string
            else:
                self.prompt_template = ""
        except FileNotFoundError:
            logger.warning(f"DSDMA base prompt template not found for domain '{domain_name}', using fallback")
            # Create a PromptCollection with fallback data
            from ciris_engine.schemas.dma.prompts import PromptCollection, PromptTemplate

            self.prompt_template_data = PromptCollection(
                name="dsdma_base_fallback",
                description="Fallback DSDMA prompt collection",
                prompts={
                    "system_guidance_header": PromptTemplate(
                        name="system_guidance_header",
                        template=self.DEFAULT_TEMPLATE if self.DEFAULT_TEMPLATE else "",
                        description="Fallback system guidance",
                    )
                },
            )
            self.prompt_template = (
                prompt_template
                if prompt_template is not None
                else (self.DEFAULT_TEMPLATE if self.DEFAULT_TEMPLATE else "")
            )

        logger.info(f"BaseDSDMA '{self.domain_name}' initialized with model: {self.model_name}")

    class LLMOutputForDSDMA(BaseModel):
        score: float = Field(..., ge=0.0, le=1.0)
        recommended_action: Optional[str] = Field(default=None)
        flags: List[str] = Field(default_factory=list)
        reasoning: str

    async def evaluate(self, *args: Any, **kwargs: Any) -> DSDMAResult:  # type: ignore[override]
        """Evaluate thought within domain-specific context."""
        # Extract arguments - maintain backward compatibility
        input_data = args[0] if args else kwargs.get("input_data")
        current_context = args[1] if len(args) > 1 else kwargs.get("current_context")

        if not input_data:
            raise ValueError("input_data is required")

        # Extract DMAInputData if provided
        dma_input_data: Optional[DMAInputData] = None
        if current_context and isinstance(current_context, dict):
            # Try to extract DMAInputData if it's in the context
            if "dma_input_data" in current_context:
                dma_input_data = current_context["dma_input_data"]
            else:
                logger.debug("No DMAInputData in context, using legacy Dict[str, Any]")

        return await self.evaluate_thought(input_data, dma_input_data)

    async def evaluate_thought(
        self, thought_item: ProcessingQueueItem, current_context: Optional[DMAInputData]
    ) -> DSDMAResult:

        thought_content_str = str(thought_item.content)

        # Use DMAInputData if provided, otherwise fall back to ProcessingQueueItem context
        if current_context:
            # Use typed DMAInputData fields
            context_str = f"Round {current_context.round_number}, Ponder count: {current_context.current_thought_depth}"
            rules_summary_str = (
                self.domain_specific_knowledge.get("rules_summary", "General domain guidance")
                if isinstance(self.domain_specific_knowledge, dict)
                else "General domain guidance"
            )

            # Get system snapshot from DMAInputData - CRITICAL requirement
            if not current_context.system_snapshot:
                raise ValueError(
                    f"CRITICAL: System snapshot is required for DSDMA evaluation in domain '{self.domain_name}'"
                )
            system_snapshot = current_context.system_snapshot
            user_profiles_data = system_snapshot.user_profiles
            # Convert list of UserProfile to dict format expected by format_user_profiles
            user_profiles_dict = {}
            for profile in user_profiles_data:
                user_profiles_dict[profile.user_id] = {
                    "name": profile.display_name,
                    "nick": profile.display_name,
                    "interests": getattr(profile, "interests", []),
                    "primary_channel": getattr(profile, "primary_channel", None),
                }
            user_profiles_block = format_user_profiles(user_profiles_dict)
            system_snapshot_block = format_system_snapshot(system_snapshot)

            # Get identity from system snapshot - CRITICAL requirement
            if not system_snapshot.agent_identity:
                raise ValueError(
                    f"CRITICAL: Agent identity is required for DSDMA evaluation in domain '{self.domain_name}'"
                )
            # Format identity block from agent_identity data
            identity_block = f"Agent: {system_snapshot.agent_identity.get('agent_id', 'Unknown')}\n"
            identity_block += f"Description: {system_snapshot.agent_identity.get('description', 'No description')}\n"
            identity_block += f"Role: {system_snapshot.agent_identity.get('role', 'No role defined')}"
        else:
            # Fallback to old logic for backwards compatibility
            context_str = "No specific platform context provided."
            rules_summary_str = (
                self.domain_specific_knowledge.get("rules_summary", "General domain guidance")
                if isinstance(self.domain_specific_knowledge, dict)
                else "General domain guidance"
            )

            system_snapshot_block = ""
            user_profiles_block = ""
            identity_block = ""

            if hasattr(thought_item, "context") and thought_item.context:
                system_snapshot = thought_item.context.get("system_snapshot")
                if system_snapshot:
                    user_profiles_data = system_snapshot.get("user_profiles")
                    user_profiles_block = format_user_profiles(user_profiles_data)
                    system_snapshot_block = format_system_snapshot(system_snapshot)

                identity_block = thought_item.context.get("identity_context", "")

        escalation_guidance_block = get_escalation_guidance(0)

        # Import crisis resources formatter
        from ciris_engine.logic.formatters import format_crisis_resources_block

        crisis_resources_block = format_crisis_resources_block(include_full_disclaimer=False)

        task_history_block = ""

        template_has_blocks = any(
            placeholder in self.prompt_template
            for placeholder in [
                "{task_history_block}",
                "{escalation_guidance_block}",
                "{system_snapshot_block}",
                "{user_profiles_block}",
                "{crisis_resources_block}",
            ]
        )

        if template_has_blocks:
            try:
                system_message_content = self.prompt_template.format(
                    task_history_block=task_history_block,
                    escalation_guidance_block=escalation_guidance_block,
                    system_snapshot_block=system_snapshot_block,
                    user_profiles_block=user_profiles_block,
                    crisis_resources_block=crisis_resources_block,
                    domain_name=self.domain_name,
                    rules_summary_str=rules_summary_str,
                    context_str=context_str,
                )
            except KeyError as e:
                logger.error(f"Missing template variable in DSDMA template: {e}")
                system_message_content = format_system_prompt_blocks(
                    identity_block,  # Now guaranteed to be non-empty when we have current_context
                    task_history_block,
                    system_snapshot_block,
                    user_profiles_block,
                    escalation_guidance_block,
                    f"You are a domain-specific evaluator for the '{self.domain_name}' domain. "
                    f"Consider the domain rules: '{rules_summary_str}' and context: '{context_str}'.",
                )
        else:
            system_message_template = self.prompt_template
            if not system_message_template:
                system_message_template = (
                    "You are a domain-specific evaluator for the '{domain_name}' domain. "
                    "Your primary goal is to assess how well a given 'thought' aligns with the specific rules, "
                    "objectives, and knowledge pertinent to this domain. "
                    "Consider the provided domain rules: '{rules_summary_str}' and the general platform context: '{context_str}'. "
                    "Additionally, user profile information and system snapshot details will be provided with the thought for background awareness. "
                    "Focus your evaluation on domain alignment."
                )

            system_message_content = system_message_template.format(
                domain_name=self.domain_name, rules_summary_str=rules_summary_str, context_str=context_str
            )

        full_snapshot_and_profile_context_str = system_snapshot_block + user_profiles_block
        user_message_content = f"{full_snapshot_and_profile_context_str}\nEvaluate this thought for the '{self.domain_name}' domain: \"{thought_content_str}\""

        logger.debug(
            f"DSDMA '{self.domain_name}' input to LLM for thought {thought_item.thought_id}:\nSystem: {system_message_content}\nUser: {user_message_content}"
        )

        messages = [
            {"role": "system", "content": COVENANT_TEXT},
            {"role": "system", "content": system_message_content},
            {"role": "user", "content": user_message_content},
        ]

        try:
            llm_eval_data, _ = await self.call_llm_structured(
                messages=messages, response_model=BaseDSDMA.LLMOutputForDSDMA, max_tokens=512, temperature=0.0
            )

            result = DSDMAResult(
                domain=self.domain_name,
                domain_alignment=min(max(llm_eval_data.score, 0.0), 1.0),
                flags=llm_eval_data.flags,
                reasoning=llm_eval_data.reasoning,
            )
            logger.info(
                f"DSDMA '{self.domain_name}' (instructor) evaluation successful for thought ID {thought_item.thought_id}: "
                f"Domain Alignment: {result.domain_alignment}"
            )
            # raw_llm_response field has been removed from DSDMAResult
            return result
        except Exception as e:
            logger.error(
                f"DSDMA {self.domain_name} evaluation failed for thought ID {thought_item.thought_id}: {e}",
                exc_info=True,
            )
            return DSDMAResult(
                domain=self.domain_name,
                domain_alignment=0.0,
                flags=["LLM_Error_Instructor"],
                reasoning=f"Failed DSDMA evaluation via instructor: {str(e)}",
            )

    async def evaluate_alias(self, input_data: ProcessingQueueItem, **kwargs: Any) -> DSDMAResult:
        """Alias for evaluate_thought to satisfy BaseDMA."""
        # Extract DMAInputData if available, otherwise None
        context_raw = kwargs.get("current_context")
        dma_input_data: Optional[DMAInputData] = None

        if isinstance(context_raw, dict) and "dma_input_data" in context_raw:
            dma_input_data = context_raw["dma_input_data"]
        elif isinstance(context_raw, DMAInputData):
            dma_input_data = context_raw

        return await self.evaluate_thought(input_data, dma_input_data)

    def __repr__(self) -> str:
        return f"<BaseDSDMA domain='{self.domain_name}'>"
        # No legacy field names present; v1 field names are already used throughout.
