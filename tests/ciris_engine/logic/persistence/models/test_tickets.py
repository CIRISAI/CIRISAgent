"""
Tests for Tickets Persistence Model

Tests cover:
- create_ticket with all parameters and edge cases
- get_ticket with error handling
- update_ticket_status with new parameters
- update_ticket_metadata with all parameters
- list_tickets with filter combinations
- delete_ticket with error cases
- get_tickets_by_correlation_id
- _row_to_dict edge cases (PostgreSQL vs SQLite)
- Status updates with agent_occurrence_id
- Dynamic SQL construction
- All 8 status values
- Terminal status handling (completed_at)
- Atomic claiming with require_current_occurrence_id
- Error handling for all functions
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.persistence.models.tickets import (
    _get_row_value,
    _parse_automated_value,
    _parse_datetime_value,
    _parse_metadata_value,
    _row_to_dict,
    create_ticket,
    delete_ticket,
    get_ticket,
    get_tickets_by_correlation_id,
    list_tickets,
    update_ticket_metadata,
    update_ticket_status,
)


class TestUpdateTicketStatus:
    """Test update_ticket_status function with status system enhancements."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired.

        CIRISAgent#763: ticket persistence routes through ciris-persist's
        `ticket_*` substrate, so we bootstrap the persist Engine onto the
        temp DB via `initialize_database` (which also runs all SQLite
        migrations) and restore the previous engine on teardown.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
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
            automated=False
        )
        return ticket_id

    def test_update_status_only(self, temp_db_path, test_ticket_id):
        """TC-TP001: Verify updating status alone."""
        # Update status
        result = update_ticket_status(test_ticket_id, "in_progress")

        assert result is True, "Update should succeed"

        # Verify update
        ticket = get_ticket(test_ticket_id)
        assert ticket["status"] == "in_progress"
        assert ticket["completed_at"] is None, "Non-terminal status should not set completed_at"

        # Verify last_updated changed
        assert ticket["last_updated"] is not None

    def test_update_status_with_notes(self, temp_db_path, test_ticket_id):
        """TC-TP002: Verify status update with notes."""
        result = update_ticket_status(
            test_ticket_id, "blocked", notes="Waiting for legal approval")

        assert result is True

        ticket = get_ticket(test_ticket_id)
        assert ticket["status"] == "blocked"
        assert ticket["notes"] == "Waiting for legal approval"

    def test_update_status_with_agent_occurrence_id(self, temp_db_path, test_ticket_id):
        """TC-TP003: Verify updating agent_occurrence_id during status change."""
        result = update_ticket_status(
            test_ticket_id, "assigned", agent_occurrence_id="occurrence-1")

        assert result is True

        ticket = get_ticket(test_ticket_id)
        assert ticket["status"] == "assigned"
        assert ticket["agent_occurrence_id"] == "occurrence-1"

    def test_update_all_parameters(self, temp_db_path, test_ticket_id):
        """TC-TP004: Verify updating status + notes + occurrence_id."""
        result = update_ticket_status(
            test_ticket_id,
            "assigned",
            notes="Claimed by occurrence",
            agent_occurrence_id="occurrence-2",
        )

        assert result is True

        ticket = get_ticket(test_ticket_id)
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
                submitted_at=datetime.now(timezone.utc).isoformat()
            )
            ticket_ids.append((ticket_id, status))

        # Update to terminal statuses
        for ticket_id, terminal_status in ticket_ids:
            update_ticket_status(ticket_id, terminal_status)

        # Verify all have completed_at
        for ticket_id, _ in ticket_ids:
            ticket = get_ticket(ticket_id)
            assert ticket["completed_at"] is not None, f"Ticket {ticket_id} should have completed_at"

    def test_non_terminal_leaves_completed_at_null(self, temp_db_path, test_ticket_id):
        """TC-TP006: Verify completed_at remains NULL for non-terminal statuses."""
        non_terminal_statuses = ["pending", "assigned", "in_progress", "blocked", "deferred"]

        for status in non_terminal_statuses:
            update_ticket_status(test_ticket_id, status)
            ticket = get_ticket(test_ticket_id)
            assert ticket["completed_at"] is None, f"Status {status} should not set completed_at"

    def test_nonexistent_ticket(self, temp_db_path):
        """TC-TP007: Verify error handling for missing ticket."""
        result = update_ticket_status("NONEXISTENT", "completed")

        assert result is False, "Update of nonexistent ticket should fail"

    def test_all_8_status_values(self, temp_db_path, test_ticket_id):
        """TC-TP009: Verify all status values accepted."""
        all_statuses = ["pending", "assigned", "in_progress", "blocked", "deferred", "completed", "cancelled", "failed"]

        for status in all_statuses:
            result = update_ticket_status(test_ticket_id, status)
            assert result is True, f"Status {status} should be accepted"

            ticket = get_ticket(test_ticket_id)
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
                test_ticket_id, status, notes=notes, agent_occurrence_id=agent_occurrence_id)

            # Verify update succeeded
            ticket = get_ticket(test_ticket_id)
            assert ticket["status"] == status

            if notes:
                assert ticket["notes"] == notes
            if agent_occurrence_id:
                assert ticket["agent_occurrence_id"] == agent_occurrence_id


