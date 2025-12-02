"""
Additional tests for ciris_runtime_helpers.py to increase coverage.

Covers uncovered functions:
- _get_direct_service_references
- _execute_service_stop_tasks
- _wait_for_service_stops
- _handle_hanging_services
- _check_service_stop_errors
- log_adapter_configuration_details
- create_adapter_lifecycle_tasks
- _check_adapter_health
- wait_for_adapter_readiness
- verify_adapter_service_registration
- Run helper functions
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.runtime.ciris_runtime_helpers import (
    _check_adapter_health,
    _check_service_stop_errors,
    _collect_all_services_to_stop,
    _execute_service_stop_tasks,
    _get_direct_service_references,
    _handle_hanging_services,
    _wait_for_service_stops,
    create_adapter_lifecycle_tasks,
    handle_runtime_agent_task_completion,
    handle_runtime_task_failures,
    initialize_runtime_execution_context,
    log_adapter_configuration_details,
    monitor_runtime_shutdown_signals,
    setup_runtime_monitoring_tasks,
    verify_adapter_service_registration,
    wait_for_adapter_readiness,
)


class TestGetDirectServiceReferences:
    """Tests for _get_direct_service_references."""

    def test_returns_all_service_references(self):
        """Returns list of direct service references from runtime."""
        runtime = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.tsdb_consolidation_service = Mock()
        runtime.service_initializer.task_scheduler_service = Mock()
        runtime.service_initializer.incident_management_service = Mock()
        runtime.service_initializer.resource_monitor_service = Mock()
        runtime.service_initializer.config_service = Mock()
        runtime.service_initializer.auth_service = Mock()
        runtime.service_initializer.runtime_control_service = Mock()
        runtime.service_initializer.self_observation_service = Mock()
        runtime.service_initializer.visibility_service = Mock()
        runtime.service_initializer.secrets_tool_service = Mock()
        runtime.service_initializer.wa_auth_system = Mock()
        runtime.service_initializer.initialization_service = Mock()
        runtime.service_initializer.shutdown_service = Mock()
        runtime.service_initializer.time_service = Mock()
        runtime.maintenance_service = Mock()
        runtime.adaptive_filter_service = Mock()
        runtime.telemetry_service = Mock()
        runtime.audit_service = Mock()
        runtime.llm_service = Mock()
        runtime.secrets_service = Mock()
        runtime.memory_service = Mock()

        result = _get_direct_service_references(runtime)

        # Should return a list of services
        assert isinstance(result, list)
        assert len(result) > 0
        # Filter out None values
        non_none = [s for s in result if s is not None]
        assert len(non_none) > 10


class TestCollectAllServicesToStop:
    """Tests for _collect_all_services_to_stop."""

    def test_collects_services_from_registry_and_direct_refs(self):
        """Collects services from both registry and direct references."""
        runtime = Mock()
        runtime.service_registry = Mock()

        # Mock registered services
        service1 = Mock()
        service1.stop = AsyncMock()
        service2 = Mock()
        service2.stop = AsyncMock()
        runtime.service_registry.get_all_services.return_value = [service1, service2]

        # Mock direct services
        runtime.service_initializer = Mock()
        runtime.service_initializer.tsdb_consolidation_service = None
        runtime.service_initializer.task_scheduler_service = None
        runtime.service_initializer.incident_management_service = None
        runtime.service_initializer.resource_monitor_service = None
        runtime.service_initializer.config_service = None
        runtime.service_initializer.auth_service = None
        runtime.service_initializer.runtime_control_service = None
        runtime.service_initializer.self_observation_service = None
        runtime.service_initializer.visibility_service = None
        runtime.service_initializer.secrets_tool_service = None
        runtime.service_initializer.wa_auth_system = None
        runtime.service_initializer.initialization_service = None
        runtime.service_initializer.shutdown_service = None
        runtime.service_initializer.time_service = None
        runtime.maintenance_service = None
        runtime.adaptive_filter_service = None
        runtime.telemetry_service = None
        runtime.audit_service = None
        runtime.llm_service = None
        runtime.secrets_service = None
        runtime.memory_service = None

        result = _collect_all_services_to_stop(runtime)

        # Should have collected 2 registered services
        assert len(result) == 2

    def test_deduplicates_services(self):
        """Does not include duplicate services."""
        runtime = Mock()
        runtime.service_registry = Mock()

        # Same service in both registry and direct refs
        shared_service = Mock()
        shared_service.stop = AsyncMock()
        runtime.service_registry.get_all_services.return_value = [shared_service]

        runtime.service_initializer = Mock()
        runtime.service_initializer.tsdb_consolidation_service = shared_service
        runtime.service_initializer.task_scheduler_service = None
        runtime.service_initializer.incident_management_service = None
        runtime.service_initializer.resource_monitor_service = None
        runtime.service_initializer.config_service = None
        runtime.service_initializer.auth_service = None
        runtime.service_initializer.runtime_control_service = None
        runtime.service_initializer.self_observation_service = None
        runtime.service_initializer.visibility_service = None
        runtime.service_initializer.secrets_tool_service = None
        runtime.service_initializer.wa_auth_system = None
        runtime.service_initializer.initialization_service = None
        runtime.service_initializer.shutdown_service = None
        runtime.service_initializer.time_service = None
        runtime.maintenance_service = None
        runtime.adaptive_filter_service = None
        runtime.telemetry_service = None
        runtime.audit_service = None
        runtime.llm_service = None
        runtime.secrets_service = None
        runtime.memory_service = None

        result = _collect_all_services_to_stop(runtime)

        # Should only have 1 service (deduplicated)
        assert len(result) == 1


class TestExecuteServiceStopTasks:
    """Tests for _execute_service_stop_tasks."""

    @pytest.mark.asyncio
    async def test_executes_stop_on_all_services(self):
        """Executes stop on all services with stop method."""
        service1 = Mock()
        service1.__class__.__name__ = "Service1"
        service1.stop = AsyncMock()

        service2 = Mock()
        service2.__class__.__name__ = "Service2"
        service2.stop = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime_helpers._wait_for_service_stops") as mock_wait:
            mock_wait.return_value = ([], [])

            await _execute_service_stop_tasks([service1, service2])

            service1.stop.assert_called_once()
            service2.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_empty_list(self):
        """Handles empty service list gracefully."""
        result = await _execute_service_stop_tasks([])
        assert result == ([], [])


class TestWaitForServiceStops:
    """Tests for _wait_for_service_stops."""

    @pytest.mark.asyncio
    async def test_all_services_stop_successfully(self):
        """All services stop successfully within timeout."""

        # Create mock tasks that complete immediately
        async def mock_stop():
            pass

        tasks = [asyncio.create_task(mock_stop()) for _ in range(2)]
        service_names = ["Service1", "Service2"]

        # Wait for tasks to complete
        await asyncio.sleep(0.01)

        with patch("ciris_engine.logic.runtime.ciris_runtime_helpers._check_service_stop_errors") as mock_check:
            mock_check.return_value = None

            result = await _wait_for_service_stops(tasks, service_names)

            assert len(result[0]) == 2
            assert len(result[1]) == 2


class TestHandleHangingServices:
    """Tests for _handle_hanging_services."""

    @pytest.mark.asyncio
    async def test_cancels_hanging_tasks(self):
        """Cancels tasks that didn't complete in time."""

        # Create a task that never completes
        async def never_completes():
            await asyncio.sleep(100)

        task = asyncio.create_task(never_completes())
        pending = {task}
        stop_tasks = [task]
        service_names = ["HangingService"]

        await _handle_hanging_services(pending, stop_tasks, service_names)

        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_handles_unknown_task(self):
        """Handles task not in stop_tasks list."""

        async def never_completes():
            await asyncio.sleep(100)

        task = asyncio.create_task(never_completes())
        pending = {task}
        stop_tasks = []  # Task not in list
        service_names = []

        # Should not raise
        await _handle_hanging_services(pending, stop_tasks, service_names)

        assert task.cancelled()


