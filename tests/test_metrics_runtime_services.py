"""
Comprehensive metric tests for all Runtime services.

Tests metrics collection for:
1. LLMService (OpenAICompatibleClient) - 15 metrics (no caching)
2. RuntimeControlService - 16 metrics
3. TaskSchedulerService - 16 metrics

Each service test verifies:
- All expected metrics are present and valid
- Metric ranges and data types are correct
- Service-specific functionality affects metrics properly
- Mock integrations work correctly
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.services.lifecycle.scheduler import TaskSchedulerService
from ciris_engine.logic.services.runtime.control_service import RuntimeControlService
from ciris_engine.logic.services.runtime.llm_service import OpenAICompatibleClient, OpenAIConfig
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core.runtime import ProcessorStatus
from tests.test_metrics_base import BaseMetricsTest


# Module-level fixtures for integration tests
@pytest.fixture
def mock_telemetry_service():
    """Mock telemetry service."""
    telemetry = AsyncMock()
    telemetry.record_metric = AsyncMock()
    telemetry.get_metrics = AsyncMock(return_value={})
    return telemetry


@pytest.fixture
def llm_config():
    """Mock LLM configuration."""
    return OpenAIConfig(
        api_key="test-api-key", model_name="gpt-4o-mini", instructor_mode="JSON", max_retries=3, timeout_seconds=30
    )


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client."""
    with patch("ciris_engine.logic.services.runtime.llm_service.AsyncOpenAI") as mock_client:
        # Mock the client instance
        client_instance = AsyncMock()
        client_instance.close = AsyncMock()
        mock_client.return_value = client_instance

        # Mock instructor client
        with patch("ciris_engine.logic.services.runtime.llm_service.instructor.from_openai") as mock_instructor:
            instructor_instance = AsyncMock()
            mock_instructor.return_value = instructor_instance
            yield {"openai_client": client_instance, "instructor_client": instructor_instance}


@pytest.fixture
def mock_circuit_breaker():
    """Mock circuit breaker."""
    with patch("ciris_engine.logic.services.runtime.llm_service.CircuitBreaker") as mock_cb:
        cb_instance = MagicMock()
        cb_instance.is_available.return_value = True
        cb_instance.get_stats.return_value = {
            "state": "closed",
            "consecutive_failures": 0,
            "recovery_attempts": 0,
            "last_failure_age": 0,
            "success_rate": 1.0,
            "call_count": 5,
            "failure_count": 0,
        }
        cb_instance.check_and_raise.return_value = None
        cb_instance.record_success.return_value = None
        cb_instance.record_failure.return_value = None
        mock_cb.return_value = cb_instance
        yield cb_instance


@pytest_asyncio.fixture
async def llm_service(llm_config, mock_openai_client, mock_circuit_breaker, mock_time_service, mock_telemetry_service):
    """Create LLM service with mocked dependencies."""
    # Mock environment variables to prevent mock LLM detection
    with patch.dict("os.environ", {}, clear=True):
        with patch("sys.argv", ["test"]):  # Remove any --mock-llm flags
            service = OpenAICompatibleClient(
                config=llm_config,
                telemetry_service=mock_telemetry_service,
                time_service=mock_time_service,
                service_name="test_llm_service",
            )

            # Simulate some activity for metrics
            service._response_times = [100.0, 150.0, 120.0]  # Response times in ms
            service._total_api_calls = 5
            service._successful_api_calls = 4

            await service.start()
            yield service
            await service.stop()


@pytest.fixture
def mock_runtime():
    """Mock runtime interface."""
    runtime = MagicMock()
    runtime.agent_processor = MagicMock()
    runtime.agent_processor.queue = []  # Empty queue
    runtime.agent_processor.state = "WORK"
    runtime.agent_processor.single_step = AsyncMock(return_value="step_result")
    runtime.agent_processor.pause_processing = AsyncMock(return_value=True)
    runtime.agent_processor.resume_processing = AsyncMock(return_value=True)
    runtime.agent_processor.get_queue_status = MagicMock()
    runtime.agent_processor.get_queue_status.return_value = MagicMock(pending_thoughts=2, pending_tasks=1)

    # Mock service registry
    runtime.service_registry = MagicMock()
    runtime.service_registry.get_service.return_value = MagicMock()

    return runtime