class TestTicketStatusTransitions:
    """Test valid status transition scenarios."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
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
            submitted_at=datetime.now(timezone.utc).isoformat()
        )

        # Typical workflow: PENDING → ASSIGNED → IN_PROGRESS → COMPLETED
        transitions = [
            ("assigned", "occurrence-1"),
            ("in_progress", "occurrence-1"),
            ("completed", "occurrence-1"),
        ]

        for status, occurrence_id in transitions:
            result = update_ticket_status(ticket_id, status, agent_occurrence_id=occurrence_id)
            assert result is True, f"Transition to {status} should succeed"

            ticket = get_ticket(ticket_id)
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
            submitted_at=datetime.now(timezone.utc).isoformat()
        )

        # IN_PROGRESS → BLOCKED → IN_PROGRESS → COMPLETED
        transitions = [
            ("blocked", "Waiting for legal clearance"),
            ("in_progress", "Legal clearance received"),
            ("completed", "All stages complete"),
        ]

        for status, note in transitions:
            result = update_ticket_status(ticket_id, status, notes=note)
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
            submitted_at=datetime.now(timezone.utc).isoformat()
        )

        # IN_PROGRESS → DEFERRED → IN_PROGRESS → COMPLETED
        result = update_ticket_status(ticket_id, "deferred", notes="Awaiting data")
        assert result is True

        ticket = get_ticket(ticket_id)
        assert ticket["status"] == "deferred"


class TestCreateTicket:
    """Test create_ticket function with all parameters and edge cases."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_create_ticket_minimal_params(self, temp_db_path):
        """TC-CT001: Create ticket with minimal required parameters."""
        ticket_id = "TEST-MIN-001"
        result = create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="test@example.com",
        )

        assert result is True
        ticket = get_ticket(ticket_id)
        assert ticket is not None
        assert ticket["ticket_id"] == ticket_id
        assert ticket["sop"] == "DSAR_ACCESS"
        assert ticket["ticket_type"] == "dsar"
        assert ticket["email"] == "test@example.com"
        assert ticket["status"] == "pending"
        assert ticket["priority"] == 5
        assert ticket["agent_occurrence_id"] == "__shared__"
        assert ticket["automated"] is False

    def test_create_ticket_all_params(self, temp_db_path):
        """TC-CT002: Create ticket with all optional parameters."""
        ticket_id = "TEST-ALL-001"
        submitted_at = datetime.now(timezone.utc)
        deadline = submitted_at + timedelta(days=30)
        metadata = {"stage": 1, "progress": 0.0, "data": {"key": "value"}}

        result = create_ticket(
            ticket_id=ticket_id,
            sop="APPOINTMENT_SCHEDULE",
            ticket_type="appointment",
            email="full@example.com",
            status="assigned",
            priority=8,
            user_identifier="user456",
            submitted_at=submitted_at,
            deadline=deadline,
            metadata=metadata,
            notes="Initial notes",
            automated=True,
            correlation_id="corr-123",
            agent_occurrence_id="occurrence-1",
        )

        assert result is True
        ticket = get_ticket(ticket_id)
        assert ticket["status"] == "assigned"
        assert ticket["priority"] == 8
        assert ticket["user_identifier"] == "user456"
        assert ticket["metadata"]["stage"] == 1
        assert ticket["notes"] == "Initial notes"
        assert ticket["automated"] is True
        assert ticket["correlation_id"] == "corr-123"
        assert ticket["agent_occurrence_id"] == "occurrence-1"

    def test_create_ticket_datetime_string(self, temp_db_path):
        """TC-CT003: Create ticket with datetime as ISO string.

        Persist normalizes `+00:00` → `Z` on round-trip; compare via parsed
        datetimes rather than raw strings.
        """
        ticket_id = "TEST-STR-001"
        submitted_at_str = "2025-01-15T10:30:00+00:00"
        deadline_str = "2025-02-15T10:30:00+00:00"

        result = create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="str@example.com",
            submitted_at=submitted_at_str,
            deadline=deadline_str,
        )

        assert result is True
        ticket = get_ticket(ticket_id)
        assert datetime.fromisoformat(ticket["submitted_at"].replace("Z", "+00:00")) == datetime.fromisoformat(
            submitted_at_str
        )
        assert datetime.fromisoformat(ticket["deadline"].replace("Z", "+00:00")) == datetime.fromisoformat(
            deadline_str
        )

    def test_create_ticket_duplicate_id_upserts(self, temp_db_path):
        """TC-CT004: Re-creating with the same ticket_id upserts (CIRISAgent#763).

        Post-migration `create_ticket` routes through persist's `ticket_upsert`,
        so duplicates overwrite the existing row rather than failing. Legacy
        INSERT-with-conflict-error behavior is gone.
        """
        ticket_id = "TEST-DUP-001"

        result1 = create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="dup@example.com",
        )
        assert result1 is True

        result2 = create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="dup2@example.com",
        )
        assert result2 is True

        ticket = get_ticket(ticket_id)
        assert ticket["email"] == "dup2@example.com"

    def test_create_ticket_empty_metadata(self, temp_db_path):
        """TC-CT005: Create ticket with empty metadata dict."""
        ticket_id = "TEST-EMPTY-001"
        result = create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="empty@example.com",
            metadata={},
        )

        assert result is True
        ticket = get_ticket(ticket_id)
        assert ticket["metadata"] == {}

    def test_create_ticket_none_metadata(self, temp_db_path):
        """TC-CT006: Create ticket with None metadata (should default to {})."""
        ticket_id = "TEST-NONE-001"
        result = create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="none@example.com",
            metadata=None,
        )

        assert result is True
        ticket = get_ticket(ticket_id)
        assert ticket["metadata"] == {}

    def test_create_ticket_default_submitted_at(self, temp_db_path):
        """TC-CT008: Verify submitted_at defaults to current time."""
        ticket_id = "TEST-DEFAULT-001"
        before = datetime.now(timezone.utc)

        result = create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="default@example.com",
        )

        after = datetime.now(timezone.utc)
        assert result is True

        ticket = get_ticket(ticket_id)
        submitted_at = datetime.fromisoformat(ticket["submitted_at"])
        assert before <= submitted_at <= after


