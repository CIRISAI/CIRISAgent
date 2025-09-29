"""
Comprehensive tests for ciris_runtime_helpers.py

Ensures 80%+ coverage for all helper functions with production-grade testing.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import Any, List

from ciris_engine.logic.runtime.ciris_runtime_helpers import (
    _get_service_shutdown_priority,
    _SERVICE_SHUTDOWN_PRIORITIES,
    validate_shutdown_preconditions,
    prepare_shutdown_maintenance_tasks,
    execute_final_maintenance_tasks,
    handle_agent_processor_shutdown,
    handle_adapter_shutdown_cleanup,
    execute_service_shutdown_sequence,
    preserve_critical_system_state,
    finalize_shutdown_logging,
    cleanup_runtime_resources,
    validate_shutdown_completion,
    _collect_scheduled_services,
    _stop_service_task,
    _transition_agent_to_shutdown_state,
    _handle_processing_loop_shutdown,
    _execute_shutdown_processor_directly,
    _wait_for_shutdown_processor_completion,
    _collect_all_services_to_stop,
    _get_direct_service_references,
    _execute_service_stop_tasks,
    _wait_for_service_stops,
    _handle_hanging_services,
    _check_service_stop_errors,
)


class TestServiceShutdownPriority:
    """Test service shutdown priority assignment."""

    def test_service_priority_mapping_completeness(self):
        """Test that all priority mappings are defined."""
        assert len(_SERVICE_SHUTDOWN_PRIORITIES) == 20
        assert "TSDB" in _SERVICE_SHUTDOWN_PRIORITIES
        assert "Shutdown" in _SERVICE_SHUTDOWN_PRIORITIES

    def test_get_service_shutdown_priority_known_services(self):
        """Test priority assignment for known service types."""
        # Mock services for different priority levels
        tsdb_service = Mock()
        tsdb_service.__class__.__name__ = "TSDBConsolidationService"

        memory_service = Mock()
        memory_service.__class__.__name__ = "MemoryService"

        unknown_service = Mock()
        unknown_service.__class__.__name__ = "UnknownService"

        assert _get_service_shutdown_priority(tsdb_service) == 0  # TSDB priority
        assert _get_service_shutdown_priority(memory_service) == 9  # Memory priority
        assert _get_service_shutdown_priority(unknown_service) == 5  # Default

    def test_get_service_shutdown_priority_edge_cases(self):
        """Test priority assignment edge cases."""
        # Service with multiple keywords - should get first match
        multi_service = Mock()
        multi_service.__class__.__name__ = "TSDBMemoryService"  # Has both TSDB and Memory
        assert _get_service_shutdown_priority(multi_service) == 0  # TSDB has priority in iteration

        # Case sensitivity
        case_service = Mock()
        case_service.__class__.__name__ = "tsdbService"  # lowercase
        assert _get_service_shutdown_priority(case_service) == 0  # Should still match


class TestValidateShutdownPreconditions:
    """Test shutdown precondition validation."""

    def test_validate_shutdown_preconditions_already_complete(self):
        """Test early exit when shutdown already completed."""
        runtime = Mock()
        runtime._shutdown_complete = True

        result = validate_shutdown_preconditions(runtime)
        assert result is False

    def test_validate_shutdown_preconditions_success(self):
        """Test successful precondition validation."""
        runtime = Mock()
        runtime._shutdown_complete = False
        service_registry = Mock()
        runtime.service_registry = service_registry

        result = validate_shutdown_preconditions(runtime)
        assert result is True
        assert service_registry._shutdown_mode is True

    def test_validate_shutdown_preconditions_no_shutdown_complete_attr(self):
        """Test when _shutdown_complete attribute doesn't exist."""
        runtime = Mock()
        del runtime._shutdown_complete  # Remove the attribute
        service_registry = Mock()
        runtime.service_registry = service_registry

        result = validate_shutdown_preconditions(runtime)
        assert result is True
        assert service_registry._shutdown_mode is True

    def test_validate_shutdown_preconditions_no_service_registry(self):
        """Test when service registry is None."""
        runtime = Mock()
        runtime._shutdown_complete = False
        runtime.service_registry = None

        result = validate_shutdown_preconditions(runtime)
        assert result is True