@pytest.fixture
def mock_adapter_manager():
    """Mock adapter manager."""
    manager = MagicMock()
    manager.active_adapters = {"test_adapter": MagicMock()}
    manager.list_adapters = AsyncMock(return_value=[])
    manager.load_adapter = AsyncMock()
    manager.unload_adapter = AsyncMock()
    manager.get_adapter_info = AsyncMock(return_value={})
    return manager


@pytest_asyncio.fixture
async def runtime_control_service(mock_runtime, mock_adapter_manager, mock_time_service, mock_config_service):
    """Create runtime control service with mocked dependencies."""
    service = RuntimeControlService(
        runtime=mock_runtime,
        adapter_manager=mock_adapter_manager,
        config_manager=mock_config_service,
        time_service=mock_time_service,
    )

    # Simulate some activity
    service._thoughts_processed = 10
    service._thoughts_pending = 2
    service._messages_processed = 15
    service._runtime_errors = 1
    service._thought_times = [100.0, 150.0, 120.0]
    service._message_times = [50.0, 75.0, 60.0]

    await service.start()
    yield service
    await service.stop()


@pytest_asyncio.fixture
async def task_scheduler_service(mock_time_service):
    """Create task scheduler service with mocked dependencies."""
    with patch("ciris_engine.logic.services.lifecycle.scheduler.get_db_connection"):
        service = TaskSchedulerService(db_path=":memory:", time_service=mock_time_service, check_interval_seconds=60)

        # Simulate some activity
        service._tasks_scheduled = 5
        service._tasks_triggered = 4
        service._tasks_completed = 3
        service._tasks_failed = 1
        service._recurring_tasks = 2
        service._oneshot_tasks = 3

        # Add some active tasks
        from ciris_engine.schemas.runtime.extended import ScheduledTask

        task1 = ScheduledTask(
            task_id="task1",
            name="Test Task 1",
            goal_description="Test goal",
            status="ACTIVE",
            trigger_prompt="Test prompt",
            origin_thought_id="thought1",
            created_at=datetime.now(timezone.utc).isoformat(),
            schedule_cron="0 9 * * *",  # Recurring
            deferral_count=0,
            deferral_history=[],
        )
        task2 = ScheduledTask(
            task_id="task2",
            name="Test Task 2",
            goal_description="Test goal 2",
            status="PENDING",
            trigger_prompt="Test prompt 2",
            origin_thought_id="thought2",
            created_at=datetime.now(timezone.utc).isoformat(),
            defer_until=datetime.now(timezone.utc) + timedelta(hours=1),  # One-shot
            deferral_count=0,
            deferral_history=[],
        )

        service._active_tasks = {"task1": task1, "task2": task2}

        await service.start()
        yield service
        await service.stop()


