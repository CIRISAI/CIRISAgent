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

    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.tasks.add_system_task")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_create_wakeup_tasks_creates_sequence(
        self, mock_persistence, mock_identity, mock_add_task, mock_try_claim, mock_is_completed, wakeup_processor
    ):
        """Test that _create_wakeup_tasks creates a wakeup sequence."""
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task

        # Mock shared task not completed
        mock_is_completed.return_value = False

        # Create a mock root task
        root_task = Task(
            task_id="WAKEUP_SHARED_20251027",
            channel_id="test_channel_123",
            description="Wakeup ritual (shared across all occurrences)",
            status=TaskStatus.PENDING,
            priority=10,
            created_at="2024-01-01T12:00:00Z",
            updated_at="2024-01-01T12:00:00Z",
            agent_occurrence_id="__shared__",
        )

        # Mock claiming the shared task
        mock_try_claim.return_value = (root_task, True)

        # Mock identity with attributes
        identity_mock = Mock()
        identity_mock.agent_name = "TestAgent"
        identity_mock.agent_role = "TestRole"
        identity_mock.description = "Testing agent"
        mock_identity.return_value = identity_mock

        # Mock add_system_task to return tasks
        def create_task(task_obj=None, **kwargs):
            return task_obj if task_obj else None

        mock_add_task.side_effect = create_task

        await wakeup_processor._create_wakeup_tasks()

        assert len(wakeup_processor.wakeup_tasks) > 0
        # First task should be the root task
        root_task_result = wakeup_processor.wakeup_tasks[0]
        assert "WAKEUP" in root_task_result.task_id

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_check_all_steps_complete_returns_true_when_all_completed(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test that _check_all_steps_complete returns True when all steps are done."""
        # Set up wakeup tasks
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        # Mock all step tasks as completed
        def get_task_mock(task_id, occurrence_id="default"):
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
        def get_task_mock(task_id, occurrence_id="default"):
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
        def get_task_mock(task_id, occurrence_id="default"):
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

    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.tasks.add_system_task")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_non_blocking_creates_tasks(
        self, mock_persistence, mock_identity, mock_add_task, mock_try_claim, mock_is_completed, wakeup_processor
    ):
        """Test that non-blocking mode creates wakeup tasks."""
        from ciris_engine.schemas.runtime.enums import TaskStatus
        from ciris_engine.schemas.runtime.models import Task

        # Mock shared task not completed
        mock_is_completed.return_value = False

        # Create a mock root task
        root_task = Task(
            task_id="WAKEUP_SHARED_20251027",
            channel_id="test_channel_123",
            description="Wakeup ritual (shared across all occurrences)",
            status=TaskStatus.PENDING,
            priority=10,
            created_at="2024-01-01T12:00:00Z",
            updated_at="2024-01-01T12:00:00Z",
            agent_occurrence_id="__shared__",
        )

        # Mock claiming the shared task
        mock_try_claim.return_value = (root_task, True)

        identity_mock = Mock()
        identity_mock.agent_name = "TestAgent"
        identity_mock.agent_role = "TestRole"
        identity_mock.description = "Testing agent"
        mock_identity.return_value = identity_mock

        mock_persistence.create_task = Mock(side_effect=lambda t: t)
        mock_persistence.get_task_by_id = Mock(return_value=None)
        mock_add_task.side_effect = lambda task_obj=None, **kwargs: task_obj

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
        def get_task_mock(task_id, occurrence_id="default"):
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
        def get_task_mock(task_id, occurrence_id="default"):
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
        def get_task_mock(task_id, occurrence_id="default"):
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
        def get_task_mock(task_id, occurrence_id="default"):
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
        def get_task_mock(task_id, occurrence_id="default"):
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

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_non_claiming_occurrence_monitors_without_marking_complete(
        self, mock_persistence, mock_identity, wakeup_processor
    ):
        """Test that non-claiming occurrence monitors shared task without marking it complete."""
        # Simulate non-claiming occurrence with only root task
        root_task = Mock()
        root_task.task_id = "WAKEUP_SHARED_20251027"
        root_task.agent_occurrence_id = "__shared__"
        root_task.status = TaskStatus.ACTIVE
        wakeup_processor.wakeup_tasks = [root_task]

        # Mock the shared task as still in progress
        mock_persistence.get_task_by_id.return_value = root_task

        # Process wakeup - should return in_progress without marking complete
        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result["status"] == "in_progress"
        assert result["wakeup_complete"] is False
        assert result["steps_status"] == []

        # Verify it checked the task but didn't try to mark it complete
        mock_persistence.get_task_by_id.assert_called_once_with(root_task.task_id, root_task.agent_occurrence_id)
        # update_task_status should not be called by non-claiming occurrence
        mock_persistence.update_task_status.assert_not_called()

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_non_claiming_occurrence_detects_completion(self, mock_persistence, mock_identity, wakeup_processor):
        """Test that non-claiming occurrence detects when shared task completes."""
        # Simulate non-claiming occurrence with only root task
        root_task = Mock()
        root_task.task_id = "WAKEUP_SHARED_20251027"
        root_task.agent_occurrence_id = "__shared__"
        root_task.status = TaskStatus.COMPLETED
        wakeup_processor.wakeup_tasks = [root_task]

        # Mock the shared task as completed
        completed_task = Mock()
        completed_task.status = TaskStatus.COMPLETED
        mock_persistence.get_task_by_id.return_value = completed_task

        # Process wakeup - should detect completion
        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result["status"] == "completed"
        assert result["wakeup_complete"] is True
        assert wakeup_processor.wakeup_complete is True

        # Should NOT call update_task_status - claiming occurrence already marked it
        mock_persistence.update_task_status.assert_not_called()

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_non_claiming_occurrence_detects_failure(self, mock_persistence, mock_identity, wakeup_processor):
        """Test that non-claiming occurrence detects when shared task fails."""
        # Simulate non-claiming occurrence with only root task
        root_task = Mock()
        root_task.task_id = "WAKEUP_SHARED_20251027"
        root_task.agent_occurrence_id = "__shared__"
        root_task.status = TaskStatus.ACTIVE
        wakeup_processor.wakeup_tasks = [root_task]

        # Mock the shared task as failed
        failed_task = Mock()
        failed_task.status = TaskStatus.FAILED
        mock_persistence.get_task_by_id.return_value = failed_task

        # Process wakeup - should detect failure
        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        assert result["status"] == "failed"
        assert result["wakeup_complete"] is False
        assert "error" in result

        # Should NOT call update_task_status - claiming occurrence already marked it
        mock_persistence.update_task_status.assert_not_called()


class TestWakeupProcessorRoleExtraction:
    """Test role extraction from agent description."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    def test_get_wakeup_sequence_extracts_moderation_role(self, mock_identity, wakeup_processor):
        """Test role extraction for moderation agent."""
        identity_mock = Mock()
        identity_mock.agent_name = "TestAgent"
        identity_mock.agent_role = "AI agent"
        identity_mock.description = "A moderation agent for community management"
        mock_identity.return_value = identity_mock

        sequence = wakeup_processor._get_wakeup_sequence()

        assert len(sequence) == 5
        # Check that the role was extracted in the sequence
        assert "Discord moderation agent" in sequence[0][1]

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    def test_get_wakeup_sequence_extracts_teacher_role(self, mock_identity, wakeup_processor):
        """Test role extraction for teaching agent."""
        identity_mock = Mock()
        identity_mock.agent_name = "TeacherBot"
        identity_mock.agent_role = "AI agent"
        identity_mock.description = "A helpful teacher for students"
        mock_identity.return_value = identity_mock

        sequence = wakeup_processor._get_wakeup_sequence()

        assert len(sequence) == 5
        assert "teaching assistant" in sequence[0][1]

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    def test_get_wakeup_sequence_extracts_student_role(self, mock_identity, wakeup_processor):
        """Test role extraction for learning agent."""
        identity_mock = Mock()
        identity_mock.agent_name = "LearnerBot"
        identity_mock.agent_role = "AI agent"
        identity_mock.description = "A student learning new concepts"
        mock_identity.return_value = identity_mock

        sequence = wakeup_processor._get_wakeup_sequence()

        assert len(sequence) == 5
        assert "learning agent" in sequence[0][1]

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    def test_get_wakeup_sequence_keeps_specific_role(self, mock_identity, wakeup_processor):
        """Test that specific roles are not overridden."""
        identity_mock = Mock()
        identity_mock.agent_name = "SpecialBot"
        identity_mock.agent_role = "Special Agent"
        identity_mock.description = "A teacher that does moderation"
        mock_identity.return_value = identity_mock

        sequence = wakeup_processor._get_wakeup_sequence()

        assert len(sequence) == 5
        # Should keep the original role since it's not "AI agent"
        assert "Special Agent" in sequence[0][1]


class TestWakeupProcessorHelperMethods:
    """Test helper methods for validation and status checking."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_validate_task_state_returns_true_for_active(self, mock_persistence, wakeup_processor, sample_task):
        """Test _validate_task_state returns True for active tasks."""
        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task

        is_valid, status = wakeup_processor._validate_task_state(sample_task)

        assert is_valid is True
        assert status == "active"

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_validate_task_state_returns_false_for_missing(self, mock_persistence, wakeup_processor, sample_task):
        """Test _validate_task_state returns False for missing tasks."""
        mock_persistence.get_task_by_id.return_value = None

        is_valid, status = wakeup_processor._validate_task_state(sample_task)

        assert is_valid is False
        assert status == "missing"

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_validate_task_state_returns_false_for_completed(self, mock_persistence, wakeup_processor, sample_task):
        """Test _validate_task_state returns False for completed tasks."""
        completed_task = Mock()
        completed_task.status = TaskStatus.COMPLETED
        mock_persistence.get_task_by_id.return_value = completed_task

        is_valid, status = wakeup_processor._validate_task_state(sample_task)

        assert is_valid is False
        assert status == "completed"

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_get_task_thoughts_summary(self, mock_persistence, wakeup_processor):
        """Test _get_task_thoughts_summary aggregates thought counts."""
        thoughts = [
            Mock(status=ThoughtStatus.PENDING),
            Mock(status=ThoughtStatus.PROCESSING),
            Mock(status=ThoughtStatus.COMPLETED),
            Mock(status=ThoughtStatus.COMPLETED),
        ]
        mock_persistence.get_thoughts_by_task_id.return_value = thoughts

        summary = wakeup_processor._get_task_thoughts_summary("task_123", "occurrence_1")

        assert summary["total"] == 4
        assert summary["pending"] == 1
        assert summary["processing"] == 1
        assert summary["completed"] == 2
        assert len(summary["thoughts"]) == 4

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_build_step_status(self, mock_persistence, wakeup_processor, sample_task):
        """Test _build_step_status creates correct status dict."""
        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task

        sample_task.task_id = "VERIFY_IDENTITY_abc123"
        status = wakeup_processor._build_step_status(sample_task, 1)

        assert status["step"] == 1
        assert status["task_id"] == "VERIFY_IDENTITY_abc123"
        assert status["status"] == "active"
        assert status["type"] == "VERIFY"

    def test_needs_new_thought_returns_false_for_no_task(self, wakeup_processor):
        """Test _needs_new_thought returns False when task doesn't exist."""
        result = wakeup_processor._needs_new_thought([], None)
        assert result is False

    def test_needs_new_thought_returns_false_for_inactive_task(self, wakeup_processor, sample_task):
        """Test _needs_new_thought returns False for inactive tasks."""
        sample_task.status = TaskStatus.COMPLETED
        result = wakeup_processor._needs_new_thought([], sample_task)
        assert result is False

    def test_needs_new_thought_returns_true_for_active_with_no_thoughts(self, wakeup_processor, sample_task):
        """Test _needs_new_thought returns True for active task with no thoughts."""
        sample_task.status = TaskStatus.ACTIVE
        result = wakeup_processor._needs_new_thought([], sample_task)
        assert result is True

    def test_needs_new_thought_returns_false_for_pending_thoughts(self, wakeup_processor, sample_task):
        """Test _needs_new_thought returns False when pending thoughts exist."""
        sample_task.status = TaskStatus.ACTIVE
        pending_thought = Mock(status=ThoughtStatus.PENDING)
        result = wakeup_processor._needs_new_thought([pending_thought], sample_task)
        assert result is False

    def test_needs_new_thought_returns_false_for_processing_thoughts(self, wakeup_processor, sample_task):
        """Test _needs_new_thought returns False when processing thoughts exist."""
        sample_task.status = TaskStatus.ACTIVE
        processing_thought = Mock(status=ThoughtStatus.PROCESSING)
        result = wakeup_processor._needs_new_thought([processing_thought], sample_task)
        assert result is False

    def test_needs_new_thought_returns_true_for_only_completed_thoughts(self, wakeup_processor, sample_task):
        """Test _needs_new_thought returns True when only completed thoughts exist."""
        sample_task.status = TaskStatus.ACTIVE
        completed_thought = Mock(status=ThoughtStatus.COMPLETED)
        result = wakeup_processor._needs_new_thought([completed_thought], sample_task)
        assert result is True

    def test_collect_steps_status(self, wakeup_processor, wakeup_task_sequence):
        """Test _collect_steps_status collects all step statuses."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        with patch.object(wakeup_processor, "_build_step_status") as mock_build:
            mock_build.return_value = {"step": 1, "status": "active"}
            statuses = wakeup_processor._collect_steps_status()

            # Should call for each step task (excluding root)
            assert mock_build.call_count == len(wakeup_task_sequence) - 1
            assert len(statuses) == len(wakeup_task_sequence) - 1


class TestWakeupProcessorMultiOccurrenceCoordination:
    """Test multi-occurrence coordination paths."""

    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_create_wakeup_tasks_skips_when_already_completed(
        self, mock_persistence, mock_is_completed, wakeup_processor
    ):
        """Test that _create_wakeup_tasks skips creation when wakeup already completed."""
        mock_is_completed.return_value = True

        await wakeup_processor._create_wakeup_tasks()

        assert wakeup_processor.wakeup_complete is True
        assert len(wakeup_processor.wakeup_tasks) == 0

    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_create_wakeup_tasks_handles_non_claiming_occurrence(
        self, mock_persistence, mock_try_claim, mock_is_completed, wakeup_processor
    ):
        """Test that non-claiming occurrence only stores root task."""
        mock_is_completed.return_value = False

        # Another occurrence claimed the task
        root_task = Mock()
        root_task.task_id = "WAKEUP_SHARED_123"
        root_task.agent_occurrence_id = "__shared__"
        mock_try_claim.return_value = (root_task, False)  # was_created=False

        await wakeup_processor._create_wakeup_tasks()

        # Should only have root task, no step tasks
        assert len(wakeup_processor.wakeup_tasks) == 1
        assert wakeup_processor.wakeup_tasks[0] == root_task

    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_create_wakeup_tasks_raises_on_no_communication_bus(
        self, mock_persistence, mock_try_claim, mock_is_completed, wakeup_processor
    ):
        """Test that _create_wakeup_tasks raises error when communication bus unavailable."""
        mock_is_completed.return_value = False
        wakeup_processor.services.communication_bus = None

        with pytest.raises(RuntimeError, match="Communication bus not available"):
            await wakeup_processor._create_wakeup_tasks()

    @patch("ciris_engine.logic.registries.base.ServiceRegistry")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_create_wakeup_tasks_raises_on_no_default_channel(
        self, mock_persistence, mock_try_claim, mock_is_completed, mock_registry_class, wakeup_processor
    ):
        """Test that _create_wakeup_tasks raises error when no default channel available."""
        mock_is_completed.return_value = False
        wakeup_processor.services.communication_bus.get_default_channel = AsyncMock(return_value=None)

        # Mock ServiceRegistry for diagnostic info
        mock_registry = Mock()
        mock_registry.get_provider_info.return_value = {"providers": []}
        mock_registry_class.get_instance.return_value = mock_registry

        with pytest.raises(RuntimeError, match="No communication adapter has a home channel"):
            await wakeup_processor._create_wakeup_tasks()


class TestWakeupProcessorBlockingMode:
    """Test blocking mode processing paths."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_blocking_mode_success(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test blocking mode completes successfully."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        with patch.object(wakeup_processor, "_process_wakeup_steps", return_value=True) as mock_process:
            result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=False)

            assert result["status"] == "success"
            assert result["wakeup_complete"] is True
            assert wakeup_processor.wakeup_complete is True
            mock_process.assert_called_once_with(1, non_blocking=False)

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_blocking_mode_failure(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test blocking mode handles failure."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        with patch.object(wakeup_processor, "_process_wakeup_steps", return_value=False) as mock_process:
            result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=False)

            assert result["status"] == "failed"
            assert result["wakeup_complete"] is False
            assert "error" in result
            mock_process.assert_called_once_with(1, non_blocking=False)

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_process_wakeup_steps_non_blocking_no_tasks(self, mock_persistence, wakeup_processor):
        """Test _process_wakeup_steps_non_blocking handles no tasks."""
        wakeup_processor.wakeup_tasks = []
        # Should return without error
        wakeup_processor._process_wakeup_steps_non_blocking(1)

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_process_wakeup_steps_non_blocking_only_root(self, mock_persistence, wakeup_processor):
        """Test _process_wakeup_steps_non_blocking handles only root task."""
        root_task = Mock()
        wakeup_processor.wakeup_tasks = [root_task]
        # Should return without error
        wakeup_processor._process_wakeup_steps_non_blocking(1)

    @patch("ciris_engine.logic.processors.states.wakeup_processor.generate_thought_id")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_process_wakeup_steps_non_blocking_creates_thoughts(
        self, mock_persistence, mock_gen_id, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps_non_blocking creates thoughts for active tasks."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        mock_gen_id.return_value = "th_test_123"

        # Mock active tasks with no thoughts
        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.add_thought = Mock()

        wakeup_processor._process_wakeup_steps_non_blocking(1)

        # Should have created thoughts for step tasks
        assert mock_persistence.add_thought.call_count >= 1

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_process_wakeup_steps_non_blocking_skips_with_pending_thoughts(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps_non_blocking skips tasks with pending thoughts."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task

        pending_thought = Mock(status=ThoughtStatus.PENDING)
        mock_persistence.get_thoughts_by_task_id.return_value = [pending_thought]
        mock_persistence.add_thought = Mock()

        wakeup_processor._process_wakeup_steps_non_blocking(1)

        # Should not create new thoughts
        mock_persistence.add_thought.assert_not_called()

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_process_wakeup_steps_non_blocking_finds_existing_thoughts(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps_non_blocking finds existing pending thoughts."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        pending_thought = Mock(status=ThoughtStatus.PENDING, thought_id="th_existing")
        mock_persistence.get_thoughts_by_task_id.return_value = [pending_thought]

        wakeup_processor._process_wakeup_steps_non_blocking(1)

        # Should find the existing thought
        mock_persistence.get_thoughts_by_task_id.assert_called()


class TestWakeupProcessorBlockingStepProcessing:
    """Test blocking step processing paths."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.generate_thought_id")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_processes_all_steps(
        self, mock_persistence, mock_gen_id, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps processes all step tasks."""
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        mock_gen_id.return_value = "th_test_123"

        # Mock active tasks
        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.add_thought = Mock()

        # Mock thought processing - use HandlerActionType enum
        mock_result = Mock()
        mock_result.selected_action = HandlerActionType.SPEAK
        with patch.object(wakeup_processor, "_process_step_thought", return_value=mock_result):
            with patch.object(wakeup_processor, "_dispatch_step_action", return_value=True):
                with patch.object(wakeup_processor, "_wait_for_task_completion", return_value=True):
                    result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        assert result is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_handles_no_result(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps handles missing result."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.update_task_status = Mock()

        with patch.object(wakeup_processor, "_create_step_thought") as mock_create:
            mock_create.return_value = (Mock(), None)
            with patch.object(wakeup_processor, "_process_step_thought", return_value=None):
                result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_handles_missing_selected_action(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps handles result without selected_action."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.update_task_status = Mock()

        # Result without selected_action attribute
        mock_result = Mock(spec=[])
        with patch.object(wakeup_processor, "_create_step_thought") as mock_create:
            mock_create.return_value = (Mock(), None)
            with patch.object(wakeup_processor, "_process_step_thought", return_value=mock_result):
                result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_handles_ponder_action(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps handles PONDER action."""
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []

        mock_result = Mock()
        mock_result.selected_action = HandlerActionType.PONDER
        with patch.object(wakeup_processor, "_create_step_thought") as mock_create:
            mock_create.return_value = (Mock(), None)
            with patch.object(wakeup_processor, "_process_step_thought", return_value=mock_result):
                with patch.object(wakeup_processor, "_wait_for_task_completion", return_value=True):
                    result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        assert result is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_handles_invalid_action(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps handles invalid action type."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.update_task_status = Mock()

        mock_result = Mock()
        mock_result.selected_action = "INVALID_ACTION"
        with patch.object(wakeup_processor, "_create_step_thought") as mock_create:
            mock_create.return_value = (Mock(), None)
            with patch.object(wakeup_processor, "_process_step_thought", return_value=mock_result):
                result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_handles_dispatch_failure(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps handles dispatch failure."""
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []

        mock_result = Mock()
        mock_result.selected_action = HandlerActionType.SPEAK
        with patch.object(wakeup_processor, "_create_step_thought") as mock_create:
            mock_create.return_value = (Mock(), None)
            with patch.object(wakeup_processor, "_process_step_thought", return_value=mock_result):
                with patch.object(wakeup_processor, "_dispatch_step_action", return_value=False):
                    result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_handles_completion_failure(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps handles task completion failure."""
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []

        mock_result = Mock()
        mock_result.selected_action = HandlerActionType.SPEAK
        with patch.object(wakeup_processor, "_create_step_thought") as mock_create:
            mock_create.return_value = (Mock(), None)
            with patch.object(wakeup_processor, "_process_step_thought", return_value=mock_result):
                with patch.object(wakeup_processor, "_dispatch_step_action", return_value=True):
                    with patch.object(wakeup_processor, "_wait_for_task_completion", return_value=False):
                        result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_skips_inactive_tasks(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps skips inactive tasks."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        inactive_task = Mock()
        inactive_task.status = TaskStatus.COMPLETED
        mock_persistence.get_task_by_id.return_value = inactive_task

        result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        # Should return True since no active tasks to fail
        assert result is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_skips_tasks_with_active_thoughts(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps skips tasks with active thoughts."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task

        processing_thought = Mock(status=ThoughtStatus.PROCESSING)
        mock_persistence.get_thoughts_by_task_id.return_value = [processing_thought]

        result = await wakeup_processor._process_wakeup_steps(1, non_blocking=False)

        # Should return True since no failed tasks
        assert result is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_process_wakeup_steps_non_blocking_returns_immediately(
        self, mock_persistence, wakeup_processor, wakeup_task_sequence
    ):
        """Test _process_wakeup_steps returns immediately in non-blocking mode."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence

        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.get_thoughts_by_task_id.return_value = []

        with patch.object(wakeup_processor, "_create_step_thought") as mock_create:
            mock_create.return_value = (Mock(), None)
            result = await wakeup_processor._process_wakeup_steps(1, non_blocking=True)

        # Should return True without processing
        assert result is True


class TestWakeupProcessorDispatchAndWait:
    """Test dispatch and wait helper methods."""

    @pytest.mark.asyncio
    async def test_process_step_thought_creates_queue_item(self, wakeup_processor, sample_thought):
        """Test _process_step_thought creates and processes queue item."""
        mock_result = Mock()
        with patch.object(wakeup_processor, "process_thought_item", return_value=mock_result) as mock_process:
            result = await wakeup_processor._process_step_thought(sample_thought, None)

        assert result == mock_result
        mock_process.assert_called_once()

    @patch("ciris_engine.logic.utils.context_utils.build_dispatch_context")
    @pytest.mark.asyncio
    async def test_dispatch_step_action_builds_context(
        self, mock_build_context, wakeup_processor, sample_thought, sample_task
    ):
        """Test _dispatch_step_action builds proper dispatch context."""
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        mock_context = Mock()
        mock_context.model_dump.return_value = {"test": "context"}
        mock_build_context.return_value = mock_context

        # Set task_id on sample_task if needed
        if not hasattr(sample_task, "task_id") or "_" not in sample_task.task_id:
            sample_task.task_id = "TEST_STEP_123"

        mock_result = Mock()
        mock_result.selected_action = HandlerActionType.SPEAK
        with patch.object(wakeup_processor, "dispatch_action", return_value=True) as mock_dispatch:
            result = await wakeup_processor._dispatch_step_action(mock_result, sample_thought, sample_task)

        assert result is True
        mock_dispatch.assert_called_once()
        mock_build_context.assert_called_once()

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_wait_for_task_completion_succeeds(self, mock_persistence, wakeup_processor, sample_task):
        """Test _wait_for_task_completion succeeds when task completes."""
        completed_task = Mock()
        completed_task.status = TaskStatus.COMPLETED
        mock_persistence.get_task_by_id.return_value = completed_task

        result = await wakeup_processor._wait_for_task_completion(sample_task, "TEST", max_wait=1)

        assert result is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_wait_for_task_completion_handles_missing_task(
        self, mock_persistence, wakeup_processor, sample_task
    ):
        """Test _wait_for_task_completion handles disappeared task."""
        mock_persistence.get_task_by_id.return_value = None

        result = await wakeup_processor._wait_for_task_completion(sample_task, "TEST", max_wait=1)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_wait_for_task_completion_handles_failed_task(self, mock_persistence, wakeup_processor, sample_task):
        """Test _wait_for_task_completion handles failed task."""
        failed_task = Mock()
        failed_task.status = TaskStatus.FAILED
        mock_persistence.get_task_by_id.return_value = failed_task

        result = await wakeup_processor._wait_for_task_completion(sample_task, "TEST", max_wait=1)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_wait_for_task_completion_handles_deferred_task(
        self, mock_persistence, wakeup_processor, sample_task
    ):
        """Test _wait_for_task_completion handles deferred task."""
        deferred_task = Mock()
        deferred_task.status = TaskStatus.DEFERRED
        mock_persistence.get_task_by_id.return_value = deferred_task

        result = await wakeup_processor._wait_for_task_completion(sample_task, "TEST", max_wait=1)

        assert result is False

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_wait_for_task_completion_times_out(self, mock_persistence, wakeup_processor, sample_task):
        """Test _wait_for_task_completion handles timeout."""
        active_task = Mock()
        active_task.status = TaskStatus.ACTIVE
        mock_persistence.get_task_by_id.return_value = active_task
        mock_persistence.update_task_status = Mock()

        result = await wakeup_processor._wait_for_task_completion(
            sample_task, "TEST", max_wait=0.2, poll_interval=0.1
        )

        assert result is False
        # Should have marked task as failed
        mock_persistence.update_task_status.assert_called_once()


class TestWakeupProcessorTaskMarking:
    """Test task marking helper methods."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_mark_task_failed(self, mock_persistence, wakeup_processor):
        """Test _mark_task_failed marks task as failed."""
        mock_persistence.update_task_status = Mock()

        wakeup_processor._mark_task_failed("task_123", "Test failure", "occurrence_1")

        mock_persistence.update_task_status.assert_called_once_with(
            "task_123", TaskStatus.FAILED, "occurrence_1", wakeup_processor.time_service
        )

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_mark_root_task_complete(self, mock_persistence, wakeup_processor, wakeup_task_sequence):
        """Test _mark_root_task_complete marks root task as complete."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        mock_persistence.update_task_status = Mock()

        wakeup_processor._mark_root_task_complete()

        root_task = wakeup_task_sequence[0]
        mock_persistence.update_task_status.assert_called_once_with(
            root_task.task_id, TaskStatus.COMPLETED, root_task.agent_occurrence_id, wakeup_processor.time_service
        )

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_mark_root_task_failed(self, mock_persistence, wakeup_processor, wakeup_task_sequence):
        """Test _mark_root_task_failed marks root task as failed."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        mock_persistence.update_task_status = Mock()

        wakeup_processor._mark_root_task_failed()

        root_task = wakeup_task_sequence[0]
        mock_persistence.update_task_status.assert_called_once_with(
            root_task.task_id, TaskStatus.FAILED, root_task.agent_occurrence_id, wakeup_processor.time_service
        )


class TestWakeupProcessorStatusAndControl:
    """Test status reporting and control methods."""

    def test_is_wakeup_complete_returns_false(self, wakeup_processor):
        """Test is_wakeup_complete returns False when not complete."""
        wakeup_processor.wakeup_complete = False
        assert wakeup_processor.is_wakeup_complete() is False

    def test_is_wakeup_complete_returns_true(self, wakeup_processor):
        """Test is_wakeup_complete returns True when complete."""
        wakeup_processor.wakeup_complete = True
        assert wakeup_processor.is_wakeup_complete() is True

    @pytest.mark.asyncio
    async def test_start_processing_runs_until_complete(self, wakeup_processor):
        """Test start_processing runs until wakeup complete."""
        call_count = 0

        async def mock_process(round_num):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                wakeup_processor.wakeup_complete = True
            return Mock(wakeup_complete=wakeup_processor.wakeup_complete)

        with patch.object(wakeup_processor, "process", side_effect=mock_process):
            await wakeup_processor.start_processing(num_rounds=None)

        assert call_count == 3
        assert wakeup_processor.wakeup_complete is True

    @pytest.mark.asyncio
    async def test_start_processing_respects_num_rounds(self, wakeup_processor):
        """Test start_processing respects num_rounds limit."""
        call_count = 0

        async def mock_process(round_num):
            nonlocal call_count
            call_count += 1
            return Mock(wakeup_complete=False)

        with patch.object(wakeup_processor, "process", side_effect=mock_process):
            await wakeup_processor.start_processing(num_rounds=3)

        assert call_count == 3

    def test_stop_processing_sets_complete_flag(self, wakeup_processor):
        """Test stop_processing sets wakeup_complete flag."""
        wakeup_processor.wakeup_complete = False
        wakeup_processor.stop_processing()
        assert wakeup_processor.wakeup_complete is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_get_status_returns_complete_status(
        self, mock_persistence, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test get_status returns complete status dict."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        wakeup_processor.wakeup_complete = False

        identity_mock = Mock()
        identity_mock.agent_name = "TestAgent"
        identity_mock.agent_role = "TestRole"
        identity_mock.description = "Testing agent"
        mock_identity.return_value = identity_mock

        # Mock 2 completed, 1 active
        def get_task_mock(task_id, occurrence_id="default"):
            if task_id in [wakeup_task_sequence[1].task_id, wakeup_task_sequence[2].task_id]:
                completed = Mock()
                completed.status = TaskStatus.COMPLETED
                return completed
            active = Mock()
            active.status = TaskStatus.ACTIVE
            return active

        mock_persistence.get_task_by_id.side_effect = get_task_mock

        status = wakeup_processor.get_status()

        assert status["processor_type"] == "wakeup"
        assert status["wakeup_complete"] is False
        assert status["progress"]["total_steps"] == 5
        assert status["progress"]["completed_steps"] == 2
        assert status["progress"]["progress_percent"] == 40.0
        assert status["total_tasks"] == 4


class TestWakeupProcessorProcessingThoughts:
    """Test processing thoughts paths with detailed status checking."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.generate_thought_id")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_non_blocking_handles_processing_thoughts(
        self, mock_persistence, mock_gen_id, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test that non-blocking mode detects and waits for PROCESSING thoughts."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        mock_gen_id.return_value = "th_test_123"

        # Mock first task with processing thought
        def get_task_mock(task_id, occurrence_id="default"):
            active_task = Mock()
            active_task.status = TaskStatus.ACTIVE
            active_task.task_id = task_id
            return active_task

        mock_persistence.get_task_by_id.side_effect = get_task_mock

        # First step has processing thought, others have no thoughts
        def get_thoughts_mock(task_id, occurrence_id="default"):
            if task_id == wakeup_task_sequence[1].task_id:
                processing_thought = Mock(status=ThoughtStatus.PROCESSING)
                return [processing_thought]
            return []

        mock_persistence.get_thoughts_by_task_id.side_effect = get_thoughts_mock
        mock_persistence.add_thought = Mock()

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        # Should be in progress (waiting for processing thought)
        assert result["status"] == "in_progress"
        # Should create thoughts for other active tasks
        assert mock_persistence.add_thought.call_count >= 1

    @patch("ciris_engine.logic.processors.states.wakeup_processor.get_identity_for_context")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.generate_thought_id")
    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    @pytest.mark.asyncio
    async def test_non_blocking_skips_step_when_not_needing_thought(
        self, mock_persistence, mock_gen_id, mock_identity, wakeup_processor, wakeup_task_sequence
    ):
        """Test that non-blocking mode correctly skips steps that don't need new thoughts."""
        wakeup_processor.wakeup_tasks = wakeup_task_sequence
        mock_gen_id.return_value = "th_test_123"

        # Mock task as inactive
        def get_task_mock(task_id, occurrence_id="default"):
            inactive_task = Mock()
            inactive_task.status = TaskStatus.COMPLETED
            inactive_task.task_id = task_id
            return inactive_task

        mock_persistence.get_task_by_id.side_effect = get_task_mock
        mock_persistence.get_thoughts_by_task_id.return_value = []
        mock_persistence.add_thought = Mock()

        result = await wakeup_processor._process_wakeup(round_number=1, non_blocking=True)

        # Should detect all completed
        assert result["status"] == "completed"
        # Should not create any thoughts for completed tasks
        mock_persistence.add_thought.assert_not_called()
