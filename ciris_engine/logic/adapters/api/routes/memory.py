"""
Memory service endpoints for CIRIS API v3 (Simplified).

The memory service implements the three universal verbs: MEMORIZE, RECALL, FORGET.
All operations work through the graph memory system.
"""
import logging
import uuid
from typing import List, Optional, Dict, Literal, TYPE_CHECKING, Any, Tuple
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException, Depends, Query, Path
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_serializer, model_validator

from ciris_engine.schemas.api.responses import SuccessResponse, ResponseMetadata
from ciris_engine.schemas.services.graph_core import GraphNode, NodeType, GraphScope, GraphEdge, GraphEdgeAttributes
from ciris_engine.schemas.services.operations import MemoryQuery, MemoryOpResult
from ciris_engine.schemas.services.graph.memory import MemorySearchFilter
from ..dependencies.auth import require_observer, require_admin, AuthContext
from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.services.memory_service.timeline_query_service import TimelineQueryService
from ciris_engine.logic.services.memory_service.graph_visualization_service import GraphVisualizationService, LayoutType
from ciris_engine.logic.services.memory_service.memory_query_builder import MemoryQueryBuilder

if TYPE_CHECKING:
    import networkx as nx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/memory", tags=["memory"])

# SQL Query Constants
SQL_SELECT_NODES = "SELECT node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at"
SQL_FROM_NODES = "FROM graph_nodes"
SQL_WHERE_TIME_RANGE = "WHERE updated_at >= ? AND updated_at < ?"
SQL_EXCLUDE_METRICS = "AND NOT (node_type = 'tsdb_data' AND node_id LIKE 'metric_%')"
SQL_WHERE_SCOPE = "AND scope = ?"
SQL_WHERE_NODE_TYPE = "AND node_type = ?"
SQL_ORDER_RANDOM = "ORDER BY RANDOM()"
SQL_LIMIT = "LIMIT ?"

# Common String Constants
MEMORY_SERVICE_NOT_AVAILABLE = "Memory service not available"
TIMEZONE_SUFFIX = '+00:00'
MARKER_END = '</marker>'

# Request/Response schemas for simplified API

class StoreRequest(BaseModel):
    """Request to store typed nodes in memory (MEMORIZE)."""
    node: GraphNode = Field(..., description="Typed graph node to store")


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
    buckets: Dict[str, int] = Field(..., description="Time bucket counts")
    start_time: datetime = Field(..., description="Start of timeline range")
    end_time: datetime = Field(..., description="End of timeline range")
    total: int = Field(..., description="Total nodes in range (before limit)")


class CreateEdgeRequest(BaseModel):
    """Request to create an edge between nodes."""
    edge: GraphEdge = Field(..., description="Edge to create")


class MemoryStats(BaseModel):
    """Memory service statistics."""
    total_nodes: int = Field(..., description="Total number of nodes")
    total_edges: int = Field(..., description="Total number of edges")
    nodes_by_type: Dict[str, int] = Field(..., description="Node count by type")
    nodes_by_scope: Dict[str, int] = Field(..., description="Node count by scope")
    oldest_memory: Optional[datetime] = Field(None, description="Timestamp of oldest memory")
    newest_memory: Optional[datetime] = Field(None, description="Timestamp of newest memory")
    storage_size_mb: Optional[float] = Field(None, description="Storage size in MB")


# Endpoints

