"""SQL query builders for TSDB consolidation to reduce cognitive complexity.

This module provides database-agnostic SQL query builders and row parsers
to eliminate PostgreSQL/SQLite branching logic from query_manager.py.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.persistence.models.graph import parse_json_field
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

logger = logging.getLogger(__name__)


def build_nodes_in_period_query(adapter: Any, period_start: str, period_end: str) -> Tuple[str, Tuple[str, str]]:
    """Build SQL query for fetching nodes created in a time period.

    Args:
        adapter: Database adapter for placeholder syntax
        period_start: ISO format start time
        period_end: ISO format end time

    Returns:
        Tuple of (sql_query, parameters)
    """
    if adapter.is_postgresql():
        sql = f"""
            SELECT node_id, node_type, scope, attributes_json,
                   version, updated_by, updated_at, created_at
            FROM graph_nodes
            WHERE scope = 'local'
              AND created_at >= {adapter.placeholder()}
              AND created_at < {adapter.placeholder()}
            ORDER BY node_type, created_at
        """
    else:
        sql = f"""
            SELECT node_id, node_type, scope, attributes_json,
                   version, updated_by, updated_at, created_at
            FROM graph_nodes
            WHERE scope = 'local'
              AND datetime(created_at) >= datetime({adapter.placeholder()})
              AND datetime(created_at) < datetime({adapter.placeholder()})
            ORDER BY node_type, created_at
        """

    params = (period_start, period_end)
    return sql, params


def build_tsdb_data_query(adapter: Any, period_start: str, period_end: str) -> Tuple[str, Tuple[str, str, str, str]]:
    """Build SQL query for fetching TSDB data nodes.

    Queries TSDB_DATA nodes updated or created in the period.

    Args:
        adapter: Database adapter for placeholder syntax
        period_start: ISO format start time
        period_end: ISO format end time

    Returns:
        Tuple of (sql_query, parameters)
    """
    if adapter.is_postgresql():
        sql = f"""
            SELECT node_id, scope, attributes_json, version,
                   updated_by, updated_at, created_at
            FROM graph_nodes
            WHERE node_type = 'tsdb_data'
              AND ((updated_at >= {adapter.placeholder()} AND updated_at < {adapter.placeholder()})
                   OR (updated_at IS NULL AND created_at >= {adapter.placeholder()} AND created_at < {adapter.placeholder()}))
            ORDER BY updated_at
        """
    else:
        sql = f"""
            SELECT node_id, scope, attributes_json, version,
                   updated_by, updated_at, created_at
            FROM graph_nodes
            WHERE node_type = 'tsdb_data'
              AND ((datetime(updated_at) >= datetime({adapter.placeholder()}) AND datetime(updated_at) < datetime({adapter.placeholder()}))
                   OR (updated_at IS NULL AND datetime(created_at) >= datetime({adapter.placeholder()}) AND datetime(created_at) < datetime({adapter.placeholder()})))
            ORDER BY updated_at
        """

    params = (period_start, period_end, period_start, period_end)
    return sql, params


def build_service_correlations_query(
    adapter: Any, period_start: str, period_end: str, correlation_types: Optional[List[str]] = None
) -> Tuple[str, List[Any]]:
    """Build SQL query for service correlations.

    Args:
        adapter: Database adapter for placeholder syntax
        period_start: ISO format start time
        period_end: ISO format end time
        correlation_types: Optional list of correlation types to filter

    Returns:
        Tuple of (sql_query, parameters_list)
    """
    if adapter.is_postgresql():
        query = f"""
            SELECT correlation_id, correlation_type, service_type, action_type,
                   trace_id, span_id, parent_span_id,
                   timestamp, request_data, response_data, tags
            FROM service_correlations
            WHERE timestamp >= {adapter.placeholder()} AND timestamp < {adapter.placeholder()}
        """
    else:
        query = f"""
            SELECT correlation_id, correlation_type, service_type, action_type,
                   trace_id, span_id, parent_span_id,
                   timestamp, request_data, response_data, tags
            FROM service_correlations
            WHERE datetime(timestamp) >= datetime({adapter.placeholder()}) AND datetime(timestamp) < datetime({adapter.placeholder()})
        """

    params = [period_start, period_end]

    if correlation_types:
        placeholders = ",".join([adapter.placeholder()] * len(correlation_types))
        query += f" AND correlation_type IN ({placeholders})"
        params.extend(correlation_types)

    query += " ORDER BY timestamp"

    return query, params


def build_tasks_in_period_query(adapter: Any, period_start: str, period_end: str) -> Tuple[str, Tuple[str, str]]:
    """Build SQL query for tasks in a time period.

    Args:
        adapter: Database adapter for placeholder syntax
        period_start: ISO format start time
        period_end: ISO format end time

    Returns:
        Tuple of (sql_query, parameters)
    """
    if adapter.is_postgresql():
        sql = f"""
            SELECT task_id, channel_id, description, status, priority,
                   created_at, updated_at, parent_task_id,
                   context_json, outcome_json, retry_count
            FROM tasks
            WHERE updated_at >= {adapter.placeholder()} AND updated_at < {adapter.placeholder()}
              AND status != 'deferred'
            ORDER BY updated_at
        """
    else:
        sql = f"""
            SELECT task_id, channel_id, description, status, priority,
                   created_at, updated_at, parent_task_id,
                   context_json, outcome_json, retry_count
            FROM tasks
            WHERE datetime(updated_at) >= datetime({adapter.placeholder()}) AND datetime(updated_at) < datetime({adapter.placeholder()})
              AND status != 'deferred'
            ORDER BY updated_at
        """

    params = (period_start, period_end)
    return sql, params


def build_oldest_unconsolidated_query(adapter: Any, scope: str = "local") -> Tuple[str, Tuple[str]]:
    """Build query to find oldest unconsolidated TSDB data.

    Args:
        adapter: Database adapter for placeholder syntax
        scope: Graph scope to query (default: "local")

    Returns:
        Tuple of (sql_query, parameters)
    """
    # Both PostgreSQL and SQLite use the same query since updated_at is handled consistently
    sql = f"""
        SELECT MIN(updated_at) as oldest
        FROM graph_nodes
        WHERE node_type = 'tsdb_data'
          AND scope = {adapter.placeholder()}
          AND updated_at IS NOT NULL
    """

    params = (scope,)
    return sql, params


def parse_datetime_field(value: Any) -> Optional[datetime]:
    """Parse datetime field from database.

    Handles both PostgreSQL datetime objects and SQLite TEXT strings.

    Args:
        value: Raw value from database (datetime object or ISO string)

    Returns:
        datetime object with UTC timezone, or None if value is None
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        # PostgreSQL returns datetime object - ensure it has timezone
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    else:
        # SQLite returns string - parse it
        return datetime.fromisoformat(value.replace("Z", UTC_TIMEZONE_SUFFIX))


