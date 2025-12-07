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

    # Additional context can be added via extra fields
    model_config = ConfigDict(
        extra="allow",  # Allow additional context fields
        arbitrary_types_allowed=True,  # Allow runtime objects
    )


__all__ = ["ConscienceCheckContext"]
