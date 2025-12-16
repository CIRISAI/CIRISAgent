import logging
from typing import Any, Dict, List, Optional

from ciris_engine.constants import DEFAULT_OPENAI_MODEL_NAME
from ciris_engine.logic.formatters import format_system_snapshot, format_user_profiles
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import COVENANT_TEXT
from ciris_engine.protocols.dma.base import PDMAProtocol
from ciris_engine.schemas.dma.results import EthicalDMAResult
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import get_prompt_loader

logger = logging.getLogger(__name__)


class EthicalPDMAEvaluator(BaseDMA[ProcessingQueueItem, EthicalDMAResult], PDMAProtocol):
    """
    Evaluates a thought against core ethical principles using an LLM
    and returns a structured EthicalDMAResult using the 'instructor' library.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        model_name: str = DEFAULT_OPENAI_MODEL_NAME,
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

        self.prompt_loader = get_prompt_loader()
        self.prompt_template_data = self.prompt_loader.load_prompt_template("pdma_ethical")

        # Store last user prompt for debugging/streaming
        self.last_user_prompt: Optional[str] = None

        logger.info(f"EthicalPDMAEvaluator initialized with model: {self.model_name}")

    async def evaluate(self, *args: Any, **kwargs: Any) -> EthicalDMAResult:  # type: ignore[override]
        # Extract arguments - maintain backward compatibility
        input_data = args[0] if args else kwargs.get("input_data")
        context = args[1] if len(args) > 1 else kwargs.get("context")

        if not input_data:
            raise ValueError("input_data is required")

        original_thought_content = str(input_data.content)
        logger.debug(f"Evaluating thought ID {input_data.thought_id}")

        # Fetch original task for context
        thought_depth = getattr(input_data, "thought_depth", 0)
        agent_occurrence_id = getattr(input_data, "agent_occurrence_id", "default")
        original_task = await self.fetch_original_task(input_data.source_task_id, agent_occurrence_id)
        task_context_str = self.format_task_context(original_task, thought_depth)

        system_snapshot_context_str = ""
        user_profile_context_str = ""
        if context and hasattr(context, "system_snapshot") and context.system_snapshot:
            system_snapshot_context_str = format_system_snapshot(context.system_snapshot)
            if hasattr(context.system_snapshot, "user_profiles") and context.system_snapshot.user_profiles:
                user_profile_context_str = format_user_profiles(context.system_snapshot.user_profiles)
        elif context and hasattr(context, "user_profiles") and context.user_profiles:
            user_profile_context_str = format_user_profiles(context.user_profiles)

        # Include task context in the full context
        full_context_str = (
            f"=== ORIGINAL TASK ===\n{task_context_str}\n\n" + system_snapshot_context_str + user_profile_context_str
        )

        messages: List[JSONDict] = []

        if self.prompt_loader.uses_covenant_header(self.prompt_template_data):
            messages.append({"role": "system", "content": COVENANT_TEXT})

        system_message = self.prompt_loader.get_system_message(
            self.prompt_template_data,
            original_thought_content=original_thought_content,
            full_context_str=full_context_str,
        )
        messages.append({"role": "system", "content": system_message})

        user_message_text = self.prompt_loader.get_user_message(
            self.prompt_template_data,
            original_thought_content=original_thought_content,
            full_context_str=full_context_str,
        )
        # Build multimodal content if images are present
        input_images = getattr(input_data, "images", []) or []
        if input_images:
            logger.info(f"[VISION] EthicalPDMA building multimodal content with {len(input_images)} images")
        user_content = self.build_multimodal_content(user_message_text, input_images)
        messages.append({"role": "user", "content": user_content})

        # Store user prompt for streaming/debugging
        self.last_user_prompt = user_message_text

        result_tuple = await self.call_llm_structured(
            messages=messages,
            response_model=EthicalDMAResult,
            max_tokens=4096,
            temperature=0.0,
            thought_id=input_data.thought_id,
            task_id=input_data.source_task_id,
        )
        response_obj: EthicalDMAResult = result_tuple[0]
        logger.info(f"Evaluation successful for thought ID {input_data.thought_id}")
        return response_obj

    def __repr__(self) -> str:
        return f"<EthicalPDMAEvaluator model='{self.model_name}'>"
