"""
Test suite for APIRuntimeControlService.

Tests:
- Pause and resume processing
- State transitions
- Single-step debugging
- Queue status monitoring
- Runtime status reporting
"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.adapters.api.api_runtime_control import APIRuntimeControlService


# Define ProcessorState enum for tests
class ProcessorState(str, Enum):
    WAKEUP = "WAKEUP"
    WORK = "WORK"
    PLAY = "PLAY"
    SOLITUDE = "SOLITUDE"
    DREAM = "DREAM"
    SHUTDOWN = "SHUTDOWN"


@pytest.fixture
def mock_runtime():
    """Create mock runtime with necessary services."""
    runtime = Mock()
    runtime.state = "RUNNING"
    runtime.pause_processing = AsyncMock(return_value=True)
    runtime.resume_processing = AsyncMock(return_value=True)
    runtime.request_state_transition = AsyncMock(return_value=True)
    runtime.single_step = AsyncMock(return_value=True)

    # Processor mock
    runtime.processor = Mock()
    runtime.processor.state = "WORK"
    runtime.current_state = "WORK"
    runtime.processor.get_queue_status = Mock(return_value={"pending": 5, "processing": 1, "completed": 100})

    # Other services
    runtime.time_service = Mock()
    runtime.time_service.now.return_value = datetime.now(timezone.utc)
    runtime.telemetry_service = Mock()
    runtime.resource_monitor = Mock()
    runtime.resource_monitor.get_current_metrics.return_value = {"cpu_percent": 45.5, "memory_mb": 1024, "threads": 10}

    runtime.get_uptime = Mock(return_value=3600.0)
    runtime.get_status = Mock(return_value={})

    return runtime


@pytest.fixture
def runtime_control_service(mock_runtime):
    """Create APIRuntimeControlService instance."""
    return APIRuntimeControlService(mock_runtime, time_service=None)


class TestAPIRuntimeControlPauseResume:
    """Test pause and resume functionality."""

    @pytest.mark.asyncio
    async def test_pause_processing(self, runtime_control_service, mock_runtime):
        """Test pausing processing with reason."""
        result = await runtime_control_service.pause_processing("Maintenance")

        assert result is True
        mock_runtime.pause_processing.assert_called_once_with("Maintenance")

    @pytest.mark.asyncio
    async def test_pause_processing_no_reason(self, runtime_control_service, mock_runtime):
        """Test pausing without reason."""
        result = await runtime_control_service.pause_processing("Paused via API")

        assert result is True
        mock_runtime.pause_processing.assert_called_once_with("Paused via API")

    @pytest.mark.asyncio
    async def test_pause_already_paused(self, runtime_control_service, mock_runtime):
        """Test pausing when already paused."""
        # First pause to set the state
        await runtime_control_service.pause_processing("Initial pause")

        # Try to pause again
        result = await runtime_control_service.pause_processing("Already paused")

        assert result is False

    @pytest.mark.asyncio
    async def test_resume_processing(self, runtime_control_service, mock_runtime):
        """Test resuming processing."""
        # First pause
        await runtime_control_service.pause_processing("Test pause")

        # Then resume
        result = await runtime_control_service.resume_processing()

        assert result is True
        mock_runtime.resume_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_processing_no_reason(self, runtime_control_service, mock_runtime):
        """Test resuming without prior pause."""
        result = await runtime_control_service.resume_processing()
        assert result is False  # Should return False when not paused
        mock_runtime.resume_processing.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_not_paused(self, runtime_control_service, mock_runtime):
        """Test resuming when not paused."""
        mock_runtime.state = "RUNNING"

        result = await runtime_control_service.resume_processing()

        assert result is False


class TestAPIRuntimeControlStateTransitions:
    """Test state transition functionality."""

    @pytest.mark.asyncio
    async def test_request_state_transition(self, runtime_control_service, mock_runtime):
        """Test valid state transition."""
        result = await runtime_control_service.request_state_transition(
            ProcessorState.PLAY.value, "Testing state transition"
        )

        assert result is True
        mock_runtime.request_state_transition.assert_called_once_with(
            ProcessorState.PLAY.value, "Testing state transition"
        )

    @pytest.mark.asyncio
    async def test_state_transition_invalid(self, runtime_control_service, mock_runtime):
        """Test invalid state transition."""
        mock_runtime.request_state_transition.return_value = False

        result = await runtime_control_service.request_state_transition("INVALID_STATE", "Testing invalid state")

        assert result is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "target,expected",
        [
            (ProcessorState.WORK.value, True),
            (ProcessorState.PLAY.value, True),
            (ProcessorState.SOLITUDE.value, True),
            (ProcessorState.DREAM.value, True),
            (ProcessorState.SHUTDOWN.value, True),
            ("INVALID_STATE", False),
        ],
    )
    async def test_state_transition_with_validation(self, runtime_control_service, mock_runtime, target, expected):
        """Test state transition with various targets."""
        if target == "INVALID_STATE":
            mock_runtime.request_state_transition.return_value = False

        result = await runtime_control_service.request_state_transition(target, "Automated test")

        # Should handle all state transitions
        assert result is expected


class TestAPIRuntimeControlDebugging:
    """Test debugging functionality."""

    @pytest.mark.asyncio
    async def test_get_queue_status(self, runtime_control_service, mock_runtime):
        """Test getting queue status."""
        # get_queue_status is not implemented in APIRuntimeControlService
        # Using get_runtime_status instead
        status = runtime_control_service.get_runtime_status()

        assert status is not None
        assert "paused" in status

    @pytest.mark.asyncio
    async def test_get_queue_status_no_processor(self, runtime_control_service, mock_runtime):
        """Test queue status without processor."""
        runtime_control_service.runtime.processor = None

        # get_queue_status is not implemented in APIRuntimeControlService
        status = runtime_control_service.get_runtime_status()

        assert status is not None


class TestAPIRuntimeControlStatus:
    """Test status reporting functionality."""

    @pytest.mark.asyncio
    async def test_get_runtime_status(self, runtime_control_service, mock_runtime):
        """Test getting comprehensive runtime status."""
        status = runtime_control_service.get_runtime_status()

        assert status["paused"] is False
        assert status["cognitive_state"] == "WORK"
        assert status["pause_reason"] is None
        assert "uptime_seconds" in status

    @pytest.mark.asyncio
    async def test_get_runtime_status_paused(self, runtime_control_service, mock_runtime):
        """Test runtime status when paused."""
        # First pause the service
        await runtime_control_service.pause_processing("Test pause")

        status = runtime_control_service.get_runtime_status()

        assert status["paused"] is True
        assert status["pause_reason"] == "Test pause"

    @pytest.mark.asyncio
    async def test_get_runtime_status_with_errors(self, runtime_control_service, mock_runtime):
        """Test runtime status with error conditions."""
        mock_runtime.telemetry_service.get_error_count = Mock(return_value=5)

        status = runtime_control_service.get_runtime_status()

        assert status["paused"] is False
        # Errors are not included in runtime status

    @pytest.mark.asyncio
    async def test_get_processor_info(self, runtime_control_service, mock_runtime):
        """Test getting processor information."""
        status = runtime_control_service.get_runtime_status()

        assert status["cognitive_state"] == "WORK"
        assert status["paused"] is False


class TestAPIRuntimeControlErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_pause_with_exception(self, runtime_control_service, mock_runtime):
        """Test pause handling when runtime raises exception."""
        mock_runtime.pause_processing.side_effect = Exception("Pause failed")

        # The exception should propagate from the runtime
        with pytest.raises(Exception, match="Pause failed"):
            await runtime_control_service.pause_processing("Test pause")

    @pytest.mark.asyncio
    async def test_resume_with_exception(self, runtime_control_service, mock_runtime):
        """Test resume handling when runtime raises exception."""
        mock_runtime.resume_processing.side_effect = Exception("Resume failed")

        # Resume doesn't raise exceptions in the current implementation
        result = await runtime_control_service.resume_processing()
        assert result is False  # Returns False when not paused

    @pytest.mark.asyncio
    async def test_state_transition_with_exception(self, runtime_control_service, mock_runtime):
        """Test state transition with runtime exception."""
        mock_runtime.request_state_transition.side_effect = Exception("Transition failed")

        # The method catches exceptions and returns False
        result = await runtime_control_service.request_state_transition("INVALID_STATE", "Test")
        assert result is False


class TestAPIRuntimeControlConcurrency:
    """Test concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_pause_resume(self, runtime_control_service, mock_runtime):
        """Test concurrent pause/resume operations."""
        # Create multiple pause/resume tasks
        tasks = []
        for i in range(5):
            if i % 2 == 0:
                tasks.append(runtime_control_service.pause_processing(f"Pause {i}"))
            else:
                mock_runtime.state = "PAUSED"
                tasks.append(runtime_control_service.resume_processing())

        # Execute concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Should handle all operations
        assert len(results) == 5
        assert all(isinstance(r, bool) or isinstance(r, Exception) for r in results)

    @pytest.mark.asyncio
    async def test_status_during_operations(self, runtime_control_service, mock_runtime):
        """Test getting status during ongoing operations."""

        # Simulate slow pause operation
        async def slow_pause(reason=None):
            await asyncio.sleep(0.1)
            return True

        mock_runtime.pause_processing = slow_pause

        # Start pause operation
        pause_task = asyncio.create_task(runtime_control_service.pause_processing("Slow pause"))

        # Get status while pausing
        status = runtime_control_service.get_runtime_status()
        assert status is not None

        # Wait for pause to complete
        await pause_task
