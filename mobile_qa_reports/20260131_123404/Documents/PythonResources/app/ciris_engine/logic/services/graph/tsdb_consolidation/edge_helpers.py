"""
Helper functions for creating typed edge attributes.

Centralizes edge attribute creation to ensure type safety.
"""

from typing import Any, Dict, List, Optional

from ciris_engine.schemas.services.graph.edges import (
    CrossSummaryAttributes,
    EdgeAttributes,
    GenericEdgeAttributes,
    SummaryEdgeAttributes,
    TaskSummaryAttributes,
    TraceSummaryAttributes,
)
from ciris_engine.schemas.types import JSONDict


def create_summary_edge_attributes(
    period_label: Optional[str] = None,
    node_count: Optional[int] = None,
    aggregation_type: Optional[str] = None,
    context: Optional[str] = None,
) -> EdgeAttributes:
    """Create attributes for summary edges."""
    return SummaryEdgeAttributes(
        context=context or "Summary edge created during consolidation",
        created_by="tsdb_consolidation",
        period_label=period_label,
        node_count=node_count,
        aggregation_type=aggregation_type,
    )


def create_task_summary_attributes(
    task_count: int,
    handlers_used: Optional[List[str]] = None,
    duration_ms: Optional[float] = None,
    context: Optional[str] = None,
) -> EdgeAttributes:
    """Create attributes for task summary edges."""
    return TaskSummaryAttributes(
        context=context or "Task summary edge",
        created_by="tsdb_consolidation",
        task_count=task_count,
        handlers_used=handlers_used or [],
        duration_ms=duration_ms,
    )


def create_trace_summary_attributes(
    span_count: int, error_count: int = 0, services: Optional[List[str]] = None, context: Optional[str] = None
) -> EdgeAttributes:
    """Create attributes for trace summary edges."""
    return TraceSummaryAttributes(
        context=context or "Trace summary edge",
        created_by="tsdb_consolidation",
        span_count=span_count,
        error_count=error_count,
        services=services or [],
    )


def create_cross_summary_attributes(
    relationship_type: str,
    shared_resources: Optional[Dict[str, float]] = None,
    correlation_strength: Optional[float] = None,
    context: Optional[str] = None,
) -> EdgeAttributes:
    """Create attributes for cross-summary edges."""
    return CrossSummaryAttributes(
        context=context or f"Cross-summary {relationship_type} edge",
        created_by="tsdb_consolidation",
        relationship_type=relationship_type,
        shared_resources=shared_resources,
        correlation_strength=correlation_strength,
    )


def create_generic_edge_attributes(data: Optional[JSONDict] = None, context: Optional[str] = None) -> EdgeAttributes:
    """Create generic edge attributes for flexible use cases."""
    return GenericEdgeAttributes(context=context or "Generic edge", created_by="tsdb_consolidation", data=data or {})


__all__ = [
    "create_summary_edge_attributes",
    "create_task_summary_attributes",
    "create_trace_summary_attributes",
    "create_cross_summary_attributes",
    "create_generic_edge_attributes",
]
