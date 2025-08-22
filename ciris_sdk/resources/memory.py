from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ..models import GraphNode as ModelsGraphNode
from ..pagination import PageIterator
from ..transport import Transport

# Request/Response Models for v1 API


class MemoryStoreRequest(BaseModel):
    """Request to store a node in memory."""

    node: Dict[str, Any] = Field(..., description="GraphNode data to store")


class MemoryStoreResponse(BaseModel):
    """Response from storing a node."""

    success: bool = Field(..., description="Whether the operation succeeded")
    node_id: str = Field(..., description="ID of the stored node")
    message: Optional[str] = Field(None, description="Status message")
    operation: str = Field(default="MEMORIZE", description="Operation performed")


class MemoryQueryRequest(BaseModel):
    """Flexible query interface for memory with top-level common filters."""

    # Common filters as top-level fields
    type: Optional[str] = Field(None, description="Filter by node type")
    tags: Optional[List[str]] = Field(None, description="Filter by tags (AND operation)")
    since: Optional[datetime] = Field(None, description="Filter by creation time (after)")
    until: Optional[datetime] = Field(None, description="Filter by creation time (before)")
    related_to: Optional[str] = Field(None, description="Find nodes related to this node ID")
    text: Optional[str] = Field(None, description="Full-text search in node content")

    # Advanced/custom filters
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional custom filters")

    # Cursor-based pagination
    cursor: Optional[str] = Field(None, description="Pagination cursor from previous response")
    limit: int = Field(20, ge=1, le=100, description="Maximum results to return")

    # Graph options
    include_edges: bool = Field(False, description="Include relationship data")
    depth: int = Field(1, ge=1, le=3, description="Graph traversal depth")


# Use GraphNode from models.py instead of redefining
GraphNode = ModelsGraphNode


class MemoryQueryResponse(BaseModel):
    """Response from memory query with cursor pagination."""

    nodes: List[GraphNode] = Field(..., description="List of matching nodes")
    cursor: Optional[str] = Field(None, description="Cursor for next page of results")
    has_more: bool = Field(..., description="Whether more results are available")
    total_matches: Optional[int] = Field(None, description="Total matches (expensive, only if requested)")


class TimelineResponse(BaseModel):
    """Timeline view of memories."""

    memories: List[GraphNode] = Field(..., description="Recent memories")
    buckets: Union[List[Dict[str, Any]], Dict[str, int]] = Field(..., description="Time bucket counts")
    total: int = Field(..., description="Total memories in timeframe")


class MemoryVisualizationParams(BaseModel):
    """Parameters for memory graph visualization."""

    hours: int = Field(24, ge=1, le=168, description="Hours to look back")
    layout: str = Field("timeline", description="Layout: timeline, hierarchy, circular")
    width: int = Field(800, ge=400, le=2000, description="SVG width")
    height: int = Field(600, ge=300, le=1500, description="SVG height")
    scope: Optional[str] = Field(None, description="Filter by scope")
    type: Optional[str] = Field(None, description="Filter by node type")