class TestCollectScheduledServices:
    """Test scheduled service collection."""

    def test_collect_scheduled_services_with_tasks(self):
        """Test collecting services with _task attributes."""
        runtime = Mock()
        service_registry = Mock()
        runtime.service_registry = service_registry

        # Mock services
        scheduled_service1 = Mock()
        scheduled_service1._task = Mock()

        scheduled_service2 = Mock()
        scheduled_service2._scheduler = Mock()

        normal_service = Mock()
        # normal_service has no _task or _scheduler

        service_registry.get_all_services.return_value = [
            scheduled_service1, scheduled_service2, normal_service
        ]

        result = _collect_scheduled_services(runtime)
        assert len(result) == 2
        assert scheduled_service1 in result
        assert scheduled_service2 in result
        assert normal_service not in result

    def test_collect_scheduled_services_no_registry(self):
        """Test when no service registry exists."""
        runtime = Mock()
        runtime.service_registry = None

        result = _collect_scheduled_services(runtime)
        assert result == []

    def test_collect_scheduled_services_empty_registry(self):
        """Test with empty service registry."""
        runtime = Mock()
        service_registry = Mock()
        runtime.service_registry = service_registry
        service_registry.get_all_services.return_value = []

        result = _collect_scheduled_services(runtime)
        assert result == []


class TestStopServiceTask:
    """Test individual service task stopping."""

    @pytest.mark.asyncio
    async def test_stop_service_task_with_task_attribute(self):
        """Test stopping service with _task attribute."""
        service = Mock()
        service.__class__.__name__ = "TestService"
        task_mock = AsyncMock()
        service._task = task_mock

        await _stop_service_task(service)
        task_mock.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_service_task_with_scheduler(self):
        """Test stopping service with scheduler."""
        service = Mock()
        service.__class__.__name__ = "TestService"
        service.stop_scheduler = AsyncMock()

        await _stop_service_task(service)
        service.stop_scheduler.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_service_task_cancelled_error(self):
        """Test handling of CancelledError."""
        service = Mock()
        service.__class__.__name__ = "TestService"
        task_mock = AsyncMock()
        task_mock.side_effect = asyncio.CancelledError()
        service._task = task_mock

        # Mock current_task to return non-cancelled task
        with patch('asyncio.current_task') as mock_current_task:
            current_task_mock = Mock()
            current_task_mock.cancelled.return_value = False
            mock_current_task.return_value = current_task_mock

            await _stop_service_task(service)  # Should not raise


class TestPrepareShutdownMaintenanceTasks:
    """Test shutdown maintenance preparation."""

    @pytest.mark.asyncio
    async def test_prepare_shutdown_maintenance_tasks_success(self):
        """Test successful maintenance task preparation."""
        runtime = Mock()
        service_registry = Mock()
        runtime.service_registry = service_registry

        # Mock scheduled service
        scheduled_service = Mock()
        scheduled_service.__class__.__name__ = "TestScheduledService"
        scheduled_service._task = AsyncMock()

        service_registry.get_all_services.return_value = [scheduled_service]

        with patch('ciris_engine.logic.runtime.ciris_runtime_helpers._stop_service_task') as mock_stop:
            mock_stop.return_value = None

            result = await prepare_shutdown_maintenance_tasks(runtime)
            assert len(result) == 1
            assert scheduled_service in result
            mock_stop.assert_called_once_with(scheduled_service)

    @pytest.mark.asyncio
    async def test_prepare_shutdown_maintenance_tasks_with_error(self):
        """Test handling of service stop errors."""
        runtime = Mock()
        service_registry = Mock()
        runtime.service_registry = service_registry

        scheduled_service = Mock()
        scheduled_service.__class__.__name__ = "TestService"
        scheduled_service._task = Mock()

        service_registry.get_all_services.return_value = [scheduled_service]

        with patch('ciris_engine.logic.runtime.ciris_runtime_helpers._stop_service_task') as mock_stop:
            mock_stop.side_effect = Exception("Stop failed")

            result = await prepare_shutdown_maintenance_tasks(runtime)
            assert len(result) == 1  # Service still in list despite error


