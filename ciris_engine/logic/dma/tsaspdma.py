"""Tool-Specific Action Selection PDMA (TSASPDMA) Evaluator.

TSASPDMA is activated ONLY when ASPDMA selects a TOOL action.
It provides full tool documentation and allows the agent to:
- Proceed with TOOL execution (optionally with refined parameters)
- Switch to SPEAK for user clarification ("I need the user to answer...")
- Switch to PONDER to reconsider (maybe a different tool is better)

TSASPDMA returns ActionSelectionDMAResult (same as ASPDMA) for transparent integration.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ciris_engine.schemas.dma.prompts import PromptCollection

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.formatters import format_system_prompt_blocks
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import get_localized_accord_text
from ciris_engine.protocols.dma.tsaspdma import TSASPDMAProtocol
from ciris_engine.schemas.actions.parameters import PonderParams, SpeakParams, ToolParams
from ciris_engine.schemas.adapters.tools import ToolDocumentation, ToolInfo
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import DMAPromptLoader, get_prompt_loader


class TSASPDMALLMResult(BaseModel):
    """Gemini-compatible TSASPDMA LLM output - FLAT structure, NO Union types.

    TSASPDMA returns 3 action types:
    - TOOL: Proceed with execution (parameters in tool_parameters dict, optionally corrected tool_name)
    - SPEAK: Ask user for clarification (speak_content field)
    - PONDER: Reconsider the approach (ponder_questions field)

    In CORRECTION MODE (when ASPDMA selected a non-existent tool):
    - TSASPDMA can return TOOL with a corrected tool_name from the available tools list
    - Or SPEAK/PONDER if no suitable tool exists

    Mirrors ASPDMALLMResult pattern with flat, explicit fields per action type.
    """

    selected_action: HandlerActionType = Field(
        ..., description="Action to take: TOOL (proceed), SPEAK (clarify), or PONDER (reconsider)"
    )
    reasoning: str = Field(..., description="Reasoning for this decision, including any gotchas acknowledged")

    # === TOOL parameters (TSASPDMA refines these) ===
    tool_name: Optional[str] = Field(
        None,
        description="Corrected tool name if different from requested (use in correction mode). "
        "Must be an EXACT name from the available tools list.",
    )
    tool_parameters: Optional[Dict[str, Any]] = Field(
        None, description='Tool parameters dict (e.g., {"entity_id": "light.x", "action": "turn_on"})'
    )

    # === SPEAK parameters ===
    speak_content: Optional[str] = Field(None, description="Clarification question (for SPEAK action)")

    # === PONDER parameters ===
    ponder_questions: Optional[List[str]] = Field(None, description="Questions to reconsider (for PONDER action)")

    model_config = ConfigDict(extra="forbid")


logger = logging.getLogger(__name__)


class TSASPDMAEvaluator(BaseDMA[ProcessingQueueItem, ActionSelectionDMAResult], TSASPDMAProtocol):
    """
    Tool-Specific Action Selection PDMA.

    Reviews a TOOL action with full documentation, returning:
    - TOOL: Proceed with execution (may refine parameters)
    - SPEAK: Ask user for clarification
    - PONDER: Reconsider the approach

    This is a "second look" that catches issues ASPDMA couldn't see
    without full tool documentation.
    """

    def __init__(
        self,
        service_registry: ServiceRegistry,
        model_name: Optional[str] = None,
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
        self._prompt_template_name = "tsaspdma"

        # Store last user prompt for debugging/streaming
        self.last_user_prompt: Optional[str] = None

        # Per-thought language override populated from user_profiles. None
        # falls back to env var. Avoids the legacy global set_prompt_language
        # path which mutated shared state.
        self._explicit_language: Optional[str] = None

        logger.info(f"TSASPDMAEvaluator initialized with model: {self.model_name}")

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""
        return get_prompt_loader(language=self._explicit_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect language changes."""
        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    def _sync_language_from_context(self, context: Optional[Any]) -> None:
        """Sync prompt language using the full localization priority chain.

        Walks thought/task preferred_language → user_profile.preferred_language →
        CIRIS_PREFERRED_LANGUAGE env → "en" via :func:`get_user_language_from_context`.
        Accepts dataclass-style or dict-style contexts.
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
            logger.debug(f"TSASPDMA: Synced prompt language to {new_language}")

    def _convert_tsaspdma_result(
        self,
        llm_result: TSASPDMALLMResult,
        tool_name: str,
    ) -> ActionSelectionDMAResult:
        """Convert flat TSASPDMA LLM result to typed ActionSelectionDMAResult.

        Uses flat fields matching ASPDMALLMResult pattern:
        - TOOL: tool_parameters dict contains the tool arguments, tool_name may be corrected
        - SPEAK: speak_content is the clarification question
        - PONDER: ponder_questions is the list to reconsider

        In correction mode, llm_result.tool_name may contain a corrected tool name
        that should be used instead of the original tool_name parameter.
        """
        action = llm_result.selected_action

        params: ToolParams | SpeakParams | PonderParams

        if action == HandlerActionType.TOOL:
            # Use LLM-provided corrected tool_name if available, otherwise use original
            final_tool_name = llm_result.tool_name if llm_result.tool_name else tool_name
            if llm_result.tool_name and llm_result.tool_name != tool_name:
                logger.info(f"TSASPDMA: Tool name corrected '{tool_name}' -> '{llm_result.tool_name}'")
            params = ToolParams(
                name=final_tool_name,
                parameters=llm_result.tool_parameters or {},
            )
        elif action == HandlerActionType.SPEAK:
            # For SPEAK, use speak_content
            content = llm_result.speak_content or "I need clarification before proceeding."
            params = SpeakParams(content=str(content))
        elif action == HandlerActionType.PONDER:
            # For PONDER, use ponder_questions
            questions = llm_result.ponder_questions or ["Should I reconsider this approach?"]
            if isinstance(questions, str):
                questions = [questions]
            params = PonderParams(questions=questions)
        else:
            # Fallback - TSASPDMA should only return TOOL/SPEAK/PONDER
            logger.warning(f"TSASPDMA returned unexpected action: {action}, falling back to PONDER")
            params = PonderParams(
                questions=[f"TSASPDMA returned unexpected action {action} - what should I do?"],
            )
            action = HandlerActionType.PONDER

        return ActionSelectionDMAResult(
            selected_action=action,
            action_parameters=params,
            rationale=llm_result.reasoning,
        )

    def _format_parameter_schema(self, tool_info: ToolInfo) -> List[str]:
        """Format parameter schema section."""
        if not tool_info.parameters:
            return []
        sections = ["\n### Parameter Schema (FILL THESE IN)"]
        param_schema = tool_info.parameters
        sections.append(f"Type: {param_schema.type}")
        if param_schema.required:
            sections.append(f"Required: {', '.join(param_schema.required)}")
        sections.append("Properties:")
        for prop_name, prop_def in param_schema.properties.items():
            prop_type = prop_def.get("type", "any") if isinstance(prop_def, dict) else "any"
            prop_desc = prop_def.get("description", "") if isinstance(prop_def, dict) else ""
            required_marker = "*" if prop_name in (param_schema.required or []) else ""
            sections.append(f"  - {prop_name}{required_marker} ({prop_type}): {prop_desc}")
        return sections

    def _format_documentation_section(self, doc: ToolDocumentation) -> List[str]:
        """Format tool documentation section."""
        sections: List[str] = []
        if doc.quick_start:
            sections.append(f"\n### Quick Start\n{doc.quick_start}")
        if doc.detailed_instructions:
            sections.append(f"\n### Detailed Instructions\n{doc.detailed_instructions}")
        if doc.examples:
            sections.append("\n### Examples")
            for ex in doc.examples:
                sections.append(f"**{ex.title}**")
                if ex.description:
                    sections.append(ex.description)
                sections.append(f"```{ex.language}\n{ex.code}\n```")
        if doc.gotchas:
            sections.append("\n### Gotchas (Watch Out!)")
            for gotcha in doc.gotchas:
                severity_icon = {"info": "ℹ️", "warning": "⚠️", "error": "🚫"}.get(gotcha.severity, "⚠️")
                sections.append(f"{severity_icon} **{gotcha.title}**: {gotcha.description}")
        return sections

    def _format_dma_guidance(self, guidance: Any) -> List[str]:
        """Format DMA guidance section."""
        sections = ["\n### DMA Guidance"]
        if guidance.when_not_to_use:
            sections.append(f"**When NOT to use:** {guidance.when_not_to_use}")
        if guidance.ethical_considerations:
            sections.append(f"**Ethical considerations:** {guidance.ethical_considerations}")
        if guidance.prerequisite_actions:
            sections.append(f"**Prerequisites:** {', '.join(guidance.prerequisite_actions)}")
        if guidance.requires_approval:
            sections.append("**⚠️ Requires wise authority approval**")
        return sections

    def _format_tool_documentation(self, tool_info: ToolInfo) -> str:
        """Format tool documentation for the prompt including parameter schema."""
        sections = [
            f"**Tool:** {tool_info.name}",
            f"**Description:** {tool_info.description}",
        ]
        if tool_info.when_to_use:
            sections.append(f"**When to Use:** {tool_info.when_to_use}")

        sections.extend(self._format_parameter_schema(tool_info))

        if tool_info.documentation:
            sections.extend(self._format_documentation_section(tool_info.documentation))

        if tool_info.dma_guidance:
            sections.extend(self._format_dma_guidance(tool_info.dma_guidance))

        return "\n".join(sections)

    def _format_context_enrichment(self, context_enrichment: Optional[Dict[str, Any]]) -> str:
        """Format context enrichment data for the prompt.

        Context enrichment contains pre-run tool results like ha_list_entities
        that provide available resources (e.g., entity IDs) for parameter selection.
        """
        if not context_enrichment:
            logger.info("[TSASPDMA] No context enrichment data provided")
            return ""

        logger.info(f"[TSASPDMA] Formatting context enrichment with {len(context_enrichment)} entries")
        logger.info(f"[TSASPDMA] Context enrichment keys: {list(context_enrichment.keys())}")

        sections = []
        for tool_key, result in context_enrichment.items():
            logger.info(f"[TSASPDMA] Processing enrichment: {tool_key} = {type(result)}")
            if not result:
                continue

            # Handle _tool_highlight from _info_only tools
            if isinstance(result, dict) and result.get("_tool_highlight"):
                tool_name = result.get("tool_name", tool_key)
                when_to_use = result.get("when_to_use", "")
                message = result.get("message", "")
                sections.append(f"--- IMPORTANT TOOL AVAILABLE: {tool_name} ---")
                sections.append(f"  ⭐ {message}")
                if when_to_use:
                    sections.append(f"  When to use: {when_to_use}")
                sections.append(f'  tool_name="{tool_name}" - Use this EXACT name!')
                logger.info(f"[TSASPDMA] Added tool highlight for: {tool_name}")
                continue

            # Format based on tool type
            if "ha_list_entities" in tool_key or "home_assistant" in tool_key:
                # Format HA entities specially
                if isinstance(result, dict):
                    entities = result.get("entities", [])
                    if entities:
                        sections.append(f"--- Home Assistant Entities ({len(entities)} shown) ---")
                        for entity in entities[:30]:  # Limit for prompt size
                            entity_id = entity.get("entity_id", "")
                            friendly_name = entity.get("friendly_name", "")
                            state = entity.get("state", "")
                            sections.append(f"  {entity_id}: '{friendly_name}' (state: {state})")
                        if len(entities) > 30:
                            sections.append(f"  ... and {len(entities) - 30} more entities")
            else:
                # Generic formatting for other tools
                sections.append(f"--- {tool_key} ---")
                if isinstance(result, dict):
                    for key, value in list(result.items())[:10]:
                        sections.append(f"  {key}: {value}")
                else:
                    sections.append(f"  {str(result)[:500]}")

        return "\n".join(sections) if sections else ""

    def _create_tsaspdma_messages(
        self,
        tool_name: str,
        tool_info: ToolInfo,
        aspdma_reasoning: str,
        original_thought_content: str,
        context_enrichment: Optional[Dict[str, Any]] = None,
    ) -> List[JSONDict]:
        """Assemble prompt messages for TSASPDMA evaluation.

        NOTE: Parameters are NOT passed from ASPDMA - TSASPDMA extracts them
        from the original_thought_content which contains the user's request.

        Args:
            context_enrichment: Pre-run tool results (e.g., ha_list_entities)
                               containing available resources for parameter selection.
        """
        messages: List[JSONDict] = []

        # TSASPDMA uses localized accord (single language) for clearer action selection guidance
        # Uses the prompt_loader's language which was synced from user context
        accord_text = get_localized_accord_text(self.prompt_loader.language)
        if accord_text:
            messages.append({"role": "system", "content": accord_text})
        # Per-language guidance — empty for most languages, populated for
        # locales where systematic terminology gaps were observed (am as
        # of 2.7.6). See ciris_engine.logic.utils.localization.get_language_guidance.
        from ciris_engine.logic.utils.localization import get_language_guidance
        _lang_guidance = get_language_guidance(self.prompt_loader.language)
        if _lang_guidance:
            messages.append({"role": "system", "content": _lang_guidance})

        # Get system message from prompt template
        system_message = self.prompt_loader.get_system_message(
            self.prompt_template_data,
            tool_name=tool_name,
        )

        # Format with standard blocks (no identity needed for TSASPDMA)
        formatted_system = format_system_prompt_blocks(
            "",  # identity block
            "",  # additional context
            "",  # system snapshot
            "",  # user profiles
            None,
            system_message,
        )
        messages.append({"role": "system", "content": formatted_system})

        # Format tool documentation
        tool_documentation = self._format_tool_documentation(tool_info)

        # Format context enrichment (available entities, etc.)
        context_enrichment_data = self._format_context_enrichment(context_enrichment)
        context_enrichment_section = ""
        if context_enrichment_data:
            context_enrichment_section = (
                f"=== AVAILABLE RESOURCES (from context enrichment) ===\n"
                f"{context_enrichment_data}\n\n"
                f"IMPORTANT: Use the EXACT entity_id values from the list above.\n"
                f"Do NOT use friendly names directly - map them to entity_id first."
            )

        # Get user message from template
        # NOTE: No tool_parameters - TSASPDMA extracts them from original thought
        user_message_text = self.prompt_loader.get_user_message(
            self.prompt_template_data,
            tool_name=tool_name,
            aspdma_reasoning=aspdma_reasoning,
            original_thought_content=original_thought_content,
            tool_documentation=tool_documentation,
            context_enrichment_section=context_enrichment_section,
        )

        messages.append({"role": "user", "content": user_message_text})

        return messages

    async def evaluate_tool_action(
        self,
        tool_name: str,
        tool_info: ToolInfo,
        aspdma_reasoning: str,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
        context_enrichment: Optional[Dict[str, Any]] = None,
    ) -> ActionSelectionDMAResult:
        """Evaluate a TOOL action with full documentation.

        TSASPDMA reasons about and infers appropriate parameters from context
        using the tool's schema, documentation, and examples.
        ASPDMA only provides the tool name, not parameters.

        Args:
            context_enrichment: Pre-run tool results (e.g., ha_list_entities)
                               containing available resources for parameter selection.

        Returns ActionSelectionDMAResult with:
        - TOOL: Proceed with execution (parameters inferred from context)
        - SPEAK: Ask user for clarification
        - PONDER: Reconsider the approach
        """
        logger.info(f"[TSASPDMA] evaluate_tool_action called for tool: {tool_name}")
        logger.info(
            f"[TSASPDMA] Tool info: name={tool_info.name}, when_to_use={tool_info.when_to_use[:50] if tool_info.when_to_use else 'N/A'}..."
        )
        logger.info(
            f"[TSASPDMA] Context enrichment received: {list(context_enrichment.keys()) if context_enrichment else 'None'}"
        )

        # Sync user's language preference before building prompts
        self._sync_language_from_context(context)

        # Access the text content directly from ThoughtContent, not str() which gives repr
        thought_content_str = (
            original_thought.content.text
            if hasattr(original_thought.content, "text")
            else str(original_thought.content)
        )
        logger.info(f"[TSASPDMA] Original thought: {thought_content_str[:100]}...")

        messages = self._create_tsaspdma_messages(
            tool_name=tool_name,
            tool_info=tool_info,
            aspdma_reasoning=aspdma_reasoning,
            original_thought_content=thought_content_str,
            context_enrichment=context_enrichment,
        )

        # Store user prompt for debugging
        user_messages = [m for m in messages if m.get("role") == "user"]
        content = user_messages[-1]["content"] if user_messages else None
        self.last_user_prompt = str(content) if content is not None else None

        logger.debug(
            "TSASPDMA evaluating tool action for thought %s: tool=%s",
            original_thought.thought_id,
            tool_name,
        )

        try:
            # Use Gemini-compatible flat schema (no Union types)
            result_tuple = await self.call_llm_structured(
                messages=messages,
                response_model=TSASPDMALLMResult,
                max_tokens=8192,
                temperature=0.0,
                thought_id=original_thought.thought_id,
                task_id=original_thought.source_task_id,
            )
            llm_result: TSASPDMALLMResult = result_tuple[0]

            # Convert flat LLM result to typed ActionSelectionDMAResult
            tsaspdma_result = self._convert_tsaspdma_result(
                llm_result=llm_result,
                tool_name=tool_name,
            )

            # Prefix rationale with TSASPDMA marker
            if tsaspdma_result.rationale and not tsaspdma_result.rationale.startswith("TSASPDMA:"):
                # Create new instance with updated rationale
                tsaspdma_result = ActionSelectionDMAResult(
                    selected_action=tsaspdma_result.selected_action,
                    action_parameters=tsaspdma_result.action_parameters,
                    rationale=f"TSASPDMA: {tsaspdma_result.rationale}",
                    raw_llm_response=tsaspdma_result.raw_llm_response,
                    reasoning=tsaspdma_result.rationale,
                    evaluation_time_ms=tsaspdma_result.evaluation_time_ms,
                    resource_usage=tsaspdma_result.resource_usage,
                    user_prompt=tsaspdma_result.user_prompt,
                )

            logger.info(
                f"TSASPDMA evaluation for thought {original_thought.thought_id}: "
                f"action={tsaspdma_result.selected_action}"
            )
            return tsaspdma_result

        except Exception as e:
            logger.error(
                f"TSASPDMA evaluation failed for thought {original_thought.thought_id}: {e}",
                exc_info=True,
            )
            # NO FALLBACK - re-raise to trigger proper deferral/ponder behavior
            raise

    async def evaluate_tool_correction(
        self,
        requested_tool_name: str,
        available_tools: List[ToolInfo],
        aspdma_reasoning: str,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
    ) -> ActionSelectionDMAResult:
        """Evaluate tool correction when ASPDMA selected a non-existent tool.

        CORRECTION MODE: ASPDMA hallucinated a tool name that doesn't exist.
        TSASPDMA reviews available tools and either:
        - Corrects to the right tool (returns TOOL with corrected tool_name)
        - Asks for clarification (returns SPEAK)
        - Reconsiders approach (returns PONDER)
        """
        # Sync user's language preference before building prompts
        self._sync_language_from_context(context)

        thought_content_str = (
            original_thought.content.text
            if hasattr(original_thought.content, "text")
            else str(original_thought.content)
        )

        # Format available tools list for prompt
        tools_list_text = self._format_available_tools_for_correction(available_tools)

        messages = self._create_correction_mode_messages(
            requested_tool=requested_tool_name,
            available_tools_list=tools_list_text,
            aspdma_reasoning=aspdma_reasoning,
            original_thought_content=thought_content_str,
        )

        logger.info(
            f"TSASPDMA-CORRECTION: Evaluating correction for '{requested_tool_name}' "
            f"with {len(available_tools)} available tools"
        )

        try:
            result_tuple = await self.call_llm_structured(
                messages=messages,
                response_model=TSASPDMALLMResult,
                max_tokens=8192,
                temperature=0.0,
                thought_id=original_thought.thought_id,
                task_id=original_thought.source_task_id,
            )
            llm_result: TSASPDMALLMResult = result_tuple[0]

            # Validate corrected tool name if TOOL action
            if llm_result.selected_action == HandlerActionType.TOOL and llm_result.tool_name:
                available_names = [t.name for t in available_tools]
                if llm_result.tool_name not in available_names:
                    logger.warning(
                        f"TSASPDMA-CORRECTION: LLM returned invalid tool_name '{llm_result.tool_name}' "
                        f"not in available: {available_names}. Falling back to PONDER."
                    )
                    return ActionSelectionDMAResult(
                        selected_action=HandlerActionType.PONDER,
                        action_parameters=PonderParams(
                            questions=[
                                f"Tool '{requested_tool_name}' doesn't exist and correction failed.",
                                f"Available tools: {', '.join(available_names)}",
                                "What alternative approach should I take?",
                            ]
                        ),
                        rationale="TSASPDMA-CORRECTION: Invalid tool correction - forcing reconsideration",
                    )

            # Convert result, using the corrected tool_name if provided
            tsaspdma_result = self._convert_tsaspdma_result(
                llm_result=llm_result,
                tool_name=llm_result.tool_name or requested_tool_name,
            )

            # Add correction marker to rationale
            if tsaspdma_result.selected_action == HandlerActionType.TOOL and llm_result.tool_name:
                tsaspdma_result = ActionSelectionDMAResult(
                    selected_action=tsaspdma_result.selected_action,
                    action_parameters=tsaspdma_result.action_parameters,
                    rationale=f"TSASPDMA-CORRECTION: Corrected '{requested_tool_name}' -> '{llm_result.tool_name}'. {tsaspdma_result.rationale or ''}",
                )
            elif not tsaspdma_result.rationale.startswith("TSASPDMA"):
                tsaspdma_result = ActionSelectionDMAResult(
                    selected_action=tsaspdma_result.selected_action,
                    action_parameters=tsaspdma_result.action_parameters,
                    rationale=f"TSASPDMA-CORRECTION: {tsaspdma_result.rationale}",
                )

            logger.info(
                f"TSASPDMA-CORRECTION: Result for '{requested_tool_name}': "
                f"action={tsaspdma_result.selected_action}, "
                f"corrected_to={llm_result.tool_name if llm_result.tool_name else 'N/A'}"
            )
            return tsaspdma_result

        except Exception as e:
            logger.error(f"TSASPDMA-CORRECTION: Failed for '{requested_tool_name}': {e}", exc_info=True)
            raise

    def _format_available_tools_for_correction(self, tools: List[ToolInfo]) -> str:
        """Format available tools list for correction mode prompt."""
        lines = []
        for tool in tools:
            line = f"  - {tool.name}: {tool.description}"
            if tool.when_to_use:
                line += f" (Use when: {tool.when_to_use})"
            lines.append(line)
        return "\n".join(lines) if lines else "  (No tools available)"

    def _create_correction_mode_messages(
        self,
        requested_tool: str,
        available_tools_list: str,
        aspdma_reasoning: str,
        original_thought_content: str,
    ) -> List[JSONDict]:
        """Create prompt messages for TSASPDMA correction mode."""
        messages: List[JSONDict] = []

        # TSASPDMA uses localized accord (single language) for clearer action selection guidance
        accord_text = get_localized_accord_text(self.prompt_loader.language)
        if accord_text:
            messages.append({"role": "system", "content": accord_text})
        # Per-language guidance — empty for most languages, populated for
        # locales where systematic terminology gaps were observed (am as
        # of 2.7.6). See ciris_engine.logic.utils.localization.get_language_guidance.
        from ciris_engine.logic.utils.localization import get_language_guidance
        _lang_guidance = get_language_guidance(self.prompt_loader.language)
        if _lang_guidance:
            messages.append({"role": "system", "content": _lang_guidance})

        # System message for correction mode
        system_message = self.prompt_loader.get_system_message(
            self.prompt_template_data,
            tool_name=requested_tool,
        )
        messages.append({"role": "system", "content": system_message})

        # Get the correction section template (stored in custom_prompts by loader)
        correction_template = self.prompt_template_data.get_prompt("tool_correction_section") or ""
        correction_section = correction_template.format(
            requested_tool=requested_tool,
            available_tools_list=available_tools_list,
        )

        # User message with correction context
        user_message = f"""=== TOOL CORRECTION MODE ===

