"""
Database query helper functions for TSDB consolidation.

Centralizes common SQL query patterns for querying summaries and nodes.
"""

import logging
from datetime import datetime
from sqlite3 import Cursor
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Validation error messages
ERR_TIMEZONE_AWARE = "period_start and period_end must be timezone-aware"
ERR_PERIOD_ORDER = "period_start must be before period_end"


def query_summaries_in_period(
    cursor: Cursor,
    summary_type: str,
    period_start: datetime,
    period_end: datetime,
    consolidation_level: str = "basic",
) -> List[Tuple[str, str, str]]:
    """
    Query summaries of a specific type within a time period.

    Args:
        cursor: Database cursor
        summary_type: Node type to query (e.g., "tsdb_summary", "audit_summary")
        period_start: Start of period (inclusive)
        period_end: End of period (inclusive)
        consolidation_level: Level to query ('basic', 'daily', 'weekly', 'monthly')
                           Use 'basic' to get unconsolidated summaries.

    Returns:
        List of tuples: (node_id, attributes_json, period_start_str)

    Examples:
        >>> # Query basic tsdb summaries from last week
        >>> summaries = query_summaries_in_period(
        ...     cursor, "tsdb_summary", week_start, week_end, "basic"
        ... )
        >>> len(summaries)  # Returns count of summaries found
    """
    if not summary_type:
        raise ValueError("summary_type cannot be empty")

    if period_start.tzinfo is None or period_end.tzinfo is None:
        raise ValueError(ERR_TIMEZONE_AWARE)

    if period_start >= period_end:
        raise ValueError(ERR_PERIOD_ORDER)

    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # Query summaries with specified consolidation level
    # PostgreSQL: Use JSONB operators and direct TIMESTAMP comparison
    # SQLite: Use json_extract() and datetime() function
    if adapter.is_postgresql():
        sql = """
            SELECT node_id, attributes_json,
                   attributes_json->>'period_start' as period_start
            FROM graph_nodes
            WHERE node_type = ?
              AND created_at >= ?
              AND created_at <= ?
              AND (attributes_json->>'consolidation_level' IS NULL
                   OR attributes_json->>'consolidation_level' = ?)
            ORDER BY attributes_json->>'period_start'
        """
    else:
        sql = """
            SELECT node_id, attributes_json,
                   json_extract(attributes_json, '$.period_start') as period_start
            FROM graph_nodes
            WHERE node_type = ?
              AND datetime(created_at) >= datetime(?)
              AND datetime(created_at) <= datetime(?)
              AND (json_extract(attributes_json, '$.consolidation_level') IS NULL
                   OR json_extract(attributes_json, '$.consolidation_level') = ?)
            ORDER BY period_start
        """

    cursor.execute(
        sql,
        (summary_type, period_start.isoformat(), period_end.isoformat(), consolidation_level),
    )

    return cursor.fetchall()


def query_all_summary_types_in_period(
    cursor: Cursor, period_start: datetime, period_end: datetime, consolidation_level: str = "basic"
) -> Dict[str, List[Tuple[str, str, str]]]:
    """
    Query all summary types within a time period.

    Args:
        cursor: Database cursor
        period_start: Start of period (inclusive)
        period_end: End of period (inclusive)
        consolidation_level: Level to query (default: 'basic')

    Returns:
        Dictionary mapping summary_type to list of (node_id, attributes_json, period_start_str)

    Examples:
        >>> # Query all summary types from last week
        >>> all_summaries = query_all_summary_types_in_period(
        ...     cursor, week_start, week_end, "basic"
        ... )
        >>> all_summaries.keys()  # ['tsdb_summary', 'audit_summary', ...]
    """
    if period_start.tzinfo is None or period_end.tzinfo is None:
        raise ValueError(ERR_TIMEZONE_AWARE)

    if period_start >= period_end:
        raise ValueError(ERR_PERIOD_ORDER)

    summary_types = [
        "tsdb_summary",
        "audit_summary",
        "trace_summary",
        "conversation_summary",
        "task_summary",
    ]

    result: Dict[str, List[Tuple[str, str, str]]] = {}

    for summary_type in summary_types:
        summaries = query_summaries_in_period(cursor, summary_type, period_start, period_end, consolidation_level)
        if summaries:
            result[summary_type] = summaries
            logger.debug(f"Found {len(summaries)} {summary_type} summaries in period")

    return result