class TestGetTicket:
    """Test get_ticket function with error handling."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_get_ticket_nonexistent(self, temp_db_path):
        """TC-GT001: Verify get_ticket returns None for nonexistent ticket."""
        result = get_ticket("NONEXISTENT-001")
        assert result is None

    def test_get_ticket_existing(self, temp_db_path):
        """TC-GT002: Verify get_ticket returns ticket data."""
        ticket_id = "TEST-GET-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="get@example.com",
        )

        ticket = get_ticket(ticket_id)
        assert ticket is not None
        assert ticket["ticket_id"] == ticket_id
        assert "submitted_at" in ticket
        assert "last_updated" in ticket


class TestUpdateTicketMetadata:
    """Test update_ticket_metadata function."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def test_ticket_id(self, temp_db_path):
        """Create a test ticket."""
        ticket_id = "TEST-META-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="meta@example.com",
            metadata={"stage": 1, "progress": 0.0},
        )
        return ticket_id

    def test_update_metadata_simple(self, temp_db_path, test_ticket_id):
        """TC-UM001: Update metadata with simple dict."""
        new_metadata = {"stage": 2, "progress": 0.5, "notes": "Updated"}

        result = update_ticket_metadata(test_ticket_id, new_metadata)
        assert result is True

        ticket = get_ticket(test_ticket_id)
        assert ticket["metadata"]["stage"] == 2
        assert ticket["metadata"]["progress"] == 0.5
        assert ticket["metadata"]["notes"] == "Updated"

    def test_update_metadata_complex(self, temp_db_path, test_ticket_id):
        """TC-UM002: Update metadata with nested structures."""
        new_metadata = {
            "stage": 3,
            "stages": [
                {"name": "verify", "status": "completed"},
                {"name": "extract", "status": "in_progress"},
            ],
            "data": {"records_found": 42, "files": ["doc1.pdf", "doc2.pdf"]},
        }

        result = update_ticket_metadata(test_ticket_id, new_metadata)
        assert result is True

        ticket = get_ticket(test_ticket_id)
        assert ticket["metadata"]["stage"] == 3
        assert len(ticket["metadata"]["stages"]) == 2
        assert ticket["metadata"]["data"]["records_found"] == 42

    def test_update_metadata_empty_dict(self, temp_db_path, test_ticket_id):
        """TC-UM003: Update metadata to empty dict (clears metadata)."""
        result = update_ticket_metadata(test_ticket_id, {})
        assert result is True

        ticket = get_ticket(test_ticket_id)
        assert ticket["metadata"] == {}

    def test_update_metadata_nonexistent_ticket(self, temp_db_path):
        """TC-UM004: Verify error handling for nonexistent ticket."""
        result = update_ticket_metadata("NONEXISTENT", {"test": True})
        assert result is False

    def test_update_metadata_updates_last_updated(self, temp_db_path, test_ticket_id):
        """TC-UM006: Verify last_updated timestamp is updated."""
        ticket_before = get_ticket(test_ticket_id)
        last_updated_before = ticket_before["last_updated"]

        # Small delay to ensure timestamp difference
        import time

        time.sleep(0.1)

        result = update_ticket_metadata(test_ticket_id, {"updated": True})
        assert result is True

        ticket_after = get_ticket(test_ticket_id)
        last_updated_after = ticket_after["last_updated"]

        assert last_updated_after > last_updated_before


