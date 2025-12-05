"""
Runtime control service schemas for type-safe operations.

This module provides Pydantic models for the runtime control service,
ensuring full type safety and validation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.conscience.results import ConscienceResult
from ciris_engine.schemas.dma.core import DMAContext
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.handlers.schemas import HandlerResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.system_context import SystemSnapshot
from ciris_engine.schemas.types import ConfigDict, ConfigValue, JSONDict, SerializedModel

# Type aliases for configuration values
ConfigItem = Tuple[str, ConfigValue]


class ConfigDictMixin:
    """Mixin providing standard config dict access methods.

    Classes using this mixin must have a 'configs: ConfigDict' field.
    DRY pattern to avoid code duplication across classes with config fields.
    """

    configs: ConfigDict  # Type hint for IDEs

    def get(self, key: str, default: Optional[ConfigValue] = None) -> Optional[ConfigValue]:
        """Get a configuration value with optional default."""
        return self.configs.get(key, default)

    def set(self, key: str, value: ConfigValue) -> None:
        """Set a configuration value."""
        self.configs[key] = value

    def update(self, values: ConfigDict) -> None:
        """Update multiple configuration values."""
        self.configs.update(values)

    def keys(self) -> List[str]:
        """Get all configuration keys."""
        return list(self.configs.keys())


# Field description constants (DRY principle - avoid duplication)
DESC_THOUGHT_ID = "Thought being processed"
DESC_TIMESTAMP = "Event timestamp"
DESC_PARENT_TASK = "Parent task if any"
DESC_CONSCIENCE_PASSED = "Whether conscience checks passed"
DESC_CONSCIENCE_OVERRIDE_REASON = "Reason if conscience overrode action"
DESC_AUDIT_SEQUENCE = "Sequence number in audit hash chain"
DESC_AUDIT_HASH = "Hash of audit entry (tamper-evident)"
DESC_AUDIT_SIGNATURE = "Cryptographic signature of audit entry"


class StepPoint(str, Enum):
    """Points where single-stepping can pause in the H3ERE pipeline."""

    # H3ERE Pipeline - 10 step points (0 setup + 7 core + 2 optional recursive)
    START_ROUND = "start_round"  # 0) Setup: Tasks → Thoughts → Round Queue → Ready for context
    GATHER_CONTEXT = "gather_context"  # 1) Build context for DMA processing
    PERFORM_DMAS = "perform_dmas"  # 2) Execute multi-perspective DMAs
    PERFORM_ASPDMA = "perform_aspdma"  # 3) LLM-powered action selection
    CONSCIENCE_EXECUTION = "conscience_execution"  # 4) Ethical safety validation
    RECURSIVE_ASPDMA = "recursive_aspdma"  # 3B) Optional: Re-run action selection if conscience failed
    RECURSIVE_CONSCIENCE = "recursive_conscience"  # 4B) Optional: Re-validate if recursive action failed
    FINALIZE_ACTION = "finalize_action"  # 5) Final action determination
    PERFORM_ACTION = "perform_action"  # 6) Dispatch action to handler
    ACTION_COMPLETE = "action_complete"  # 9) Action execution completed
    ROUND_COMPLETE = "round_complete"  # 10) Processing round completed


class ReasoningEvent(str, Enum):
    """Simplified reasoning stream events - 6 clear result events."""

    THOUGHT_START = "thought_start"  # 0) Thought begins processing - metadata and content
    SNAPSHOT_AND_CONTEXT = "snapshot_and_context"  # 1) System snapshot + gathered context
    DMA_RESULTS = "dma_results"  # 2) All 3 DMA results (csdma, dsdma, aspdma)
    ASPDMA_RESULT = "aspdma_result"  # 3) Selected action + rationale
    CONSCIENCE_RESULT = "conscience_result"  # 4) Conscience evaluation + final action
    ACTION_RESULT = "action_result"  # 5) Action execution outcome + audit trail


class StepDuration(str, Enum):
    """How long to wait before building the round queue."""

    IMMEDIATE = "immediate"  # 10 seconds
    SHORT = "short"  # 20 seconds
    NORMAL = "normal"  # 30 seconds
    LONG = "long"  # 60 seconds


# Map durations to seconds
STEP_DURATION_SECONDS = {
    StepDuration.IMMEDIATE: 10.0,
    StepDuration.SHORT: 20.0,
    StepDuration.NORMAL: 30.0,
    StepDuration.LONG: 60.0,
}


class CircuitBreakerState(str, Enum):
    """States of a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerStatus(BaseModel):
    """Status information for a circuit breaker."""

    state: CircuitBreakerState = Field(..., description="Current state of the circuit breaker")
    failure_count: int = Field(0, description="Number of consecutive failures")
    last_failure_time: Optional[datetime] = Field(None, description="Time of last failure")
    last_success_time: Optional[datetime] = Field(None, description="Time of last success")
    half_open_retry_time: Optional[datetime] = Field(None, description="When to retry in half-open state")
    trip_threshold: int = Field(5, description="Number of failures before tripping")
    reset_timeout_seconds: float = Field(60.0, description="Seconds before attempting reset")
    service_name: str = Field(..., description="Name of the service this breaker protects")


