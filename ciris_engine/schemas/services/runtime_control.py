"""
Runtime control service schemas for type-safe operations.

This module provides Pydantic models to replace Dict[str, Any] usage
in the runtime control service, ensuring full type safety and validation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.conscience.results import ConscienceResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.processors.states import AgentState


class StepPoint(str, Enum):
    """Points where single-stepping can pause in the pipeline."""

    # Pipeline step points in execution order
    FINALIZE_TASKS_QUEUE = "finalize_tasks_queue"  # Finalize which tasks to process
    POPULATE_THOUGHT_QUEUE = "populate_thought_queue"  # Generate thoughts from tasks
    POPULATE_ROUND = "populate_round"  # Select thoughts for this round
    BUILD_CONTEXT = "build_context"  # Build context for DMAs
    PERFORM_DMAS = "perform_dmas"  # Execute parallel DMAs (ethical, common sense, domain)
    PERFORM_ASPDMA = "perform_aspdma"  # Execute ASPDMA (may recurse)
    CONSCIENCE_EXECUTION = "conscience_execution"  # Parallel conscience checks on ASPDMA result
    RECURSIVE_ASPDMA = "recursive_aspdma"  # If conscience failed, retry ASPDMA
    RECURSIVE_CONSCIENCE = "recursive_conscience"  # Conscience check on recursive ASPDMA
    ACTION_SELECTION = "action_selection"  # Final action selection
    HANDLER_START = "handler_start"  # Handler execution begins
    BUS_OUTBOUND = "bus_outbound"  # Bus processing outbound messages
    PACKAGE_HANDLING = "package_handling"  # Package handling at edge (adapters)
    BUS_INBOUND = "bus_inbound"  # Bus processing inbound results
    HANDLER_COMPLETE = "handler_complete"  # Handler execution completes


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


class ConfigValueMap(BaseModel):
    """Typed map for configuration values."""

    configs: Dict[str, Union[str, int, float, bool, list, dict]] = Field(
        default_factory=dict, description="Configuration key-value pairs with typed values"
    )

    def get(
        self, key: str, default: Optional[Union[str, int, float, bool, list, dict]] = None
    ) -> Optional[Union[str, int, float, bool, list, dict]]:
        """Get a configuration value with optional default."""
        return self.configs.get(key, default)

    def set(self, key: str, value: Union[str, int, float, bool, list, dict]) -> None:
        """Set a configuration value."""
        self.configs[key] = value

    def update(self, values: Dict[str, Union[str, int, float, bool, list, dict]]) -> None:
        """Update multiple configuration values."""
        self.configs.update(values)

    def keys(self) -> List[str]:
        """Get all configuration keys."""
        return list(self.configs.keys())

    def items(self) -> List[tuple]:
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
    capabilities: Optional[Dict[str, Union[str, int, float, bool, list]]] = Field(
        None, description="Provider capabilities"
    )
    metadata: Optional[Dict[str, Union[str, int, float, bool]]] = Field(None, description="Provider metadata")
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

    configs: Dict[str, Union[str, int, float, bool, list, dict]] = Field(
        ..., description="Backed up configuration values"
    )
    backup_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When the backup was created"
    )
    backup_version: str = Field(..., description="Version of the configuration")
    backup_by: str = Field("RuntimeControlService", description="Who created the backup")

    def to_config_value(self) -> dict:
        """Convert to a format suitable for storage as a config value."""
        return {
            "configs": self.configs,
            "backup_timestamp": self.backup_timestamp.isoformat(),
            "backup_version": self.backup_version,
            "backup_by": self.backup_by,
        }

    @classmethod
    def from_config_value(cls, data: dict) -> "ConfigBackupData":
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
    metadata: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional item metadata"
    )


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
    entered_step_at: datetime = Field(..., description="When thought entered current step")
    processing_time_ms: float = Field(0.0, description="Total processing time so far")

    # Data accumulated at each step - using existing schemas
    context_built: Optional[Dict[str, Any]] = Field(None, description="Context built for DMAs")
    ethical_dma: Optional[EthicalDMAResult] = Field(None, description="Ethical DMA result")
    common_sense_dma: Optional[CSDMAResult] = Field(None, description="Common sense DMA result")
    domain_dma: Optional[DSDMAResult] = Field(None, description="Domain DMA result")
    aspdma_result: Optional[ActionSelectionDMAResult] = Field(None, description="ASPDMA result")
    conscience_results: Optional[List[ConscienceResult]] = Field(None, description="Conscience evaluations")
    selected_action: Optional[str] = Field(None, description="Final selected action")
    handler_result: Optional[Dict[str, Any]] = Field(None, description="Handler execution result")
    bus_operations: Optional[List[str]] = Field(None, description="Bus operations performed")

    # Tracking recursion
    is_recursive: bool = Field(False, description="Whether in recursive ASPDMA")
    recursion_count: int = Field(0, description="Number of ASPDMA recursions")


class PipelineState(BaseModel):
    """Complete state of the processing pipeline."""

    is_paused: bool = Field(False, description="Whether pipeline is paused")
    current_round: int = Field(0, description="Current processing round")

    # Thoughts at each step point
    thoughts_by_step: Dict[str, List[ThoughtInPipeline]] = Field(
        default_factory=lambda: {step.value: [] for step in StepPoint},
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


class StepResultFinalizeTasksQueue(BaseModel):
    """Result from FINALIZE_TASKS_QUEUE step - determines which tasks to process."""

    step_point: StepPoint = Field(StepPoint.FINALIZE_TASKS_QUEUE)
    success: bool = Field(..., description="Whether step succeeded")
    round_number: int = Field(..., description="Current round number")
    current_state: AgentState = Field(..., description="Current agent state")

    # Tasks selected for processing
    tasks_to_process: List[QueuedTask] = Field(
        default_factory=list, description="Tasks selected for thought generation"
    )

    # Tasks deferred or skipped
    tasks_deferred: List[Dict[str, str]] = Field(default_factory=list, description="Tasks deferred with reasons")

    # Selection criteria used
    selection_criteria: Dict[str, Any] = Field(
        default_factory=dict, description="Criteria used to select tasks (priority, age, channel, etc.)"
    )

    # Metrics
    total_pending_tasks: int = Field(0)
    total_active_tasks: int = Field(0)
    tasks_selected_count: int = Field(0)
    processing_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultPopulateThoughtQueue(BaseModel):
    """Result from POPULATE_THOUGHT_QUEUE step - generates thoughts from tasks."""

    step_point: StepPoint = Field(StepPoint.POPULATE_THOUGHT_QUEUE)
    success: bool = Field(..., description="Whether step succeeded")
    round_number: int = Field(..., description="Current round number")

    # Thoughts generated
    thoughts_generated: List[QueuedThought] = Field(
        default_factory=list, description="New thoughts generated from tasks"
    )

    # Task to thought mapping
    task_thought_mapping: Dict[str, List[str]] = Field(
        default_factory=dict, description="Mapping of task_id to generated thought_ids"
    )

    # Generation statistics
    thoughts_per_task: Dict[str, int] = Field(default_factory=dict)
    generation_errors: List[Dict[str, str]] = Field(default_factory=list)

    # Metrics
    total_thoughts_generated: int = Field(0)
    processing_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultPopulateRound(BaseModel):
    """Result from POPULATE_ROUND step - selects thoughts for this processing round."""

    step_point: StepPoint = Field(StepPoint.POPULATE_ROUND)
    success: bool = Field(..., description="Whether step succeeded")
    round_number: int = Field(..., description="Current round number")

    # Selected thoughts for this round
    thoughts_for_round: List[ThoughtInPipeline] = Field(
        default_factory=list, description="Thoughts selected for processing this round"
    )

    # Thoughts deferred to next round
    thoughts_deferred: List[Dict[str, str]] = Field(default_factory=list, description="Thoughts deferred with reasons")

    # Selection parameters
    batch_size: int = Field(0, description="Batch size used")
    priority_threshold: Optional[int] = Field(None)

    # Queue state
    remaining_in_queue: int = Field(0)
    processing_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultBuildContext(BaseModel):
    """Result from BUILD_CONTEXT step - builds context for DMA processing."""

    step_point: StepPoint = Field(StepPoint.BUILD_CONTEXT)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Context components built
    system_snapshot: Dict[str, Any] = Field(..., description="System state captured")
    agent_identity: Dict[str, Any] = Field(..., description="Agent identity data")
    thought_context: Dict[str, Any] = Field(..., description="Full thought context")
    channel_context: Optional[Dict[str, Any]] = Field(None)
    memory_context: Optional[Dict[str, Any]] = Field(None)

    # Permissions and constraints
    permitted_actions: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)

    # Metrics
    context_size_bytes: int = Field(0)
    memory_queries_performed: int = Field(0)
    processing_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultPerformDMAs(BaseModel):
    """Result from PERFORM_DMAS step - parallel execution of base DMAs."""

    step_point: StepPoint = Field(StepPoint.PERFORM_DMAS)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # DMA results (run in parallel) - using existing schemas
    ethical_dma: Optional[EthicalDMAResult] = Field(None, description="Ethical DMA result")
    common_sense_dma: Optional[CSDMAResult] = Field(None, description="Common sense DMA result")
    domain_dma: Optional[DSDMAResult] = Field(None, description="Domain-specific DMA result")

    # Execution details
    dmas_executed: List[str] = Field(default_factory=list)
    dma_failures: List[Dict[str, str]] = Field(default_factory=list)

    # Timing (parallel execution)
    longest_dma_time_ms: float = Field(0.0, description="Longest DMA execution time")
    total_time_ms: float = Field(0.0, description="Total parallel execution time")

    error: Optional[str] = Field(None)


# Using the existing ConscienceResult schema instead of creating ConscienceEvaluation


class StepResultPerformASPDMA(BaseModel):
    """Result from PERFORM_ASPDMA step - action selection DMA execution."""

    step_point: StepPoint = Field(StepPoint.PERFORM_ASPDMA)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # ASPDMA prompt and response
    prompt_text: str = Field(..., description="Full prompt sent to LLM")
    llm_model: str = Field(..., description="Model used")
    raw_response: str = Field(..., description="Raw LLM response")

    # Parsed result - using existing schema
    aspdma_result: ActionSelectionDMAResult = Field(..., description="ASPDMA result with action and parameters")

    # LLM metrics
    tokens_used: Optional[int] = Field(None)
    retry_count: int = Field(0)
    processing_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultConscienceExecution(BaseModel):
    """Result from CONSCIENCE_EXECUTION step - parallel conscience checks."""

    step_point: StepPoint = Field(StepPoint.CONSCIENCE_EXECUTION)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Action being evaluated - from ASPDMA result
    aspdma_result: ActionSelectionDMAResult = Field(..., description="ASPDMA result being evaluated")

    # Conscience results (run in parallel)
    conscience_evaluations: List[ConscienceResult] = Field(default_factory=list)

    # Overall result
    all_passed: bool = Field(..., description="Whether all consciences passed")
    failures: List[str] = Field(default_factory=list, description="Failed conscience names")
    override_required: bool = Field(False)

    # Timing
    longest_conscience_time_ms: float = Field(0.0)
    total_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultRecursiveASPDMA(BaseModel):
    """Result from RECURSIVE_ASPDMA step - retry after conscience failure."""

    step_point: StepPoint = Field(StepPoint.RECURSIVE_ASPDMA)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Why we're recursing
    original_action: str = Field(..., description="Action that failed conscience")
    conscience_feedback: str = Field(..., description="Feedback from conscience")
    recursion_count: int = Field(..., description="Current recursion depth")

    # New ASPDMA attempt
    retry_prompt: str = Field(..., description="Modified prompt with conscience feedback")
    raw_response: str = Field(...)

    # New selection - using existing schema
    new_aspdma_result: ActionSelectionDMAResult = Field(..., description="New ASPDMA result after recursion")

    # Metrics
    tokens_used: Optional[int] = Field(None)
    processing_time_ms: float = Field(0.0)

    error: Optional[str] = Field(None)


class StepResultRecursiveConscience(BaseModel):
    """Result from RECURSIVE_CONSCIENCE step - recheck after recursive ASPDMA."""

    step_point: StepPoint = Field(StepPoint.RECURSIVE_CONSCIENCE)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Same structure as regular conscience but marked as recursive
    is_recursive: bool = Field(True)
    recursion_count: int = Field(...)

    aspdma_result: ActionSelectionDMAResult = Field(..., description="ASPDMA result being evaluated")
    conscience_evaluations: List[ConscienceResult] = Field(default_factory=list)

    all_passed: bool = Field(...)
    failures: List[str] = Field(default_factory=list)

    # If still failing, what happens
    final_override_to_ponder: bool = Field(False)

    processing_time_ms: float = Field(0.0)
    error: Optional[str] = Field(None)


class StepResultActionSelection(BaseModel):
    """Result from ACTION_SELECTION step - final action determined."""

    step_point: StepPoint = Field(StepPoint.ACTION_SELECTION)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Final selected action - using existing schema
    final_action_result: ActionSelectionDMAResult = Field(..., description="Final action result after all processing")

    # How we got here
    was_overridden: bool = Field(False)
    override_reason: Optional[str] = Field(None)
    recursion_performed: bool = Field(False)

    # What handler will process this
    target_handler: str = Field(..., description="Handler that will process this action")

    processing_time_ms: float = Field(0.0)
    error: Optional[str] = Field(None)


class StepResultHandlerStart(BaseModel):
    """Result from HANDLER_START step - handler begins execution."""

    step_point: StepPoint = Field(StepPoint.HANDLER_START)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Handler details
    handler_name: str = Field(..., description="Handler executing")
    action_type: str = Field(...)
    action_parameters: Dict[str, Any] = Field(...)

    # Handler context prepared
    handler_context: Dict[str, Any] = Field(...)

    # What we expect
    expected_bus_operations: List[str] = Field(default_factory=list)

    processing_time_ms: float = Field(0.0)
    error: Optional[str] = Field(None)


class StepResultBusOutbound(BaseModel):
    """Result from BUS_OUTBOUND step - messages sent to buses."""

    step_point: StepPoint = Field(StepPoint.BUS_OUTBOUND)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Bus operations
    buses_called: List[str] = Field(default_factory=list, description="Buses invoked")

    # Outbound messages
    communication_bus: Optional[Dict[str, Any]] = Field(None, description="Message sent to comms")
    memory_bus: Optional[Dict[str, Any]] = Field(None, description="Data sent to memory")
    tool_bus: Optional[Dict[str, Any]] = Field(None, description="Tool invocation")

    # Async tracking
    operations_initiated: List[str] = Field(default_factory=list)
    awaiting_responses: List[str] = Field(default_factory=list)

    processing_time_ms: float = Field(0.0)
    error: Optional[str] = Field(None)


class StepResultPackageHandling(BaseModel):
    """Result from PACKAGE_HANDLING step - edge adapter processing."""

    step_point: StepPoint = Field(StepPoint.PACKAGE_HANDLING)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Adapter handling
    adapter_name: str = Field(..., description="Adapter handling the package")
    package_type: str = Field(..., description="Type of package (message, tool call, etc.)")

    # External operations
    external_service_called: Optional[str] = Field(None)
    external_response_received: Optional[bool] = Field(None)

    # Transformation
    package_transformed: bool = Field(False)
    transformation_details: Optional[Dict[str, Any]] = Field(None)

    processing_time_ms: float = Field(0.0)
    error: Optional[str] = Field(None)


class StepResultBusInbound(BaseModel):
    """Result from BUS_INBOUND step - responses from buses."""

    step_point: StepPoint = Field(StepPoint.BUS_INBOUND)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Responses received
    responses_received: Dict[str, Any] = Field(default_factory=dict)

    # Response details
    communication_response: Optional[Dict[str, Any]] = Field(None)
    memory_response: Optional[Dict[str, Any]] = Field(None)
    tool_response: Optional[Dict[str, Any]] = Field(None)

    # Aggregation
    responses_aggregated: bool = Field(False)
    final_result: Optional[Dict[str, Any]] = Field(None)

    processing_time_ms: float = Field(0.0)
    error: Optional[str] = Field(None)


class StepResultHandlerComplete(BaseModel):
    """Result from HANDLER_COMPLETE step - handler finishes execution."""

    step_point: StepPoint = Field(StepPoint.HANDLER_COMPLETE)
    success: bool = Field(..., description="Whether step succeeded")
    thought_id: str = Field(..., description="Thought being processed")

    # Handler result
    handler_success: bool = Field(...)
    handler_message: Optional[str] = Field(None)
    handler_data: Optional[Dict[str, Any]] = Field(None)

    # Thought status update
    thought_final_status: str = Field(..., description="Final thought status")
    task_status_update: Optional[str] = Field(None, description="Task status if changed")

    # Total metrics for this thought
    total_processing_time_ms: float = Field(...)
    total_tokens_used: Optional[int] = Field(None)

    # Next steps
    triggers_new_thoughts: bool = Field(False)
    triggered_thought_ids: List[str] = Field(default_factory=list)

    error: Optional[str] = Field(None)


# Union type for all step results
StepResult = Union[
    StepResultFinalizeTasksQueue,
    StepResultPopulateThoughtQueue,
    StepResultPopulateRound,
    StepResultBuildContext,
    StepResultPerformDMAs,
    StepResultPerformASPDMA,
    StepResultConscienceExecution,
    StepResultRecursiveASPDMA,
    StepResultRecursiveConscience,
    StepResultActionSelection,
    StepResultHandlerStart,
    StepResultBusOutbound,
    StepResultPackageHandling,
    StepResultBusInbound,
    StepResultHandlerComplete,
]

# Re-export for backwards compatibility
ConscienceEvaluation = ConscienceResult


# DEPRECATED - Remove these old schemas after migration
class StepResultRoundStart(BaseModel):
    """
    Result from single-stepping at round start.
    Shows what happened in the last round and what's queued for this round.
    """

    success: bool = Field(..., description="Whether step succeeded")
    step_point: str = Field("round_start", description="Where we paused (deprecated)")
    round_number: int = Field(..., description="Current round number")
    current_state: AgentState = Field(..., description="Current agent state")

    # Results from last round
    last_round_results: List[ThoughtProcessingResult] = Field(
        default_factory=list, description="Results from thoughts processed in the last round"
    )
    last_round_summary: Dict[str, int] = Field(
        default_factory=dict, description="Summary counts (completed, failed, deferred, etc.)"
    )

    # Queue for this round
    thought_queue: List[QueuedThought] = Field(default_factory=list, description="Thoughts queued for this round")

    # Active tasks that may generate more thoughts
    active_tasks: List[QueuedTask] = Field(default_factory=list, description="Tasks currently active")
    pending_tasks: List[QueuedTask] = Field(default_factory=list, description="Tasks pending processing")

    # System metrics
    queue_depth: int = Field(0, description="Total thoughts in queue")
    active_task_count: int = Field(0, description="Number of active tasks")
    pending_task_count: int = Field(0, description="Number of pending tasks")

    # Timing
    step_duration_used: StepDuration = Field(..., description="Duration waited before building queue")
    queue_build_time_ms: float = Field(..., description="Time to build queue")

    # What happens next
    next_operation: str = Field(
        "Process thought queue through DMA and consciences", description="What will happen if we continue"
    )

    # Optional error
    error: Optional[str] = Field(None, description="Error message if failed")


class DMAExecutionContext(BaseModel):
    """Full context passed to DMAs and LLM."""

    # Core DMA input data
    thought_id: str = Field(..., description="Thought being processed")
    thought_type: str = Field(..., description="Type of thought")
    task_description: str = Field(..., description="Task description")

    # System context
    agent_identity: Dict[str, Any] = Field(..., description="Agent identity data")
    system_snapshot: Dict[str, Any] = Field(..., description="System state snapshot")
    permitted_actions: List[str] = Field(..., description="Actions agent can take")

    # Processing context
    current_thought_depth: int = Field(0, description="Number of times pondered")
    round_number: int = Field(0, description="Current round")
    channel_id: Optional[str] = Field(None, description="Source channel")


class LLMPromptData(BaseModel):
    """Data about prompts sent to LLM."""

    prompt_type: str = Field(..., description="Type of prompt (ASPDMA, conscience, etc.)")
    prompt_text: str = Field(..., description="Full prompt text sent to LLM")
    model_used: str = Field(..., description="LLM model used")
    tokens_used: Optional[int] = Field(None, description="Tokens consumed")

    # Response
    raw_response: Optional[str] = Field(None, description="Raw LLM response")
    parsed_result: Optional[Dict[str, Any]] = Field(None, description="Parsed/typed result")

    # Errors/retries
    retry_count: int = Field(0, description="Number of retries")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")

    # Timing
    response_time_ms: float = Field(..., description="LLM response time")


class StepResultPostConsciencePreHandler(BaseModel):
    """
    Result from single-stepping after conscience processing.
    Shows full DMA/LLM context and what action will be taken.
    """

    success: bool = Field(..., description="Whether step succeeded")
    step_point: str = Field("post_conscience_pre_handler", description="Where we paused (deprecated)")

    # Thought being processed
    thought_id: str = Field(..., description="Thought being processed")
    thought_type: str = Field(..., description="Type of thought")
    task_id: str = Field(..., description="Associated task ID")
    task_description: str = Field(..., description="Task description")

    # DMA Context passed to LLMBus
    dma_context: DMAExecutionContext = Field(..., description="Full context passed to DMAs")

    # DMA Results
    ethical_result: Optional[Dict[str, Any]] = Field(None, description="Ethical DMA result")
    common_sense_result: Optional[Dict[str, Any]] = Field(None, description="Common sense DMA result")
    domain_result: Optional[Dict[str, Any]] = Field(None, description="Domain DMA result")

    # ASPDMA LLM interaction
    aspdma_prompt: LLMPromptData = Field(..., description="ASPDMA prompt and response")
    aspdma_result: Dict[str, Any] = Field(..., description="Typed ASPDMA result")

    # Action selected (pre-conscience)
    initial_action: str = Field(..., description="Action initially selected")
    initial_parameters: Dict[str, Any] = Field(..., description="Initial action parameters")
    initial_rationale: str = Field(..., description="Initial selection rationale")

    # Conscience processing
    conscience_evaluations: List[ConscienceResult] = Field(
        default_factory=list, description="All conscience evaluations performed"
    )
    conscience_prompts: List[LLMPromptData] = Field(
        default_factory=list, description="Conscience prompts sent to LLM (if any)"
    )

    # Final action (post-conscience)
    final_action: str = Field(..., description="Final action after conscience")
    final_parameters: Dict[str, Any] = Field(..., description="Final action parameters")
    conscience_overridden: bool = Field(False, description="Whether conscience changed the action")
    override_reason: Optional[str] = Field(None, description="Reason for override")

    # What happens next
    next_handler: str = Field(..., description="Handler that will process this action")
    expected_bus_operations: List[str] = Field(
        default_factory=list, description="Expected bus operations (e.g., 'CommunicationBus.send', 'MemoryBus.store')"
    )

    # Timing
    total_dma_time_ms: float = Field(..., description="Total DMA processing time")
    aspdma_time_ms: float = Field(..., description="ASPDMA execution time")
    conscience_total_time_ms: float = Field(..., description="Total conscience processing time")
    total_processing_time_ms: float = Field(..., description="Total time for this thought")

    # Current state
    current_state: AgentState = Field(..., description="Current agent state")
    round_number: int = Field(..., description="Current round")

    # Errors/failures
    dma_failures: List[str] = Field(default_factory=list, description="DMA failures")
    retry_attempts: int = Field(0, description="Number of retry attempts")
    error: Optional[str] = Field(None, description="Error message if failed")
