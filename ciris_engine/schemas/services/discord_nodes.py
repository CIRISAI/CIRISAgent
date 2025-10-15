"""Discord-specific graph node schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from ciris_engine.schemas.services.graph_core import GraphNode
from ciris_engine.schemas.services.graph_typed_nodes import TypedGraphNode, register_node_type
from ciris_engine.schemas.types import JSONDict as NodeAttributesDict


@register_node_type("DISCORD_DEFERRAL")
class DiscordDeferralNode(TypedGraphNode):
    """Represents a deferral stored in the graph."""

    type: str = Field(default="DISCORD_DEFERRAL", description="Node type")  # type: ignore[assignment]

    # Deferral details
    deferral_id: str = Field(..., description="Unique deferral ID")
    task_id: str = Field(..., description="Associated task ID")
    thought_id: str = Field(..., description="Associated thought ID")
    reason: str = Field(..., description="Reason for deferral")
    defer_until: datetime = Field(..., description="When to reconsider")

    # Discord specifics
    channel_id: str = Field(..., description="Discord channel ID")
    message_id: Optional[str] = Field(None, description="Discord message ID")

    # Resolution details
    status: str = Field(default="pending", description="Status: pending, resolved, expired")
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution: Optional[str] = None

    # Context
    context: NodeAttributesDict = Field(default_factory=dict, description="Deferral context metadata")

    def to_graph_node(self) -> GraphNode:
        """Convert to generic GraphNode for storage."""
        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=self._serialize_extra_fields(),
            version=self.version,
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "DiscordDeferralNode":
        """Reconstruct from generic GraphNode."""
        # Handle both dict and GraphNodeAttributes
        if isinstance(node.attributes, dict):
            attrs = node.attributes
        else:
            attrs = {}

        # Extract required fields with proper validation
        deferral_id = attrs.get("deferral_id")
        if not deferral_id:
            raise ValueError("Missing required field: deferral_id")

        task_id = attrs.get("task_id")
        if not task_id:
            raise ValueError("Missing required field: task_id")

        thought_id = attrs.get("thought_id")
        if not thought_id:
            raise ValueError("Missing required field: thought_id")

        reason = attrs.get("reason")
        if not reason:
            raise ValueError("Missing required field: reason")

        defer_until = cls._deserialize_datetime(attrs.get("defer_until"))
        if not defer_until:
            raise ValueError("Missing required field: defer_until")

        channel_id = attrs.get("channel_id")
        if not channel_id:
            raise ValueError("Missing required field: channel_id")

        return cls(
            id=node.id,
            type="DISCORD_DEFERRAL",  # Use literal type
            scope=node.scope,
            version=node.version,
            updated_by=node.updated_by,
            updated_at=node.updated_at,
            attributes=node.attributes,  # Pass through attributes
            # Extra fields from attributes
            deferral_id=deferral_id,
            task_id=task_id,
            thought_id=thought_id,
            reason=reason,
            defer_until=defer_until,
            channel_id=channel_id,
            message_id=attrs.get("message_id"),
            status=attrs.get("status", "pending"),
            resolved_at=cls._deserialize_datetime(attrs.get("resolved_at")),
            resolved_by=attrs.get("resolved_by"),
            resolution=attrs.get("resolution"),
            context=attrs.get("context", {}),
        )


@register_node_type("DISCORD_APPROVAL")
class DiscordApprovalNode(TypedGraphNode):
    """Represents an approval request stored in the graph."""

    type: str = Field(default="DISCORD_APPROVAL", description="Node type")  # type: ignore[assignment]

    # Approval details
    approval_id: str = Field(..., description="Unique approval ID")
    action: str = Field(..., description="Action requiring approval")
    request_type: str = Field(..., description="Type of approval request")

    # Discord specifics
    channel_id: str = Field(..., description="Discord channel ID")
    message_id: str = Field(..., description="Discord message ID")

    # Context
    task_id: Optional[str] = None
    thought_id: Optional[str] = None
    requester_id: str = Field(..., description="Who requested approval")

    # Resolution
    status: str = Field(default="pending", description="Status: pending, approved, denied, timeout")
    resolved_at: Optional[datetime] = None
    resolver_id: Optional[str] = None
    resolver_name: Optional[str] = None

    # Additional context
    context: NodeAttributesDict = Field(default_factory=dict, description="Approval context metadata")
    action_params: NodeAttributesDict = Field(default_factory=dict, description="Action parameters")

    def to_graph_node(self) -> GraphNode:
        """Convert to generic GraphNode for storage."""
        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=self._serialize_extra_fields(),
            version=self.version,
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "DiscordApprovalNode":
        """Reconstruct from generic GraphNode."""
        # Handle both dict and GraphNodeAttributes
        if isinstance(node.attributes, dict):
            attrs = node.attributes
        else:
            attrs = {}

        # Extract required fields with proper validation
        approval_id = attrs.get("approval_id")
        if not approval_id:
            raise ValueError("Missing required field: approval_id")

        action = attrs.get("action")
        if not action:
            raise ValueError("Missing required field: action")

        request_type = attrs.get("request_type")
        if not request_type:
            raise ValueError("Missing required field: request_type")

        channel_id = attrs.get("channel_id")
        if not channel_id:
            raise ValueError("Missing required field: channel_id")

        message_id = attrs.get("message_id")
        if not message_id:
            raise ValueError("Missing required field: message_id")

        requester_id = attrs.get("requester_id")
        if not requester_id:
            raise ValueError("Missing required field: requester_id")

        return cls(
            id=node.id,
            type="DISCORD_APPROVAL",  # Use literal type
            scope=node.scope,
            version=node.version,
            updated_by=node.updated_by,
            updated_at=node.updated_at,
            attributes=node.attributes,  # Pass through attributes
            # Extra fields from attributes
            approval_id=approval_id,
            action=action,
            request_type=request_type,
            channel_id=channel_id,
            message_id=message_id,
            task_id=attrs.get("task_id"),
            thought_id=attrs.get("thought_id"),
            requester_id=requester_id,
            status=attrs.get("status", "pending"),
            resolved_at=cls._deserialize_datetime(attrs.get("resolved_at")),
            resolver_id=attrs.get("resolver_id"),
            resolver_name=attrs.get("resolver_name"),
            context=attrs.get("context", {}),
            action_params=attrs.get("action_params", {}),
        )


@register_node_type("DISCORD_WA")
class DiscordWANode(TypedGraphNode):
    """Represents a Discord Wise Authority in the graph."""

    type: str = Field(default="DISCORD_WA", description="Node type")  # type: ignore[assignment]

    # Discord identity
    discord_id: str = Field(..., description="Discord user ID")
    discord_name: str = Field(..., description="Discord username")
    discriminator: Optional[str] = Field(None, description="Discord discriminator")

    # WA details
    wa_id: str = Field(..., description="CIRIS WA ID")
    roles: List[str] = Field(default_factory=list, description="Discord roles")

    # Permissions
    has_authority: bool = Field(default=False, description="Has AUTHORITY role")
    has_observer: bool = Field(default=False, description="Has OBSERVER role")

    # Activity tracking
    last_seen: datetime = Field(..., description="Last activity time")
    approval_count: int = Field(default=0, description="Number of approvals made")
    deferral_count: int = Field(default=0, description="Number of deferrals resolved")

    # Guild information
    guilds: List[Dict[str, str]] = Field(default_factory=list, description="List of guilds user is in")

    def to_graph_node(self) -> GraphNode:
        """Convert to generic GraphNode for storage."""
        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=self._serialize_extra_fields(),
            version=self.version,
            updated_by=self.updated_by,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "DiscordWANode":
        """Reconstruct from generic GraphNode."""
        # Handle both dict and GraphNodeAttributes
        if isinstance(node.attributes, dict):
            attrs = node.attributes
        else:
            attrs = {}

        # Extract required fields with proper validation
        discord_id = attrs.get("discord_id")
        if not discord_id:
            raise ValueError("Missing required field: discord_id")

        discord_name = attrs.get("discord_name")
        if not discord_name:
            raise ValueError("Missing required field: discord_name")

        wa_id = attrs.get("wa_id")
        if not wa_id:
            raise ValueError("Missing required field: wa_id")

        last_seen = cls._deserialize_datetime(attrs.get("last_seen"))
        if not last_seen:
            raise ValueError("Missing required field: last_seen")

        return cls(
            id=node.id,
            type="DISCORD_WA",  # Use literal type
            scope=node.scope,
            version=node.version,
            updated_by=node.updated_by,
            updated_at=node.updated_at,
            attributes=node.attributes,  # Pass through attributes
            # Extra fields from attributes
            discord_id=discord_id,
            discord_name=discord_name,
            discriminator=attrs.get("discriminator"),
            wa_id=wa_id,
            roles=attrs.get("roles", []),
            has_authority=attrs.get("has_authority", False),
            has_observer=attrs.get("has_observer", False),
            last_seen=last_seen,
            approval_count=attrs.get("approval_count", 0),
            deferral_count=attrs.get("deferral_count", 0),
            guilds=attrs.get("guilds", []),
        )


# Discord-specific node types are registered via the @register_node_type decorator