class TraceContext(BaseModel):
    """OTLP-compatible trace context for step correlation."""

    trace_id: str = Field(..., description="Unique trace identifier")
    span_id: str = Field(..., description="Unique span identifier")
    parent_span_id: Optional[str] = Field(None, description="Parent span identifier")
    span_name: str = Field(..., description="Human-readable span name")
    operation_name: str = Field(..., description="Operation name for tracing")
    start_time_ns: int = Field(..., description="Start time in nanoseconds")
    end_time_ns: int = Field(..., description="End time in nanoseconds")
    duration_ns: int = Field(..., description="Duration in nanoseconds")
    span_kind: str = Field("internal", description="Span kind (internal, server, client, etc.)")


class SpanAttribute(BaseModel):
    """OTLP-compatible span attribute."""

    key: str = Field(..., description="Attribute key")
    value: JSONDict = Field(
        ..., description="Attribute value in OTLP format"
    )  # OTLP standard requires JSON-compatible dict


class ConfigValueMap(ConfigDictMixin, BaseModel):
    """Typed map for configuration values."""

    configs: ConfigDict = Field(default_factory=dict, description="Configuration key-value pairs with typed values")

    def items(self) -> List[ConfigItem]:
        """Get all key-value pairs."""
        return list(self.configs.items())

    def values(self) -> List[ConfigValue]:
        """Get all configuration values."""
        return list(self.configs.values())


class TaskSelectionCriteria(ConfigDictMixin, BaseModel):
    """Criteria used for task selection in processing rounds."""

    max_priority: Optional[int] = Field(None, description="Maximum priority threshold")
    min_priority: Optional[int] = Field(None, description="Minimum priority threshold")
    max_age_hours: Optional[float] = Field(None, description="Maximum age in hours")
    channel_filter: Optional[str] = Field(None, description="Channel ID filter")
    task_type_filter: Optional[str] = Field(None, description="Task type filter")
    exclude_failed: bool = Field(True, description="Whether to exclude previously failed tasks")
    max_retry_count: int = Field(3, description="Maximum retry count for tasks")
    user_id_filter: Optional[str] = Field(None, description="User ID filter")
    batch_size: int = Field(10, description="Maximum number of tasks to select")
    configs: ConfigDict = Field(
        default_factory=dict, description="Additional configuration key-value pairs with typed values"
    )

    def items(self) -> List[ConfigItem]:
        """Get all key-value pairs."""
        return list(self.configs.items())


class ServiceProviderUpdate(BaseModel):
    """Details of a service provider update."""

    service_type: str = Field(..., description="Type of service")
    old_priority: str = Field(..., description="Previous priority")
    new_priority: str = Field(..., description="New priority")
    old_priority_group: int = Field(..., description="Previous priority group")
    new_priority_group: int = Field(..., description="New priority group")
    old_strategy: str = Field(..., description="Previous selection strategy")
    new_strategy: str = Field(..., description="New selection strategy")


class ServicePriorityUpdateResponse(BaseModel):
    """Response from service priority update operation."""

    success: bool = Field(..., description="Whether the update succeeded")
    message: Optional[str] = Field(None, description="Success or error message")
    provider_name: str = Field(..., description="Name of the service provider")
    changes: Optional[ServiceProviderUpdate] = Field(None, description="Details of changes made")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    error: Optional[str] = Field(None, description="Error message if operation failed")


class CircuitBreakerResetResponse(BaseModel):
    """Response from circuit breaker reset operation."""

    success: bool = Field(..., description="Whether the reset succeeded")
    message: str = Field(..., description="Operation result message")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    service_type: Optional[str] = Field(None, description="Service type if specified")
    reset_count: Optional[int] = Field(None, description="Number of breakers reset")
    error: Optional[str] = Field(None, description="Error message if operation failed")


class ServiceProviderInfo(BaseModel):
    """Information about a registered service provider."""

    name: str = Field(..., description="Provider name")
    priority: str = Field(..., description="Priority level name")
    priority_group: int = Field(..., description="Priority group number")
    strategy: str = Field(..., description="Selection strategy")
    capabilities: Optional[ConfigDict] = Field(None, description="Provider capabilities")
    metadata: Optional[ConfigDict] = Field(None, description="Provider metadata")
    circuit_breaker_state: Optional[str] = Field(None, description="Circuit breaker state if available")


class ServiceRegistryInfoResponse(BaseModel):
    """Enhanced service registry information response."""

    total_services: int = Field(0, description="Total registered services")
    services_by_type: Dict[str, int] = Field(default_factory=dict, description="Count by service type")
    handlers: Dict[str, Dict[str, List[ServiceProviderInfo]]] = Field(
        default_factory=dict, description="Handlers and their services with details"
    )
    global_services: Optional[Dict[str, List[ServiceProviderInfo]]] = Field(
        None, description="Global services not tied to specific handlers"
    )
    healthy_services: int = Field(0, description="Number of healthy services")
    circuit_breaker_states: Dict[str, str] = Field(
        default_factory=dict, description="Circuit breaker states by service"
    )
    error: Optional[str] = Field(None, description="Error message if query failed")


