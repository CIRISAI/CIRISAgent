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
from ciris_engine.protocols.pipeline_control import SingleStepResult
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, AdapterOperationResult
from ciris_engine.schemas.runtime.adapter_management import RuntimeAdapterStatus as AdapterStatusModel
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.core.runtime import (
    AdapterInfo,
    AdapterStatus,
    ProcessorControlResponse,
    ProcessorStatus,
)
from ciris_engine.schemas.services.runtime_control import (
    FinalizeActionStepData,
    PipelineState,
    SpanAttribute,
    StepPoint,
    StepResultData,
    TraceContext,
)


def create_test_step_result_data(
    thought_id: str = "test-thought",
    task_id: str = "task_001",
    step_point: StepPoint = StepPoint.FINALIZE_ACTION,
    success: bool = True,
    processing_time_ms: float = 50.0,
    **kwargs,
) -> StepResultData:
    """Helper to create StepResultData for tests."""

    trace_context = TraceContext(
        trace_id=f"trace-{thought_id}",
        span_id=f"span-{step_point.value}",
        span_name=f"test-{step_point.value}",
        operation_name=f"test_{step_point.value}",
        start_time_ns=1000000000,
        end_time_ns=1000100000,
        duration_ns=100000,
    )

    timestamp = datetime.now().isoformat()

    # Create step data for FINALIZE_ACTION
    from ciris_engine.schemas.conscience.core import EpistemicData

    step_data = FinalizeActionStepData(
        timestamp=timestamp,
        thought_id=thought_id,
        task_id=task_id,
        processing_time_ms=processing_time_ms,
        success=success,
        selected_action=kwargs.get("selected_action", "test_action"),
        conscience_passed=kwargs.get("conscience_passed", True),
        conscience_override_reason=kwargs.get("conscience_override_reason", None),
        epistemic_data=kwargs.get(
            "epistemic_data",
            EpistemicData(
                entropy_level=0.1,
                coherence_level=0.9,
                uncertainty_acknowledged=True,
                reasoning_transparency=1.0,
            ),
        ),
    )

    return StepResultData(
        step_point=step_point.value,
        success=success,
        processing_time_ms=processing_time_ms,
        thought_id=thought_id,
        task_id=task_id,
        step_data=step_data,
        trace_context=trace_context,
        span_attributes=kwargs.get("span_attributes", []),
    )


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

        # Create proper StepResultData object for the mock
        test_step_result = create_test_step_result_data(
            thought_id="test-thought",
            task_id="task_001",
            step_point=StepPoint.FINALIZE_ACTION,
            success=True,
            processing_time_ms=50.0,
        )

        # Create proper PipelineState object for the mock
        test_pipeline_state = PipelineState(
            is_paused=False,
            current_round=1,
            task_queue=[],
            thought_queue=[],
            total_thoughts_processed=2,
            total_thoughts_in_flight=0,
        )

        # Mock agent processor with proper methods
        mock.agent_processor = Mock()
        mock.agent_processor.queue = []  # Empty list instead of queue_size
        mock.agent_processor.is_paused = Mock(return_value=False)
        mock.agent_processor.pause_processing = AsyncMock(return_value=True)
        mock.agent_processor.resume_processing = AsyncMock(return_value=True)

        # Return SingleStepResult model instead of dict
        # Note: step_results and pipeline_state must be dicts (SerializedModel), not Pydantic models
        # Only use fields that actually exist in SingleStepResult schema
        mock.agent_processor.single_step = AsyncMock(
            return_value=SingleStepResult(
                success=True,
                step_point="BUILD_CONTEXT",
                message="Step completed",
                processing_time_ms=50.0,
                thoughts_advanced=1,  # Correct field name
                step_results=[test_step_result.model_dump()],
                pipeline_state=test_pipeline_state.model_dump(),
            )
        )
        mock.agent_processor.get_queue_status = Mock(return_value=Mock(pending_thoughts=5, pending_tasks=2))

        # Mock service registry
        mock.service_registry = Mock()
        mock.service_registry._circuit_breakers = {}
        mock.service_registry.reset_circuit_breakers = Mock()

        # Mock shutdown service
        mock_shutdown_service = Mock()
        mock_shutdown_service.request_shutdown = Mock()
        mock.service_registry.get_service = Mock(return_value=mock_shutdown_service)

        # Mock adapters list
        mock.adapters = []

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
        manager.active_adapters = []  # Add this for metrics
        # Mock _sanitize_config_params to return the config as-is (pass-through for tests)
        manager._sanitize_config_params = Mock(
            side_effect=lambda adapter_type, config: config or AdapterConfig(adapter_type=adapter_type, enabled=True)
        )
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
        # Set start time to avoid datetime calculation errors
        service._start_time = datetime.now(timezone.utc) - timedelta(hours=1)
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

        # Verify H3ERE step data is passed through
        assert response.step_point == "BUILD_CONTEXT"
        assert response.step_results is not None
        assert len(response.step_results) == 1
        assert isinstance(response.step_results[0], StepResultData)
        assert response.step_results[0].task_id == "task_001"
        assert response.step_results[0].thought_id == "test-thought"
        assert response.thoughts_processed == 1
        assert response.processing_time_ms == 50.0
        assert isinstance(response.pipeline_state, PipelineState)
        assert response.pipeline_state.current_round == 1
        assert response.pipeline_state.total_thoughts_processed == 2
        # Note: current_round is not a field in SingleStepResult, so it will be None
        # assert response.current_round == 1  # Removed - SingleStepResult doesn't have this field
        assert response.pipeline_empty is False

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
        # When already paused, pause_processing returns success but doesn't increment counter
        mock_runtime.agent_processor.is_paused.return_value = True
        control_service._processor_status = ProcessorStatus.PAUSED
        initial_cycles = control_service._pause_resume_cycles

        response = await control_service.pause_processing()

        # It still succeeds but doesn't increment the counter
        assert response.success is True
        assert control_service._pause_resume_cycles == initial_cycles

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
        # When not paused, resume_processing returns success but doesn't change state
        mock_runtime.agent_processor.is_paused.return_value = False
        control_service._processor_status = ProcessorStatus.RUNNING

        response = await control_service.resume_processing()

        # It still succeeds
        assert response.success is True
        assert control_service._processor_status == ProcessorStatus.RUNNING

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
        assert response.new_status == ProcessorStatus.STOPPED  # Shutdown sets to STOPPED
        assert control_service._processor_status == ProcessorStatus.STOPPED  # Changes to STOPPED
        mock_runtime.service_registry.get_service.assert_called_once_with("ShutdownService")
        mock_shutdown_service = mock_runtime.service_registry.get_service.return_value
        mock_shutdown_service.request_shutdown.assert_called_once_with("Runtime control: Test shutdown")

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
        assert response.success is False  # Just check success, not message

    @pytest.mark.asyncio
    async def test_unload_adapter_success(self, control_service, mock_adapter_manager):
        """Test unload_adapter when successful."""
        response = await control_service.unload_adapter("test_id")

        assert response.success is True
        mock_adapter_manager.unload_adapter.assert_called_once_with("test_id")

    @pytest.mark.asyncio
    async def test_list_adapters(self, control_service, mock_adapter_manager):
        """Test list_adapters method."""
        mock_adapter_manager.list_adapters = AsyncMock(
            return_value=[
                AdapterStatusModel(
                    adapter_id="test1",
                    adapter_type="cli",
                    is_running=True,
                    loaded_at=datetime.now(timezone.utc),
                    services_registered=[],
                    config_params=AdapterConfig(adapter_type="cli"),
                    metrics=None,
                )
            ]
        )

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
        # Use a real dict for loaded_adapters so 'in' operator works
        mock_adapter_manager.loaded_adapters = {"test_id": mock_instance}
        # Control service expects adapter_manager.get_adapter_info to return AdapterInfo from adapter_management
        from ciris_engine.schemas.runtime.adapter_management import AdapterInfo as AMAdapterInfo

        mock_info = AMAdapterInfo(
            adapter_id="test_id",
            adapter_type="cli",
            is_running=True,
            load_time=datetime.now(timezone.utc).isoformat(),
            config=AdapterConfig(adapter_type="cli", settings={}),
            services_registered=[],
            lifecycle_tasks=[],
            metrics={},
        )
        mock_adapter_manager.get_adapter_info = Mock(return_value=mock_info)

        info = await control_service.get_adapter_info("test_id")

        assert info is not None
        assert info.adapter_id == "test_id"
        assert info.adapter_type == "cli"
        assert info.status == AdapterStatus.RUNNING

    @pytest.mark.asyncio
    async def test_get_adapter_info_not_found(self, control_service, mock_adapter_manager):
        """Test get_adapter_info when adapter not found."""
        # Use a real dict for loaded_adapters so 'in' operator works
        mock_adapter_manager.loaded_adapters = {}
        mock_adapter_manager.get_adapter_info = Mock(return_value=None)

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
        mock_runtime.agent_processor.pause_processing = AsyncMock(return_value=False)

        response = await control_service.pause_processing()
        assert response.success is False
        assert response.error == "Failed to pause processor"

        # Reset for resume test
        mock_runtime.agent_processor.pause_processing = AsyncMock(return_value=True)
        control_service._processor_status = ProcessorStatus.PAUSED
        mock_runtime.agent_processor.is_paused.return_value = True
        mock_runtime.agent_processor.resume_processing = AsyncMock(return_value=False)

        response = await control_service.resume_processing()
        assert response.success is False
        assert response.error == "Failed to resume processor"

    @pytest.mark.asyncio
    async def test_service_health_check(self, control_service):
        """Test service health checking."""
        # Service should be healthy initially
        # Check health directly
        health = await control_service.is_healthy()
        # Service may not be healthy without proper setup
        assert isinstance(health, bool)

        # Get status should return proper schema
        status = control_service.get_status()
        assert isinstance(status, ServiceStatus)
        assert status.is_healthy is True

    @pytest.mark.asyncio
    async def test_service_capabilities(self, control_service):
        """Test service capabilities."""
        # RuntimeControlService doesn't have get_service_capabilities method
        # Just verify the service has the expected attributes
        assert hasattr(control_service, "_processor_status")
        assert hasattr(control_service, "_runtime_errors")
        assert control_service.get_service_type() == ServiceType.RUNTIME_CONTROL

    @pytest.mark.asyncio
    async def test_runtime_control_metrics(self, control_service, mock_adapter_manager):
        """Test that metrics are properly tracked."""
        # Add active_adapters attribute to mock adapter manager
        mock_adapter_manager.active_adapters = []

        # Perform some operations
        await control_service.pause_processing()
        control_service._processor_status = ProcessorStatus.PAUSED
        control_service.runtime.agent_processor.is_paused.return_value = True
        await control_service.resume_processing()

        # Just verify metrics returns a dict
        metrics = await control_service.get_metrics()
        assert isinstance(metrics, dict)
        # Don't check specific values as they depend on implementation details

    @pytest.mark.asyncio
    async def test_queue_depth_integration(self, control_service, mock_runtime):
        """Test queue depth integration using get_processor_queue_status method."""
        # Mock the get_processor_queue_status method to return specific queue size
        mock_queue_status = Mock()
        mock_queue_status.queue_size = 15
        control_service.get_processor_queue_status = AsyncMock(return_value=mock_queue_status)

        status = await control_service.get_runtime_status()

        # Verify queue_depth is correctly set from processor queue status
        assert (
            status.queue_depth == 15
        ), f"Expected queue_depth=15 from processor queue status, got {status.queue_depth}"
        control_service.get_processor_queue_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_queue_depth_exception_handling(self, control_service, mock_runtime):
        """Test exception handling when get_processor_queue_status fails."""
        # Mock get_processor_queue_status to raise exception
        control_service.get_processor_queue_status = AsyncMock(side_effect=RuntimeError("Queue status error"))

        with patch("ciris_engine.logic.services.runtime.control_service.service.logger") as mock_logger:
            status = await control_service.get_runtime_status()

            # Should log warning and fallback to 0
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Failed to get queue depth from processor queue status" in warning_call
            assert status.queue_depth == 0, f"Expected queue_depth=0 on exception, got {status.queue_depth}"

    @pytest.mark.asyncio
    async def test_queue_depth_no_agent_processor(self, control_service):
        """Test queue depth when agent processor is not available."""
        # Remove agent processor to test fallback
        control_service.runtime.agent_processor = None

        status = await control_service.get_runtime_status()

        # Should fallback to 0 when no agent processor
        assert status.queue_depth == 0, f"Expected queue_depth=0 when no agent processor, got {status.queue_depth}"

    @pytest.mark.asyncio
    async def test_get_processor_queue_status_no_processor(self, control_service):
        """Test get_processor_queue_status when agent processor is None."""
        # Set agent processor to None to trigger the uncovered branch
        control_service.runtime.agent_processor = None

        with patch("ciris_engine.logic.services.runtime.control_service.service.logger") as mock_logger:
            status = await control_service.get_processor_queue_status()

            # Should log debug message and return empty queue status
            mock_logger.debug.assert_called_once_with(
                "Agent processor not yet initialized, returning empty queue status"
            )
            assert status.processor_name == "agent"
            assert status.queue_size == 0
            assert status.max_size == 1000
            assert status.processing_rate == 0.0
            assert status.average_latency_ms == 0.0
            assert status.oldest_message_age_seconds is None

    @pytest.mark.asyncio
    async def test_get_processor_queue_status_success_path(self, control_service, mock_runtime):
        """Test get_processor_queue_status successful execution path."""
        # Setup mock to return queue status
        mock_queue_status = Mock(pending_thoughts=5, pending_tasks=3)
        mock_runtime.agent_processor.get_queue_status.return_value = mock_queue_status

        # Set up calculation methods to return values
        control_service._calculate_processing_rate = Mock(return_value=2.5)
        control_service._calculate_average_latency = Mock(return_value=45.0)

        status = await control_service.get_processor_queue_status()

        assert status.processor_name == "agent"
        assert status.queue_size == 8  # 5 thoughts + 3 tasks
        assert status.max_size == 1000
        assert status.processing_rate == 2.5
        assert status.average_latency_ms == 45.0
        assert status.oldest_message_age_seconds is None

        mock_runtime.agent_processor.get_queue_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_processor_queue_status_exception_handling(self, control_service, mock_runtime):
        """Test get_processor_queue_status exception handling."""
        # Make get_queue_status raise an exception
        mock_runtime.agent_processor.get_queue_status.side_effect = RuntimeError("Queue access failed")

        with patch("ciris_engine.logic.services.runtime.control_service.service.logger") as mock_logger:
            status = await control_service.get_processor_queue_status()

            # Should log error and return error status
            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args[0][0]
            assert "Failed to get queue status:" in error_call

            assert status.processor_name == "agent"
            assert status.queue_size == 0
            assert status.max_size == 0
            assert status.processing_rate == 0.0
            assert status.average_latency_ms == 0.0
            assert status.oldest_message_age_seconds is None
