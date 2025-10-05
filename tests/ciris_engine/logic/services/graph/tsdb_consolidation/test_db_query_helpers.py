"""
Tests for database query helper functions.

Ensures 80%+ coverage with mocked database cursors.
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock

from ciris_engine.logic.services.graph.tsdb_consolidation.db_query_helpers import (
    query_summaries_in_period,
    query_all_summary_types_in_period,
    query_expired_summaries,
    update_summary_consolidation_level,
    count_nodes_in_period,
)


class TestQuerySummariesInPeriod:
    """Tests for query_summaries_in_period function."""

    def test_queries_basic_summaries_successfully(self):
        """Should query basic summaries within period."""
        cursor = Mock()
        cursor.fetchall.return_value = [
            ("node_1", '{"period_start": "2023-10-01T00:00:00+00:00"}', "2023-10-01T00:00:00+00:00"),
            ("node_2", '{"period_start": "2023-10-01T06:00:00+00:00"}', "2023-10-01T06:00:00+00:00"),
        ]

        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        result = query_summaries_in_period(cursor, "tsdb_summary", start, end, "basic")

        assert len(result) == 2
        assert result[0][0] == "node_1"
        cursor.execute.assert_called_once()

    def test_raises_on_empty_summary_type(self):
        """Should raise ValueError for empty summary_type."""
        cursor = Mock()
        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="cannot be empty"):
            query_summaries_in_period(cursor, "", start, end)

    def test_raises_on_naive_datetime(self):
        """Should raise ValueError for naive datetime."""
        cursor = Mock()
        naive_start = datetime(2023, 10, 1, 0, 0)  # No tzinfo
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="timezone-aware"):
            query_summaries_in_period(cursor, "tsdb_summary", naive_start, end)

    def test_raises_when_start_after_end(self):
        """Should raise ValueError when period_start >= period_end."""
        cursor = Mock()
        start = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="must be before"):
            query_summaries_in_period(cursor, "tsdb_summary", start, end)

    def test_executes_correct_sql_query(self):
        """Should execute SQL with correct parameters."""
        cursor = Mock()
        cursor.fetchall.return_value = []

        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        query_summaries_in_period(cursor, "audit_summary", start, end, "daily")

        # Verify SQL was called with correct params
        call_args = cursor.execute.call_args
        assert "audit_summary" in call_args[0][1]
        assert start.isoformat() in call_args[0][1]
        assert end.isoformat() in call_args[0][1]
        assert "daily" in call_args[0][1]


class TestQueryAllSummaryTypesInPeriod:
    """Tests for query_all_summary_types_in_period function."""

    def test_queries_all_summary_types(self):
        """Should query all 5 summary types."""
        cursor = Mock()
        # Return different results for each summary type
        cursor.fetchall.side_effect = [
            [("tsdb_1", '{}', "2023-10-01T00:00:00+00:00")],  # tsdb_summary
            [("audit_1", '{}', "2023-10-01T00:00:00+00:00")],  # audit_summary
            [],  # trace_summary (empty)
            [("conv_1", '{}', "2023-10-01T00:00:00+00:00")],  # conversation_summary
            [],  # task_summary (empty)
        ]

        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        result = query_all_summary_types_in_period(cursor, start, end)

        assert "tsdb_summary" in result
        assert "audit_summary" in result
        assert "conversation_summary" in result
        assert "trace_summary" not in result  # Empty results not included
        assert "task_summary" not in result
        assert len(result) == 3

    def test_raises_on_naive_datetime(self):
        """Should raise ValueError for naive datetime."""
        cursor = Mock()
        naive_start = datetime(2023, 10, 1, 0, 0)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="timezone-aware"):
            query_all_summary_types_in_period(cursor, naive_start, end)

    def test_returns_empty_dict_when_no_summaries(self):
        """Should return empty dict when no summaries found."""
        cursor = Mock()
        cursor.fetchall.return_value = []

        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        result = query_all_summary_types_in_period(cursor, start, end)

        assert result == {}


class TestQueryExpiredSummaries:
    """Tests for query_expired_summaries function."""

    def test_queries_expired_summaries(self):
        """Should query summaries with period_end before cutoff."""
        cursor = Mock()
        cursor.fetchall.return_value = [
            ("node_1", "tsdb_summary", '{"period_end": "2023-09-01T00:00:00+00:00"}'),
            ("node_2", "audit_summary", '{"period_end": "2023-09-15T00:00:00+00:00"}'),
        ]

        cutoff = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        result = query_expired_summaries(cursor, cutoff)

        assert len(result) == 2
        assert result[0][0] == "node_1"
        cursor.execute.assert_called_once()

    def test_raises_on_naive_datetime(self):
        """Should raise ValueError for naive cutoff_date."""
        cursor = Mock()
        naive_cutoff = datetime(2023, 10, 1, 0, 0)

        with pytest.raises(ValueError, match="timezone-aware"):
            query_expired_summaries(cursor, naive_cutoff)


class TestUpdateSummaryConsolidationLevel:
    """Tests for update_summary_consolidation_level function."""

    def test_updates_consolidation_level_successfully(self):
        """Should update consolidation_level in attributes."""
        cursor = Mock()
        existing_attrs = {"period_start": "2023-10-01", "consolidation_level": "basic"}
        cursor.fetchone.return_value = (json.dumps(existing_attrs),)

        update_summary_consolidation_level(cursor, "node_123", "consolidated")

        # Should read current attributes
        assert cursor.fetchone.called

        # Should update with new level
        update_call = cursor.execute.call_args_list[1]  # Second call is the UPDATE
        updated_attrs_json = update_call[0][1][0]
        updated_attrs = json.loads(updated_attrs_json)
        assert updated_attrs["consolidation_level"] == "consolidated"
        assert updated_attrs["period_start"] == "2023-10-01"  # Preserved

    def test_raises_on_empty_node_id(self):
        """Should raise ValueError for empty node_id."""
        cursor = Mock()

        with pytest.raises(ValueError, match="cannot be empty"):
            update_summary_consolidation_level(cursor, "", "consolidated")

    def test_raises_on_empty_new_level(self):
        """Should raise ValueError for empty new_level."""
        cursor = Mock()

        with pytest.raises(ValueError, match="cannot be empty"):
            update_summary_consolidation_level(cursor, "node_123", "")

    def test_raises_when_node_not_found(self):
        """Should raise ValueError when node doesn't exist."""
        cursor = Mock()
        cursor.fetchone.return_value = None

        with pytest.raises(ValueError, match="not found"):
            update_summary_consolidation_level(cursor, "nonexistent", "consolidated")

    def test_handles_null_attributes(self):
        """Should handle node with null attributes_json."""
        cursor = Mock()
        cursor.fetchone.return_value = (None,)

        update_summary_consolidation_level(cursor, "node_123", "consolidated")

        # Should create new attributes dict
        update_call = cursor.execute.call_args_list[1]
        updated_attrs_json = update_call[0][1][0]
        updated_attrs = json.loads(updated_attrs_json)
        assert updated_attrs["consolidation_level"] == "consolidated"