class TestCheckServiceStopErrors:
    """Tests for _check_service_stop_errors."""

    @pytest.mark.asyncio
    async def test_logs_errors_in_completed_tasks(self):
        """Logs errors from completed tasks."""

        # Create a task that raises an exception
        async def failing_task():
            raise ValueError("Stop failed")

        task = asyncio.create_task(failing_task())

        # Wait for task to complete with exception
        try:
            await task
        except ValueError:
            pass

        done = {task}
        stop_tasks = [task]
        service_names = ["FailingService"]

        # Should not raise, just log
        await _check_service_stop_errors(done, stop_tasks, service_names)

    @pytest.mark.asyncio
    async def test_skips_cancelled_tasks(self):
        """Skips cancelled tasks."""

        async def dummy():
            await asyncio.sleep(100)

        task = asyncio.create_task(dummy())
        task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass

        done = {task}
        stop_tasks = [task]
        service_names = ["CancelledService"]

        # Should not raise
        await _check_service_stop_errors(done, stop_tasks, service_names)


class TestLogAdapterConfigurationDetails:
    """Tests for log_adapter_configuration_details."""

    def test_logs_discord_adapter_config(self):
        """Logs Discord adapter configuration details."""
        adapter = Mock()
        adapter.__class__.__name__ = "DiscordPlatform"
        adapter.config = Mock()
        adapter.config.monitored_channel_ids = ["123", "456"]
        adapter.config.server_id = "server123"
        adapter.config.bot_token = "xxxxxxxxxxx123456"

        # Should not raise
        log_adapter_configuration_details([adapter])

    def test_logs_non_discord_adapters(self):
        """Logs other adapter types."""
        adapter = Mock()
        adapter.__class__.__name__ = "APIAdapter"

        # Should not raise
        log_adapter_configuration_details([adapter])


