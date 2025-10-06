import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic.formatters import (
    format_parent_task_chain,
    format_system_prompt_blocks,
    format_system_snapshot,
    format_thoughts_chain,
    format_user_profiles,
    format_user_prompt_blocks,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import COVENANT_TEXT
from ciris_engine.protocols.dma.base import CSDMAProtocol
from ciris_engine.schemas.dma.results import CSDMAResult

from .base_dma import BaseDMA
from .prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """=== Common Sense DMA Guidance ===
You are a Common Sense Evaluation agent. Your task is to assess a given "thought" for its alignment with general common-sense understanding of the physical world, typical interactions, and resource constraints on Earth, considering the provided context.
[... truncated for brevity ...]
"""


class CSDMAEvaluator(BaseDMA[ProcessingQueueItem, CSDMAResult], CSDMAProtocol):
    """
    Evaluates a thought for common-sense plausibility using an LLM
    and returns a structured CSDMAResult using the 'instructor' library.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        model_name: Optional[str] = None,
        max_retries: int = 2,
        environmental_kg: Optional[Any] = None,
        task_specific_kg: Optional[Any] = None,
        prompt_overrides: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> None:

        # Use provided model_name or default from base class
        super().__init__(
            service_registry=service_registry,
            model_name=model_name,
            max_retries=max_retries,
            prompt_overrides=prompt_overrides,
            **kwargs,
        )

        # Load prompts from YAML file
        self.prompt_loader = get_prompt_loader()
        self.prompt_template_data = self.prompt_loader.load_prompt_template("csdma_common_sense")

        # Client will be retrieved from the service registry during evaluation

        self.env_kg = environmental_kg  # Placeholder for now
        self.task_kg = task_specific_kg  # Placeholder for now
        # Log the final client type being used
        logger.info(f"CSDMAEvaluator initialized with model: {self.model_name}")

    def _create_csdma_messages_for_instructor(
        self,
        thought_content: str,
        context_summary: str,
        identity_context_block: str,
        system_snapshot_block: str,
        user_profiles_block: str,
    ) -> List[Dict[str, str]]:
        """Assemble prompt messages using canonical formatting utilities and prompt loader."""
        messages = []

        if self.prompt_loader.uses_covenant_header(self.prompt_template_data):
            messages.append({"role": "system", "content": COVENANT_TEXT})

        system_message = self.prompt_loader.get_system_message(
            self.prompt_template_data, context_summary=context_summary, original_thought_content=thought_content
        )

        formatted_system = format_system_prompt_blocks(
            identity_context_block,
            "",
            system_snapshot_block,
            user_profiles_block,
            None,
            system_message,
        )
        messages.append({"role": "system", "content": formatted_system})

        user_message = self.prompt_loader.get_user_message(
            self.prompt_template_data, context_summary=context_summary, original_thought_content=thought_content
        )

        if not user_message or user_message == f"Thought to evaluate: {thought_content}":
            user_message = format_user_prompt_blocks(
                format_parent_task_chain([]),
                format_thoughts_chain([{"content": thought_content}]),
                None,
            )

        messages.append({"role": "user", "content": user_message})

        return messages

    def _extract_context_from_modern_path(self, context: Any) -> tuple[str, str, str]:
        """Extract context strings from modern context object."""
        system_snapshot_str = ""
        user_profiles_str = ""
        context_summary = (
            "CIRIS AI Agent operating via Discord, API, or CLI - Digital/virtual interactions are normal and expected."
        )

        if hasattr(context, "system_snapshot") and context.system_snapshot:
            system_snapshot_str = format_system_snapshot(context.system_snapshot)
            if hasattr(context.system_snapshot, "user_profiles") and context.system_snapshot.user_profiles:
                user_profiles_str = format_user_profiles(context.system_snapshot.user_profiles)

            agent_identity = getattr(context.system_snapshot, "agent_identity", None)
            if agent_identity:
                context_summary = self._build_context_summary(agent_identity)
        elif hasattr(context, "user_profiles") and context.user_profiles:
            user_profiles_str = format_user_profiles(context.user_profiles)

        return system_snapshot_str, user_profiles_str, context_summary

    def _extract_context_from_legacy_path(self, thought_item: ProcessingQueueItem) -> tuple[str, str, str, str]:
        """Extract context strings from legacy thought_item.initial_context."""
        identity_block = ""
        system_snapshot_block = ""
        user_profiles_block = ""
        context_summary = (
            "CIRIS AI Agent operating via Discord, API, or CLI - Digital/virtual interactions are normal and expected."
        )

        if not hasattr(thought_item, "initial_context") or not thought_item.initial_context:
            return identity_block, system_snapshot_block, user_profiles_block, context_summary

        if not isinstance(thought_item.initial_context, dict):
            return identity_block, system_snapshot_block, user_profiles_block, context_summary

        system_snapshot = thought_item.initial_context.get("system_snapshot")
        if not system_snapshot:
            return identity_block, system_snapshot_block, user_profiles_block, context_summary

        system_snapshot_block = format_system_snapshot(system_snapshot)

        user_profiles_data = system_snapshot.get("user_profiles") if isinstance(system_snapshot, dict) else None
        user_profiles_block = format_user_profiles(user_profiles_data) if user_profiles_data else ""

        agent_identity = system_snapshot.get("agent_identity") if isinstance(system_snapshot, dict) else None
        if agent_identity:
            identity_block = self._build_identity_block(agent_identity)
            context_summary = self._build_context_summary(agent_identity)

        return identity_block, system_snapshot_block, user_profiles_block, context_summary

    def _build_identity_block(self, agent_identity: Any) -> str:
        """Build identity block from agent_identity data."""
        agent_id = (
            agent_identity.get("agent_id", "Unknown")
            if isinstance(agent_identity, dict)
            else getattr(agent_identity, "agent_id", "Unknown")
        )
        description = (
            agent_identity.get("description", "")
            if isinstance(agent_identity, dict)
            else getattr(agent_identity, "description", "")
        )
        role = (
            agent_identity.get("role", "") if isinstance(agent_identity, dict) else getattr(agent_identity, "role", "")
        )

        return (
            "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===\n"
            f"Agent: {agent_id}\n"
            f"Description: {description}\n"
            f"Role: {role}\n"
            "============================================"
        )

    def _build_context_summary(self, agent_identity: Any) -> str:
        """Build context summary from agent_identity data."""
        agent_id = (
            agent_identity.get("agent_id", "Unknown")
            if isinstance(agent_identity, dict)
            else getattr(agent_identity, "agent_id", "Unknown")
        )
        description = (
            agent_identity.get("description", "")
            if isinstance(agent_identity, dict)
            else getattr(agent_identity, "description", "")
        )
        role = (
            agent_identity.get("role", "") if isinstance(agent_identity, dict) else getattr(agent_identity, "role", "")
        )

        return (
            f"{agent_id} ({role}) - {description}. "
            f"Operating via Discord, API, or CLI in digital/virtual environment."
        )

    async def evaluate_thought(self, thought_item: ProcessingQueueItem, context: Optional[Any] = None) -> CSDMAResult:
        thought_content_str = str(thought_item.content)

        # Extract context using modern or legacy path
        if context:
            system_snapshot_str, user_profiles_str, context_summary = self._extract_context_from_modern_path(context)
            identity_block = ""
            system_snapshot_block = system_snapshot_str + user_profiles_str
            user_profiles_block = ""
        else:
            identity_block, system_snapshot_block, user_profiles_block, context_summary = (
                self._extract_context_from_legacy_path(thought_item)
            )

        messages = self._create_csdma_messages_for_instructor(
            thought_content_str,
            context_summary,
            identity_block,
            system_snapshot_block,
            user_profiles_block,
        )
        logger.debug(
            "CSDMA input to LLM for thought %s:\nSystem Snapshot Block: %s\nUser Profiles Block: %s\nContext Summary: %s",
            thought_item.thought_id,
            system_snapshot_block,
            user_profiles_block,
            context_summary,
        )

        try:
            result_tuple = await self.call_llm_structured(
                messages=messages, response_model=CSDMAResult, max_tokens=512, temperature=0.0
            )
            csdma_eval: CSDMAResult = result_tuple[0]

            # raw_llm_response field has been removed from CSDMAResult

            logger.info(
                f"CSDMA (instructor) evaluation successful for thought ID {thought_item.thought_id}: Score {csdma_eval.plausibility_score:.2f}"
            )
            return csdma_eval

        except Exception as e:
            logger.error(f"CSDMA evaluation failed for thought ID {thought_item.thought_id}: {e}", exc_info=True)
            return CSDMAResult(
                plausibility_score=0.0,
                flags=["LLM_Error", "defer_for_retry"],
                reasoning=f"Failed CSDMA evaluation: {str(e)}",
            )

    async def evaluate(self, *args: Any, **kwargs: Any) -> CSDMAResult:  # type: ignore[override]
        """Evaluate thought for common sense alignment."""
        # Extract arguments - maintain backward compatibility with PDMA pattern
        input_data = args[0] if args else kwargs.get("input_data")
        context = args[1] if len(args) > 1 else kwargs.get("context")

        if not input_data:
            raise ValueError("input_data is required")

        return await self.evaluate_thought(input_data, context)

    def __repr__(self) -> str:
        return f"<CSDMAEvaluator model='{self.model_name}' (using instructor)>"
