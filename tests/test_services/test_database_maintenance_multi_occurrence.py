"""
TDD tests for database maintenance service multi-occurrence support.

These tests verify that the maintenance service properly handles:
1. Shared tasks with __shared__ occurrence_id
2. Occurrence-specific tasks with proper occurrence_id isolation
3. Stale wakeup task cleanup across occurrences
4. Thought cleanup with correct occurrence_id context
"""

import pytest
from datetime import datetime, timedelta, timezone

from ciris_engine.logic import persistence
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus


pytestmark = pytest.mark.asyncio


class TestMultiOccurrenceWakeupCleanup:
    """Test stale wakeup task cleanup with multi-occurrence support."""

    async def test_cleanup_preserves_fresh_shared_wakeup_tasks(
        self,
        clean_db,
        database_maintenance_service,
        fresh_wakeup_task_data,
    ):
        """
        GIVEN a fresh shared wakeup task (< 5 minutes old)
        WHEN startup cleanup runs
        THEN the task should be preserved
        """
        # Create fresh shared wakeup task
        from ciris_engine.schemas.runtime.models import Task

        task = Task(**fresh_wakeup_task_data)
        persistence.add_task(task, clean_db)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify task still exists
        retrieved_task = persistence.get_task_by_id(
            fresh_wakeup_task_data["task_id"],
            fresh_wakeup_task_data["agent_occurrence_id"],
            clean_db,
        )
        assert retrieved_task is not None
        assert retrieved_task.status == TaskStatus.ACTIVE

    async def test_cleanup_removes_stale_shared_wakeup_tasks(
        self,
        clean_db,
        database_maintenance_service,
        old_wakeup_task_data,
    ):
        """
        GIVEN a stale shared wakeup task (> 5 minutes old)
        WHEN startup cleanup runs
        THEN the task should be deleted
        """
        # Create stale shared wakeup task
        from ciris_engine.schemas.runtime.models import Task

        task = Task(**old_wakeup_task_data)
        persistence.add_task(task, clean_db)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify task was deleted
        retrieved_task = persistence.get_task_by_id(
            old_wakeup_task_data["task_id"],
            old_wakeup_task_data["agent_occurrence_id"],
            clean_db,
        )
        assert retrieved_task is None

    async def test_cleanup_handles_occurrence_specific_tasks_correctly(
        self,
        clean_db,
        database_maintenance_service,
        fresh_wakeup_task_data,
        occurrence_specific_task_data,
    ):
        """
        GIVEN an occurrence-specific task with a shared parent
        WHEN startup cleanup runs with correct occurrence_id context
        THEN the task should not be marked as orphan
        """
        # Create shared parent task
        from ciris_engine.schemas.runtime.models import Task

        parent_task = Task(**fresh_wakeup_task_data)
        persistence.add_task(parent_task, clean_db)

        # Create occurrence-specific child task
        # Update parent_task_id to match fresh wakeup
        occurrence_specific_task_data["parent_task_id"] = fresh_wakeup_task_data["task_id"]
        child_task = Task(**occurrence_specific_task_data)
        persistence.add_task(child_task, clean_db)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify child task was NOT deleted (parent exists in shared namespace)
        retrieved_child = persistence.get_task_by_id(
            occurrence_specific_task_data["task_id"],
            occurrence_specific_task_data["agent_occurrence_id"],
            clean_db,
        )
        assert retrieved_child is not None
        assert retrieved_child.status == TaskStatus.ACTIVE


class TestMultiOccurrenceThoughtCleanup:
    """Test thought cleanup with multi-occurrence occurrence_id context."""

    async def test_cleanup_uses_correct_occurrence_id_for_thoughts(
        self,
        clean_db,
        database_maintenance_service,
        old_wakeup_task_data,
        stale_thought_data,
    ):
        """
        GIVEN a stale thought with __shared__ occurrence_id
        WHEN cleanup runs
        THEN get_thoughts_by_task_id must use the thought's occurrence_id
        """
        # Create stale shared wakeup task
        from ciris_engine.schemas.runtime.models import Task, Thought

        task = Task(**old_wakeup_task_data)
        persistence.add_task(task, clean_db)

        # Create stale thought for that task
        thought = Thought(**stale_thought_data)
        persistence.add_thought(thought, clean_db)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify thought was cleaned up
        retrieved_thought = persistence.get_thought_by_id(
            stale_thought_data["thought_id"],
            stale_thought_data["agent_occurrence_id"],
            clean_db,
        )
        assert retrieved_thought is None

    async def test_cleanup_preserves_thoughts_from_other_occurrences(
        self,
        clean_db,
        database_maintenance_service,
        multi_occurrence_cleanup_scenario,
    ):
        """
        GIVEN thoughts from multiple occurrences
        WHEN cleanup runs
        THEN only stale thoughts should be cleaned, preserving active ones
        """
        from ciris_engine.schemas.runtime.models import Task, Thought

        scenario = multi_occurrence_cleanup_scenario

        # Create all tasks
        for task_data in scenario["tasks"]:
            task = Task(**task_data)
            persistence.add_task(task, clean_db)

        # Create all thoughts
        for thought_data in scenario["thoughts"]:
            thought = Thought(**thought_data)
            persistence.add_thought(thought, clean_db)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify expected tasks were cleaned
        for task_id in scenario["expected_cleaned_tasks"]:
            # Get the task data to find its occurrence_id
            task_data = next(t for t in scenario["tasks"] if t["task_id"] == task_id)
            retrieved = persistence.get_task_by_id(task_id, task_data["agent_occurrence_id"], clean_db)
            assert retrieved is None, f"Expected {task_id} to be cleaned"

        # Verify expected tasks were preserved
        for task_id in scenario["expected_preserved_tasks"]:
            task_data = next(t for t in scenario["tasks"] if t["task_id"] == task_id)
            retrieved = persistence.get_task_by_id(task_id, task_data["agent_occurrence_id"], clean_db)
            assert retrieved is not None, f"Expected {task_id} to be preserved"

        # Verify expected thoughts were cleaned
        for thought_id in scenario["expected_cleaned_thoughts"]:
            thought_data = next(t for t in scenario["thoughts"] if t["thought_id"] == thought_id)
            retrieved = persistence.get_thought_by_id(
                thought_id,
                thought_data["agent_occurrence_id"],
                clean_db
            )
            assert retrieved is None, f"Expected {thought_id} to be cleaned"

        # Verify expected thoughts were preserved
        for thought_id in scenario["expected_preserved_thoughts"]:
            thought_data = next(t for t in scenario["thoughts"] if t["thought_id"] == thought_id)
            retrieved = persistence.get_thought_by_id(
                thought_id,
                thought_data["agent_occurrence_id"],
                clean_db
            )
            assert retrieved is not None, f"Expected {thought_id} to be preserved"


