"""
Conversation summary nodes for consolidating speak/observe correlations.

These nodes preserve conversation content while consolidating metrics.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.graph_typed_nodes import TypedGraphNode, register_node_type
from ciris_engine.schemas.types import JSONDict


class ConversationMessage(BaseModel):
    """A single message in a conversation."""

    timestamp: str = Field(..., description="ISO timestamp")
    author_id: str = Field(..., description="Author ID")
    author_name: str = Field(..., description="Author name")
    content: str = Field(..., description="Message content")
    action_type: str = Field(..., description="Action type (speak, observe, etc.)")
    correlation_id: str = Field(..., description="Correlation ID")


@register_node_type("CONVERSATION_SUMMARY")
class ConversationSummaryNode(TypedGraphNode):
    """
    Consolidated conversation summary for a time period.

    Preserves full message content from speak/observe actions while
    summarizing metrics and patterns.
    """

    # Period information
    period_start: datetime = Field(..., description="Start of the consolidation period")
    period_end: datetime = Field(..., description="End of the consolidation period")
    period_label: str = Field(..., description="Human-readable period label")

    # Conversation content - CRITICAL for memory
    conversations_by_channel: Dict[str, List[ConversationMessage]] = Field(
        default_factory=dict, description="Full conversation history by channel"
    )

    # Message structure in conversations_by_channel:
    # {
    #   "channel_id": [
    #     {
    #       "timestamp": "2024-01-01T12:00:00Z",
    #       "author_id": "user123",
    #       "author_name": "Bob",
    #       "content": "Hello CIRIS",
    #       "action_type": "observe",
    #       "correlation_id": "abc123"
    #     },
    #     {
    #       "timestamp": "2024-01-01T12:00:05Z",
    #       "author_id": "ciris",
    #       "author_name": "CIRIS",
    #       "content": "Hello Bob! How can I help?",
    #       "action_type": "speak",
    #       "correlation_id": "def456"
    #     }
    #   ]
    # }

    # Aggregated metrics
    total_messages: int = Field(0, description="Total messages in period")
    messages_by_channel: Dict[str, int] = Field(default_factory=dict, description="Message count per channel")
    unique_users: int = Field(0, description="Number of unique users")
    user_list: List[str] = Field(default_factory=list, description="List of user IDs who interacted")

    # Service interaction metrics
    action_counts: Dict[str, int] = Field(
        default_factory=dict, description="Count of each action type (speak, observe, etc.)"
    )
    service_calls: Dict[str, int] = Field(default_factory=dict, description="Count of calls to each service")

    # Performance metrics
    avg_response_time_ms: float = Field(0.0, description="Average response time")
    total_processing_time_ms: float = Field(0.0, description="Total processing time")
    error_count: int = Field(0, description="Number of errors")
    success_rate: float = Field(1.0, description="Success rate (0-1)")

    # Conversation patterns (for future ML/analysis)
    topic_keywords: List[str] = Field(default_factory=list, description="Extracted topic keywords")
    sentiment_summary: Optional[Dict[str, float]] = Field(None, description="Sentiment analysis if available")

    # Summary metadata
    source_correlation_count: int = Field(0, description="Number of correlations consolidated")
    consolidation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When this summary was created"
    )

    # Required TypedGraphNode fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="TSDBConsolidationService")
    updated_by: str = Field(default="TSDBConsolidationService")

    # Graph node type
    type: NodeType = Field(default=NodeType.CONVERSATION_SUMMARY)
    scope: GraphScope = Field(default=GraphScope.LOCAL)
    id: str = Field(..., description="Node ID")
    version: int = Field(default=1)
    attributes: JSONDict = Field(default_factory=dict, description="Node attributes")

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        extra_fields = {
            # Period info
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_label": self.period_label,
            # CRITICAL: Full conversation content
            "conversations_by_channel": self.conversations_by_channel,
            # Metrics
            "total_messages": self.total_messages,
            "messages_by_channel": self.messages_by_channel,
            "unique_users": self.unique_users,
            "user_list": self.user_list,
            "action_counts": self.action_counts,
            "service_calls": self.service_calls,
            # Performance
            "avg_response_time_ms": self.avg_response_time_ms,
            "total_processing_time_ms": self.total_processing_time_ms,
            "error_count": self.error_count,
            "success_rate": self.success_rate,
            # Patterns
            "topic_keywords": self.topic_keywords,
            "sentiment_summary": self.sentiment_summary,
            # Metadata
            "source_correlation_count": self.source_correlation_count,
            "consolidation_timestamp": self.consolidation_timestamp.isoformat(),
            # Type hint
            "node_class": "ConversationSummaryNode",
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
    def from_graph_node(cls, node: GraphNode) -> "ConversationSummaryNode":
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
            # Conversations
            conversations_by_channel=attrs.get("conversations_by_channel", {}),
            # Metrics
            total_messages=attrs.get("total_messages", 0),
            messages_by_channel=attrs.get("messages_by_channel", {}),
            unique_users=attrs.get("unique_users", 0),
            user_list=attrs.get("user_list", []),
            action_counts=attrs.get("action_counts", {}),
            service_calls=attrs.get("service_calls", {}),
            # Performance
            avg_response_time_ms=attrs.get("avg_response_time_ms", 0.0),
            total_processing_time_ms=attrs.get("total_processing_time_ms", 0.0),
            error_count=attrs.get("error_count", 0),
            success_rate=attrs.get("success_rate", 1.0),
            # Patterns
            topic_keywords=attrs.get("topic_keywords", []),
            sentiment_summary=attrs.get("sentiment_summary"),
            # Metadata
            source_correlation_count=attrs.get("source_correlation_count", 0),
            consolidation_timestamp=cls._deserialize_datetime(attrs.get("consolidation_timestamp"))
            or datetime.now(timezone.utc),
        )