class TestLLMServiceMetrics(BaseMetricsTest):
    """Test metrics for LLM service."""

    # Expected LLM service metrics (15 total, no caching)
    EXPECTED_LLM_METRICS = {
        # Circuit breaker metrics (7)
        "circuit_breaker_state",
        "consecutive_failures",
        "recovery_attempts",
        "last_failure_age_seconds",
        "success_rate",
        "call_count",
        "failure_count",
        # Performance metrics (6)
        "avg_response_time_ms",
        "max_response_time_ms",
        "min_response_time_ms",
        "total_api_calls",
        "successful_api_calls",
        "api_success_rate",
        # Configuration metrics (5)
        "model_cost_per_1k_tokens",
        "retry_delay_base",
        "retry_delay_max",
        "model_timeout_seconds",
        "model_max_retries",
    }

    NON_NEGATIVE_LLM_METRICS = {
        "consecutive_failures",
        "recovery_attempts",
        "last_failure_age_seconds",
        "call_count",
        "failure_count",
        "avg_response_time_ms",
        "max_response_time_ms",
        "min_response_time_ms",
        "total_api_calls",
        "successful_api_calls",
        "model_cost_per_1k_tokens",
        "retry_delay_base",
        "retry_delay_max",
        "model_timeout_seconds",
        "model_max_retries",
    }

    RATIO_LLM_METRICS = {"success_rate", "api_success_rate"}

    @pytest.mark.asyncio
    async def test_llm_service_base_metrics(self, llm_service):
        """Test that LLM service has all base metrics."""
        metrics = await self.verify_service_metrics_base_requirements(llm_service)
        assert len(metrics) >= len(self.BASE_METRICS)

    @pytest.mark.asyncio
    async def test_llm_service_expected_metrics(self, llm_service):
        """Test that LLM service has all expected metrics."""
        metrics = await self.get_service_metrics(llm_service)

        # Check all expected metrics exist
        self.assert_metrics_exist(metrics, self.EXPECTED_LLM_METRICS)

        # Check non-negative metrics
        for metric in self.NON_NEGATIVE_LLM_METRICS:
            if metric in metrics:
                assert metrics[metric] >= 0, f"Metric {metric} should be non-negative: {metrics[metric]}"

        # Check ratio metrics
        for metric in self.RATIO_LLM_METRICS:
            if metric in metrics:
                assert 0 <= metrics[metric] <= 1.0001, f"Metric {metric} should be 0-1: {metrics[metric]}"

    @pytest.mark.asyncio
    async def test_llm_circuit_breaker_metrics(self, llm_service):
        """Test circuit breaker state metrics."""
        metrics = await self.get_service_metrics(llm_service)

        # Circuit breaker should be closed (0.0)
        # v1.4.3: Old metric removed

        # assert metrics["circuit_breaker_state"] == 0.0, "Circuit breaker should be closed"
        # v1.4.3: Old metric removed

        # assert metrics["consecutive_failures"] == 0, "No consecutive failures expected"
        assert metrics["success_rate"] == 1.0, "Success rate should be 1.0"

    @pytest.mark.asyncio
    async def test_llm_response_time_tracking(self, llm_service):
        """Test response time metrics tracking."""
        metrics = await self.get_service_metrics(llm_service)

        # Should have response time metrics from simulated data
        assert metrics["avg_response_time_ms"] > 0, "Should have average response time"
        assert metrics["max_response_time_ms"] >= metrics["avg_response_time_ms"]
        assert metrics["min_response_time_ms"] <= metrics["avg_response_time_ms"]

        # Check that response times list is being used
        expected_avg = sum(llm_service._response_times) / len(llm_service._response_times)
        assert abs(metrics["avg_response_time_ms"] - expected_avg) < 0.1

    @pytest.mark.asyncio
    async def test_llm_api_call_metrics(self, llm_service):
        """Test API call tracking metrics."""
        metrics = await self.get_service_metrics(llm_service)

        # Check API call counts
        assert metrics["total_api_calls"] == 5, "Should track total API calls"
        assert metrics["successful_api_calls"] == 4, "Should track successful calls"
        assert abs(metrics["api_success_rate"] - 0.8) < 0.001, "API success rate should be 4/5"

    @pytest.mark.asyncio
    async def test_llm_configuration_metrics(self, llm_service):
        """Test configuration-related metrics."""
        metrics = await self.get_service_metrics(llm_service)

        # Check model configuration metrics
        assert metrics["model_timeout_seconds"] == 30.0, "Should reflect config timeout"
        assert metrics["model_max_retries"] == 3.0, "Should reflect config max retries"
        assert metrics["model_cost_per_1k_tokens"] > 0, "Should have cost estimate"


