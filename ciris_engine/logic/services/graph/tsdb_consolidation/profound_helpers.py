"""
Profound consolidation helper functions.

Functions for in-place compression of daily summaries to meet storage targets.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from sqlite3 import Connection, Cursor
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_int, get_str
from ciris_engine.schemas.services.graph.tsdb_models import SummaryAttributes
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def parse_summary_attributes_with_fallback(attrs_dict: JSONDict) -> SummaryAttributes:
    """
    Parse summary attributes dict into SummaryAttributes model with fallback.

    If parsing fails, creates a minimal SummaryAttributes object to maintain compatibility.

    Args:
        attrs_dict: Raw attributes dictionary from JSON

    Returns:
        Parsed or minimal SummaryAttributes object

    Examples:
        >>> attrs = parse_summary_attributes_with_fallback({"period_start": "2023-10-01T00:00:00Z", ...})
        >>> isinstance(attrs, SummaryAttributes)
        True
    """
    try:
        return SummaryAttributes(**attrs_dict)
    except Exception as e:
        logger.warning(f"Failed to convert summary attributes to SummaryAttributes model: {e}")
        # Create minimal SummaryAttributes for compatibility
        # Use try/except for date parsing in case the values are invalid
        try:
            period_start_str = get_str(attrs_dict, "period_start", "2025-01-01T00:00:00Z")
            period_start = datetime.fromisoformat(period_start_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            period_start = datetime(2025, 1, 1, tzinfo=timezone.utc)

        try:
            period_end_str = get_str(attrs_dict, "period_end", "2025-01-02T00:00:00Z")
            period_end = datetime.fromisoformat(period_end_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            period_end = datetime(2025, 1, 2, tzinfo=timezone.utc)

        consolidation_level = get_str(attrs_dict, "consolidation_level", "basic")
        return SummaryAttributes(
            period_start=period_start,
            period_end=period_end,
            consolidation_level=consolidation_level,
        )


def calculate_storage_metrics(
    cursor: Cursor,
    month_start: datetime,
    month_end: datetime,
    compressor: Any,  # SummaryCompressor type
) -> Tuple[float, List[SummaryAttributes]]:
    """
    Calculate current storage metrics for extensive summaries in a period.

    Args:
        cursor: Database cursor
        month_start: Start of month period
        month_end: End of month period
        compressor: SummaryCompressor instance

    Returns:
        Tuple of (daily_mb, summary_attrs_list)

    Examples:
        >>> daily_mb, attrs_list = calculate_storage_metrics(cursor, start, end, compressor)
        >>> daily_mb > 0
        True
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # Query extensive summaries in period (PostgreSQL: JSONB operators, SQLite: json_extract)
    if adapter.is_postgresql():
        sql = """
            SELECT attributes_json
            FROM graph_nodes
            WHERE attributes_json->>'consolidation_level' = 'extensive'
              AND (attributes_json->>'period_start')::timestamp >= ?::timestamp
              AND (attributes_json->>'period_start')::timestamp <= ?::timestamp
        """
    else:
        sql = """
            SELECT attributes_json
            FROM graph_nodes
            WHERE json_extract(attributes_json, '$.consolidation_level') = 'extensive'
              AND datetime(json_extract(attributes_json, '$.period_start')) >= datetime(?)
              AND datetime(json_extract(attributes_json, '$.period_start')) <= datetime(?)
        """

    cursor.execute(sql, (month_start.isoformat(), month_end.isoformat()))

    # Parse attributes
    summary_attrs_list = []
    for (attrs_json,) in cursor.fetchall():
        attrs_dict = json.loads(attrs_json) if attrs_json else {}
        attrs = parse_summary_attributes_with_fallback(attrs_dict)
        summary_attrs_list.append(attrs)

    # Calculate storage
    days_in_period = (month_end - month_start).days + 1
    daily_mb = compressor.estimate_daily_size(summary_attrs_list, days_in_period)

    return float(daily_mb), summary_attrs_list


