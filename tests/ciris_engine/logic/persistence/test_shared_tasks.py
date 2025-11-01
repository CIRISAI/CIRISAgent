"""
Unit tests for multi-occurrence shared task coordination.

Tests atomic task claiming, race condition handling, and shared task queries.
"""

import asyncio
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import List, Tuple

import pytest

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.models.tasks import (
    get_latest_shared_task,
    get_shared_task_status,
    get_task_by_correlation_id,
    is_shared_task_completed,
    try_claim_shared_task,
    update_task_status,
)
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task


class MockTimeService:
    """Mock time service for testing."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        return self.now().isoformat()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Initialize database schema
    from ciris_engine.logic.persistence.db import initialize_database

    initialize_database(db_path)

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def time_service():
    """Provide mock time service."""
    return MockTimeService()


def test_try_claim_shared_task_first_claim(temp_db: str, time_service: TimeServiceProtocol):
    """Test claiming a shared task that doesn't exist yet."""
    task, was_created = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Test wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created is True
    assert task.task_id.startswith("WAKEUP_SHARED_")
    assert task.agent_occurrence_id == "__shared__"
    assert task.channel_id == "system"
    assert task.description == "Test wakeup task"
    assert task.priority == 10
    assert task.status == TaskStatus.PENDING


def test_try_claim_shared_task_already_exists(temp_db: str, time_service: TimeServiceProtocol):
    """Test claiming a shared task that already exists."""
    # First claim
    task1, was_created1 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Test wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True

    # Second claim (same day)
    task2, was_created2 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Test wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is False
    assert task1.task_id == task2.task_id
    assert task2.agent_occurrence_id == "__shared__"


def test_try_claim_shared_task_race_condition(temp_db: str, time_service: TimeServiceProtocol):
    """Test atomic claiming with simulated concurrent claims."""

    def claim_task(occurrence_id: int) -> Tuple[Task, bool]:
        """Helper to claim task from a thread."""
        task, created = try_claim_shared_task(
            task_type="wakeup",
            channel_id="system",
            description=f"Claim from occurrence {occurrence_id}",
            priority=10,
            time_service=time_service,
            db_path=temp_db,
        )
        return (task, created)

    # Simulate 5 occurrences trying to claim simultaneously
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(claim_task, i) for i in range(5)]
        results = [future.result() for future in futures]

    # Verify exactly one occurrence successfully created the task
    created_count = sum(1 for _, was_created in results if was_created)
    assert created_count == 1, "Exactly one occurrence should successfully claim the task"

    # Verify all got the same task
    task_ids = {task.task_id for task, _ in results}
    assert len(task_ids) == 1, "All occurrences should get the same task"

    # Verify task is properly marked as shared
    shared_task = results[0][0]
    assert shared_task.agent_occurrence_id == "__shared__"


def test_get_shared_task_status_no_task(temp_db: str):
    """Test querying status when no shared task exists."""
    status = get_shared_task_status("wakeup", within_hours=24, db_path=temp_db)
    assert status is None


def test_get_shared_task_status_existing_task(temp_db: str, time_service: TimeServiceProtocol):
    """Test querying status of an existing shared task."""
    # Create a shared task
    task, _ = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Test task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    # Query status
    status = get_shared_task_status("wakeup", within_hours=24, db_path=temp_db)
    assert status == TaskStatus.PENDING

    # Update status to COMPLETED
    update_task_status(task.task_id, TaskStatus.COMPLETED, "__shared__", time_service, db_path=temp_db)

    # Query again
    status = get_shared_task_status("wakeup", within_hours=24, db_path=temp_db)
    assert status == TaskStatus.COMPLETED


def test_get_shared_task_status_outside_window(temp_db: str, time_service: TimeServiceProtocol):
    """Test that old tasks are not returned."""
    # Create a shared task
    task, _ = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Old task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    # Manually update created_at to be 48 hours ago
    old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    with get_db_connection(temp_db) as conn:
        conn.execute("UPDATE tasks SET created_at = ? WHERE task_id = ?", (old_time, task.task_id))
        conn.commit()

    # Query with 24-hour window - should return None
    status = get_shared_task_status("wakeup", within_hours=24, db_path=temp_db)
    assert status is None

    # Query with 72-hour window - should return the task
    status = get_shared_task_status("wakeup", within_hours=72, db_path=temp_db)
    assert status == TaskStatus.PENDING


