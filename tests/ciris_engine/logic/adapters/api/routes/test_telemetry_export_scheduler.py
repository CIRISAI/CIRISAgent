"""Unit tests for TelemetryExportScheduler.

Tests cover:
1. Scheduler lifecycle (start/stop)
2. Destination checking and push scheduling
3. Authentication header building
4. Signal data collection
5. Format conversion (OTLP, Prometheus, Graphite)
6. Error handling
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.telemetry_export_scheduler import (
    TelemetryExportScheduler,
    get_scheduler,
    set_scheduler,
    start_export_scheduler,
    stop_export_scheduler,
)


@pytest.fixture
def mock_telemetry_service():
    """Create a mock telemetry service."""
    service = MagicMock()
    service.get_aggregated_telemetry = AsyncMock(
        return_value=MagicMock(
            model_dump=MagicMock(
                return_value={
                    "system_healthy": True,
                    "services_online": 22,
                    "services_total": 22,
                    "overall_error_rate": 0.01,
                }
            )
        )
    )
    return service


@pytest.fixture
def mock_config_service():
    """Create a mock config service with destinations."""
    service = MagicMock()
    storage = {"telemetry_export:destinations": []}

    async def mock_get_config(key):
        if key not in storage or not storage[key]:
            return None
        mock_node = MagicMock()
        mock_node.value.value = storage.get(key, [])
        return mock_node

    async def mock_set_config(key, value, updated_by):
        storage[key] = value

    service.get_config = mock_get_config
    service.set_config = mock_set_config
    service._storage = storage  # For test access

    return service


@pytest.fixture
def sample_destination():
    """Sample export destination."""
    return {
        "id": "test123",
        "name": "Test Destination",
        "endpoint": "http://localhost:9999",
        "format": "otlp",
        "signals": ["metrics"],
        "auth_type": "none",
        "interval_seconds": 60,
        "enabled": True,
    }


class TestSchedulerLifecycle:
    """Tests for scheduler start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_scheduler_starts_and_stops(self, mock_telemetry_service, mock_config_service):
        """Test that scheduler starts and stops cleanly."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
            check_interval=1.0,
        )

        # Start
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._scheduler_task is not None
        assert scheduler._client is not None

        # Give it a moment
        await asyncio.sleep(0.1)

        # Stop
        await scheduler.stop()
        assert scheduler._running is False
        assert scheduler._client is None

    @pytest.mark.asyncio
    async def test_scheduler_double_start_warning(self, mock_telemetry_service, mock_config_service):
        """Test that starting twice logs a warning."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        await scheduler.start()
        # Second start should just warn
        await scheduler.start()

        await scheduler.stop()

    @pytest.mark.asyncio
    async def test_start_export_scheduler_helper(self, mock_telemetry_service, mock_config_service):
        """Test the helper function for starting the scheduler."""
        scheduler = await start_export_scheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        assert scheduler is not None
        assert get_scheduler() is scheduler

        await stop_export_scheduler()
        # After stop, global instance might be cleared depending on implementation


