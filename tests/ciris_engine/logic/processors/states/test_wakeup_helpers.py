"""Tests for WakeupProcessor helper methods."""

from unittest.mock import Mock, patch

import pytest

from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus


class TestWakeupHelpers:
    """Test helper methods in WakeupProcessor."""

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_validate_task_state_returns_true_for_active(self, mock_persistence, wakeup_processor, sample_task):
        """Test that _validate_task_state returns True for active task."""
        mock_persistence.get_task_by_id.return_value = sample_task

        is_valid, status = wakeup_processor._validate_task_state(sample_task)

        assert is_valid is True
        assert status == "active"
        mock_persistence.get_task_by_id.assert_called_once_with(sample_task.task_id)

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_validate_task_state_returns_false_for_missing(self, mock_persistence, wakeup_processor, sample_task):
        """Test that _validate_task_state returns False for missing task."""
        mock_persistence.get_task_by_id.return_value = None

        is_valid, status = wakeup_processor._validate_task_state(sample_task)

        assert is_valid is False
        assert status == "missing"

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_validate_task_state_returns_false_for_completed(self, mock_persistence, wakeup_processor, sample_task):
        """Test that _validate_task_state returns False for completed task."""
        completed_task = Mock()
        completed_task.status = TaskStatus.COMPLETED
        mock_persistence.get_task_by_id.return_value = completed_task

        is_valid, status = wakeup_processor._validate_task_state(sample_task)

        assert is_valid is False
        assert status == "completed"

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_get_task_thoughts_summary_counts_correctly(self, mock_persistence, wakeup_processor):
        """Test that _get_task_thoughts_summary counts thoughts by status."""
        # Create mock thoughts with different statuses
        thoughts = [
            Mock(status=ThoughtStatus.PENDING),
            Mock(status=ThoughtStatus.PENDING),
            Mock(status=ThoughtStatus.PROCESSING),
            Mock(status=ThoughtStatus.COMPLETED),
            Mock(status=ThoughtStatus.COMPLETED),
            Mock(status=ThoughtStatus.COMPLETED),
        ]
        mock_persistence.get_thoughts_by_task_id.return_value = thoughts

        summary = wakeup_processor._get_task_thoughts_summary("test_task_123")

        assert summary["total"] == 6
        assert summary["pending"] == 2
        assert summary["processing"] == 1
        assert summary["completed"] == 3
        assert summary["thoughts"] == thoughts

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_build_step_status_includes_all_fields(self, mock_persistence, wakeup_processor, sample_task):
        """Test that _build_step_status includes all required fields."""
        mock_persistence.get_task_by_id.return_value = sample_task

        status = wakeup_processor._build_step_status(sample_task, 1)

        assert status["step"] == 1
        assert status["task_id"] == "TEST_TASK_123"
        assert status["status"] == "active"
        assert status["type"] == "TEST"

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_build_step_status_handles_missing_task(self, mock_persistence, wakeup_processor, sample_task):
        """Test that _build_step_status handles missing task."""
        mock_persistence.get_task_by_id.return_value = None

        status = wakeup_processor._build_step_status(sample_task, 2)

        assert status["status"] == "missing"
        assert status["step"] == 2

    def test_needs_new_thought_returns_true_for_no_existing(self, wakeup_processor, sample_task):
        """Test that _needs_new_thought returns True when no existing thoughts."""
        result = wakeup_processor._needs_new_thought([], sample_task)
        assert result is True

    def test_needs_new_thought_returns_false_for_inactive_task(self, wakeup_processor):
        """Test that _needs_new_thought returns False for inactive task."""
        inactive_task = Mock()
        inactive_task.status = TaskStatus.COMPLETED

        result = wakeup_processor._needs_new_thought([], inactive_task)
        assert result is False

    def test_needs_new_thought_returns_false_for_pending_thoughts(self, wakeup_processor, sample_task):
        """Test that _needs_new_thought returns False when pending thoughts exist."""
        thoughts = [Mock(status=ThoughtStatus.PENDING)]

        result = wakeup_processor._needs_new_thought(thoughts, sample_task)
        assert result is False

    def test_needs_new_thought_returns_false_for_processing_thoughts(self, wakeup_processor, sample_task):
        """Test that _needs_new_thought returns False when processing thoughts exist."""
        thoughts = [Mock(status=ThoughtStatus.PROCESSING)]

        result = wakeup_processor._needs_new_thought(thoughts, sample_task)
        assert result is False

    def test_needs_new_thought_returns_true_for_completed_thoughts(self, wakeup_processor, sample_task):
        """Test that _needs_new_thought returns True when only completed thoughts exist."""
        thoughts = [Mock(status=ThoughtStatus.COMPLETED)]

        result = wakeup_processor._needs_new_thought(thoughts, sample_task)
        assert result is True

    @patch("ciris_engine.logic.processors.states.wakeup_processor.persistence")
    def test_collect_steps_status_returns_all_steps(self, mock_persistence, wakeup_processor, sample_task):
        """Test that _collect_steps_status returns status for all steps."""
        # Set up wakeup_tasks with root + 3 steps
        step1 = Mock(task_id="STEP1_123")
        step2 = Mock(task_id="STEP2_456")
        step3 = Mock(task_id="STEP3_789")
        wakeup_processor.wakeup_tasks = [sample_task, step1, step2, step3]

        mock_persistence.get_task_by_id.return_value = sample_task

        statuses = wakeup_processor._collect_steps_status()

        assert len(statuses) == 3  # Should skip root task
        assert statuses[0]["step"] == 1
        assert statuses[1]["step"] == 2
        assert statuses[2]["step"] == 3
