"""
Deferral schemas for CIRIS.

Provides type-safe structures for deferral handling.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class DeferralReason(str, Enum):
    """Standard deferral reason codes."""

    conscience_FAILURE = "conscience_failure"
    MAX_ROUNDS_REACHED = "max_rounds_reached"
    CHANNEL_POLICY_UPDATE = "channel_policy_update"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    ETHICAL_CONCERN = "ethical_concern"
    SYSTEM_ERROR = "system_error"
    WA_REVIEW_REQUIRED = "wa_review_required"
    MEMORY_CONFLICT = "memory_conflict"
    UNKNOWN = "unknown"


class EthicalAssessment(BaseModel):
    """Ethical evaluation results."""

    decision: str = Field(..., description="approve, reject, defer")
    reasoning: str = Field(..., description="Explanation")
    principles_upheld: List[str] = Field(default_factory=list)
    principles_violated: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class CSDMAAssessment(BaseModel):
    """Common sense evaluation results."""

    makes_sense: bool = Field(..., description="Whether action makes sense")
    practicality_score: float = Field(..., ge=0.0, le=1.0)
    flags: List[str] = Field(default_factory=list, description="Common sense flags")
    reasoning: str = Field(..., description="Explanation")

    model_config = ConfigDict(extra="forbid")


class DSDMAAssessment(BaseModel):
    """Domain-specific evaluation results."""

    domain: str = Field(..., description="Domain of expertise")
    alignment_score: float = Field(..., ge=0.0, le=1.0)
    recommendations: List[str] = Field(default_factory=list)
    reasoning: str = Field(..., description="Explanation")

    model_config = ConfigDict(extra="forbid")


class ActionHistoryItem(BaseModel):
    """A single action in history."""

    action_type: str = Field(..., description="Type of action taken")
    timestamp: datetime = Field(..., description="When action occurred")
    parameters: Dict[str, str] = Field(default_factory=dict, description="Action parameters")
    result: Optional[str] = Field(None, description="Action result")

    model_config = ConfigDict(extra="forbid")


class DeferralPackage(BaseModel):
    """Complete context package for deferred decisions."""

    thought_id: str = Field(..., description="ID of deferred thought")
    task_id: str = Field(..., description="ID of associated task")
    deferral_reason: DeferralReason = Field(..., description="Reason code")
    reason_description: str = Field(..., description="Human-readable reason")

    # Core content
    thought_content: str = Field(..., description="The thought being deferred")
    task_description: Optional[str] = Field(None, description="Task description")

    # Assessments (no Dict[str, Any]!)
    ethical_assessment: Optional[EthicalAssessment] = Field(None)
    csdma_assessment: Optional[CSDMAAssessment] = Field(None)
    dsdma_assessment: Optional[DSDMAAssessment] = Field(None)

    # Context
    user_profiles: Dict[str, str] = Field(default_factory=dict, description="User profile data as strings")
    system_snapshot: Dict[str, str] = Field(default_factory=dict, description="System state as strings")

    # History
    ponder_history: List[str] = Field(default_factory=list, description="Previous ponder thoughts")
    action_history: List[ActionHistoryItem] = Field(default_factory=list, description="Actions taken")

    # Metadata
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When package was created"
    )

    model_config = ConfigDict(extra="forbid")


class TransportData(BaseModel):
    """Transport-specific metadata."""

    adapter_type: str = Field(..., description="Type of adapter")
    channel_id: Optional[str] = Field(None, description="Channel identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    message_id: Optional[str] = Field(None, description="Message identifier")
    additional_context: Dict[str, str] = Field(default_factory=dict, description="Additional transport context")

    model_config = ConfigDict(extra="forbid")


class DeferralReport(BaseModel):
    """Deferral report for transmission to WA."""

    report_id: str = Field(..., description="Unique report ID")
    package: DeferralPackage = Field(..., description="Deferral package")
    target_wa_identifier: str = Field(..., description="Target WA (Discord user, email, etc.)")
    urgency_level: str = Field(default="normal", pattern="^(low|normal|high|critical)$", description="Urgency level")

    # Transport metadata (no Dict[str, Any]!)
    transport_data: TransportData = Field(..., description="Transport metadata")
    created_at: datetime = Field(..., description="Report creation time")

    # Status tracking
    delivered: bool = Field(default=False, description="Whether delivered")
    delivered_at: Optional[datetime] = Field(None, description="Delivery timestamp")
    response_received: bool = Field(default=False, description="Whether response received")
    response_at: Optional[datetime] = Field(None, description="Response timestamp")

    model_config = ConfigDict(extra="forbid")


class DeferralResolution(BaseModel):
    """WA resolution of a deferral."""

    report_id: str = Field(..., description="Report being resolved")
    wa_id: str = Field(..., description="WA who resolved")
    decision: str = Field(..., description="approve, reject, modify")
    reasoning: str = Field(..., description="Explanation of decision")

    # Modifications if any
    modified_action: Optional[str] = Field(None, description="Modified action if changed")
    conditions: List[str] = Field(default_factory=list, description="Conditions on approval")

    # Timing
    resolved_at: datetime = Field(..., description="When resolved")
    signature: str = Field(..., description="Digital signature")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "DeferralReason",
    "EthicalAssessment",
    "CSDMAAssessment",
    "DSDMAAssessment",
    "ActionHistoryItem",
    "DeferralPackage",
    "TransportData",
    "DeferralReport",
    "DeferralResolution",
]