class WAPublicKeyMap(BaseModel):
    """Map of Wise Authority IDs to their public keys."""

    keys: Dict[str, str] = Field(
        default_factory=dict, description="Mapping of WA ID to Ed25519 public key (PEM format)"
    )

    def add_key(self, wa_id: str, public_key_pem: str) -> None:
        """Add a WA public key."""
        self.keys[wa_id] = public_key_pem

    def get_key(self, wa_id: str) -> Optional[str]:
        """Get a WA public key by ID."""
        return self.keys.get(wa_id)

    def has_key(self, wa_id: str) -> bool:
        """Check if a WA ID has a registered key."""
        return wa_id in self.keys

    def clear(self) -> None:
        """Clear all keys."""
        self.keys.clear()

    def count(self) -> int:
        """Get the number of registered keys."""
        return len(self.keys)


class ConfigBackupData(BaseModel):
    """Data structure for configuration backups."""

    configs: ConfigDict = Field(..., description="Backed up configuration values")
    backup_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When the backup was created"
    )
    backup_version: str = Field(..., description="Version of the configuration")
    backup_by: str = Field("RuntimeControlService", description="Who created the backup")

    def to_config_value(self) -> SerializedModel:
        """Convert to a format suitable for storage as a config value."""
        return {
            "configs": self.configs,
            "backup_timestamp": self.backup_timestamp.isoformat(),
            "backup_version": self.backup_version,
            "backup_by": self.backup_by,
        }

    @classmethod
    def from_config_value(cls, data: SerializedModel) -> "ConfigBackupData":
        """Create from a stored config value."""
        return cls(
            configs=data.get("configs", {}),
            backup_timestamp=datetime.fromisoformat(data["backup_timestamp"]),
            backup_version=data["backup_version"],
            backup_by=data.get("backup_by", "RuntimeControlService"),
        )


class ProcessingQueueItem(BaseModel):
    """
    Information about an item in the processing queue.
    Used for runtime control service to report queue status.
    """

    item_id: str = Field(..., description="Unique identifier for the queue item")
    item_type: str = Field(..., description="Type of item (e.g., thought, task, message)")
    priority: int = Field(0, description="Processing priority (higher = more urgent)")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(None, description="When processing started")
    status: str = Field("pending", description="Item status: pending, processing, completed, failed")
    source: Optional[str] = Field(None, description="Source of the queue item")
    metadata: Dict[str, str | int | float | bool] = Field(default_factory=dict, description="Additional item metadata")


class QueuedThought(BaseModel):
    """A thought queued for processing in the next round."""

    thought_id: str = Field(..., description="Unique thought ID")
    thought_type: str = Field(..., description="Type of thought")
    source_task_id: str = Field(..., description="Source task ID")
    task_description: str = Field(..., description="Task description")
    created_at: datetime = Field(..., description="When thought was created")
    priority: int = Field(0, description="Processing priority")
    status: str = Field(..., description="Current status")


class QueuedTask(BaseModel):
    """A task that may generate thoughts."""

    task_id: str = Field(..., description="Unique task ID")
    description: str = Field(..., description="Task description")
    status: str = Field(..., description="Task status")
    channel_id: str = Field(..., description="Source channel")
    created_at: datetime = Field(..., description="When task was created")
    thoughts_generated: int = Field(0, description="Number of thoughts generated")


class ThoughtInPipeline(BaseModel):
    """Tracks a thought's position in the processing pipeline."""

    thought_id: str = Field(..., description="Unique thought ID")
    task_id: str = Field(..., description="Source task ID")
    thought_type: str = Field(..., description="Type of thought")
    current_step: StepPoint = Field(..., description="Current step point in pipeline")
    last_completed_step: Optional[StepPoint] = Field(None, description="Last completed step point")
    entered_step_at: datetime = Field(..., description="When thought entered current step")
    processing_time_ms: float = Field(0.0, description="Total processing time so far")

    # Data accumulated at each step - using existing schemas
    context_built: Optional[DMAContext] = Field(None, description="Context built for DMAs")
    ethical_dma: Optional[EthicalDMAResult] = Field(None, description="Ethical DMA result")
    common_sense_dma: Optional[CSDMAResult] = Field(None, description="Common sense DMA result")
    domain_dma: Optional[DSDMAResult] = Field(None, description="Domain DMA result")
    aspdma_result: Optional[ActionSelectionDMAResult] = Field(None, description="ASPDMA result")
    conscience_results: Optional[List[ConscienceResult]] = Field(None, description="Conscience evaluations")
    selected_action: Optional[str] = Field(None, description="Final selected action")
    handler_result: Optional[HandlerResult] = Field(None, description="Handler execution result")
    bus_operations: Optional[List[str]] = Field(None, description="Bus operations performed")

    # Tracking recursion
    is_recursive: bool = Field(False, description="Whether in recursive ASPDMA")
    recursion_count: int = Field(0, description="Number of ASPDMA recursions")


