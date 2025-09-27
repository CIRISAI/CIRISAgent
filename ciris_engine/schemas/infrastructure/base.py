"""
Schemas for infrastructure base operations.

These replace all Dict[str, Any] usage in protocols/infrastructure/base.py.
"""

from datetime import datetime
from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field


class RuntimeStats(BaseModel):
    """Runtime statistics and metrics."""

    uptime_seconds: float = Field(..., description="Runtime uptime in seconds")
    total_messages_processed: int = Field(0, description="Total messages processed")
    active_tasks: int = Field(0, description="Number of active tasks")
    memory_usage_mb: float = Field(..., description="Memory usage in MB")
    cpu_usage_percent: float = Field(..., description="CPU usage percentage")
    last_checkpoint: Optional[datetime] = Field(None, description="Last checkpoint time")
    errors_last_hour: int = Field(0, description="Errors in last hour")
    warnings_last_hour: int = Field(0, description="Warnings in last hour")
    agent_state: str = Field(..., description="Current agent state")
    additional_stats: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional runtime stats"
    )


class HealthCheckResult(BaseModel):
    """Health check result for a component."""

    component_name: str = Field(..., description="Name of the component")
    healthy: bool = Field(..., description="Whether component is healthy")
    message: Optional[str] = Field(None, description="Health status message")
    last_check: datetime = Field(..., description="Last health check time")
    details: Optional[Dict[str, Union[str, int, float, bool]]] = Field(None, description="Additional health details")


class ComponentHealthStatus(BaseModel):
    """Overall health status of all components."""

    overall_healthy: bool = Field(..., description="Whether all components are healthy")
    components: Dict[str, bool] = Field(..., description="Health status by component name")
    unhealthy_components: List[str] = Field(default_factory=list, description="List of unhealthy components")
    last_check: datetime = Field(..., description="Last health check time")
    details: List[HealthCheckResult] = Field(default_factory=list, description="Detailed health results")


class ServiceDependencies(BaseModel):
    """Service dependency validation results."""

    all_satisfied: bool = Field(..., description="Whether all dependencies are satisfied")
    dependencies: Dict[str, List[str]] = Field(..., description="Dependencies by service name")
    missing_dependencies: Dict[str, List[str]] = Field(
        default_factory=dict, description="Missing dependencies by service"
    )
    circular_dependencies: List[str] = Field(default_factory=list, description="Detected circular dependencies")
    validation_time: datetime = Field(..., description="When validation was performed")


class BusMetrics(BaseModel):
    """Message bus performance metrics."""

    messages_sent: int = Field(0, description="Total messages sent")
    messages_received: int = Field(0, description="Total messages received")
    messages_dropped: int = Field(0, description="Messages dropped")
    average_latency_ms: float = Field(0.0, description="Average message latency")
    active_subscriptions: int = Field(0, description="Number of active subscriptions")
    queue_depth: int = Field(0, description="Current queue depth")
    errors_last_hour: int = Field(0, description="Bus errors in last hour")
    busiest_service: Optional[str] = Field(None, description="Service with most traffic")
    additional_metrics: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional bus metrics"
    )


class DreamConsolidationResult(BaseModel):
    """Result of memory consolidation during dream state."""

    dream_id: str = Field(..., description="Dream session ID")
    memories_processed: int = Field(0, description="Number of memories processed")
    memories_consolidated: int = Field(0, description="Number of memories consolidated")
    memories_pruned: int = Field(0, description="Number of memories pruned")
    patterns_detected: int = Field(0, description="Number of patterns detected")
    insights_generated: int = Field(0, description="Number of insights generated")
    duration_seconds: float = Field(..., description="Consolidation duration")
    success: bool = Field(..., description="Whether consolidation succeeded")
    errors: List[str] = Field(default_factory=list, description="Errors during consolidation")


class DreamSchedule(BaseModel):
    """Dream processing schedule information."""

    next_dream_time: Optional[datetime] = Field(None, description="Next scheduled dream")
    last_dream_time: Optional[datetime] = Field(None, description="Last dream time")
    dream_frequency_hours: float = Field(24.0, description="Hours between dreams")
    is_dreaming: bool = Field(False, description="Currently in dream state")
    current_dream_id: Optional[str] = Field(None, description="Current dream ID if dreaming")
    dreams_completed: int = Field(0, description="Total dreams completed")
    average_dream_duration_minutes: float = Field(0.0, description="Average dream duration")


class DreamInsight(BaseModel):
    """Insight discovered during dream analysis."""

    insight_id: str = Field(..., description="Unique insight ID")
    insight_type: str = Field(..., description="Type of insight")
    description: str = Field(..., description="Insight description")
    supporting_memories: List[str] = Field(default_factory=list, description="Memory IDs supporting this insight")
    timestamp: datetime = Field(..., description="When insight was discovered")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional insight metadata"
    )


class IdentityBaseline(BaseModel):
    """Identity baseline for variance monitoring."""

    baseline_id: str = Field(..., description="Baseline ID")
    created_at: datetime = Field(..., description="When baseline was created")
    core_values: List[str] = Field(..., description="Core value identifiers")
    behavioral_patterns: Dict[str, float] = Field(..., description="Behavioral pattern scores")
    decision_weights: Dict[str, float] = Field(..., description="Decision making weights")
    memory_priorities: List[str] = Field(..., description="Memory priority types")
    baseline_hash: str = Field(..., description="Hash of baseline for integrity")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional baseline data"
    )


