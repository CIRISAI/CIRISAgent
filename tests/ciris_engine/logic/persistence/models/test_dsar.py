"""
Comprehensive unit tests for ciris_engine/logic/persistence/models/dsar.py

Tests focus on DSAR ticket persistence for GDPR compliance:
- create_dsar_ticket() - Store new DSAR tickets
- get_dsar_ticket() - Retrieve by ticket_id
- update_dsar_ticket_status() - Update status and notes
- list_dsar_tickets_by_status() - List by status filter
- list_dsar_tickets_by_email() - List by email
- _row_to_dict() - Database row conversion

GDPR Requirement: DSAR tickets must survive server restarts (30-day response window)
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from ciris_engine.logic.persistence.db import get_db_connection, initialize_database
from ciris_engine.logic.persistence.models.dsar import (
    create_dsar_ticket,
    get_dsar_ticket,
    list_dsar_tickets_by_email,
    list_dsar_tickets_by_status,
    update_dsar_ticket_status,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    # Initialize database schema
    initialize_database(db_path)

    yield db_path

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


class TestCreateDSARTicket:
    """Test create_dsar_ticket() function."""

    def test_create_basic_ticket(self, temp_db):
        """Test creating a basic DSAR ticket."""
        ticket_id = "DSAR-20251103-123456"
        email = "user@example.com"
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        success = create_dsar_ticket(
            ticket_id=ticket_id,
            request_type="access",
            email=email,
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        assert success is True

        # Verify ticket was created
        ticket = get_dsar_ticket(ticket_id, db_path=temp_db)
        assert ticket is not None
        assert ticket["ticket_id"] == ticket_id
        assert ticket["email"] == email
        assert ticket["request_type"] == "access"
        assert ticket["status"] == "pending_review"
        assert ticket["automated"] is False

    def test_create_ticket_with_all_fields(self, temp_db):
        """Test creating a ticket with all optional fields."""
        ticket_id = "DSAR-20251103-789012"
        access_package = {"data_found": True, "record_count": 5}
        export_package = {"format": "json", "file_size": 1024}
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=3)

        success = create_dsar_ticket(
            ticket_id=ticket_id,
            request_type="export",
            email="urgent@example.com",
            status="completed",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=True,
            user_identifier="discord:123456789",
            details="Urgent export request",
            urgent=True,
            access_package=access_package,
            export_package=export_package,
            db_path=temp_db,
        )

        assert success is True

        # Verify all fields
        ticket = get_dsar_ticket(ticket_id, db_path=temp_db)
        assert ticket["user_identifier"] == "discord:123456789"
        assert ticket["details"] == "Urgent export request"
        assert ticket["urgent"] is True
        assert ticket["automated"] is True
        assert ticket["access_package"] == access_package
        assert ticket["export_package"] == export_package

    def test_create_duplicate_ticket_fails(self, temp_db):
        """Test that creating a duplicate ticket_id fails."""
        ticket_id = "DSAR-20251103-999999"
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        # Create first ticket
        success = create_dsar_ticket(
            ticket_id=ticket_id,
            request_type="delete",
            email="test@example.com",
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )
        assert success is True

        # Attempt to create duplicate
        success = create_dsar_ticket(
            ticket_id=ticket_id,  # Same ticket_id
            request_type="access",
            email="different@example.com",
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )
        assert success is False


class TestGetDSARTicket:
    """Test get_dsar_ticket() function."""

    def test_get_existing_ticket(self, temp_db):
        """Test retrieving an existing ticket."""
        ticket_id = "DSAR-20251103-111111"
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        create_dsar_ticket(
            ticket_id=ticket_id,
            request_type="correct",
            email="correct@example.com",
            status="in_progress",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        ticket = get_dsar_ticket(ticket_id, db_path=temp_db)
        assert ticket is not None
        assert ticket["ticket_id"] == ticket_id
        assert ticket["request_type"] == "correct"
        assert ticket["email"] == "correct@example.com"

    def test_get_nonexistent_ticket(self, temp_db):
        """Test retrieving a nonexistent ticket returns None."""
        ticket = get_dsar_ticket("DSAR-NONEXISTENT", db_path=temp_db)
        assert ticket is None


class TestUpdateDSARTicketStatus:
    """Test update_dsar_ticket_status() function."""

    def test_update_status_only(self, temp_db):
        """Test updating only the status field."""
        ticket_id = "DSAR-20251103-222222"
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        create_dsar_ticket(
            ticket_id=ticket_id,
            request_type="access",
            email="status@example.com",
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        # Update status
        success = update_dsar_ticket_status(ticket_id, "in_progress", db_path=temp_db)
        assert success is True

        # Verify update
        ticket = get_dsar_ticket(ticket_id, db_path=temp_db)
        assert ticket["status"] == "in_progress"
        assert ticket["notes"] is None  # Should remain None

    def test_update_status_with_notes(self, temp_db):
        """Test updating status with notes."""
        ticket_id = "DSAR-20251103-333333"
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        create_dsar_ticket(
            ticket_id=ticket_id,
            request_type="delete",
            email="notes@example.com",
            status="in_progress",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        # Update with notes
        notes = "Completed data deletion process"
        success = update_dsar_ticket_status(ticket_id, "completed", notes=notes, db_path=temp_db)
        assert success is True

        # Verify notes were saved
        ticket = get_dsar_ticket(ticket_id, db_path=temp_db)
        assert ticket["status"] == "completed"
        assert ticket["notes"] == notes

    def test_update_nonexistent_ticket(self, temp_db):
        """Test updating a nonexistent ticket returns False."""
        success = update_dsar_ticket_status("DSAR-NONEXISTENT", "completed", db_path=temp_db)
        assert success is False


class TestListDSARTicketsByStatus:
    """Test list_dsar_tickets_by_status() function."""

    def test_list_by_status(self, temp_db):
        """Test listing tickets by status."""
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        # Create tickets with different statuses
        create_dsar_ticket(
            ticket_id="DSAR-PENDING-001",
            request_type="access",
            email="user1@example.com",
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        create_dsar_ticket(
            ticket_id="DSAR-PROGRESS-001",
            request_type="delete",
            email="user2@example.com",
            status="in_progress",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        create_dsar_ticket(
            ticket_id="DSAR-PENDING-002",
            request_type="export",
            email="user3@example.com",
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        # List pending tickets
        pending = list_dsar_tickets_by_status("pending_review", db_path=temp_db)
        assert len(pending) == 2
        assert all(t["status"] == "pending_review" for t in pending)

        # List in_progress tickets
        in_progress = list_dsar_tickets_by_status("in_progress", db_path=temp_db)
        assert len(in_progress) == 1
        assert in_progress[0]["ticket_id"] == "DSAR-PROGRESS-001"

    def test_list_all_tickets(self, temp_db):
        """Test listing all tickets without status filter."""
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        # Create 3 tickets
        for i in range(3):
            create_dsar_ticket(
                ticket_id=f"DSAR-ALL-{i:03d}",
                request_type="access",
                email=f"user{i}@example.com",
                status="pending_review" if i % 2 == 0 else "completed",
                submitted_at=submitted_at,
                estimated_completion=estimated_completion,
                automated=False,
                db_path=temp_db,
            )

        # List all tickets (no status filter)
        all_tickets = list_dsar_tickets_by_status(None, db_path=temp_db)
        assert len(all_tickets) >= 3  # May include tickets from other tests


class TestListDSARTicketsByEmail:
    """Test list_dsar_tickets_by_email() function."""

    def test_list_by_email(self, temp_db):
        """Test listing tickets for a specific email."""
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)
        target_email = "multiuser@example.com"

        # Create multiple tickets for same email
        for i in range(3):
            create_dsar_ticket(
                ticket_id=f"DSAR-EMAIL-{i:03d}",
                request_type="access",
                email=target_email,
                status="pending_review",
                submitted_at=submitted_at,
                estimated_completion=estimated_completion,
                automated=False,
                db_path=temp_db,
            )

        # Create ticket for different email
        create_dsar_ticket(
            ticket_id="DSAR-OTHER-001",
            request_type="access",
            email="other@example.com",
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            db_path=temp_db,
        )

        # List tickets for target email
        tickets = list_dsar_tickets_by_email(target_email, db_path=temp_db)
        assert len(tickets) == 3
        assert all(t["email"] == target_email for t in tickets)

    def test_list_by_email_no_results(self, temp_db):
        """Test listing tickets for email with no requests."""
        tickets = list_dsar_tickets_by_email("nonexistent@example.com", db_path=temp_db)
        assert len(tickets) == 0


class TestGDPRCompliance:
    """Test GDPR compliance requirements."""

    def test_tickets_survive_restart(self, temp_db):
        """Critical test: Tickets must survive server restart (30-day GDPR requirement)."""
        ticket_id = "DSAR-GDPR-RESTART"
        submitted_at = datetime.now(timezone.utc)
        estimated_completion = submitted_at + timedelta(days=30)

        # Create ticket
        create_dsar_ticket(
            ticket_id=ticket_id,
            request_type="access",
            email="gdpr@example.com",
            status="pending_review",
            submitted_at=submitted_at,
            estimated_completion=estimated_completion,
            automated=False,
            user_identifier="user:12345",
            details="GDPR Article 15 access request",
            db_path=temp_db,
        )

        # Simulate server restart by getting new connection
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM dsar_tickets WHERE ticket_id = ?", (ticket_id,))
            count = cursor.fetchone()[0]

        # Ticket must still exist
        assert count == 1

        # Verify full ticket data persisted
        ticket = get_dsar_ticket(ticket_id, db_path=temp_db)
        assert ticket is not None
        assert ticket["ticket_id"] == ticket_id
        assert ticket["email"] == "gdpr@example.com"
        assert ticket["user_identifier"] == "user:12345"
        assert ticket["details"] == "GDPR Article 15 access request"
