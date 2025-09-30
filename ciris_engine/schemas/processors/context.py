"""
Context models for processor operations.

Provides typed models for processor contexts instead of Dict[str, Any].
"""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.models import Thought


class ProcessorContext(BaseModel):
    """Context passed to processor.process_thought_item."""

    origin: str = Field(..., description="Origin of the processing request")
    prefetched_thought: Optional[Thought] = Field(None, description="Pre-fetched thought object")
    batch_context: Optional[Any] = Field(None, description="Batch processing context")

    model_config = ConfigDict(extra="allow")


class BatchProcessingContext(BaseModel):
    """Context for batch processing operations."""

    batch_id: str = Field(..., description="Unique batch identifier")
    batch_size: int = Field(..., description="Number of items in batch")
    current_index: int = Field(0, description="Current item index in batch")
    total_processed: int = Field(0, description="Total items processed so far")

    model_config = ConfigDict(extra="forbid")


__all__ = ["ProcessorContext", "BatchProcessingContext"]
