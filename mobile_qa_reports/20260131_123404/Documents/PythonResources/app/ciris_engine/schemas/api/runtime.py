"""
Runtime API response schemas - fully typed replacements for Dict[str, Any].
"""

from typing import Optional

from pydantic import BaseModel, Field


class StateTransitionResult(BaseModel):
    """Result of state transition request."""

    success: bool = Field(..., description="Whether transition succeeded")
    target_state: str = Field(..., description="Requested target state")
    current_state: str = Field(..., description="Current state after request")
    reason: str = Field(..., description="Reason for transition")
    transition_time_ms: Optional[float] = Field(None, description="Time taken for transition")


class ProcessingSpeedResult(BaseModel):
    """Result of processing speed change."""

    success: bool = Field(..., description="Whether speed change succeeded")
    multiplier: float = Field(..., description="New speed multiplier")
    description: str = Field(..., description="Human-readable description")
    effective_immediately: bool = Field(True, description="Whether change is immediate")