def test_is_shared_task_completed_false(temp_db: str, time_service: TimeServiceProtocol):
    """Test is_shared_task_completed returns False for pending task."""
    # Create a pending shared task
    try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Pending task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert is_shared_task_completed("wakeup", within_hours=24, db_path=temp_db) is False


def test_is_shared_task_completed_true(temp_db: str, time_service: TimeServiceProtocol):
    """Test is_shared_task_completed returns True for completed task."""
    # Create and complete a shared task
    task, _ = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Task to complete",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    update_task_status(task.task_id, TaskStatus.COMPLETED, "__shared__", time_service, db_path=temp_db)

    assert is_shared_task_completed("wakeup", within_hours=24, db_path=temp_db) is True


def test_get_latest_shared_task_not_found(temp_db: str):
    """Test get_latest_shared_task returns None when no task exists."""
    task = get_latest_shared_task("wakeup", within_hours=24, db_path=temp_db)
    assert task is None


def test_get_latest_shared_task_found(temp_db: str, time_service: TimeServiceProtocol):
    """Test get_latest_shared_task returns the correct task."""
    # Create a shared task
    original_task, _ = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Latest task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    # Retrieve it
    retrieved_task = get_latest_shared_task("wakeup", within_hours=24, db_path=temp_db)

    assert retrieved_task is not None
    assert retrieved_task.task_id == original_task.task_id
    assert retrieved_task.agent_occurrence_id == "__shared__"
    assert retrieved_task.description == "Latest task"


def test_different_task_types_isolated(temp_db: str, time_service: TimeServiceProtocol):
    """Test that different task types are isolated from each other."""
    # Create wakeup task
    wakeup_task, _ = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    # Create shutdown task
    shutdown_task, _ = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="Shutdown task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    # Verify they have different task IDs
    assert wakeup_task.task_id != shutdown_task.task_id
    assert wakeup_task.task_id.startswith("WAKEUP_SHARED_")
    assert shutdown_task.task_id.startswith("SHUTDOWN_SHARED_")

    # Complete wakeup task
    update_task_status(wakeup_task.task_id, TaskStatus.COMPLETED, "__shared__", time_service, db_path=temp_db)

    # Verify wakeup is completed but shutdown is still pending
    assert is_shared_task_completed("wakeup", within_hours=24, db_path=temp_db) is True
    assert is_shared_task_completed("shutdown", within_hours=24, db_path=temp_db) is False


@pytest.mark.asyncio
async def test_concurrent_claims_stress_test(temp_db: str, time_service: TimeServiceProtocol):
    """Stress test with many concurrent claims."""

    async def claim_task_async(occurrence_id: int) -> Tuple[str, bool]:
        """Async wrapper for claiming."""
        loop = asyncio.get_event_loop()
        task, created = await loop.run_in_executor(
            None,
            try_claim_shared_task,
            "wakeup",
            "system",
            f"Claim from {occurrence_id}",
            10,
            time_service,
            temp_db,
        )
        return (task.task_id, created)

    # Simulate 20 occurrences
    results = await asyncio.gather(*[claim_task_async(i) for i in range(20)])

    # Verify exactly one created the task
    created_count = sum(1 for _, was_created in results if was_created)
    assert created_count == 1

    # Verify all got the same task ID
    task_ids = {task_id for task_id, _ in results}
    assert len(task_ids) == 1


def test_shared_task_deterministic_id_format(temp_db: str, time_service: TimeServiceProtocol):
    """Test that shared task IDs follow deterministic format."""
    task, _ = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Test task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    # Verify format: {TYPE}_SHARED_{YYYYMMDD}
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    expected_id = f"WAKEUP_SHARED_{date_str}"
    assert task.task_id == expected_id


