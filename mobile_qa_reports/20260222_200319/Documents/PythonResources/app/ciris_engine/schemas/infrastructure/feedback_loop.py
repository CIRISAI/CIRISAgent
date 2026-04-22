"""
Schemas for configuration feedback loop operations.

These replace all Dict[str, Any] usage in logic/infrastructure/sub_services/configuration_feedback_loop.py.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class PatternType(str, Enum):
    """Types of patterns we can detect."""

    TEMPORAL = "temporal"  # Time-based patterns
    FREQUENCY = "frequency"  # Usage frequency patterns
    PERFORMANCE = "performance"  # Performance optimization patterns
    ERROR = "error"  # Error/failure patterns
    USER_PREFERENCE = "user_preference"  # User interaction patterns


class PatternMetrics(BaseModel):
    """Metrics associated with a detected pattern."""

    occurrence_count: int = Field(0, description="Number of occurrences")
    average_value: float = Field(0.0, description="Average metric value")
    peak_value: float = Field(0.0, description="Peak metric value")
    time_range_hours: float = Field(24.0, description="Time range analyzed")
    data_points: int = Field(0, description="Number of data points")
    trend: str = Field("stable", description="Trend: increasing, decreasing, stable")
    metadata: JSONDict = Field(default_factory=dict, description="Additional metrics")


class DetectedPattern(BaseModel):
    """A pattern detected from metrics/telemetry."""

    pattern_type: PatternType = Field(..., description="Type of pattern")
    pattern_id: str = Field(..., description="Unique pattern identifier")
    description: str = Field(..., description="Human-readable description")
    evidence_nodes: List[str] = Field(default_factory=list, description="Supporting evidence node IDs")
    detected_at: datetime = Field(..., description="When pattern was detected")
    metrics: PatternMetrics = Field(..., description="Pattern metrics")


class AnalysisResult(BaseModel):
    """Result of feedback loop analysis."""

    status: str = Field(..., description="Status: completed, not_due, error")
    patterns_detected: int = Field(0, description="Number of patterns detected")
    insights_stored: int = Field(0, description="Number of insights stored for agent introspection")
    timestamp: datetime = Field(..., description="Analysis timestamp")
    next_analysis_in: Optional[float] = Field(None, description="Seconds until next analysis")
    error: Optional[str] = Field(None, description="Error message if failed")