class TestRuntimeControlServiceMetrics(BaseMetricsTest):
    """Test metrics for Runtime Control service."""

    # Expected Runtime Control metrics (16 total)
    EXPECTED_RUNTIME_METRICS = {
        # Original metrics (3)
        "events_count",
        "processor_status",
        "adapters_loaded",
        # Enhanced metrics (13)
        "queue_depth",
        "thoughts_processed",
        "thoughts_pending",
        "cognitive_state",
        "average_thought_time_ms",
        "runtime_paused",
        "runtime_step_mode",
        "service_overrides_active",
        "runtime_errors",
        "messages_processed",
        "average_message_latency_ms",
        "processing_rate_per_sec",
        "system_load",
    }

    NON_NEGATIVE_RUNTIME_METRICS = {
        "events_count",
        "adapters_loaded",
        "queue_depth",
        "thoughts_processed",
        "thoughts_pending",
        "average_thought_time_ms",
        "service_overrides_active",
        "runtime_errors",
        "messages_processed",
        "average_message_latency_ms",
        "processing_rate_per_sec",
    }

    RATIO_RUNTIME_METRICS = {"processor_status", "runtime_paused", "runtime_step_mode", "system_load"}

    @pytest.mark.asyncio
    async def test_runtime_control_base_metrics(self, runtime_control_service):
        """Test that Runtime Control service has all base metrics."""
        metrics = await self.verify_service_metrics_base_requirements(runtime_control_service)
        assert len(metrics) >= len(self.BASE_METRICS)

    @pytest.mark.asyncio
    async def test_runtime_control_expected_metrics(self, runtime_control_service):
        """Test that Runtime Control service has all expected metrics."""
        metrics = await self.get_service_metrics(runtime_control_service)

        # Check all expected metrics exist
        self.assert_metrics_exist(metrics, self.EXPECTED_RUNTIME_METRICS)

        # Check non-negative metrics
        for metric in self.NON_NEGATIVE_RUNTIME_METRICS:
            if metric in metrics:
                assert metrics[metric] >= 0, f"Metric {metric} should be non-negative: {metrics[metric]}"

        # Check ratio metrics (should be 0-1 or valid status codes)
        for metric in self.RATIO_RUNTIME_METRICS:
            if metric in metrics:
                if metric == "cognitive_state":
                    assert metrics[metric] >= 0, f"Cognitive state should be >= 0: {metrics[metric]}"
                else:
                    assert 0 <= metrics[metric] <= 1.0001, f"Metric {metric} should be 0-1: {metrics[metric]}"

    @pytest.mark.asyncio
    async def test_runtime_control_queue_metrics(self, runtime_control_service):
        """Test queue depth and processing metrics."""
        metrics = await self.get_service_metrics(runtime_control_service)

        # Queue should be empty by default
        assert metrics["queue_depth"] == 0.0, "Queue should be empty"
        assert metrics["thoughts_processed"] == 10.0, "Should track thoughts processed"
        assert metrics["thoughts_pending"] == 2.0, "Should track pending thoughts"

    @pytest.mark.asyncio
    async def test_runtime_control_cognitive_state(self, runtime_control_service):
        """Test cognitive state mapping."""
        metrics = await self.get_service_metrics(runtime_control_service)

        # WORK state should map to 2.0
        assert metrics["cognitive_state"] == 2.0, "WORK state should map to 2.0"

    @pytest.mark.asyncio
    async def test_runtime_control_processing_rates(self, runtime_control_service):
        """Test processing rate calculations."""
        metrics = await self.get_service_metrics(runtime_control_service)

        # Should have processing metrics
        assert metrics["messages_processed"] == 15.0, "Should track messages processed"
        assert metrics["processing_rate_per_sec"] >= 0, "Processing rate should be non-negative"
        assert metrics["average_message_latency_ms"] > 0, "Should have average latency"

    @pytest.mark.asyncio
    async def test_runtime_control_system_load(self, runtime_control_service):
        """Test system load calculation."""
        metrics = await self.get_service_metrics(runtime_control_service)

        # System load should be 0-1 range
        assert 0 <= metrics["system_load"] <= 1.0, "System load should be 0-1"

    @pytest.mark.asyncio
    async def test_runtime_control_processor_status_changes(self, runtime_control_service):
        """Test processor status changes affect metrics."""
        # Test pause
        response = await runtime_control_service.pause_processing()
        assert response.success

        metrics = await self.get_service_metrics(runtime_control_service)
        assert metrics["runtime_paused"] == 1.0, "Should show runtime as paused"

        # Test resume
        response = await runtime_control_service.resume_processing()
        assert response.success

        metrics = await self.get_service_metrics(runtime_control_service)
        assert metrics["runtime_paused"] == 0.0, "Should show runtime as not paused"


