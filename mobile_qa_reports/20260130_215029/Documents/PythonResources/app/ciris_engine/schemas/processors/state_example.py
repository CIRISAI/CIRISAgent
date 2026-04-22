"""
Example usage of state transition schemas.
This shows how to use the typed schemas instead of Dict[str, Any].
"""

from datetime import datetime

from ciris_engine.schemas.processors.state import (
    StateCondition,
    StateHistory,
    StateMetadata,
    StateTransitionRecord,
    StateTransitionRequest,
    StateTransitionResult,
    StateTransitionValidation,
)
from ciris_engine.schemas.processors.states import AgentState


def example_state_transition() -> None:
    """Example of recording a state transition."""
    # Create a transition record
    transition = StateTransitionRecord(
        timestamp=datetime.now().isoformat(),
        from_state=AgentState.WORK.value,
        to_state=AgentState.DREAM.value,
        metadata={"reason": "Scheduled dream time", "duration_hours": 6},
    )

    # Access fields directly - no more dict access
    print(f"Transition from {transition.from_state} to {transition.to_state}")
    print(f"At time: {transition.timestamp}")

    # Records are immutable (frozen=True)
    # transition.to_state = "PLAY"  # This would raise an error


def example_state_request() -> None:
    """Example of requesting a state transition."""
    # Request a transition
    request = StateTransitionRequest(
        target_state=AgentState.SOLITUDE,
        reason="High error rate detected, entering reflection mode",
        force=False,
        metadata={"error_count": 15, "last_error": "Memory allocation failed"},
    )

    # Process the request
    if request.force:
        print(f"Force transitioning to {request.target_state.value}")
    else:
        print(f"Requesting transition to {request.target_state.value}: {request.reason}")


def example_state_result() -> None:
    """Example of handling transition results."""
    # Successful transition
    success_result = StateTransitionResult(
        success=True,
        from_state=AgentState.WORK,
        to_state=AgentState.PLAY,
        reason="User requested creative mode",
        timestamp=datetime.now().isoformat(),
        duration_in_previous_state=3600.5,  # 1 hour in WORK state
    )

    # Failed transition
    failure_result = StateTransitionResult(
        success=False,
        from_state=AgentState.SHUTDOWN,
        to_state=None,  # No transition occurred
        reason="Cannot transition from SHUTDOWN to PLAY",
        timestamp=datetime.now().isoformat(),
        duration_in_previous_state=0.0,
    )

    # Handle results
    for result in [success_result, failure_result]:
        if result.success:
            if result.to_state is not None:
                print(f"✓ Transitioned to {result.to_state.value}")
            else:
                print("✓ Transitioned to unknown state")
            print(f"  Spent {result.duration_in_previous_state:.1f}s in {result.from_state.value}")
        else:
            print(f"✗ Failed to transition from {result.from_state.value}")
            print(f"  Reason: {result.reason}")


def example_state_history() -> None:
    """Example of working with state history."""
    # Create some historical transitions
    history = StateHistory(
        transitions=[
            StateTransitionRecord(
                timestamp="2025-01-01T08:00:00Z", from_state=None, to_state=AgentState.SHUTDOWN.value  # Initial state
            ),
            StateTransitionRecord(
                timestamp="2025-01-01T08:00:10Z", from_state=AgentState.SHUTDOWN.value, to_state=AgentState.WAKEUP.value
            ),
            StateTransitionRecord(
                timestamp="2025-01-01T08:05:00Z",
                from_state=AgentState.WAKEUP.value,
                to_state=AgentState.WORK.value,
                metadata={"wakeup_duration": 290},
            ),
        ],
        current_state=AgentState.WORK,
        current_state_metadata=StateMetadata(
            entered_at="2025-01-01T08:05:00Z", metrics={"thoughts_processed": 42, "tasks_completed": 3}
        ),
    )

    # Get recent transitions
    recent = history.get_recent_transitions(limit=2)
    print(f"Last {len(recent)} transitions:")
    for t in recent:
        print(f"  {t.from_state} → {t.to_state} at {t.timestamp}")

    # Calculate time in WORK state
    work_duration = history.get_state_duration(AgentState.WORK)
    print(f"Time spent in WORK state: {work_duration:.1f} seconds")

    # Access current state metrics
    print(f"Current state metrics: {history.current_state_metadata.metrics}")


def example_state_validation() -> None:
    """Example of validating state transitions."""
    # Check if a transition is valid
    validation = StateTransitionValidation(
        from_state=AgentState.DREAM,
        to_state=AgentState.SHUTDOWN,
        is_valid=True,
        conditions=[
            StateCondition(
                name="shutdown_allowed", description="Shutdown transitions are allowed from any state", met=True
            ),
            StateCondition(
                name="dream_complete",
                description="Dream processing must be complete",
                met=False,
                details={"remaining_tasks": 3, "elapsed_time": 1200},
            ),
        ],
    )

    # Check validation
    if validation.is_valid:
        unmet = [c for c in validation.conditions if not c.met]
        if unmet:
            print(f"Transition allowed but {len(unmet)} conditions not met:")
            for condition in unmet:
                print(f"  - {condition.description}")
                if condition.details:
                    print(f"    Details: {condition.details}")
    else:
        print(f"Transition blocked: {validation.blocking_reason}")


if __name__ == "__main__":
    print("=== State Transition Examples ===\n")

    print("1. Recording Transitions:")
    example_state_transition()

    print("\n2. Requesting Transitions:")
    example_state_request()

    print("\n3. Handling Results:")
    example_state_result()

    print("\n4. State History:")
    example_state_history()

    print("\n5. Transition Validation:")
    example_state_validation()
