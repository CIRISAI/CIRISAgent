"""
Tests for aggregation helper functions.

Ensures 80%+ coverage for all aggregation logic.
"""

import json
from datetime import date, datetime, timezone

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.aggregation_helpers import (
    MetricStats,
    ResourceTotals,
    aggregate_action_counts,
    aggregate_metric_stats,
    aggregate_resource_usage,
    create_aggregated_summary_attributes,
    group_summaries_by_day,
    group_summaries_by_month,
    parse_summary_attributes,
)


class TestMetricStats:
    """Tests for MetricStats class."""

    def test_initialization(self):
        """Should initialize with correct defaults."""
        stats = MetricStats()
        assert stats.count == 0
        assert stats.sum == 0.0
        assert stats.min == float("inf")
        assert stats.max == float("-inf")
        assert stats.avg == 0.0

    def test_to_dict_with_infinity_values(self):
        """Should convert infinity values to 0 in dict."""
        stats = MetricStats()
        result = stats.to_dict()

        assert result["min"] == 0.0
        assert result["max"] == 0.0
        assert result["count"] == 0
        assert result["sum"] == 0.0
        assert result["avg"] == 0.0

    def test_to_dict_with_real_values(self):
        """Should preserve real values in dict."""
        stats = MetricStats()
        stats.count = 10
        stats.sum = 50.0
        stats.min = 1.0
        stats.max = 10.0
        stats.avg = 5.0

        result = stats.to_dict()
        assert result["count"] == 10
        assert result["sum"] == 50.0
        assert result["min"] == 1.0
        assert result["max"] == 10.0
        assert result["avg"] == 5.0


class TestResourceTotals:
    """Tests for ResourceTotals class."""

    def test_initialization(self):
        """Should initialize with zero values."""
        totals = ResourceTotals()
        assert totals.total_tokens == 0
        assert totals.total_cost_cents == 0.0
        assert totals.total_carbon_grams == 0.0
        assert totals.total_energy_kwh == 0.0
        assert totals.error_count == 0

    def test_to_dict(self):
        """Should convert to dictionary correctly."""
        totals = ResourceTotals()
        totals.total_tokens = 1000
        totals.total_cost_cents = 5.5
        totals.error_count = 3

        result = totals.to_dict()
        assert result["total_tokens"] == 1000
        assert result["total_cost_cents"] == 5.5
        assert result["error_count"] == 3
        assert result["total_carbon_grams"] == 0.0


class TestAggregateMetricStats:
    """Tests for aggregate_metric_stats function."""

    def test_aggregates_dict_format_metrics(self):
        """Should aggregate metrics in dict format."""
        summaries = [
            {"metrics": {"cpu": {"count": 2, "sum": 1.5, "min": 0.5, "max": 1.0}}},
            {"metrics": {"cpu": {"count": 1, "sum": 0.8, "min": 0.8, "max": 0.8}}},
        ]

        result = aggregate_metric_stats(summaries)

        assert result["cpu"]["count"] == 3
        assert result["cpu"]["sum"] == pytest.approx(2.3)
        assert result["cpu"]["min"] == 0.5
        assert result["cpu"]["max"] == 1.0
        assert result["cpu"]["avg"] == pytest.approx(2.3 / 3)

    def test_aggregates_single_value_format_metrics(self):
        """Should aggregate metrics in old single-value format."""
        summaries = [
            {"metrics": {"memory": 100}},
            {"metrics": {"memory": 200}},
            {"metrics": {"memory": 150}},
        ]

        result = aggregate_metric_stats(summaries)

        assert result["memory"]["count"] == 3
        assert result["memory"]["sum"] == 450
        assert result["memory"]["min"] == 100
        assert result["memory"]["max"] == 200
        assert result["memory"]["avg"] == 150

    def test_handles_mixed_format_metrics(self):
        """Should handle mix of dict and single-value formats."""
        summaries = [
            {"metrics": {"cpu": {"count": 2, "sum": 1.5, "min": 0.5, "max": 1.0}}},
            {"metrics": {"cpu": 0.75}},
        ]

        result = aggregate_metric_stats(summaries)

        assert result["cpu"]["count"] == 3
        assert result["cpu"]["sum"] == pytest.approx(2.25)
        assert result["cpu"]["min"] == 0.5
        assert result["cpu"]["max"] == 1.0

    def test_aggregates_multiple_metrics(self):
        """Should aggregate multiple different metrics."""
        summaries = [
            {"metrics": {"cpu": 0.5, "memory": 100}},
            {"metrics": {"cpu": 0.8, "memory": 200, "disk": 50}},
        ]

        result = aggregate_metric_stats(summaries)

        assert "cpu" in result
        assert "memory" in result
        assert "disk" in result
        assert result["disk"]["count"] == 1

    def test_returns_empty_dict_for_no_metrics(self):
        """Should return empty dict when no metrics."""
        summaries = [{"no_metrics": True}]
        result = aggregate_metric_stats(summaries)
        assert result == {}

    def test_handles_empty_summaries_list(self):
        """Should handle empty summaries list."""
        result = aggregate_metric_stats([])
        assert result == {}


