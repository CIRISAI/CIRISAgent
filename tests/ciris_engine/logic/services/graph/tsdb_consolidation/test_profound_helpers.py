"""
Tests for profound consolidation helper functions.

Ensures 80%+ coverage for profound consolidation logic.
"""

import json
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation.profound_helpers import (
    calculate_storage_metrics,
    cleanup_old_basic_summaries,
    compress_and_update_summaries,
    parse_summary_attributes_with_fallback,
    query_extensive_summaries_in_month,
)
from ciris_engine.schemas.services.graph.tsdb_models import SummaryAttributes


class TestParseSummaryAttributesWithFallback:
    """Tests for parse_summary_attributes_with_fallback function."""

    def test_parses_valid_attributes(self):
        """Should parse valid attributes dict."""
        attrs_dict = {
            "period_start": "2023-10-01T00:00:00+00:00",
            "period_end": "2023-10-01T23:59:59+00:00",
            "consolidation_level": "extensive",
        }

        attrs = parse_summary_attributes_with_fallback(attrs_dict)

        assert isinstance(attrs, SummaryAttributes)
        assert attrs.consolidation_level == "extensive"

    def test_creates_minimal_attributes_on_error(self):
        """Should create minimal attributes when parsing fails."""
        # Invalid dict will fail Pydantic validation
        attrs_dict = {
            "period_start": "not-a-valid-date",
            "invalid_field": True,
        }

        attrs = parse_summary_attributes_with_fallback(attrs_dict)

        # Should still return a valid SummaryAttributes object
        assert isinstance(attrs, SummaryAttributes)
        assert attrs.consolidation_level == "basic"  # Default value

    def test_handles_z_timezone_in_fallback(self):
        """Should handle 'Z' timezone notation in fallback."""
        attrs_dict = {
            "period_start": "2023-10-01T00:00:00Z",
            "period_end": "2023-10-02T00:00:00Z",
            "invalid_field_triggers_fallback": True,
        }

        attrs = parse_summary_attributes_with_fallback(attrs_dict)

        assert isinstance(attrs, SummaryAttributes)
        assert attrs.period_start.tzinfo is not None

    def test_uses_defaults_when_dates_missing(self):
        """Should use default dates when not provided."""
        attrs_dict = {}  # Empty dict

        attrs = parse_summary_attributes_with_fallback(attrs_dict)

        assert isinstance(attrs, SummaryAttributes)
        # Should have default dates (2025-01-01 per implementation)


class TestCalculateStorageMetrics:
    """Tests for calculate_storage_metrics function."""

    def test_calculates_storage_correctly(self):
        """Should calculate storage metrics from summaries."""
        cursor = Mock()
        cursor.fetchall.return_value = [
            (json.dumps({"period_start": "2023-10-01T00:00:00+00:00", "period_end": "2023-10-02T00:00:00+00:00"}),),
            (json.dumps({"period_start": "2023-10-02T00:00:00+00:00", "period_end": "2023-10-03T00:00:00+00:00"}),),
        ]

        compressor = Mock()
        compressor.estimate_daily_size.return_value = 5.5  # 5.5 MB/day

        month_start = datetime(2023, 10, 1, tzinfo=timezone.utc)
        month_end = datetime(2023, 10, 31, tzinfo=timezone.utc)

        daily_mb, attrs_list = calculate_storage_metrics(cursor, month_start, month_end, compressor)

        assert daily_mb == 5.5
        assert len(attrs_list) == 2
        assert all(isinstance(a, SummaryAttributes) for a in attrs_list)
        cursor.execute.assert_called_once()

    def test_handles_empty_results(self):
        """Should handle no summaries found."""
        cursor = Mock()
        cursor.fetchall.return_value = []

        compressor = Mock()
        compressor.estimate_daily_size.return_value = 0.0

        month_start = datetime(2023, 10, 1, tzinfo=timezone.utc)
        month_end = datetime(2023, 10, 31, tzinfo=timezone.utc)

        daily_mb, attrs_list = calculate_storage_metrics(cursor, month_start, month_end, compressor)

        assert daily_mb == 0.0
        assert attrs_list == []

    def test_handles_null_json(self):
        """Should handle None/null JSON in results."""
        cursor = Mock()
        cursor.fetchall.return_value = [(None,), ("{}",)]

        compressor = Mock()
        compressor.estimate_daily_size.return_value = 1.0

        month_start = datetime(2023, 10, 1, tzinfo=timezone.utc)
        month_end = datetime(2023, 10, 31, tzinfo=timezone.utc)

        daily_mb, attrs_list = calculate_storage_metrics(cursor, month_start, month_end, compressor)

        assert len(attrs_list) == 2  # Both should be parsed with fallback


