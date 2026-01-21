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


def _get_tag_value(tags: Any, key: str, default: str = "unknown") -> str:
    """Extract a string value from tags.additional_tags safely."""
    if not tags or not hasattr(tags, "additional_tags"):
        return default
    value = tags.additional_tags.get(key, default)
    return str(value) if value else default


def _get_tag_bool(tags: Any, key: str, true_value: str = "true") -> bool:
    """Check if a tag value equals a specific string (default 'true')."""
    if not tags or not hasattr(tags, "additional_tags"):
        return False
    return bool(tags.additional_tags.get(key) == true_value)


def _initialize_task_summary(task_id: str, timestamp: Optional[datetime]) -> JSONDict:
    """Create initial task summary structure."""
    timestamp_str = timestamp.isoformat() if timestamp else None
    return {
        "task_id": task_id,
        "status": "processing",
        "thoughts": [],
        "start_time": timestamp_str,
        "end_time": timestamp_str,
        "handlers_selected": [],
        "trace_ids": [],  # Use list for JSON compatibility; converted to set during processing
    }


def _update_task_trace_id(task_summaries: JSONDict, task_id: str, trace_id: str, timestamp: Optional[datetime]) -> None:
    """Update task summary with trace ID and timestamp."""
    task_summary = task_summaries.get(task_id)
    if not isinstance(task_summary, dict):
        return

    trace_ids = task_summary.get("trace_ids")
    if isinstance(trace_ids, list) and trace_id not in trace_ids:
        trace_ids.append(trace_id)
    task_summary["end_time"] = timestamp.isoformat() if timestamp else None


def _process_handler_for_thought(
    task_summaries: JSONDict,
    task_id: str,
    thought_id: str,
    action_type: str,
    timestamp: Optional[datetime],
    handler_actions: Dict[str, int],
) -> None:
    """Process handler component for a thought."""
    handler_actions[action_type] += 1

    task_summary = task_summaries.get(task_id)
    if not isinstance(task_summary, dict):
        return

    handlers_sel = task_summary.get("handlers_selected")
    if isinstance(handlers_sel, list):
        handlers_sel.append(action_type)

    thoughts_list = task_summary.get("thoughts")
    if isinstance(thoughts_list, list):
        thoughts_list.append({
            "thought_id": thought_id,
            "handler": action_type,
            "timestamp": timestamp.isoformat() if timestamp else None,
        })


def _update_task_status(task_summaries: JSONDict, task_id: str, status: str, tasks_by_status: Dict[str, int]) -> None:
    """Update task status tracking."""
    tasks_by_status[status] += 1
    task_summary = task_summaries.get(task_id)
    if isinstance(task_summary, dict):
        task_summary["status"] = status


def _process_span_errors(
    span: TraceSpanData,
    component_type: str,
    component_failures: Dict[str, int],
    errors_by_component: Dict[str, int],
) -> int:
    """Process error information from span. Returns 1 if error found, 0 otherwise."""
    if not span.error:
        return 0
    component_failures[component_type] += 1
    errors_by_component[component_type] += 1
    return 1


def _process_span_latency(span: TraceSpanData, component_type: str, component_latencies: Dict[str, List[float]]) -> None:
    """Track latency from span."""
    if span.latency_ms is not None:
        component_latencies[component_type].append(span.latency_ms)
    elif span.duration_ms > 0:
        component_latencies[component_type].append(span.duration_ms)


def _process_guardrail_span(span: TraceSpanData, guardrail_violations: Dict[str, int]) -> None:
    """Process guardrail component span."""
    guardrail_type = _get_tag_value(span.tags, "guardrail_type")
    violation = _get_tag_bool(span.tags, "violation")
    if violation:
        guardrail_violations[guardrail_type] += 1


def _process_dma_span(span: TraceSpanData, dma_decisions: Dict[str, int]) -> None:
    """Process DMA component span."""
    dma_type = _get_tag_value(span.tags, "dma_type")
    dma_decisions[dma_type] += 1


