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

from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_int
from ciris_engine.schemas.api.responses import ResponseMetadata, SuccessResponse
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode
from ciris_engine.schemas.services.operations import GraphScope, MemoryOpResult, MemoryOpStatus

from ..dependencies.auth import AuthContext, require_admin, require_observer
from .memory_filters import filter_nodes_by_user_attribution, get_user_allowed_ids, should_apply_user_filtering

# Import extracted modules
from .memory_models import MemoryStats, QueryRequest, StoreRequest, TimelineResponse
from .memory_queries import get_memory_stats, query_timeline_nodes, search_nodes
from .memory_visualization import generate_svg

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

# Constants
MEMORY_SERVICE_NOT_AVAILABLE = "Memory service not available"
AUTH_SERVICE_NOT_AVAILABLE = "Authentication service not available"
USER_ID_NOT_FOUND = "User ID not found in token"


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================


def get_memory_service(request: Request) -> Any:
    """Dependency to get memory service from app state (DRY helper)."""
    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    return memory_service


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def get_user_filter_ids_for_observer(request: Request, auth: AuthContext) -> Optional[List[str]]:
    """
    Get user filter IDs for OBSERVER role users.

    Returns None for ADMIN users (no filtering).
    Returns list of allowed user IDs for OBSERVER users.

    Raises HTTPException if authentication service not available or user_id missing.
    """
    from ciris_engine.schemas.api.auth import UserRole

    user_role = auth.role

    if not should_apply_user_filtering(user_role):
        return None

    auth_service = getattr(request.app.state, "authentication_service", None)
    if not auth_service:
        raise HTTPException(status_code=503, detail=AUTH_SERVICE_NOT_AVAILABLE)

    user_id = auth.user_id
    if not user_id:
        raise HTTPException(status_code=401, detail=USER_ID_NOT_FOUND)

    allowed_user_ids = await get_user_allowed_ids(auth_service, user_id)
    return list(allowed_user_ids)


def calculate_time_buckets(nodes: List[GraphNode], hours: int) -> Dict[str, int]:
    """
    Calculate time buckets for nodes based on hours range.

    Buckets by hour if <= 48 hours, otherwise by day.
    Returns dict mapping bucket key to node count.
    """
    buckets: Dict[str, int] = {}
    bucket_size = "hour" if hours <= 48 else "day"

    for node in nodes:
        if node.updated_at:
            if bucket_size == "hour":
                bucket_key = node.updated_at.strftime("%Y-%m-%d %H:00")
            else:
                bucket_key = node.updated_at.strftime("%Y-%m-%d")

            buckets[bucket_key] = buckets.get(bucket_key, 0) + 1

    return buckets


def _convert_to_graph_scope(scope: Any) -> GraphScope:
    """Convert scope value to GraphScope enum."""
    from ciris_engine.schemas.services.graph_core import GraphScope

    if isinstance(scope, str):
        converted_scope: GraphScope = GraphScope(scope)
        return converted_scope
    result_scope: GraphScope = scope
    return result_scope


def _is_edge_valid(edge: "GraphEdge", node_ids: set[str], seen_edges: set[tuple[str, str]]) -> bool:
    """
    Check if an edge is valid for visualization.

    Args:
        edge: Edge to validate
        node_ids: Set of node IDs in visualization
        seen_edges: Set of already seen edge pairs

    Returns:
        True if edge should be included
    """
    # Only include edges where both nodes are in visualization
    if edge.target not in node_ids:
        return False

    # Check for duplicates (bidirectional)
    edge_key = (edge.source, edge.target)
    reverse_key = (edge.target, edge.source)

    return edge_key not in seen_edges and reverse_key not in seen_edges


