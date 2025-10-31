"""
Cleanup helper functions for TSDB consolidation.

Functions to validate and delete expired nodes safely.
"""

import json
import logging
from datetime import datetime
from sqlite3 import Cursor
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def validate_and_count_nodes(
    cursor: Cursor,
    node_type: str,
    period_start: str,
    period_end: str,
) -> int:
    """
    Count nodes of a specific type within a period.

    Database-agnostic: Works with both SQLite and PostgreSQL.

    Args:
        cursor: Database cursor
        node_type: Type of nodes to count (e.g., 'tsdb_data', 'audit_entry')
        period_start: ISO format period start
        period_end: ISO format period end

    Returns:
        Count of nodes in the period

    Examples:
        >>> count = validate_and_count_nodes(cursor, 'tsdb_data', '2023-10-01T00:00:00+00:00', '2023-10-02T00:00:00+00:00')
        >>> count
        42
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    if adapter.is_postgresql():
        cursor.execute(
            """
            SELECT COUNT(*) FROM graph_nodes
            WHERE node_type = %s
              AND created_at::timestamp >= %s::timestamp
              AND created_at::timestamp < %s::timestamp
        """,
            (node_type, period_start, period_end),
        )
    else:
        cursor.execute(
            """
            SELECT COUNT(*) FROM graph_nodes
            WHERE node_type = ?
              AND datetime(created_at) >= datetime(?)
              AND datetime(created_at) < datetime(?)
        """,
            (node_type, period_start, period_end),
        )

    result = cursor.fetchone()
    return result[0] if result else 0


def validate_and_count_correlations(
    cursor: Cursor,
    period_start: str,
    period_end: str,
) -> int:
    """
    Count service correlations within a period.

    Database-agnostic: Works with both SQLite and PostgreSQL.

    Args:
        cursor: Database cursor
        period_start: ISO format period start
        period_end: ISO format period end

    Returns:
        Count of correlations in the period

    Examples:
        >>> count = validate_and_count_correlations(cursor, '2023-10-01T00:00:00+00:00', '2023-10-02T00:00:00+00:00')
        >>> count
        15
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    if adapter.is_postgresql():
        cursor.execute(
            """
            SELECT COUNT(*) FROM service_correlations
            WHERE created_at::timestamp >= %s::timestamp
              AND created_at::timestamp < %s::timestamp
        """,
            (period_start, period_end),
        )
    else:
        cursor.execute(
            """
            SELECT COUNT(*) FROM service_correlations
            WHERE datetime(created_at) >= datetime(?)
              AND datetime(created_at) < datetime(?)
        """,
            (period_start, period_end),
        )

    result = cursor.fetchone()
    return result[0] if result else 0


