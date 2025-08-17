"""
Memory query helpers - modular functions for database queries.

Following CIRIS principles:
- Single Responsibility: Each class handles one aspect
- Type Safety: All inputs and outputs are typed
- No Kings: No special cases or bypass patterns
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

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
    ) -> Tuple[str, List[Any]]:
        """Build a timeline query with filters."""
        query_parts = [QueryBuilder.SQL_SELECT_NODES, QueryBuilder.SQL_FROM_NODES, QueryBuilder.SQL_WHERE_TIME_RANGE]
        params = [start_time.isoformat(), end_time.isoformat()]

        if exclude_metrics:
            query_parts.append(QueryBuilder.SQL_EXCLUDE_METRICS)

        if scope:
            query_parts.append(QueryBuilder.SQL_WHERE_SCOPE)
            params.append(scope.value if hasattr(scope, "value") else str(scope))

        if node_type:
            query_parts.append(QueryBuilder.SQL_WHERE_NODE_TYPE)
            params.append(node_type.value if hasattr(node_type, "value") else str(node_type))

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
    ) -> Tuple[str, List[Any]]:
        """Build a search query with multiple filters."""
        query_parts = [QueryBuilder.SQL_SELECT_NODES, QueryBuilder.SQL_FROM_NODES, "WHERE 1=1"]
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
            query_parts.append("AND attributes_json LIKE ?")
            params.append(f"%{query}%")

        if tags:
            for tag in tags:
                query_parts.append("AND attributes_json LIKE ?")
                params.append(f'%"{tag}"%')

        query_parts.append(QueryBuilder.SQL_ORDER_BY)
        query_parts.append(f"LIMIT {limit} OFFSET {offset}")

        return " ".join(query_parts), params


class AttributeParser:
    """Parses JSON attributes from database rows."""

    @staticmethod
    def parse_attributes(attributes_json: Optional[str], node_id: str) -> Dict[str, Any]:
        """Parse JSON attributes with error handling."""
        if not attributes_json:
            return {}

        try:
            return json.loads(attributes_json)
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
    def build_from_row(row: Tuple) -> Optional[GraphNode]:
        """Build a GraphNode from a database row."""
        try:
            # Parse attributes
            attributes = AttributeParser.parse_attributes(row[3], row[0])

            # Parse timestamps
            updated_at = DateTimeParser.parse_datetime(row[6])
            created_at = DateTimeParser.parse_datetime(row[7]) if row[7] else None

            # Create GraphNode
            return GraphNode(
                id=row[0],  # node_id
                scope=row[1],  # scope
                type=row[2],  # node_type
                attributes=attributes,
                version=row[4] if row[4] else 1,  # version
                updated_by=row[5] if row[5] else "system",  # updated_by
                updated_at=updated_at,
                created_at=created_at,
            )
        except Exception as e:
            logger.error(f"Failed to create GraphNode from row: {e}")
            return None

    @staticmethod
    def build_from_rows(rows: List[Tuple]) -> List[GraphNode]:
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
    def execute_query(db_path: str, query: str, params: List[Any]) -> List[Tuple]:
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
