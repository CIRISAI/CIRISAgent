"""
Trace consolidation for trace spans and task processing.

Consolidates TRACE_SPAN correlations into TraceSummaryNode.
"""

import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple, TypedDict, Union

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.utils.jsondict_helpers import get_dict, get_float, get_int, get_list, get_str
from ciris_engine.schemas.services.graph.consolidation import TraceSpanData
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class ThoughtInfo(TypedDict):
    """Information about a thought in a task."""

    thought_id: str
    handler: str
    timestamp: Optional[str]


class TaskSummaryData(TypedDict, total=False):
    """Summary data for a task (using total=False for optional fields).

    Note: This TypedDict is used for documentation purposes.
    Actual runtime uses JSONDict to allow datetime/Set objects
    that are later serialized to JSON-compatible types.
    """

    task_id: str
    status: str
    thoughts: List[JSONDict]  # List of thought info dicts
    start_time: datetime
    end_time: datetime
    handlers_selected: List[str]
    trace_ids: Set[str]
    duration_ms: float


class TraceConsolidator:
    """Consolidates trace span data into summaries."""

    def __init__(self, memory_bus: Optional[MemoryBus] = None):
        """
        Initialize trace consolidator.

        Args:
            memory_bus: Memory bus for storing results
        """
        self._memory_bus = memory_bus

    async def consolidate(
        self, period_start: datetime, period_end: datetime, period_label: str, trace_spans: List[TraceSpanData]
    ) -> Optional[GraphNode]:
        """
        Consolidate trace spans into a summary showing task processing patterns.

        Args:
            period_start: Start of consolidation period
            period_end: End of consolidation period
            period_label: Human-readable period label
            trace_spans: List of TraceSpanData objects

        Returns:
            TraceSummaryNode as GraphNode if successful
        """
        if not trace_spans:
            logger.info(f"No trace spans found for period {period_start} - creating empty summary")

        logger.info(f"Consolidating {len(trace_spans)} trace spans")

        # Initialize tracking structures
        # Note: Using JSONDict because task_summaries contains datetime and Set objects
        # that are later serialized to JSON-compatible types before storage
        task_summaries: JSONDict = {}  # task_id -> summary data
        unique_tasks: Set[str] = set()
        unique_thoughts: Set[str] = set()
        tasks_by_status: Dict[str, int] = defaultdict(int)
        thoughts_by_type: Dict[str, int] = defaultdict(int)
        component_calls: Dict[str, int] = defaultdict(int)
        component_failures: Dict[str, int] = defaultdict(int)
        component_latencies: Dict[str, List[float]] = defaultdict(list)
        handler_actions: Dict[str, int] = defaultdict(int)
        errors_by_component: Dict[str, int] = defaultdict(int)
        total_errors = 0
        guardrail_violations: Dict[str, int] = defaultdict(int)
        dma_decisions: Dict[str, int] = defaultdict(int)

        for span in trace_spans:
            # Extract key identifiers from typed schema
            trace_id = span.trace_id
            span_id = span.span_id
            parent_span_id = span.parent_span_id
            timestamp = span.timestamp

            # Extract from tags
            tags = span.tags
            task_id = span.task_id
            thought_id = span.thought_id
            component_type = span.component_type or "unknown"

            # Track unique entities
            if task_id:
                unique_tasks.add(task_id)

                # Initialize task summary if needed
                if task_id not in task_summaries:
                    task_summaries[task_id] = {
                        "task_id": task_id,
                        "status": "processing",
                        "thoughts": [],
                        "start_time": timestamp,
                        "end_time": timestamp,
                        "handlers_selected": [],
                        "trace_ids": set(),
                    }

                # Type narrowing for nested access
                task_summary_val = task_summaries.get(task_id)
                if isinstance(task_summary_val, dict):
                    trace_ids_val = task_summary_val.get("trace_ids")
                    if isinstance(trace_ids_val, set):
                        trace_ids_val.add(trace_id)
                    task_summary_val["end_time"] = timestamp

            if thought_id:
                unique_thoughts.add(thought_id)

                # Track thought type
                thought_type = "unknown"
                if tags and hasattr(tags, "additional_tags"):
                    thought_type_val = tags.additional_tags.get("thought_type", "unknown")
                    thought_type = str(thought_type_val) if thought_type_val else "unknown"
                thoughts_by_type[thought_type] += 1

                # Track handler selection
                if component_type == "handler" and task_id:
                    action_type = "unknown"
                    if tags and hasattr(tags, "additional_tags"):
                        action_type_val = tags.additional_tags.get("action_type", "unknown")
                        action_type = str(action_type_val) if action_type_val else "unknown"
                    handler_actions[action_type] += 1

                    task_summary_handler = task_summaries.get(task_id)
                    if isinstance(task_summary_handler, dict):
                        handlers_sel = task_summary_handler.get("handlers_selected")
                        if isinstance(handlers_sel, list):
                            handlers_sel.append(action_type)

                        thoughts_list = task_summary_handler.get("thoughts")
                        if isinstance(thoughts_list, list):
                            thoughts_list.append(
                                {
                                    "thought_id": thought_id,
                                    "handler": action_type,
                                    "timestamp": timestamp.isoformat() if timestamp else None,
                                }
                            )

            # Track task completion
            if task_id and tags and hasattr(tags, "additional_tags") and tags.additional_tags.get("task_status"):
                status_val = tags.additional_tags["task_status"]
                status = str(status_val) if isinstance(status_val, (str, int, float)) else "unknown"
                tasks_by_status[status] += 1
                task_summary_status = task_summaries.get(task_id)
                if isinstance(task_summary_status, dict):
                    task_summary_status["status"] = status

            # Component tracking
            component_calls[component_type] += 1

            # Process error information
            if span.error:
                component_failures[component_type] += 1
                errors_by_component[component_type] += 1
                total_errors += 1

            # Track latency
            if span.latency_ms is not None:
                component_latencies[component_type].append(span.latency_ms)
            elif span.duration_ms > 0:
                component_latencies[component_type].append(span.duration_ms)

            # Track guardrail violations
            if component_type == "guardrail":
                guardrail_type = "unknown"
                violation = False
                if tags and hasattr(tags, "additional_tags"):
                    guardrail_type_val = tags.additional_tags.get("guardrail_type", "unknown")
                    guardrail_type = str(guardrail_type_val) if guardrail_type_val else "unknown"
                    violation = tags.additional_tags.get("violation") == "true"
                if violation:
                    guardrail_violations[guardrail_type] += 1

            # Track DMA decisions
            if component_type == "dma":
                dma_type = "unknown"
                if tags and hasattr(tags, "additional_tags"):
                    dma_type_val = tags.additional_tags.get("dma_type", "unknown")
                    dma_type = str(dma_type_val) if dma_type_val else "unknown"
                dma_decisions[dma_type] += 1

        # Calculate latency statistics
        component_latency_stats = {}
        for component, latencies in component_latencies.items():
            if latencies:
                sorted_latencies = sorted(latencies)
                component_latency_stats[component] = {
                    "avg": sum(latencies) / len(latencies),
                    "p50": sorted_latencies[len(sorted_latencies) // 2],
                    "p95": sorted_latencies[int(len(sorted_latencies) * 0.95)],
                    "p99": sorted_latencies[int(len(sorted_latencies) * 0.99)],
                }

        # Calculate task processing times
        task_processing_times = []
        for task_id, summary_val in task_summaries.items():
            if not isinstance(summary_val, dict):
                continue
            summary = summary_val

            start_time = summary.get("start_time")
            end_time = summary.get("end_time")
            if isinstance(start_time, datetime) and isinstance(end_time, datetime):
                duration_ms = (end_time - start_time).total_seconds() * 1000
                task_processing_times.append(duration_ms)
                summary["duration_ms"] = duration_ms

            # Convert sets to lists for JSON serialization
            trace_ids = summary.get("trace_ids")
            if isinstance(trace_ids, set):
                summary["trace_ids"] = list(trace_ids)

        # Calculate task time percentiles
        avg_task_time = 0.0
        p50_task_time = 0.0
        p95_task_time = 0.0
        p99_task_time = 0.0

        if task_processing_times:
            sorted_times = sorted(task_processing_times)
            avg_task_time = sum(task_processing_times) / len(task_processing_times)
            p50_task_time = sorted_times[len(sorted_times) // 2]
            p95_task_time = sorted_times[int(len(sorted_times) * 0.95)]
            p99_task_time = sorted_times[int(len(sorted_times) * 0.99)]

        # Calculate trace depth metrics
        trace_depths = []
        for s in task_summaries.values():
            if isinstance(s, dict):
                thoughts = get_list(s, "thoughts", [])
                trace_depths.append(len(thoughts))
        max_trace_depth = max(trace_depths) if trace_depths else 0
        avg_trace_depth = sum(trace_depths) / len(trace_depths) if trace_depths else 0.0

        # Calculate error rate
        total_calls = sum(component_calls.values())
        error_rate = total_errors / total_calls if total_calls > 0 else 0.0

        # Calculate avg thoughts per task
        avg_thoughts_per_task = len(unique_thoughts) / len(unique_tasks) if unique_tasks else 0.0

        # Create summary data
        summary_data = {
            "id": f"trace_summary_{period_start.strftime('%Y%m%d_%H')}",
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "period_label": period_label,
            "total_tasks_processed": len(unique_tasks),
            "tasks_by_status": dict(tasks_by_status),
            "unique_task_ids": list(unique_tasks),
            "task_summaries": task_summaries,
            "total_thoughts_processed": len(unique_thoughts),
            "thoughts_by_type": dict(thoughts_by_type),
            "avg_thoughts_per_task": avg_thoughts_per_task,
            "component_calls": dict(component_calls),
            "component_failures": dict(component_failures),
            "component_latency_ms": component_latency_stats,
            "dma_decisions": dict(dma_decisions),
            "guardrail_violations": dict(guardrail_violations),
            "handler_actions": dict(handler_actions),
            "avg_task_processing_time_ms": avg_task_time,
            "p50_task_processing_time_ms": p50_task_time,
            "p95_task_processing_time_ms": p95_task_time,
            "p99_task_processing_time_ms": p99_task_time,
            "total_processing_time_ms": sum(task_processing_times) if task_processing_times else 0.0,
            "total_errors": total_errors,
            "errors_by_component": dict(errors_by_component),
            "error_rate": error_rate,
            "max_trace_depth": max_trace_depth,
            "avg_trace_depth": avg_trace_depth,
            "source_correlation_count": len(trace_spans),
            "created_at": period_end.isoformat(),
            "updated_at": period_end.isoformat(),
        }

        # Create GraphNode
        summary_node = GraphNode(
            id=str(summary_data["id"]),
            type=NodeType.TRACE_SUMMARY,
            scope=GraphScope.LOCAL,
            attributes=summary_data,
            updated_by="tsdb_consolidation",
            updated_at=period_end,  # Use period end as timestamp
        )

        # Store summary
        if self._memory_bus:
            result = await self._memory_bus.memorize(node=summary_node)
            if result.status != MemoryOpStatus.OK:
                logger.error(f"Failed to store trace summary: {result.error}")
                return None
        else:
            logger.warning("No memory bus available - summary not stored")

        return summary_node

    def get_edges(
        self, summary_node: GraphNode, trace_spans: List[TraceSpanData]
    ) -> List[Tuple[GraphNode, GraphNode, str, JSONDict]]:
        """
        Get edges to create for trace summary.

        Returns edges from summary to:
        - Tasks with high latency
        - Components with errors
        """
        edges: List[Tuple[GraphNode, GraphNode, str, JSONDict]] = []

        # Find unique tasks
        tasks_with_errors = set()
        high_latency_tasks = set()

        for span in trace_spans:
            task_id = span.trace_id
            if task_id:
                # Check for errors
                if span.error:
                    tasks_with_errors.add(task_id)

                # Check for high latency (> 5 seconds)
                latency = span.latency_ms or span.duration_ms
                if latency and latency > 5000:
                    high_latency_tasks.add(task_id)

        # Create edges to problematic tasks (limit to 10 each)
        for i, task_id in enumerate(list(tasks_with_errors)[:10]):
            edge_attrs: JSONDict = {"task_id": task_id, "error_type": "trace_error"}
            edges.append((summary_node, summary_node, "ERROR_TASK", edge_attrs))

        for i, task_id in enumerate(list(high_latency_tasks)[:10]):
            edge_attrs_latency: JSONDict = {"task_id": task_id, "latency_category": "high"}
            edges.append((summary_node, summary_node, "HIGH_LATENCY_TASK", edge_attrs_latency))

        return edges
