"""
Database query utilities for memory API.

Extracted from memory.py to improve modularity and testability.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.logic.utils.jsondict_helpers import get_dict
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict

from .memory_query_helpers import DatabaseExecutor, DateTimeParser, GraphNodeBuilder, QueryBuilder, TimeRangeCalculator

logger = logging.getLogger(__name__)

# SQL Query Constants
SQL_SELECT_NODES = "SELECT node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at"
SQL_FROM_NODES = "FROM graph_nodes"
SQL_WHERE_TIME_RANGE = "WHERE updated_at >= ? AND updated_at < ?"
SQL_EXCLUDE_METRICS = "AND NOT (node_type = 'tsdb_data' AND node_id LIKE 'metric_%')"
SQL_WHERE_SCOPE = "AND scope = ?"
SQL_WHERE_NODE_TYPE = "AND node_type = ?"
SQL_ORDER_RANDOM = "ORDER BY RANDOM()"
SQL_LIMIT = "LIMIT ?"


async def query_timeline_nodes(
    memory_service: Any,
    hours: int = 24,
    scope: Optional[str] = None,
    node_type: Optional[str] = None,
    limit: int = 100,
    exclude_metrics: bool = True,
    user_filter_ids: Optional[List[str]] = None,
) -> List[GraphNode]:
    """
    Query nodes from memory within a time range.

    Args:
        memory_service: Memory service instance
        hours: Number of hours to look back
        scope: Optional scope filter
        node_type: Optional node type filter
        limit: Maximum number of results
        exclude_metrics: Whether to exclude metric nodes
        user_filter_ids: Optional list of user IDs for OBSERVER filtering (SQL Layer 1)

    Returns:
        List of GraphNode objects
    """
    # Get database path
    db_path = DatabaseExecutor.get_db_path(memory_service)
    if not db_path:
        return []

    # Calculate time range
    start_time, end_time = TimeRangeCalculator.calculate_range(hours)

    # Build query with all filters (including user filtering for OBSERVER users)
    query, params = QueryBuilder.build_timeline_query(
        start_time=start_time,
        end_time=end_time,
        scope=scope,
        node_type=node_type,
        exclude_metrics=exclude_metrics,
        limit=limit,
        user_filter_ids=user_filter_ids,
    )

    # Execute query and get rows
    rows = DatabaseExecutor.execute_query(db_path, query, params)

    # Build GraphNode objects from rows
    return GraphNodeBuilder.build_from_rows(rows)


async def get_memory_stats(memory_service: Any) -> JSONDict:
    """
    Get statistics about memory storage.

    Args:
        memory_service: Memory service instance

    Returns:
        Dictionary with memory statistics
    """
    stats: JSONDict = {
        "total_nodes": 0,
        "total_edges": 0,
        "nodes_by_type": {},
        "nodes_by_scope": {},
        "recent_activity": {},
        "storage_size_mb": 0.0,
    }

    try:
        db_path = getattr(memory_service, "db_path", None)
        if not db_path:
            return stats

        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()

            # Total nodes
            cursor.execute("SELECT COUNT(*) FROM graph_nodes")
            stats["total_nodes"] = cursor.fetchone()[0]

            # Total edges
            cursor.execute("SELECT COUNT(*) FROM graph_edges")
            stats["total_edges"] = cursor.fetchone()[0]

            # Nodes by type
            nodes_by_type = get_dict(stats, "nodes_by_type", {})
            cursor.execute("SELECT node_type, COUNT(*) FROM graph_nodes GROUP BY node_type")
            for row in cursor.fetchall():
                nodes_by_type[row[0]] = row[1]

            # Nodes by scope
            nodes_by_scope = get_dict(stats, "nodes_by_scope", {})
            cursor.execute("SELECT scope, COUNT(*) FROM graph_nodes GROUP BY scope")
            for row in cursor.fetchall():
                nodes_by_scope[row[0]] = row[1]

            # Recent activity (last 24 hours)
            recent_activity = get_dict(stats, "recent_activity", {})
            now = datetime.now()
            yesterday = now - timedelta(days=1)

            from ciris_engine.logic.persistence.db.dialect import get_adapter

            placeholder = get_adapter().placeholder()

            cursor.execute(
                f"SELECT COUNT(*) FROM graph_nodes WHERE updated_at >= {placeholder}", (yesterday.isoformat(),)
            )
            recent_activity["nodes_24h"] = cursor.fetchone()[0]

            cursor.execute(
                f"SELECT COUNT(*) FROM graph_edges WHERE created_at >= {placeholder}", (yesterday.isoformat(),)
            )
            recent_activity["edges_24h"] = cursor.fetchone()[0]

            # Storage size
            import os

            if os.path.exists(db_path):
                stats["storage_size_mb"] = os.path.getsize(db_path) / (1024 * 1024)

    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")

    return stats


async def search_nodes(
    memory_service: Any,
    query: Optional[str] = None,
    node_type: Optional[NodeType] = None,
    scope: Optional[GraphScope] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    tags: Optional[List[str]] = None,
    limit: int = 20,
    offset: int = 0,
    user_filter_ids: Optional[List[str]] = None,
) -> List[GraphNode]:
    """
    Search for nodes in memory with various filters.

    Args:
        memory_service: Memory service instance
        query: Text search query
        node_type: Filter by node type
        scope: Filter by scope
        since: Filter by minimum timestamp
        until: Filter by maximum timestamp
        tags: Filter by tags
        limit: Maximum results
        offset: Pagination offset
        user_filter_ids: Optional list of user IDs for OBSERVER filtering (SQL Layer 1)

    Returns:
        List of matching GraphNode objects
    """
    # Get database path
    db_path = DatabaseExecutor.get_db_path(memory_service)
    if not db_path:
        return []

    # Build search query with all filters (including user filtering for OBSERVER users)
    sql_query, params = QueryBuilder.build_search_query(
        query=query,
        node_type=node_type,
        scope=scope,
        since=since,
        until=until,
        tags=tags,
        limit=limit,
        offset=offset,
        user_filter_ids=user_filter_ids,
    )

    # Execute query and get rows
    rows = DatabaseExecutor.execute_query(db_path, sql_query, params)

    # Build GraphNode objects from rows
    return GraphNodeBuilder.build_from_rows(rows)


def _parse_datetime(value: Any) -> Optional[datetime]:
    """Parse datetime from various formats."""
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            # Try ISO format
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            pass

        try:
            # Try without timezone
            return datetime.fromisoformat(value.split("+")[0])
        except ValueError:
            pass

    return None
