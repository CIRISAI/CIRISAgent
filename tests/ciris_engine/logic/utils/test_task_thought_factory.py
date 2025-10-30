"""
Unit tests for centralized task/thought creation factory.

Tests verify:
1. Proper occurrence_id propagation in all creation scenarios
2. Context inheritance and validation
3. Single and multi-occurrence support
4. "default" treated as regular occurrence_id
"""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.utils.task_thought_factory import (
    create_follow_up_thought,
    create_seed_thought_for_task,
    create_task,
    create_thought,
)
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, TaskContext, Thought, ThoughtContext


class TestCreateTask:
    """Test create_task() function."""

    def test_create_task_minimal(self):
        """Test creating task with minimal required parameters."""
        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="002",
            correlation_id="corr_123",
        )

        assert task.task_id is not None
        assert task.description == "Test task"
        assert task.channel_id == "test_channel"
        assert task.agent_occurrence_id == "002"
        assert task.status == TaskStatus.PENDING
        assert task.priority == 5
        assert task.context is not None
        assert task.context.agent_occurrence_id == "002"
        assert task.context.channel_id == "test_channel"
        assert task.context.correlation_id == "corr_123"

    def test_create_task_with_default_occurrence(self):
        """Test that 'default' is treated as regular occurrence_id."""
        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="default",
            correlation_id="corr_123",
        )

        assert task.agent_occurrence_id == "default"
        assert task.context.agent_occurrence_id == "default"

    def test_create_task_missing_occurrence_id(self):
        """Test that missing occurrence_id raises error."""
        with pytest.raises(ValueError, match="agent_occurrence_id is required"):
            create_task(
                description="Test task",
                channel_id="test_channel",
                agent_occurrence_id="",
                correlation_id="corr_123",
            )

    def test_create_task_with_time_service(self):
        """Test task creation with time service."""
        mock_time = Mock()
        mock_time.now_iso.return_value = "2025-10-30T12:00:00+00:00"

        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="003",
            correlation_id="corr_123",
            time_service=mock_time,
        )

        assert task.created_at == "2025-10-30T12:00:00+00:00"
        assert task.updated_at == "2025-10-30T12:00:00+00:00"

    def test_create_task_with_custom_context(self):
        """Test task creation with pre-built context."""
        context = TaskContext(
            channel_id="test_channel",
            user_id="user_123",
            agent_occurrence_id="002",
            correlation_id="corr_456",  # Context's correlation_id is used
        )

        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="002",
            correlation_id="corr_123",  # Will be overridden by context
            context=context,
        )

        assert task.context.user_id == "user_123"
        assert task.context.correlation_id == "corr_456"  # From context, not parameter
        assert task.context.agent_occurrence_id == "002"

    def test_create_task_context_occurrence_mismatch(self):
        """Test that mismatched occurrence_id in context gets overwritten."""
        context = TaskContext(
            channel_id="test_channel",
            correlation_id="corr_123",
            agent_occurrence_id="001",  # Wrong occurrence
        )

        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="002",  # Correct occurrence
            correlation_id="corr_123",
            context=context,
        )

        # Should be overwritten to match task
        assert task.context.agent_occurrence_id == "002"

    def test_create_task_with_user_id(self):
        """Test task creation with user_id."""
        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            user_id="user_123",
        )

        assert task.context.user_id == "user_123"
        assert task.context.correlation_id == "corr_123"

    def test_create_task_custom_priority_status(self):
        """Test task creation with custom priority and status."""
        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            priority=8,
            status=TaskStatus.ACTIVE,
        )

        assert task.priority == 8
        assert task.status == TaskStatus.ACTIVE


