import logging
from typing import TYPE_CHECKING, Any, Dict, List, Mapping, Optional, Tuple, Union, cast

if TYPE_CHECKING:
    from ciris_engine.logic.prompt_assembly.segmenting import Segments
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest, PromptSegment

from pydantic import BaseModel, Field

from ciris_engine.schemas.dma.sent_prompts import attach_sent_prompts, carry_sent_prompts, sent_prompts_from_messages
from ciris_engine.logic.conscience.transport import surfaces_as_transport_failure
from ciris_engine.logic.formatters import (
    amendment_texts,
    format_core_identity_block,
    format_system_prompt_blocks,
    format_system_snapshot,
    format_user_profiles,
    get_escalation_guidance,
    wa_authorization_of,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.protocols.dma.base import DSDMAProtocol
from ciris_engine.schemas.dma.core import DMAInputData
from ciris_engine.schemas.dma.prompts import PromptCollection
from ciris_engine.schemas.dma.results import DSDMAResult
from ciris_engine.schemas.runtime.models import ImageContent, WAAuthorization
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader, safe_format
from ciris_engine.logic.utils.localization import in_thought_language

logger = logging.getLogger(__name__)

#: What a template's legacy ``{crisis_resources_block}`` slot renders to since
#: #1248. The block itself is a separate system message (see
#: ``append_round1_accord_blocks``); this pointer carries no number, so a
#: template can never re-introduce one out of the gated corpus path.
DSDMA_CRISIS_BLOCK_POINTER = (
    "(See the \"=== Crisis Resources ===\" system message: verified resources for this locale. "
    "Emergency numbers there are general emergency services, not mental-health helplines.)"
)


def _format_domain_specific_knowledge(dsk: Optional[Mapping[str, Any]]) -> str:
    """Render the agent's full ``domain_specific_knowledge`` dict into the
    DSDMA prompt. Every top-level key flows through, not just ``rules_summary``.

    ``rules_summary`` (if present and a string) is emitted first as plain prose
    so simple templates render cleanly. Everything else becomes labeled
    sections — strings inline, lists bulleted, nested dicts indented.
    """
    if not isinstance(dsk, Mapping) or not dsk:
        return "General domain guidance"

    parts: List[str] = []

    rules_summary = dsk.get("rules_summary")
    if isinstance(rules_summary, str) and rules_summary.strip():
        parts.append(rules_summary.strip())

    for key, value in dsk.items():
        if key == "rules_summary" or value is None:
            continue
        label = key.replace("_", " ").strip().title()
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(f"- {label}: {text}")
        elif isinstance(value, list):
            items = [str(x).strip() for x in value if str(x).strip()]
            if items:
                bullets = "\n  • " + "\n  • ".join(items)
                parts.append(f"- {label}:{bullets}")
        elif isinstance(value, Mapping):
            sub_items = [f"{k}: {v}" for k, v in value.items() if v is not None]
            if sub_items:
                bullets = "\n  • " + "\n  • ".join(sub_items)
                parts.append(f"- {label}:{bullets}")
        else:
            parts.append(f"- {label}: {value}")

    return "\n".join(parts) if parts else "General domain guidance"


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

        # Do NOT cache template - language may change at runtime
        self._prompt_template_name = "dsdma_base"
        self._custom_prompt_template = prompt_template  # User-provided override

        # Store last prompts for debugging/streaming

        logger.info(f"BaseDSDMA '{self.domain_name}' initialized with model: {self.model_name}")

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""
        return get_prompt_loader(language=self.thought_language)

    @property
    def prompt_template_data(self) -> PromptCollection:
        """Load prompt template fresh each time to respect language changes."""
        try:
            return self.prompt_loader.load_prompt_template(self._prompt_template_name)
        except FileNotFoundError:
            logger.warning(f"DSDMA base prompt template not found for domain '{self.domain_name}', using fallback")
            return PromptCollection(
                component_name="dsdma_base_fallback",
                description="Fallback DSDMA prompt collection",
                system_guidance_header=self.DEFAULT_TEMPLATE if self.DEFAULT_TEMPLATE else "",
            )

    @property
    def prompt_template(self) -> str:
        """The engine's system guidance header in the thought's language.

        Engine-owned (#1366): an agent's custom DSDMA template (``core_profile.dsdma_prompt_template``) is added
        after the engine header as agent-profile text (:meth:`_custom_body`), never in its place, so the role and
        instructions render in the thought's language whatever the agent supplies.
        """
        system_guidance = self.prompt_template_data.get_prompt("system_guidance_header")
        if system_guidance:
            return system_guidance
        return self.DEFAULT_TEMPLATE if self.DEFAULT_TEMPLATE else ""

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

    # The orchestrator hands DSDMA DMAMetadata, never the processing context PDMA and CSDMA resolve against, so
    # the context is the one the queue item carries (gather_context stores the ProcessingThoughtContext there):
    # its initial_task_context holds the message's language. Reading only the item fell to the deployment
    # default -- the English primer and template in an `am` thought (#1366, RATCHET am context map).
    @in_thought_language("thought_item", "thought_item.initial_context", "current_context")
    async def evaluate_thought(
        self, thought_item: ProcessingQueueItem, current_context: Optional[DMAInputData]
    ) -> DSDMAResult:

        thought_content_str = str(thought_item.content)

        # Fetch original task for context
        thought_depth = getattr(thought_item, "thought_depth", 0)
        agent_occurrence_id = getattr(thought_item, "agent_occurrence_id", "default")
        original_task = await self.fetch_original_task(thought_item.source_task_id, agent_occurrence_id)
        task_context_str = self.format_task_context(original_task, thought_depth, thought=thought_item)
        task_language = self.thought_language  # the language format_task_context rendered the sender in

        # Use DMAInputData if provided, otherwise fall back to ProcessingQueueItem context
        if current_context:
            # Use typed DMAInputData fields
            context_str = f"Round {current_context.round_number}, Ponder count: {current_context.current_thought_depth}"
            rules_summary_str = _format_domain_specific_knowledge(self.domain_specific_knowledge)

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

            # Routed (#974 step 3): one keyed source (prompts.identity_block)
            # for the CORE IDENTITY doctrine, replaceable via the research
            # `string` namespace and translatable per bundle.
            identity_block = format_core_identity_block(
                str(agent_id),
                str(description),
                str(role),
                language=self.thought_language,
                amendments=amendment_texts(agent_identity),
            )
            agent_identity_for_prompt: Any = agent_identity
        else:
            # NO FALLBACK - STRICT TYPE CHECKING ONLY
            # When no DMAInputData, we still need to get identity from ProcessingQueueItem
            context_str = "No specific platform context provided."
            rules_summary_str = _format_domain_specific_knowledge(self.domain_specific_knowledge)

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

            # Build identity block — routed (#974 step 3), see branch above.
            identity_block = format_core_identity_block(
                str(agent_id),
                str(description),
                str(role),
                language=self.thought_language,
                amendments=amendment_texts(agent_identity_raw),
            )
            agent_identity_for_prompt = agent_identity_raw

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

        # Get images from thought item for multimodal
        thought_images = getattr(thought_item, "images", []) or []

        # Compose messages via the extracted seam (#972), built by PromptAssembler (#1366 Phase 3)
        from ciris_engine.logic.formatters.verified_sender import verified_sender_of
        from ciris_engine.logic.prompt_assembly.segmenting import task_context_segments

        messages, manifest = self.compose_prompt(
            thought_content_str,
            thought_item.thought_id,
            task_context_segments(task_context_str, verified_sender_of(thought_item, original_task), task_language),
            agent_identity_for_prompt,
            identity_block,
            system_snapshot_block,
            user_profiles_block,
            context_str,
            rules_summary_str,
            images=thought_images,
            thought=thought_item,
            authorization=wa_authorization_of(original_task) or wa_authorization_of(thought_item),
        )

        try:
            # The dsdma_base.yml output contract asks the LLM for the 4
            # DSDMAResult fields directly (domain, domain_alignment, flags,
            # reasoning) — no intermediate shim. Using DSDMAResult as the
            # instructor response_model means Pydantic validates against the
            # exact shape we asked the LLM to produce; the legacy
            # `score`-based LLMOutputForDSDMA shim was a 2.7.4 regression
            # source (the prompt asked for domain_alignment, the response
            # model demanded score → InstructorRetryException → circuit
            # breaker → "All LLM services failed").
            with prompt_manifest_scope(manifest):
                llm_eval_data, _ = await self.call_llm_structured(
                    messages=messages,
                    response_model=DSDMAResult,
                    max_tokens=8192,
                    temperature=0.0,
                    thought_id=thought_item.thought_id,
                    task_id=thought_item.source_task_id,
                )

            # The LLM picks its own domain string — use that. Clamp the
            # alignment to [0, 1] defensively in case the model exceeded
            # the schema's bounds (instructor usually catches this, but
            # paranoia is cheap).
            result = carry_sent_prompts(llm_eval_data, DSDMAResult(
                domain=llm_eval_data.domain or self.domain_name,
                domain_alignment=min(max(llm_eval_data.domain_alignment, 0.0), 1.0),
                flags=llm_eval_data.flags,
                reasoning=llm_eval_data.reasoning,
            ))
            logger.info(
                f"DSDMA '{self.domain_name}' (instructor) evaluation successful for thought ID {thought_item.thought_id}: "
                f"Domain Alignment: {result.domain_alignment}"
            )
            return result
        except Exception as e:
            if surfaces_as_transport_failure(e):
                # Never reached the model: re-raise for run_dma_with_retries
                # (same policy as PDMA) rather than invent a 0.0 alignment.
                logger.warning(
                    f"DSDMA {self.domain_name} transport failure for thought ID {thought_item.thought_id}: {e}"
                )
                raise
            logger.error(f"DSDMA {self.domain_name} evaluation failed for thought ID {thought_item.thought_id}: {e}")
            # The call failed after these messages were built: record them, so
            # the failure is auditable (local to this call, never shared).
            return attach_sent_prompts(
                DSDMAResult(
                    domain=self.domain_name,
                    domain_alignment=0.0,
                    flags=["LLM_Error_Instructor"],
                    reasoning=f"Failed DSDMA evaluation via instructor: {str(e)}",
                ),
                sent_prompts_from_messages(messages),
            )

    def _resolve_user_template(self) -> "tuple[DMAPromptLoader, PromptCollection]":
        """Resolve the DSDMA user-message template (#974 step 2).

        ``context_integration`` existed in dsdma_base.yml before #974 but was
        never rendered, and all 28 localized files carry translations of that
        DEAD template. Routing must not silently activate them (that would be
        a material non-base-locale prompt change, not a routing), so a
        template renders only when it is one of:

        - an explicit research override for ``dsdma_base.context_integration``
          (honored verbatim — fail-loud if it names unknown slots), or
        - a post-#974 template carrying the live structural slot
          ``{full_snapshot_and_profile_context_str}``.

        Anything else — stale localized translation, missing field — serves
        the base-locale doctrine, exactly what the inline f-string always did.
        """
        from ciris_engine.logic.dma.prompt_loader import DEFAULT_LANGUAGE
        from ciris_engine.logic.utils.research_overrides import override_dma_prompt

        loader = self.prompt_loader
        template_data = self.prompt_template_data
        text = template_data.context_integration
        if text:
            if override_dma_prompt(self._prompt_template_name, "context_integration") == text:
                return loader, template_data
            if "{full_snapshot_and_profile_context_str}" in text:
                return loader, template_data
        if loader.language != DEFAULT_LANGUAGE:
            loader = get_prompt_loader(DEFAULT_LANGUAGE)
            template_data = loader.load_prompt_template(self._prompt_template_name)
            if template_data.context_integration:
                return loader, template_data
        raise ValueError(
            "dsdma_base.yml no longer defines a live context_integration — the DSDMA "
            "user message has no source. #974 routed it out of Python; it must live "
            "in the YAML with the {full_snapshot_and_profile_context_str} slot."
        )

    def _header_tail(self) -> str:
        """``system_guidance_header_tail``: the rest of the engine header after its pipeline-position paragraph."""
        tail = getattr(self.prompt_template_data, "system_guidance_header_tail", None)
        # isinstance, not truthiness: tests substitute a Mock for `prompt_template_data`.
        return tail if isinstance(tail, str) else ""

    def _pipeline_position(self) -> str:
        """The engine template's pipeline-position paragraph (#1366 item 12); a custom template cannot replace it."""
        try:
            text = self.prompt_loader.pipeline_position(self._prompt_template_name)
        except FileNotFoundError:
            return ""
        return text if isinstance(text, str) else ""

    def _render_template(
        self,
        template: str,
        identity_block: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        context_str: str,
        rules_summary_str: str,
        escalation_guidance_block: Optional[str] = None,
        crisis_resources_block: str = DSDMA_CRISIS_BLOCK_POINTER,
    ) -> str:
        """One DSDMA template with its slots filled (the legacy block placeholders included)."""
        # The crisis block is NOT rendered into the template any more (#1248):
        # it arrives as its own system message right after language guidance,
        # the same block every DMA sees. A template that still carries a
        # `{crisis_resources_block}` slot (the echo-speculative identity, under
        # "For Mental Health Concerns:") gets a number-free pointer to it, so
        # DSDMA never carries the block twice.
        return template.format(
            identity_block=identity_block,
            task_history_block="",
            escalation_guidance_block=(
                get_escalation_guidance(0) if escalation_guidance_block is None else escalation_guidance_block
            ),
            system_snapshot_block=system_snapshot_block,
            user_profiles_block=user_profiles_block,
            crisis_resources_block=crisis_resources_block,
            domain_name=self.domain_name,
            rules_summary_str=rules_summary_str,
            context_str=context_str,
        )

    def _engine_body(
        self,
        identity_block: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        context_str: str,
        rules_summary_str: str,
        pipeline_position: Optional[str] = None,
    ) -> str:
        """The engine header: ``system_guidance_header``, the pipeline position (#1366 item 12), then
        ``system_guidance_header_tail``, joined by blank lines, in the thought's language. Engine-owned: no agent
        template replaces it. ``pipeline_position`` None reads it from the engine template (the assembler passes
        a slot value)."""
        position = self._pipeline_position() if pipeline_position is None else pipeline_position
        head = self.prompt_template or (
            "You are a domain-specific evaluator for the '{domain_name}' domain. "
            "Your primary goal is to assess how well a given 'thought' aligns with the specific rules, "
            "objectives, and knowledge pertinent to this domain. "
            "Consider the provided domain rules: '{rules_summary_str}' and the general platform context: '{context_str}'. "
            "Additionally, user profile information and system snapshot details will be provided with the thought for background awareness. "
            "Focus your evaluation on domain alignment."
        )
        args = (identity_block, system_snapshot_block, user_profiles_block, context_str, rules_summary_str)
        try:
            rendered = [self._render_template(template, *args) for template in (head, self._header_tail())]
        except KeyError as e:
            logger.error(f"Missing template variable in DSDMA template: {e}")
            rendered = [
                format_system_prompt_blocks(
                    identity_block,
                    "",
                    system_snapshot_block,
                    user_profiles_block,
                    get_escalation_guidance(0),
                    f"You are a domain-specific evaluator for the '{self.domain_name}' domain. "
                    f"Consider the domain rules: '{rules_summary_str}' and context: '{context_str}'.",
                ),
                "",
            ]
        return "\n\n".join(part for part in (rendered[0], position, rendered[1]) if part)

    def _custom_body(
        self,
        system_snapshot_block: str,
        user_profiles_block: str,
        context_str: str,
        rules_summary_str: str,
        escalation_guidance_block: Optional[str] = None,
        crisis_resources_block: str = DSDMA_CRISIS_BLOCK_POINTER,
    ) -> str:
        """The agent's own DSDMA template (``core_profile.dsdma_prompt_template``), ADDED after the engine header.

        It used to replace the engine header, so a custom template sent its own (English) role framing in place
        of the localized one. Its ``{identity_block}`` renders empty: the identity always leads the system
        message (:meth:`compose_prompt` prepends it), so it is never carried twice.
        """
        if not self._custom_prompt_template:
            return ""
        try:
            return self._render_template(
                self._custom_prompt_template,
                "",
                system_snapshot_block,
                user_profiles_block,
                context_str,
                rules_summary_str,
                escalation_guidance_block,
                crisis_resources_block,
            ).strip()
        except KeyError as e:
            logger.error(f"Missing template variable in the agent's DSDMA template, not sent: {e}")
            return ""

    def _response_body(self, context_str: str, rules_summary_str: str) -> str:
        """``response_format`` / ``closing_reminder`` (#990), engine-owned, in the thought's language."""
        # BaseDSDMA has never used `DMAPromptLoader.get_system_message()`: it
        # renders `system_guidance_header` alone, via the `prompt_template`
        # property, so every OTHER populated field in dsdma_base.yml was inert —
        # including `response_format`, the LANGUAGE RULES block. Appended here
        # rather than by switching to get_system_message(): that method renders
        # six fields in a fixed order and DSDMA's own header is already rendered
        # above with block substitution the shared path does not do. Going
        # through the loader-owned collection keeps the research dma_prompt
        # namespace intercepting these keys.
        _template_data = self.prompt_template_data
        _lang = self.prompt_loader.language
        parts: List[str] = []
        for _field in ("response_format", "closing_reminder"):
            _value = getattr(_template_data, _field, None)
            # isinstance, not truthiness: `prompt_template_data` is a property
            # and tests substitute a Mock for it, where every attribute is a
            # truthy Mock.
            if isinstance(_value, str) and _value:
                parts.append(
                    safe_format(
                        _value,
                        source=f"{self._prompt_template_name}.{_field}[{_lang}]",
                        domain_name=self.domain_name,
                        rules_summary_str=rules_summary_str,
                        context_str=context_str,
                    )
                )
        return "\n\n".join(parts)

    def _system_body(
        self,
        identity_block: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        context_str: str,
        rules_summary_str: str,
        pipeline_position: Optional[str] = None,
        custom_body: Optional[str] = None,
    ) -> str:
        """The system message before the identity prepend: the engine header, the agent's custom template when it
        has one, then response_format / closing_reminder (#990), joined by blank lines. ``custom_body`` None
        renders the custom template (the assembler passes a slot value)."""
        if custom_body is None:
            custom_body = self._custom_body(system_snapshot_block, user_profiles_block, context_str, rules_summary_str)
        return "\n\n".join(
            part
            for part in (
                self._engine_body(
                    identity_block,
                    system_snapshot_block,
                    user_profiles_block,
                    context_str,
                    rules_summary_str,
                    pipeline_position,
                ),
                custom_body,
                self._response_body(context_str, rules_summary_str),
            )
            if part
        )

    def _domain_knowledge_slot(self, segment_id: str, rules_summary_str: str) -> "Dict[str, PromptSegment]":
        """``{"rules_summary_str": segment}`` when the text is the agent template's domain knowledge, else ``{}``
        (the engine's own "General domain guidance" placeholder stays engine text)."""
        from ciris_engine.logic.prompt_assembly.segmenting import segment
        from ciris_engine.schemas.context.prompt_provenance import SegmentKind, SegmentSource

        if not self.domain_specific_knowledge or not rules_summary_str:
            return {}
        return {
            "rules_summary_str": segment(
                segment_id, SegmentKind.STAGE_INSTRUCTION, rules_summary_str, SegmentSource.AGENT_PROFILE
            )
        }

    def _expand_custom_body(
        self,
        system: "Segments",
        custom_text: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        context_str: str,
        rules_summary_str: str,
        language: str,
    ) -> "Segments":
        """The custom-template segment cut into its agent-profile pieces and the engine values it renders."""
        from ciris_engine.logic.prompt_assembly.segmenting import (
            SegmentationError,
            expand,
            history,
            segment,
            split_template,
        )
        from ciris_engine.schemas.context.prompt_provenance import SegmentKind, SegmentSource

        def render(
            system_snapshot_block: str,
            user_profiles_block: str,
            escalation_guidance_block: str,
            crisis_resources_block: str,
            rules_summary_str: str = rules_summary_str,
        ) -> str:
            return self._custom_body(
                system_snapshot_block,
                user_profiles_block,
                context_str,
                rules_summary_str,
                escalation_guidance_block,
                crisis_resources_block,
            )

        # The engine's own blocks the template places stay engine text; the template's words are the agent's.
        engine_blocks = {
            name: segment(f"sys:agent_template:{name}", SegmentKind.STAGE_INSTRUCTION, text)
            for name, text in (
                ("escalation_guidance_block", get_escalation_guidance(0)),
                ("crisis_resources_block", DSDMA_CRISIS_BLOCK_POINTER),
            )
        }
        try:
            parts = split_template(
                render,
                {
                    **engine_blocks,
                    "system_snapshot_block": history("sys:agent_template:system_snapshot", system_snapshot_block),
                    "user_profiles_block": history("sys:agent_template:user_profiles", user_profiles_block),
                    **self._domain_knowledge_slot("sys:agent_template:domain_knowledge", rules_summary_str),
                },
                prefix="instr:agent_template",
                first_glue="",
                instruction_source=SegmentSource.AGENT_PROFILE,
            )
            return expand(system, "sys:agent_template", parts, language)
        except SegmentationError as e:
            logger.warning(f"[DSDMA] agent template not segmentable ({e}); sent as one agent_profile segment")
            return system

    def compose_messages(
        self,
        thought_content_str: str,
        thought_id: str,
        task_context: "Segments",
        agent_identity: Any,
        identity_block: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        context_str: str,
        rules_summary_str: str,
        images: Optional[List[ImageContent]] = None,
        thought: Any = None,
    ) -> List[JSONDict]:
        """The DSDMA messages alone (#972 seam); see :meth:`compose_prompt`."""
        messages, _ = self.compose_prompt(
            thought_content_str,
            thought_id,
            task_context,
            agent_identity,
            identity_block,
            system_snapshot_block,
            user_profiles_block,
            context_str,
            rules_summary_str,
            images=images,
            thought=thought,
        )
        return messages

    def _identity_segments(self, agent_identity: Any, identity_block: str) -> "Segments":
        """The validated identity block as segments: identity_base pieces and one amendment segment per grant."""
        from ciris_engine.logic.prompt_assembly.segmenting import block, identity_segments, joined
        from ciris_engine.schemas.context.prompt_provenance import PromptSegment, SegmentKind, SegmentSource

        segments = identity_segments(agent_identity, self.thought_language)
        if joined(segments) == identity_block:
            return segments
        # An identity the shared renderer reads differently: keep its bytes.
        logger.warning("[DSDMA] identity block not segmentable; sent as one identity_base segment")
        return block(
            PromptSegment(
                segment_id="identity:base:0",
                kind=SegmentKind.IDENTITY_BASE,
                source=SegmentSource.AGENT_PROFILE,
                text=identity_block,
            )
        )

    def compose_prompt(
        self,
        thought_content_str: str,
        thought_id: str,
        task_context: "Segments",
        agent_identity: Any,
        identity_block: str,
        system_snapshot_block: str,
        user_profiles_block: str,
        context_str: str,
        rules_summary_str: str,
        images: Optional[List[ImageContent]] = None,
        thought: Any = None,
        authorization: Optional[WAAuthorization] = None,
    ) -> "Tuple[List[JSONDict], PromptManifest]":
        """Compose the DSDMA prompt from typed segments with PromptAssembler (FSD/PROMPT_CONTEXT_PROVENANCE.md §6).

        Pure prompt composition - no LLM call, no data fetching (#972). All awaited data gathering (task fetch,
        snapshot/identity extraction, language sync) happens in ``evaluate_thought()`` before this is called.
        ``task_context`` is the task's text and verified sender (:func:`segmenting.task_context_segments`);
        ``identity_block`` is the validated CORE IDENTITY block the segments must reproduce.
        """
        from ciris_engine.logic.prompt_assembly.segmenting import (
            PromptBuilder,
            concat,
            evaluator_call,
            expand,
            governance_segments,
            history,
            original_task_segments,
            pipeline_position_slot,
            round1_preamble,
            segment,
            split_template,
            thought_request,
        )
        from ciris_engine.schemas.context.prompt_provenance import PromptStage, SegmentKind, SegmentSource

        language = self.prompt_loader.language
        builder = PromptBuilder()
        # Round-1 DMA system blocks — ACCORD + per-language guidance + crisis resources + prohibition context
        # (#910, #1248), the shared order (NOT ASPDMA).
        round1_preamble(builder, language, self.prompt_loader.get_accord_mode(self.prompt_template_data))

        identity = self._identity_segments(agent_identity, identity_block) if identity_block else ([], [])

        def system_render(
            identity_block: str,
            system_snapshot_block: str,
            user_profiles_block: str,
            rules_summary_str: str = rules_summary_str,
            pipeline_position: Optional[str] = None,
            custom_body: Optional[str] = None,
        ) -> str:
            return self._system_body(
                identity_block,
                system_snapshot_block,
                user_profiles_block,
                context_str,
                rules_summary_str,
                pipeline_position,
                custom_body,
            )

        # The agent template's pieces carry its source (FSD §4.3): its domain knowledge (the template's
        # dsdma_kwargs.domain_specific_knowledge, rendered verbatim into the engine's AGENT'S DOMAIN KNOWLEDGE
        # section) and, when the agent has one, its custom DSDMA template, added after the engine header.
        knowledge = self._domain_knowledge_slot("sys:domain_knowledge", rules_summary_str)
        custom_text = self._custom_body(system_snapshot_block, user_profiles_block, context_str, rules_summary_str)
        custom = (
            {
                "custom_body": segment(
                    "sys:agent_template", SegmentKind.STAGE_INSTRUCTION, custom_text, SegmentSource.AGENT_PROFILE
                )
            }
            if custom_text
            else {}
        )
        system = split_template(
            system_render,
            {
                "identity_block": segment("sys:identity", SegmentKind.IDENTITY_BASE, identity_block),
                "system_snapshot_block": history("sys:system_snapshot", system_snapshot_block),
                "user_profiles_block": history("sys:user_profiles", user_profiles_block),
                **knowledge,
                # The pipeline position is its own segment, from the engine template's field (#1366 item 12).
                **pipeline_position_slot(self._pipeline_position()),
                **custom,
            },
            prefix="instr:system",
            first_glue="",
        )
        # The render split_template just proved its pieces rejoin to: read back, not rendered a third time.
        real = "".join(seg.text for seg in system[0])
        if custom_text:
            system = self._expand_custom_body(
                system, custom_text, system_snapshot_block, user_profiles_block, context_str, rules_summary_str, language
            )
        if identity_block:
            system = expand(system, "sys:identity", identity, language)
        # CRITICAL: Identity block must ALWAYS be first in system message after accord. Prepend identity to the
        # system message if the template did not already include it. (Stored prompts are the bytes sent, identity
        # included: RATCHET runs 39844408349, 39845804302.)
        if identity_block and "CORE IDENTITY" not in real:
            system = concat(identity, system, "\n\n")
        # The Wise Authority's signed guidance in force, as a signed rule with its grant (#1366).
        system = concat(system, governance_segments(authorization, [], language), "\n\n")
        builder.message("system", *system)

        # Routed (#974 step 2, FSD RESEARCH_PROMPT_OVERRIDES §11.2): the DSDMA user message lives in dsdma_base.yml
        # `context_integration`, rendered through the loader so the research-override dma_prompt namespace
        # intercepts it (key: dsdma_base.context_integration).
        user_loader, user_template_data = self._resolve_user_template()

        def user_render(
            full_snapshot_and_profile_context_str: str, thought_content_str: str, original_thought_content: str
        ) -> str:
            return user_loader.get_user_message(
                user_template_data,
                full_snapshot_and_profile_context_str=full_snapshot_and_profile_context_str,
                domain_name=self.domain_name,
                thought_content_str=thought_content_str,
                # Slots the stale pre-#974 template shape used — supplied so an explicit research override written
                # against the old shape still renders instead of KeyError-ing.
                rules_summary_str=rules_summary_str,
                context_str=context_str,
                original_thought_content=original_thought_content,
            )

        context = original_task_segments(task_context, system_snapshot_block, user_profiles_block)
        from ciris_engine.logic.prompt_assembly.segmenting import joined

        user = split_template(
            user_render,
            {
                "full_snapshot_and_profile_context_str": segment("ctx", SegmentKind.HISTORY, joined(context, language)),
                "thought_content_str": thought_request("request", thought_content_str, thought),
                "original_thought_content": thought_request("request:legacy_slot", thought_content_str, thought),
            },
            prefix="instr:user",
            first_glue="",
        )
        user = expand(user, "ctx", context, language)

        logger.debug(f"DSDMA '{self.domain_name}' composed prompt for thought {thought_id}")
        thought_images = images or []
        if thought_images:
            logger.info(
                f"[VISION] DSDMA '{self.domain_name}' building multimodal content with {len(thought_images)} images"
            )
        builder.message("user", *user, images=thought_images)
        return builder.assemble(
            PromptStage.DSDMA,
            evaluator_call(DSDMAResult.__name__, thought, language, authorization, agent_identity),
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
