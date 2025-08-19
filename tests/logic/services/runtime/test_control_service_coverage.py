"""
Comprehensive tests for RuntimeControlService to improve code coverage.

Tests focus on uncovered methods and edge cases.
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
from ciris_engine.schemas.services.core.runtime import (
    AdapterInfo,
    AdapterOperationResponse,
    ConfigBackup,
    ConfigOperationResponse,
    ConfigReloadResult,
    ConfigScope,
    ConfigSnapshot,
    ConfigValidationLevel,
    ConfigValidationResponse,
    ProcessorControlResponse,
    ProcessorQueueStatus,
    ProcessorStatus,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeStatusResponse,
    ServiceHealthStatus,
    ServiceSelectionExplanation,
)
from ciris_engine.schemas.services.runtime_control import (
    CircuitBreakerResetResponse,
    CircuitBreakerState,
    CircuitBreakerStatus,
    ConfigBackupData,
    ConfigValueMap,
    ServicePriorityUpdateResponse,
    ServiceProviderInfo,
    ServiceRegistryInfoResponse,
    WAPublicKeyMap,
)
from ciris_engine.schemas.services.shutdown import EmergencyShutdownStatus, KillSwitchConfig, WASignedCommand


class TestRuntimeControlServiceCoverage:
    """Test suite for RuntimeControlService to improve coverage."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock(spec=TimeServiceProtocol)
        mock.now.return_value = datetime.now(timezone.utc)
        mock.uptime = Mock(return_value=100.0)
        return mock

    @pytest.fixture
    def mock_runtime(self):
        """Create a mock runtime interface."""
        mock = Mock()
        mock.agent_processor = Mock()
        mock.agent_processor.queue_size = 5
        mock.agent_processor.is_paused = False
        mock.agent_processor.pause = AsyncMock()
        mock.agent_processor.resume = AsyncMock()
        mock.agent_processor.single_step = AsyncMock(return_value=True)
        mock.agent_processor.get_metrics = AsyncMock(
            return_value={"thoughts_processed": 100, "thoughts_pending": 5, "average_thought_time_ms": 50.0}
        )

        mock.service_registry = Mock()
        mock.service_registry.get_all_services = Mock(return_value={})
        mock.service_registry.update_priority = Mock(return_value=True)
        mock.service_registry.get_service_priorities = Mock(return_value={})
        mock.service_registry.reset_circuit_breaker = Mock()
        mock.service_registry.get_circuit_breaker_states = Mock(return_value={})
        mock.service_registry.get_selection_strategy = Mock(return_value="priority")

        mock.request_shutdown = AsyncMock()
        mock.get_runtime_status = AsyncMock(
            return_value={"status": "running", "cognitive_state": "work", "uptime": 100.0}
        )

        return mock

    @pytest.fixture
    def mock_adapter_manager(self, mock_runtime, mock_time_service):
        """Create a mock adapter manager."""
        manager = RuntimeAdapterManager(mock_runtime, mock_time_service)
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
        return manager

    @pytest.fixture
    def mock_config_manager(self):
        """Create a mock config manager."""
        mock = Mock()
        mock.get_config = AsyncMock(return_value={"test": "value"})
        mock.update_config = AsyncMock(return_value=True)
        mock.validate_config = AsyncMock(return_value=(True, []))
        mock.backup_config = AsyncMock(return_value="backup_20240101_120000")
        mock.restore_config = AsyncMock(return_value=True)
        mock.list_backups = AsyncMock(return_value=[])
        mock.reload_config = AsyncMock(return_value=True)
        return mock

    @pytest.fixture
    def control_service(self, mock_runtime, mock_adapter_manager, mock_config_manager, mock_time_service):
        """Create a RuntimeControlService instance with mocks."""
        service = RuntimeControlService(
            runtime=mock_runtime,
            adapter_manager=mock_adapter_manager,
            config_manager=mock_config_manager,
            time_service=mock_time_service,
        )
        return service

    @pytest.mark.asyncio
    async def test_initialize(self, control_service):
        """Test the _initialize method."""
        await control_service._initialize()
        assert control_service._service_status == ServiceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_single_step_success(self, control_service, mock_runtime):
        """Test single_step when processor succeeds."""
        response = await control_service.single_step()

        assert response.success is True
        assert response.processor_state == ProcessorStatus.RUNNING
        assert "completed" in response.message.lower()
        assert control_service._single_steps == 1
        mock_runtime.agent_processor.single_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_step_no_processor(self, control_service):
        """Test single_step when no processor is available."""
        control_service.runtime = None
        response = await control_service.single_step()

        assert response.success is False
        assert "not available" in response.message.lower()

    @pytest.mark.asyncio
    async def test_single_step_processor_error(self, control_service, mock_runtime):
        """Test single_step when processor raises an error."""
        mock_runtime.agent_processor.single_step.side_effect = Exception("Processing error")

        response = await control_service.single_step()

        assert response.success is False
        assert "error" in response.message.lower()
        assert control_service._runtime_errors == 1

    @pytest.mark.asyncio
    async def test_pause_processing_success(self, control_service, mock_runtime):
        """Test pause_processing when successful."""
        response = await control_service.pause_processing()

        assert response.success is True
        assert response.processor_state == ProcessorStatus.PAUSED
        assert control_service._processor_status == ProcessorStatus.PAUSED
        assert control_service._pause_resume_cycles == 1
        mock_runtime.agent_processor.pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_processing_already_paused(self, control_service, mock_runtime):
        """Test pause_processing when already paused."""
        mock_runtime.agent_processor.is_paused = True
        control_service._processor_status = ProcessorStatus.PAUSED

        response = await control_service.pause_processing()

        assert response.success is False
        assert "already paused" in response.message.lower()

    @pytest.mark.asyncio
    async def test_resume_processing_success(self, control_service, mock_runtime):
        """Test resume_processing when successful."""
        control_service._processor_status = ProcessorStatus.PAUSED
        mock_runtime.agent_processor.is_paused = True

        response = await control_service.resume_processing()

        assert response.success is True
        assert response.processor_state == ProcessorStatus.RUNNING
        assert control_service._processor_status == ProcessorStatus.RUNNING
        mock_runtime.agent_processor.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_processor_queue_status(self, control_service, mock_runtime):
        """Test get_processor_queue_status method."""
        control_service._thoughts_processed = 100
        control_service._thoughts_pending = 5
        control_service._average_thought_time_ms = 50.0
        control_service._thought_times = [45.0, 50.0, 55.0]

        status = await control_service.get_processor_queue_status()

        assert status.queue_depth == 5
        assert status.thoughts_processed == 100
        assert status.thoughts_pending == 5
        assert status.average_thought_time_ms == 50.0
        assert status.processing_rate > 0

    @pytest.mark.asyncio
    async def test_shutdown_runtime(self, control_service, mock_runtime):
        """Test shutdown_runtime method."""
        response = await control_service.shutdown_runtime("Test shutdown")

        assert response.success is True
        assert response.processor_state == ProcessorStatus.SHUTDOWN
        assert control_service._processor_status == ProcessorStatus.SHUTDOWN
        mock_runtime.request_shutdown.assert_called_once_with("Test shutdown")

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
        response = await control_service.unload_adapter("test_id", force=True)

        assert response.success is True
        mock_adapter_manager.unload_adapter.assert_called_once_with("test_id", force=True)

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
    async def test_get_config(self, control_service, mock_config_manager):
        """Test get_config method."""
        snapshot = await control_service.get_config("/test/path", include_sensitive=True)

        assert snapshot.config == {"test": "value"}
        assert snapshot.scope == ConfigScope.ALL
        mock_config_manager.get_config.assert_called_once_with("/test/path", include_sensitive=True)

    @pytest.mark.asyncio
    async def test_update_config(self, control_service, mock_config_manager):
        """Test update_config method."""
        updates = {"key": "value"}
        response = await control_service.update_config(updates, scope=ConfigScope.RUNTIME)

        assert response.success is True
        mock_config_manager.update_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_config(self, control_service, mock_config_manager):
        """Test validate_config method."""
        config = {"key": "value"}
        response = await control_service.validate_config(config, level=ConfigValidationLevel.STRICT)

        assert response.valid is True
        assert response.issues == []
        mock_config_manager.validate_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_backup_config(self, control_service, mock_config_manager):
        """Test backup_config method."""
        response = await control_service.backup_config("test_backup")

        assert response.success is True
        assert response.backup_name == "backup_20240101_120000"
        mock_config_manager.backup_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_restore_config(self, control_service, mock_config_manager):
        """Test restore_config method."""
        response = await control_service.restore_config("test_backup")

        assert response.success is True
        mock_config_manager.restore_config.assert_called_once_with("test_backup")

    @pytest.mark.asyncio
    async def test_list_config_backups(self, control_service, mock_config_manager):
        """Test list_config_backups method."""
        mock_config_manager.list_backups.return_value = [{"name": "backup1", "created_at": datetime.now(timezone.utc)}]

        backups = await control_service.list_config_backups()

        assert len(backups) == 1
        assert backups[0].backup_name == "backup1"

    @pytest.mark.asyncio
    async def test_get_runtime_status(self, control_service, mock_runtime):
        """Test get_runtime_status method."""
        control_service._processor_status = ProcessorStatus.RUNNING
        control_service._thoughts_processed = 100

        status = await control_service.get_runtime_status()

        assert status.processor_status == ProcessorStatus.RUNNING
        assert status.thoughts_processed == 100
        assert status.cognitive_state == "work"

    @pytest.mark.asyncio
    async def test_get_runtime_snapshot(self, control_service, mock_runtime):
        """Test get_runtime_snapshot method."""
        control_service._events_history = [
            RuntimeEvent(timestamp=datetime.now(timezone.utc), event_type="startup", details={"message": "Started"})
        ]

        snapshot = await control_service.get_runtime_snapshot()

        assert snapshot.processor_status == ProcessorStatus.RUNNING
        assert len(snapshot.recent_events) == 1
        assert snapshot.recent_events[0].event_type == "startup"

    @pytest.mark.asyncio
    async def test_update_service_priority(self, control_service, mock_runtime):
        """Test update_service_priority method."""
        response = await control_service.update_service_priority(ServiceType.LLM, 80, "round_robin")

        assert response.success is True
        assert response.service_type == ServiceType.LLM
        assert response.new_priority == 80
        mock_runtime.service_registry.update_priority.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_circuit_breakers(self, control_service, mock_runtime):
        """Test reset_circuit_breakers method."""
        mock_runtime.service_registry.get_circuit_breaker_states.return_value = {
            ServiceType.LLM: {"state": "open", "failures": 0}
        }

        response = await control_service.reset_circuit_breakers(ServiceType.LLM.value)

        assert response.success is True
        assert response.services_reset == 1
        mock_runtime.service_registry.reset_circuit_breaker.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_circuit_breaker_status(self, control_service, mock_runtime):
        """Test get_circuit_breaker_status method."""
        mock_runtime.service_registry.get_circuit_breaker_states.return_value = {
            ServiceType.LLM: {"state": "closed", "failures": 0, "last_failure": None, "success_count": 10}
        }

        status = await control_service.get_circuit_breaker_status()

        assert ServiceType.LLM.value in status
        assert status[ServiceType.LLM.value].state == CircuitBreakerState.CLOSED
        assert status[ServiceType.LLM.value].failure_count == 0

    @pytest.mark.asyncio
    async def test_get_service_selection_explanation(self, control_service, mock_runtime):
        """Test get_service_selection_explanation method."""
        mock_runtime.service_registry.get_selection_strategy.return_value = "priority"
        mock_runtime.service_registry.get_service_priorities.return_value = {ServiceType.LLM: 100}

        explanation = await control_service.get_service_selection_explanation()

        assert explanation.current_strategy == "priority"
        assert ServiceType.LLM.value in explanation.service_priorities

    @pytest.mark.asyncio
    async def test_get_service_health_status(self, control_service, mock_runtime):
        """Test get_service_health_status method."""
        mock_runtime.service_registry.get_all_services.return_value = {
            ServiceType.LLM: [Mock(healthy=True, __class__=Mock(__name__="TestService"))]
        }

        health = await control_service.get_service_health_status()

        assert health.healthy_services == 1
        assert health.total_services == 1
        assert health.overall_health == "healthy"

    @pytest.mark.asyncio
    async def test_get_metrics(self, control_service):
        """Test get_metrics method."""
        control_service._thoughts_processed = 100
        control_service._thoughts_pending = 5
        control_service._average_thought_time_ms = 50.0
        control_service._runtime_errors = 2
        control_service._single_steps = 10

        metrics = await control_service.get_metrics()

        assert metrics["thoughts_processed"] == 100
        assert metrics["thoughts_pending"] == 5
        assert metrics["average_thought_time_ms"] == 50.0
        assert metrics["runtime_errors"] == 2
        assert metrics["single_steps"] == 10

    @pytest.mark.asyncio
    async def test_handle_emergency_shutdown(self, control_service, mock_runtime):
        """Test handle_emergency_shutdown method."""
        command = WASignedCommand(
            command="shutdown",
            reason="Emergency",
            signature="test_signature",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Mock the shutdown service
        mock_shutdown_service = Mock()
        mock_shutdown_service.handle_emergency_shutdown = AsyncMock(
            return_value=EmergencyShutdownStatus(
                shutdown_initiated=True,
                verification_passed=True,
                reason="Emergency",
                timestamp=datetime.now(timezone.utc),
            )
        )
        mock_runtime.shutdown_service = mock_shutdown_service

        status = await control_service.handle_emergency_shutdown(command)

        assert status.shutdown_initiated is True
        assert status.verification_passed is True
        mock_shutdown_service.handle_emergency_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_record_event(self, control_service):
        """Test _record_event method."""
        await control_service._record_event("test_event", {"detail": "test"})

        assert len(control_service._events_history) == 1
        assert control_service._events_history[0].event_type == "test_event"
        assert control_service._events_history[0].details == {"detail": "test"}

    @pytest.mark.asyncio
    async def test_reload_config(self, control_service, mock_config_manager):
        """Test _reload_config method."""
        result = await control_service._reload_config("/test/path")

        assert result.success is True
        assert result.config_version is not None
        mock_config_manager.reload_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_start(self, control_service):
        """Test _on_start method."""
        await control_service._on_start()
        assert control_service._service_status == ServiceStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_on_stop(self, control_service):
        """Test _on_stop method."""
        await control_service._on_stop()
        assert control_service._service_status == ServiceStatus.STOPPED

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
    async def test_error_handling_in_pause(self, control_service, mock_runtime):
        """Test error handling in pause_processing."""
        mock_runtime.agent_processor.pause.side_effect = Exception("Pause failed")

        response = await control_service.pause_processing()

        assert response.success is False
        assert "error" in response.message.lower()
        assert control_service._runtime_errors == 1

    @pytest.mark.asyncio
    async def test_error_handling_in_resume(self, control_service, mock_runtime):
        """Test error handling in resume_processing."""
        control_service._processor_status = ProcessorStatus.PAUSED
        mock_runtime.agent_processor.is_paused = True
        mock_runtime.agent_processor.resume.side_effect = Exception("Resume failed")

        response = await control_service.resume_processing()

        assert response.success is False
        assert "error" in response.message.lower()
        assert control_service._runtime_errors == 1

    @pytest.mark.asyncio
    async def test_service_capabilities(self, control_service):
        """Test get_service_capabilities method."""
        capabilities = control_service.get_service_capabilities()

        assert isinstance(capabilities, ServiceCapabilities)
        assert "processor_control" in capabilities.capabilities
        assert "adapter_management" in capabilities.capabilities
        assert "config_management" in capabilities.capabilities

    @pytest.mark.asyncio
    async def test_get_service_type(self, control_service):
        """Test get_service_type method."""
        service_type = control_service.get_service_type()
        assert service_type == ServiceType.RUNTIME_CONTROL

    @pytest.mark.asyncio
    async def test_processor_status_tracking(self, control_service, mock_runtime):
        """Test that processor status is tracked correctly."""
        # Initial state
        assert control_service._processor_status == ProcessorStatus.RUNNING

        # Pause
        await control_service.pause_processing()
        assert control_service._processor_status == ProcessorStatus.PAUSED

        # Resume
        control_service._processor_status = ProcessorStatus.PAUSED
        mock_runtime.agent_processor.is_paused = True
        await control_service.resume_processing()
        assert control_service._processor_status == ProcessorStatus.RUNNING

        # Shutdown
        await control_service.shutdown_runtime("test")
        assert control_service._processor_status == ProcessorStatus.SHUTDOWN

    @pytest.mark.asyncio
    async def test_adapter_operations_with_error_handling(self, control_service, mock_adapter_manager):
        """Test adapter operations with error conditions."""
        # Test load failure
        mock_adapter_manager.load_adapter.return_value = AdapterOperationResult(
            success=False,
            adapter_id="failed",
            adapter_type="cli",
            message="Load failed",
            error="Test error",
            details={},
        )

        config = AdapterConfig(adapter_type="cli", settings={})
        response = await control_service.load_adapter("cli", "failed", config)
        assert response.success is False
        assert "failed" in response.message.lower()

        # Test unload failure
        mock_adapter_manager.unload_adapter.return_value = AdapterOperationResult(
            success=False,
            adapter_id="failed",
            adapter_type="cli",
            message="Unload failed",
            error="Test error",
            details={},
        )

        response = await control_service.unload_adapter("failed")
        assert response.success is False

    @pytest.mark.asyncio
    async def test_config_operations_with_errors(self, control_service, mock_config_manager):
        """Test config operations with error conditions."""
        # Test validation failure
        mock_config_manager.validate_config.return_value = (False, ["Invalid config"])

        response = await control_service.validate_config({"bad": "config"})
        assert response.valid is False
        assert len(response.issues) > 0

        # Test backup failure
        mock_config_manager.backup_config.side_effect = Exception("Backup failed")

        response = await control_service.backup_config("test")
        assert response.success is False

        # Test restore failure
        mock_config_manager.restore_config.return_value = False

        response = await control_service.restore_config("test")
        assert response.success is False

    @pytest.mark.asyncio
    async def test_event_history_limit(self, control_service):
        """Test that event history is limited."""
        # Add many events
        for i in range(150):
            await control_service._record_event(f"event_{i}", {"index": i})

        # Should be limited to 100 most recent
        assert len(control_service._events_history) == 100
        # First event should be event_50
        assert control_service._events_history[0].event_type == "event_50"
        # Last event should be event_149
        assert control_service._events_history[-1].event_type == "event_149"

    @pytest.mark.asyncio
    async def test_processing_metrics_update(self, control_service, mock_runtime):
        """Test that processing metrics are updated correctly."""
        # Set up mock return values
        mock_runtime.agent_processor.get_metrics.return_value = {
            "thoughts_processed": 200,
            "thoughts_pending": 10,
            "average_thought_time_ms": 75.0,
        }

        # Trigger metric update (this would normally happen in background)
        control_service._thoughts_processed = 200
        control_service._thoughts_pending = 10
        control_service._average_thought_time_ms = 75.0

        metrics = await control_service.get_metrics()

        assert metrics["thoughts_processed"] == 200
        assert metrics["thoughts_pending"] == 10
        assert metrics["average_thought_time_ms"] == 75.0

    @pytest.mark.asyncio
    async def test_runtime_not_available_scenarios(self, control_service):
        """Test scenarios where runtime is not available."""
        control_service.runtime = None

        # Test processor operations
        response = await control_service.pause_processing()
        assert response.success is False

        response = await control_service.resume_processing()
        assert response.success is False

        response = await control_service.single_step()
        assert response.success is False

        # Test status operations
        status = await control_service.get_runtime_status()
        assert status.processor_status == ProcessorStatus.UNKNOWN

        health = await control_service.get_service_health_status()
        assert health.overall_health == "critical"
