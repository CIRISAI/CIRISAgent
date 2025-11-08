"""
Tests for Tickets Persistence Model

Tests cover:
- update_ticket_status with new parameters
- Status updates with agent_occurrence_id
- Dynamic SQL construction
- All 8 status values
- Terminal status handling (completed_at)
- Error handling
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.persistence.models.tickets import create_ticket, get_ticket, update_ticket_status


class TestUpdateTicketStatus:
    """Test update_ticket_status function with status system enhancements."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        # Apply migrations to create schema
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent
        migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "sqlite"

        conn = sqlite3.connect(db_path)
        for i in range(1, 10):  # Apply migrations 001-009
            migration_files = list(migrations_dir.glob(f"{i:03d}_*.sql"))
            if migration_files:
                with open(migration_files[0], "r") as f:
                    sql = f.read()
                    # Workaround for pre-existing view bug: fix active_scheduled_tasks view
                    if i == 1:
                        sql = sql.replace("t.task_id as associated_task_id", "t.thought_id as associated_thought_id")
                    conn.executescript(sql)

        conn.commit()
        conn.close()

        yield db_path

        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def test_ticket_id(self, temp_db_path):
        """Create a test ticket and return its ID."""
        ticket_id = "TEST-TICKET-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="test@example.com",
            user_identifier="user123",
            priority=5,
            submitted_at=datetime.now(timezone.utc).isoformat(),
            deadline=None,
            metadata={"test": True},
            notes="Test ticket",
            automated=False,
            db_path=temp_db_path,
        )
        return ticket_id

    def test_update_status_only(self, temp_db_path, test_ticket_id):
        """TC-TP001: Verify updating status alone."""
        # Update status
        result = update_ticket_status(test_ticket_id, "in_progress", db_path=temp_db_path)

        assert result is True, "Update should succeed"

        # Verify update
        ticket = get_ticket(test_ticket_id, db_path=temp_db_path)
        assert ticket["status"] == "in_progress"
        assert ticket["completed_at"] is None, "Non-terminal status should not set completed_at"

        # Verify last_updated changed
        assert ticket["last_updated"] is not None

    def test_update_status_with_notes(self, temp_db_path, test_ticket_id):
        """TC-TP002: Verify status update with notes."""
        result = update_ticket_status(
            test_ticket_id, "blocked", notes="Waiting for legal approval", db_path=temp_db_path
        )

        assert result is True

        ticket = get_ticket(test_ticket_id, db_path=temp_db_path)
        assert ticket["status"] == "blocked"
        assert ticket["notes"] == "Waiting for legal approval"

    def test_update_status_with_agent_occurrence_id(self, temp_db_path, test_ticket_id):
        """TC-TP003: Verify updating agent_occurrence_id during status change."""
        result = update_ticket_status(
            test_ticket_id, "assigned", agent_occurrence_id="occurrence-1", db_path=temp_db_path
        )

        assert result is True

        ticket = get_ticket(test_ticket_id, db_path=temp_db_path)
        assert ticket["status"] == "assigned"
        assert ticket["agent_occurrence_id"] == "occurrence-1"

    def test_update_all_parameters(self, temp_db_path, test_ticket_id):
        """TC-TP004: Verify updating status + notes + occurrence_id."""
        result = update_ticket_status(
            test_ticket_id,
            "assigned",
            notes="Claimed by occurrence",
            agent_occurrence_id="occurrence-2",
            db_path=temp_db_path,
        )

        assert result is True

        ticket = get_ticket(test_ticket_id, db_path=temp_db_path)
        assert ticket["status"] == "assigned"
        assert ticket["notes"] == "Claimed by occurrence"
        assert ticket["agent_occurrence_id"] == "occurrence-2"

    def test_terminal_status_sets_completed_at(self, temp_db_path):
        """TC-TP005: Verify completed_at set for terminal statuses."""
        # Create three tickets
        ticket_ids = []
        for i, status in enumerate(["completed", "failed", "cancelled"]):
            ticket_id = f"TEST-TERMINAL-{i}"
            create_ticket(
                ticket_id=ticket_id,
                sop="DSAR_ACCESS",
                ticket_type="dsar",
                status="in_progress",  # Start non-terminal
                email="test@example.com",
                submitted_at=datetime.now(timezone.utc).isoformat(),
                db_path=temp_db_path,
            )
            ticket_ids.append((ticket_id, status))

        # Update to terminal statuses
        for ticket_id, terminal_status in ticket_ids:
            update_ticket_status(ticket_id, terminal_status, db_path=temp_db_path)

        # Verify all have completed_at
        for ticket_id, _ in ticket_ids:
            ticket = get_ticket(ticket_id, db_path=temp_db_path)
            assert ticket["completed_at"] is not None, f"Ticket {ticket_id} should have completed_at"

    def test_non_terminal_leaves_completed_at_null(self, temp_db_path, test_ticket_id):
        """TC-TP006: Verify completed_at remains NULL for non-terminal statuses."""
        non_terminal_statuses = ["pending", "assigned", "in_progress", "blocked", "deferred"]

        for status in non_terminal_statuses:
            update_ticket_status(test_ticket_id, status, db_path=temp_db_path)
            ticket = get_ticket(test_ticket_id, db_path=temp_db_path)
            assert ticket["completed_at"] is None, f"Status {status} should not set completed_at"

    def test_nonexistent_ticket(self, temp_db_path):
        """TC-TP007: Verify error handling for missing ticket."""
        result = update_ticket_status("NONEXISTENT", "completed", db_path=temp_db_path)

        assert result is False, "Update of nonexistent ticket should fail"

    @patch("ciris_engine.logic.persistence.models.tickets.get_db_connection")
    def test_database_error(self, mock_get_db, temp_db_path, test_ticket_id):
        """TC-TP008: Verify exception handling."""
        # Mock to raise exception
        mock_get_db.side_effect = Exception("Database error")

        result = update_ticket_status(test_ticket_id, "completed", db_path=temp_db_path)

        assert result is False, "Should return False on exception"

    def test_all_8_status_values(self, temp_db_path, test_ticket_id):
        """TC-TP009: Verify all status values accepted."""
        all_statuses = ["pending", "assigned", "in_progress", "blocked", "deferred", "completed", "cancelled", "failed"]

        for status in all_statuses:
            result = update_ticket_status(test_ticket_id, status, db_path=temp_db_path)
            assert result is True, f"Status {status} should be accepted"

            ticket = get_ticket(test_ticket_id, db_path=temp_db_path)
            assert ticket["status"] == status

    def test_dynamic_sql_construction(self, temp_db_path, test_ticket_id):
        """TC-TP010: Verify SQL builds correctly based on parameters."""
        # Test various parameter combinations
        test_cases = [
            # (status, notes, agent_occurrence_id, expected_fields)
            ("assigned", None, None, ["status", "last_updated", "completed_at"]),
            ("blocked", "Test note", None, ["status", "last_updated", "completed_at", "notes"]),
            ("assigned", None, "occ-1", ["status", "last_updated", "completed_at", "agent_occurrence_id"]),
            (
                "in_progress",
                "Note",
                "occ-2",
                ["status", "last_updated", "completed_at", "notes", "agent_occurrence_id"],
            ),
        ]

        for status, notes, agent_occurrence_id, expected_fields in test_cases:
            # Update with specific parameters
            update_ticket_status(
                test_ticket_id, status, notes=notes, agent_occurrence_id=agent_occurrence_id, db_path=temp_db_path
            )

            # Verify update succeeded
            ticket = get_ticket(test_ticket_id, db_path=temp_db_path)
            assert ticket["status"] == status

            if notes:
                assert ticket["notes"] == notes
            if agent_occurrence_id:
                assert ticket["agent_occurrence_id"] == agent_occurrence_id


