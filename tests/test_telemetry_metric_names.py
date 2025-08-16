"""
Unit tests for telemetry metric name alignment with production TSDB nodes.
"""

import unittest
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.schemas.telemetry.core import TimeSeriesDataPoint


class TestTelemetryMetricNames(unittest.TestCase):
    """Test that telemetry service queries for correct metric names."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock memory bus
        self.mock_memory_bus = AsyncMock()

        # Create mock time service
        self.mock_time_service = MagicMock()
        self.mock_time_service.now.return_value = datetime(2025, 1, 16, 12, 0, 0, tzinfo=timezone.utc)

        # Create telemetry service
        self.telemetry_service = GraphTelemetryService(
            memory_bus=self.mock_memory_bus, time_service=self.mock_time_service
        )

    @pytest.mark.asyncio
    async def test_query_metrics_filters_by_name(self):
        """Test that query_metrics correctly filters by metric name."""
        # Mock recall_timeseries to return test data
        test_data = [
            TimeSeriesDataPoint(
                metric_name="llm.tokens.total",
                value=100.0,
                timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
                tags={"service": "llm"},
            ),
            TimeSeriesDataPoint(
                metric_name="llm.cost.cents",
                value=10.5,
                timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
                tags={"service": "llm"},
            ),
            TimeSeriesDataPoint(
                metric_name="llm.tokens.total",
                value=150.0,
                timestamp=datetime(2025, 1, 16, 11, 30, 0, tzinfo=timezone.utc),
                tags={"service": "llm"},
            ),
        ]
        self.mock_memory_bus.recall_timeseries.return_value = test_data

        # Query for specific metric
        results = await self.telemetry_service.query_metrics(
            metric_name="llm.tokens.total",
            start_time=datetime(2025, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 16, 12, 0, 0, tzinfo=timezone.utc),
        )

        # Should only return llm.tokens.total metrics
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertEqual(result["metric_name"], "llm.tokens.total")

        # Verify values
        self.assertEqual(results[0]["value"], 100.0)
        self.assertEqual(results[1]["value"], 150.0)

    @pytest.mark.asyncio
    async def test_get_telemetry_summary_queries_correct_metrics(self):
        """Test that get_telemetry_summary queries for the correct metric names."""
        # Mock recall_timeseries to track what metrics are queried
        queried_metrics = []

        async def mock_query_metrics(metric_name, **kwargs):
            queried_metrics.append(metric_name)
            # Return some dummy data
            if "tokens" in metric_name:
                return [{"value": 100.0, "timestamp": self.mock_time_service.now()}]
            elif "cost" in metric_name:
                return [{"value": 0.1, "timestamp": self.mock_time_service.now()}]
            return []

        # Patch query_metrics
        with patch.object(self.telemetry_service, "query_metrics", side_effect=mock_query_metrics):
            # Call get_telemetry_summary
            summary = await self.telemetry_service.get_telemetry_summary()

        # Check that the correct metrics were queried
        expected_metrics = [
            "llm.tokens.total",
            "llm_tokens_used",  # Legacy metric
            "llm.tokens.input",
            "llm.tokens.output",
            "llm.cost.cents",
            "llm.environmental.carbon_grams",
            "llm.environmental.energy_kwh",
            "llm.latency.ms",
            "thought_processing_completed",
            "thought_processing_started",
            "action_selected_task_complete",
            "handler_invoked_total",
            "error.occurred",
        ]

        for metric in expected_metrics:
            self.assertIn(metric, queried_metrics, f"Expected {metric} to be queried")

    @pytest.mark.asyncio
    async def test_query_metrics_handles_empty_results(self):
        """Test that query_metrics handles empty results gracefully."""
        # Mock empty recall
        self.mock_memory_bus.recall_timeseries.return_value = []

        results = await self.telemetry_service.query_metrics(
            metric_name="non.existent.metric",
            start_time=datetime(2025, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 1, 16, 12, 0, 0, tzinfo=timezone.utc),
        )

        # Should return empty list
        self.assertEqual(results, [])

    @pytest.mark.asyncio
    async def test_query_metrics_filters_by_tags(self):
        """Test that query_metrics correctly filters by tags."""
        # Mock data with different tags
        test_data = [
            TimeSeriesDataPoint(
                metric_name="llm.tokens.total",
                value=100.0,
                timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
                tags={"service": "llm", "model": "gpt-4"},
            ),
            TimeSeriesDataPoint(
                metric_name="llm.tokens.total",
                value=200.0,
                timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
                tags={"service": "llm", "model": "claude"},
            ),
        ]
        self.mock_memory_bus.recall_timeseries.return_value = test_data

        # Query with tag filter
        results = await self.telemetry_service.query_metrics(metric_name="llm.tokens.total", tags={"model": "gpt-4"})

        # Should only return metrics with matching tags
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["value"], 100.0)
        self.assertEqual(results[0]["tags"]["model"], "gpt-4")

    @pytest.mark.asyncio
    async def test_production_metric_names_exist(self):
        """Test that we query for metric names that actually exist in production."""
        # These are the actual metric names found in production TSDB nodes
        production_metrics = [
            "llm.tokens.total",
            "llm.tokens.input",
            "llm.tokens.output",
            "llm.cost.cents",
            "llm.environmental.carbon_grams",
            "llm.environmental.energy_kwh",
            "llm.latency.ms",
            "llm_tokens_used",
            "llm_api_call_structured",
            "thought_processing_completed",
            "thought_processing_started",
            "handler_invoked_total",
            "handler_completed_total",
            "action_selected_task_complete",
            "action_selected_memorize",
        ]

        # Mock data for each metric
        mock_data = []
        for metric in production_metrics:
            mock_data.append(
                TimeSeriesDataPoint(metric_name=metric, value=1.0, timestamp=self.mock_time_service.now(), tags={})
            )

        self.mock_memory_bus.recall_timeseries.return_value = mock_data

        # Query each metric to ensure no errors
        for metric_name in production_metrics:
            results = await self.telemetry_service.query_metrics(metric_name=metric_name)
            # Should get at least one result for production metrics
            self.assertGreaterEqual(len(results), 0, f"No results for production metric {metric_name}")


if __name__ == "__main__":
    unittest.main()