class MemoryResource:
    """
    Memory service client for v1 API (Pre-Beta).

    **WARNING**: This SDK is for the v1 API which is in pre-beta stage.
    The API interfaces may change without notice.

    The memory service provides unified access to the agent's graph memory,
    implementing MEMORIZE, RECALL, and FORGET operations through a simplified
    query interface.
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def store(self, node: Union[Dict[str, Any], GraphNode]) -> MemoryStoreResponse:
        """
        Store typed nodes in memory (MEMORIZE).

        This is the primary way to add information to the agent's memory.
        Requires: ADMIN role

        Args:
            node: GraphNode data to store (as dict or GraphNode instance)

        Returns:
            MemoryStoreResponse with success status and node ID

        Example:
            # Using dict
            node = {
                "type": "CONCEPT",
                "attributes": {
                    "name": "quantum_computing",
                    "description": "A type of computation...",
                    "tags": ["physics", "computing"]
                }
            }
            result = await client.memory.store(node)
            print(f"Stored node: {result.node_id}")

            # Using GraphNode
            node = GraphNode(
                id="my-node",
                type="CONCEPT",
                scope="local",
                attributes={"name": "quantum_computing"}
            )
            result = await client.memory.store(node)
        """
        # Convert GraphNode to dict if necessary
        if isinstance(node, (GraphNode, ModelsGraphNode)):
            # Handle both Pydantic v1 (dict) and v2 (model_dump)
            if hasattr(node, "model_dump"):
                node_dict = node.model_dump(exclude_none=True, mode="json")
            else:
                node_dict = node.dict(exclude_none=True)
        else:
            node_dict = node

        payload = {"node": node_dict}
        result = await self._transport.request("POST", "/v1/memory/store", json=payload)

        # Handle API response format
        if isinstance(result, dict):
            # Check if wrapped in SuccessResponse
            if "data" in result:
                api_result = result["data"]
            else:
                api_result = result

            # Convert MemoryOpResult to MemoryStoreResponse
            if api_result and "status" in api_result:
                return MemoryStoreResponse(
                    success=api_result.get("status", "error").lower() in ["ok", "success"],
                    node_id=node_dict.get("id", ""),
                    message=api_result.get("reason"),
                    operation="MEMORIZE",
                )

        # Fallback - assume it's a MemoryOpResult
        if isinstance(result, dict) and "status" in result:
            return MemoryStoreResponse(
                success=result.get("status", "error").lower() in ["ok", "success"],
                node_id=node_dict.get("id", ""),
                message=result.get("reason"),
                operation="MEMORIZE",
            )

        # Last resort - try direct mapping
        return MemoryStoreResponse(**result)

    async def query(
        self,
        query: Optional[str] = None,  # Allow positional query parameter for backward compatibility
        *,
        type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        related_to: Optional[str] = None,
        text: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        include_edges: bool = False,
        depth: int = 1,
        include_total: bool = False,
    ) -> Union[MemoryQueryResponse, List[GraphNode]]:
        """
        Flexible query interface for memory (RECALL).

        The v1 API provides top-level fields for common filters and a filters
        object for advanced/custom queries. Uses cursor-based pagination.

        Args:
            type: Filter by node type (e.g., "CONCEPT", "EXPERIENCE")
            tags: Filter by tags (AND operation)
            since: Filter by creation time (after this time)
            until: Filter by creation time (before this time)
            related_to: Find nodes related to this node ID
            text: Full-text search in node content
            filters: Additional custom filters for advanced queries
            cursor: Pagination cursor from previous response
            limit: Maximum results (1-100)
            include_edges: Include relationship data
            depth: Graph traversal depth (1-3)
            include_total: Include total match count (expensive)

        Returns:
            MemoryQueryResponse with matching nodes and optional cursor

        Examples:
            # Simple query by type
            concepts = await client.memory.query(type="CONCEPT")

            # Query with multiple filters
            quantum_nodes = await client.memory.query(
                type="CONCEPT",
                tags=["quantum", "physics"],
                since=datetime(2025, 1, 1)
            )

            # Paginated query
            first_page = await client.memory.query(type="EXPERIENCE", limit=50)
            if first_page.has_more:
                next_page = await client.memory.query(
                    type="EXPERIENCE",
                    cursor=first_page.cursor,
                    limit=50
                )

            # Find related nodes with depth
            related = await client.memory.query(
                related_to="node_123",
                depth=2,
                include_edges=True
            )
        """
        # Handle backward compatibility - query parameter stays as query
        if query is not None and text is None:
            text = query

        payload: Dict[str, Any] = {"limit": limit, "include_edges": include_edges, "depth": depth}

        # Add top-level filters
        if type:
            payload["type"] = type
        if tags:
            payload["tags"] = tags
        if since:
            payload["since"] = since.isoformat() if isinstance(since, datetime) else since
        if until:
            payload["until"] = until.isoformat() if isinstance(until, datetime) else until
        if related_to:
            payload["related_to"] = related_to
        if text:
            # API expects 'query' not 'text'
            payload["query"] = text

        # Add custom filters
        if filters:
            payload["filters"] = filters

        # Pagination
        if cursor:
            payload["cursor"] = cursor

        # Optional expensive operations
        if include_total:
            payload["include_total"] = include_total

        result = await self._transport.request("POST", "/v1/memory/query", json=payload)

        # Handle API response format
        if isinstance(result, dict) and "data" in result:
            # API wraps response in SuccessResponse
            nodes_data = result["data"]
            if isinstance(nodes_data, list):
                # Direct list of nodes
                response = MemoryQueryResponse(
                    nodes=[GraphNode(**node) for node in nodes_data],
                    cursor=None,
                    has_more=False,
                    total_matches=len(nodes_data),
                )
            else:
                # Already a query response
                response = MemoryQueryResponse(**nodes_data)
        elif isinstance(result, list):
            # Direct list of nodes (legacy format)
            response = MemoryQueryResponse(
                nodes=[GraphNode(**node) for node in result], cursor=None, has_more=False, total_matches=len(result)
            )
        else:
            response = MemoryQueryResponse(**result)

        # For backward compatibility, if called with positional query arg, return just the nodes
        if query is not None:
            return response.nodes
        return response

    def query_iter(
        self,
        *,
        type: Optional[str] = None,
        tags: Optional[List[str]] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        related_to: Optional[str] = None,
        text: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 50,
        include_edges: bool = False,
        depth: int = 1,
    ) -> PageIterator[Dict[str, Any]]:
        """
        Iterate over all query results with automatic pagination.

        This is a convenience method that handles pagination automatically.
        It returns an async iterator that fetches new pages as needed.

        Args:
            Same as query() except no cursor or include_total

        Returns:
            Async iterator of GraphNode dictionaries

        Example:
            # Iterate over all concepts
            async for node in client.memory.query_iter(type="CONCEPT"):
                print(f"Found: {node['id']}")
        """
        params = {
            "type": type,
            "tags": tags,
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
            "related_to": related_to,
            "text": text,
            "filters": filters,
            "limit": limit,
            "include_edges": include_edges,
            "depth": depth,
        }

        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}

        return PageIterator(
            fetch_func=self.query, initial_params=params, item_class=dict  # Using dict since GraphNode is just a dict
        )

    async def forget(self, node_id: str) -> MemoryStoreResponse:
        """
        Remove specific memories (FORGET).

        Requires: ADMIN role

        Args:
            node_id: ID of node to forget

        Returns:
            MemoryStoreResponse with success status
        """
        result = await self._transport.request("DELETE", f"/v1/memory/{node_id}")
        return MemoryStoreResponse(**result)

    async def get_node(self, node_id: str) -> GraphNode:
        """
        Get specific node by ID.

        Direct access to a memory node.
        Requires: OBSERVER role

        Args:
            node_id: Node ID to retrieve

        Returns:
            GraphNode object
        """
        result = await self._transport.request("GET", f"/v1/memory/{node_id}")
        return GraphNode(**result)

    async def recall(self, node_id: str) -> GraphNode:
        """
        Alias for get_node for backward compatibility.

        Args:
            node_id: Node ID to retrieve

        Returns:
            GraphNode object
        """
        return await self.get_node(node_id)

    async def get_timeline(
        self,
        hours: int = 24,
        bucket_size: str = "hour",
        scope: Optional[str] = None,
        type: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> TimelineResponse:
        """
        Temporal view of memories.

        Get memories organized chronologically with time bucket counts.
        Requires: OBSERVER role

        Args:
            hours: Hours to look back (1-168)
            bucket_size: Time bucket size ("hour" or "day")
            scope: Memory scope filter
            type: Node type filter
            limit: Maximum number of memories to return

        Returns:
            TimelineResponse with memories and time buckets

        Example:
            # Get last 24 hours of EXPERIENCE nodes
            timeline = await client.memory.get_timeline(
                hours=24,
                type="EXPERIENCE",
                bucket_size="hour"
            )
            for bucket in timeline.buckets:
                print(f"{bucket['time']}: {bucket['count']} memories")
        """
        params = {"hours": str(hours), "bucket_size": bucket_size}
        if scope:
            params["scope"] = scope
        if type:
            params["type"] = type
        if limit:
            params["limit"] = str(limit)

        result = await self._transport.request("GET", "/v1/memory/timeline", params=params)
        return TimelineResponse(**result)

    async def timeline(self, hours: int = 24, limit: int = 20) -> TimelineResponse:
        """
        Alias for get_timeline for backward compatibility.

        Args:
            hours: Hours to look back (1-168)
            limit: Maximum memories to return

        Returns:
            TimelineResponse
        """
        return await self.get_timeline(hours=hours, limit=limit)

    # Convenience methods for common queries

    async def query_by_type(self, node_type: str, limit: int = 20) -> List[GraphNode]:
        """
        Query nodes by type.

        Convenience method for type-based queries.

        Args:
            node_type: Type of nodes to retrieve
            limit: Maximum number of results

        Returns:
            List of GraphNode objects
        """
        response = await self.query(type=node_type, limit=limit)
        return response.nodes

    async def query_by_tags(self, tags: List[str], limit: int = 20) -> List[GraphNode]:
        """
        Query nodes by tags.

        Find nodes that have all specified tags.

        Args:
            tags: List of tags to filter by
            limit: Maximum number of results

        Returns:
            List of GraphNode objects
        """
        response = await self.query(tags=tags, limit=limit)
        return response.nodes

    async def query_recent(self, hours: int = 24, type: Optional[str] = None) -> List[GraphNode]:
        """
        Query recent nodes.

        Get nodes created in the last N hours.

        Args:
            hours: How many hours to look back
            type: Optional node type filter

        Returns:
            List of GraphNode objects
        """
        since = datetime.now() - timedelta(hours=hours)
        response = await self.query(type=type, since=since, limit=100)
        return response.nodes

    async def find_related(self, node_id: str, depth: int = 2) -> List[GraphNode]:
        """
        Find nodes related to a specific node.

        Args:
            node_id: ID of the source node
            depth: How many levels to traverse (1-3)

        Returns:
            List of related GraphNode objects
        """
        response = await self.query(related_to=node_id, depth=depth, include_edges=True)
        return response.nodes

    async def visualize(
        self,
        hours: int = 24,
        layout: str = "timeline",
        width: int = 800,
        height: int = 600,
        scope: Optional[str] = None,
        type: Optional[str] = None,
    ) -> str:
        """
        Generate an interactive SVG visualization of the memory graph.

        Args:
            hours: Hours to look back (1-168, default 24)
            layout: Layout algorithm - "timeline", "hierarchy", or "circular"
            width: SVG width in pixels (400-2000)
            height: SVG height in pixels (300-1500)
            scope: Filter by scope (optional)
            type: Filter by node type (optional)

        Returns:
            HTML string containing the SVG visualization

        Example:
            # Get timeline visualization for last 7 days
            html = await client.memory.visualize(
                hours=168,
                layout="timeline",
                width=1200,
                height=800
            )

            # Save to file
            with open("memory_graph.html", "w") as f:
                f.write(html)

            # Filter by type
            concepts_viz = await client.memory.visualize(
                type="CONCEPT",
                layout="hierarchy"
            )
        """
        params = {"hours": hours, "layout": layout, "width": width, "height": height}

        if scope:
            params["scope"] = scope
        if type:
            params["type"] = type

        # The visualization endpoint returns HTML directly
        result = await self._transport.request(
            "GET", "/v1/memory/visualize/graph", params=params, raw_response=True  # Get raw HTML response
        )

        # If transport returns bytes, decode to string
        if isinstance(result, bytes):
            return result.decode("utf-8")
        return result
