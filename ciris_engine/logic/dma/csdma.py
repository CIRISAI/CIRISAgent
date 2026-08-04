import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ciris_engine.schemas.dma.prompts import PromptCollection

from ciris_engine.logic.formatters import (
    append_round1_accord_blocks,
    format_parent_task_chain,
    format_system_prompt_blocks,
    format_system_snapshot,
    format_thoughts_chain,
    format_user_profiles,
    format_user_prompt_blocks,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.protocols.dma.base import CSDMAProtocol
from ciris_engine.schemas.dma.results import CSDMAResult
from ciris_engine.schemas.runtime.models import ImageContent
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader
from .template_overrides import additive

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

        # Get prompt loader (do NOT cache template - language may change at runtime)
        self._prompt_template_name = "csdma_common_sense"

        # Store last prompts for debugging/streaming
        self.last_user_prompt: Optional[str] = None
        self.last_system_prompt: Optional[str] = None

        # Client will be retrieved from the service registry during evaluation

        self.env_kg = environmental_kg  # Placeholder for now
        self.task_kg = task_specific_kg  # Placeholder for now

        # Per-thought language override populated from user_profiles. None
        # falls back to env var. Avoids the legacy global set_prompt_language
        # path which mutated shared state.
        self._explicit_language: Optional[str] = None

        # Log the final client type being used
        logger.info(f"CSDMAEvaluator initialized with model: {self.model_name}")

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""
        return get_prompt_loader(language=self._explicit_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect language changes.

        IMPORTANT: Do NOT cache this value. The user's preferred language may
        change at runtime via the settings page, and we need to load the
        correct localized template for each request.
        """
        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    def _create_csdma_messages_for_instructor(
        self,
        thought_content: str,
        context_summary: str,
        identity_context_block: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        images: Optional[List[ImageContent]] = None,
    ) -> List[JSONDict]:
        """Assemble prompt messages using canonical formatting utilities and prompt loader.

        Template overrides (from the agent template's `csdma_overrides`) are
        FIELD-scoped — see `dma/template_overrides.py`. Replacing one field must
        never disable another (#996):

        - `system_prompt` REPLACES the `system_guidance_header` field. The other
          five fields `get_system_message` composes are unaffected.
        - `user_prompt_template` is ADDITIVE: it leads, and the composed user
          message follows undiminished. `context_integration` carries live slots
          (`context_summary`), so it is not fit for replacement.
        """
        messages: List[JSONDict] = []

        # Round-1 DMA system blocks — ACCORD + per-language guidance +
        # prohibition context (#910) — via the shared helper (NOT ASPDMA).
        append_round1_accord_blocks(
            messages,
            language=self.prompt_loader.language,
            accord_mode=self.prompt_loader.get_accord_mode(self.prompt_template_data),
        )

        # Check for template override of system_prompt (e.g., HE-300 format instructions)
        template_system_override = None
        if isinstance(self.prompts, dict):
            template_system_override = self.prompts.get("system_prompt")

        # #996 — a `system_prompt` override replaces the `system_guidance_header`
        # FIELD, not the composed system message. It used to return the override
        # in place of get_system_message(), which composes six fields — so
        # replacing the header also disabled domain_principles, evaluation_steps,
        # evaluation_criteria, response_format and response_guidance. Replacing
        # one field must never disable another.
        template_data = self.prompt_template_data
        if template_system_override:
            template_data = template_data.model_copy(update={"system_guidance_header": template_system_override})
            logger.debug(
                "CSDMA template system_prompt override replaces system_guidance_header (%d chars); "
                "the other composed fields are unaffected",
                len(template_system_override),
            )
        system_message = self.prompt_loader.get_system_message(
            template_data, context_summary=context_summary, original_thought_content=thought_content
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

        # Check for template override of user_prompt_template
        template_user_override = None
        if isinstance(self.prompts, dict):
            template_user_override = self.prompts.get("user_prompt_template")

        user_message_text = self.prompt_loader.get_user_message(
            self.prompt_template_data, context_summary=context_summary, original_thought_content=thought_content
        )

        if not user_message_text or user_message_text == f"Thought to evaluate: {thought_content}":
            user_message_text = format_user_prompt_blocks(
                format_parent_task_chain([]),
                format_thoughts_chain([{"content": thought_content}]),
                None,
            )

        # #996 — ADDITIVE. `context_integration` carries live slots
        # (`context_summary`, `original_thought_content`), so it is not fit for
        # replacement: substituting a template's text for it dropped
        # `context_summary` outright. The authored framing leads, the
        # composition follows undiminished.
        if template_user_override:
            framing = template_user_override.format(
                thought_content=thought_content,
                context_summary=context_summary,
            )
            logger.debug(
                "CSDMA template user_prompt_template override: %d chars framing + %d chars composition",
                len(framing),
                len(user_message_text),
            )
            user_message_text = additive(framing, user_message_text)

        # Build multimodal content if images are present
        images_list = images or []
        if images_list:
            logger.info(f"[VISION] CSDMA building multimodal content with {len(images_list)} images")
        user_content = self.build_multimodal_content(user_message_text, images_list)
        messages.append({"role": "user", "content": user_content})

        return messages

    def compose_messages(
        self,
        thought_content: str,
        context_summary: str,
        task_context_str: str,
        system_snapshot_str: str,
        user_profiles_str: str,
        images: Optional[List[ImageContent]] = None,
    ) -> List[JSONDict]:
        """Compose the full CSDMA prompt message list from gathered inputs (#972).

        Pure prompt composition - no LLM call, no data fetching. All awaited
        data gathering (task fetch, context extraction) happens in
        ``evaluate_thought()`` before this is called.
        """
        # Prepend task context to system snapshot
        task_context_block = f"=== ORIGINAL TASK ===\n{task_context_str}\n\n"
        combined_snapshot_block = task_context_block + system_snapshot_str + user_profiles_str

        return self._create_csdma_messages_for_instructor(
            thought_content,
            context_summary,
            identity_context_block="",
            system_snapshot_block=combined_snapshot_block,
            user_profiles_block="",
            images=images,
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
            logger.debug(f"CSDMA: Synced prompt language to {new_language}")

    def _extract_context_data(self, context: Optional[Any]) -> tuple[str, str, str]:
        """Extract context strings from context object.

        Also syncs user's language preference to the DMA prompt loader.

        Args:
            context: Context object with system_snapshot and/or user_profiles

        Returns:
            Tuple of (system_snapshot_str, user_profiles_str, context_summary)
        """
        system_snapshot_str = ""
        user_profiles_str = ""
        context_summary = (
            "CIRIS AI Agent operating via Discord, API, or CLI - Digital/virtual interactions are normal and expected."
        )

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
                context_summary = self._build_context_summary(agent_identity)
        elif hasattr(context, "user_profiles") and context.user_profiles:
            user_profiles = context.user_profiles
            user_profiles_str = format_user_profiles(user_profiles)

        self._sync_language_from_context(context)
        return system_snapshot_str, user_profiles_str, context_summary

    def _build_context_summary(self, agent_identity: Any) -> str:
        """Build context summary from agent_identity data."""
        agent_id = getattr(agent_identity, "agent_id", "Unknown")
        description = getattr(agent_identity, "description", "")
        role = getattr(agent_identity, "role", "")

        return (
            f"{agent_id} ({role}) - {description}. "
            f"Operating via Discord, API, or CLI in digital/virtual environment."
        )

    async def evaluate_thought(self, thought_item: ProcessingQueueItem, context: Optional[Any] = None) -> CSDMAResult:
        thought_content_str = str(thought_item.content)

        # Fetch original task for context
        thought_depth = getattr(thought_item, "thought_depth", 0)
        agent_occurrence_id = getattr(thought_item, "agent_occurrence_id", "default")
        original_task = await self.fetch_original_task(thought_item.source_task_id, agent_occurrence_id)
        task_context_str = self.format_task_context(original_task, thought_depth)

        # Extract context data from context object
        system_snapshot_str, user_profiles_str, context_summary = self._extract_context_data(context)

        # Get images from thought item for multimodal
        thought_images = getattr(thought_item, "images", []) or []

        # Compose messages via the extracted seam (#972)
        messages = self.compose_messages(
            thought_content_str,
            context_summary,
            task_context_str,
            system_snapshot_str,
            user_profiles_str,
            images=thought_images,
        )

        # Store prompts for streaming/debugging
        system_messages = [m for m in messages if m.get("role") == "system"]
        self.last_system_prompt = "\n\n".join(str(m.get("content", "")) for m in system_messages)
        user_messages = [m for m in messages if m.get("role") == "user"]
        content = user_messages[-1]["content"] if user_messages else None
        self.last_user_prompt = str(content) if content is not None else None

        logger.debug(
            "CSDMA input to LLM for thought %s:\nContext Summary: %s",
            thought_item.thought_id,
            context_summary,
        )

        try:
            result_tuple = await self.call_llm_structured(
                messages=messages,
                response_model=CSDMAResult,
                max_tokens=8192,
                temperature=0.0,
                thought_id=thought_item.thought_id,
                task_id=thought_item.source_task_id,
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
