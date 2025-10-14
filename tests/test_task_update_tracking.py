"""
Unit tests for task update tracking functionality.

Tests the TASK_UPDATED_INFO_AVAILABLE feature that detects when new observations
arrive in a channel with an active task.
"""

import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tasks import (
    add_task,
    get_active_task_for_channel,
    get_task_by_id,
    set_task_updated_info_flag,
)
from ciris_engine.logic.persistence.models.thoughts import add_thought
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import FinalAction, Task, TaskContext, Thought, ThoughtContext


class TestTaskUpdateTracking:
    """Test task update tracking persistence functions."""

    @pytest.fixture
    def temp_db(self):
        """Create temporary database with schema."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Initialize database schema with migrations
        initialize_database(db_path)

        yield db_path

        # Cleanup
        import os

        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        mock_time = Mock()
        mock_time.now.return_value = datetime.now(timezone.utc)
        mock_time.now_iso.return_value = datetime.now(timezone.utc).isoformat()
        return mock_time

    @pytest.fixture
    def sample_task(self, mock_time_service):
        """Create a sample task."""
        return Task(
            task_id=str(uuid.uuid4()),
            channel_id="test-channel-123",
            description="Test task for update tracking",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            context=TaskContext(
                channel_id="test-channel-123",
                user_id="user-123",
                correlation_id=str(uuid.uuid4()),
                parent_task_id=None,
            ),
        )

    def test_get_active_task_for_channel_no_tasks(self, temp_db):
        """Test getting active task when none exist."""
        result = get_active_task_for_channel("channel-123", db_path=temp_db)
        assert result is None

    def test_get_active_task_for_channel_with_active_task(self, temp_db, sample_task):
        """Test getting active task when one exists."""
        add_task(sample_task, db_path=temp_db)

        result = get_active_task_for_channel("test-channel-123", db_path=temp_db)
        assert result is not None
        assert result.task_id == sample_task.task_id
        assert result.channel_id == "test-channel-123"
        assert result.status == TaskStatus.ACTIVE

    def test_get_active_task_for_channel_ignores_completed(self, temp_db, sample_task, mock_time_service):
        """Test that completed tasks are not returned."""
        # Add completed task
        sample_task.status = TaskStatus.COMPLETED
        add_task(sample_task, db_path=temp_db)

        result = get_active_task_for_channel("test-channel-123", db_path=temp_db)
        assert result is None

    def test_get_active_task_for_channel_returns_most_recent(self, temp_db, mock_time_service):
        """Test that most recent active task is returned."""
        # Add two active tasks in same channel
        task1 = Task(
            task_id=str(uuid.uuid4()),
            channel_id="test-channel-123",
            description="First task",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            context=TaskContext(
                channel_id="test-channel-123",
                user_id="user-123",
                correlation_id=str(uuid.uuid4()),
                parent_task_id=None,
            ),
        )
        add_task(task1, db_path=temp_db)

        # Second task created later
        import time

        time.sleep(0.01)  # Ensure different timestamps
        mock_time_service.now_iso.return_value = datetime.now(timezone.utc).isoformat()

        task2 = Task(
            task_id=str(uuid.uuid4()),
            channel_id="test-channel-123",
            description="Second task",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            context=TaskContext(
                channel_id="test-channel-123",
                user_id="user-123",
                correlation_id=str(uuid.uuid4()),
                parent_task_id=None,
            ),
        )
        add_task(task2, db_path=temp_db)

        result = get_active_task_for_channel("test-channel-123", db_path=temp_db)
        assert result is not None
        assert result.task_id == task2.task_id  # Most recent

    def test_set_task_updated_info_flag_no_thoughts(self, temp_db, sample_task, mock_time_service):
        """Test setting flag on task with no thoughts yet."""
        add_task(sample_task, db_path=temp_db)

        success = set_task_updated_info_flag(
            sample_task.task_id, "New message: @user says hello", "default", mock_time_service, db_path=temp_db
        )

        assert success is True

        # Verify flag was set
        updated_task = get_task_by_id(sample_task.task_id, "default", db_path=temp_db)
        assert updated_task is not None
        assert updated_task.updated_info_available is True
        assert updated_task.updated_info_content == "New message: @user says hello"

    def test_set_task_updated_info_flag_with_ponder_thought(self, temp_db, sample_task, mock_time_service):
        """Test setting flag on task that has completed PONDER thought."""
        add_task(sample_task, db_path=temp_db)

        # Add a completed thought with PONDER action
        thought = Thought(
            thought_id=str(uuid.uuid4()),
            source_task_id=sample_task.task_id,
            content="Pondering the question",
            status=ThoughtStatus.COMPLETED,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            thought_depth=0,
            final_action=FinalAction(
                action_type=HandlerActionType.PONDER.value,
                action_params={"questions": ["Why?"]},
                reasoning="Need more thought",
            ),
            context=ThoughtContext(
                task_id=sample_task.task_id,
                correlation_id=str(uuid.uuid4()),
                round_number=0,
                depth=0,
            ),
        )
        add_thought(thought, db_path=temp_db)

        # Should still succeed because PONDER is allowed
        success = set_task_updated_info_flag(
            sample_task.task_id, "New message arrived", "default", mock_time_service, db_path=temp_db
        )

        assert success is True

    def test_set_task_updated_info_flag_with_speak_thought(self, temp_db, sample_task, mock_time_service):
        """Test setting flag on task that has completed SPEAK thought (should fail)."""
        add_task(sample_task, db_path=temp_db)

        # Add a completed thought with SPEAK action
        thought = Thought(
            thought_id=str(uuid.uuid4()),
            source_task_id=sample_task.task_id,
            content="Planning to speak",
            status=ThoughtStatus.COMPLETED,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            thought_depth=0,
            final_action=FinalAction(
                action_type=HandlerActionType.SPEAK.value,
                action_params={"content": "Hello there"},
                reasoning="Ready to respond",
            ),
            context=ThoughtContext(
                task_id=sample_task.task_id,
                correlation_id=str(uuid.uuid4()),
                round_number=0,
                depth=0,
            ),
        )
        add_thought(thought, db_path=temp_db)

        # Should fail because task already committed to SPEAK action
        success = set_task_updated_info_flag(
            sample_task.task_id, "New message arrived", "default", mock_time_service, db_path=temp_db
        )

        assert success is False

        # Verify flag was NOT set
        updated_task = get_task_by_id(sample_task.task_id, "default", db_path=temp_db)
        assert updated_task is not None
        assert updated_task.updated_info_available is False

    def test_set_task_updated_info_flag_with_task_complete_thought(self, temp_db, sample_task, mock_time_service):
        """Test setting flag on task that has completed TASK_COMPLETE thought (should fail)."""
        add_task(sample_task, db_path=temp_db)

        # Add a completed thought with TASK_COMPLETE action
        thought = Thought(
            thought_id=str(uuid.uuid4()),
            source_task_id=sample_task.task_id,
            content="Task completed",
            status=ThoughtStatus.COMPLETED,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            thought_depth=0,
            final_action=FinalAction(
                action_type=HandlerActionType.TASK_COMPLETE.value, action_params={}, reasoning="Task done"
            ),
            context=ThoughtContext(
                task_id=sample_task.task_id,
                correlation_id=str(uuid.uuid4()),
                round_number=0,
                depth=0,
            ),
        )
        add_thought(thought, db_path=temp_db)

        # Should fail because task already committed to TASK_COMPLETE
        success = set_task_updated_info_flag(
            sample_task.task_id, "New message arrived", "default", mock_time_service, db_path=temp_db
        )

        assert success is False

    def test_set_task_updated_info_flag_nonexistent_task(self, temp_db, mock_time_service):
        """Test setting flag on nonexistent task."""
        success = set_task_updated_info_flag(
            "nonexistent-task-id", "New message", "default", mock_time_service, db_path=temp_db
        )

        assert success is False

    def test_task_schema_includes_update_fields(self, temp_db, mock_time_service):
        """Test that Task schema properly includes updated_info fields."""
        task = Task(
            task_id=str(uuid.uuid4()),
            channel_id="test-channel",
            description="Test task",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=mock_time_service.now_iso(),
            updated_at=mock_time_service.now_iso(),
            updated_info_available=True,
            updated_info_content="Test update content",
            context=TaskContext(
                channel_id="test-channel",
                user_id="user-123",
                correlation_id=str(uuid.uuid4()),
                parent_task_id=None,
            ),
        )

        # Should not raise validation error
        assert task.updated_info_available is True
        assert task.updated_info_content == "Test update content"

        # Save and retrieve
        add_task(task, db_path=temp_db)
        retrieved = get_task_by_id(task.task_id, "default", db_path=temp_db)

        assert retrieved is not None
        assert retrieved.updated_info_available is True
        assert retrieved.updated_info_content == "Test update content"