ASPDMA selected tool '{requested_tool}' but this tool does NOT exist.

{correction_section}

=== ASPDMA'S ORIGINAL SELECTION ===
Tool: {requested_tool}
Rationale: {aspdma_reasoning}

=== ORIGINAL THOUGHT (user's intent) ===
{original_thought_content}

=== YOUR TASK ===
1. Find the correct tool from the available list that matches the user's intent
2. If found: Return TOOL with "tool_name" set to the EXACT name and appropriate "tool_parameters"
3. If unclear: Return SPEAK to ask for clarification
4. If no match: Return PONDER to reconsider

Return your response as a FLAT JSON object."""

        messages.append({"role": "user", "content": user_message})
        return messages

    async def evaluate(self, *args: Any, **kwargs: Any) -> ActionSelectionDMAResult:
        """Evaluate tool action (generic interface)."""
        # Extract required arguments
        tool_name = kwargs.get("tool_name") or (args[0] if len(args) > 0 else None)
        tool_info = kwargs.get("tool_info") or (args[1] if len(args) > 1 else None)
        aspdma_reasoning = kwargs.get("aspdma_reasoning") or (args[2] if len(args) > 2 else "")
        original_thought = kwargs.get("original_thought") or (args[3] if len(args) > 3 else None)
        context = kwargs.get("context")

        if not tool_name or not tool_info or not original_thought:
            raise ValueError("tool_name, tool_info, and original_thought are required")

        return await self.evaluate_tool_action(
            tool_name=tool_name,
            tool_info=tool_info,
            aspdma_reasoning=aspdma_reasoning,
            original_thought=original_thought,
            context=context,
        )

    def __repr__(self) -> str:
        return f"<TSASPDMAEvaluator model='{self.model_name}'>"
