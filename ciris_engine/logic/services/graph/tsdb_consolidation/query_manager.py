"""
Query management for TSDB consolidation.

Handles querying both graph nodes and service correlations for consolidation periods.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.logic.services.graph.tsdb_consolidation.data_converter import TSDBDataConverter
from ciris_engine.schemas.services.graph.consolidation import TaskCorrelationData
from ciris_engine.schemas.services.graph.query_results import ServiceCorrelationQueryResult, TSDBNodeQueryResult
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery

logger = logging.getLogger(__name__)


class QueryManager:
    """Manages querying data for consolidation."""

    def __init__(self, memory_bus: Optional[MemoryBus] = None, db_path: Optional[str] = None):
        """
        Initialize query manager.

        Args:
            memory_bus: Memory bus for graph operations
            db_path: Database path to use (if not provided, uses default)
        """
        self._memory_bus = memory_bus
        self._db_path = db_path

    def query_all_nodes_in_period(self, period_start: datetime, period_end: datetime) -> Dict[str, TSDBNodeQueryResult]:
        """
        Query ALL graph nodes created or updated within a period.

        Args:
            period_start: Period start time
            period_end: Period end time

        Returns:
            Dictionary mapping node types to TSDBNodeQueryResult objects
        """
        nodes_by_type = defaultdict(list)

        # Note: We don't actually need memory bus for direct DB queries
        # This method queries the database directly

        try:
            # Direct database query for efficiency
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Query all LOCAL nodes CREATED in this period
                # CRITICAL: Only local nodes can have edges within the same scope
                # We want nodes CREATED during the period, not just updated
                cursor.execute(
                    """
                    SELECT node_id, node_type, scope, attributes_json,
                           version, updated_by, updated_at, created_at
                    FROM graph_nodes
                    WHERE scope = 'local'
                      AND datetime(created_at) >= datetime(?)
                      AND datetime(created_at) < datetime(?)
                    ORDER BY node_type, created_at
                """,
                    (period_start.isoformat(), period_end.isoformat()),
                )

                for row in cursor.fetchall():
                    # Parse node type
                    node_type_str = row["node_type"]
                    try:
                        node_type = NodeType(node_type_str)
                    except ValueError:
                        # For unknown types, use AGENT as fallback
                        node_type = NodeType.AGENT

                    # Parse attributes JSON
                    import json

                    attributes = {}
                    if row["attributes_json"]:
                        try:
                            attributes = json.loads(row["attributes_json"])
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse attributes for node {row['node_id']}")

                    # Create GraphNode
                    node = GraphNode(
                        id=row["node_id"],
                        type=node_type,
                        scope=GraphScope(row["scope"]) if row["scope"] else GraphScope.LOCAL,
                        attributes=attributes,
                        version=row["version"],
                        updated_by=row["updated_by"],
                        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    )

                    nodes_by_type[node_type_str].append(node)

                logger.info(
                    f"Found {sum(len(nodes) for nodes in nodes_by_type.values())} nodes across {len(nodes_by_type)} types for period {period_start}"
                )

        except Exception as e:
            logger.error(f"Failed to query nodes for period: {e}")

        # Convert to TSDBNodeQueryResult for each node type
        result = {}
        for node_type, nodes in nodes_by_type.items():
            result[node_type] = TSDBNodeQueryResult(nodes=nodes, period_start=period_start, period_end=period_end)

        return result

    def query_tsdb_data_nodes(self, period_start: datetime, period_end: datetime) -> TSDBNodeQueryResult:
        """
        Query TSDB_DATA nodes specifically for a period.

        Args:
            period_start: Period start time
            period_end: Period end time

        Returns:
            TSDBNodeQueryResult containing TSDB_DATA nodes
        """
        nodes = []

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Query TSDB_DATA nodes
                cursor.execute(
                    """
                    SELECT node_id, scope, attributes_json, version,
                           updated_by, updated_at, created_at
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_data'
                      AND ((datetime(updated_at) >= datetime(?) AND datetime(updated_at) < datetime(?))
                           OR (updated_at IS NULL AND datetime(created_at) >= datetime(?) AND datetime(created_at) < datetime(?)))
                    ORDER BY updated_at
                """,
                    (
                        period_start.isoformat(),
                        period_end.isoformat(),
                        period_start.isoformat(),
                        period_end.isoformat(),
                    ),
                )

                for row in cursor.fetchall():
                    # Parse attributes JSON
                    import json

                    attributes = {}
                    if row["attributes_json"]:
                        try:
                            attributes = json.loads(row["attributes_json"])
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse attributes for node {row['node_id']}")

                    node = GraphNode(
                        id=row["node_id"],
                        type=NodeType.TSDB_DATA,
                        scope=GraphScope(row["scope"]) if row["scope"] else GraphScope.LOCAL,
                        attributes=attributes,
                        version=row["version"],
                        updated_by=row["updated_by"],
                        updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    )
                    nodes.append(node)

                logger.info(f"Found {len(nodes)} TSDB_DATA nodes for period {period_start}")

        except Exception as e:
            logger.error(f"Failed to query TSDB data nodes: {e}")

        return TSDBNodeQueryResult(nodes=nodes, period_start=period_start, period_end=period_end)

    def query_service_correlations(
        self, period_start: datetime, period_end: datetime, correlation_types: Optional[List[str]] = None
    ) -> ServiceCorrelationQueryResult:
        """
        Query service correlations for a period.

        Args:
            period_start: Period start time
            period_end: Period end time
            correlation_types: Optional list of correlation types to filter

        Returns:
            ServiceCorrelationQueryResult with typed correlation data
        """
        service_interactions = []
        metric_correlations = []
        trace_spans = []
        task_correlations = []

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Build query
                query = """
                    SELECT correlation_id, correlation_type, service_type, action_type,
                           trace_id, span_id, parent_span_id,
                           timestamp, request_data, response_data, tags
                    FROM service_correlations
                    WHERE datetime(timestamp) >= datetime(?) AND datetime(timestamp) < datetime(?)
                """

                params = [period_start.isoformat(), period_end.isoformat()]

                if correlation_types:
                    placeholders = ",".join("?" * len(correlation_types))
                    query += f" AND correlation_type IN ({placeholders})"
                    params.extend(correlation_types)

                query += " ORDER BY timestamp"

                cursor.execute(query, params)

                for row in cursor.fetchall():
                    # Parse timestamp
                    ts_str = row["timestamp"]
                    if ts_str:
                        ts = datetime.fromisoformat(ts_str.replace("Z", UTC_TIMEZONE_SUFFIX))
                    else:
                        ts = None

                    # Parse JSON fields
                    request_data = row["request_data"]
                    if request_data and isinstance(request_data, str):
                        try:
                            request_data = json.loads(request_data)
                        except Exception:
                            request_data = {}
                    elif request_data is None:
                        request_data = {}

                    response_data = row["response_data"]
                    if isinstance(response_data, str) and response_data.strip():
                        try:
                            response_data = json.loads(response_data)
                        except Exception as e:
                            logger.debug(f"Failed to parse response_data: {e}")
                            response_data = {}
                    else:
                        response_data = {}

                    tags = row["tags"]
                    if isinstance(tags, str) and tags.strip():
                        try:
                            tags = json.loads(tags)
                        except Exception as e:
                            logger.debug(f"Failed to parse tags: {e}")
                            tags = {}
                    else:
                        tags = {}

                    # Create raw correlation dict for converter
                    raw_correlation = {
                        "correlation_id": row["correlation_id"],
                        "correlation_type": row["correlation_type"],
                        "service_type": row["service_type"],
                        "action_type": row["action_type"],
                        "trace_id": row["trace_id"],
                        "span_id": row["span_id"],
                        "parent_span_id": row["parent_span_id"],
                        "timestamp": ts,
                        "request_data": request_data,
                        "response_data": response_data,
                        "tags": tags,
                    }

                    # Convert to typed models based on correlation type
                    correlation_type = row["correlation_type"]

                    if correlation_type == "service_interaction":
                        converted = TSDBDataConverter.convert_service_interaction(raw_correlation)
                        if converted:
                            service_interactions.append(converted)
                    elif correlation_type == "metric_datapoint":
                        converted = TSDBDataConverter.convert_metric_correlation(raw_correlation)
                        if converted:
                            metric_correlations.append(converted)
                    elif correlation_type == "trace_span":
                        converted = TSDBDataConverter.convert_trace_span(raw_correlation)
                        if converted:
                            trace_spans.append(converted)
                    elif correlation_type == "task_correlation":
                        # For task correlations, we'll query the tasks separately
                        pass

                total = len(service_interactions) + len(metric_correlations) + len(trace_spans) + len(task_correlations)
                logger.info(f"Found {total} correlations for period {period_start}")

        except Exception as e:
            logger.error(f"Failed to query service correlations: {e}")
            import traceback

            traceback.print_exc()

        return ServiceCorrelationQueryResult(
            service_interactions=service_interactions,
            metric_correlations=metric_correlations,
            trace_spans=trace_spans,
            task_correlations=task_correlations,
        )

    def query_tasks_in_period(self, period_start: datetime, period_end: datetime) -> List[TaskCorrelationData]:
        """
        Query tasks completed or updated in a period.

        Args:
            period_start: Period start time
            period_end: Period end time

        Returns:
            List of TaskCorrelationData objects
        """
        task_correlations = []

        try:
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Query tasks (excluding deferred ones)
                cursor.execute(
                    """
                    SELECT task_id, channel_id, description, status, priority,
                           created_at, updated_at, parent_task_id,
                           context_json, outcome_json, retry_count
                    FROM tasks
                    WHERE datetime(updated_at) >= datetime(?) AND datetime(updated_at) < datetime(?)
                      AND status != 'deferred'
                    ORDER BY updated_at
                """,
                    (period_start.isoformat(), period_end.isoformat()),
                )

                raw_tasks = []
                for row in cursor.fetchall():
                    task = {
                        "task_id": row["task_id"],
                        "channel_id": row["channel_id"],
                        "description": row["description"],
                        "status": row["status"],
                        "priority": row["priority"],
                        "created_at": row["created_at"],
                        "updated_at": row["updated_at"],
                        "parent_task_id": row["parent_task_id"],
                        "context": row["context_json"],
                        "outcome": row["outcome_json"],
                        "retry_count": row["retry_count"],
                    }
                    raw_tasks.append(task)

                # Also get thoughts for these tasks
                if raw_tasks:
                    task_ids = [t["task_id"] for t in raw_tasks]
                    placeholders = ",".join("?" * len(task_ids))

                    cursor.execute(
                        f"""
                        SELECT source_task_id, thought_id, thought_type, status,
                               created_at, final_action_json
                        FROM thoughts
                        WHERE source_task_id IN ({placeholders})
                        ORDER BY created_at
                    """,
                        task_ids,
                    )

                    # Group thoughts by task
                    thoughts_by_task = defaultdict(list)
                    for row in cursor.fetchall():
                        thoughts_by_task[row["source_task_id"]].append(
                            {
                                "thought_id": row["thought_id"],
                                "thought_type": row["thought_type"],
                                "status": row["status"],
                                "created_at": row["created_at"],
                                "final_action": row["final_action_json"],
                            }
                        )

                    # Add thoughts to tasks and convert to typed models
                    for task in raw_tasks:
                        task["thoughts"] = thoughts_by_task.get(task["task_id"], [])

                        # Convert to TaskCorrelationData
                        converted = TSDBDataConverter.convert_task(task)
                        if converted:
                            task_correlations.append(converted)

                logger.info(f"Found {len(task_correlations)} tasks for period {period_start}")

        except Exception as e:
            logger.error(f"Failed to query tasks: {e}")

        return task_correlations

    def get_special_node_types(self) -> Set[str]:
        """
        Get the list of special node types to track in summaries.

        Returns:
            Set of node type strings
        """
        return {
            "concept",
            "shutdown_memory",
            "identity_update",
            "config_update",
            "wise_feedback",
            "self_observation",
            "task_assignment",
            "user",
            "agent",
            "observation",
        }

    def check_period_consolidated(self, period_start: datetime) -> bool:
        """
        Check if a period has already been consolidated.

        Args:
            period_start: Start of the period

        Returns:
            True if already consolidated
        """
        if not self._memory_bus:
            return False

        try:
            # Query the database directly to check for ANY tsdb_summary nodes for this period
            # This prevents duplicates from test runs or other sources
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Check for any tsdb_summary nodes with matching period_start
                cursor.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM graph_nodes
                    WHERE node_type = 'tsdb_summary'
                      AND json_extract(attributes_json, '$.period_start') = ?
                      AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
                """,
                    (period_start.isoformat(),),
                )

                row = cursor.fetchone()
                count = row["count"] if row else 0

                if count > 0:
                    logger.info(f"Period {period_start} already has {count} consolidation(s)")

                return count > 0

        except Exception as e:
            logger.error(f"Failed to check consolidation status: {e}")
            return False

    async def get_last_consolidated_period(self) -> Optional[datetime]:
        """
        Get the timestamp of the last successfully consolidated period.

        Returns:
            Datetime of the last consolidated period start, or None if no consolidation found
        """
        if not self._memory_bus:
            return None

        try:
            # Query for TSDB summary nodes using wildcard
            query = MemoryQuery(
                node_id="tsdb_summary_*",  # Wildcard to match all TSDB summaries
                scope=GraphScope.LOCAL,
                type=NodeType.TSDB_SUMMARY,
                include_edges=False,
                depth=1,
            )

            summaries = await self._memory_bus.recall(query, handler_name="tsdb_consolidation")

            if not summaries:
                return None

            # Extract period timestamps from node IDs
            periods = []
            for summary in summaries:
                # Node ID format: tsdb_summary_YYYYMMDD_HH
                if summary.id.startswith("tsdb_summary_"):
                    period_str = summary.id.replace("tsdb_summary_", "")
                    try:
                        # Parse format YYYYMMDD_HH
                        date_part, hour_part = period_str.split("_")
                        year = int(date_part[:4])
                        month = int(date_part[4:6])
                        day = int(date_part[6:8])
                        hour = int(hour_part)

                        period_dt = datetime(year, month, day, hour, tzinfo=timezone.utc)
                        periods.append(period_dt)
                    except (ValueError, IndexError) as e:
                        logger.warning(f"Failed to parse period from summary ID {summary.id}: {e}")
                        continue

            # Return the most recent period
            if periods:
                return max(periods)

            return None

        except Exception as e:
            logger.error(f"Failed to get last consolidated period: {e}")
            return None
