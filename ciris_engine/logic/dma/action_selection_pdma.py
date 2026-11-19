"""Refactored Action Selection PDMA - Modular and Clean."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union, cast

if TYPE_CHECKING:
    from ciris_engine.logic.prompt_assembly import AssemblyCall
    from ciris_engine.logic.prompt_assembly.segmenting import PromptBuilder, Segments
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest

from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.logic.prompt_assembly.assembler import LayoutItem
from ciris_engine.schemas.dma.sent_prompts import carry_sent_prompts, sent_prompts_of
from ciris_engine.constants import DEFAULT_OPENAI_MODEL_NAME
from ciris_engine.logic.formatters import format_system_snapshot, format_user_profiles
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils.constants import get_localized_accord_text
from ciris_engine.protocols.dma.base import ActionSelectionDMAProtocol
from ciris_engine.protocols.faculties import EpistemicFaculty
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.faculty import ConscienceFailureContext, EnhancedDMAInputs
from ciris_engine.schemas.dma.prompts import PromptCollection
from ciris_engine.schemas.dma.results import (
    ActionSelectionDMAResult,
    ASPDMALLMResult,
    convert_llm_result_to_action_result,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.types import JSONDict

from .action_selection import ActionSelectionContextBuilder, ActionSelectionSpecialCases
from .prompt_loader import get_prompt_loader
from ciris_engine.logic.utils.localization import current_thought_language, in_thought_language
from .action_selection.faculty_integration import FacultyIntegration
from .base_dma import BaseDMA

logger = logging.getLogger(__name__)


def _segment(segment_id: str, kind: str, text: str, source: str = "engine") -> Any:
    """A prompt segment (kinds and sources by their policy names)."""
    from ciris_engine.schemas.context.prompt_provenance import AcctCarrier, PromptSegment, SegmentKind, SegmentSource

    seg_kind = SegmentKind(kind)
    return PromptSegment(
        segment_id=segment_id,
        kind=seg_kind,
        source=SegmentSource(source),
        text=text,
        acct=AcctCarrier() if seg_kind == SegmentKind.CONSCIENCE_FEEDBACK else None,
    )


def _joined(segments: List[Any], layout: List["LayoutItem"]) -> str:
    """The text of segments laid out with their glue (what the assembler renders for them)."""
    out: List[str] = []
    by_id = {seg.segment_id: seg for seg in segments}
    for item in layout:
        if out:
            out.append(item.glue)
        out.append(by_id[item.segment_id].text)
    return "".join(out)


def _concat(head: Any, tail: Any, glue: str) -> Any:
    """Two (segments, layout) blocks as one, ``glue`` between them (none when the head is empty)."""
    h_segments, h_layout = head
    t_segments, t_layout = tail
    if not t_segments:
        return h_segments, h_layout
    if not h_segments:
        return t_segments, [t_layout[0].model_copy(update={"glue": ""})] + t_layout[1:]
    return h_segments + t_segments, h_layout + [t_layout[0].model_copy(update={"glue": glue})] + t_layout[1:]


def _approval_segments(block: str, authorization: Any, language: str) -> Any:
    """The WA approval block: the grant (``rule.signed_guidance``, with its authz) and the rule that follows it."""
    from ciris_engine.logic.formatters.wa_approval import format_wa_approval_rule
    from ciris_engine.logic.prompt_assembly.segmenting import items, signed_guidance_segment

    rule = format_wa_approval_rule(authorization, language=language)
    if not rule or not block.endswith("\n\n" + rule):
        whole = _segment("instr:wa_approval", "stage_instruction", block)
        return [whole], items([whole], "")
    grant = signed_guidance_segment("rule:wa_grant", block[: -len(rule) - 2], authorization)
    rule_seg = _segment("instr:wa_approval_rule", "stage_instruction", rule)
    return [grant, rule_seg], items([grant, rule_seg], "\n\n")


#: The ASPDMA main-user slots that carry something other than the engine's own instruction text.
_MAIN_USER_SLOT_KINDS: Dict[str, "tuple[str, str]"] = {
    "original_thought_content": ("request", "user_input"),
    "original_task_str": ("request", "user_input"),
    "ponder_notes_str": ("dma_output", "llm_output"),
    "user_profile_context_str": ("history", "engine"),
    "system_snapshot_context_str": ("history", "engine"),
    "ethical_summary": ("dma_output", "llm_output"),
    "csdma_summary": ("dma_output", "llm_output"),
    "dsdma_summary_str": ("dma_output", "llm_output"),
    "idma_summary_str": ("dma_output", "llm_output"),
}


def _typed_main_user_slots(input_data: EnhancedDMAInputs, parts: Any) -> "tuple[Dict[str, Any], Dict[str, Any]]":
    """(typed slot segments, plain slot values) for the ASPDMA main user template.

    ``conscience_guidance`` is the retry veto (``conscience_feedback``) when the thought carries one, else the
    exhausted-bounce advisory alone (a DMA's rationale, ``dma_output``). A follow-up thought's content is model
    text, so its request segment's source is ``llm_output``.
    """
    from ciris_engine.logic.conscience.veto_contract import veto_entries_of_feedback
    from ciris_engine.schemas.context.prompt_provenance import AcctCarrier

    typed: Dict[str, Any] = {}
    plain: Dict[str, Any] = {}
    depth = getattr(input_data.original_thought, "thought_depth", 0)
    follow_up = isinstance(depth, int) and depth > 0
    for name, value in parts.slots.items():
        text = format(value)
        if name in _MAIN_USER_SLOT_KINDS and text:
            kind, source = _MAIN_USER_SLOT_KINDS[name]
            if name == "original_thought_content" and follow_up:
                source = "llm_output"
            typed[name] = _segment(f"slot:{name}", kind, text, source)
        elif name == "conscience_guidance" and text:
            if parts.conscience_feedback is not None:
                entries = veto_entries_of_feedback(parts.conscience_feedback)
                typed[name] = _segment("conscience_feedback", "conscience_feedback", text, "llm_output").model_copy(
                    update={"acct": AcctCarrier(veto_id=entries[-1].veto_id if entries else None)}
                )
            else:
                typed[name] = _segment("slot:bounce_advisory", "dma_output", text, "llm_output")
        else:
            plain[name] = value
    return typed, plain


def _split_sender(segments: List[Any], layout: List["LayoutItem"], sender: Any, language: str) -> "Segments":
    """Cut the VERIFIED SENDER block out of the original-task request into its own segments (#1366 item 5).

    ``original_task_str`` renders the task, then the block, then (on a follow-up) the follow-through note. The
    block becomes a ``sender_identity`` segment (rendered from its authn carrier), a ``display_name`` segment and
    the closing lines, as every other DMA sends it; the note after it is the engine's own instruction. Same bytes.
    """
    if sender is None:
        return segments, layout
    from ciris_engine.logic.formatters.verified_sender import format_verified_sender_block
    from ciris_engine.logic.prompt_assembly.segmenting import sender_block_segments

    block = format_verified_sender_block(sender, language)
    for index, seg in enumerate(segments):
        if seg.segment_id != "slot:original_task_str" or not block or block not in seg.text:
            continue
        start = seg.text.index(block)
        before, after = seg.text[:start], seg.text[start + len(block) :]
        sender_segs, sender_items = sender_block_segments(sender, include_display_name=True, language=language)
        glue = layout[index].glue
        new: List[Any] = []
        new_items: List[LayoutItem] = []
        if before:
            new.append(seg.model_copy(update={"text": before}))
            new_items.append(LayoutItem(segment_id=seg.segment_id, glue=glue))
            glue = ""
        new.extend(sender_segs)
        new_items.append(sender_items[0].model_copy(update={"glue": glue}))
        new_items.extend(sender_items[1:])
        if after:
            note = _segment("instr:task_followthrough", "stage_instruction", after)
            new.append(note)
            new_items.append(LayoutItem(segment_id=note.segment_id, glue=""))
        return segments[:index] + new + segments[index + 1 :], layout[:index] + new_items + layout[index + 1 :]
    return segments, layout


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    """Get a value from either a dict or object attribute."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


DEFAULT_TEMPLATE = """{system_header}

{pipeline_position}

{stage_contract}

{decision_format}

{closing_reminder}"""


def _merged_locale(locales: List[Optional[str]], language: str) -> Optional[str]:
    """The locale of a piece joined from fields served in ``locales``: their one locale, or, when they differ, the
    one that is not the thought's language (so the piece is listed as a fallback), else unknown."""
    known = [loc for loc in locales if loc]
    if not known or len(known) != len(locales):
        return next((loc for loc in known if loc.split("-")[0] != language.split("-")[0]), None)
    if len(set(known)) == 1:
        return known[0]
    return next((loc for loc in known if loc.split("-")[0] != language.split("-")[0]), known[0])


def _stage_contract() -> str:
    """The engine-owned ASPDMA contract (#1366): pipeline position, roles and authority, conscience override.

    Read from the engine's prompt template, NEVER from ``self.prompts``: that mapping carries the agent
    template's ``action_selection_pdma_overrides``, and every shipped template replaces ``system_header``
    there. The contract used to live inside ``system_header``, so no real agent ever saw it. No override
    key can reach this field; a research manifest still can (``load_prompt_template`` applies it).

    A locale whose copy lacks the field falls back to the English one, field by field, until the
    translation lane adds it.
    """
    from ciris_engine.logic.dma.prompt_loader import DEFAULT_LANGUAGE, DMAPromptLoader

    loader = get_prompt_loader(language=current_thought_language())
    text = loader.load_prompt_template("action_selection_pdma").stage_contract
    if not text and loader.language != DEFAULT_LANGUAGE:
        text = DMAPromptLoader(language=DEFAULT_LANGUAGE).load_prompt_template("action_selection_pdma").stage_contract
    return text or ""


def _stage_contract_served() -> Tuple[str, Optional[str]]:
    """``(contract, locale served)``: the thought language's copy, else English (as :func:`_stage_contract`)."""
    text = _stage_contract()
    own = get_prompt_loader(language=current_thought_language()).load_prompt_template("action_selection_pdma")
    if own.stage_contract:
        return text, own.served_language
    return text, "en" if text else None


def _pipeline_position_served() -> Tuple[str, Optional[str]]:
    """``(paragraph, locale served)`` of :func:`_pipeline_position`."""
    return get_prompt_loader(language=current_thought_language()).pipeline_position_served("action_selection_pdma")


def _pipeline_position() -> str:
    """The ASPDMA pipeline-position paragraph (#1366 item 12): engine-read like :func:`_stage_contract`, with the
    same English fallback. It opened ``stage_contract`` until it became a structural field of its own."""
    return get_prompt_loader(language=current_thought_language()).pipeline_position("action_selection_pdma")


class ActionSelectionPDMAEvaluator(BaseDMA[EnhancedDMAInputs, ActionSelectionDMAResult], ActionSelectionDMAProtocol):
    """
    Modular Action Selection PDMA Evaluator.

    Takes outputs from PDMA, CSDMA, DSDMA, and IDMA (which evaluates their reasoning)
    and selects a concrete handler action using the Principled Decision-Making Algorithm.

    Features:
    - Modular component architecture
    - Faculty integration for enhanced evaluation
    - Recursive evaluation on conscience failures
    - Special case handling (wakeup tasks, forced ponder, etc.)
    """

    PROMPT_FILE = Path(__file__).parent / "prompts" / "action_selection_pdma.yml"

    def __init__(
        self,
        service_registry: ServiceRegistry,
        model_name: str = DEFAULT_OPENAI_MODEL_NAME,
        max_retries: int = 2,
        prompt_overrides: Optional[Union[Dict[str, str], PromptCollection]] = None,
        faculties: Optional[Dict[str, EpistemicFaculty]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize ActionSelectionPDMAEvaluator."""
        # The caller's explicit overrides (the agent template's
        # action_selection_pdma_overrides): they win in every language.
        self._caller_overrides: Dict[str, str] = dict(prompt_overrides) if isinstance(prompt_overrides, dict) else {}
        super().__init__(
            service_registry=service_registry,
            model_name=model_name,
            max_retries=max_retries,
            prompt_overrides=prompt_overrides,
            faculties=faculties,
            **kwargs,
        )

        self.context_builder = ActionSelectionContextBuilder(self.prompts, service_registry, self.sink)
        # The builder reads the prompts of the thought being evaluated, not the init-time English copy.
        self.context_builder.prompts_provider = lambda: self.prompts
        self.faculty_integration = FacultyIntegration(faculties) if faculties else None

        # Store last prompts for debugging/streaming

    @property
    def prompts(self) -> Union[Dict[str, str], PromptCollection]:
        """This thought's ASPDMA prompts: the engine file, its localized copy, then the caller's overrides.

        BaseDMA loads ``PROMPT_FILE`` (the English root template) once at construction, so every
        thought used to read ``decision_format``, ``closing_reminder``, the action schemas and the
        guidance fields in English whatever its language. The localized template's copy of each of
        those keys now takes their place in the thought's language; a key the locale lacks keeps the
        English text, and an explicit caller override still wins.
        """
        base = self._file_prompts
        if isinstance(base, PromptCollection):
            return base
        language = current_thought_language()
        from ciris_engine.logic.dma.prompt_loader import DEFAULT_LANGUAGE

        if language == DEFAULT_LANGUAGE:
            return base
        try:
            localized = get_prompt_loader(language=language).load_prompt_template("action_selection_pdma")
        except (FileNotFoundError, ValueError) as e:
            logger.warning(f"ASPDMA: no localized prompts for {language!r} ({e}); using the base template")
            return base
        merged = dict(base)
        for key in base:
            value = localized.get_prompt(key)
            if isinstance(value, str) and value:
                merged[key] = value
        merged.update(self._caller_overrides)
        return merged

    @prompts.setter
    def prompts(self, value: Union[Dict[str, str], PromptCollection]) -> None:
        self._file_prompts = value

    def _prompt_locale(self, key: str) -> Optional[str]:
        """The locale ``self.prompts[key]`` was served in, by the same per-key merge (FSD §8.1).

        A caller override is the agent's own text (unknown); in a non-English thought, the localized copy's
        locale when it supplies the key, else ``en`` (the key kept the English root template's text).
        """
        if key in self._caller_overrides:
            return None
        base = self._file_prompts
        if isinstance(base, PromptCollection):
            return base.served_language
        from ciris_engine.logic.dma.prompt_loader import DEFAULT_LANGUAGE

        language = current_thought_language()
        if language == DEFAULT_LANGUAGE:
            return DEFAULT_LANGUAGE
        try:
            localized = get_prompt_loader(language=language).load_prompt_template("action_selection_pdma")
        except (FileNotFoundError, ValueError):
            return DEFAULT_LANGUAGE
        value = localized.get_prompt(key)
        if isinstance(value, str) and value:
            return localized.served_language
        return DEFAULT_LANGUAGE

    @in_thought_language("input_data.original_thought", "input_data.processing_context")
    async def evaluate(  # type: ignore[override]  # Extends base signature with enable_recursive_evaluation
        self, input_data: EnhancedDMAInputs, enable_recursive_evaluation: bool = False
    ) -> ActionSelectionDMAResult:
        """Evaluate triaged inputs and select optimal action."""

        if not input_data:
            raise ValueError("input_data is required")

        original_thought: Thought = input_data.original_thought
        logger.debug(f"Evaluating action selection for thought ID {original_thought.thought_id}")

        # Handle special cases first
        special_result = await self._handle_special_cases(input_data)
        if special_result:
            return special_result

        # Perform main evaluation
        try:
            result = await self._perform_main_evaluation(input_data, enable_recursive_evaluation)

            # Add faculty metadata if applicable
            faculty_enhanced = getattr(input_data, "faculty_enhanced", False)
            recursive_evaluation = getattr(input_data, "recursive_evaluation", False)

            if self.faculty_integration and faculty_enhanced:
                result = self.faculty_integration.add_faculty_metadata_to_result(
                    result, faculty_enhanced=True, recursive_evaluation=recursive_evaluation
                )

            logger.info(
                f"Action selection successful for thought {original_thought.thought_id}: {result.selected_action.value}"
            )
            return result

        except Exception as e:
            logger.error(f"Action selection failed for thought {original_thought.thought_id}: {e}", exc_info=True)
            return self._create_fallback_result(str(e))

    async def recursive_evaluate_with_faculties(
        self,
        input_data: Union[JSONDict, EnhancedDMAInputs],
        conscience_failure_context: Union[JSONDict, ConscienceFailureContext],
    ) -> ActionSelectionDMAResult:
        """Perform recursive evaluation using epistemic faculties."""

        if not self.faculty_integration:
            logger.warning(
                "Recursive evaluation requested but no faculties available. Falling back to regular evaluation."
            )
            # Convert to EnhancedDMAInputs if dict
            if isinstance(input_data, dict):
                input_data = EnhancedDMAInputs(**input_data)
            return await self.evaluate(input_data, enable_recursive_evaluation=False)

        # Convert to EnhancedDMAInputs if dict
        if isinstance(input_data, dict):
            input_data = EnhancedDMAInputs(**input_data)

        original_thought: Thought = input_data.original_thought
        logger.info(f"Starting recursive evaluation with faculties for thought {original_thought.thought_id}")

        # Convert conscience context to typed model if needed
        if isinstance(conscience_failure_context, dict):
            conscience_failure_context = ConscienceFailureContext(
                failure_reason=conscience_failure_context.get("failure_reason", "Unknown"),
                retry_guidance=conscience_failure_context.get("retry_guidance", ""),
            )

        # At this point input_data is guaranteed to be EnhancedDMAInputs
        input_dict = input_data.model_dump()

        enhanced_inputs = await self.faculty_integration.enhance_evaluation_with_faculties(
            original_thought=original_thought,
            triaged_inputs=input_dict,
            conscience_failure_context=conscience_failure_context,
        )
        enhanced_inputs.recursive_evaluation = True

        return await self.evaluate(enhanced_inputs, enable_recursive_evaluation=False)

    async def _handle_special_cases(self, input_data: EnhancedDMAInputs) -> Optional[ActionSelectionDMAResult]:
        """Handle special cases that override normal evaluation."""

        # Check for forced ponder
        ponder_result = await ActionSelectionSpecialCases.handle_ponder_force(input_data)
        if ponder_result:
            return ponder_result

        # Check wakeup task SPEAK requirement
        wakeup_result = await ActionSelectionSpecialCases.handle_wakeup_task_speak_requirement(input_data)
        if wakeup_result:
            return wakeup_result

        return None

    def _build_main_user_content(self, input_data: EnhancedDMAInputs, agent_name: str) -> str:
        """The main user content as text (the segments of :meth:`_user_segments`, joined)."""
        return _joined(*self._user_segments(input_data, agent_name))

    def _user_segments(self, input_data: EnhancedDMAInputs, agent_name: str) -> "Segments":
        """The main user content as typed segments, in the bytes it has always had.

        A template's `user_prompt_template` is ADDITIVE (#996): it leads, and
        the composed integration layer follows undiminished. It does not
        replace `context_integration` — that field carries 22 live slots, so
        replacing it would disable every summary, advisory and guidance block
        those slots render.
        """
        from ciris_engine.logic.prompt_assembly.segmenting import split_template

        template_user_override = self.prompts.get("user_prompt_template") if isinstance(self.prompts, dict) else None
        parts = self.context_builder.main_user_parts(input_data, agent_name)
        typed, plain = _typed_main_user_slots(input_data, parts)
        segments, layout = split_template(
            lambda **values: self.context_builder.render_main_user(parts, values),
            typed,
            prefix="instr:user",
            plain=plain,
            # The collection render_main_user reads (ASPDMA has no prompt_template_data of its own).
            locale=parts.template_data.served_language if isinstance(parts.template_data, PromptCollection) else None,
        )
        segments, layout = _split_sender(segments, layout, parts.sender, current_thought_language())

        if template_user_override:
            thought_content = str(input_data.original_thought.content) if input_data.original_thought else ""
            available_actions = (
                ", ".join(a.value for a in input_data.permitted_actions)
                if input_data.permitted_actions
                else "speak, task_complete"
            )
            # #996 — APPEND the composition, do not replace it.
            #
            # This branch used to `return framing`, leaving the builder call
            # below unreachable whenever a template supplied a
            # `user_prompt_template`. `build_main_user_content` is the SOLE
            # assembler of the prior-DMA summaries (context_builder.py:189-192);
            # the system message carries system_header/identity/snapshot and no
            # DMA results, and `compose_messages` emits exactly four messages,
            # so there is no third path. On `default` (Ally) that meant 131 B of
            # framing in place of a 7,932 B composition — 98.3% absent, and what
            # was absent was the entire integration layer:
            #
            #   Ethical PDMA summary                        axiotic
            #   CSDMA plausibility                          empirical
            #   DSDMA domain alignment                      empirical
            #   IDMA k_eff/rho fragility                    epistemic
            #   conscience retry guidance + bounce advisory epistemic
            #   ponder notes                                epistemic
            #   final-attempt advisory                      deontic
            #   original task context                       contingent
            #   context_integration                         structural
            #
            # Every faculty class the pipeline produces, dropped at once: the
            # ethical evaluation ran, produced a result, and was discarded
            # before the action was chosen. The four consciences still gate the
            # output afterwards, so this was never an unguarded pipeline — but
            # selection was made blind to the findings computed for it. And
            # `default` is what a deployment gets by default.
            #
            # Sharpest single item is the deontic one: the final-attempt
            # advisory fires at depth >= max_rounds - 1 to say PONDER is no
            # longer available. It never rendered here, so the forced-action
            # band was invisible to selection while ponder_handler still
            # enforced it.
            #
            # Appended rather than slotted, per #993: a new {slot} would have to
            # be added to 29 localized copies to render for anyone but English
            # speakers, which is the #991/#992 failure mode. Framing first keeps
            # the template's authored voice in the lead position. The thought and
            # action list therefore appear twice — once in the persona framing,
            # once in the structured composition; that duplication is accepted
            # deliberately over losing either the voice or the integration layer.
            from ciris_engine.schemas.context.prompt_provenance import SegmentSource

            # The framing's words are the agent template's (FSD §4.3); the thought it quotes stays the request. (The
            # permitted-action list it may name is plain text inside it: an enum list, not free text.)
            framing, framing_layout = split_template(
                lambda **values: template_user_override.format(**values),
                {"thought_content": _segment("request:framing", "request", thought_content, "user_input")},
                prefix="instr:framing",
                plain={"available_actions": available_actions},
                instruction_source=SegmentSource.AGENT_PROFILE,
            )
            if framing and segments:
                logger.debug(
                    "ASPDMA template user_prompt_template override: %d chars framing + %d chars composition",
                    len(_joined(framing, framing_layout)),
                    len(_joined(segments, layout)),
                )
                layout = framing_layout + [layout[0].model_copy(update={"glue": "\n\n"})] + layout[1:]
                segments = framing + segments
            elif framing:
                segments, layout = framing, framing_layout
        return segments, layout

    @staticmethod
    def _working_language(original_thought: Any, processing_context: Any) -> str:
        """This thought's language, by the one resolver every DMA and conscience uses (resolve_thought_language)."""
        from ciris_engine.logic.utils.localization import resolve_thought_language

        return resolve_thought_language(original_thought, processing_context)

    def _build_accord_with_metadata(self, original_thought: Any, processing_context: Any = None) -> str:
        """Build accord text with thought type metadata (uses LOCALIZED ACCORD for ASPDMA).

        ASPDMA uses the localized accord (single language) for clearer action selection guidance.
        Other DMAs (PDMA, CSDMA, IDMA, DSDMA) use the polyglot accord for cross-cultural depth.
        """
        return _joined(*self._accord_segments(original_thought, processing_context))

    def _accord_segments(self, original_thought: Any, processing_context: Any = None) -> "Segments":
        """The thought-type line, then the localized accord (one system message); ([], []) without an accord."""
        from ciris_engine.logic.prompt_assembly.segmenting import items

        # ASPDMA uses the localized accord, in the same language as its guidance.
        accord_text = get_localized_accord_text(self._working_language(original_thought, processing_context))
        if not accord_text:
            return [], []
        accord = _segment("accord", "accord", accord_text)
        if original_thought and hasattr(original_thought, "thought_type"):
            line = _segment("instr:thought_type", "stage_instruction", f"THOUGHT_TYPE={original_thought.thought_type.value}")
            return [line, accord], items([line, accord], "\n\n")
        return [accord], items([accord], "")

    async def _perform_main_evaluation(
        self, input_data: EnhancedDMAInputs, enable_recursive_evaluation: bool
    ) -> ActionSelectionDMAResult:
        """Perform the main LLM-based evaluation."""
        input_images = getattr(input_data, "images", []) or []
        logger.info(f"[VISION] _perform_main_evaluation called with {len(input_images)} images")

        agent_identity = getattr(input_data, "agent_identity", {})
        agent_name = _get_value(agent_identity, "agent_name", "CIRISAgent")
        original_thought = input_data.original_thought

        # Pre-cache tools AND task context BEFORE building prompt
        await self.context_builder.pre_cache_context(original_thought)

        # Compose messages via the extracted seam (#972), built by PromptAssembler (#1366 Phase 3)
        messages, manifest = self.compose_prompt(input_data, agent_name)

        # Use Gemini-compatible flat schema (no Union types)
        # This enables compatibility with providers that don't support Union (Google Gemini)
        with prompt_manifest_scope(manifest):
            result_tuple = await self.call_llm_structured(
                messages=messages,
                response_model=ASPDMALLMResult,
                max_tokens=8192,
                temperature=0.0,
                thought_id=input_data.original_thought.thought_id,
                task_id=input_data.original_thought.source_task_id,
            )

        # Extract the LLM result and convert to typed ActionSelectionDMAResult
        llm_result = cast(ASPDMALLMResult, result_tuple[0])

        # Get channel_id from context if available
        channel_id = _get_value(input_data.processing_context, "channel_id") if input_data.processing_context else None

        sent = sent_prompts_of(llm_result)
        # Convert flat LLM result to typed ActionSelectionDMAResult
        final_result = convert_llm_result_to_action_result(
            llm_result=llm_result,
            channel_id=channel_id,
            raw_llm_response=None,  # Set if needed for debugging
            evaluation_time_ms=None,  # Set from metrics if available
            resource_usage=None,  # Set from metrics if available
            # From THIS call's result, never from the evaluator: one evaluator
            # serves every concurrent thought (schemas/dma/sent_prompts.py).
            user_prompt=sent.user if sent else None,
            system_prompt=sent.system if sent else None,
        )
        carry_sent_prompts(llm_result, final_result)

        if final_result.selected_action == HandlerActionType.OBSERVE:
            thought_id = input_data.original_thought.thought_id
            logger.warning(f"OBSERVE ACTION: Successfully created for thought {thought_id}")
            logger.warning(f"OBSERVE PARAMS: {final_result.action_parameters}")
            logger.warning(f"OBSERVE RATIONALE: {final_result.rationale}")

        return final_result

    def compose_messages(self, input_data: EnhancedDMAInputs, agent_name: str) -> List[JSONDict]:
        """Compose the full ASPDMA prompt message list from gathered inputs (#972).

        Pure prompt composition - no LLM call, no data fetching. The awaited
        ``context_builder.pre_cache_context()`` (tools + task cache) must run
        in ``_perform_main_evaluation()`` before this is called.
        """
        messages, _ = self.compose_prompt(input_data, agent_name)
        return messages

    @in_thought_language("input_data.original_thought", "input_data.processing_context")
    def compose_prompt(self, input_data: EnhancedDMAInputs, agent_name: str) -> "tuple[List[JSONDict], PromptManifest]":
        """The ASPDMA messages and their manifest, built by PromptAssembler from typed segments (FSD §6)."""
        from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block
        from ciris_engine.logic.prompt_assembly.segmenting import PromptBuilder
        from ciris_engine.logic.utils.localization import get_language_guidance, language_guidance_locale
        from ciris_engine.schemas.context.prompt_provenance import PromptStage

        # #1007 — SYSTEM FIRST, matching the order the messages are emitted in.
        #
        # The #997 dump records each field render as it happens and matches those
        # parts to messages FIFO, because composition order IS the honesty rule:
        # a part queue that searched instead of consuming could attribute a field
        # to whichever message happened to contain similar bytes.
        #
        # User content used to be built first while the system message is emitted
        # first, so the queue read [user parts…, system parts…] against messages
        # [system…, user]. Covering the system message hit a user part, failed,
        # and the whole 2,755 B message fell back to one opaque `mixed` block —
        # which carries "Recall CIRIS principles override personal preference",
        # axiotic, so §10.2.1 refused every axiotic regime on `default`.
        #
        # The two builders are independent (both read only `input_data`), so the
        # swap is order-of-evaluation only. The 12 goldens are the proof.
        system_segments, system_layout = self._system_segments(input_data)

        # Build main user content
        user_segments, user_layout = self._user_segments(input_data, agent_name)

        # Append faculty insights if available
        if input_data.faculty_evaluations and self.faculty_integration:
            faculty_insights = self.faculty_integration.build_faculty_insights_string(input_data.faculty_evaluations)
            if faculty_insights:
                insights = _segment("faculty_insights", "dma_output", faculty_insights, "llm_output")
                user_segments = user_segments + [insights]
                user_layout = user_layout + [LayoutItem(segment_id=insights.segment_id, glue="")]

        input_images = getattr(input_data, "images", []) or []
        if input_images:
            logger.info(f"[VISION] ActionSelectionPDMA building multimodal content with {len(input_images)} images")

        builder = PromptBuilder()
        builder.message("system", *self._accord_segments(input_data.original_thought, input_data.processing_context))
        # Per-language guidance, in THIS THOUGHT'S language. ASPDMA writes the
        # reply, so it needs the user's guidance more than any other DMA. It used
        # to read the env var (CIRIS_PREFERRED_LANGUAGE) while IDMA, DSDMA,
        # DSASPDMA and the consciences resolved the thought's own language: a bn
        # user on a deployment without that variable got English guidance and
        # English crisis numbers here while coherence judged the reply in bn
        # (2.18.0 bn battery, q04/q06/q07).
        _lang = self._working_language(input_data.original_thought, input_data.processing_context)
        builder.single("system", _segment("instr:language", "stage_instruction", get_language_guidance(_lang) or "").model_copy(update={"locale": language_guidance_locale(_lang)}))
        # Crisis resources ride directly after language guidance (#1248) — the
        # locale's verified numbers, from the one composer every DMA shares.
        builder.single("system", _segment("instr:crisis", "stage_instruction", get_crisis_resources_system_block(_lang) or ""))
        builder.message("system", system_segments, system_layout)
        builder.message("user", user_segments, user_layout, images=input_images)
        return builder.assemble(PromptStage.ASPDMA, self._assembly_call(input_data, _lang, builder))

    def _assembly_call(self, input_data: EnhancedDMAInputs, language: str, builder: "PromptBuilder") -> "AssemblyCall":
        """The manifest's call facts, from trusted state only (the verified grant, verified amendments)."""
        from ciris_engine.logic.formatters import wa_authorization_of
        from ciris_engine.logic.prompt_assembly import AssemblyCall
        from ciris_engine.logic.prompt_assembly.segmenting import policy_facts
        from ciris_engine.schemas.context.prompt_provenance import ManifestThoughtKind, SegmentKind

        processing_context = input_data.processing_context
        authorization = wa_authorization_of(processing_context)
        snapshot = _get_value(processing_context, "system_snapshot") if processing_context else None
        agent_identity = _get_value(snapshot, "agent_identity") if snapshot else None
        thought = input_data.original_thought
        depth = getattr(thought, "thought_depth", 0)
        kind = (
            ManifestThoughtKind.GUIDANCE
            if authorization is not None
            else ManifestThoughtKind.FOLLOWUP if isinstance(depth, int) and depth > 0 else ManifestThoughtKind.SEED
        )
        retry = any(seg.kind == SegmentKind.CONSCIENCE_FEEDBACK for seg in builder.segments)
        task_id = getattr(thought, "source_task_id", None)
        thought_id = getattr(thought, "thought_id", None)
        return AssemblyCall(
            task_id=task_id if isinstance(task_id, str) else None,
            thought_id=thought_id if isinstance(thought_id, str) else None,
            thought_kind=kind,
            retry_index=1 if retry else 0,
            response_model=ASPDMALLMResult.__name__,
            facts=policy_facts(authorization, agent_identity, id_scoped=False),
            language=language,
        )

    def _extract_system_blocks(self, processing_context: Any) -> tuple[str, str, Any]:
        """Extract system snapshot block, user profiles block, and system snapshot object."""
        system_snapshot = _get_value(processing_context, "system_snapshot")
        if not system_snapshot:
            return "", "", None

        user_profiles = _get_value(system_snapshot, "user_profiles")
        return (
            format_system_snapshot(system_snapshot),
            format_user_profiles(user_profiles),
            system_snapshot,
        )

    def _validate_and_build_identity_block(self, system_snapshot: Any) -> str:
        """Validate identity exists and build the identity block. Raises on missing identity."""
        if not system_snapshot:
            raise ValueError(
                "CRITICAL: No system_snapshot in processing_context for ActionSelectionPDMA! "
                "Identity is required for ALL DMA evaluations. This is a fatal error."
            )

        agent_identity = _get_value(system_snapshot, "agent_identity")
        if not agent_identity:
            raise ValueError(
                "CRITICAL: No agent identity found in system_snapshot for ActionSelectionPDMA! "
                "Identity is required for ALL DMA evaluations. This is a fatal error."
            )

        agent_id = _get_value(agent_identity, "agent_id")
        description = _get_value(agent_identity, "description")
        role = _get_value(agent_identity, "role")

        for field_name, field_value in [("agent_id", agent_id), ("description", description), ("role", role)]:
            if not field_value:
                raise ValueError(
                    f"CRITICAL: {field_name} is missing from identity in ActionSelectionPDMA! This is a fatal error."
                )

        # Routed (#974 step 3): one keyed source (prompts.identity_block) for
        # the CORE IDENTITY doctrine, replaceable via the research `string`
        # namespace. ASPDMA has no prompt_loader; language resolves from the
        # deployment env inside the helper, matching this DMA's convention.
        from ciris_engine.logic.formatters import amendment_texts, format_core_identity_block

        return format_core_identity_block(
            str(agent_id), str(description), str(role), amendments=amendment_texts(agent_identity)
        )

    def _identity_segments(self, system_snapshot: Any) -> "Segments":
        """The validated identity block as segments: identity_base pieces and one amendment segment per grant."""
        from ciris_engine.logic.prompt_assembly.segmenting import identity_segments, items

        legacy = self._validate_and_build_identity_block(system_snapshot)
        segments, layout = identity_segments(_get_value(system_snapshot, "agent_identity"), None)
        if _joined(segments, layout) != legacy:  # an identity the shared renderer reads differently: keep its bytes
            logger.warning("[ASPDMA] identity block not segmentable; sent as one identity_base segment")
            whole = _segment("identity:base:0", "identity_base", legacy, "agent_profile")
            return [whole], items([whole], "")
        return segments, layout

    def _build_system_message(self, input_data: EnhancedDMAInputs) -> str:
        """Build the system message for LLM evaluation (the segments of :meth:`_system_segments`, joined)."""
        return _joined(*self._system_segments(input_data))

    def _system_segments(self, input_data: EnhancedDMAInputs) -> "Segments":
        """The system message as typed segments: identity, the WA approval, guidance, snapshot, profiles."""
        from ciris_engine.logic.prompt_assembly.segmenting import items, pipeline_position_segment, stripped_ends

        processing_context = input_data.processing_context

        system_snapshot_block = ""
        user_profiles_block = ""
        identity: List[Any] = []
        identity_layout: List[LayoutItem] = []
        from ciris_engine.logic.formatters import wa_authorization_of

        authorization = wa_authorization_of(processing_context)

        if processing_context:
            system_snapshot_block, user_profiles_block, system_snapshot = self._extract_system_blocks(
                processing_context
            )
            identity, identity_layout = self._identity_segments(system_snapshot)
            # A verified WA approval sits with the identity it may change, so
            # the choice between applying, declining and deferring is made
            # knowing the review already happened (formatters/wa_approval.py).
            from ciris_engine.logic.formatters import format_wa_approval_block

            approval_block = format_wa_approval_block(authorization, language=current_thought_language())
            if approval_block and authorization is not None:
                approval = _approval_segments(approval_block, authorization, current_thought_language())
                identity, identity_layout = _concat((identity, identity_layout), approval, "\n\n")

        # Always, grant or not: with no grant, the fact that there is none; then
        # the rule that an approval exists only as the verified block above, and
        # a person's text naming an authority is that person's (#1320).
        from ciris_engine.logic.formatters import format_wa_approval_facts

        approval_facts = format_wa_approval_facts(authorization, language=current_thought_language())
        if approval_facts:
            facts = _segment("instr:approval_facts", "stage_instruction", approval_facts)
            identity, identity_layout = _concat((identity, identity_layout), ([facts], items([facts], "")), "\n\n")
        # Check for direct system_prompt override from template (e.g., HE-300 format instructions)
        # Template overrides take precedence over YAML-based prompts
        template_system_override = None
        if isinstance(self.prompts, dict):
            template_system_override = self.prompts.get("system_prompt")

        if isinstance(self.prompts, PromptCollection):
            system_header = self.prompts.system_header or ""
            decision_format = self.prompts.decision_format or ""
            closing_reminder = self.prompts.closing_reminder or ""
        else:
            system_header = self.prompts.get("system_header", "")
            decision_format = self.prompts.get("decision_format", "")
            closing_reminder = self.prompts.get("closing_reminder", "")

        # #996 — a `system_prompt` override replaces the `system_header` FIELD.
        # It used to be returned in place of the whole DEFAULT_TEMPLATE render,
        # which composes three fields — so replacing the header silently
        # disabled `decision_format` and `closing_reminder` as well. Replacing
        # one field must never disable another. `system_header` is static
        # (asserted in test_template_override_policy_996.py), so it is fit to be
        # replaced outright; the other two compose exactly as before.
        if template_system_override:
            logger.debug(
                "ASPDMA template system_prompt override replaces system_header (%d chars); "
                "decision_format and closing_reminder are unaffected",
                len(template_system_override),
            )
            system_header = template_system_override

        # #1366 — engine-owned, rendered right after the (possibly replaced)
        # header; see `_stage_contract` for why it is not read from self.prompts.
        stage_contract, contract_locale = _stage_contract_served()
        pipeline_position, position_locale = _pipeline_position_served()
        field_locales = {
            "system_header": self._prompt_locale("system_header"),
            "pipeline_position": position_locale,
            "stage_contract": contract_locale,
            "decision_format": self._prompt_locale("decision_format"),
            "closing_reminder": self._prompt_locale("closing_reminder"),
        }

        # #1007 — render each field through `safe_format` so the composer's
        # per-field seam exists here too.
        #
        # This was `DEFAULT_TEMPLATE.format(...)`, a bare .format() in Python.
        # The #997 dump records a field by wrapping `safe_format`, so three
        # fields joined by a Python literal arrived as ONE opaque message and
        # were annotated `mixed`. That block carries "Recall CIRIS principles
        # override personal preference" — axiotic — so §10.2.1 refused every
        # regime varying axiotic on the `default` template: the shipped persona
        # could not be a campaign arm.
        #
        # DEFAULT_TEMPLATE is "{system_header}\n\n{pipeline_position}\n\n
        # {stage_contract}\n\n{decision_format}\n\n{closing_reminder}", so
        # joining the renders on "\n\n" is the same bytes — proven by the
        # goldens, which is why they are the gate for this change rather than a
        # formality. #1366 split `stage_contract` out of `system_header` at a
        # blank line, and `pipeline_position` out of `stage_contract` (item 12),
        # so with no override the message bytes are unchanged.
        from ciris_engine.logic.dma.prompt_loader import safe_format

        _lang = current_thought_language()
        rendered = [
            (_field, safe_format(_text, source=f"action_selection_pdma.{_field}[{_lang}]"))
            for _field, _text in (
                ("system_header", system_header),
                ("pipeline_position", pipeline_position),
                ("stage_contract", stage_contract),
                ("decision_format", decision_format),
                ("closing_reminder", closing_reminder),
            )
            if _field not in ("stage_contract", "pipeline_position") or _text
        ]
        system_guidance = "\n\n".join(_text for _, _text in rendered)

        # format_system_prompt_blocks: identity, guidance, snapshot, profiles; blank-line joined, stripped.
        # The guidance is the instruction before the pipeline position, the position itself (its own segment,
        # from its own field: #1366 item 12), and the instruction after it, joined by the same blank lines.
        names = [_field for _field, _ in rendered]
        at = names.index("pipeline_position") if "pipeline_position" in names else len(names)
        # The header is the agent template's when it supplies one (`system_header`, or a `system_prompt` in its
        # place): the agent's own text, so it carries the agent-profile source (FSD §4.3), never `engine`.
        header_source = (
            "agent_profile"
            if template_system_override or "system_header" in getattr(self, "_caller_overrides", {})
            else "engine"
        )
        # Locales (FSD §8.1): the agent's own header is unstated; a piece joined from engine fields served in
        # different locales records the fallback one, so e.g. an English stage contract in ta is listed.
        def located(seg: Any, fields: List[str]) -> Any:
            return seg.model_copy(update={"locale": _merged_locale([field_locales[f] for f in fields], _lang)})

        header = _segment("instr:system", "stage_instruction", rendered[0][1], header_source)
        guidance_parts = [located(header, ["system_header"]) if header_source == "engine" else header]
        if at > 1:  # no pipeline position (a research manifest emptied it): the engine fields after the header
            guidance_parts.append(
                located(
                    _segment(
                        "instr:system:after_header", "stage_instruction", "\n\n".join(t for _, t in rendered[1:at])
                    ),
                    names[1:at],
                )
            )
        if at < len(names):
            guidance_parts.append(pipeline_position_segment(rendered[at][1], locale=position_locale))
            if rendered[at + 1 :]:
                guidance_parts.append(
                    located(
                        _segment(
                            "instr:system:after_position",
                            "stage_instruction",
                            "\n\n".join(_text for _, _text in rendered[at + 1 :]),
                        ),
                        names[at + 1 :],
                    )
                )
        blocks: List[Any] = [(identity, identity_layout)]
        if system_guidance:
            blocks.append((guidance_parts, items(guidance_parts, "\n\n")))
        if system_snapshot_block:
            snap = _segment("system_snapshot", "history", system_snapshot_block)
            blocks.append(([snap], items([snap], "")))
        if user_profiles_block:
            profiles = _segment("user_profiles", "history", user_profiles_block)
            blocks.append(([profiles], items([profiles], "")))
        segments: List[Any] = []
        layout: List[LayoutItem] = []
        for block in blocks:
            if block[0]:
                segments, layout = _concat((segments, layout), block, "\n\n")
        segments = stripped_ends(segments)
        kept = {seg.segment_id for seg in segments}
        return segments, [i for i in layout if i.segment_id in kept]

    def _create_fallback_result(self, error_message: str) -> ActionSelectionDMAResult:
        """Create a fallback result for error cases."""

        fallback_params = PonderParams(questions=[f"System error during action selection: {error_message}"])

        return ActionSelectionDMAResult(
            selected_action=HandlerActionType.PONDER,
            action_parameters=fallback_params,
            rationale=f"Fallback due to error: {error_message}",
        )

    def __repr__(self) -> str:
        faculty_count = len(self.faculties) if self.faculties else 0
        return f"<ActionSelectionPDMAEvaluator model='{self.model_name}' faculties={faculty_count}>"