def compress_and_update_summaries(
    cursor: Cursor,
    summaries: List[Tuple[str, str, str, int]],
    compressor: Any,  # SummaryCompressor type
    now: datetime,
) -> Tuple[int, float]:
    """
    Compress summaries in-place and update database.

    Args:
        cursor: Database cursor
        summaries: List of (node_id, node_type, attrs_json, version) tuples
        compressor: SummaryCompressor instance
        now: Current timestamp

    Returns:
        Tuple of (compressed_count, total_reduction)

    Examples:
        >>> count, reduction = compress_and_update_summaries(cursor, summaries, compressor, datetime.now())
        >>> count >= 0
        True
    """
    compressed_count = 0
    total_reduction = 0.0

    for node_id, node_type, attrs_json, version in summaries:
        attrs_dict = json.loads(attrs_json) if attrs_json else {}

        # Parse attributes with fallback
        attrs = parse_summary_attributes_with_fallback(attrs_dict)

        # Compress the attributes
        compression_result = compressor.compress_summary(attrs)
        compressed_attrs = compression_result.compressed_attributes
        reduction_ratio = compression_result.reduction_ratio

        # Convert back to dict and add compression metadata
        compressed_attrs_dict = compressed_attrs.model_dump(mode="json")
        compressed_attrs_dict["profound_compressed"] = True
        compressed_attrs_dict["compression_date"] = now.isoformat()
        compressed_attrs_dict["compression_ratio"] = reduction_ratio

        # Update the node in-place
        cursor.execute(
            """
            UPDATE graph_nodes
            SET attributes_json = ?,
                version = ?,
                updated_by = 'tsdb_profound_consolidation',
                updated_at = ?
            WHERE node_id = ?
        """,
            (json.dumps(compressed_attrs_dict), version + 1, now.isoformat(), node_id),
        )

        if cursor.rowcount > 0:
            compressed_count += 1
            total_reduction += reduction_ratio
            logger.debug(f"Compressed {node_id} by {reduction_ratio:.1%}")

    return compressed_count, total_reduction


def cleanup_old_basic_summaries(
    cursor: Cursor,
    cutoff_date: datetime,
) -> int:
    """
    Delete basic-level summaries older than cutoff date.

    Args:
        cursor: Database cursor
        cutoff_date: Delete summaries before this date

    Returns:
        Number of summaries deleted

    Examples:
        >>> deleted = cleanup_old_basic_summaries(cursor, datetime(2023, 10, 1))
        >>> deleted >= 0
        True
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # PostgreSQL: JSONB operators, SQLite: json_extract
    if adapter.is_postgresql():
        sql = """
            DELETE FROM graph_nodes
            WHERE attributes_json->>'consolidation_level' = 'basic'
              AND (attributes_json->>'period_start')::timestamp < ?::timestamp
        """
    else:
        sql = """
            DELETE FROM graph_nodes
            WHERE json_extract(attributes_json, '$.consolidation_level') = 'basic'
              AND datetime(json_extract(attributes_json, '$.period_start')) < datetime(?)
        """

    cursor.execute(sql, (cutoff_date.isoformat(),))

    return cursor.rowcount


def query_extensive_summaries_in_month(
    cursor: Cursor,
    month_start: datetime,
    month_end: datetime,
) -> List[Tuple[str, str, str, int]]:
    """
    Query all extensive (daily) summaries from a calendar month.

    Args:
        cursor: Database cursor
        month_start: Start of month
        month_end: End of month

    Returns:
        List of (node_id, node_type, attributes_json, version) tuples

    Examples:
        >>> summaries = query_extensive_summaries_in_month(cursor, start, end)
        >>> all(len(s) == 4 for s in summaries)
        True
    """
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()

    # PostgreSQL: JSONB operators, SQLite: json_extract
    if adapter.is_postgresql():
        sql = """
            SELECT node_id, node_type, attributes_json, version
            FROM graph_nodes
            WHERE attributes_json->>'consolidation_level' = 'extensive'
              AND (attributes_json->>'period_start')::timestamp >= ?::timestamp
              AND (attributes_json->>'period_start')::timestamp <= ?::timestamp
            ORDER BY node_type, attributes_json->>'period_start'
        """
    else:
        sql = """
            SELECT node_id, node_type, attributes_json, version
            FROM graph_nodes
            WHERE json_extract(attributes_json, '$.consolidation_level') = 'extensive'
              AND datetime(json_extract(attributes_json, '$.period_start')) >= datetime(?)
              AND datetime(json_extract(attributes_json, '$.period_start')) <= datetime(?)
            ORDER BY node_type, json_extract(attributes_json, '$.period_start')
        """

    cursor.execute(sql, (month_start.isoformat(), month_end.isoformat()))

    return cursor.fetchall()
