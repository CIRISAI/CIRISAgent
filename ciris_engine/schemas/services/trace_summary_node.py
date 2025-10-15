"""
Trace summary nodes for consolidating task/thought processing traces.

These nodes summarize TRACE_SPAN correlations showing how tasks and thoughts
flowed through the various processing components.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Set, Union

from pydantic import Field

from ciris_engine.logic.utils.jsondict_helpers import get_list
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.graph_typed_nodes import TypedGraphNode, register_node_type
from ciris_engine.schemas.types import JSONDict


@register_node_type("TRACE_SUMMARY")
class TraceSummaryNode(TypedGraphNode):
    """
    Consolidated trace summary for a time period.

    Summarizes how tasks and thoughts were processed through various components
    like processors, DMAs, guardrails, and handlers.
    """

    # Period information
    period_start: datetime = Field(..., description="Start of the consolidation period")
    period_end: datetime = Field(..., description="End of the consolidation period")
    period_label: str = Field(..., description="Human-readable period label")

    # Task-level metrics
    total_tasks_processed: int = Field(0, description="Total tasks processed")
    tasks_by_status: Dict[str, int] = Field(default_factory=dict, description="Task count by final status")
    unique_task_ids: Set[str] = Field(default_factory=set, description="Set of unique task IDs processed")
    task_summaries: Dict[str, JSONDict] = Field(
        default_factory=dict, description="Elegant task summaries showing handler selections per thought"
    )

    # Thought-level metrics
    total_thoughts_processed: int = Field(0, description="Total thoughts processed")
    thoughts_by_type: Dict[str, int] = Field(default_factory=dict, description="Thought count by type")
    avg_thoughts_per_task: float = Field(0.0, description="Average thoughts per task")

    # Component interaction metrics
    component_calls: Dict[str, int] = Field(
        default_factory=dict, description="Calls to each component type (processor, dma, guardrail, handler)"
    )
    component_failures: Dict[str, int] = Field(default_factory=dict, description="Failures by component type")
    component_latency_ms: Dict[str, Dict[str, float]] = Field(
        default_factory=dict, description="Latency stats by component: {component: {avg, p95, p99}}"
    )

    # Processing patterns
    dma_decisions: Dict[str, int] = Field(default_factory=dict, description="Count of decisions by DMA type")
    guardrail_violations: Dict[str, int] = Field(
        default_factory=dict, description="Count of violations by guardrail type"
    )
    handler_actions: Dict[str, int] = Field(default_factory=dict, description="Count of actions by handler type")

    # Performance summary
    avg_task_processing_time_ms: float = Field(0.0, description="Average task processing time")
    p95_task_processing_time_ms: float = Field(0.0, description="95th percentile task time")
    p99_task_processing_time_ms: float = Field(0.0, description="99th percentile task time")
    total_processing_time_ms: float = Field(0.0, description="Total processing time")

    # Error tracking
    total_errors: int = Field(0, description="Total errors across all components")
    errors_by_component: Dict[str, int] = Field(default_factory=dict, description="Error count by component")
    error_rate: float = Field(0.0, description="Overall error rate (0-1)")

    # Trace depth metrics
    max_trace_depth: int = Field(0, description="Maximum trace depth observed")
    avg_trace_depth: float = Field(0.0, description="Average trace depth")

    # Summary metadata
    source_correlation_count: int = Field(0, description="Number of TRACE_SPAN correlations")
    consolidation_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When this summary was created"
    )

    # Required TypedGraphNode fields
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(default="TSDBConsolidationService")
    updated_by: str = Field(default="TSDBConsolidationService")

    # Graph node type
    type: NodeType = Field(default=NodeType.TSDB_SUMMARY)
    scope: GraphScope = Field(default=GraphScope.LOCAL)
    id: str = Field(..., description="Node ID")
    version: int = Field(default=1)
    attributes: JSONDict = Field(default_factory=dict, description="Node attributes")

    def to_graph_node(self) -> GraphNode:
        """Convert to GraphNode for storage."""
        extra_fields = {
            # Period info
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "period_label": self.period_label,
            # Task metrics
            "total_tasks_processed": self.total_tasks_processed,
            "tasks_by_status": self.tasks_by_status,
            "unique_task_ids": list(self.unique_task_ids),  # Convert set to list
            "task_summaries": self.task_summaries,
            # Thought metrics
            "total_thoughts_processed": self.total_thoughts_processed,
            "thoughts_by_type": self.thoughts_by_type,
            "avg_thoughts_per_task": self.avg_thoughts_per_task,
            # Component metrics
            "component_calls": self.component_calls,
            "component_failures": self.component_failures,
            "component_latency_ms": self.component_latency_ms,
            # Processing patterns
            "dma_decisions": self.dma_decisions,
            "guardrail_violations": self.guardrail_violations,
            "handler_actions": self.handler_actions,
            # Performance
            "avg_task_processing_time_ms": self.avg_task_processing_time_ms,
            "p95_task_processing_time_ms": self.p95_task_processing_time_ms,
            "p99_task_processing_time_ms": self.p99_task_processing_time_ms,
            "total_processing_time_ms": self.total_processing_time_ms,
            # Errors
            "total_errors": self.total_errors,
            "errors_by_component": self.errors_by_component,
            "error_rate": self.error_rate,
            # Trace depth
            "max_trace_depth": self.max_trace_depth,
            "avg_trace_depth": self.avg_trace_depth,
            # Metadata
            "source_correlation_count": self.source_correlation_count,
            "consolidation_timestamp": self.consolidation_timestamp.isoformat(),
            # Type hint
            "node_class": "TraceSummaryNode",
        }

        return GraphNode(
            id=self.id,
            type=self.type,
            scope=self.scope,
            attributes=extra_fields,
            version=self.version,
            updated_by=self.updated_by or "TSDBConsolidationService",
            updated_at=self.updated_at or self.consolidation_timestamp,
        )

    @classmethod
    def from_graph_node(cls, node: GraphNode) -> "TraceSummaryNode":
        """Reconstruct from GraphNode."""
        attrs = node.attributes if isinstance(node.attributes, dict) else {}

        return cls(
            # Base fields from GraphNode
            id=node.id,
            type=node.type,
            scope=node.scope,
            version=node.version,
            updated_by=node.updated_by,
            updated_at=node.updated_at,
            # Period info
            period_start=cls._deserialize_datetime(attrs.get("period_start")),
            period_end=cls._deserialize_datetime(attrs.get("period_end")),
            period_label=attrs.get("period_label", ""),
            # Task metrics
            total_tasks_processed=attrs.get("total_tasks_processed", 0),
            tasks_by_status=attrs.get("tasks_by_status", {}),
            unique_task_ids=set(get_list(attrs, "unique_task_ids", [])),  # Convert list to set - type-safe
            task_summaries=attrs.get("task_summaries", {}),
            # Thought metrics
            total_thoughts_processed=attrs.get("total_thoughts_processed", 0),
            thoughts_by_type=attrs.get("thoughts_by_type", {}),
            avg_thoughts_per_task=attrs.get("avg_thoughts_per_task", 0.0),
            # Component metrics
            component_calls=attrs.get("component_calls", {}),
            component_failures=attrs.get("component_failures", {}),
            component_latency_ms=attrs.get("component_latency_ms", {}),
            # Processing patterns
            dma_decisions=attrs.get("dma_decisions", {}),
            guardrail_violations=attrs.get("guardrail_violations", {}),
            handler_actions=attrs.get("handler_actions", {}),
            # Performance
            avg_task_processing_time_ms=attrs.get("avg_task_processing_time_ms", 0.0),
            p95_task_processing_time_ms=attrs.get("p95_task_processing_time_ms", 0.0),
            p99_task_processing_time_ms=attrs.get("p99_task_processing_time_ms", 0.0),
            total_processing_time_ms=attrs.get("total_processing_time_ms", 0.0),
            # Errors
            total_errors=attrs.get("total_errors", 0),
            errors_by_component=attrs.get("errors_by_component", {}),
            error_rate=attrs.get("error_rate", 0.0),
            # Trace depth
            max_trace_depth=attrs.get("max_trace_depth", 0),
            avg_trace_depth=attrs.get("avg_trace_depth", 0.0),
            # Metadata
            source_correlation_count=attrs.get("source_correlation_count", 0),
            consolidation_timestamp=cls._deserialize_datetime(attrs.get("consolidation_timestamp"))
            or datetime.now(timezone.utc),
        )
