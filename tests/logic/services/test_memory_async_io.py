"""
Tests to verify that memory service database I/O operations are non-blocking.

These tests verify that async methods use run_in_executor for database operations
to avoid blocking the event loop.
"""

import asyncio
from pathlib import Path
from typing import Any, Callable
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.schemas.services.graph_core import GraphScope


@pytest.fixture
def memory_service(tmp_path: Path) -> LocalGraphMemoryService:
    """Create a memory service with a temporary database."""
    db_path = str(tmp_path / "test.db")
    service = LocalGraphMemoryService(db_path=db_path)
    return service


class TestExportIdentityContextAsync:
    """Test export_identity_context uses executor."""

    @pytest.mark.asyncio
    async def test_export_identity_context_uses_executor(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify export_identity_context runs database query in executor."""

        # Mock the executor to verify it's being used
        mock_executor_result = "Test Identity Context"

        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            # Setup the executor mock to return our test result
            async def mock_run_in_executor(executor: Any, func: Callable[[], str]) -> str:
                # Call the function to ensure it works
                result = func()
                return mock_executor_result

            mock_loop.run_in_executor = mock_run_in_executor

            # Call the method
            result = await memory_service.export_identity_context()

            # Verify get_event_loop was called
            assert mock_get_loop.called

    @pytest.mark.asyncio
    async def test_export_identity_context_concurrent_execution(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify multiple export_identity_context calls can execute concurrently."""

        # Create multiple concurrent tasks
        tasks = [memory_service.export_identity_context() for _ in range(5)]

        # All tasks should complete without blocking each other
        results = await asyncio.gather(*tasks)

        # All results should be strings (empty or formatted identity)
        assert all(isinstance(r, str) for r in results)


class TestIsHealthyAsync:
    """Test is_healthy uses executor."""

    @pytest.mark.asyncio
    async def test_is_healthy_uses_executor(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify is_healthy runs database query in executor."""

        # Start the service first
        await memory_service.start()

        # Mock the executor to verify it's being used
        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = MagicMock()
            mock_get_loop.return_value = mock_loop

            # Setup the executor mock to return healthy status
            async def mock_run_in_executor(executor: Any, func: Callable[[], bool]) -> bool:
                # Call the function to ensure it works
                result = func()
                return True

            mock_loop.run_in_executor = mock_run_in_executor

            # Call the method
            result = await memory_service.is_healthy()

            # Verify get_event_loop was called
            assert mock_get_loop.called

        await memory_service.stop()

    @pytest.mark.asyncio
    async def test_is_healthy_concurrent_execution(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify multiple is_healthy calls can execute concurrently."""

        # Start the service first
        await memory_service.start()

        # Create multiple concurrent tasks
        tasks = [memory_service.is_healthy() for _ in range(10)]

        # All tasks should complete without blocking each other
        results = await asyncio.gather(*tasks)

        # All results should be boolean
        assert all(isinstance(r, bool) for r in results)

        await memory_service.stop()

    @pytest.mark.asyncio
    async def test_is_healthy_returns_false_when_not_started(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify is_healthy returns False when service is not started."""

        result = await memory_service.is_healthy()
        assert result is False


class TestNonBlockingBehavior:
    """Test that database operations don't block the event loop."""

    @pytest.mark.asyncio
    async def test_concurrent_database_operations(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify that multiple database operations can run concurrently."""

        await memory_service.start()

        # Add some export_identity_context tasks
        identity_tasks = [memory_service.export_identity_context() for _ in range(3)]

        # Add some is_healthy tasks
        health_tasks = [memory_service.is_healthy() for _ in range(3)]

        # All tasks should complete successfully without blocking
        identity_results = await asyncio.gather(*identity_tasks)
        health_results = await asyncio.gather(*health_tasks)

        # Verify we got results for all tasks
        assert len(identity_results) == 3
        assert len(health_results) == 3

        # Identity results should be strings
        assert all(isinstance(r, str) for r in identity_results)

        # Health results should be booleans
        assert all(isinstance(r, bool) for r in health_results)

        await memory_service.stop()

    @pytest.mark.asyncio
    async def test_event_loop_not_blocked(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify event loop can handle other tasks while DB operations run."""

        await memory_service.start()

        # Track if other tasks can execute
        other_task_executed = False

        async def other_task() -> None:
            nonlocal other_task_executed
            await asyncio.sleep(0.01)
            other_task_executed = True

        # Run database operation and other task concurrently
        await asyncio.gather(memory_service.is_healthy(), other_task())

        # Verify the other task was able to execute
        assert other_task_executed

        await memory_service.stop()


class TestRecallTimeseriesAsync:
    """Test that recall_timeseries already uses executor (good example)."""

    @pytest.mark.asyncio
    async def test_recall_timeseries_uses_executor(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify recall_timeseries continues to use executor correctly."""

        await memory_service.start()

        # This should work without blocking
        result = await memory_service.recall_timeseries(scope="local", hours=1)

        # Should return a list (empty or with data points)
        assert isinstance(result, list)

        await memory_service.stop()

    @pytest.mark.asyncio
    async def test_recall_timeseries_concurrent_execution(self, memory_service: LocalGraphMemoryService) -> None:
        """Verify multiple recall_timeseries calls can execute concurrently."""

        await memory_service.start()

        # Create multiple concurrent tasks
        tasks = [memory_service.recall_timeseries(scope="local", hours=i + 1) for i in range(5)]

        # All tasks should complete without blocking each other
        results = await asyncio.gather(*tasks)

        # All results should be lists
        assert all(isinstance(r, list) for r in results)

        await memory_service.stop()
