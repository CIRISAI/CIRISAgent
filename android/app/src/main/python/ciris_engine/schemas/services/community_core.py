"""
Community Schemas v1 - Community awareness with minimal memory footprint

Designed for deployments that might track just one community at a time.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SchemaVersion(str, Enum):
    """Version of the schema."""

    V1_0 = "v1.0"


class CommunityHealth(BaseModel):
    """Community health metrics - single byte per metric where possible"""

    activity_level: int = Field(default=50, ge=0, le=100, description="Activity level (0-100)")
    conflict_level: int = Field(default=0, ge=0, le=100, description="Conflict level (0-100)")
    helpfulness: int = Field(default=50, ge=0, le=100, description="Helpfulness level (0-100)")
    flourishing: int = Field(default=50, ge=0, le=100, description="Composite flourishing metric from Annex A")

    model_config = ConfigDict(extra="forbid")


class CommunityValue(BaseModel):
    """A single community value"""

    name: str = Field(description="Value name")
    importance: int = Field(ge=0, le=100, description="Importance rating (0-100)")

    model_config = ConfigDict(extra="forbid")


class MinimalCommunityContext(BaseModel):
    """Just enough context to serve a community well"""

    schema_version: SchemaVersion = Field(default=SchemaVersion.V1_0, description="Schema version")
    community_id: str = Field(description="Unique community identifier")
    member_count: int = Field(default=0, ge=0, description="Number of community members")
    primary_values: List[CommunityValue] = Field(default_factory=list, description="Community's primary values")
    health: CommunityHealth = Field(default_factory=CommunityHealth, description="Community health metrics")
    agent_role: Optional[str] = Field(default=None, description="Agent's role (moderator, helper, etc.)")

    model_config = ConfigDict(extra="forbid")


class CommunityMember(BaseModel):
    """Minimal member information"""

    member_id: str = Field(description="Member identifier")
    trust_level: int = Field(default=50, ge=0, le=100, description="Trust level (0-100)")
    contribution_score: int = Field(default=50, ge=0, le=100, description="Contribution score (0-100)")
    last_active: Optional[str] = Field(default=None, description="ISO timestamp of last activity")

    model_config = ConfigDict(extra="forbid")


class CommunityEvent(BaseModel):
    """Significant community event"""

    event_id: str = Field(description="Event identifier")
    event_type: str = Field(description="Type of event")
    impact_score: int = Field(ge=0, le=100, description="Impact on community (0-100)")
    timestamp: str = Field(description="ISO timestamp of event")
    summary: str = Field(description="Brief event summary")

    model_config = ConfigDict(extra="forbid")


class CommunitySnapshot(BaseModel):
    """Point-in-time community state"""

    snapshot_id: str = Field(description="Snapshot identifier")
    timestamp: str = Field(description="ISO timestamp of snapshot")
    context: MinimalCommunityContext = Field(description="Community context")
    active_members: List[str] = Field(default_factory=list, description="IDs of currently active members")
    recent_events: List[CommunityEvent] = Field(default_factory=list, description="Recent significant events")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "SchemaVersion",
    "CommunityHealth",
    "CommunityValue",
    "MinimalCommunityContext",
    "CommunityMember",
    "CommunityEvent",
    "CommunitySnapshot",
]
