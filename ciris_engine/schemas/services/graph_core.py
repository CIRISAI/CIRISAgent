"""
Core graph schemas for CIRIS Trinity Architecture.

Everything is a memory node in the graph.
NO Dict[str, Any] - use typed attributes.
"""
from enum import Enum
from typing import Optional, List, Union, Any, Dict
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict

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
    AUDIT_ENTRY = "audit_entry"
    IDENTITY_SNAPSHOT = "identity_snapshot"
    BEHAVIORAL = "behavioral"
    SOCIAL = "social"
    IDENTITY = "identity"
    OBSERVATION = "observation"

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
}

class GraphNodeAttributes(BaseModel):
    """Base typed attributes for graph nodes."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(..., description="Who created this node")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")

    model_config = ConfigDict(extra = "forbid")

class GraphNode(BaseModel):
    """Base node for the graph - everything is a memory."""
    id: str = Field(..., description="Unique node identifier")
    type: NodeType = Field(..., description="Type of node")
    scope: GraphScope = Field(..., description="Scope of the node")
    attributes: Union[GraphNodeAttributes, Dict[str, Any]] = Field(..., description="Node attributes")
    version: int = Field(default=1, ge=1, description="Version number")
    updated_by: Optional[str] = Field(None, description="Who last updated")
    updated_at: Optional[datetime] = Field(None, description="When last updated")

    model_config = ConfigDict(extra = "forbid")

class GraphEdgeAttributes(BaseModel):
    """Typed attributes for graph edges."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    context: Optional[str] = Field(None, description="Context of the relationship")

    model_config = ConfigDict(extra = "forbid")

class GraphEdge(BaseModel):
    """Edge connecting nodes in the graph."""
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    relationship: str = Field(..., description="Type of relationship")
    scope: GraphScope = Field(..., description="Scope of the edge")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Relationship weight")
    attributes: GraphEdgeAttributes = Field(default_factory=lambda: GraphEdgeAttributes())

    model_config = ConfigDict(extra = "forbid")

__all__ = [
    "GraphScope",
    "NodeType",
    "ConfigNodeType",
    "CONFIG_SCOPE_MAP",
    "GraphNode",
    "GraphNodeAttributes",
    "GraphEdge",
    "GraphEdgeAttributes",
]
