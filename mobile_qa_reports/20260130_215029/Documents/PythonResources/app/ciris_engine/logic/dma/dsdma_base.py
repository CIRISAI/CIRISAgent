import logging
from typing import Any, Dict, List, Optional, Union, cast

from pydantic import BaseModel, Field

from ciris_engine.logic.formatters import (
    format_system_prompt_blocks,
    format_system_snapshot,
    format_user_profiles,
    get_escalation_guidance,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils.constants import COVENANT_TEXT
from ciris_engine.protocols.dma.base import DSDMAProtocol
from ciris_engine.schemas.dma.core import DMAInputData
from ciris_engine.schemas.dma.results import DSDMAResult
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)


class BaseDSDMA(BaseDMA[DMAInputData, DSDMAResult], DSDMAProtocol):
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
        domain_specific_knowledge: Optional[JSONDict] = None,
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
            from ciris_engine.schemas.dma.prompts import PromptCollection

            self.prompt_template_data = PromptCollection(
                component_name="dsdma_base_fallback",
                description="Fallback DSDMA prompt collection",
                system_guidance_header=self.DEFAULT_TEMPLATE if self.DEFAULT_TEMPLATE else "",
            )
            self.prompt_template = (
                prompt_template
                if prompt_template is not None
                else (self.DEFAULT_TEMPLATE if self.DEFAULT_TEMPLATE else "")
            )

        # Store last user prompt for debugging/streaming
        self.last_user_prompt: Optional[str] = None

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
                logger.debug("No DMAInputData in context, using legacy JSONDict")

        return await self.evaluate_thought(input_data, dma_input_data)

    async def evaluate_thought(
        self, thought_item: ProcessingQueueItem, current_context: Optional[DMAInputData]
    ) -> DSDMAResult:

        thought_content_str = str(thought_item.content)

        # Fetch original task for context
        thought_depth = getattr(thought_item, "thought_depth", 0)
        agent_occurrence_id = getattr(thought_item, "agent_occurrence_id", "default")
        original_task = await self.fetch_original_task(thought_item.source_task_id, agent_occurrence_id)
        task_context_str = self.format_task_context(original_task, thought_depth)
        task_context_block = f"=== ORIGINAL TASK ===\n{task_context_str}\n\n"

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
            # Format identity block from agent_identity data - FAIL FAST if incomplete
            # Type narrow to dict for .get() access
            agent_identity = system_snapshot.agent_identity
            if isinstance(agent_identity, dict):
                agent_id = agent_identity.get("agent_id")
                description = agent_identity.get("description")
                role = agent_identity.get("role")
            else:
                # It's IdentityData model
                agent_id = agent_identity.agent_id
                description = agent_identity.description
                role = agent_identity.role

            # CRITICAL: Identity must be complete - no defaults allowed
            if not agent_id:
                raise ValueError(f"CRITICAL: agent_id is missing from identity! This is a fatal error.")
            if not description:
                raise ValueError(f"CRITICAL: description is missing from identity! This is a fatal error.")
            if not role:
                raise ValueError(f"CRITICAL: role is missing from identity! This is a fatal error.")

            identity_block = "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===\n"
            identity_block += f"Agent: {agent_id}\n"
            identity_block += f"Description: {description}\n"
            identity_block += f"Role: {role}\n"
            identity_block += "============================================"
        else:
            # NO FALLBACK - STRICT TYPE CHECKING ONLY
            # When no DMAInputData, we still need to get identity from ProcessingQueueItem
            context_str = "No specific platform context provided."
            rules_summary_str = (
                self.domain_specific_knowledge.get("rules_summary", "General domain guidance")
                if isinstance(self.domain_specific_knowledge, dict)
                else "General domain guidance"
            )

            # STRICT TYPE CHECKING - initial_context MUST be a dict
            if not isinstance(thought_item.initial_context, dict):
                raise ValueError(
                    f"CRITICAL: initial_context must be a dict, got {type(thought_item.initial_context).__name__}! "
                    f"This is a fatal error. DSDMA domain '{self.domain_name}' requires properly typed inputs."
                )

            # Extract system_snapshot - MUST exist
            system_snapshot_raw = thought_item.initial_context.get("system_snapshot")
            if not system_snapshot_raw:
                raise ValueError(
                    f"CRITICAL: No system_snapshot in initial_context for DSDMA domain '{self.domain_name}'! "
                    "This is a fatal error. Identity is required for ALL DMA evaluations."
                )

            # Extract agent_identity - MUST exist and be complete
            agent_identity_raw = (
                system_snapshot_raw.get("agent_identity") if isinstance(system_snapshot_raw, dict) else None
            )
            if not agent_identity_raw:
                raise ValueError(
                    f"CRITICAL: No agent_identity found in system_snapshot for DSDMA domain '{self.domain_name}'! "
                    "Identity is required for ALL DMA evaluations. This is a fatal error."
                )

            # Validate ALL required identity fields - type narrow for dict access
            if not isinstance(agent_identity_raw, dict):
                raise ValueError(
                    f"CRITICAL: agent_identity must be a dict, got {type(agent_identity_raw).__name__}! "
                    f"This is a fatal error. DSDMA domain '{self.domain_name}' requires properly typed inputs."
                )
            agent_id = agent_identity_raw.get("agent_id")
            description = agent_identity_raw.get("description")
            role = agent_identity_raw.get("role")

            if not agent_id:
                raise ValueError(
                    f"CRITICAL: agent_id is missing from identity in DSDMA domain '{self.domain_name}'! This is a fatal error."
                )
            if not description:
                raise ValueError(
                    f"CRITICAL: description is missing from identity in DSDMA domain '{self.domain_name}'! This is a fatal error."
                )
            if not role:
                raise ValueError(
                    f"CRITICAL: role is missing from identity in DSDMA domain '{self.domain_name}'! This is a fatal error."
                )

            # Build identity block
            identity_block = "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===\n"
            identity_block += f"Agent: {agent_id}\n"
            identity_block += f"Description: {description}\n"
            identity_block += f"Role: {role}\n"
            identity_block += "============================================"

            # Format optional blocks - type narrow for .get() access
            if isinstance(system_snapshot_raw, dict):
                user_profiles_data_raw = system_snapshot_raw.get("user_profiles")
                # format_user_profiles accepts Union[List[Any], dict[str, Any], None]
                user_profiles_block = format_user_profiles(user_profiles_data_raw) if user_profiles_data_raw else ""
                # Cast dict to SystemSnapshot for format_system_snapshot
                system_snapshot_block = format_system_snapshot(cast(SystemSnapshot, system_snapshot_raw))
            else:
                # system_snapshot_raw is not a dict - shouldn't happen but handle gracefully
                user_profiles_block = ""
                system_snapshot_block = ""

        escalation_guidance_block = get_escalation_guidance(0)

        # Import crisis resources formatter
        from ciris_engine.logic.formatters import format_crisis_resources_block

        crisis_resources_block = format_crisis_resources_block(include_full_disclaimer=False)

        task_history_block = ""

        template_has_blocks = any(
            placeholder in self.prompt_template
            for placeholder in [
                "{identity_block}",
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
                    identity_block=identity_block,
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

        full_snapshot_and_profile_context_str = task_context_block + system_snapshot_block + user_profiles_block
        user_message_content = f"{full_snapshot_and_profile_context_str}\nEvaluate this thought for the '{self.domain_name}' domain: \"{thought_content_str}\""

        # Store user prompt for streaming/debugging
        self.last_user_prompt = user_message_content

        logger.debug(
            f"DSDMA '{self.domain_name}' input to LLM for thought {thought_item.thought_id}:\nSystem: {system_message_content}\nUser: {user_message_content}"
        )

        # CRITICAL: Identity block must ALWAYS be first in system message after covenant
        # Prepend identity to system message if not already included
        if identity_block and "CORE IDENTITY" not in system_message_content:
            system_message_content = identity_block + "\n\n" + system_message_content

        # Get images from thought item for multimodal
        thought_images = getattr(thought_item, "images", []) or []
        if thought_images:
            logger.info(
                f"[VISION] DSDMA '{self.domain_name}' building multimodal content with {len(thought_images)} images"
            )
        user_content = self.build_multimodal_content(user_message_content, thought_images)

        messages: List[JSONDict] = [
            {"role": "system", "content": COVENANT_TEXT},
            {"role": "system", "content": system_message_content},
            {"role": "user", "content": user_content},
        ]

        try:
            llm_eval_data, _ = await self.call_llm_structured(
                messages=messages,
                response_model=BaseDSDMA.LLMOutputForDSDMA,
                max_tokens=4096,
                temperature=0.0,
                thought_id=thought_item.thought_id,
                task_id=thought_item.source_task_id,
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
