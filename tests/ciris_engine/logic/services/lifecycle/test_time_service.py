"""Unit tests for TimeService."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus


@pytest.mark.asyncio
async def test_time_service_lifecycle():
    """Test TimeService start/stop lifecycle."""
    service = TimeService()

    # Before start
    assert service._started is False

    # Start
    await service.start()
    assert service._started is True
    assert service._start_time is not None

    # Stop
    await service.stop()
    assert service._started is False


def test_time_service_now():
    """Test TimeService.now() returns UTC datetime."""
    service = TimeService()

    now = service.now()
    assert isinstance(now, datetime)
    assert now.tzinfo == timezone.utc

    # Should be recent
    time_diff = (datetime.now(timezone.utc) - now).total_seconds()
    assert abs(time_diff) < 1.0  # Within 1 second


def test_time_service_now_iso():
    """Test TimeService.now_iso() returns ISO format string."""
    service = TimeService()

    now_iso = service.now_iso()
    assert isinstance(now_iso, str)
    assert "T" in now_iso  # ISO format separator
    assert "+00:00" in now_iso  # UTC timezone indicator

    # Should be parseable
    parsed = datetime.fromisoformat(now_iso)
    assert parsed.tzinfo == timezone.utc


def test_time_service_timestamp():
    """Test TimeService.timestamp() returns Unix timestamp."""
    service = TimeService()

    timestamp = service.timestamp()
    assert isinstance(timestamp, float)
    assert timestamp > 0

    # Should be recent
    now_timestamp = datetime.now(timezone.utc).timestamp()
    assert abs(now_timestamp - timestamp) < 1.0  # Within 1 second


def test_time_service_capabilities():
    """Test TimeService.get_capabilities() returns correct info."""
    service = TimeService()

    caps = service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "TimeService"
    assert caps.version == "1.0.0"
    assert "now" in caps.actions
    assert "now_iso" in caps.actions
    assert "timestamp" in caps.actions
    assert len(caps.dependencies) == 0
    assert caps.metadata["description"] == "Provides consistent UTC time operations"


@pytest.mark.asyncio
async def test_time_service_status():
    """Test TimeService.get_status() returns correct status."""
    service = TimeService()

    # Before start
    status = service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "TimeService"
    assert status.service_type == "time"
    assert status.is_healthy is False  # Not running yet

    # After start
    await service.start()
    await asyncio.sleep(0.1)  # Let some time pass

    # Check health to set last_health_check
    await service.is_healthy()

    status = service.get_status()
    assert status.is_healthy is True
    assert status.uptime_seconds > 0
    assert status.last_error is None
    assert status.last_health_check is not None

    # After stop
    await service.stop()
    status = service.get_status()
    assert status.is_healthy is False


def test_time_service_consistency():
    """Test that TimeService provides consistent time across calls."""
    service = TimeService()

    # Get time in different formats
    dt1 = service.now()
    iso1 = service.now_iso()
    ts1 = service.timestamp()

    # Parse ISO back to datetime
    dt_from_iso = datetime.fromisoformat(iso1)

    # Create datetime from timestamp
    dt_from_ts = datetime.fromtimestamp(ts1, tz=timezone.utc)

    # All should be within a second of each other
    assert abs((dt1 - dt_from_iso).total_seconds()) < 1.0
    assert abs((dt1 - dt_from_ts).total_seconds()) < 1.0


@pytest.mark.asyncio
async def test_time_service_mocking():
    """Test that TimeService can be mocked for testing."""
    service = TimeService()

    # Mock the datetime.now to return a fixed time
    fixed_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    with patch("ciris_engine.logic.services.lifecycle.time.service.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_time
        mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        # Test that service uses the mocked time
        now = service.now()
        assert now == fixed_time

        now_iso = service.now_iso()
        assert now_iso == "2024-01-01T12:00:00+00:00"

        timestamp = service.timestamp()
        assert timestamp == fixed_time.timestamp()
