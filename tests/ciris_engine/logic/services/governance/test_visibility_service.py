"""Unit tests for Visibility Service."""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from ciris_engine.logic.services.governance.visibility import VisibilityService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import FinalAction, Task, TaskOutcome, Thought
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.visibility import ReasoningTrace, TaskDecisionHistory, VisibilitySnapshot


@pytest.fixture
def time_service():
    """Create a time service."""
    return TimeService()


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def visibility_service(time_service, temp_db):
    """Create a VisibilityService instance for testing."""
    from ciris_engine.logic.buses import BusManager
    from ciris_engine.logic.registries.base import ServiceRegistry

    # Create mock bus manager
    registry = ServiceRegistry()
    bus_manager = BusManager(registry, time_service)

    service = VisibilityService(bus_manager=bus_manager, time_service=time_service, db_path=temp_db)
    return service


def create_test_task(task_id: str, status: TaskStatus = TaskStatus.ACTIVE) -> Task:
    """Create a test task."""
    now = datetime.now(timezone.utc)
    return Task(
        task_id=task_id,
        channel_id="test_channel",
        description=f"Test task {task_id}",
        status=status,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        parent_task_id=None,
        context=None,
        outcome=None,
    )


def create_test_thought(
    thought_id: str,
    task_id: str,
    status: ThoughtStatus = ThoughtStatus.PENDING,
    action_type: str = None,
    parent_thought_id: str = None,
) -> Thought:
    """Create a test thought."""
    now = datetime.now(timezone.utc)

    final_action = None
    if action_type:
        final_action = FinalAction(
            action_type=action_type, action_params={"message": "Test message"}, reasoning=f"Reasoning for {action_type}"
        )

    return Thought(
        thought_id=thought_id,
        content=f"Thought content for {thought_id}",
        source_task_id=task_id,
        status=status,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        parent_thought_id=parent_thought_id,
        thought_depth=1 if not parent_thought_id else 2,
        final_action=final_action,
    )


@pytest.mark.asyncio
async def test_visibility_service_lifecycle(visibility_service):
    """Test VisibilityService start/stop lifecycle."""
    # Service should not be running initially
    assert visibility_service._started is False
    assert await visibility_service.is_healthy() is False

    # Start the service
    await visibility_service.start()
    assert visibility_service._started is True
    assert visibility_service._start_time is not None
    assert await visibility_service.is_healthy() is True

    # Stop the service
    await visibility_service.stop()
    assert visibility_service._started is False
    assert await visibility_service.is_healthy() is False


def test_visibility_service_capabilities(visibility_service):
    """Test VisibilityService.get_capabilities() returns correct info."""
    capabilities = visibility_service.get_capabilities()

    assert isinstance(capabilities, ServiceCapabilities)
    assert capabilities.service_name == "VisibilityService"
    assert "get_current_state" in capabilities.actions
    assert "get_reasoning_trace" in capabilities.actions
    assert "get_decision_history" in capabilities.actions
    assert capabilities.version == "1.0.0"
    assert "BusManager" in capabilities.dependencies


@pytest.mark.asyncio
async def test_visibility_service_status(visibility_service):
    """Test VisibilityService.get_status() returns correct info."""
    await visibility_service.start()
    # Call is_healthy to set last_health_check
    await visibility_service.is_healthy()
    status = visibility_service.get_status()

    assert isinstance(status, ServiceStatus)
    assert status.service_name == "VisibilityService"
    assert status.service_type == "visibility"
    assert status.is_healthy is True
    assert status.uptime_seconds >= 0
    assert isinstance(status.metrics, dict)
    assert status.last_error is None
    assert isinstance(status.last_health_check, datetime)


@pytest.mark.asyncio
async def test_visibility_empty_state(visibility_service):
    """Test visibility with no active tasks or thoughts."""
    await visibility_service.start()

    # With no data in persistence, should return empty state
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status", return_value=[]):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_status", return_value=[]):
            snapshot = await visibility_service.get_current_state()

    assert isinstance(snapshot, VisibilitySnapshot)
    assert snapshot.current_task is None
    assert len(snapshot.active_thoughts) == 0
    assert len(snapshot.recent_decisions) == 0
    assert snapshot.reasoning_depth == 0


@pytest.mark.asyncio
async def test_visibility_with_active_task(visibility_service):
    """Test visibility with an active task."""
    await visibility_service.start()

    # Create test task
    task = create_test_task("task-123", TaskStatus.ACTIVE)

    # Mock persistence to return the task
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status", return_value=[task]):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_status", return_value=[]):
            snapshot = await visibility_service.get_current_state()

    assert isinstance(snapshot, VisibilitySnapshot)
    assert snapshot.current_task is not None
    assert snapshot.current_task.task_id == "task-123"
    assert snapshot.current_task.status == TaskStatus.ACTIVE


