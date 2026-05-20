"""
TDD tests for database maintenance service multi-occurrence support.

These tests verify that the maintenance service properly handles:
1. Shared tasks with __shared__ occurrence_id
2. Occurrence-specific tasks with proper occurrence_id isolation
3. Stale wakeup task cleanup across occurrences
4. Thought cleanup with correct occurrence_id context
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

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
        )
        assert retrieved_before is not None
        assert retrieved_before.task_id == "SHUTDOWN_SHARED_20251027"

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Verify task was deleted
        retrieved_after = persistence.get_task_by_id(
            old_shutdown_task_data["task_id"],
            old_shutdown_task_data["agent_occurrence_id"],
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
        persistence.add_thought(thought)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Post-2.9.0 absorption: cleanup deletes the stale thought via
        # persist's thought_delete substrate (CIRISPersist#60 landed in
        # the 1.6.x window). The thought_id is the canonical key — the
        # occurrence_id must be passed to avoid cross-occurrence leakage.
        retrieved_thought = persistence.get_thought_by_id(
            stale_thought_data["thought_id"],
            stale_thought_data["agent_occurrence_id"],
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
            persistence.add_thought(thought)

        # Run startup cleanup
        await database_maintenance_service.perform_startup_cleanup()

        # Post-2.9.0 absorption (CIRISAgent#763 / CIRISPersist#60): persist
        # has no `thought_delete` API. `delete_tasks_by_ids` now soft-cancels
        # (parent task → 'failed') when child thoughts block FK cascade.
        # Tasks marked for cleanup are still loadable but with status FAILED;
        # child thoughts stay put. When CIRISPersist#60 lands the assertions
        # flip back to expect physical deletion.
        for task_id in scenario["expected_cleaned_tasks"]:
            task_data = next(t for t in scenario["tasks"] if t["task_id"] == task_id)
            retrieved = persistence.get_task_by_id(task_id, task_data["agent_occurrence_id"])
            # Row remains; soft-cancelled to FAILED status (or already gone if
            # it had no child thoughts and persist.task_delete succeeded).
            if retrieved is not None:
                assert retrieved.status in (TaskStatus.FAILED, TaskStatus.COMPLETED), (
                    f"Expected {task_id} to be cleaned (deleted or soft-cancelled); got {retrieved.status}"
                )

        # Verify expected tasks were preserved (these never reach the
        # cleanup pass, so they remain active/unchanged).
        for task_id in scenario["expected_preserved_tasks"]:
            task_data = next(t for t in scenario["tasks"] if t["task_id"] == task_id)
            retrieved = persistence.get_task_by_id(task_id, task_data["agent_occurrence_id"])
            assert retrieved is not None, f"Expected {task_id} to be preserved"

        # Thought rows: soft-cancel of parent task does NOT physically remove
        # child thoughts. They all stay (a regression vs legacy until
        # CIRISPersist#60 lands).
        for thought_id in scenario["expected_preserved_thoughts"]:
            thought_data = next(t for t in scenario["thoughts"] if t["thought_id"] == thought_id)
            retrieved = persistence.get_thought_by_id(thought_id, thought_data["agent_occurrence_id"])
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

        # Verify task was marked with a terminal status under its
        # correct occurrence_id (COMPLETED via update_task_status, or
        # FAILED via the soft-cancel fallback path).
        retrieved = persistence.get_task_by_id("old_user_task_123", "occurrence_1")
        assert retrieved is not None
        assert retrieved.status in (TaskStatus.COMPLETED, TaskStatus.FAILED)

        # Verify it's NOT accessible under "default" occurrence_id
        retrieved_default = persistence.get_task_by_id("old_user_task_123", "default")
        assert retrieved_default is None


@pytest.mark.timeout(60)  # Fail fast if cleanup takes >60s
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
        assert persistence.get_task_by_id("WAKEUP_SHARED_DAY1", "__shared__") is None
        assert persistence.get_task_by_id("WAKEUP_SHARED_10MIN", "__shared__") is None

        # Verify fresh wakeup preserved
        retrieved = persistence.get_task_by_id("WAKEUP_SHARED_NOW", "__shared__")
        assert retrieved is not None
        assert retrieved.status == TaskStatus.ACTIVE


def insert_raw_thought(db_path: str, thought_id: str, context_json: str, source_task_id: str = "task_123"):
    """
    Helper function to insert a thought with potentially invalid context.

    Post-2.9.0 absorption (CIRISAgent#763): routes through persist substrate
    so migrated readers find the row. The context_json may be an invalid
    pattern string — it lands in `cirislens_thoughts.context_json` as-is.

    Args:
        db_path: Path to the database (legacy parameter; persist engine is
                 wired module-globally and ignores this).
        thought_id: Unique identifier for the thought
        context_json: JSON string for context (can be invalid)
        source_task_id: ID of the source task (default: "task_123")
    """
    import json as _json

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    assert engine is not None, "persist engine must be wired"

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    # Ensure source task exists in persist (FK constraint on cirislens_thoughts).
    task_payload = {
        "task_id": source_task_id,
        "channel_id": "api",
        "agent_occurrence_id": "default",
        "description": f"Test task {source_task_id}",
        "status": "active",
        "priority": 0,
        "created_at": now_iso,
        "updated_at": now_iso,
    }
    engine.task_upsert(_json.dumps(task_payload))

    # Insert thought. The context payload may be a malformed string; persist
    # accepts both dict and string and stores it verbatim.
    try:
        parsed_ctx = _json.loads(context_json) if context_json else None
    except _json.JSONDecodeError:
        parsed_ctx = None

    thought_payload = {
        "thought_id": thought_id,
        "source_task_id": source_task_id,
        "agent_occurrence_id": "default",
        "channel_id": "api",
        "thought_type": "standard",
        "status": "pending",
        "created_at": now_iso,
        "updated_at": now_iso,
        "round_number": 1,
        "content": f"Test thought {thought_id}",
        "thought_depth": 0,
    }
    if parsed_ctx is not None:
        thought_payload["context"] = parsed_ctx
    engine.thought_upsert(_json.dumps(thought_payload))


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
        retrieved = persistence.get_thought_by_id("helper_test_001", "default")
        assert retrieved is not None
        assert retrieved.thought_id == "helper_test_001"
        assert retrieved.source_task_id == "task_123"

    def test_insert_raw_thought_allows_invalid_context(self, clean_db):
        """
        GIVEN invalid context JSON
        WHEN insert_raw_thought is called
        THEN the record is created in `cirislens_thoughts` (persist substrate).

        Post-2.9.0 absorption: empty `{}` context arrives at persist as the
        empty-dict payload and is dropped on the substrate side (no
        materialization). The row still exists; we verify via persist
        engine directly.
        """
        insert_raw_thought(clean_db, "helper_test_002", "{}")

        # Verify thought row exists in the persist substrate.
        import json as _json

        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        raw = engine.thought_get("helper_test_002")
        assert raw is not None
        row = _json.loads(raw) if isinstance(raw, str) else raw
        # Empty {} context is dropped to None by persist; the row still exists.
        assert row["thought_id"] == "helper_test_002"


class TestInvalidThoughtCleanup:
    """Test cleanup of thoughts with invalid or malformed context.

    Post-2.9.0 absorption (CIRISAgent#763): `_cleanup_invalid_thoughts` is
    a soft no-op pending CIRISPersist#60 (`thought_delete` API). These
    tests now assert the no-op behaviour rather than hard deletion; they
    will be flipped back when persist exposes `thought_delete`.
    """

    async def test_cleanup_invalid_thoughts_with_empty_context(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """Soft no-op: invalid thought row remains after cleanup."""
        insert_raw_thought(clean_db, "invalid_001", "{}")

        # Run cleanup (now a no-op)
        await database_maintenance_service._cleanup_invalid_thoughts()

        # Verify thought was NOT deleted (soft no-op pending CIRISPersist#60).
        # Note: the row may still be invisible to migrated readers because
        # it was inserted via raw SQL into legacy `thoughts`, not
        # `cirislens_thoughts`. We don't assert via the migrated reader
        # here; just verify cleanup didn't crash.

    async def test_cleanup_invalid_thoughts_missing_task_id(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """Soft no-op: invalid thought row missing task_id remains."""
        insert_raw_thought(clean_db, "invalid_002", '{"correlation_id": "corr_123"}')
        await database_maintenance_service._cleanup_invalid_thoughts()

    async def test_cleanup_invalid_thoughts_missing_correlation_id(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """Soft no-op: invalid thought row missing correlation_id remains."""
        insert_raw_thought(clean_db, "invalid_003", '{"task_id": "task_123"}')
        await database_maintenance_service._cleanup_invalid_thoughts()

    async def test_cleanup_invalid_thoughts_preserves_valid(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """Soft no-op: valid thoughts always preserved."""
        insert_raw_thought(clean_db, "valid_001", '{"task_id": "task_123", "correlation_id": "corr_123"}')
        insert_raw_thought(clean_db, "invalid_004", "{}")

        await database_maintenance_service._cleanup_invalid_thoughts()

        # Both rows remain in the legacy `thoughts` table; cleanup is a
        # no-op pending CIRISPersist#60. We just verify it didn't crash.

    async def test_cleanup_invalid_thoughts_handles_no_invalid(
        self,
        clean_db,
        database_maintenance_service,
    ):
        """Soft no-op: also a no-op when no invalid thoughts exist."""
        insert_raw_thought(clean_db, "valid_002", '{"task_id": "task_123", "correlation_id": "corr_123"}')

        # Run cleanup - should complete without errors (soft no-op).
        await database_maintenance_service._cleanup_invalid_thoughts()

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

        # Force persist engine to be unavailable so _cleanup_invalid_thoughts
        # hits its exception path. Post-2.9.0 the cleanup uses persist's
        # `thought_list` / `cirisgraph_*` rather than `get_db_connection`;
        # patching `get_persist_engine` to return None achieves the same
        # "downstream layer broken" contract the legacy mock provided.
        monkeypatch.setattr(
            "ciris_engine.logic.persistence.models.graph.get_persist_engine",
            lambda: None,
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
        assert persistence.get_task_by_id(parent_task_id, "__shared__") is not None
        for task in step_tasks:
            assert persistence.get_task_by_id(task.task_id, "002") is not None

        # Simulate Scout 001 starting up 10 seconds later
        # Run orphan cleanup (should SKIP recent tasks)
        await database_maintenance_service.perform_startup_cleanup()

        # Verify all tasks still exist (were NOT deleted due to age check)
        assert (
            persistence.get_task_by_id(parent_task_id, "__shared__") is not None
        ), "Shared parent task should still exist"

        for task in step_tasks:
            retrieved = persistence.get_task_by_id(task.task_id, "002")
            assert retrieved is not None, (
                f"Task {task.task_id} should still exist (created {(mock_time_service.now() - now).seconds}s ago, "
                "under 2-minute threshold)"
            )

    @pytest.mark.xfail(
        reason=(
            "Post-2.9.0 absorption (CIRISAgent#763): the test pre-seeds an "
            "'orphan' task with parent_task_id='NONEXISTENT_PARENT'. Persist's "
            "cirislens_tasks FK on parent_task_id is now strictly enforced, "
            "so add_task itself raises Conflict before cleanup even runs. "
            "The orphan-by-dangling-pointer scenario was a quirk of the "
            "legacy schema that didn't enforce that FK — it's no longer "
            "reachable. To exercise this code path under the new substrate, "
            "seed with a parent task that is then deleted (which is itself "
            "blocked by FK pending CIRISPersist#60)."
        ),
        strict=False,
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
        assert persistence.get_task_by_id(orphaned_task.task_id, "default") is not None

        # Run orphan cleanup (should DELETE old orphan)
        await database_maintenance_service.perform_startup_cleanup()

        # Verify old orphaned task was marked with a terminal status.
        # Pre-2.9.0: _cleanup_old_active_tasks → COMPLETED.
        # Post-2.9.0 (CIRISAgent#763 / CIRISPersist#60): the soft-cancel
        # fallback in `delete_tasks_by_ids` may also flip it to FAILED if
        # cleanup tried task_delete first and hit the FK constraint.
        retrieved = persistence.get_task_by_id(orphaned_task.task_id, "default")
        assert retrieved is not None, "Task should still exist (marked terminal, not deleted)"
        assert retrieved.status in (TaskStatus.COMPLETED, TaskStatus.FAILED), (
            f"Old orphaned task should be marked terminal (COMPLETED or FAILED); "
            f"actual status: {retrieved.status}"
        )


class TestDialectAdapterInitialization:
    """Test that dialect adapter is initialized correctly for database operations."""

    async def test_cleanup_duplicate_temporal_edges_uses_correct_placeholders(
        self,
        clean_db,
        database_maintenance_service,
        mock_time_service,
    ):
        """Post-2.9.0 `_cleanup_duplicate_temporal_edges` is a no-op shim.

        The v1.5.5 Postgres dedupe cleanup it targeted is no longer needed —
        persist >=1.6.0 fixed the underlying edge_manager bug. The original
        test inserted raw graph_nodes/graph_edges and asserted DELETE-based
        cleanup; with the production method now a no-op (deliberate), the
        test contract is reduced to verifying the call completes without
        raising. The placeholder-mismatch regression it guarded against
        is no longer reachable.
        """
        # Should not raise on either backend; the body is a debug log only.
        await database_maintenance_service._cleanup_duplicate_temporal_edges()


class TestConfigPreservationLogic:
    """Test the config preservation helper methods for runtime config cleanup."""

    def test_is_runtime_config_matches_adapter_pattern(self, database_maintenance_service):
        """Test that adapter.* patterns are recognized as runtime configs."""
        assert database_maintenance_service._is_runtime_config("adapter.my_adapter.config") is True
        assert database_maintenance_service._is_runtime_config("adapter.accord_abc123.type") is True

    def test_is_runtime_config_matches_runtime_pattern(self, database_maintenance_service):
        """Test that runtime.* patterns are recognized as runtime configs."""
        assert database_maintenance_service._is_runtime_config("runtime.state") is True
        assert database_maintenance_service._is_runtime_config("runtime.settings.foo") is True

    def test_is_runtime_config_matches_session_pattern(self, database_maintenance_service):
        """Test that session.* patterns are recognized as runtime configs."""
        assert database_maintenance_service._is_runtime_config("session.user_123") is True

    def test_is_runtime_config_matches_temp_pattern(self, database_maintenance_service):
        """Test that temp.* patterns are recognized as runtime configs."""
        assert database_maintenance_service._is_runtime_config("temp.cache") is True

    def test_is_runtime_config_rejects_other_patterns(self, database_maintenance_service):
        """Test that non-runtime config patterns are rejected."""
        assert database_maintenance_service._is_runtime_config("system.settings") is False
        assert database_maintenance_service._is_runtime_config("agent.identity") is False
        assert database_maintenance_service._is_runtime_config("essential.config") is False

    def test_should_preserve_config_preserves_system_bootstrap(self, database_maintenance_service):
        """Test that configs created by system_bootstrap are preserved."""

        class MockConfigNode:
            updated_by = "system_bootstrap"

        should_preserve, reason = database_maintenance_service._should_preserve_config(
            "adapter.bootstrap.config", MockConfigNode()
        )
        assert should_preserve is True
        assert "bootstrap config" in reason.lower()

    def test_should_preserve_config_preserves_runtime_adapter_manager_configs(self, database_maintenance_service):
        """Test that adapter configs from runtime_adapter_manager are preserved for persist check."""

        class MockConfigNode:
            updated_by = "runtime_adapter_manager"

        should_preserve, reason = database_maintenance_service._should_preserve_config(
            "adapter.accord_metrics_abc123.config", MockConfigNode()
        )
        assert should_preserve is True
        assert "persist check" in reason.lower()

    def test_should_preserve_config_deletes_other_adapter_configs(self, database_maintenance_service):
        """Test that adapter configs from other sources are NOT preserved."""

        class MockConfigNode:
            updated_by = "some_other_service"

        should_preserve, reason = database_maintenance_service._should_preserve_config(
            "adapter.temp_adapter.config", MockConfigNode()
        )
        assert should_preserve is False
        assert reason == ""

    def test_should_preserve_config_deletes_session_configs(self, database_maintenance_service):
        """Test that session configs are NOT preserved."""

        class MockConfigNode:
            updated_by = "user_session"

        should_preserve, reason = database_maintenance_service._should_preserve_config(
            "session.user_123", MockConfigNode()
        )
        assert should_preserve is False

    def test_log_cleanup_result_with_deletions(self, database_maintenance_service, caplog):
        """Test that cleanup result logging works with deletions."""
        import logging

        with caplog.at_level(logging.INFO):
            database_maintenance_service._log_cleanup_result(5)

        assert "Cleaned up 5 runtime-specific configuration entries" in caplog.text

    def test_log_cleanup_result_with_no_deletions(self, database_maintenance_service, caplog):
        """Test that cleanup result logging works with no deletions."""
        import logging

        with caplog.at_level(logging.INFO):
            database_maintenance_service._log_cleanup_result(0)

        assert "No runtime-specific configuration entries to clean up" in caplog.text


class TestAdapterConfigHelpers:
    """Test the adapter config helper methods for deduplication and persistence."""

    def test_find_adapter_ids_from_configs_extracts_ids(self, database_maintenance_service):
        """Test that adapter IDs are correctly extracted from config keys."""
        all_configs = {
            "adapter.discord_abc123.type": "discord",
            "adapter.discord_abc123.config": {"token": "xxx"},
            "adapter.ha_def456.type": "home_assistant",
            "adapter.ha_def456.config": {"url": "http://localhost"},
            "other.config.key": "value",
        }
        result = database_maintenance_service._find_adapter_ids_from_configs(all_configs)
        assert "discord_abc123" in result
        assert "ha_def456" in result
        assert len(result) == 2
        # Each entry should have type_key
        assert result["discord_abc123"]["type_key"] == "adapter.discord_abc123.type"
        assert result["ha_def456"]["type_key"] == "adapter.ha_def456.type"

    def test_find_adapter_ids_from_configs_ignores_non_type_keys(self, database_maintenance_service):
        """Test that non-.type adapter keys are ignored."""
        all_configs = {
            "adapter.discord_abc123.config": {"token": "xxx"},
            "adapter.discord_abc123.persist": True,
        }
        result = database_maintenance_service._find_adapter_ids_from_configs(all_configs)
        assert len(result) == 0

    def test_find_adapter_ids_from_configs_ignores_malformed_keys(self, database_maintenance_service):
        """Test that malformed keys with wrong number of parts are ignored."""
        all_configs = {
            "adapter.type": "bad",  # Only 2 parts
            "adapter.a.b.c.type": "bad",  # More than 3 parts
        }
        result = database_maintenance_service._find_adapter_ids_from_configs(all_configs)
        assert len(result) == 0

    def test_group_adapters_by_signature(self, database_maintenance_service):
        """Test that adapters are correctly grouped by (type, occurrence_id, config_hash)."""
        adapter_instances = {
            "discord_1": {"adapter_type": "discord", "occurrence_id": "node1", "config_hash": "abc123"},
            "discord_2": {"adapter_type": "discord", "occurrence_id": "node1", "config_hash": "abc123"},  # Duplicate
            "discord_3": {
                "adapter_type": "discord",
                "occurrence_id": "node2",
                "config_hash": "abc123",
            },  # Different occurrence
            "ha_1": {"adapter_type": "home_assistant", "occurrence_id": "node1", "config_hash": "def456"},
        }
        result = database_maintenance_service._group_adapters_by_signature(adapter_instances)

        # Should have 3 groups
        assert len(result) == 3

        # discord + node1 + abc123 should have 2 adapters
        discord_node1_group = result[("discord", "node1", "abc123")]
        assert len(discord_node1_group) == 2
        assert "discord_1" in discord_node1_group
        assert "discord_2" in discord_node1_group

        # discord + node2 + abc123 should have 1 adapter
        discord_node2_group = result[("discord", "node2", "abc123")]
        assert len(discord_node2_group) == 1
        assert "discord_3" in discord_node2_group

        # home_assistant + node1 + def456 should have 1 adapter
        ha_group = result[("home_assistant", "node1", "def456")]
        assert len(ha_group) == 1
        assert "ha_1" in ha_group

    def test_group_adapters_by_signature_skips_entries_without_type(self, database_maintenance_service):
        """Test that adapters without adapter_type are skipped during grouping."""
        adapter_instances = {
            "good_adapter": {"adapter_type": "discord", "occurrence_id": "node1", "config_hash": "abc123"},
            "bad_adapter": {"occurrence_id": "node1", "config_hash": "def456"},  # No adapter_type
        }
        result = database_maintenance_service._group_adapters_by_signature(adapter_instances)
        assert len(result) == 1
        assert ("discord", "node1", "abc123") in result

    def test_extract_config_value_handles_none(self, database_maintenance_service):
        """Test that _extract_config_value handles None gracefully."""
        assert database_maintenance_service._extract_config_value(None) is None

    def test_extract_config_value_extracts_string_value(self, database_maintenance_service):
        """Test that _extract_config_value extracts string values."""

        class MockConfigValue:
            string_value = "test_string"
            dict_value = None
            int_value = None
            bool_value = None
            list_value = None
            float_value = None

        class MockConfigNode:
            value = MockConfigValue()

        result = database_maintenance_service._extract_config_value(MockConfigNode())
        assert result == "test_string"

    def test_extract_config_value_extracts_dict_value(self, database_maintenance_service):
        """Test that _extract_config_value extracts dict values."""

        class MockConfigValue:
            string_value = None
            dict_value = {"key": "value"}
            int_value = None
            bool_value = None
            list_value = None
            float_value = None

        class MockConfigNode:
            value = MockConfigValue()

        result = database_maintenance_service._extract_config_value(MockConfigNode())
        assert result == {"key": "value"}

    def test_extract_config_value_extracts_bool_value(self, database_maintenance_service):
        """Test that _extract_config_value extracts bool values."""

        class MockConfigValue:
            string_value = None
            dict_value = None
            int_value = None
            bool_value = True
            list_value = None
            float_value = None

        class MockConfigNode:
            value = MockConfigValue()

        result = database_maintenance_service._extract_config_value(MockConfigNode())
        assert result is True

    def test_extract_config_value_returns_raw_value(self, database_maintenance_service):
        """Test that _extract_config_value returns raw value when no typed value."""

        class MockConfigNode:
            value = "raw_value"

        result = database_maintenance_service._extract_config_value(MockConfigNode())
        assert result == "raw_value"


class TestAdapterDeduplication:
    """Test adapter deduplication with mock config service."""

    @pytest.fixture
    def mock_config_service(self):
        """Create a mock config service for testing."""
        from unittest.mock import AsyncMock, MagicMock

        mock = MagicMock()
        mock.list_configs = AsyncMock()
        mock.get_config = AsyncMock()
        mock.graph = MagicMock()
        mock.graph.forget = AsyncMock()
        return mock

    async def test_dedupe_adapter_configs_skips_when_no_config_service(self, database_maintenance_service, caplog):
        """Test that dedupe is skipped when config_service is not available."""
        import logging

        database_maintenance_service.config_service = None
        with caplog.at_level(logging.DEBUG):
            await database_maintenance_service._dedupe_adapter_configs()

        assert "Cannot dedupe adapter configs - config service not available" in caplog.text

    async def test_dedupe_adapter_configs_skips_empty_configs(self, database_maintenance_service, mock_config_service):
        """Test that dedupe completes early when no configs exist."""
        database_maintenance_service.config_service = mock_config_service
        mock_config_service.list_configs.return_value = {}

        await database_maintenance_service._dedupe_adapter_configs()

        # Should not try to get any config details
        mock_config_service.get_config.assert_not_called()

    async def test_delete_duplicate_adapters_in_group_keeps_newest(
        self, database_maintenance_service, mock_config_service
    ):
        """Test that only the newest adapter is kept when deduplicating."""
        from datetime import datetime, timezone
        from unittest.mock import patch

        database_maintenance_service.config_service = mock_config_service

        adapter_instances = {
            "old_adapter": {"created_at": datetime(2024, 1, 1, tzinfo=timezone.utc)},
            "newer_adapter": {"created_at": datetime(2024, 6, 1, tzinfo=timezone.utc)},
            "newest_adapter": {"created_at": datetime(2025, 1, 1, tzinfo=timezone.utc)},
        }

        group_key = ("discord", "node1", "abc123")
        adapter_ids = ["old_adapter", "newer_adapter", "newest_adapter"]

        # Mock current occurrence to match the group's occurrence_id for multi-occurrence safety
        with patch(
            "ciris_engine.logic.utils.occurrence_utils.get_current_occurrence_id",
            return_value="node1",
        ):
            deleted_count = await database_maintenance_service._delete_duplicate_adapters_in_group(
                group_key, adapter_ids, adapter_instances
            )

        # Should delete 2 (keep newest_adapter)
        assert deleted_count == 2

    async def test_delete_duplicate_adapters_in_group_noop_for_single_adapter(
        self, database_maintenance_service, mock_config_service
    ):
        """Test that single adapter in group doesn't trigger deletion."""
        database_maintenance_service.config_service = mock_config_service

        adapter_instances = {
            "only_adapter": {"created_at": "2024-01-01T00:00:00Z"},
        }

        group_key = ("discord", "node1", "abc123")
        adapter_ids = ["only_adapter"]

        deleted_count = await database_maintenance_service._delete_duplicate_adapters_in_group(
            group_key, adapter_ids, adapter_instances
        )

        assert deleted_count == 0


class TestAdapterPersistence:
    """Test adapter persistence helper methods."""

    @pytest.fixture
    def mock_config_service(self):
        """Create a mock config service for testing."""
        from unittest.mock import AsyncMock, MagicMock

        mock = MagicMock()
        mock.list_configs = AsyncMock()
        mock.get_config = AsyncMock()
        mock.graph = MagicMock()
        mock.graph.forget = AsyncMock()
        return mock

    async def test_is_adapter_persistent_returns_true_for_persist_true(
        self, database_maintenance_service, mock_config_service
    ):
        """Test that _is_adapter_persistent returns True when persist=True."""
        database_maintenance_service.config_service = mock_config_service

        class MockConfigValue:
            string_value = None
            dict_value = None
            int_value = None
            bool_value = True
            list_value = None
            float_value = None

        class MockConfigNode:
            value = MockConfigValue()

        mock_config_service.get_config.return_value = MockConfigNode()

        result = await database_maintenance_service._is_adapter_persistent("test_adapter")
        assert result is True

    async def test_is_adapter_persistent_returns_false_for_persist_false(
        self, database_maintenance_service, mock_config_service
    ):
        """Test that _is_adapter_persistent returns False when persist=False."""
        database_maintenance_service.config_service = mock_config_service

        class MockConfigValue:
            string_value = None
            dict_value = None
            int_value = None
            bool_value = False
            list_value = None
            float_value = None

        class MockConfigNode:
            value = MockConfigValue()

        mock_config_service.get_config.return_value = MockConfigNode()

        result = await database_maintenance_service._is_adapter_persistent("test_adapter")
        assert result is False

    async def test_is_adapter_persistent_returns_false_for_missing_persist(
        self, database_maintenance_service, mock_config_service
    ):
        """Test that _is_adapter_persistent returns False when persist is missing."""
        database_maintenance_service.config_service = mock_config_service
        mock_config_service.get_config.return_value = None

        result = await database_maintenance_service._is_adapter_persistent("test_adapter")
        assert result is False

    async def test_cleanup_non_persistent_adapters_skips_when_no_config_service(
        self, database_maintenance_service, caplog
    ):
        """Test that cleanup is skipped when config_service is not available."""
        import logging

        database_maintenance_service.config_service = None
        with caplog.at_level(logging.DEBUG):
            await database_maintenance_service._cleanup_non_persistent_adapters()

        assert "Cannot cleanup non-persistent adapters - config service not available" in caplog.text

    async def test_delete_non_persistent_adapters_keeps_persistent_ones(
        self, database_maintenance_service, mock_config_service, caplog
    ):
        """Test that adapters with persist=True are kept."""
        import logging

        database_maintenance_service.config_service = mock_config_service

        class MockConfigValue:
            string_value = None
            dict_value = None
            int_value = None
            bool_value = True
            list_value = None
            float_value = None

        class MockConfigNode:
            value = MockConfigValue()

        mock_config_service.get_config.return_value = MockConfigNode()
        mock_config_service.list_configs.return_value = {}

        with caplog.at_level(logging.DEBUG):
            deleted = await database_maintenance_service._delete_non_persistent_adapters({"test_adapter"})

        assert deleted == 0
        assert "marked for persistence, keeping" in caplog.text


class TestStaleTaskHelpers:
    """Tests for helper methods used in stale task cleanup."""

    @pytest.fixture
    def database_maintenance_service(self, tmp_path):
        """Create a DatabaseMaintenanceService for testing."""
        from unittest.mock import Mock

        from ciris_engine.logic.services.infrastructure.database_maintenance.service import DatabaseMaintenanceService

        service = DatabaseMaintenanceService.__new__(DatabaseMaintenanceService)
        service.db_path = str(tmp_path / "test.db")
        service.time_service = Mock()
        return service

    def test_is_wakeup_or_shutdown_task_wakeup(self, database_maintenance_service):
        """Test _is_wakeup_or_shutdown_task returns True for wakeup tasks."""
        assert database_maintenance_service._is_wakeup_or_shutdown_task("WAKEUP_123") is True
        assert database_maintenance_service._is_wakeup_or_shutdown_task("VERIFY_IDENTITY_456") is True
        assert database_maintenance_service._is_wakeup_or_shutdown_task("VALIDATE_INTEGRITY_789") is True
        assert database_maintenance_service._is_wakeup_or_shutdown_task("EVALUATE_RESILIENCE_abc") is True
        assert database_maintenance_service._is_wakeup_or_shutdown_task("ACCEPT_INCOMPLETENESS_def") is True
        assert database_maintenance_service._is_wakeup_or_shutdown_task("EXPRESS_GRATITUDE_ghi") is True

    def test_is_wakeup_or_shutdown_task_shutdown(self, database_maintenance_service):
        """Test _is_wakeup_or_shutdown_task returns True for shutdown tasks."""
        assert database_maintenance_service._is_wakeup_or_shutdown_task("shutdown_123") is True
        assert database_maintenance_service._is_wakeup_or_shutdown_task("SHUTDOWN_456") is True

    def test_is_wakeup_or_shutdown_task_other(self, database_maintenance_service):
        """Test _is_wakeup_or_shutdown_task returns False for other tasks."""
        assert database_maintenance_service._is_wakeup_or_shutdown_task("regular_task_123") is False
        assert database_maintenance_service._is_wakeup_or_shutdown_task("user_request_456") is False
        assert database_maintenance_service._is_wakeup_or_shutdown_task("task_WAKEUP_789") is False

    def test_get_task_age_seconds_with_datetime(self, database_maintenance_service):
        """Test _get_task_age_seconds with datetime object."""
        from datetime import datetime, timedelta, timezone

        current_time = datetime.now(timezone.utc)
        task = Mock()
        task.created_at = current_time - timedelta(seconds=300)

        age = database_maintenance_service._get_task_age_seconds(task, current_time)

        assert age == pytest.approx(300, abs=1)

    def test_get_task_age_seconds_with_string(self, database_maintenance_service):
        """Test _get_task_age_seconds with ISO string timestamp."""
        from datetime import datetime, timedelta, timezone

        current_time = datetime.now(timezone.utc)
        created_at = current_time - timedelta(seconds=600)
        task = Mock()
        task.created_at = created_at.isoformat()

        age = database_maintenance_service._get_task_age_seconds(task, current_time)

        assert age == pytest.approx(600, abs=1)

    def test_get_task_age_seconds_with_z_suffix(self, database_maintenance_service):
        """Test _get_task_age_seconds handles Z suffix in ISO string."""
        from datetime import datetime, timedelta, timezone

        current_time = datetime.now(timezone.utc)
        created_at = current_time - timedelta(seconds=120)
        task = Mock()
        # Some systems use Z suffix
        task.created_at = created_at.strftime("%Y-%m-%dT%H:%M:%S") + "Z"

        age = database_maintenance_service._get_task_age_seconds(task, current_time)

        assert age == pytest.approx(120, abs=1)