def parse_json_string_field(value: Any, field_name: str = "field") -> Dict[str, Any]:
    """Parse JSON field that might be a string or already parsed.

    Args:
        value: Raw value from database (could be str, dict, or None)
        field_name: Field name for logging (optional)

    Returns:
        Parsed dictionary (empty dict if parsing fails or None)
    """
    if value is None:
        return {}

    if isinstance(value, dict):
        # Already parsed (PostgreSQL JSONB)
        return value

    if isinstance(value, str):
        if not value.strip():
            return {}
        try:
            result = json.loads(value)
            if isinstance(result, dict):
                return result
            return {}
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to parse {field_name}: {e}")
            return {}

    return {}


def parse_graph_node_row(row: Any, node_type: Optional[NodeType] = None) -> GraphNode:
    """Parse database row into GraphNode object.

    Args:
        row: Database row (dict-like object from SQLite or PostgreSQL)
        node_type: Node type override (if not in row)

    Returns:
        GraphNode instance
    """
    # Convert to dict to handle both sqlite3.Row and PostgreSQL dict-like objects
    if hasattr(row, "keys"):
        row_dict = dict(row)
    else:
        row_dict = row

    # Parse node type if not provided
    if node_type is None:
        node_type_str = row_dict.get("node_type", "agent")
        try:
            node_type = NodeType(node_type_str)
        except ValueError:
            # For unknown types, use AGENT as fallback
            node_type = NodeType.AGENT

    # Parse JSON attributes
    attributes = parse_json_field(row_dict.get("attributes_json", {}))

    # Parse datetime fields
    updated_at = parse_datetime_field(row_dict.get("updated_at"))

    # Parse scope
    scope_value = row_dict.get("scope", "local")
    scope = GraphScope(scope_value) if scope_value else GraphScope.LOCAL

    return GraphNode(
        id=row_dict["node_id"],
        type=node_type,
        scope=scope,
        attributes=attributes,
        version=row_dict.get("version", 1),
        updated_by=row_dict.get("updated_by", "system"),
        updated_at=updated_at,
    )


def parse_correlation_row(row: Any) -> Dict[str, Any]:
    """Parse service correlation row from database.

    Args:
        row: Database row (dict-like object from SQLite or PostgreSQL)

    Returns:
        Dictionary with parsed fields ready for TSDBDataConverter
    """
    # Convert to dict to handle both sqlite3.Row and PostgreSQL dict-like objects
    if hasattr(row, "keys"):
        row_dict = dict(row)
    else:
        row_dict = row

    # Parse timestamp
    ts = parse_datetime_field(row_dict.get("timestamp"))

    # Parse JSON fields
    request_data = parse_json_string_field(row_dict.get("request_data"), "request_data")
    response_data = parse_json_string_field(row_dict.get("response_data"), "response_data")
    tags = parse_json_string_field(row_dict.get("tags"), "tags")

    return {
        "correlation_id": row_dict["correlation_id"],
        "correlation_type": row_dict["correlation_type"],
        "service_type": row_dict.get("service_type"),
        "action_type": row_dict.get("action_type"),
        "trace_id": row_dict.get("trace_id"),
        "span_id": row_dict.get("span_id"),
        "parent_span_id": row_dict.get("parent_span_id"),
        "timestamp": ts,
        "request_data": request_data,
        "response_data": response_data,
        "tags": tags,
    }


def parse_task_row(row: Dict[str, Any]) -> Dict[str, Any]:
    """Parse task row from database.

    Args:
        row: Database row dictionary

    Returns:
        Dictionary with parsed fields ready for TaskCorrelationData
    """
    # Handle datetime fields (PostgreSQL returns datetime, SQLite returns string)
    created_at = row["created_at"]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()

    updated_at = row["updated_at"]
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()

    return {
        "task_id": row["task_id"],
        "channel_id": row["channel_id"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "created_at": created_at,
        "updated_at": updated_at,
        "parent_task_id": row.get("parent_task_id"),
        "context": row.get("context_json"),
        "outcome": row.get("outcome_json"),
        "retry_count": row.get("retry_count", 0),
    }
