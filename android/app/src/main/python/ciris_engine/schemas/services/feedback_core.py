"""
Feedback schemas for Wise Authority feedback processing.

Provides type-safe structures for WA feedback and directives.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class FeedbackType(str, Enum):
    """Types of WA feedback."""

    IDENTITY_UPDATE = "identity_update"
    ENVIRONMENT_UPDATE = "environment_update"
    MEMORY_CORRECTION = "memory_correction"
    DECISION_OVERRIDE = "decision_override"
    POLICY_CLARIFICATION = "policy_clarification"
    SYSTEM_DIRECTIVE = "system_directive"


class FeedbackSource(str, Enum):
    """Source of the feedback."""

    WISE_AUTHORITY = "wise_authority"
    HUMAN_OPERATOR = "human_operator"
    SYSTEM_MONITOR = "system_monitor"
    PEER_AGENT = "peer_agent"


class FeedbackDirective(BaseModel):
    """Specific directive within feedback."""

    action: str = Field(..., description="Action: update, delete, add, override, etc.")
    target: str = Field(..., description="What to act on")
    data: Union[Dict[str, str], str, List[str]] = Field(..., description="Directive data")
    reasoning: Optional[str] = Field(None, description="Reasoning for directive")

    model_config = ConfigDict(extra="forbid")


class WiseAuthorityFeedback(BaseModel):
    """Structured feedback from WA on deferred decisions."""

    feedback_id: str = Field(..., description="Unique feedback ID")

    # Original context
    original_report_id: Optional[str] = Field(None, description="Original report ID")
    original_thought_id: Optional[str] = Field(None, description="Original thought ID")
    original_task_id: Optional[str] = Field(None, description="Original task ID")

    # Feedback details
    feedback_type: FeedbackType = Field(..., description="Type of feedback")
    feedback_source: FeedbackSource = Field(..., description="Source of feedback")
    directives: List[FeedbackDirective] = Field(default_factory=list, description="Specific directives")

    # Content
    summary: str = Field("", description="Feedback summary")
    detailed_reasoning: Optional[str] = Field(None, description="Detailed reasoning")

    # Priority and timing
    priority: str = Field(default="normal", pattern="^(low|normal|high|critical)$")
    implementation_notes: Optional[str] = Field(None, description="Implementation guidance")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field("wise_authority", description="Creator identifier")
    expires_at: Optional[datetime] = Field(None, description="Expiration time")

    # Processing status
    processed: bool = Field(False, description="Whether processed")
    processed_at: Optional[datetime] = Field(None, description="Processing time")
    processing_result: Dict[str, str] = Field(default_factory=dict, description="Processing results")

    model_config = ConfigDict(extra="forbid")


class FeedbackMapping(BaseModel):
    """Maps feedback to original context for processing."""

    mapping_id: str = Field(..., description="Unique mapping ID")
    feedback_id: str = Field(..., description="Feedback ID")

    # Original context
    source_message_id: Optional[str] = Field(None, description="Discord message, etc.")
    source_task_id: Optional[str] = Field(None, description="Source task")
    source_thought_id: Optional[str] = Field(None, description="Source thought")

    # Transport context
    transport_type: str = Field(..., description="Transport: discord, email, api, etc.")
    transport_data: Dict[str, str] = Field(default_factory=dict, description="Transport metadata")

    created_at: datetime = Field(..., description="Creation time")

    model_config = ConfigDict(extra="forbid")


class FeedbackProcessingRequest(BaseModel):
    """Request to process feedback."""

    feedback_id: str = Field(..., description="Feedback to process")
    force: bool = Field(False, description="Force reprocessing")
    dry_run: bool = Field(False, description="Validate without applying")

    model_config = ConfigDict(extra="forbid")


class FeedbackProcessingResult(BaseModel):
    """Result of feedback processing."""

    success: bool = Field(..., description="Whether processing succeeded")
    feedback_id: str = Field(..., description="Processed feedback ID")
    actions_taken: List[str] = Field(..., description="Actions performed")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "FeedbackType",
    "FeedbackSource",
    "FeedbackDirective",
    "WiseAuthorityFeedback",
    "FeedbackMapping",
    "FeedbackProcessingRequest",
    "FeedbackProcessingResult",
]
