"""
Tests for WorkProcessor - Ticket Discovery and Two-Phase Claiming

Tests cover:
- Phase 1: Atomic claiming of PENDING tickets with __shared__
- Phase 2: Continuation tasks for ASSIGNED/IN_PROGRESS tickets
- Status-based task generation control (BLOCKED/DEFERRED)
- Multi-occurrence coordination
- Deferral handling
- Error scenarios
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.persistence.models.tasks import add_task, get_all_tasks
from ciris_engine.logic.persistence.models.tickets import create_ticket, get_ticket, update_ticket_status
from ciris_engine.logic.processors.states.work_processor import WorkProcessor
from ciris_engine.schemas.runtime.enums import TaskStatus


class TestWorkProcessorPhase1Claiming:
    """Test Phase 1: Atomic claiming of PENDING tickets."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        migrations_dir = (
            Path(__file__).parent.parent.parent.parent.parent.parent
            / "ciris_engine"
            / "logic"
            / "persistence"
            / "migrations"
            / "sqlite"
        )

        conn = sqlite3.connect(db_path)
        for i in range(1, 11):  # Include migration 010 for images_json column
            migration_files = list(migrations_dir.glob(f"{i:03d}_*.sql"))
            if migration_files:
                with open(migration_files[0], "r") as f:
                    sql = f.read()
                    # Workaround for pre-existing view bug in migration 001
                    if i == 1:
                        sql = sql.replace("t.task_id as associated_task_id", "t.thought_id as associated_thought_id")
                    conn.executescript(sql)

        conn.commit()
        conn.close()

        yield db_path

        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def mock_config(self, temp_db_path):
        """Create mock config."""
        config = Mock()
        config.db_path = temp_db_path
        config.agent_occurrence_id = "occurrence-1"
        return config

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2025, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.fixture
    def work_processor(self, mock_config, mock_time_service):
        """Create WorkProcessor instance."""
        # Create mock services
        mock_services = Mock()
        mock_services.time_service = mock_time_service

        # Create mock thought processor and action dispatcher
        mock_thought_processor = Mock()
        mock_action_dispatcher = Mock()

        processor = WorkProcessor(
            config_accessor=mock_config,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            agent_occurrence_id="occurrence-1",
        )
        return processor

    @pytest.mark.asyncio
    async def test_claim_single_pending_ticket(self, work_processor, temp_db_path):
        """TC-WP001: Verify occurrence can claim PENDING ticket with __shared__."""
        # Create PENDING ticket with __shared__
        ticket_id = "PENDING-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        # Execute discovery
        tasks_created = await work_processor._discover_incomplete_tickets()

        # Verify
        assert tasks_created == 1, "Should create one task"

        # Verify ticket claimed
        ticket = get_ticket(ticket_id, db_path=temp_db_path)
        assert ticket["status"] == "assigned"
        assert ticket["agent_occurrence_id"] == "occurrence-1"

        # Verify task created
        tasks = get_all_tasks(occurrence_id="occurrence-1", db_path=temp_db_path)
        assert len(tasks) == 1
        assert tasks[0].task_id.startswith(f"TICKET-{ticket_id}-")
        assert tasks[0].agent_occurrence_id == "occurrence-1"

    @pytest.mark.asyncio
    async def test_atomic_claiming_race_condition(self, mock_config, mock_time_service, temp_db_path):
        """TC-WP002: Verify only ONE occurrence claims shared ticket."""
        # Create PENDING ticket
        ticket_id = "RACE-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        # Create two processors
        mock_services1 = Mock()
        mock_services1.time_service = mock_time_service
        processor1 = WorkProcessor(
            config_accessor=mock_config,
            thought_processor=Mock(),
            action_dispatcher=Mock(),
            services=mock_services1,
            agent_occurrence_id="occurrence-1",
        )

        config2 = Mock()
        config2.db_path = temp_db_path
        config2.agent_occurrence_id = "occurrence-2"

        mock_services2 = Mock()
        mock_services2.time_service = mock_time_service
        processor2 = WorkProcessor(
            config_accessor=config2,
            thought_processor=Mock(),
            action_dispatcher=Mock(),
            services=mock_services2,
            agent_occurrence_id="occurrence-2",
        )

        # Both try to claim
        tasks1 = await processor1._discover_incomplete_tickets()
        tasks2 = await processor2._discover_incomplete_tickets()

        # Only one should succeed
        assert (tasks1 + tasks2) == 1, "Only one occurrence should create task"

        # Verify only one task exists (check both occurrences)
        tasks1_final = get_all_tasks(occurrence_id="occurrence-1", db_path=temp_db_path)
        tasks2_final = get_all_tasks(occurrence_id="occurrence-2", db_path=temp_db_path)
        assert len(tasks1_final) + len(tasks2_final) == 1

    @pytest.mark.asyncio
    async def test_skip_non_shared_pending_tickets(self, work_processor, temp_db_path):
        """TC-WP003: Verify occurrence skips PENDING tickets already assigned."""
        # Create PENDING ticket already assigned to different occurrence
        ticket_id = "NON-SHARED-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )
        # Assign to different occurrence
        update_ticket_status(ticket_id, "pending", agent_occurrence_id="occurrence-2", db_path=temp_db_path)

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0, "Should not claim ticket assigned to different occurrence"

    @pytest.mark.asyncio
    async def test_skip_blocked_tickets(self, work_processor, temp_db_path):
        """TC-WP004: Verify PENDING+BLOCKED tickets not claimed."""
        ticket_id = "BLOCKED-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="blocked",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0, "Should not claim BLOCKED ticket"

    @pytest.mark.asyncio
    async def test_skip_deferred_tickets(self, work_processor, temp_db_path):
        """TC-WP005: Verify PENDING+DEFERRED tickets not claimed."""
        ticket_id = "DEFERRED-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="deferred",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0, "Should not claim DEFERRED ticket"


