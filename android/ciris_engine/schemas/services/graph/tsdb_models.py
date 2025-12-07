"""
Typed models for TSDB consolidation internals.

Provides typed schemas for tsdb_consolidation service.
Follows 'No Dicts' principle.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict


class SummaryAttributes(BaseModel):
    """Attributes for consolidated summary nodes."""

    period_start: datetime = Field(..., description="Start of consolidation period")
    period_end: datetime = Field(..., description="End of consolidation period")
    consolidation_level: str = Field(..., description="Level: basic, extensive, profound")

    # Metrics and statistics
    total_interactions: int = Field(default=0, description="Total service interactions")
    unique_services: int = Field(default=0, description="Unique services involved")
    total_tasks: int = Field(default=0, description="Total tasks processed")
    total_thoughts: int = Field(default=0, description="Total thoughts generated")

    # Key patterns and insights
    dominant_patterns: List[str] = Field(default_factory=list, description="Key behavior patterns")
    significant_events: List[str] = Field(default_factory=list, description="Notable events")

    # Compressed data
    compressed_metrics: Optional[Dict[str, float]] = Field(default=None, description="Compressed metric values")
    compressed_descriptions: Optional[List[str]] = Field(default=None, description="Compressed text summaries")

    # Multimedia placeholders (future)
    image_refs: List[str] = Field(default_factory=list, description="References to compressed images")
    video_refs: List[str] = Field(default_factory=list, description="References to video summaries")
    telemetry_refs: List[str] = Field(default_factory=list, description="References to telemetry data")

    # Dynamic data fields (for backward compatibility during migration)
    messages_by_channel: Optional[Dict[str, Union[int, JSONDict]]] = Field(
        default=None, description="Messages by channel - flexible for migration"
    )
    participants: Optional[Dict[str, JSONDict]] = Field(
        default=None, description="Participant data - flexible for migration"
    )

    model_config = ConfigDict(extra="allow")  # NOQA - Migration flexibility pattern


class CompressionResult(BaseModel):
    """Result of compression operation."""

    compressed_attributes: SummaryAttributes
    original_size: int = Field(..., description="Original size in bytes")
    compressed_size: int = Field(..., description="Compressed size in bytes")
    reduction_ratio: float = Field(..., description="Size reduction ratio (0-1)")
    compression_method: str = Field(default="text", description="Method used")


class ConsolidationMetadata(BaseModel):
    """Metadata for consolidation operations."""

    consolidation_id: str = Field(..., description="Unique consolidation ID")
    started_at: datetime = Field(..., description="When consolidation started")
    completed_at: Optional[datetime] = Field(None, description="When consolidation completed")
    source_count: int = Field(..., description="Number of source records")
    output_count: int = Field(..., description="Number of output records")
    compression_applied: bool = Field(default=False, description="Whether compression was applied")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")


class EdgeAttributes(BaseModel):
    """Attributes for graph edges in consolidation."""

    edge_type: str = Field(..., description="Type of relationship")
    weight: float = Field(default=1.0, description="Edge weight/strength")
    created_at: datetime = Field(..., description="When edge was created")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Edge metadata - typed values only"
    )

    model_config = ConfigDict(extra="forbid")


class NodeReference(BaseModel):
    """Reference to a graph node."""

    node_id: str = Field(..., description="Node identifier")
    node_type: str = Field(..., description="Type of node")
    collection: Optional[str] = Field(None, description="Collection name")
    attributes: Optional[SummaryAttributes] = Field(None, description="Node attributes if loaded")


class BatchProcessingContext(BaseModel):
    """Context for batch processing operations."""

    batch_id: str = Field(..., description="Batch identifier")
    batch_size: int = Field(..., description="Number of items in batch")
    current_index: int = Field(default=0, description="Current processing index")
    start_time: datetime = Field(..., description="Batch start time")
    end_time: Optional[datetime] = Field(None, description="Batch end time")
    processed_count: int = Field(default=0, description="Items processed")
    error_count: int = Field(default=0, description="Errors encountered")
    skip_count: int = Field(default=0, description="Items skipped")
