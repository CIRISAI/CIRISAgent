"""
Conscience Check Context Schema.

Provides typed context for conscience check operations, replacing Dict[str, Any].
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConscienceCheckContext(BaseModel):
    """Context for conscience check operations.

    This schema replaces Dict[str, Any] context parameters in conscience checks,
    providing type safety while maintaining flexibility for additional context data.
    """

    # Core context - thought being evaluated
    thought: Any = Field(..., description="Thought being evaluated (Thought object)")

    # Optional context fields
    task: Optional[Any] = Field(None, description="Associated task if available (Task object)")
    round_number: Optional[int] = Field(None, description="Current processing round number")
    system_snapshot: Optional[Any] = Field(None, description="System state snapshot (SystemSnapshot object)")

    # Upstream DMA outputs that every conscience should be able to read when
    # forming its judgment. These are populated from the DMA chain BEFORE
    # conscience execution — they are inputs to the conscience layer, not
    # outputs of it.
    #
    # idma_result gives the conscience the fragility / source-diversity /
    # k_eff picture IDMA built for this thought (phase, collapse_margin,
    # correlation_risk, etc.). A conscience can cross-reference its own
    # judgment against IDMA's epistemic state — e.g. a high-coherence answer
    # on a thought IDMA flagged as fragile (collapse_margin ≤ 0) warrants
    # extra scrutiny even when no single shard would have fired on its own.
    idma_result: Optional[Any] = Field(
        None, description="IDMAResult from the reasoning stack (fragility / k_eff / phase)"
    )

    # Additional context can be added via extra fields
    model_config = ConfigDict(
        extra="allow",  # Allow additional context fields
        arbitrary_types_allowed=True,  # Allow runtime objects
    )


__all__ = ["ConscienceCheckContext"]
