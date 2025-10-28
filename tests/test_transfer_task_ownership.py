#!/usr/bin/env python3
"""
Test the transfer_task_ownership function for shared task ownership transfers.

This tests the critical P0 fix for multi-occurrence shared task claiming where
tasks need to be transferred from "__shared__" occurrence to a specific occurrence
before status updates can work correctly.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tempfile
from datetime import datetime, timezone
from unittest.mock import Mock

from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tasks import (
    add_task,
    get_task_by_id,
    transfer_task_ownership,
    update_task_status,
)
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext


class MockTimeService:
    """Mock time service for testing."""

    def now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()


def test_transfer_task_ownership_success(mock_audit_service):
    """Test successful transfer from __shared__ to specific occurrence."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
        db_path = tmp_db.name

    try:
        # Initialize database schema
        initialize_database(db_path)
        time_service = MockTimeService()

        # Create a task with __shared__ occurrence
        task_context = TaskContext(
            channel_id="test-channel",
            user_id="test-user",
            correlation_id="test-correlation",
            parent_task_id=None,
        )

        task = Task(
            task_id="TEST_TRANSFER_1",
            channel_id="test-channel",
            description="Test shared task",
            status=TaskStatus.PENDING,
            priority=1,
            context=task_context,
            agent_occurrence_id="__shared__",
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
        )

        # Create task in database
        add_task(task, db_path=db_path)

        # Verify task exists with __shared__ occurrence
        retrieved = get_task_by_id(task.task_id, "__shared__", db_path=db_path)
        assert retrieved is not None
        assert retrieved.agent_occurrence_id == "__shared__"

        # Transfer ownership to specific occurrence
        result = transfer_task_ownership(
            task_id=task.task_id,
            from_occurrence_id="__shared__",
            to_occurrence_id="occurrence-123",
            time_service=time_service,
            audit_service=mock_audit_service,
            db_path=db_path,
        )

        # Verify transfer succeeded
        assert result is True

        # Verify task is no longer accessible via __shared__
        shared_task = get_task_by_id(task.task_id, "__shared__", db_path=db_path)
        assert shared_task is None, "Task should not be accessible via __shared__ after transfer"

        # Verify task IS accessible via new occurrence
        transferred = get_task_by_id(task.task_id, "occurrence-123", db_path=db_path)
        assert transferred is not None, "Task should be accessible via new occurrence"
        assert transferred.agent_occurrence_id == "occurrence-123"
        assert transferred.task_id == task.task_id
        assert transferred.description == task.description

        print("✓ Test 1 passed: Successful ownership transfer from __shared__ to specific occurrence")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_transfer_task_ownership_enables_status_update(mock_audit_service):
    """Test that transfer enables subsequent status updates to work correctly.

    This is the critical bug fix test: without transfer, update_task_status
    would fail because it filters by both task_id AND occurrence_id.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
        db_path = tmp_db.name

    try:
        # Initialize database schema
        initialize_database(db_path)
        time_service = MockTimeService()

        # Create shared task
        task_context = TaskContext(
            channel_id="test-channel",
            user_id="test-user",
            correlation_id="test-correlation",
            parent_task_id=None,
        )

        task = Task(
            task_id="TEST_STATUS_UPDATE",
            channel_id="test-channel",
            description="Test status update after transfer",
            status=TaskStatus.PENDING,
            priority=1,
            context=task_context,
            agent_occurrence_id="__shared__",
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
        )

        add_task(task, db_path=db_path)

        # Transfer ownership
        transfer_result = transfer_task_ownership(
            task_id=task.task_id,
            from_occurrence_id="__shared__",
            to_occurrence_id="occurrence-456",
            time_service=time_service,
            audit_service=mock_audit_service,
            db_path=db_path,
        )
        assert transfer_result is True

        # Now update status using new occurrence ID - this should succeed
        status_result = update_task_status(
            task_id=task.task_id,
            new_status=TaskStatus.ACTIVE,
            occurrence_id="occurrence-456",
            time_service=time_service,
            db_path=db_path,
        )

        assert status_result is True, "Status update should succeed after ownership transfer"

        # Verify status was actually updated
        updated_task = get_task_by_id(task.task_id, "occurrence-456", db_path=db_path)
        assert updated_task is not None
        assert updated_task.status == TaskStatus.ACTIVE, "Status should be ACTIVE after update"

        print("✓ Test 2 passed: Status update works correctly after ownership transfer")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_transfer_task_ownership_wrong_from_occurrence(mock_audit_service):
    """Test transfer fails when from_occurrence_id doesn't match database."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
        db_path = tmp_db.name

    try:
        # Initialize database schema
        initialize_database(db_path)
        time_service = MockTimeService()

        # Create task with specific occurrence
        task_context = TaskContext(
            channel_id="test-channel",
            user_id="test-user",
            correlation_id="test-correlation",
            parent_task_id=None,
        )

        task = Task(
            task_id="TEST_WRONG_FROM",
            channel_id="test-channel",
            description="Test wrong from occurrence",
            status=TaskStatus.PENDING,
            priority=1,
            context=task_context,
            agent_occurrence_id="occurrence-original",
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
        )

        add_task(task, db_path=db_path)

        # Try to transfer from wrong occurrence
        result = transfer_task_ownership(
            task_id=task.task_id,
            from_occurrence_id="occurrence-wrong",  # Wrong!
            to_occurrence_id="occurrence-new",
            time_service=time_service,
            audit_service=mock_audit_service,
            db_path=db_path,
        )

        # Transfer should fail
        assert result is False, "Transfer should fail when from_occurrence_id doesn't match"

        # Verify task still has original occurrence
        original = get_task_by_id(task.task_id, "occurrence-original", db_path=db_path)
        assert original is not None
        assert original.agent_occurrence_id == "occurrence-original"

        print("✓ Test 3 passed: Transfer fails correctly when from_occurrence_id is wrong")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_transfer_task_ownership_nonexistent_task(mock_audit_service):
    """Test transfer fails gracefully for nonexistent task."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
        db_path = tmp_db.name

    try:
        # Initialize database schema
        initialize_database(db_path)
        time_service = MockTimeService()

        # Try to transfer task that doesn't exist
        result = transfer_task_ownership(
            task_id="NONEXISTENT_TASK",
            from_occurrence_id="__shared__",
            to_occurrence_id="occurrence-789",
            time_service=time_service,
            audit_service=mock_audit_service,
            db_path=db_path,
        )

        # Should fail gracefully
        assert result is False, "Transfer should fail for nonexistent task"

        print("✓ Test 4 passed: Transfer fails gracefully for nonexistent task")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_transfer_task_ownership_multiple_times(mock_audit_service):
    """Test that a task can be transferred multiple times (e.g., re-claiming)."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
        db_path = tmp_db.name

    try:
        # Initialize database schema
        initialize_database(db_path)
        time_service = MockTimeService()

        # Create shared task
        task_context = TaskContext(
            channel_id="test-channel",
            user_id="test-user",
            correlation_id="test-correlation",
            parent_task_id=None,
        )

        task = Task(
            task_id="TEST_MULTIPLE_TRANSFER",
            channel_id="test-channel",
            description="Test multiple transfers",
            status=TaskStatus.PENDING,
            priority=1,
            context=task_context,
            agent_occurrence_id="__shared__",
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
        )

        add_task(task, db_path=db_path)

        # First transfer: __shared__ -> occurrence-1
        result1 = transfer_task_ownership(
            task_id=task.task_id,
            from_occurrence_id="__shared__",
            to_occurrence_id="occurrence-1",
            time_service=time_service,
            audit_service=mock_audit_service,
            db_path=db_path,
        )
        assert result1 is True

        # Verify first transfer
        task1 = get_task_by_id(task.task_id, "occurrence-1", db_path=db_path)
        assert task1 is not None
        assert task1.agent_occurrence_id == "occurrence-1"

        # Second transfer: occurrence-1 -> occurrence-2
        result2 = transfer_task_ownership(
            task_id=task.task_id,
            from_occurrence_id="occurrence-1",
            to_occurrence_id="occurrence-2",
            time_service=time_service,
            audit_service=mock_audit_service,
            db_path=db_path,
        )
        assert result2 is True

        # Verify second transfer
        task2 = get_task_by_id(task.task_id, "occurrence-2", db_path=db_path)
        assert task2 is not None
        assert task2.agent_occurrence_id == "occurrence-2"

        # Verify no longer accessible via occurrence-1
        task1_after = get_task_by_id(task.task_id, "occurrence-1", db_path=db_path)
        assert task1_after is None

        print("✓ Test 5 passed: Multiple transfers work correctly")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_transfer_preserves_all_task_data(mock_audit_service):
    """Test that transfer only changes occurrence_id and preserves all other data."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp_db:
        db_path = tmp_db.name

    try:
        # Initialize database schema
        initialize_database(db_path)
        time_service = MockTimeService()

        # Create task with rich data
        task_context = TaskContext(
            channel_id="rich-channel",
            user_id="rich-user",
            correlation_id="rich-correlation",
            parent_task_id="PARENT_123",
        )

        original_time = time_service.now_iso()
        task = Task(
            task_id="TEST_DATA_PRESERVATION",
            channel_id="rich-channel",
            description="Test data preservation during transfer",
            status=TaskStatus.PENDING,
            priority=5,
            context=task_context,
            agent_occurrence_id="__shared__",
            created_at=original_time,
            updated_at=original_time,
        )

        add_task(task, db_path=db_path)

        # Transfer ownership
        transfer_task_ownership(
            task_id=task.task_id,
            from_occurrence_id="__shared__",
            to_occurrence_id="occurrence-preserve",
            time_service=time_service,
            audit_service=mock_audit_service,
            db_path=db_path,
        )

        # Retrieve transferred task
        transferred = get_task_by_id(task.task_id, "occurrence-preserve", db_path=db_path)
        assert transferred is not None

        # Verify all data preserved except occurrence_id
        assert transferred.task_id == task.task_id
        assert transferred.description == task.description
        assert transferred.status == task.status
        assert transferred.priority == task.priority
        assert transferred.context.channel_id == task.context.channel_id
        assert transferred.context.user_id == task.context.user_id
        assert transferred.context.correlation_id == task.context.correlation_id
        assert transferred.context.parent_task_id == task.context.parent_task_id
        assert transferred.created_at == original_time

        # Only occurrence_id should change
        assert transferred.agent_occurrence_id == "occurrence-preserve"

        print("✓ Test 6 passed: Transfer preserves all task data except occurrence_id")

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def run_all_tests():
    """Run all transfer_task_ownership tests."""
    print("=" * 80)
    print("Testing transfer_task_ownership function")
    print("=" * 80)
    print()

    test_transfer_task_ownership_success()
    test_transfer_task_ownership_enables_status_update()
    test_transfer_task_ownership_wrong_from_occurrence()
    test_transfer_task_ownership_nonexistent_task()
    test_transfer_task_ownership_multiple_times()
    test_transfer_preserves_all_task_data()

    print()
    print("=" * 80)
    print("✅ All transfer_task_ownership tests passed!")
    print("=" * 80)
    print()
    print("Tests verified:")
    print("  ✓ Successful ownership transfer from __shared__ to specific occurrence")
    print("  ✓ Status updates work correctly after ownership transfer")
    print("  ✓ Transfer fails when from_occurrence_id doesn't match")
    print("  ✓ Transfer fails gracefully for nonexistent tasks")
    print("  ✓ Multiple sequential transfers work correctly")
    print("  ✓ All task data preserved except occurrence_id")
    print()
    print("Critical P0 bug fix validated:")
    print("  - Tasks can be transferred from __shared__ to claiming occurrence")
    print("  - update_task_status() works correctly after transfer")
    print("  - Database row is properly updated before status changes")
    print()


if __name__ == "__main__":
    run_all_tests()
