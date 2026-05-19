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
    # db_path retained for signature compat; persist owns the connection.
    db_path = DatabaseExecutor.get_db_path(memory_service)

    # Calculate time range
    start_time, end_time = TimeRangeCalculator.calculate_range(hours)

    logger.info(
        f"[TIMELINE-QUERY] Time range: start={start_time.isoformat()}, end={end_time.isoformat()}, hours={hours}"
    )

    # Build persist NodeFilter + client-side post-options.
    node_filter, post_options = QueryBuilder.build_timeline_query(
        start_time=start_time,
        end_time=end_time,
        scope=scope,
        node_type=node_type,
        exclude_metrics=exclude_metrics,
        limit=limit,
        user_filter_ids=user_filter_ids,
    )

    # Execute via persist substrate.
    rows = DatabaseExecutor.execute_query(db_path, node_filter, post_options)

    # Build GraphNode objects from persist rows.
    return GraphNodeBuilder.build_from_rows(rows)


async def get_memory_stats(memory_service: Any) -> JSONDict:
    """Get statistics about memory storage.

    Post-A1 absorption (CIRISAgent#763, CIRISPersist#65): counts are
    aggregated via persist's `cirisgraph_count_*` substrate. Recent-
    activity buckets use `cirisgraph_query_nodes` with `updated_after`
    filter (#62) so we don't paginate the full graph just to count.
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
        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        if engine is None:
            return stats

        # Sum totals + by-type counts across every scope. Persist's
        # `cirisgraph_count_nodes` requires a scope filter; we sum across
        # all known scopes.
        scopes = ("LOCAL", "COMMUNITY", "IDENTITY", "ENVIRONMENT")
        nodes_by_type = get_dict(stats, "nodes_by_type", {})
        nodes_by_scope = get_dict(stats, "nodes_by_scope", {})

        total_nodes = 0
        total_edges = 0
        for scope in scopes:
            n_nodes = int(engine.cirisgraph_count_nodes(json.dumps({"scope": scope})))
            n_edges = int(engine.cirisgraph_count_edges(scope))
            total_nodes += n_nodes
            total_edges += n_edges
            if n_nodes:
                nodes_by_scope[scope] = n_nodes
            # By type within scope
            raw = engine.cirisgraph_count_nodes_by_type(scope)
            per_type = json.loads(raw) if isinstance(raw, (bytes, str)) else (raw or {})
            for ntype, count in per_type.items():
                nodes_by_type[ntype] = nodes_by_type.get(ntype, 0) + int(count)

        stats["total_nodes"] = total_nodes
        stats["total_edges"] = total_edges

        # Recent activity: count nodes/edges updated in the last 24h via
        # the updated_after filter (CIRISPersist#62 / #65). Sum across scopes.
        now = datetime.now()
        yesterday = (now - timedelta(days=1)).isoformat()
        recent_activity = get_dict(stats, "recent_activity", {})
        recent_nodes = 0
        for scope in scopes:
            recent_nodes += int(
                engine.cirisgraph_count_nodes(
                    json.dumps({"scope": scope, "updated_after": yesterday})
                )
            )
        recent_activity["nodes_24h"] = recent_nodes
        # Persist's `cirisgraph_count_edges` is scope-only (no time filter
        # in 1.6.0); recent edges fall back to 0 until upstream adds the
        # time-windowed counter.
        recent_activity["edges_24h"] = 0

        # Storage size: best-effort against the engine DSN. Persist owns
        # the file; if the agent can resolve a SQLite path on disk, size
        # it; otherwise skip (Postgres deployments don't have a file).
        try:
            import os

            from ciris_engine.logic.persistence import get_sqlite_db_full_path

            sqlite_path = get_sqlite_db_full_path()
            if isinstance(sqlite_path, str) and os.path.exists(sqlite_path):
                stats["storage_size_mb"] = os.path.getsize(sqlite_path) / (1024 * 1024)
        except Exception:
            pass

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
    # db_path retained for signature compat; persist owns the connection.
    db_path = DatabaseExecutor.get_db_path(memory_service)

    # Build persist NodeFilter + client-side post-options.
    node_filter, post_options = QueryBuilder.build_search_query(
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

    # Execute via persist substrate.
    rows = DatabaseExecutor.execute_query(db_path, node_filter, post_options)

    # Build GraphNode objects from persist rows.
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
