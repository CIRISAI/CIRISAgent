"""
Schemas for TSDB Consolidation Service.

Defines configuration and data structures for long-term telemetry consolidation.
"""

from typing import Optional

from pydantic import BaseModel, Field


class TSDBConsolidationConfig(BaseModel):
    """Configuration for TSDB consolidation service."""

    consolidation_interval_hours: int = Field(default=6, description="How often to run consolidation (hours)")
    raw_retention_hours: int = Field(default=24, description="How long to keep raw TSDB nodes before deletion (hours)")
    enabled: bool = Field(default=True, description="Whether consolidation is enabled")


class TSDBConsolidationStatus(BaseModel):
    """Status information for TSDB consolidation service."""

    running: bool = Field(..., description="Whether service is running")
    last_consolidation: Optional[str] = Field(None, description="ISO timestamp of last consolidation")
    next_consolidation: Optional[str] = Field(None, description="ISO timestamp of next scheduled consolidation")
    nodes_consolidated: int = Field(default=0, description="Total nodes consolidated")
    summaries_created: int = Field(default=0, description="Total summaries created")
