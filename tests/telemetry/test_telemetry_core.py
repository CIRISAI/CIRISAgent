"""
Comprehensive tests for telemetry/core.py module.

Tests the BasicTelemetryCollector class including metric recording,
security filtering, path type detection, and system snapshot updates.
"""

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.logic.telemetry.core import BasicTelemetryCollector
from ciris_engine.logic.telemetry.security import SecurityFilter
from ciris_engine.schemas.runtime.system_context import SystemSnapshot, TelemetrySummary
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    MetricData,
    ServiceCorrelation,
    ServiceCorrelationStatus,
)


@pytest.fixture
def time_service():
    """Mock time service."""
    service = Mock(spec=TimeService)
    service.now.return_value = datetime.now(timezone.utc)
    return service


@pytest.fixture
def security_filter():
    """Mock security filter."""
    filter_mock = Mock(spec=SecurityFilter)
    # By default, allow all metrics through
    filter_mock.sanitize.side_effect = lambda name, value: (name, value)
    return filter_mock


@pytest.fixture
def telemetry_collector(time_service, security_filter):
    """Create a BasicTelemetryCollector instance."""
    return BasicTelemetryCollector(
        buffer_size=100,
        security_filter=security_filter,
        time_service=time_service,
    )


class TestBasicTelemetryCollector:
    """Test BasicTelemetryCollector class."""

    @pytest.mark.asyncio
    async def test_initialization(self, telemetry_collector, time_service):
        """Test collector initialization."""
        assert telemetry_collector.buffer_size == 100
        assert telemetry_collector._time_service == time_service
        assert telemetry_collector.start_time == time_service.now.return_value
        assert isinstance(telemetry_collector._history, dict)

    @pytest.mark.asyncio
    async def test_start_stop(self, telemetry_collector):
        """Test starting and stopping the collector."""
        # Start
        await telemetry_collector.start()
        assert telemetry_collector._started is True

        # Stop
        await telemetry_collector.stop()
        assert telemetry_collector._started is False

    @pytest.mark.asyncio
    async def test_record_metric_basic(self, telemetry_collector, time_service):
        """Test basic metric recording."""
        # Record a metric
        await telemetry_collector.record_metric("test_metric", 42.0)

        # Check it was stored
        assert "test_metric" in telemetry_collector._history
        history = telemetry_collector._history["test_metric"]
        assert len(history) == 1
        assert history[0][0] == time_service.now.return_value
        assert history[0][1] == 42.0

    @pytest.mark.asyncio
    async def test_record_metric_with_tags(self, telemetry_collector):
        """Test recording metrics with tags."""
        tags = {"service": "test", "environment": "testing"}
        await telemetry_collector.record_metric("tagged_metric", 10.0, tags=tags, source_module="test_module")

        # Check enhanced history
        assert hasattr(telemetry_collector, "_enhanced_history")
        enhanced = telemetry_collector._enhanced_history["tagged_metric"]
        assert len(enhanced) == 1
        entry = enhanced[0]
        assert entry["value"] == 10.0
        assert entry["tags"] == tags
        assert entry["source_module"] == "test_module"

    @pytest.mark.asyncio
    async def test_path_type_auto_detection(self, telemetry_collector):
        """Test automatic path type detection based on metric name."""
        # Critical path
        await telemetry_collector.record_metric("auth_error", 1.0)
        assert telemetry_collector._enhanced_history["auth_error"][0]["path_type"] == "critical"

        # Hot path
        await telemetry_collector.record_metric("thought_processing_time", 100.0)
        assert telemetry_collector._enhanced_history["thought_processing_time"][0]["path_type"] == "hot"

        # Cold path
        await telemetry_collector.record_metric("memory_fetch_duration", 50.0)
        assert telemetry_collector._enhanced_history["memory_fetch_duration"][0]["path_type"] == "cold"

        # Normal path
        await telemetry_collector.record_metric("generic_metric", 1.0)
        assert telemetry_collector._enhanced_history["generic_metric"][0]["path_type"] == "normal"

    @pytest.mark.asyncio
    async def test_explicit_path_type(self, telemetry_collector):
        """Test explicitly setting path type."""
        await telemetry_collector.record_metric("custom_metric", 5.0, path_type="critical")
        assert telemetry_collector._enhanced_history["custom_metric"][0]["path_type"] == "critical"

    @pytest.mark.asyncio
    async def test_security_filter_blocks_metric(self, telemetry_collector, security_filter):
        """Test that security filter can block metrics."""
        # Configure filter to block this metric - override the side_effect
        security_filter.sanitize.side_effect = None
        security_filter.sanitize.return_value = None

        await telemetry_collector.record_metric("blocked_metric", 100.0)

        # Metric should not be recorded
        assert "blocked_metric" not in telemetry_collector._history

    @pytest.mark.asyncio
    async def test_security_filter_sanitizes_metric(self, telemetry_collector, security_filter):
        """Test that security filter can sanitize metrics."""
        # Configure filter to sanitize the value - override the side_effect
        security_filter.sanitize.side_effect = None
        security_filter.sanitize.return_value = ("sanitized_metric", 0.0)

        await telemetry_collector.record_metric("original_metric", 999.0)

        # Should use sanitized name and value
        assert "sanitized_metric" in telemetry_collector._history
        assert "original_metric" not in telemetry_collector._history
        assert telemetry_collector._history["sanitized_metric"][0][1] == 0.0

    @pytest.mark.asyncio
    async def test_buffer_size_limit(self, time_service):
        """Test that buffer respects size limit."""
        collector = BasicTelemetryCollector(buffer_size=3, time_service=time_service)

        # Add more metrics than buffer size
        for i in range(5):
            await collector.record_metric("overflow_metric", float(i))

        # Should only keep last 3
        history = collector._history["overflow_metric"]
        assert len(history) == 3
        values = [h[1] for h in history]
        assert values == [2.0, 3.0, 4.0]

    @pytest.mark.asyncio
    async def test_metric_correlation_creation(self, telemetry_collector):
        """Test that metric correlations are created correctly."""
        with patch("ciris_engine.logic.telemetry.core.add_correlation") as mock_add:
            await telemetry_collector.record_metric(
                "correlation_test", 25.0, tags={"test": "value"}, path_type="hot", source_module="test_module"
            )

            # Wait for async task
            await asyncio.sleep(0.1)

            # Check correlation was created
            assert mock_add.called
            correlation = mock_add.call_args[0][0]
            assert isinstance(correlation, ServiceCorrelation)
            assert correlation.service_type == "telemetry"
            assert correlation.handler_name == "telemetry_service"
            assert correlation.action_type == "record_metric"
            assert correlation.correlation_type == CorrelationType.METRIC_DATAPOINT
            assert correlation.metric_data.metric_name == "correlation_test"
            assert correlation.metric_data.metric_value == 25.0
            assert correlation.tags["test"] == "value"
            assert correlation.tags["path_type"] == "hot"
            assert correlation.tags["source_module"] == "test_module"

    @pytest.mark.asyncio
    async def test_correlation_error_handling(self, telemetry_collector):
        """Test that correlation errors don't break metric recording."""
        with patch("ciris_engine.logic.telemetry.core.add_correlation") as mock_add:
            mock_add.side_effect = Exception("Database error")

            # Should not raise
            await telemetry_collector.record_metric("error_test", 1.0)

            # Metric should still be recorded locally
            assert "error_test" in telemetry_collector._history

    @pytest.mark.asyncio
    async def test_update_system_snapshot_basic(self, telemetry_collector, time_service):
        """Test updating system snapshot with telemetry data."""
        # Set up time points
        now = datetime.now(timezone.utc)
        time_service.now.return_value = now

        # Record various metrics
        await telemetry_collector.record_metric("message_processed", 1.0)
        await telemetry_collector.record_metric("message_processed", 1.0)
        await telemetry_collector.record_metric("error", 1.0)
        await telemetry_collector.record_metric("thought_processed", 1.0)
        await telemetry_collector.record_metric("task_completed", 1.0)

        # Create snapshot
        snapshot = SystemSnapshot()

        # Update snapshot
        await telemetry_collector.update_system_snapshot(snapshot)

        # Check telemetry summary
        assert snapshot.telemetry_summary is not None
        assert snapshot.telemetry_summary.messages_processed_24h == 2
        assert snapshot.telemetry_summary.errors_24h == 1
        assert snapshot.telemetry_summary.thoughts_processed_24h == 1
        assert snapshot.telemetry_summary.tasks_completed_24h == 1

    @pytest.mark.asyncio
    async def test_update_system_snapshot_time_windows(self, telemetry_collector, time_service):
        """Test that snapshot correctly filters metrics by time window."""
        now = datetime.now(timezone.utc)
        old_time = now - timedelta(hours=25)  # Outside 24h window
        recent_time = now - timedelta(minutes=30)  # Within 1h window

        # Add old and recent metrics
        telemetry_collector._history["message_processed"].append((old_time, 1.0))
        telemetry_collector._history["message_processed"].append((recent_time, 1.0))
        telemetry_collector._history["message_processed"].append((now, 1.0))

        time_service.now.return_value = now

        snapshot = SystemSnapshot()
        await telemetry_collector.update_system_snapshot(snapshot)

        # Old metric should be filtered out
        assert snapshot.telemetry_summary.messages_processed_24h == 2  # Only recent ones
        assert snapshot.telemetry_summary.messages_current_hour == 2  # Both within hour

    @pytest.mark.asyncio
    async def test_update_system_snapshot_error_rate(self, telemetry_collector, time_service):
        """Test error rate calculation in snapshot."""
        now = datetime.now(timezone.utc)
        time_service.now.return_value = now

        # Record messages and errors
        for _ in range(10):
            await telemetry_collector.record_metric("message_processed", 1.0)
        for _ in range(2):
            await telemetry_collector.record_metric("error", 1.0)

        snapshot = SystemSnapshot()
        await telemetry_collector.update_system_snapshot(snapshot)

        # Error rate should be 20%
        assert snapshot.telemetry_summary.error_rate_percent == 20.0

    @pytest.mark.asyncio
    async def test_update_system_snapshot_service_calls(self, telemetry_collector, time_service):
        """Test service call tracking in snapshot."""
        now = datetime.now(timezone.utc)
        time_service.now.return_value = now

        # Record service calls
        await telemetry_collector.record_metric("service_auth_call", 1.0)
        await telemetry_collector.record_metric("service_auth_call", 1.0)
        await telemetry_collector.record_metric("service_memory_call", 1.0)

        snapshot = SystemSnapshot()
        await telemetry_collector.update_system_snapshot(snapshot)

        # Check service calls
        assert snapshot.telemetry_summary.service_calls["auth"] == 2
        assert snapshot.telemetry_summary.service_calls["memory"] == 1

    @pytest.mark.asyncio
    async def test_update_system_snapshot_uptime(self, telemetry_collector, time_service):
        """Test uptime calculation in snapshot."""
        start_time = datetime.now(timezone.utc)
        current_time = start_time + timedelta(hours=2)

        telemetry_collector.start_time = start_time
        time_service.now.return_value = current_time

        snapshot = SystemSnapshot()
        await telemetry_collector.update_system_snapshot(snapshot)

        # Uptime should be 2 hours in seconds
        assert snapshot.telemetry_summary.uptime_seconds == 7200.0

    def test_get_retention_policy(self, telemetry_collector):
        """Test retention policy determination."""
        assert telemetry_collector._get_retention_policy("critical") == "raw"
        assert telemetry_collector._get_retention_policy("hot") == "raw"
        assert telemetry_collector._get_retention_policy("cold") == "aggregated"
        assert telemetry_collector._get_retention_policy("normal") == "aggregated"
        assert telemetry_collector._get_retention_policy(None) == "aggregated"

    @pytest.mark.asyncio
    async def test_concurrent_metric_recording(self, telemetry_collector):
        """Test that concurrent metric recording works correctly."""

        async def record_metrics(name: str, count: int):
            for i in range(count):
                await telemetry_collector.record_metric(name, float(i))

        # Record metrics concurrently
        await asyncio.gather(
            record_metrics("concurrent_1", 10),
            record_metrics("concurrent_2", 10),
            record_metrics("concurrent_3", 10),
        )

        # Check all metrics were recorded
        assert len(telemetry_collector._history["concurrent_1"]) == 10
        assert len(telemetry_collector._history["concurrent_2"]) == 10
        assert len(telemetry_collector._history["concurrent_3"]) == 10

    @pytest.mark.asyncio
    async def test_empty_snapshot_update(self, telemetry_collector, time_service):
        """Test updating snapshot when no metrics have been recorded."""
        now = datetime.now(timezone.utc)
        time_service.now.return_value = now

        snapshot = SystemSnapshot()
        await telemetry_collector.update_system_snapshot(snapshot)

        # Should have telemetry summary with zero values
        assert snapshot.telemetry_summary is not None
        assert snapshot.telemetry_summary.messages_processed_24h == 0
        assert snapshot.telemetry_summary.errors_24h == 0
        assert snapshot.telemetry_summary.error_rate_percent == 0.0


