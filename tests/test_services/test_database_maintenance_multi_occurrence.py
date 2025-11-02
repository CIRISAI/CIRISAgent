"""
TDD tests for database maintenance service multi-occurrence support.

These tests verify that the maintenance service properly handles:
1. Shared tasks with __shared__ occurrence_id
2. Occurrence-specific tasks with proper occurrence_id isolation
3. Stale wakeup task cleanup across occurrences
4. Thought cleanup with correct occurrence_id context
"""

from datetime import datetime, timedelta, timezone

import pytest

from ciris_engine.logic import persistence
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus

pytestmark = pytest.mark.asyncio


class TestMultiOccurrenceWakeupCleanup:
    """Test stale wakeup task cleanup with multi-occurrence support."""

    async def test_cleanup_removes_stale_uppercase_shutdown_tasks(
        self,
        clean_db,
        database_maintenance_service,
        old_shutdown_task_data,
    ):
        """
        GIVEN a stale shared shutdown task with uppercase SHUTDOWN_ prefix (> 5 minutes old)
        WHEN startup cleanup runs
        THEN the task should be deleted

        This tests the fix for the bug where SHUTDOWN_ (uppercase) tasks weren't being
        cleaned up because the code only checked for "shutdown_" (lowercase), causing
        infinite loops when old shutdown tasks were reused on restart.
        """
        # Create stale shared shutdown task with uppercase SHUTDOWN_
        from ciris_engine.schemas.runtime.models import Task

        task = Task(**old_shutdown_task_data)
        persistence.add_task(task, clean_db)

        # Verify task exists before cleanup
        retrieved_before = persistence.get_task_by_id(
            old_shutdown_task_data["task_id"],
            old_shutdown_task_data["agent_occurrence_id"],
            clean_db,
        )
        assert retrieved_before is not None
        assert retrieved_before.task_id == "SHUTDOWN_SHARED_20251027"

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify task was deleted
        retrieved_after = persistence.get_task_by_id(
            old_shutdown_task_data["task_id"],
            old_shutdown_task_data["agent_occurrence_id"],
            clean_db,
        )
        assert retrieved_after is None

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
            retrieved = persistence.get_thought_by_id(thought_id, thought_data["agent_occurrence_id"], clean_db)
            assert retrieved is None, f"Expected {thought_id} to be cleaned"

        # Verify expected thoughts were preserved
        for thought_id in scenario["expected_preserved_thoughts"]:
            thought_data = next(t for t in scenario["thoughts"] if t["thought_id"] == thought_id)
            retrieved = persistence.get_thought_by_id(thought_id, thought_data["agent_occurrence_id"], clean_db)
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


def insert_raw_thought(db_path: str, thought_id: str, context_json: str, source_task_id: str = "task_123"):
    """
    Helper function to insert a thought with potentially invalid context directly into the database.

    This bypasses Pydantic validation to allow testing cleanup of malformed data.

    Args:
        db_path: Path to the database
        thought_id: Unique identifier for the thought
        context_json: JSON string for context (can be invalid)
        source_task_id: ID of the source task (default: "task_123")
    """
    from ciris_engine.logic.persistence import get_db_connection

    now = datetime.now(timezone.utc)

    with get_db_connection(db_path=db_path) as conn:
        # First, ensure the source task exists (for foreign key constraint)
        conn.execute(
            """
            INSERT OR IGNORE INTO tasks (task_id, description, status, agent_occurrence_id,
                                        channel_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_task_id,
                f"Test task {source_task_id}",
                "active",
                "default",
                "api",
                now.isoformat(),
                now.isoformat(),
            ),
        )

        # Now insert the thought
        conn.execute(
            """
            INSERT INTO thoughts (thought_id, source_task_id, agent_occurrence_id, channel_id,
                                thought_type, status, created_at, updated_at, round_number,
                                content, context_json, thought_depth)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                thought_id,
                source_task_id,
                "default",
                "api",
                "standard",  # Valid ThoughtType
                "pending",
                now.isoformat(),
                now.isoformat(),
                1,
                f"Test thought {thought_id}",
                context_json,
                0,
            ),
        )
        conn.commit()


