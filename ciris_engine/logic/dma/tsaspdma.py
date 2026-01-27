"""Tool-Specific Action Selection PDMA (TSASPDMA) Evaluator.

TSASPDMA is activated ONLY when ASPDMA selects a TOOL action.
It provides full tool documentation and allows the agent to:
- Proceed with TOOL execution (optionally with refined parameters)
- Switch to SPEAK for user clarification ("I need the user to answer...")
- Switch to PONDER to reconsider (maybe a different tool is better)

TSASPDMA returns ActionSelectionDMAResult (same as ASPDMA) for transparent integration.
"""

import logging
from typing import Any, Dict, List, Optional

from ciris_engine.logic.formatters import format_system_prompt_blocks
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.utils import COVENANT_TEXT
from ciris_engine.protocols.dma.tsaspdma import TSASPDMAProtocol
from ciris_engine.schemas.adapters.tools import ToolDocumentation, ToolInfo
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.types import JSONDict

from .base_dma import BaseDMA
from .prompt_loader import get_prompt_loader

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

        # Load prompts from YAML file
        self.prompt_loader = get_prompt_loader()
        self.prompt_template_data = self.prompt_loader.load_prompt_template("tsaspdma")

        # Store last user prompt for debugging/streaming
        self.last_user_prompt: Optional[str] = None

        logger.info(f"TSASPDMAEvaluator initialized with model: {self.model_name}")

    def _format_tool_documentation(self, tool_info: ToolInfo) -> str:
        """Format tool documentation for the prompt."""
        sections = []

        sections.append(f"**Tool:** {tool_info.name}")
        sections.append(f"**Description:** {tool_info.description}")

        if tool_info.when_to_use:
            sections.append(f"**When to Use:** {tool_info.when_to_use}")

        doc = tool_info.documentation
        if doc:
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

        # DMA guidance
        guidance = tool_info.dma_guidance
        if guidance:
            sections.append("\n### DMA Guidance")
            if guidance.when_not_to_use:
                sections.append(f"**When NOT to use:** {guidance.when_not_to_use}")
            if guidance.ethical_considerations:
                sections.append(f"**Ethical considerations:** {guidance.ethical_considerations}")
            if guidance.prerequisite_actions:
                sections.append(f"**Prerequisites:** {', '.join(guidance.prerequisite_actions)}")
            if guidance.requires_approval:
                sections.append("**⚠️ Requires wise authority approval**")

        return "\n".join(sections)

    def _create_tsaspdma_messages(
        self,
        tool_name: str,
        tool_info: ToolInfo,
        tool_parameters: JSONDict,
        aspdma_rationale: str,
        original_thought_content: str,
    ) -> List[JSONDict]:
        """Assemble prompt messages for TSASPDMA evaluation."""
        messages: List[JSONDict] = []

        # Add covenant (always included for DMAs)
        if self.prompt_loader.uses_covenant_header(self.prompt_template_data):
            messages.append({"role": "system", "content": COVENANT_TEXT})

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

        # Get user message from template
        import json

        user_message_text = self.prompt_loader.get_user_message(
            self.prompt_template_data,
            tool_name=tool_name,
            tool_parameters=json.dumps(tool_parameters, indent=2),
            aspdma_rationale=aspdma_rationale,
            original_thought_content=original_thought_content,
            tool_documentation=tool_documentation,
        )

        messages.append({"role": "user", "content": user_message_text})

        return messages

    async def evaluate_tool_action(
        self,
        tool_name: str,
        tool_info: ToolInfo,
        tool_parameters: Dict[str, Any],
        aspdma_rationale: str,
        original_thought: ProcessingQueueItem,
        context: Optional[Any] = None,
    ) -> ActionSelectionDMAResult:
        """Evaluate a TOOL action with full documentation.

        Returns ActionSelectionDMAResult with:
        - TOOL: Proceed with execution (may have refined parameters)
        - SPEAK: Ask user for clarification
        - PONDER: Reconsider the approach
        """
        thought_content_str = str(original_thought.content)

        messages = self._create_tsaspdma_messages(
            tool_name=tool_name,
            tool_info=tool_info,
            tool_parameters=tool_parameters,
            aspdma_rationale=aspdma_rationale,
            original_thought_content=thought_content_str,
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
            result_tuple = await self.call_llm_structured(
                messages=messages,
                response_model=ActionSelectionDMAResult,
                max_tokens=4096,
                temperature=0.0,
                thought_id=original_thought.thought_id,
                task_id=original_thought.source_task_id,
            )
            tsaspdma_result: ActionSelectionDMAResult = result_tuple[0]

            # Prefix rationale with TSASPDMA marker
            if tsaspdma_result.rationale and not tsaspdma_result.rationale.startswith("TSASPDMA:"):
                tsaspdma_result.rationale = f"TSASPDMA: {tsaspdma_result.rationale}"

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

    async def evaluate(self, *args: Any, **kwargs: Any) -> ActionSelectionDMAResult:  # type: ignore[override]
        """Evaluate tool action (generic interface)."""
        # Extract required arguments
        tool_name = kwargs.get("tool_name") or (args[0] if len(args) > 0 else None)
        tool_info = kwargs.get("tool_info") or (args[1] if len(args) > 1 else None)
        tool_parameters = kwargs.get("tool_parameters") or (args[2] if len(args) > 2 else {})
        aspdma_rationale = kwargs.get("aspdma_rationale") or (args[3] if len(args) > 3 else "")
        original_thought = kwargs.get("original_thought") or (args[4] if len(args) > 4 else None)
        context = kwargs.get("context")

        if not tool_name or not tool_info or not original_thought:
            raise ValueError("tool_name, tool_info, and original_thought are required")

        return await self.evaluate_tool_action(
            tool_name=tool_name,
            tool_info=tool_info,
            tool_parameters=tool_parameters,
            aspdma_rationale=aspdma_rationale,
            original_thought=original_thought,
            context=context,
        )

    def __repr__(self) -> str:
        return f"<TSASPDMAEvaluator model='{self.model_name}'>"
