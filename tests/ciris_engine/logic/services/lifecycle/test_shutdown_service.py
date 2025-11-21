"""Unit tests for ShutdownService."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus


@pytest.mark.asyncio
async def test_shutdown_service_lifecycle():
    """Test ShutdownService start/stop lifecycle."""
    service = ShutdownService()

    # Before start
    assert service._started is False

    # Start
    await service.start()
    assert service._started is True
    assert service._shutdown_event is not None

    # Stop
    await service.stop()
    assert service._started is False


@pytest.mark.asyncio
async def test_shutdown_service_request_shutdown():
    """Test requesting shutdown."""
    service = ShutdownService()

    # Initially not requested
    assert service.is_shutdown_requested() is False
    assert service.get_shutdown_reason() is None

    # Request shutdown
    await service.request_shutdown("Test reason")

    # Now requested
    assert service.is_shutdown_requested() is True
    assert service.get_shutdown_reason() == "Test reason"


@pytest.mark.asyncio
async def test_shutdown_service_register_handler():
    """Test registering shutdown handlers."""
    service = ShutdownService()

    # Mock handler with __name__ attribute
    handler = MagicMock()
    handler.__name__ = "mock_handler"

    # Register handler
    service.register_shutdown_handler(handler)

    # Request shutdown - should call handler
    await service.request_shutdown("Test")
    handler.assert_called_once()


@pytest.mark.asyncio
async def test_shutdown_service_async_handler():
    """Test registering async shutdown handlers."""
    service = ShutdownService()
    await service.start()

    # Mock async handler with __name__ attribute
    handler = AsyncMock()
    handler.__name__ = "mock_async_handler"

    # Register async handler (using internal method)
    service._register_async_shutdown_handler(handler)

    # Request shutdown - async handlers are not automatically called
    await service.request_shutdown("Test async")
    # Note: async handlers need to be executed separately in the actual implementation


@pytest.mark.asyncio
async def test_shutdown_service_wait_for_shutdown():
    """Test waiting for shutdown."""
    service = ShutdownService()
    await service.start()

    # Start waiting in background (using internal method)
    wait_task = asyncio.create_task(service._wait_for_shutdown())

    # Give it a moment
    await asyncio.sleep(0.1)
    assert not wait_task.done()

    # Request shutdown
    await service.request_shutdown("Test wait")

    # Wait should complete
    await asyncio.wait_for(wait_task, timeout=1.0)
    assert wait_task.done()


def test_shutdown_service_capabilities():
    """Test ShutdownService.get_capabilities() returns correct info."""
    service = ShutdownService()

    caps = service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "ShutdownService"
    assert caps.version == "1.0.0"
    assert "request_shutdown" in caps.actions
    assert "register_shutdown_handler" in caps.actions
    assert "is_shutdown_requested" in caps.actions
    assert "get_shutdown_reason" in caps.actions
    assert len(caps.dependencies) == 0
    assert caps.metadata.description == "Coordinates graceful system shutdown"


@pytest.mark.asyncio
async def test_shutdown_service_status():
    """Test ShutdownService.get_status() returns correct status."""
    service = ShutdownService()

    # Before start
    status = service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "ShutdownService"
    assert status.service_type == "shutdown"
    assert status.is_healthy is False

    # After start
    await service.start()
    status = service.get_status()
    assert status.is_healthy is True
    assert status.metrics["shutdown_requested"] == 0.0

    # After shutdown request
    await service.request_shutdown("Test status")
    status = service.get_status()
    assert status.metrics["shutdown_requested"] == 1.0

    # After stop
    await service.stop()
    status = service.get_status()
    assert status.is_healthy is False


@pytest.mark.asyncio
async def test_shutdown_service_multiple_handlers():
    """Test that multiple shutdown handlers are called."""
    service = ShutdownService()

    # Mock handlers with names
    handler1 = MagicMock()
    handler1.__name__ = "handler1"
    handler2 = MagicMock()
    handler2.__name__ = "handler2"
    handler3 = MagicMock()
    handler3.__name__ = "handler3"

    # Register handlers
    service.register_shutdown_handler(handler1)
    service.register_shutdown_handler(handler2)
    service.register_shutdown_handler(handler3)

    # Request shutdown - all should be called
    await service.request_shutdown("Test multiple")

    handler1.assert_called_once()
    handler2.assert_called_once()
    handler3.assert_called_once()


def test_shutdown_service_thread_safety():
    """Test that shutdown operations are thread-safe."""
    import asyncio
    import threading

    service = ShutdownService()

    # Track calls
    call_count = 0

    def handler():
        nonlocal call_count
        call_count += 1

    handler.__name__ = "test_handler"
    service.register_shutdown_handler(handler)

    # Function to run async request_shutdown in thread
    def thread_shutdown(reason):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(service.request_shutdown(reason))
        finally:
            loop.close()
            asyncio.set_event_loop(None)

    # Multiple threads trying to shutdown
    threads = []
    for i in range(10):
        t = threading.Thread(target=thread_shutdown, args=(f"Thread {i}",))
        threads.append(t)
        t.start()

    # Wait for all threads
    for t in threads:
        t.join()

    # Handler should only be called once due to thread safety
    assert call_count == 1
    assert service.is_shutdown_requested() is True


@pytest.mark.asyncio
async def test_is_force_shutdown_initially_false():
    """Test is_force_shutdown() returns False initially."""
    service = ShutdownService()

    assert service.is_force_shutdown() is False


@pytest.mark.asyncio
async def test_is_force_shutdown_false_after_normal_shutdown():
    """Test is_force_shutdown() returns False after normal shutdown."""
    service = ShutdownService()
    await service.start()

    # Request normal shutdown
    await service.request_shutdown("Normal shutdown")

    # Should not be force shutdown
    assert service.is_shutdown_requested() is True
    assert service.is_force_shutdown() is False


@pytest.mark.asyncio
async def test_is_force_shutdown_true_after_emergency_shutdown():
    """Test is_force_shutdown() returns True after emergency shutdown."""
    service = ShutdownService()
    await service.start()

    # Track if sys.exit was called
    exit_called = False

    def mock_exit(code):
        nonlocal exit_called
        exit_called = True
        # Don't actually exit during test
        raise SystemExit(code)

    # Mock sys.exit to prevent actual termination
    import sys
    original_exit = sys.exit
    sys.exit = mock_exit

    try:
        # Request emergency shutdown (will raise SystemExit)
        with pytest.raises(SystemExit):
            await service.emergency_shutdown("Emergency test", timeout_seconds=1)

        # Should be marked as force shutdown
        assert service.is_shutdown_requested() is True
        assert service.is_force_shutdown() is True
        assert exit_called is True

        # Reason should have EMERGENCY prefix
        assert "EMERGENCY:" in service.get_shutdown_reason()

    finally:
        # Restore original sys.exit
        sys.exit = original_exit


@pytest.mark.asyncio
async def test_emergency_shutdown_executes_handlers():
    """Test emergency_shutdown() executes both sync and async handlers."""
    service = ShutdownService()
    await service.start()

    # Track handler calls
    sync_called = False
    async_called = False

    def sync_handler():
        nonlocal sync_called
        sync_called = True
    sync_handler.__name__ = "sync_handler"

    async def async_handler():
        nonlocal async_called
        async_called = True
    async_handler.__name__ = "async_handler"

    # Register handlers
    service.register_shutdown_handler(sync_handler)
    service._register_async_shutdown_handler(async_handler)

    # Mock sys.exit to prevent actual termination
    import sys
    original_exit = sys.exit
    sys.exit = lambda code: (_ for _ in ()).throw(SystemExit(code))

    try:
        # Request emergency shutdown (will raise SystemExit)
        with pytest.raises(SystemExit):
            await service.emergency_shutdown("Handler test", timeout_seconds=1)

        # Both handlers should have been called
        assert sync_called is True
        assert async_called is True

    finally:
        # Restore original sys.exit
        sys.exit = original_exit


@pytest.mark.asyncio
async def test_emergency_shutdown_timeout_handling():
    """Test emergency_shutdown() handles handler timeout correctly."""
    service = ShutdownService()
    await service.start()

    # Create a slow async handler that will timeout
    async def slow_handler():
        await asyncio.sleep(10)  # Sleep longer than timeout
    slow_handler.__name__ = "slow_handler"

    service._register_async_shutdown_handler(slow_handler)

    # Mock sys.exit to prevent actual termination
    import sys
    original_exit = sys.exit
    sys.exit = lambda code: (_ for _ in ()).throw(SystemExit(code))

    try:
        # Request emergency shutdown with short timeout
        with pytest.raises(SystemExit):
            await service.emergency_shutdown("Timeout test", timeout_seconds=1)

        # Should still complete despite handler timeout
        assert service.is_force_shutdown() is True

    finally:
        # Restore original sys.exit
        sys.exit = original_exit


@pytest.mark.asyncio
async def test_emergency_shutdown_metrics():
    """Test emergency_shutdown() updates metrics correctly."""
    service = ShutdownService()
    await service.start()

    # Get initial metrics
    initial_metrics = await service.get_metrics()
    assert initial_metrics["shutdown_requests_total"] == 0.0
    assert initial_metrics["shutdown_emergency_total"] == 0.0

    # Mock sys.exit to prevent actual termination
    import sys
    original_exit = sys.exit
    sys.exit = lambda code: (_ for _ in ()).throw(SystemExit(code))

    try:
        # Request emergency shutdown (will raise SystemExit)
        with pytest.raises(SystemExit):
            await service.emergency_shutdown("Metrics test", timeout_seconds=1)

        # Check metrics updated
        final_metrics = await service.get_metrics()
        assert final_metrics["shutdown_requests_total"] == 1.0
        assert final_metrics["shutdown_emergency_total"] == 1.0
        assert final_metrics["shutdown_graceful_total"] == 0.0

    finally:
        # Restore original sys.exit
        sys.exit = original_exit