class TestIntegration:
    """Integration tests for telemetry collector."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, time_service):
        """Test full lifecycle of telemetry collector."""
        collector = BasicTelemetryCollector(buffer_size=50, time_service=time_service)

        # Start collector
        await collector.start()

        # Record various metrics
        for i in range(5):
            await collector.record_metric("lifecycle_test", float(i))
            await collector.record_metric("service_test_call", 1.0)

        # Create and update snapshot
        snapshot = SystemSnapshot()
        await collector.update_system_snapshot(snapshot)

        # Stop collector
        await collector.stop()

        # Verify data persisted
        assert len(collector._history["lifecycle_test"]) == 5
        assert snapshot.telemetry_summary.service_calls["test"] == 5

    @pytest.mark.asyncio
    async def test_real_world_scenario(self, time_service):
        """Test realistic usage scenario."""
        collector = BasicTelemetryCollector(time_service=time_service)

        # Simulate message processing with occasional errors
        for i in range(100):
            await collector.record_metric(
                "message_processed", 1.0, tags={"user_id": f"user_{i % 10}"}, source_module="discord_adapter"
            )

            # 5% error rate
            if i % 20 == 0:
                await collector.record_metric("error", 1.0, tags={"error_type": "validation"}, path_type="critical")

            # Record some thoughts
            if i % 3 == 0:
                await collector.record_metric("thought_processed", 1.0, path_type="hot")

        # Update snapshot
        snapshot = SystemSnapshot()
        await collector.update_system_snapshot(snapshot)

        # Verify realistic metrics
        assert snapshot.telemetry_summary.messages_processed_24h == 100
        assert snapshot.telemetry_summary.errors_24h == 5
        assert snapshot.telemetry_summary.error_rate_percent == 5.0
        assert snapshot.telemetry_summary.thoughts_processed_24h == 34  # ~100/3