def query_expired_summaries(cursor: Cursor, cutoff_date: datetime) -> List[Tuple[str, str, str]]:
    """
    Query summaries with period_end older than cutoff date.

    These are candidates for deletion based on retention policy.

    Args:
        cursor: Database cursor
        cutoff_date: Delete summaries with period_end before this date

    Returns:
        List of tuples: (node_id, node_type, attributes_json)

    Examples:
        >>> # Query summaries older than 30 days
        >>> cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        >>> expired = query_expired_summaries(cursor, cutoff)
        >>> len(expired)  # Returns count of expired summaries
    """
    if cutoff_date.tzinfo is None:
        raise ValueError("cutoff_date must be timezone-aware")

    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # PostgreSQL: Use JSONB operator, SQLite: Use json_extract()
    # Compare as text (ISO format strings) to avoid casting issues
    # PostgreSQL: Escape % in LIKE pattern by doubling it (%%_summary)
    if adapter.is_postgresql():
        sql = """
            SELECT node_id, node_type, attributes_json
            FROM graph_nodes
            WHERE node_type LIKE '%%_summary'
              AND attributes_json->>'period_end' < ?
            ORDER BY attributes_json->>'period_end'
        """
    else:
        sql = """
            SELECT node_id, node_type, attributes_json
            FROM graph_nodes
            WHERE node_type LIKE '%_summary'
              AND json_extract(attributes_json, '$.period_end') < ?
            ORDER BY json_extract(attributes_json, '$.period_end')
        """

    cursor.execute(sql, (cutoff_date.isoformat(),))

    return cursor.fetchall()


def update_summary_consolidation_level(cursor: Cursor, node_id: str, new_level: str) -> None:
    """
    Update the consolidation_level field in a summary node's attributes.

    Used to mark summaries as 'consolidated' after processing.

    Args:
        cursor: Database cursor
        node_id: ID of the node to update
        new_level: New consolidation level ('daily', 'weekly', 'monthly', 'consolidated')

    Examples:
        >>> # Mark a summary as consolidated
        >>> update_summary_consolidation_level(cursor, node_id, 'consolidated')
    """
    if not node_id:
        raise ValueError("node_id cannot be empty")

    if not new_level:
        raise ValueError("new_level cannot be empty")

    # Get current attributes
    cursor.execute("SELECT attributes_json FROM graph_nodes WHERE node_id = ?", (node_id,))
    row = cursor.fetchone()

    if not row:
        raise ValueError(f"Node {node_id} not found")

    # Parse, update, and save
    import json

    # Handle PostgreSQL JSONB vs SQLite TEXT
    if isinstance(row[0], dict):
        attrs = row[0]  # PostgreSQL
    else:
        attrs = json.loads(row[0]) if row[0] else {}  # SQLite

    attrs["consolidation_level"] = new_level

    cursor.execute(
        "UPDATE graph_nodes SET attributes_json = ? WHERE node_id = ?",
        (json.dumps(attrs), node_id),
    )

    logger.debug(f"Updated {node_id} consolidation_level to '{new_level}'")


def count_nodes_in_period(cursor: Cursor, node_type: str, period_start: datetime, period_end: datetime) -> int:
    """
    Count nodes of a specific type within a time period.

    Args:
        cursor: Database cursor
        node_type: Type of nodes to count (e.g., 'tsdb_data', 'audit_entry')
        period_start: Start of period (inclusive)
        period_end: End of period (inclusive)

    Returns:
        Count of nodes

    Examples:
        >>> # Count raw telemetry nodes in the last hour
        >>> count = count_nodes_in_period(cursor, 'tsdb_data', hour_start, hour_end)
        >>> count
        42
    """
    if not node_type:
        raise ValueError("node_type cannot be empty")

    if period_start.tzinfo is None or period_end.tzinfo is None:
        raise ValueError(ERR_TIMEZONE_AWARE)

    if period_start >= period_end:
        raise ValueError(ERR_PERIOD_ORDER)

    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # PostgreSQL: Use direct TIMESTAMP comparison
    # SQLite: Use datetime() function
    if adapter.is_postgresql():
        sql = """
            SELECT COUNT(*) FROM graph_nodes
            WHERE node_type = ?
              AND created_at >= ?
              AND created_at <= ?
        """
    else:
        sql = """
            SELECT COUNT(*) FROM graph_nodes
            WHERE node_type = ?
              AND datetime(created_at) >= datetime(?)
              AND datetime(created_at) <= datetime(?)
        """

    cursor.execute(
        sql,
        (node_type, period_start.isoformat(), period_end.isoformat()),
    )

    result = cursor.fetchone()
    return result[0] if result else 0
