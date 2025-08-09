"""Context building utilities for Action Selection PDMA."""

import logging
from typing import Any, Dict, List, Optional, Union

from ciris_engine.logic.formatters import format_system_snapshot, format_user_profiles
from ciris_engine.schemas.dma.faculty import ConscienceFailureContext, EnhancedDMAInputs
from ciris_engine.schemas.dma.prompts import PromptCollection
from ciris_engine.schemas.dma.results import CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought

logger = logging.getLogger(__name__)


class ActionSelectionContextBuilder:
    """Builds context for action selection evaluation."""

    def __init__(
        self,
        prompts: Union[Dict[str, str], PromptCollection],
        service_registry: Optional[Any] = None,
        bus_manager: Optional[Any] = None,
    ):
        self.prompts = prompts
        self.service_registry = service_registry
        self.bus_manager = bus_manager
        self._instruction_generator: Optional[Any] = None

    def build_main_user_content(self, triaged_inputs: EnhancedDMAInputs, agent_name: Optional[str] = None) -> str:
        """Build the main user content for LLM evaluation."""

        logger.info("[CONTEXT] Building main user content for action selection")

        # Extract core components from typed input
        original_thought = triaged_inputs.original_thought
        ethical_pdma_result = triaged_inputs.ethical_pdma_result
        csdma_result = triaged_inputs.csdma_result
        dsdma_result = triaged_inputs.dsdma_result
        current_thought_depth = triaged_inputs.current_thought_depth
        max_rounds = triaged_inputs.max_rounds

        # Build context sections
        permitted_actions = self._get_permitted_actions(triaged_inputs)
        _action_options_str = ", ".join([a.value for a in permitted_actions])

        _available_tools_str = self._get_available_tools_str(permitted_actions)

        # Build DMA summaries
        _ethical_summary = self._build_ethical_summary(ethical_pdma_result)
        _csdma_summary = self._build_csdma_summary(csdma_result)
        _dsdma_summary_str = self._build_dsdma_summary(dsdma_result)

        # Build ponder context
        _ponder_notes_str = self._build_ponder_context(original_thought, current_thought_depth)

        # Build final attempt advisory
        _final_ponder_advisory = self._build_final_attempt_advisory(current_thought_depth, max_rounds, agent_name)

        # Build guidance sections
        _guidance_sections = self._build_guidance_sections(agent_name, permitted_actions)

        # Build system context
        processing_context = triaged_inputs.processing_context
        user_profile_context_str, system_snapshot_context_str = self._build_system_context(processing_context)

        # Log context size details
        if user_profile_context_str:
            logger.info(f"[CONTEXT] User profile context: {len(user_profile_context_str)} chars")
        if system_snapshot_context_str:
            logger.info(f"[CONTEXT] System snapshot context: {len(system_snapshot_context_str)} chars")

        # Build startup guidance
        _startup_guidance = self._build_startup_guidance(original_thought)

        # Build conscience feedback guidance if available
        conscience_feedback = getattr(triaged_inputs, "conscience_feedback", None)
        _conscience_guidance = self._build_conscience_guidance(conscience_feedback)

        # Get reject thought guidance
        _reject_thought_guidance = self._get_reject_thought_guidance()

        # Extract all guidance sections for template formatting
        _action_parameter_schemas = _guidance_sections.get("action_parameter_schemas", "")
        _action_parameters_speak_csdma_guidance = _guidance_sections.get("action_parameters_speak_csdma_guidance", "")
        _action_parameters_ponder_guidance = _guidance_sections.get("action_parameters_ponder_guidance", "")
        _action_parameters_observe_guidance = _guidance_sections.get("action_parameters_observe_guidance", "")
        _rationale_csdma_guidance = _guidance_sections.get("rationale_csdma_guidance", "")

        # Assemble final content
        main_user_content = """
Your task is to determine the single most appropriate HANDLER ACTION based on an original thought and evaluations from three prior DMAs (Ethical PDMA, CSDMA, DSDMA).
You MUST execute the Principled Decision-Making Algorithm (PDMA) to choose this HANDLER ACTION and structure your response as a JSON object matching the provided schema.
All fields specified in the schema for your response are MANDATORY unless explicitly marked as optional.
Permitted Handler Actions: {action_options_str}{available_tools_str}
{startup_guidance}
{conscience_guidance}
{reject_thought_guidance}
{final_ponder_advisory}
{action_parameter_schemas}
Action Selection Instructions:
Based on the DMA results and original thought, select the most appropriate handler action.

Your response MUST be a JSON object with exactly these three keys:
1. 'selected_action': Choose from {action_options_str}
2. 'action_parameters': Parameters matching the schema for your selected_action
    {action_parameters_speak_csdma_guidance}
    {action_parameters_ponder_guidance}
    {action_parameters_observe_guidance}
3. 'rationale': Explain why this action is optimal given the DMA evaluations and CIRIS principles
    {rationale_csdma_guidance}

IMPORTANT: Return ONLY a JSON object with these exact keys: selected_action, action_parameters, rationale.

Original Thought: "{original_thought_content}"
{ponder_notes_str}
{user_profile_context_str}
{system_snapshot_context_str}

DMA Summaries to consider for your PDMA reasoning:
Ethical PDMA: {ethical_summary}
CSDMA: {csdma_summary}
DSDMA: {dsdma_summary_str}

Based on all the provided information and the PDMA framework for action selection, determine the appropriate handler action and structure your response as specified.
Adhere strictly to the schema for your JSON output.
"""
        # Format the template with all the variables
        formatted_content = main_user_content.format(
            action_options_str=_action_options_str,
            available_tools_str=_available_tools_str,
            startup_guidance=_startup_guidance,
            conscience_guidance=_conscience_guidance,
            reject_thought_guidance=_reject_thought_guidance,
            action_parameter_schemas=_action_parameter_schemas,
            action_parameters_speak_csdma_guidance=_action_parameters_speak_csdma_guidance,
            action_parameters_ponder_guidance=_action_parameters_ponder_guidance,
            action_parameters_observe_guidance=_action_parameters_observe_guidance,
            rationale_csdma_guidance=_rationale_csdma_guidance,
            self=self,
            final_ponder_advisory=_final_ponder_advisory,
            guidance_sections=_guidance_sections,
            original_thought=original_thought,
            original_thought_content=original_thought.content,
            ponder_notes_str=_ponder_notes_str,
            user_profile_context_str=user_profile_context_str,
            system_snapshot_context_str=system_snapshot_context_str,
            ethical_summary=_ethical_summary,
            csdma_summary=_csdma_summary,
            dsdma_summary_str=_dsdma_summary_str,
        )
        return formatted_content.strip()

    def _get_permitted_actions(self, triaged_inputs: EnhancedDMAInputs) -> List[HandlerActionType]:
        """Get permitted actions from triaged inputs."""
        default_permitted_actions = [
            HandlerActionType.SPEAK,
            HandlerActionType.PONDER,
            HandlerActionType.REJECT,
            HandlerActionType.DEFER,
            HandlerActionType.MEMORIZE,
            HandlerActionType.RECALL,
            HandlerActionType.FORGET,
            HandlerActionType.OBSERVE,
            HandlerActionType.TOOL,
            HandlerActionType.TASK_COMPLETE,
        ]

        permitted_actions = triaged_inputs.permitted_actions or default_permitted_actions

        if not permitted_actions:
            original_thought = triaged_inputs.original_thought
            logger.warning(
                f"ActionSelectionPDMA: 'permitted_actions' in triaged_inputs is empty for thought {original_thought.thought_id}. Falling back to default."
            )
            permitted_actions = default_permitted_actions

        # Return the permitted actions - they MUST be HandlerActionType enums
        return list(permitted_actions)

    def _get_available_tools_str(self, permitted_actions: List[HandlerActionType]) -> str:
        """Get available tools string if TOOL action is permitted."""
        available_tools_str = ""
        if HandlerActionType.TOOL in permitted_actions:
            try:
                # Get tools from service registry if available
                if self.service_registry:
                    from ciris_engine.schemas.runtime.enums import ServiceType

                    tool_services = self.service_registry.get_services_by_type(ServiceType.TOOL)
                    _all_tools: List[str] = []
                    for service in tool_services:
                        if hasattr(service, "get_available_tools"):
                            # This is an async method, so we need to handle it properly
                            # For now, we'll skip the async call since we're in a sync context
                            # The dynamic instruction generator will handle this better
                            pass
                    # Fall back to empty string if we can't get tools synchronously
            except Exception:
                pass

        return available_tools_str

    def _build_ethical_summary(self, ethical_pdma_result: EthicalDMAResult) -> str:
        """Build ethical DMA summary."""
        conflicts_str = "None"
        resolution_str = "None"
        if isinstance(ethical_pdma_result.alignment_check, dict):
            conflicts_str = str(ethical_pdma_result.alignment_check.get("conflicts", "None"))
            resolution_str = str(ethical_pdma_result.alignment_check.get("resolution", "None"))

        return f"Ethical PDMA Stance: {ethical_pdma_result.decision}. Key Conflicts: {conflicts_str}. Resolution: {resolution_str}."

    def _build_csdma_summary(self, csdma_result: CSDMAResult) -> str:
        """Build CSDMA summary."""
        return f"CSDMA Output: Plausibility {csdma_result.plausibility_score:.2f}, Flags: {', '.join(csdma_result.flags) if csdma_result.flags else 'None'}. Reasoning: {csdma_result.reasoning}"

    def _build_dsdma_summary(self, dsdma_result: Optional[DSDMAResult]) -> str:
        """Build DSDMA summary."""
        if not dsdma_result:
            return "DSDMA did not apply or did not run for this thought."

        return (
            f"DSDMA ({dsdma_result.domain}) Output: Domain Alignment {dsdma_result.domain_alignment:.2f}, "
            f"Flags: {', '.join(dsdma_result.flags) if dsdma_result.flags else 'None'}. "
            f"Reasoning: {dsdma_result.reasoning}"
        )

    def _build_ponder_context(self, original_thought: Thought, current_thought_depth: int) -> str:
        """Build ponder context string."""
        notes_list = original_thought.ponder_notes if original_thought.ponder_notes else []

        if notes_list:
            ponder_notes_str = "\n\nIMPORTANT CONTEXT FROM PREVIOUS ACTION ROUNDS:\n"
            ponder_notes_str += (
                f"This thought has been pondered {current_thought_depth} time(s). PLEASE TRY AND ACT (SPEAK) NOW\n"
            )
            ponder_notes_str += "The following key questions were previously identified:\n"
            for i, q_note in enumerate(notes_list):
                ponder_notes_str += f"{i+1}. {q_note}\n"
            ponder_notes_str += (
                "Please consider these questions and the original thought in your current evaluation. "
                "If you choose to 'Ponder' again, ensure your new 'questions' are DIFFERENT "
                "from the ones listed above and aim to address any REMAINING ambiguities or guide towards a solution.\n"
            )
            return ponder_notes_str
        elif current_thought_depth > 0:
            return f"\n\nThis thought has been pondered {current_thought_depth} time(s) previously. If choosing 'Ponder' again, formulate new, insightful questions.\n"

        return ""

    def _build_final_attempt_advisory(
        self, current_thought_depth: int, max_rounds: int, agent_name: Optional[str]
    ) -> str:
        """Build final attempt advisory."""
        is_final_attempt_round = current_thought_depth >= max_rounds - 1

        if not is_final_attempt_round:
            return ""

        final_ponder_advisory_template = self._get_agent_specific_prompt("final_ponder_advisory", agent_name)
        try:
            return final_ponder_advisory_template.format(
                current_thought_depth_plus_1=current_thought_depth + 1,
                max_rounds=max_rounds,
            )
        except KeyError as e:
            logger.error(
                f"KeyError formatting final_ponder_advisory_template: {e}. Template: '{final_ponder_advisory_template}'"
            )
            return "\nIMPORTANT FINAL ATTEMPT: Attempt to provide a terminal action."

    def _build_guidance_sections(
        self, agent_name: Optional[str], permitted_actions: List[HandlerActionType]
    ) -> Dict[str, str]:
        """Build all guidance sections."""
        return {
            "action_alignment_csdma_guidance": self._get_agent_specific_prompt("csdma_ambiguity_guidance", agent_name),
            "action_alignment_example": self._get_agent_specific_prompt(
                "csdma_ambiguity_alignment_example", agent_name
            ),
            "action_parameters_speak_csdma_guidance": self._get_agent_specific_prompt(
                "action_params_speak_csdma_guidance", agent_name
            ),
            "action_parameters_ponder_guidance": self._get_agent_specific_prompt(
                "action_params_ponder_guidance", agent_name
            ),
            "action_parameters_observe_guidance": self._get_agent_specific_prompt(
                "action_params_observe_guidance", agent_name
            ),
            "rationale_csdma_guidance": self._get_agent_specific_prompt("rationale_csdma_guidance", agent_name),
            "action_parameter_schemas": self._get_dynamic_action_schemas(permitted_actions),
        }

    def _build_system_context(self, processing_context_data: Any) -> tuple[str, str]:
        """Build user profile and system snapshot context."""
        user_profile_context_str = ""
        system_snapshot_context_str = ""

        if processing_context_data:
            if hasattr(processing_context_data, "system_snapshot") and processing_context_data.system_snapshot:
                user_profiles_data = getattr(processing_context_data.system_snapshot, "user_profiles", None)
                user_profile_context_str = format_user_profiles(user_profiles_data)
                system_snapshot_context_str = format_system_snapshot(processing_context_data.system_snapshot)

        return user_profile_context_str, system_snapshot_context_str

    def _build_startup_guidance(self, original_thought: Thought) -> str:
        """Build startup guidance if applicable."""
        if original_thought.thought_type == "startup_meta":
            return (
                "\nCRITICAL STARTUP DIRECTIVE: When handling 'startup_meta' thoughts, "
                "select SPEAK to confirm status or PONDER only if additional internal checks are required. "
                "Avoid MEMORIZE, ACT, REJECT, or DEFER during startup."
            )
        return ""

    def _build_conscience_guidance(
        self, conscience_feedback: Optional[Union[Dict[str, Any], ConscienceFailureContext]]
    ) -> str:
        """Build conscience guidance from feedback if available."""
        if not conscience_feedback:
            return ""

        if isinstance(conscience_feedback, ConscienceFailureContext):
            return f"\n\n**CONSCIENCE OVERRIDE GUIDANCE:**\n{conscience_feedback.retry_guidance}\n"
        elif isinstance(conscience_feedback, dict) and "retry_guidance" in conscience_feedback:
            return f"\n\n**CONSCIENCE OVERRIDE GUIDANCE:**\n{conscience_feedback['retry_guidance']}\n"

        return ""

    def _get_reject_thought_guidance(self) -> str:
        """Get reject thought guidance."""
        return "\nNote on 'Reject Thought': Use this action sparingly, primarily if the original thought is nonsensical, impossible to act upon even with clarification, or fundamentally misaligned with the agent's purpose. Prefer 'Ponder' or 'Speak' for clarification if possible."

    def _get_agent_specific_prompt(self, base_key: str, agent_name: Optional[str]) -> str:
        """Get agent-specific prompt variation, falling back to base key."""
        # Handle both dict and PromptCollection
        if isinstance(self.prompts, PromptCollection):
            prompt = self.prompts.get_prompt(base_key, agent_name)
            if prompt:
                return prompt
        else:
            # Original dict logic
            if agent_name:
                agent_key = f"{agent_name.lower()}_mode_{base_key}"
                if agent_key in self.prompts:
                    return self.prompts[agent_key]

            if base_key in self.prompts:
                return self.prompts[base_key]

        logger.warning(f"Prompt key for '{base_key}' (agent: {agent_name}) not found. Using empty string.")
        return ""

    def _get_dynamic_action_schemas(self, permitted_actions: List[HandlerActionType]) -> str:
        """Get dynamically generated action schemas or fall back to static prompts."""
        try:
            # Lazy initialize the instruction generator
            if self._instruction_generator is None:
                from ciris_engine.logic.dma.action_selection.action_instruction_generator import (
                    ActionInstructionGenerator,
                )

                self._instruction_generator = ActionInstructionGenerator(self.service_registry, self.bus_manager)

            # Generate dynamic instructions
            dynamic_schemas = self._instruction_generator.generate_action_instructions(permitted_actions)

            if dynamic_schemas:
                logger.debug("Using dynamically generated action schemas")
                return dynamic_schemas

        except Exception as e:
            logger.warning(f"Failed to generate dynamic action schemas: {e}")

        # Fall back to static schemas from prompts
        if isinstance(self.prompts, PromptCollection):
            return self.prompts.action_parameter_schemas or ""
        else:
            return self.prompts.get("action_parameter_schemas", "")
