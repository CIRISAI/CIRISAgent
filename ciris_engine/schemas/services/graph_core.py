"""
Core graph schemas for CIRIS Trinity Architecture.

Everything is a memory node in the graph.
NO Dict[str, Any] - use typed attributes.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.consent.core import ConsentStream
from ciris_engine.schemas.services.graph.attributes import AnyNodeAttributes
from ciris_engine.schemas.types import JSONDict


class GraphScope(str, Enum):
    """Scope of graph nodes and edges."""

    LOCAL = "local"
    IDENTITY = "identity"
    ENVIRONMENT = "environment"
    COMMUNITY = "community"


class NodeType(str, Enum):
    """Types of nodes in the graph."""

    AGENT = "agent"
    USER = "user"
    CHANNEL = "channel"
    CONCEPT = "concept"
    CONFIG = "config"
    TSDB_DATA = "tsdb_data"
    TSDB_SUMMARY = "tsdb_summary"
    CONVERSATION_SUMMARY = "conversation_summary"
    TRACE_SUMMARY = "trace_summary"
    AUDIT_SUMMARY = "audit_summary"
    TASK_SUMMARY = "task_summary"
    AUDIT_ENTRY = "audit_entry"
    IDENTITY_SNAPSHOT = "identity_snapshot"
    BEHAVIORAL = "behavioral"
    SOCIAL = "social"
    IDENTITY = "identity"
    OBSERVATION = "observation"
    CONSENT = "consent"
    DECAY = "decay"
    MODERATION = "moderation"
    SAFETY_SCORE = "safety_score"


class ConfigNodeType(str, Enum):
    """Types of configuration nodes with scope requirements."""

    # LOCAL scope
    FILTER_CONFIG = "filter_config"
    CHANNEL_CONFIG = "channel_config"
    USER_TRACKING = "user_tracking"
    RESPONSE_TEMPLATES = "response_templates"
    TOOL_PREFERENCES = "tool_preferences"

    # IDENTITY scope (requires WA approval)
    BEHAVIOR_CONFIG = "behavior_config"
    ETHICAL_BOUNDARIES = "ethical_boundaries"
    CAPABILITY_LIMITS = "capability_limits"
    TRUST_PARAMETERS = "trust_parameters"
    LEARNING_RULES = "learning_rules"
    COGNITIVE_STATE_BEHAVIORS = "cognitive_state_behaviors"  # Wakeup/shutdown/play/dream/solitude config
    TICKET_SOPS = "ticket_sops"  # DSAR and other ticket Standard Operating Procedures


# Mapping of config types to required scopes
CONFIG_SCOPE_MAP = {
    ConfigNodeType.FILTER_CONFIG: GraphScope.LOCAL,
    ConfigNodeType.CHANNEL_CONFIG: GraphScope.LOCAL,
    ConfigNodeType.USER_TRACKING: GraphScope.LOCAL,
    ConfigNodeType.RESPONSE_TEMPLATES: GraphScope.LOCAL,
    ConfigNodeType.TOOL_PREFERENCES: GraphScope.LOCAL,
    ConfigNodeType.BEHAVIOR_CONFIG: GraphScope.IDENTITY,
    ConfigNodeType.ETHICAL_BOUNDARIES: GraphScope.IDENTITY,
    ConfigNodeType.CAPABILITY_LIMITS: GraphScope.IDENTITY,
    ConfigNodeType.TRUST_PARAMETERS: GraphScope.IDENTITY,
    ConfigNodeType.LEARNING_RULES: GraphScope.IDENTITY,
    ConfigNodeType.COGNITIVE_STATE_BEHAVIORS: GraphScope.IDENTITY,
    ConfigNodeType.TICKET_SOPS: GraphScope.IDENTITY,
}


class GraphNodeAttributes(BaseModel):
    """Base typed attributes for graph nodes."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(..., description="Who created this node")
    content: str | None = Field(None, description="Optional content for the node")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    model_config = ConfigDict(extra="forbid")


class GraphNode(BaseModel):
    """Base node for the graph - everything is a memory."""

    id: str = Field(..., description="Unique node identifier")
    type: NodeType = Field(..., description="Type of node")
    scope: GraphScope = Field(..., description="Scope of the node")
    attributes: AnyNodeAttributes | JSONDict | GraphNodeAttributes = Field(
        ..., description="Node attributes"
    )  # NOQA - Graph flexibility pattern
    version: int = Field(default=1, ge=1, description="Version number")
    updated_by: str | None = Field(None, description="Who last updated")
    updated_at: datetime | None = Field(None, description="When last updated")
    consent_stream: ConsentStream = Field(
        default=ConsentStream.TEMPORARY,
        description="Consent stream for this node (TEMPORARY=14-day, PARTNERED=persistent, ANONYMOUS=stats-only)",
    )
    expires_at: datetime | None = Field(
        None, description="Expiry time for TEMPORARY consent nodes (auto-set to 14 days for TEMPORARY)"
    )

    model_config = ConfigDict(extra="forbid")


class GraphEdgeAttributes(BaseModel):
    """Typed attributes for graph edges."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    context: str | None = Field(None, description="Context of the relationship")

    model_config = ConfigDict(extra="forbid")


class GraphEdge(BaseModel):
    """Edge connecting nodes in the graph."""

    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    relationship: str = Field(..., description="Type of relationship")
    scope: GraphScope = Field(..., description="Scope of the edge")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Relationship weight")
    attributes: GraphEdgeAttributes = Field(
        default_factory=lambda: GraphEdgeAttributes(created_at=datetime.now(timezone.utc), context=None)
    )

    model_config = ConfigDict(extra="forbid")


class ConnectedNodeInfo(BaseModel):
    """Flexible schema for connected node information - supports multiple graph sources."""

    node_id: str = Field(..., description="Connected node identifier")
    node_type: str = Field(..., description="Type of connected node")
    relationship: str = Field(..., description="Relationship type to the source node")
    attributes: JSONDict = Field(
        default_factory=dict, description="Connected node attributes"
    )  # NOQA - Graph integration pattern
    source_service: str = Field(default="MemoryService", description="Service that provided connection info")
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When connection was retrieved"
    )
    edge_metadata: JSONDict | None = Field(
        None, description="Additional edge metadata from future sources"
    )  # NOQA - Future source extensibility


class SecretsData(BaseModel):
    """Flexible schema for secrets snapshot data - supports multiple secrets sources."""

    secrets_count: int = Field(0, description="Number of secrets stored")
    filter_status: str = Field("unknown", description="Secrets filter status")
    last_updated: datetime | None = Field(None, description="When secrets were last updated")
    detected_secrets: List[str] = Field(default_factory=list, description="List of detected secret patterns")
    secrets_filter_version: int = Field(0, description="Version of the secrets filter being used")
    source_service: str = Field(default="SecretsService", description="Service that provided secrets data")
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When secrets data was retrieved"
    )
    additional_data: JSONDict = Field(  # NOQA - Future source extensibility
        default_factory=dict, description="Additional secrets data from future sources"
    )


__all__ = [
    "GraphScope",
    "NodeType",
    "ConfigNodeType",
    "CONFIG_SCOPE_MAP",
    "GraphNode",
    "GraphNodeAttributes",
    "GraphEdge",
    "GraphEdgeAttributes",
    "ConnectedNodeInfo",
    "SecretsData",
]
