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
    """Points where single-stepping can pause in the H3ERE pipeline."""

    # H3ERE Pipeline - 9 real step points (7 core + 2 optional recursive)
    GATHER_CONTEXT = "gather_context"  # 1) Build context for DMA processing
    PERFORM_DMAS = "perform_dmas"  # 2) Execute multi-perspective DMAs
    PERFORM_ASPDMA = "perform_aspdma"  # 3) LLM-powered action selection
    CONSCIENCE_EXECUTION = "conscience_execution"  # 4) Ethical safety validation
    RECURSIVE_ASPDMA = "recursive_aspdma"  # 3B) Optional: Re-run action selection if conscience failed
    RECURSIVE_CONSCIENCE = "recursive_conscience"  # 4B) Optional: Re-validate if recursive action failed
    FINALIZE_ACTION = "finalize_action"  # 5) Final action determination
    PERFORM_ACTION = "perform_action"  # 6) Dispatch action to handler
    ACTION_COMPLETE = "action_complete"  # 7) Action execution completed


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






class StepResultGatherContext(BaseModel):
    """Result from GATHER_CONTEXT step - builds context for DMA processing."""

    step_point: StepPoint = Field(StepPoint.GATHER_CONTEXT)
    success: bool = Field(..., description="Whether step succeeded")
    
    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    task_id: Optional[str] = Field(None, description="Task ID from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


class StepResultPerformDMAs(BaseModel):
    """Result from PERFORM_DMAS step - parallel execution of base DMAs."""

    step_point: StepPoint = Field(StepPoint.PERFORM_DMAS)
    success: bool = Field(..., description="Whether step succeeded")
    
    # EXACT data from SUT step_data dict
    timestamp: str = Field(..., description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT") 
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
    selected_action: str = Field(..., description="Selected action from SUT")
    selection_reasoning: str = Field(..., description="Selection reasoning from SUT")
    conscience_passed: bool = Field(..., description="Conscience passed from SUT")
    processing_time_ms: float = Field(..., description="Processing time from SUT")

    error: Optional[str] = Field(None)


class StepResultPerformAction(BaseModel):
    """Result from PERFORM_ACTION step - action dispatch begins."""

    step_point: StepPoint = Field(StepPoint.PERFORM_ACTION)
    success: bool = Field(..., description="Whether step succeeded")
    
    # EXACT data from SUT step_data dict
    timestamp: Optional[str] = Field(None, description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    selected_action: str = Field(..., description="Selected action from SUT")
    action_parameters: Optional[str] = Field(None, description="Action parameters from SUT")
    dispatch_context: str = Field(..., description="Dispatch context from SUT")

    error: Optional[str] = Field(None)


class StepResultActionComplete(BaseModel):
    """Result from ACTION_COMPLETE step - action execution completed."""

    step_point: StepPoint = Field(StepPoint.ACTION_COMPLETE)
    success: bool = Field(..., description="Whether step succeeded")
    
    # EXACT data from SUT step_data dict
    timestamp: Optional[str] = Field(None, description="Timestamp from SUT")
    thought_id: str = Field(..., description="Thought ID from SUT")
    action_executed: str = Field(..., description="Action executed from SUT")
    dispatch_success: bool = Field(..., description="Dispatch success from SUT")
    execution_time_ms: float = Field(..., description="Execution time from SUT")
    handler_completed: bool = Field(..., description="Handler completed from SUT")
    follow_up_processing_pending: bool = Field(..., description="Follow-up processing pending from SUT")

    error: Optional[str] = Field(None)


# Union type for all step results
StepResultUnion = Union[
    StepResultGatherContext,
    StepResultPerformDMAs, 
    StepResultPerformASPDMA,
    StepResultConscienceExecution,
    StepResultRecursiveASPDMA,
    StepResultRecursiveConscience,
    StepResultFinalizeAction,
    StepResultPerformAction,
    StepResultActionComplete,
]