class TestAggregateResourceUsage:
    """Tests for aggregate_resource_usage function."""

    def test_aggregates_all_resource_fields(self):
        """Should aggregate all resource usage fields."""
        summaries = [
            {
                "total_tokens": 100,
                "total_cost_cents": 0.5,
                "total_carbon_grams": 0.1,
                "total_energy_kwh": 0.01,
                "error_count": 1,
            },
            {
                "total_tokens": 200,
                "total_cost_cents": 1.0,
                "total_carbon_grams": 0.2,
                "total_energy_kwh": 0.02,
                "error_count": 2,
            },
        ]

        result = aggregate_resource_usage(summaries)

        assert result["total_tokens"] == 300
        assert result["total_cost_cents"] == 1.5
        assert result["total_carbon_grams"] == pytest.approx(0.3)
        assert result["total_energy_kwh"] == pytest.approx(0.03)
        assert result["error_count"] == 3

    def test_handles_missing_fields(self):
        """Should handle missing resource fields."""
        summaries = [
            {"total_tokens": 100},
            {"total_cost_cents": 0.5},
        ]

        result = aggregate_resource_usage(summaries)

        assert result["total_tokens"] == 100
        assert result["total_cost_cents"] == 0.5
        assert result["total_carbon_grams"] == 0.0
        assert result["error_count"] == 0

    def test_handles_empty_summaries(self):
        """Should return zeros for empty summaries."""
        result = aggregate_resource_usage([])

        assert result["total_tokens"] == 0
        assert result["total_cost_cents"] == 0.0


class TestAggregateActionCounts:
    """Tests for aggregate_action_counts function."""

    def test_aggregates_action_counts(self):
        """Should aggregate action counts correctly."""
        summaries = [
            {"action_counts": {"speak": 5, "observe": 3}},
            {"action_counts": {"speak": 2, "tool": 1}},
            {"action_counts": {"observe": 1}},
        ]

        result = aggregate_action_counts(summaries)

        assert result["speak"] == 7
        assert result["observe"] == 4
        assert result["tool"] == 1

    def test_handles_missing_action_counts(self):
        """Should handle summaries without action_counts."""
        summaries = [
            {"action_counts": {"speak": 5}},
            {"no_actions": True},
        ]

        result = aggregate_action_counts(summaries)
        assert result["speak"] == 5

    def test_returns_empty_dict_for_empty_summaries(self):
        """Should return empty dict for empty summaries."""
        result = aggregate_action_counts([])
        assert result == {}


class TestGroupSummariesByDay:
    """Tests for group_summaries_by_day function."""

    def test_groups_by_day_correctly(self):
        """Should group summaries by date."""
        summaries = [
            ("node1", "{}", "2023-10-01T00:00:00Z"),
            ("node2", "{}", "2023-10-01T06:00:00Z"),
            ("node3", "{}", "2023-10-02T00:00:00Z"),
        ]

        grouped = group_summaries_by_day(summaries)

        assert len(grouped[date(2023, 10, 1)]) == 2
        assert len(grouped[date(2023, 10, 2)]) == 1
        assert grouped[date(2023, 10, 1)][0][0] == "node1"

    def test_handles_utc_offset_format(self):
        """Should handle +00:00 format."""
        summaries = [
            ("node1", "{}", "2023-10-01T12:00:00+00:00"),
        ]

        grouped = group_summaries_by_day(summaries)
        assert len(grouped[date(2023, 10, 1)]) == 1

    def test_skips_entries_without_period_start(self):
        """Should skip entries with None period_start."""
        summaries = [
            ("node1", "{}", "2023-10-01T00:00:00Z"),
            ("node2", "{}", None),
        ]

        grouped = group_summaries_by_day(summaries)
        assert len(grouped[date(2023, 10, 1)]) == 1

    def test_returns_empty_dict_for_empty_input(self):
        """Should return empty dict for empty input."""
        result = group_summaries_by_day([])
        assert result == {}