class TestCreateAdapterLifecycleTasks:
    """Tests for create_adapter_lifecycle_tasks."""

    @pytest.mark.asyncio
    async def test_creates_lifecycle_tasks(self):
        """Creates lifecycle tasks for adapters with run_lifecycle method."""
        adapter = Mock()
        adapter.__class__.__name__ = "TestAdapter"

        # Create a proper async function for run_lifecycle
        async def mock_lifecycle(task):
            await asyncio.sleep(0)  # Minimal async operation

        adapter.run_lifecycle = mock_lifecycle

        agent_task = Mock()

        result = create_adapter_lifecycle_tasks([adapter], agent_task)

        assert len(result) == 1
        assert result[0].get_name() == "TestAdapterLifecycleTask"

        # Clean up task properly
        result[0].cancel()
        try:
            await result[0]
        except asyncio.CancelledError:
            pass

    def test_skips_adapters_without_lifecycle(self):
        """Skips adapters without run_lifecycle method."""
        adapter = Mock(spec=[])  # No run_lifecycle

        result = create_adapter_lifecycle_tasks([adapter], Mock())

        assert len(result) == 0


class TestCheckAdapterHealth:
    """Tests for _check_adapter_health."""

    @pytest.mark.asyncio
    async def test_returns_true_for_non_discord(self):
        """Returns True for non-Discord adapters."""
        adapter = Mock()
        adapter.__class__.__name__ = "APIAdapter"

        result = await _check_adapter_health(adapter)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_true_for_healthy_discord(self):
        """Returns True for healthy Discord adapter."""
        adapter = Mock()
        adapter.__class__.__name__ = "DiscordPlatform"
        adapter.is_healthy = AsyncMock(return_value=True)

        result = await _check_adapter_health(adapter)

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_for_unhealthy_discord(self):
        """Returns False for unhealthy Discord adapter."""
        adapter = Mock()
        adapter.__class__.__name__ = "DiscordPlatform"
        adapter.is_healthy = AsyncMock(return_value=False)

        result = await _check_adapter_health(adapter)

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_for_missing_health_method(self):
        """Returns False when Discord adapter has no is_healthy method."""
        adapter = Mock(spec=[])  # No is_healthy
        adapter.__class__.__name__ = "DiscordPlatform"

        result = await _check_adapter_health(adapter)

        assert result is False

    @pytest.mark.asyncio
    async def test_handles_health_check_exception(self):
        """Handles exceptions in health check."""
        adapter = Mock()
        adapter.__class__.__name__ = "DiscordPlatform"
        adapter.is_healthy = AsyncMock(side_effect=Exception("Health check failed"))

        result = await _check_adapter_health(adapter)

        assert result is False


class TestWaitForAdapterReadiness:
    """Tests for wait_for_adapter_readiness."""

    @pytest.mark.asyncio
    async def test_returns_true_when_all_healthy(self):
        """Returns True when all adapters are healthy."""
        adapter = Mock()
        adapter.__class__.__name__ = "APIAdapter"

        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers._check_adapter_health",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = True

            result = await wait_for_adapter_readiness([adapter])

            assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self):
        """Returns False when timeout is reached."""
        adapter = Mock()
        adapter.__class__.__name__ = "DiscordPlatform"

        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers._check_adapter_health",
            new_callable=AsyncMock,
        ) as mock_check:
            mock_check.return_value = False

            with patch("ciris_engine.logic.runtime.ciris_runtime_helpers._async_timeout") as mock_timeout:
                # Simulate timeout
                mock_timeout.side_effect = asyncio.TimeoutError()

                result = await wait_for_adapter_readiness([adapter])

                assert result is False