class TestCreateThought:
    """Test create_thought() function."""

    def test_create_thought_minimal(self):
        """Test creating thought with minimal required parameters."""
        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Test thought content",
        )

        assert thought.thought_id is not None
        assert thought.source_task_id == "task_123"
        assert thought.agent_occurrence_id == "002"
        assert thought.content == "Test thought content"
        assert thought.status == ThoughtStatus.PENDING
        assert thought.thought_type == ThoughtType.STANDARD
        assert thought.round_number == 0
        assert thought.thought_depth == 0
        assert thought.context is not None
        assert thought.context.agent_occurrence_id == "002"

    def test_create_thought_with_default_occurrence(self):
        """Test that 'default' is treated as regular occurrence_id."""
        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="default",
            correlation_id="corr_123",
            content="Test thought",
        )

        assert thought.agent_occurrence_id == "default"
        assert thought.context.agent_occurrence_id == "default"

    def test_create_thought_missing_occurrence_id(self):
        """Test that missing occurrence_id raises error."""
        with pytest.raises(ValueError, match="agent_occurrence_id is required"):
            create_thought(
                source_task_id="task_123",
                agent_occurrence_id="",
                correlation_id="corr_123",
                content="Test thought",
            )

    def test_create_thought_with_time_service(self):
        """Test thought creation with time service."""
        mock_time = Mock()
        mock_time.now_iso.return_value = "2025-10-30T12:00:00+00:00"

        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="003",
            correlation_id="corr_123",
            content="Test thought",
            time_service=mock_time,
        )

        assert thought.created_at == "2025-10-30T12:00:00+00:00"
        assert thought.updated_at == "2025-10-30T12:00:00+00:00"

    def test_create_thought_with_custom_context(self):
        """Test thought creation with pre-built context."""
        context = ThoughtContext(
            task_id="task_123",
            channel_id="test_channel",
            round_number=2,
            depth=1,
            parent_thought_id="parent_456",
            agent_occurrence_id="002",
            correlation_id="corr_123",
        )

        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Test thought",
            context=context,
        )

        assert thought.context.round_number == 2
        assert thought.context.depth == 1
        assert thought.context.parent_thought_id == "parent_456"
        assert thought.context.agent_occurrence_id == "002"

    def test_create_thought_context_occurrence_mismatch(self):
        """Test that mismatched occurrence_id in context gets overwritten."""
        context = ThoughtContext(
            task_id="task_123",
            channel_id="test_channel",
            round_number=0,
            depth=0,
            correlation_id="corr_123",
            agent_occurrence_id="001",  # Wrong occurrence
        )

        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",  # Correct occurrence
            correlation_id="corr_123",
            content="Test thought",
            context=context,
        )

        # Should be overwritten to match thought
        assert thought.context.agent_occurrence_id == "002"

    def test_create_thought_with_parent(self):
        """Test creating thought with parent reference."""
        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Follow-up thought",
            parent_thought_id="parent_456",
            round_number=2,
            thought_depth=1,
        )

        assert thought.parent_thought_id == "parent_456"
        assert thought.round_number == 2
        assert thought.thought_depth == 1
        assert thought.context.parent_thought_id == "parent_456"

    def test_create_thought_guidance_type(self):
        """Test creating guidance thought."""
        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Guidance from WA",
            thought_type=ThoughtType.GUIDANCE,
        )

        assert thought.thought_type == ThoughtType.GUIDANCE


class TestCreateSeedThought:
    """Test create_seed_thought_for_task() function."""

    def test_create_seed_thought_from_task(self):
        """Test creating seed thought inherits from task."""
        task = create_task(
            description="Parent task description",
            channel_id="test_channel",
            agent_occurrence_id="002",
            correlation_id="corr_456",
            user_id="user_123",
        )

        seed = create_seed_thought_for_task(task=task)

        # Should inherit occurrence_id from task
        assert seed.agent_occurrence_id == "002"
        assert seed.context.agent_occurrence_id == "002"

        # Should inherit task properties
        assert seed.source_task_id == task.task_id
        assert seed.content == task.description
        assert seed.channel_id == "test_channel"
        assert seed.round_number == 0
        assert seed.thought_depth == 0
        assert seed.parent_thought_id is None

        # Context should inherit from task
        assert seed.context.task_id == task.task_id
        assert seed.context.channel_id == "test_channel"

    def test_create_seed_thought_with_time_service(self):
        """Test seed thought creation with time service."""
        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="003",
            correlation_id="corr_123",
        )

        mock_time = Mock()
        mock_time.now_iso.return_value = "2025-10-30T12:00:00+00:00"

        seed = create_seed_thought_for_task(task=task, time_service=mock_time)

        assert seed.created_at == "2025-10-30T12:00:00+00:00"

    def test_create_seed_thought_custom_round(self):
        """Test seed thought with custom starting round."""
        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="002",
            correlation_id="corr_123",
        )

        seed = create_seed_thought_for_task(task=task, round_number=5)

        assert seed.round_number == 5
        assert seed.context.round_number == 5


