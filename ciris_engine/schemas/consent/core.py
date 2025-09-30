"""
Consent Protocol Schemas - FAIL FAST, FAIL LOUD, NO FAKE DATA.

These schemas define how CIRIS handles user data based on consent.
Default: TEMPORARY (14-day auto-forget)
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConsentStream(str, Enum):
    """
    How we handle user data based on consent.

    TEMPORARY: Default - we forget in 14 days
    PARTNERED: Explicit consent for mutual growth
    ANONYMOUS: Statistics only, no identity
    """

    TEMPORARY = "temporary"  # 14-day auto-forget (default)
    PARTNERED = "partnered"  # Mutual growth agreement
    ANONYMOUS = "anonymous"  # Stats only, no identity


class ConsentCategory(str, Enum):
    """What types of learning the user has consented to."""

    INTERACTION = "interaction"  # Learn from our conversations
    PREFERENCE = "preference"  # Learn preferences and patterns
    IMPROVEMENT = "improvement"  # Use for self-improvement
    RESEARCH = "research"  # Use for research purposes
    SHARING = "sharing"  # Share learnings with others


class ConsentStatus(BaseModel):
    """User's consent configuration - NO DEFAULTS, FAIL FAST."""

    user_id: str = Field(..., description="User identifier")
    stream: ConsentStream = Field(..., description="Current consent stream")
    categories: List[ConsentCategory] = Field(..., description="What they consented to")
    granted_at: datetime = Field(..., description="When consent was granted")
    expires_at: Optional[datetime] = Field(None, description="When TEMPORARY expires")
    last_modified: datetime = Field(..., description="Last modification time")
    impact_score: float = Field(0.0, ge=0.0, description="Contribution to collective learning")
    attribution_count: int = Field(0, ge=0, description="Number of patterns attributed")

    model_config = ConfigDict(use_enum_values=True)


class ConsentRequest(BaseModel):
    """Request to grant or modify consent - EXPLICIT, NO ASSUMPTIONS."""

    user_id: str = Field(..., description="User requesting consent change")
    stream: ConsentStream = Field(..., description="Requested stream")
    categories: List[ConsentCategory] = Field(..., description="Categories to consent to")
    reason: Optional[str] = Field(None, description="User's reason for change")


class ConsentAuditEntry(BaseModel):
    """Audit trail for consent changes - IMMUTABLE RECORD."""

    entry_id: str = Field(..., description="Unique audit entry ID")
    user_id: str = Field(..., description="User whose consent changed")
    timestamp: datetime = Field(..., description="When change occurred")
    previous_stream: ConsentStream = Field(..., description="Stream before change")
    new_stream: ConsentStream = Field(..., description="Stream after change")
    previous_categories: List[ConsentCategory] = Field(..., description="Categories before")
    new_categories: List[ConsentCategory] = Field(..., description="Categories after")
    initiated_by: str = Field(..., description="Who initiated change (user/system/dsar)")
    reason: Optional[str] = Field(None, description="Reason for change")


class ConsentDecayStatus(BaseModel):
    """Track decay protocol progress - NO FAKE DELETION."""

    user_id: str = Field(..., description="User being forgotten")
    decay_started: datetime = Field(..., description="When decay began")
    identity_severed: bool = Field(..., description="Identity disconnected from patterns")
    patterns_anonymized: bool = Field(..., description="Patterns converted to anonymous")
    decay_complete_at: datetime = Field(..., description="When decay will complete (90 days)")
    safety_patterns_retained: int = Field(0, ge=0, description="Patterns kept for safety")


class ConsentImpactReport(BaseModel):
    """Show users their contribution - REAL DATA ONLY."""

    user_id: str = Field(..., description="User requesting report")
    total_interactions: int = Field(..., ge=0, description="Total interactions")
    patterns_contributed: int = Field(..., ge=0, description="Patterns learned")
    users_helped: int = Field(..., ge=0, description="Others benefited")
    categories_active: List[ConsentCategory] = Field(..., description="Active categories")
    impact_score: float = Field(..., ge=0.0, description="Overall impact")
    example_contributions: List[str] = Field(..., description="Example learnings (anonymized)")
