"""
Tool-Specific Action Selection PDMA (TSASPDMA) protocol.

TSASPDMA is activated ONLY when ASPDMA selects a TOOL action.
It provides full tool documentation and allows the agent to:
- Proceed with tool execution (TOOL action with parameters)
- Ask for user clarification (SPEAK action)
- Reconsider the approach (PONDER action)
"""

from typing import TYPE_CHECKING, Any, Dict, Optional, Protocol

if TYPE_CHECKING:
    from ciris_engine.schemas.adapters.tools import ToolInfo
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult


class TSASPDMAProtocol(Protocol):
    """Protocol for Tool-Specific Action Selection PDMA.

    TSASPDMA evaluates a TOOL action with full documentation,
    returning the same ActionSelectionDMAResult type as ASPDMA.

    This allows TSASPDMA to:
    - Confirm TOOL action (with parameters reasoned/inferred from context)
    - Switch to SPEAK for user clarification
    - Switch to PONDER to reconsider the approach

    Note: TSASPDMA reasons about and infers appropriate tool parameters from
    context using the tool's schema and documentation. ASPDMA only provides
    tool_name; parameters are determined by TSASPDMA.
    """

    async def evaluate_tool_action(
        self,
        tool_name: str,
        tool_info: "ToolInfo",
        aspdma_rationale: str,
        original_thought: Any,
        context: Optional[Any] = None,
    ) -> "ActionSelectionDMAResult":
        """Evaluate a TOOL action with full documentation.

        Args:
            tool_name: Name of the tool selected by ASPDMA
            tool_info: Full ToolInfo with documentation, examples, gotchas
            aspdma_rationale: ASPDMA's reasoning for selecting this tool
            original_thought: The ProcessingQueueItem being processed
            context: Optional additional processing context

        Returns:
            ActionSelectionDMAResult with one of:
            - TOOL: Proceed with execution (parameters inferred from context)
            - SPEAK: Ask user for clarification ("I need the user to answer...")
            - PONDER: Reconsider the approach (different tool may be better)
        """
        ...


__all__ = ["TSASPDMAProtocol"]
