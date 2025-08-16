"""
Database query utilities for memory API.

Extracted from memory.py to improve modularity and testability.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

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

    Returns:
        List of GraphNode objects
    """
    nodes = []

    try:
        # Calculate time range
        now = datetime.now()
        start_time = now - timedelta(hours=hours)

        # Build query
        query_parts = [SQL_SELECT_NODES, SQL_FROM_NODES, SQL_WHERE_TIME_RANGE]
        params = [start_time.isoformat(), now.isoformat()]

        if exclude_metrics:
            query_parts.append(SQL_EXCLUDE_METRICS)

        if scope:
            query_parts.append(SQL_WHERE_SCOPE)
            params.append(scope.value if hasattr(scope, "value") else str(scope))

        if node_type:
            query_parts.append(SQL_WHERE_NODE_TYPE)
            params.append(node_type.value if hasattr(node_type, "value") else str(node_type))

        query_parts.append("ORDER BY updated_at DESC")
        query_parts.append(SQL_LIMIT)
        params.append(limit)

        query = " ".join(query_parts)

        # Execute query
        db_path = getattr(memory_service, "db_path", None)
        if not db_path:
            logger.warning("Memory service has no db_path")
            return nodes

        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)

            for row in cursor.fetchall():
                try:
                    # Parse attributes
                    attributes = {}
                    if row[3]:  # attributes_json
                        try:
                            attributes = json.loads(row[3])
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse attributes for node {row[0]}")

                    # Create GraphNode
                    node = GraphNode(
                        id=row[0],  # node_id
                        scope=row[1],  # scope
                        type=row[2],  # node_type
                        attributes=attributes,
                        version=row[4] if row[4] else 1,  # version
                        updated_by=row[5] if row[5] else "system",  # updated_by
                        updated_at=_parse_datetime(row[6]),  # updated_at
                        created_at=_parse_datetime(row[7]) if row[7] else None,  # created_at
                    )
                    nodes.append(node)

                except Exception as e:
                    logger.error(f"Failed to create GraphNode from row: {e}")
                    continue

    except Exception as e:
        logger.error(f"Failed to query timeline nodes: {e}")

    return nodes


async def get_memory_stats(memory_service: Any) -> Dict[str, Any]:
    """
    Get statistics about memory storage.

    Args:
        memory_service: Memory service instance

    Returns:
        Dictionary with memory statistics
    """
    stats = {
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
            cursor.execute("SELECT node_type, COUNT(*) FROM graph_nodes GROUP BY node_type")
            for row in cursor.fetchall():
                stats["nodes_by_type"][row[0]] = row[1]

            # Nodes by scope
            cursor.execute("SELECT scope, COUNT(*) FROM graph_nodes GROUP BY scope")
            for row in cursor.fetchall():
                stats["nodes_by_scope"][row[0]] = row[1]

            # Recent activity (last 24 hours)
            now = datetime.now()
            yesterday = now - timedelta(days=1)

            cursor.execute("SELECT COUNT(*) FROM graph_nodes WHERE updated_at >= ?", (yesterday.isoformat(),))
            stats["recent_activity"]["nodes_24h"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM graph_edges WHERE created_at >= ?", (yesterday.isoformat(),))
            stats["recent_activity"]["edges_24h"] = cursor.fetchone()[0]

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

    Returns:
        List of matching GraphNode objects
    """
    nodes = []

    try:
        # Build query
        query_parts = [SQL_SELECT_NODES, SQL_FROM_NODES, "WHERE 1=1"]
        params = []

        if node_type:
            query_parts.append("AND node_type = ?")
            params.append(node_type.value if hasattr(node_type, "value") else str(node_type))

        if scope:
            query_parts.append("AND scope = ?")
            params.append(scope.value if hasattr(scope, "value") else str(scope))

        if since:
            query_parts.append("AND updated_at >= ?")
            params.append(since.isoformat())

        if until:
            query_parts.append("AND updated_at <= ?")
            params.append(until.isoformat())

        if query:
            # Simple text search in attributes
            query_parts.append("AND attributes_json LIKE ?")
            params.append(f"%{query}%")

        if tags:
            # Search for tags in attributes
            for tag in tags:
                query_parts.append("AND attributes_json LIKE ?")
                params.append(f'%"{tag}"%')

        query_parts.append("ORDER BY updated_at DESC")
        query_parts.append(f"LIMIT {limit} OFFSET {offset}")

        sql_query = " ".join(query_parts)

        # Execute query
        db_path = getattr(memory_service, "db_path", None)
        if not db_path:
            return nodes

        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql_query, params)

            for row in cursor.fetchall():
                try:
                    # Parse attributes
                    attributes = {}
                    if row[3]:  # attributes_json
                        try:
                            attributes = json.loads(row[3])
                        except json.JSONDecodeError:
                            pass

                    # Create GraphNode
                    node = GraphNode(
                        id=row[0],
                        scope=row[1],
                        type=row[2],
                        attributes=attributes,
                        version=row[4] if row[4] else 1,
                        updated_by=row[5] if row[5] else "system",
                        updated_at=_parse_datetime(row[6]),
                        created_at=_parse_datetime(row[7]) if row[7] else None,
                    )
                    nodes.append(node)

                except Exception as e:
                    logger.error(f"Failed to create GraphNode from row: {e}")
                    continue

    except Exception as e:
        logger.error(f"Failed to search nodes: {e}")

    return nodes


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
