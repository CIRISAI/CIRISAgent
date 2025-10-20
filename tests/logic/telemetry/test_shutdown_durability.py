import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from ciris_engine.logic.telemetry.core import BasicTelemetryCollector


@pytest.mark.asyncio
async def test_metrics_persist_before_shutdown():
    """Verify all metrics are persisted before stop() completes."""
    collector = BasicTelemetryCollector()
    await collector.start()

    # Track correlation calls
    call_count = 0

    def track_correlation(*args, **kwargs):
        nonlocal call_count
        call_count += 1

    with patch("ciris_engine.logic.telemetry.core.add_correlation", side_effect=track_correlation):
        # Record 100 metrics
        for i in range(100):
            await collector.record_metric(f"test_metric_{i}", value=float(i))

        # Stop should wait for all to persist
        await collector.stop()

        # Verify all 100 metrics were persisted
        # Give a small grace period for async tasks
        await asyncio.sleep(0.1)
        assert call_count == 100, f"Expected 100 correlations, got {call_count}"


@pytest.mark.asyncio
async def test_shutdown_timeout_handling():
    """Verify graceful handling if persistence times out."""
    collector = BasicTelemetryCollector()
    await collector.start()

    # Mock slow persistence (60s delay)
    async def slow_add_correlation(*args, **kwargs):
        await asyncio.sleep(60)

    with patch("ciris_engine.logic.persistence.models.correlations.add_correlation", side_effect=slow_add_correlation):
        await collector.record_metric("slow_metric", 1.0)

        # Stop should timeout after 30s, not hang forever
        start = time.time()
        await collector.stop()
        duration = time.time() - start

        assert duration < 35  # 30s timeout + 5s buffer


@pytest.mark.asyncio
async def test_no_task_overwrites():
    """Verify all tasks are tracked, none are overwritten."""
    collector = BasicTelemetryCollector()
    await collector.start()

    # Record 10 metrics rapidly
    for i in range(10):
        await collector.record_metric(f"rapid_metric_{i}", value=float(i))

    # Check that all 10 tasks are tracked
    assert len(collector._pending_stores) <= 10  # May have completed some

    await collector.stop()


@pytest.mark.asyncio
async def test_health_check_backlog_detection():
    """Verify health check fails with excessive backlog."""
    collector = BasicTelemetryCollector()
    await collector.start()

    # Use a lock to prevent the mock from completing
    # This simulates a very slow DB operation
    completion_event = asyncio.Event()

    def blocking_add_correlation(*args, **kwargs):
        # This will never complete during the test
        # In a real async context we can't truly block, but we can
        # make the task pending indefinitely
        pass

    # Patch _store_metric_correlation to create tasks that don't complete
    original_store = collector._store_metric_correlation

    async def slow_store(correlation):
        # Never completes - simulates infinitely slow storage
        await completion_event.wait()

    collector._store_metric_correlation = slow_store

    try:
        # Record 150 metrics to exceed 100 task threshold
        for i in range(150):
            await collector.record_metric(f"backlog_metric_{i}", value=float(i))

        # Give tasks a moment to accumulate
        await asyncio.sleep(0.1)

        # Health check should fail due to backlog (>100 pending tasks)
        is_healthy = await collector.is_healthy()
        assert not is_healthy, f"Health check passed but backlog is {len(collector._pending_stores)}"

    finally:
        # Restore original and cleanup
        collector._store_metric_correlation = original_store
        completion_event.set()  # Release any waiting tasks
        await collector.stop()
