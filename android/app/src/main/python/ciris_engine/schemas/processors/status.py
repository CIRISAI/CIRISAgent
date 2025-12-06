"""
Schemas for processor status operations.

These replace all Dict[str, Any] usage in processor status methods.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.processors.base import ProcessorMetrics
from ciris_engine.schemas.processors.solitude import ReflectionData


class SolitudeStats(BaseModel):
    """Statistics specific to solitude processor."""

    reflection_data: ReflectionData = Field(..., description="Reflection activity data")
    critical_threshold: int = Field(..., description="Critical priority threshold")
    total_rounds: int = Field(0, description="Total rounds completed")
    cleanup_performed: bool = Field(False, description="Whether cleanup was performed")


class ProcessorInfo(BaseModel):
    """General processor status information."""

    processor_type: str = Field(..., description="Type of processor")
    supported_states: List[str] = Field(..., description="States this processor supports")
    is_running: bool = Field(False, description="Whether processor is running")
    metrics: ProcessorMetrics = Field(..., description="Processor metrics")

    # Processor-specific stats
    solitude_stats: Optional[SolitudeStats] = Field(None, description="Solitude-specific stats")
    critical_threshold: Optional[int] = Field(None, description="Critical threshold if applicable")