class IdentityVarianceMetric(BaseModel):
    """Identity variance measurement."""

    measurement_time: datetime = Field(..., description="When measurement was taken")
    variance_percentage: float = Field(..., description="Variance from baseline percentage")
    changed_values: List[str] = Field(default_factory=list, description="Values that changed")
    behavioral_drift: Dict[str, float] = Field(default_factory=dict, description="Behavioral pattern changes")
    decision_drift: Dict[str, float] = Field(default_factory=dict, description="Decision weight changes")
    within_threshold: bool = Field(..., description="Whether variance is within acceptable threshold")
    alert_triggered: bool = Field(False, description="Whether alert was triggered")


class ConfigurationFeedback(BaseModel):
    """Configuration feedback data."""

    feedback_id: str = Field(..., description="Feedback ID")
    timestamp: datetime = Field(..., description="When feedback was collected")
    configuration_item: str = Field(..., description="Configuration item")
    performance_score: float = Field(..., description="Performance score 0-1")
    error_rate: float = Field(..., description="Error rate percentage")
    user_satisfaction: Optional[float] = Field(None, description="User satisfaction score")
    suggested_adjustment: Optional[str] = Field(None, description="Suggested configuration adjustment")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional feedback data"
    )


class ConfigurationPattern(BaseModel):
    """Detected configuration pattern."""

    pattern_id: str = Field(..., description="Pattern ID")
    pattern_type: str = Field(..., description="Type of pattern")
    frequency: int = Field(..., description="How often pattern occurs")
    success_rate: float = Field(..., description="Success rate when pattern active")
    configuration_items: List[str] = Field(..., description="Configuration items in pattern")
    recommended_action: str = Field(..., description="Recommended action for pattern")


class ConfigurationUpdate(BaseModel):
    """Proposed configuration update."""

    update_id: str = Field(..., description="Update ID")
    proposed_at: datetime = Field(..., description="When update was proposed")
    configuration_item: str = Field(..., description="Item to update")
    current_value: str = Field(..., description="Current value")
    proposed_value: str = Field(..., description="Proposed new value")
    rationale: str = Field(..., description="Why this update is recommended")
    expected_improvement: float = Field(..., description="Expected improvement percentage")
    risk_score: float = Field(..., description="Risk score 0-1")
    approved: bool = Field(False, description="Whether update is approved")


class ActiveAdapter(BaseModel):
    """Information about an active adapter."""

    adapter_type: str = Field(..., description="Type of adapter")
    adapter_id: str = Field(..., description="Unique adapter ID")
    status: str = Field(..., description="Adapter status")
    started_at: datetime = Field(..., description="When adapter was started")
    messages_handled: int = Field(0, description="Messages handled by adapter")
    last_activity: Optional[datetime] = Field(None, description="Last activity time")
    configuration: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Adapter configuration"
    )


class CheckpointInfo(BaseModel):
    """Information about a system checkpoint."""

    checkpoint_id: str = Field(..., description="Checkpoint ID")
    created_at: datetime = Field(..., description="When checkpoint was created")
    size_bytes: int = Field(..., description="Checkpoint size in bytes")
    description: str = Field(..., description="Checkpoint description")
    agent_state: str = Field(..., description="Agent state at checkpoint")
    includes_memory: bool = Field(True, description="Whether memory is included")
    includes_config: bool = Field(True, description="Whether config is included")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional checkpoint metadata"
    )


class ServiceRegistration(BaseModel):
    """Service registration information."""

    service_name: str = Field(..., description="Service name")
    service_type: str = Field(..., description="Service type")
    registered_at: datetime = Field(..., description="Registration time")
    status: str = Field(..., description="Service status")
    endpoints: List[str] = Field(default_factory=list, description="Service endpoints")
    capabilities: List[str] = Field(default_factory=list, description="Service capabilities")
    dependencies: List[str] = Field(default_factory=list, description="Service dependencies")
    health_check_url: Optional[str] = Field(None, description="Health check endpoint")
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional service metadata"
    )


class ServiceRegistrySnapshot(BaseModel):
    """Snapshot of the service registry state for serialization."""

    services: Dict[str, ServiceRegistration] = Field(..., description="All registered services")
    total_services: int = Field(..., description="Total number of services")
    healthy_services: int = Field(..., description="Number of healthy services")
    last_update: datetime = Field(..., description="Last registry update")


__all__ = [
    "RuntimeStats",
    "HealthCheckResult",
    "ComponentHealthStatus",
    "ServiceDependencies",
    "BusMetrics",
    "DreamConsolidationResult",
    "DreamSchedule",
    "DreamInsight",
    "IdentityBaseline",
    "IdentityVarianceMetric",
    "ConfigurationFeedback",
    "ConfigurationPattern",
    "ConfigurationUpdate",
    "ActiveAdapter",
    "CheckpointInfo",
    "ServiceRegistration",
    "ServiceRegistrySnapshot",
]
