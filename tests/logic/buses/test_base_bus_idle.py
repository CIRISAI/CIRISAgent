"""
Tests to verify base bus has no busy-looping behavior when idle
"""

import asyncio
import time
from typing import Optional

import pytest

from ciris_engine.logic.buses.base_bus import BaseBus, BusMessage
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.schemas.runtime.enums import ServiceType


class MockBus(BaseBus):
    """Mock implementation of BaseBus for testing"""

    def __init__(self, service_registry: ServiceRegistry):
        super().__init__(ServiceType.LLM, service_registry)
        self.processed_messages = []

    async def _process_message(self, message: BusMessage) -> None:
        """Store processed messages"""
        self.processed_messages.append(message)
        await asyncio.sleep(0.01)  # Simulate processing


@pytest.fixture
def service_registry():
    """Create a mock service registry"""
    return ServiceRegistry()


@pytest.mark.asyncio
async def test_bus_no_busy_loop_when_idle(service_registry):
    """Test that the bus doesn't busy-loop when idle"""
    bus = MockBus(service_registry)

    # Start the bus
    await bus.start()

    # Measure CPU impact by checking event loop iterations
    start_time = time.perf_counter()
    loop_iterations = 0

    async def count_iterations():
        nonlocal loop_iterations
        for _ in range(100):
            loop_iterations += 1
            await asyncio.sleep(0.01)

    # Run for 1 second - if bus is busy-looping, it will consume cycles
    await asyncio.wait_for(count_iterations(), timeout=2.0)
    elapsed = time.perf_counter() - start_time

    # Should complete in ~1 second if no busy-looping
    # Allow some margin for system variance
    assert elapsed < 1.5, f"Event loop appears blocked, took {elapsed}s for 1s of work"
    assert loop_iterations == 100

    # Stop the bus
    await bus.stop()


@pytest.mark.asyncio
async def test_bus_processes_messages_correctly(service_registry):
    """Test that messages are still processed correctly"""
    bus = MockBus(service_registry)

    # Start the bus
    await bus.start()

    # Send some messages
    messages = [
        BusMessage(
            id=f"msg-{i}",
            handler_name="test",
            timestamp=asyncio.get_event_loop().time(),
            metadata={},
        )
        for i in range(5)
    ]

    for msg in messages:
        await bus._enqueue(msg)

    # Wait for processing
    await asyncio.sleep(0.2)

    # Verify all messages were processed
    assert len(bus.processed_messages) == 5
    assert [m.id for m in bus.processed_messages] == [f"msg-{i}" for i in range(5)]

    # Stop the bus
    await bus.stop()


@pytest.mark.asyncio
async def test_bus_shutdown_is_fast(service_registry):
    """Test that shutdown doesn't wait for timeout"""
    bus = MockBus(service_registry)

    # Start the bus
    await bus.start()

    # Wait a bit
    await asyncio.sleep(0.1)

    # Measure shutdown time
    start = time.perf_counter()
    await bus.stop()
    shutdown_time = time.perf_counter() - start

    # Should shutdown almost immediately (not wait for 0.1s timeout)
    assert shutdown_time < 0.5, f"Shutdown took {shutdown_time}s, should be near-instant"


@pytest.mark.asyncio
async def test_bus_alternating_idle_and_active(service_registry):
    """Test bus behavior when alternating between idle and active"""
    bus = MockBus(service_registry)

    # Start the bus
    await bus.start()

    # Idle period
    await asyncio.sleep(0.2)

    # Send message
    msg1 = BusMessage(
        id="msg-1",
        handler_name="test",
        timestamp=asyncio.get_event_loop().time(),
        metadata={},
    )
    await bus._enqueue(msg1)

    # Another idle period
    await asyncio.sleep(0.2)

    # Send another message
    msg2 = BusMessage(
        id="msg-2",
        handler_name="test",
        timestamp=asyncio.get_event_loop().time(),
        metadata={},
    )
    await bus._enqueue(msg2)

    # Wait for processing
    await asyncio.sleep(0.1)

    # Verify both messages were processed
    assert len(bus.processed_messages) == 2
    assert bus.processed_messages[0].id == "msg-1"
    assert bus.processed_messages[1].id == "msg-2"

    # Stop the bus
    await bus.stop()


@pytest.mark.asyncio
async def test_bus_concurrent_operations(service_registry):
    """Test that bus doesn't interfere with concurrent operations"""
    bus = MockBus(service_registry)

    # Start the bus
    await bus.start()

    # Run concurrent tasks
    results = []

    async def concurrent_task(task_id: int):
        await asyncio.sleep(0.05)
        results.append(task_id)

    tasks = [concurrent_task(i) for i in range(10)]

    start = time.perf_counter()
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    # Should complete in ~0.05s if bus isn't interfering
    assert elapsed < 0.2, f"Concurrent tasks delayed by bus, took {elapsed}s"
    assert sorted(results) == list(range(10))

    # Stop the bus
    await bus.stop()
