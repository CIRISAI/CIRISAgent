"""
Agent Processor Protocol - Main coordinator for all processing states.

This protocol defines the interface for the main agent processor that:
- Manages state transitions between WAKEUP, WORK, PLAY, SOLITUDE, DREAM, SHUTDOWN
- Provides runtime control (pause, resume, stop, single-step)
- Coordinates all sub-processors
- Respects RuntimeControl commands
"""

from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol

if TYPE_CHECKING:
    from ciris_engine.schemas.processors.state import StateTransitionRecord
else:
    StateTransitionRecord = Any


class ProcessingSchedule(Protocol):
    """Schedule for state transitions."""

    next_dream_time: Optional[datetime]
    dream_interval_hours: float
    work_play_ratio: float
    solitude_triggers: List[str]


class AgentProcessorMetrics(Protocol):
    """Detailed processor metrics."""

    thoughts_processed: int
    tasks_completed: int
    errors_encountered: int
    current_round: int
    state_transitions: Dict[str, int]
    average_thought_time_ms: float
    queue_depth: int
    memory_usage_mb: float


class QueueStatus(Protocol):
    """Processing queue status."""

    pending_thoughts: int
    pending_tasks: int
    active_thoughts: int
    active_tasks: int
    blocked_items: int
    priority_distribution: Dict[str, int]


class StepResult(Protocol):
    """Result of a single-step processing operation."""

    success: bool
    item_processed: Optional[str]  # thought_id or task_id
    processing_time_ms: float
    next_state: Optional[str]  # AgentState
    error: Optional[str]


class AgentProcessorProtocol(Protocol):
    """
    Protocol for the main agent processor that coordinates all states.

    This is the central coordinator that:
    - Manages the state machine (WAKEUP → WORK → PLAY → etc.)
    - Handles runtime control commands (pause, resume, stop)
    - Coordinates all sub-processors
    - Provides fine-grained control for debugging and safety

    Note: AgentProcessor IS a service (implements ServiceProtocol separately).
    This protocol defines the processor-specific behavior, not service behavior.
    The implementation should be: class AgentProcessor(AgentProcessorProtocol, ServiceProtocol)
    """

    # ========================================================================
    # STATE MANAGEMENT
    # ========================================================================

    @abstractmethod
    async def enter_state(self, state: str) -> bool:  # state: AgentState
        """
        Transition to a specific state.

        Args:
            state: Target AgentState to transition to

        Returns:
            True if transition successful, False otherwise
        """
        ...

    @abstractmethod
    def get_current_state(self) -> str:  # -> AgentState
        """
        Get current processing state.

        Returns:
            Current AgentState
        """
        ...

    @abstractmethod
    def get_processing_schedule(self) -> ProcessingSchedule:
        """
        Get schedule for state transitions.

        This includes:
        - When to enter DREAM state for memory consolidation
        - Work/Play balance ratios
        - Solitude triggers

        Returns:
            Processing schedule configuration
        """
        ...

    @abstractmethod
    async def force_state_transition(self, target_state: str, reason: str) -> bool:
        """
        Force transition to a state, bypassing normal checks.

        Args:
            target_state: Target AgentState
            reason: Reason for forced transition

        Returns:
            True if transition successful
        """
        ...

    # ========================================================================
    # RUNTIME CONTROL
    # ========================================================================

    @abstractmethod
    async def pause_processing(self) -> bool:
        """
        Pause all processing.

        Processing can be resumed with resume_processing().
        Current thought/task will complete before pausing.

        Returns:
            True if successfully paused
        """
        ...

    @abstractmethod
    async def resume_processing(self) -> bool:
        """
        Resume paused processing.

        Returns:
            True if successfully resumed
        """
        ...

    @abstractmethod
    async def single_step(self) -> StepResult:
        """
        Process one item and pause.

        Useful for debugging and step-through analysis.

        Returns:
            Result of processing the single item
        """
        ...

    @abstractmethod
    async def stop_processing(self, _: bool = True) -> None:
        """
        Stop processing.

        Args:
            graceful: If True, complete current item and cleanup.
                     If False, stop immediately.
        """
        ...

    @abstractmethod
    async def emergency_stop(self) -> None:
        """
        Emergency stop - immediate halt with no cleanup.

        Use only in critical situations. May leave system in
        inconsistent state requiring manual cleanup.
        """
        ...

    # ========================================================================
    # STATUS AND MONITORING
    # ========================================================================

    @abstractmethod
    def get_processor_metrics(self) -> AgentProcessorMetrics:
        """
        Get detailed processor metrics.

        Returns:
            Comprehensive metrics about processing
        """
        ...

    @abstractmethod
    def get_queue_status(self) -> QueueStatus:
        """
        Get processing queue status.

        Returns:
            Current queue depths and distribution
        """
        ...

    @abstractmethod
    def is_paused(self) -> bool:
        """
        Check if processing is paused.

        Returns:
            True if paused
        """
        ...

    @abstractmethod
    def is_single_stepping(self) -> bool:
        """
        Check if in single-step mode.

        Returns:
            True if single-stepping
        """
        ...

    @abstractmethod
    def is_processing(self) -> bool:
        """
        Check if actively processing.

        Returns:
            True if processing loop is active
        """
        ...

    # ========================================================================
    # ADVANCED CONTROL
    # ========================================================================

    @abstractmethod
    async def set_processing_speed(self, _: float) -> None:
        """
        Set processing speed multiplier.

        Args:
            multiplier: 1.0 = normal, 0.5 = half speed, 2.0 = double speed
        """
        ...

    @abstractmethod
    async def skip_current_item(self, reason: str) -> bool:
        """
        Skip the currently processing item.

        Args:
            reason: Why the item is being skipped

        Returns:
            True if successfully skipped
        """
        ...

    @abstractmethod
    async def replay_last_item(self) -> StepResult:
        """
        Replay the last processed item.

        Useful for debugging processing issues.

        Returns:
            Result of reprocessing
        """
        ...

    @abstractmethod
    def get_state_history(self, limit: int = 10) -> List[StateTransitionRecord]:
        """
        Get recent state transition history.

        Args:
            limit: Maximum number of transitions to return

        Returns:
            List of state transitions with timestamps and reasons
        """
        ...
