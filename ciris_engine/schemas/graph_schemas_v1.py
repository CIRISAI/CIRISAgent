from enum import Enum
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, List
from datetime import datetime, timezone


class GraphScope(str, Enum):
    LOCAL = "local"
    IDENTITY = "identity"
    ENVIRONMENT = "environment"
    COMMUNITY = "community"


class NodeType(str, Enum):
    AGENT = "agent"
    USER = "user"
    CHANNEL = "channel"
    CONCEPT = "concept"
    CONFIG = "config"
    TSDB_DATA = "tsdb_data"

class ConfigNodeType(str, Enum):
    """Types of configuration nodes with scope requirements"""

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


class GraphNode(BaseModel):
    """Minimal node for v1"""

    id: str
    type: NodeType
    scope: GraphScope
    attributes: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    updated_by: Optional[str] = None  # WA feedback tracking
    updated_at: Optional[str] = None


class GraphEdge(BaseModel):
    """Minimal edge for v1"""

    source: str
    target: str
    relationship: str
    scope: GraphScope
    weight: float = 1.0
    attributes: Dict[str, Any] = Field(default_factory=dict)


class AdaptationProposalNode(GraphNode):
    """
    Specialized node for configuration adaptation proposals.
    
    Represents an agent's proposal to adapt its configuration based on
    observed patterns and experiences.
    """
    
    # Override type to be CONFIG by default
    type: NodeType = Field(default=NodeType.CONFIG)
    
    # Adaptation-specific fields
    trigger: str = Field(..., description="What triggered this adaptation proposal")
    current_pattern: Optional[str] = Field(None, description="Current behavioral pattern")
    proposed_changes: Dict[str, Any] = Field(..., description="Proposed configuration changes")
    evidence: List[str] = Field(default_factory=list, description="Node IDs supporting this proposal")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in this adaptation")
    auto_applicable: bool = Field(default=False, description="Can be auto-applied if confidence high enough")
    applied: bool = Field(default=False, description="Whether this proposal was applied")
    applied_at: Optional[datetime] = Field(None, description="When the proposal was applied")
    
    def __init__(self, **data: Any) -> None:
        """Initialize AdaptationProposalNode with proper defaults"""
        if 'id' not in data:
            timestamp_str = int(datetime.now(timezone.utc).timestamp())
            trigger = data.get('trigger', 'unknown').replace(' ', '_')
            data['id'] = f"adaptation_{trigger}_{timestamp_str}"
        
        # Ensure it's stored in appropriate scope based on impact
        if 'scope' not in data:
            # Check if changes affect identity-level configs
            proposed_changes = data.get('proposed_changes', {})
            affects_identity = any(
                key in proposed_changes for key in 
                ['ethical_boundaries', 'capability_limits', 'trust_parameters', 'behavior_config']
            )
            data['scope'] = GraphScope.IDENTITY if affects_identity else GraphScope.LOCAL
        
        super().__init__(**data)
    
    def can_auto_apply(self, threshold: float = 0.8) -> bool:
        """Check if this proposal can be automatically applied."""
        return (
            self.auto_applicable and 
            self.confidence >= threshold and 
            self.scope == GraphScope.LOCAL and
            not self.applied
        )


class TSDBGraphNode(GraphNode):
    """
    Specialized graph node for time-series database data.
    
    Extends GraphNode with time-series specific fields for efficient
    storage and retrieval of metrics, logs, and audit events.
    """
    
    # Override type to be TSDB_DATA by default
    type: NodeType = Field(default=NodeType.TSDB_DATA)
    
    # Time-series specific fields
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    log_level: Optional[str] = None
    log_message: Optional[str] = None
    data_type: str  # "metric", "log_entry", "audit_event"
    
    # TSDB tags for efficient querying
    tags: Dict[str, str] = Field(default_factory=dict)
    
    # Retention and aggregation hints
    retention_policy: str = "raw"  # "raw", "aggregated", "downsampled"
    aggregation_period: Optional[str] = None  # "1m", "5m", "1h", "1d"
    
    def __init__(self, **data: Any) -> None:
        """Initialize TSDBGraphNode with proper defaults"""
        if 'id' not in data:
            timestamp_str = int(datetime.now(timezone.utc).timestamp())
            data_type = data.get('data_type', 'unknown')
            data['id'] = f"tsdb_{data_type}_{timestamp_str}"
        
        if 'attributes' not in data:
            data['attributes'] = {}
        
        tsdb_fields = ['metric_name', 'metric_value', 'log_level', 'log_message', 'data_type', 'tags', 'retention_policy']
        for field in tsdb_fields:
            if field in data and data[field] is not None:
                data['attributes'][field] = data[field]
        
        super().__init__(**data)
    
    @classmethod
    def create_metric_node(cls, metric_name: str, value: float, tags: Optional[Dict[str, str]] = None, 
                          scope: GraphScope = GraphScope.LOCAL, retention_policy: str = "raw") -> "TSDBGraphNode":
        """Create a TSDBGraphNode for a metric data point"""
        timestamp = datetime.now(timezone.utc)
        return cls(
            id=f"metric_{metric_name}_{int(timestamp.timestamp())}",
            scope=scope,
            timestamp=timestamp,
            metric_name=metric_name,
            metric_value=value,
            data_type="metric",
            tags=tags or {},
            retention_policy=retention_policy,
            attributes={
                "metric_name": metric_name,
                "metric_value": value,
                "data_type": "metric",
                "tags": tags or {},
                "retention_policy": retention_policy
            }
        )
    
    @classmethod
    def create_log_node(cls, log_message: str, log_level: str = "INFO", tags: Optional[Dict[str, str]] = None,
                       scope: GraphScope = GraphScope.LOCAL, retention_policy: str = "raw") -> "TSDBGraphNode":
        """Create a TSDBGraphNode for a log entry"""
        timestamp = datetime.now(timezone.utc)
        return cls(
            id=f"log_{int(timestamp.timestamp())}_{hash(log_message) % 10000:04d}",
            scope=scope,
            timestamp=timestamp,
            log_message=log_message,
            log_level=log_level,
            data_type="log_entry",
            tags=tags or {},
            retention_policy=retention_policy,
            attributes={
                "log_message": log_message,
                "log_level": log_level,
                "data_type": "log_entry",
                "tags": tags or {},
                "retention_policy": retention_policy
            }
        )
    
    @classmethod
    def create_audit_node(cls, action_type: str, outcome: str, tags: Optional[Dict[str, str]] = None,
                         scope: GraphScope = GraphScope.LOCAL, retention_policy: str = "raw") -> "TSDBGraphNode":
        """Create a TSDBGraphNode for an audit event"""
        timestamp = datetime.now(timezone.utc)
        return cls(
            id=f"audit_{action_type}_{int(timestamp.timestamp())}",
            scope=scope,
            timestamp=timestamp,
            data_type="audit_event",
            tags={**(tags or {}), "action_type": action_type, "outcome": outcome},
            retention_policy=retention_policy,
            attributes={
                "action_type": action_type,
                "outcome": outcome,
                "data_type": "audit_event",
                "tags": {**(tags or {}), "action_type": action_type, "outcome": outcome},
                "retention_policy": retention_policy
            }
        )
    
    def to_correlation_data(self) -> Dict[str, Any]:
        """Convert TSDBGraphNode to correlation data format"""
        return {
            "timestamp": self.timestamp,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "log_level": self.log_level,
            "log_message": self.log_message,
            "data_type": self.data_type,
            "tags": self.tags,
            "retention_policy": self.retention_policy,
            "scope": self.scope.value
        }