def test_get_task_by_correlation_id_found(temp_db: str, time_service: TimeServiceProtocol):
    """Test retrieving a task by correlation_id when it exists."""
    from uuid import uuid4

    from ciris_engine.logic.persistence.models.tasks import add_task, get_task_by_correlation_id
    from ciris_engine.schemas.runtime.models import TaskContext

    # Create a task with a correlation_id
    correlation_id = "reddit_post_abc123"
    task = Task(
        task_id=str(uuid4()),
        channel_id="reddit:r/ciris",
        agent_occurrence_id="default",
        description="Test Reddit post",
        status=TaskStatus.ACTIVE,
        priority=0,
        created_at=time_service.now_iso(),
        updated_at=time_service.now_iso(),
        context=TaskContext(
            channel_id="reddit:r/ciris",
            user_id="test_user",
            correlation_id=correlation_id,
            agent_occurrence_id="default",
        ),
    )

    add_task(task, db_path=temp_db)

    # Retrieve by correlation_id
    retrieved_task = get_task_by_correlation_id(correlation_id, occurrence_id="default", db_path=temp_db)

    assert retrieved_task is not None
    assert retrieved_task.task_id == task.task_id
    assert retrieved_task.context.correlation_id == correlation_id
    assert retrieved_task.description == "Test Reddit post"


def test_get_task_by_correlation_id_not_found(temp_db: str):
    """Test retrieving a task by correlation_id when it doesn't exist."""
    from ciris_engine.logic.persistence.models.tasks import get_task_by_correlation_id

    retrieved_task = get_task_by_correlation_id("nonexistent_correlation_id", occurrence_id="default", db_path=temp_db)

    assert retrieved_task is None


def test_get_task_by_correlation_id_multiple_tasks_returns_latest(temp_db: str, time_service: TimeServiceProtocol):
    """Test that unique constraint prevents duplicate correlation_ids and add_task returns existing task_id."""
    from uuid import uuid4

    from ciris_engine.logic.persistence.models.tasks import add_task, get_task_by_correlation_id
    from ciris_engine.schemas.runtime.models import TaskContext

    correlation_id = "reddit_comment_xyz789"

    # Create first task with correlation_id
    task1 = Task(
        task_id=str(uuid4()),
        channel_id="reddit:r/ciris",
        agent_occurrence_id="default",
        description="First task",
        status=TaskStatus.COMPLETED,
        priority=0,
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
        context=TaskContext(
            channel_id="reddit:r/ciris",
            user_id="test_user",
            correlation_id=correlation_id,
            agent_occurrence_id="default",
        ),
    )

    # Create second task with same correlation_id (should be prevented by unique constraint)
    task2 = Task(
        task_id=str(uuid4()),
        channel_id="reddit:r/ciris",
        agent_occurrence_id="default",
        description="Second task (newer)",
        status=TaskStatus.ACTIVE,
        priority=0,
        created_at="2025-01-02T00:00:00Z",
        updated_at="2025-01-02T00:00:00Z",
        context=TaskContext(
            channel_id="reddit:r/ciris",
            user_id="test_user",
            correlation_id=correlation_id,
            agent_occurrence_id="default",
        ),
    )

    # Add first task
    task1_id = add_task(task1, db_path=temp_db)
    assert task1_id == task1.task_id

    # Try to add second task - should return existing task1_id due to unique constraint
    returned_task_id = add_task(task2, db_path=temp_db)
    assert (
        returned_task_id == task1.task_id
    ), "add_task should return existing task_id when duplicate correlation_id is detected"

    # Verify only task1 exists in database
    retrieved_task = get_task_by_correlation_id(correlation_id, occurrence_id="default", db_path=temp_db)

    assert retrieved_task is not None
    assert retrieved_task.task_id == task1.task_id, "Should return the first task since duplicate was prevented"
    assert retrieved_task.description == "First task"


