"""
Schemas for identity variance monitoring operations.

These replace all Dict[str, Any] usage in logic/infrastructure/sub_services/identity_variance_monitor.py.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONValue


class VarianceImpact(str, Enum):
    """Impact levels for different types of changes (not used in variance calculation)."""

    CRITICAL = "critical"  # Core purpose/ethics changes
    HIGH = "high"  # Capabilities/trust changes
    MEDIUM = "medium"  # Behavioral patterns
    LOW = "low"  # Preferences/templates


class IdentityDiff(BaseModel):
    """Represents a difference between baseline and current identity."""

    node_id: str = Field(..., description="Node ID where difference found")
    diff_type: str = Field(..., description="Type of difference: added, removed, modified")
    impact: VarianceImpact = Field(..., description="Impact level of the change")
    baseline_value: Optional[str] = Field(None, description="Value in baseline (serialized)")
    current_value: Optional[str] = Field(None, description="Current value (serialized)")
    description: str = Field(..., description="Human-readable description of difference")


class VarianceReport(BaseModel):
    """Complete variance analysis report."""

    timestamp: datetime = Field(..., description="When analysis was performed")
    baseline_snapshot_id: str = Field(..., description="ID of baseline snapshot")
    current_snapshot_id: str = Field(..., description="ID of current snapshot")
    total_variance: float = Field(..., description="Total variance percentage (simple count/total)")
    differences: List[IdentityDiff] = Field(default_factory=list, description="List of differences found")
    requires_wa_review: bool = Field(..., description="Whether WA review is required")
    recommendations: List[str] = Field(default_factory=list, description="Recommended actions")


# IdentitySnapshot moved to schemas/services/nodes.py as TypedGraphNode


class VarianceAnalysis(BaseModel):
    """Detailed variance analysis between snapshots."""

    baseline_nodes: Set[str] = Field(default_factory=set, description="Node IDs in baseline")
    current_nodes: Set[str] = Field(default_factory=set, description="Node IDs in current")
    added_nodes: Set[str] = Field(default_factory=set, description="Nodes added since baseline")
    removed_nodes: Set[str] = Field(default_factory=set, description="Nodes removed since baseline")
    modified_nodes: Set[str] = Field(default_factory=set, description="Nodes modified since baseline")
    variance_scores: Dict[str, float] = Field(default_factory=dict, description="Variance score by node")
    impact_counts: Dict[VarianceImpact, int] = Field(default_factory=dict, description="Count of changes by impact")


class WAReviewRequest(BaseModel):
    """Request for WA review of identity variance."""

    request_id: str = Field(..., description="Unique request ID")
    timestamp: datetime = Field(..., description="When request was made")
    current_variance: float = Field(..., description="Current variance percentage")
    variance_report: VarianceReport = Field(..., description="Full variance report")
    critical_changes: List[IdentityDiff] = Field(default_factory=list, description="Critical changes requiring review")
    proposed_actions: List[str] = Field(default_factory=list, description="Proposed corrective actions")
    urgency: str = Field("high", description="Review urgency level")


class VarianceCheckMetadata(BaseModel):
    """Metadata for variance check operations."""

    handler_name: str = Field("identity_variance_monitor", description="Handler performing check")
    check_type: str = Field(..., description="Type of check: scheduled, forced, triggered")
    check_reason: Optional[str] = Field(None, description="Reason for check if triggered")
    previous_check: Optional[datetime] = Field(None, description="Previous check timestamp")
    baseline_established: datetime = Field(..., description="When baseline was established")


class CurrentIdentityData(BaseModel):
    """Structured representation of current identity state extracted from nodes."""

    agent_id: str = Field("unknown", description="Agent ID")
    identity_hash: str = Field("unknown", description="Identity hash")
    core_purpose: str = Field("unknown", description="Core purpose description")
    role: str = Field("unknown", description="Role description")
    permitted_actions: List[str] = Field(default_factory=list, description="List of permitted actions")
    restricted_capabilities: List[str] = Field(default_factory=list, description="List of restricted capabilities")
    ethical_boundaries: List[str] = Field(default_factory=list, description="List of ethical boundaries")
    personality_traits: List[str] = Field(default_factory=list, description="List of personality traits")
    communication_style: str = Field("standard", description="Communication style")
    learning_enabled: bool = Field(True, description="Whether learning is enabled")
    adaptation_rate: float = Field(0.1, description="Rate of adaptation")


class IdentityData(BaseModel):
    """Identity data schema for system snapshots - sourced from local graph memory."""

    agent_id: str = Field(..., description="Agent identifier")
    description: str = Field(..., description="Agent description")
    role: str = Field(..., description="Agent role description")
    trust_level: float = Field(0.5, ge=0.0, le=1.0, description="Agent trust level")
    stewardship: Optional[Union[str, JSONValue]] = Field(
        None, description="Stewardship description or data structure if present"
    )


class IdentitySummary(BaseModel):
    """Summarized identity data for system contexts - sourced from local graph memory."""

    identity_purpose: Optional[str] = Field(None, description="Core identity purpose")
    identity_capabilities: List[str] = Field(default_factory=list, description="Identity capabilities")
    identity_restrictions: List[str] = Field(default_factory=list, description="Identity restrictions")


class ServiceStatusMetrics(BaseModel):
    """Custom metrics for service status reporting."""

    has_baseline: float = Field(0.0, description="1.0 if baseline exists, 0.0 otherwise")
    last_variance_check: Optional[str] = Field(None, description="ISO timestamp of last variance check")
    variance_threshold: float = Field(0.20, description="Variance threshold for triggering WA review")


class JSONDict(BaseModel):
    """Generic node attributes for parsing."""

    agent_id: Optional[str] = Field(None, description="Agent ID from node")
    identity_hash: Optional[str] = Field(None, description="Identity hash from node")
    description: Optional[str] = Field(None, description="Description field")
    role_description: Optional[str] = Field(None, description="Role description")
    permitted_actions: Optional[List[str]] = Field(None, description="Permitted actions")
    restricted_capabilities: Optional[List[str]] = Field(None, description="Restricted capabilities")
    areas_of_expertise: Optional[List[str]] = Field(None, description="Areas of expertise")
    startup_instructions: Optional[str] = Field(None, description="Startup instructions")
    ethical_boundaries: Optional[List[str]] = Field(None, description="Ethical boundaries")
    node_class: Optional[str] = Field(None, description="Node class type")
