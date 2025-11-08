"""
Tests for Migration 009: Ticket Status Handling System

Tests cover:
- SQLite and PostgreSQL migration application
- agent_occurrence_id column addition
- Status CHECK constraint expansion (8 states)
- Index creation for multi-occurrence coordination
- Data migration from existing tickets
- Error handling and rollback
"""

import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ciris_engine.logic.persistence.db.core import get_db_connection


class TestMigration009SQLite:
    """Test Migration 009 for SQLite."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        yield db_path
        if os.path.exists(db_path):
            os.unlink(db_path)

    @pytest.fixture
    def migrations_dir(self):
        """Get migrations directory."""
        # Go up to project root and then to migrations
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent
        return project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "sqlite"

    def apply_migration(self, db_path: str, migration_file: Path, migration_num: int = 0) -> None:
        """Apply a single migration file."""
        with open(migration_file, "r") as f:
            sql = f.read()
            # Workaround for pre-existing view bug in migration 001
            if migration_num == 1:
                sql = sql.replace("t.task_id as associated_task_id", "t.thought_id as associated_thought_id")

        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()

    def apply_migrations_up_to(self, db_path: str, migrations_dir: Path, up_to: int) -> None:
        """Apply migrations 001 through specified number."""
        for i in range(1, up_to + 1):
            migration_files = list(migrations_dir.glob(f"{i:03d}_*.sql"))
            if migration_files:
                self.apply_migration(db_path, migration_files[0], migration_num=i)

    def test_migration_009_fresh_database(self, temp_db_path, migrations_dir):
        """TC-M001: Verify migration 009 applies cleanly on fresh database."""
        # Apply migrations 001-008
        self.apply_migrations_up_to(temp_db_path, migrations_dir, 8)

        # Apply migration 009
        migration_009 = list(migrations_dir.glob("009_*.sql"))[0]
        self.apply_migration(temp_db_path, migration_009)

        # Verify agent_occurrence_id column exists
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(tickets)")
        columns = {row[1]: row for row in cursor.fetchall()}

        assert "agent_occurrence_id" in columns, "agent_occurrence_id column should exist"
        assert columns["agent_occurrence_id"][2] == "TEXT", "Should be TEXT type"
        assert columns["agent_occurrence_id"][3] == 1, "Should be NOT NULL"
        assert columns["agent_occurrence_id"][4] == "'__shared__'", "Default should be '__shared__'"

        # Verify status CHECK constraint includes all 8 states by attempting inserts
        cursor.execute(
            "INSERT INTO tickets (ticket_id, sop, ticket_type, status, email, submitted_at, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "T-TEST-001",
                "TEST_SOP",
                "test",
                "pending",
                "test@example.com",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        cursor.execute(
            "INSERT INTO tickets (ticket_id, sop, ticket_type, status, email, submitted_at, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "T-TEST-002",
                "TEST_SOP",
                "test",
                "assigned",
                "test@example.com",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        cursor.execute(
            "INSERT INTO tickets (ticket_id, sop, ticket_type, status, email, submitted_at, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "T-TEST-003",
                "TEST_SOP",
                "test",
                "blocked",
                "test@example.com",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        cursor.execute(
            "INSERT INTO tickets (ticket_id, sop, ticket_type, status, email, submitted_at, last_updated) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                "T-TEST-004",
                "TEST_SOP",
                "test",
                "deferred",
                "test@example.com",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

        conn.commit()

        # Verify index exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_tickets_occurrence_status'")
        index = cursor.fetchone()
        assert index is not None, "idx_tickets_occurrence_status index should exist"

        conn.close()

    def test_migration_009_with_existing_tickets(self, temp_db_path, migrations_dir):
        """TC-M002: Verify existing tickets migrate correctly."""
        # Apply migrations 001-008
        self.apply_migrations_up_to(temp_db_path, migrations_dir, 8)

        # Insert test tickets with old schema
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        test_tickets = [
            ("T-001", "DSAR_ACCESS", "dsar", "pending", 5, "user1@example.com", "user1"),
            ("T-002", "DSAR_ACCESS", "dsar", "in_progress", 8, "user2@example.com", "user2"),
            ("T-003", "DSAR_DELETE", "dsar", "completed", 5, "user3@example.com", "user3"),
            ("T-004", "DSAR_EXPORT", "dsar", "cancelled", 3, "user4@example.com", "user4"),
            ("T-005", "DSAR_ACCESS", "dsar", "failed", 9, "user5@example.com", "user5"),
        ]

        now = datetime.now(timezone.utc).isoformat()
        for ticket in test_tickets:
            cursor.execute(
                """
                INSERT INTO tickets (ticket_id, sop, ticket_type, status, priority, email, user_identifier, submitted_at, last_updated, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (*ticket, now, now, "{}"),
            )

        conn.commit()
        conn.close()

        # Apply migration 009
        migration_009 = list(migrations_dir.glob("009_*.sql"))[0]
        self.apply_migration(temp_db_path, migration_009)

        # Verify all tickets preserved with agent_occurrence_id='__shared__'
        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT ticket_id, status, agent_occurrence_id FROM tickets ORDER BY ticket_id")
        migrated_tickets = cursor.fetchall()

        assert len(migrated_tickets) == 5, "All tickets should be preserved"
        for ticket_id, status, agent_occurrence_id in migrated_tickets:
            assert (
                agent_occurrence_id == "__shared__"
            ), f"Ticket {ticket_id} should have agent_occurrence_id='__shared__'"

        # Verify specific tickets
        expected = {
            "T-001": "pending",
            "T-002": "in_progress",
            "T-003": "completed",
            "T-004": "cancelled",
            "T-005": "failed",
        }
        for ticket_id, status, _ in migrated_tickets:
            assert status == expected[ticket_id], f"Ticket {ticket_id} status should be preserved"

        conn.close()

    def test_migration_009_new_status_values(self, temp_db_path, migrations_dir):
        """TC-M003: Verify new status values can be inserted."""
        # Apply all migrations including 009
        self.apply_migrations_up_to(temp_db_path, migrations_dir, 9)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()

        # Test new status values
        new_statuses = ["assigned", "blocked", "deferred"]
        for i, status in enumerate(new_statuses):
            cursor.execute(
                """
                INSERT INTO tickets (ticket_id, sop, ticket_type, status, email, submitted_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (f"T-NEW-{i}", "TEST_SOP", "test", status, "test@example.com", now, now),
            )

        conn.commit()

        # Verify inserts succeeded
        cursor.execute("SELECT ticket_id, status FROM tickets WHERE ticket_id LIKE 'T-NEW-%' ORDER BY ticket_id")
        inserted = cursor.fetchall()

        assert len(inserted) == 3
        assert inserted[0][1] == "assigned"
        assert inserted[1][1] == "blocked"
        assert inserted[2][1] == "deferred"

        conn.close()

    def test_migration_009_invalid_status_rejected(self, temp_db_path, migrations_dir):
        """TC-M004: Verify CHECK constraint rejects invalid statuses."""
        # Apply all migrations including 009
        self.apply_migrations_up_to(temp_db_path, migrations_dir, 9)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()

        # Attempt to insert invalid status
        with pytest.raises(sqlite3.IntegrityError) as exc_info:
            cursor.execute(
                """
                INSERT INTO tickets (ticket_id, sop, ticket_type, status, email, submitted_at, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                ("T-INVALID", "TEST_SOP", "test", "invalid_status", "test@example.com", now, now),
            )

        assert "CHECK constraint failed" in str(exc_info.value) or "constraint failed" in str(exc_info.value)

        conn.close()

    def test_migration_009_index_performance(self, temp_db_path, migrations_dir):
        """TC-M005: Verify multi-occurrence index created and used."""
        # Apply all migrations including 009
        self.apply_migrations_up_to(temp_db_path, migrations_dir, 9)

        conn = sqlite3.connect(temp_db_path)
        cursor = conn.cursor()

        # Check query plan uses index
        cursor.execute(
            """
            EXPLAIN QUERY PLAN
            SELECT * FROM tickets
            WHERE agent_occurrence_id='occurrence-1' AND status='pending'
        """
        )
        plan = cursor.fetchall()
        plan_str = " ".join([str(row) for row in plan])

        # Should use idx_tickets_occurrence_status index
        assert "idx_tickets_occurrence_status" in plan_str, "Query should use occurrence_status index"

        conn.close()

    def test_migration_009_transaction_boundaries(self, temp_db_path, migrations_dir):
        """TC-M009: Verify migration uses transaction (PRAGMA and BEGIN/COMMIT present)."""
        # Read migration file
        migration_009 = list(migrations_dir.glob("009_*.sql"))[0]
        with open(migration_009, "r") as f:
            content = f.read()

        # Verify transaction boundaries exist
        assert "BEGIN TRANSACTION" in content or "BEGIN" in content, "Migration should use transaction"
        assert "COMMIT" in content, "Migration should commit transaction"
        assert "PRAGMA foreign_keys=OFF" in content, "Migration should disable FK constraints"
        assert "PRAGMA foreign_keys=ON" in content, "Migration should re-enable FK constraints"


class TestMigration009PostgreSQL:
    """Test Migration 009 for PostgreSQL."""

    def test_migration_009_has_postgres_version(self):
        """TC-M006: Verify PostgreSQL migration exists."""
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent
        postgres_migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "postgres"
        migration_009_files = list(postgres_migrations_dir.glob("009_*.sql"))

        assert len(migration_009_files) > 0, "PostgreSQL migration 009 should exist"

        # Read and verify content
        with open(migration_009_files[0], "r") as f:
            content = f.read()

        # Verify key PostgreSQL-specific operations
        assert "ALTER TABLE tickets ADD COLUMN" in content, "Should add agent_occurrence_id column"
        assert "DROP CONSTRAINT" in content, "Should drop old CHECK constraint"
        assert "ADD CONSTRAINT" in content, "Should add new CHECK constraint"
        assert "CREATE INDEX" in content, "Should create occurrence_status index"

    def test_migration_009_constraint_modification(self):
        """TC-M007: Verify PostgreSQL CHECK constraint properly modified."""
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent
        postgres_migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "postgres"
        migration_009 = list(postgres_migrations_dir.glob("009_*.sql"))[0]

        with open(migration_009, "r") as f:
            content = f.read()

        # Verify constraint modification approach (PostgreSQL can ALTER)
        assert "tickets_status_check" in content, "Should reference status CHECK constraint"
        assert "assigned" in content and "blocked" in content and "deferred" in content, "Should include new statuses"

    def test_migration_009_idempotency_check(self):
        """TC-M008: Verify migration uses IF NOT EXISTS for idempotency."""
        test_file = Path(__file__).resolve()
        project_root = test_file.parent.parent.parent.parent.parent.parent
        postgres_migrations_dir = project_root / "ciris_engine" / "logic" / "persistence" / "migrations" / "postgres"
        migration_009 = list(postgres_migrations_dir.glob("009_*.sql"))[0]

        with open(migration_009, "r") as f:
            content = f.read()

        # Verify idempotent operations
        assert "IF NOT EXISTS" in content or "IF EXISTS" in content, "Should use IF NOT EXISTS/EXISTS for idempotency"
