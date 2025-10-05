"""
Tests for extensive consolidation helper functions.

Ensures 80%+ coverage for extensive consolidation logic.
"""

from datetime import date, datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.extensive_helpers import (
    check_daily_summary_exists,
    create_daily_summary_attributes,
    create_daily_summary_node,
    maintain_temporal_chain_to_daily,
    query_basic_summaries_in_period,
)
from ciris_engine.schemas.services.graph_core import GraphNode, NodeType


class TestQueryBasicSummariesInPeriod:
    """Tests for query_basic_summaries_in_period function."""

    def test_queries_basic_summaries_correctly(self):
        """Should query basic summaries in period."""
        cursor = Mock()
        cursor.fetchall.return_value = [
            ("node1", "{}", "2023-10-01T00:00:00Z"),
            ("node2", "{}", "2023-10-01T06:00:00Z"),
        ]

        start = datetime(2023, 10, 1, tzinfo=timezone.utc)
        end = datetime(2023, 10, 7, tzinfo=timezone.utc)

        summaries = query_basic_summaries_in_period(cursor, "tsdb_summary", start, end)

        assert len(summaries) == 2
        assert all(len(s) == 3 for s in summaries)
        cursor.execute.assert_called_once()

    def test_returns_empty_list_when_no_summaries(self):
        """Should return empty list when no summaries found."""
        cursor = Mock()
        cursor.fetchall.return_value = []

        start = datetime(2023, 10, 1, tzinfo=timezone.utc)
        end = datetime(2023, 10, 7, tzinfo=timezone.utc)

        summaries = query_basic_summaries_in_period(cursor, "tsdb_summary", start, end)

        assert summaries == []


class TestCheckDailySummaryExists:
    """Tests for check_daily_summary_exists function."""

    def test_returns_true_when_summary_exists(self):
        """Should return True when summary exists."""
        cursor = Mock()
        cursor.fetchone.return_value = ("tsdb_summary_daily_20231001",)

        exists = check_daily_summary_exists(cursor, "tsdb_summary_daily_20231001")

        assert exists is True

    def test_returns_false_when_summary_does_not_exist(self):
        """Should return False when summary doesn't exist."""
        cursor = Mock()
        cursor.fetchone.return_value = None

        exists = check_daily_summary_exists(cursor, "tsdb_summary_daily_20231001")

        assert exists is False


