"""Comprehensive unit tests for Runtime Control Service and Bus."""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.buses.runtime_control_bus import OperationPriority, RuntimeControlBus
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.core.runtime import (
    AdapterInfo,
    AdapterOperationResponse,
    AdapterStatus,
    ConfigSnapshot,
    ProcessorControlResponse,
    ProcessorQueueStatus,
    ProcessorStatus,
    RuntimeStatusResponse,
)

# No need to add path since we're in the proper test structure


class MockRuntimeControlService:
    """Mock implementation of RuntimeControlService for testing."""

    def __init__(self):
        self.is_healthy = AsyncMock(return_value=True)
        self.get_capabilities = MagicMock(
            return_value=ServiceCapabilities(
                service_name="mock_runtime_control",
                version="1.0.0",
                actions=[
                    "pause_processing",
                    "resume_processing",
                    "single_step",
                    "get_processor_queue_status",
                    "shutdown_runtime",
                    "load_adapter",
                    "unload_adapter",
                    "list_adapters",
                    "get_adapter_info",
                    "get_config",
                    "get_runtime_status",
                ],
            )
        )

        # Mock all the protocol methods
        self.pause_processing = AsyncMock()
        self.resume_processing = AsyncMock()
        self.single_step = AsyncMock()
        self.get_processor_queue_status = AsyncMock()
        self.shutdown_runtime = AsyncMock()
        self.load_adapter = AsyncMock()
        self.unload_adapter = AsyncMock()
        self.list_adapters = AsyncMock()
        self.get_adapter_info = AsyncMock()
        self.get_config = AsyncMock()
        self.update_config = AsyncMock()
        self.validate_config = AsyncMock()
        self.backup_config = AsyncMock()
        self.restore_config = AsyncMock()
        self.list_config_backups = AsyncMock()
        self.get_runtime_status = AsyncMock()
        self.get_runtime_snapshot = AsyncMock()
        self.get_service_health_status = AsyncMock()
        self.get_events_history = MagicMock()
        self.update_service_priority = AsyncMock()
        self.reset_circuit_breakers = AsyncMock()
        self.get_circuit_breaker_status = AsyncMock()
        self.get_service_selection_explanation = AsyncMock()
        self.handle_emergency_shutdown = AsyncMock()


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    service = MagicMock(spec=TimeServiceProtocol)
    service.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
    service.now_iso.return_value = "2025-01-01T12:00:00"
    return service


@pytest.fixture
def mock_service_registry():
    """Create a mock service registry."""
    registry = MagicMock(spec=ServiceRegistry)
    registry.get_providers = MagicMock(return_value=[])
    return registry


@pytest.fixture
def mock_runtime_control_service():
    """Create a mock runtime control service."""
    return MockRuntimeControlService()


@pytest.fixture
def runtime_control_bus(mock_service_registry, mock_time_service):
    """Create a runtime control bus for testing."""
    bus = RuntimeControlBus(service_registry=mock_service_registry, time_service=mock_time_service)
    return bus


