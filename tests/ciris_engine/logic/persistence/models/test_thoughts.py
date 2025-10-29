"""
Comprehensive unit tests for ciris_engine/logic/persistence/models/thoughts.py

Tests focus on multi-occurrence functionality, thought ownership transfer,
and all query functions with occurrence_id parameters.
"""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.persistence.db import get_db_connection, initialize_database
from ciris_engine.logic.persistence.models.tasks import add_task
from ciris_engine.logic.persistence.models.thoughts import (
    add_thought,
    async_get_thought_by_id,
    async_get_thought_status,
    async_get_thoughts_by_ids,
    count_thoughts,
    delete_thoughts_by_ids,
    get_recent_thoughts,
    get_thought_by_id,
    get_thoughts_by_ids,
    get_thoughts_by_status,
    get_thoughts_by_task_id,
    get_thoughts_older_than,
    transfer_thought_ownership,
    update_thought_status,
)
from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought


class MockTimeService:
    """Mock time service for testing."""

    def __init__(self, fixed_time: Optional[str] = None):
        self.fixed_time = fixed_time

    def now_iso(self) -> str:
        if self.fixed_time:
            return self.fixed_time
        return datetime.now(timezone.utc).isoformat()


class MockAuditService:
    """Mock audit service for testing."""

    def __init__(self):
        self.events: List[tuple] = []

    async def log_event(self, event_type: str, event_data: any) -> None:
        """Log event for verification."""
        self.events.append((event_type, event_data))


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Initialize database schema
    initialize_database(db_path)

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def time_service():
    """Provide mock time service."""
    return MockTimeService()


@pytest.fixture
def audit_service():
    """Provide mock audit service."""
    return MockAuditService()