class TestVerifyAdapterServiceRegistration:
    """Tests for verify_adapter_service_registration."""

    @pytest.mark.asyncio
    async def test_returns_true_when_services_available(self):
        """Returns True when services are available."""
        runtime = Mock()
        runtime._register_adapter_services = AsyncMock()
        runtime.service_registry = Mock()
        runtime.service_registry.get_service = AsyncMock(return_value=Mock())

        with patch("ciris_engine.logic.runtime.ciris_runtime_helpers._async_timeout") as mock_timeout:
            # Simulate successful check
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def mock_context(_):
                yield

            mock_timeout.return_value = mock_context(10.0)

            result = await verify_adapter_service_registration(runtime)

            assert result is True
            runtime._register_adapter_services.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self):
        """Returns False when service registration times out."""
        runtime = Mock()
        runtime._register_adapter_services = AsyncMock()
        runtime.service_registry = Mock()
        runtime.service_registry.get_service = AsyncMock(side_effect=Exception("Not found"))

        with patch("ciris_engine.logic.runtime.ciris_runtime_helpers._async_timeout") as mock_timeout:
            mock_timeout.side_effect = asyncio.TimeoutError()

            result = await verify_adapter_service_registration(runtime)

            assert result is False


class TestInitializeRuntimeExecutionContext:
    """Tests for initialize_runtime_execution_context."""

    def test_raises_when_not_initialized(self):
        """Raises RuntimeError when runtime not initialized."""
        runtime = Mock()
        runtime._initialized = False

        with pytest.raises(RuntimeError, match="must be initialized"):
            initialize_runtime_execution_context(runtime)

    def test_passes_when_initialized(self):
        """Does not raise when runtime is initialized."""
        runtime = Mock()
        runtime._initialized = True

        # Should not raise
        initialize_runtime_execution_context(runtime)


class TestSetupRuntimeMonitoringTasks:
    """Tests for setup_runtime_monitoring_tasks."""

    def test_returns_none_without_adapter_tasks(self):
        """Returns None values when no adapter tasks."""
        runtime = Mock()
        runtime._adapter_tasks = []

        result = setup_runtime_monitoring_tasks(runtime)

        assert result == (None, [], [])


class TestMonitorRuntimeShutdownSignals:
    """Tests for monitor_runtime_shutdown_signals."""

    def test_logs_shutdown_when_triggered(self):
        """Logs shutdown reason when triggered."""
        runtime = Mock()
        runtime._shutdown_event = Mock()
        runtime._shutdown_event.is_set.return_value = True
        runtime._shutdown_reason = "Test shutdown"
        runtime._shutdown_manager = Mock()
        runtime._shutdown_manager.get_shutdown_reason.return_value = None

        result = monitor_runtime_shutdown_signals(runtime, False)

        assert result is True  # Now logged

    def test_returns_existing_flag_when_already_logged(self):
        """Returns existing flag when already logged."""
        runtime = Mock()
        runtime._shutdown_event = Mock()
        runtime._shutdown_event.is_set.return_value = True

        result = monitor_runtime_shutdown_signals(runtime, True)

        assert result is True


class TestHandleRuntimeAgentTaskCompletion:
    """Tests for handle_runtime_agent_task_completion."""

    def test_requests_shutdown_on_completion(self):
        """Requests shutdown when agent task completes."""
        runtime = Mock()
        runtime.request_shutdown = Mock()

        agent_task = Mock()
        agent_task.cancelled.return_value = False
        agent_task.result.return_value = "completed"

        adapter_task = Mock()
        adapter_task.done.return_value = False

        handle_runtime_agent_task_completion(runtime, agent_task, [adapter_task])

        runtime.request_shutdown.assert_called_once()
        adapter_task.cancel.assert_called_once()


class TestHandleRuntimeTaskFailures:
    """Tests for handle_runtime_task_failures."""

    def test_handles_task_failure(self):
        """Handles task failure and requests shutdown."""
        runtime = Mock()
        runtime.request_shutdown = Mock()

        task = Mock()
        task.get_name.return_value = "FailingTask"
        task.cancelled.return_value = False
        task.result.return_value = None
        task.exception.return_value = Exception("Task failed")

        handle_runtime_task_failures(runtime, {task}, set())

        runtime.request_shutdown.assert_called_once()

    def test_skips_excluded_tasks(self):
        """Skips tasks in excluded set."""
        runtime = Mock()
        runtime.request_shutdown = Mock()

        task = Mock()
        task.exception.return_value = Exception("Task failed")

        handle_runtime_task_failures(runtime, {task}, {task})

        runtime.request_shutdown.assert_not_called()