def _collect_edges_for_node(
    node: "GraphNode",
    node_ids: set[str],
    seen_edges: set[tuple[str, str]],
    max_edges: int,
    current_edges: List["GraphEdge"],
) -> bool:
    """
    Collect edges for a single node.

    Args:
        node: Node to query edges for
        node_ids: Set of all node IDs in visualization
        seen_edges: Set of seen edge pairs (modified in place)
        max_edges: Maximum edges allowed
        current_edges: List of current edges (modified in place)

    Returns:
        True if max_edges reached, False otherwise
    """
    from ciris_engine.logic.persistence.models.graph import get_edges_for_node

    scope_enum = _convert_to_graph_scope(node.scope)
    node_edges = get_edges_for_node(node_id=node.id, scope=scope_enum)

    for edge_data in node_edges:
        if _is_edge_valid(edge_data, node_ids, seen_edges):
            current_edges.append(edge_data)
            seen_edges.add((edge_data.source, edge_data.target))

            if len(current_edges) >= max_edges:
                return True

    return False


def query_edges_for_visualization(nodes: List[GraphNode], max_edges: int = 500) -> List[GraphEdge]:
    """
    Query edges for graph visualization.

    Args:
        nodes: List of nodes to get edges for
        max_edges: Maximum number of edges to return

    Returns:
        List of edges between the provided nodes
    """
    if not nodes:
        return []

    edges: List[GraphEdge] = []
    node_ids: set[str] = set(node.id for node in nodes)
    seen_edges: set[tuple[str, str]] = set()

    try:
        for node in nodes[:500]:  # Query edges for up to 500 nodes
            if _collect_edges_for_node(node, node_ids, seen_edges, max_edges, edges):
                break  # Max edges reached

        logger.info(f"Found {len(edges)} edges for {len(nodes)} nodes in visualization")

    except Exception as e:
        logger.warning(f"Failed to query edges for visualization: {e}")

    return edges


def generate_html_wrapper(svg: str, hours: int, layout: str, node_count: int, width: int) -> str:
    """
    Generate HTML wrapper for SVG visualization.

    Args:
        svg: The SVG content
        hours: Time range in hours
        layout: Layout type
        node_count: Number of nodes
        width: SVG width

    Returns:
        HTML string with embedded SVG
    """
    # Safely escape user-controlled values to prevent XSS
    safe_hours = html.escape(str(hours))
    safe_layout = html.escape(str(layout))
    safe_node_count = html.escape(str(node_count))
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

    return html_content


# ============================================================================
# CORE ENDPOINTS
# ============================================================================