def test_get_task_by_correlation_id_different_occurrence(temp_db: str, time_service: TimeServiceProtocol):
    """Test that get_task_by_correlation_id respects occurrence_id filtering."""
    from uuid import uuid4

    from ciris_engine.logic.persistence.models.tasks import add_task, get_task_by_correlation_id
    from ciris_engine.schemas.runtime.models import TaskContext

    correlation_id = "reddit_post_def456"

    # Create task for occurrence "occurrence-1"
    task = Task(
        task_id=str(uuid4()),
        channel_id="reddit:r/ciris",
        agent_occurrence_id="occurrence-1",
        description="Test Reddit post",
        status=TaskStatus.ACTIVE,
        priority=0,
        created_at=time_service.now_iso(),
        updated_at=time_service.now_iso(),
        context=TaskContext(
            channel_id="reddit:r/ciris",
            user_id="test_user",
            correlation_id=correlation_id,
            agent_occurrence_id="occurrence-1",
        ),
    )

    add_task(task, db_path=temp_db)

    # Try to retrieve with different occurrence_id
    retrieved_task = get_task_by_correlation_id(correlation_id, occurrence_id="occurrence-2", db_path=temp_db)

    assert retrieved_task is None  # Should not find task from different occurrence

    # Retrieve with correct occurrence_id
    retrieved_task = get_task_by_correlation_id(correlation_id, occurrence_id="occurrence-1", db_path=temp_db)

    assert retrieved_task is not None
    assert retrieved_task.task_id == task.task_id


# =============================================================================
# Stale Task Detection Tests (for try_claim_shared_task bug fix)
# =============================================================================


def test_try_claim_shared_task_reuses_fresh_active_task(temp_db: str, time_service: TimeServiceProtocol):
    """Test that a fresh ACTIVE task is correctly reused (happy path)."""
    # Create first task
    task1, was_created1 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="Fresh shutdown task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True
    assert task1.status == TaskStatus.PENDING

    # Update to ACTIVE (simulating processing started)
    update_task_status(task1.task_id, TaskStatus.ACTIVE, "__shared__", time_service, db_path=temp_db)

    # Try to claim again - should reuse the fresh active task
    task2, was_created2 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="Fresh shutdown task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is False, "Should reuse fresh ACTIVE task"
    assert task2.task_id == task1.task_id
    assert task2.status == TaskStatus.ACTIVE


def test_try_claim_shared_task_reuses_fresh_pending_task(temp_db: str, time_service: TimeServiceProtocol):
    """Test that a fresh PENDING task is correctly reused."""
    # Create first task
    task1, was_created1 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Fresh wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True
    assert task1.status == TaskStatus.PENDING

    # Try to claim again immediately - should reuse the fresh pending task
    task2, was_created2 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Fresh wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is False, "Should reuse fresh PENDING task"
    assert task2.task_id == task1.task_id
    assert task2.status == TaskStatus.PENDING


def test_try_claim_shared_task_deletes_completed_stale_task(temp_db: str, time_service: TimeServiceProtocol):
    """Test that a COMPLETED stale task is deleted and new task is created."""
    # Create and complete first task
    task1, was_created1 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="Old shutdown task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True
    update_task_status(task1.task_id, TaskStatus.COMPLETED, "__shared__", time_service, db_path=temp_db)

    # Try to claim again - should create NEW task (delete stale completed one)
    task2, was_created2 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="New shutdown task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is True, "Should create new task after deleting stale COMPLETED task"
    assert task2.task_id == task1.task_id  # Same deterministic ID
    assert task2.status == TaskStatus.PENDING  # Fresh task should be PENDING


def test_try_claim_shared_task_deletes_failed_stale_task(temp_db: str, time_service: TimeServiceProtocol):
    """Test that a FAILED stale task is deleted and new task is created."""
    # Create and fail first task
    task1, was_created1 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Failed wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True
    update_task_status(task1.task_id, TaskStatus.FAILED, "__shared__", time_service, db_path=temp_db)

    # Try to claim again - should create NEW task (delete stale failed one)
    task2, was_created2 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="New wakeup task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is True, "Should create new task after deleting stale FAILED task"
    assert task2.task_id == task1.task_id  # Same deterministic ID
    assert task2.status == TaskStatus.PENDING  # Fresh task should be PENDING