class TestTicketStatusTransitions:
    """Test valid status transition scenarios."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent
        migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "sqlite"

        conn = sqlite3.connect(db_path)
        for i in range(1, 10):
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

    def test_typical_dsar_workflow(self, temp_db_path):
        """Test typical DSAR ticket workflow through status transitions."""
        # Create ticket
        ticket_id = "DSAR-WORKFLOW-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="pending",
            email="workflow@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        # Typical workflow: PENDING → ASSIGNED → IN_PROGRESS → COMPLETED
        transitions = [
            ("assigned", "occurrence-1"),
            ("in_progress", "occurrence-1"),
            ("completed", "occurrence-1"),
        ]

        for status, occurrence_id in transitions:
            result = update_ticket_status(ticket_id, status, agent_occurrence_id=occurrence_id, db_path=temp_db_path)
            assert result is True, f"Transition to {status} should succeed"

            ticket = get_ticket(ticket_id, db_path=temp_db_path)
            assert ticket["status"] == status
            assert ticket["agent_occurrence_id"] == occurrence_id

    def test_blocked_workflow(self, temp_db_path):
        """Test workflow with BLOCKED status."""
        ticket_id = "BLOCKED-WORKFLOW-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="blocked@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        # IN_PROGRESS → BLOCKED → IN_PROGRESS → COMPLETED
        transitions = [
            ("blocked", "Waiting for legal clearance"),
            ("in_progress", "Legal clearance received"),
            ("completed", "All stages complete"),
        ]

        for status, note in transitions:
            result = update_ticket_status(ticket_id, status, notes=note, db_path=temp_db_path)
            assert result is True

    def test_deferred_workflow(self, temp_db_path):
        """Test workflow with DEFERRED status."""
        ticket_id = "DEFERRED-WORKFLOW-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="deferred@example.com",
            submitted_at=datetime.now(timezone.utc).isoformat(),
            db_path=temp_db_path,
        )

        # IN_PROGRESS → DEFERRED → IN_PROGRESS → COMPLETED
        result = update_ticket_status(ticket_id, "deferred", notes="Awaiting data", db_path=temp_db_path)
        assert result is True

        ticket = get_ticket(ticket_id, db_path=temp_db_path)
        assert ticket["status"] == "deferred"
