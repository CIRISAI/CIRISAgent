"""
Extensive consolidation helper functions.

Functions for creating daily summaries from 6-hour basic summaries.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from sqlite3 import Cursor
from typing import Any, Dict, List, Optional, Tuple, cast
from uuid import uuid4

from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def query_basic_summaries_in_period(
    cursor: Cursor,
    summary_type: str,
    period_start: datetime,
    period_end: datetime,
) -> List[Tuple[str, str, str]]:
    """
    Query basic-level summaries of specific type within time period.

    Args:
        cursor: Database cursor
        summary_type: Type of summaries to query (e.g., 'tsdb_summary')
        period_start: Start of period
        period_end: End of period

    Returns:
        List of (node_id, attributes_json, period_start_str) tuples

    Examples:
        >>> summaries = query_basic_summaries_in_period(cursor, 'tsdb_summary', start, end)
        >>> all(len(s) == 3 for s in summaries)
        True
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # PostgreSQL: Use JSONB operators, SQLite: Use json_extract()
    if adapter.is_postgresql():
        sql = """
            SELECT node_id, attributes_json,
                   attributes_json->>'period_start' as period_start
            FROM graph_nodes
            WHERE node_type = ?
              AND created_at >= ?
              AND created_at <= ?
              AND (attributes_json->>'consolidation_level' IS NULL
                   OR attributes_json->>'consolidation_level' = 'basic')
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
                   OR json_extract(attributes_json, '$.consolidation_level') = 'basic')
            ORDER BY period_start
        """

    # Translate placeholders for PostgreSQL
    sql = adapter.translate_placeholders(sql)

    cursor.execute(
        sql,
        (summary_type, period_start.isoformat(), period_end.isoformat()),
    )

    return cursor.fetchall()


def check_daily_summary_exists(cursor: Cursor, daily_node_id: str) -> bool:
    """
    Check if a daily summary node already exists.

    Args:
        cursor: Database cursor
        daily_node_id: ID of the daily summary to check

    Returns:
        True if exists, False otherwise

    Examples:
        >>> exists = check_daily_summary_exists(cursor, 'tsdb_summary_daily_20231001')
        >>> isinstance(exists, bool)
        True
    """
    cursor.execute(
        """
        SELECT node_id FROM graph_nodes
        WHERE node_id = ?
    """,
        (daily_node_id,),
    )

    return cursor.fetchone() is not None


def create_daily_summary_attributes(
    summary_type: str,
    day: datetime,
    day_summaries: List[Tuple[str, str]],
    metrics: Dict[str, Dict[str, float]],
    resources: Dict[str, float],
    action_counts: Dict[str, int],
) -> JSONDict:
    """
    Create attributes dictionary for a daily summary node.

    Args:
        summary_type: Type of summary (e.g., 'tsdb_summary')
        day: Date for this daily summary
        day_summaries: List of (node_id, attrs_json) tuples for source summaries
        metrics: Aggregated metrics
        resources: Aggregated resource usage
        action_counts: Aggregated action counts

    Returns:
        Dictionary of attributes for the daily summary

    Examples:
        >>> attrs = create_daily_summary_attributes('tsdb_summary', date(2023, 10, 1), [], {}, {}, {})
        >>> attrs['consolidation_level']
        'extensive'
    """
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    day_end = datetime.combine(day, datetime.max.time(), tzinfo=timezone.utc)

    source_summary_ids = [node_id for node_id, _ in day_summaries]

    daily_attrs = {
        "summary_type": summary_type,
        "consolidation_level": "extensive",
        "period_start": day_start.isoformat(),
        "period_end": day_end.isoformat(),
        "period_label": day.strftime("%Y-%m-%d"),
        "source_summary_count": len(day_summaries),
        "source_summary_ids": source_summary_ids[:10],  # Keep first 10 for reference
    }

    # Add type-specific attributes
    if summary_type == "tsdb_summary":
        daily_attrs.update(
            {
                "metrics": metrics,
                "total_tokens": resources.get("total_tokens", 0),
                "total_cost_cents": resources.get("total_cost_cents", 0.0),
                "total_carbon_grams": resources.get("total_carbon_grams", 0.0),
                "total_energy_kwh": resources.get("total_energy_kwh", 0.0),
                "action_counts": action_counts,
                "error_count": resources.get("error_count", 0),
                "success_rate": (
                    1.0 - (resources.get("error_count", 0) / sum(action_counts.values()))
                    if sum(action_counts.values()) > 0
                    else 1.0
                ),
            }
        )

    return cast(JSONDict, daily_attrs)


