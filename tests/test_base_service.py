"""
Tests for the BaseService class and its specialized variants.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List

import pytest

from ciris_engine.logic.services.base_graph_service import BaseGraphService
from ciris_engine.logic.services.base_infrastructure_service import BaseInfrastructureService
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus


# Mock time service for testing
class MockTimeService(TimeServiceProtocol):
    def __init__(self):
        self._current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self._start_time = self._current_time
        self._started = False

    def now(self) -> datetime:
        return self._current_time

    def now_iso(self) -> str:
        return self._current_time.isoformat()

    def timestamp(self) -> float:
        return self._current_time.timestamp()

    def get_uptime(self) -> float:
        """Get service uptime in seconds."""
        if not self._started:
            return 0.0
        return (self._current_time - self._start_time).total_seconds()

    def advance(self, seconds: float):
        """Advance time for testing."""
        from datetime import timedelta

        self._current_time += timedelta(seconds=seconds)

    async def start(self) -> None:
        self._started = True
        self._start_time = self._current_time

    async def stop(self) -> None:
        self._started = False

    async def is_healthy(self) -> bool:
        return self._started

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.TIME

    def get_capabilities(self) -> ServiceCapabilities:
        return ServiceCapabilities(
            service_name="MockTimeService",
            actions=["now", "now_iso", "timestamp", "get_uptime"],
            version="1.0.0",
            dependencies=[],
            metadata={"description": "Mock time service for base service testing"},
        )

    def get_status(self) -> ServiceStatus:
        return ServiceStatus(
            service_name="MockTimeService",
            service_type="time",
            is_healthy=self._started,
            uptime_seconds=self.get_uptime(),
            metrics={"current_time": self._current_time.timestamp(), "started": 1.0 if self._started else 0.0},
            last_error=None,
            last_health_check=self._current_time,
        )


# Mock implementation of BaseService (not a test class - renamed to avoid pytest collection)
class MockServiceForTesting(BaseService):
    def __init__(self, dependency=None, **kwargs):
        super().__init__(**kwargs)
        self.dependency = dependency
        self.started_called = False
        self.stopped_called = False

    def get_service_type(self) -> ServiceType:
        return ServiceType.LLM  # Using LLM as a test service type

    def _get_actions(self) -> List[str]:
        return ["test_action", "another_action"]

    def _check_dependencies(self) -> bool:
        return self.dependency is not None

    async def _on_start(self) -> None:
        self.started_called = True

    async def _on_stop(self) -> None:
        self.stopped_called = True

    def _collect_custom_metrics(self) -> Dict[str, float]:
        return {"custom_metric": 42.0}


class MockScheduledServiceForTesting(BaseScheduledService):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.task_run_count = 0

    def get_service_type(self) -> ServiceType:
        return ServiceType.MAINTENANCE  # Using MAINTENANCE for scheduled services

    def _get_actions(self) -> List[str]:
        return ["scheduled_task"]

    def _check_dependencies(self) -> bool:
        return True

    async def _run_scheduled_task(self) -> None:
        self.task_run_count += 1
        if self.task_run_count == 2:
            # Simulate an error on second run
            raise ValueError("Test error")


class TestBaseService:
    """Test the BaseService implementation."""

    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test service initializes with correct defaults."""
        time_service = MockTimeService()
        service = MockServiceForTesting(dependency="test", time_service=time_service, service_name="CustomName", version="2.0.0")

        assert service.service_name == "CustomName"
        assert service._version == "2.0.0"
        assert not service._started
        assert service._time_service == time_service
        assert "TimeService" in service._dependencies

    @pytest.mark.asyncio
    async def test_service_lifecycle(self):
        """Test service start/stop lifecycle."""
        service = MockServiceForTesting(dependency="test")

        # Start service
        await service.start()
        assert service._started
        assert service.started_called
        assert service._start_time is not None

        # Try starting again (should warn but not error)
        await service.start()

        # Stop service
        await service.stop()
        assert not service._started
        assert service.stopped_called

        # Try stopping again (should warn but not error)
        await service.stop()

    @pytest.mark.asyncio
    async def test_dependency_check(self):
        """Test dependency checking prevents start."""
        service = MockServiceForTesting(dependency=None)  # No dependency

        with pytest.raises(RuntimeError, match="Required dependencies not available"):
            await service.start()

        assert not service._started

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health checking."""
        service = MockServiceForTesting(dependency="test")

        # Not started = not healthy
        assert not await service.is_healthy()

        # Started = healthy
        await service.start()
        assert await service.is_healthy()

        # Stopped = not healthy
        await service.stop()
        assert not await service.is_healthy()

    @pytest.mark.asyncio
    async def test_capabilities(self):
        """Test service capabilities reporting."""
        service = MockServiceForTesting(dependency="test")
        caps = service.get_capabilities()

        assert caps.service_name == "MockServiceForTesting"
        assert caps.actions == ["test_action", "another_action"]
        assert caps.version == "1.0.0"
        assert "TimeService" not in caps.dependencies  # No time service provided

    @pytest.mark.asyncio
    async def test_status_reporting(self):
        """Test service status reporting."""
        time_service = MockTimeService()
        service = MockServiceForTesting(dependency="test", time_service=time_service)

        # Get status before start
        status = service.get_status()
        assert status.service_name == "MockServiceForTesting"
        assert status.service_type == ServiceType.LLM.value
        assert not status.is_healthy
        assert status.uptime_seconds == 0.0

        # Start and advance time
        await service.start()
        time_service.advance(10)  # 10 seconds

        # Get status after start
        status = service.get_status()
        assert status.is_healthy
        assert status.uptime_seconds == 10.0
        assert status.metrics["custom_metric"] == 42.0
        assert status.metrics["healthy"] == 1.0
        assert status.metrics["error_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_error_tracking(self):
        """Test error tracking."""
        service = MockServiceForTesting(dependency="test")
        await service.start()

        # Track some errors
        error1 = ValueError("Test error 1")
        error2 = RuntimeError("Test error 2")

        service._track_error(error1)
        service._track_error(error2)

        status = service.get_status()
        assert status.last_error == "Test error 2"
        assert status.metrics["error_count"] == 2.0
        assert status.metrics["error_rate"] == 2.0  # 2 errors, 0 requests

        # Track some requests
        service._track_request()
        service._track_request()

        status = service.get_status()
        assert status.metrics["request_count"] == 2.0
        assert status.metrics["error_rate"] == 1.0  # 2 errors, 2 requests


class TestInfrastructureService:
    """Test the BaseInfrastructureService."""

    @pytest.mark.asyncio
    async def test_infrastructure_service_type(self):
        """Test infrastructure service has correct type."""

        class MyInfraService(BaseInfrastructureService):
            def _get_actions(self) -> List[str]:
                return ["infra_action"]

            def _check_dependencies(self) -> bool:
                return True

        service = MyInfraService()
        # Infrastructure services should have specific types
        # Since this is a test infrastructure service, we'll check it has a valid type
        service_type = service.get_service_type()
        assert isinstance(service_type, ServiceType)

        # Check metadata
        caps = service.get_capabilities()
        assert caps.metadata["category"] == "infrastructure"
        assert caps.metadata["critical"] is True


class TestScheduledServiceClass:
    """Test the BaseScheduledService."""

    @pytest.mark.asyncio
    async def test_scheduled_task_execution(self):
        """Test scheduled task runs periodically."""
        service = MockScheduledServiceForTesting(run_interval_seconds=0.1)

        await service.start()

        # Wait for a few runs
        await asyncio.sleep(0.35)

        # Should have run at least 3 times
        assert service.task_run_count >= 3
        assert service._task_error_count == 1  # One error on second run

        # Check metrics
        status = service.get_status()
        assert status.metrics["task_run_count"] >= 3
        assert status.metrics["task_error_count"] == 1
        assert status.metrics["task_interval_seconds"] == 0.1
        assert status.metrics["task_running"] == 1.0

        await service.stop()

        # Task should be stopped
        status = service.get_status()
        assert status.metrics["task_running"] == 0.0


class TestGraphService:
    """Test the BaseGraphService."""

    @pytest.mark.asyncio
    async def test_graph_service_memory_bus_check(self):
        """Test graph service requires memory bus."""

        class MyGraphService(BaseGraphService):
            def get_service_type(self) -> ServiceType:
                return ServiceType.MEMORY  # Graph services typically use MEMORY type

            def _get_actions(self) -> List[str]:
                return ["store", "query"]

        # Without memory bus
        service = MyGraphService()
        assert not await service.is_healthy()

        with pytest.raises(RuntimeError, match="Required dependencies not available"):
            await service.start()

        # Check metrics show memory bus unavailable
        status = service.get_status()
        assert status.metrics["memory_bus_available"] == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
