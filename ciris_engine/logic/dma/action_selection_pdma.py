"""Refactored Action Selection PDMA - Modular and Clean."""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union, cast

from ciris_engine.constants import DEFAULT_OPENAI_MODEL_NAME
from ciris_engine.logic.formatters import format_system_prompt_blocks, format_system_snapshot, format_user_profiles
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import COVENANT_TEXT
from ciris_engine.protocols.dma.base import ActionSelectionDMAProtocol
from ciris_engine.protocols.faculties import EpistemicFaculty
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.faculty import ConscienceFailureContext, EnhancedDMAInputs
from ciris_engine.schemas.dma.prompts import PromptCollection
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought

from .action_selection import ActionSelectionContextBuilder, ActionSelectionSpecialCases
from .action_selection.faculty_integration import FacultyIntegration
from .base_dma import BaseDMA

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """{system_header}

{decision_format}

{closing_reminder}"""


class ActionSelectionPDMAEvaluator(BaseDMA, ActionSelectionDMAProtocol):
    """
    Modular Action Selection PDMA Evaluator.

    Takes outputs from Ethical PDMA, CSDMA, and DSDMA and selects a concrete
    handler action using the Principled Decision-Making Algorithm.

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

    async def evaluate(
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
        input_data: Union[Dict[str, Any], EnhancedDMAInputs],
        conscience_failure_context: Union[Dict[str, Any], ConscienceFailureContext],
    ) -> ActionSelectionDMAResult:
        """Perform recursive evaluation using epistemic faculties."""

        if not self.faculty_integration:
            logger.warning(
                "Recursive evaluation requested but no faculties available. Falling back to regular evaluation."
            )
            return await self.evaluate(input_data, enable_recursive_evaluation=False)

        original_thought: Thought = input_data.original_thought
        logger.info(f"Starting recursive evaluation with faculties for thought {original_thought.thought_id}")

        # Convert conscience context to typed model if needed
        if isinstance(conscience_failure_context, dict):
            conscience_failure_context = ConscienceFailureContext(
                failure_reason=conscience_failure_context.get("failure_reason", "Unknown"),
                retry_guidance=conscience_failure_context.get("retry_guidance", ""),
            )

        # Convert input_data to dict for faculty integration if needed
        input_dict = input_data if isinstance(input_data, dict) else input_data.model_dump()

        enhanced_inputs = await self.faculty_integration.enhance_evaluation_with_faculties(
            original_thought=original_thought,
            triaged_inputs=input_dict,
            conscience_failure_context=conscience_failure_context,
        )
        enhanced_inputs.recursive_evaluation = True

        return await self.evaluate(enhanced_inputs, enable_recursive_evaluation=False)

    async def _handle_special_cases(
        self, input_data: Union[Dict[str, Any], EnhancedDMAInputs]
    ) -> Optional[ActionSelectionDMAResult]:
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

    async def _perform_main_evaluation(
        self, input_data: EnhancedDMAInputs, enable_recursive_evaluation: bool
    ) -> ActionSelectionDMAResult:
        """Perform the main LLM-based evaluation."""

        agent_identity = getattr(input_data, "agent_identity", {})
        agent_name = (
            agent_identity.get("agent_name", "CIRISAgent")
            if isinstance(agent_identity, dict)
            else getattr(agent_identity, "agent_name", "CIRISAgent")
        )

        main_user_content = self.context_builder.build_main_user_content(input_data, agent_name)

        # Get faculty evaluations from typed input
        faculty_evaluations = input_data.faculty_evaluations

        if faculty_evaluations and self.faculty_integration:
            faculty_insights = self.faculty_integration.build_faculty_insights_string(faculty_evaluations)
            main_user_content += faculty_insights

        system_message = self._build_system_message(input_data)

        # Get original thought from input_data for follow-up detection
        original_thought = input_data.original_thought

        # Prepend thought type to covenant for rock-solid follow-up detection
        covenant_with_metadata = COVENANT_TEXT
        if original_thought and hasattr(original_thought, "thought_type"):
            covenant_with_metadata = f"THOUGHT_TYPE={original_thought.thought_type.value}\n\n{COVENANT_TEXT}"

        messages = [
            {"role": "system", "content": covenant_with_metadata},
            {"role": "system", "content": system_message},
            {"role": "user", "content": main_user_content},
        ]

        result_tuple = await self.call_llm_structured(
            messages=messages, response_model=ActionSelectionDMAResult, max_tokens=1500, temperature=0.0
        )

        # Extract the result from the tuple and cast to the correct type
        final_result = cast(ActionSelectionDMAResult, result_tuple[0])

        if final_result.selected_action == HandlerActionType.OBSERVE:
            thought_id = input_data.original_thought.thought_id
            logger.warning(f"OBSERVE ACTION: Successfully created for thought {thought_id}")
            logger.warning(f"OBSERVE PARAMS: {final_result.action_parameters}")
            logger.warning(f"OBSERVE RATIONALE: {final_result.rationale}")

        return final_result

    def _build_system_message(self, input_data: EnhancedDMAInputs) -> str:
        """Build the system message for LLM evaluation."""

        processing_context = input_data.processing_context

        system_snapshot_block = ""
        user_profiles_block = ""
        identity_block = ""

        if processing_context:
            system_snapshot = None
            if isinstance(processing_context, dict):
                system_snapshot = processing_context.get("system_snapshot")
                if system_snapshot:
                    user_profiles_block = format_user_profiles(system_snapshot.get("user_profiles"))
                    system_snapshot_block = format_system_snapshot(system_snapshot)
            else:
                # Handle ThoughtContext objects
                if hasattr(processing_context, "system_snapshot") and processing_context.system_snapshot:
                    system_snapshot = processing_context.system_snapshot
                    user_profiles_block = format_user_profiles(
                        getattr(processing_context.system_snapshot, "user_profiles", None)
                    )
                    system_snapshot_block = format_system_snapshot(processing_context.system_snapshot)

            # Extract and validate identity - FAIL FAST if missing
            if system_snapshot:
                if isinstance(system_snapshot, dict):
                    agent_identity = system_snapshot.get("agent_identity")
                else:
                    agent_identity = getattr(system_snapshot, "agent_identity", None)

                if agent_identity:
                    if isinstance(agent_identity, dict):
                        agent_id = agent_identity.get("agent_id")
                        description = agent_identity.get("description")
                        role = agent_identity.get("role")
                    else:
                        agent_id = getattr(agent_identity, "agent_id", None)
                        description = getattr(agent_identity, "description", None)
                        role = getattr(agent_identity, "role", None)

                    # CRITICAL: Identity must be complete - no defaults allowed
                    if not agent_id:
                        raise ValueError(
                            f"CRITICAL: agent_id is missing from identity in ActionSelectionPDMA! This is a fatal error."
                        )
                    if not description:
                        raise ValueError(
                            f"CRITICAL: description is missing from identity in ActionSelectionPDMA! This is a fatal error."
                        )
                    if not role:
                        raise ValueError(
                            f"CRITICAL: role is missing from identity in ActionSelectionPDMA! This is a fatal error."
                        )

                    identity_block = "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===\n"
                    identity_block += f"Agent: {agent_id}\n"
                    identity_block += f"Description: {description}\n"
                    identity_block += f"Role: {role}\n"
                    identity_block += "============================================"
                else:
                    # CRITICAL: No identity found - this is a fatal error
                    raise ValueError(
                        "CRITICAL: No agent identity found in system_snapshot for ActionSelectionPDMA! "
                        "Identity is required for ALL DMA evaluations. This is a fatal error."
                    )
            else:
                # No system snapshot means no identity - FAIL FAST
                raise ValueError(
                    "CRITICAL: No system_snapshot in processing_context for ActionSelectionPDMA! "
                    "Identity is required for ALL DMA evaluations. This is a fatal error."
                )

        # Get prompts based on type
        if isinstance(self.prompts, PromptCollection):
            system_header = self.prompts.system_header or ""
            decision_format = self.prompts.decision_format or ""
            closing_reminder = self.prompts.closing_reminder or ""
        else:
            system_header = self.prompts.get("system_header", "")
            decision_format = self.prompts.get("decision_format", "")
            closing_reminder = self.prompts.get("closing_reminder", "")

        system_guidance = DEFAULT_TEMPLATE.format(
            system_header=system_header,
            decision_format=decision_format,
            closing_reminder=closing_reminder,
        )

        return format_system_prompt_blocks(
            identity_block,
            "",
            system_snapshot_block,
            user_profiles_block,
            None,
            system_guidance,
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
