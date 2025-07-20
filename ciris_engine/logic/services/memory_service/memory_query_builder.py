"""
Memory Query Builder for consolidating query patterns.

Provides a consistent interface for building different types of memory queries.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

from ciris_engine.logic.persistence import get_db_connection
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.adapters.memory import QueryRequest, MemorySearchFilter
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.protocols.services.graph import MemoryServiceProtocol

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    """Types of memory queries."""
    NODE_ID = "node_id"
    TEXT_SEARCH = "text_search"
    RELATED = "related"
    TIME_RANGE = "time_range"
    TYPE_FILTER = "type_filter"
    WILDCARD = "wildcard"


class MemoryQueryBuilder:
    """Builder for memory queries with consistent patterns."""
    
    # SQL query fragments
    SQL_SELECT_NODES = "SELECT node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at"
    SQL_FROM_NODES = "FROM graph_nodes"
    SQL_WHERE_NODE_ID = "WHERE node_id = ?"
    SQL_WHERE_TIME_RANGE = "WHERE updated_at >= ? AND updated_at < ?"
    SQL_WHERE_SCOPE = "AND scope = ?"
    SQL_WHERE_NODE_TYPE = "AND node_type = ?"
    SQL_WHERE_TEXT_SEARCH = "AND (attributes_json LIKE ? OR node_id LIKE ?)"
    SQL_EXCLUDE_METRICS = "AND NOT (node_type = 'tsdb_data' AND node_id LIKE 'metric_%')"
    SQL_ORDER_BY_TIME = "ORDER BY updated_at DESC"
    SQL_ORDER_RANDOM = "ORDER BY RANDOM()"
    SQL_LIMIT = "LIMIT ?"
    SQL_OFFSET = "OFFSET ?"
    
    def __init__(self, memory_service: MemoryServiceProtocol):
        """Initialize query builder with memory service."""
        self.memory_service = memory_service
    
    def determine_query_type(self, request: QueryRequest) -> QueryType:
        """Determine the type of query from request parameters."""
        if request.node_id and request.node_id != "*":
            return QueryType.NODE_ID
        elif request.query:
            return QueryType.TEXT_SEARCH
        elif request.related_to:
            return QueryType.RELATED
        elif request.since or request.until:
            return QueryType.TIME_RANGE
        elif request.type:
            return QueryType.TYPE_FILTER
        else:
            return QueryType.WILDCARD
    
    async def build_and_execute(self, request: QueryRequest) -> List[GraphNode]:
        """Build and execute appropriate query based on request."""
        query_type = self.determine_query_type(request)
        
        if query_type == QueryType.NODE_ID:
            return await self._query_by_node_id(request)
        elif query_type == QueryType.TEXT_SEARCH:
            return await self._query_by_text(request)
        elif query_type == QueryType.RELATED:
            return await self._query_related_nodes(request)
        elif query_type == QueryType.TIME_RANGE:
            return await self._query_by_time_range(request)
        elif query_type == QueryType.TYPE_FILTER:
            return await self._query_by_type(request)
        else:
            return await self._query_wildcard(request)
    
    async def _query_by_node_id(self, request: QueryRequest) -> List[GraphNode]:
        """Query for specific node by ID."""
        query = MemoryQuery(
            node_id=request.node_id,
            scope=request.scope or GraphScope.LOCAL,
            type=request.type,
            include_edges=request.include_edges,
            depth=request.depth or 1
        )
        return await self.memory_service.recall(query)
    
    async def _query_by_text(self, request: QueryRequest) -> List[GraphNode]:
        """Query nodes by text search."""
        filters = MemorySearchFilter(
            scope=request.scope.value if request.scope else None,
            node_type=request.type.value if request.type else None,
            tags=request.tags,
            limit=request.limit or 100
        )
        nodes = await self.memory_service.search(request.query, filters=filters)
        
        # Apply time filtering if specified
        if request.since or request.until:
            nodes = self._filter_by_time(nodes, request.since, request.until)
        
        return nodes[:request.limit] if request.limit else nodes
    
    async def _query_related_nodes(self, request: QueryRequest) -> List[GraphNode]:
        """Query nodes related to a specific node."""
        query = MemoryQuery(
            node_id=request.related_to,
            scope=request.scope or GraphScope.LOCAL,
            type=request.type,
            include_edges=True,
            depth=request.depth or 2
        )
        related_nodes = await self.memory_service.recall(query)
        
        # Filter out the source node
        return [n for n in related_nodes if n.id != request.related_to]
    
    async def _query_by_time_range(self, request: QueryRequest) -> List[GraphNode]:
        """Query nodes within a time range."""
        # Use direct SQL for efficient time-based queries
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Build query
                query_parts = [
                    self.SQL_SELECT_NODES,
                    self.SQL_FROM_NODES,
                    self.SQL_WHERE_TIME_RANGE
                ]
                
                params: List[Any] = [
                    request.since.isoformat() if request.since else "1970-01-01T00:00:00+00:00",
                    request.until.isoformat() if request.until else datetime.now(timezone.utc).isoformat()
                ]
                
                # Add filters
                if request.scope:
                    query_parts.append(self.SQL_WHERE_SCOPE)
                    params.append(request.scope.value)
                
                if request.type:
                    query_parts.append(self.SQL_WHERE_NODE_TYPE)
                    params.append(request.type.value)
                
                # Add ordering and limit
                query_parts.extend([
                    self.SQL_ORDER_BY_TIME,
                    self.SQL_LIMIT
                ])
                params.append(request.limit or 100)
                
                if request.offset:
                    query_parts.append(self.SQL_OFFSET)
                    params.append(request.offset)
                
                query = " ".join(query_parts)
                cursor.execute(query, params)
                
                # Convert results to GraphNode objects
                nodes = []
                for row in cursor.fetchall():
                    try:
                        node = self._row_to_graph_node(row)
                        nodes.append(node)
                    except Exception as e:
                        logger.warning(f"Failed to parse node from row: {e}")
                
                return nodes
                
        except Exception as e:
            logger.error(f"Time range query failed: {e}")
            # Fall back to memory service
            return await self._fallback_time_query(request)
    
    async def _query_by_type(self, request: QueryRequest) -> List[GraphNode]:
        """Query nodes by type."""
        all_nodes = await self.memory_service.recall(MemoryQuery(
            node_id="*",
            scope=request.scope or GraphScope.LOCAL,
            type=request.type,
            include_edges=False,
            depth=1
        ))
        
        # Apply additional filters
        if request.since or request.until:
            all_nodes = self._filter_by_time(all_nodes, request.since, request.until)
        
        return all_nodes[:request.limit] if request.limit else all_nodes
    
    async def _query_wildcard(self, request: QueryRequest) -> List[GraphNode]:
        """Query all nodes with optional filters."""
        query = MemoryQuery(
            node_id="*",
            scope=request.scope or GraphScope.LOCAL,
            type=request.type,
            include_edges=request.include_edges,
            depth=request.depth or 1
        )
        return await self.memory_service.recall(query)
    
    def _filter_by_time(
        self,
        nodes: List[GraphNode],
        since: Optional[datetime],
        until: Optional[datetime]
    ) -> List[GraphNode]:
        """Filter nodes by time range."""
        filtered = []
        
        for node in nodes:
            node_time = self._get_node_time(node)
            if node_time:
                if since and node_time < since:
                    continue
                if until and node_time > until:
                    continue
                filtered.append(node)
        
        return filtered
    
    def _get_node_time(self, node: GraphNode) -> Optional[datetime]:
        """Extract timestamp from node."""
        # Try attributes first
        if isinstance(node.attributes, dict):
            time_val = node.attributes.get('created_at') or node.attributes.get('timestamp')
        else:
            time_val = getattr(node.attributes, 'created_at', None)
        
        # Fall back to updated_at
        if not time_val and hasattr(node, 'updated_at'):
            time_val = node.updated_at
        
        # Convert to datetime if needed
        if time_val:
            if isinstance(time_val, str):
                try:
                    return datetime.fromisoformat(time_val.replace('Z', '+00:00'))
                except Exception:
                    return None
            elif isinstance(time_val, datetime):
                return time_val
        
        return None
    
    def _row_to_graph_node(self, row: Dict[str, Any]) -> GraphNode:
        """Convert database row to GraphNode."""
        import json
        
        attributes = json.loads(row['attributes_json']) if row['attributes_json'] else {}
        
        return GraphNode(
            id=row['node_id'],
            type=NodeType(row['node_type']),
            scope=GraphScope(row['scope']),
            attributes=attributes,
            version=row['version'],
            updated_by=row['updated_by'],
            updated_at=datetime.fromisoformat(row['updated_at'].replace('Z', '+00:00'))
        )
    
    async def _fallback_time_query(self, request: QueryRequest) -> List[GraphNode]:
        """Fallback query using memory service when direct SQL fails."""
        # Get all nodes and filter
        all_nodes = await self.memory_service.recall(MemoryQuery(
            node_id="*",
            scope=request.scope or GraphScope.LOCAL,
            type=request.type,
            include_edges=False,
            depth=1
        ))
        
        # Filter by time
        filtered = self._filter_by_time(all_nodes, request.since, request.until)
        
        # Apply limit
        return filtered[:request.limit] if request.limit else filtered