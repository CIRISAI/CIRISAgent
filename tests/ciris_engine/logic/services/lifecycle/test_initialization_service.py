"""Unit tests for InitializationService."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from ciris_engine.logic.services.lifecycle.initialization import InitializationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.lifecycle.initialization import InitializationStatus
from ciris_engine.schemas.services.operations import InitializationPhase


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def init_service(time_service):
    """Create an initialization service for testing."""
    return InitializationService(time_service)


@pytest.mark.asyncio
async def test_initialization_service_lifecycle(init_service):
    """Test InitializationService start/stop lifecycle."""
    # Before start
    assert init_service._started is False

    # Start
    await init_service.start()
    assert init_service._started is True

    # Stop
    await init_service.stop()
    assert init_service._started is False


@pytest.mark.asyncio
async def test_initialization_service_register_step(init_service):
    """Test registering initialization steps."""
    # Mock handler
    handler = AsyncMock()

    # Register step
    init_service.register_step(phase=InitializationPhase.INFRASTRUCTURE, name="test_step", handler=handler)

    # Verify step was registered
    assert len(init_service._steps) == 1
    assert init_service._steps[0].name == "test_step"
    assert init_service._steps[0].phase == InitializationPhase.INFRASTRUCTURE


@pytest.mark.asyncio
async def test_initialization_service_initialize(init_service):
    """Test running initialization."""
    await init_service.start()

    # Mock handlers
    handler1 = AsyncMock()
    handler2 = AsyncMock()

    # Register steps for same phase
    init_service.register_step(phase=InitializationPhase.INFRASTRUCTURE, name="step1", handler=handler1)
    init_service.register_step(phase=InitializationPhase.INFRASTRUCTURE, name="step2", handler=handler2)

    # Run initialization
    success = await init_service.initialize()

    # Should succeed
    assert success is True

    # Both handlers should be called
    handler1.assert_called_once()
    handler2.assert_called_once()

    # Steps should be marked complete (with phase prefix)
    assert "infrastructure/step1" in init_service._completed_steps
    assert "infrastructure/step2" in init_service._completed_steps


@pytest.mark.asyncio
async def test_initialization_service_with_verifier(init_service):
    """Test initialization step with verification."""
    await init_service.start()

    # Mock handler and verifier
    handler = AsyncMock()
    verifier = AsyncMock(return_value=True)

    # Register step with verifier
    init_service.register_step(phase=InitializationPhase.DATABASE, name="db_init", handler=handler, verifier=verifier)

    # Run initialization
    success = await init_service.initialize()

    # Should succeed
    assert success is True

    # Both should be called
    handler.assert_called_once()
    verifier.assert_called_once()


@pytest.mark.asyncio
async def test_initialization_service_failed_verification(init_service):
    """Test initialization failure when verification fails."""
    await init_service.start()

    # Mock handler and failing verifier
    handler = AsyncMock()
    verifier = AsyncMock(return_value=False)

    # Register critical step with failing verifier
    init_service.register_step(
        phase=InitializationPhase.DATABASE, name="db_init", handler=handler, verifier=verifier, critical=True
    )

    # Running initialization should fail
    success = await init_service.initialize()
    assert success is False

    # Should have an error
    assert init_service._error is not None


@pytest.mark.asyncio
async def test_initialization_service_non_critical_failure(init_service):
    """Test non-critical step failure doesn't stop initialization."""
    await init_service.start()

    # Mock failing handler
    handler = AsyncMock(side_effect=Exception("Test error"))

    # Register non-critical step
    init_service.register_step(
        phase=InitializationPhase.SERVICES, name="optional_service", handler=handler, critical=False
    )

    # Should succeed despite non-critical failure
    success = await init_service.initialize()
    assert success is True

    # Step should not be in completed list
    assert "optional_service" not in init_service._completed_steps


def test_initialization_service_capabilities(init_service):
    """Test InitializationService.get_capabilities() returns correct info."""
    caps = init_service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "InitializationService"
    assert caps.version == "1.0.0"
    assert "register_step" in caps.actions
    assert "initialize" in caps.actions
    assert "get_initialization_status" in caps.actions
    assert "TimeService" in caps.dependencies
    assert hasattr(caps.metadata, "description") and caps.metadata.description  # Infrastructure services now have metadata


@pytest.mark.asyncio
async def test_initialization_service_status(init_service):
    """Test InitializationService.get_status() returns correct status."""
    # Before start
    status = init_service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "InitializationService"
    assert status.service_type == "initialization"
    assert status.is_healthy is False  # Not running yet

    # After start
    await init_service.start()
    status = init_service.get_status()
    assert status.is_healthy is True
    assert status.metrics["initialization_complete"] == 0.0

    # After running initialization
    handler = AsyncMock()
    init_service.register_step(phase=InitializationPhase.INFRASTRUCTURE, name="test", handler=handler)
    await init_service.initialize()

    status = init_service.get_status()
    assert status.metrics["completed_steps"] == 1.0


@pytest.mark.asyncio
async def test_initialization_service_get_status_details(init_service):
    """Test getting detailed initialization status."""
    await init_service.start()

    # Get initial status
    init_status = await init_service.get_initialization_status()
    assert isinstance(init_status, InitializationStatus)
    assert init_status.completed_steps == []
    assert init_status.complete is False

    # Register and run a step
    handler = AsyncMock()
    init_service.register_step(phase=InitializationPhase.INFRASTRUCTURE, name="test_step", handler=handler)

    # Before running
    init_status = await init_service.get_initialization_status()
    assert init_status.complete is False

    # Run initialization
    await init_service.initialize()

    # After running
    init_status = await init_service.get_initialization_status()
    assert init_status.complete is True
    assert len(init_status.completed_steps) == 1


@pytest.mark.asyncio
async def test_initialization_service_timeout(init_service):
    """Test initialization step timeout."""
    await init_service.start()

    # Mock handler that takes too long
    async def slow_handler():
        await asyncio.sleep(2.0)

    # Register step with short timeout
    init_service.register_step(phase=InitializationPhase.SERVICES, name="slow_step", handler=slow_handler, timeout=0.1)

    # Should fail due to timeout
    success = await init_service.initialize()
    assert success is False
    assert init_service._error is not None
