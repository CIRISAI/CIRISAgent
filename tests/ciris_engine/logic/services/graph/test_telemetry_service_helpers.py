"""Tests for TelemetryService helper methods added in v1.4.5."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService, TelemetryAggregator
from ciris_engine.schemas.services.core.runtime import AdapterStatus
from ciris_engine.schemas.services.graph.telemetry import (
    AggregatedTelemetryMetadata,
    AggregatedTelemetryResponse,
    ServiceTelemetryData,
)


@pytest.fixture
def telemetry_aggregator():
    """Create a telemetry aggregator with mock dependencies."""
    service_registry = Mock()
    time_service = Mock()
    time_service.now.return_value = datetime.now(timezone.utc)
    runtime = Mock()

    aggregator = TelemetryAggregator(service_registry=service_registry, time_service=time_service, runtime=runtime)
    return aggregator


@pytest.fixture
def mock_aggregator():
    """Create a mock telemetry aggregator."""
    aggregator = Mock()
    aggregator.cache = {}
    aggregator.cache_ttl = timedelta(seconds=30)
    return aggregator


class TestTelemetryHelperMethods:
    """Test the new helper methods added for cognitive complexity reduction."""

    @pytest.mark.asyncio
    async def test_get_control_service_from_runtime(self, telemetry_aggregator):
        """Test _get_control_service when runtime has runtime_control_service."""
        mock_control = Mock()
        telemetry_aggregator.runtime.runtime_control_service = mock_control

        result = await telemetry_aggregator._get_control_service()
        assert result == mock_control

    @pytest.mark.asyncio
    async def test_get_control_service_from_registry(self, telemetry_aggregator):
        """Test _get_control_service when using service registry."""
        telemetry_aggregator.runtime = Mock(spec=[])  # No runtime_control_service
        mock_control = Mock()
        telemetry_aggregator.service_registry.get_service = AsyncMock(return_value=mock_control)

        result = await telemetry_aggregator._get_control_service()
        assert result == mock_control

    @pytest.mark.asyncio
    async def test_get_control_service_none(self, telemetry_aggregator):
        """Test _get_control_service when no service available."""
        telemetry_aggregator.runtime = None
        telemetry_aggregator.service_registry = None

        result = await telemetry_aggregator._get_control_service()
        assert result is None

    def test_is_adapter_running_with_is_running(self, telemetry_aggregator):
        """Test _is_adapter_running with is_running attribute."""
        adapter_info = Mock()
        adapter_info.is_running = True

        result = telemetry_aggregator._is_adapter_running(adapter_info)
        assert result is True

        adapter_info.is_running = False
        result = telemetry_aggregator._is_adapter_running(adapter_info)
        assert result is False

    def test_is_adapter_running_with_status(self, telemetry_aggregator):
        """Test _is_adapter_running with status attribute."""
        adapter_info = Mock(spec=[])  # No is_running
        adapter_info.status = AdapterStatus.ACTIVE

        result = telemetry_aggregator._is_adapter_running(adapter_info)
        assert result is True

        adapter_info.status = AdapterStatus.RUNNING
        result = telemetry_aggregator._is_adapter_running(adapter_info)
        assert result is True

        adapter_info.status = Mock()  # Some other status
        result = telemetry_aggregator._is_adapter_running(adapter_info)
        assert result is False

    def test_is_adapter_running_no_attributes(self, telemetry_aggregator):
        """Test _is_adapter_running with no relevant attributes."""
        adapter_info = Mock(spec=[])
        result = telemetry_aggregator._is_adapter_running(adapter_info)
        assert result is False

    def test_find_adapter_instance(self, telemetry_aggregator):
        """Test _find_adapter_instance finding matching adapter."""
        mock_adapter = Mock()
        mock_adapter.__class__.__name__ = "ApiAdapter"

        telemetry_aggregator.runtime.adapters = [mock_adapter]

        result = telemetry_aggregator._find_adapter_instance("api")
        assert result == mock_adapter

    def test_find_adapter_instance_no_match(self, telemetry_aggregator):
        """Test _find_adapter_instance with no matching adapter."""
        mock_adapter = Mock()
        mock_adapter.__class__.__name__ = "DiscordAdapter"

        telemetry_aggregator.runtime.adapters = [mock_adapter]

        result = telemetry_aggregator._find_adapter_instance("api")
        assert result is None

    def test_find_adapter_instance_no_runtime(self, telemetry_aggregator):
        """Test _find_adapter_instance with no runtime."""
        telemetry_aggregator.runtime = None
        result = telemetry_aggregator._find_adapter_instance("api")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_adapter_metrics_async(self, telemetry_aggregator):
        """Test _get_adapter_metrics with async get_metrics."""
        mock_adapter = Mock()
        mock_metrics = {"uptime_seconds": 100, "error_count": 0}
        mock_adapter.get_metrics = AsyncMock(return_value=mock_metrics)

        result = await telemetry_aggregator._get_adapter_metrics(mock_adapter)
        assert result == mock_metrics

    @pytest.mark.asyncio
    async def test_get_adapter_metrics_sync(self, telemetry_aggregator):
        """Test _get_adapter_metrics with sync get_metrics."""
        mock_adapter = Mock()
        mock_metrics = {"uptime_seconds": 200, "error_count": 1}
        mock_adapter.get_metrics = Mock(return_value=mock_metrics)

        result = await telemetry_aggregator._get_adapter_metrics(mock_adapter)
        assert result == mock_metrics

    @pytest.mark.asyncio
    async def test_get_adapter_metrics_no_method(self, telemetry_aggregator):
        """Test _get_adapter_metrics with no get_metrics method."""
        mock_adapter = Mock(spec=[])
        result = await telemetry_aggregator._get_adapter_metrics(mock_adapter)
        assert result is None

    def test_create_telemetry_data_with_metrics(self, telemetry_aggregator):
        """Test _create_telemetry_data with valid metrics."""
        metrics = {
            "uptime_seconds": 123.4,
            "error_count": 5,
            "request_count": 100,
            "error_rate": 0.05,
            "memory_mb": 256.7,
            "custom_metrics": {"extra": "data"},
        }

        result = telemetry_aggregator._create_telemetry_data(metrics, adapter_id="test_adapter", healthy=True)

        assert isinstance(result, ServiceTelemetryData)
        assert result.healthy is True
        assert result.uptime_seconds == 123.4
        assert result.error_count == 5
        assert result.requests_handled == 100
        assert result.error_rate == 0.05
        assert result.memory_mb == 256.7
        assert result.custom_metrics["adapter_id"] == "test_adapter"
        assert result.custom_metrics["extra"] == "data"

    def test_create_telemetry_data_no_metrics(self, telemetry_aggregator):
        """Test _create_telemetry_data with no metrics."""
        result = telemetry_aggregator._create_telemetry_data(None, adapter_id="empty_adapter")

        assert isinstance(result, ServiceTelemetryData)
        assert result.healthy is False
        assert result.uptime_seconds == 0.0
        assert result.error_count == 0
        assert result.custom_metrics == {"adapter_id": "empty_adapter"}

    def test_create_telemetry_data_with_adapter_info(self, telemetry_aggregator):
        """Test _create_telemetry_data with adapter_info."""
        metrics = {"uptime_seconds": 50}
        adapter_info = Mock()
        adapter_info.adapter_type = "api"
        adapter_info.started_at = datetime.now(timezone.utc)

        result = telemetry_aggregator._create_telemetry_data(metrics, adapter_info=adapter_info, adapter_id="api_123")

        assert result.custom_metrics["adapter_id"] == "api_123"
        assert result.custom_metrics["adapter_type"] == "api"
        assert "start_time" in result.custom_metrics

    def test_extract_metric_value_from_telemetry_data(self, telemetry_aggregator):
        """Test _extract_metric_value from ServiceTelemetryData."""
        telemetry_data = ServiceTelemetryData(
            healthy=True,
            uptime_seconds=100,
            error_count=0,
            requests_handled=50,
            error_rate=0.0,
            custom_metrics={"test_metric": 42},
        )

        result = telemetry_aggregator._extract_metric_value(telemetry_data, "test_metric")
        assert result == 42

        result = telemetry_aggregator._extract_metric_value(telemetry_data, "missing", "default")
        assert result == "default"

    def test_extract_metric_value_from_dict(self, telemetry_aggregator):
        """Test _extract_metric_value from dict."""
        metrics_dict = {"test_metric": 99, "another": "value"}

        result = telemetry_aggregator._extract_metric_value(metrics_dict, "test_metric")
        assert result == 99

        result = telemetry_aggregator._extract_metric_value(metrics_dict, "missing", 0)
        assert result == 0

    def test_extract_governance_metrics(self, telemetry_aggregator):
        """Test _extract_governance_metrics."""
        telemetry = {
            "governance": {
                "wise_authority": ServiceTelemetryData(
                    healthy=True,
                    uptime_seconds=1000,
                    error_count=0,
                    requests_handled=10,
                    error_rate=0.0,
                    custom_metrics={"deferral_count": 3, "guidance_requests": 10},
                )
            }
        }

        result = telemetry_aggregator._extract_governance_metrics(
            telemetry,
            "wise_authority",
            {"wise_authority_deferrals": "deferral_count", "ethical_decisions": "guidance_requests"},
        )

        assert result["wise_authority_deferrals"] == 3
        assert result["ethical_decisions"] == 10

    def test_extract_governance_metrics_no_service(self, telemetry_aggregator):
        """Test _extract_governance_metrics when service not present."""
        telemetry = {"governance": {}}

        result = telemetry_aggregator._extract_governance_metrics(
            telemetry, "missing_service", {"some_metric": "metric_name"}
        )

        assert result == {}