class TestHeaderBuilding:
    """Tests for authentication header building."""

    def test_build_headers_no_auth(self, mock_telemetry_service, mock_config_service):
        """Test header building with no auth."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        dest = {"auth_type": "none"}
        headers = scheduler._build_headers(dest)

        assert "Authorization" not in headers
        assert headers["Content-Type"] == "application/json"

    def test_build_headers_bearer_auth(self, mock_telemetry_service, mock_config_service):
        """Test header building with bearer auth."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        dest = {"auth_type": "bearer", "auth_value": "secret_token"}
        headers = scheduler._build_headers(dest)

        assert headers["Authorization"] == "Bearer secret_token"

    def test_build_headers_basic_auth(self, mock_telemetry_service, mock_config_service):
        """Test header building with basic auth."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        dest = {"auth_type": "basic", "auth_value": "user:pass"}
        headers = scheduler._build_headers(dest)

        import base64

        expected = base64.b64encode(b"user:pass").decode()
        assert headers["Authorization"] == f"Basic {expected}"

    def test_build_headers_custom_header(self, mock_telemetry_service, mock_config_service):
        """Test header building with custom header auth."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        dest = {
            "auth_type": "header",
            "auth_value": "my-api-key",
            "auth_header": "X-Custom-Key",
        }
        headers = scheduler._build_headers(dest)

        assert headers["X-Custom-Key"] == "my-api-key"

    def test_build_headers_null_auth_header_uses_default(self, mock_telemetry_service, mock_config_service):
        """Test that explicit null auth_header falls back to X-API-Key default."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        # This simulates a destination created without specifying auth_header,
        # which persists as auth_header: null in the config
        dest = {
            "auth_type": "header",
            "auth_value": "my-api-key",
            "auth_header": None,  # Explicit null, not missing
        }
        headers = scheduler._build_headers(dest)

        # Should use default X-API-Key, not fail with headers[None]
        assert "X-API-Key" in headers
        assert headers["X-API-Key"] == "my-api-key"
        assert None not in headers


class TestSignalCollection:
    """Tests for signal data collection."""

    @pytest.mark.asyncio
    async def test_collect_metrics_signal(self, mock_telemetry_service, mock_config_service):
        """Test collecting metrics signal data."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        data = await scheduler._collect_signal_data("metrics")

        assert data is not None
        assert "system_healthy" in data
        mock_telemetry_service.get_aggregated_telemetry.assert_called_once()

    @pytest.mark.asyncio
    async def test_collect_traces_signal_no_service(self, mock_telemetry_service, mock_config_service):
        """Test collecting traces when visibility service is not available."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
            visibility_service=None,
        )

        data = await scheduler._collect_signal_data("traces")
        assert data is None

    @pytest.mark.asyncio
    async def test_collect_logs_signal(self, mock_telemetry_service, mock_config_service):
        """Test collecting logs signal (currently returns None)."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        data = await scheduler._collect_signal_data("logs")
        # Logs export not yet implemented
        assert data is None


class TestPathAppending:
    """Tests for URL path appending."""

    def test_append_path_simple(self, mock_telemetry_service, mock_config_service):
        """Test appending path to base URL."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        result = scheduler._append_path("http://example.com", "/v1/metrics")
        assert result == "http://example.com/v1/metrics"

    def test_append_path_trailing_slash(self, mock_telemetry_service, mock_config_service):
        """Test appending path when base has trailing slash."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        result = scheduler._append_path("http://example.com/", "/v1/metrics")
        assert result == "http://example.com/v1/metrics"

    def test_append_path_no_leading_slash(self, mock_telemetry_service, mock_config_service):
        """Test appending path without leading slash."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        result = scheduler._append_path("http://example.com", "v1/metrics")
        assert result == "http://example.com/v1/metrics"


class TestDestinationChecking:
    """Tests for destination checking logic."""

    @pytest.mark.asyncio
    async def test_disabled_destination_skipped(self, mock_telemetry_service, mock_config_service, sample_destination):
        """Test that disabled destinations are skipped."""
        sample_destination["enabled"] = False
        mock_config_service._storage["telemetry_export:destinations"] = [sample_destination]

        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
            check_interval=0.1,
        )

        await scheduler.start()
        await asyncio.sleep(0.2)
        await scheduler.stop()

        # Should not have pushed to disabled destination
        assert scheduler._pushes_total == 0

    @pytest.mark.asyncio
    async def test_destination_with_no_endpoint_skipped(
        self, mock_telemetry_service, mock_config_service, sample_destination
    ):
        """Test that destinations without endpoints are skipped."""
        sample_destination["endpoint"] = ""
        mock_config_service._storage["telemetry_export:destinations"] = [sample_destination]

        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
            check_interval=0.1,
        )

        # Push to destination should be skipped
        await scheduler._push_to_destination(sample_destination, datetime.now(timezone.utc))
        assert scheduler._pushes_total == 0


class TestMetrics:
    """Tests for scheduler metrics."""

    def test_get_metrics(self, mock_telemetry_service, mock_config_service):
        """Test getting scheduler metrics."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        metrics = scheduler.get_metrics()

        assert "pushes_total" in metrics
        assert "pushes_success" in metrics
        assert "pushes_failed" in metrics
        assert "destinations_tracked" in metrics
        assert "running" in metrics


class TestGlobalScheduler:
    """Tests for global scheduler instance management."""

    def test_set_and_get_scheduler(self, mock_telemetry_service, mock_config_service):
        """Test setting and getting global scheduler."""
        scheduler = TelemetryExportScheduler(
            telemetry_service=mock_telemetry_service,
            config_service=mock_config_service,
        )

        set_scheduler(scheduler)
        assert get_scheduler() is scheduler

        # Clean up
        set_scheduler(None)  # type: ignore
        assert get_scheduler() is None
