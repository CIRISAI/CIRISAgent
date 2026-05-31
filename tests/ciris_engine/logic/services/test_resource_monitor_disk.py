"""Tests for the AgentMode disk gating methods on ResourceMonitorService.

Covers ``get_available_disk_bytes`` + ``is_server_mode_eligible``.
"""

from __future__ import annotations

import os
import tempfile
from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.constants import SERVER_MINIMUM_DISK_BYTES
from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceMonitorService, ResourceSignalBus
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.resources_core import ResourceBudget

# Minimal fake of shutil.disk_usage's return type.
_Usage = namedtuple("_Usage", ["total", "used", "free"])


@pytest.fixture
def time_service() -> TimeService:
    return TimeService()


@pytest.fixture
def temp_db() -> str:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def resource_monitor(time_service: TimeService, temp_db: str) -> ResourceMonitorService:
    return ResourceMonitorService(
        budget=ResourceBudget(),
        db_path=temp_db,
        time_service=time_service,
        signal_bus=ResourceSignalBus(),
    )


class TestGetAvailableDiskBytes:
    def test_returns_int_for_real_path(self, resource_monitor: ResourceMonitorService) -> None:
        # Default behaviour: route through path resolution. The host CI
        # may have arbitrary disk free; we only assert it's a non-negative
        # int and not raising.
        result = resource_monitor.get_available_disk_bytes()
        assert isinstance(result, int)
        assert result >= 0

    def test_explicit_path_argument(self, resource_monitor: ResourceMonitorService) -> None:
        result = resource_monitor.get_available_disk_bytes(Path("/"))
        assert isinstance(result, int)
        assert result >= 0

    def test_mocked_disk_usage_returns_exact_value(self, resource_monitor: ResourceMonitorService) -> None:
        fake = _Usage(total=10_000, used=5_000, free=4_321)
        with patch(
            "ciris_engine.logic.services.infrastructure.resource_monitor.service.shutil.disk_usage",
            return_value=fake,
        ):
            assert resource_monitor.get_available_disk_bytes(Path("/")) == 4_321

    def test_oserror_returns_zero(self, resource_monitor: ResourceMonitorService) -> None:
        with patch(
            "ciris_engine.logic.services.infrastructure.resource_monitor.service.shutil.disk_usage",
            side_effect=OSError("nope"),
        ):
            assert resource_monitor.get_available_disk_bytes(Path("/nonexistent")) == 0

    def test_value_error_returns_zero(self, resource_monitor: ResourceMonitorService) -> None:
        with patch(
            "ciris_engine.logic.services.infrastructure.resource_monitor.service.shutil.disk_usage",
            side_effect=ValueError("bad path"),
        ):
            assert resource_monitor.get_available_disk_bytes(Path("/x")) == 0

    def test_postgres_db_path_falls_back_to_data_dir(self, time_service: TimeService) -> None:
        """When db_path is a Postgres URL and path resolution fails, we get 0
        (the documented silent-zero contract). When path resolution succeeds,
        we measure the data dir, not the URL."""
        monitor = ResourceMonitorService(
            budget=ResourceBudget(),
            db_path="postgresql://localhost/ciris",
            time_service=time_service,
            signal_bus=ResourceSignalBus(),
        )
        # With path_resolution working, the call should not raise and should
        # return a non-negative int (measured against the resolved data dir).
        result = monitor.get_available_disk_bytes()
        assert isinstance(result, int)
        assert result >= 0


class TestIsServerModeEligible:
    def test_eligible_when_disk_above_threshold(self, resource_monitor: ResourceMonitorService) -> None:
        fake = _Usage(
            total=SERVER_MINIMUM_DISK_BYTES * 2,
            used=0,
            free=SERVER_MINIMUM_DISK_BYTES + 1,
        )
        with patch(
            "ciris_engine.logic.services.infrastructure.resource_monitor.service.shutil.disk_usage",
            return_value=fake,
        ):
            assert resource_monitor.is_server_mode_eligible(Path("/")) is True

    def test_not_eligible_at_threshold_minus_one(self, resource_monitor: ResourceMonitorService) -> None:
        fake = _Usage(
            total=SERVER_MINIMUM_DISK_BYTES,
            used=1,
            free=SERVER_MINIMUM_DISK_BYTES - 1,
        )
        with patch(
            "ciris_engine.logic.services.infrastructure.resource_monitor.service.shutil.disk_usage",
            return_value=fake,
        ):
            assert resource_monitor.is_server_mode_eligible(Path("/")) is False

    def test_eligible_exactly_at_threshold(self, resource_monitor: ResourceMonitorService) -> None:
        # ">=" is the contract: an exact match qualifies.
        fake = _Usage(
            total=SERVER_MINIMUM_DISK_BYTES,
            used=0,
            free=SERVER_MINIMUM_DISK_BYTES,
        )
        with patch(
            "ciris_engine.logic.services.infrastructure.resource_monitor.service.shutil.disk_usage",
            return_value=fake,
        ):
            assert resource_monitor.is_server_mode_eligible(Path("/")) is True

    def test_oserror_means_not_eligible(self, resource_monitor: ResourceMonitorService) -> None:
        with patch(
            "ciris_engine.logic.services.infrastructure.resource_monitor.service.shutil.disk_usage",
            side_effect=OSError("nope"),
        ):
            assert resource_monitor.is_server_mode_eligible(Path("/x")) is False