def _calculate_latency_stats(component_latencies: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
    """Calculate latency statistics for each component."""
    stats = {}
    for component, latencies in component_latencies.items():
        if not latencies:
            continue
        sorted_latencies = sorted(latencies)
        n = len(sorted_latencies)
        stats[component] = {
            "avg": sum(latencies) / n,
            "p50": sorted_latencies[n // 2],
            "p95": sorted_latencies[int(n * 0.95)],
            "p99": sorted_latencies[int(n * 0.99)],
        }
    return stats


def _calculate_percentiles(values: List[float]) -> Tuple[float, float, float, float]:
    """Calculate avg, p50, p95, p99 from a list of values. Returns (0,0,0,0) if empty."""
    if not values:
        return 0.0, 0.0, 0.0, 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    return (
        sum(values) / n,
        sorted_vals[n // 2],
        sorted_vals[int(n * 0.95)],
        sorted_vals[int(n * 0.99)],
    )


def _finalize_task_summaries(task_summaries: JSONDict) -> List[float]:
    """Finalize task summaries and return processing times.

    Calculates duration_ms for each task and converts sets to lists.
    """
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

    return task_processing_times


def _calculate_trace_depth_metrics(task_summaries: JSONDict) -> Tuple[int, float]:
    """Calculate max and average trace depth from task summaries."""
    trace_depths = []
    for s in task_summaries.values():
        if isinstance(s, dict):
            thoughts = get_list(s, "thoughts", [])
            trace_depths.append(len(thoughts))
    max_depth = max(trace_depths) if trace_depths else 0
    avg_depth = sum(trace_depths) / len(trace_depths) if trace_depths else 0.0
    return max_depth, avg_depth


class TraceConsolidator:
    """Consolidates trace span data into summaries."""

    def __init__(self, memory_bus: Optional[MemoryBus] = None):
        """
        Initialize trace consolidator.

        Args:
            memory_bus: Memory bus for storing results
        """
        self._memory_bus = memory_bus

    def _process_task_id(
        self,
        span: TraceSpanData,
        task_id: str,
        task_summaries: JSONDict,
        unique_tasks: Set[str],
    ) -> None:
        """Process task ID from span, initializing or updating task summary."""
        unique_tasks.add(task_id)

        if task_id not in task_summaries:
            task_summaries[task_id] = _initialize_task_summary(task_id, span.timestamp)

        _update_task_trace_id(task_summaries, task_id, span.trace_id, span.timestamp)

    def _process_thought_id(
        self,
        span: TraceSpanData,
        thought_id: str,
        task_id: Optional[str],
        component_type: str,
        task_summaries: JSONDict,
        unique_thoughts: Set[str],
        thoughts_by_type: Dict[str, int],
        handler_actions: Dict[str, int],
    ) -> None:
        """Process thought ID from span."""
        unique_thoughts.add(thought_id)

        # Track thought type
        thought_type = _get_tag_value(span.tags, "thought_type")
        thoughts_by_type[thought_type] += 1

        # Track handler selection
        if component_type == "handler" and task_id:
            action_type = _get_tag_value(span.tags, "action_type")
            _process_handler_for_thought(
                task_summaries, task_id, thought_id, action_type, span.timestamp, handler_actions
            )

    def _process_task_completion(
        self,
        span: TraceSpanData,
        task_id: str,
        task_summaries: JSONDict,
        tasks_by_status: Dict[str, int],
    ) -> None:
        """Check and process task completion status."""
        tags = span.tags
        if not tags or not hasattr(tags, "additional_tags"):
            return

        task_status = tags.additional_tags.get("task_status")
        if not task_status:
            return

        status = str(task_status) if isinstance(task_status, (str, int, float)) else "unknown"
        _update_task_status(task_summaries, task_id, status, tasks_by_status)

    def _process_single_span(
        self,
        span: TraceSpanData,
        task_summaries: JSONDict,
        unique_tasks: Set[str],
        unique_thoughts: Set[str],
        tasks_by_status: Dict[str, int],
        thoughts_by_type: Dict[str, int],
        component_calls: Dict[str, int],
        component_failures: Dict[str, int],
        component_latencies: Dict[str, List[float]],
        handler_actions: Dict[str, int],
        errors_by_component: Dict[str, int],
        guardrail_violations: Dict[str, int],
        dma_decisions: Dict[str, int],
    ) -> int:
        """Process a single trace span. Returns error count (0 or 1)."""
        task_id = span.task_id
        thought_id = span.thought_id
        component_type = span.component_type or "unknown"

        # Process task ID
        if task_id:
            self._process_task_id(span, task_id, task_summaries, unique_tasks)

        # Process thought ID
        if thought_id:
            self._process_thought_id(
                span, thought_id, task_id, component_type,
                task_summaries, unique_thoughts, thoughts_by_type, handler_actions
            )

        # Track task completion
        if task_id:
            self._process_task_completion(span, task_id, task_summaries, tasks_by_status)

        # Component tracking
        component_calls[component_type] += 1

        # Process errors
        error_count = _process_span_errors(span, component_type, component_failures, errors_by_component)

        # Track latency
        _process_span_latency(span, component_type, component_latencies)

        # Component-specific processing
        if component_type == "guardrail":
            _process_guardrail_span(span, guardrail_violations)
        elif component_type == "dma":
            _process_dma_span(span, dma_decisions)

        return error_count

    def _build_summary_data(
        self,
        period_start: datetime,
        period_end: datetime,
        period_label: str,
        unique_tasks: Set[str],
        unique_thoughts: Set[str],
        tasks_by_status: Dict[str, int],
        thoughts_by_type: Dict[str, int],
        component_calls: Dict[str, int],
        component_failures: Dict[str, int],
        component_latency_stats: Dict[str, Dict[str, float]],
        handler_actions: Dict[str, int],
        errors_by_component: Dict[str, int],
        total_errors: int,
        guardrail_violations: Dict[str, int],
        dma_decisions: Dict[str, int],
        task_summaries: JSONDict,
        task_processing_times: List[float],
        max_trace_depth: int,
        avg_trace_depth: float,
        source_count: int,
    ) -> JSONDict:
        """Build the summary data dictionary."""
        avg_task_time, p50_task_time, p95_task_time, p99_task_time = _calculate_percentiles(task_processing_times)

        total_calls = sum(component_calls.values())
        error_rate = total_errors / total_calls if total_calls > 0 else 0.0
        avg_thoughts_per_task = len(unique_thoughts) / len(unique_tasks) if unique_tasks else 0.0

        return {
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
            "source_correlation_count": source_count,
            "created_at": period_end.isoformat(),
            "updated_at": period_end.isoformat(),
        }

    async def _store_summary(self, summary_node: GraphNode) -> bool:
        """Store summary node via memory bus. Returns True on success."""
        if not self._memory_bus:
            logger.warning("No memory bus available - summary not stored")
            return True  # Not a failure, just no storage

        result = await self._memory_bus.memorize(node=summary_node)
        if result.status != MemoryOpStatus.OK:
            logger.error(f"Failed to store trace summary: {result.error}")
            return False
        return True

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
        task_summaries: JSONDict = {}
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

        # Process all spans
        for span in trace_spans:
            total_errors += self._process_single_span(
                span,
                task_summaries,
                unique_tasks,
                unique_thoughts,
                tasks_by_status,
                thoughts_by_type,
                component_calls,
                component_failures,
                component_latencies,
                handler_actions,
                errors_by_component,
                guardrail_violations,
                dma_decisions,
            )

        # Calculate statistics
        component_latency_stats = _calculate_latency_stats(component_latencies)
        task_processing_times = _finalize_task_summaries(task_summaries)
        max_trace_depth, avg_trace_depth = _calculate_trace_depth_metrics(task_summaries)

        # Build summary data
        summary_data = self._build_summary_data(
            period_start,
            period_end,
            period_label,
            unique_tasks,
            unique_thoughts,
            tasks_by_status,
            thoughts_by_type,
            component_calls,
            component_failures,
            component_latency_stats,
            handler_actions,
            errors_by_component,
            total_errors,
            guardrail_violations,
            dma_decisions,
            task_summaries,
            task_processing_times,
            max_trace_depth,
            avg_trace_depth,
            len(trace_spans),
        )

        # Create GraphNode
        summary_node = GraphNode(
            id=str(summary_data["id"]),
            type=NodeType.TRACE_SUMMARY,
            scope=GraphScope.LOCAL,
            attributes=summary_data,
            updated_by="tsdb_consolidation",
            updated_at=period_end,
        )

        # Store summary
        if not await self._store_summary(summary_node):
            return None

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
