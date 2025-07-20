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

class CreateEdgeRequest(BaseModel):
    """Request to create an edge between nodes."""
    edge: GraphEdge = Field(..., description="Edge to create between nodes")

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

    @model_validator(mode='after')
    def validate_query_params(self) -> 'QueryRequest':
        """Ensure at least one query parameter is provided."""
        if not any([
            self.node_id,
            self.type,
            self.query,
            self.since,
            self.related_to
        ]):
            raise ValueError("At least one query parameter must be provided")
        return self

class TimelineResponse(BaseModel):
    """Temporal view of memories."""
    memories: List[GraphNode] = Field(..., description="Memories in chronological order")
    edges: Optional[List[GraphEdge]] = Field(None, description="Edges between memories")
    buckets: Dict[str, int] = Field(..., description="Memory counts by time bucket (hour/day)")
    start_time: datetime = Field(..., description="Start of timeline range")
    end_time: datetime = Field(..., description="End of timeline range")
    total: int = Field(..., description="Total memories in range")

    @field_serializer('start_time', 'end_time')
    def serialize_times(self, dt: datetime, _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None

class MemoryStats(BaseModel):
    """Memory graph statistics."""
    total_nodes: int = Field(0, description="Total number of nodes in memory")
    nodes_by_type: Dict[str, int] = Field(default_factory=dict, description="Node count by type")
    nodes_by_scope: Dict[str, int] = Field(default_factory=dict, description="Node count by scope")
    recent_nodes_24h: int = Field(0, description="Nodes created/updated in last 24 hours")
    oldest_node_date: Optional[datetime] = Field(None, description="Timestamp of oldest node")
    newest_node_date: Optional[datetime] = Field(None, description="Timestamp of newest node")
    
    @field_serializer('oldest_node_date', 'newest_node_date')
    def serialize_dates(self, dt: datetime, _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None

# Simplified Endpoints

@router.post("/store", response_model=SuccessResponse[MemoryOpResult])
async def store_memory(
    request: Request,
    body: StoreRequest,
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[MemoryOpResult]:
    """
    Store typed nodes in memory (MEMORIZE).

    This is the primary way to add information to the agent's memory.
    Requires ADMIN role as this modifies system state.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
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
async def forget_memory(
    request: Request,
    node_id: str = Path(..., description="ID of node to forget"),
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[MemoryOpResult]:
    """
    Remove specific memories (FORGET).

    Requires ADMIN role as this modifies system state.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        # First get the node
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

        # Forget the node
        result = await memory_service.forget(nodes[0])
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
    include_edges: bool = Query(False, description="Include edges in response"),
    depth: int = Query(1, ge=1, le=3, description="Graph traversal depth if include_edges is true"),
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[GraphNode]:
    """
    Recall specific memory by ID.

    Direct access to a memory node using the RECALL verb.
    """
    return await get_memory(request, node_id, include_edges, depth, auth)

@router.get("/stats", response_model=SuccessResponse[MemoryStats])
async def get_memory_stats(
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[MemoryStats]:
    """
    Get memory graph statistics.
    
    Returns counts and metadata about nodes in memory without requiring any query parameters.
    OBSERVER role can view memory statistics.
    """
    try:
        stats = MemoryStats()
        
        # Get stats from database
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Total node count
            cursor.execute("SELECT COUNT(*) as total FROM graph_nodes")
            stats.total_nodes = cursor.fetchone()['total'] or 0
            
            # Nodes by type
            cursor.execute("""
                SELECT node_type, COUNT(*) as count 
                FROM graph_nodes 
                GROUP BY node_type
            """)
            stats.nodes_by_type = {row['node_type']: row['count'] for row in cursor.fetchall()}
            
            # Nodes by scope  
            cursor.execute("""
                SELECT scope, COUNT(*) as count 
                FROM graph_nodes 
                GROUP BY scope
            """)
            stats.nodes_by_scope = {row['scope']: row['count'] for row in cursor.fetchall()}
            
            # Recent nodes (24h)
            twenty_four_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            cursor.execute("""
                SELECT COUNT(*) as count 
                FROM graph_nodes 
                WHERE updated_at >= ?
            """, (twenty_four_hours_ago,))
            stats.recent_nodes_24h = cursor.fetchone()['count'] or 0
            
            # Date range
            cursor.execute("""
                SELECT 
                    MIN(updated_at) as oldest,
                    MAX(updated_at) as newest
                FROM graph_nodes
            """)
            row = cursor.fetchone()
            if row and row['oldest']:
                stats.oldest_node_date = datetime.fromisoformat(row['oldest'].replace('Z', UTC_TIMEZONE_SUFFIX))
            if row and row['newest']:
                stats.newest_node_date = datetime.fromisoformat(row['newest'].replace('Z', UTC_TIMEZONE_SUFFIX))
        
        return SuccessResponse(
            data=stats,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )
        
    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        # Return empty stats on error
        return SuccessResponse(
            data=MemoryStats(),
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc),
                request_id=str(uuid.uuid4()),
                duration_ms=0
            )
        )

@router.get("/{node_id}", response_model=SuccessResponse[GraphNode])
async def get_memory(
    request: Request,
    node_id: str = Path(..., description="Node ID to retrieve"),
    include_edges: bool = Query(False, description="Include edges in response"),
    depth: int = Query(1, ge=1, le=3, description="Graph traversal depth if include_edges is true"),
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[GraphNode]:
    """
    Get specific node by ID.

    Direct access to a memory node.
    """
    memory_service = getattr(request.app.state, 'memory_service', None)
    if not memory_service:
        raise HTTPException(status_code=503, detail=MEMORY_SERVICE_NOT_AVAILABLE)

    try:
        query = MemoryQuery(
            node_id=node_id,
            scope=GraphScope.LOCAL,
            type=None,
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
            
            # For timeline layout, query database directly to get time-distributed nodes
            if layout == "timeline":
                # Cap timeline visualizations to prevent Cloudflare timeouts
                effective_limit = min(limit, 100)  # Max 100 nodes for timeline through proxy
                if limit > effective_limit:
                    logger.info(f"Capping timeline visualization from {limit} to {effective_limit} nodes for performance")
                import json
                
                try:
                    logger.info(f"Timeline visualization: Querying database for {hours} hours with limit {effective_limit}")
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        
                        # For timeline, we need to sample across time buckets
                        # For proper time windows, use hour buckets instead of day buckets for smaller ranges
                        if hours <= 48:
                            # Use hour buckets for better precision
                            bucket_hours = 3  # 3-hour buckets
                            num_buckets = (hours + bucket_hours - 1) // bucket_hours
                            nodes_per_bucket = max(1, effective_limit // num_buckets)
                            logger.info(f"Timeline: {num_buckets} buckets ({bucket_hours}h each), {nodes_per_bucket} nodes per bucket")
                            
                            # Sample nodes from each time bucket
                            all_db_nodes = []
                            for bucket_idx in range(num_buckets):
                                bucket_start = now - timedelta(hours=(bucket_idx + 1) * bucket_hours)
                                bucket_end = now - timedelta(hours=bucket_idx * bucket_hours)
                                
                                # Ensure we don't go before the window start
                                if bucket_start < since:
                                    bucket_start = since
                                
                                # Build query for this bucket
                                query_parts = [
                                    SQL_SELECT_NODES,
                                    SQL_FROM_NODES,
                                    SQL_WHERE_TIME_RANGE,
                                ]
                                params: List[Any] = [bucket_start.isoformat(), bucket_end.isoformat()]
                                
                                # Add metric filter
                                if not include_metrics:
                                    query_parts.append(SQL_EXCLUDE_METRICS)
                                
                                # Add scope filter
                                if scope:
                                    query_parts.append(SQL_WHERE_SCOPE)
                                    params.append(scope.value)
                                
                                # Add type filter
                                if node_type:
                                    query_parts.append(SQL_WHERE_NODE_TYPE)
                                    params.append(node_type.value)
                                
                                # Random sampling for better distribution
                                query_parts.extend([
                                    SQL_ORDER_RANDOM,
                                    SQL_LIMIT
                                ])
                                params.append(nodes_per_bucket * 2)  # Get extra to allow for filtering
                            
                                query = " ".join(query_parts)
                                cursor.execute(query, params)
                                
                                # Convert rows to GraphNode objects for this bucket
                                for row in cursor.fetchall():
                                    try:
                                        # Parse attributes
                                        attributes = json.loads(row['attributes_json']) if row['attributes_json'] else {}
                                        
                                        # Create GraphNode
                                        node = GraphNode(
                                            id=row['node_id'],
                                            type=NodeType(row['node_type']),
                                            scope=GraphScope(row['scope']),
                                            attributes=attributes,
                                            version=row['version'],
                                            updated_by=row['updated_by'],
                                            updated_at=datetime.fromisoformat(row['updated_at'].replace('Z', UTC_TIMEZONE_SUFFIX))
                                        )
                                        all_db_nodes.append(node)
                                    except Exception as e:
                                        logger.warning(f"Failed to parse node {row['node_id']}: {e}")
                                        continue
                        else:
                            # Use day buckets for longer ranges
                            days_in_range = int((now - since).total_seconds() / 86400) + 1
                            nodes_per_day = max(1, effective_limit // days_in_range)
                            logger.info(f"Timeline: {days_in_range} days, {nodes_per_day} nodes per day")
                            
                            # Sample nodes from each day
                            all_db_nodes = []
                            for day_offset in range(days_in_range):
                                # Use precise time boundaries based on the actual time window
                                day_start = now - timedelta(days=day_offset + 1)
                                day_end = now - timedelta(days=day_offset)
                                
                                # Ensure we stay within the requested window
                                if day_start < since:
                                    day_start = since
                                if day_end > now:
                                    day_end = now
                                
                                # Skip if invalid range
                                if day_start >= day_end:
                                    continue
                                
                                # Build query for this day
                                query_parts = [
                                    SQL_SELECT_NODES,
                                    SQL_FROM_NODES,
                                    SQL_WHERE_TIME_RANGE,
                                ]
                                day_params: List[Any] = [day_start.isoformat(), day_end.isoformat()]
                                
                                # Add metric filter
                                if not include_metrics:
                                    query_parts.append(SQL_EXCLUDE_METRICS)
                                
                                # Add scope filter
                                if scope:
                                    query_parts.append(SQL_WHERE_SCOPE)
                                    day_params.append(scope.value)
                                
                                # Add type filter
                                if node_type:
                                    query_parts.append(SQL_WHERE_NODE_TYPE)
                                    day_params.append(node_type.value)
                                
                                # Random sampling for better distribution
                                query_parts.extend([
                                    SQL_ORDER_RANDOM,
                                    SQL_LIMIT
                                ])
                                day_params.append(nodes_per_day * 2)  # Get extra to allow for filtering
                                
                                query = " ".join(query_parts)
                                cursor.execute(query, day_params)
                                
                                # Convert rows to GraphNode objects for this day
                                for row in cursor.fetchall():
                                    try:
                                        # Parse attributes
                                        attributes = json.loads(row['attributes_json']) if row['attributes_json'] else {}
                                        
                                        # Create GraphNode
                                        node = GraphNode(
                                            id=row['node_id'],
                                            type=NodeType(row['node_type']),
                                            scope=GraphScope(row['scope']),
                                            attributes=attributes,
                                            version=row['version'],
                                            updated_by=row['updated_by'],
                                            updated_at=datetime.fromisoformat(row['updated_at'].replace('Z', UTC_TIMEZONE_SUFFIX))
                                        )
                                        all_db_nodes.append(node)
                                    except Exception as e:
                                        logger.warning(f"Failed to parse node {row['node_id']}: {e}")
                                        continue
                        
                        # Set nodes from database query
                        nodes = all_db_nodes[:effective_limit] if len(all_db_nodes) > effective_limit else all_db_nodes
                        logger.info(f"Timeline: Collected {len(all_db_nodes)} nodes, using {len(nodes)} for visualization")
                        
                except Exception as e:
                    logger.error(f"Failed to query timeline data: {e}")
                    # Fall back to standard query
                    memory_query = MemoryQuery(
                        node_id="*",
                        scope=scope or GraphScope.LOCAL,
                        type=node_type,
                        include_edges=False,
                        depth=1
                    )
                    all_nodes = await memory_service.recall(memory_query)
                    nodes = all_nodes
            else:
                # Regular time-based query
                memory_query = MemoryQuery(
                    node_id="*",
                    scope=scope or GraphScope.LOCAL,
                    type=node_type,
                    include_edges=False,
                    depth=1
                )
                all_nodes = await memory_service.recall(memory_query)
            
            # Skip additional filtering if we already have nodes from timeline database query
            if layout != "timeline" and nodes == []:
                # Filter out metric_ TSDB_DATA nodes by default unless specifically requested
                if not include_metrics and node_type != NodeType.TSDB_DATA:
                    all_nodes = [n for n in all_nodes if not (n.type == NodeType.TSDB_DATA and n.id.startswith('metric_'))]
                
                # Filter by time
                for node in all_nodes:
                    if isinstance(node.attributes, dict):
                        node_time = node.attributes.get('created_at') or node.attributes.get('timestamp')
                    else:
                        node_time = node.attributes.created_at
                    
                    # Fallback to top-level updated_at
                    if not node_time and hasattr(node, 'updated_at'):
                        node_time = node.updated_at
                    
                    if node_time:
                        if isinstance(node_time, str):
                            node_time = datetime.fromisoformat(node_time.replace('Z', UTC_TIMEZONE_SUFFIX))
                        
                        # Ensure node_time has timezone info for comparison
                        if isinstance(node_time, datetime):
                            if node_time.tzinfo is None:
                                # Assume UTC if no timezone
                                node_time = node_time.replace(tzinfo=timezone.utc)
                            
                            if since <= node_time <= now:
                                nodes.append(node)
            
            # Sort by time for timeline layout
            def get_node_sort_time(n: GraphNode) -> datetime:
                """Get datetime for sorting, with fallback to epoch."""
                epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
                try:
                    if isinstance(n.attributes, dict):
                        time_val = n.attributes.get('created_at') or n.attributes.get('timestamp')
                    else:
                        time_val = n.attributes.created_at
                    
                    # Fallback to top-level updated_at
                    if not time_val and hasattr(n, 'updated_at'):
                        time_val = n.updated_at
                    
                    if time_val:
                        if isinstance(time_val, str):
                            return datetime.fromisoformat(time_val.replace('Z', UTC_TIMEZONE_SUFFIX))
                        elif isinstance(time_val, datetime):
                            # Ensure datetime is timezone-aware
                            if time_val.tzinfo is None:
                                return time_val.replace(tzinfo=timezone.utc)
                            return time_val
                except Exception as e:
                    logger.warning(f"Failed to parse time for node {n.id}: {e}")
                
                return epoch
            if nodes:  # Only sort if we have nodes from time filtering
                nodes.sort(key=get_node_sort_time)
        else:
            # Regular query - get nodes with optional type filter
            # For timeline layout, we need many more nodes to cover time range
            if layout == "timeline":
                # Cap timeline visualizations to prevent Cloudflare timeouts
                effective_limit = min(limit, 100)  # Max 100 nodes for timeline through proxy
                if limit > effective_limit:
                    logger.info(f"Capping timeline visualization from {limit} to {effective_limit} nodes for performance")
                # Query database directly for timeline to get proper time distribution
                import json
                
                now = datetime.now(timezone.utc)
                start_time = now - timedelta(hours=hours or 0)
                
                try:
                    logger.info(f"Timeline visualization: Querying database for {hours} hours with limit {effective_limit}")
                    with get_db_connection() as conn:
                        cursor = conn.cursor()
                        
                        # For timeline, we need to sample across time buckets
                        days_in_range = int((now - start_time).total_seconds() / 86400) + 1
                        nodes_per_day = max(1, effective_limit // days_in_range)
                        logger.info(f"Timeline: {days_in_range} days, {nodes_per_day} nodes per day")
                        
                        # Sample nodes from each day
                        all_db_nodes = []
                        for day_offset in range(days_in_range):
                            day_start = (now - timedelta(days=day_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
                            day_end = day_start + timedelta(days=1)
                            
                            # Build query for this day
                            query_parts = [
                                SQL_SELECT_NODES,
                                SQL_FROM_NODES,
                                SQL_WHERE_TIME_RANGE,
                            ]
                            day_params2: List[Any] = [day_start.isoformat(), day_end.isoformat()]
                            
                            # Add metric filter
                            if not include_metrics:
                                query_parts.append(SQL_EXCLUDE_METRICS)
                            
                            # Add scope filter
                            if scope:
                                query_parts.append(SQL_WHERE_SCOPE)
                                day_params2.append(scope.value)
                            
                            # Add type filter
                            if node_type:
                                query_parts.append(SQL_WHERE_NODE_TYPE)
                                day_params2.append(node_type.value)
                            
                            # Random sampling for better distribution
                            query_parts.extend([
                                SQL_ORDER_RANDOM,
                                SQL_LIMIT
                            ])
                            day_params2.append(nodes_per_day * 2)  # Get extra to allow for filtering
                        
                            query = " ".join(query_parts)
                            cursor.execute(query, day_params2)
                            
                            # Convert rows to GraphNode objects for this day
                            for row in cursor.fetchall():
                                try:
                                    # Parse attributes
                                    attributes = json.loads(row['attributes_json']) if row['attributes_json'] else {}
                                    
                                    # Create GraphNode
                                    node = GraphNode(
                                        id=row['node_id'],
                                        type=NodeType(row['node_type']),
                                        scope=GraphScope(row['scope']),
                                        attributes=attributes,
                                        version=row['version'],
                                        updated_by=row['updated_by'],
                                        updated_at=datetime.fromisoformat(row['updated_at'].replace('Z', UTC_TIMEZONE_SUFFIX))
                                    )
                                    all_db_nodes.append(node)
                                except Exception as e:
                                    logger.warning(f"Failed to parse node {row['node_id']}: {e}")
                                    continue
                        
                        # Limit nodes if we got too many
                        logger.info(f"Timeline: Collected {len(all_db_nodes)} total nodes from database")
                        if len(all_db_nodes) > effective_limit:
                            # Sample evenly across the collected nodes
                            step = len(all_db_nodes) // effective_limit
                            nodes = [all_db_nodes[i] for i in range(0, len(all_db_nodes), step)][:effective_limit]
                        else:
                            nodes = all_db_nodes
                        logger.info(f"Timeline: Using {len(nodes)} nodes for visualization")
                            
                except Exception as e:
                    logger.error(f"Failed to query timeline data: {e}")
                    # Fall back to standard search
                    search_filters = MemorySearchFilter(
                        scope=(scope or GraphScope.LOCAL).value,
                        node_type=node_type.value if node_type else None,
                        limit=limit,
                        offset=None
                    )
                    nodes = await memory_service.search("", filters=search_filters)
            else:
                # Regular query for non-timeline layouts
                memory_query = MemoryQuery(
                    node_id="*",
                    scope=scope or GraphScope.LOCAL,
                    type=node_type,
                    include_edges=False,
                    depth=1
                )
                nodes = await memory_service.recall(memory_query)
                
                # Filter out TSDB_DATA nodes by default unless specifically requested
                if node_type != NodeType.TSDB_DATA:
                    nodes = [n for n in nodes if n.type != NodeType.TSDB_DATA]
                
                # Apply limit for non-timeline layouts
                nodes = nodes[:limit]
        
        # Don't limit here - we handle limiting differently for timeline layout
        
        # Debug log sample node data
        if nodes and layout == "timeline":
            logger.info(f"Visualizing {len(nodes)} nodes in timeline layout")
            for i, node in enumerate(nodes[:3]):  # Log first 3 nodes
                logger.info(f"Sample node {i}: id={node.id}, type={node.type}")
                if hasattr(node, 'updated_at'):
                    logger.info(f"  updated_at: {node.updated_at}")
                if hasattr(node, 'attributes'):
                    if isinstance(node.attributes, dict):
                        logger.info(f"  attributes keys: {list(node.attributes.keys())}")
                        if 'created_at' in node.attributes:
                            logger.info(f"  created_at: {node.attributes['created_at']}")
                        if 'timestamp' in node.attributes:
                            logger.info(f"  timestamp: {node.attributes['timestamp']}")
                    else:
                        logger.info(f"  attributes type: {type(node.attributes)}")
        
        if not nodes:
            # Return empty SVG if no nodes
            svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
                <rect width="{width}" height="{height}" fill="#f8f9fa"/>
                <text x="{width//2}" y="{height//2}" text-anchor="middle" font-family="Arial" font-size="16" fill="#6c757d">
                    No memories found
                </text>
            </svg>'''
            return Response(content=svg, media_type="image/svg+xml")
        
        # Create graph
        G = nx.DiGraph()
        
        # Add nodes with their attributes
        for node in nodes:
            # Prepare node attributes for visualization
            node_attrs = {
                'label': node.id[:30] + '...' if len(node.id) > 30 else node.id,
                'type': node.type.value,
                'scope': node.scope.value,
                'title': node.attributes.get('title', '') if isinstance(node.attributes, dict) else '',
                'created_at': (node.attributes.get('created_at') or node.attributes.get('timestamp') or str(getattr(node, 'updated_at', ''))) if isinstance(node.attributes, dict) else str(getattr(node.attributes, 'created_at', getattr(node, 'updated_at', ''))),
                'color': _get_node_color(node.type),
                'size': _get_node_size(node)
            }
            G.add_node(node.id, **node_attrs)
        
        # Query edges for all nodes in the visualization
        edges_to_add = []
        node_ids = [node.id for node in nodes]
        
        # Import edge query function
        from ciris_engine.logic.persistence.models.graph import get_edges_for_node
        
        # Query edges for each node
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
                            edges_to_add.append(edge)
                            # Add edge to NetworkX graph
                            G.add_edge(edge.source, edge.target, 
                                     relationship=edge.relationship,
                                     weight=edge.weight,
                                     attributes=edge.attributes)
            except Exception as e:
                logger.warning(f"Failed to get edges for node {node.id}: {e}")
        
        logger.info(f"Found {len(edges_to_add)} edges connecting {len(nodes)} nodes")
        
        # Calculate layout based on selected algorithm
        if layout == "timeline" and hours:
            pos = _calculate_timeline_layout(G, nodes, width, height, hours)
        elif layout == "hierarchical":
            # Try to use hierarchical layout if the graph has a tree-like structure
            try:
                # Check if graph is a tree or can be converted to one
                if nx.is_tree(G.to_undirected()):
                    # Find root nodes (nodes with no incoming edges)
                    root_nodes = [n for n in G.nodes() if G.in_degree(n) == 0]
                    if root_nodes:
                        # Use the first root node for hierarchical layout
                        pos = _hierarchy_pos(G, root_nodes[0])
                    else:
                        # Fallback to spring layout
                        pos = nx.spring_layout(G, k=2, iterations=50)
                else:
                    # For non-tree graphs, use spring layout with higher k value
                    pos = nx.spring_layout(G, k=3, iterations=50)
            except (nx.NetworkXError, ValueError, TypeError, AttributeError, KeyError):
                # Fallback to spring layout if hierarchical fails
                # NetworkXError: General NetworkX exceptions
                # ValueError: Invalid parameters to layout functions
                # TypeError: Type mismatches in graph operations
                # AttributeError: Missing attributes on graph objects
                # KeyError: Missing nodes in position calculations
                pos = nx.spring_layout(G, k=2, iterations=50)
            
            # Scale to fit canvas
            pos = {node: (x * (width - 100) + 50, y * (height - 100) + 50) for node, (x, y) in pos.items()}
        else:  # force layout
            pos = nx.spring_layout(G, k=1.5, iterations=30)
            # Scale to fit canvas
            pos = {node: (x * (width - 100) + 50, y * (height - 100) + 50) for node, (x, y) in pos.items()}
        
        # Generate SVG with edges
        svg = _generate_svg(G, pos, width, height, layout, hours, edges_to_add)
        
        return Response(content=svg, media_type="image/svg+xml")
        
    except ImportError:
        raise HTTPException(
            status_code=503, 
            detail="Graph visualization requires networkx. Please install: pip install networkx"
        )
    except Exception as e:
        logger.exception(f"Error generating graph visualization: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_edge_color(relationship: str) -> str:
    """Get color for edge based on relationship type."""
    # Define color mapping for common relationship types
    color_map = {
        "created": "#4CAF50",        # Green - creation relationships
        "updated": "#2196F3",        # Blue - update relationships
        "references": "#FF9800",     # Orange - reference relationships
        "part_of": "#9C27B0",        # Purple - hierarchical relationships
        "related_to": "#607D8B",     # Blue Grey - general relationships
        "follows": "#00BCD4",        # Cyan - temporal relationships
        "responds_to": "#E91E63",    # Pink - response relationships
        "depends_on": "#F44336",     # Red - dependency relationships
        "contains": "#795548",       # Brown - containment relationships
        "tagged_with": "#FFC107",    # Amber - tagging relationships
    }
    
    # Check if relationship contains any of the mapped types (case-insensitive)
    relationship_lower = relationship.lower()
    for key, color in color_map.items():
        if key in relationship_lower:
            return color
    
    return "#999999"  # Default grey for unknown relationships


def _get_edge_style(relationship: str) -> str:
    """Get dash style for edge based on relationship type."""
    # Define style mapping for relationship types
    style_map = {
        "weak": "5,5",          # Dotted for weak relationships
        "strong": "0",          # Solid for strong relationships
        "temporal": "10,5",     # Long dash for temporal relationships
        "inferred": "2,2",      # Short dash for inferred relationships
        "potential": "5,10",    # Dash-dot for potential relationships
    }
    
    # Check if relationship contains any style keywords
    relationship_lower = relationship.lower()
    for key, style in style_map.items():
        if key in relationship_lower:
            return style
    
    # Default styles for common relationships
    if any(word in relationship_lower for word in ["created", "updated", "depends"]):
        return "0"  # Solid line for strong relationships
    elif any(word in relationship_lower for word in ["related", "references", "tagged"]):
        return "5,5"  # Dotted for looser relationships
    
    return "0"  # Default solid line


def _get_node_color(node_type: NodeType) -> str:
    """Get color for node based on type."""
    color_map = {
        NodeType.AGENT: "#4CAF50",      # Green
        NodeType.USER: "#2196F3",       # Blue
        NodeType.CHANNEL: "#9C27B0",    # Purple
        NodeType.CONCEPT: "#FF9800",    # Orange
        NodeType.CONFIG: "#795548",     # Brown
        NodeType.TSDB_DATA: "#00BCD4",  # Cyan
        NodeType.OBSERVATION: "#E91E63", # Pink
        NodeType.IDENTITY: "#3F51B5",   # Indigo
        NodeType.AUDIT_ENTRY: "#607D8B", # Blue Grey
    }
    return color_map.get(node_type, "#9E9E9E")  # Default grey


def _get_node_size(node: GraphNode) -> int:
    """Calculate node size based on importance/attributes."""
    base_size = 30
    
    # Increase size for nodes with more attributes
    if node.attributes:
        if isinstance(node.attributes, dict):
            attr_count = len([k for k, v in node.attributes.items() if v is not None])
        else:
            # Count non-None fields in GraphNodeAttributes
            attr_count = len([f for f in node.attributes.model_fields if getattr(node.attributes, f, None) is not None])
        base_size += min(attr_count * 2, 20)
    
    # Increase size for identity-related nodes
    if node.scope == GraphScope.IDENTITY:
        base_size += 10
    
    return base_size


def _hierarchy_pos(G: "nx.DiGraph", root: str, width: float = 1., vert_gap: float = 0.2, vert_loc: float = 0, xcenter: float = 0.5) -> Dict[str, Tuple[float, float]]:
    """
    Create a hierarchical tree layout.
    
    If the graph is not a tree, this will still produce a hierarchical layout
    by doing a breadth-first traversal.
    """
    def _hierarchy_pos_recursive(G: "nx.DiGraph", root: str, width: float = 1., vert_gap: float = 0.2, 
                                vert_loc: float = 0, xcenter: float = 0.5, 
                                pos: Optional[Dict[str, Tuple[float, float]]] = None, 
                                parent: Optional[str] = None, 
                                parsed: Optional[set[str]] = None) -> Dict[str, Tuple[float, float]]:
        if pos is None:
            pos = {root: (xcenter, vert_loc)}
        else:
            pos[root] = (xcenter, vert_loc)
            
        if parsed is None:
            parsed = set([root])
        else:
            parsed.add(root)
            
        children = []
        for neighbor in G.neighbors(root):
            if neighbor not in parsed:
                children.append(neighbor)
                
        if len(children) != 0:
            dx = width / len(children)
            nextx = xcenter - width/2 - dx/2
            for child in children:
                nextx += dx
                pos = _hierarchy_pos_recursive(G, child, width=dx, vert_gap=vert_gap, 
                                             vert_loc=vert_loc-vert_gap, xcenter=nextx, pos=pos, 
                                             parent=root, parsed=parsed)
        return pos

    return _hierarchy_pos_recursive(G, root, width, vert_gap, vert_loc, xcenter)


def _calculate_timeline_layout(G: "nx.DiGraph", nodes: List[GraphNode], width: int, height: int, hours: Optional[int] = None) -> Dict[str, Tuple[float, float]]:
    """Calculate timeline layout with nodes arranged chronologically."""
    pos = {}
    
    # Determine the time window
    now = datetime.now(timezone.utc)
    if hours:
        window_start = now - timedelta(hours=hours)
        window_end = now
    else:
        # Default to 24 hours if not specified
        window_start = now - timedelta(hours=24)
        window_end = now
    
    # Collect nodes with timestamps
    nodes_with_time: List[Tuple[datetime, str]] = []
    nodes_without_time = []
    
    for node in nodes:
        node_time = None
        try:
            # Try to get timestamp from various sources
            if isinstance(node.attributes, dict):
                node_time = node.attributes.get('created_at') or node.attributes.get('timestamp')
            else:
                node_time = node.attributes.created_at
            
            # Fallback to top-level updated_at if no timestamp in attributes
            if not node_time and hasattr(node, 'updated_at'):
                node_time = node.updated_at
            
            if node_time:
                # Debug log the raw timestamp value
                logger.debug(f"Node {node.id} raw timestamp: {node_time} (type: {type(node_time)})")
                
                # Convert string to datetime if needed
                if isinstance(node_time, str):
                    # Handle ISO format with Z suffix
                    node_time = datetime.fromisoformat(node_time.replace('Z', UTC_TIMEZONE_SUFFIX))
                
                # Ensure we have a datetime object
                if isinstance(node_time, datetime):
                    # Ensure timezone info
                    if node_time.tzinfo is None:
                        node_time = node_time.replace(tzinfo=timezone.utc)
                    
                    nodes_with_time.append((node_time, node.id))
                    logger.debug(f"Node {node.id} timestamp: {node_time.isoformat()}")
                else:
                    logger.warning(f"Node {node.id} has non-datetime timestamp after parsing: {node_time}")
                    nodes_without_time.append(node.id)
            else:
                nodes_without_time.append(node.id)
        except Exception as e:
            logger.warning(f"Failed to parse timestamp for node {node.id}: {e}")
            nodes_without_time.append(node.id)
    
    # Sort nodes by time
    nodes_with_time.sort()
    
    logger.info(f"Timeline layout: {len(nodes_with_time)} nodes with timestamps, {len(nodes_without_time)} without")
    
    if not nodes_with_time:
        # Fallback to force layout if no timestamps
        layout_result = nx.spring_layout(G)
        # Convert to proper type
        return {node: (float(x), float(y)) for node, (x, y) in layout_result.items()}
    
    # Get time range - use the window range, not the data range
    window_range = (window_end - window_start).total_seconds()
    
    # Get actual data range for logging
    data_min_time = nodes_with_time[0][0]
    data_max_time = nodes_with_time[-1][0]
    data_range = (data_max_time - data_min_time).total_seconds()
    
    logger.info(f"Window range: {window_start.isoformat()} to {window_end.isoformat()} ({window_range/3600:.1f} hours)")
    logger.info(f"Data range: {data_min_time.isoformat()} to {data_max_time.isoformat()} ({data_range/3600:.1f} hours)")
    
    # If all nodes are at the same time or very close, use vertical distribution
    if data_range < 3600:  # Less than 1 hour range
        logger.info("All nodes within 1 hour - using vertical distribution at appropriate x position")
        # Place the group at the correct position within the window
        time_offset = (data_min_time - window_start).total_seconds()
        x = 100 + (time_offset / window_range) * (width - 200)
        y_spacing = (height - 100) / max(len(nodes_with_time), 1)
        for i, (_, node_id) in enumerate(nodes_with_time):
            y = 50 + i * y_spacing + (y_spacing / 2)
            pos[node_id] = (x, y)
    else:
        # Distribute nodes across the timeline proportionally
        x_margin = 100
        available_width = width - 2 * x_margin
        
        # Group nodes that are very close in time (within 5 minutes)
        node_groups: List[List[Tuple[datetime, str]]] = []
        current_group: List[Tuple[datetime, str]] = [nodes_with_time[0]]
        
        for i in range(1, len(nodes_with_time)):
            time_diff = (nodes_with_time[i][0] - current_group[-1][0]).total_seconds()
            if time_diff < 300:  # Within 5 minutes
                current_group.append(nodes_with_time[i])
            else:
                node_groups.append(current_group)
                current_group = [nodes_with_time[i]]
        node_groups.append(current_group)
        
        logger.info(f"Grouped nodes into {len(node_groups)} time groups")
        
        # Position each group
        for group in node_groups:
            # Calculate x position based on the group's average time within the window
            avg_time = sum((t.timestamp() for t, _ in group), 0.0) / len(group)
            avg_datetime = datetime.fromtimestamp(avg_time, tz=timezone.utc)
            time_offset = (avg_datetime - window_start).total_seconds()
            
            # Ensure nodes stay within bounds
            if time_offset < 0:
                # Node is before window start - place at left edge
                x = x_margin
            elif time_offset > window_range:
                # Node is after window end - place at right edge
                x = width - x_margin
            else:
                # Normal case - position proportionally
                x = x_margin + (time_offset / window_range) * available_width
            
            # Distribute nodes in the group vertically with slight x variation
            if len(group) == 1:
                pos[group[0][1]] = (x, height / 2)
            else:
                y_spacing = (height - 100) / len(group)
                for j, (_, node_id) in enumerate(group):
                    # Add small x offset to avoid perfect vertical lines
                    x_offset = (hash(node_id) % 30) - 15
                    y = 50 + j * y_spacing + (y_spacing / 2)
                    pos[node_id] = (x + x_offset, y)
    
    # Place nodes without timestamps at the beginning
    if nodes_without_time:
        # Place them in a vertical column at x=25 (before the timeline)
        y_spacing = (height - 100) / max(len(nodes_without_time), 1)
        for j, node_id in enumerate(nodes_without_time):
            y = 50 + j * y_spacing + (y_spacing / 2)
            pos[node_id] = (25, y)
        logger.info(f"Placed {len(nodes_without_time)} nodes without timestamps at x=25")
    
    # Log final position summary
    if pos:
        x_positions = sorted(set(x for x, y in pos.values()))
        logger.info(f"Timeline positions assigned: {len(pos)} nodes across {len(x_positions)} unique x-positions")
        logger.info(f"X-position range: {min(x_positions):.1f} to {max(x_positions):.1f}")
        if len(x_positions) <= 5:
            logger.info(f"All x-positions: {[f'{x:.1f}' for x in x_positions]}")
    
    return pos


def _generate_svg(G: "nx.DiGraph", pos: Dict[str, tuple], width: int, height: int, 
                  layout: str, hours: Optional[int], edges: Optional[List[GraphEdge]] = None) -> str:
    """Generate SVG visualization of the graph."""
    svg_parts = [
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        f'<rect width="{width}" height="{height}" fill="#f8f9fa"/>',
        '<defs>',
        # Define multiple arrow markers for different relationship types
        '<marker id="arrowhead-default" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">',
        '<polygon points="0 0, 10 3.5, 0 7" fill="#999" />',
        MARKER_END,
        '<marker id="arrowhead-strong" markerWidth="12" markerHeight="8" refX="11" refY="4" orient="auto">',
        '<polygon points="0 0, 12 4, 0 8" fill="#666" />',
        MARKER_END,
        '<marker id="arrowhead-weak" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">',
        '<polygon points="0 0, 8 3, 0 6" fill="#ccc" />',
        MARKER_END,
        # Add hover style
        '<style>',
        '.edge-line { cursor: pointer; }',
        '.edge-line:hover { stroke-width: 4; opacity: 1.0; }',
        '.edge-label { pointer-events: none; font-family: Arial; font-size: 10px; fill: #666; }',
        '</style>',
        '</defs>'
    ]
    
    # Add title
    title = f"Memory Graph Visualization"
    if layout == "timeline" and hours:
        title = f"Memory Timeline - Last {hours} hours"
    svg_parts.append(
        f'<text x="{width//2}" y="30" text-anchor="middle" font-family="Arial" '
        f'font-size="20" font-weight="bold" fill="#333">{title}</text>'
    )
    
    # Draw edges with different styles for different relationship types
    if edges:
        for edge in edges:
            if edge.source in pos and edge.target in pos:
                x1, y1 = pos[edge.source]
                x2, y2 = pos[edge.target]
                
                # Calculate edge style based on relationship type and weight
                edge_color = _get_edge_color(edge.relationship)
                edge_style = _get_edge_style(edge.relationship)
                edge_width = 1 + (edge.weight * 2)  # Width based on weight
                opacity = 0.4 + (edge.weight * 0.4)  # Opacity based on weight
                
                # Choose arrow marker based on weight
                if edge.weight > 0.7:
                    marker = "arrowhead-strong"
                elif edge.weight < 0.3:
                    marker = "arrowhead-weak"
                else:
                    marker = "arrowhead-default"
                
                # Draw edge line with data attributes for interactivity
                svg_parts.append(
                    f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                    f'stroke="{edge_color}" stroke-width="{edge_width}" '
                    f'stroke-dasharray="{edge_style}" '
                    f'marker-end="url(#{marker})" opacity="{opacity}" '
                    f'class="edge-line" '
                    f'data-source="{edge.source}" data-target="{edge.target}" '
                    f'data-relationship="{edge.relationship}" data-weight="{edge.weight}"/>'
                )
                
                # Add edge label at midpoint
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2
                svg_parts.append(
                    f'<text x="{mid_x}" y="{mid_y}" class="edge-label" '
                    f'text-anchor="middle">{edge.relationship}</text>'
                )
    
    # Draw nodes
    for node_id, attrs in G.nodes(data=True):
        x, y = pos[node_id]
        color = attrs.get('color', '#9E9E9E')
        size = attrs.get('size', 30)
        label = attrs.get('label', node_id)
        node_type = attrs.get('type', 'unknown')
        
        # Node circle with data-node-id attribute for click handling
        svg_parts.append(
            f'<circle cx="{x}" cy="{y}" r="{size}" fill="{color}" '
            f'stroke="#333" stroke-width="2" opacity="0.8" '
            f'data-node-id="{node_id}"/>'
        )
        
        # Node label
        svg_parts.append(
            f'<text x="{x}" y="{y + size + 15}" text-anchor="middle" '
            f'font-family="Arial" font-size="12" fill="#333">{label}</text>'
        )
        
        # Node type label
        svg_parts.append(
            f'<text x="{x}" y="{y + 5}" text-anchor="middle" '
            f'font-family="Arial" font-size="10" fill="white" font-weight="bold">{node_type}</text>'
        )
    
    # Add timeline axis if in timeline mode
    if layout == "timeline" and hours:
        # Draw time axis
        svg_parts.append(
            f'<line x1="50" y1="{height - 40}" x2="{width - 50}" y2="{height - 40}" '
            f'stroke="#666" stroke-width="2"/>'
        )
        
        # Add time labels with fixed intervals
        now = datetime.now(timezone.utc)
        # Use predefined safe intervals based on hours range
        if hours <= 6:
            intervals = [0, 1, 2, 3, 4, 5, hours][:hours+1]
        elif hours <= 24:
            intervals = [0, 4, 8, 12, 16, 20, hours]
        elif hours <= 48:
            intervals = [0, 8, 16, 24, 32, 40, hours]
        elif hours <= 96:
            intervals = [0, 16, 32, 48, 64, 80, hours]
        else:  # hours <= 168
            intervals = [0, 24, 48, 72, 96, 120, 144, hours]
        
        # Filter out any duplicates and sort
        intervals = sorted(set(i for i in intervals if i <= hours))
        
        for hour in intervals:
            x = 50 + (hour / hours) * (width - 100)
            time_label = (now - timedelta(hours=hours-hour)).strftime("%m/%d %H:%M")
            svg_parts.append(
                f'<text x="{x}" y="{height - 20}" text-anchor="middle" '
                f'font-family="Arial" font-size="10" fill="#666">{time_label}</text>'
            )
    
    # Add legend
    legend_y = height - 200
    
    # Node types legend
    svg_parts.append(
        f'<text x="20" y="{legend_y}" font-family="Arial" font-size="14" '
        f'font-weight="bold" fill="#333">Node Types:</text>'
    )
    
    type_colors = [
        (NodeType.CONCEPT, "Concept"),
        (NodeType.OBSERVATION, "Observation"),
        (NodeType.IDENTITY, "Identity"),
        (NodeType.CONFIG, "Config"),
    ]
    
    for i, (node_type, label) in enumerate(type_colors):
        y_offset = legend_y + 20 + i * 20
        color = _get_node_color(node_type)
        svg_parts.append(
            f'<circle cx="30" cy="{y_offset}" r="8" fill="{color}" stroke="#333" stroke-width="1"/>'
        )
        svg_parts.append(
            f'<text x="45" y="{y_offset + 5}" font-family="Arial" font-size="12" fill="#333">{label}</text>'
        )
    
    # Edge relationships legend (if we have edges)
    if edges and len(edges) > 0:
        edge_legend_y = legend_y + 100
        svg_parts.append(
            f'<text x="20" y="{edge_legend_y}" font-family="Arial" font-size="14" '
            f'font-weight="bold" fill="#333">Edge Types:</text>'
        )
        
        # Get unique relationship types from displayed edges
        unique_relationships = list(set(edge.relationship for edge in edges))[:4]  # Show max 4
        
        for i, relationship in enumerate(unique_relationships):
            y_offset = edge_legend_y + 20 + i * 20
            color = _get_edge_color(relationship)
            style = _get_edge_style(relationship)
            
            # Draw sample edge line
            svg_parts.append(
                f'<line x1="20" y1="{y_offset}" x2="40" y2="{y_offset}" '
                f'stroke="{color}" stroke-width="2" stroke-dasharray="{style}"/>'
            )
            svg_parts.append(
                f'<text x="45" y="{y_offset + 5}" font-family="Arial" font-size="12" fill="#333">{relationship}</text>'
            )
    
    svg_parts.append('</svg>')
    
    return '\n'.join(svg_parts)

@router.post("/edges", response_model=SuccessResponse[MemoryOpResult])
async def create_edge(
    request: Request,
    body: CreateEdgeRequest,
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[MemoryOpResult]:
    """
    Create an edge between two nodes in the memory graph.
    
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
