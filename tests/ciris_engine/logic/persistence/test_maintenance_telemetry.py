"""Tests for DatabaseMaintenanceService telemetry functionality."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.persistence.maintenance import DatabaseMaintenanceService
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus


class TestDatabaseMaintenanceTelemetry:
    """Test the database maintenance service telemetry functionality."""

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
    async def maintenance_service(self, mock_time_service, mock_config_service, temp_archive_dir):
        """Create the database maintenance service."""
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
    async def test_get_telemetry(self, maintenance_service):
        """Test getting telemetry data from database maintenance service."""
        # Set up some metrics
        maintenance_service._run_count = 5

        telemetry = await maintenance_service.get_telemetry()

        # Check required fields
        assert telemetry["service_name"] == "database_maintenance"
        assert telemetry["healthy"] is True
        assert telemetry["error_count"] == 0
        assert telemetry["task_run_count"] == 5
        assert telemetry["uptime_seconds"] >= 0
        assert telemetry["archive_count"] == 2  # From temp_archive_dir
        assert telemetry["archive_older_than_hours"] == 24
        assert telemetry["maintenance_interval_seconds"] == 3600
        assert "last_updated" in telemetry
        assert "archive_dir" in telemetry

    @pytest.mark.asyncio
    async def test_get_telemetry_no_archive(self, maintenance_service):
        """Test telemetry when no archives exist."""
        # Clear archive directory
        archive_dir = Path(maintenance_service.archive_dir)
        for file in archive_dir.glob("*.jsonl"):
            file.unlink()

        telemetry = await maintenance_service.get_telemetry()

        assert telemetry["archive_count"] == 0
        assert telemetry["healthy"] is True

    @pytest.mark.asyncio
    async def test_get_telemetry_without_run_count(self, maintenance_service):
        """Test telemetry when run_count attribute doesn't exist."""
        # Remove _run_count attribute if it exists
        if hasattr(maintenance_service, "_run_count"):
            delattr(maintenance_service, "_run_count")

        telemetry = await maintenance_service.get_telemetry()

        assert telemetry["task_run_count"] == 0
        assert telemetry["healthy"] is True

    @pytest.mark.asyncio
    async def test_get_telemetry_without_start_time(self, maintenance_service):
        """Test telemetry when start_time doesn't exist."""
        maintenance_service._start_time = None

        telemetry = await maintenance_service.get_telemetry()

        assert telemetry["uptime_seconds"] == 0
        assert telemetry["healthy"] is True

    @pytest.mark.asyncio
    async def test_get_telemetry_error_handling(self, maintenance_service):
        """Test telemetry handles errors gracefully."""
        # Mock archive_dir.exists() to raise an exception
        with patch.object(Path, "exists", side_effect=Exception("Filesystem error")):
            telemetry = await maintenance_service.get_telemetry()

        assert telemetry["service_name"] == "database_maintenance"
        assert telemetry["healthy"] is False
        assert telemetry["error"] == "Filesystem error"
        assert telemetry["error_count"] == 1
        assert telemetry["task_run_count"] == 0
        assert telemetry["uptime_seconds"] == 0

    @pytest.mark.asyncio
    async def test_get_telemetry_with_running_status(self, maintenance_service):
        """Test telemetry reflects running status."""
        maintenance_service.is_running = True

        telemetry = await maintenance_service.get_telemetry()

        assert telemetry["healthy"] is True

        maintenance_service.is_running = False

        telemetry = await maintenance_service.get_telemetry()

        # Should still show as healthy even when not running (stopped gracefully)
        assert telemetry["healthy"] is False
