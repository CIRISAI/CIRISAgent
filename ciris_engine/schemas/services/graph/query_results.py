"""
Query result schemas for TSDB consolidation service.

These schemas provide type-safe alternatives to Dict[str, Any] returns.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.services.graph.consolidation import (
    MetricCorrelationData,
    ServiceInteractionData,
    TaskCorrelationData,
    TraceSpanData,
)
from ciris_engine.schemas.services.graph_core import GraphNode


class ServiceCorrelationQueryResult(BaseModel):
    """Result of querying service correlations."""

    service_interactions: List[ServiceInteractionData] = Field(
        default_factory=list, description="Service interaction correlations"
    )
    metric_correlations: List[MetricCorrelationData] = Field(default_factory=list, description="Metric correlations")
    trace_spans: List[TraceSpanData] = Field(default_factory=list, description="Trace span correlations")
    task_correlations: List[TaskCorrelationData] = Field(default_factory=list, description="Task correlations")

    def to_dict_by_type(
        self,
    ) -> Dict[
        str,
        Union[
            List[ServiceInteractionData], List[MetricCorrelationData], List[TraceSpanData], List[TaskCorrelationData]
        ],
    ]:
        """Convert to dictionary keyed by correlation type."""
        return {
            "service_interactions": self.service_interactions,
            "metric_correlations": self.metric_correlations,
            "trace_spans": self.trace_spans,
            "task_correlations": self.task_correlations,
        }


class TSDBNodeQueryResult(BaseModel):
    """Result of querying TSDB nodes."""

    nodes: List[GraphNode] = Field(default_factory=list, description="TSDB data nodes")
    period_start: datetime = Field(..., description="Query period start")
    period_end: datetime = Field(..., description="Query period end")
    count: int = Field(0, description="Number of nodes found")

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self.count = len(self.nodes)


class EdgeQueryResult(BaseModel):
    """Result of querying edges between nodes."""

    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    edge_type: str = Field(..., description="Type of edge")
    properties: Dict[str, str] = Field(default_factory=dict, description="Edge properties")
    created_at: Optional[datetime] = Field(None, description="Edge creation time")


class ConsolidationSummary(BaseModel):
    """Summary of a consolidation operation."""

    consolidation_id: str = Field(..., description="Unique consolidation ID")
    period_start: datetime = Field(..., description="Consolidation period start")
    period_end: datetime = Field(..., description="Consolidation period end")
    nodes_created: int = Field(0, description="Number of nodes created")
    edges_created: int = Field(0, description="Number of edges created")
    correlations_processed: int = Field(0, description="Number of correlations processed")
    success: bool = Field(True, description="Whether consolidation succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    execution_time_ms: float = Field(0.0, description="Execution time in milliseconds")