def _create_empty_pipeline_steps() -> Dict[str, List["ThoughtInPipeline"]]:
    """Create empty pipeline step dictionary with proper typing."""
    return {step.value: [] for step in StepPoint}


class PipelineState(BaseModel):
    """Complete state of the processing pipeline."""

    is_paused: bool = Field(False, description="Whether pipeline is paused")
    current_round: int = Field(0, description="Current processing round")

    # Thoughts at each step point
    thoughts_by_step: Dict[str, List[ThoughtInPipeline]] = Field(
        default_factory=_create_empty_pipeline_steps,
        description="Thoughts grouped by their current step point",
    )

    # Queues
    task_queue: List[QueuedTask] = Field(default_factory=list, description="Tasks waiting to generate thoughts")
    thought_queue: List[QueuedThought] = Field(default_factory=list, description="Thoughts waiting to enter pipeline")

    # Metrics
    total_thoughts_processed: int = Field(0, description="Total thoughts processed")
    total_thoughts_in_flight: int = Field(0, description="Thoughts currently in pipeline")

    def get_thoughts_at_step(self, step: StepPoint) -> List[ThoughtInPipeline]:
        """Get all thoughts at a specific step point."""
        return self.thoughts_by_step.get(step.value, [])

    def move_thought(self, thought_id: str, from_step: StepPoint, to_step: StepPoint) -> bool:
        """Move a thought from one step to another."""
        from_list = self.thoughts_by_step.get(from_step.value, [])
        thought = next((t for t in from_list if t.thought_id == thought_id), None)
        if thought:
            from_list.remove(thought)
            thought.current_step = to_step
            thought.entered_step_at = datetime.now(timezone.utc)
            self.thoughts_by_step.setdefault(to_step.value, []).append(thought)
            return True
        return False

    def get_next_step(self, current_step: StepPoint) -> Optional[StepPoint]:
        """Get the next step in the pipeline."""
        steps = list(StepPoint)
        try:
            current_idx = steps.index(current_step)
            if current_idx < len(steps) - 1:
                return steps[current_idx + 1]
        except ValueError:
            pass
        return None


class ThoughtProcessingResult(BaseModel):
    """Result from processing a thought through the full pipeline."""

    thought_id: str = Field(..., description="Unique thought ID")
    task_id: str = Field(..., description="Source task ID")
    thought_type: str = Field(..., description="Type of thought")

    # Handler execution result
    handler_type: str = Field(..., description="Handler that processed the action")
    handler_success: bool = Field(..., description="Whether handler succeeded")
    handler_message: Optional[str] = Field(None, description="Handler result message")
    handler_error: Optional[str] = Field(None, description="Handler error if failed")

    # Bus operations performed
    bus_operations: List[str] = Field(
        default_factory=list, description="Bus operations performed (e.g., 'memory_stored', 'message_sent')"
    )

    # Timing
    total_processing_time_ms: float = Field(..., description="Total processing time")
    dma_time_ms: Optional[float] = Field(None, description="DMA processing time")
    conscience_time_ms: Optional[float] = Field(None, description="Conscience processing time")
    handler_time_ms: Optional[float] = Field(None, description="Handler execution time")

    # Final status
    final_status: str = Field(..., description="Final thought status")

    # Tasks selected for processing
    tasks_to_process: List[QueuedTask] = Field(
        default_factory=list, description="Tasks selected for thought generation"
    )

    # Tasks deferred or skipped
    tasks_deferred: List[Dict[str, str]] = Field(default_factory=list, description="Tasks deferred with reasons")

    # Selection criteria used
    selection_criteria: TaskSelectionCriteria = Field(
        default_factory=TaskSelectionCriteria,
        description="Criteria used to select tasks (priority, age, channel, etc.)",
    )

    # Metrics
    total_pending_tasks: int = Field(0)
    total_active_tasks: int = Field(0)
    tasks_selected_count: int = Field(0)
    processing_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultStartRound(BaseModel):
    """Result from START_ROUND step - moves thoughts from PENDING to PROCESSING."""

    step_point: StepPoint = Field(StepPoint.START_ROUND)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    # Round start specific data
    thoughts_processed: int = Field(..., description="Number of thoughts processed in this step")
    round_started: bool = Field(..., description="Whether round was successfully started")

    error: Optional[str] = Field(None)


class StepResultGatherContext(BaseModel):
    """Result from GATHER_CONTEXT step - builds context for DMA processing."""

    step_point: StepPoint = Field(StepPoint.GATHER_CONTEXT)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    # Additional context-specific fields
    context_size: Optional[int] = Field(None, description="Number of context items gathered")
    summary: Optional[str] = Field(None, description="Summary of context gathering process")
    thought_content: Optional[str] = Field(None, description="Content of the thought")
    thought_type: str = Field(default="standard", description="Type of thought being processed")

    error: Optional[str] = Field(None)