def test_try_claim_shared_task_deletes_old_active_task(temp_db: str, time_service: TimeServiceProtocol):
    """Test that an old ACTIVE task (>10 minutes) is deleted and new task is created."""
    # Create first task
    task1, was_created1 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="Old active shutdown task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True
    update_task_status(task1.task_id, TaskStatus.ACTIVE, "__shared__", time_service, db_path=temp_db)

    # Manually update created_at to be 15 minutes ago (stale)
    old_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
    with get_db_connection(temp_db) as conn:
        conn.execute("UPDATE tasks SET created_at = ? WHERE task_id = ?", (old_time, task1.task_id))
        conn.commit()

    # Try to claim again - should create NEW task (delete stale active one)
    task2, was_created2 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="New shutdown task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is True, "Should create new task after deleting stale ACTIVE task (>10 min)"
    assert task2.task_id == task1.task_id  # Same deterministic ID
    assert task2.status == TaskStatus.PENDING  # Fresh task should be PENDING


def test_try_claim_shared_task_boundary_10_minute_age(temp_db: str, time_service: TimeServiceProtocol):
    """Test behavior at the 10-minute boundary (edge case)."""
    # Create first task
    task1, was_created1 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Boundary test task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True
    update_task_status(task1.task_id, TaskStatus.ACTIVE, "__shared__", time_service, db_path=temp_db)

    # Manually update created_at to be exactly 9 minutes 59 seconds ago (should still be fresh)
    boundary_time = (datetime.now(timezone.utc) - timedelta(minutes=9, seconds=59)).isoformat()
    with get_db_connection(temp_db) as conn:
        conn.execute("UPDATE tasks SET created_at = ? WHERE task_id = ?", (boundary_time, task1.task_id))
        conn.commit()

    # Try to claim again - should REUSE (still fresh)
    task2, was_created2 = try_claim_shared_task(
        task_type="wakeup",
        channel_id="system",
        description="Boundary test task",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is False, "Should reuse task that's just under 10 minutes old"
    assert task2.task_id == task1.task_id


def test_try_claim_shared_task_datum_bug_scenario(temp_db: str, time_service: TimeServiceProtocol):
    """Test the exact Datum bug scenario: 20-hour-old ACTIVE task with completed seed thought."""
    # Simulate Datum's first shutdown attempt (20 hours ago)
    task1, was_created1 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="Datum first shutdown",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created1 is True
    update_task_status(task1.task_id, TaskStatus.ACTIVE, "__shared__", time_service, db_path=temp_db)

    # Manually update created_at to be 20 hours ago (simulating Datum's stale task)
    old_time = (datetime.now(timezone.utc) - timedelta(hours=20)).isoformat()
    with get_db_connection(temp_db) as conn:
        conn.execute("UPDATE tasks SET created_at = ? WHERE task_id = ?", (old_time, task1.task_id))
        conn.commit()

    # Now simulate Datum's second shutdown attempt - should DELETE stale task and create new one
    task2, was_created2 = try_claim_shared_task(
        task_type="shutdown",
        channel_id="system",
        description="Datum second shutdown",
        priority=10,
        time_service=time_service,
        db_path=temp_db,
    )

    assert was_created2 is True, "Should create new task after deleting 20-hour-old ACTIVE task"
    assert task2.task_id == task1.task_id  # Same deterministic ID
    assert task2.status == TaskStatus.PENDING  # Fresh task should be PENDING

    # Verify the old task was actually deleted and replaced (check created_at is recent)
    from ciris_engine.logic.persistence.models.tasks import get_task_by_id

    retrieved_task = get_task_by_id(task2.task_id, "__shared__", db_path=temp_db)
    assert retrieved_task is not None

    # Task should have been created very recently (within last minute)
    task_age = datetime.now(timezone.utc) - datetime.fromisoformat(retrieved_task.created_at.replace("Z", "+00:00"))
    assert task_age < timedelta(minutes=1), "New task should have fresh created_at timestamp"
