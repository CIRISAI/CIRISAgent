"""
State transition schemas for processor state management.
Provides typed schemas usage in state history and transitions.
"""

from datetime import datetime
from typing import Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.processors.states import AgentState


class StateTransitionMetadata(BaseModel):
    """Metadata for state transitions."""

    reason: Optional[str] = Field(None, description="Reason for the transition")
    trigger: Optional[str] = Field(None, description="What triggered the transition")
    duration_in_previous_state: Optional[float] = Field(None, description="Seconds spent in previous state")
    forced: bool = Field(False, description="Whether transition was forced")
    validator_results: Dict[str, bool] = Field(default_factory=dict, description="Results of state validators")

    model_config = ConfigDict(extra="allow")  # Allow additional fields for extensibility


class StateTransitionRecord(BaseModel):
    """Record of a state transition that occurred."""

    timestamp: str = Field(description="ISO format timestamp of the transition")
    from_state: Optional[str] = Field(None, description="State before transition (None for initial state)")
    to_state: str = Field(description="State after transition")
    metadata: Optional[StateTransitionMetadata] = Field(None, description="Additional transition metadata")

    model_config = ConfigDict(frozen=True)  # Make immutable once created


class StateTransitionContext(BaseModel):
    """Context for state transition requests."""

    trigger_source: Optional[str] = Field(None, description="What triggered this transition request")
    task_context: Optional[str] = Field(None, description="Current task being processed")
    memory_state: Optional[str] = Field(None, description="Current memory state summary")
    processor_metrics: Dict[str, float] = Field(default_factory=dict, description="Current processor metrics")

    model_config = ConfigDict(extra="allow")  # Allow additional fields for extensibility


class StateTransitionRequest(BaseModel):
    """Request to transition to a new state."""

    target_state: AgentState = Field(description="Target state to transition to")
    reason: Optional[str] = Field(None, description="Reason for the transition")
    force: bool = Field(False, description="Force transition even if conditions not met")
    context: Optional[StateTransitionContext] = Field(None, description="Additional transition context")


class StateTransitionResult(BaseModel):
    """Result of a state transition attempt."""

    success: bool = Field(description="Whether the transition succeeded")
    from_state: AgentState = Field(description="State before transition attempt")
    to_state: Optional[AgentState] = Field(None, description="State after transition (if successful)")
    reason: Optional[str] = Field(None, description="Reason for success or failure")
    timestamp: str = Field(description="ISO format timestamp of the attempt")
    duration_in_previous_state: Optional[float] = Field(None, description="Seconds spent in previous state")


class StateMetrics(BaseModel):
    """Metrics tracked for a specific state."""

    tasks_processed: int = Field(0, description="Number of tasks processed in this state")
    errors_encountered: int = Field(0, description="Number of errors in this state")
    average_task_duration_ms: Optional[float] = Field(None, description="Average task processing time")
    memory_operations: int = Field(0, description="Number of memory operations performed")
    llm_calls: int = Field(0, description="Number of LLM calls made")
    custom_metrics: Dict[str, Union[int, float, str]] = Field(
        default_factory=dict, description="State-specific custom metrics"
    )

    def increment(self, metric: str, value: Union[int, float] = 1) -> None:
        """Increment a metric value."""
        if metric in self.model_fields:
            current = getattr(self, metric, 0)
            setattr(self, metric, current + value)
        else:
            current = self.custom_metrics.get(metric, 0)
            if isinstance(current, (int, float)) and isinstance(value, (int, float)):
                self.custom_metrics[metric] = current + value
            else:
                self.custom_metrics[metric] = value


