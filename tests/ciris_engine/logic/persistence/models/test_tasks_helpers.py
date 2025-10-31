"""
Unit tests for task persistence helper functions.

Tests the private helper functions extracted from add_task to reduce cognitive complexity.
"""

import tempfile
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tasks import (
    _get_correlation_id_from_task,
    _handle_duplicate_task,
    _is_correlation_id_constraint_violation,
    add_task,
)
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext


class TestIsCorrelationIdConstraintViolation:
    """Test the _is_correlation_id_constraint_violation helper function."""

    def test_sqlite_correlation_constraint(self):
        """Test SQLite correlation_id constraint error detection."""
        error_msg = "unique constraint failed: tasks.agent_occurrence_id, tasks.json_extract"
        assert _is_correlation_id_constraint_violation(error_msg) is True

    def test_postgresql_correlation_constraint(self):
        """Test PostgreSQL correlation_id constraint error detection."""
        error_msg = 'duplicate key value violates unique constraint "idx_tasks_occurrence_correlation"'
        assert _is_correlation_id_constraint_violation(error_msg) is True

    def test_generic_correlation_mention(self):
        """Test detection with generic correlation mention."""
        error_msg = "unique constraint failed on correlation field"
        assert _is_correlation_id_constraint_violation(error_msg) is True

    def test_non_correlation_unique_constraint(self):
        """Test that non-correlation unique constraints are not detected."""
        error_msg = "unique constraint failed: tasks.task_id"
        assert _is_correlation_id_constraint_violation(error_msg) is False

    def test_non_unique_constraint_error(self):
        """Test that non-constraint errors are not detected."""
        error_msg = "foreign key constraint failed"
        assert _is_correlation_id_constraint_violation(error_msg) is False

    def test_empty_error_message(self):
        """Test handling of empty error message."""
        assert _is_correlation_id_constraint_violation("") is False

    def test_case_sensitivity(self):
        """Test that detection works with mixed case (should be lowercase)."""
        # Function expects lowercase input
        error_msg = "UNIQUE CONSTRAINT failed on CORRELATION"
        assert _is_correlation_id_constraint_violation(error_msg.lower()) is True


class TestGetCorrelationIdFromTask:
    """Test the _get_correlation_id_from_task helper function."""

    def test_task_with_correlation_id(self):
        """Test extracting correlation_id from task with context."""
        task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Test task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id="reddit_post_abc123",
                agent_occurrence_id="default",
            ),
        )

        correlation_id = _get_correlation_id_from_task(task)
        assert correlation_id == "reddit_post_abc123"

    def test_task_with_empty_correlation_id(self):
        """Test extracting correlation_id when it's an empty string."""
        task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Test task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id="",
                agent_occurrence_id="default",
            ),
        )

        correlation_id = _get_correlation_id_from_task(task)
        # Empty string is still returned as-is
        assert correlation_id == ""

    def test_task_without_context(self):
        """Test extracting correlation_id from task without context."""
        task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Test task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        correlation_id = _get_correlation_id_from_task(task)
        assert correlation_id is None

    def test_task_with_none_context(self):
        """Test extracting correlation_id when context is explicitly None."""
        task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Test task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=None,
        )

        correlation_id = _get_correlation_id_from_task(task)
        assert correlation_id is None


class TestHandleDuplicateTask:
    """Test the _handle_duplicate_task helper function."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        import os

        os.close(fd)
        initialize_database(db_path)
        yield db_path
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_handle_duplicate_with_existing_task(self, temp_db):
        """Test handling duplicate when existing task is found."""
        # Create original task
        original_task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Original task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id="reddit_post_abc123",
                agent_occurrence_id="default",
            ),
        )
        add_task(original_task, db_path=temp_db)

        # Create duplicate task
        duplicate_task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Duplicate task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id="reddit_post_abc123",
                agent_occurrence_id="default",
            ),
        )

        # Handle duplicate should return original task_id
        returned_id = _handle_duplicate_task(duplicate_task, temp_db)
        assert returned_id == original_task.task_id

    def test_handle_duplicate_with_empty_correlation_id(self, temp_db):
        """Test handling duplicate when correlation_id is empty string."""
        task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Task with empty correlation_id",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id="",
                agent_occurrence_id="default",
            ),
        )

        # Should return the attempted task_id when correlation_id is empty
        returned_id = _handle_duplicate_task(task, temp_db)
        assert returned_id == task.task_id

    def test_handle_duplicate_without_context(self, temp_db):
        """Test handling duplicate when task has no context."""
        task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Task without context",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Should return the attempted task_id
        returned_id = _handle_duplicate_task(task, temp_db)
        assert returned_id == task.task_id

    def test_handle_duplicate_no_existing_task_found(self, temp_db):
        """Test handling duplicate when no existing task is found (edge case)."""
        task = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Task with correlation_id but no existing task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id="nonexistent_correlation_id",
                agent_occurrence_id="default",
            ),
        )

        # Should return the attempted task_id since no existing task found
        returned_id = _handle_duplicate_task(task, temp_db)
        assert returned_id == task.task_id


class TestAddTaskIntegration:
    """Integration tests for add_task with helper functions."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary database for testing."""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        import os

        os.close(fd)
        initialize_database(db_path)
        yield db_path
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_add_task_duplicate_returns_original_id(self, temp_db):
        """Test that adding duplicate task returns original task_id."""
        correlation_id = f"reddit_post_{uuid4()}"

        # Add first task
        task1 = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="First task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id=correlation_id,
                agent_occurrence_id="default",
            ),
        )
        task1_id = add_task(task1, db_path=temp_db)
        assert task1_id == task1.task_id

        # Try to add duplicate
        task2 = Task(
            task_id=str(uuid4()),
            channel_id="test:channel",
            agent_occurrence_id="default",
            description="Duplicate task",
            status=TaskStatus.PENDING,
            priority=0,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            context=TaskContext(
                channel_id="test:channel",
                user_id="test_user",
                correlation_id=correlation_id,
                agent_occurrence_id="default",
            ),
        )
        task2_id = add_task(task2, db_path=temp_db)

        # Should return original task_id
        assert task2_id == task1.task_id
        assert task2_id != task2.task_id
