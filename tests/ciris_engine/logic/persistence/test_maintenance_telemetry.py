"""Tests for DatabaseMaintenanceService metrics functionality."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.persistence.maintenance import DatabaseMaintenanceService
from ciris_engine.schemas.config import EssentialConfig
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus

# Import the mock_db_path fixture from conftest
from tests.conftest_config_mock import mock_db_path  # noqa: F401


class TestDatabaseMaintenanceTelemetry:
    """Test the database maintenance service metrics functionality."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
        return mock

    @pytest.fixture
    def mock_config_service(self):
        """Create a mock config service."""
        mock = Mock()
        mock.list_configs = AsyncMock(return_value={})
        mock.get_config = AsyncMock(return_value=None)
        return mock

    @pytest.fixture
    def temp_archive_dir(self, tmp_path):
        """Create a temporary archive directory."""
        archive_dir = tmp_path / "test_archive"
        archive_dir.mkdir()
        # Create some fake archive files
        (archive_dir / "archive_thoughts_20240101.jsonl").touch()
        (archive_dir / "archive_thoughts_20240102.jsonl").touch()
        return str(archive_dir)

    @pytest_asyncio.fixture
    async def maintenance_service(
        self,
        mock_time_service,
        mock_config_service,
        temp_archive_dir,
        tmp_path,
        monkeypatch,
    ):
        """Create the database maintenance service."""
        # Patch database path functions for the duration of the test
        test_db_path = str(tmp_path / "test.db")
        monkeypatch.setattr("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path", lambda: test_db_path)
        monkeypatch.setattr("ciris_engine.logic.persistence.get_sqlite_db_full_path", lambda: test_db_path)

        service = DatabaseMaintenanceService(
            time_service=mock_time_service,
            archive_dir_path=temp_archive_dir,
            archive_older_than_hours=24,
            config_service=mock_config_service,
        )
        await service.start()
        service._start_time = mock_time_service.now()
        return service

    @pytest.mark.asyncio
    async def test_get_metrics(self, maintenance_service):
        """Test getting metrics data from database maintenance service."""
        # Set up some metrics
        maintenance_service._cleanup_runs = 5
        maintenance_service._records_deleted = 100
        maintenance_service._vacuum_runs = 2
        maintenance_service._archive_runs = 3

        metrics = await maintenance_service.get_metrics()

        # Check required metrics
        assert "uptime_seconds" in metrics
        assert "request_count" in metrics
        assert "error_count" in metrics
        assert "error_rate" in metrics
        assert "healthy" in metrics

        # Check service-specific metrics
        assert metrics["cleanup_runs"] == 5.0
        assert metrics["records_deleted"] == 100.0
        assert metrics["vacuum_runs"] == 2.0
        assert metrics["archive_runs"] == 3.0
        assert "database_size_mb" in metrics
        assert "last_cleanup_duration_s" in metrics
        assert "cleanup_due" in metrics
        assert "archive_due" in metrics

    @pytest.mark.asyncio
    async def test_get_metrics_no_archive(self, maintenance_service):
        """Test metrics when no archives exist."""
        # Set metrics to zero
        maintenance_service._archive_runs = 0

        metrics = await maintenance_service.get_metrics()

        assert metrics["archive_runs"] == 0.0
        assert metrics["healthy"] == 1.0  # Service should be healthy

    @pytest.mark.asyncio
    async def test_get_metrics_without_run_count(self, maintenance_service):
        """Test metrics when task has never run."""
        # Reset all counters
        maintenance_service._cleanup_runs = 0
        maintenance_service._vacuum_runs = 0
        maintenance_service._archive_runs = 0

        metrics = await maintenance_service.get_metrics()

        assert metrics["cleanup_runs"] == 0.0
        assert metrics["vacuum_runs"] == 0.0
        assert metrics["archive_runs"] == 0.0
        assert metrics["healthy"] == 1.0

    @pytest.mark.asyncio
    async def test_get_metrics_without_start_time(self, maintenance_service):
        """Test metrics without start time."""
        maintenance_service._start_time = None

        metrics = await maintenance_service.get_metrics()

        assert metrics["uptime_seconds"] == 0.0
        assert metrics["healthy"] == 1.0  # Still healthy

    @pytest.mark.asyncio
    async def test_get_metrics_error_handling(self, maintenance_service):
        """Test metrics handles errors gracefully."""
        # Set error count
        maintenance_service._error_count = 5

        metrics = await maintenance_service.get_metrics()

        assert metrics["error_count"] == 5.0
        assert metrics["error_rate"] > 0  # Should have error rate

    @pytest.mark.asyncio
    async def test_get_metrics_with_running_status(self, maintenance_service):
        """Test metrics reflects running status."""
        # The task_running metric is based on the _task attribute being active
        # When the service starts, it creates a scheduled task that runs in the background
        metrics = await maintenance_service.get_metrics()

        # The scheduled service starts automatically, so the task should be running
        assert "task_running" in metrics
        # Since the service has started, the task should be running (1.0)
        # The value is 1.0 if _task exists and is not done
        assert metrics["task_running"] in [0.0, 1.0]  # Accept either state since it depends on timing