class TestWorkProcessorPhase2Continuation:
    """Test Phase 2: Continuation tasks for ASSIGNED/IN_PROGRESS tickets."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        migrations_dir = (
            Path(__file__).parent.parent.parent.parent.parent.parent
            / "ciris_engine"
            / "logic"
            / "persistence"
            / "migrations"
            / "sqlite"
        )

        conn = sqlite3.connect(db_path)
        for i in range(1, 11):  # Include migration 010 for images_json column
            migration_files = list(migrations_dir.glob(f"{i:03d}_*.sql"))
            if migration_files:
                with open(migration_files[0], "r") as f:
                    sql = f.read()
                    # Workaround for pre-existing view bug in migration 001
                    if i == 1:
                        sql = sql.replace("t.task_id as associated_task_id", "t.thought_id as associated_thought_id")
                    conn.executescript(sql)

        conn.commit()
        conn.close()

        yield db_path

        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def work_processor(self, temp_db_path):
        """Create WorkProcessor."""
        config = Mock()
        config.db_path = temp_db_path
        config.agent_occurrence_id = "occurrence-1"

        time_service = Mock()
        time_service.now.return_value = datetime(2025, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

        # Create mock services
        mock_services = Mock()
        mock_services.time_service = time_service

        # Create mock thought processor and action dispatcher
        mock_thought_processor = Mock()
        mock_action_dispatcher = Mock()

        processor = WorkProcessor(
            config_accessor=config,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            agent_occurrence_id="occurrence-1",
        )
        return processor

    @pytest.mark.asyncio
    async def test_create_continuation_task_for_assigned(self, work_processor, temp_db_path):
        """TC-WP008: Verify continuation task created for ASSIGNED ticket."""
        ticket_id = "ASSIGNED-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="assigned",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            agent_occurrence_id="occurrence-1",  # Already assigned to this occurrence
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 1

        tasks = get_all_tasks(occurrence_id="occurrence-1", db_path=temp_db_path)
        assert len(tasks) == 1
        assert tasks[0].task_id.startswith(f"TICKET-{ticket_id}-")
        assert tasks[0].agent_occurrence_id == "occurrence-1"

    @pytest.mark.asyncio
    async def test_create_continuation_task_for_in_progress(self, work_processor, temp_db_path):
        """TC-WP009: Verify continuation task created for IN_PROGRESS ticket."""
        ticket_id = "IN-PROGRESS-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            agent_occurrence_id="occurrence-1",  # Already assigned to this occurrence
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 1

    @pytest.mark.asyncio
    async def test_skip_different_occurrence(self, work_processor, temp_db_path):
        """TC-WP010: Verify occurrence only processes its own tickets."""
        ticket_id = "OTHER-OCC-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="assigned",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            agent_occurrence_id="occurrence-2",  # Already assigned to this occurrence
            db_path=temp_db_path,
        )
        # Assign to different occurrence
        update_ticket_status(ticket_id, "assigned", agent_occurrence_id="occurrence-2", db_path=temp_db_path)

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0, "Should not process tickets from different occurrence"

    @pytest.mark.asyncio
    async def test_skip_blocked_tickets_phase2(self, work_processor, temp_db_path):
        """TC-WP011: Verify BLOCKED tickets don't generate continuation tasks."""
        ticket_id = "BLOCKED-PHASE2-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="blocked",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0

    @pytest.mark.asyncio
    async def test_skip_deferred_tickets_phase2(self, work_processor, temp_db_path):
        """TC-WP012: Verify DEFERRED tickets don't generate continuation tasks."""
        ticket_id = "DEFERRED-PHASE2-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="deferred",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0

    @pytest.mark.asyncio
    async def test_skip_tickets_with_active_tasks(self, work_processor, temp_db_path):
        """TC-WP013: Verify no duplicate tasks created."""
        ticket_id = "HAS-TASK-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            agent_occurrence_id="occurrence-1",  # Already assigned to this occurrence
            db_path=temp_db_path,
        )

        # Create existing ACTIVE task for ticket
        from ciris_engine.schemas.runtime.models import Task

        now = datetime.now(timezone.utc).isoformat()
        existing_task = Task(
            task_id=f"TICKET-{ticket_id}-EXISTING",
            channel_id="test",
            agent_occurrence_id="occurrence-1",
            description="Existing task",
            status=TaskStatus.ACTIVE,
            priority=5,
            created_at=now,
            updated_at=now,
        )
        add_task(existing_task, db_path=temp_db_path)

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0, "Should not create duplicate task"

    @pytest.mark.asyncio
    async def test_respect_deferred_until_not_expired(self, work_processor, temp_db_path):
        """TC-WP014: Verify tickets with future deferred_until skip task creation."""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

        ticket_id = "DEFERRED-FUTURE-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"deferred_until": future_time},
            agent_occurrence_id="occurrence-1",
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0, "Should not create task for future-deferred ticket"

    @pytest.mark.asyncio
    async def test_deferred_until_expired_creates_task(self, work_processor, temp_db_path):
        """TC-WP015: Verify expired deferred_until allows task creation."""
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()

        ticket_id = "DEFERRED-EXPIRED-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"deferred_until": past_time},
            agent_occurrence_id="occurrence-1",
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 1, "Should create task when deferral expired"

    @pytest.mark.asyncio
    async def test_skip_awaiting_human_response(self, work_processor, temp_db_path):
        """TC-WP016: Verify awaiting_human_response prevents task creation."""
        ticket_id = "AWAITING-HUMAN-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"awaiting_human_response": True},
            agent_occurrence_id="occurrence-1",
            db_path=temp_db_path,
        )

        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 0

    @pytest.mark.asyncio
    async def test_invalid_deferred_until_format(self, work_processor, temp_db_path):
        """TC-WP017: Verify graceful handling of invalid timestamp."""
        ticket_id = "INVALID-DEFER-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="test@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"deferred_until": "invalid-date-format"},
            agent_occurrence_id="occurrence-1",
            db_path=temp_db_path,
        )

        # Should not crash, should continue and create task
        tasks_created = await work_processor._discover_incomplete_tickets()

        assert tasks_created == 1, "Should handle invalid format gracefully and create task"


