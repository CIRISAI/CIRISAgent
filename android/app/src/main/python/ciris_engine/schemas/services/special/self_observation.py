"""
Self-observation service schemas.

Provides typed schemas for self-observation operations.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import JSONValue


class ObservationState(str, Enum):
    """Current state of the self-observation system."""

    LEARNING = "learning"  # Gathering data, no changes yet
    PROPOSING = "proposing"  # Actively proposing observations
    ADAPTING = "adapting"  # Applying approved changes
    STABILIZING = "stabilizing"  # Waiting for changes to settle
    REVIEWING = "reviewing"  # Under WA review for variance


class ProcessSnapshotResult(BaseModel):
    """Result of processing a system snapshot for observation."""

    patterns_detected: int = Field(0, description="Number of patterns detected")
    proposals_generated: int = Field(0, description="Number of proposals generated")
    changes_applied: int = Field(0, description="Number of changes applied")
    variance_percent: float = Field(0.0, description="Current variance from baseline")
    requires_review: bool = Field(False, description="Whether WA review is required")
    error: Optional[str] = Field(None, description="Error message if processing failed")


class ObservationCycleResult(BaseModel):
    """Result of running an observation cycle."""

    cycle_id: str = Field(..., description="Unique cycle identifier")
    state: ObservationState = Field(..., description="Current observation state")
    started_at: datetime = Field(..., description="When cycle started")
    completed_at: Optional[datetime] = Field(None, description="When cycle completed")

    # Pattern detection
    patterns_detected: int = Field(0, description="Number of patterns found")
    pattern_types: List[str] = Field(default_factory=list, description="Types of patterns")

    # Proposals
    proposals_generated: int = Field(0, description="Number of proposals created")
    proposals_approved: int = Field(0, description="Number of proposals approved")
    proposals_rejected: int = Field(0, description="Number of proposals rejected")

    # Changes
    changes_applied: int = Field(0, description="Number of changes applied")
    rollbacks_performed: int = Field(0, description="Number of rollbacks")

    # Variance
    variance_before: float = Field(0.0, description="Variance before cycle")
    variance_after: float = Field(0.0, description="Variance after cycle")

    # Outcome
    success: bool = Field(True, description="Whether cycle succeeded")
    requires_review: bool = Field(False, description="Whether WA review needed")
    error: Optional[str] = Field(None, description="Error if cycle failed")


class CycleEventData(BaseModel):
    """Data for observation cycle events."""

    event_type: str = Field(..., description="Type of event")
    cycle_id: str = Field(..., description="Associated cycle ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Event-specific data
    patterns: Optional[List[str]] = Field(None, description="Patterns for detection events")
    proposals: Optional[List[str]] = Field(None, description="Proposals for proposal events")
    changes: Optional[List[str]] = Field(None, description="Changes for change events")
    variance: Optional[float] = Field(None, description="Variance for variance events")

    # Additional context
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional event metadata"
    )


class ObservationStatus(BaseModel):
    """Current status of the observation system."""

    is_active: bool = Field(..., description="Whether observation is active")
    current_state: ObservationState = Field(..., description="Current state")
    cycles_completed: int = Field(..., description="Total cycles completed")
    last_cycle_at: Optional[datetime] = Field(None, description="Last cycle time")

    # Current metrics
    current_variance: float = Field(0.0, description="Current variance from baseline")
    patterns_in_buffer: int = Field(0, description="Patterns awaiting processing")
    pending_proposals: int = Field(0, description="Proposals awaiting approval")

    # Performance
    average_cycle_duration_seconds: float = Field(0.0, description="Average cycle time")
    total_changes_applied: int = Field(0, description="Total changes ever applied")
    rollback_rate: float = Field(0.0, description="Percentage of changes rolled back")

    # Identity tracking
    identity_stable: bool = Field(True, description="Whether identity is stable")
    time_since_last_change: Optional[float] = Field(None, description="Seconds since last change")

    # Review status
    under_review: bool = Field(False, description="Whether under WA review")
    review_reason: Optional[str] = Field(None, description="Why review was triggered")


class ReviewOutcome(BaseModel):
    """Outcome of WA review process."""

    review_id: str = Field(..., description="Review identifier")
    reviewer_id: str = Field(..., description="WA reviewer identifier")
    decision: str = Field(..., description="approve, reject, or modify")

    # Approved changes
    approved_changes: List[str] = Field(default_factory=list, description="Changes approved")
    rejected_changes: List[str] = Field(default_factory=list, description="Changes rejected")

    # Modifications
    modified_proposals: Dict[str, str] = Field(default_factory=dict, description="Proposals with modifications")

    # Guidance
    feedback: Optional[str] = Field(None, description="Review feedback")
    new_constraints: List[str] = Field(default_factory=list, description="New constraints added")

    # Actions
    resume_observation: bool = Field(True, description="Whether to resume observation")
    new_variance_limit: Optional[float] = Field(None, description="New variance limit if changed")


# ========== New Schemas for Enhanced Protocol ==========


class ConfigurationChange(BaseModel):
    """A proposed or applied configuration change."""

    change_id: str = Field(..., description="Unique change identifier")
    scope: str = Field(..., description="Scope: LOCAL, ENVIRONMENT, IDENTITY, COMMUNITY")
    target_path: str = Field(..., description="Configuration path to change")
    old_value: Optional[JSONValue] = Field(None, description="Previous configuration value")
    new_value: JSONValue = Field(..., description="New configuration value")
    estimated_variance_impact: float = Field(..., description="Estimated variance %")
    reliability_score: float = Field(..., description="Reliability score for this change")
    reason: str = Field(..., description="Why this change is proposed")
    status: str = Field("proposed", description="proposed, approved, applied, rolled_back")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    applied_at: Optional[datetime] = Field(None)


class ChangeApprovalResult(BaseModel):
    """Result of approving configuration changes."""

    approved_count: int = Field(0, description="Number of changes approved")
    rejected_count: int = Field(0, description="Number of changes rejected")
    applied_changes: List[str] = Field(default_factory=list, description="Change IDs applied")
    total_variance_impact: float = Field(0.0, description="Total variance from changes")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")


class RollbackResult(BaseModel):
    """Result of rolling back configuration changes."""

    rollback_count: int = Field(0, description="Number of changes rolled back")
    successful_rollbacks: List[str] = Field(default_factory=list, description="Successfully rolled back")
    failed_rollbacks: List[str] = Field(default_factory=list, description="Failed to rollback")
    variance_restored: float = Field(0.0, description="Variance % restored")
    errors: List[str] = Field(default_factory=list, description="Errors during rollback")


class ObservabilitySignal(BaseModel):
    """A signal from observability sources."""

    signal_type: str = Field(..., description="trace, log, metric, incident, security")
    timestamp: datetime = Field(..., description="When signal occurred")
    severity: str = Field("info", description="info, warning, error, critical")
    source: str = Field(..., description="Source service or component")
    details: Dict[str, JSONValue] = Field(default_factory=dict, description="Signal details")


class ImprovementMetrics(BaseModel):
    """Expected improvement metrics for an observation opportunity."""

    performance_gain_percent: float = Field(0.0, description="Expected performance improvement %")
    error_reduction_percent: float = Field(0.0, description="Expected error rate reduction %")
    resource_efficiency_gain: float = Field(0.0, description="Expected resource efficiency gain %")


class ObservationOpportunity(BaseModel):
    """An opportunity for system observation."""

    opportunity_id: str = Field(..., description="Unique identifier")
    trigger_signals: List[ObservabilitySignal] = Field(..., description="Signals that triggered this")
    proposed_changes: List[ConfigurationChange] = Field(..., description="Proposed changes")
    expected_improvement: ImprovementMetrics = Field(..., description="Expected improvements")
    risk_assessment: str = Field(..., description="Risk level: low, medium, high")
    priority: int = Field(0, description="Priority score")


class ObservabilityAnalysis(BaseModel):
    """Analysis of all observability signals for a time window."""

    window_start: datetime = Field(..., description="Analysis window start")
    window_end: datetime = Field(..., description="Analysis window end")

    # Signal counts
    total_signals: int = Field(0, description="Total signals analyzed")
    signals_by_type: Dict[str, int] = Field(default_factory=dict)

    # Patterns found
    patterns_detected: List[str] = Field(default_factory=list, description="Pattern types found")
    anomalies_detected: List[str] = Field(default_factory=list, description="Anomalies found")

    # Opportunities
    observation_opportunities: List[ObservationOpportunity] = Field(default_factory=list)

    # Health assessment
    system_health_score: float = Field(100.0, description="Overall health 0-100")
    component_health: Dict[str, float] = Field(default_factory=dict)


class ObservationImpact(BaseModel):
    """Measured impact of an observation."""

    dimension: str = Field(..., description="Impact dimension measured")
    baseline_value: float = Field(..., description="Value before observation")
    current_value: float = Field(..., description="Value after observation")
    improvement_percent: float = Field(..., description="Percentage improvement")
    measurement_timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ObservationEffectiveness(BaseModel):
    """Overall effectiveness of an observation across all dimensions."""

    observation_id: str = Field(..., description="Observation being measured")
    measurement_period_hours: int = Field(24, description="Measurement period")

    # Impact by dimension
    performance_impact: Optional[ObservationImpact] = Field(None)
    error_impact: Optional[ObservationImpact] = Field(None)
    resource_impact: Optional[ObservationImpact] = Field(None)
    stability_impact: Optional[ObservationImpact] = Field(None)
    user_satisfaction_impact: Optional[ObservationImpact] = Field(None)

    # Overall assessment
    overall_effectiveness: float = Field(0.0, description="Overall effectiveness score")
    recommendation: str = Field(..., description="keep, modify, rollback")


class PatternRecord(BaseModel):
    """A learned observation pattern."""

    pattern_id: str = Field(..., description="Unique pattern identifier")
    trigger_conditions: List[ObservabilitySignal] = Field(..., description="What triggers this")
    successful_applications: int = Field(0, description="Times successfully applied")
    failed_applications: int = Field(0, description="Times failed")
    average_improvement: float = Field(0.0, description="Average improvement %")
    reliability_score: float = Field(0.0, description="Reliability score for pattern")
    last_applied: Optional[datetime] = Field(None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PatternLibrarySummary(BaseModel):
    """Summary of the pattern library."""

    total_patterns: int = Field(0, description="Total patterns in library")
    high_reliability_patterns: int = Field(0, description="Patterns with >70% reliability score")
    recently_used_patterns: int = Field(0, description="Used in last 30 days")
    most_effective_patterns: List[PatternRecord] = Field(default_factory=list)
    pattern_categories: Dict[str, int] = Field(default_factory=dict)


class ImprovementRecord(BaseModel):
    """Record of a specific improvement."""

    improvement_description: str = Field(..., description="What was improved")
    performance_gain: float = Field(..., description="Performance gain %")
    impact_score: float = Field(..., description="Overall impact score")


class ServiceImprovementReport(BaseModel):
    """Comprehensive service improvement report."""

    report_period_start: datetime = Field(..., description="Report period start")
    report_period_end: datetime = Field(..., description="Report period end")

    # Observation summary
    total_observations: int = Field(0, description="Total observations in period")
    successful_observations: int = Field(0, description="Successful observations")
    rolled_back_observations: int = Field(0, description="Observations rolled back")

    # Impact summary
    average_performance_improvement: float = Field(0.0, description="Avg performance gain %")
    error_rate_reduction: float = Field(0.0, description="Error rate reduction %")
    resource_efficiency_gain: float = Field(0.0, description="Resource efficiency gain %")

    # Variance tracking
    starting_variance: float = Field(0.0, description="Variance at period start")
    ending_variance: float = Field(0.0, description="Variance at period end")
    peak_variance: float = Field(0.0, description="Peak variance in period")

    # Top improvements
    top_improvements: List[ImprovementRecord] = Field(default_factory=list, description="Top improvement records")

    # Recommendations
    recommendations: List[str] = Field(default_factory=list, description="Future recommendations")


# Additional schemas for replacing Dict[str, Any] usage


class PatternInsight(BaseModel):
    """Insight from pattern analysis."""

    pattern_id: str = Field(..., description="Pattern identifier")
    pattern_type: str = Field(..., description="Type of pattern")
    description: str = Field(..., description="Pattern description")
    confidence: float = Field(..., description="Confidence score 0-1")
    occurrences: int = Field(..., description="Number of occurrences")
    last_seen: datetime = Field(..., description="When last observed")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional pattern metadata"
    )


class LearningSummary(BaseModel):
    """Summary of system learning progress."""

    total_patterns: int = Field(0, description="Total patterns detected")
    patterns_by_type: Dict[str, int] = Field(default_factory=dict, description="Patterns grouped by type")
    action_frequencies: Dict[str, int] = Field(default_factory=dict, description="Action usage counts")
    most_used_actions: List[str] = Field(default_factory=list, description="Top 5 most used actions")
    least_used_actions: List[str] = Field(default_factory=list, description="Bottom 5 used actions")
    insights_count: int = Field(0, description="Number of insights generated")
    recent_insights: List[str] = Field(default_factory=list, description="Recent insight descriptions")
    learning_rate: float = Field(0.0, description="Rate of new pattern detection")
    recommendation: str = Field("continue", description="continue, review, pause")


class PatternEffectiveness(BaseModel):
    """Effectiveness metrics for a specific pattern."""

    pattern_id: str = Field(..., description="Pattern identifier")
    pattern_type: str = Field(..., description="Type of pattern")
    times_applied: int = Field(0, description="Times pattern was applied")
    success_rate: float = Field(0.0, description="Success rate 0-1")
    average_improvement: float = Field(0.0, description="Average improvement %")
    last_applied: Optional[datetime] = Field(None, description="When last applied")
    recommendation: str = Field("monitor", description="monitor, apply, ignore")


class AnalysisStatus(BaseModel):
    """Current status of pattern analysis system."""

    is_running: bool = Field(..., description="Whether analysis is active")
    last_analysis: datetime = Field(..., description="When last analysis ran")
    next_analysis_in_seconds: float = Field(..., description="Seconds until next analysis")
    patterns_detected: int = Field(0, description="Total patterns detected")
    insights_generated: int = Field(0, description="Total insights generated")
    analysis_interval_seconds: float = Field(..., description="Current analysis interval")
    error_count: int = Field(0, description="Number of analysis errors")
    last_error: Optional[str] = Field(None, description="Last error message")


# Re-export SystemSnapshot from runtime context

__all__ = [
    "ObservationState",
    "ProcessSnapshotResult",
    "ObservationCycleResult",
    "CycleEventData",
    "ObservationStatus",
    "ReviewOutcome",
    "ConfigurationChange",
    "ChangeApprovalResult",
    "RollbackResult",
    "ObservabilitySignal",
    "ObservationOpportunity",
    "ObservabilityAnalysis",
    "ObservationImpact",
    "ObservationEffectiveness",
    "PatternRecord",
    "PatternLibrarySummary",
    "ServiceImprovementReport",
    "PatternInsight",
    "LearningSummary",
    "PatternEffectiveness",
    "AnalysisStatus",
    "SystemSnapshot",
]