class StateConfiguration(BaseModel):
    """State-specific configuration."""

    # Common state configuration
    auto_transition_enabled: bool = Field(True, description="Allow automatic state transitions")
    max_duration_seconds: Optional[int] = Field(None, description="Maximum time to stay in this state")
    min_duration_seconds: Optional[int] = Field(None, description="Minimum time to stay in this state")

    # State-specific settings
    processing_mode: Optional[str] = Field(None, description="Processing mode for this state")
    priority_level: Optional[int] = Field(None, description="Priority level for state processing")

    # Resource limits for this state
    memory_limit_mb: Optional[int] = Field(None, description="Memory limit for this state")
    cpu_limit_percent: Optional[float] = Field(None, description="CPU limit for this state")

    # Custom configuration
    custom_settings: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Custom state settings"
    )

    model_config = ConfigDict(extra="allow")  # Allow state-specific extensions


class StateMetadata(BaseModel):
    """Metadata for a specific state."""

    entered_at: str = Field(description="ISO format timestamp when state was entered")
    metrics: StateMetrics = Field(default_factory=StateMetrics, description="State-specific metrics")
    exit_reason: Optional[str] = Field(None, description="Reason for exiting this state")
    state_config: StateConfiguration = Field(
        default_factory=StateConfiguration, description="State-specific configuration"
    )

    def add_metric(self, key: str, value: Union[int, float, str]) -> None:
        """Add or update a metric."""
        self.metrics.custom_metrics[key] = value


class StateHistory(BaseModel):
    """Complete state history with typed records."""

    transitions: list[StateTransitionRecord] = Field(
        default_factory=list, description="Ordered list of state transitions"
    )
    current_state: AgentState = Field(description="Current agent state")
    current_state_metadata: StateMetadata = Field(description="Metadata for current state")

    def add_transition(self, record: StateTransitionRecord) -> None:
        """Add a transition record to history."""
        self.transitions.append(record)

    def get_recent_transitions(self, limit: int = 10) -> list[StateTransitionRecord]:
        """Get the most recent transitions."""
        return self.transitions[-limit:] if self.transitions else []

    def get_state_duration(self, state: AgentState) -> float:
        """Calculate total time spent in a specific state across all transitions."""
        total_duration = 0.0

        for i, transition in enumerate(self.transitions):
            if transition.to_state == state.value:
                # Find when we left this state
                exit_time = None
                for j in range(i + 1, len(self.transitions)):
                    if self.transitions[j].from_state == state.value:
                        exit_time = self.transitions[j].timestamp
                        break

                # If we haven't left yet and it's the current state, use now
                if exit_time is None and self.current_state == state:
                    exit_time = datetime.now().isoformat()

                if exit_time:
                    enter_time = datetime.fromisoformat(transition.timestamp)
                    exit_datetime = datetime.fromisoformat(exit_time)
                    total_duration += (exit_datetime - enter_time).total_seconds()

        return total_duration


class StateConditionDetails(BaseModel):
    """Details about a state condition check."""

    checked_at: str = Field(description="ISO format timestamp of check")
    check_duration_ms: Optional[float] = Field(None, description="Time taken to check condition")
    threshold_value: Optional[Union[int, float]] = Field(None, description="Threshold value if applicable")
    actual_value: Optional[Union[int, float]] = Field(None, description="Actual value if applicable")
    error_message: Optional[str] = Field(None, description="Error if check failed")

    model_config = ConfigDict(extra="allow")  # Allow additional fields for specific conditions


class StateCondition(BaseModel):
    """Condition that must be met for a state transition."""

    name: str = Field(description="Name of the condition")
    description: str = Field(description="Human-readable description")
    met: bool = Field(description="Whether the condition is currently met")
    details: Optional[StateConditionDetails] = Field(None, description="Additional condition details")


class StateTransitionValidation(BaseModel):
    """Validation result for a potential state transition."""

    from_state: AgentState = Field(description="Current state")
    to_state: AgentState = Field(description="Target state")
    is_valid: bool = Field(description="Whether the transition is valid")
    conditions: list[StateCondition] = Field(default_factory=list, description="Conditions checked")
    blocking_reason: Optional[str] = Field(None, description="Reason transition is blocked if invalid")