def delete_nodes_in_period(
    cursor: Cursor,
    node_type: str,
    period_start: str,
    period_end: str,
) -> int:
    """
    Delete nodes of a specific type within a period.

    CRITICAL: Deletes edges referencing the nodes first to avoid FOREIGN KEY constraint violations.
    Database-agnostic: Works with both SQLite and PostgreSQL.

    Args:
        cursor: Database cursor
        node_type: Type of nodes to delete
        period_start: ISO format period start
        period_end: ISO format period end

    Returns:
        Number of nodes deleted

    Examples:
        >>> deleted = delete_nodes_in_period(cursor, 'tsdb_data', '2023-10-01T00:00:00+00:00', '2023-10-02T00:00:00+00:00')
        >>> logger.info(f"Deleted {deleted} nodes")
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # Step 1: Delete edges referencing these nodes to avoid FOREIGN KEY constraint violations
    # Use correct column names: source_node_id and target_node_id (not source_id/target_id)
    if adapter.is_postgresql():
        # PostgreSQL: Use CAST for datetime comparison
        cursor.execute(
            """
            DELETE FROM graph_edges
            WHERE source_node_id IN (
                SELECT node_id FROM graph_nodes
                WHERE node_type = %s
                  AND created_at::timestamp >= %s::timestamp
                  AND created_at::timestamp < %s::timestamp
            )
            OR target_node_id IN (
                SELECT node_id FROM graph_nodes
                WHERE node_type = %s
                  AND created_at::timestamp >= %s::timestamp
                  AND created_at::timestamp < %s::timestamp
            )
        """,
            (node_type, period_start, period_end, node_type, period_start, period_end),
        )
    else:
        # SQLite: Use datetime() function
        cursor.execute(
            """
            DELETE FROM graph_edges
            WHERE source_node_id IN (
                SELECT node_id FROM graph_nodes
                WHERE node_type = ?
                  AND datetime(created_at) >= datetime(?)
                  AND datetime(created_at) < datetime(?)
            )
            OR target_node_id IN (
                SELECT node_id FROM graph_nodes
                WHERE node_type = ?
                  AND datetime(created_at) >= datetime(?)
                  AND datetime(created_at) < datetime(?)
            )
        """,
            (node_type, period_start, period_end, node_type, period_start, period_end),
        )

    # Step 2: Delete the nodes
    if adapter.is_postgresql():
        cursor.execute(
            """
            DELETE FROM graph_nodes
            WHERE node_type = %s
              AND created_at::timestamp >= %s::timestamp
              AND created_at::timestamp < %s::timestamp
        """,
            (node_type, period_start, period_end),
        )
    else:
        cursor.execute(
            """
            DELETE FROM graph_nodes
            WHERE node_type = ?
              AND datetime(created_at) >= datetime(?)
              AND datetime(created_at) < datetime(?)
        """,
            (node_type, period_start, period_end),
        )

    return cursor.rowcount


def delete_correlations_in_period(
    cursor: Cursor,
    period_start: str,
    period_end: str,
) -> int:
    """
    Delete service correlations within a period.

    Database-agnostic: Works with both SQLite and PostgreSQL.

    Args:
        cursor: Database cursor
        period_start: ISO format period start
        period_end: ISO format period end

    Returns:
        Number of correlations deleted

    Examples:
        >>> deleted = delete_correlations_in_period(cursor, '2023-10-01T00:00:00+00:00', '2023-10-02T00:00:00+00:00')
        >>> logger.info(f"Deleted {deleted} correlations")
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    if adapter.is_postgresql():
        cursor.execute(
            """
            DELETE FROM service_correlations
            WHERE created_at::timestamp >= %s::timestamp
              AND created_at::timestamp < %s::timestamp
        """,
            (period_start, period_end),
        )
    else:
        cursor.execute(
            """
            DELETE FROM service_correlations
            WHERE datetime(created_at) >= datetime(?)
              AND datetime(created_at) < datetime(?)
        """,
            (period_start, period_end),
        )

    return cursor.rowcount


