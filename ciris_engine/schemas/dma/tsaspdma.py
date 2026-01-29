"""
Tool-Specific Action Selection PDMA (TSASPDMA) schemas.

TSASPDMA provides a "second look" after ASPDMA selects a TOOL action,
giving the agent full tool documentation before execution.

It returns the same ActionSelectionDMAResult as ASPDMA, allowing it to:
- Confirm TOOL action (with optionally refined parameters)
- Switch to SPEAK for user clarification
- Switch to PONDER to reconsider (maybe a different tool is better)
"""

from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
    from ciris_engine.schemas.adapters.tools import ToolInfo


class TSASPDMAInputs(BaseModel):
    """Inputs for TSASPDMA evaluation.

    TSASPDMA is invoked AFTER ASPDMA selects a TOOL action.
    It receives full tool documentation to make an informed decision.
    """

    # Tool information from ASPDMA selection
    tool_name: str = Field(..., description="Name of the tool selected by ASPDMA")
    tool_parameters: JSONDict = Field(..., description="Parameters ASPDMA selected for the tool")
    aspdma_rationale: str = Field(..., description="ASPDMA's rationale for selecting this tool")

    # Full tool metadata with documentation
    tool_info: Any = Field(..., description="Full ToolInfo with documentation, gotchas, examples")

    # Original thought context
    original_thought: Any = Field(..., description="The ProcessingQueueItem being processed")

    # Optional additional context
    context: Optional[Any] = Field(None, description="Additional processing context if available")

    model_config = ConfigDict(extra="forbid")


# NOTE: TSASPDMA OUTPUT is ActionSelectionDMAResult (same as ASPDMA!)
#
# This design choice means TSASPDMA is a transparent "second opinion" that can:
# - Confirm with TOOL action (same or refined parameters)
# - Switch to SPEAK ("I need the user to answer [question]")
# - Switch to PONDER (reconsider the approach, maybe different tool)
#
# The thought processor simply replaces the ASPDMA result with TSASPDMA result.
# No special handling needed - it's the same action types.


__all__ = ["TSASPDMAInputs"]
