"""Comprehensive tests for WakeupProcessor."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought


class TestWakeupProcessorInitialization:
    """Test WakeupProcessor initialization and setup."""

    def test_processor_initializes_with_correct_dependencies(self, wakeup_processor):
        """Test that processor initializes with all required dependencies."""
        assert wakeup_processor is not None
        assert wakeup_processor.time_service is not None
        assert wakeup_processor.auth_service is not None
        assert wakeup_processor.wakeup_tasks == []
        assert wakeup_processor.wakeup_complete is False

    def test_get_supported_states_returns_wakeup_only(self, wakeup_processor):
        """Test that processor only supports WAKEUP state."""
        supported = wakeup_processor.get_supported_states()
        assert supported == [AgentState.WAKEUP]
        assert len(supported) == 1

    @pytest.mark.asyncio
    async def test_can_process_returns_true_for_wakeup_state(self, wakeup_processor):
        """Test that processor can process WAKEUP state when not complete."""
        can_process = await wakeup_processor.can_process(AgentState.WAKEUP)
        assert can_process is True

    @pytest.mark.asyncio
    async def test_can_process_returns_false_when_complete(self, wakeup_processor):
        """Test that processor cannot process when wakeup is complete."""
        wakeup_processor.wakeup_complete = True
        can_process = await wakeup_processor.can_process(AgentState.WAKEUP)
        assert can_process is False

    @pytest.mark.asyncio
    async def test_can_process_returns_false_for_non_wakeup_state(self, wakeup_processor):
        """Test that processor cannot process non-WAKEUP states."""
        can_process = await wakeup_processor.can_process(AgentState.WORK)
        assert can_process is False


class TestWakeupProcessorTaskManagement:
    """Test task creation and management in WakeupProcessor."""

    @patch("ciris_engine.logic.persistence.models.tasks.add_system_task")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_create_wakeup_tasks_creates_sequence(
        self, mock_persistence, mock_identity, mock_add_task, wakeup_processor
    ):
        """Test that _create_wakeup_tasks creates a wakeup sequence."""
        # Mock identity with attributes
        identity_mock = Mock()
        identity_mock.agent_name = "TestAgent"
        identity_mock.agent_role = "TestRole"
        identity_mock.description = "Testing agent"
        mock_identity.return_value = identity_mock

        # Mock add_system_task to return tasks
        def create_task(description=None, channel_id=None, task_id=None, task_obj=None, **kwargs):
            from ciris_engine.schemas.runtime.enums import TaskStatus
            from ciris_engine.schemas.runtime.models import Task

            # Handle both task object and description string
            if task_obj:
                return task_obj

            return Task(
                task_id=task_id or f"TASK_{len(wakeup_processor.wakeup_tasks)}",
                channel_id=channel_id or "test_channel",
                description=str(description) if description else "Test task",
                status=TaskStatus.ACTIVE,
                priority=1,
                created_at="2024-01-01T12:00:00Z",
                updated_at="2024-01-01T12:00:00Z",
            )

        mock_add_task.side_effect = create_task

        await wakeup_processor._create_wakeup_tasks()

        assert len(wakeup_processor.wakeup_tasks) > 0
        # First task should be the root task
        root_task = wakeup_processor.wakeup_tasks[0]
        assert "WAKEUP" in root_task.task_id or "wakeup" in root_task.description.lower()

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_check_all_steps_complete_returns_true_when_all_completed(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test that _check_all_steps_complete returns True when all steps are done."""
        # Set up wakeup tasks
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock all step tasks as completed
        def get_task_mock(task_id):
            task = next((t for t in wakeup_task_sequence if t.task_id == task_id), None)
            if task:
                completed_task = Mock()
                completed_task.status = TaskStatus.COMPLETED
                return completed_task
            return None

        mock_persistence.get_task_by_id.side_effect = get_task_mock

        result = wakeup_processor._check_all_steps_complete()
        assert result is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_check_all_steps_complete_returns_false_when_incomplete(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test that _check_all_steps_complete returns False when steps are incomplete."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock first step as active, rest as completed
        def get_task_mock(task_id):
            task = next((t for t in wakeup_task_sequence if t.task_id == task_id), None)
            if task and task == wakeup_task_sequence[1]:  # First step task
                active_task = Mock()
                active_task.status = TaskStatus.ACTIVE
                return active_task
            elif task:
                completed_task = Mock()
                completed_task.status = TaskStatus.COMPLETED
                return completed_task
            return None

        mock_persistence.get_task_by_id.side_effect = get_task_mock

        result = wakeup_processor._check_all_steps_complete()
        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_count_completed_steps_counts_correctly(self, mock_persistence, wakeup_processor, wakeup_task_sequence):
        """Test that _count_completed_steps counts completed tasks correctly."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock 2 steps as completed, 1 as active
        def get_task_mock(task_id):
            task = next((t for t in wakeup_task_sequence if t.task_id == task_id), None)
            if task and task in wakeup_task_sequence[1:3]:  # First 2 step tasks
                completed_task = Mock()
                completed_task.status = TaskStatus.COMPLETED
                return completed_task
            elif task and task == wakeup_task_sequence[3]:  # Third step task
                active_task = Mock()
                active_task.status = TaskStatus.ACTIVE
                return active_task
            return None

        mock_persistence.get_task_by_id.side_effect = get_task_mock

        count = wakeup_processor._count_completed_steps()
        assert count == 2


class TestWakeupProcessorThoughtCreation:
    """Test thought creation logic in WakeupProcessor."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.generate_thought_id")
    def test_create_step_thought_creates_valid_thought(
        self, mock_gen_id, mock_persistence, wakeup_processor, sample_task
    ):
        """Test that _create_step_thought creates a valid thought."""
        mock_gen_id.return_value = "th_wakeup_123"
        mock_persistence.create_thought = Mock(side_effect=lambda t: t)

        thought, context = wakeup_processor._create_step_thought(sample_task, round_number=1)

        assert thought is not None
        assert thought.thought_id == "th_wakeup_123"
        assert thought.source_task_id == sample_task.task_id
        assert thought.status == ThoughtStatus.PENDING
        assert thought.round_number == 1
        # Context is None in non-blocking mode
        assert context is None


