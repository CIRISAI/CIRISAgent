"""
Tests for cleanup helper functions.

Ensures 80%+ coverage for all cleanup logic.
"""

import json
from unittest.mock import Mock

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.cleanup_helpers import (
    cleanup_audit_summary,
    cleanup_trace_summary,
    cleanup_tsdb_summary,
    delete_correlations_in_period,
    delete_nodes_in_period,
    parse_summary_period,
    should_cleanup_summary,
    validate_and_count_correlations,
    validate_and_count_nodes,
)


class TestValidateAndCountNodes:
    """Tests for validate_and_count_nodes function."""

    def test_counts_nodes_in_period(self):
        """Should count nodes correctly."""
        cursor = Mock()
        cursor.fetchone.return_value = (42,)

        count = validate_and_count_nodes(cursor, "tsdb_data", "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert count == 42
        cursor.execute.assert_called_once()

    def test_returns_zero_when_no_nodes(self):
        """Should return 0 when no nodes found."""
        cursor = Mock()
        cursor.fetchone.return_value = (0,)

        count = validate_and_count_nodes(cursor, "tsdb_data", "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert count == 0

    def test_returns_zero_when_fetchone_returns_none(self):
        """Should return 0 when fetchone returns None."""
        cursor = Mock()
        cursor.fetchone.return_value = None

        count = validate_and_count_nodes(cursor, "tsdb_data", "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert count == 0


class TestValidateAndCountCorrelations:
    """Tests for validate_and_count_correlations function."""

    def test_counts_correlations_in_period(self):
        """Should count correlations correctly."""
        cursor = Mock()
        cursor.fetchone.return_value = (15,)

        count = validate_and_count_correlations(cursor, "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert count == 15

    def test_returns_zero_when_fetchone_returns_none(self):
        """Should return 0 when fetchone returns None."""
        cursor = Mock()
        cursor.fetchone.return_value = None

        count = validate_and_count_correlations(cursor, "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert count == 0


class TestDeleteNodesInPeriod:
    """Tests for delete_nodes_in_period function."""

    def test_deletes_nodes_and_returns_count(self):
        """Should delete nodes and return rowcount."""
        cursor = Mock()
        cursor.rowcount = 10

        deleted = delete_nodes_in_period(cursor, "tsdb_data", "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert deleted == 10
        # CRITICAL: delete_nodes_in_period calls execute TWICE (edges first, then nodes)
        assert cursor.execute.call_count == 2

    def test_returns_zero_when_no_rows_deleted(self):
        """Should return 0 when no rows deleted."""
        cursor = Mock()
        cursor.rowcount = 0

        deleted = delete_nodes_in_period(cursor, "tsdb_data", "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert deleted == 0


class TestDeleteCorrelationsInPeriod:
    """Tests for delete_correlations_in_period function."""

    def test_deletes_correlations_and_returns_count(self):
        """Should delete correlations and return rowcount."""
        cursor = Mock()
        cursor.rowcount = 5

        deleted = delete_correlations_in_period(cursor, "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert deleted == 5

    def test_returns_zero_when_no_rows_deleted(self):
        """Should return 0 when no rows deleted."""
        cursor = Mock()
        cursor.rowcount = 0

        deleted = delete_correlations_in_period(cursor, "2023-10-01T00:00:00+00:00", "2023-10-02T00:00:00+00:00")

        assert deleted == 0


class TestParseSummaryPeriod:
    """Tests for parse_summary_period function."""

    def test_parses_valid_json(self):
        """Should parse valid JSON with period fields."""
        attrs_json = json.dumps(
            {
                "period_start": "2023-10-01T00:00:00+00:00",
                "period_end": "2023-10-02T00:00:00+00:00",
            }
        )

        start, end = parse_summary_period(attrs_json)

        assert start == "2023-10-01T00:00:00+00:00"
        assert end == "2023-10-02T00:00:00+00:00"

    def test_returns_none_for_missing_fields(self):
        """Should return None when fields are missing."""
        attrs_json = json.dumps({"other_field": "value"})

        start, end = parse_summary_period(attrs_json)

        assert start is None
        assert end is None

    def test_returns_none_for_null_json(self):
        """Should return None for None input."""
        start, end = parse_summary_period(None)

        assert start is None
        assert end is None

    def test_returns_none_for_empty_json(self):
        """Should return None for empty string."""
        start, end = parse_summary_period("")

        assert start is None
        assert end is None

    def test_handles_invalid_json(self):
        """Should return None for invalid JSON."""
        start, end = parse_summary_period("not-valid-json")

        assert start is None
        assert end is None


class TestShouldCleanupSummary:
    """Tests for should_cleanup_summary function."""

    def test_returns_true_when_counts_match_and_positive(self):
        """Should return True when claimed matches actual and > 0."""
        assert should_cleanup_summary(10, 10) is True
        assert should_cleanup_summary(1, 1) is True
        assert should_cleanup_summary(100, 100) is True

    def test_returns_false_when_counts_mismatch(self):
        """Should return False when counts don't match."""
        assert should_cleanup_summary(10, 9) is False
        assert should_cleanup_summary(10, 11) is False
        assert should_cleanup_summary(5, 0) is False

    def test_returns_false_when_actual_is_zero(self):
        """Should return False when actual count is 0."""
        assert should_cleanup_summary(0, 0) is False
        assert should_cleanup_summary(10, 0) is False

    def test_returns_false_when_actual_is_negative(self):
        """Should return False for negative counts."""
        assert should_cleanup_summary(10, -1) is False


class TestCleanupTsdbSummary:
    """Tests for cleanup_tsdb_summary function."""

    def test_cleans_up_when_counts_match(self):
        """Should cleanup nodes when counts match."""
        cursor = Mock()
        cursor.fetchone.return_value = (10,)  # Actual count
        cursor.rowcount = 10  # Deleted count

        attrs = {
            "source_node_count": 10,
            "period_start": "2023-10-01T00:00:00+00:00",
            "period_end": "2023-10-02T00:00:00+00:00",
        }

        deleted = cleanup_tsdb_summary(cursor, "summary_123", json.dumps(attrs))

        assert deleted == 10
        # 1 count query + 2 delete calls (edges + nodes) = 3 total
        assert cursor.execute.call_count == 3

    def test_does_not_cleanup_when_counts_mismatch(self):
        """Should not cleanup when counts don't match."""
        cursor = Mock()
        cursor.fetchone.return_value = (5,)  # Actual count (mismatch)

        attrs = {
            "source_node_count": 10,  # Claimed
            "period_start": "2023-10-01T00:00:00+00:00",
            "period_end": "2023-10-02T00:00:00+00:00",
        }

        deleted = cleanup_tsdb_summary(cursor, "summary_123", json.dumps(attrs))

        assert deleted == 0
        assert cursor.execute.call_count == 1  # Only count, no delete

    def test_returns_zero_when_no_period_data(self):
        """Should return 0 when period data is missing."""
        cursor = Mock()

        deleted = cleanup_tsdb_summary(cursor, "summary_123", json.dumps({}))

        assert deleted == 0

    def test_handles_null_attrs_json(self):
        """Should handle None attrs_json."""
        cursor = Mock()

        deleted = cleanup_tsdb_summary(cursor, "summary_123", None)

        assert deleted == 0


class TestCleanupAuditSummary:
    """Tests for cleanup_audit_summary function."""

    def test_cleans_up_audit_entries_when_counts_match(self):
        """Should cleanup audit_entry nodes when counts match."""
        cursor = Mock()
        cursor.fetchone.return_value = (5,)
        cursor.rowcount = 5

        attrs = {
            "source_node_count": 5,
            "period_start": "2023-10-01T00:00:00+00:00",
            "period_end": "2023-10-02T00:00:00+00:00",
        }

        deleted = cleanup_audit_summary(cursor, "audit_summary_123", json.dumps(attrs))

        assert deleted == 5
        # 1 count query + 2 delete calls (edges + nodes) = 3 total
        assert cursor.execute.call_count == 3

    def test_does_not_cleanup_when_counts_mismatch(self):
        """Should not cleanup when counts mismatch."""
        cursor = Mock()
        cursor.fetchone.return_value = (3,)

        attrs = {
            "source_node_count": 5,
            "period_start": "2023-10-01T00:00:00+00:00",
            "period_end": "2023-10-02T00:00:00+00:00",
        }

        deleted = cleanup_audit_summary(cursor, "audit_summary_123", json.dumps(attrs))

        assert deleted == 0

    def test_handles_missing_period_data(self):
        """Should return 0 when period data missing."""
        cursor = Mock()

        deleted = cleanup_audit_summary(cursor, "audit_summary_123", json.dumps({}))

        assert deleted == 0


class TestCleanupTraceSummary:
    """Tests for cleanup_trace_summary function."""

    def test_cleans_up_correlations_when_counts_match(self):
        """Should cleanup correlations when counts match."""
        cursor = Mock()
        cursor.fetchone.return_value = (15,)
        cursor.rowcount = 15

        attrs = {
            "source_correlation_count": 15,
            "period_start": "2023-10-01T00:00:00+00:00",
            "period_end": "2023-10-02T00:00:00+00:00",
        }

        deleted = cleanup_trace_summary(cursor, "trace_summary_123", json.dumps(attrs))

        assert deleted == 15
        assert cursor.execute.call_count == 2

    def test_does_not_cleanup_when_counts_mismatch(self):
        """Should not cleanup when counts mismatch."""
        cursor = Mock()
        cursor.fetchone.return_value = (10,)

        attrs = {
            "source_correlation_count": 15,
            "period_start": "2023-10-01T00:00:00+00:00",
            "period_end": "2023-10-02T00:00:00+00:00",
        }

        deleted = cleanup_trace_summary(cursor, "trace_summary_123", json.dumps(attrs))

        assert deleted == 0

    def test_handles_missing_period_data(self):
        """Should return 0 when period data missing."""
        cursor = Mock()

        deleted = cleanup_trace_summary(cursor, "trace_summary_123", json.dumps({}))

        assert deleted == 0