@pytest.mark.asyncio
async def test_visibility_with_active_thoughts(visibility_service):
    """Test visibility with active thoughts."""
    await visibility_service.start()

    # Create test thoughts
    thoughts = [create_test_thought(f"thought-{i}", "task-123", ThoughtStatus.PENDING) for i in range(3)]

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status", return_value=[]):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_status", return_value=thoughts):
            snapshot = await visibility_service.get_current_state()

    assert isinstance(snapshot, VisibilitySnapshot)
    assert len(snapshot.active_thoughts) == 3
    assert all(t.status == ThoughtStatus.PENDING for t in snapshot.active_thoughts)


@pytest.mark.asyncio
async def test_visibility_with_recent_decisions(visibility_service):
    """Test visibility with recent decisions (completed thoughts with actions)."""
    await visibility_service.start()

    # Create completed thoughts with final_action
    decisions = [create_test_thought(f"thought-{i}", "task-123", ThoughtStatus.COMPLETED, "SPEAK") for i in range(5)]

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status", return_value=[]):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_status") as mock_get_thoughts:
            # Return empty for PENDING, decisions for COMPLETED
            def side_effect(status, db_path):
                if status == ThoughtStatus.PENDING:
                    return []
                elif status == ThoughtStatus.COMPLETED:
                    return decisions
                return []

            mock_get_thoughts.side_effect = side_effect

            snapshot = await visibility_service.get_current_state()

    assert isinstance(snapshot, VisibilitySnapshot)
    assert len(snapshot.recent_decisions) == 5
    assert all(t.final_action is not None for t in snapshot.recent_decisions)
    assert all(t.final_action.action_type == "SPEAK" for t in snapshot.recent_decisions)


@pytest.mark.asyncio
async def test_visibility_reasoning_depth(visibility_service):
    """Test calculation of reasoning depth from thought hierarchy."""
    await visibility_service.start()

    # Create thoughts with parent relationships
    thoughts = [
        create_test_thought("thought-0", "task-123", ThoughtStatus.PENDING),
        create_test_thought("thought-1", "task-123", ThoughtStatus.PENDING, parent_thought_id="thought-0"),
        create_test_thought("thought-2", "task-123", ThoughtStatus.PENDING, parent_thought_id="thought-1"),
    ]

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status", return_value=[]):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_status", return_value=thoughts):
            snapshot = await visibility_service.get_current_state()

    assert isinstance(snapshot, VisibilitySnapshot)
    assert snapshot.reasoning_depth == 3  # Three levels deep


@pytest.mark.asyncio
async def test_get_reasoning_trace_no_task(visibility_service):
    """Test reasoning trace for non-existent task."""
    await visibility_service.start()

    # Mock persistence to return None
    with patch("ciris_engine.logic.services.governance.visibility.get_task_by_id", return_value=None):
        trace = await visibility_service.get_reasoning_trace("nonexistent-task")

    assert isinstance(trace, ReasoningTrace)
    assert trace.task.task_id == "nonexistent-task"
    assert trace.task.description == "Task not found"
    assert len(trace.thought_steps) == 0
    assert trace.total_thoughts == 0
    assert trace.processing_time_ms == 0.0


@pytest.mark.asyncio
async def test_get_reasoning_trace_with_thoughts(visibility_service):
    """Test reasoning trace with actual thoughts."""
    await visibility_service.start()

    # Create test data
    task = create_test_task("task-123")
    thoughts = [
        create_test_thought("thought-0", "task-123", ThoughtStatus.COMPLETED, "PONDER"),
        create_test_thought("thought-1", "task-123", ThoughtStatus.COMPLETED, "SPEAK", parent_thought_id="thought-0"),
    ]

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_task_by_id", return_value=task):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_task_id", return_value=thoughts):
            trace = await visibility_service.get_reasoning_trace("task-123")

    assert isinstance(trace, ReasoningTrace)
    assert trace.task.task_id == "task-123"
    assert len(trace.thought_steps) == 2
    assert trace.total_thoughts == 2
    assert "PONDER" in trace.actions_taken
    assert "SPEAK" in trace.actions_taken

    # Check thought steps
    assert trace.thought_steps[0].thought.thought_id == "thought-0"
    assert trace.thought_steps[1].thought.thought_id == "thought-1"
    assert trace.thought_steps[0].followup_thoughts == ["thought-1"]  # thought-1 has thought-0 as parent


@pytest.mark.asyncio
async def test_get_decision_history_no_task(visibility_service):
    """Test decision history for non-existent task."""
    await visibility_service.start()

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_task_by_id", return_value=None):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_task_id", return_value=[]):
            history = await visibility_service.get_decision_history("nonexistent-task")

    assert isinstance(history, TaskDecisionHistory)
    assert history.task_id == "nonexistent-task"
    assert history.task_description == "Unknown task"
    assert len(history.decisions) == 0
    assert history.total_decisions == 0
    assert history.successful_decisions == 0
    assert history.final_status == "unknown"