class TestWakeupProcessorNonBlocking:
    """Test non-blocking wakeup processing."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_non_blocking_creates_tasks(self, mock_persistence, mock_identity, wakeup_processor):
        """Test that non-blocking mode creates wakeup tasks."""
        identity_mock = Mock()
        identity_mock.agent_name = "TestAgent"
        identity_mock.agent_role = "TestRole"
        identity_mock.description = "Testing agent"
        mock_identity.return_value = identity_mock

        mock_persistence.create_task = Mock(side_effect=lambda t: t)
        mock_persistence.get_task_by_id = Mock(return_value=None)

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result is not None
        assert "status" in result
        assert len(wakeup_processor.wakeup_tasks) > 0

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.generate_thought_id")
    @pytest.mark.asyncio
    async def test_process_wakeup_non_blocking_creates_thoughts_for_active_tasks(
        self, mock_gen_id, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test that non-blocking mode creates thoughts for active tasks."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        mock_gen_id.return_value = "th_test_123"

        # Mock tasks as active with no thoughts
        def get_task_mock(task_id):
            task = next((t for t in wakeup_task_sequence if t.task_id == task_id), None)
            if task:
                active_task = Mock()
                active_task.status = TaskStatus.ACTIVE
                active_task.task_id = task.task_id
                return active_task
            return None

        mock_persistence.get_task_by_id.side_effect = get_task_mock
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.add_thought = Mock(side_effect=lambda t: t)

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result["status"] in ["in_progress", "completed"]
        # Should have created thoughts for step tasks (not root)
        assert mock_persistence.add_thought.call_count >= 1

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_non_blocking_skips_tasks_with_pending_thoughts(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence, sample_thought
    ):
        """Test that non-blocking mode skips tasks that already have pending thoughts."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock tasks as active with pending thoughts
        def get_task_mock(task_id):
            active_task = Mock()
            active_task.status = TaskStatus.ACTIVE
            active_task.task_id = task_id
            return active_task

        mock_persistence.get_task_by_id.side_effect = get_task_mock
        mock_persistence.get_thoughts_by_task_id.return_value = [sample_thought]
        mock_persistence.create_thought = Mock()

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        # Should not create new thoughts since pending thoughts exist
        assert result["processed_thoughts"] is True  # Found pending thoughts to process

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_non_blocking_detects_completion(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test that non-blocking mode detects when all steps are complete."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock all step tasks as completed
        def get_task_mock(task_id):
            completed_task = Mock()
            completed_task.status = TaskStatus.COMPLETED
            completed_task.task_id = task_id
            return completed_task

        mock_persistence.get_task_by_id.side_effect = get_task_mock
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.update_task = Mock()

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result["status"] == "completed"
        assert result["wakeup_complete"] is True
        assert wakeup_processor.wakeup_complete is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_non_blocking_detects_failure(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test that non-blocking mode detects when any step fails."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock first step as failed, rest as active
        def get_task_mock(task_id):
            task = next((t for t in wakeup_task_sequence if t.task_id == task_id), None)
            if task and task == wakeup_task_sequence[1]:  # First step
                failed_task = Mock()
                failed_task.status = TaskStatus.FAILED
                failed_task.task_id = task.task_id
                return failed_task
            elif task:
                active_task = Mock()
                active_task.status = TaskStatus.ACTIVE
                active_task.task_id = task.task_id
                return active_task
            return None

        mock_persistence.get_task_by_id.side_effect = get_task_mock
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.update_task = Mock()

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result["status"] == "failed"
        assert result["wakeup_complete"] is False
        assert "error" in result


class TestWakeupProcessorProcess:
    """Test the main process() method."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_returns_wakeup_result(self, mock_persistence, mock_identity, wakeup_processor):
        """Test that process() returns a proper WakeupResult."""
        identity_mock = Mock()
        identity_mock.agent_name = "TestAgent"
        identity_mock.agent_role = "TestRole"
        identity_mock.description = "Testing agent"
        mock_identity.return_value = identity_mock

        mock_persistence.create_task = Mock(side_effect=lambda t: t)
        mock_persistence.get_task_by_id = Mock(return_value=None)

        result = await wakeup_processor.process(round_number=1)

        assert result is not None
        assert hasattr(result, "thoughts_processed")
        assert hasattr(result, "wakeup_complete")
        assert hasattr(result, "errors")
        assert hasattr(result, "duration_seconds")
        assert result.duration_seconds >= 0

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_tracks_errors_on_failure(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence, failed_task
    ):
        """Test that process() tracks errors when tasks fail."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock first step as failed
        def get_task_mock(task_id):
            if task_id == wakeup_task_sequence[1].task_id:
                return failed_task
            return None

        mock_persistence.get_task_by_id.side_effect = get_task_mock
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.update_task = Mock()

        result = await wakeup_processor.process(round_number=1)

        assert result.errors > 0


class TestWakeupProcessorEdgeCases:
    """Test edge cases and error handling."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_handles_exception(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test that _process_wakeup handles exceptions gracefully."""
        # Set up wakeup tasks first so it doesn't try to create them
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock persistence to raise exception when trying to get task
        mock_persistence.get_task_by_id.side_effect = Exception("Test error")

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result["status"] == "error"
        assert "error" in result
        assert result["wakeup_complete"] is False

    def test_count_completed_steps_returns_zero_for_no_tasks(self, wakeup_processor):
        """Test that _count_completed_steps returns 0 when no tasks exist."""
        count = wakeup_processor._count_completed_steps()
        assert count == 0

    def test_check_all_steps_complete_returns_false_for_no_tasks(self, wakeup_processor):
        """Test that _check_all_steps_complete returns False when no tasks exist."""
        result = wakeup_processor._check_all_steps_complete()
        assert result is False

    def test_check_all_steps_complete_returns_false_for_too_few_tasks(self, wakeup_processor):
        """Test that _check_all_steps_complete returns False for insufficient tasks."""
        wakeup_processor.wakeup_tasks = [Mock()]  # Only root task
        result = wakeup_processor._check_all_steps_complete()
        assert result is False
