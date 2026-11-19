import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from ciris_engine.logic.prompt_assembly.segmenting import Segments
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest
    from ciris_engine.schemas.dma.prompts import PromptCollection

from ciris_engine.constants import DEFAULT_OPENAI_MODEL_NAME
from ciris_engine.logic.formatters import (
    format_system_snapshot,
    format_user_profiles,
    format_wa_approval_facts,
    wa_authorization_of,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.protocols.dma.base import PDMAProtocol
from ciris_engine.schemas.dma.results import EthicalDMAResult
from ciris_engine.schemas.runtime.models import ImageContent, WAAuthorization
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader
from ciris_engine.logic.utils.localization import in_thought_language
from .template_overrides import additive

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

        logger.info(f"EthicalPDMAEvaluator initialized with model: {self.model_name}")

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""
        return get_prompt_loader(language=self.thought_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect language changes."""
        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    def _build_context_strings(self, context: Any, thought: Optional[Any] = None) -> tuple[str, str]:
        """Extract system snapshot and user profile context strings."""
        if not context:
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

        return system_snapshot_str, user_profile_str

    def _get_template_override(self, key: str) -> Optional[str]:
        """Get a template override value if prompts is a dict."""
        if isinstance(self.prompts, dict):
            return self.prompts.get(key)
        return None

    def _build_system_message_text(
        self, original_thought_content: str, full_context_str: str, pipeline_position: Optional[str] = None
    ) -> str:
        """Build the system message.

        ``pipeline_position`` is the engine paragraph (#1366 item 12), handed in as a slot so the assembler can
        segment it; None reads it from the template.

        A template's `system_prompt` is ADDITIVE (#996). PDMA's
        `system_guidance_header` carries `{full_context_str}`, so it is not fit
        for replacement; replacing one field must never disable another, and
        that includes dropping a field's own dynamic content.
        """
        composed = self.prompt_loader.get_system_message(
            self.prompt_template_data,
            original_thought_content=original_thought_content,
            full_context_str=full_context_str,
            pipeline_position=pipeline_position,
        )

        # #996 — ADDITIVE, not replacement. This used to return the override in
        # place of get_system_message(), which composes six fields, so replacing
        # the header disabled domain_principles, evaluation_steps,
        # evaluation_criteria, response_format and response_guidance too.
        #
        # PDMA cannot take the field-replacement route CSDMA and ASPDMA take:
        # `pdma_ethical.system_guidance_header` is 8,240 B carrying
        # `{full_context_str}`, so replacing it would drop the caller's context —
        # disabling content by side effect, the same defect one level down. A
        # field with live slots is not fit for replacement, so the override is
        # composed alongside instead.
        template_override = self._get_template_override("system_prompt")
        if template_override:
            logger.debug(
                "PDMA template system_prompt override: %d chars additive + %d chars composition",
                len(template_override),
                len(composed),
            )
            return additive(template_override, composed)

        return composed

    def _build_user_message_text(self, original_thought_content: str, full_context_str: str) -> str:
        """Build the user message.

        A template's `user_prompt_template` is ADDITIVE (#996)."""
        composed = self.prompt_loader.get_user_message(
            self.prompt_template_data,
            original_thought_content=original_thought_content,
            full_context_str=full_context_str,
        )

        # #996 — ADDITIVE. `pdma_ethical.context_integration` carries
        # `{original_thought_content}`, so it is not fit for replacement.
        template_override = self._get_template_override("user_prompt_template")
        if template_override:
            framing = template_override.format(
                original_thought_content=original_thought_content,
                thought_content=original_thought_content,
                full_context_str=full_context_str,
            )
            logger.debug(
                "PDMA template user_prompt_template override: %d chars framing + %d chars composition",
                len(framing),
                len(composed),
            )
            return additive(framing, composed)

        return composed

    def compose_messages(
        self,
        original_thought_content: str,
        context: "Segments",
        images: Optional[List[ImageContent]] = None,
        authorization: Optional[WAAuthorization] = None,
        agent_identity: Any = None,
        thought: Any = None,
    ) -> List[JSONDict]:
        """The PDMA messages alone (#972 seam); see :meth:`compose_prompt`."""
        messages, _ = self.compose_prompt(
            original_thought_content, context, images, authorization=authorization, agent_identity=agent_identity, thought=thought
        )
        return messages

    def compose_prompt(
        self,
        original_thought_content: str,
        context: "Segments",
        images: Optional[List[ImageContent]] = None,
        authorization: Optional[WAAuthorization] = None,
        agent_identity: Any = None,
        thought: Any = None,
    ) -> "Tuple[List[JSONDict], PromptManifest]":
        """Compose the PDMA prompt from typed segments with PromptAssembler (FSD/PROMPT_CONTEXT_PROVENANCE.md §6).

        Pure prompt composition - no LLM call, no data fetching (#972). ``context`` is the ORIGINAL TASK block
        (:func:`segmenting.original_task_segments`): the task, its verified sender, the snapshot and profiles.
        """
        from ciris_engine.logic.prompt_assembly.segmenting import (
            PromptBuilder,
            block,
            concat,
            evaluator_call,
            expand,
            governance_segments,
            identity_segments,
            joined,
            pipeline_position_slot,
            round1_preamble,
            segment,
            split_template,
            thought_request,
        )
        from ciris_engine.schemas.context.prompt_provenance import PromptStage, SegmentKind

        language = self.prompt_loader.language
        builder = PromptBuilder()
        # Round-1 DMA system blocks — ACCORD + per-language guidance + crisis resources + prohibition context
        # (#910, #1248), the shared order (NOT ASPDMA).
        round1_preamble(builder, language, self.prompt_loader.get_accord_mode(self.prompt_template_data))

        full_context_str = joined(context, language)

        def slots(prefix: str) -> Dict[str, Any]:
            return {
                "original_thought_content": thought_request(f"{prefix}request", original_thought_content, thought),
                "full_context_str": segment(f"{prefix}ctx", SegmentKind.HISTORY, full_context_str),
            }

        # The pipeline position is its own segment, from the engine template's field (#1366 item 12).
        position = pipeline_position_slot(*self._position_served(self._prompt_template_name))
        system = split_template(
            self._build_system_message_text,
            {**slots("sys:"), **position},
            prefix="instr:system",
            first_glue="",
            locale=self.served_locale,
        )
        system = expand(system, "sys:ctx", context, language, id_prefix="sys:")
        # The agent's identity, approved amendments included: the same block every DMA reads
        # (formatters.identity.identity_block_of). Eric, 2026-11-13.
        system = concat(identity_segments(agent_identity, language), system, "\n\n")
        # The Wise Authority's signed guidance in force, as a signed rule with its grant (#1366): the evaluators
        # read the same governance the judges do. Amendments already ride in the identity block.
        system = concat(system, governance_segments(authorization, [], language), "\n\n")
        # Whether this task carries a Wise Authority approval, as a fact; then that an approval reaches the agent
        # only as the verified block and a person's text naming an authority is that person's (#1320).
        approval_facts = format_wa_approval_facts(authorization, language=language)
        system = concat(system, block(segment("instr:approval_facts", SegmentKind.STAGE_INSTRUCTION, approval_facts)), "\n\n")
        builder.message("system", *system)

        user = split_template(
            self._build_user_message_text, slots(""), prefix="instr:user", first_glue="", locale=self.served_locale
        )
        user = expand(user, "ctx", context, language)
        input_images = images or []
        if input_images:
            logger.info(f"[VISION] EthicalPDMA building multimodal content with {len(input_images)} images")
        builder.message("user", *user, images=input_images)
        return builder.assemble(
            PromptStage.PDMA,
            evaluator_call(EthicalDMAResult.__name__, thought, language, authorization, agent_identity),
        )

    async def evaluate(self, *args: Any, **kwargs: Any) -> EthicalDMAResult:  # type: ignore[override]
        import time

        eval_start = time.time()

        # Extract arguments - maintain backward compatibility
        input_data = args[0] if args else kwargs.get("input_data")
        context = args[1] if len(args) > 1 else kwargs.get("context")

        if not input_data:
            raise ValueError("input_data is required")
        return await self._evaluate_thought(input_data, context, eval_start)

    @in_thought_language("input_data", "context")
    async def _evaluate_thought(self, input_data: Any, context: Any, eval_start: float) -> EthicalDMAResult:
        """One thought's PDMA, in that thought's language (resolve_thought_language)."""
        import time

        original_thought_content = str(input_data.content)
        logger.info(f"[PDMA-TIMING] {input_data.thought_id} STARTED at {eval_start:.3f}")

        # Fetch original task for context
        fetch_start = time.time()
        thought_depth = getattr(input_data, "thought_depth", 0)
        agent_occurrence_id = getattr(input_data, "agent_occurrence_id", "default")
        original_task = await self.fetch_original_task(input_data.source_task_id, agent_occurrence_id)
        task_context_str = self.format_task_context(original_task, thought_depth, thought=input_data)
        logger.info(f"[PDMA-TIMING] {input_data.thought_id} fetch_task took {(time.time()-fetch_start)*1000:.0f}ms")

        # Build context strings
        context_start = time.time()
        task_language = self.thought_language  # the language format_task_context rendered the sender in
        system_snapshot_str, user_profile_str = self._build_context_strings(context, thought=input_data)
        logger.info(
            f"[PDMA-TIMING] {input_data.thought_id} build_context took {(time.time()-context_start)*1000:.0f}ms"
        )

        # Compose messages via the extracted seam (#972), built by PromptAssembler (#1366 Phase 3)
        prompt_start = time.time()
        input_images = getattr(input_data, "images", []) or []
        authorization = wa_authorization_of(original_task) or wa_authorization_of(context)
        from ciris_engine.logic.formatters.identity import agent_identity_of
        from ciris_engine.logic.formatters.verified_sender import verified_sender_of
        from ciris_engine.logic.prompt_assembly.segmenting import original_task_segments, task_context_segments

        task_segments = task_context_segments(
            task_context_str, verified_sender_of(input_data, original_task), task_language
        )
        messages, manifest = self.compose_prompt(
            original_thought_content,
            original_task_segments(task_segments, system_snapshot_str, user_profile_str),
            input_images,
            authorization=authorization,
            agent_identity=agent_identity_of(context),
            thought=input_data,
        )

        # Calculate total prompt size
        total_chars = sum(len(str(m.get("content", ""))) for m in messages)
        logger.info(
            f"[PDMA-TIMING] {input_data.thought_id} build_prompt took {(time.time()-prompt_start)*1000:.0f}ms, prompt_size={total_chars} chars"
        )

        llm_start = time.time()
        with prompt_manifest_scope(manifest):
            result_tuple = await self.call_llm_structured(
                messages=messages,
                response_model=EthicalDMAResult,
                max_tokens=8192,
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