class TestCompressAndUpdateSummaries:
    """Tests for compress_and_update_summaries function."""

    def test_compresses_and_updates_summaries(self):
        """Should compress summaries and update database."""
        cursor = Mock()
        cursor.rowcount = 1  # Successful update

        # Mock compression result
        compressed_attrs = SummaryAttributes(
            period_start=datetime(2023, 10, 1, tzinfo=timezone.utc),
            period_end=datetime(2023, 10, 2, tzinfo=timezone.utc),
            consolidation_level="profound",
        )
        compression_result = Mock()
        compression_result.compressed_attributes = compressed_attrs
        compression_result.reduction_ratio = 0.35  # 35% reduction

        compressor = Mock()
        compressor.compress_summary.return_value = compression_result

        summaries = [
            ("node1", "tsdb_summary", json.dumps({"period_start": "2023-10-01T00:00:00+00:00"}), 1),
            ("node2", "tsdb_summary", json.dumps({"period_start": "2023-10-02T00:00:00+00:00"}), 1),
        ]

        now = datetime(2023, 10, 5, tzinfo=timezone.utc)

        compressed_count, total_reduction = compress_and_update_summaries(cursor, summaries, compressor, now)

        assert compressed_count == 2
        assert total_reduction == pytest.approx(0.70)  # 0.35 + 0.35
        assert cursor.execute.call_count == 2

    def test_handles_update_failures(self):
        """Should handle failed updates gracefully."""
        cursor = Mock()
        cursor.rowcount = 0  # Update failed

        compression_result = Mock()
        compression_result.compressed_attributes = SummaryAttributes(
            period_start=datetime(2023, 10, 1, tzinfo=timezone.utc),
            period_end=datetime(2023, 10, 2, tzinfo=timezone.utc),
            consolidation_level="profound",
        )
        compression_result.reduction_ratio = 0.35

        compressor = Mock()
        compressor.compress_summary.return_value = compression_result

        summaries = [("node1", "type", "{}", 1)]
        now = datetime.now(timezone.utc)

        compressed_count, total_reduction = compress_and_update_summaries(cursor, summaries, compressor, now)

        assert compressed_count == 0
        assert total_reduction == 0.0

    def test_adds_compression_metadata(self):
        """Should add profound_compressed metadata."""
        cursor = Mock()
        cursor.rowcount = 1

        compression_result = Mock()
        compression_result.compressed_attributes = SummaryAttributes(
            period_start=datetime(2023, 10, 1, tzinfo=timezone.utc),
            period_end=datetime(2023, 10, 2, tzinfo=timezone.utc),
            consolidation_level="profound",
        )
        compression_result.reduction_ratio = 0.25

        compressor = Mock()
        compressor.compress_summary.return_value = compression_result

        summaries = [("node1", "type", "{}", 1)]
        now = datetime(2023, 10, 5, 12, 0, 0, tzinfo=timezone.utc)

        compress_and_update_summaries(cursor, summaries, compressor, now)

        # Check that UPDATE was called with metadata
        call_args = cursor.execute.call_args
        updated_json = call_args[0][1][0]
        updated_dict = json.loads(updated_json)

        assert updated_dict["profound_compressed"] is True
        assert "compression_date" in updated_dict
        assert updated_dict["compression_ratio"] == 0.25


class TestCleanupOldBasicSummaries:
    """Tests for cleanup_old_basic_summaries function."""

    def test_deletes_old_summaries(self):
        """Should delete basic summaries before cutoff."""
        cursor = Mock()
        cursor.rowcount = 15

        cutoff_date = datetime(2023, 9, 1, tzinfo=timezone.utc)

        deleted = cleanup_old_basic_summaries(cursor, cutoff_date)

        assert deleted == 15
        cursor.execute.assert_called_once()

    def test_returns_zero_when_none_deleted(self):
        """Should return 0 when no rows deleted."""
        cursor = Mock()
        cursor.rowcount = 0

        cutoff_date = datetime(2023, 9, 1, tzinfo=timezone.utc)

        deleted = cleanup_old_basic_summaries(cursor, cutoff_date)

        assert deleted == 0


class TestQueryExtensiveSummariesInMonth:
    """Tests for query_extensive_summaries_in_month function."""

    def test_queries_summaries_correctly(self):
        """Should query extensive summaries in month."""
        cursor = Mock()
        cursor.fetchall.return_value = [
            ("node1", "tsdb_summary", "{}", 1),
            ("node2", "audit_summary", "{}", 1),
        ]

        month_start = datetime(2023, 10, 1, tzinfo=timezone.utc)
        month_end = datetime(2023, 10, 31, tzinfo=timezone.utc)

        summaries = query_extensive_summaries_in_month(cursor, month_start, month_end)

        assert len(summaries) == 2
        assert all(len(s) == 4 for s in summaries)
        cursor.execute.assert_called_once()

    def test_returns_empty_list_when_no_summaries(self):
        """Should return empty list when no summaries found."""
        cursor = Mock()
        cursor.fetchall.return_value = []

        month_start = datetime(2023, 10, 1, tzinfo=timezone.utc)
        month_end = datetime(2023, 10, 31, tzinfo=timezone.utc)

        summaries = query_extensive_summaries_in_month(cursor, month_start, month_end)

        assert summaries == []