@router.post("/store", response_model=SuccessResponse[MemoryOpResult])
async def store_memory(
    request: Request,
    body: StoreRequest,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[MemoryOpResult]:
    """
    Store a typed node in memory (MEMORIZE).
    
    The memory service handles:
    - Deduplication
    - Version management
    - Relationship extraction
    - Graph integration
    
    OBSERVER role can store memories.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        # Add auth context to node metadata
        if not body.node.updated_by:
            body.node.updated_by = auth.user_id
        
        result = await memory_service.memorize(body.node)
        
        return SuccessResponse(
            data=result,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/query", response_model=SuccessResponse[List[GraphNode]])
async def query_memory(
    request: Request,
    body: QueryRequest,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[List[GraphNode]]:
    """
    Flexible query interface for memory (RECALL).

    This unified endpoint replaces recall/search/correlations.
    Supports multiple query patterns:
    - By ID: Get specific node
    - By type: Filter by node type
    - By text: Natural language search
    - By time: Temporal queries
    - By correlation: Find related nodes

    OBSERVER role can read all memories.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Use MemoryQueryBuilder for consistent query patterns
        query_builder = MemoryQueryBuilder(memory_service)
        nodes = await query_builder.build_and_execute(body)

        return SuccessResponse(
            data=nodes,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{node_id}", response_model=SuccessResponse[MemoryOpResult])
async def delete_memory(
    request: Request,
    node_id: str = Path(..., description="Node ID to delete"),
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[MemoryOpResult]:
    """
    Delete a node from memory (FORGET).
    
    Requires ADMIN role as this permanently removes data.
    The memory service handles:
    - Cascade deletion of orphaned edges
    - Version history cleanup
    - Graph integrity
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        result = await memory_service.forget(node_id)
        
        return SuccessResponse(
            data=result,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/timeline", response_model=SuccessResponse[TimelineResponse])
async def get_timeline(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    bucket_size: str = Query("hour", description="Time bucket size: hour, day"),
    scope: Optional[GraphScope] = Query(None, description="Memory scope filter"),
    type: Optional[NodeType] = Query(None, description="Node type filter"),
    limit: Optional[int] = Query(1000, ge=1, le=1000, description="Maximum number of memories to return"),
    include_edges: bool = Query(False, description="Include edges between memories"),
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[TimelineResponse]:
    """
    Temporal view of memories.

    Get memories organized chronologically with time bucket counts.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # Use the TimelineQueryService to handle the complex logic
        timeline_service = TimelineQueryService(memory_service)
        
        response = await timeline_service.get_timeline(
            hours=hours,
            bucket_size=bucket_size,
            scope=scope,
            node_type=type,
            limit=limit or 1000,
            include_edges=include_edges
        )

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )

    except Exception as e:
        logger.error(f"Timeline query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/recall/{node_id}", response_model=SuccessResponse[GraphNode])
async def recall_memory(
    request: Request,
    node_id: str = Path(..., description="Node ID to recall"),
    include_edges: bool = Query(False, description="Include connected edges"),
    depth: int = Query(1, ge=1, le=5, description="Depth for graph traversal"),
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[GraphNode]:
    """
    Recall a specific memory by ID.
    
    This is a convenience endpoint for direct node access.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        query = MemoryQuery(
            node_id=node_id,
            scope=GraphScope.LOCAL,  # Will search all scopes
            type=None,  # Any type
            include_edges=include_edges,
            depth=depth
        )
        nodes = await memory_service.recall(query)
        
        if not nodes:
            raise HTTPException(
                status_code=404,
                detail=f"Node {node_id} not found"
            )
        
        return SuccessResponse(
            data=nodes[0],
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats", response_model=SuccessResponse[MemoryStats])
async def get_memory_stats(
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[MemoryStats]:
    """
    Get memory service statistics.
    
    Provides insights into memory usage and distribution.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        stats = await memory_service.get_stats()
        
        # Convert to response model
        memory_stats = MemoryStats(
            total_nodes=stats.get('total_nodes', 0),
            total_edges=stats.get('total_edges', 0),
            nodes_by_type=stats.get('nodes_by_type', {}),
            nodes_by_scope=stats.get('nodes_by_scope', {}),
            oldest_memory=stats.get('oldest_memory'),
            newest_memory=stats.get('newest_memory'),
            storage_size_mb=stats.get('storage_size_mb')
        )
        
        return SuccessResponse(
            data=memory_stats,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{node_id}", response_model=SuccessResponse[GraphNode])
async def get_node(
    request: Request,
    node_id: str = Path(..., description="Node ID to retrieve"),
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[GraphNode]:
    """
    Get a specific node by ID.
    
    Simple endpoint for direct node retrieval without traversal.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        query = MemoryQuery(
            node_id=node_id,
            scope=GraphScope.LOCAL,
            type=None,
            include_edges=False,
            depth=1
        )
        nodes = await memory_service.recall(query)
        
        if not nodes:
            raise HTTPException(
                status_code=404,
                detail=f"Node {node_id} not found"
            )
        
        return SuccessResponse(
            data=nodes[0],
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/visualize/graph")
async def visualize_memory_graph(
    request: Request,
    node_type: Optional[NodeType] = Query(None, description="Filter by node type"),
    scope: Optional[GraphScope] = Query(GraphScope.LOCAL, description="Memory scope"),
    hours: Optional[int] = Query(None, ge=1, le=168, description="Hours to look back for timeline view"),
    layout: Literal["force", "timeline", "hierarchical"] = Query("force", description="Graph layout algorithm"),
    width: int = Query(1200, ge=400, le=4000, description="SVG width in pixels"),
    height: int = Query(800, ge=300, le=3000, description="SVG height in pixels"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum nodes to visualize"),
    include_metrics: bool = Query(False, description="Include metric TSDB_DATA nodes"),
    auth: AuthContext = Depends(require_observer)
) -> Response:
    """
    Generate an SVG visualization of the memory graph.
    
    Layout options:
    - force: Force-directed layout for general graph visualization
    - timeline: Arrange nodes chronologically along x-axis
    - hierarchical: Tree-like layout based on relationships
    
    Returns SVG image that can be embedded or downloaded.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        # Use the visualization service
        viz_service = GraphVisualizationService()
        
        from datetime import datetime
        
        # Query nodes based on filters
        nodes = []
        
        if hours:
            # Timeline view - get nodes from the specified time range
            now = datetime.now(timezone.utc)
            since = now - timedelta(hours=hours)
            
            # Use MemoryQueryBuilder for time-based query
            query_builder = MemoryQueryBuilder(memory_service)
            query_request = QueryRequest(
                since=since,
                until=now,
                scope=scope,
                type=node_type,
                limit=limit
            )
            nodes = await query_builder.build_and_execute(query_request)
        else:
            # Regular query - get nodes with optional type filter
            memory_query = MemoryQuery(
                node_id="*",
                scope=scope or GraphScope.LOCAL,
                type=node_type,
                include_edges=False,
                depth=1
            )
            nodes = await memory_service.recall(memory_query)
            
            # Filter out TSDB_DATA nodes unless specifically requested
            if not include_metrics and node_type != NodeType.TSDB_DATA:
                nodes = [n for n in nodes if not (n.type == NodeType.TSDB_DATA and n.id.startswith('metric_'))]
            
            # Apply limit
            nodes = nodes[:limit]
        
        # Query edges for nodes
        edges = []
        if nodes:
            # Import edge query function
            from ciris_engine.logic.persistence.models.graph import get_edges_for_node
            
            node_ids = [node.id for node in nodes]
            edge_set = set()  # To avoid duplicate edges
            
            for node in nodes:
                try:
                    node_edges = get_edges_for_node(node.id, node.scope, db_path=memory_service.db_path)
                    for edge in node_edges:
                        # Only include edges where both nodes are in our visualization
                        if edge.source in node_ids and edge.target in node_ids:
                            # Create a unique edge identifier to avoid duplicates
                            edge_key = (edge.source, edge.target, edge.relationship)
                            if edge_key not in edge_set:
                                edge_set.add(edge_key)
                                edges.append(edge)
                except Exception as e:
                    logger.warning(f"Failed to get edges for node {node.id}: {e}")
            
            logger.info(f"Found {len(edges)} edges connecting {len(nodes)} nodes")
        
        # Convert layout string to enum
        layout_type = LayoutType(layout)
        
        # Generate SVG using visualization service
        svg = await viz_service.generate_svg(
            nodes=nodes,
            edges=edges,
            layout_type=layout_type,
            width=width,
            height=height,
            hours=hours
        )
        
        return Response(content=svg, media_type="image/svg+xml")
        
    except ImportError:
        raise HTTPException(
            status_code=503, 
            detail="Graph visualization requires networkx. Please install: pip install networkx"
        )
    except Exception as e:
        logger.exception(f"Error generating graph visualization: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/edges", response_model=SuccessResponse[MemoryOpResult])
async def create_edge(
    request: Request,
    body: CreateEdgeRequest,
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[MemoryOpResult]:
    """
    Create an edge between two nodes.
    
    Requires ADMIN role as this modifies the graph structure.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        result = await memory_service.create_edge(body.edge)
        return SuccessResponse(
            data=result,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{node_id}/edges", response_model=SuccessResponse[List[GraphEdge]])
async def get_node_edges(
    request: Request,
    node_id: str = Path(..., description="Node ID to get edges for"),
    scope: GraphScope = Query(GraphScope.LOCAL, description="Scope of the node"),
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[List[GraphEdge]]:
    """
    Get all edges connected to a specific node.
    
    Returns both incoming and outgoing edges.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)
    
    try:
        edges = await memory_service.get_node_edges(node_id, scope)
        return SuccessResponse(
            data=edges,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))