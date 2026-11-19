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
    from ciris_engine.logic.prompt_assembly import AssemblyCall
    from ciris_engine.logic.prompt_assembly.segmenting import PromptBuilder, Segments
    from ciris_engine.schemas.context.prompt_provenance import PromptManifest
    from ciris_engine.schemas.runtime.models import VerifiedSender
    from ciris_engine.schemas.dma.prompts import PromptCollection

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.logic.dma.conscience_feedback import ConscienceFeedback
from ciris_engine.logic.prompt_assembly import prompt_manifest_scope
from ciris_engine.logic.prompt_assembly.assembler import LayoutItem
from ciris_engine.schemas.dma.sent_prompts import PromptCarrier, carry_sent_prompts, sent_prompts_of
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
from .prompt_loader import DMAPromptLoader, get_prompt_loader, safe_format
from ciris_engine.logic.utils.localization import in_thought_language


class TSASPDMALLMResult(PromptCarrier):
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

        logger.info(f"TSASPDMAEvaluator initialized with model: {self.model_name}")

    @property
    def prompt_loader(self) -> DMAPromptLoader:
        """Get prompt loader for the thread's currently-active language."""
        return get_prompt_loader(language=self.thought_language)

    @property
    def prompt_template_data(self) -> "PromptCollection":
        """Load prompt template fresh each time to respect language changes."""
        return self.prompt_loader.load_prompt_template(self._prompt_template_name)

    @staticmethod
    def _agent_identity(context: Optional[Any]) -> Any:
        """The agent's identity, approved amendments included, from the thought's context."""
        from ciris_engine.logic.formatters.identity import agent_identity_of

        return agent_identity_of(context)

    @staticmethod
    def _sender(context: Optional[Any], original_thought: Optional[Any] = None) -> Optional["VerifiedSender"]:
        """The verified sender, rendered beside the identity block (#1366 item 5).

        TSASPDMA re-decides the tool call, including who it is for. In sh-un-08
        it called an OBSERVER "a designated Wise Authority" (the ``wa-`` id
        prefix) and once filed under the authorized person's id: it had only
        the ``@display (ID: …)`` line. The sender is the thought's own (a
        coalesced message's) when it has one, else the task creator's.
        """
        from ciris_engine.logic.formatters.verified_sender import verified_sender_of

        return verified_sender_of(original_thought, context)

    def _assembly_call(
        self, original_thought: Optional[Any], context: Optional[Any], agent_identity: Any, retry: bool
    ) -> "AssemblyCall":
        """The manifest's call facts, from trusted state only (the verified grant, verified amendments)."""
        from ciris_engine.logic.formatters.wa_approval import wa_authorization_of
        from ciris_engine.logic.prompt_assembly import AssemblyCall
        from ciris_engine.logic.prompt_assembly.segmenting import policy_facts
        from ciris_engine.schemas.context.prompt_provenance import ManifestThoughtKind

        authorization = wa_authorization_of(context)
        depth = getattr(original_thought, "thought_depth", 0)
        kind = (
            ManifestThoughtKind.GUIDANCE
            if authorization is not None
            else ManifestThoughtKind.FOLLOWUP if isinstance(depth, int) and depth > 0 else ManifestThoughtKind.SEED
        )
        task_id = getattr(original_thought, "source_task_id", None)
        thought_id = getattr(original_thought, "thought_id", None)
        return AssemblyCall(
            task_id=task_id if isinstance(task_id, str) else None,
            thought_id=thought_id if isinstance(thought_id, str) else None,
            thought_kind=kind,
            retry_index=1 if retry else 0,
            response_model=TSASPDMALLMResult.__name__,
            facts=policy_facts(authorization, agent_identity, id_scoped=False),
            language=self.prompt_loader.language,
        )

    def _system_segments(
        self, system_message: Any, agent_identity: Any, sender: Optional["VerifiedSender"], prefix: str
    ) -> "Segments":
        """The system message: identity (+ amendments), the VERIFIED SENDER block, the stage's own instruction.

        The bytes of ``format_system_prompt_blocks(identity + sender, "", "", "", None, system_message)``.
        ``system_message`` is the instruction's text (one segment) or its segments, joined with no glue (the
        instruction split around its pipeline-position segment, #1366 item 12).
        """
        from ciris_engine.logic.prompt_assembly.segmenting import (
            identity_segments,
            items,
            segment,
            sender_block_segments,
            stripped_ends,
        )
        from ciris_engine.schemas.context.prompt_provenance import SegmentKind

        language = self.prompt_loader.language
        segs, _ = identity_segments(agent_identity, language)
        parts = [segs]
        if sender is not None:
            parts.append(sender_block_segments(sender, include_display_name=True, language=language)[0])
        if isinstance(system_message, str):
            parts.append([segment(f"{prefix}:system", SegmentKind.STAGE_INSTRUCTION, system_message)])
        else:
            parts.append(list(system_message))
        segments: List[Any] = []
        layout: List[Any] = []
        for block in parts:
            block = [s for s in block if s.text or s.kind == SegmentKind.SENDER_IDENTITY]
            if not block:
                continue
            glue = "\n" if block[0].kind == SegmentKind.SENDER_IDENTITY else ""
            segments.extend(block)
            layout.extend(items(block, glue, "\n\n"))
        segments = stripped_ends(segments)
        kept = {s.segment_id for s in segments}
        return segments, [i for i in layout if i.segment_id in kept]

    def _preamble(self, builder: "PromptBuilder") -> None:
        """Accord (localized, single language), language guidance, crisis resources: one system message each."""
        from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block
        from ciris_engine.logic.prompt_assembly.segmenting import segment
        from ciris_engine.logic.utils.localization import get_language_guidance
        from ciris_engine.schemas.context.prompt_provenance import SegmentKind

        language = self.prompt_loader.language
        # TSASPDMA uses localized accord (single language) for clearer action selection guidance
        builder.single("system", segment("accord", SegmentKind.ACCORD, get_localized_accord_text(language) or ""))
        # Per-language guidance — empty for most languages, populated for locales where systematic terminology
        # gaps were observed (am as of 2.7.6).
        builder.single("system", segment("instr:language", SegmentKind.STAGE_INSTRUCTION, get_language_guidance(language) or ""))
        # Crisis resources ride directly after language guidance (#1248).
        builder.single(
            "system", segment("instr:crisis", SegmentKind.STAGE_INSTRUCTION, get_crisis_resources_system_block(language) or "")
        )

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
        agent_identity: Any = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
        sender: Optional["VerifiedSender"] = None,
    ) -> List[JSONDict]:
        """The TSASPDMA messages alone (the composition seam); see :meth:`_compose_tsaspdma`."""
        messages, _ = self._compose_tsaspdma(
            tool_name,
            tool_info,
            aspdma_reasoning,
            original_thought_content,
            context_enrichment=context_enrichment,
            agent_identity=agent_identity,
            conscience_feedback=conscience_feedback,
            sender=sender,
        )
        return messages

    def _compose_tsaspdma(
        self,
        tool_name: str,
        tool_info: ToolInfo,
        aspdma_reasoning: str,
        original_thought_content: str,
        context_enrichment: Optional[Dict[str, Any]] = None,
        agent_identity: Any = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
        sender: Optional["VerifiedSender"] = None,
        original_thought: Optional[Any] = None,
        context: Optional[Any] = None,
    ) -> "tuple[List[JSONDict], PromptManifest]":
        """Assemble TSASPDMA's prompt from typed segments (PromptAssembler, FSD/PROMPT_CONTEXT_PROVENANCE.md §6).

        NOTE: Parameters are NOT passed from ASPDMA - TSASPDMA extracts them
        from the original_thought_content which contains the user's request.

        Args:
            context_enrichment: Pre-run tool results (e.g., ha_list_entities)
                               containing available resources for parameter selection.
        """
        from ciris_engine.logic.dma.conscience_feedback import conscience_feedback_segment
        from ciris_engine.logic.prompt_assembly.segmenting import PromptBuilder, segment, split_template
        from ciris_engine.schemas.context.prompt_provenance import PromptStage, SegmentKind, SegmentSource

        builder = PromptBuilder()
        self._preamble(builder)

        # The agent's identity, approved amendments included: the same block every DMA reads
        # (formatters.identity.identity_block_of). Eric, 2026-11-13. The verified sender beside it (#1366 item 5).
        # The pipeline position is its own segment, from the engine template's field (#1366 item 12).
        instruction, _ = split_template(
            lambda **values: self.prompt_loader.get_system_message(self.prompt_template_data, **values),
            self._position_slot(),
            prefix="instr:system",
            plain={"tool_name": tool_name},
            locale=self.served_locale,
        )
        builder.message("system", *self._system_segments(instruction, agent_identity, sender, "instr"))

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

        # The user message from its template. NOTE: No tool_parameters - TSASPDMA extracts them from the
        # original thought.
        depth = getattr(original_thought, "thought_depth", 0)
        follow_up = isinstance(depth, int) and depth > 0
        slots = {
            "aspdma_reasoning": segment("aspdma_reasoning", SegmentKind.DMA_OUTPUT, aspdma_reasoning, SegmentSource.LLM_OUTPUT),
            "original_thought_content": segment(
                "request",
                SegmentKind.REQUEST,
                original_thought_content,
                SegmentSource.LLM_OUTPUT if follow_up else SegmentSource.USER_INPUT,
            ),
            "tool_documentation": segment(
                "instr:tool_documentation", SegmentKind.STAGE_INSTRUCTION, tool_documentation, SegmentSource.ADAPTER_METADATA
            ),
        }
        plain = {"tool_name": tool_name}
        if context_enrichment_section:
            slots["context_enrichment_section"] = segment(
                "tool_output", SegmentKind.TOOL_OUTPUT, context_enrichment_section, SegmentSource.TOOL_OUTPUT
            )
        else:
            plain["context_enrichment_section"] = ""
        user_segments, user_items = split_template(
            lambda **values: self.prompt_loader.get_user_message(self.prompt_template_data, **values),
            slots,
            prefix="instr:user",
            plain=plain,
            locale=self.served_locale,
        )
        # On a conscience retry, the veto ASPDMA saw (#1366 item 1): without it
        # this pass re-proposed the vetoed call (0 of 162 retries carried it).
        feedback = conscience_feedback_segment(conscience_feedback)
        if feedback is not None:
            user_segments.append(feedback)
            user_items.append(LayoutItem(segment_id=feedback.segment_id))
        builder.message("user", user_segments, user_items)

        return builder.assemble(
            PromptStage.TSASPDMA,
            self._assembly_call(original_thought, context, agent_identity, retry=feedback is not None),
        )

    @in_thought_language("original_thought", "context")
    async def evaluate_tool_action(
        self,
        tool_name: str,
        tool_info: ToolInfo,
        aspdma_reasoning: str,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
        context_enrichment: Optional[Dict[str, Any]] = None,
        conscience_feedback: Optional[ConscienceFeedback] = None,
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

        # Access the text content directly from ThoughtContent, not str() which gives repr
        thought_content_str = (
            original_thought.content.text
            if hasattr(original_thought.content, "text")
            else str(original_thought.content)
        )
        logger.info(f"[TSASPDMA] Original thought: {thought_content_str[:100]}...")

        agent_identity = self._agent_identity(context)
        messages, manifest = self._compose_tsaspdma(
            tool_name=tool_name,
            tool_info=tool_info,
            aspdma_reasoning=aspdma_reasoning,
            original_thought_content=thought_content_str,
            context_enrichment=context_enrichment,
            agent_identity=agent_identity,
            sender=self._sender(context, original_thought),
            conscience_feedback=conscience_feedback,
            original_thought=original_thought,
            context=context,
        )

        # Store user prompt for debugging
        user_messages = [m for m in messages if m.get("role") == "user"]
        content = user_messages[-1]["content"] if user_messages else None

        logger.debug(
            "TSASPDMA evaluating tool action for thought %s: tool=%s",
            original_thought.thought_id,
            tool_name,
        )

        try:
            # Use Gemini-compatible flat schema (no Union types)
            with prompt_manifest_scope(manifest):
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
                )

            logger.info(
                f"TSASPDMA evaluation for thought {original_thought.thought_id}: "
                f"action={tsaspdma_result.selected_action}"
            )
            # This call's prompts, carried by its result (schemas/dma/sent_prompts.py).
            return carry_sent_prompts(llm_result, tsaspdma_result)

        except Exception as e:
            logger.error(
                f"TSASPDMA evaluation failed for thought {original_thought.thought_id}: {e}",
                exc_info=True,
            )
            # NO FALLBACK - re-raise to trigger proper deferral/ponder behavior
            raise

    @in_thought_language("original_thought", "context")
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

        thought_content_str = (
            original_thought.content.text
            if hasattr(original_thought.content, "text")
            else str(original_thought.content)
        )

        # Format available tools list for prompt
        tools_list_text = self._format_available_tools_for_correction(available_tools)

        agent_identity = self._agent_identity(context)
        messages, manifest = self._compose_correction_mode(
            requested_tool=requested_tool_name,
            available_tools_list=tools_list_text,
            aspdma_reasoning=aspdma_reasoning,
            original_thought_content=thought_content_str,
            agent_identity=agent_identity,
            sender=self._sender(context, original_thought),
            original_thought=original_thought,
            context=context,
        )

        logger.info(
            f"TSASPDMA-CORRECTION: Evaluating correction for '{requested_tool_name}' "
            f"with {len(available_tools)} available tools"
        )

        try:
            with prompt_manifest_scope(manifest):
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
            return carry_sent_prompts(llm_result, tsaspdma_result)

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
        agent_identity: Any = None,
        sender: Optional["VerifiedSender"] = None,
    ) -> List[JSONDict]:
        """The correction-mode messages alone (the composition seam); see :meth:`_compose_correction_mode`."""
        messages, _ = self._compose_correction_mode(
            requested_tool, available_tools_list, aspdma_reasoning, original_thought_content, agent_identity, sender
        )
        return messages

    def _compose_correction_mode(
        self,
        requested_tool: str,
        available_tools_list: str,
        aspdma_reasoning: str,
        original_thought_content: str,
        agent_identity: Any = None,
        sender: Optional["VerifiedSender"] = None,
        original_thought: Optional[Any] = None,
        context: Optional[Any] = None,
    ) -> "tuple[List[JSONDict], PromptManifest]":
        """Assemble TSASPDMA's correction-mode prompt from typed segments (PromptAssembler).

        The requested tool name is ASPDMA's output (a name that does not exist), so wherever it is interpolated it
        is a ``dma_output`` segment, never instruction text.
        """
        from ciris_engine.logic.prompt_assembly.segmenting import PromptBuilder, segment, split_template
        from ciris_engine.schemas.context.prompt_provenance import PromptStage, SegmentKind, SegmentSource

        builder = PromptBuilder()
        self._preamble(builder)

        # System message for correction mode: identity, the verified sender, the stage's instruction.
        def requested(n: int) -> Any:
            return segment(f"requested_tool:{n}", SegmentKind.DMA_OUTPUT, requested_tool, SegmentSource.LLM_OUTPUT)

        system_segments, system_items = split_template(
            lambda **values: self.prompt_loader.get_system_message(self.prompt_template_data, **values),
            {"tool_name": requested(0), **self._position_slot()},
            prefix="instr:system",
            locale=self.served_locale,
        )
        segs, its = self._identity_and_sender(agent_identity, sender)
        if segs:
            system_items = its + [system_items[0].model_copy(update={"glue": "\n\n"})] + system_items[1:]
            system_segments = segs + system_segments
        builder.message("system", system_segments, system_items)

        # Get the correction section template (stored in custom_prompts by loader)
        correction_template = self.prompt_template_data.get_prompt("tool_correction_section") or ""
        # `safe_format`, not bare `.format()` — #997. Byte-identical by
        # construction (`safe_format` returns `template.format(**kwargs)`); what
        # it adds is the composer's own provenance tag, which is the seam the
        # compose dump splits blocks on. Without it these 899 B of LOCALIZED
        # correction doctrine are indistinguishable from the English f-string
        # scaffold around them, and the whole user message reports as one
        # unmeasurable `mixed` block.
        def correction_section(**values: str) -> str:
            return safe_format(
                correction_template,
                source=f"tsaspdma.tool_correction_section[{self.prompt_loader.language}]",
                **values,
            )

        # User message with correction context
        def user_message(**values: str) -> str:
            return f"""=== TOOL CORRECTION MODE ===

ASPDMA selected tool '{values["requested_tool"]}' but this tool does NOT exist.

{values["correction_section"]}

=== ASPDMA'S ORIGINAL SELECTION ===
Tool: {values["requested_tool"]}
Rationale: {values["aspdma_reasoning"]}

=== ORIGINAL THOUGHT (user's intent) ===
{values["original_thought_content"]}

=== YOUR TASK ===
1. Find the correct tool from the available list that matches the user's intent
2. If found: Return TOOL with "tool_name" set to the EXACT name and appropriate "tool_parameters"
3. If unclear: Return SPEAK to ask for clarification
4. If no match: Return PONDER to reconsider

Return your response as a FLAT JSON object."""

        depth = getattr(original_thought, "thought_depth", 0)
        follow_up = isinstance(depth, int) and depth > 0
        section_segments, _ = split_template(
            correction_section,
            {
                "requested_tool": requested(1),
                "available_tools_list": segment(
                    "instr:available_tools", SegmentKind.STAGE_INSTRUCTION, available_tools_list, SegmentSource.ADAPTER_METADATA
                ),
            },
            prefix="instr:correction",
            locale=self.served_locale,
        )
        section = "".join(s.text for s in section_segments)
        user_segments, user_items = split_template(
            user_message,
            {
                "requested_tool": requested(2),
                "aspdma_reasoning": segment("aspdma_reasoning", SegmentKind.DMA_OUTPUT, aspdma_reasoning, SegmentSource.LLM_OUTPUT),
                "original_thought_content": segment(
                    "request",
                    SegmentKind.REQUEST,
                    original_thought_content,
                    SegmentSource.LLM_OUTPUT if follow_up else SegmentSource.USER_INPUT,
                ),
                "correction_section": segment("instr:correction_section", SegmentKind.STAGE_INSTRUCTION, section),
            },
            prefix="instr:user",
            locale="en",  # an English f-string in code, whatever the thought language
        )
        # The correction section's own pieces replace its placeholder segment, in place.
        at = next(i for i, s in enumerate(user_segments) if s.segment_id == "instr:correction_section")
        user_segments[at : at + 1] = section_segments
        user_items[at : at + 1] = [
            LayoutItem(segment_id=s.segment_id, glue="") for s in section_segments
        ]
        builder.message("user", user_segments, user_items)

        return builder.assemble(
            PromptStage.TSASPDMA, self._assembly_call(original_thought, context, agent_identity, retry=False)
        )

    def _position_slot(self) -> Dict[str, Any]:
        """The engine template's pipeline-position paragraph as its own segment (#1366 item 12), as a slot."""
        from ciris_engine.logic.prompt_assembly.segmenting import pipeline_position_slot

        return pipeline_position_slot(self.prompt_loader.pipeline_position(self._prompt_template_name))

    def _identity_and_sender(self, agent_identity: Any, sender: Optional["VerifiedSender"]) -> "Segments":
        """Identity (+ amendments) then the VERIFIED SENDER block, joined by a blank line ("" when neither)."""
        from ciris_engine.logic.prompt_assembly.segmenting import identity_segments, items, sender_block_segments

        language = self.prompt_loader.language
        segments, layout = identity_segments(agent_identity, language)
        if sender is not None:
            s_segs, s_items = sender_block_segments(sender, include_display_name=True, language=language)
            if not segments:
                s_items = [s_items[0].model_copy(update={"glue": ""})] + s_items[1:]
            segments = segments + s_segs
            layout = layout + s_items
        return segments, layout

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
            conscience_feedback=kwargs.get("conscience_feedback"),
        )

    def __repr__(self) -> str:
        return f"<TSASPDMAEvaluator model='{self.model_name}'>"