class TestWorkProcessorTwoPhaseIntegration:
    """Test both phases working together."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent
        migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "sqlite"

        conn = sqlite3.connect(db_path)
        for i in range(1, 11):  # Include migration 010 for images_json column
            migration_files = list(migrations_dir.glob(f"{i:03d}_*.sql"))
            if migration_files:
                with open(migration_files[0], "r") as f:
                    sql = f.read()
                    # Workaround for pre-existing view bug in migration 001
                    if i == 1:
                        sql = sql.replace("t.task_id as associated_task_id", "t.thought_id as associated_thought_id")
                    conn.executescript(sql)

        conn.commit()
        conn.close()

        yield db_path

        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_two_phase_combined_multiple_tickets(self, temp_db_path):
        """TC-WP018: Verify both phases work together with multiple ticket types."""
        # Setup
        config = Mock()
        config.db_path = temp_db_path
        config.agent_occurrence_id = "occurrence-1"

        time_service = Mock()
        time_service.now.return_value = datetime(2025, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

        # Create mock services
        mock_services = Mock()
        mock_services.time_service = time_service

        # Create mock thought processor and action dispatcher
        mock_thought_processor = Mock()
        mock_action_dispatcher = Mock()

        processor = WorkProcessor(
            config_accessor=config,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            agent_occurrence_id=config.agent_occurrence_id,
        )
        processor.agent_occurrence_id = "occurrence-1"

        # Create test tickets
        # Ticket A: PENDING with __shared__ (should be claimed)
        ticket_a = "TICKET-A"
        create_ticket(
            ticket_id=ticket_a,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="a@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        # Ticket B: ASSIGNED to occurrence-1 (should get continuation)
        ticket_b = "TICKET-B"
        create_ticket(
            ticket_id=ticket_b,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="assigned",
            email="b@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            agent_occurrence_id="occurrence-1",  # Already assigned to this occurrence
            db_path=temp_db_path,
        )
        update_ticket_status(ticket_b, "assigned", agent_occurrence_id="occurrence-1", db_path=temp_db_path)

        # Ticket C: IN_PROGRESS for occurrence-1 (should get continuation)
        ticket_c = "TICKET-C"
        create_ticket(
            ticket_id=ticket_c,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="c@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            agent_occurrence_id="occurrence-1",  # Already assigned to this occurrence
            db_path=temp_db_path,
        )
        update_ticket_status(ticket_c, "in_progress", agent_occurrence_id="occurrence-1", db_path=temp_db_path)

        # Ticket D: BLOCKED (should be skipped)
        ticket_d = create_ticket(
            ticket_id="TICKET-D",
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="blocked",
            email="d@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        # Execute
        tasks_created = await processor._discover_incomplete_tickets()

        # Verify
        assert tasks_created == 3, "Should create 3 tasks (A claimed, B+C continued)"

        # Verify Ticket A was claimed
        ticket_a_updated = get_ticket("TICKET-A", db_path=temp_db_path)
        assert ticket_a_updated["status"] == "assigned"
        assert ticket_a_updated["agent_occurrence_id"] == "occurrence-1"

        # Verify tasks
        tasks = get_all_tasks(occurrence_id="occurrence-1", db_path=temp_db_path)
        # We should have 3 tasks total (1 from TICKET-A claim, 2 from TICKET-B/C continuation)
        assert len(tasks) == 3

        # Check that we have tasks for the right tickets
        task_ids = [t.task_id for t in tasks]
        assert any("TICKET-A" in tid for tid in task_ids), "Should have task for TICKET-A"
        assert any("TICKET-B" in tid for tid in task_ids), "Should have task for TICKET-B"
        assert any("TICKET-C" in tid for tid in task_ids), "Should have task for TICKET-C"
        assert not any("TICKET-D" in tid for tid in task_ids), "Should not have task for TICKET-D"

    @pytest.mark.asyncio
    async def test_task_context_structure(self, temp_db_path):
        """TC-WP019: Verify seed/continuation tasks have correct context."""
        config = Mock()
        config.db_path = temp_db_path
        config.agent_occurrence_id = "occurrence-1"

        time_service = Mock()
        time_service.now.return_value = datetime.now(timezone.utc)

        # Create mock services
        mock_services = Mock()
        mock_services.time_service = time_service

        # Create mock thought processor and action dispatcher
        mock_thought_processor = Mock()
        mock_action_dispatcher = Mock()

        processor = WorkProcessor(
            config_accessor=config,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            agent_occurrence_id=config.agent_occurrence_id,
        )
        processor.agent_occurrence_id = "occurrence-1"

        # Create ticket
        ticket_id = "CONTEXT-TEST-001"

        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="context@example.com",
            user_identifier="user123",
            priority=8,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            metadata={"test_meta": "value"},
            db_path=temp_db_path,
        )

        await processor._discover_incomplete_tickets()

        # Verify task created
        tasks = get_all_tasks(occurrence_id="occurrence-1", db_path=temp_db_path)
        assert len(tasks) == 1

        task = tasks[0]
        # Task context is stored in database but filtered by map_row_to_task to only include TaskContext fields
        # We can verify the task was created correctly by checking task fields
        assert task.task_id.startswith(f"TICKET-{ticket_id}-")
        assert task.agent_occurrence_id == "occurrence-1"
        assert task.priority == 8
        assert "DSAR_ACCESS" in task.description

    @pytest.mark.asyncio
    async def test_error_handling_exception_during_discovery(self, temp_db_path):
        """TC-WP020: Verify exceptions logged and don't crash processor."""
        config = Mock()
        config.db_path = temp_db_path
        config.agent_occurrence_id = "occurrence-1"

        mock_services = Mock()
        mock_services.time_service = Mock()
        mock_services.time_service.now.return_value = datetime(2025, 11, 7, 12, 0, 0, tzinfo=timezone.utc)

        processor = WorkProcessor(
            config_accessor=config,
            thought_processor=Mock(),
            action_dispatcher=Mock(),
            services=mock_services,
            agent_occurrence_id="occurrence-1",
        )

        # Mock list_tickets to raise exception
        with patch("ciris_engine.logic.persistence.models.tickets.list_tickets", side_effect=Exception("Test error")):
            tasks_created = await processor._discover_incomplete_tickets()

        # Should return 0 and not crash
        assert tasks_created == 0
