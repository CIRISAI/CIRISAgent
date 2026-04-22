"""
Task consolidation for completed tasks and their outcomes.

Creates TaskSummaryNode with final task results and handler selections.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, cast

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.schemas.services.graph.consolidation import TaskCorrelationData
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class TaskConsolidator:
    """Consolidates task outcomes and thought processes."""

    def __init__(self, memory_bus: Optional[MemoryBus] = None):
        """
        Initialize task consolidator.

        Args:
            memory_bus: Memory bus for storing results
        """
        self._memory_bus = memory_bus

    async def consolidate(
        self, period_start: datetime, period_end: datetime, period_label: str, tasks: List[TaskCorrelationData]
    ) -> Optional[GraphNode]:
        """
        Consolidate tasks into a summary showing outcomes and patterns.

        Args:
            period_start: Start of consolidation period
            period_end: End of consolidation period
            period_label: Human-readable period label
            tasks: List of TaskCorrelationData objects

        Returns:
            TaskSummaryNode as GraphNode if successful, None otherwise
        """
        if not tasks:
            logger.info(f"No tasks found for period {period_start} to {period_end} - creating empty summary")

        logger.info(f"Consolidating {len(tasks)} tasks for period {period_start}")

        # Aggregate task data
        tasks_by_status: Dict[str, int] = defaultdict(int)
        tasks_by_channel: Dict[str, int] = defaultdict(int)
        tasks_by_user: Dict[str, int] = defaultdict(int)
        unique_users = set()
        handler_usage: Dict[str, int] = defaultdict(int)
        task_durations = []
        task_summaries = {}
        total_thoughts = 0
        thoughts_per_task = []
        retry_stats: Dict[str, int] = defaultdict(int)

        for task in tasks:
            task_id = task.task_id
            status = task.status
            channel = task.channel_id or "unknown"
            user_id = task.user_id

            # Track unique users and count tasks per user
            if user_id:
                unique_users.add(user_id)
                tasks_by_user[user_id] += 1

            # Count by status and channel
            tasks_by_status[status] += 1
            tasks_by_channel[channel] += 1

            # Track retries
            retry_count = task.retry_count
            if retry_count > 0:
                retry_stats[f"retries_{retry_count}"] += 1

            # Use duration from schema or calculate
            duration_ms = task.duration_ms
            if duration_ms == 0:
                try:
                    created = task.created_at
                    updated = task.updated_at
                    duration_ms = (updated - created).total_seconds() * 1000
                except (AttributeError, TypeError):
                    duration_ms = 0
            task_durations.append(duration_ms)

            # Process thoughts and handlers
            thoughts = task.thoughts
            total_thoughts += len(thoughts)
            thoughts_per_task.append(len(thoughts))

            # Use handlers from schema
            handlers_selected = task.handlers_used
            for handler in handlers_selected:
                handler_usage[handler] += 1

            # Add final handler if present
            if task.final_handler:
                handler_usage[task.final_handler] += 1

            # Create task summary
            task_summaries[task_id] = {
                "task_id": task_id,
                "description": task.result_summary or "",
                "status": status,
                "channel": channel,
                "user_id": user_id,  # OBSERVER filtering: preserve user attribution
                "duration_ms": duration_ms,
                "thought_count": len(thoughts),
                "handlers_selected": handlers_selected,
                "retry_count": retry_count,
                "outcome": "success" if task.success else task.error_message,
            }

        # Calculate statistics
        avg_duration = sum(task_durations) / len(task_durations) if task_durations else 0
        avg_thoughts = sum(thoughts_per_task) / len(thoughts_per_task) if thoughts_per_task else 0

        # Sort task durations for percentiles
        if task_durations:
            sorted_durations = sorted(task_durations)
            p50_duration = sorted_durations[len(sorted_durations) // 2]
            p95_duration = sorted_durations[int(len(sorted_durations) * 0.95)]
            p99_duration = sorted_durations[int(len(sorted_durations) * 0.99)]
        else:
            p50_duration = p95_duration = p99_duration = 0

        # Calculate completion rate
        completed_tasks = tasks_by_status.get("completed", 0) + tasks_by_status.get("success", 0)
        total_tasks = len(tasks)
        completion_rate = completed_tasks / total_tasks if total_tasks > 0 else 0

        # Create task summary node
        summary_data = {
            "id": f"task_summary_{period_start.strftime('%Y%m%d_%H')}",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "period_label": period_label,
            "total_tasks": total_tasks,
            "tasks_by_status": dict(tasks_by_status),
            "tasks_by_channel": dict(tasks_by_channel),
            "tasks_by_user": dict(tasks_by_user),  # OBSERVER filtering: task count per user
            "user_list": list(unique_users),  # OBSERVER filtering: all users involved
            "unique_users": len(unique_users),
            "completion_rate": completion_rate,
            "total_thoughts": total_thoughts,
            "avg_thoughts_per_task": avg_thoughts,
            "handler_usage": dict(handler_usage),
            "avg_duration_ms": avg_duration,
            "p50_duration_ms": p50_duration,
            "p95_duration_ms": p95_duration,
            "p99_duration_ms": p99_duration,
            "retry_stats": dict(retry_stats),
            "task_summaries": task_summaries,
            "created_at": period_end.isoformat(),
            "updated_at": period_end.isoformat(),
        }

        # Create GraphNode
        summary_node = GraphNode(
            id=str(summary_data["id"]),
            type=NodeType.TASK_SUMMARY,
            scope=GraphScope.LOCAL,
            attributes=summary_data,
            updated_by="tsdb_consolidation",
            updated_at=period_end,  # Use period end as timestamp
        )

        # Store summary
        if self._memory_bus:
            result = await self._memory_bus.memorize(node=summary_node)
            if result.status != MemoryOpStatus.OK:
                logger.error(f"Failed to store task summary: {result.error}")
                return None
        else:
            logger.error("Memory bus not available")
            return None

        return summary_node

    def get_edges(
        self, summary_node: GraphNode, tasks: List[TaskCorrelationData]
    ) -> List[Tuple[GraphNode, GraphNode, str, JSONDict]]:
        """
        Get edges to create for task summary.

        Returns edges from summary to:
        - Failed tasks
        - Tasks with retries
        - Long-running tasks
        """
        edges = []

        # Process tasks for edge creation
        failed_count = 0
        retry_count = 0
        long_running_count = 0

        for task in tasks:
            task_id = task.task_id

            # Failed tasks
            if not task.success and failed_count < 5:
                edges.append(
                    (
                        summary_node,
                        summary_node,  # Self-reference with task data
                        "FAILED_TASK",
                        {
                            "task_id": task_id,
                            "failure_reason": task.error_message or "unknown",
                            "channel_id": task.channel_id,
                        },
                    )
                )
                failed_count += 1

            # Tasks with retries
            if task.retry_count > 0 and retry_count < 5:
                edges.append(
                    (
                        summary_node,
                        summary_node,  # Self-reference with task data
                        "RETRIED_TASK",
                        {"task_id": task_id, "retry_count": str(task.retry_count), "final_status": task.status},
                    )
                )
                retry_count += 1

            # Long-running tasks (> 1 minute)
            duration_seconds = task.duration_ms / 1000.0
            if duration_seconds > 60 and long_running_count < 5:
                task_attrs: Dict[str, Optional[str]] = {
                    "task_id": task_id,
                    "duration_seconds": str(duration_seconds),
                    "status": task.status,
                }
                edges.append(
                    (
                        summary_node,
                        summary_node,  # Self-reference with task data
                        "LONG_RUNNING_TASK",
                        task_attrs,
                    )
                )
                long_running_count += 1

        return cast(List[Tuple[GraphNode, GraphNode, str, JSONDict]], edges)