class TestCreateDailySummaryAttributes:
    """Tests for create_daily_summary_attributes function."""

    def test_creates_basic_attributes(self):
        """Should create basic attributes for daily summary."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        day_summaries = [("node1", "{}"), ("node2", "{}")]
        metrics = {"cpu": {"count": 10, "sum": 5.0, "avg": 0.5, "min": 0.1, "max": 0.9}}
        resources = {"total_tokens": 1000, "total_cost_cents": 5.0}
        action_counts = {"speak": 10, "observe": 5}

        attrs = create_daily_summary_attributes(
            "tsdb_summary", day, day_summaries, metrics, resources, action_counts
        )

        assert attrs["consolidation_level"] == "extensive"
        assert attrs["source_summary_count"] == 2
        assert "period_start" in attrs
        assert "period_end" in attrs

    def test_creates_tsdb_specific_attributes(self):
        """Should create TSDB-specific attributes."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        day_summaries = [("node1", "{}")]
        metrics = {"cpu": {"count": 5, "sum": 2.5, "avg": 0.5, "min": 0.1, "max": 0.9}}
        resources = {
            "total_tokens": 1000,
            "total_cost_cents": 5.0,
            "total_carbon_grams": 0.1,
            "total_energy_kwh": 0.01,
            "error_count": 2,
        }
        action_counts = {"speak": 10, "observe": 5}

        attrs = create_daily_summary_attributes(
            "tsdb_summary", day, day_summaries, metrics, resources, action_counts
        )

        assert attrs["metrics"] == metrics
        assert attrs["total_tokens"] == 1000
        assert attrs["total_cost_cents"] == 5.0
        assert attrs["action_counts"] == action_counts
        assert attrs["error_count"] == 2
        assert "success_rate" in attrs

    def test_calculates_success_rate_correctly(self):
        """Should calculate success rate from error count and action counts."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        day_summaries = [("node1", "{}")]
        metrics = {}
        resources = {"error_count": 2}
        action_counts = {"speak": 8, "observe": 2}  # Total 10, 2 errors = 80% success

        attrs = create_daily_summary_attributes(
            "tsdb_summary", day, day_summaries, metrics, resources, action_counts
        )

        assert attrs["success_rate"] == pytest.approx(0.8)

    def test_handles_zero_actions_gracefully(self):
        """Should handle zero action counts without division error."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        day_summaries = [("node1", "{}")]
        metrics = {}
        resources = {"error_count": 0}
        action_counts = {}  # No actions

        attrs = create_daily_summary_attributes(
            "tsdb_summary", day, day_summaries, metrics, resources, action_counts
        )

        assert attrs["success_rate"] == 1.0

    def test_limits_source_summary_ids_to_10(self):
        """Should limit source_summary_ids to first 10."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        day_summaries = [(f"node{i}", "{}") for i in range(15)]  # 15 summaries
        metrics = {}
        resources = {}
        action_counts = {}

        attrs = create_daily_summary_attributes(
            "tsdb_summary", day, day_summaries, metrics, resources, action_counts
        )

        assert len(attrs["source_summary_ids"]) == 10
        assert attrs["source_summary_count"] == 15  # Count should still be 15


class TestCreateDailySummaryNode:
    """Tests for create_daily_summary_node function."""

    def test_creates_tsdb_summary_node(self):
        """Should create TSDB summary node."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        attrs = {"consolidation_level": "extensive"}
        now = datetime(2023, 10, 8, tzinfo=timezone.utc)

        node = create_daily_summary_node("tsdb_summary", day, attrs, now)

        assert isinstance(node, GraphNode)
        assert node.type == NodeType.TSDB_SUMMARY
        assert node.id == "tsdb_summary_daily_20231001"
        assert node.attributes == attrs
        assert node.updated_by == "tsdb_consolidation_extensive"

    def test_creates_audit_summary_node(self):
        """Should create audit summary node."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        attrs = {"consolidation_level": "extensive"}
        now = datetime.now(timezone.utc)

        node = create_daily_summary_node("audit_summary", day, attrs, now)

        assert node.type == NodeType.AUDIT_SUMMARY

    def test_creates_trace_summary_node(self):
        """Should create trace summary node."""
        day = datetime(2023, 10, 1, tzinfo=timezone.utc)
        attrs = {}
        now = datetime.now(timezone.utc)

        node = create_daily_summary_node("trace_summary", day, attrs, now)

        assert node.type == NodeType.TRACE_SUMMARY


class TestMaintainTemporalChainToDaily:
    """Tests for maintain_temporal_chain_to_daily function."""

    def test_creates_temporal_edges_when_6h_summary_exists(self):
        """Should create bidirectional temporal edges."""
        cursor = Mock()
        cursor.fetchone.return_value = ("tsdb_summary_20231001_18",)  # 6h summary exists

        period_start = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        edges_created = maintain_temporal_chain_to_daily(cursor, period_start)

        assert edges_created == 2
        # Should have called execute 4 times: 1 select + 1 delete + 2 inserts
        assert cursor.execute.call_count == 4

    def test_returns_zero_when_6h_summary_not_found(self):
        """Should return 0 when previous 6h summary doesn't exist."""
        cursor = Mock()
        cursor.fetchone.return_value = None  # Not found

        period_start = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        edges_created = maintain_temporal_chain_to_daily(cursor, period_start)

        assert edges_created == 0
        # Should only have called execute once for the SELECT
        assert cursor.execute.call_count == 1

    def test_deletes_self_referencing_edges(self):
        """Should delete self-referencing edges before creating new ones."""
        cursor = Mock()
        cursor.fetchone.return_value = ("tsdb_summary_20231001_18",)

        period_start = datetime(2023, 10, 2, 0, 0, tzinfo=timezone.utc)

        maintain_temporal_chain_to_daily(cursor, period_start)

        # Check that DELETE was called
        delete_calls = [call for call in cursor.execute.call_args_list if "DELETE" in str(call)]
        assert len(delete_calls) == 1
