import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ciris_engine.schemas.dma.prompts import PromptCollection

from ciris_engine.constants import DEFAULT_OPENAI_MODEL_NAME
from ciris_engine.logic.formatters import format_system_snapshot, format_user_profiles
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import get_accord_text
from ciris_engine.protocols.dma.base import PDMAProtocol
from ciris_engine.schemas.dma.results import EthicalDMAResult
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader

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

        # Do NOT cache template - language may change at runtime
        self._prompt_template_name = "pdma_ethical"

        # Store last prompts for debugging/streaming
        self.last_user_prompt: Optional[str] = None
        self.last_system_prompt: Optional[str] = None

        # Per-thought language override; populated from user_profiles in
        # _build_context_strings. None means fall back to env var. Never use
        # the legacy global set_prompt_language() — that mutated shared
        # state and bled across concurrent thoughts.
        self._explicit_language: Optional[str] = None

        logger.info(f"EthicalPDMAEvaluator initialized with model: {self.model_name}")

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""
        return get_prompt_loader(language=self._explicit_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect language changes."""
        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    def _sync_language_from_context(self, context: Optional[Any], thought: Optional[Any] = None) -> None:
        """Sync prompt language using the full localization priority chain.

        Walks thought.preferred_language → context.thought/task.preferred_language →
        user_profile.preferred_language → CIRIS_PREFERRED_LANGUAGE env → "en" via
        :func:`get_user_language_from_context`. The ``thought`` argument is the
        ProcessingQueueItem being evaluated; its preferred_language is the
        authoritative per-thought signal and beats the (often default-"en")
        user_profile entry. Without consulting the thought directly, the
        UserProfile.preferred_language="en" default would silently override
        legitimate channel/thought signals.
        """
        from ciris_engine.logic.utils.localization import (
            _str_lang,
            get_preferred_language,
            get_user_language_from_context,
        )

        # Thought's own preferred_language is the highest-priority signal.
        thought_lang = _str_lang(thought, "preferred_language") if thought is not None else None
        if thought_lang:
            new_language = thought_lang
        elif context is not None:
            new_language = get_user_language_from_context(context)
        else:
            new_language = get_preferred_language()
        if new_language != self._explicit_language:
            self._explicit_language = new_language
            logger.debug(f"PDMA: Synced prompt language to {new_language}")

    def _build_context_strings(self, context: Any, thought: Optional[Any] = None) -> tuple[str, str]:
        """Extract system snapshot and user profile context strings.

        Also syncs user's language preference to the DMA prompt loader.
        """
        if not context:
            # No context = no profile = no language. Reset so a previous
            # thought's language doesn't bleed into this one.
            self._sync_language_from_context(None)
            return "", ""

        system_snapshot_str = ""
        user_profile_str = ""
        user_profiles = None

        if hasattr(context, "system_snapshot") and context.system_snapshot:
            system_snapshot_str = format_system_snapshot(context.system_snapshot)
            if hasattr(context.system_snapshot, "user_profiles") and context.system_snapshot.user_profiles:
                user_profiles = context.system_snapshot.user_profiles
                user_profile_str = format_user_profiles(user_profiles)
        elif hasattr(context, "user_profiles") and context.user_profiles:
            user_profiles = context.user_profiles
            user_profile_str = format_user_profiles(user_profiles)

        self._sync_language_from_context(context, thought=thought)
        return system_snapshot_str, user_profile_str

    def _get_template_override(self, key: str) -> Optional[str]:
        """Get a template override value if prompts is a dict."""
        if isinstance(self.prompts, dict):
            return self.prompts.get(key)
        return None

    def _build_system_message_text(self, original_thought_content: str, full_context_str: str) -> str:
        """Build system message, using template override if available."""
        template_override = self._get_template_override("system_prompt")
        if template_override:
            logger.debug(f"PDMA using template system_prompt override ({len(template_override)} chars)")
            return template_override

        return self.prompt_loader.get_system_message(
            self.prompt_template_data,
            original_thought_content=original_thought_content,
            full_context_str=full_context_str,
        )

    def _build_user_message_text(self, original_thought_content: str, full_context_str: str) -> str:
        """Build user message, using template override if available."""
        template_override = self._get_template_override("user_prompt_template")
        if template_override:
            text = template_override.format(
                original_thought_content=original_thought_content,
                thought_content=original_thought_content,
                full_context_str=full_context_str,
            )
            logger.debug(f"PDMA using template user_prompt_template override ({len(text)} chars)")
            return text

        return self.prompt_loader.get_user_message(
            self.prompt_template_data,
            original_thought_content=original_thought_content,
            full_context_str=full_context_str,
        )

    async def evaluate(self, *args: Any, **kwargs: Any) -> EthicalDMAResult:  # type: ignore[override]
        import time

        eval_start = time.time()

        # Extract arguments - maintain backward compatibility
        input_data = args[0] if args else kwargs.get("input_data")
        context = args[1] if len(args) > 1 else kwargs.get("context")

        if not input_data:
            raise ValueError("input_data is required")

        original_thought_content = str(input_data.content)
        logger.info(f"[PDMA-TIMING] {input_data.thought_id} STARTED at {eval_start:.3f}")

        # Fetch original task for context
        fetch_start = time.time()
        thought_depth = getattr(input_data, "thought_depth", 0)
        agent_occurrence_id = getattr(input_data, "agent_occurrence_id", "default")
        original_task = await self.fetch_original_task(input_data.source_task_id, agent_occurrence_id)
        task_context_str = self.format_task_context(original_task, thought_depth)
        logger.info(f"[PDMA-TIMING] {input_data.thought_id} fetch_task took {(time.time()-fetch_start)*1000:.0f}ms")

        # Build context strings
        context_start = time.time()
        system_snapshot_str, user_profile_str = self._build_context_strings(context, thought=input_data)
        full_context_str = f"=== ORIGINAL TASK ===\n{task_context_str}\n\n{system_snapshot_str}{user_profile_str}"
        logger.info(
            f"[PDMA-TIMING] {input_data.thought_id} build_context took {(time.time()-context_start)*1000:.0f}ms"
        )

        # Build messages
        prompt_start = time.time()
        messages: List[JSONDict] = []

        # Add accord based on mode (centralized in get_accord_text)
        accord_mode = self.prompt_loader.get_accord_mode(self.prompt_template_data)
        accord_text = get_accord_text(accord_mode)
        if accord_text:
            messages.append({"role": "system", "content": accord_text})

        system_message = self._build_system_message_text(original_thought_content, full_context_str)
        messages.append({"role": "system", "content": system_message})

        user_message_text = self._build_user_message_text(original_thought_content, full_context_str)
        # Build multimodal content if images are present
        input_images = getattr(input_data, "images", []) or []
        if input_images:
            logger.info(f"[VISION] EthicalPDMA building multimodal content with {len(input_images)} images")
        user_content = self.build_multimodal_content(user_message_text, input_images)
        messages.append({"role": "user", "content": user_content})

        # Store prompts for streaming/debugging
        system_messages = [m for m in messages if m.get("role") == "system"]
        self.last_system_prompt = "\n\n".join(str(m.get("content", "")) for m in system_messages)
        self.last_user_prompt = user_message_text

        # Calculate total prompt size
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        logger.info(
            f"[PDMA-TIMING] {input_data.thought_id} build_prompt took {(time.time()-prompt_start)*1000:.0f}ms, prompt_size={total_chars} chars"
        )

        llm_start = time.time()
        result_tuple = await self.call_llm_structured(
            messages=messages,
            response_model=EthicalDMAResult,
            max_tokens=4096,
            temperature=0.0,
            thought_id=input_data.thought_id,
            task_id=input_data.source_task_id,
        )
        llm_time = time.time() - llm_start
        response_obj: EthicalDMAResult = result_tuple[0]

        total_time = time.time() - eval_start
        logger.info(
            f"[PDMA-TIMING] {input_data.thought_id} COMPLETED: llm={llm_time*1000:.0f}ms, total={total_time*1000:.0f}ms"
        )
        return response_obj

    def __repr__(self) -> str:
        return f"<EthicalPDMAEvaluator model='{self.model_name}'>"
