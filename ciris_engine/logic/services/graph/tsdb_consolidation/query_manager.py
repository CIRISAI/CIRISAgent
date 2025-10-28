"""
Query management for TSDB consolidation.

Handles querying both graph nodes and service correlations for consolidation periods.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, TypedDict

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.persistence.db.core import get_db_connection
from ciris_engine.logic.services.graph.tsdb_consolidation.data_converter import TSDBDataConverter
from ciris_engine.schemas.services.graph.consolidation import (
    MetricCorrelationData,
    ServiceInteractionData,
    TaskCorrelationData,
    TraceSpanData,
)
from ciris_engine.schemas.services.graph.query_results import ServiceCorrelationQueryResult, TSDBNodeQueryResult
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class ThoughtQueryResult(TypedDict):
    """Type for thought query results."""

    thought_id: str
    thought_type: str
    status: str
    created_at: str
    final_action: Optional[JSONDict]


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

    def _query_thoughts_for_tasks(
        self, cursor: Any, adapter: Any, task_ids: List[str]
    ) -> Dict[str, List[ThoughtQueryResult]]:
        """Query thoughts for a list of task IDs.

        Args:
            cursor: Database cursor
            adapter: Database adapter for placeholders
            task_ids: List of task IDs to query

        Returns:
            Dict mapping task_id to list of thought query results
        """
        placeholders = ",".join([adapter.placeholder()] * len(task_ids))
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

        thoughts_by_task = defaultdict(list)
        for row in cursor.fetchall():
            # Handle PostgreSQL datetime vs SQLite string
            created_at = row["created_at"]
            if isinstance(created_at, datetime):
                created_at = created_at.isoformat()

            thoughts_by_task[row["source_task_id"]].append(
                {
                    "thought_id": row["thought_id"],
                    "thought_type": row["thought_type"],
                    "status": row["status"],
                    "created_at": created_at,
                    "final_action": row["final_action_json"],
                }
            )

        return dict(thoughts_by_task)

    def query_all_nodes_in_period(self, period_start: datetime, period_end: datetime) -> Dict[str, TSDBNodeQueryResult]:
        """
        Query ALL graph nodes created or updated within a period.

        Args:
            period_start: Period start time
            period_end: Period end time

        Returns:
            Dictionary mapping node types to TSDBNodeQueryResult objects
        """
        from ciris_engine.logic.persistence.db.dialect import get_adapter
        from ciris_engine.logic.services.graph.tsdb_consolidation.sql_builders import (
            build_nodes_in_period_query,
            parse_graph_node_row,
        )

        nodes_by_type = defaultdict(list)

        try:
            adapter = get_adapter()

            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Build and execute query using helper
                sql, params = build_nodes_in_period_query(adapter, period_start.isoformat(), period_end.isoformat())
                cursor.execute(sql, params)

                # Parse rows using helper
                for row in cursor.fetchall():
                    node = parse_graph_node_row(row)
                    node_type_str = row["node_type"]
                    nodes_by_type[node_type_str].append(node)

                logger.info(
                    f"Found {sum(len(nodes) for nodes in nodes_by_type.values())} nodes across {len(nodes_by_type)} types for period {period_start}"
                )

        except Exception as e:
            logger.error(f"Failed to query nodes for period: {e}")

        # Convert to TSDBNodeQueryResult for each node type
        result: Dict[str, TSDBNodeQueryResult] = {}
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
        from ciris_engine.logic.persistence.db.dialect import get_adapter
        from ciris_engine.logic.services.graph.tsdb_consolidation.sql_builders import (
            build_tsdb_data_query,
            parse_graph_node_row,
        )

        nodes = []

        try:
            adapter = get_adapter()

            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Build and execute query using helper
                sql, params = build_tsdb_data_query(adapter, period_start.isoformat(), period_end.isoformat())
                cursor.execute(sql, params)

                # Parse rows using helper
                for row in cursor.fetchall():
                    node = parse_graph_node_row(row, node_type=NodeType.TSDB_DATA)
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
        from ciris_engine.logic.persistence.db.dialect import get_adapter
        from ciris_engine.logic.services.graph.tsdb_consolidation.sql_builders import (
            build_service_correlations_query,
            parse_correlation_row,
        )

        service_interactions: List[ServiceInteractionData] = []
        metric_correlations: List[MetricCorrelationData] = []
        trace_spans: List[TraceSpanData] = []
        task_correlations: List[TaskCorrelationData] = []

        try:
            adapter = get_adapter()

            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Build and execute query using helper
                query, params = build_service_correlations_query(
                    adapter, period_start.isoformat(), period_end.isoformat(), correlation_types
                )
                cursor.execute(query, params)

                # Parse rows using helper
                for row in cursor.fetchall():
                    raw_correlation = parse_correlation_row(row)
                    correlation_type = row["correlation_type"]

                    # Convert to typed models based on correlation type
                    if correlation_type == "service_interaction":
                        converted_interaction = TSDBDataConverter.convert_service_interaction(raw_correlation)
                        if converted_interaction:
                            service_interactions.append(converted_interaction)
                    elif correlation_type == "metric_datapoint":
                        converted_metric = TSDBDataConverter.convert_metric_correlation(raw_correlation)
                        if converted_metric:
                            metric_correlations.append(converted_metric)
                    elif correlation_type == "trace_span":
                        converted_trace = TSDBDataConverter.convert_trace_span(raw_correlation)
                        if converted_trace:
                            trace_spans.append(converted_trace)

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
            from ciris_engine.logic.persistence.db.dialect import get_adapter

            adapter = get_adapter()

            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Query tasks (excluding deferred ones)
                # PostgreSQL: TIMESTAMP column, compare directly
                # SQLite: TEXT column, use datetime() function
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

                cursor.execute(sql, (period_start.isoformat(), period_end.isoformat()))

                raw_tasks = []
                for row in cursor.fetchall():
                    # Handle PostgreSQL datetime vs SQLite string for timestamps
                    created_at = row["created_at"]
                    if isinstance(created_at, datetime):
                        created_at = created_at.isoformat()

                    updated_at = row["updated_at"]
                    if isinstance(updated_at, datetime):
                        updated_at = updated_at.isoformat()

                    task = {
                        "task_id": row["task_id"],
                        "channel_id": row["channel_id"],
                        "description": row["description"],
                        "status": row["status"],
                        "priority": row["priority"],
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "parent_task_id": row["parent_task_id"],
                        "context": row["context_json"],
                        "outcome": row["outcome_json"],
                        "retry_count": row["retry_count"],
                    }
                    raw_tasks.append(task)

                # Also get thoughts for these tasks
                if raw_tasks:
                    task_ids = [t["task_id"] for t in raw_tasks]
                    thoughts_by_task = self._query_thoughts_for_tasks(cursor, adapter, task_ids)

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

    def acquire_consolidation_lock(self, consolidation_type: str, period_identifier: str) -> bool:
        """
        Try to acquire exclusive lock for a consolidation activity.

        This is a generic locking mechanism that works for all consolidation types:
        - basic: Lock individual 6-hour periods
        - extensive: Lock a specific week
        - profound: Lock a specific month

        Uses database-level locking to prevent multiple instances from
        consolidating simultaneously:
        - PostgreSQL: pg_try_advisory_lock with hash of type+period
        - SQLite: BEGIN IMMEDIATE transaction

        Args:
            consolidation_type: Type of consolidation ('basic', 'extensive', 'profound')
            period_identifier: Period identifier (ISO datetime for basic, date string for others)

        Returns:
            True if lock acquired successfully, False if another instance holds it
        """
        try:
            from ciris_engine.logic.persistence.db.dialect import get_adapter

            adapter = get_adapter()

            # Generate a consistent numeric lock ID from type + period
            # Use hash for deterministic lock ID across instances
            lock_key = f"{consolidation_type}:{period_identifier}"
            lock_id = hash(lock_key) & 0x7FFFFFFF  # Keep positive 32-bit

            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                if adapter.is_postgresql():
                    # PostgreSQL: Try to acquire advisory lock
                    cursor.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,))
                    result = cursor.fetchone()

                    if not result:
                        logger.error(
                            f"Failed to acquire {consolidation_type} lock for {period_identifier}: "
                            f"pg_try_advisory_lock returned no result (lock_id={lock_id})"
                        )
                        return False

                    # Convert to boolean (PostgreSQL returns integer or boolean depending on driver)
                    # Use dict-style access because RealDictCursor returns dict-like objects
                    acquired = bool(result["pg_try_advisory_lock"])

                    if acquired:
                        logger.info(
                            f"Acquired {consolidation_type} consolidation lock for {period_identifier} (lock_id={lock_id})"
                        )
                    else:
                        logger.info(
                            f"Failed to acquire {consolidation_type} lock for {period_identifier} (already locked, lock_id={lock_id})"
                        )

                    return acquired

                else:
                    # SQLite: Use BEGIN IMMEDIATE to acquire write lock
                    try:
                        cursor.execute("BEGIN IMMEDIATE")
                        conn.commit()
                        logger.info(f"Acquired SQLite write lock for {consolidation_type} {period_identifier}")
                        return True
                    except Exception as e:
                        logger.info(
                            f"Failed to acquire SQLite write lock for {consolidation_type} {period_identifier}: {e}"
                        )
                        return False

        except Exception as e:
            logger.error(
                f"Error acquiring {consolidation_type} lock for {period_identifier}: {type(e).__name__}: {e}",
                exc_info=True,
            )
            return False

    def release_consolidation_lock(self, consolidation_type: str, period_identifier: str) -> None:
        """
        Release the consolidation lock.

        Args:
            consolidation_type: Type of consolidation
            period_identifier: Period identifier
        """
        try:
            from ciris_engine.logic.persistence.db.dialect import get_adapter

            adapter = get_adapter()

            # Generate same lock ID as acquire
            lock_key = f"{consolidation_type}:{period_identifier}"
            lock_id = hash(lock_key) & 0x7FFFFFFF

            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                if adapter.is_postgresql():
                    # PostgreSQL: Release advisory lock
                    cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
                    result = cursor.fetchone()

                    if not result:
                        logger.warning(
                            f"Failed to release {consolidation_type} lock for {period_identifier}: "
                            f"pg_advisory_unlock returned no result (lock_id={lock_id})"
                        )
                        return

                    # Convert to boolean (PostgreSQL returns integer or boolean depending on driver)
                    # Use dict-style access because RealDictCursor returns dict-like objects
                    released = bool(result["pg_advisory_unlock"])

                    if released:
                        logger.debug(f"Released {consolidation_type} lock for {period_identifier} (lock_id={lock_id})")
                    else:
                        logger.warning(
                            f"Failed to release {consolidation_type} lock for {period_identifier} (not held, lock_id={lock_id})"
                        )

                else:
                    # SQLite: Lock is automatically released when connection closes
                    logger.debug(
                        f"SQLite lock for {consolidation_type} {period_identifier} will be released on connection close"
                    )

        except Exception as e:
            logger.error(
                f"Error releasing {consolidation_type} lock for {period_identifier}: {type(e).__name__}: {e}",
                exc_info=True,
            )

    def acquire_period_lock(self, period_start: datetime) -> bool:
        """
        Try to acquire exclusive lock for consolidating a period.

        Convenience wrapper for acquire_consolidation_lock for basic consolidation.

        Args:
            period_start: Period start time to lock

        Returns:
            True if lock acquired successfully, False if another instance holds it
        """
        return self.acquire_consolidation_lock("basic", period_start.isoformat())

    def release_period_lock(self, period_start: datetime) -> None:
        """
        Release the consolidation lock for a period.

        Convenience wrapper for release_consolidation_lock for basic consolidation.

        Args:
            period_start: Period start time to unlock
        """
        self.release_consolidation_lock("basic", period_start.isoformat())

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
            from ciris_engine.logic.persistence.db.dialect import get_adapter

            adapter = get_adapter()

            # Query the database directly to check for ANY tsdb_summary nodes for this period
            # This prevents duplicates from test runs or other sources
            with get_db_connection(db_path=self._db_path) as conn:
                cursor = conn.cursor()

                # Check for any tsdb_summary nodes with matching period_start
                # PostgreSQL: Use JSONB operators
                # SQLite: Use json_extract() function
                if adapter.is_postgresql():
                    sql = f"""
                        SELECT COUNT(*) as count
                        FROM graph_nodes
                        WHERE node_type = 'tsdb_summary'
                          AND attributes_json->>'period_start' = {adapter.placeholder()}
                          AND attributes_json->>'consolidation_level' = 'basic'
                    """
                else:
                    sql = f"""
                        SELECT COUNT(*) as count
                        FROM graph_nodes
                        WHERE node_type = 'tsdb_summary'
                          AND json_extract(attributes_json, '$.period_start') = {adapter.placeholder()}
                          AND json_extract(attributes_json, '$.consolidation_level') = 'basic'
                    """

                cursor.execute(sql, (period_start.isoformat(),))

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