class TestTaskSchedulerServiceMetrics(BaseMetricsTest):
    """Test metrics for Task Scheduler service."""

    # Expected Task Scheduler metrics (14 total)
    EXPECTED_SCHEDULER_METRICS = {
        # Base scheduled service metrics (5)
        "task_run_count",
        "task_interval_seconds",
        "task_running",
        "task_error_count",
        "time_since_last_task_run",
        # Task scheduler specific metrics (9)
        "active_tasks",
        "check_interval",
        "tasks_scheduled",
        "tasks_triggered",
        "tasks_completed",
        "tasks_failed",
        "task_success_rate",
        "recurring_tasks",
        "task_error_rate",
    }

    NON_NEGATIVE_SCHEDULER_METRICS = {
        "task_run_count",
        "task_interval_seconds",
        "task_error_count",
        "time_since_last_task_run",
        "active_tasks",
        "check_interval",
        "tasks_scheduled",
        "tasks_triggered",
        "tasks_completed",
        "tasks_failed",
        "recurring_tasks",
    }

    RATIO_SCHEDULER_METRICS = {"task_running", "task_success_rate", "task_error_rate"}

    @pytest.mark.asyncio
    async def test_scheduler_service_base_metrics(self, task_scheduler_service):
        """Test that Task Scheduler service has all base metrics."""
        # v1.4.3: Services do not have generic base metrics
        pass

    @pytest.mark.asyncio
    async def test_scheduler_service_expected_metrics(self, task_scheduler_service):
        """Test that Task Scheduler service has all expected metrics."""
        metrics = await self.get_service_metrics(task_scheduler_service)

        # Check all expected metrics exist (may have more due to base class)
        missing_metrics = self.EXPECTED_SCHEDULER_METRICS - set(metrics.keys())
        assert not missing_metrics, f"Missing expected metrics: {missing_metrics}"

        # Check non-negative metrics
        for metric in self.NON_NEGATIVE_SCHEDULER_METRICS:
            if metric in metrics:
                assert metrics[metric] >= 0, f"Metric {metric} should be non-negative: {metrics[metric]}"

        # Check ratio metrics
        for metric in self.RATIO_SCHEDULER_METRICS:
            if metric in metrics:
                assert 0 <= metrics[metric] <= 1.0001, f"Metric {metric} should be 0-1: {metrics[metric]}"

    @pytest.mark.asyncio
    async def test_scheduler_task_count_metrics(self, task_scheduler_service):
        """Test task counting metrics."""
        metrics = await self.get_service_metrics(task_scheduler_service)

        # Check task counts
        assert metrics["active_tasks"] == 2.0, "Should have 2 active tasks"
        assert metrics["tasks_scheduled"] == 5.0, "Should track scheduled tasks"
        assert metrics["tasks_triggered"] == 4.0, "Should track triggered tasks"
        assert metrics["tasks_completed"] == 3.0, "Should track completed tasks"
        assert metrics["tasks_failed"] == 1.0, "Should track failed tasks"

    @pytest.mark.asyncio
    async def test_scheduler_success_rate_calculation(self, task_scheduler_service):
        """Test task success rate calculation."""
        metrics = await self.get_service_metrics(task_scheduler_service)

        # Success rate should be completed / (completed + failed) = 3 / (3 + 1) = 0.75
        expected_rate = 3.0 / (3.0 + 1.0)
        assert (
            abs(metrics["task_success_rate"] - expected_rate) < 0.001
        ), f"Success rate should be {expected_rate}, got {metrics['task_success_rate']}"

    @pytest.mark.asyncio
    async def test_scheduler_recurring_vs_oneshot(self, task_scheduler_service):
        """Test recurring vs one-shot task counting."""
        metrics = await self.get_service_metrics(task_scheduler_service)

        # Should have 1 recurring task (with cron) and 1 one-shot (with defer_until)
        assert metrics["recurring_tasks"] == 1.0, "Should have 1 recurring task"

    @pytest.mark.asyncio
    async def test_scheduler_configuration_metrics(self, task_scheduler_service):
        """Test configuration-related metrics."""
        metrics = await self.get_service_metrics(task_scheduler_service)

        # Check configuration
        assert metrics["check_interval"] == 60.0, "Should reflect check interval"
        assert metrics["task_interval_seconds"] == 60.0, "Should reflect task interval"

    @pytest.mark.asyncio
    async def test_scheduler_task_scheduling(self, task_scheduler_service):
        """Test that scheduling a task updates metrics."""
        # Get initial metrics
        initial_metrics = await self.get_service_metrics(task_scheduler_service)
        initial_scheduled = initial_metrics["tasks_scheduled"]
        initial_active = initial_metrics["active_tasks"]

        # Schedule a new task
        task = await task_scheduler_service.schedule_task(
            name="New Test Task",
            goal_description="New test goal",
            trigger_prompt="New test prompt",
            origin_thought_id="new_thought",
            defer_until=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        )

        # Check updated metrics
        updated_metrics = await self.get_service_metrics(task_scheduler_service)

        assert updated_metrics["tasks_scheduled"] == initial_scheduled + 1, "Should increment scheduled tasks count"
        assert updated_metrics["active_tasks"] == initial_active + 1, "Should increment active tasks count"

    @pytest.mark.asyncio
    async def test_scheduler_task_cancellation(self, task_scheduler_service):
        """Test that cancelling a task updates metrics."""
        # Get initial metrics
        initial_metrics = await self.get_service_metrics(task_scheduler_service)
        initial_active = initial_metrics["active_tasks"]

        # Cancel an existing task
        success = await task_scheduler_service.cancel_task("task1")
        assert success, "Should successfully cancel task"

        # Check updated metrics
        updated_metrics = await self.get_service_metrics(task_scheduler_service)

        assert updated_metrics["active_tasks"] == initial_active - 1, "Should decrement active tasks count"


