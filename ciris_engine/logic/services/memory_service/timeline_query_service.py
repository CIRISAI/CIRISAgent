"""
Timeline Query Service for Memory API.

Extracts complex time bucketing and sampling logic from the memory routes.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any

from ciris_engine.logic.persistence import get_db_connection
from ciris_engine.schemas.adapters.memory import QueryRequest, TimelineResponse
from ciris_engine.schemas.services.graph_core import GraphNode, GraphEdge, GraphScope, NodeType, GraphEdgeAttributes
from ciris_engine.protocols.services.graph import MemoryServiceProtocol

logger = logging.getLogger(__name__)

# SQL constants (shared with memory routes)
SQL_SELECT_NODES = "SELECT node_id, scope, node_type, attributes_json, version, updated_by, updated_at"
SQL_FROM_NODES = "FROM graph_nodes"
SQL_WHERE_TIME_RANGE = "WHERE updated_at >= ? AND updated_at < ?"
SQL_EXCLUDE_METRICS = "AND node_type != 'metric'"
SQL_WHERE_SCOPE = "AND scope = ?"
SQL_WHERE_NODE_TYPE = "AND node_type = ?"
SQL_ORDER_RANDOM = "ORDER BY RANDOM()"
SQL_LIMIT = "LIMIT ?"

UTC_TIMEZONE_SUFFIX = "+00:00"


class TimelineQueryService:
    """Service for handling timeline queries with efficient time bucketing."""
    
    def __init__(self, memory_service: MemoryServiceProtocol):
        self.memory_service = memory_service
        
    async def get_timeline(
        self,
        hours: int,
        bucket_size: str,
        scope: Optional[GraphScope] = None,
        node_type: Optional[NodeType] = None,
        limit: int = 1000,
        include_edges: bool = False
    ) -> TimelineResponse:
        """
        Get timeline view of memories with time bucketing.
        
        Args:
            hours: Number of hours to look back
            bucket_size: Size of time buckets ("hour" or "day")
            scope: Optional scope filter
            node_type: Optional node type filter
            limit: Maximum number of nodes to return
            include_edges: Whether to include edges
            
        Returns:
            TimelineResponse with nodes, edges, and bucket counts
        """
        # Calculate time range
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=hours)
        
        # Query nodes
        nodes = await self._query_timeline_nodes(
            start_time, now, scope, node_type, limit
        )
        
        # Sort by time
        nodes = self._sort_nodes_by_time(nodes)
        
        # Create time buckets
        buckets = self._create_time_buckets(
            nodes, start_time, now, bucket_size
        )
        
        # Limit nodes to return
        returned_nodes = nodes[:limit]
        
        # Fetch edges if requested
        edges = None
        if include_edges and returned_nodes:
            edges = await self._fetch_edges_for_nodes(returned_nodes)
            
        return TimelineResponse(
            memories=returned_nodes,
            edges=edges,
            buckets=buckets,
            start_time=start_time,
            end_time=now,
            total=len(nodes)
        )
    
    async def _query_timeline_nodes(
        self,
        start_time: datetime,
        end_time: datetime,
        scope: Optional[GraphScope],
        node_type: Optional[NodeType],
        limit: int
    ) -> List[GraphNode]:
        """Query nodes within time range with sampling."""
        try:
            return await self._query_with_day_sampling(
                start_time, end_time, scope, node_type, limit
            )
        except Exception as e:
            logger.error(f"Failed to query timeline data: {e}")
            # Fall back to standard search
            return await self._fallback_search(
                start_time, end_time, scope, node_type
            )
    
    async def _query_with_day_sampling(
        self,
        start_time: datetime,
        end_time: datetime,
        scope: Optional[GraphScope],
        node_type: Optional[NodeType],
        limit: int
    ) -> List[GraphNode]:
        """Query nodes with sampling across days for better distribution."""
        nodes = []
        
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Calculate sampling parameters
            days_in_range = int((end_time - start_time).total_seconds() / 86400) + 1
            nodes_per_day = max(1, limit // days_in_range)
            
            # Sample nodes from each day
            all_db_nodes = []
            for day_offset in range(days_in_range):
                day_nodes = self._query_day_nodes(
                    cursor, end_time, day_offset, scope, node_type, nodes_per_day
                )
                all_db_nodes.extend(day_nodes)
            
            # Apply sampling if we have too many nodes
            if len(all_db_nodes) > limit:
                nodes = self._sample_nodes_evenly(all_db_nodes, limit)
            else:
                nodes = all_db_nodes
                
        return nodes
    
    def _query_day_nodes(
        self,
        cursor,
        end_time: datetime,
        day_offset: int,
        scope: Optional[GraphScope],
        node_type: Optional[NodeType],
        nodes_per_day: int
    ) -> List[GraphNode]:
        """Query nodes for a specific day."""
        day_start = (end_time - timedelta(days=day_offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        day_end = day_start + timedelta(days=1)
        
        # Build query
        query_parts = [
            SQL_SELECT_NODES,
            SQL_FROM_NODES,
            SQL_WHERE_TIME_RANGE,
            SQL_EXCLUDE_METRICS
        ]
        params: List[Any] = [day_start.isoformat(), day_end.isoformat()]
        
        # Add filters
        if scope:
            query_parts.append(SQL_WHERE_SCOPE)
            params.append(scope.value)
            
        if node_type:
            query_parts.append(SQL_WHERE_NODE_TYPE)
            params.append(node_type.value)
            
        # Random sampling for better distribution
        query_parts.extend([SQL_ORDER_RANDOM, SQL_LIMIT])
        params.append(nodes_per_day * 2)  # Get extra to allow for filtering
        
        query = " ".join(query_parts)
        cursor.execute(query, params)
        
        # Convert rows to GraphNode objects
        nodes = []
        for row in cursor.fetchall():
            try:
                node = self._row_to_graph_node(row)
                nodes.append(node)
            except Exception as e:
                logger.warning(f"Failed to parse node {row['node_id']}: {e}")
                
        return nodes
    
    def _row_to_graph_node(self, row: Dict[str, Any]) -> GraphNode:
        """Convert database row to GraphNode."""
        attributes = json.loads(row['attributes_json']) if row['attributes_json'] else {}
        
        return GraphNode(
            id=row['node_id'],
            type=NodeType(row['node_type']),
            scope=GraphScope(row['scope']),
            attributes=attributes,
            version=row['version'],
            updated_by=row['updated_by'],
            updated_at=datetime.fromisoformat(
                row['updated_at'].replace('Z', UTC_TIMEZONE_SUFFIX)
            )
        )
    
    def _sample_nodes_evenly(
        self,
        nodes: List[GraphNode],
        limit: int
    ) -> List[GraphNode]:
        """Sample nodes evenly across time buckets."""
        # Group by hour buckets
        hour_buckets: Dict[datetime, List[GraphNode]] = {}
        for node in nodes:
            if node.updated_at is None:
                continue
            hour = node.updated_at.replace(minute=0, second=0, microsecond=0)
            if hour not in hour_buckets:
                hour_buckets[hour] = []
            hour_buckets[hour].append(node)
        
        # Sample nodes from each bucket
        sampled_nodes = []
        target_per_bucket = max(1, limit // len(hour_buckets)) if hour_buckets else 1
        
        for hour, bucket_nodes in hour_buckets.items():
            # Take up to target_per_bucket nodes from each hour
            sampled = bucket_nodes[:target_per_bucket]
            sampled_nodes.extend(sampled)
        
        # If we don't have enough, add more from the most populated buckets
        if len(sampled_nodes) < limit:
            remaining = limit - len(sampled_nodes)
            sorted_buckets = sorted(
                hour_buckets.items(),
                key=lambda x: len(x[1]),
                reverse=True
            )
            
            for hour, bucket_nodes in sorted_buckets:
                already_taken = min(target_per_bucket, len(bucket_nodes))
                available = bucket_nodes[already_taken:]
                if available:
                    take = min(len(available), remaining)
                    sampled_nodes.extend(available[:take])
                    remaining -= take
                    if remaining <= 0:
                        break
                        
        return sampled_nodes
    
    async def _fallback_search(
        self,
        start_time: datetime,
        end_time: datetime,
        scope: Optional[GraphScope],
        node_type: Optional[NodeType]
    ) -> List[GraphNode]:
        """Fallback to standard search when direct query fails."""
        from ciris_engine.schemas.adapters.memory import MemorySearchFilter
        
        all_nodes = await self.memory_service.search("", filters=MemorySearchFilter(
            scope=scope.value if scope else None,
            node_type=node_type.value if node_type else None,
            limit=1000
        ))
        
        # Filter by time
        filtered_nodes = []
        for node in all_nodes:
            node_time = self._get_node_time(node)
            if node_time and start_time <= node_time <= end_time:
                filtered_nodes.append(node)
                
        return filtered_nodes
    
    def _get_node_time(self, node: GraphNode) -> Optional[datetime]:
        """Extract timestamp from node attributes."""
        if isinstance(node.attributes, dict):
            time_val = node.attributes.get('created_at') or node.attributes.get('timestamp')
        else:
            time_val = getattr(node.attributes, 'created_at', None)
        
        # Fallback to top-level updated_at
        if not time_val and hasattr(node, 'updated_at'):
            time_val = node.updated_at
        
        if time_val:
            if isinstance(time_val, str):
                return datetime.fromisoformat(time_val.replace('Z', UTC_TIMEZONE_SUFFIX))
            elif isinstance(time_val, datetime):
                return time_val
                
        return None
    
    def _sort_nodes_by_time(self, nodes: List[GraphNode]) -> List[GraphNode]:
        """Sort nodes by timestamp."""
        def get_sort_key(n: GraphNode) -> str:
            time_val = self._get_node_time(n)
            return str(time_val) if time_val else ''
            
        return sorted(nodes, key=get_sort_key, reverse=True)
    
    def _create_time_buckets(
        self,
        nodes: List[GraphNode],
        start_time: datetime,
        end_time: datetime,
        bucket_size: str
    ) -> Dict[str, int]:
        """Create time buckets and count nodes in each."""
        buckets = {}
        bucket_delta = timedelta(hours=1) if bucket_size == "hour" else timedelta(days=1)
        
        # Initialize buckets
        current_bucket = start_time
        while current_bucket < end_time:
            bucket_key = current_bucket.strftime(
                "%Y-%m-%d %H:00" if bucket_size == "hour" else "%Y-%m-%d"
            )
            buckets[bucket_key] = 0
            current_bucket += bucket_delta
        
        # Count nodes in buckets
        for node in nodes:
            node_time = self._get_node_time(node)
            if node_time:
                bucket_key = node_time.strftime(
                    "%Y-%m-%d %H:00" if bucket_size == "hour" else "%Y-%m-%d"
                )
                if bucket_key in buckets:
                    buckets[bucket_key] += 1
                    
        return buckets
    
    async def _fetch_edges_for_nodes(
        self,
        nodes: List[GraphNode]
    ) -> List[GraphEdge]:
        """Fetch edges for given nodes."""
        node_ids = [n.id for n in nodes]
        edges = []
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                
                # Query edges where either source or target is in our node list
                placeholders = ','.join('?' * len(node_ids))
                query = f"""
                SELECT edge_id, source_node_id, target_node_id, scope, 
                       relationship, weight, attributes_json, created_at
                FROM graph_edges
                WHERE source_node_id IN ({placeholders}) 
                   OR target_node_id IN ({placeholders})
                """
                
                cursor.execute(query, node_ids + node_ids)
                
                for row in cursor.fetchall():
                    try:
                        edge = self._row_to_graph_edge(row)
                        edges.append(edge)
                    except Exception as e:
                        logger.warning(f"Failed to parse edge {row[0]}: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to fetch edges: {e}")
            
        return edges
    
    def _row_to_graph_edge(self, row: Tuple[Any, ...]) -> GraphEdge:
        """Convert database row to GraphEdge."""
        # row: edge_id, source_node_id, target_node_id, scope, 
        #      relationship, weight, attributes_json, created_at
        attributes_json = json.loads(row[6]) if row[6] else {}
        
        # Create GraphEdgeAttributes
        edge_attrs = GraphEdgeAttributes(
            created_at=attributes_json.get('created_at', row[7]),
            context=attributes_json.get('context')
        )
        
        return GraphEdge(
            source=row[1],  # source_node_id
            target=row[2],  # target_node_id
            relationship=row[4],  # relationship type
            scope=row[3],  # scope
            weight=row[5] if row[5] is not None else 1.0,
            attributes=edge_attrs
        )