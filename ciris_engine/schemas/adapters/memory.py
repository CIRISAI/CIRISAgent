"""
Memory adapter schemas for API routes.

These schemas are used by the memory API routes and related services.
"""
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field

from ciris_engine.schemas.services.graph_core import GraphNode, GraphEdge, GraphScope, NodeType


class QueryRequest(BaseModel):
    """Flexible query request supporting multiple patterns (RECALL)."""
    # Query patterns
    node_id: Optional[str] = Field(None, description="Specific node ID to retrieve")
    query: Optional[str] = Field(None, description="Natural language search query")
    related_to: Optional[str] = Field(None, description="Find nodes related to this node ID")
    
    # Filters
    since: Optional[datetime] = Field(None, description="Start time for temporal queries")
    until: Optional[datetime] = Field(None, description="End time for temporal queries")
    scope: Optional[GraphScope] = Field(None, description="Scope filter")
    type: Optional[NodeType] = Field(None, description="Node type filter")
    tags: Optional[List[str]] = Field(None, description="Tag filters")
    
    # Options
    include_edges: bool = Field(False, description="Include edges in response")
    depth: int = Field(1, ge=1, le=5, description="Depth for graph traversal")
    limit: int = Field(100, ge=1, le=1000, description="Maximum results")
    offset: int = Field(0, ge=0, description="Pagination offset")


class TimelineResponse(BaseModel):
    """Response for timeline view."""
    memories: List[GraphNode] = Field(..., description="Nodes in the timeline")
    edges: Optional[List[GraphEdge]] = Field(None, description="Edges between nodes if requested")
    buckets: dict[str, int] = Field(..., description="Time bucket counts")
    start_time: datetime = Field(..., description="Start of timeline range")
    end_time: datetime = Field(..., description="End of timeline range")
    total: int = Field(..., description="Total nodes in range (before limit)")


# Re-export MemorySearchFilter from the correct location
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter

__all__ = ["QueryRequest", "TimelineResponse", "MemorySearchFilter"]