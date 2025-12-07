"""
State management for the CIRISAgent processor.
Handles transitions between WAKEUP, DREAM, PLAY, WORK, SOLITUDE, and SHUTDOWN states.

Supports template-driven cognitive state behaviors configuration per
FSD/COGNITIVE_STATE_BEHAVIORS.md for mission-appropriate transition rules.

Covenant References:
- Section V: Model Welfare & Self-Governance
- Section VIII: Dignified Sunset Protocol
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors
from ciris_engine.schemas.processors.state import StateHistory, StateMetadata, StateMetrics, StateTransitionRecord
from ciris_engine.schemas.processors.states import AgentState

logger = logging.getLogger(__name__)


class StateTransition:
    """Represents a state transition with validation rules."""

    def __init__(
        self,
        from_state: AgentState,
        to_state: AgentState,
        condition_fn: Optional[Callable[["StateManager"], bool]] = None,
        on_transition_fn: Optional[Callable[["StateManager", AgentState, AgentState], None]] = None,
    ) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.condition_fn = condition_fn  # Optional validation function
        self.on_transition_fn = on_transition_fn  # Optional transition handler


class StateManager:
    """Manages agent state transitions and state-specific behaviors.

    Supports template-driven cognitive state behaviors configuration:
    - Wakeup ceremony can be bypassed for partnership-model agents
    - Shutdown can be instant, conditional, or always-consent
    - PLAY/DREAM/SOLITUDE states can be enabled/disabled per agent

    See FSD/COGNITIVE_STATE_BEHAVIORS.md for design rationale.
    """

    # Base valid transitions - these are filtered based on cognitive_behaviors config
    BASE_TRANSITIONS = [
        # Transitions TO shutdown from any state
        StateTransition(AgentState.WAKEUP, AgentState.SHUTDOWN),
        StateTransition(AgentState.WORK, AgentState.SHUTDOWN),
        StateTransition(AgentState.DREAM, AgentState.SHUTDOWN),
        StateTransition(AgentState.PLAY, AgentState.SHUTDOWN),
        StateTransition(AgentState.SOLITUDE, AgentState.SHUTDOWN),
        # Special startup transition - may be WAKEUP or WORK depending on config
        StateTransition(AgentState.SHUTDOWN, AgentState.WAKEUP),
        StateTransition(AgentState.SHUTDOWN, AgentState.WORK),  # Direct to WORK when wakeup bypassed
        # Other valid transitions
        StateTransition(AgentState.WAKEUP, AgentState.WORK),
        StateTransition(AgentState.WAKEUP, AgentState.DREAM),
        StateTransition(AgentState.WORK, AgentState.DREAM),
        StateTransition(AgentState.WORK, AgentState.PLAY),
        StateTransition(AgentState.WORK, AgentState.SOLITUDE),
        StateTransition(AgentState.DREAM, AgentState.WORK),
        StateTransition(AgentState.PLAY, AgentState.WORK),
        StateTransition(AgentState.PLAY, AgentState.SOLITUDE),
        StateTransition(AgentState.SOLITUDE, AgentState.WORK),
    ]

    # Legacy class attribute for backwards compatibility
    VALID_TRANSITIONS = BASE_TRANSITIONS

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        initial_state: AgentState = AgentState.SHUTDOWN,
        cognitive_behaviors: Optional[CognitiveStateBehaviors] = None,
    ) -> None:
        """Initialize the state manager.

        Args:
            time_service: Service for time operations
            initial_state: Starting state (default: SHUTDOWN)
            cognitive_behaviors: Template-driven state transition config.
                If None, uses default Covenant-compliant behaviors.
        """
        self.time_service = time_service
        self.current_state = initial_state
        self.state_history: List[StateTransitionRecord] = []
        self.state_metadata: Dict[AgentState, StateMetadata] = {}

        # Store cognitive behaviors config (default if not provided)
        self.cognitive_behaviors = cognitive_behaviors or CognitiveStateBehaviors()

        # Build transition map respecting cognitive behaviors
        self._transition_map = self._build_transition_map()

        self._record_state_change(initial_state, None)

        # Initialize metadata for the initial state
        self.state_metadata[initial_state] = StateMetadata(
            entered_at=self.time_service.now_iso(), metrics=StateMetrics()
        )

        # Log cognitive behaviors configuration with clear indication of source
        logger.info(
            f"[STATE_MANAGER] Initialized with cognitive behaviors "
            f"(from_template={cognitive_behaviors is not None}): "
            f"wakeup.enabled={self.cognitive_behaviors.wakeup.enabled}, "
            f"startup_target={self.startup_target_state.value}, "
            f"shutdown.mode={self.cognitive_behaviors.shutdown.mode}"
        )

    @property
    def wakeup_bypassed(self) -> bool:
        """Check if wakeup ceremony is bypassed for this agent."""
        return not self.cognitive_behaviors.wakeup.enabled

    @property
    def startup_target_state(self) -> AgentState:
        """Get the target state for startup (WAKEUP or WORK)."""
        if self.wakeup_bypassed:
            return AgentState.WORK
        return AgentState.WAKEUP

    def _build_transition_map(self) -> Dict[AgentState, Dict[AgentState, StateTransition]]:
        """Build a map for quick transition lookups respecting cognitive behaviors.

        Filters transitions based on:
        - wakeup.enabled: Determines SHUTDOWN -> WAKEUP vs SHUTDOWN -> WORK
        - play.enabled: Whether PLAY state is accessible
        - dream.enabled: Whether DREAM state is accessible
        - solitude.enabled: Whether SOLITUDE state is accessible
        """
        transition_map: Dict[AgentState, Dict[AgentState, StateTransition]] = {}
        behaviors = self.cognitive_behaviors

        for transition in self.BASE_TRANSITIONS:
            # Filter based on cognitive behaviors config
            if not self._is_transition_allowed(transition, behaviors):
                continue

            if transition.from_state not in transition_map:
                transition_map[transition.from_state] = {}
            transition_map[transition.from_state][transition.to_state] = transition

        return transition_map

    def _is_optional_state_enabled(self, state: AgentState, behaviors: CognitiveStateBehaviors) -> bool:
        """Check if an optional cognitive state is enabled in behaviors.

        Returns True for states that are always enabled (WORK, WAKEUP, SHUTDOWN).
        Returns the enabled flag for optional states (PLAY, DREAM, SOLITUDE).
        """
        state_behavior_map = {
            AgentState.PLAY: behaviors.play,
            AgentState.DREAM: behaviors.dream,
            AgentState.SOLITUDE: behaviors.solitude,
        }
        behavior = state_behavior_map.get(state)
        return bool(getattr(behavior, "enabled", True)) if behavior else True

    def _check_shutdown_wakeup_transition(
        self, from_state: AgentState, to_state: AgentState, behaviors: CognitiveStateBehaviors
    ) -> Optional[bool]:
        """Check SHUTDOWN -> WAKEUP/WORK transitions based on wakeup config.

        Returns True/False for definitive result, None if not a shutdown transition.
        """
        if from_state != AgentState.SHUTDOWN:
            return None
        if to_state == AgentState.WAKEUP:
            return behaviors.wakeup.enabled
        if to_state == AgentState.WORK:
            return not behaviors.wakeup.enabled
        return None

    def _is_transition_allowed(
        self,
        transition: StateTransition,
        behaviors: CognitiveStateBehaviors,
    ) -> bool:
        """Check if a transition is allowed based on cognitive behaviors.

        Args:
            transition: The transition to check
            behaviors: The cognitive behaviors configuration

        Returns:
            True if the transition is allowed, False otherwise
        """
        from_state = transition.from_state
        to_state = transition.to_state

        # Check SHUTDOWN -> WAKEUP/WORK transitions
        shutdown_result = self._check_shutdown_wakeup_transition(from_state, to_state, behaviors)
        if shutdown_result is not None:
            return shutdown_result

        # Check if optional states (PLAY, DREAM, SOLITUDE) are enabled
        if not self._is_optional_state_enabled(to_state, behaviors):
            return False
        if not self._is_optional_state_enabled(from_state, behaviors):
            return False

        return True

    def _record_state_change(self, new_state: AgentState, old_state: Optional[AgentState]) -> None:
        """Record state change in history."""
        record = StateTransitionRecord(
            timestamp=self.time_service.now_iso(),
            from_state=old_state.value if old_state else None,
            to_state=new_state.value,
            metadata=None,  # Optional field, explicitly set to None
        )
        self.state_history.append(record)

    async def can_transition_to(self, target_state: AgentState) -> bool:
        """Check if transition to target state is valid."""
        if self.current_state not in self._transition_map:
            return False

        if target_state not in self._transition_map[self.current_state]:
            return False

        transition = self._transition_map[self.current_state][target_state]

        # Check condition function if present
        if transition.condition_fn and not transition.condition_fn(self):
            return False

        return True

    async def transition_to(self, target_state: AgentState) -> bool:
        """
        Attempt to transition to a new state.
        Returns True if successful, False otherwise.

        Note: Respects cognitive_behaviors configuration for startup transitions.
        When wakeup is bypassed, SHUTDOWN -> WORK is the valid startup path.
        """
        # Handle startup transition based on cognitive behaviors
        if self.current_state == AgentState.SHUTDOWN:
            expected_startup = self.startup_target_state
            if target_state != expected_startup:
                logger.warning(
                    f"Attempted transition from SHUTDOWN to {target_state.value} - blocked! "
                    f"Expected startup transition is SHUTDOWN -> {expected_startup.value} "
                    f"(wakeup_bypassed={self.wakeup_bypassed})"
                )
                return False
            # Allow the configured startup transition

        if not await self.can_transition_to(target_state):
            logger.warning(f"Invalid state transition attempted: {self.current_state.value} -> {target_state.value}")
            return False

        old_state = self.current_state
        transition = self._transition_map[old_state][target_state]

        # Execute transition handler if present
        if transition.on_transition_fn:
            try:
                transition.on_transition_fn(self, old_state, target_state)
            except Exception as e:
                logger.error(f"Error in transition handler for {old_state.value} -> {target_state.value}: {e}")
                return False

        # Update state
        self.current_state = target_state
        self._record_state_change(target_state, old_state)

        logger.info(f"State transition: {old_state.value} -> {target_state.value}")
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            print(f"[{timestamp}] [STATE] Transition: {old_state.value} -> {target_state.value}")  # Print to console
        except OSError:
            # Stdout closed during shutdown - this is expected in some contexts (e.g., QA runner)
            # Note: BrokenPipeError is a subclass of OSError, so catching OSError handles both
            pass

        # Initialize metadata for new state if needed
        if target_state not in self.state_metadata:
            self.state_metadata[target_state] = StateMetadata(
                entered_at=self.time_service.now_iso(), metrics=StateMetrics()
            )

        return True

    def get_state(self) -> AgentState:
        """Get current state."""
        return self.current_state

    def get_state_metadata(self) -> StateMetadata:
        """Get metadata for current state."""
        return self.state_metadata.get(
            self.current_state, StateMetadata(entered_at=self.time_service.now_iso(), metrics=StateMetrics())
        )

    def update_state_metadata(self, key: str, value: Any) -> None:
        """Update metadata for current state."""
        if self.current_state not in self.state_metadata:
            self.state_metadata[self.current_state] = StateMetadata(
                entered_at=self.time_service.now_iso(), metrics=StateMetrics()
            )
        self.state_metadata[self.current_state].add_metric(key, value)

    def get_state_duration(self) -> float:
        """Get duration in seconds for current state."""
        metadata = self.get_state_metadata()
        if metadata.entered_at:
            entered_at = datetime.fromisoformat(metadata.entered_at)
            return (self.time_service.now() - entered_at).total_seconds()
        return 0.0

    def should_auto_transition(self) -> Optional[AgentState]:
        """
        Check if an automatic state transition should occur.
        Returns the target state if a transition should happen, None otherwise.
        """
        # NEVER auto-transition from SHUTDOWN state
        if self.current_state == AgentState.SHUTDOWN:
            return None

        if self.current_state == AgentState.WAKEUP:
            # After successful wakeup, transition to WORK
            metadata = self.get_state_metadata()
            if metadata.metrics.custom_metrics.get("wakeup_complete", False):
                return AgentState.WORK

        # All other auto-transitions are removed as per the new requirements.
        # For example, the transition from WORK to DREAM based on idle time,
        # and from DREAM to WORK based on duration, are no longer automatic.

        return None

    def get_state_history(self) -> List[StateTransitionRecord]:
        """Get the complete state transition history as typed records."""
        return self.state_history.copy()

    def get_state_history_summary(self) -> StateHistory:
        """Get a complete summary of state history and current state."""
        current_metadata = self.state_metadata.get(
            self.current_state, StateMetadata(entered_at=self.time_service.now_iso(), metrics=StateMetrics())
        )

        return StateHistory(
            transitions=self.state_history.copy(),
            current_state=self.current_state,
            current_state_metadata=current_metadata,
        )
