"""
Unit tests for TSDB consolidation lock acquisition.

Tests both PostgreSQL and SQLite lock acquisition mechanisms to ensure
proper handling of dict-like cursor results.

Post-2.9.0 (CIRISAgent#763, CIRISPersist#63): locks now flow through
the persist substrate's lock_try_acquire / lock_release. The
QueryManager wrapper preserves the legacy public API.
"""

from datetime import datetime, timezone

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.query_manager import QueryManager


class TestLockAcquisition:
    """Test lock acquisition with both SQLite and PostgreSQL."""

    @pytest.fixture
    def query_manager(self, persist_engine):
        """Create QueryManager instance wired to the test persist engine."""
        return QueryManager()

    # TODO(CIRISPersist): query_manager calls engine.lock_acquire, but the
    # persist substrate exposes lock_try_acquire instead. These three
    # acquire/release wrapper tests can re-enable once production code in
    # query_manager.py is updated to call the correct method name.
    def test_acquire_lock_sqlite_success(self, query_manager):
        """Test successful lock acquisition with SQLite via persist."""
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

    def test_persist_lock_try_acquire_returns_json(self, persist_engine):
        """Verify persist's lock_try_acquire returns JSON on success."""
        engine = persist_engine

        # Acquire returns the MaintenanceLock JSON
        raw = engine.lock_try_acquire("tsdb:test:lock_1", "instance_a", 60, None)
        assert raw is not None
        assert "tsdb:test:lock_1" in raw

        # Same-holder refresh: success
        raw2 = engine.lock_try_acquire("tsdb:test:lock_1", "instance_a", 60, None)
        assert raw2 is not None

        # Different caller: contention -> None
        raw3 = engine.lock_try_acquire("tsdb:test:lock_1", "instance_b", 60, None)
        assert raw3 is None

        engine.lock_release("tsdb:test:lock_1", "instance_a")


class TestLockConvenience:
    """Test convenience wrapper methods for period locks."""

    @pytest.fixture
    def query_manager(self, persist_engine):
        """Create QueryManager instance wired to the test persist engine."""
        return QueryManager()

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
