"""
Processor error handling schemas.

Provides typed schemas in handle_error() method with typed schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ErrorSeverity(str, Enum):
    """Severity levels for processor errors."""

    LOW = "low"  # Can be ignored, processing continues
    MEDIUM = "medium"  # Should be logged, processing continues with caution
    HIGH = "high"  # Significant issue, may need intervention
    CRITICAL = "critical"  # Processing should stop, immediate attention needed


class AdditionalErrorContext(BaseModel):
    """Additional context for error handling."""

    channel_id: Optional[str] = Field(None, description="Channel where error occurred")
    user_id: Optional[str] = Field(None, description="User involved in the error")
    task_id: Optional[str] = Field(None, description="Task ID if error during task processing")
    memory_operation: Optional[str] = Field(None, description="Memory operation if error during memory access")
    llm_model: Optional[str] = Field(None, description="LLM model if error during LLM call")
    handler_name: Optional[str] = Field(None, description="Handler name if error during handler execution")
    custom_data: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Custom error context data"
    )

    model_config = ConfigDict(extra="allow")


class ErrorContext(BaseModel):
    """Context information for processor error handling."""

    processor_name: str = Field(..., description="Name of the processor where error occurred")
    state: str = Field(..., description="Current AgentState when error occurred")
    round_number: int = Field(..., description="Processing round when error occurred")
    operation: str = Field(..., description="Operation being performed (e.g., 'process_thought', 'dispatch_action')")
    item_id: Optional[str] = Field(None, description="ID of item being processed if applicable")
    thought_content: Optional[str] = Field(None, description="Thought content if error during thought processing")
    action_type: Optional[str] = Field(None, description="Action type if error during action dispatch")
    additional_context: Optional[AdditionalErrorContext] = Field(None, description="Any additional context")


class ProcessingError(BaseModel):
    """Structured error information for processor errors."""

    error_type: str = Field(..., description="Type of error (e.g., exception class name)")
    error_message: str = Field(..., description="Human-readable error message")
    severity: ErrorSeverity = Field(..., description="Severity level of the error")
    timestamp: datetime = Field(..., description="When the error occurred")
    context: ErrorContext = Field(..., description="Context about the error")
    stack_trace: Optional[str] = Field(None, description="Stack trace if available")
    recovery_attempted: bool = Field(False, description="Whether recovery was attempted")
    recovery_successful: bool = Field(False, description="Whether recovery succeeded")
    should_continue: bool = Field(True, description="Whether processing should continue")


class ErrorHandlingResult(BaseModel):
    """Result of error handling operation."""

    handled: bool = Field(..., description="Whether error was successfully handled")
    should_continue: bool = Field(..., description="Whether processing should continue")
    recovery_action: Optional[str] = Field(None, description="Action taken to recover")
    new_state: Optional[str] = Field(None, description="New state to transition to if needed")
    error_logged: bool = Field(True, description="Whether error was logged")
    metrics_updated: bool = Field(True, description="Whether error metrics were updated")


class ProcessorConfigOverrides(BaseModel):
    """Processor-specific configuration overrides."""

    # Common processor overrides
    batch_size: Optional[int] = Field(None, description="Batch size for processing")
    processing_interval_ms: Optional[int] = Field(None, description="Processing interval in milliseconds")
    enable_caching: Optional[bool] = Field(None, description="Enable caching for this processor")
    cache_ttl_seconds: Optional[int] = Field(None, description="Cache time-to-live in seconds")

    # State-specific overrides
    min_state_duration_seconds: Optional[int] = Field(None, description="Minimum time to stay in state")
    max_state_duration_seconds: Optional[int] = Field(None, description="Maximum time to stay in state")

    # Resource limits
    max_memory_mb: Optional[int] = Field(None, description="Maximum memory usage in MB")
    max_cpu_percent: Optional[float] = Field(None, description="Maximum CPU usage percentage")

    # Custom settings
    custom_flags: Dict[str, bool] = Field(default_factory=dict, description="Custom boolean flags")
    custom_values: Dict[str, Union[str, int, float]] = Field(
        default_factory=dict, description="Custom configuration values"
    )

    model_config = ConfigDict(extra="forbid")


class ProcessorConfig(BaseModel):
    """Configuration for a processor."""

    processor_name: str = Field(..., description="Name of the processor")
    supported_states: list[str] = Field(..., description="States this processor supports")
    max_retries: int = Field(3, description="Maximum retry attempts on error")
    timeout_seconds: Optional[int] = Field(None, description="Processing timeout in seconds")
    error_threshold: int = Field(10, description="Error count before processor is considered unhealthy")
    config_overrides: Optional[ProcessorConfigOverrides] = Field(None, description="Processor-specific configuration")


__all__ = [
    "ErrorSeverity",
    "AdditionalErrorContext",
    "ErrorContext",
    "ProcessingError",
    "ErrorHandlingResult",
    "ProcessorConfigOverrides",
    "ProcessorConfig",
]
