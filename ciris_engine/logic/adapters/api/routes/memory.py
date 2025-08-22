"""
Memory service endpoints for CIRIS API v3 (Simplified and Refactored).

The memory service implements the three universal verbs: MEMORIZE, RECALL, FORGET.
All operations work through the graph memory system.

This is a refactored version with better modularity and testability.
"""

import html
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse, Response

from ciris_engine.schemas.api.responses import ResponseMetadata, SuccessResponse
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode
from ciris_engine.schemas.services.operations import GraphScope, MemoryOpResult, MemoryOpStatus

from ..dependencies.auth import AuthContext, require_admin, require_observer

# Import extracted modules
from .memory_models import CreateEdgeRequest, MemoryStats, QueryRequest, StoreRequest, TimelineResponse
from .memory_queries import get_memory_stats, query_timeline_nodes, search_nodes
from .memory_visualization import generate_svg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

# Constants
MEMORY_SERVICE_NOT_AVAILABLE = "Memory service not available"


# ============================================================================
# CORE ENDPOINTS
# ============================================================================


@router.post("/store", response_model=SuccessResponse[MemoryOpResult])
async def store_memory(
    request: Request,
    body: StoreRequest,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[MemoryOpResult]:
    """
    Store typed nodes in memory (MEMORIZE).

    This is the primary way to add information to the agent's memory.
    Requires ADMIN role as this modifies system state.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Store node via memory service
        # Note: memorize() only accepts the node parameter
        result = await memory_service.memorize(node=body.node)

        return SuccessResponse(
            data=result,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    except Exception as e:
        logger.error(f"Failed to store memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", response_model=SuccessResponse[List[GraphNode]])
async def query_memory(
    request: Request,
    body: QueryRequest,
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[List[GraphNode]]:
    """
    Query memories with flexible filters (RECALL).

    Supports querying by ID, type, text, time range, and relationships.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # If querying by specific ID
        if body.node_id:
            # Use recall method with a query for the specific node
            from ciris_engine.schemas.services.operations import MemoryQuery

            query = MemoryQuery(
                node_id=body.node_id, scope=body.scope or GraphScope.LOCAL, type=body.type, include_edges=False, depth=1
            )
            nodes = await memory_service.recall(query)

        # If querying by relationship
        elif body.related_to:
            nodes = await memory_service.find_related(
                node_id=body.related_to,
                depth=body.depth,
                scope=body.scope,
            )

        # General search
        else:
            nodes = await search_nodes(
                memory_service=memory_service,
                query=body.query,
                node_type=body.type,
                scope=body.scope,
                since=body.since,
                until=body.until,
                tags=body.tags,
                limit=body.limit,
                offset=body.offset,
            )

        return SuccessResponse(
            data=nodes,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_results=len(nodes),
            ),
        )

    except Exception as e:
        logger.error(f"Failed to query memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{node_id}", response_model=SuccessResponse[MemoryOpResult])
