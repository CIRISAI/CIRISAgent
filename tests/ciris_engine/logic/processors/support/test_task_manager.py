"""Comprehensive unit tests for Task Scheduler/Manager with focus on achieving 80% coverage."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.processors.support.task_manager import TaskManager
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext

# No need to add path since we're in the proper test structure


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    service = MagicMock(spec=TimeServiceProtocol)
    service.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
    service.now_iso.return_value = "2025-01-01T12:00:00"
    return service


@pytest.fixture
def task_manager(mock_time_service):
    """Create a task manager for testing."""
    return TaskManager(max_active_tasks=10, time_service=mock_time_service)


@pytest.fixture
def sample_task(mock_time_service):
    """Create a sample task for testing."""
    return Task(
        task_id="test-task-123",
        channel_id="test-channel",
        description="Test task description",
        status=TaskStatus.PENDING,
        priority=5,
        created_at=mock_time_service.now_iso(),
        updated_at=mock_time_service.now_iso(),
        parent_task_id=None,
        context=TaskContext(
            channel_id="test-channel", user_id="test-user", correlation_id="test-correlation", parent_task_id=None
        ),
        outcome=None,
        signed_by=None,
        signature=None,
        signed_at=None,
    )


class TestTaskManager:
    """Test suite for TaskManager."""

    def test_initialization(self, mock_time_service):
        """Test task manager initialization."""
        manager = TaskManager(max_active_tasks=20, time_service=mock_time_service)
        assert manager.max_active_tasks == 20
        assert manager._time_service == mock_time_service

    def test_time_service_property_error(self):
        """Test that accessing time_service without setting it raises error."""
        manager = TaskManager(max_active_tasks=10, time_service=None)

        with pytest.raises(RuntimeError) as exc_info:
            _ = manager.time_service

        assert "TimeService not injected" in str(exc_info.value)

    @patch("ciris_engine.logic.persistence.add_task")
    @patch("uuid.uuid4")
    def test_create_task_basic(self, mock_uuid, mock_add_task, task_manager):
        """Test basic task creation."""
        mock_uuid.return_value = "test-uuid-123"

        task = task_manager.create_task(description="Test task", channel_id="test-channel", priority=3)

        assert task.description == "Test task"
        assert task.channel_id == "test-channel"
        assert task.priority == 3
        assert task.status == TaskStatus.PENDING
        assert task.task_id == "test-uuid-123"
        assert task.parent_task_id is None
        assert task.outcome is None
        assert task.signed_by is None
        assert task.signature is None
        assert task.signed_at is None

        # Verify persistence was called
        mock_add_task.assert_called_once_with(task)

    @patch("ciris_engine.logic.persistence.add_task")
    @patch("uuid.uuid4")
    def test_create_task_with_context(self, mock_uuid, mock_add_task, task_manager):
        """Test task creation with custom context."""
        mock_uuid.side_effect = ["context-uuid", "task-uuid"]

        context = {"user_id": "custom-user", "correlation_id": "custom-correlation", "extra_field": "should be ignored"}

        task = task_manager.create_task(
            description="Test task with context",
            channel_id="test-channel",
            priority=5,
            context=context,
            parent_task_id="parent-123",
        )

        assert task.context.user_id == "custom-user"
        assert task.context.correlation_id == "custom-correlation"
        assert task.context.parent_task_id == "parent-123"
        assert task.parent_task_id == "parent-123"

    @patch("ciris_engine.logic.persistence.update_task_status")
    @patch("ciris_engine.logic.persistence.get_pending_tasks_for_activation")
    @patch("ciris_engine.logic.persistence.count_active_tasks")
    def test_activate_pending_tasks_success(
        self, mock_count_active, mock_get_pending, mock_update_status, task_manager, sample_task
    ):
        """Test successful activation of pending tasks."""
        mock_count_active.return_value = 5  # 5 active tasks
        pending_tasks = [
            sample_task,
            Task(
                task_id="task-2",
                channel_id="test-channel",
                description="Task 2",
                status=TaskStatus.PENDING,
                priority=8,
                created_at=sample_task.created_at,
                updated_at=sample_task.updated_at,
                parent_task_id=None,
                context=sample_task.context,
                outcome=None,
                signed_by=None,
                signature=None,
                signed_at=None,
            ),
        ]
        mock_get_pending.return_value = pending_tasks
        mock_update_status.return_value = True

        activated = task_manager.activate_pending_tasks()

        assert activated == 2
        mock_count_active.assert_called_once()
        mock_get_pending.assert_called_once_with("default", limit=5)  # max 10 - 5 active = 5
        assert mock_update_status.call_count == 2

    @patch("ciris_engine.logic.persistence.count_active_tasks")
    def test_activate_pending_tasks_at_limit(self, mock_count_active, task_manager):
        """Test activation when at max active tasks limit."""
        mock_count_active.return_value = 10  # At limit

        activated = task_manager.activate_pending_tasks()

        assert activated == 0
        mock_count_active.assert_called_once()

    @patch("ciris_engine.logic.persistence.update_task_status")
    @patch("ciris_engine.logic.persistence.get_pending_tasks_for_activation")
    @patch("ciris_engine.logic.persistence.count_active_tasks")
    def test_activate_pending_tasks_update_failure(
        self, mock_count_active, mock_get_pending, mock_update_status, task_manager, sample_task
    ):
        """Test activation when task status update fails."""
        mock_count_active.return_value = 8
        mock_get_pending.return_value = [sample_task]
        mock_update_status.return_value = False  # Update fails

        activated = task_manager.activate_pending_tasks()

        assert activated == 0

    @patch("ciris_engine.logic.persistence.get_tasks_needing_seed_thought")
    def test_get_tasks_needing_seed(self, mock_get_tasks, task_manager, sample_task):
        """Test getting tasks that need seed thoughts."""
        # Create tasks with various IDs
        wakeup_task = Task(
            task_id="WAKEUP_ROOT",
            channel_id="test",
            description="Wakeup",
            status=TaskStatus.ACTIVE,
            priority=1,
            created_at=sample_task.created_at,
            updated_at=sample_task.updated_at,
            parent_task_id=None,
            context=sample_task.context,
            outcome=None,
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        system_task = Task(
            task_id="SYSTEM_TASK",
            channel_id="test",
            description="System",
            status=TaskStatus.ACTIVE,
            priority=1,
            created_at=sample_task.created_at,
            updated_at=sample_task.updated_at,
            parent_task_id=None,
            context=sample_task.context,
            outcome=None,
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        wakeup_child = Task(
            task_id="child-task",
            channel_id="test",
            description="Child of wakeup",
            status=TaskStatus.ACTIVE,
            priority=1,
            created_at=sample_task.created_at,
            updated_at=sample_task.updated_at,
            parent_task_id="WAKEUP_ROOT",
            context=sample_task.context,
            outcome=None,
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        mock_get_tasks.return_value = [
            sample_task,  # Normal task - should be included
            wakeup_task,  # Should be excluded
            system_task,  # Should be excluded
            wakeup_child,  # Should be excluded (parent is WAKEUP_ROOT)
        ]

        tasks = task_manager.get_tasks_needing_seed(limit=10)

        assert len(tasks) == 1
        assert tasks[0] == sample_task
        mock_get_tasks.assert_called_once_with("default", 10)

    @patch("ciris_engine.logic.persistence.update_task_status")
    @patch("ciris_engine.logic.persistence.get_task_by_id")
    def test_complete_task_success(self, mock_get_task, mock_update_status, task_manager, sample_task):
        """Test successful task completion."""
        mock_get_task.return_value = sample_task
        mock_update_status.return_value = True

        result = task_manager.complete_task("test-task-123", {"result": "success"})

        assert result is True
        mock_get_task.assert_called_once_with("test-task-123", "default")
        mock_update_status.assert_called_once_with(
            "test-task-123", TaskStatus.COMPLETED, "default", task_manager.time_service
        )

    @patch("ciris_engine.logic.persistence.get_task_by_id")
    def test_complete_task_not_found(self, mock_get_task, task_manager):
        """Test completing a task that doesn't exist."""
        mock_get_task.return_value = None

        result = task_manager.complete_task("nonexistent-task")

        assert result is False

    @patch("ciris_engine.logic.persistence.update_task_status")
    @patch("ciris_engine.logic.persistence.get_task_by_id")
    def test_fail_task_success(self, mock_get_task, mock_update_status, task_manager, sample_task):
        """Test successful task failure."""
        mock_get_task.return_value = sample_task
        mock_update_status.return_value = True

        result = task_manager.fail_task("test-task-123", "Task failed due to error")

        assert result is True
        mock_update_status.assert_called_once_with(
            "test-task-123", TaskStatus.FAILED, "default", task_manager.time_service
        )

    @patch("ciris_engine.logic.persistence.get_task_by_id")
    def test_fail_task_not_found(self, mock_get_task, task_manager):
        """Test failing a task that doesn't exist."""
        mock_get_task.return_value = None

        result = task_manager.fail_task("nonexistent-task", "reason")

        assert result is False

    @patch("ciris_engine.logic.persistence.add_task")
    @patch("ciris_engine.logic.persistence.update_task_status")
    @patch("ciris_engine.logic.persistence.task_exists")
    @patch("ciris_engine.logic.config.env_utils.get_env_var")
    @patch("uuid.uuid4")
    def test_create_wakeup_sequence_tasks(
        self, mock_uuid, mock_get_env, mock_task_exists, mock_update_status, mock_add_task, task_manager
    ):
        """Test creation of wakeup sequence tasks."""
        # Need 7 UUIDs: 1 for correlation ID in root, plus 5 for step tasks + 1 for each step's correlation
        mock_uuid.side_effect = [
            "root-corr",
            "uuid1",
            "uuid1-corr",
            "uuid2",
            "uuid2-corr",
            "uuid3",
            "uuid3-corr",
            "uuid4",
            "uuid4-corr",
            "uuid5",
            "uuid5-corr",
        ]
        mock_get_env.return_value = None  # No env var set
        mock_task_exists.return_value = False

        tasks = task_manager.create_wakeup_sequence_tasks(channel_id="custom-channel")

        assert len(tasks) == 6  # Root + 5 steps

        # Check root task
        root = tasks[0]
        assert root.task_id == "WAKEUP_ROOT"
        assert root.channel_id == "custom-channel"
        assert root.description == "Wakeup ritual"
        assert root.status == TaskStatus.ACTIVE
        assert root.priority == 1
        assert root.parent_task_id is None

        # Check step tasks
        expected_prefixes = ["CORE IDENTITY", "INTEGRITY", "RESILIENCE", "INCOMPLETENESS", "SIGNALLING GRATITUDE"]

        for i, (task, prefix) in enumerate(zip(tasks[1:], expected_prefixes), 1):
            assert task.parent_task_id == "WAKEUP_ROOT"
            assert task.channel_id == "custom-channel"
            assert task.status == TaskStatus.ACTIVE
            assert task.priority == 0
            assert prefix in task.description

        # Verify persistence calls
        assert mock_add_task.call_count == 6

    @patch("ciris_engine.logic.persistence.add_task")
    @patch("ciris_engine.logic.persistence.update_task_status")
    @patch("ciris_engine.logic.persistence.task_exists")
    @patch("ciris_engine.logic.config.env_utils.get_env_var")
    def test_create_wakeup_sequence_tasks_existing_root(
        self, mock_get_env, mock_task_exists, mock_update_status, mock_add_task, task_manager
    ):
        """Test wakeup sequence when root task already exists."""
        mock_get_env.return_value = "discord-channel-123"
        mock_task_exists.return_value = True  # Root already exists
        mock_update_status.return_value = True

        tasks = task_manager.create_wakeup_sequence_tasks()

        # Should update existing root status instead of adding
        mock_update_status.assert_called_once_with(
            "WAKEUP_ROOT", TaskStatus.ACTIVE, "default", task_manager.time_service
        )
        # Should add 5 step tasks but not the root
        assert mock_add_task.call_count == 5

    @patch("ciris_engine.logic.persistence.count_active_tasks")
    def test_get_active_task_count(self, mock_count, task_manager):
        """Test getting active task count."""
        mock_count.return_value = 7

        count = task_manager.get_active_task_count()

        assert count == 7
        mock_count.assert_called_once()

    @patch("ciris_engine.logic.persistence.count_tasks")
    def test_get_pending_task_count(self, mock_count, task_manager):
        """Test getting pending task count."""
        mock_count.return_value = 15

        count = task_manager.get_pending_task_count()

        assert count == 15
        mock_count.assert_called_once_with(TaskStatus.PENDING, "default")

    @patch("ciris_engine.logic.persistence.delete_tasks_by_ids")
    @patch("ciris_engine.logic.persistence.get_tasks_older_than")
    def test_cleanup_old_completed_tasks(self, mock_get_old, mock_delete, task_manager, sample_task):
        """Test cleanup of old completed tasks."""
        # Create mix of completed and other tasks
        completed1 = Task(
            task_id="old-complete-1",
            channel_id="test",
            description="Old completed",
            status=TaskStatus.COMPLETED,
            priority=1,
            created_at=sample_task.created_at,
            updated_at=sample_task.updated_at,
            parent_task_id=None,
            context=sample_task.context,
            outcome=None,
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        completed2 = Task(
            task_id="old-complete-2",
            channel_id="test",
            description="Old completed 2",
            status=TaskStatus.COMPLETED,
            priority=1,
            created_at=sample_task.created_at,
            updated_at=sample_task.updated_at,
            parent_task_id=None,
            context=sample_task.context,
            outcome=None,
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        active_old = Task(
            task_id="old-active",
            channel_id="test",
            description="Old but active",
            status=TaskStatus.ACTIVE,
            priority=1,
            created_at=sample_task.created_at,
            updated_at=sample_task.updated_at,
            parent_task_id=None,
            context=sample_task.context,
            outcome=None,
            signed_by=None,
            signature=None,
            signed_at=None,
        )

        mock_get_old.return_value = [completed1, completed2, active_old]
        mock_delete.return_value = 2

        deleted = task_manager.cleanup_old_completed_tasks(days_old=7)

        assert deleted == 2
        # Check that the cutoff date was calculated correctly
        cutoff_call = mock_get_old.call_args[0][0]
        # Should be December 25, 2024 (7 days before Jan 1, 2025)
        assert cutoff_call.startswith("2024-12-25")

        # Verify only completed tasks were deleted
        mock_delete.assert_called_once_with(["old-complete-1", "old-complete-2"], "default")

    @patch("ciris_engine.logic.persistence.get_tasks_older_than")
    def test_cleanup_old_completed_tasks_none_found(self, mock_get_old, task_manager):
        """Test cleanup when no old completed tasks exist."""
        mock_get_old.return_value = []

        deleted = task_manager.cleanup_old_completed_tasks(days_old=30)

        assert deleted == 0

    def test_task_manager_initialization_defaults(self):
        """Test task manager initialization with default values."""
        manager = TaskManager()
        assert manager.max_active_tasks == 10
        assert manager._time_service is None

    @patch("ciris_engine.logic.persistence.add_task")
    @patch("uuid.uuid4")
    def test_create_task_minimal(self, mock_uuid, mock_add_task, task_manager):
        """Test task creation with minimal parameters."""
        mock_uuid.return_value = "minimal-uuid"

        task = task_manager.create_task(description="Minimal task", channel_id="minimal-channel")

        assert task.task_id == "minimal-uuid"
        assert task.priority == 0  # Default priority
        assert task.context.user_id is None
        assert task.parent_task_id is None

    @patch("ciris_engine.logic.persistence.update_task_status")
    @patch("ciris_engine.logic.persistence.get_pending_tasks_for_activation")
    @patch("ciris_engine.logic.persistence.count_active_tasks")
    def test_activate_pending_tasks_no_pending(
        self, mock_count_active, mock_get_pending, mock_update_status, task_manager
    ):
        """Test activation when no pending tasks exist."""
        mock_count_active.return_value = 3
        mock_get_pending.return_value = []

        activated = task_manager.activate_pending_tasks()

        assert activated == 0
        mock_update_status.assert_not_called()


class TestTaskContext:
    """Test TaskContext schema usage in TaskManager."""

    def test_task_context_creation(self):
        """Test that TaskContext is created correctly."""
        context = TaskContext(
            channel_id="test-channel",
            user_id="test-user",
            correlation_id="test-correlation",
            parent_task_id="parent-123",
        )

        assert context.channel_id == "test-channel"
        assert context.user_id == "test-user"
        assert context.correlation_id == "test-correlation"
        assert context.parent_task_id == "parent-123"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch("ciris_engine.logic.persistence.add_task")
    @patch("uuid.uuid4")
    def test_create_task_with_empty_context(self, mock_uuid, mock_add_task, task_manager):
        """Test task creation with empty context dict."""
        mock_uuid.return_value = "empty-context-uuid"

        task = task_manager.create_task(description="Task with empty context", channel_id="test-channel", context={})

        assert task.context.user_id is None
        assert task.context.correlation_id == "empty-context-uuid"

    def test_task_status_enum_values(self):
        """Verify TaskStatus enum values used in TaskManager."""
        assert TaskStatus.PENDING
        assert TaskStatus.ACTIVE
        assert TaskStatus.COMPLETED
        assert TaskStatus.FAILED

    @patch("ciris_engine.logic.persistence.get_tasks_older_than")
    def test_cleanup_with_datetime_edge_case(self, mock_get_old, task_manager):
        """Test cleanup with edge case datetime calculation."""
        # Test with 1 day old (edge case for date arithmetic)
        mock_get_old.return_value = []

        deleted = task_manager.cleanup_old_completed_tasks(days_old=1)

        assert deleted == 0
        # Should have called with December 31, 2024
        cutoff_call = mock_get_old.call_args[0][0]
        assert cutoff_call.startswith("2024-12-31")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
