"""
Memory query helpers - modular functions for database queries.

Following CIRIS principles:
- Single Responsibility: Each class handles one aspect
- Type Safety: All inputs and outputs are typed
- No Exceptions: No special cases or bypass patterns
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class QueryBuilder:
    """Builds SQL queries following single responsibility principle."""

    # SQL constants
    SQL_SELECT_NODES = "SELECT node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at"
    SQL_FROM_NODES = "FROM graph_nodes"
    SQL_WHERE_TIME_RANGE = "WHERE updated_at >= ? AND updated_at < ?"
    SQL_EXCLUDE_METRICS = "AND NOT (node_type = 'tsdb_data' AND node_id LIKE 'metric_%')"
    SQL_WHERE_SCOPE = "AND scope = ?"
    SQL_WHERE_NODE_TYPE = "AND node_type = ?"
    SQL_WHERE_ATTR_LIKE = "attributes_json LIKE ?"
    SQL_ORDER_BY = "ORDER BY updated_at DESC"
    SQL_LIMIT = "LIMIT ?"

    @staticmethod
    def build_timeline_query(
        start_time: datetime,
        end_time: datetime,
        scope: Optional[str] = None,
        node_type: Optional[str] = None,
        exclude_metrics: bool = True,
        limit: int = 100,
        user_filter_ids: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """
        Build a timeline query with filters.

        Args:
            start_time: Start of time range
            end_time: End of time range
            scope: Optional scope filter
            node_type: Optional node type filter
            exclude_metrics: Whether to exclude metric nodes
            limit: Maximum results
            user_filter_ids: Optional list of user IDs for OBSERVER filtering (SQL Layer 1)
        """
        query_parts = [QueryBuilder.SQL_SELECT_NODES, QueryBuilder.SQL_FROM_NODES, QueryBuilder.SQL_WHERE_TIME_RANGE]
        params: List[Any] = [start_time.isoformat(), end_time.isoformat()]

        if exclude_metrics:
            query_parts.append(QueryBuilder.SQL_EXCLUDE_METRICS)

        if scope:
            query_parts.append(QueryBuilder.SQL_WHERE_SCOPE)
            params.append(scope.value if hasattr(scope, "value") else str(scope))

        if node_type:
            query_parts.append(QueryBuilder.SQL_WHERE_NODE_TYPE)
            params.append(node_type.value if hasattr(node_type, "value") else str(node_type))

        # SECURITY LAYER 1: SQL-level user filtering
        if user_filter_ids:
            QueryBuilder._add_user_filter(query_parts, params, user_filter_ids)

        query_parts.append(QueryBuilder.SQL_ORDER_BY)
        query_parts.append(QueryBuilder.SQL_LIMIT)
        params.append(limit)

        return " ".join(query_parts), params

    @staticmethod
    def build_search_query(
        query: Optional[str] = None,
        node_type: Optional[NodeType] = None,
        scope: Optional[GraphScope] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        tags: Optional[List[str]] = None,
        limit: int = 20,
        offset: int = 0,
        user_filter_ids: Optional[List[str]] = None,
    ) -> Tuple[str, List[Any]]:
        """
        Build a search query with multiple filters.

        Args:
            query: Text search query
            node_type: Filter by node type
            scope: Filter by scope
            since: Filter by minimum timestamp
            until: Filter by maximum timestamp
            tags: Filter by tags
            limit: Maximum results
            offset: Pagination offset
            user_filter_ids: Optional list of user IDs for OBSERVER filtering (SQL Layer 1)
        """
        query_parts = [QueryBuilder.SQL_SELECT_NODES, QueryBuilder.SQL_FROM_NODES, "WHERE 1=1"]
        params: List[Any] = []

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
            query_parts.append(f"AND {QueryBuilder.SQL_WHERE_ATTR_LIKE}")
            params.append(f"%{query}%")

        if tags:
            for tag in tags:
                query_parts.append(f"AND {QueryBuilder.SQL_WHERE_ATTR_LIKE}")
                params.append(f'%"{tag}"%')

        # SECURITY LAYER 1: SQL-level user filtering
        if user_filter_ids:
            QueryBuilder._add_user_filter(query_parts, params, user_filter_ids)

        query_parts.append(QueryBuilder.SQL_ORDER_BY)
        query_parts.append("LIMIT ? OFFSET ?")
        params.extend([limit, offset])

        return " ".join(query_parts), params

    @staticmethod
    def _add_user_filter(query_parts: List[str], params: List[Any], user_filter_ids: List[str]) -> None:
        """
        Add SQL-level user filtering to query (SECURITY LAYER 1).

        Filters nodes by checking if ANY of the user_filter_ids appear in:
        - json_extract(attributes_json, '$.created_by')
        - json_extract(attributes_json, '$.user_list') (as JSON array)
        - attributes_json LIKE patterns for task_summaries and conversations

        This is a comprehensive OR-based filter that matches the Layer 2 logic.
        """
        if not user_filter_ids:
            return

        # Build OR conditions for user attribution
        or_conditions = []

        # 1. Direct creator: json_extract(attributes_json, '$.created_by') IN (...)
        placeholders_created_by = ",".join("?" * len(user_filter_ids))
        or_conditions.append(f"json_extract(attributes_json, '$.created_by') IN ({placeholders_created_by})")
        params.extend(user_filter_ids)

        # 2. User list participants: Check if user_id appears in user_list JSON array
        # For each user_id, check if attributes_json contains it in user_list
        for user_id in user_filter_ids:
            # SQLite: Check if user_id is in the user_list array
            # Using LIKE is safe here as we're checking JSON array membership
            or_conditions.append(QueryBuilder.SQL_WHERE_ATTR_LIKE)
            params.append(f'%"user_list"%{user_id}%')

        # 3. Task summaries: Check if user_id appears in task_summaries
        for user_id in user_filter_ids:
            or_conditions.append(QueryBuilder.SQL_WHERE_ATTR_LIKE)
            params.append(f'%"task_summaries"%"user_id"%{user_id}%')

        # 4. Conversations: Check if user_id appears as author_id in conversations
        for user_id in user_filter_ids:
            or_conditions.append(QueryBuilder.SQL_WHERE_ATTR_LIKE)
            params.append(f'%"author_id"%{user_id}%')

        # Combine all conditions with OR
        combined_condition = f"AND ({' OR '.join(or_conditions)})"
        query_parts.append(combined_condition)


class AttributeParser:
    """Parses JSON attributes from database rows."""

    @staticmethod
    def parse_attributes(attributes_json: Optional[str], node_id: str) -> JSONDict:
        """Parse JSON attributes with error handling."""
        if not attributes_json:
            return {}

        try:
            result: JSONDict = json.loads(attributes_json)
            return result
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse attributes for node {node_id}")
            return {}


class DateTimeParser:
    """Parses datetime values from various formats."""

    @staticmethod
    def parse_datetime(value: Any) -> Optional[datetime]:
        """Parse datetime from various formats."""
        if not value:
            return None

        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            # Try ISO format with timezone
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                pass

            # Try without timezone
            try:
                return datetime.fromisoformat(value.split("+")[0])
            except ValueError:
                pass

        return None


class GraphNodeBuilder:
    """Builds GraphNode objects from database rows."""

    @staticmethod
    def build_from_row(row: Tuple[Any, ...]) -> Optional[GraphNode]:
        """Build a GraphNode from a database row."""
        try:
            # Parse attributes JSON
            attributes_dict = AttributeParser.parse_attributes(row[3], row[0])

            # Parse timestamps
            updated_at = DateTimeParser.parse_datetime(row[6])
            created_at = DateTimeParser.parse_datetime(row[7]) if row[7] else None

            # Create typed GraphNodeAttributes
            # Extract known fields and pass the rest as tags if present
            tags = attributes_dict.pop("tags", [])
            created_by = attributes_dict.pop("created_by", row[5] if row[5] else "system")

            # Build proper GraphNodeAttributes
            typed_attributes = GraphNodeAttributes(
                created_at=created_at or updated_at or datetime.now(),
                updated_at=updated_at or datetime.now(),
                created_by=created_by,
                tags=tags if isinstance(tags, list) else [],
            )

            # Create GraphNode with typed attributes
            return GraphNode(
                id=row[0],  # node_id
                scope=row[1],  # scope
                type=row[2],  # node_type
                attributes=typed_attributes,
                version=row[4] if row[4] else 1,  # version
                updated_by=row[5] if row[5] else "system",  # updated_by
                updated_at=updated_at,
            )
        except Exception as e:
            logger.error(f"Failed to create GraphNode from row: {e}")
            return None

    @staticmethod
    def build_from_rows(rows: List[Tuple[Any, ...]]) -> List[GraphNode]:
        """Build multiple GraphNodes from database rows."""
        nodes = []
        for row in rows:
            node = GraphNodeBuilder.build_from_row(row)
            if node:
                nodes.append(node)
        return nodes


class DatabaseExecutor:
    """Executes database queries with proper error handling."""

    @staticmethod
    def execute_query(db_path: str, query: str, params: List[Any]) -> List[Tuple[Any, ...]]:
        """Execute a query and return results."""
        try:
            with get_db_connection(db_path=db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Database query failed: {e}")
            return []

    @staticmethod
    def get_db_path(memory_service: Any) -> Optional[str]:
        """Extract database path from memory service."""
        db_path = getattr(memory_service, "db_path", None)
        if not db_path:
            logger.warning("Memory service has no db_path")
        return db_path


class TimeRangeCalculator:
    """Calculates time ranges for queries."""

    @staticmethod
    def calculate_range(hours: int) -> Tuple[datetime, datetime]:
        """Calculate start and end time from hours."""
        now = datetime.now()
        start_time = now - timedelta(hours=hours)
        return start_time, now

    @staticmethod
    def calculate_range_from_days(days: int) -> Tuple[datetime, datetime]:
        """Calculate start and end time from days."""
        now = datetime.now()
        start_time = now - timedelta(days=days)
        return start_time, now