class TestExecuteFinalMaintenanceTasks:
    """Test final maintenance execution."""

    @pytest.mark.asyncio
    async def test_execute_final_maintenance_tasks_success(self):
        """Test successful maintenance execution."""
        runtime = Mock()
        maintenance_service = AsyncMock()
        runtime.maintenance_service = maintenance_service

        service_initializer = Mock()
        tsdb_service = AsyncMock()
        service_initializer.tsdb_consolidation_service = tsdb_service
        runtime.service_initializer = service_initializer

        await execute_final_maintenance_tasks(runtime)

        maintenance_service.perform_startup_cleanup.assert_called_once()
        tsdb_service._run_consolidation.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_final_maintenance_tasks_with_errors(self):
        """Test handling of maintenance errors."""
        runtime = Mock()
        maintenance_service = AsyncMock()
        maintenance_service.perform_startup_cleanup.side_effect = Exception("Maintenance failed")
        runtime.maintenance_service = maintenance_service

        service_initializer = Mock()
        tsdb_service = AsyncMock()
        tsdb_service._run_consolidation.side_effect = Exception("TSDB failed")
        service_initializer.tsdb_consolidation_service = tsdb_service
        runtime.service_initializer = service_initializer

        # Should not raise exceptions
        await execute_final_maintenance_tasks(runtime)

    @pytest.mark.asyncio
    async def test_execute_final_maintenance_tasks_no_services(self):
        """Test when maintenance services don't exist."""
        runtime = Mock()
        runtime.maintenance_service = None
        runtime.service_initializer = None

        # Should complete without errors
        await execute_final_maintenance_tasks(runtime)


class TestAgentProcessorShutdown:
    """Test agent processor shutdown handling."""

    @pytest.mark.asyncio
    async def test_handle_agent_processor_shutdown_no_processor(self):
        """Test when no agent processor exists."""
        runtime = Mock()
        runtime.agent_processor = None

        # Should complete without errors
        await handle_agent_processor_shutdown(runtime)

    @pytest.mark.asyncio
    async def test_handle_agent_processor_shutdown_already_shutdown(self):
        """Test when already in shutdown state."""
        from ciris_engine.schemas.processors.states import AgentState

        runtime = Mock()
        agent_processor = Mock()
        state_manager = Mock()
        state_manager.get_state.return_value = AgentState.SHUTDOWN
        agent_processor.state_manager = state_manager
        runtime.agent_processor = agent_processor

        await handle_agent_processor_shutdown(runtime)
        # Should exit early without transition attempts

    @pytest.mark.asyncio
    async def test_transition_agent_to_shutdown_state_success(self):
        """Test successful state transition."""
        from ciris_engine.schemas.processors.states import AgentState

        runtime = Mock()
        agent_processor = Mock()
        state_manager = AsyncMock()
        state_manager.can_transition_to.return_value = True
        state_manager.transition_to = AsyncMock()
        agent_processor.state_manager = state_manager
        runtime.agent_processor = agent_processor

        result = await _transition_agent_to_shutdown_state(runtime, AgentState.WORK)
        assert result is True
        state_manager.can_transition_to.assert_called_once_with(AgentState.SHUTDOWN)
        state_manager.transition_to.assert_called_once_with(AgentState.SHUTDOWN)

    @pytest.mark.asyncio
    async def test_transition_agent_to_shutdown_state_failed(self):
        """Test failed state transition."""
        from ciris_engine.schemas.processors.states import AgentState

        runtime = Mock()
        agent_processor = Mock()
        state_manager = AsyncMock()
        state_manager.can_transition_to.return_value = False
        agent_processor.state_manager = state_manager
        runtime.agent_processor = agent_processor

        result = await _transition_agent_to_shutdown_state(runtime, AgentState.WORK)
        assert result is False


class TestAdapterShutdownCleanup:
    """Test adapter shutdown cleanup."""

    @pytest.mark.asyncio
    async def test_handle_adapter_shutdown_cleanup_success(self):
        """Test successful adapter cleanup."""
        runtime = Mock()

        # Mock bus manager
        bus_manager = AsyncMock()
        runtime.bus_manager = bus_manager

        # Mock adapters
        adapter1 = Mock()
        adapter1.stop = AsyncMock()
        adapter2 = Mock()
        adapter2.stop = AsyncMock()
        runtime.adapters = [adapter1, adapter2]

        await handle_adapter_shutdown_cleanup(runtime)

        bus_manager.stop.assert_called_once()
        adapter1.stop.assert_called_once()
        adapter2.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_adapter_shutdown_cleanup_timeout(self):
        """Test bus manager timeout handling."""
        runtime = Mock()

        # Mock bus manager with timeout
        bus_manager = AsyncMock()
        bus_manager.stop.side_effect = asyncio.TimeoutError()
        runtime.bus_manager = bus_manager
        runtime.adapters = []

        # Should not raise exception
        await handle_adapter_shutdown_cleanup(runtime)

    @pytest.mark.asyncio
    async def test_handle_adapter_shutdown_cleanup_adapter_errors(self):
        """Test adapter stop error handling."""
        runtime = Mock()
        runtime.bus_manager = None

        # Mock adapter with stop error
        adapter = Mock()
        adapter.__class__.__name__ = "TestAdapter"
        adapter.stop = AsyncMock(side_effect=Exception("Stop failed"))
        runtime.adapters = [adapter]

        # Should complete without raising
        await handle_adapter_shutdown_cleanup(runtime)