class TestCreateFollowUpThought:
    """Test create_follow_up_thought() function."""

    def test_create_follow_up_inherits_occurrence(self):
        """Test follow-up thought inherits occurrence_id from parent."""
        parent = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Parent thought",
            channel_id="test_channel",
            round_number=0,
        )

        follow_up = create_follow_up_thought(
            parent_thought=parent,
            content="Follow-up thought",
        )

        # Should inherit occurrence_id
        assert follow_up.agent_occurrence_id == "002"
        assert follow_up.context.agent_occurrence_id == "002"

        # Should link to parent
        assert follow_up.parent_thought_id == parent.thought_id
        assert follow_up.source_task_id == parent.source_task_id
        assert follow_up.channel_id == parent.channel_id

        # Should increment round by default
        assert follow_up.round_number == parent.round_number + 1
        assert follow_up.thought_depth == parent.thought_depth

    def test_create_follow_up_no_round_increment(self):
        """Test follow-up without round increment."""
        parent = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Parent thought",
            round_number=5,
        )

        follow_up = create_follow_up_thought(
            parent_thought=parent,
            content="Follow-up thought",
            increment_round=False,
        )

        assert follow_up.round_number == 5  # Not incremented

    def test_create_follow_up_with_depth_increment(self):
        """Test follow-up with depth increment."""
        parent = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Parent thought",
            thought_depth=2,
        )

        follow_up = create_follow_up_thought(
            parent_thought=parent,
            content="Follow-up thought",
            increment_depth=True,
        )

        assert follow_up.thought_depth == 3  # Incremented

    def test_create_follow_up_custom_type(self):
        """Test follow-up with custom thought type."""
        parent = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            correlation_id="corr_123",
            content="Parent thought",
        )

        follow_up = create_follow_up_thought(
            parent_thought=parent,
            content="Follow-up thought",
            thought_type=ThoughtType.GUIDANCE,
        )

        assert follow_up.thought_type == ThoughtType.GUIDANCE


class TestSharedTaskPattern:
    """Test __shared__ pattern for multi-occurrence coordination."""

    def test_create_task_with_shared_occurrence(self):
        """Test creating task with __shared__ occurrence for multi-occurrence coordination."""
        task = create_task(
            description="Wakeup ritual (shared across all occurrences)",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="wakeup_123",
            priority=10,
        )

        assert task.agent_occurrence_id == "__shared__"
        assert task.context.agent_occurrence_id == "__shared__"
        assert task.priority == 10
        assert task.channel_id == "system"

    def test_shared_task_seed_thought_inheritance(self):
        """Test that seed thoughts inherit __shared__ from task."""
        task = create_task(
            description="Wakeup ritual",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="wakeup_123",
        )

        seed = create_seed_thought_for_task(task=task)

        # Should inherit __shared__ from task
        assert seed.agent_occurrence_id == "__shared__"
        assert seed.context.agent_occurrence_id == "__shared__"
        assert seed.source_task_id == task.task_id
        assert seed.content == task.description

    def test_shared_task_follow_up_thought(self):
        """Test that follow-up thoughts preserve __shared__ occurrence."""
        # Create shared task
        task = create_task(
            description="System coordination task",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="coord_123",
        )

        # Create seed thought
        seed = create_seed_thought_for_task(task=task)

        # Create follow-up thought
        follow_up = create_follow_up_thought(
            parent_thought=seed,
            content="Continuing coordination...",
        )

        # All should maintain __shared__ occurrence
        assert task.agent_occurrence_id == "__shared__"
        assert seed.agent_occurrence_id == "__shared__"
        assert follow_up.agent_occurrence_id == "__shared__"

    def test_shared_and_regular_tasks_coexist(self):
        """Test that __shared__ tasks can coexist with regular occurrence tasks."""
        # Create shared task
        shared_task = create_task(
            description="Shared coordination task",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="shared_123",
        )

        # Create regular occurrence task
        regular_task = create_task(
            description="Regular task for 002",
            channel_id="channel_1",
            agent_occurrence_id="002",
            correlation_id="reg_123",
        )

        # Should maintain separate occurrence IDs
        assert shared_task.agent_occurrence_id == "__shared__"
        assert regular_task.agent_occurrence_id == "002"

        # Contexts should match
        assert shared_task.context.agent_occurrence_id == "__shared__"
        assert regular_task.context.agent_occurrence_id == "002"

    def test_shutdown_shared_task_pattern(self):
        """Test creating shutdown shared task (another common __shared__ pattern)."""
        task = create_task(
            description="Shutdown ritual (shared across all occurrences)",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="shutdown_456",
            priority=10,
            task_id="SHUTDOWN_SHARED_20251030",
        )

        assert task.task_id == "SHUTDOWN_SHARED_20251030"
        assert task.agent_occurrence_id == "__shared__"
        assert task.priority == 10
        assert "Shutdown ritual" in task.description