class StepResultPerformDMAs(BaseModel):
    """Result from PERFORM_DMAS step - parallel execution of base DMAs."""

    step_point: StepPoint = Field(StepPoint.PERFORM_DMAS)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    context: str = Field(..., description="Thought context from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


# Using the existing ConscienceResult schema instead of creating ConscienceEvaluation


class StepResultPerformASPDMA(BaseModel):
    """Result from PERFORM_ASPDMA step - action selection DMA execution."""

    step_point: StepPoint = Field(StepPoint.PERFORM_ASPDMA)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    dma_results: Optional[str] = Field(None, description="DMA results from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


class StepResultConscienceExecution(BaseModel):
    """Result from CONSCIENCE_EXECUTION step - parallel conscience checks."""

    step_point: StepPoint = Field(StepPoint.CONSCIENCE_EXECUTION)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    selected_action: str = Field(..., description="Selected action from SUT")
    action_result: Optional[str] = Field(None, description="Action result from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


class StepResultRecursiveASPDMA(BaseModel):
    """Result from RECURSIVE_ASPDMA step - retry after conscience failure."""

    step_point: StepPoint = Field(StepPoint.RECURSIVE_ASPDMA)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    retry_reason: str = Field(..., description="Retry reason from SUT")
    original_action: str = Field(..., description="Original action from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


class StepResultRecursiveConscience(BaseModel):
    """Result from RECURSIVE_CONSCIENCE step - recheck after recursive ASPDMA."""

    step_point: StepPoint = Field(StepPoint.RECURSIVE_CONSCIENCE)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    retry_action: str = Field(..., description="Retry action from SUT")
    retry_result: Optional[str] = Field(None, description="Retry result from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


class StepResultFinalizeAction(BaseModel):
    """Result from FINALIZE_ACTION step - final action determined."""

    step_point: StepPoint = Field(StepPoint.FINALIZE_ACTION)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    selected_action: str = Field(..., description="Selected action from SUT")
    conscience_passed: bool = Field(..., description=DESC_CONSCIENCE_PASSED)
    conscience_override_reason: Optional[str] = Field(None, description=DESC_CONSCIENCE_OVERRIDE_REASON)
    epistemic_data: EpistemicData = Field(..., description="Rich conscience evaluation data")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


class StepResultPerformAction(BaseModel):
    """Result from PERFORM_ACTION step - action dispatch begins."""

    step_point: StepPoint = Field(StepPoint.PERFORM_ACTION)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: Optional[str] = Field(None, description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    selected_action: str = Field(..., description="Selected action from SUT")
    action_parameters: Optional[str] = Field(None, description="Action parameters from SUT")
    dispatch_context: str = Field(..., description="Dispatch context from SUT")

    error: Optional[str] = Field(None)


class StepResultActionComplete(BaseModel):
    """Result from ACTION_COMPLETE step - action execution completed with audit trail."""

    step_point: StepPoint = Field(StepPoint.ACTION_COMPLETE)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: Optional[str] = Field(None, description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    action_executed: str = Field(..., description="Action executed from SUT")
    dispatch_success: bool = Field(..., description="Dispatch success from SUT")
    execution_time_ms: float = Field(..., description="Execution time from SUT")
    handler_completed: bool = Field(..., description="Handler completed from SUT")
    follow_up_processing_pending: bool = Field(..., description="Follow-up processing pending from SUT")
    audit_entry_id: Optional[str] = Field(None, description="ID of audit entry for this action")
    audit_sequence_number: Optional[int] = Field(None, description=DESC_AUDIT_SEQUENCE)
    audit_entry_hash: Optional[str] = Field(None, description=DESC_AUDIT_HASH)
    audit_signature: Optional[str] = Field(None, description=DESC_AUDIT_SIGNATURE)


class StepResultRoundComplete(BaseModel):
    """Result from ROUND_COMPLETE step - processing round completed."""

    step_point: StepPoint = Field(StepPoint.ROUND_COMPLETE)
    success: bool = Field(..., description="Whether step succeeded")

    # EXACT data from SUT step_data dict
    timestamp: Optional[str] = Field(None, description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")
    round_status: str = Field(..., description="Round completion status from SUT")
    thoughts_processed: int = Field(..., description="Number of thoughts processed from SUT")

    error: Optional[str] = Field(None)


# Union type for all step results
StepResultUnion = (
    StepResultGatherContext
    | StepResultPerformDMAs
    | StepResultPerformASPDMA
    | StepResultConscienceExecution
    | StepResultRecursiveASPDMA
    | StepResultRecursiveConscience
    | StepResultFinalizeAction
    | StepResultPerformAction
    | StepResultActionComplete
)


# Step Data Schemas for type-safe step processing


class BaseStepData(BaseModel):
    """Base step data with common fields for all steps."""

    timestamp: str = Field(..., description="ISO timestamp when step started")
    thought_id: str = Field(..., description="Unique thought identifier")
    task_id: Optional[str] = Field(None, description="Source task identifier")
    processing_time_ms: float = Field(..., description="Step processing time in milliseconds")
    success: bool = Field(True, description="Whether step completed successfully")
    error: Optional[str] = Field(None, description="Error message if step failed")


class StartRoundStepData(BaseStepData):
    """Step data for START_ROUND step."""

    thoughts_processed: int = Field(..., description="Number of thoughts to process in round")
    round_started: bool = Field(True, description="Round initiation flag")


class GatherContextStepData(BaseStepData):
    """Step data for GATHER_CONTEXT step."""

    context: str = Field(..., description="Built context data for DMA processing")


class PerformDMAsStepData(BaseStepData):
    """Step data for PERFORM_DMAS step."""

    dma_results: str = Field(..., description="Results from DMA processing")
    context: str = Field(..., description="Initial context for DMA processing")


class PerformASPDMAStepData(BaseStepData):
    """Step data for PERFORM_ASPDMA step."""

    selected_action: str = Field(..., description="Action selected by ASPDMA")
    action_rationale: str = Field(..., description="Rationale for action selection")
    dma_results: Optional[str] = Field(None, description="DMA results string summary from previous PERFORM_DMAS step")
    dma_results_obj: Optional[Any] = Field(None, description="Concrete InitialDMAResults object from PERFORM_DMAS step")


class ConscienceExecutionStepData(BaseStepData):
    """Step data for CONSCIENCE_EXECUTION step."""

    selected_action: str = Field(..., description="Final action after conscience check")
    action_rationale: str = Field(..., description="Rationale for the final action (REQUIRED)")
    conscience_passed: bool = Field(..., description="Whether conscience validation passed")
    action_result: str = Field(..., description="Complete action result")
    override_reason: Optional[str] = Field(None, description="Reason for conscience override if failed")
    conscience_result: ConscienceResult = Field(..., description="Complete conscience evaluation result")
    aspdma_prompt: Optional[str] = Field(None, description="User prompt passed to ASPDMA for debugging")


class RecursiveASPDMAStepData(BaseStepData):
    """Step data for RECURSIVE_ASPDMA step."""

    retry_reason: str = Field(..., description="Reason for recursive ASPDMA execution")
    original_action: str = Field(..., description="Original action that was retried")


class RecursiveConscienceStepData(BaseStepData):
    """Step data for RECURSIVE_CONSCIENCE step."""

    retry_action: str = Field(..., description="Action being retried through conscience")
    retry_result: str = Field(..., description="Result of recursive conscience check")


class FinalizeActionStepData(BaseStepData):
    """Step data for FINALIZE_ACTION step."""

    selected_action: str = Field(..., description="Final selected action")
    conscience_passed: bool = Field(..., description="Whether conscience checks passed")
    conscience_override_reason: Optional[str] = Field(None, description="Reason if conscience overrode action")
    epistemic_data: EpistemicData = Field(..., description="Rich conscience evaluation data from all checks")
    updated_status_detected: Optional[bool] = Field(
        None, description="Whether UpdatedStatusConscience detected new information during task processing"
    )


class PerformActionStepData(BaseStepData):
    """Step data for PERFORM_ACTION step."""

    selected_action: str = Field(..., description="Action being performed")
    action_parameters: str = Field("None", description="Parameters for action execution")
    dispatch_context: str = Field("{}", description="Context for action dispatch")


class ActionCompleteStepData(BaseStepData):
    """Step data for ACTION_COMPLETE step with audit trail and resource usage information."""

    action_executed: str = Field(..., description="Action that was executed")
    dispatch_success: bool = Field(..., description="Whether action dispatch succeeded")
    handler_completed: bool = Field(..., description="Whether action handler completed")
    follow_up_processing_pending: bool = Field(False, description="Whether follow-up processing needed")
    follow_up_thought_id: Optional[str] = Field(None, description="ID of follow-up thought if created")
    execution_time_ms: float = Field(0.0, description="Action execution time")
    audit_entry_id: str = Field(..., description="ID of audit entry created for this action (REQUIRED)")
    audit_sequence_number: int = Field(..., description="Sequence number in audit hash chain (REQUIRED)")
    audit_entry_hash: str = Field(..., description="Hash of audit entry - tamper-evident (REQUIRED)")
    audit_signature: str = Field(..., description="Cryptographic signature of audit entry (REQUIRED)")

    # Resource usage (queried from telemetry by thought_id)
    tokens_total: int = Field(0, description="Total tokens used (query telemetry by thought_id)")
    tokens_input: int = Field(0, description="Input tokens (query telemetry by thought_id)")
    tokens_output: int = Field(0, description="Output tokens (query telemetry by thought_id)")
    cost_cents: float = Field(0.0, description="Cost in USD cents (query telemetry by thought_id)")
    carbon_grams: float = Field(0.0, description="CO2 emissions in grams (query telemetry by thought_id)")
    energy_mwh: float = Field(0.0, description="Energy in milliwatt-hours (query telemetry by thought_id)")
    llm_calls: int = Field(0, description="Number of LLM calls (query telemetry by thought_id)")
    models_used: List[str] = Field(default_factory=list, description="Models used (query telemetry by thought_id)")


class ActionResponse(BaseModel):
    """Typed response from action dispatch."""

    success: bool = Field(..., description="Whether action dispatch succeeded")
    handler: str = Field(..., description="Handler that executed the action")
    action_type: str = Field(..., description="Type of action executed")
    follow_up_thought_id: Optional[str] = Field(None, description="ID of follow-up thought if created")
    execution_time_ms: float = Field(0.0, description="Action execution time in milliseconds")

    # Audit trail data (REQUIRED) from AuditEntryResult
    audit_data: AuditEntryResult = Field(..., description="Audit entry with hash chain data (REQUIRED)")


class RoundCompleteStepData(BaseStepData):
    """Step data for ROUND_COMPLETE step."""

    round_status: str = Field("completed", description="Status of completed round")
    thoughts_processed: int = Field(..., description="Number of thoughts processed in round")


# Union type for all step data
StepDataUnion = (
    StartRoundStepData
    | GatherContextStepData
    | PerformDMAsStepData
    | PerformASPDMAStepData
    | ConscienceExecutionStepData
    | RecursiveASPDMAStepData
    | RecursiveConscienceStepData
    | FinalizeActionStepData
    | PerformActionStepData
    | ActionCompleteStepData
    | RoundCompleteStepData
)


class StepResultData(BaseModel):
    """Complete step result data structure for streaming."""

    step_point: str = Field(..., description="Step point name")
    success: bool = Field(True, description="Whether step succeeded")
    processing_time_ms: float = Field(0.0, description="Step processing time")
    thought_id: str = Field("", description="Thought identifier")
    task_id: str = Field("", description="Task identifier")
    step_data: StepDataUnion = Field(..., description="Typed step data")
    trace_context: TraceContext = Field(..., description="OTLP trace context")
    span_attributes: List[SpanAttribute] = Field(..., description="OTLP span attributes")
    otlp_compatible: bool = Field(True, description="OTLP compatibility flag")


class StepExecutionResult(BaseModel):
    """Result from executing a single step for a paused thought."""

    success: bool = Field(..., description="Whether step execution succeeded")
    thought_id: str = Field(..., description="Thought identifier")
    message: Optional[str] = Field(None, description="Success message")
    error: Optional[str] = Field(None, description="Error message if failed")


class AllStepsExecutionResult(BaseModel):
    """Result from executing steps for all paused thoughts."""

    success: bool = Field(..., description="Whether execution succeeded")
    thoughts_advanced: int = Field(0, description="Number of thoughts advanced")
    message: Optional[str] = Field(None, description="Result message")
    error: Optional[str] = Field(None, description="Error message if failed")


# ============================================================================
# Simplified Reasoning Stream Event Results (6 clear events, no UI metadata)
# ============================================================================


class ThoughtStartEvent(BaseModel):
    """Event 0: Thought begins processing - thought and task metadata (START_ROUND step)."""

    event_type: ReasoningEvent = Field(ReasoningEvent.THOUGHT_START)
    thought_id: str = Field(..., description=DESC_THOUGHT_ID)
    task_id: str = Field(..., description="Source task identifier")
    timestamp: str = Field(..., description=DESC_TIMESTAMP)

    # Thought metadata
    thought_type: str = Field(..., description="Type of thought (standard, pondering, etc)")
    thought_content: str = Field(..., description="Thought content/reasoning")
    thought_status: str = Field(..., description="Current thought status")
    round_number: int = Field(..., description="Processing round")
    thought_depth: int = Field(0, description="Pondering depth if applicable")
    parent_thought_id: Optional[str] = Field(None, description="Parent thought if pondering")

    # Task metadata (context for the thought)
    task_description: str = Field(..., description="What needs to be done")
    task_priority: int = Field(..., description="Priority 0-10")
    channel_id: str = Field(..., description="Channel where task originated")
    updated_info_available: bool = Field(False, description="Whether task has updated information")


class SnapshotAndContextResult(BaseModel):
    """Event 1: System snapshot (GATHER_CONTEXT step).

    The system_snapshot field contains all context data in structured form.
    The redundant context string field has been removed to eliminate duplication.
    """

    event_type: ReasoningEvent = Field(ReasoningEvent.SNAPSHOT_AND_CONTEXT)
    thought_id: str = Field(..., description=DESC_THOUGHT_ID)
    task_id: Optional[str] = Field(None, description=DESC_PARENT_TASK)
    timestamp: str = Field(..., description=DESC_TIMESTAMP)

    # System snapshot - contains all context data
    system_snapshot: SystemSnapshot = Field(..., description="Current system state with all context data")


class DMAResultsEvent(BaseModel):
    """Event 2: Results from all 3 DMA perspectives (PERFORM_DMAS step)."""

    event_type: ReasoningEvent = Field(ReasoningEvent.DMA_RESULTS)
    thought_id: str = Field(..., description=DESC_THOUGHT_ID)
    task_id: Optional[str] = Field(None, description=DESC_PARENT_TASK)
    timestamp: str = Field(..., description=DESC_TIMESTAMP)

    # All 3 DMA results - strongly typed, non-optional
    csdma: CSDMAResult = Field(..., description="Common Sense DMA result")
    dsdma: DSDMAResult = Field(..., description="Domain Specific DMA result")
    pdma: EthicalDMAResult = Field(..., description="Ethical Perspective DMA result (PDMA)")

    # User prompts passed to each DMA (for debugging/transparency)
    csdma_prompt: Optional[str] = Field(None, description="User prompt passed to CSDMA")
    dsdma_prompt: Optional[str] = Field(None, description="User prompt passed to DSDMA")
    pdma_prompt: Optional[str] = Field(None, description="User prompt passed to PDMA")


class ASPDMAResultEvent(BaseModel):
    """Event 3: Selected action and rationale (PERFORM_ASPDMA + RECURSIVE_ASPDMA steps)."""

    event_type: ReasoningEvent = Field(ReasoningEvent.ASPDMA_RESULT)
    thought_id: str = Field(..., description=DESC_THOUGHT_ID)
    task_id: Optional[str] = Field(None, description=DESC_PARENT_TASK)
    timestamp: str = Field(..., description=DESC_TIMESTAMP)
    is_recursive: bool = Field(False, description="Whether this is a recursive ASPDMA after conscience override")

    # ASPDMA selection
    selected_action: str = Field(..., description="Action selected by ASPDMA")
    action_rationale: str = Field(..., description="Rationale for selection")

    # User prompt passed to ASPDMA (for debugging/transparency)
    aspdma_prompt: Optional[str] = Field(None, description="User prompt passed to ASPDMA")


class ConscienceResultEvent(BaseModel):
    """Event 4: Conscience evaluation and final action (CONSCIENCE_EXECUTION + RECURSIVE_CONSCIENCE + FINALIZE_ACTION steps)."""

    event_type: ReasoningEvent = Field(ReasoningEvent.CONSCIENCE_RESULT)
    thought_id: str = Field(..., description=DESC_THOUGHT_ID)
    task_id: Optional[str] = Field(None, description=DESC_PARENT_TASK)
    timestamp: str = Field(..., description=DESC_TIMESTAMP)
    is_recursive: bool = Field(False, description="Whether this is a recursive conscience check after override")

    # Conscience evaluation
    conscience_passed: bool = Field(..., description=DESC_CONSCIENCE_PASSED)
    conscience_override_reason: Optional[str] = Field(None, description=DESC_CONSCIENCE_OVERRIDE_REASON)
    epistemic_data: EpistemicData = Field(..., description="Rich conscience evaluation data from all checks")

    # Final action
    final_action: str = Field(..., description="Final action after conscience evaluation")
    action_was_overridden: bool = Field(..., description="Whether conscience changed the action")

    # UpdatedStatusConscience detection
    updated_status_available: Optional[bool] = Field(
        None, description="Whether UpdatedStatusConscience detected new information during task processing"
    )


class ActionResultEvent(BaseModel):
    """Event 5: Action execution outcome with audit trail and resource usage (ACTION_COMPLETE step)."""

    event_type: ReasoningEvent = Field(ReasoningEvent.ACTION_RESULT)
    thought_id: str = Field(..., description=DESC_THOUGHT_ID)
    task_id: Optional[str] = Field(None, description=DESC_PARENT_TASK)
    timestamp: str = Field(..., description=DESC_TIMESTAMP)

    # Action execution
    action_executed: str = Field(..., description="Action that was executed")
    execution_success: bool = Field(..., description="Whether execution succeeded")
    execution_time_ms: float = Field(..., description="Execution time in milliseconds")
    follow_up_thought_id: Optional[str] = Field(None, description="Follow-up thought created if any")
    error: Optional[str] = Field(None, description="Error message if execution failed")

    # Audit trail (tamper-evident)
    audit_entry_id: Optional[str] = Field(None, description="ID of audit entry for this action")
    audit_sequence_number: Optional[int] = Field(None, description=DESC_AUDIT_SEQUENCE)
    audit_entry_hash: Optional[str] = Field(None, description=DESC_AUDIT_HASH)
    audit_signature: Optional[str] = Field(None, description=DESC_AUDIT_SIGNATURE)

    # Resource usage (queried from telemetry by thought_id)
    tokens_total: int = Field(0, description="Total tokens used for this thought")
    tokens_input: int = Field(0, description="Input tokens used for this thought")
    tokens_output: int = Field(0, description="Output tokens used for this thought")
    cost_cents: float = Field(0.0, description="Total cost in USD cents for this thought")
    carbon_grams: float = Field(0.0, description="CO2 emissions in grams for this thought")
    energy_mwh: float = Field(0.0, description="Energy used in milliwatt-hours for this thought")
    llm_calls: int = Field(0, description="Number of LLM calls for this thought")
    models_used: List[str] = Field(default_factory=list, description="Unique models used for this thought")