class TestMultiOccurrenceOldActiveTaskCleanup:
    """Test old active task cleanup with correct occurrence_id handling."""

    async def test_cleanup_uses_task_occurrence_id_not_default(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """
        GIVEN an old active task with occurrence_id="occurrence_1"
        WHEN cleanup marks it as completed
        THEN it should use the task's occurrence_id, NOT "default"
        """
        from ciris_engine.schemas.runtime.models import Task

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(minutes=10)

        # Create old active task with specific occurrence_id
        task_data = {
            "task_id": "old_user_task_123",
            "description": "Old user task",
            "status": "active",
            "agent_occurrence_id": "occurrence_1",
            "parent_task_id": None,
            "created_at": old_time.isoformat(),
            "updated_at": old_time.isoformat(),
            "channel_id": "api",
        }
        task = Task(**task_data)
        persistence.add_task(task, clean_db)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify task was marked completed with correct occurrence_id
        retrieved = persistence.get_task_by_id("old_user_task_123", "occurrence_1", clean_db)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.COMPLETED

        # Verify it's NOT accessible under "default" occurrence_id
        retrieved_default = persistence.get_task_by_id("old_user_task_123", "default", clean_db)
        assert retrieved_default is None


class TestSharedWakeupTaskIsolation:
    """Test that shared wakeup tasks are properly isolated and cleaned."""

    async def test_multiple_fresh_shared_wakeups_from_rapid_restarts(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """
        GIVEN multiple shared wakeup tasks from rapid restarts
        WHEN cleanup runs
        THEN only the stale ones (>5 min) should be cleaned
        """
        from ciris_engine.schemas.runtime.models import Task

        now = datetime.now(timezone.utc)

        # Create old wakeup (should clean)
        old_wakeup = Task(
            task_id="WAKEUP_SHARED_DAY1",
            description="Wakeup from yesterday",
            status=TaskStatus.ACTIVE,
            agent_occurrence_id="__shared__",
            parent_task_id=None,
            created_at=(now - timedelta(days=1)).isoformat(),
            updated_at=(now - timedelta(days=1)).isoformat(),
            channel_id="api",
        )
        persistence.add_task(old_wakeup, clean_db)

        # Create medium-old wakeup (should clean, >5min)
        medium_wakeup = Task(
            task_id="WAKEUP_SHARED_10MIN",
            description="Wakeup from 10min ago",
            status=TaskStatus.ACTIVE,
            agent_occurrence_id="__shared__",
            parent_task_id=None,
            created_at=(now - timedelta(minutes=10)).isoformat(),
            updated_at=(now - timedelta(minutes=10)).isoformat(),
            channel_id="api",
        )
        persistence.add_task(medium_wakeup, clean_db)

        # Create fresh wakeup (should preserve, <5min)
        fresh_wakeup = Task(
            task_id="WAKEUP_SHARED_NOW",
            description="Current wakeup",
            status=TaskStatus.ACTIVE,
            agent_occurrence_id="__shared__",
            parent_task_id=None,
            created_at=(now - timedelta(seconds=30)).isoformat(),
            updated_at=(now - timedelta(seconds=30)).isoformat(),
            channel_id="api",
        )
        persistence.add_task(fresh_wakeup, clean_db)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify old wakeups cleaned
        assert persistence.get_task_by_id("WAKEUP_SHARED_DAY1", "__shared__", clean_db) is None
        assert persistence.get_task_by_id("WAKEUP_SHARED_10MIN", "__shared__", clean_db) is None

        # Verify fresh wakeup preserved
        retrieved = persistence.get_task_by_id("WAKEUP_SHARED_NOW", "__shared__", clean_db)
        assert retrieved is not None
        assert retrieved.status == TaskStatus.ACTIVE