async def forget_memory(
    request: Request,
    node_id: str = Path(..., description="Node ID to forget"),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[MemoryOpResult]:
    """
    Forget a specific memory node (FORGET).

    Requires ADMIN role as this permanently removes data.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Create a minimal GraphNode with just the ID for deletion
        # The forget method will look up the full node internally
        from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

        node_to_forget = GraphNode(
            id=node_id,
            type=NodeType.CONCEPT,  # Default type, will be looked up by forget method
            scope=GraphScope.LOCAL,  # Default scope
            attributes={},
        )

        # Forget node via memory service
        result = await memory_service.forget(node=node_to_forget)

        return SuccessResponse(
            data=result,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    except Exception as e:
        logger.error(f"Failed to forget memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ANALYSIS ENDPOINTS
# ============================================================================


@router.get("/timeline", response_model=SuccessResponse[TimelineResponse])
async def get_timeline(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
    type: Optional[str] = Query(None, description="Filter by node type"),
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[TimelineResponse]:
    """
    Get a timeline view of recent memories.

    Returns memories organized chronologically with time buckets.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Query timeline nodes
        nodes = await query_timeline_nodes(
            memory_service=memory_service,
            hours=hours,
            scope=scope,
            node_type=type,
            limit=1000,
        )

        # Calculate time buckets
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)

        # Bucket by hour if < 48 hours, otherwise by day
        buckets = {}
        bucket_size = "hour" if hours <= 48 else "day"

        for node in nodes:
            if node.updated_at:
                if bucket_size == "hour":
                    bucket_key = node.updated_at.strftime("%Y-%m-%d %H:00")
                else:
                    bucket_key = node.updated_at.strftime("%Y-%m-%d")

                buckets[bucket_key] = buckets.get(bucket_key, 0) + 1

        response = TimelineResponse(
            memories=nodes,
            buckets=buckets,
            start_time=start_time,
            end_time=now,
            total=len(nodes),
        )

        return SuccessResponse(
            data=response,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=now.isoformat(),
            ),
        )

    except Exception as e:
        logger.error(f"Failed to get timeline: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=SuccessResponse[MemoryStats])
async def get_stats(
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[MemoryStats]:
    """
    Get statistics about memory storage.

    Returns counts, distributions, and metadata about the memory graph.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Get stats from database
        stats_data = await get_memory_stats(memory_service)

        # Get date range
        oldest = None
        newest = None

        timeline_nodes = await query_timeline_nodes(
            memory_service=memory_service,
            hours=24 * 365,  # Look back 1 year
            limit=1,
        )
        if timeline_nodes:
            oldest = timeline_nodes[0].updated_at

        timeline_nodes = await query_timeline_nodes(
            memory_service=memory_service,
            hours=1,
            limit=1,
        )
        if timeline_nodes:
            newest = timeline_nodes[0].updated_at

        stats = MemoryStats(
            total_nodes=stats_data["total_nodes"],
            nodes_by_type=stats_data["nodes_by_type"],
            nodes_by_scope=stats_data["nodes_by_scope"],
            recent_nodes_24h=stats_data["recent_activity"].get("nodes_24h", 0),
            oldest_node_date=oldest,
            newest_node_date=newest,
        )

        return SuccessResponse(
            data=stats,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# VISUALIZATION ENDPOINTS
# ============================================================================


@router.get("/visualize/graph")
async def visualize_graph(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    layout: str = Query("hierarchy", description="Layout: hierarchy, timeline, circular"),
    width: int = Query(800, ge=400, le=2000, description="SVG width"),
    height: int = Query(600, ge=300, le=1500, description="SVG height"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
    type: Optional[str] = Query(None, description="Filter by node type"),
    auth: AuthContext = Depends(require_observer),
) -> Response:
    """
    Generate an interactive SVG visualization of the memory graph.

    Returns an HTML page with an embedded SVG visualization.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Query nodes
        nodes = await query_timeline_nodes(
            memory_service=memory_service,
            hours=hours,
            scope=scope,
            node_type=type,
            limit=1000,  # Increased default limit for better visualization
        )

        # Query edges between the nodes we have
        edges = []
        if nodes:
            # Get all node IDs for filtering
            node_ids = set(node.id for node in nodes)

            # Query edges directly from persistence for these nodes
            try:
                # Import the edge query function
                from ciris_engine.logic.persistence.models.graph import get_edges_for_node

                # Get edges for each node (limit to prevent too many)
                seen_edges = set()  # Track (source, target) pairs to avoid duplicates

                for node in nodes[:500]:  # Query edges for up to 500 nodes
                    # Get all edges for this node
                    # get_edges_for_node expects a GraphScope enum, not a string
                    from ciris_engine.schemas.services.graph_core import GraphScope

                    # Convert scope to GraphScope enum if it's a string
                    if isinstance(node.scope, str):
                        scope_enum = GraphScope(node.scope)
                    else:
                        scope_enum = node.scope

                    node_edges = get_edges_for_node(node_id=node.id, scope=scope_enum)

                    for edge_data in node_edges:
                        # Only include edges where both nodes are in our visualization
                        if edge_data.target in node_ids:
                            edge_key = (edge_data.source, edge_data.target)
                            reverse_key = (edge_data.target, edge_data.source)

                            # Avoid duplicate edges
                            if edge_key not in seen_edges and reverse_key not in seen_edges:
                                edges.append(edge_data)
                                seen_edges.add(edge_key)

                                # Limit total edges for performance
                                if len(edges) >= 500:
                                    break

                    if len(edges) >= 500:
                        break

                logger.info(f"Found {len(edges)} edges for {len(nodes)} nodes in visualization")

            except Exception as e:
                logger.warning(f"Failed to query edges for visualization: {e}")
                # Continue with empty edges if query fails

        # Generate SVG
        svg = generate_svg(
            nodes=nodes,
            edges=edges,
            layout=layout,
            width=width,
            height=height,
        )

        # Safely escape user-controlled values to prevent XSS
        safe_hours = html.escape(str(hours))
        safe_layout = html.escape(str(layout))
        safe_node_count = html.escape(str(len(nodes)))
        safe_width = int(width) + 40  # Already validated as int by Query

        # Wrap in HTML with escaped values
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Memory Graph Visualization</title>
            <style>
                body {{
                    font-family: monospace;
                    margin: 0;
                    padding: 20px;
                    background: #f3f4f6;
                }}
                .container {{
                    max-width: {safe_width}px;
                    margin: 0 auto;
                    background: white;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }}
                h1 {{
                    margin-top: 0;
                    color: #1f2937;
                }}
                .stats {{
                    margin-bottom: 20px;
                    padding: 10px;
                    background: #f9fafb;
                    border-radius: 4px;
                }}
                .svg-container {{
                    border: 1px solid #e5e7eb;
                    border-radius: 4px;
                    overflow: auto;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Memory Graph Visualization</h1>
                <div class="stats">
                    <strong>Time Range:</strong> Last {safe_hours} hours<br>
                    <strong>Nodes:</strong> {safe_node_count}<br>
                    <strong>Layout:</strong> {safe_layout}
                </div>
                <div class="svg-container">
                    {svg}
                </div>
            </div>
        </body>
        </html>
        """

        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Failed to visualize graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EDGE MANAGEMENT ENDPOINTS
# ============================================================================


@router.post("/edges", response_model=SuccessResponse[MemoryOpResult])
async def create_edge(
    request: Request,
    body: CreateEdgeRequest,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[MemoryOpResult]:
    """
    Create an edge between two nodes.

    Establishes a relationship in the memory graph.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Create edge via memory service
        result = await memory_service.create_edge(edge=body.edge)

        return SuccessResponse(
            data=result,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    except Exception as e:
        logger.error(f"Failed to create edge: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{node_id}/edges", response_model=SuccessResponse[List[GraphEdge]])
async def get_node_edges(
    request: Request,
    node_id: str = Path(..., description="Node ID"),
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[List[GraphEdge]]:
    """
    Get all edges connected to a node.

    Returns both incoming and outgoing edges.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Get edges from memory service
        edges = await memory_service.get_edges(node_id=node_id)

        return SuccessResponse(
            data=edges,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_results=len(edges),
            ),
        )

    except Exception as e:
        logger.error(f"Failed to get edges: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# COMPATIBILITY ENDPOINTS (Legacy Support)
# ============================================================================


@router.get("/recall/{node_id}", response_model=SuccessResponse[GraphNode])
async def recall_by_id(
    request: Request,
    node_id: str = Path(..., description="Node ID to recall"),
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[GraphNode]:
    """
    Recall a specific node by ID (legacy endpoint).

    Use GET /memory/{node_id} for new implementations.
    """
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Use recall method with a query for the specific node
        from ciris_engine.schemas.services.operations import MemoryQuery

        query = MemoryQuery(
            node_id=node_id,
            scope=GraphScope.LOCAL,
            type=None,
            include_edges=True,  # Include edges for detail view
            depth=1,
        )
        nodes = await memory_service.recall(query)
        if not nodes:
            raise HTTPException(status_code=404, detail=f"Node {node_id} not found")
        node = nodes[0]

        return SuccessResponse(
            data=node,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to recall node: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{node_id}", response_model=SuccessResponse[GraphNode])
async def get_node(
    request: Request,
    node_id: str = Path(..., description="Node ID"),
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[GraphNode]:
    """
    Get a specific node by ID.

    Standard RESTful endpoint for node retrieval.
    """
    return await recall_by_id(request, node_id, auth)