@router.post("/store", response_model=SuccessResponse[MemoryOpResult[GraphNode]])
async def store_memory(
    request: Request,
    body: StoreRequest,
    auth: AuthContext = Depends(require_admin),
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[MemoryOpResult[GraphNode]]:
    """
    Store typed nodes in memory (MEMORIZE).

    This is the primary way to add information to the agent's memory.
    Requires ADMIN role as this modifies system state.
    """

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
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[List[GraphNode]]:
    """
    Query memories with flexible filters (RECALL).

    Supports querying by ID, type, text, time range, and relationships.

    SECURITY: OBSERVER users only see nodes they created or participated in.
    """

    try:
        # Determine user filtering (for OBSERVER users)
        user_filter_ids = await get_user_filter_ids_for_observer(request, auth)

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

        # General search (with SQL Layer 1 filtering if OBSERVER)
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
                user_filter_ids=user_filter_ids,  # SECURITY LAYER 1: SQL-level filtering
            )

        # SECURITY LAYER 2: Double-check with result filtering for defense in depth
        if user_filter_ids:
            nodes = filter_nodes_by_user_attribution(nodes, set(user_filter_ids))

        return SuccessResponse(
            data=nodes,
            meta=ResponseMetadata(
                request_id=str(request.state.request_id) if hasattr(request.state, "request_id") else None,
                timestamp=datetime.now(timezone.utc).isoformat(),
                total_results=len(nodes),
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to query memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{node_id}", response_model=SuccessResponse[MemoryOpResult[GraphNode]])
async def forget_memory(
    request: Request,
    node_id: str = Path(..., description="Node ID to forget"),
    auth: AuthContext = Depends(require_admin),
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[MemoryOpResult[GraphNode]]:
    """
    Forget a specific memory node (FORGET).

    Requires ADMIN role as this permanently removes data.
    """

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
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[TimelineResponse]:
    """
    Get a timeline view of recent memories.

    Returns memories organized chronologically with time buckets.

    SECURITY: OBSERVER users only see nodes they created or participated in.
    """
    try:
        # Determine user filtering before queries (for OBSERVER users)
        user_filter_ids = await get_user_filter_ids_for_observer(request, auth)

        # Query timeline nodes (with SQL Layer 1 filtering if OBSERVER)
        nodes = await query_timeline_nodes(
            memory_service=memory_service,
            hours=hours,
            scope=scope,
            node_type=type,
            limit=1000,
            user_filter_ids=user_filter_ids,  # SECURITY LAYER 1: SQL-level filtering
        )

        # SECURITY LAYER 2: Double-check with result filtering for defense in depth
        if user_filter_ids:
            nodes = filter_nodes_by_user_attribution(nodes, set(user_filter_ids))

        # Calculate time buckets
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)
        buckets = calculate_time_buckets(nodes, hours)

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
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[MemoryStats]:
    """
    Get statistics about memory storage.

    Returns counts, distributions, and metadata about the memory graph.
    """
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

        # Extract recent_activity dict with proper typing
        recent_activity = get_dict(stats_data, "recent_activity", {})

        stats = MemoryStats(
            total_nodes=stats_data["total_nodes"],
            nodes_by_type=stats_data["nodes_by_type"],
            nodes_by_scope=stats_data["nodes_by_scope"],
            recent_nodes_24h=get_int(recent_activity, "nodes_24h", 0),
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
    memory_service: Any = Depends(get_memory_service),
) -> Response:
    """
    Generate an interactive SVG visualization of the memory graph.

    Returns an HTML page with an embedded SVG visualization.
    """
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
        edges = query_edges_for_visualization(nodes, max_edges=500)

        # Generate SVG
        svg = generate_svg(
            nodes=nodes,
            edges=edges,
            layout=layout,
            width=width,
            height=height,
        )

        # Generate HTML wrapper with XSS protection
        html_content = generate_html_wrapper(svg=svg, hours=hours, layout=layout, node_count=len(nodes), width=width)

        return HTMLResponse(content=html_content)

    except Exception as e:
        logger.error(f"Failed to visualize graph: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# EDGE MANAGEMENT ENDPOINTS
# ============================================================================


# Edge creation happens internally through agent processing
# No direct API endpoint should be exposed for manual memory manipulation


@router.get("/{node_id}/edges", response_model=SuccessResponse[List[GraphEdge]])
async def get_node_edges(
    request: Request,
    node_id: str = Path(..., description="Node ID"),
    auth: AuthContext = Depends(require_observer),
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[List[GraphEdge]]:
    """
    Get all edges connected to a node.

    Returns both incoming and outgoing edges.
    """
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
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[GraphNode]:
    """
    Recall a specific node by ID (legacy endpoint).

    Use GET /memory/{node_id} for new implementations.

    SECURITY: OBSERVER users can only access nodes they created or participated in.
    """
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

        # SECURITY LAYER 2: Filter by user attribution for OBSERVER users
        user_filter_ids = await get_user_filter_ids_for_observer(request, auth)

        if user_filter_ids:
            allowed_user_ids = set(user_filter_ids)
            filtered_nodes = filter_nodes_by_user_attribution(nodes, allowed_user_ids)

            # If filtering removed the node, return 403 Forbidden
            if not filtered_nodes:
                raise HTTPException(
                    status_code=403, detail="Access denied: You do not have permission to view this memory node"
                )

            node = filtered_nodes[0]
        else:
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
    memory_service: Any = Depends(get_memory_service),
) -> SuccessResponse[GraphNode]:
    """
    Get a specific node by ID.

    Standard RESTful endpoint for node retrieval.
    """
    return await recall_by_id(request, node_id, auth, memory_service)