class TestRuntimeControlBus:
    """Test suite for RuntimeControlBus."""

    def test_initialization(self, mock_service_registry, mock_time_service):
        """Test bus initialization."""
        bus = RuntimeControlBus(service_registry=mock_service_registry, time_service=mock_time_service)
        assert bus.service_type == ServiceType.RUNTIME_CONTROL
        assert bus._time_service == mock_time_service
        assert bus._active_operations == {}
        assert bus._shutting_down is False
        assert bus._operation_lock is not None

    @pytest.mark.asyncio
    async def test_get_processor_queue_status_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful processor queue status retrieval."""
        expected_status = ProcessorQueueStatus(
            processor_name="test_processor",
            queue_size=10,
            max_size=1000,
            processing_rate=5.0,
            average_latency_ms=100.0,
            oldest_message_age_seconds=300.0,
        )

        mock_runtime_control_service.get_processor_queue_status.return_value = expected_status
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        status = await runtime_control_bus.get_processor_queue_status("test_processor")

        assert status == expected_status
        runtime_control_bus.get_service.assert_called_once_with(
            handler_name="test_processor", required_capabilities=["get_processor_queue_status"]
        )

    @pytest.mark.asyncio
    async def test_get_processor_queue_status_no_service(self, runtime_control_bus):
        """Test processor queue status when no service is available."""
        runtime_control_bus.get_service = AsyncMock(return_value=None)

        status = await runtime_control_bus.get_processor_queue_status("test_processor")

        assert status.processor_name == "test_processor"
        assert status.queue_size == 0
        assert status.processing_rate == 0.0

    @pytest.mark.asyncio
    async def test_get_processor_queue_status_exception(self, runtime_control_bus, mock_runtime_control_service):
        """Test processor queue status when service raises exception."""
        mock_runtime_control_service.get_processor_queue_status.side_effect = Exception("Test error")
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        status = await runtime_control_bus.get_processor_queue_status("test_processor")

        assert status.processor_name == "test_processor"
        assert status.queue_size == 0
        assert status.processing_rate == 0.0

    @pytest.mark.asyncio
    async def test_shutdown_runtime_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful runtime shutdown."""
        expected_response = ProcessorControlResponse(
            success=True,
            processor_name="test_processor",
            operation="shutdown",
            new_status=ProcessorStatus.STOPPED,
            error=None,
        )

        mock_runtime_control_service.shutdown_runtime.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        response = await runtime_control_bus.shutdown_runtime("Test shutdown", "test_processor")

        assert response.success is True
        assert response.new_status == ProcessorStatus.STOPPED
        assert runtime_control_bus._shutting_down is True

    @pytest.mark.asyncio
    async def test_shutdown_runtime_already_shutting_down(self, runtime_control_bus):
        """Test shutdown when already shutting down."""
        runtime_control_bus._shutting_down = True

        response = await runtime_control_bus.shutdown_runtime("Test shutdown", "test_processor")

        assert response.success is True
        assert response.new_status == ProcessorStatus.STOPPED

    @pytest.mark.asyncio
    async def test_shutdown_runtime_cancel_active_operations(self, runtime_control_bus, mock_runtime_control_service):
        """Test that shutdown cancels active operations."""
        # Add mock active operations
        mock_task1 = MagicMock(spec=asyncio.Task)
        mock_task2 = MagicMock(spec=asyncio.Task)
        runtime_control_bus._active_operations = {"operation1": mock_task1, "operation2": mock_task2}

        expected_response = ProcessorControlResponse(
            success=True,
            processor_name="test_processor",
            operation="shutdown",
            new_status=ProcessorStatus.STOPPED,
            error=None,
        )

        mock_runtime_control_service.shutdown_runtime.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        await runtime_control_bus.shutdown_runtime("Test shutdown", "test_processor")

        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_called_once()
        assert runtime_control_bus._active_operations == {}

    @pytest.mark.asyncio
    async def test_get_config_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful config retrieval."""
        expected_config = ConfigSnapshot(
            configs={"key1": "value1", "key2": "value2"}, version="1.0.0", metadata={"source": "test"}
        )

        mock_runtime_control_service.get_config.return_value = expected_config
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        config = await runtime_control_bus.get_config("/test/path", True, "test_handler")

        assert config == expected_config
        mock_runtime_control_service.get_config.assert_called_once_with("/test/path", True)

    @pytest.mark.asyncio
    async def test_get_runtime_status_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful runtime status retrieval."""
        expected_response = RuntimeStatusResponse(
            is_running=True,
            uptime_seconds=3600,
            processor_count=2,
            adapter_count=3,
            total_messages_processed=1000,
            current_load=0.75,
        )

        mock_runtime_control_service.get_runtime_status.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        # Add some active operations
        runtime_control_bus._active_operations = {"op1": MagicMock(), "op2": MagicMock()}

        status = await runtime_control_bus.get_runtime_status("test_handler")

        assert status["is_running"] is True
        assert status["uptime_seconds"] == 3600
        assert status["processor_count"] == 2
        assert status["adapter_count"] == 3
        assert status["total_messages_processed"] == 1000
        assert status["current_load"] == 0.75
        assert status["bus_status"]["active_operations"] == ["op1", "op2"]
        assert status["bus_status"]["shutting_down"] is False

    @pytest.mark.asyncio
    async def test_load_adapter_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful adapter loading."""
        expected_response = AdapterOperationResponse(
            success=True,
            adapter_id="test_adapter",
            adapter_type="discord",
            status=AdapterStatus.RUNNING,
            operation="load",
            timestamp=datetime.now(),
            error=None,
        )

        mock_runtime_control_service.load_adapter.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.load_adapter(
            "discord", "test_adapter", {"token": "test"}, True, "test_handler"
        )

        assert result.adapter_id == "test_adapter"
        assert result.adapter_type == "discord"
        assert result.status == AdapterStatus.RUNNING
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_load_adapter_during_shutdown(self, runtime_control_bus):
        """Test adapter loading during shutdown."""
        runtime_control_bus._shutting_down = True

        result = await runtime_control_bus.load_adapter(
            "discord", "test_adapter", {"token": "test"}, True, "test_handler"
        )

        assert result.status == AdapterStatus.ERROR
        assert result.last_error == "System shutting down"

    @pytest.mark.asyncio
    async def test_unload_adapter_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful adapter unloading."""
        expected_response = AdapterOperationResponse(
            success=True,
            adapter_id="test_adapter",
            adapter_type="discord",
            status=AdapterStatus.STOPPED,
            operation="unload",
            timestamp=datetime.now(),
            error=None,
        )

        mock_runtime_control_service.unload_adapter.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.unload_adapter("test_adapter", False, "test_handler")

        assert result.adapter_id == "test_adapter"
        assert result.status == AdapterStatus.STOPPED
        assert result.started_at is None  # Adapter is unloaded

    @pytest.mark.asyncio
    async def test_list_adapters_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful adapter listing."""
        expected_adapters = [
            AdapterInfo(
                adapter_id="adapter1",
                adapter_type="discord",
                status=AdapterStatus.RUNNING,
                started_at=datetime.now(),
                messages_processed=100,
                error_count=0,
                last_error=None,
                tools=None,
            ),
            AdapterInfo(
                adapter_id="adapter2",
                adapter_type="api",
                status=AdapterStatus.RUNNING,
                started_at=datetime.now(),
                messages_processed=200,
                error_count=1,
                last_error=None,
                tools=None,
            ),
        ]

        mock_runtime_control_service.list_adapters.return_value = expected_adapters
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        adapters = await runtime_control_bus.list_adapters("test_handler")

        assert len(adapters) == 2
        assert adapters[0].adapter_id == "adapter1"
        assert adapters[1].adapter_id == "adapter2"

    @pytest.mark.asyncio
    async def test_pause_processing_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful processing pause."""
        expected_response = ProcessorControlResponse(
            success=True,
            processor_name="test_processor",
            operation="pause",
            new_status=ProcessorStatus.PAUSED,
            error=None,
        )

        mock_runtime_control_service.pause_processing.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.pause_processing("test_handler")

        assert result is True

    @pytest.mark.asyncio
    async def test_pause_processing_during_shutdown(self, runtime_control_bus):
        """Test pause processing during shutdown."""
        runtime_control_bus._shutting_down = True

        result = await runtime_control_bus.pause_processing("test_handler")

        assert result is False

    @pytest.mark.asyncio
    async def test_resume_processing_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful processing resume."""
        expected_response = ProcessorControlResponse(
            success=True,
            processor_name="test_processor",
            operation="resume",
            new_status=ProcessorStatus.RUNNING,
            error=None,
        )

        mock_runtime_control_service.resume_processing.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.resume_processing("test_handler")

        assert result is True

    @pytest.mark.asyncio
    async def test_single_step_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful single step execution."""
        expected_response = ProcessorControlResponse(
            success=True,
            processor_name="test_processor",
            operation="single_step",
            new_status=ProcessorStatus.PAUSED,
            error=None,
        )

        mock_runtime_control_service.single_step.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.single_step("test_handler")

        assert result == expected_response

    @pytest.mark.asyncio
    async def test_single_step_failed(self, runtime_control_bus, mock_runtime_control_service):
        """Test failed single step execution."""
        expected_response = ProcessorControlResponse(
            success=False,
            processor_name="test_processor",
            operation="single_step",
            new_status=ProcessorStatus.PAUSED,
            error="No thoughts to process",
        )

        mock_runtime_control_service.single_step.return_value = expected_response
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.single_step("test_handler")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_adapter_info_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test successful adapter info retrieval."""
        from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema

        # Create proper ToolInfo objects with required parameters field
        tool1 = ToolInfo(
            name="tool1",
            description="Tool 1",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[]
            )
        )
        tool2 = ToolInfo(
            name="tool2",
            description="Tool 2",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[]
            )
        )

        expected_info = AdapterInfo(
            adapter_id="test_adapter",
            adapter_type="discord",
            status=AdapterStatus.RUNNING,
            started_at=datetime.now(),
            messages_processed=500,
            error_count=2,
            last_error=None,
            tools=[tool1, tool2],
        )

        mock_runtime_control_service.get_adapter_info.return_value = expected_info
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        info = await runtime_control_bus.get_adapter_info("test_adapter", "test_handler")

        assert info == expected_info

    @pytest.mark.asyncio
    async def test_get_adapter_info_not_found(self, runtime_control_bus, mock_runtime_control_service):
        """Test adapter info when adapter not found."""
        mock_runtime_control_service.get_adapter_info.return_value = None
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        info = await runtime_control_bus.get_adapter_info("unknown_adapter", "test_handler")

        assert info.adapter_id == "unknown_adapter"
        assert info.status == AdapterStatus.ERROR
        assert info.last_error == "Adapter not found"

    @pytest.mark.asyncio
    async def test_is_healthy_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test health check success."""
        mock_runtime_control_service.is_healthy.return_value = True
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.is_healthy("test_handler")

        assert result is True

    @pytest.mark.asyncio
    async def test_is_healthy_during_shutdown(self, runtime_control_bus, mock_runtime_control_service):
        """Test health check during shutdown."""
        mock_runtime_control_service.is_healthy.return_value = True
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)
        runtime_control_bus._shutting_down = True

        result = await runtime_control_bus.is_healthy("test_handler")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_capabilities_success(self, runtime_control_bus, mock_runtime_control_service):
        """Test capabilities retrieval."""
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        capabilities = await runtime_control_bus.get_capabilities("test_handler")

        assert "pause_processing" in capabilities
        assert "resume_processing" in capabilities
        assert "single_step" in capabilities
        assert "shutdown_runtime" in capabilities

    @pytest.mark.asyncio
    async def test_get_capabilities_no_service(self, runtime_control_bus):
        """Test capabilities when no service available."""
        runtime_control_bus.get_service = AsyncMock(return_value=None)

        capabilities = await runtime_control_bus.get_capabilities("test_handler")

        assert capabilities == []

    @pytest.mark.asyncio
    async def test_concurrent_operations_lock(self, runtime_control_bus, mock_runtime_control_service):
        """Test that operations are properly locked."""
        # Create a slow pause operation
        pause_event = asyncio.Event()

        async def slow_pause():
            await pause_event.wait()
            return ProcessorControlResponse(
                success=True, processor_name="test", operation="pause", new_status=ProcessorStatus.PAUSED, error=None
            )

        mock_runtime_control_service.pause_processing = slow_pause
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        # Start pause operation
        pause_task = asyncio.create_task(runtime_control_bus.pause_processing())

        # Give it time to acquire the lock
        await asyncio.sleep(0.01)

        # Try to resume - should wait for lock
        resume_started = False

        async def track_resume():
            nonlocal resume_started
            resume_started = True
            return ProcessorControlResponse(
                success=True, processor_name="test", operation="resume", new_status=ProcessorStatus.RUNNING, error=None
            )

        mock_runtime_control_service.resume_processing = AsyncMock(side_effect=track_resume)

        # Start resume operation (should wait for lock)
        resume_task = asyncio.create_task(runtime_control_bus.resume_processing())

        # Give it time to try acquiring the lock
        await asyncio.sleep(0.01)

        # Resume should not have started yet
        assert not resume_started

        # Complete the pause operation
        pause_event.set()
        await pause_task

        # Now resume should complete
        await resume_task
        assert resume_started

    def test_operation_priority_enum(self):
        """Test OperationPriority enum values."""
        assert OperationPriority.CRITICAL == "critical"
        assert OperationPriority.HIGH == "high"
        assert OperationPriority.NORMAL == "normal"
        assert OperationPriority.LOW == "low"

    @pytest.mark.asyncio
    async def test_error_handling_in_operations(self, runtime_control_bus, mock_runtime_control_service):
        """Test error handling in various operations."""
        # Test exception in pause_processing
        mock_runtime_control_service.pause_processing.side_effect = Exception("Pause error")
        runtime_control_bus.get_service = AsyncMock(return_value=mock_runtime_control_service)

        result = await runtime_control_bus.pause_processing()
        assert result is False

        # Test exception in get_runtime_status
        mock_runtime_control_service.get_runtime_status.side_effect = Exception("Status error")

        status = await runtime_control_bus.get_runtime_status()
        assert status["status"] == "error"
        assert "Status error" in status["message"]

        # Test exception in load_adapter
        mock_runtime_control_service.load_adapter.side_effect = Exception("Load error")

        adapter_info = await runtime_control_bus.load_adapter("discord", "test_adapter", {}, True)
        assert adapter_info.status == AdapterStatus.ERROR
        assert "Load error" in adapter_info.last_error


class TestOperationPriority:
    """Test OperationPriority enum."""

    def test_priority_values(self):
        """Test that priority values are correct."""
        assert OperationPriority.CRITICAL.value == "critical"
        assert OperationPriority.HIGH.value == "high"
        assert OperationPriority.NORMAL.value == "normal"
        assert OperationPriority.LOW.value == "low"

    def test_priority_comparison(self):
        """Test priority comparison (though not directly comparable as strings)."""
        # These are string enums, so direct comparison doesn't give priority ordering
        # But we can verify they are distinct
        priorities = [
            OperationPriority.CRITICAL,
            OperationPriority.HIGH,
            OperationPriority.NORMAL,
            OperationPriority.LOW,
        ]
        assert len(set(priorities)) == 4  # All unique


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