def parse_summary_period(attrs_json: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse period_start and period_end from summary attributes JSON.

    Args:
        attrs_json: JSON string of summary attributes

    Returns:
        Tuple of (period_start, period_end) as ISO strings, or (None, None) if missing

    Examples:
        >>> start, end = parse_summary_period('{"period_start": "2023-10-01T00:00:00+00:00", "period_end": "2023-10-02T00:00:00+00:00"}')
        >>> start
        '2023-10-01T00:00:00+00:00'
    """
    if not attrs_json:
        return None, None

    try:
        attrs = json.loads(attrs_json)
        period_start = attrs.get("period_start")
        period_end = attrs.get("period_end")
        return period_start, period_end
    except json.JSONDecodeError:
        logger.warning("Failed to parse summary attributes JSON")
        return None, None


def should_cleanup_summary(
    claimed_count: int,
    actual_count: int,
) -> bool:
    """
    Determine if a summary should be cleaned up based on count validation.

    Only cleanup if:
    1. Claimed count matches actual count (data integrity)
    2. Actual count > 0 (there's data to cleanup)

    Args:
        claimed_count: Count claimed in summary attributes
        actual_count: Actual count from database

    Returns:
        True if summary should be cleaned up, False otherwise

    Examples:
        >>> should_cleanup_summary(10, 10)
        True
        >>> should_cleanup_summary(10, 9)  # Mismatch
        False
        >>> should_cleanup_summary(10, 0)  # No data
        False
    """
    return claimed_count == actual_count and actual_count > 0


def cleanup_tsdb_summary(
    cursor: Cursor,
    node_id: str,
    attrs_json: str,
) -> int:
    """
    Cleanup nodes associated with a tsdb_summary.

    Validates claimed count matches actual count before deletion.

    Args:
        cursor: Database cursor
        node_id: Summary node ID (for logging)
        attrs_json: Summary attributes JSON

    Returns:
        Number of nodes deleted

    Examples:
        >>> deleted = cleanup_tsdb_summary(cursor, 'tsdb_summary_20231001', '{"source_node_count": 10, ...}')
    """
    period_start, period_end = parse_summary_period(attrs_json)
    if not period_start or not period_end:
        return 0

    attrs = json.loads(attrs_json) if attrs_json else {}
    claimed_count = attrs.get("source_node_count", 0)

    # Validate count
    actual_count = validate_and_count_nodes(cursor, "tsdb_data", period_start, period_end)

    if should_cleanup_summary(claimed_count, actual_count):
        deleted = delete_nodes_in_period(cursor, "tsdb_data", period_start, period_end)
        if deleted > 0:
            logger.info(f"Deleted {deleted} tsdb_data nodes for period {node_id}")
        return deleted

    return 0


def cleanup_audit_summary(
    cursor: Cursor,
    node_id: str,
    attrs_json: str,
) -> int:
    """
    Cleanup graph audit nodes associated with an audit_summary.

    IMPORTANT: This only deletes graph_nodes entries, NOT the audit_log table.
    The audit_log table is preserved forever for reputability.

    Args:
        cursor: Database cursor
        node_id: Summary node ID (for logging)
        attrs_json: Summary attributes JSON

    Returns:
        Number of nodes deleted

    Examples:
        >>> deleted = cleanup_audit_summary(cursor, 'audit_summary_20231001', '{"source_node_count": 5, ...}')
    """
    period_start, period_end = parse_summary_period(attrs_json)
    if not period_start or not period_end:
        return 0

    attrs = json.loads(attrs_json) if attrs_json else {}
    claimed_count = attrs.get("source_node_count", 0)

    # Validate count
    actual_count = validate_and_count_nodes(cursor, "audit_entry", period_start, period_end)

    if should_cleanup_summary(claimed_count, actual_count):
        deleted = delete_nodes_in_period(cursor, "audit_entry", period_start, period_end)
        if deleted > 0:
            logger.info(f"Deleted {deleted} audit_entry graph nodes for period {node_id} (audit_log table preserved)")
        return deleted

    return 0


def cleanup_trace_summary(
    cursor: Cursor,
    node_id: str,
    attrs_json: str,
) -> int:
    """
    Cleanup service correlations associated with a trace_summary.

    Args:
        cursor: Database cursor
        node_id: Summary node ID (for logging)
        attrs_json: Summary attributes JSON

    Returns:
        Number of correlations deleted

    Examples:
        >>> deleted = cleanup_trace_summary(cursor, 'trace_summary_20231001', '{"source_correlation_count": 15, ...}')
    """
    period_start, period_end = parse_summary_period(attrs_json)
    if not period_start or not period_end:
        return 0

    attrs = json.loads(attrs_json) if attrs_json else {}
    claimed_count = attrs.get("source_correlation_count", 0)

    # Validate count
    actual_count = validate_and_count_correlations(cursor, period_start, period_end)

    if should_cleanup_summary(claimed_count, actual_count):
        deleted = delete_correlations_in_period(cursor, period_start, period_end)
        if deleted > 0:
            logger.info(f"Deleted {deleted} correlations for period {node_id}")
        return deleted

    return 0
