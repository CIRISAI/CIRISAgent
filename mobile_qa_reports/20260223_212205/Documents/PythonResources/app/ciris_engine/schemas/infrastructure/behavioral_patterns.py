"""
Schemas for identity variance and behavioral pattern tracking.

Provides typed schemas in identity_variance_monitor.py and configuration_feedback_loop.py.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class BehavioralPattern(BaseModel):
    """A detected behavioral pattern from agent history."""

    pattern_type: str = Field(..., description="Type of pattern: action_frequency, response_style, etc.")
    frequency: float = Field(..., description="How often this pattern occurs (0.0-1.0)")
    evidence: List[str] = Field(default_factory=list, description="Evidence supporting this pattern")
    first_seen: datetime = Field(..., description="When pattern was first observed")
    last_seen: datetime = Field(..., description="Most recent occurrence")

    model_config = ConfigDict()

    @field_serializer("first_seen", "last_seen")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()


class ActionFrequency(BaseModel):
    """Tracks frequency of specific actions."""

    action: str = Field(..., description="Action type being tracked")
    count: int = Field(0, description="Number of occurrences")
    evidence: List[str] = Field(default_factory=list, description="Recent examples")
    last_seen: datetime = Field(..., description="Most recent occurrence")
    daily_average: Optional[float] = Field(None, description="Average occurrences per day")

    model_config = ConfigDict()

    @field_serializer("last_seen")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()


class EthicalBoundary(BaseModel):
    """Represents an ethical boundary configuration."""

    boundary_type: str = Field(..., description="Type of boundary: harm_prevention, autonomy, etc.")
    threshold: float = Field(..., description="Configured threshold value")
    current_value: float = Field(..., description="Current measured value")
    is_violated: bool = Field(False, description="Whether boundary is currently violated")
    violation_count: int = Field(0, description="Number of violations detected")
    last_violation: Optional[datetime] = Field(None, description="Most recent violation")

    model_config = ConfigDict()

    @field_serializer("last_violation")
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None


class IdentityMetric(BaseModel):
    """A single identity variance metric."""

    metric_name: str = Field(..., description="Name of the metric")
    baseline_value: float = Field(..., description="Expected baseline value")
    current_value: float = Field(..., description="Current measured value")
    variance: float = Field(..., description="Variance from baseline (percentage)")
    is_within_bounds: bool = Field(..., description="Whether variance is acceptable")
    timestamp: datetime = Field(..., description="When measurement was taken")

    model_config = ConfigDict()

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()


class IdentityVarianceReport(BaseModel):
    """Complete identity variance analysis report."""

    timestamp: datetime = Field(..., description="Report generation time")
    overall_variance: float = Field(..., description="Overall variance percentage")
    is_stable: bool = Field(..., description="Whether identity is stable")
    metrics: List[IdentityMetric] = Field(default_factory=list, description="Individual metrics")
    behavioral_patterns: List[BehavioralPattern] = Field(default_factory=list, description="Detected patterns")
    ethical_boundaries: List[EthicalBoundary] = Field(default_factory=list, description="Ethical boundary status")
    recommendations: List[str] = Field(default_factory=list, description="Recommended adjustments")

    model_config = ConfigDict()

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()


class TemporalPattern(BaseModel):
    """A time-based pattern detected in agent behavior."""

    pattern_id: str = Field(..., description="Unique pattern identifier")
    pattern_type: str = Field(..., description="Type: daily, weekly, hourly")
    time_window: str = Field(..., description="Time window (e.g., '09:00-17:00', 'monday-friday')")
    activity_description: str = Field(..., description="What happens during this time")
    occurrence_count: int = Field(0, description="Times this pattern occurred")
    first_detected: datetime = Field(..., description="When pattern was first detected")
    last_observed: datetime = Field(..., description="Most recent occurrence")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Associated metrics")

    model_config = ConfigDict()

    @field_serializer("first_detected", "last_observed")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()


class FeedbackLoopAnalysis(BaseModel):
    """Analysis from configuration feedback loop."""

    timestamp: datetime = Field(..., description="Analysis timestamp")
    dominant_actions: Dict[str, ActionFrequency] = Field(default_factory=dict, description="Most frequent actions")
    underused_capabilities: List[str] = Field(default_factory=list, description="Capabilities not being used")
    suggested_adjustments: List[str] = Field(default_factory=list, description="Recommended config changes")
    reliability_level: float = Field(0.5, description="Reliability of recommendations (0.0-1.0)")

    model_config = ConfigDict()

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()