def create_test_task(
    task_id: str = "task-1",
    occurrence_id: str = "default",
    status: TaskStatus = TaskStatus.PENDING,
    **kwargs,
) -> Task:
    """Helper to create a test Task object."""
    defaults = {
        "task_id": task_id,
        "agent_occurrence_id": occurrence_id,
        "channel_id": "test-channel",
        "description": "Test task",
        "status": status,
        "priority": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    defaults.update(kwargs)
    return Task(**defaults)


def create_test_thought(
    thought_id: str = "test-thought-1",
    occurrence_id: str = "default",
    status: ThoughtStatus = ThoughtStatus.PENDING,
    task_id: str = "task-1",
    content: str = "Test thought content",
    db_path: Optional[str] = None,
    **kwargs,
) -> Thought:
    """Helper to create a test Thought object.

    Automatically creates the parent task in the database if db_path is provided.
    """
    # Create parent task if db_path provided
    if db_path is not None:
        task = create_test_task(task_id=task_id, occurrence_id=occurrence_id)
        try:
            add_task(task, db_path=db_path)
        except Exception:
            # Task might already exist, that's ok
            pass

    defaults = {
        "thought_id": thought_id,
        "agent_occurrence_id": occurrence_id,
        "source_task_id": task_id,
        "channel_id": "test-channel",
        "thought_type": "standard",  # Use valid ThoughtType enum value
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "round_number": 0,
        "content": content,
        "thought_depth": 1,
    }
    defaults.update(kwargs)
    return Thought(**defaults)


# ========== transfer_thought_ownership Tests ==========


def test_transfer_thought_ownership_success(
    temp_db: str, time_service: TimeServiceProtocol, audit_service: AuditServiceProtocol
):
    """Test successful thought ownership transfer."""
    # Create a thought with __shared__ ownership
    thought = create_test_thought(
        thought_id="shared-thought-1",
        occurrence_id="__shared__",
        status=ThoughtStatus.PENDING,
        db_path=temp_db,
    )
    add_thought(thought, db_path=temp_db)

    # Transfer ownership to specific occurrence
    result = transfer_thought_ownership(
        thought_id="shared-thought-1",
        from_occurrence_id="__shared__",
        to_occurrence_id="occurrence-123",
        time_service=time_service,
        audit_service=audit_service,
        db_path=temp_db,
    )

    assert result is True

    # Verify ownership was transferred
    transferred_thought = get_thought_by_id("shared-thought-1", "occurrence-123", db_path=temp_db)
    assert transferred_thought is not None
    assert transferred_thought.agent_occurrence_id == "occurrence-123"

    # Verify old ownership is gone
    old_thought = get_thought_by_id("shared-thought-1", "__shared__", db_path=temp_db)
    assert old_thought is None


def test_transfer_thought_ownership_not_found(
    temp_db: str, time_service: TimeServiceProtocol, audit_service: AuditServiceProtocol
):
    """Test transfer when thought doesn't exist with from_occurrence_id."""
    result = transfer_thought_ownership(
        thought_id="nonexistent-thought",
        from_occurrence_id="__shared__",
        to_occurrence_id="occurrence-123",
        time_service=time_service,
        audit_service=audit_service,
        db_path=temp_db,
    )

    assert result is False


def test_transfer_thought_ownership_wrong_owner(
    temp_db: str, time_service: TimeServiceProtocol, audit_service: AuditServiceProtocol
):
    """Test transfer when thought exists but with different owner."""
    # Create thought with occurrence-456
    thought = create_test_thought(thought_id="owned-thought", occurrence_id="occurrence-456", db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    # Try to transfer from __shared__ (wrong owner)
    result = transfer_thought_ownership(
        thought_id="owned-thought",
        from_occurrence_id="__shared__",
        to_occurrence_id="occurrence-123",
        time_service=time_service,
        audit_service=audit_service,
        db_path=temp_db,
    )

    assert result is False

    # Verify ownership didn't change
    thought_check = get_thought_by_id("owned-thought", "occurrence-456", db_path=temp_db)
    assert thought_check is not None
    assert thought_check.agent_occurrence_id == "occurrence-456"


def test_transfer_thought_ownership_database_error(
    time_service: TimeServiceProtocol, audit_service: AuditServiceProtocol
):
    """Test transfer with database error (invalid path)."""
    result = transfer_thought_ownership(
        thought_id="test-thought",
        from_occurrence_id="__shared__",
        to_occurrence_id="occurrence-123",
        time_service=time_service,
        audit_service=audit_service,
        db_path="/invalid/path/to/db.db",
    )

    assert result is False


@pytest.mark.asyncio
async def test_transfer_thought_ownership_audit_logging(temp_db: str, time_service: TimeServiceProtocol):
    """Test that transfer logs audit events properly."""
    audit_service = MockAuditService()

    # Create thought
    thought = create_test_thought(thought_id="audit-test-thought", occurrence_id="__shared__", db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    # Transfer with running event loop
    result = transfer_thought_ownership(
        thought_id="audit-test-thought",
        from_occurrence_id="__shared__",
        to_occurrence_id="occurrence-789",
        time_service=time_service,
        audit_service=audit_service,
        db_path=temp_db,
    )

    assert result is True

    # Give async task time to execute
    await asyncio.sleep(0.1)

    # Verify audit event was logged
    assert len(audit_service.events) == 1
    event_type, event_data = audit_service.events[0]
    assert event_type == "thought_ownership_transfer"
    assert event_data.entity_id == "audit-test-thought"
    assert event_data.outcome == "success"


def test_transfer_thought_ownership_no_event_loop(
    temp_db: str, time_service: TimeServiceProtocol, audit_service: AuditServiceProtocol
):
    """Test transfer without event loop (should log debug message)."""
    # Create thought
    thought = create_test_thought(thought_id="no-loop-thought", occurrence_id="__shared__", db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    # Call outside of event loop (should handle gracefully)
    result = transfer_thought_ownership(
        thought_id="no-loop-thought",
        from_occurrence_id="__shared__",
        to_occurrence_id="occurrence-999",
        time_service=time_service,
        audit_service=audit_service,
        db_path=temp_db,
    )

    # Should still succeed even if audit logging deferred
    assert result is True


# ========== add_thought and get_thought_by_id Exception Tests ==========


def test_add_thought_exception_handling():
    """Test that add_thought raises exception on database error."""
    thought = create_test_thought("test-t1", "occ1", db_path=None)

    # Try to add to invalid database
    with pytest.raises(Exception):
        add_thought(thought, db_path="/invalid/path/db.db")


def test_get_thought_by_id_exception_returns_none():
    """Test that get_thought_by_id returns None on database error."""
    # This should handle the exception and return None
    result = get_thought_by_id("test-t1", "occ1", db_path="/invalid/path/db.db")
    assert result is None


# ========== get_thoughts_by_status Tests ==========


def test_get_thoughts_by_status_basic(temp_db: str):
    """Test getting thoughts by status for specific occurrence."""
    # Create thoughts with different statuses and occurrences
    thoughts = [
        create_test_thought("t1", "occ1", ThoughtStatus.PENDING, db_path=temp_db),
        create_test_thought("t2", "occ1", ThoughtStatus.PENDING, db_path=temp_db),
        create_test_thought("t3", "occ1", ThoughtStatus.PROCESSING, db_path=temp_db),
        create_test_thought("t4", "occ2", ThoughtStatus.PENDING, db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    # Get PENDING thoughts for occ1
    result = get_thoughts_by_status(ThoughtStatus.PENDING, "occ1", db_path=temp_db)

    assert len(result) == 2
    assert all(t.status == ThoughtStatus.PENDING for t in result)
    assert all(t.agent_occurrence_id == "occ1" for t in result)


def test_get_thoughts_by_status_with_limit(temp_db: str):
    """Test getting thoughts by status with limit."""
    # Create 5 pending thoughts
    for i in range(5):
        thought = create_test_thought(f"t{i}", "occ1", ThoughtStatus.PENDING, db_path=temp_db)
        add_thought(thought, db_path=temp_db)

    # Get only 3
    result = get_thoughts_by_status(ThoughtStatus.PENDING, "occ1", db_path=temp_db, limit=3)

    assert len(result) == 3


def test_get_thoughts_by_status_invalid_type(temp_db: str):
    """Test that invalid status type raises TypeError."""
    with pytest.raises(TypeError, match="Expected ThoughtStatus enum"):
        get_thoughts_by_status("invalid", "occ1", db_path=temp_db)


def test_get_thoughts_by_status_empty_result(temp_db: str):
    """Test getting thoughts when none match."""
    thought = create_test_thought("t1", "occ1", ThoughtStatus.PENDING, db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    # Query different occurrence
    result = get_thoughts_by_status(ThoughtStatus.PENDING, "occ2", db_path=temp_db)

    assert len(result) == 0


def test_get_thoughts_by_status_database_error():
    """Test handling database error gracefully."""
    result = get_thoughts_by_status(
        ThoughtStatus.PENDING,
        "occ1",
        db_path="/invalid/path.db",
    )

    assert len(result) == 0


# ========== get_thoughts_by_ids Tests ==========


def test_get_thoughts_by_ids_multiple(temp_db: str):
    """Test batch fetching multiple thoughts."""
    thoughts = [
        create_test_thought("t1", "occ1", db_path=temp_db),
        create_test_thought("t2", "occ1", db_path=temp_db),
        create_test_thought("t3", "occ1", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    result = get_thoughts_by_ids(["t1", "t2", "t3"], "occ1", db_path=temp_db)

    assert len(result) == 3
    assert "t1" in result
    assert "t2" in result
    assert "t3" in result
    assert result["t1"].thought_id == "t1"


def test_get_thoughts_by_ids_empty_list(temp_db: str):
    """Test with empty thought_ids list."""
    result = get_thoughts_by_ids([], "occ1", db_path=temp_db)

    assert result == {}


def test_get_thoughts_by_ids_partial_match(temp_db: str):
    """Test when only some IDs exist."""
    thought = create_test_thought("t1", "occ1", db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    result = get_thoughts_by_ids(["t1", "nonexistent"], "occ1", db_path=temp_db)

    assert len(result) == 1
    assert "t1" in result
    assert "nonexistent" not in result


def test_get_thoughts_by_ids_wrong_occurrence(temp_db: str):
    """Test that thoughts from different occurrence are not returned."""
    thought = create_test_thought("t1", "occ1", db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    # Query with different occurrence
    result = get_thoughts_by_ids(["t1"], "occ2", db_path=temp_db)

    assert len(result) == 0


def test_get_thoughts_by_ids_database_error():
    """Test handling database error."""
    result = get_thoughts_by_ids(["t1"], "occ1", db_path="/invalid/path.db")

    assert result == {}


# ========== Async Function Tests ==========


@pytest.mark.asyncio
async def test_async_get_thought_by_id(temp_db: str):
    """Test async wrapper for get_thought_by_id."""
    thought = create_test_thought("async-t1", "occ1", db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    result = await async_get_thought_by_id("async-t1", "occ1", db_path=temp_db)

    assert result is not None
    assert result.thought_id == "async-t1"
    assert result.agent_occurrence_id == "occ1"


@pytest.mark.asyncio
async def test_async_get_thought_by_id_not_found(temp_db: str):
    """Test async get when thought doesn't exist."""
    result = await async_get_thought_by_id("nonexistent", "occ1", db_path=temp_db)

    assert result is None


@pytest.mark.asyncio
async def test_async_get_thoughts_by_ids(temp_db: str):
    """Test async wrapper for get_thoughts_by_ids."""
    thoughts = [
        create_test_thought("async-t1", "occ1", db_path=temp_db),
        create_test_thought("async-t2", "occ1", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    result = await async_get_thoughts_by_ids(["async-t1", "async-t2"], "occ1", db_path=temp_db)

    assert len(result) == 2
    assert "async-t1" in result
    assert "async-t2" in result


@pytest.mark.asyncio
async def test_async_get_thought_status(temp_db: str):
    """Test async retrieval of thought status."""
    thought = create_test_thought("status-t1", "occ1", ThoughtStatus.PROCESSING, db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    status = await async_get_thought_status("status-t1", "occ1", db_path=temp_db)

    assert status == ThoughtStatus.PROCESSING


@pytest.mark.asyncio
async def test_async_get_thought_status_not_found(temp_db: str):
    """Test async status retrieval when thought doesn't exist."""
    status = await async_get_thought_status("nonexistent", "occ1", db_path=temp_db)

    assert status is None


@pytest.mark.asyncio
async def test_async_get_thought_status_database_error():
    """Test async status retrieval with database error."""
    status = await async_get_thought_status("t1", "occ1", db_path="/invalid/path.db")

    assert status is None


# ========== count_thoughts Tests ==========


def test_count_thoughts_basic(temp_db: str):
    """Test counting PENDING and PROCESSING thoughts."""
    thoughts = [
        create_test_thought("t1", "occ1", ThoughtStatus.PENDING, db_path=temp_db),
        create_test_thought("t2", "occ1", ThoughtStatus.PROCESSING, db_path=temp_db),
        create_test_thought("t3", "occ1", ThoughtStatus.COMPLETED, db_path=temp_db),
        create_test_thought("t4", "occ1", ThoughtStatus.PENDING, db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    count = count_thoughts("occ1", db_path=temp_db)

    # Should count 3 (2 PENDING + 1 PROCESSING, excluding COMPLETED)
    assert count == 3


def test_count_thoughts_occurrence_isolation(temp_db: str):
    """Test that count is isolated by occurrence."""
    thoughts = [
        create_test_thought("t1", "occ1", ThoughtStatus.PENDING, db_path=temp_db),
        create_test_thought("t2", "occ2", ThoughtStatus.PENDING, db_path=temp_db),
        create_test_thought("t3", "occ2", ThoughtStatus.PENDING, db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    count_occ1 = count_thoughts("occ1", db_path=temp_db)
    count_occ2 = count_thoughts("occ2", db_path=temp_db)

    assert count_occ1 == 1
    assert count_occ2 == 2


def test_count_thoughts_database_error():
    """Test count with database error."""
    count = count_thoughts("occ1", db_path="/invalid/path.db")

    assert count == 0


# ========== delete_thoughts_by_ids Tests ==========


def test_delete_thoughts_by_ids_success(temp_db: str):
    """Test deleting multiple thoughts."""
    thoughts = [
        create_test_thought("del-t1", "occ1", db_path=temp_db),
        create_test_thought("del-t2", "occ1", db_path=temp_db),
        create_test_thought("del-t3", "occ1", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    deleted = delete_thoughts_by_ids(["del-t1", "del-t2"], "occ1", db_path=temp_db)

    assert deleted == 2

    # Verify deletion
    assert get_thought_by_id("del-t1", "occ1", db_path=temp_db) is None
    assert get_thought_by_id("del-t2", "occ1", db_path=temp_db) is None
    assert get_thought_by_id("del-t3", "occ1", db_path=temp_db) is not None


def test_delete_thoughts_by_ids_empty_list(temp_db: str):
    """Test delete with empty list."""
    deleted = delete_thoughts_by_ids([], "occ1", db_path=temp_db)

    assert deleted == 0


def test_delete_thoughts_by_ids_occurrence_isolation(temp_db: str):
    """Test that delete respects occurrence boundaries."""
    # Create thoughts with different IDs but same base name in different occurrences
    thoughts = [
        create_test_thought("del-occ1-t1", "occ1", db_path=temp_db),
        create_test_thought("del-occ2-t1", "occ2", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    # Try to delete occ2 thought using occ1 context (should not delete)
    deleted = delete_thoughts_by_ids(["del-occ2-t1"], "occ1", db_path=temp_db)

    assert deleted == 0  # Should not delete thought from different occurrence

    # Verify both still exist in their respective occurrences
    assert get_thought_by_id("del-occ1-t1", "occ1", db_path=temp_db) is not None
    assert get_thought_by_id("del-occ2-t1", "occ2", db_path=temp_db) is not None


def test_delete_thoughts_by_ids_database_error():
    """Test delete with database error."""
    deleted = delete_thoughts_by_ids(["t1"], "occ1", db_path="/invalid/path.db")

    assert deleted == 0


# ========== get_thoughts_older_than Tests ==========


def test_get_thoughts_older_than_basic(temp_db: str):
    """Test getting thoughts older than timestamp."""
    now = datetime.now(timezone.utc)
    old_time = (now - timedelta(hours=2)).isoformat()
    newer_time = (now - timedelta(hours=1)).isoformat()

    thoughts = [
        create_test_thought("old1", "occ1", created_at=old_time, db_path=temp_db),
        create_test_thought("old2", "occ1", created_at=old_time, db_path=temp_db),
        create_test_thought("new1", "occ1", created_at=newer_time, db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    # Get thoughts older than 90 minutes ago
    cutoff = (now - timedelta(minutes=90)).isoformat()
    result = get_thoughts_older_than(cutoff, "occ1", db_path=temp_db)

    assert len(result) == 2
    assert all(t.thought_id in ["old1", "old2"] for t in result)


def test_get_thoughts_older_than_occurrence_isolation(temp_db: str):
    """Test that query respects occurrence boundaries."""
    old_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

    thoughts = [
        create_test_thought("old1", "occ1", created_at=old_time, db_path=temp_db),
        create_test_thought("old2", "occ2", created_at=old_time, db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    result = get_thoughts_older_than(
        (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "occ1",
        db_path=temp_db,
    )

    assert len(result) == 1
    assert result[0].agent_occurrence_id == "occ1"


def test_get_thoughts_older_than_database_error():
    """Test handling database error."""
    result = get_thoughts_older_than(
        datetime.now(timezone.utc).isoformat(),
        "occ1",
        db_path="/invalid/path.db",
    )

    assert len(result) == 0


# ========== get_recent_thoughts Tests ==========


def test_get_recent_thoughts_basic(temp_db: str):
    """Test getting recent thoughts as summaries."""
    thoughts = [
        create_test_thought("rec1", "occ1", db_path=temp_db),
        create_test_thought("rec2", "occ1", db_path=temp_db),
        create_test_thought("rec3", "occ1", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    result = get_recent_thoughts("occ1", limit=2, db_path=temp_db)

    assert len(result) == 2
    # Should be ThoughtSummary objects
    assert all(hasattr(r, "thought_id") for r in result)
    assert all(hasattr(r, "status") for r in result)


def test_get_recent_thoughts_occurrence_isolation(temp_db: str):
    """Test that recent thoughts respects occurrence."""
    thoughts = [
        create_test_thought("rec1", "occ1", db_path=temp_db),
        create_test_thought("rec2", "occ2", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    result = get_recent_thoughts("occ1", limit=10, db_path=temp_db)

    assert len(result) == 1
    assert result[0].thought_id == "rec1"


def test_get_recent_thoughts_database_error():
    """Test handling database error."""
    result = get_recent_thoughts("occ1", limit=10, db_path="/invalid/path.db")

    assert len(result) == 0


# ========== get_thoughts_by_task_id Tests ==========


def test_get_thoughts_by_task_id_basic(temp_db: str):
    """Test getting thoughts by task ID."""
    thoughts = [
        create_test_thought("t1", "occ1", task_id="task-123", db_path=temp_db),
        create_test_thought("t2", "occ1", task_id="task-123", db_path=temp_db),
        create_test_thought("t3", "occ1", task_id="task-456", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    result = get_thoughts_by_task_id("task-123", "occ1", db_path=temp_db)

    assert len(result) == 2
    assert all(t.source_task_id == "task-123" for t in result)


def test_get_thoughts_by_task_id_occurrence_isolation(temp_db: str):
    """Test that task query respects occurrence."""
    thoughts = [
        create_test_thought("t1", "occ1", task_id="task-123", db_path=temp_db),
        create_test_thought("t2", "occ2", task_id="task-123", db_path=temp_db),
    ]
    for t in thoughts:
        add_thought(t, db_path=temp_db)

    result = get_thoughts_by_task_id("task-123", "occ1", db_path=temp_db)

    assert len(result) == 1
    assert result[0].agent_occurrence_id == "occ1"


def test_get_thoughts_by_task_id_database_error():
    """Test handling database error."""
    result = get_thoughts_by_task_id("task-123", "occ1", db_path="/invalid/path.db")

    assert len(result) == 0


# ========== update_thought_status Tests ==========


def test_update_thought_status_success(temp_db: str):
    """Test updating thought status."""
    thought = create_test_thought("upd-t1", "occ1", ThoughtStatus.PENDING, db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    result = update_thought_status(
        "upd-t1",
        ThoughtStatus.COMPLETED,
        "occ1",
        db_path=temp_db,
    )

    assert result is True

    # Verify update
    updated = get_thought_by_id("upd-t1", "occ1", db_path=temp_db)
    assert updated.status == ThoughtStatus.COMPLETED


def test_update_thought_status_not_found(temp_db: str):
    """Test updating non-existent thought."""
    result = update_thought_status(
        "nonexistent",
        ThoughtStatus.COMPLETED,
        "occ1",
        db_path=temp_db,
    )

    assert result is False


def test_update_thought_status_wrong_occurrence(temp_db: str):
    """Test that update respects occurrence boundaries."""
    thought = create_test_thought("upd-t1", "occ1", ThoughtStatus.PENDING, db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    # Try to update from wrong occurrence
    result = update_thought_status(
        "upd-t1",
        ThoughtStatus.COMPLETED,
        "occ2",
        db_path=temp_db,
    )

    assert result is False

    # Verify status unchanged
    thought_check = get_thought_by_id("upd-t1", "occ1", db_path=temp_db)
    assert thought_check.status == ThoughtStatus.PENDING


def test_update_thought_status_database_error():
    """Test update with database error."""
    result = update_thought_status(
        "t1",
        ThoughtStatus.COMPLETED,
        "occ1",
        db_path="/invalid/path.db",
    )

    assert result is False


def test_update_thought_status_with_final_action(temp_db: str):
    """Test updating status with final_action (should be ignored per code comments)."""
    thought = create_test_thought("upd-t2", "occ1", ThoughtStatus.PENDING, db_path=temp_db)
    add_thought(thought, db_path=temp_db)

    # Pass final_action (should be ignored based on DELETED comment in code)
    result = update_thought_status(
        "upd-t2",
        ThoughtStatus.COMPLETED,
        "occ1",
        db_path=temp_db,
        final_action={"test": "data"},
    )

    assert result is True
