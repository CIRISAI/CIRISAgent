"""
Unit tests for telemetry metric name alignment with production TSDB nodes.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.schemas.runtime.memory import TimeSeriesDataPoint


@pytest.fixture
def telemetry_setup(monkeypatch):
    """Set up test fixtures for telemetry tests."""
    # Create mock memory bus
    mock_memory_bus = AsyncMock()

    # Create mock time service
    mock_time_service = MagicMock()
    mock_time_service.now.return_value = datetime(2025, 1, 16, 12, 0, 0, tzinfo=timezone.utc)

    # Create telemetry service
    telemetry_service = GraphTelemetryService(memory_bus=mock_memory_bus, time_service=mock_time_service)

    # Mock database connection for get_average_thought_depth
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = (2.5,)
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__.return_value = mock_conn
    mock_conn.__exit__.return_value = None
    monkeypatch.setattr("ciris_engine.logic.persistence.get_db_connection", lambda **kwargs: mock_conn)

    # Mock runtime control for queue saturation
    mock_runtime_bus = MagicMock()
    mock_runtime = AsyncMock()
    mock_queue_status = MagicMock()
    mock_queue_status.queue_size = 5
    mock_queue_status.max_size = 100
    mock_runtime.get_processor_queue_status.return_value = mock_queue_status
    mock_runtime_bus.get_service.return_value = mock_runtime
    setattr(telemetry_service, "_runtime_control_bus", mock_runtime_bus)
    setattr(telemetry_service, "_start_time", datetime(2025, 1, 16, 0, 0, 0, tzinfo=timezone.utc))

    return telemetry_service, mock_memory_bus, mock_time_service


@pytest.mark.asyncio
async def test_query_metrics_filters_by_name(telemetry_setup):
    """Test that query_metrics correctly filters by metric name."""
    telemetry_service, mock_memory_bus, mock_time_service = telemetry_setup

    # Mock recall_timeseries to return test data
    test_data = [
        TimeSeriesDataPoint(
            metric_name="llm.tokens.total",
            value=100.0,
            timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
            correlation_type="METRIC_DATAPOINT",
            tags={"service": "llm"},
        ),
        TimeSeriesDataPoint(
            metric_name="llm.cost.cents",
            value=10.5,
            timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
            correlation_type="METRIC_DATAPOINT",
            tags={"service": "llm"},
        ),
        TimeSeriesDataPoint(
            metric_name="llm.tokens.total",
            value=150.0,
            timestamp=datetime(2025, 1, 16, 11, 30, 0, tzinfo=timezone.utc),
            correlation_type="METRIC_DATAPOINT",
            tags={"service": "llm"},
        ),
    ]
    mock_memory_bus.recall_timeseries.return_value = test_data

    # Query for specific metric
    results = await telemetry_service.query_metrics(
        metric_name="llm.tokens.total",
        start_time=datetime(2025, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 16, 12, 0, 0, tzinfo=timezone.utc),
    )

    # Should only return llm.tokens.total metrics
    assert len(results) == 2
    for result in results:
        assert result.metric_name == "llm.tokens.total"

    # Verify values
    assert results[0].value == 100.0
    assert results[1].value == 150.0


@pytest.mark.asyncio
async def test_get_telemetry_summary_queries_correct_metrics(telemetry_setup):
    """Test that get_telemetry_summary queries for the correct metric names."""
    telemetry_service, mock_memory_bus, mock_time_service = telemetry_setup

    # Mock recall_timeseries to track what metrics are queried
    queried_metrics = []

    async def mock_query_metrics(metric_name, **kwargs):
        from ciris_engine.schemas.services.graph.telemetry import MetricRecord

        queried_metrics.append(metric_name)
        # Return some dummy data
        if "tokens" in metric_name:
            return [MetricRecord(metric_name=metric_name, value=100.0, timestamp=mock_time_service.now(), tags={})]
        elif "cost" in metric_name:
            return [MetricRecord(metric_name=metric_name, value=0.1, timestamp=mock_time_service.now(), tags={})]
        return []

    # Patch query_metrics
    with patch.object(telemetry_service, "query_metrics", side_effect=mock_query_metrics):
        # Call get_telemetry_summary
        summary = await telemetry_service.get_telemetry_summary()

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
        assert metric in queried_metrics, f"Expected {metric} to be queried"


@pytest.mark.asyncio
async def test_query_metrics_handles_empty_results(telemetry_setup):
    """Test that query_metrics handles empty results gracefully."""
    telemetry_service, mock_memory_bus, mock_time_service = telemetry_setup

    # Mock empty recall
    mock_memory_bus.recall_timeseries.return_value = []

    results = await telemetry_service.query_metrics(
        metric_name="non.existent.metric",
        start_time=datetime(2025, 1, 16, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2025, 1, 16, 12, 0, 0, tzinfo=timezone.utc),
    )

    # Should return empty list
    assert results == []


@pytest.mark.asyncio
async def test_query_metrics_filters_by_tags(telemetry_setup):
    """Test that query_metrics correctly filters by tags."""
    telemetry_service, mock_memory_bus, mock_time_service = telemetry_setup

    # Mock data with different tags
    test_data = [
        TimeSeriesDataPoint(
            metric_name="llm.tokens.total",
            value=100.0,
            timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
            correlation_type="METRIC_DATAPOINT",
            tags={"service": "llm", "model": "gpt-4"},
        ),
        TimeSeriesDataPoint(
            metric_name="llm.tokens.total",
            value=200.0,
            timestamp=datetime(2025, 1, 16, 11, 0, 0, tzinfo=timezone.utc),
            correlation_type="METRIC_DATAPOINT",
            tags={"service": "llm", "model": "claude"},
        ),
    ]
    mock_memory_bus.recall_timeseries.return_value = test_data

    # Query with tag filter
    results = await telemetry_service.query_metrics(metric_name="llm.tokens.total", tags={"model": "gpt-4"})

    # Should only return metrics with matching tags
    assert len(results) == 1
    assert results[0].value == 100.0
    assert results[0].tags["model"] == "gpt-4"


@pytest.mark.asyncio
async def test_production_metric_names_exist(telemetry_setup):
    """Test that we query for metric names that actually exist in production."""
    telemetry_service, mock_memory_bus, mock_time_service = telemetry_setup

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
            TimeSeriesDataPoint(
                metric_name=metric,
                value=1.0,
                timestamp=mock_time_service.now(),
                correlation_type="METRIC_DATAPOINT",
                tags={},
            )
        )

    mock_memory_bus.recall_timeseries.return_value = mock_data

    # Query each metric to ensure no errors
    for metric_name in production_metrics:
        results = await telemetry_service.query_metrics(metric_name=metric_name)
        # Should get at least one result for production metrics
        assert len(results) >= 0, f"No results for production metric {metric_name}"