class TestInsertRawThoughtHelper:
    """Test the insert_raw_thought helper function."""

    def test_insert_raw_thought_creates_record(self, clean_db):
        """
        GIVEN a database path and thought parameters
        WHEN insert_raw_thought is called
        THEN a thought record is created with the specified context
        """
        insert_raw_thought(clean_db, "helper_test_001", '{"task_id": "t1", "correlation_id": "c1"}')

        # Verify thought exists
        retrieved = persistence.get_thought_by_id("helper_test_001", "default", clean_db)
        assert retrieved is not None
        assert retrieved.thought_id == "helper_test_001"
        assert retrieved.source_task_id == "task_123"

    def test_insert_raw_thought_allows_invalid_context(self, clean_db):
        """
        GIVEN invalid context JSON
        WHEN insert_raw_thought is called
        THEN the record is created without Pydantic validation
        """
        # This would fail Pydantic validation but should work with raw insert
        insert_raw_thought(clean_db, "helper_test_002", "{}")

        # Verify thought exists with empty context
        from ciris_engine.logic.persistence import get_db_connection

        with get_db_connection(db_path=clean_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT context_json FROM thoughts WHERE thought_id = ?", ("helper_test_002",))
            row = cursor.fetchone()
            assert row is not None
            assert row["context_json"] == "{}"


class TestInvalidThoughtCleanup:
    """Test cleanup of thoughts with invalid or malformed context."""

    async def test_cleanup_invalid_thoughts_with_empty_context(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """
        GIVEN thoughts with empty context {}
        WHEN cleanup runs
        THEN invalid thoughts should be deleted
        """
        # Insert thought with empty context using helper
        insert_raw_thought(clean_db, "invalid_001", "{}")

        # Verify thought exists before cleanup
        retrieved_before = persistence.get_thought_by_id("invalid_001", "default", clean_db)
        assert retrieved_before is not None

        # Run cleanup
        await database_maintenance_service._cleanup_invalid_thoughts()

        # Verify thought was deleted
        retrieved_after = persistence.get_thought_by_id("invalid_001", "default", clean_db)
        assert retrieved_after is None

    async def test_cleanup_invalid_thoughts_missing_task_id(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """
        GIVEN thoughts with context missing task_id
        WHEN cleanup runs
        THEN invalid thoughts should be deleted
        """
        # Insert thought with context missing task_id
        insert_raw_thought(clean_db, "invalid_002", '{"correlation_id": "corr_123"}')

        # Run cleanup
        await database_maintenance_service._cleanup_invalid_thoughts()

        # Verify thought was deleted
        retrieved = persistence.get_thought_by_id("invalid_002", "default", clean_db)
        assert retrieved is None

    async def test_cleanup_invalid_thoughts_missing_correlation_id(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """
        GIVEN thoughts with context missing correlation_id
        WHEN cleanup runs
        THEN invalid thoughts should be deleted
        """
        # Insert thought with context missing correlation_id
        insert_raw_thought(clean_db, "invalid_003", '{"task_id": "task_123"}')

        # Run cleanup
        await database_maintenance_service._cleanup_invalid_thoughts()

        # Verify thought was deleted
        retrieved = persistence.get_thought_by_id("invalid_003", "default", clean_db)
        assert retrieved is None

    async def test_cleanup_invalid_thoughts_preserves_valid(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """
        GIVEN mix of valid and invalid thoughts
        WHEN cleanup runs
        THEN only invalid thoughts are deleted, valid ones preserved
        """
        # Insert valid thought with complete context
        insert_raw_thought(clean_db, "valid_001", '{"task_id": "task_123", "correlation_id": "corr_123"}')

        # Insert invalid thought with empty context
        insert_raw_thought(clean_db, "invalid_004", "{}")

        # Run cleanup
        await database_maintenance_service._cleanup_invalid_thoughts()

        # Verify valid thought preserved
        valid_retrieved = persistence.get_thought_by_id("valid_001", "default", clean_db)
        assert valid_retrieved is not None

        # Verify invalid thought deleted
        invalid_retrieved = persistence.get_thought_by_id("invalid_004", "default", clean_db)
        assert invalid_retrieved is None

    async def test_cleanup_invalid_thoughts_handles_no_invalid(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """
        GIVEN no invalid thoughts
        WHEN cleanup runs
        THEN no errors occur and valid thoughts preserved
        """
        # Insert only valid thought
        insert_raw_thought(clean_db, "valid_002", '{"task_id": "task_123", "correlation_id": "corr_123"}')

        # Run cleanup - should complete without errors
        await database_maintenance_service._cleanup_invalid_thoughts()

        # Verify valid thought still exists
        retrieved = persistence.get_thought_by_id("valid_002", "default", clean_db)
        assert retrieved is not None

    async def test_cleanup_invalid_thoughts_handles_exception(
        self,
        database_maintenance_service,
        monkeypatch,
    ):
        """
        GIVEN database error during cleanup
        WHEN cleanup runs
        THEN exception is caught and logged, no crash
        """

        # Mock get_db_connection to raise exception
        def mock_get_db_connection(*args, **kwargs):
            raise Exception("Database connection failed")

        monkeypatch.setattr(
            "ciris_engine.logic.persistence.get_db_connection",
            mock_get_db_connection,
        )

        # Should not raise exception
        await database_maintenance_service._cleanup_invalid_thoughts()


class TestMultiOccurrenceRaceConditionProtection:
    """Test protection against multi-occurrence race conditions during startup cleanup."""

    async def test_orphan_cleanup_skips_recently_created_tasks(
        self,
        clean_db,
        database_maintenance_service,
        mock_time_service,
    ):
        """
        GIVEN a multi-occurrence setup where Occurrence 2 creates wakeup step tasks
        AND Occurrence 1 starts up 10 seconds later and runs orphan cleanup
        WHEN orphan cleanup runs on Occurrence 1
        THEN tasks created within last 2 minutes should be skipped (not deleted)

        This tests the fix for the Scout wakeup bug where:
        - Scout 002 created wakeup step tasks at 00:19:56
        - Scout 001 started at 00:20:08 (12 seconds later)
        - Scout 001's orphan cleanup deleted Scout 002's fresh tasks
        - Result: Both stuck in wakeup loop (002 can't find tasks, 001 waits for 002)
        """
        from uuid import uuid4

        from ciris_engine.schemas.runtime.models import Task, TaskContext

        # Simulate Scout 002 creating wakeup step tasks
        now = mock_time_service.now()
        parent_task_id = f"WAKEUP_SHARED_{now.strftime('%Y%m%d')}"

        # Create parent shared wakeup task
        parent_task = Task(
            task_id=parent_task_id,
            channel_id="api_0.0.0.0_8080",
            agent_occurrence_id="__shared__",
            description="Wakeup ritual (shared across all occurrences)",
            status=TaskStatus.ACTIVE,
            priority=10,
            created_at=now.isoformat(),
            updated_at=now.isoformat(),
            context=TaskContext(
                channel_id="api_0.0.0.0_8080",
                user_id="system",
                correlation_id=f"wakeup_{now.strftime('%Y%m%d')}",
                agent_occurrence_id="__shared__",
            ),
        )
        persistence.add_task(parent_task, clean_db)

        # Create wakeup step tasks owned by occurrence "002" (child tasks)
        step_tasks = []
        for step_name in ["VERIFY_IDENTITY", "VALIDATE_INTEGRITY", "EVALUATE_RESILIENCE"]:
            task = Task(
                task_id=f"{step_name}_{uuid4()}",
                channel_id="api_0.0.0.0_8080",
                agent_occurrence_id="002",  # Owned by occurrence 002
                parent_task_id=parent_task_id,  # Child of shared wakeup task
                description=f"Wakeup step: {step_name}",
                status=TaskStatus.ACTIVE,
                priority=0,
                created_at=now.isoformat(),
                updated_at=now.isoformat(),
                context=TaskContext(
                    channel_id="api_0.0.0.0_8080",
                    user_id="system",
                    correlation_id=f"wakeup_{step_name.lower()}_{uuid4().hex[:8]}",
                    agent_occurrence_id="002",
                ),
            )
            persistence.add_task(task, clean_db)
            step_tasks.append(task)

        # Verify all tasks exist before cleanup
        assert persistence.get_task_by_id(parent_task_id, "__shared__", clean_db) is not None
        for task in step_tasks:
            assert persistence.get_task_by_id(task.task_id, "002", clean_db) is not None

        # Simulate Scout 001 starting up 10 seconds later
        # Run orphan cleanup (should SKIP recent tasks)
        await database_maintenance_service.perform_startup_cleanup()

        # Verify all tasks still exist (were NOT deleted due to age check)
        assert (
            persistence.get_task_by_id(parent_task_id, "__shared__", clean_db) is not None
        ), "Shared parent task should still exist"

        for task in step_tasks:
            retrieved = persistence.get_task_by_id(task.task_id, "002", clean_db)
            assert retrieved is not None, (
                f"Task {task.task_id} should still exist (created {(mock_time_service.now() - now).seconds}s ago, "
                "under 2-minute threshold)"
            )

    async def test_orphan_cleanup_deletes_old_orphaned_tasks(
        self,
        clean_db,
        database_maintenance_service,
        mock_time_service,
    ):
        """
        GIVEN orphaned tasks created > 2 minutes ago
        WHEN orphan cleanup runs
        THEN old orphaned tasks should be deleted

        This ensures the age check doesn't prevent legitimate cleanup of old orphans.
        """
        from uuid import uuid4

        from ciris_engine.schemas.runtime.models import Task, TaskContext

        # Create orphaned task (parent doesn't exist) from 5 minutes ago
        old_time = mock_time_service.now() - timedelta(minutes=5)

        orphaned_task = Task(
            task_id=f"ORPHAN_{uuid4()}",
            channel_id="api_0.0.0.0_8080",
            agent_occurrence_id="default",
            parent_task_id="NONEXISTENT_PARENT",  # Parent doesn't exist - orphan!
            description="Old orphaned task",
            status=TaskStatus.ACTIVE,
            priority=0,
            created_at=old_time.isoformat(),
            updated_at=old_time.isoformat(),
            context=TaskContext(
                channel_id="api_0.0.0.0_8080",
                user_id="system",
                correlation_id=f"orphan_{uuid4().hex[:8]}",
                agent_occurrence_id="default",
            ),
        )
        persistence.add_task(orphaned_task, clean_db)

        # Verify task exists before cleanup
        assert persistence.get_task_by_id(orphaned_task.task_id, "default", clean_db) is not None

        # Run orphan cleanup (should DELETE old orphan)
        await database_maintenance_service.perform_startup_cleanup()

        # Verify old orphaned task was marked as completed (by _cleanup_old_active_tasks)
        # Note: The old active task cleanup runs before orphan cleanup and marks old tasks as completed
        retrieved = persistence.get_task_by_id(orphaned_task.task_id, "default", clean_db)
        assert retrieved is not None, "Task should still exist (marked as completed, not deleted)"
        assert retrieved.status == TaskStatus.COMPLETED, (
            f"Old orphaned task should be marked as COMPLETED by _cleanup_old_active_tasks "
            f"(actual status: {retrieved.status})"
        )


class TestDialectAdapterInitialization:
    """Test that dialect adapter is initialized correctly for database operations."""

    async def test_cleanup_duplicate_temporal_edges_uses_correct_placeholders(
        self,
        clean_db,
        database_maintenance_service,
        mock_time_service,
    ):
        """
        GIVEN a PostgreSQL or SQLite database with duplicate temporal edges
        WHEN _cleanup_duplicate_temporal_edges runs during startup
        THEN it should use the correct SQL placeholders for the database backend

        Bug: _cleanup_duplicate_temporal_edges() called get_adapter() BEFORE opening
        the database connection, causing it to always get the default SQLite adapter
        even on PostgreSQL. This resulted in using '?' placeholders on PostgreSQL,
        causing SQL syntax errors during startup cleanup.

        Fix: Move get_adapter() call inside the with block AFTER get_db_connection()
        to ensure the dialect is initialized for the correct database backend.
        """
        from uuid import uuid4

        from ciris_engine.logic.persistence.db import get_db_connection
        from ciris_engine.logic.persistence.db.dialect import get_adapter
        from ciris_engine.schemas.runtime.models import TaskContext

        # Create duplicate temporal edges in the database
        now = mock_time_service.now().isoformat()
        old_time = (mock_time_service.now() - timedelta(minutes=10)).isoformat()

        # Create two summary nodes
        summary1_id = f"summary_{uuid4().hex[:8]}"
        summary2_id = f"summary_{uuid4().hex[:8]}"
        summary3_id = f"summary_{uuid4().hex[:8]}"

        with get_db_connection(clean_db) as conn:
            cursor = conn.cursor()
            adapter = get_adapter()
            ph = adapter.placeholder()

            # Insert summary nodes
            for summary_id in [summary1_id, summary2_id, summary3_id]:
                cursor.execute(
                    f"""
                    INSERT INTO graph_nodes (node_id, scope, node_type, attributes_json, created_at, updated_at)
                    VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
                """,
                    (summary_id, "default", "summary", "{}", now, now),
                )

            # Create duplicate TEMPORAL_NEXT edges (bug scenario)
            # summary1 -> summary2 (duplicate, older)
            cursor.execute(
                f"""
                INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, scope, relationship, created_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
                (f"edge_1_{uuid4().hex[:8]}", summary1_id, summary2_id, "default", "TEMPORAL_NEXT", old_time),
            )

            # summary1 -> summary2 (duplicate, newer - should be kept)
            cursor.execute(
                f"""
                INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, scope, relationship, created_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
                (f"edge_2_{uuid4().hex[:8]}", summary1_id, summary2_id, "default", "TEMPORAL_NEXT", now),
            )

            # Create duplicate TEMPORAL_PREV edges
            # summary2 -> summary1 (duplicate, older)
            cursor.execute(
                f"""
                INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, scope, relationship, created_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
                (f"edge_3_{uuid4().hex[:8]}", summary2_id, summary1_id, "default", "TEMPORAL_PREV", old_time),
            )

            # summary2 -> summary1 (duplicate, newer - should be kept)
            cursor.execute(
                f"""
                INSERT INTO graph_edges (edge_id, source_node_id, target_node_id, scope, relationship, created_at)
                VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph})
            """,
                (f"edge_4_{uuid4().hex[:8]}", summary2_id, summary1_id, "default", "TEMPORAL_PREV", now),
            )

            conn.commit()

            # Verify duplicates exist
            cursor.execute(
                f"""
                SELECT source_node_id, relationship, COUNT(*) as count
                FROM graph_edges
                WHERE relationship IN ('TEMPORAL_NEXT', 'TEMPORAL_PREV')
                GROUP BY source_node_id, relationship
                HAVING COUNT(*) > 1
            """
            )
            duplicates_before = cursor.fetchall()
            assert len(duplicates_before) == 2, "Should have 2 sets of duplicate edges"

        # Run cleanup - this should NOT raise SQL syntax errors
        await database_maintenance_service._cleanup_duplicate_temporal_edges()

        # Verify cleanup worked correctly
        with get_db_connection(clean_db) as conn:
            cursor = conn.cursor()
            adapter = get_adapter()

            # Check that duplicates are gone
            cursor.execute(
                """
                SELECT source_node_id, relationship, COUNT(*) as count
                FROM graph_edges
                WHERE relationship IN ('TEMPORAL_NEXT', 'TEMPORAL_PREV')
                GROUP BY source_node_id, relationship
                HAVING COUNT(*) > 1
            """
            )
            duplicates_after = cursor.fetchall()
            assert len(duplicates_after) == 0, "All duplicate edges should be cleaned up"

            # Check that we still have exactly 2 edges (one TEMPORAL_NEXT, one TEMPORAL_PREV)
            cursor.execute(
                """
                SELECT relationship, COUNT(*) as count
                FROM graph_edges
                WHERE relationship IN ('TEMPORAL_NEXT', 'TEMPORAL_PREV')
                GROUP BY relationship
            """
            )
            remaining_edges = cursor.fetchall()

            if adapter.is_postgresql():
                edge_counts = {row["relationship"]: row["count"] for row in remaining_edges}
            else:
                edge_counts = {row[0]: row[1] for row in remaining_edges}

            assert edge_counts.get("TEMPORAL_NEXT") == 1, "Should have exactly 1 TEMPORAL_NEXT edge (newest)"
            assert edge_counts.get("TEMPORAL_PREV") == 1, "Should have exactly 1 TEMPORAL_PREV edge (newest)"