@pytest.mark.asyncio
async def test_get_decision_history_with_decisions(visibility_service):
    """Test decision history with actual decisions."""
    await visibility_service.start()

    # Create test data
    task = create_test_task("task-123", TaskStatus.COMPLETED)
    task.outcome = TaskOutcome(status="success", summary="Task completed successfully")

    thoughts = [
        create_test_thought("thought-0", "task-123", ThoughtStatus.COMPLETED, "PONDER"),
        create_test_thought("thought-1", "task-123", ThoughtStatus.COMPLETED, "SPEAK"),
        create_test_thought("thought-2", "task-123", ThoughtStatus.FAILED, "REJECT"),  # Failed thought
    ]

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_task_by_id", return_value=task):
        with patch("ciris_engine.logic.services.governance.visibility.get_thoughts_by_task_id", return_value=thoughts):
            history = await visibility_service.get_decision_history("task-123")

    assert isinstance(history, TaskDecisionHistory)
    assert history.task_id == "task-123"
    assert history.task_description == "Test task task-123"
    assert len(history.decisions) == 3
    assert history.total_decisions == 3
    assert history.successful_decisions == 2  # Only COMPLETED thoughts count as successful
    assert history.final_status == "success"
    assert history.completion_time is not None

    # Check decision records
    assert history.decisions[0].action_type == "PONDER"
    assert history.decisions[0].executed is True
    assert history.decisions[0].success is True

    assert history.decisions[2].action_type == "REJECT"
    assert history.decisions[2].executed is False  # FAILED status means not executed
    assert history.decisions[2].success is False


@pytest.mark.asyncio
async def test_explain_action(visibility_service):
    """Test explaining an action."""
    await visibility_service.start()

    # Create test thought with action
    thought = create_test_thought("thought-123", "task-123", ThoughtStatus.COMPLETED, "SPEAK")

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_thought_by_id", return_value=thought):
        explanation = await visibility_service.explain_action("thought-123")

    assert "Action: SPEAK" in explanation
    assert "Reasoning: Reasoning for SPEAK" in explanation


@pytest.mark.asyncio
async def test_explain_action_no_thought(visibility_service):
    """Test explaining action for non-existent thought."""
    await visibility_service.start()

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_thought_by_id", return_value=None):
        explanation = await visibility_service.explain_action("nonexistent")

    assert "No thought found with ID nonexistent" in explanation


@pytest.mark.asyncio
async def test_explain_action_no_final_action(visibility_service):
    """Test explaining action for thought without final_action."""
    await visibility_service.start()

    # Create thought without action
    thought = create_test_thought("thought-123", "task-123", ThoughtStatus.PENDING)

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_thought_by_id", return_value=thought):
        explanation = await visibility_service.explain_action("thought-123")

    assert "did not result in an action" in explanation


@pytest.mark.asyncio
async def test_get_task_history(visibility_service):
    """Test getting recent task history."""
    await visibility_service.start()

    # Create test tasks with different statuses and timestamps
    now = datetime.now(timezone.utc)
    completed_tasks = [
        create_test_task("task-1", TaskStatus.COMPLETED),
        create_test_task("task-2", TaskStatus.COMPLETED),
        create_test_task("task-3", TaskStatus.COMPLETED),
    ]
    # Set different updated times
    from datetime import timedelta

    for i, task in enumerate(completed_tasks):
        task.updated_at = (now - timedelta(hours=i)).isoformat()

    failed_tasks = [
        create_test_task("task-4", TaskStatus.FAILED),
        create_test_task("task-5", TaskStatus.FAILED),
    ]
    # Set different updated times
    for i, task in enumerate(failed_tasks):
        task.updated_at = (now - timedelta(hours=(i + 3))).isoformat()

    # Mock persistence
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status") as mock_get_tasks:

        def side_effect(status, db_path):
            if status == TaskStatus.COMPLETED:
                return completed_tasks
            elif status == TaskStatus.FAILED:
                return failed_tasks
            return []

        mock_get_tasks.side_effect = side_effect

        # Get task history with default limit
        history = await visibility_service.get_task_history(limit=10)

    assert isinstance(history, list)
    assert len(history) == 5  # Should return all 5 tasks
    assert all(isinstance(task, Task) for task in history)

    # Check ordering - most recent first
    assert history[0].task_id == "task-1"  # Most recent completed task

    # Test with smaller limit
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status") as mock_get_tasks:
        mock_get_tasks.side_effect = side_effect
        history_limited = await visibility_service.get_task_history(limit=2)

    assert len(history_limited) == 2


@pytest.mark.asyncio
async def test_get_task_history_empty(visibility_service):
    """Test getting task history when no tasks exist."""
    await visibility_service.start()

    # Mock persistence to return empty lists
    with patch("ciris_engine.logic.services.governance.visibility.get_tasks_by_status", return_value=[]):
        history = await visibility_service.get_task_history()

    assert isinstance(history, list)
    assert len(history) == 0