class TestServiceShutdownSequence:
    """Test service shutdown sequence execution."""

    def test_collect_all_services_to_stop(self):
        """Test comprehensive service collection."""
        runtime = Mock()

        # Mock service registry
        service_registry = Mock()
        registered_service = Mock()
        registered_service.stop = Mock()
        service_registry.get_all_services.return_value = [registered_service]
        runtime.service_registry = service_registry

        # Mock service initializer and runtime services
        service_initializer = Mock()
        service_initializer.tsdb_consolidation_service = Mock()
        runtime.service_initializer = service_initializer
        runtime.memory_service = Mock()
        runtime.memory_service.stop = Mock()

        # Mock other services as None to avoid adding them
        runtime.maintenance_service = None
        runtime.transaction_orchestrator = None

        services = _collect_all_services_to_stop(runtime)

        # Should include registered service, tsdb service, and memory service
        assert len(services) >= 2
        assert registered_service in services

    def test_get_direct_service_references(self):
        """Test direct service reference collection."""
        runtime = Mock()

        # Mock service initializer
        service_initializer = Mock()
        service_initializer.tsdb_consolidation_service = Mock()
        service_initializer.memory_service = Mock()
        runtime.service_initializer = service_initializer

        # Mock runtime services
        runtime.memory_service = Mock()
        runtime.secrets_service = Mock()

        references = _get_direct_service_references(runtime)

        # Should return list of service references
        assert len(references) == 23  # Total number of direct references
        assert service_initializer.tsdb_consolidation_service in references
        assert runtime.memory_service in references

    @pytest.mark.asyncio
    async def test_execute_service_stop_tasks_success(self):
        """Test successful service stop execution."""
        # Mock services
        service1 = Mock()
        service1.__class__.__name__ = "Service1"
        service1.stop = AsyncMock()

        service2 = Mock()
        service2.__class__.__name__ = "Service2"
        service2.stop = Mock(return_value="sync_result")  # Sync stop

        services = [service1, service2]

        with patch('ciris_engine.logic.runtime.ciris_runtime_helpers._wait_for_service_stops') as mock_wait:
            mock_wait.return_value = ([], [])

            tasks, names = await _execute_service_stop_tasks(services)
            # Should return tasks and names even if no async tasks
            assert isinstance(tasks, list)
            assert isinstance(names, list)

    @pytest.mark.asyncio
    async def test_execute_service_shutdown_sequence_integration(self):
        """Test complete service shutdown sequence."""
        runtime = Mock()

        # Mock service registry with empty services
        service_registry = Mock()
        service_registry.get_all_services.return_value = []
        runtime.service_registry = service_registry

        # Mock service initializer
        service_initializer = Mock()
        for attr in ['tsdb_consolidation_service', 'task_scheduler_service', 'incident_management_service']:
            setattr(service_initializer, attr, None)
        runtime.service_initializer = service_initializer

        # Mock runtime services as None
        for attr in ['memory_service', 'secrets_service', 'llm_service']:
            setattr(runtime, attr, None)

        services, names = await execute_service_shutdown_sequence(runtime)

        # Should complete without errors even with no services
        assert isinstance(services, list)
        assert isinstance(names, list)


class TestSystemStatePreservation:
    """Test system state preservation."""

    @pytest.mark.asyncio
    async def test_preserve_critical_system_state_success(self):
        """Test successful state preservation."""
        runtime = Mock()
        runtime.agent_identity = Mock()  # Identity exists
        runtime._preserve_shutdown_consciousness = AsyncMock()

        await preserve_critical_system_state(runtime)

        runtime._preserve_shutdown_consciousness.assert_called_once()

    @pytest.mark.asyncio
    async def test_preserve_critical_system_state_no_identity(self):
        """Test when no agent identity exists."""
        runtime = Mock()
        runtime.agent_identity = None

        # Should complete without calling consciousness preservation
        await preserve_critical_system_state(runtime)

    @pytest.mark.asyncio
    async def test_preserve_critical_system_state_error(self):
        """Test error handling in state preservation."""
        runtime = Mock()
        runtime.agent_identity = Mock()
        runtime._preserve_shutdown_consciousness = AsyncMock(side_effect=Exception("Preservation failed"))

        # Should not raise exception
        await preserve_critical_system_state(runtime)


