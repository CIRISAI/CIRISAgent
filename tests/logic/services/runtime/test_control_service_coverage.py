"""
Comprehensive tests for RuntimeControlService to improve code coverage.

These tests align with CIRIS philosophy:
- All data uses proper schemas (ProcessorControlResponse, etc.)
- Tests verify actual behavior, not mocked expectations
- Focus on coverage of uncovered methods and edge cases
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.runtime.adapter_manager import AdapterInstance, RuntimeAdapterManager
from ciris_engine.logic.services.runtime.control_service import RuntimeControlService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, AdapterOperationResult, AdapterStatus
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.core.runtime import ProcessorControlResponse, ProcessorStatus


class TestRuntimeControlServiceCoverage:
    """Test suite for RuntimeControlService to improve coverage."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock(spec=TimeServiceProtocol)
        mock.now = Mock(return_value=datetime.now(timezone.utc))
        mock.uptime = Mock(return_value=100.0)
        return mock

    @pytest.fixture
    def mock_runtime(self):
        """Create a mock runtime interface."""
        mock = Mock()

        # Mock agent processor with proper methods
        mock.agent_processor = Mock()
        mock.agent_processor.queue_size = 5
        mock.agent_processor.is_paused = Mock(return_value=False)
        mock.agent_processor.pause_processing = AsyncMock(return_value=True)
        mock.agent_processor.resume_processing = AsyncMock(return_value=True)
        mock.agent_processor.single_step = AsyncMock(return_value={"success": True, "processing_time_ms": 50.0})
        mock.agent_processor.get_queue_status = Mock(return_value=Mock(pending_thoughts=5, pending_tasks=2))

        # Mock service registry
        mock.service_registry = Mock()
        mock.service_registry._circuit_breakers = {}
        mock.service_registry.reset_circuit_breakers = Mock()

        # Mock shutdown
        mock.request_shutdown = AsyncMock(return_value=None)

        return mock

    @pytest.fixture
    def mock_adapter_manager(self, mock_runtime, mock_time_service):
        """Create a mock adapter manager."""
        manager = Mock(spec=RuntimeAdapterManager)
        manager.load_adapter = AsyncMock(
            return_value=AdapterOperationResult(
                success=True,
                adapter_id="test_adapter",
                adapter_type="cli",
                message="Adapter loaded",
                error=None,
                details={},
            )
        )
        manager.unload_adapter = AsyncMock(
            return_value=AdapterOperationResult(
                success=True,
                adapter_id="test_adapter",
                adapter_type="cli",
                message="Adapter unloaded",
                error=None,
                details={},
            )
        )
        manager.list_adapters = AsyncMock(return_value=[])
        manager.loaded_adapters = {}
        return manager

    @pytest.fixture
    def control_service(self, mock_runtime, mock_adapter_manager, mock_time_service):
        """Create a RuntimeControlService instance with mocks."""
        service = RuntimeControlService(
            runtime=mock_runtime,
            adapter_manager=mock_adapter_manager,
            config_manager=None,
            time_service=mock_time_service,
        )
        return service

    @pytest.mark.asyncio
    async def test_single_step_success(self, control_service, mock_runtime):
        """Test single_step when processor succeeds."""
        # Processor must be paused for single_step to work
        mock_runtime.agent_processor.is_paused.return_value = True

        response = await control_service.single_step()

        assert response.success is True
        assert response.new_status == ProcessorStatus.RUNNING
        assert response.operation == "single_step"
        assert control_service._single_steps == 1
        mock_runtime.agent_processor.single_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_step_not_paused(self, control_service, mock_runtime):
        """Test single_step when processor is not paused."""
        # Processor is not paused
        mock_runtime.agent_processor.is_paused.return_value = False

        response = await control_service.single_step()

        assert response.success is False
        assert response.error == "Cannot single-step unless processor is paused"

    @pytest.mark.asyncio
    async def test_single_step_no_processor(self, control_service):
        """Test single_step when no processor is available."""
        control_service.runtime = None

        response = await control_service.single_step()

        assert response.success is False
        assert response.error == "Agent processor not available"

    @pytest.mark.asyncio
    async def test_pause_processing_success(self, control_service, mock_runtime):
        """Test pause_processing when successful."""
        response = await control_service.pause_processing()

        assert response.success is True
        assert response.new_status == ProcessorStatus.PAUSED
        assert control_service._processor_status == ProcessorStatus.PAUSED
        assert control_service._pause_resume_cycles == 1
        mock_runtime.agent_processor.pause_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_processing_already_paused(self, control_service, mock_runtime):
        """Test pause_processing when already paused."""
        mock_runtime.agent_processor.is_paused.return_value = True
        control_service._processor_status = ProcessorStatus.PAUSED

        response = await control_service.pause_processing()

        assert response.success is False
        assert "already paused" in response.error.lower()

    @pytest.mark.asyncio
    async def test_resume_processing_success(self, control_service, mock_runtime):
        """Test resume_processing when successful."""
        control_service._processor_status = ProcessorStatus.PAUSED
        mock_runtime.agent_processor.is_paused.return_value = True

        response = await control_service.resume_processing()

        assert response.success is True
        assert response.new_status == ProcessorStatus.RUNNING
        assert control_service._processor_status == ProcessorStatus.RUNNING
        mock_runtime.agent_processor.resume_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_processing_not_paused(self, control_service, mock_runtime):
        """Test resume_processing when not paused."""
        mock_runtime.agent_processor.is_paused.return_value = False
        control_service._processor_status = ProcessorStatus.RUNNING

        response = await control_service.resume_processing()

        assert response.success is False
        assert "not paused" in response.error.lower()

    @pytest.mark.asyncio
    async def test_get_processor_queue_status(self, control_service, mock_runtime):
        """Test get_processor_queue_status method."""
        control_service._thoughts_processed = 100
        control_service._thoughts_pending = 5
        control_service._average_thought_time_ms = 50.0

        status = await control_service.get_processor_queue_status()

        # Check the schema fields that actually exist
        assert status.processor_name == "agent"
        assert status.queue_size == 7  # 5 thoughts + 2 tasks from mock
        mock_runtime.agent_processor.get_queue_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_runtime(self, control_service, mock_runtime):
        """Test shutdown_runtime method."""
        response = await control_service.shutdown_runtime("Test shutdown")

        assert response.success is True
        assert response.new_status == ProcessorStatus.SHUTDOWN
        assert control_service._processor_status == ProcessorStatus.SHUTDOWN
        mock_runtime.request_shutdown.assert_called_once_with("Test shutdown")

    @pytest.mark.asyncio
    async def test_reset_circuit_breakers_all(self, control_service, mock_runtime):
        """Test resetting all circuit breakers."""
        mock_runtime.service_registry._circuit_breakers = {
            "provider1": Mock(),
            "provider2": Mock(),
            "provider3": Mock(),
        }

        response = await control_service.reset_circuit_breakers()

        assert response.success is True
        assert response.reset_count == 3
        mock_runtime.service_registry.reset_circuit_breakers.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_circuit_breakers_no_registry(self, control_service):
        """Test reset when registry not available."""
        control_service.runtime = None

        response = await control_service.reset_circuit_breakers()

        assert response.success is False
        assert "not available" in response.error.lower()

    @pytest.mark.asyncio
    async def test_get_service_selection_explanation(self, control_service):
        """Test get_service_selection_explanation method."""
        explanation = await control_service.get_service_selection_explanation()

        # Just verify it returns the right schema type
        assert explanation.overview is not None
        assert isinstance(explanation.priorities, dict)
        assert isinstance(explanation.selection_strategies, dict)

    @pytest.mark.asyncio
    async def test_load_adapter_success(self, control_service, mock_adapter_manager):
        """Test load_adapter when successful."""
        config = AdapterConfig(adapter_type="test", settings={})
        response = await control_service.load_adapter("test", "test_id", config)

        assert response.success is True
        assert response.adapter_id == "test_adapter"
        mock_adapter_manager.load_adapter.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_adapter_no_manager(self, control_service):
        """Test load_adapter when no adapter manager."""
        control_service.adapter_manager = None
        config = AdapterConfig(adapter_type="test", settings={})

        response = await control_service.load_adapter("test", "test_id", config)

        assert response.success is False
        assert "not available" in response.message.lower()

    @pytest.mark.asyncio
    async def test_unload_adapter_success(self, control_service, mock_adapter_manager):
        """Test unload_adapter when successful."""
        response = await control_service.unload_adapter("test_id")

        assert response.success is True
        mock_adapter_manager.unload_adapter.assert_called_once_with("test_id", force=False)

    @pytest.mark.asyncio
    async def test_list_adapters(self, control_service, mock_adapter_manager):
        """Test list_adapters method."""
        mock_adapter_manager.list_adapters.return_value = [
            AdapterStatus(
                adapter_id="test1",
                adapter_type="cli",
                is_running=True,
                loaded_at=datetime.now(timezone.utc),
                services_registered=[],
                config_params=AdapterConfig(adapter_type="cli"),
                metrics=None,
            )
        ]

        adapters = await control_service.list_adapters()

        assert len(adapters) == 1
        assert adapters[0].adapter_id == "test1"

    @pytest.mark.asyncio
    async def test_get_adapter_info(self, control_service, mock_adapter_manager):
        """Test get_adapter_info method."""
        # Setup mock adapter instance
        mock_instance = AdapterInstance(
            adapter_id="test_id",
            adapter_type="cli",
            adapter=Mock(),
            config_params=AdapterConfig(adapter_type="cli", settings={}),
            loaded_at=datetime.now(timezone.utc),
            is_running=True,
        )
        mock_adapter_manager.loaded_adapters = {"test_id": mock_instance}

        info = await control_service.get_adapter_info("test_id")

        assert info is not None
        assert info.adapter_id == "test_id"
        assert info.adapter_type == "cli"
        assert info.status == "running"

    @pytest.mark.asyncio
    async def test_get_adapter_info_not_found(self, control_service, mock_adapter_manager):
        """Test get_adapter_info when adapter not found."""
        mock_adapter_manager.loaded_adapters = {}

        info = await control_service.get_adapter_info("nonexistent")

        assert info is None

    @pytest.mark.asyncio
    async def test_get_service_type(self, control_service):
        """Test get_service_type method."""
        service_type = control_service.get_service_type()
        assert service_type == ServiceType.RUNTIME_CONTROL

    @pytest.mark.asyncio
    async def test_processor_control_with_errors(self, control_service, mock_runtime):
        """Test processor control operations with errors."""
        # Test pause returning false (failure)
        mock_runtime.agent_processor.pause_processing.return_value = False

        response = await control_service.pause_processing()
        assert response.success is False
        assert response.error == "Failed to pause processor"

        # Reset for resume test
        mock_runtime.agent_processor.pause_processing.return_value = True
        control_service._processor_status = ProcessorStatus.PAUSED
        mock_runtime.agent_processor.is_paused.return_value = True
        mock_runtime.agent_processor.resume_processing.return_value = False

        response = await control_service.resume_processing()
        assert response.success is False
        assert response.error == "Failed to resume processor"

    @pytest.mark.asyncio
    async def test_service_health_check(self, control_service):
        """Test service health checking."""
        # Service should be healthy initially
        assert await control_service.is_healthy() is True

        # Get status should return proper schema
        status = control_service.get_status()
        assert isinstance(status, ServiceStatus)
        assert status.is_healthy is True

    @pytest.mark.asyncio
    async def test_service_capabilities(self, control_service):
        """Test get_service_capabilities method."""
        capabilities = control_service.get_service_capabilities()

        assert isinstance(capabilities, ServiceCapabilities)
        # Capabilities are returned as a list of strings
        assert len(capabilities.capabilities) > 0
        assert all(isinstance(cap, str) for cap in capabilities.capabilities)

    @pytest.mark.asyncio
    async def test_runtime_control_metrics(self, control_service):
        """Test that metrics are properly tracked."""
        # Perform some operations
        await control_service.pause_processing()
        control_service._processor_status = ProcessorStatus.PAUSED
        control_service.runtime.agent_processor.is_paused.return_value = True
        await control_service.resume_processing()

        # Check metrics
        metrics = await control_service.get_metrics()

        assert isinstance(metrics, dict)
        assert metrics["pause_resume_cycles"] == 2  # One pause, one resume
        assert metrics["runtime_errors"] == 0  # No errors occurred
        assert "processor_status" in metrics
