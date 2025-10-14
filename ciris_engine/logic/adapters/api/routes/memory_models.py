"""
Data models for memory API endpoints.

Extracted from memory.py to improve modularity and testability.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_serializer, model_validator

from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict


class StoreRequest(BaseModel):
    """Request to store typed nodes in memory (MEMORIZE)."""

    node: GraphNode = Field(..., description="Typed graph node to store")


# Edge creation handled internally - no API model needed


class QueryRequest(BaseModel):
    """Flexible query interface for memory (RECALL).

    Supports multiple query patterns:
    - By ID: Specify node_id
    - By type: Specify type filter
    - By text: Specify query string
    - By time: Specify since/until filters
    - By correlation: Specify related_to node
    """

    # Node-based queries
    node_id: Optional[str] = Field(None, description="Get specific node by ID")
    type: Optional[NodeType] = Field(None, description="Filter by node type")

    # Text search
    query: Optional[str] = Field(None, description="Text search query")

    # Time-based queries
    since: Optional[datetime] = Field(None, description="Memories since this time")
    until: Optional[datetime] = Field(None, description="Memories until this time")

    # Correlation queries
    related_to: Optional[str] = Field(None, description="Find nodes related to this node ID")

    # Filters
    scope: Optional[GraphScope] = Field(None, description="Memory scope filter")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")

    # Pagination
    limit: int = Field(20, ge=1, le=1000, description="Maximum results")
    offset: int = Field(0, ge=0, description="Pagination offset")

    # Options
    include_edges: bool = Field(False, description="Include relationship data")
    depth: int = Field(1, ge=1, le=3, description="Graph traversal depth for relationships")

    @model_validator(mode="after")
    def validate_query_params(self: "QueryRequest") -> "QueryRequest":
        """Ensure at least one query parameter is specified."""
        if not any(
            [
                self.node_id,
                self.type,
                self.query,
                self.since,
                self.until,
                self.related_to,
                self.scope,
                self.tags,
            ]
        ):
            # Default to recent memories if no query specified
            self.since = datetime.now() - timedelta(hours=24)
        return self

    @field_serializer("since", "until")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class TimelineResponse(BaseModel):
    """Response containing timeline of memories."""

    memories: List[GraphNode] = Field(..., description="List of memory nodes")
    buckets: JSONDict = Field(default_factory=dict, description="Time buckets with counts")
    start_time: datetime = Field(..., description="Start of time range")
    end_time: datetime = Field(..., description="End of time range")
    total: int = Field(..., description="Total number of memories")

    @field_serializer("start_time", "end_time")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class MemoryStats(BaseModel):
    """Statistics about memory service."""

    total_nodes: int = Field(..., description="Total number of nodes")
    nodes_by_type: Dict[str, int] = Field(..., description="Node count by type")
    nodes_by_scope: Dict[str, int] = Field(..., description="Node count by scope")
    recent_nodes_24h: int = Field(..., description="Nodes created in last 24h")
    oldest_node_date: Optional[datetime] = Field(None, description="Oldest node date")
    newest_node_date: Optional[datetime] = Field(None, description="Newest node date")

    @field_serializer("oldest_node_date", "newest_node_date")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None