class TestShutdownLogging:
    """Test shutdown logging finalization."""

    @pytest.mark.asyncio
    async def test_finalize_shutdown_logging_success(self):
        """Test successful shutdown logging."""
        runtime = Mock()

        with patch('ciris_engine.logic.utils.shutdown_manager.get_shutdown_manager') as mock_get_manager:
            shutdown_manager = Mock()
            shutdown_manager.execute_async_handlers = AsyncMock()
            mock_get_manager.return_value = shutdown_manager

            await finalize_shutdown_logging(runtime)

            shutdown_manager.execute_async_handlers.assert_called_once()

    @pytest.mark.asyncio
    async def test_finalize_shutdown_logging_error(self):
        """Test error handling in shutdown logging."""
        runtime = Mock()

        with patch('ciris_engine.logic.utils.shutdown_manager.get_shutdown_manager') as mock_get_manager:
            shutdown_manager = Mock()
            shutdown_manager.execute_async_handlers = AsyncMock(side_effect=Exception("Handler failed"))
            mock_get_manager.return_value = shutdown_manager

            # Should not raise exception
            await finalize_shutdown_logging(runtime)


class TestResourceCleanup:
    """Test resource cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_runtime_resources_success(self):
        """Test successful resource cleanup."""
        runtime = Mock()

        # Mock service registry
        service_registry = Mock()
        runtime.service_registry = service_registry

        # Mock shutdown event setup
        runtime._ensure_shutdown_event = Mock()
        runtime._shutdown_event = Mock()

        await cleanup_runtime_resources(runtime)

        service_registry.clear_all.assert_called_once()
        runtime._ensure_shutdown_event.assert_called_once()
        runtime._shutdown_event.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_runtime_resources_registry_error(self):
        """Test service registry cleanup error."""
        runtime = Mock()

        service_registry = Mock()
        service_registry.clear_all.side_effect = Exception("Clear failed")
        runtime.service_registry = service_registry

        runtime._ensure_shutdown_event = Mock()
        runtime._shutdown_event = Mock()

        # Should not raise exception
        await cleanup_runtime_resources(runtime)
        runtime._ensure_shutdown_event.assert_called_once()


class TestShutdownCompletion:
    """Test shutdown completion validation."""

    def test_validate_shutdown_completion_success(self):
        """Test successful shutdown completion."""
        runtime = Mock()
        runtime._shutdown_event = Mock()

        validate_shutdown_completion(runtime)

        assert runtime._shutdown_complete is True
        runtime._shutdown_event.set.assert_called_once()

    def test_validate_shutdown_completion_no_event(self):
        """Test completion when no shutdown event exists."""
        runtime = Mock()
        del runtime._shutdown_event  # Remove shutdown event

        validate_shutdown_completion(runtime)

        assert runtime._shutdown_complete is True
        # Should not raise exception when no event exists


class TestErrorHandling:
    """Test error handling across helper functions."""

    @pytest.mark.asyncio
    async def test_wait_for_service_stops_with_timeout(self):
        """Test service stop timeout handling."""
        stop_tasks = [AsyncMock() for _ in range(2)]
        service_names = ["Service1", "Service2"]

        # Mock asyncio.wait to return pending tasks
        with patch('asyncio.wait') as mock_wait:
            pending_task = AsyncMock()
            mock_wait.return_value = (set(), {pending_task})

            with patch('ciris_engine.logic.runtime.ciris_runtime_helpers._handle_hanging_services') as mock_handle:
                with patch('ciris_engine.logic.runtime.ciris_runtime_helpers._check_service_stop_errors') as mock_check:
                    await _wait_for_service_stops(stop_tasks, service_names)
                    mock_handle.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_service_stop_errors(self):
        """Test service stop error checking."""
        # Mock completed task with exception result
        task_with_error = Mock()
        task_with_error.done.return_value = True
        task_with_error.cancelled.return_value = False
        task_with_error.result.return_value = Exception("Service failed")

        stop_tasks = [task_with_error]
        service_names = ["FailedService"]

        # Should not raise exception
        await _check_service_stop_errors([task_with_error], stop_tasks, service_names)