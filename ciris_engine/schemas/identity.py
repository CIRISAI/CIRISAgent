"""Identity resolution schemas for DSAR automation."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class UserIdentifier(BaseModel):
    """A single user identifier from a specific system."""

    identifier_type: str = Field(
        ...,
        description="Type of identifier (email, discord_id, reddit_username, api_key, etc.)",
    )
    identifier_value: str = Field(..., description="Identifier value")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this identifier (0.0-1.0)",
    )
    source: str = Field(
        default="manual",
        description="Source of identifier (oauth, manual, auto, api, etc.)",
    )
    created_at: Optional[str] = Field(default=None, description="Timestamp when identifier was added")
    verified: bool = Field(default=False, description="Whether identifier has been verified")
    graph_node_id: Optional[str] = Field(default=None, description="Reference to GraphNode in MemoryBus")


class UserIdentityNode(BaseModel):
    """Complete user identity with all known identifiers across systems."""

    primary_id: str = Field(..., description="Primary user identifier (typically email or user_id)")
    identifiers: List[UserIdentifier] = Field(default_factory=list, description="All known identifiers for this user")
    graph_node_id: Optional[str] = Field(default=None, description="Reference to primary GraphNode in MemoryBus")
    total_identifiers: int = Field(default=0, description="Total number of identifiers")
    last_updated: Optional[str] = Field(default=None, description="Timestamp of last update")


class IdentityMappingEvidence(BaseModel):
    """Evidence supporting an identity mapping."""

    evidence_type: str = Field(..., description="Type of evidence (oauth, behavior, shared_attribute, etc.)")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence contribution from this evidence",
    )
    source: str = Field(..., description="Source of evidence")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional details about evidence")
    created_at: Optional[str] = Field(default=None, description="Timestamp when evidence was collected")


class IdentityConflict(BaseModel):
    """Conflict detected in identity mapping."""

    conflict_type: str = Field(
        ...,
        description="Type of conflict (duplicate_mapping, inconsistent_data, etc.)",
    )
    identifier1: UserIdentifier = Field(..., description="First identifier in conflict")
    identifier2: UserIdentifier = Field(..., description="Second identifier in conflict")
    severity: str = Field(default="warning", description="Severity: info, warning, error, critical")
    details: str = Field(..., description="Description of conflict")
    created_at: Optional[str] = Field(default=None, description="Timestamp when conflict was detected")


class IdentityConfidence(BaseModel):
    """Confidence assessment for an identity mapping."""

    score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall confidence score (0.0-1.0)",
    )
    evidence: List[IdentityMappingEvidence] = Field(
        default_factory=list, description="Evidence supporting this mapping"
    )
    conflicts: List[IdentityConflict] = Field(default_factory=list, description="Conflicts detected for this mapping")
    recommendation: str = Field(
        ...,
        description="Recommendation: accept, review, reject",
    )
    reasoning: str = Field(..., description="Human-readable explanation of confidence score")


class IdentityGraphVisualization(BaseModel):
    """Identity graph structure for visualization/debugging."""

    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="Graph nodes with metadata")
    edges: List[Dict[str, Any]] = Field(default_factory=list, description="Graph edges with relationships")
    center_node_id: str = Field(..., description="Central node for this graph")
    depth: int = Field(..., description="Maximum depth traversed")
    total_nodes: int = Field(default=0, description="Total nodes in graph")
    total_edges: int = Field(default=0, description="Total edges in graph")


class IdentityResolutionRequest(BaseModel):
    """Request for identity resolution."""

    identifier: str = Field(..., description="User identifier value")
    identifier_type: str = Field(default="email", description="Type of identifier to resolve")
    include_low_confidence: bool = Field(
        default=False,
        description="Include low-confidence mappings (confidence < 0.5)",
    )
    max_depth: int = Field(default=2, ge=1, le=5, description="Maximum graph traversal depth")


class IdentityResolutionResult(BaseModel):
    """Result of identity resolution request."""

    success: bool = Field(..., description="Whether resolution succeeded")
    identity_node: Optional[UserIdentityNode] = Field(default=None, description="Resolved identity node")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Overall confidence in resolution",
    )
    identifiers_found: int = Field(default=0, description="Number of identifiers found")
    error: Optional[str] = Field(default=None, description="Error message if failed")


class IdentityMergeRequest(BaseModel):
    """Request to merge two user identities."""

    primary_id: str = Field(..., description="Primary user identifier (kept)")
    secondary_id: str = Field(..., description="Secondary user identifier (merged into primary)")
    reason: str = Field(..., description="Reason for merge")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in merge decision",
    )


class IdentityMergeResult(BaseModel):
    """Result of identity merge operation."""

    success: bool = Field(..., description="Whether merge succeeded")
    merged_identity: Optional[UserIdentityNode] = Field(default=None, description="Merged identity node")
    identifiers_merged: int = Field(default=0, description="Number of identifiers merged")
    conflicts_resolved: int = Field(default=0, description="Number of conflicts resolved")
    error: Optional[str] = Field(default=None, description="Error message if failed")
