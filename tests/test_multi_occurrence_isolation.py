"""
Tests for multi-occurrence isolation.

Verifies that multiple agent instances with different occurrence_ids
can safely operate against the same SQLite database without interfering
with each other's work.
"""

from datetime import datetime, timezone
from typing import List

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.persistence.analytics import get_pending_thoughts_for_active_tasks
from ciris_engine.logic.persistence.models.tasks import (
    add_task,
    get_active_task_for_channel,
    get_all_tasks,
    get_pending_tasks_for_activation,
    get_task_by_id,
)
from ciris_engine.logic.persistence.models.thoughts import add_thought, get_thought_by_id, get_thoughts_by_task_id
from ciris_engine.logic.processors.support.task_manager import TaskManager
from ciris_engine.logic.processors.support.thought_manager import ThoughtManager
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, TaskContext, Thought, ThoughtContext


class MockTimeService:
    """Simple mock time service for testing."""

    def now(self):
        """Get current time in UTC."""
        return datetime.now(timezone.utc)

    def now_iso(self) -> str:
        """Get current time as ISO string."""
        return self.now().isoformat()

    def timestamp(self) -> float:
        """Get current Unix timestamp."""
        return self.now().timestamp()


class TestMultiOccurrenceIsolation:
    """Test suite for multi-occurrence isolation functionality."""

    @pytest.fixture
    def time_service(self):
        """Provide a mock time service."""
        return MockTimeService()

    @pytest.fixture
    def occurrence_a(self):
        """First occurrence ID."""
        return "api-instance-001"

    @pytest.fixture
    def occurrence_b(self):
        """Second occurrence ID."""
        return "api-instance-002"

    def test_task_creation_with_different_occurrences(self, clean_db, time_service, occurrence_a, occurrence_b):
        """Test that tasks created by different occurrences are properly stamped."""
        # Create tasks for occurrence A
        task_a = Task(
            task_id="task_a_001",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_a,
            description="Task from occurrence A",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_a_001",
                parent_task_id=None,
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_task(task_a, db_path=clean_db)

        # Create tasks for occurrence B
        task_b = Task(
            task_id="task_b_001",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_b,
            description="Task from occurrence B",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_b_001",
                parent_task_id=None,
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_task(task_b, db_path=clean_db)

        # Verify occurrence A only sees its task
        task_a_retrieved = get_task_by_id("task_a_001", occurrence_a, db_path=clean_db)
        assert task_a_retrieved is not None
        assert task_a_retrieved.agent_occurrence_id == occurrence_a

        # Verify occurrence A cannot see occurrence B's task
        task_b_from_a = get_task_by_id("task_b_001", occurrence_a, db_path=clean_db)
        assert task_b_from_a is None

        # Verify occurrence B only sees its task
        task_b_retrieved = get_task_by_id("task_b_001", occurrence_b, db_path=clean_db)
        assert task_b_retrieved is not None
        assert task_b_retrieved.agent_occurrence_id == occurrence_b

        # Verify occurrence B cannot see occurrence A's task
        task_a_from_b = get_task_by_id("task_a_001", occurrence_b, db_path=clean_db)
        assert task_a_from_b is None

    def test_get_all_tasks_filtered_by_occurrence(self, clean_db, time_service, occurrence_a, occurrence_b):
        """Test that get_all_tasks returns only tasks for the specified occurrence."""
        # Create 3 tasks for occurrence A
        for i in range(3):
            task = Task(
                task_id=f"task_a_{i}",
                channel_id="channel_1",
                agent_occurrence_id=occurrence_a,
                description=f"Task A {i}",
                status=TaskStatus.ACTIVE,
                priority=5,
                created_at=time_service.now_iso(),
                updated_at=time_service.now_iso(),
                context=TaskContext(
                    channel_id="channel_1",
                    user_id="user_1",
                    correlation_id=f"corr_a_{i}",
                    parent_task_id=None,
                    agent_occurrence_id=occurrence_a,
                ),
            )
            add_task(task, db_path=clean_db)

        # Create 2 tasks for occurrence B
        for i in range(2):
            task = Task(
                task_id=f"task_b_{i}",
                channel_id="channel_1",
                agent_occurrence_id=occurrence_b,
                description=f"Task B {i}",
                status=TaskStatus.ACTIVE,
                priority=5,
                created_at=time_service.now_iso(),
                updated_at=time_service.now_iso(),
                context=TaskContext(
                    channel_id="channel_1",
                    user_id="user_1",
                    correlation_id=f"corr_b_{i}",
                    parent_task_id=None,
                    agent_occurrence_id=occurrence_b,
                ),
            )
            add_task(task, db_path=clean_db)

        # Verify occurrence A sees only its 3 tasks
        tasks_a = get_all_tasks(occurrence_a, db_path=clean_db)
        assert len(tasks_a) == 3
        assert all(t.agent_occurrence_id == occurrence_a for t in tasks_a)

        # Verify occurrence B sees only its 2 tasks
        tasks_b = get_all_tasks(occurrence_b, db_path=clean_db)
        assert len(tasks_b) == 2
        assert all(t.agent_occurrence_id == occurrence_b for t in tasks_b)

    def test_channel_task_isolation(self, clean_db, time_service, occurrence_a, occurrence_b):
        """Test that get_active_task_for_channel respects occurrence boundaries."""
        channel_id = "shared_channel"

        # Occurrence A creates task for shared channel
        task_a = Task(
            task_id="task_a_channel",
            channel_id=channel_id,
            agent_occurrence_id=occurrence_a,
            description="Task A for shared channel",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id=channel_id,
                user_id="user_1",
                correlation_id="corr_a_channel",
                parent_task_id=None,
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_task(task_a, db_path=clean_db)

        # Occurrence B creates task for same channel
        task_b = Task(
            task_id="task_b_channel",
            channel_id=channel_id,
            agent_occurrence_id=occurrence_b,
            description="Task B for shared channel",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id=channel_id,
                user_id="user_1",
                correlation_id="corr_b_channel",
                parent_task_id=None,
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_task(task_b, db_path=clean_db)

        # Occurrence A should only see its task
        active_task_a = get_active_task_for_channel(channel_id, occurrence_a, db_path=clean_db)
        assert active_task_a is not None
        assert active_task_a.task_id == "task_a_channel"
        assert active_task_a.agent_occurrence_id == occurrence_a

        # Occurrence B should only see its task
        active_task_b = get_active_task_for_channel(channel_id, occurrence_b, db_path=clean_db)
        assert active_task_b is not None
        assert active_task_b.task_id == "task_b_channel"
        assert active_task_b.agent_occurrence_id == occurrence_b

    def test_thought_isolation(self, clean_db, time_service, occurrence_a, occurrence_b):
        """Test that thoughts are properly isolated between occurrences."""
        # Create task for occurrence A
        task_a = Task(
            task_id="task_a_thoughts",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_a,
            description="Task A with thoughts",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_a",
                parent_task_id=None,
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_task(task_a, db_path=clean_db)

        # Create thought for occurrence A
        thought_a = Thought(
            thought_id="thought_a_001",
            source_task_id="task_a_thoughts",
            agent_occurrence_id=occurrence_a,
            channel_id="channel_1",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="Thought from A",
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
            context=ThoughtContext(
                task_id="task_a_thoughts",
                channel_id="channel_1",
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id="corr_a",
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_thought(thought_a, db_path=clean_db)

        # Create task for occurrence B
        task_b = Task(
            task_id="task_b_thoughts",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_b,
            description="Task B with thoughts",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_b",
                parent_task_id=None,
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_task(task_b, db_path=clean_db)

        # Create thought for occurrence B
        thought_b = Thought(
            thought_id="thought_b_001",
            source_task_id="task_b_thoughts",
            agent_occurrence_id=occurrence_b,
            channel_id="channel_1",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="Thought from B",
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
            context=ThoughtContext(
                task_id="task_b_thoughts",
                channel_id="channel_1",
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id="corr_b",
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_thought(thought_b, db_path=clean_db)

        # Verify occurrence A only sees its thought
        thought_a_retrieved = get_thought_by_id("thought_a_001", occurrence_a, db_path=clean_db)
        assert thought_a_retrieved is not None
        assert thought_a_retrieved.agent_occurrence_id == occurrence_a

        # Verify occurrence A cannot see occurrence B's thought
        thought_b_from_a = get_thought_by_id("thought_b_001", occurrence_a, db_path=clean_db)
        assert thought_b_from_a is None

        # Verify thoughts by task isolation
        thoughts_for_task_a = get_thoughts_by_task_id("task_a_thoughts", occurrence_a, db_path=clean_db)
        assert len(thoughts_for_task_a) == 1
        assert thoughts_for_task_a[0].thought_id == "thought_a_001"

        # Occurrence A should not see task B's thoughts
        thoughts_for_task_b_from_a = get_thoughts_by_task_id("task_b_thoughts", occurrence_a, db_path=clean_db)
        assert len(thoughts_for_task_b_from_a) == 0

    def test_pending_thoughts_for_active_tasks(self, clean_db, time_service, occurrence_a, occurrence_b):
        """Test that thoughts for active tasks are properly isolated by occurrence."""
        # Create active task and pending thought for occurrence A
        task_a = Task(
            task_id="task_a_pending",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_a,
            description="Task A",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_a",
                parent_task_id=None,
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_task(task_a, db_path=clean_db)

        thought_a = Thought(
            thought_id="thought_a_pending",
            source_task_id="task_a_pending",
            agent_occurrence_id=occurrence_a,
            channel_id="channel_1",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="Pending thought A",
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
            context=ThoughtContext(
                task_id="task_a_pending",
                channel_id="channel_1",
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id="corr_a",
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_thought(thought_a, db_path=clean_db)

        # Create active task and pending thought for occurrence B
        task_b = Task(
            task_id="task_b_pending",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_b,
            description="Task B",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_b",
                parent_task_id=None,
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_task(task_b, db_path=clean_db)

        thought_b = Thought(
            thought_id="thought_b_pending",
            source_task_id="task_b_pending",
            agent_occurrence_id=occurrence_b,
            channel_id="channel_1",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="Pending thought B",
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
            context=ThoughtContext(
                task_id="task_b_pending",
                channel_id="channel_1",
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id="corr_b",
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_thought(thought_b, db_path=clean_db)

        # Verify thoughts are isolated by occurrence via direct queries
        thoughts_a_for_task = get_thoughts_by_task_id("task_a_pending", occurrence_a, db_path=clean_db)
        assert len(thoughts_a_for_task) == 1
        assert thoughts_a_for_task[0].thought_id == "thought_a_pending"

        thoughts_b_for_task = get_thoughts_by_task_id("task_b_pending", occurrence_b, db_path=clean_db)
        assert len(thoughts_b_for_task) == 1
        assert thoughts_b_for_task[0].thought_id == "thought_b_pending"

        # Verify cross-occurrence isolation
        assert len(get_thoughts_by_task_id("task_a_pending", occurrence_b, db_path=clean_db)) == 0
        assert len(get_thoughts_by_task_id("task_b_pending", occurrence_a, db_path=clean_db)) == 0

    def test_task_manager_isolation(self, clean_db, time_service, occurrence_a, occurrence_b):
        """Test that tasks created with occurrence_id are properly isolated."""
        # Create tasks for both occurrences with different status combinations
        task_a1 = Task(
            task_id="task_a1_manager",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_a,
            description="Task A1",
            status=TaskStatus.PENDING,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_a1",
                parent_task_id=None,
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_task(task_a1, db_path=clean_db)

        task_a2 = Task(
            task_id="task_a2_manager",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_a,
            description="Task A2",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_a2",
                parent_task_id=None,
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_task(task_a2, db_path=clean_db)

        task_b = Task(
            task_id="task_b_manager",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_b,
            description="Task B",
            status=TaskStatus.PENDING,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_b",
                parent_task_id=None,
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_task(task_b, db_path=clean_db)

        # Verify tasks are properly isolated using get_all_tasks
        all_tasks_a = get_all_tasks(occurrence_a, db_path=clean_db)
        assert len(all_tasks_a) == 2
        assert all(t.agent_occurrence_id == occurrence_a for t in all_tasks_a)

        all_tasks_b = get_all_tasks(occurrence_b, db_path=clean_db)
        assert len(all_tasks_b) == 1
        assert all(t.agent_occurrence_id == occurrence_b for t in all_tasks_b)

        # Verify cross-occurrence access fails
        assert get_task_by_id("task_a1_manager", occurrence_b, db_path=clean_db) is None
        assert get_task_by_id("task_b_manager", occurrence_a, db_path=clean_db) is None

    def test_thought_manager_isolation(self, clean_db, time_service, occurrence_a, occurrence_b):
        """Test that thoughts created with occurrence_id are properly isolated."""
        # Create tasks and thoughts for both occurrences
        task_a = Task(
            task_id="task_a_tm",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_a,
            description="Task A",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_a",
                parent_task_id=None,
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_task(task_a, db_path=clean_db)

        thought_a1 = Thought(
            thought_id="thought_a1_tm",
            source_task_id="task_a_tm",
            agent_occurrence_id=occurrence_a,
            channel_id="channel_1",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="Thought A1",
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
            context=ThoughtContext(
                task_id="task_a_tm",
                channel_id="channel_1",
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id="corr_a",
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_thought(thought_a1, db_path=clean_db)

        thought_a2 = Thought(
            thought_id="thought_a2_tm",
            source_task_id="task_a_tm",
            agent_occurrence_id=occurrence_a,
            channel_id="channel_1",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PROCESSING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="Thought A2",
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
            context=ThoughtContext(
                task_id="task_a_tm",
                channel_id="channel_1",
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id="corr_a",
                agent_occurrence_id=occurrence_a,
            ),
        )
        add_thought(thought_a2, db_path=clean_db)

        task_b = Task(
            task_id="task_b_tm",
            channel_id="channel_1",
            agent_occurrence_id=occurrence_b,
            description="Task B",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_b",
                parent_task_id=None,
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_task(task_b, db_path=clean_db)

        thought_b = Thought(
            thought_id="thought_b_tm",
            source_task_id="task_b_tm",
            agent_occurrence_id=occurrence_b,
            channel_id="channel_1",
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            round_number=0,
            content="Thought B",
            thought_depth=0,
            ponder_notes=None,
            parent_thought_id=None,
            final_action=None,
            context=ThoughtContext(
                task_id="task_b_tm",
                channel_id="channel_1",
                round_number=0,
                depth=0,
                parent_thought_id=None,
                correlation_id="corr_b",
                agent_occurrence_id=occurrence_b,
            ),
        )
        add_thought(thought_b, db_path=clean_db)

        # Verify thoughts are properly stamped and isolated
        thoughts_a = get_thoughts_by_task_id("task_a_tm", occurrence_a, db_path=clean_db)
        assert len(thoughts_a) == 2
        assert all(t.agent_occurrence_id == occurrence_a for t in thoughts_a)
        thought_ids_a = {t.thought_id for t in thoughts_a}
        assert "thought_a1_tm" in thought_ids_a
        assert "thought_a2_tm" in thought_ids_a

        thoughts_b = get_thoughts_by_task_id("task_b_tm", occurrence_b, db_path=clean_db)
        assert len(thoughts_b) == 1
        assert thoughts_b[0].agent_occurrence_id == occurrence_b
        assert thoughts_b[0].thought_id == "thought_b_tm"

        # Verify cross-occurrence access fails
        assert len(get_thoughts_by_task_id("task_a_tm", occurrence_b, db_path=clean_db)) == 0
        assert len(get_thoughts_by_task_id("task_b_tm", occurrence_a, db_path=clean_db)) == 0

    def test_default_occurrence_backward_compatibility(self, clean_db, time_service):
        """Test that 'default' occurrence_id maintains backward compatibility."""
        # Create task with default occurrence
        task = Task(
            task_id="task_default",
            channel_id="channel_1",
            agent_occurrence_id="default",
            description="Task with default occurrence",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=time_service.now_iso(),
            updated_at=time_service.now_iso(),
            context=TaskContext(
                channel_id="channel_1",
                user_id="user_1",
                correlation_id="corr_default",
                parent_task_id=None,
                agent_occurrence_id="default",
            ),
        )
        add_task(task, db_path=clean_db)

        # Should be retrievable with 'default'
        retrieved = get_task_by_id("task_default", "default", db_path=clean_db)
        assert retrieved is not None
        assert retrieved.agent_occurrence_id == "default"

        # Should not be accessible from other occurrences
        assert get_task_by_id("task_default", "other", db_path=clean_db) is None