class TestMultiOccurrenceScenarios:
    """Test multi-occurrence deployment scenarios."""

    def test_tasks_for_different_occurrences(self):
        """Test creating tasks for different occurrences."""
        task_001 = create_task(
            description="Task for 001",
            channel_id="channel_1",
            agent_occurrence_id="001",
            correlation_id="corr_123",
        )

        task_002 = create_task(
            description="Task for 002",
            channel_id="channel_2",
            agent_occurrence_id="002",
            correlation_id="corr_123",
        )

        task_default = create_task(
            description="Task for default",
            channel_id="channel_3",
            agent_occurrence_id="default",
            correlation_id="corr_123",
        )

        # Each should have correct occurrence_id
        assert task_001.agent_occurrence_id == "001"
        assert task_002.agent_occurrence_id == "002"
        assert task_default.agent_occurrence_id == "default"

        # Contexts should also be correct
        assert task_001.context.agent_occurrence_id == "001"
        assert task_002.context.agent_occurrence_id == "002"
        assert task_default.context.agent_occurrence_id == "default"

    def test_thought_chain_preserves_occurrence(self):
        """Test that thought chains preserve occurrence_id."""
        # Create task
        task = create_task(
            description="Test task",
            channel_id="test_channel",
            agent_occurrence_id="002",
            correlation_id="corr_123",
        )

        # Create seed thought
        seed = create_seed_thought_for_task(task=task)
        assert seed.agent_occurrence_id == "002"

        # Create first follow-up
        follow_1 = create_follow_up_thought(
            parent_thought=seed,
            content="First follow-up",
        )
        assert follow_1.agent_occurrence_id == "002"

        # Create second follow-up
        follow_2 = create_follow_up_thought(
            parent_thought=follow_1,
            content="Second follow-up",
        )
        assert follow_2.agent_occurrence_id == "002"

        # All should have same occurrence_id
        assert (
            task.agent_occurrence_id
            == seed.agent_occurrence_id
            == follow_1.agent_occurrence_id
            == follow_2.agent_occurrence_id
        )

    def test_no_default_occurrence_required(self):
        """Test that system works without 'default' occurrence."""
        # Create tasks for only custom occurrences
        task_001 = create_task(
            description="Task for 001",
            channel_id="channel_1",
            agent_occurrence_id="001",
            correlation_id="corr_123",
        )

        task_002 = create_task(
            description="Task for 002",
            channel_id="channel_2",
            agent_occurrence_id="002",
            correlation_id="corr_123",
        )

        task_003 = create_task(
            description="Task for 003",
            channel_id="channel_3",
            agent_occurrence_id="003",
            correlation_id="corr_123",
        )

        # Should all work without "default"
        assert task_001.agent_occurrence_id == "001"
        assert task_002.agent_occurrence_id == "002"
        assert task_003.agent_occurrence_id == "003"

    def test_wakeup_shutdown_coordination_pattern(self):
        """Test complete wakeup/shutdown coordination pattern across occurrences."""
        # Create shared wakeup task (would be created by occurrence that won the race)
        wakeup_task = create_task(
            description="Wakeup ritual (shared)",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="wakeup_20251030",
            task_id="WAKEUP_SHARED_20251030",
            priority=10,
        )

        # Create seed thought for wakeup (processing would happen on claiming occurrence)
        wakeup_seed = create_seed_thought_for_task(task=wakeup_task)

        # Create shutdown task
        shutdown_task = create_task(
            description="Shutdown ritual (shared)",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="shutdown_20251030",
            task_id="SHUTDOWN_SHARED_20251030",
            priority=10,
        )

        # Verify both coordination tasks maintain __shared__
        assert wakeup_task.agent_occurrence_id == "__shared__"
        assert wakeup_seed.agent_occurrence_id == "__shared__"
        assert shutdown_task.agent_occurrence_id == "__shared__"

        # Verify they have unique task IDs
        assert wakeup_task.task_id != shutdown_task.task_id
        assert "WAKEUP" in wakeup_task.task_id
        assert "SHUTDOWN" in shutdown_task.task_id

    def test_mixed_occurrence_deployment(self):
        """Test realistic deployment with __shared__, default, and custom occurrences."""
        # Shared coordination task
        shared_wakeup = create_task(
            description="Shared wakeup",
            channel_id="system",
            agent_occurrence_id="__shared__",
            correlation_id="wakeup_123",
        )

        # Default occurrence task (backward compatibility)
        default_task = create_task(
            description="Task from default",
            channel_id="discord_channel",
            agent_occurrence_id="default",
            correlation_id="discord_msg_1",
        )

        # Custom occurrence tasks (scale-out deployment)
        task_001 = create_task(
            description="Task from 001",
            channel_id="api_channel",
            agent_occurrence_id="001",
            correlation_id="api_req_1",
        )

        task_002 = create_task(
            description="Task from 002",
            channel_id="api_channel",
            agent_occurrence_id="002",
            correlation_id="api_req_2",
        )

        # All should maintain their distinct occurrence IDs
        assert shared_wakeup.agent_occurrence_id == "__shared__"
        assert default_task.agent_occurrence_id == "default"
        assert task_001.agent_occurrence_id == "001"
        assert task_002.agent_occurrence_id == "002"

        # Contexts should match
        assert shared_wakeup.context.agent_occurrence_id == "__shared__"
        assert default_task.context.agent_occurrence_id == "default"
        assert task_001.context.agent_occurrence_id == "001"
        assert task_002.context.agent_occurrence_id == "002"

    def test_parallel_thought_processing_isolation(self):
        """Test that parallel thought processing maintains occurrence isolation."""
        # Create tasks for 3 different occurrences
        occurrences = ["001", "002", "003"]
        tasks = []
        seed_thoughts = []
        follow_ups = []

        for occ_id in occurrences:
            # Each occurrence processes its own task
            task = create_task(
                description=f"Task for {occ_id}",
                channel_id=f"channel_{occ_id}",
                agent_occurrence_id=occ_id,
                correlation_id=f"corr_{occ_id}",
            )
            tasks.append(task)

            # Create seed thought
            seed = create_seed_thought_for_task(task=task)
            seed_thoughts.append(seed)

            # Create follow-up thought
            follow_up = create_follow_up_thought(
                parent_thought=seed,
                content=f"Follow-up from {occ_id}",
            )
            follow_ups.append(follow_up)

        # Verify each chain maintains its occurrence ID
        for i, occ_id in enumerate(occurrences):
            assert tasks[i].agent_occurrence_id == occ_id
            assert seed_thoughts[i].agent_occurrence_id == occ_id
            assert follow_ups[i].agent_occurrence_id == occ_id

            # Verify thought chains are properly linked
            assert seed_thoughts[i].source_task_id == tasks[i].task_id
            assert follow_ups[i].parent_thought_id == seed_thoughts[i].thought_id

    def test_occurrence_id_never_becomes_none(self):
        """Test that occurrence_id can never become None through factory."""
        # This should raise ValueError, not create task with None occurrence
        with pytest.raises(ValueError, match="agent_occurrence_id is required"):
            create_task(
                description="Task with empty occurrence",
                channel_id="channel",
                agent_occurrence_id="",
                correlation_id="corr_123",
            )

        # Same for thoughts
        with pytest.raises(ValueError, match="agent_occurrence_id is required"):
            create_thought(
                source_task_id="task_123",
                agent_occurrence_id="",
                correlation_id="corr_123",
                content="Invalid thought",
            )