class TestListTickets:
    """Test list_tickets function with all filter combinations."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def sample_tickets(self, temp_db_path):
        """Create sample tickets for testing."""
        tickets = [
            {
                "ticket_id": "DSAR-001",
                "sop": "DSAR_ACCESS",
                "ticket_type": "dsar",
                "status": "pending",
                "email": "user1@example.com",
            },
            {
                "ticket_id": "DSAR-002",
                "sop": "DSAR_ERASURE",
                "ticket_type": "dsar",
                "status": "in_progress",
                "email": "user2@example.com",
            },
            {
                "ticket_id": "APPT-001",
                "sop": "APPOINTMENT_SCHEDULE",
                "ticket_type": "appointment",
                "status": "pending",
                "email": "user1@example.com",
            },
            {
                "ticket_id": "APPT-002",
                "sop": "APPOINTMENT_SCHEDULE",
                "ticket_type": "appointment",
                "status": "completed",
                "email": "user3@example.com",
            },
            {
                "ticket_id": "INC-001",
                "sop": "INCIDENT_REPORT",
                "ticket_type": "incident",
                "status": "failed",
                "email": "user2@example.com",
            },
        ]

        for ticket in tickets:
            create_ticket(**ticket)

        return tickets

    def test_list_tickets_no_filters(self, temp_db_path, sample_tickets):
        """TC-LT001: List all tickets without filters."""
        tickets = list_tickets()
        assert len(tickets) == 5
        # Verify sorted by submitted_at DESC
        assert tickets[0]["ticket_id"] == "INC-001"  # Last created

    def test_list_tickets_filter_by_sop(self, temp_db_path, sample_tickets):
        """TC-LT002: Filter tickets by SOP."""
        tickets = list_tickets(sop="DSAR_ACCESS")
        assert len(tickets) == 1
        assert tickets[0]["ticket_id"] == "DSAR-001"

    def test_list_tickets_filter_by_type(self, temp_db_path, sample_tickets):
        """TC-LT003: Filter tickets by ticket_type."""
        tickets = list_tickets(ticket_type="dsar")
        assert len(tickets) == 2
        assert all(t["ticket_type"] == "dsar" for t in tickets)

    def test_list_tickets_filter_by_status(self, temp_db_path, sample_tickets):
        """TC-LT004: Filter tickets by status."""
        tickets = list_tickets(status="pending")
        assert len(tickets) == 2
        assert all(t["status"] == "pending" for t in tickets)

    def test_list_tickets_filter_by_email(self, temp_db_path, sample_tickets):
        """TC-LT005: Filter tickets by email."""
        tickets = list_tickets(email="user1@example.com")
        assert len(tickets) == 2
        assert all(t["email"] == "user1@example.com" for t in tickets)

    def test_list_tickets_multiple_filters(self, temp_db_path, sample_tickets):
        """TC-LT006: Combine multiple filters."""
        tickets = list_tickets(ticket_type="dsar", status="pending", email="user1@example.com")
        assert len(tickets) == 1
        assert tickets[0]["ticket_id"] == "DSAR-001"

    def test_list_tickets_with_limit(self, temp_db_path, sample_tickets):
        """TC-LT007: Limit number of results."""
        tickets = list_tickets(limit=3)
        assert len(tickets) == 3

    def test_list_tickets_no_matches(self, temp_db_path, sample_tickets):
        """TC-LT008: Filter with no matching results."""
        tickets = list_tickets(sop="NONEXISTENT_SOP")
        assert len(tickets) == 0

    def test_list_tickets_empty_database(self, temp_db_path):
        """TC-LT010: List tickets from empty database."""
        tickets = list_tickets()
        assert len(tickets) == 0


class TestDeleteTicket:
    """Test delete_ticket function."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_delete_ticket_success(self, temp_db_path):
        """TC-DT001: delete_ticket soft-cancels via status (CIRISAgent#763)."""
        ticket_id = "TEST-DEL-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="delete@example.com",
        )

        assert get_ticket(ticket_id) is not None

        result = delete_ticket(ticket_id)
        assert result is True

        # Persist 1.5.19 has no hard-delete substrate; delete_ticket marks
        # the row cancelled instead. Row stays queryable until ticket_delete
        # lands upstream.
        ticket = get_ticket(ticket_id)
        assert ticket is not None
        assert ticket["status"] == "cancelled"

    def test_delete_ticket_nonexistent(self, temp_db_path):
        """TC-DT002: Try to delete nonexistent ticket."""
        result = delete_ticket("NONEXISTENT")
        assert result is False


