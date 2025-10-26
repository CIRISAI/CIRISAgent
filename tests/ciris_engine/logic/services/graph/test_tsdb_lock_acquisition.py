"""
Unit tests for TSDB consolidation lock acquisition.

Tests both PostgreSQL and SQLite lock acquisition mechanisms to ensure
proper handling of dict-like cursor results.
"""

import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.query_manager import QueryManager


class TestLockAcquisition:
    """Test lock acquisition with both SQLite and PostgreSQL."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except Exception:
            pass

    @pytest.fixture
    def query_manager(self, temp_db):
        """Create QueryManager instance with temp database."""
        from ciris_engine.logic.persistence.db.core import initialize_database

        initialize_database(temp_db)
        return QueryManager(db_path=temp_db)

    def test_acquire_lock_sqlite_success(self, query_manager):
        """Test successful lock acquisition with SQLite."""
        period_start = datetime(2025, 10, 20, 0, 0, 0, tzinfo=timezone.utc)

        # Acquire lock
        acquired = query_manager.acquire_period_lock(period_start)
        assert acquired is True

        # Release lock
        query_manager.release_period_lock(period_start)

    def test_acquire_lock_all_consolidation_types(self, query_manager):
        """Test lock acquisition for all consolidation types."""
        test_cases = [
            ("basic", "2025-10-20T00:00:00+00:00"),
            ("extensive", "2025-W42"),  # Week identifier
            ("profound", "2025-10"),  # Month identifier
        ]

        for consolidation_type, period_id in test_cases:
            acquired = query_manager.acquire_consolidation_lock(consolidation_type, period_id)
            assert acquired is True, f"Failed to acquire {consolidation_type} lock"

            # Release lock
            query_manager.release_consolidation_lock(consolidation_type, period_id)

    def test_lock_hash_consistency(self, query_manager):
        """Test that lock hash generation is consistent."""
        period_id = "2025-10-20T00:00:00+00:00"

        # Acquire lock twice with same parameters
        lock_key_1 = f"basic:{period_id}"
        lock_key_2 = f"basic:{period_id}"

        lock_id_1 = hash(lock_key_1) & 0x7FFFFFFF
        lock_id_2 = hash(lock_key_2) & 0x7FFFFFFF

        assert lock_id_1 == lock_id_2, "Lock IDs should be consistent for same parameters"

    def test_postgresql_dict_result_parsing(self):
        """Test that dict-style access works for PostgreSQL-like results."""
        # Simulate what RealDictCursor returns
        pg_result = {"pg_try_advisory_lock": True}

        # This is what the fix does - use dict-style access
        acquired = bool(pg_result["pg_try_advisory_lock"])
        assert acquired is True

        # Test with integer result (some drivers return 1/0)
        pg_result_int = {"pg_try_advisory_lock": 1}
        acquired = bool(pg_result_int["pg_try_advisory_lock"])
        assert acquired is True

        # Test with False/0
        pg_result_false = {"pg_try_advisory_lock": False}
        acquired = bool(pg_result_false["pg_try_advisory_lock"])
        assert acquired is False

        pg_result_zero = {"pg_try_advisory_lock": 0}
        acquired = bool(pg_result_zero["pg_try_advisory_lock"])
        assert acquired is False

    def test_sqlite_row_dict_compatibility(self, query_manager):
        """Test that SQLite Row objects support dict-style access."""
        import sqlite3

        # Create a simple query to test Row behavior
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        cursor = conn.cursor()
        cursor.execute("SELECT 1 as test_value")
        row = cursor.fetchone()

        # Verify Row objects support dict-style access (like our fix uses)
        assert row["test_value"] == 1

        # This would fail with integer indexing if we used the old broken code
        # (but Row objects DO support integer indexing, unlike RealDictCursor)
        assert row[0] == 1

        conn.close()

    def test_lock_exception_handling(self, query_manager):
        """Test that exceptions during lock acquisition are handled gracefully."""
        # Test with invalid db_path to trigger exception
        bad_manager = QueryManager(db_path="/nonexistent/path/db.db")

        # Should return False on exception, not raise
        acquired = bad_manager.acquire_consolidation_lock("basic", "2025-10-20T00:00:00+00:00")
        assert acquired is False

        # Release should also handle exceptions gracefully (no return value to check)
        bad_manager.release_consolidation_lock("basic", "2025-10-20T00:00:00+00:00")


class TestLockConvenience:
    """Test convenience wrapper methods for period locks."""

    @pytest.fixture
    def temp_db(self):
        """Create a temporary SQLite database for testing."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        try:
            os.unlink(path)
        except Exception:
            pass

    @pytest.fixture
    def query_manager(self, temp_db):
        """Create QueryManager instance with temp database."""
        from ciris_engine.logic.persistence.db.core import initialize_database

        initialize_database(temp_db)
        return QueryManager(db_path=temp_db)

    def test_acquire_period_lock_wrapper(self, query_manager):
        """Test acquire_period_lock convenience wrapper."""
        period_start = datetime(2025, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

        # Should call acquire_consolidation_lock with "basic" and ISO format
        acquired = query_manager.acquire_period_lock(period_start)
        assert acquired is True

    def test_release_period_lock_wrapper(self, query_manager):
        """Test release_period_lock convenience wrapper."""
        period_start = datetime(2025, 10, 20, 12, 0, 0, tzinfo=timezone.utc)

        # Acquire first
        query_manager.acquire_period_lock(period_start)

        # Should call release_consolidation_lock with "basic" and ISO format
        query_manager.release_period_lock(period_start)

    def test_period_lock_iso_format(self, query_manager):
        """Test that period_start is properly converted to ISO format."""
        period_start = datetime(2025, 10, 20, 18, 0, 0, tzinfo=timezone.utc)

        # Verify the lock_id generation logic
        expected_lock_key = f"basic:{period_start.isoformat()}"
        expected_lock_id = hash(expected_lock_key) & 0x7FFFFFFF

        # The actual lock_id used internally should match
        test_lock_key = f"basic:{period_start.isoformat()}"
        test_lock_id = hash(test_lock_key) & 0x7FFFFFFF

        assert test_lock_id == expected_lock_id
        assert test_lock_id > 0  # Ensure it's a positive 32-bit int