class TestCountNodesInPeriod:
    """Tests for count_nodes_in_period function."""

    def test_counts_nodes_in_period(self):
        """Should count nodes within time period."""
        cursor = Mock()
        cursor.fetchone.return_value = (42,)

        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        count = count_nodes_in_period(cursor, "tsdb_data", start, end)

        assert count == 42
        cursor.execute.assert_called_once()

    def test_returns_zero_when_no_nodes(self):
        """Should return 0 when no nodes found."""
        cursor = Mock()
        cursor.fetchone.return_value = (0,)

        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        count = count_nodes_in_period(cursor, "tsdb_data", start, end)

        assert count == 0

    def test_returns_zero_when_fetchone_returns_none(self):
        """Should return 0 when fetchone returns None."""
        cursor = Mock()
        cursor.fetchone.return_value = None

        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        count = count_nodes_in_period(cursor, "tsdb_data", start, end)

        assert count == 0

    def test_raises_on_empty_node_type(self):
        """Should raise ValueError for empty node_type."""
        cursor = Mock()
        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="cannot be empty"):
            count_nodes_in_period(cursor, "", start, end)

    def test_raises_on_naive_datetime(self):
        """Should raise ValueError for naive datetime."""
        cursor = Mock()
        naive_start = datetime(2023, 10, 1, 0, 0)
        end = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        with pytest.raises(ValueError, match="timezone-aware"):
            count_nodes_in_period(cursor, "tsdb_data", naive_start, end)
