"""
Edge schemas for graph services.

Defines typed edge attributes to replace Dict[str, Any] usage.
"""

from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class BaseEdgeAttributes(BaseModel):
    """Base attributes for all edges."""

    context: Optional[str] = Field(None, description="Context or reason for the edge")
    created_by: Optional[str] = Field(None, description="Service or user that created the edge")
    created_at: Optional[str] = Field(None, description="ISO timestamp when edge was created")


class SummaryEdgeAttributes(BaseEdgeAttributes):
    """Attributes for edges from summaries to nodes."""

    period_label: Optional[str] = Field(None, description="Period label for the summary")
    node_count: Optional[int] = Field(None, description="Number of nodes summarized")
    aggregation_type: Optional[str] = Field(None, description="Type of aggregation performed")


class UserParticipationAttributes(BaseEdgeAttributes):
    """Attributes for user participation edges."""

    message_count: Optional[int] = Field(None, description="Number of messages from user")
    channels: Optional[List[str]] = Field(None, description="Channels user participated in")
    author_name: Optional[str] = Field(None, description="Display name of the author")


class TaskSummaryAttributes(BaseEdgeAttributes):
    """Attributes for task summary edges."""

    task_count: Optional[int] = Field(None, description="Number of tasks included")
    handlers_used: Optional[List[str]] = Field(None, description="Handlers that processed tasks")
    duration_ms: Optional[float] = Field(None, description="Total duration of tasks")


class TraceSummaryAttributes(BaseEdgeAttributes):
    """Attributes for trace summary edges."""

    span_count: Optional[int] = Field(None, description="Number of spans included")
    error_count: Optional[int] = Field(None, description="Number of error spans")
    services: Optional[List[str]] = Field(None, description="Services involved")


class CrossSummaryAttributes(BaseEdgeAttributes):
    """Attributes for edges between summaries."""

    relationship_type: str = Field(..., description="Type of relationship between summaries")
    shared_resources: Optional[Dict[str, float]] = Field(None, description="Shared resource usage")
    correlation_strength: Optional[float] = Field(None, description="Strength of correlation")


class GenericEdgeAttributes(BaseEdgeAttributes):
    """Generic edge attributes for flexible use cases."""

    data: Dict[str, Union[str, int, float, bool, List[Any]]] = Field(
        default_factory=dict, description="Additional edge data"
    )


# Type alias for edge attributes
EdgeAttributes = Union[
    SummaryEdgeAttributes,
    UserParticipationAttributes,
    TaskSummaryAttributes,
    TraceSummaryAttributes,
    CrossSummaryAttributes,
    GenericEdgeAttributes,
]


__all__ = [
    "BaseEdgeAttributes",
    "SummaryEdgeAttributes",
    "UserParticipationAttributes",
    "TaskSummaryAttributes",
    "TraceSummaryAttributes",
    "CrossSummaryAttributes",
    "GenericEdgeAttributes",
    "EdgeAttributes",
]