class TestGetTicketsByCorrelationId:
    """Test get_tickets_by_correlation_id function."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_get_tickets_by_correlation_id_found(self, temp_db_path):
        """TC-CORR001: Get tickets with matching correlation ID."""
        correlation_id = "corr-123"

        # Create tickets with same correlation ID
        for i in range(3):
            create_ticket(
                ticket_id=f"TEST-CORR-{i}",
                sop="DSAR_ACCESS",
                ticket_type="dsar",
                email=f"corr{i}@example.com",
                correlation_id=correlation_id,
            )

        # Create ticket with different correlation ID
        create_ticket(
            ticket_id="TEST-OTHER-001",
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="other@example.com",
            correlation_id="other-corr",
        )

        tickets = get_tickets_by_correlation_id(correlation_id)
        assert len(tickets) == 3
        assert all(t["correlation_id"] == correlation_id for t in tickets)

    def test_get_tickets_by_correlation_id_none_found(self, temp_db_path):
        """TC-CORR002: Get tickets with nonexistent correlation ID."""
        tickets = get_tickets_by_correlation_id("nonexistent-corr")
        assert len(tickets) == 0


class TestRowToDict:
    """Test _row_to_dict function with edge cases."""

    def test_row_to_dict_sqlite_row(self):
        """TC-RTD001: Convert SQLite row to dict."""
        # Mock SQLite row
        mock_row = {
            "ticket_id": "TEST-001",
            "sop": "DSAR_ACCESS",
            "ticket_type": "dsar",
            "status": "pending",
            "priority": 5,
            "email": "test@example.com",
            "user_identifier": "user123",
            "submitted_at": "2025-01-15T10:30:00+00:00",
            "deadline": "2025-02-15T10:30:00+00:00",
            "last_updated": "2025-01-15T10:30:00+00:00",
            "completed_at": None,
            "metadata": '{"stage": 1}',
            "notes": "Test note",
            "automated": 1,  # SQLite stores boolean as INTEGER
            "correlation_id": "corr-123",
            "created_at": "2025-01-15T10:30:00+00:00",
            "agent_occurrence_id": "__shared__",
        }

        result = _row_to_dict(mock_row)

        assert result["ticket_id"] == "TEST-001"
        assert result["metadata"]["stage"] == 1
        assert result["automated"] is True
        assert "created_at" not in result  # Should be excluded

    def test_row_to_dict_postgres_row(self):
        """TC-RTD002: Convert PostgreSQL row to dict."""
        # Mock PostgreSQL row with datetime objects
        mock_row = {
            "ticket_id": "TEST-002",
            "sop": "DSAR_ACCESS",
            "ticket_type": "dsar",
            "status": "pending",
            "priority": 5,
            "email": "test@example.com",
            "user_identifier": "user123",
            "submitted_at": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "deadline": datetime(2025, 2, 15, 10, 30, 0, tzinfo=timezone.utc),
            "last_updated": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "completed_at": datetime(2025, 1, 16, 10, 30, 0, tzinfo=timezone.utc),
            "metadata": {"stage": 1},  # PostgreSQL JSONB returns dict
            "notes": "Test note",
            "automated": True,  # PostgreSQL stores boolean as BOOLEAN
            "correlation_id": "corr-123",
            "created_at": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            "agent_occurrence_id": "__shared__",
        }

        result = _row_to_dict(mock_row)

        assert result["ticket_id"] == "TEST-002"
        assert result["metadata"]["stage"] == 1
        assert result["automated"] is True
        assert isinstance(result["submitted_at"], str)
        assert isinstance(result["completed_at"], str)

    def test_row_to_dict_missing_columns(self):
        """TC-RTD003: Handle row with missing columns (None values)."""
        mock_row = {
            "ticket_id": "TEST-003",
            "sop": "DSAR_ACCESS",
            "ticket_type": "dsar",
            "status": "pending",
            "priority": 5,
            "email": "test@example.com",
            # Missing other columns - will be looked up and get None
        }

        result = _row_to_dict(mock_row)

        assert result["ticket_id"] == "TEST-003"
        assert result["user_identifier"] is None
        assert result["deadline"] is None
        # When metadata is None (missing from dict), the condition
        # `if key == "metadata" and value:` is False (since value is None/falsy)
        # So it falls through to else: result[key] = value, storing None
        assert result["metadata"] is None

    def test_row_to_dict_invalid_json_metadata(self):
        """TC-RTD004: Handle invalid JSON in metadata."""
        mock_row = {
            "ticket_id": "TEST-004",
            "sop": "DSAR_ACCESS",
            "ticket_type": "dsar",
            "status": "pending",
            "priority": 5,
            "email": "test@example.com",
            "user_identifier": None,
            "submitted_at": "2025-01-15T10:30:00+00:00",
            "deadline": None,
            "last_updated": "2025-01-15T10:30:00+00:00",
            "completed_at": None,
            "metadata": "invalid json {",
            "notes": None,
            "automated": 0,
            "correlation_id": None,
            "created_at": "2025-01-15T10:30:00+00:00",
            "agent_occurrence_id": "__shared__",
        }

        result = _row_to_dict(mock_row)

        assert result["metadata"] == {}  # Should default to empty dict

    def test_row_to_dict_null_automated(self):
        """TC-RTD005: Handle NULL automated field."""
        mock_row = {
            "ticket_id": "TEST-005",
            "sop": "DSAR_ACCESS",
            "ticket_type": "dsar",
            "status": "pending",
            "priority": 5,
            "email": "test@example.com",
            "user_identifier": None,
            "submitted_at": "2025-01-15T10:30:00+00:00",
            "deadline": None,
            "last_updated": "2025-01-15T10:30:00+00:00",
            "completed_at": None,
            "metadata": "{}",
            "notes": None,
            "automated": None,
            "correlation_id": None,
            "created_at": "2025-01-15T10:30:00+00:00",
            "agent_occurrence_id": "__shared__",
        }

        result = _row_to_dict(mock_row)

        assert result["automated"] is False  # Should default to False


class TestUpdateTicketStatusAdvanced:
    """Test advanced update_ticket_status scenarios including atomic claiming."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database with migrations applied + persist wired (CIRISAgent#763)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name

        from ciris_engine.logic.persistence.db.core import initialize_database
        from ciris_engine.logic.persistence.models import graph as _graph_mod

        prior_engine = _graph_mod._engine
        prior_dsn = _graph_mod._engine_dsn
        initialize_database(db_path)

        yield db_path

        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn
        if os.path.exists(db_path):
            os.unlink(db_path)

    def test_atomic_claim_success(self, temp_db_path):
        """TC-ATS001: Successfully claim ticket atomically."""
        ticket_id = "TEST-CLAIM-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="claim@example.com",
            agent_occurrence_id="__shared__",
        )

        # Claim ticket from __shared__ to occurrence-1
        result = update_ticket_status(
            ticket_id,
            "assigned",
            agent_occurrence_id="occurrence-1",
            require_current_occurrence_id="__shared__",
        )

        assert result is True

        ticket = get_ticket(ticket_id)
        assert ticket["status"] == "assigned"
        assert ticket["agent_occurrence_id"] == "occurrence-1"

    def test_atomic_claim_failure_already_claimed(self, temp_db_path):
        """TC-ATS002: Fail to claim ticket already claimed by another occurrence."""
        ticket_id = "TEST-CLAIM-002"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="claim@example.com",
            agent_occurrence_id="occurrence-1",  # Already claimed
            )

        # Try to claim from __shared__ (but it's actually occurrence-1)
        result = update_ticket_status(
            ticket_id,
            "assigned",
            agent_occurrence_id="occurrence-2",
            require_current_occurrence_id="__shared__",
        )

        assert result is False  # Should fail because occurrence_id doesn't match

        ticket = get_ticket(ticket_id)
        assert ticket["agent_occurrence_id"] == "occurrence-1"  # Unchanged

    def test_atomic_claim_race_condition_simulation(self, temp_db_path):
        """TC-ATS003: Simulate race condition in claiming."""
        ticket_id = "TEST-RACE-001"
        create_ticket(
            ticket_id=ticket_id,
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            email="race@example.com",
            agent_occurrence_id="__shared__",
        )

        # First occurrence claims
        result1 = update_ticket_status(
            ticket_id,
            "assigned",
            agent_occurrence_id="occurrence-1",
            require_current_occurrence_id="__shared__",
        )
        assert result1 is True

        # Second occurrence tries to claim (should fail)
        result2 = update_ticket_status(
            ticket_id,
            "assigned",
            agent_occurrence_id="occurrence-2",
            require_current_occurrence_id="__shared__",
        )
        assert result2 is False

        ticket = get_ticket(ticket_id)
        assert ticket["agent_occurrence_id"] == "occurrence-1"