def create_daily_summary_node(
    summary_type: str,
    day: datetime,
    attributes: JSONDict,
    now: datetime,
) -> GraphNode:
    """
    Create a GraphNode for a daily summary.

    Args:
        summary_type: Type of summary (e.g., 'tsdb_summary')
        day: Date for this daily summary
        attributes: Pre-built attributes dictionary
        now: Current timestamp

    Returns:
        GraphNode for the daily summary

    Examples:
        >>> node = create_daily_summary_node('tsdb_summary', date(2023, 10, 1), {}, datetime.now())
        >>> node.type
        <NodeType.TSDB_SUMMARY: 'tsdb_summary'>
    """
    daily_node_id = f"{summary_type}_daily_{day.strftime('%Y%m%d')}"

    node_type_map = {
        "tsdb_summary": NodeType.TSDB_SUMMARY,
        "audit_summary": NodeType.AUDIT_SUMMARY,
        "trace_summary": NodeType.TRACE_SUMMARY,
        "conversation_summary": NodeType.CONVERSATION_SUMMARY,
        "task_summary": NodeType.TASK_SUMMARY,
    }

    return GraphNode(
        id=daily_node_id,
        type=node_type_map.get(summary_type, NodeType.TSDB_SUMMARY),
        scope=GraphScope.LOCAL,
        attributes=attributes,
        updated_at=now,
        updated_by="tsdb_consolidation_extensive",
    )


def maintain_temporal_chain_to_daily(
    cursor: Cursor,
    period_start: datetime,
) -> int:
    """
    Maintain temporal chain between 6-hour and daily summaries.

    Finds the last 6-hour summary before daily summaries start and creates
    bidirectional temporal edges to the first daily summary.

    Args:
        cursor: Database cursor
        period_start: Start of the daily summary period

    Returns:
        Number of edges created (0 or 2)

    Examples:
        >>> edges_created = maintain_temporal_chain_to_daily(cursor, datetime(2023, 10, 1))
        >>> edges_created in [0, 2]
        True
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # Find last 6-hour summary before the daily summaries start
    last_6h_before = period_start - timedelta(hours=6)
    last_6h_id = f"tsdb_summary_{last_6h_before.strftime('%Y%m%d_%H')}"

    # Check if it exists (PostgreSQL: JSONB operators, SQLite: json_extract)
    if adapter.is_postgresql():
        sql = """
            SELECT node_id FROM graph_nodes
            WHERE node_id = ? AND node_type = 'tsdb_summary'
            AND attributes_json->>'consolidation_level' = 'basic'
        """
    else:
        sql = """
            SELECT node_id FROM graph_nodes
            WHERE node_id = ? AND node_type = 'tsdb_summary'
            AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
        """

    cursor.execute(sql, (last_6h_id,))

    if not cursor.fetchone():
        return 0

    # Update its TEMPORAL_NEXT to point to first daily summary
    first_daily_id = f"tsdb_summary_daily_{period_start.strftime('%Y%m%d')}"

    # Delete self-referencing edge (if any)
    cursor.execute(
        """
        DELETE FROM graph_edges
        WHERE source_node_id = ? AND target_node_id = ?
        AND relationship = 'TEMPORAL_NEXT'
    """,
        (last_6h_id, last_6h_id),
    )

    # Create new edge to daily summary
    cursor.execute(
        """
        INSERT INTO graph_edges
        (edge_id, source_node_id, target_node_id, scope,
         relationship, weight, attributes_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            f"edge_{uuid4().hex[:8]}",
            last_6h_id,
            first_daily_id,
            "local",
            "TEMPORAL_NEXT",
            1.0,
            json.dumps({"context": "6-hour to daily transition"}),
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    # Also create backward edge from daily to 6-hour
    cursor.execute(
        """
        INSERT INTO graph_edges
        (edge_id, source_node_id, target_node_id, scope,
         relationship, weight, attributes_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            f"edge_{uuid4().hex[:8]}",
            first_daily_id,
            last_6h_id,
            "local",
            "TEMPORAL_PREV",
            1.0,
            json.dumps({"context": "Daily to 6-hour backward link"}),
            datetime.now(timezone.utc).isoformat(),
        ),
    )

    logger.info(f"Linked 6-hour summary {last_6h_id} to daily summary {first_daily_id}")

    return 2  # Created 2 edges
