"""
Graph node type schemas for CIRIS.

These define all the specialized node types that can be stored in the graph.
Everything in the graph is a memory - these are the different types of memories.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.services.graph_typed_nodes import TypedGraphNode, register_node_type

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.core import AgentIdentityRoot


class AuditEntryContext(BaseModel):
    """Typed context for audit entries."""

    service_name: Optional[str] = None
    method_name: Optional[str] = None
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    additional_data: Optional[Dict[str, Union[str, int, float, bool]]] = None


@register_node_type("AUDIT_ENTRY")
class AuditEntry(TypedGraphNode):
    """An audit trail entry stored as a graph memory."""

    action: str = Field(..., description="The action that was performed")
    actor: str = Field(..., description="Who/what performed the action")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    context: AuditEntryContext = Field(..., description="Typed action context")
    signature: Optional[str] = Field(None, description="Cryptographic signature if signed")
    hash_chain: Optional[str] = Field(None, description="Previous hash for chain integrity")

    # Required TypedGraphNode fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="audit_service")
    updated_by: str = Field(default="audit_service")

    # Graph node type
    type: NodeType = Field(default=NodeType.AUDIT_ENTRY)

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        # Get all fields
        all_attrs = self.model_dump()

        # Extract base GraphNode fields
        node_id = all_attrs.get("id", f"audit_{self.timestamp.strftime('%Y%m%d_%H%M%S')}_{self.actor}")
        node_type = self.type
        node_scope = all_attrs.get("scope", GraphScope.LOCAL)

        # Build attributes dict with only extra fields
        extra_fields = {
            # Required GraphNodeAttributes fields
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "tags": [f"actor:{self.actor}", f"action:{self.action}"],
            # AuditEntry specific fields
            "action": self.action,
            "actor": self.actor,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context.model_dump(),
            "signature": self.signature,
            "hash_chain": self.hash_chain,
            "node_class": "AuditEntry",
        }

        return GraphNode(
            id=node_id,
            type=node_type,
            scope=node_scope,
            attributes=extra_fields,
            version=all_attrs.get("version", 1),
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "AuditEntry":
        """Reconstruct from GraphNode."""
        # Handle both dict and GraphNodeAttributes
        if isinstance(node.attributes, dict):
            attrs = node.attributes
        elif hasattr(node.attributes, "model_dump"):
            attrs = node.attributes.model_dump()
        else:
            raise ValueError(f"Invalid attributes type: {type(node.attributes)}")

        # Deserialize timestamp
        now = datetime.now(timezone.utc)
        timestamp = cls._deserialize_datetime(attrs.get("timestamp", attrs.get("created_at"))) or now
        created_at = cls._deserialize_datetime(attrs.get("created_at", attrs.get("timestamp"))) or now
        updated_at = cls._deserialize_datetime(attrs.get("updated_at", attrs.get("created_at"))) or now

        # Deserialize context
        context_data = attrs.get("context", {})
        if isinstance(context_data, dict):
            context = AuditEntryContext(**context_data)
        else:
            context = AuditEntryContext()

        return cls(
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=node.attributes,  # Pass through the attributes
            action=attrs.get("action", "unknown"),
            actor=attrs.get("actor", "unknown"),
            timestamp=timestamp,
            context=context,
            signature=attrs.get("signature"),
            hash_chain=attrs.get("hash_chain"),
            created_at=created_at,
            updated_at=updated_at,
            created_by=attrs.get("created_by", "audit_service"),
            updated_by=attrs.get("updated_by", "audit_service"),
            version=node.version,
        )


class ConfigValue(BaseModel):
    """Typed configuration value wrapper."""

    string_value: Optional[str] = None
    int_value: Optional[int] = None
    float_value: Optional[float] = None
    bool_value: Optional[bool] = None
    list_value: Optional[List[Union[str, int, float, bool]]] = None
    dict_value: Optional[Dict[str, Union[str, int, float, bool, list, dict, None]]] = None  # Allow None values in dict

    @property
    def value(
        self,
    ) -> Optional[
        Union[
            str,
            int,
            float,
            bool,
            List[Union[str, int, float, bool]],
            Dict[str, Union[str, int, float, bool, list, dict, None]],
        ]
    ]:
        """Get the actual value."""
        # Check each field in order
        if self.string_value is not None:
            return self.string_value
        elif self.int_value is not None:
            return self.int_value
        elif self.float_value is not None:
            return self.float_value
        elif self.bool_value is not None:
            return self.bool_value
        elif self.list_value is not None:
            return self.list_value
        elif self.dict_value is not None:
            return self.dict_value
        return None


@register_node_type("config")
class ConfigNode(TypedGraphNode):
    """A configuration value stored as a graph memory with versioning."""

    key: str = Field(..., description="Configuration key")
    value: ConfigValue = Field(..., description="Typed configuration value")
    version: int = Field(default=1, description="Version number")
    updated_by: str = Field(..., description="Who updated this config")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    previous_version: Optional[str] = Field(None, description="Node ID of previous version")

    # Graph node type - use the enum value
    type: NodeType = Field(default=NodeType.CONFIG)

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        # Include both GraphNodeAttributes required fields AND ConfigNode extra fields
        extra_fields = {
            # Required GraphNodeAttributes fields
            "created_at": self.updated_at.isoformat(),  # Use updated_at as created_at
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.updated_by,
            "tags": [f"config:{self.key.split('.')[0]}"],
            # ConfigNode specific fields
            "key": self.key,
            "value": self.value.model_dump(),
            # Don't duplicate version in attributes - it's already in GraphNode.version
            "previous_version": self.previous_version,
            "node_class": "ConfigNode",
        }

        return GraphNode(
            id=f"config:{self.key}",
            type=self.type,
            scope=GraphScope.LOCAL,  # Config default to LOCAL scope
            attributes=extra_fields,
            version=self.version,
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "ConfigNode":
        """Reconstruct from GraphNode."""
        # Handle both dict and GraphNodeAttributes
        if isinstance(node.attributes, dict):
            attrs = node.attributes
        elif hasattr(node.attributes, "model_dump"):
            attrs = node.attributes.model_dump()
        else:
            raise ValueError(f"Invalid attributes type: {type(node.attributes)}")

        # Parse dates with multiple fallbacks
        updated_at = cls._deserialize_datetime(attrs.get("updated_at"))
        if not updated_at:
            # Try created_at as fallback
            updated_at = cls._deserialize_datetime(attrs.get("created_at"))

        # Get updated_by with fallback
        updated_by = attrs.get("updated_by") or attrs.get("created_by", "system")

        return cls(
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=node.attributes,  # Must pass this for GraphNode base class
            version=node.version,  # Use GraphNode's version, not from attributes
            updated_by=updated_by,
            updated_at=updated_at or datetime.now(timezone.utc),  # Final fallback
            # Extra fields from attributes
            key=attrs["key"],
            value=ConfigValue(**attrs["value"]),
            previous_version=attrs.get("previous_version"),
        )


@register_node_type("IDENTITY_SNAPSHOT")
class IdentitySnapshot(TypedGraphNode):
    """Snapshot of identity state for variance monitoring."""

    snapshot_id: str = Field(..., description="Unique snapshot ID")
    timestamp: datetime = Field(..., description="When snapshot was taken")
    agent_id: str = Field(..., description="Agent ID")
    identity_hash: str = Field(..., description="Identity hash at time of snapshot")
    core_purpose: str = Field(..., description="Core purpose")
    role: str = Field(..., description="Role description")
    permitted_actions: List[str] = Field(default_factory=list, description="Permitted actions")
    restricted_capabilities: List[str] = Field(default_factory=list, description="Restricted capabilities")
    ethical_boundaries: List[str] = Field(default_factory=list, description="Ethical boundaries")
    trust_parameters: Dict[str, str] = Field(default_factory=dict, description="Trust parameters")
    personality_traits: List[str] = Field(default_factory=list, description="Personality traits")
    communication_style: str = Field(..., description="Communication style")
    learning_enabled: bool = Field(..., description="Whether learning is enabled")
    adaptation_rate: float = Field(..., description="Rate of adaptation")
    is_baseline: bool = Field(default=False, description="Whether this is a baseline snapshot")

    # Additional fields from other versions
    behavioral_patterns: Dict[str, float] = Field(default_factory=dict, description="Behavioral pattern scores")
    config_preferences: Dict[str, str] = Field(default_factory=dict, description="Configuration preferences")
    attributes: dict = Field(default_factory=dict, description="Additional attributes")
    reason: str = Field(default="", description="Why snapshot was taken")
    system_state: Optional[Dict[str, str]] = Field(None, description="System state at snapshot time")
    active_tasks: List[str] = Field(default_factory=list, description="Active tasks at time")
    expires_at: Optional[datetime] = Field(None, description="When snapshot expires")
    tags: List[str] = Field(default_factory=list, description="Snapshot tags")
    identity_root: Optional[Dict[str, Any]] = Field(None, description="Complete identity data at time")

    # Required TypedGraphNode fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="identity_variance_monitor")
    updated_by: str = Field(default="identity_variance_monitor")

    # Graph node type
    type: NodeType = Field(default=NodeType.IDENTITY_SNAPSHOT)

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        extra_fields = {
            # Required GraphNodeAttributes fields
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "tags": ["identity_snapshot", f"agent:{self.agent_id}"],
            # IdentitySnapshot specific fields
            "snapshot_id": self.snapshot_id,
            "timestamp": self.timestamp.isoformat(),
            "agent_id": self.agent_id,
            "identity_hash": self.identity_hash,
            "core_purpose": self.core_purpose,
            "role": self.role,
            "permitted_actions": self.permitted_actions,
            "restricted_capabilities": self.restricted_capabilities,
            "ethical_boundaries": self.ethical_boundaries,
            "trust_parameters": self.trust_parameters,
            "personality_traits": self.personality_traits,
            "communication_style": self.communication_style,
            "learning_enabled": self.learning_enabled,
            "adaptation_rate": self.adaptation_rate,
            "is_baseline": self.is_baseline,
            # Additional fields
            "behavioral_patterns": self.behavioral_patterns,
            "config_preferences": self.config_preferences,
            "attributes": self.attributes,
            "reason": self.reason,
            "system_state": self.system_state,
            "active_tasks": self.active_tasks,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "tags": self.tags or [],
            "identity_root": self.identity_root,
            "node_class": "IdentitySnapshot",
        }

        return GraphNode(
            id=f"identity_snapshot:{self.snapshot_id}",
            type=self.type,
            scope=GraphScope.IDENTITY,  # Identity snapshots are IDENTITY scope
            attributes=extra_fields,
            version=1,
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "IdentitySnapshot":
        """Reconstruct from GraphNode."""
        attrs = node.attributes if isinstance(node.attributes, dict) else node.attributes.model_dump()

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=attrs,  # Use the dict version we already extracted
            version=node.version,
            updated_by=node.updated_by or "identity_variance_monitor",
            updated_at=node.updated_at or datetime.now(timezone.utc),
            # Extra fields from attributes
            snapshot_id=attrs["snapshot_id"],
            timestamp=cls._deserialize_datetime(attrs["timestamp"]) or datetime.now(timezone.utc),
            agent_id=attrs["agent_id"],
            identity_hash=attrs["identity_hash"],
            core_purpose=attrs["core_purpose"],
            role=attrs["role"],
            permitted_actions=attrs.get("permitted_actions", []),
            restricted_capabilities=attrs.get("restricted_capabilities", []),
            ethical_boundaries=attrs.get("ethical_boundaries", []),
            trust_parameters=attrs.get("trust_parameters", {}),
            personality_traits=attrs.get("personality_traits", []),
            communication_style=attrs["communication_style"],
            learning_enabled=attrs["learning_enabled"],
            adaptation_rate=attrs["adaptation_rate"],
            is_baseline=attrs.get("is_baseline", False),
            # Additional fields
            behavioral_patterns=attrs.get("behavioral_patterns", {}),
            config_preferences=attrs.get("config_preferences", {}),
            reason=attrs.get("reason", ""),
            system_state=attrs.get("system_state"),
            active_tasks=attrs.get("active_tasks", []),
            expires_at=cls._deserialize_datetime(attrs.get("expires_at")) if attrs.get("expires_at") else None,
            tags=attrs.get("tags", []),
            identity_root=attrs.get("identity_root"),
            created_at=cls._deserialize_datetime(attrs.get("created_at")) or datetime.now(timezone.utc),
            created_by=attrs.get("created_by", "identity_variance_monitor"),
        )


@register_node_type("TSDB_SUMMARY")
class TSDBSummary(TypedGraphNode):
    """Consolidated time-series telemetry summary stored as a graph memory."""

    # Period information
    period_start: datetime = Field(..., description="Start of the consolidation period")
    period_end: datetime = Field(..., description="End of the consolidation period")
    period_label: str = Field(..., description="Human-readable period label")

    # Aggregated metrics by category
    metrics: Dict[str, Dict[str, float]] = Field(default_factory=dict, description="Aggregated metrics by category")

    # Resource totals
    total_tokens: int = Field(0, description="Total tokens used in period")
    total_cost_cents: float = Field(0.0, description="Total cost in cents")
    total_carbon_grams: float = Field(0.0, description="Total carbon emissions in grams")
    total_energy_kwh: float = Field(0.0, description="Total energy used in kWh")

    # Action summary
    action_counts: Dict[str, int] = Field(default_factory=dict, description="Count of each action type")
    error_count: int = Field(0, description="Total errors in period")
    success_rate: float = Field(1.0, description="Success rate (0-1)")

    # Metadata
    source_node_count: int = Field(..., description="Number of source nodes consolidated")
    consolidation_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw_data_expired: bool = Field(False, description="Whether raw data has been deleted")

    # Required TypedGraphNode fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="TSDBConsolidationService")
    updated_by: str = Field(default="TSDBConsolidationService")

    # Graph node type
    type: NodeType = Field(default=NodeType.TSDB_SUMMARY)

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        extra_fields = {
            # Required GraphNodeAttributes fields
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "tags": [f"period:{self.period_label}", "tsdb_summary"],
            # TSDBSummary specific fields
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_label": self.period_label,
            "metrics": self.metrics,
            "total_tokens": self.total_tokens,
            "total_cost_cents": self.total_cost_cents,
            "total_carbon_grams": self.total_carbon_grams,
            "total_energy_kwh": self.total_energy_kwh,
            "action_counts": self.action_counts,
            "error_count": self.error_count,
            "success_rate": self.success_rate,
            "source_node_count": self.source_node_count,
            "consolidation_timestamp": self.consolidation_timestamp.isoformat(),
            "raw_data_expired": self.raw_data_expired,
            "node_class": "TSDBSummary",
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
    def from_graph_node(cls, node: GraphNode) -> "TSDBSummary":
        """Reconstruct from GraphNode."""
        attrs = node.attributes if isinstance(node.attributes, dict) else {}

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=node.attributes,  # Must pass this for GraphNode base class
            version=node.version,
            updated_by=node.updated_by or "tsdb_consolidation",
            updated_at=node.updated_at or datetime.now(timezone.utc),
            # Extra fields from attributes
            period_start=cls._deserialize_datetime(attrs["period_start"]) or datetime.now(timezone.utc),
            period_end=cls._deserialize_datetime(attrs["period_end"]) or datetime.now(timezone.utc),
            period_label=attrs["period_label"],
            metrics=attrs.get("metrics", {}),
            total_tokens=attrs.get("total_tokens", 0),
            total_cost_cents=attrs.get("total_cost_cents", 0.0),
            total_carbon_grams=attrs.get("total_carbon_grams", 0.0),
            total_energy_kwh=attrs.get("total_energy_kwh", 0.0),
            action_counts=attrs.get("action_counts", {}),
            error_count=attrs.get("error_count", 0),
            success_rate=attrs.get("success_rate", 1.0),
            source_node_count=attrs["source_node_count"],
            consolidation_timestamp=cls._deserialize_datetime(attrs.get("consolidation_timestamp"))
            or datetime.now(timezone.utc),
            raw_data_expired=attrs.get("raw_data_expired", False),
        )


@register_node_type("IDENTITY")
class IdentityNode(TypedGraphNode):
    """Agent identity stored as a graph memory - the core of the system."""

    # Identity fields from AgentIdentityRoot
    agent_id: str = Field(..., description="Unique agent identifier")
    identity_hash: str = Field(..., description="Hash of identity for integrity")

    # Core profile fields from CoreProfile
    description: str = Field(..., description="Agent's self-description")
    role_description: str = Field(..., description="Agent's role and purpose")
    domain_specific_knowledge: Dict[str, str] = Field(default_factory=dict, description="Domain expertise mappings")
    areas_of_expertise: List[str] = Field(default_factory=list, description="Areas where agent has expertise")
    startup_instructions: Optional[str] = Field(None, description="Instructions for startup")

    # Capabilities and permissions from AgentIdentityRoot
    permitted_actions: List[str] = Field(default_factory=list, description="Actions this agent can perform")
    restricted_capabilities: List[str] = Field(default_factory=list, description="Explicitly restricted capabilities")

    # Trust and authorization from AgentIdentityRoot
    trust_level: float = Field(0.5, ge=0.0, le=1.0, description="Agent trust level")
    authorization_scope: str = Field("standard", description="Authorization scope")
    parent_agent_id: Optional[str] = Field(None, description="Parent agent if spawned")

    # Identity metadata
    identity_created_at: datetime = Field(..., description="When identity was created")
    identity_modified_at: datetime = Field(..., description="When identity was last modified")
    modification_count: int = Field(default=0, description="Number of modifications")
    creator_agent_id: str = Field(..., description="Who created this identity")
    lineage_trace: List[str] = Field(default_factory=list, description="Lineage of creators")
    approval_required: bool = Field(default=True, description="Whether changes need approval")
    approved_by: Optional[str] = Field(None, description="Who approved this identity")
    approval_timestamp: Optional[datetime] = Field(None, description="When approved")

    # Required TypedGraphNode fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="system")
    updated_by: str = Field(default="system")

    # Graph node type
    type: NodeType = Field(default=NodeType.AGENT)
    scope: GraphScope = Field(default=GraphScope.IDENTITY)

    # Base GraphNode fields (required by TypedGraphNode)
    id: str = Field(default="agent/identity", description="Node ID")
    attributes: Union[GraphNodeAttributes, Dict[str, Any]] = Field(default_factory=dict, description="Raw attributes")
    version: int = Field(default=1, description="Version number")

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        # Pack all identity data into attributes
        extra_fields = {
            # Required GraphNodeAttributes fields
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by": self.created_by,
            "tags": ["identity:root", f"agent:{self.agent_id}"],
            # Identity fields
            "agent_id": self.agent_id,
            "identity_hash": self.identity_hash,
            "trust_level": self.trust_level,
            "authorization_scope": self.authorization_scope,
            "parent_agent_id": self.parent_agent_id,
            # Core profile fields
            "description": self.description,
            "role_description": self.role_description,
            "domain_specific_knowledge": self.domain_specific_knowledge,
            "areas_of_expertise": self.areas_of_expertise,
            "startup_instructions": self.startup_instructions,
            # Capabilities and permissions
            "permitted_actions": self.permitted_actions,
            "restricted_capabilities": self.restricted_capabilities,
            # Identity metadata
            "identity_created_at": self.identity_created_at.isoformat(),
            "identity_modified_at": self.identity_modified_at.isoformat(),
            "modification_count": self.modification_count,
            "creator_agent_id": self.creator_agent_id,
            "lineage_trace": self.lineage_trace,
            "approval_required": self.approval_required,
            "approved_by": self.approved_by,
            "approval_timestamp": self.approval_timestamp.isoformat() if self.approval_timestamp else None,
            "node_class": "IdentityNode",
        }

        return GraphNode(
            id="agent/identity",  # Always the same ID - there's only one identity
            type=self.type,
            scope=self.scope,
            attributes=extra_fields,
            version=self.modification_count + 1,  # Version tracks modifications
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "IdentityNode":
        """Reconstruct from GraphNode."""
        # Handle both dict and GraphNodeAttributes
        if isinstance(node.attributes, dict):
            attrs = node.attributes
        elif hasattr(node.attributes, "model_dump"):
            attrs = node.attributes.model_dump()
        else:
            raise ValueError(f"Invalid attributes type: {type(node.attributes)}")

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            attributes=node.attributes,
            version=node.version,
            updated_by=node.updated_by or attrs.get("updated_by", "system"),
            updated_at=cls._deserialize_datetime(node.updated_at or attrs.get("updated_at"))
            or datetime.now(timezone.utc),
            # Required fields
            created_at=cls._deserialize_datetime(attrs.get("created_at")) or datetime.now(timezone.utc),
            created_by=attrs.get("created_by", "system"),
            # Identity fields
            agent_id=attrs["agent_id"],
            identity_hash=attrs["identity_hash"],
            trust_level=attrs.get("trust_level", 0.5),
            authorization_scope=attrs.get("authorization_scope", "standard"),
            parent_agent_id=attrs.get("parent_agent_id"),
            # Core profile fields
            description=attrs["description"],
            role_description=attrs["role_description"],
            domain_specific_knowledge=attrs.get("domain_specific_knowledge", {}),
            areas_of_expertise=attrs.get("areas_of_expertise", []),
            startup_instructions=attrs.get("startup_instructions"),
            # Capabilities and permissions
            permitted_actions=attrs.get("permitted_actions", []),
            restricted_capabilities=attrs.get("restricted_capabilities", []),
            # Identity metadata
            identity_created_at=cls._deserialize_datetime(attrs["identity_created_at"]) or datetime.now(timezone.utc),
            identity_modified_at=cls._deserialize_datetime(attrs["identity_modified_at"]) or datetime.now(timezone.utc),
            modification_count=attrs.get("modification_count", 0),
            creator_agent_id=attrs["creator_agent_id"],
            lineage_trace=attrs.get("lineage_trace", []),
            approval_required=attrs.get("approval_required", True),
            approved_by=attrs.get("approved_by"),
            approval_timestamp=(
                cls._deserialize_datetime(attrs.get("approval_timestamp")) if attrs.get("approval_timestamp") else None
            ),
        )

    @classmethod
    def from_agent_identity_root(cls, identity: "AgentIdentityRoot", time_service: Any) -> "IdentityNode":
        """Create from AgentIdentityRoot object."""

        now = time_service.now()
        return cls(
            agent_id=identity.agent_id,
            identity_hash=identity.identity_hash,
            trust_level=identity.trust_level,
            authorization_scope=identity.authorization_scope,
            parent_agent_id=identity.parent_agent_id,
            # Core profile
            description=identity.core_profile.description,
            role_description=identity.core_profile.role_description,
            domain_specific_knowledge=identity.core_profile.domain_specific_knowledge,
            areas_of_expertise=identity.core_profile.areas_of_expertise,
            startup_instructions=identity.core_profile.startup_instructions,
            # Capabilities and permissions
            permitted_actions=identity.permitted_actions,
            restricted_capabilities=identity.restricted_capabilities,
            # Metadata
            identity_created_at=identity.identity_metadata.created_at if identity.identity_metadata else now,
            identity_modified_at=identity.identity_metadata.last_modified if identity.identity_metadata else now,
            modification_count=identity.identity_metadata.modification_count if identity.identity_metadata else 0,
            creator_agent_id=identity.identity_metadata.creator_agent_id if identity.identity_metadata else "system",
            lineage_trace=identity.identity_metadata.lineage_trace if identity.identity_metadata else ["system"],
            approval_required=identity.identity_metadata.approval_required if identity.identity_metadata else True,
            approved_by=identity.identity_metadata.approved_by if identity.identity_metadata else None,
            approval_timestamp=identity.identity_metadata.approval_timestamp if identity.identity_metadata else None,
            created_at=now,
            updated_at=now,
            created_by="system",
            updated_by="system",
        )

    def to_agent_identity_root(self) -> "AgentIdentityRoot":
        """Convert back to AgentIdentityRoot."""
        from ciris_engine.schemas.runtime.core import AgentIdentityRoot, CoreProfile, IdentityMetadata

        return AgentIdentityRoot(
            agent_id=self.agent_id,
            identity_hash=self.identity_hash,
            core_profile=CoreProfile(
                description=self.description,
                role_description=self.role_description,
                domain_specific_knowledge=self.domain_specific_knowledge,
                areas_of_expertise=self.areas_of_expertise,
                startup_instructions=self.startup_instructions,
                dsdma_prompt_template=None,
                csdma_overrides={},
                action_selection_pdma_overrides={},
                last_shutdown_memory=None,
            ),
            identity_metadata=IdentityMetadata(
                created_at=self.identity_created_at,
                last_modified=self.identity_modified_at,
                modification_count=self.modification_count,
                creator_agent_id=self.creator_agent_id,
                lineage_trace=self.lineage_trace,
                approval_required=self.approval_required,
                approved_by=self.approved_by,
                approval_timestamp=self.approval_timestamp,
                version=CIRIS_VERSION,
                previous_versions=[],
            ),
            permitted_actions=self.permitted_actions,
            restricted_capabilities=self.restricted_capabilities,
            capability_definitions={},
            trust_level=self.trust_level,
            authorization_scope=self.authorization_scope,
            parent_agent_id=self.parent_agent_id,
            child_agent_ids=[],
        )