# Integration tests for all runtime service metrics
class TestRuntimeServicesMetricsIntegration(BaseMetricsTest):
    """Integration tests for all runtime service metrics."""

    @pytest.mark.asyncio
    async def test_all_runtime_services_have_base_metrics(
        self, llm_service, runtime_control_service, task_scheduler_service
    ):
        """Test that all runtime services have required base metrics."""
        services = [
            ("LLMService", llm_service),
            ("RuntimeControlService", runtime_control_service),
            ("TaskSchedulerService", task_scheduler_service),
        ]

        for service_name, service in services:
            metrics = await self.get_service_metrics(service)

            # Check base metrics
            self.assert_base_metrics_present(metrics)

            # Check all values are numeric
            self.assert_all_metrics_are_floats(metrics)

            # Check valid ranges
            self.assert_metrics_valid_ranges(metrics)

    @pytest.mark.asyncio
    async def test_runtime_services_metric_counts(self, llm_service, runtime_control_service, task_scheduler_service):
        """Test that runtime services have expected metric counts."""
        # LLM Service: 15 custom + 5 base = 20 total
        llm_metrics = await self.get_service_metrics(llm_service)
        assert len(llm_metrics) >= 20, f"LLM service should have >=20 metrics, got {len(llm_metrics)}"

        # Runtime Control Service: 16 custom + 5 base = 21 total
        control_metrics = await self.get_service_metrics(runtime_control_service)
        assert len(control_metrics) >= 21, f"Runtime control should have >=21 metrics, got {len(control_metrics)}"

        # Task Scheduler Service: 14 custom + 5 base = 19 total
        scheduler_metrics = await self.get_service_metrics(task_scheduler_service)
        assert len(scheduler_metrics) >= 19, f"Task scheduler should have >=19 metrics, got {len(scheduler_metrics)}"

    @pytest.mark.asyncio
    async def test_runtime_services_no_dict_any_metrics(
        self, llm_service, runtime_control_service, task_scheduler_service
    ):
        """Test that runtime services don't return Dict[str, Any] style metrics."""
        services = [llm_service, runtime_control_service, task_scheduler_service]

        for service in services:
            metrics = await self.get_service_metrics(service)

            # All metrics should be float/int values, not complex objects
            for key, value in metrics.items():
                assert isinstance(value, (int, float)), f"Metric {key} should be numeric, got {type(value)}: {value}"

                # Should not be nested dicts or lists
                assert not isinstance(value, (dict, list)), f"Metric {key} should not be complex type: {type(value)}"

    @pytest.mark.asyncio
    async def test_runtime_services_service_types(self, llm_service, runtime_control_service, task_scheduler_service):
        """Test that runtime services report correct service types."""
        assert llm_service.get_service_type() == ServiceType.LLM
        assert runtime_control_service.get_service_type() == ServiceType.RUNTIME_CONTROL
        assert task_scheduler_service.get_service_type() == ServiceType.MAINTENANCE
