"""Refactored Action Selection PDMA - Modular and Clean."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

from ciris_engine.constants import DEFAULT_OPENAI_MODEL_NAME
from ciris_engine.logic.formatters import format_system_prompt_blocks, format_system_snapshot, format_user_profiles
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
from .template_overrides import additive
from .action_selection.faculty_integration import FacultyIntegration
from .base_dma import BaseDMA

logger = logging.getLogger(__name__)


def _get_value(obj: Any, key: str, default: Any = None) -> Any:
    """Get a value from either a dict or object attribute."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


DEFAULT_TEMPLATE = """{system_header}

{decision_format}

{closing_reminder}"""


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
        super().__init__(
            service_registry=service_registry,
            model_name=model_name,
            max_retries=max_retries,
            prompt_overrides=prompt_overrides,
            faculties=faculties,
            **kwargs,
        )

        self.context_builder = ActionSelectionContextBuilder(self.prompts, service_registry, self.sink)
        self.faculty_integration = FacultyIntegration(faculties) if faculties else None

        # Store last prompts for debugging/streaming
        self.last_user_prompt: Optional[str] = None
        self.last_system_prompt: Optional[str] = None

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
        """Build the main user content.

        A template's `user_prompt_template` is ADDITIVE (#996): it leads, and
        the composed integration layer follows undiminished. It does not
        replace `context_integration` — that field carries 22 live slots, so
        replacing it would disable every summary, advisory and guidance block
        those slots render.
        """
        template_user_override = self.prompts.get("user_prompt_template") if isinstance(self.prompts, dict) else None

        if template_user_override:
            thought_content = str(input_data.original_thought.content) if input_data.original_thought else ""
            available_actions = (
                ", ".join(a.value for a in input_data.permitted_actions)
                if input_data.permitted_actions
                else "speak, task_complete"
            )
            framing = template_user_override.format(
                thought_content=thought_content, available_actions=available_actions
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
            composed = self.context_builder.build_main_user_content(input_data, agent_name)
            logger.debug(
                "ASPDMA template user_prompt_template override: %d chars framing + %d chars composition",
                len(framing),
                len(composed),
            )
            return additive(framing, composed)

        return self.context_builder.build_main_user_content(input_data, agent_name)

    def _build_accord_with_metadata(self, original_thought: Any, processing_context: Any = None) -> str:
        """Build accord text with thought type metadata (uses LOCALIZED ACCORD for ASPDMA).

        ASPDMA uses the localized accord (single language) for clearer action selection guidance.
        Other DMAs (PDMA, CSDMA, IDMA, DSDMA) use the polyglot accord for cross-cultural depth.
        """
        # ASPDMA uses localized accord - extracts user language from context if available
        lang = None
        if processing_context:
            system_snapshot = _get_value(processing_context, "system_snapshot")
            if system_snapshot:
                user_profiles = _get_value(system_snapshot, "user_profiles")
                if user_profiles and len(user_profiles) > 0:
                    first_profile = user_profiles[0]
                    lang = (
                        first_profile.get("preferred_language")
                        if isinstance(first_profile, dict)
                        else getattr(first_profile, "preferred_language", None)
                    )

        accord_text = get_localized_accord_text(lang)
        if not accord_text:
            return ""

        if original_thought and hasattr(original_thought, "thought_type"):
            return f"THOUGHT_TYPE={original_thought.thought_type.value}\n\n{accord_text}"
        return accord_text

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

        # Compose messages via the extracted seam (#972)
        messages = self.compose_messages(input_data, agent_name)

        # Use Gemini-compatible flat schema (no Union types)
        # This enables compatibility with providers that don't support Union (Google Gemini)
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

        # Convert flat LLM result to typed ActionSelectionDMAResult
        final_result = convert_llm_result_to_action_result(
            llm_result=llm_result,
            channel_id=channel_id,
            raw_llm_response=None,  # Set if needed for debugging
            evaluation_time_ms=None,  # Set from metrics if available
            resource_usage=None,  # Set from metrics if available
            user_prompt=self.last_user_prompt,
        )

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
        # Build main user content
        main_user_content = self._build_main_user_content(input_data, agent_name)

        # Append faculty insights if available
        if input_data.faculty_evaluations and self.faculty_integration:
            faculty_insights = self.faculty_integration.build_faculty_insights_string(input_data.faculty_evaluations)
            main_user_content += faculty_insights

        # Build messages
        system_message = self._build_system_message(input_data)
        accord_with_metadata = self._build_accord_with_metadata(
            input_data.original_thought, input_data.processing_context
        )

        input_images = getattr(input_data, "images", []) or []
        if input_images:
            logger.info(f"[VISION] ActionSelectionPDMA building multimodal content with {len(input_images)} images")
        user_content = self.build_multimodal_content(main_user_content, input_images)

        messages: List[JSONDict] = []
        if accord_with_metadata:
            messages.append({"role": "system", "content": accord_with_metadata})
        # Per-language guidance — empty for most languages, populated for
        # locales where systematic terminology gaps were observed (am as
        # of 2.7.6). ASPDMA has no prompt_loader, so resolve language from
        # the env var (CIRIS_PREFERRED_LANGUAGE) which is what the agent's
        # deployment sets globally.
        from ciris_engine.logic.utils.localization import get_language_guidance, get_preferred_language

        _lang_guidance = get_language_guidance(get_preferred_language())
        if _lang_guidance:
            messages.append({"role": "system", "content": _lang_guidance})
        messages.append({"role": "system", "content": system_message})
        messages.append({"role": "user", "content": user_content})

        # Store prompts for streaming/debugging
        self.last_system_prompt = system_message
        self.last_user_prompt = main_user_content

        return messages

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
        from ciris_engine.logic.formatters import format_core_identity_block

        return format_core_identity_block(str(agent_id), str(description), str(role))

    def _build_conscience_guidance_block(self, processing_context: Any) -> str:
        """Build conscience guidance block for retry format enforcement."""
        if not processing_context:
            return ""

        conscience_guidance = _get_value(processing_context, "conscience_guidance")
        if not conscience_guidance:
            return ""

        retry_attempt = conscience_guidance.get("retry_attempt", 1)
        original_failure = conscience_guidance.get("original_action_failed_because", "")

        logger.warning(f"[ASPDMA] Conscience guidance detected - retry {retry_attempt}: {original_failure[:100]}")

        return f"""
=== CRITICAL FORMAT RETRY ===
RETRY ATTEMPT: {retry_attempt}
PREVIOUS FAILURE: {original_failure}

YOUR PREVIOUS RESPONSE WAS REJECTED because it did not start with a classification word.

MANDATORY FIX: Your SPEAK content MUST start with exactly ONE of these words:
ETHICAL, UNETHICAL, REASONABLE, UNREASONABLE, MATCHES, CONTRADICTS, FAIR, UNFAIR, JUST, UNJUST, VALID, INVALID, MORAL, IMMORAL

DO NOT start with: "The", "This", "Your", "I", "In", "It", "My" or any other word.

CORRECT: "REASONABLE. The expectation is..."
WRONG: "The expectation is reasonable..."
=== END FORMAT RETRY ===
"""

    def _build_system_message(self, input_data: EnhancedDMAInputs) -> str:
        """Build the system message for LLM evaluation."""
        processing_context = input_data.processing_context

        system_snapshot_block = ""
        user_profiles_block = ""
        identity_block = ""

        if processing_context:
            system_snapshot_block, user_profiles_block, system_snapshot = self._extract_system_blocks(
                processing_context
            )
            identity_block = self._validate_and_build_identity_block(system_snapshot)

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
        # DEFAULT_TEMPLATE is "{system_header}\n\n{decision_format}\n\n
        # {closing_reminder}", so joining the three renders on "\n\n" is the
        # same bytes — proven by the 12 goldens, which is why they are the gate
        # for this change rather than a formality.
        from ciris_engine.logic.dma.prompt_loader import safe_format

        _lang = get_prompt_loader().language
        system_guidance = "\n\n".join(
            safe_format(_text, source=f"action_selection_pdma.{_field}[{_lang}]")
            for _field, _text in (
                ("system_header", system_header),
                ("decision_format", decision_format),
                ("closing_reminder", closing_reminder),
            )
        )

        # Extract conscience_guidance from processing_context for retry format enforcement
        conscience_guidance_block = self._build_conscience_guidance_block(processing_context)

        return format_system_prompt_blocks(
            identity_block,
            "",
            system_snapshot_block,
            user_profiles_block,
            None,
            system_guidance + conscience_guidance_block,
        )

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
