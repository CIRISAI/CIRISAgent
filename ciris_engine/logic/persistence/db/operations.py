"""
High-level database operations that are dialect-agnostic.

This module provides a clean API for common database operations without
exposing SQL dialect details to business logic. All operations automatically
adapt to the configured database backend (SQLite, PostgreSQL, etc.).

Business logic should use these operations instead of writing raw SQL.

Examples:
    >>> from ciris_engine.logic.persistence.db.operations import insert_node_if_not_exists
    >>> inserted = insert_node_if_not_exists(
    ...     node_id="user_123",
    ...     scope="local",
    ...     node_type="user",
    ...     attributes={"name": "Alice"},
    ... )
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.logic.persistence.db.query_builder import ConflictResolution

logger = logging.getLogger(__name__)


def insert_node_if_not_exists(
    node_id: str,
    scope: str,
    node_type: str,
    attributes: Dict[str, Any],
    version: int = 1,
    updated_by: str = "system",
    db_path: Optional[str] = None,
) -> bool:
    """Insert a graph node, ignoring if it already exists.

    Uses dialect-specific conflict resolution (INSERT OR IGNORE for SQLite,
    ON CONFLICT DO NOTHING for PostgreSQL).

    Args:
        node_id: Unique node identifier
        scope: Node scope (typically "local" or "global")
        node_type: Type of node (e.g., "user", "channel", "concept")
        attributes: Node attributes as dictionary
        version: Node version (default: 1)
        updated_by: Who updated the node (default: "system")
        db_path: Optional database path (uses default if not provided)

    Returns:
        True if node was inserted, False if it already existed

    Examples:
        >>> inserted = insert_node_if_not_exists(
        ...     node_id="channel_cli_user",
        ...     scope="local",
        ...     node_type="channel",
        ...     attributes={"channel_type": "cli"},
        ...     updated_by="tsdb_consolidation"
        ... )
    """
    adapter = get_adapter()
    sql = adapter.insert_ignore_node_sql()

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            sql,
            (
                node_id,
                scope,
                node_type,
                json.dumps(attributes),
                version,
                updated_by,
                now,
                now,
            ),
        )

        # Check if node exists (rowcount not reliable for INSERT IGNORE/ON CONFLICT)
        cursor.execute("SELECT 1 FROM graph_nodes WHERE node_id = ? AND scope = ?", (node_id, scope))
        exists = cursor.fetchone() is not None

        conn.commit()
        return exists


def batch_insert_nodes_if_not_exist(
    nodes: List[Tuple[str, str, str, Dict[str, Any], int, str, str, str]], db_path: Optional[str] = None
) -> int:
    """Batch insert graph nodes, ignoring duplicates.

    Args:
        nodes: List of tuples (node_id, scope, node_type, attributes_dict, version, updated_by, updated_at, created_at)
        db_path: Optional database path

    Returns:
        Number of nodes in batch (not necessarily inserted due to IGNORE)

    Examples:
        >>> nodes = [
        ...     ("user_1", "local", "user", {"name": "Alice"}, 1, "system", now, now),
        ...     ("user_2", "local", "user", {"name": "Bob"}, 1, "system", now, now),
        ... ]
        >>> count = batch_insert_nodes_if_not_exist(nodes)
    """
    adapter = get_adapter()
    sql = adapter.insert_ignore_node_sql()

    # Convert dict attributes to JSON strings
    nodes_with_json = [
        (
            node_id,
            scope,
            node_type,
            json.dumps(attrs) if isinstance(attrs, dict) else attrs,
            version,
            updated_by,
            updated_at,
            created_at,
        )
        for node_id, scope, node_type, attrs, version, updated_by, updated_at, created_at in nodes
    ]

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany(sql, nodes_with_json)
        count = len(nodes)
        conn.commit()
        return count


def insert_edge_if_not_exists(
    edge_id: str,
    source_node_id: str,
    target_node_id: str,
    scope: str,
    relationship: str,
    weight: float = 1.0,
    attributes: Optional[Dict[str, Any]] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Insert a graph edge, ignoring if it already exists.

    Uses dialect-specific conflict resolution (INSERT OR IGNORE for SQLite,
    ON CONFLICT DO NOTHING for PostgreSQL).

    Args:
        edge_id: Unique edge identifier
        source_node_id: Source node ID
        target_node_id: Target node ID
        scope: Edge scope (typically "local" or "global")
        relationship: Edge relationship type (e.g., "SUMMARIZES", "TEMPORAL_NEXT")
        weight: Edge weight (default: 1.0)
        attributes: Optional edge attributes as dictionary
        db_path: Optional database path

    Returns:
        True if edge was inserted, False if it already existed

    Examples:
        >>> inserted = insert_edge_if_not_exists(
        ...     edge_id="edge_abc123",
        ...     source_node_id="summary_1",
        ...     target_node_id="concept_1",
        ...     scope="local",
        ...     relationship="CONTAINS",
        ...     weight=0.8,
        ...     attributes={"context": "Summary contains concept"}
        ... )
    """
    adapter = get_adapter()
    sql = adapter.insert_ignore_edge_sql()

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()

        cursor.execute(
            sql,
            (
                edge_id,
                source_node_id,
                target_node_id,
                scope,
                relationship,
                weight,
                json.dumps(attributes or {}),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        # Check if edge exists
        cursor.execute("SELECT 1 FROM graph_edges WHERE edge_id = ?", (edge_id,))
        exists = cursor.fetchone() is not None

        conn.commit()
        return exists


def batch_insert_edges_if_not_exist(
    edges: List[Tuple[str, str, str, str, str, float, str, str]], db_path: Optional[str] = None
) -> int:
    """Batch insert edges, ignoring duplicates.

    Args:
        edges: List of tuples (edge_id, source_id, target_id, scope, relationship, weight, attributes_json, created_at)
        db_path: Optional database path

    Returns:
        Number of edges in batch (not necessarily inserted due to IGNORE)

    Examples:
        >>> edges = [
        ...     ("edge_1", "node_a", "node_b", "local", "LINKS_TO", 1.0, "{}", now),
        ...     ("edge_2", "node_b", "node_c", "local", "LINKS_TO", 1.0, "{}", now),
        ... ]
        >>> count = batch_insert_edges_if_not_exist(edges)
    """
    adapter = get_adapter()
    sql = adapter.insert_ignore_edge_sql()

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany(sql, edges)
        count = len(edges)
        conn.commit()
        logger.debug(f"Batch inserted {count} edges (some may have been duplicates)")
        return count


def upsert_node(
    node_id: str,
    scope: str,
    node_type: str,
    attributes: Dict[str, Any],
    version: int = 1,
    updated_by: str = "system",
    db_path: Optional[str] = None,
) -> bool:
    """Insert or update a graph node (UPSERT).

    Uses dialect-specific conflict resolution (INSERT OR REPLACE for SQLite,
    ON CONFLICT DO UPDATE for PostgreSQL).

    Args:
        node_id: Unique node identifier
        scope: Node scope (typically "local" or "global")
        node_type: Type of node (e.g., "user", "channel", "concept")
        attributes: Node attributes as dictionary
        version: Node version (default: 1)
        updated_by: Who updated the node (default: "system")
        db_path: Optional database path (uses default if not provided)

    Returns:
        True if node was inserted/updated

    Examples:
        >>> upserted = upsert_node(
        ...     node_id="user_123",
        ...     scope="local",
        ...     node_type="user",
        ...     attributes={"name": "Alice", "email": "alice@example.com"},
        ... )
    """
    adapter = get_adapter()
    builder = adapter.get_query_builder()

    # Build UPSERT query
    query = builder.insert(
        table="graph_nodes",
        columns=[
            "node_id",
            "scope",
            "node_type",
            "attributes_json",
            "version",
            "updated_by",
            "updated_at",
            "created_at",
        ],
        conflict_resolution=ConflictResolution.REPLACE,
        conflict_columns=["node_id", "scope"],
    )
    sql = query.to_sql(adapter)

    with get_db_connection(db_path=db_path) as conn:
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute(
            sql,
            (
                node_id,
                scope,
                node_type,
                json.dumps(attributes),
                version,
                updated_by,
                now,
                now,
            ),
        )

        conn.commit()
        return True
