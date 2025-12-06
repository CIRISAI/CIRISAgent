"""
WiseAuthority context schemas for type-safe WA operations.

Provides context structures for WA interactions.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class GuidanceContext(BaseModel):
    """Context for requesting guidance from Wise Authority."""

    thought_id: str = Field(..., description="ID of the thought requesting guidance")
    task_id: str = Field(..., description="ID of the associated task")
    question: str = Field(..., description="The question or dilemma requiring guidance")
    ethical_considerations: List[str] = Field(default_factory=list, description="Ethical factors to consider")
    domain_context: Dict[str, str] = Field(default_factory=dict, description="Domain-specific context")

    model_config = ConfigDict(extra="forbid")


class DeferralContext(BaseModel):
    """Context for deferral operations."""

    thought_id: str = Field(..., description="ID of the thought being deferred")
    task_id: str = Field(..., description="ID of the associated task")
    reason: str = Field(..., description="Reason for deferral")
    defer_until: Optional[datetime] = Field(None, description="When to reconsider")
    priority: Optional[str] = Field(None, description="Priority level for later consideration")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional deferral metadata")

    model_config = ConfigDict(extra="forbid")


class ApprovalContext(BaseModel):
    """Context for WA approval requests."""

    request_type: str = Field(..., description="Type of approval needed")
    requestor_id: str = Field(..., description="Who is requesting approval")
    subject: str = Field(..., description="What needs approval")
    justification: str = Field(..., description="Why approval is needed")
    urgency: str = Field(default="normal", description="Urgency: low, normal, high, critical")

    # Optional fields for specific contexts
    task_id: Optional[str] = Field(None, description="Associated task")
    thought_id: Optional[str] = Field(None, description="Associated thought")

    # Additional context
    supporting_data: Dict[str, str] = Field(default_factory=dict, description="Supporting information")

    model_config = ConfigDict(extra="forbid")


class WADecision(BaseModel):
    """A decision made by a Wise Authority."""

    decision_id: str = Field(..., description="Unique decision ID")
    wa_id: str = Field(..., description="WA who made the decision")
    decision: str = Field(..., description="The decision: approve, deny, defer")
    reasoning: str = Field(..., description="Explanation for the decision")

    # Context
    request_type: str = Field(..., description="What was being decided")
    request_id: str = Field(..., description="ID of the request")

    # Timestamps
    requested_at: datetime = Field(..., description="When request was made")
    decided_at: datetime = Field(..., description="When decision was made")

    # Conditions or modifications
    conditions: List[str] = Field(default_factory=list, description="Any conditions on approval")
    modifications: Dict[str, str] = Field(default_factory=dict, description="Any modifications to request")

    # Signature
    signature: str = Field(..., description="Digital signature of decision")

    model_config = ConfigDict(extra="forbid")


class WAInteractionLog(BaseModel):
    """Log entry for WA interactions."""

    interaction_id: str = Field(..., description="Unique interaction ID")
    wa_id: str = Field(..., description="WA involved")
    interaction_type: str = Field(..., description="Type: guidance, approval, deferral")

    # Request details
    request_summary: str = Field(..., description="Summary of request")
    request_data: Dict[str, str] = Field(..., description="Request data")

    # Response details
    response_summary: str = Field(..., description="Summary of response")
    response_data: Dict[str, str] = Field(..., description="Response data")

    # Timing
    initiated_at: datetime = Field(..., description="When interaction started")
    completed_at: datetime = Field(..., description="When interaction completed")
    duration_ms: int = Field(..., description="Duration in milliseconds")

    # Context
    agent_id: str = Field(..., description="Agent involved")
    task_id: Optional[str] = Field(None, description="Associated task")
    thought_id: Optional[str] = Field(None, description="Associated thought")

    model_config = ConfigDict(extra="forbid")


__all__ = ["GuidanceContext", "DeferralContext", "ApprovalContext", "WADecision", "WAInteractionLog"]