class TestGroupSummariesByMonth:
    """Tests for group_summaries_by_month function."""

    def test_groups_by_month_correctly(self):
        """Should group summaries by month."""
        summaries = [
            ("node1", "{}", "2023-10-01T00:00:00Z"),
            ("node2", "{}", "2023-10-15T00:00:00Z"),
            ("node3", "{}", "2023-11-01T00:00:00Z"),
        ]

        grouped = group_summaries_by_month(summaries)

        assert len(grouped[(2023, 10)]) == 2
        assert len(grouped[(2023, 11)]) == 1

    def test_handles_year_boundary(self):
        """Should handle year boundaries correctly."""
        summaries = [
            ("node1", "{}", "2023-12-31T23:59:00Z"),
            ("node2", "{}", "2024-01-01T00:00:00Z"),
        ]

        grouped = group_summaries_by_month(summaries)

        assert len(grouped[(2023, 12)]) == 1
        assert len(grouped[(2024, 1)]) == 1

    def test_returns_empty_dict_for_empty_input(self):
        """Should return empty dict for empty input."""
        result = group_summaries_by_month([])
        assert result == {}


class TestCreateAggregatedSummaryAttributes:
    """Tests for create_aggregated_summary_attributes function."""

    def test_creates_tsdb_summary_attributes(self):
        """Should create attributes for tsdb_summary."""
        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 1, 23, 59, 59, tzinfo=timezone.utc)
        metrics = {"cpu": {"count": 10, "sum": 5.0, "avg": 0.5, "min": 0.1, "max": 0.9}}
        resources = {"total_tokens": 1000, "total_cost_cents": 5.0}
        action_counts = {"speak": 10, "observe": 5}

        attrs = create_aggregated_summary_attributes(
            "tsdb_summary",
            start,
            end,
            "daily",
            metrics,
            resources,
            action_counts,
            ["summary1", "summary2"],
        )

        assert attrs["consolidation_level"] == "daily"
        assert attrs["source_node_count"] == 2
        assert attrs["action_counts"] == action_counts
        assert attrs["total_tokens"] == 1000

    def test_creates_audit_summary_attributes(self):
        """Should create attributes for audit_summary."""
        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 1, 23, 59, 59, tzinfo=timezone.utc)
        action_counts = {"login": 5, "logout": 3}

        attrs = create_aggregated_summary_attributes(
            "audit_summary",
            start,
            end,
            "daily",
            {},
            {},
            action_counts,
            ["audit1"],
        )

        assert "event_counts" in attrs
        assert attrs["event_counts"] == action_counts

    def test_creates_task_summary_attributes(self):
        """Should create attributes for task_summary."""
        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 1, 23, 59, 59, tzinfo=timezone.utc)
        action_counts = {"completed": 10, "failed": 2}

        attrs = create_aggregated_summary_attributes(
            "task_summary",
            start,
            end,
            "daily",
            {},
            {},
            action_counts,
            ["task1", "task2"],
        )

        assert "task_outcomes" in attrs
        assert attrs["task_outcomes"] == action_counts

    def test_includes_period_timestamps(self):
        """Should include ISO format period timestamps."""
        start = datetime(2023, 10, 1, 0, 0, tzinfo=timezone.utc)
        end = datetime(2023, 10, 1, 23, 59, 59, tzinfo=timezone.utc)

        attrs = create_aggregated_summary_attributes("tsdb_summary", start, end, "daily", {}, {}, {}, [])

        assert attrs["period_start"] == "2023-10-01T00:00:00+00:00"
        assert attrs["period_end"] == "2023-10-01T23:59:59+00:00"


class TestParseSummaryAttributes:
    """Tests for parse_summary_attributes function."""

    def test_parses_valid_json(self):
        """Should parse valid JSON attributes."""
        summaries = [
            ("node1", '{"metrics": {"cpu": 0.5}}'),
            ("node2", '{"metrics": {"cpu": 0.8}}'),
        ]

        attrs = parse_summary_attributes(summaries)

        assert len(attrs) == 2
        assert attrs[0]["metrics"]["cpu"] == 0.5
        assert attrs[1]["metrics"]["cpu"] == 0.8

    def test_handles_empty_json(self):
        """Should handle empty/null JSON."""
        summaries = [
            ("node1", "{}"),
            ("node2", None),
            ("node3", ""),
        ]

        attrs = parse_summary_attributes(summaries)

        assert len(attrs) == 3
        assert attrs[0] == {}
        assert attrs[1] == {}
        assert attrs[2] == {}

    def test_skips_invalid_json(self):
        """Should skip entries with invalid JSON."""
        summaries = [
            ("node1", '{"valid": true}'),
            ("node2", "not-valid-json"),
            ("node3", '{"also": "valid"}'),
        ]

        attrs = parse_summary_attributes(summaries)

        assert len(attrs) == 2
        assert attrs[0]["valid"] is True
        assert attrs[1]["also"] == "valid"

    def test_returns_empty_list_for_empty_input(self):
        """Should return empty list for empty input."""
        result = parse_summary_attributes([])
        assert result == []