class TestHelperFunctions:
    """Test helper functions extracted for cognitive complexity reduction."""

    def test_parse_metadata_value_none(self):
        """TC-HF001: Parse None metadata value."""
        result = _parse_metadata_value(None)
        assert result is None

    def test_parse_metadata_value_empty_string(self):
        """TC-HF002: Parse empty string metadata value."""
        result = _parse_metadata_value("")
        assert result is None

    def test_parse_metadata_value_json_string(self):
        """TC-HF003: Parse JSON string metadata (SQLite)."""
        result = _parse_metadata_value('{"stage": 1, "progress": 0.5}')
        assert result == {"stage": 1, "progress": 0.5}

    def test_parse_metadata_value_dict(self):
        """TC-HF004: Parse dict metadata (PostgreSQL JSONB)."""
        result = _parse_metadata_value({"stage": 2, "progress": 0.75})
        assert result == {"stage": 2, "progress": 0.75}

    def test_parse_metadata_value_invalid_json(self):
        """TC-HF005: Parse invalid JSON string."""
        result = _parse_metadata_value("invalid json {")
        assert result == {}

    def test_parse_metadata_value_complex_nested(self):
        """TC-HF006: Parse complex nested metadata."""
        metadata = {"stages": [{"name": "verify", "status": "completed"}], "data": {"records": 42}}
        result = _parse_metadata_value(json.dumps(metadata))
        assert result == metadata

    def test_parse_automated_value_none(self):
        """TC-HF007: Parse None automated value."""
        result = _parse_automated_value(None)
        assert result is False

    def test_parse_automated_value_zero(self):
        """TC-HF008: Parse 0 automated value (SQLite)."""
        result = _parse_automated_value(0)
        assert result is False

    def test_parse_automated_value_one(self):
        """TC-HF009: Parse 1 automated value (SQLite)."""
        result = _parse_automated_value(1)
        assert result is True

    def test_parse_automated_value_true(self):
        """TC-HF010: Parse True automated value (PostgreSQL)."""
        result = _parse_automated_value(True)
        assert result is True

    def test_parse_automated_value_false(self):
        """TC-HF011: Parse False automated value (PostgreSQL)."""
        result = _parse_automated_value(False)
        assert result is False

    def test_parse_datetime_value_none(self):
        """TC-HF012: Parse None datetime value."""
        result = _parse_datetime_value(None)
        assert result is None

    def test_parse_datetime_value_datetime_object(self):
        """TC-HF013: Parse datetime object (PostgreSQL)."""
        dt = datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        result = _parse_datetime_value(dt)
        assert result == "2025-01-15T10:30:00+00:00"

    def test_parse_datetime_value_iso_string(self):
        """TC-HF014: Parse ISO string (SQLite)."""
        iso_string = "2025-01-15T10:30:00+00:00"
        result = _parse_datetime_value(iso_string)
        assert result == iso_string

    def test_get_row_value_dict_access(self):
        """TC-HF015: Get value from dict-like row."""
        row = {"ticket_id": "TEST-001", "status": "pending"}
        result = _get_row_value(row, "ticket_id")
        assert result == "TEST-001"

    def test_get_row_value_missing_key(self):
        """TC-HF016: Get missing value from row."""
        row = {"ticket_id": "TEST-001"}
        result = _get_row_value(row, "missing_key")
        assert result is None

    def test_get_row_value_index_error(self):
        """TC-HF017: Handle index error gracefully."""

        # Simulate a row that raises IndexError
        class BadRow:
            def __getitem__(self, key):
                raise IndexError("Bad index")

        row = BadRow()
        result = _get_row_value(row, "any_key")
        assert result is None
