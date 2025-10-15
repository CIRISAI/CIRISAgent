"""
Audit summary nodes for consolidating audit events.

These nodes store a hash of audit events from each period to prove
the audit trail existed without duplicating the permanent audit data.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Union

from pydantic import Field

from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.graph_typed_nodes import TypedGraphNode, register_node_type
from ciris_engine.schemas.types import JSONDict


@register_node_type("AUDIT_SUMMARY")
class AuditSummaryNode(TypedGraphNode):
    """
    Consolidated audit summary for a time period.

    Stores a cryptographic hash of all audit events in the period
    to prove the audit trail's existence and integrity without
    duplicating the permanent audit records.
    """

    # Period information
    period_start: datetime = Field(..., description="Start of the consolidation period")
    period_end: datetime = Field(..., description="End of the consolidation period")
    period_label: str = Field(..., description="Human-readable period label")

    # Audit hash - the main purpose
    audit_hash: str = Field(..., description="SHA-256 hash of all audit event IDs in chronological order")
    hash_algorithm: str = Field(default="sha256", description="Algorithm used for hashing")

    # Basic metrics (without storing actual events)
    total_audit_events: int = Field(0, description="Total number of audit events")
    events_by_type: Dict[str, int] = Field(default_factory=dict, description="Count of events by type")
    events_by_actor: Dict[str, int] = Field(default_factory=dict, description="Count of events by actor")
    events_by_service: Dict[str, int] = Field(default_factory=dict, description="Count of events by service")

    # Security indicators
    failed_auth_attempts: int = Field(0, description="Number of failed auth attempts")
    permission_denials: int = Field(0, description="Number of permission denials")
    emergency_shutdowns: int = Field(0, description="Number of emergency shutdowns")
    config_changes: int = Field(0, description="Number of configuration changes")

    # Summary metadata
    first_event_id: Optional[str] = Field(None, description="ID of first event in period")
    last_event_id: Optional[str] = Field(None, description="ID of last event in period")
    source_correlation_count: int = Field(0, description="Number of AUDIT_EVENT correlations")
    consolidation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When this summary was created"
    )

    # Required TypedGraphNode fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="TSDBConsolidationService")
    updated_by: str = Field(default="TSDBConsolidationService")

    # Graph node type
    type: NodeType = Field(default=NodeType.TSDB_SUMMARY)
    scope: GraphScope = Field(default=GraphScope.LOCAL)
    id: str = Field(..., description="Node ID")
    version: int = Field(default=1)
    attributes: JSONDict = Field(default_factory=dict, description="Node attributes")

    @staticmethod
    def compute_audit_hash(event_ids: list[str], algorithm: str = "sha256") -> str:
        """
        Compute a cryptographic hash of audit event IDs.

        Args:
            event_ids: List of audit event IDs in chronological order
            algorithm: Hash algorithm to use (default: sha256)

        Returns:
            Hex string of the hash
        """
        # Sort to ensure deterministic hash
        sorted_ids = sorted(event_ids)

        # Create hash
        if algorithm == "sha256":
            hasher = hashlib.sha256()
        else:
            raise ValueError(f"Unsupported hash algorithm: {algorithm}")

        # Hash the JSON representation for consistency
        hasher.update(json.dumps(sorted_ids).encode("utf-8"))
        return hasher.hexdigest()

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        extra_fields = {
            # Period info
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_label": self.period_label,
            # Audit hash
            "audit_hash": self.audit_hash,
            "hash_algorithm": self.hash_algorithm,
            # Metrics
            "total_audit_events": self.total_audit_events,
            "events_by_type": self.events_by_type,
            "events_by_actor": self.events_by_actor,
            "events_by_service": self.events_by_service,
            # Security indicators
            "failed_auth_attempts": self.failed_auth_attempts,
            "permission_denials": self.permission_denials,
            "emergency_shutdowns": self.emergency_shutdowns,
            "config_changes": self.config_changes,
            # Metadata
            "first_event_id": self.first_event_id,
            "last_event_id": self.last_event_id,
            "source_correlation_count": self.source_correlation_count,
            "consolidation_timestamp": self.consolidation_timestamp.isoformat(),
            # Type hint
            "node_class": "AuditSummaryNode",
        }

        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=extra_fields,
            version=self.version,
            updated_by=self.updated_by or "TSDBConsolidationService",
            updated_at=self.updated_at or self.consolidation_timestamp,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "AuditSummaryNode":
        """Reconstruct from GraphNode."""
        attrs = node.attributes if isinstance(node.attributes, dict) else {}

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            version=node.version,
            updated_by=node.updated_by,
            updated_at=node.updated_at,
            # Period info
            period_start=cls._deserialize_datetime(attrs.get("period_start")),
            period_end=cls._deserialize_datetime(attrs.get("period_end")),
            period_label=attrs.get("period_label", ""),
            # Audit hash
            audit_hash=attrs.get("audit_hash", ""),
            hash_algorithm=attrs.get("hash_algorithm", "sha256"),
            # Metrics
            total_audit_events=attrs.get("total_audit_events", 0),
            events_by_type=attrs.get("events_by_type", {}),
            events_by_actor=attrs.get("events_by_actor", {}),
            events_by_service=attrs.get("events_by_service", {}),
            # Security indicators
            failed_auth_attempts=attrs.get("failed_auth_attempts", 0),
            permission_denials=attrs.get("permission_denials", 0),
            emergency_shutdowns=attrs.get("emergency_shutdowns", 0),
            config_changes=attrs.get("config_changes", 0),
            # Metadata
            first_event_id=attrs.get("first_event_id"),
            last_event_id=attrs.get("last_event_id"),
            source_correlation_count=attrs.get("source_correlation_count", 0),
            consolidation_timestamp=cls._deserialize_datetime(attrs.get("consolidation_timestamp"))
            or datetime.now(timezone.utc),
        )
