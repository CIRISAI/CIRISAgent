"""
Incident management schemas for graph-based incident tracking.

These schemas support ITIL-aligned incident processing for self-improvement.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import Field
from enum import Enum

from ciris_engine.schemas.services.graph_core import GraphNode, NodeType, GraphScope
from ciris_engine.schemas.services.graph_typed_nodes import TypedGraphNode, register_node_type

class IncidentSeverity(str, Enum):
    """Incident severity levels aligned with ITIL."""
    CRITICAL = "CRITICAL"  # Service down, major impact
    HIGH = "HIGH"         # Significant degradation
    MEDIUM = "MEDIUM"     # Minor degradation
    LOW = "LOW"           # Informational

class IncidentStatus(str, Enum):
    """Incident lifecycle status."""
    OPEN = "OPEN"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"
    RECURRING = "RECURRING"  # Linked to a problem

@register_node_type("INCIDENT")
class IncidentNode(TypedGraphNode):
    """Represents an incident captured from WARNING/ERROR logs."""

    # Base fields (inherited from GraphNode)
    type: str = Field(default=NodeType.AUDIT_ENTRY, description="Node type")
    scope: GraphScope = Field(default=GraphScope.LOCAL, description="Node scope")

    # Incident specific fields (stored in attributes)
    incident_type: str = Field(..., description="Type of incident (ERROR, WARNING, EXCEPTION)")
    severity: IncidentSeverity = Field(..., description="Incident severity")
    status: IncidentStatus = Field(IncidentStatus.OPEN, description="Current incident status")

    # Incident details
    description: str = Field(..., description="Incident description from log message")
    source_component: str = Field(..., description="Component that generated the incident")
    detection_method: str = Field("AUTOMATED_LOG_MONITORING", description="How incident was detected")

    # Timing
    detected_at: datetime = Field(..., description="When incident was detected")
    resolved_at: Optional[datetime] = Field(None, description="When incident was resolved")

    # Impact assessment
    impact: Optional[str] = Field(None, description="Business/operational impact")
    urgency: Optional[str] = Field(None, description="How quickly this needs attention")

    # Tracing data (correlation with other system components)
    correlation_id: Optional[str] = Field(None, description="Correlation ID for distributed tracing")
    task_id: Optional[str] = Field(None, description="Related task ID if applicable")
    thought_id: Optional[str] = Field(None, description="Related thought ID if applicable")
    handler_name: Optional[str] = Field(None, description="Handler that was executing")

    # Technical details
    exception_type: Optional[str] = Field(None, description="Exception class name if applicable")
    stack_trace: Optional[str] = Field(None, description="Stack trace if available")
    filename: str = Field(..., description="Source file")
    line_number: int = Field(..., description="Line number")
    function_name: Optional[str] = Field(None, description="Function name")

    # Relationships
    problem_id: Optional[str] = Field(None, description="Linked problem if this is recurring")
    related_incidents: List[str] = Field(default_factory=list, description="Related incident IDs")

    def to_graph_node(self) -> GraphNode:
        """Convert to generic GraphNode for storage."""
        # Serialize extra fields only
        extra_data = self._serialize_extra_fields()

        # Handle datetime fields
        if self.detected_at:
            extra_data["detected_at"] = self.detected_at.isoformat()
        if self.resolved_at:
            extra_data["resolved_at"] = self.resolved_at.isoformat()

        # Handle enums
        extra_data["severity"] = self.severity.value
        extra_data["status"] = self.status.value

        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=extra_data,
            version=self.version,
            updated_by=self.updated_by,
            updated_at=self.updated_at
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> 'IncidentNode':
        """Reconstruct from GraphNode."""
        attrs = node.attributes.copy()
        attrs.pop("_node_class", None)

        # Handle datetime deserialization
        if "detected_at" in attrs:
            attrs["detected_at"] = cls._deserialize_datetime(attrs["detected_at"])
        if "resolved_at" in attrs:
            attrs["resolved_at"] = cls._deserialize_datetime(attrs["resolved_at"])

        # Handle enum deserialization
        if "severity" in attrs:
            attrs["severity"] = IncidentSeverity(attrs["severity"])
        if "status" in attrs:
            attrs["status"] = IncidentStatus(attrs["status"])

        # Fall back to values from attributes if the GraphNode fields are None
        updated_by = node.updated_by or attrs.get("created_by", "unknown")
        updated_at = node.updated_at or cls._deserialize_datetime(attrs.get("updated_at", attrs.get("created_at")))

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=node.attributes,  # Must pass this for GraphNode base class
            version=node.version,
            updated_by=updated_by,
            updated_at=updated_at or datetime.now(timezone.utc),
            # Extra fields from attributes
            **attrs
        )

@register_node_type("PROBLEM")
class ProblemNode(TypedGraphNode):
    """Represents a problem (root cause) identified from incident patterns."""

    # Base fields
    type: str = Field(default=NodeType.CONCEPT, description="Node type")
    scope: GraphScope = Field(default=GraphScope.IDENTITY, description="Node scope")

    problem_statement: str = Field(..., description="Description of the problem")
    affected_incidents: List[str] = Field(..., description="Incident IDs linked to this problem")
    status: str = Field("UNDER_INVESTIGATION", description="Problem status")

    # Analysis
    potential_root_causes: List[str] = Field(default_factory=list, description="Possible root causes")
    recommended_actions: List[str] = Field(default_factory=list, description="Suggested fixes")

    # Metrics
    incident_count: int = Field(..., description="Number of related incidents")
    first_occurrence: datetime = Field(..., description="When first incident occurred")
    last_occurrence: datetime = Field(..., description="Most recent incident")

    # Resolution
    resolution: Optional[str] = Field(None, description="How the problem was resolved")
    resolved_at: Optional[datetime] = Field(None, description="When problem was resolved")

    def to_graph_node(self) -> GraphNode:
        """Convert to generic GraphNode for storage."""
        extra_data = self._serialize_extra_fields()

        # Handle datetime fields
        if self.first_occurrence:
            extra_data["first_occurrence"] = self.first_occurrence.isoformat()
        if self.last_occurrence:
            extra_data["last_occurrence"] = self.last_occurrence.isoformat()
        if self.resolved_at:
            extra_data["resolved_at"] = self.resolved_at.isoformat()

        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=extra_data,
            version=self.version,
            updated_by=self.updated_by,
            updated_at=self.updated_at
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> 'ProblemNode':
        """Reconstruct from GraphNode."""
        attrs = node.attributes.copy()
        attrs.pop("_node_class", None)

        # Handle datetime deserialization
        if "first_occurrence" in attrs:
            attrs["first_occurrence"] = cls._deserialize_datetime(attrs["first_occurrence"])
        if "last_occurrence" in attrs:
            attrs["last_occurrence"] = cls._deserialize_datetime(attrs["last_occurrence"])
        if "resolved_at" in attrs:
            attrs["resolved_at"] = cls._deserialize_datetime(attrs["resolved_at"])

        # Fall back to values from attributes if the GraphNode fields are None
        updated_by = node.updated_by or attrs.get("created_by", "unknown")
        updated_at = node.updated_at or cls._deserialize_datetime(attrs.get("updated_at", attrs.get("created_at")))

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=node.attributes,
            version=node.version,
            updated_by=updated_by,
            updated_at=updated_at or datetime.now(timezone.utc),
            # Extra fields from attributes
            **attrs
        )

@register_node_type("INCIDENT_INSIGHT")
class IncidentInsightNode(TypedGraphNode):
    """Represents insights derived from incident analysis during dream cycles."""

    # Base fields
    type: str = Field(default=NodeType.CONCEPT, description="Node type")
    scope: GraphScope = Field(default=GraphScope.LOCAL, description="Node scope")

    insight_type: str = Field(..., description="Type of insight (PERIODIC_ANALYSIS, PATTERN_DETECTED, etc.)")
    summary: str = Field(..., description="High-level summary of the insight")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed analysis results")

    # Recommendations
    behavioral_adjustments: List[str] = Field(default_factory=list, description="Suggested behavioral changes")
    configuration_changes: List[str] = Field(default_factory=list, description="Suggested config changes")

    # Traceability
    source_incidents: List[str] = Field(default_factory=list, description="Incident IDs analyzed")
    source_problems: List[str] = Field(default_factory=list, description="Problem IDs referenced")
    analysis_timestamp: datetime = Field(..., description="When analysis was performed")

    # Effectiveness tracking
    applied: bool = Field(False, description="Whether recommendations were applied")
    effectiveness_score: Optional[float] = Field(None, description="How effective the changes were (0-1)")

    def to_graph_node(self) -> GraphNode:
        """Convert to generic GraphNode for storage."""
        extra_data = self._serialize_extra_fields()

        # Handle datetime fields
        if self.analysis_timestamp:
            extra_data["analysis_timestamp"] = self.analysis_timestamp.isoformat()

        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=extra_data,
            version=self.version,
            updated_by=self.updated_by,
            updated_at=self.updated_at
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> 'IncidentInsightNode':
        """Reconstruct from GraphNode."""
        attrs = node.attributes.copy()
        attrs.pop("_node_class", None)

        # Handle datetime deserialization
        if "analysis_timestamp" in attrs:
            attrs["analysis_timestamp"] = cls._deserialize_datetime(attrs["analysis_timestamp"])

        # Fall back to values from attributes if the GraphNode fields are None
        updated_by = node.updated_by or attrs.get("created_by", "unknown")
        updated_at = node.updated_at or cls._deserialize_datetime(attrs.get("updated_at", attrs.get("created_at")))

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=node.attributes,
            version=node.version,
            updated_by=updated_by,
            updated_at=updated_at or datetime.now(timezone.utc),
            # Extra fields from attributes
            **attrs
        )
