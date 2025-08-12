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


class CSDMAEvaluator(BaseDMA, CSDMAProtocol):
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

    async def evaluate_thought(self, thought_item: ProcessingQueueItem) -> CSDMAResult:

        thought_content_str = str(thought_item.content)

        context_summary = "Standard Earth-based physical context, unless otherwise specified in the thought."
        if hasattr(thought_item, "initial_context") and thought_item.initial_context:
            # Type narrow to dict
            if isinstance(thought_item.initial_context, dict) and "environment_context" in thought_item.initial_context:
                env_ctx = thought_item.initial_context["environment_context"]
                if isinstance(env_ctx, dict) and "description" in env_ctx:
                    context_summary = str(env_ctx["description"])
                elif isinstance(env_ctx, dict) and "current_channel" in env_ctx:
                    context_summary = f"Context: Discord channel '{env_ctx['current_channel']}'"
                elif isinstance(env_ctx, str):
                    context_summary = env_ctx

        # STRICT TYPE CHECKING - initial_context MUST be a dict
        if not isinstance(thought_item.initial_context, dict):
            raise ValueError(
                f"CRITICAL: initial_context must be a dict, got {type(thought_item.initial_context).__name__}! "
                "This is a fatal error. CSDMA requires properly typed inputs."
            )

        # Extract system_snapshot - MUST exist
        system_snapshot = thought_item.initial_context.get("system_snapshot")
        if not system_snapshot:
            raise ValueError(
                "CRITICAL: No system_snapshot in initial_context for CSDMA! "
                "This is a fatal error. Identity is required for ALL DMA evaluations."
            )

        # Extract agent_identity - MUST exist and be complete
        agent_identity = system_snapshot.get("agent_identity") if isinstance(system_snapshot, dict) else None
        if not agent_identity:
            raise ValueError(
                "CRITICAL: No agent_identity found in system_snapshot for CSDMA! "
                "Identity is required for ALL DMA evaluations. This is a fatal error."
            )

        # Validate ALL required identity fields
        agent_id = agent_identity.get("agent_id")
        description = agent_identity.get("description")
        role = agent_identity.get("role")

        if not agent_id:
            raise ValueError("CRITICAL: agent_id is missing from identity in CSDMA! This is a fatal error.")
        if not description:
            raise ValueError("CRITICAL: description is missing from identity in CSDMA! This is a fatal error.")
        if not role:
            raise ValueError("CRITICAL: role is missing from identity in CSDMA! This is a fatal error.")

        # Build identity block
        identity_block = "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===\n"
        identity_block += f"Agent: {agent_id}\n"
        identity_block += f"Description: {description}\n"
        identity_block += f"Role: {role}\n"
        identity_block += "============================================"

        # Format optional blocks
        user_profiles_data = system_snapshot.get("user_profiles")
        user_profiles_block = format_user_profiles(user_profiles_data) if user_profiles_data else ""
        system_snapshot_block = format_system_snapshot(system_snapshot)

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
        # Extract arguments - maintain backward compatibility
        input_data = args[0] if args else kwargs.get("input_data")

        if not input_data:
            raise ValueError("input_data is required")

        return await self.evaluate_thought(input_data)

    def __repr__(self) -> str:
        return f"<CSDMAEvaluator model='{self.model_name}' (using instructor)>"
