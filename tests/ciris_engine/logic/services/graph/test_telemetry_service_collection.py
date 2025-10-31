"""
Regression tests for telemetry service collection bug fix.

Tests the critical bug where the return statement in collect_service()
was outdented outside the except block, causing all services to report
as unhealthy even when they were healthy.

Issue: Telemetry aggregator short-circuit bug
Fix: Properly indent return statement inside except block
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.services.graph.telemetry_service import TelemetryAggregator
from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData


class TestTelemetryAggregatorCollection:
    """Test TelemetryAggregator.collect_service() method to prevent regression of the short-circuit bug."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        from datetime import datetime, timezone

        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.fixture
    def mock_service_registry(self):
        """Create a mock service registry."""
        mock = Mock()
        mock.get_services_by_type.return_value = []
        mock.list_providers.return_value = {}
        mock._agent = None
        return mock

    @pytest.fixture
    def mock_runtime(self):
        """Create a mock runtime."""
        mock = Mock()
        mock.memory_service = None
        mock.service_registry = None
        return mock

    @pytest_asyncio.fixture
    async def aggregator(self, mock_service_registry, mock_time_service, mock_runtime):
        """Create a TelemetryAggregator instance."""
        return TelemetryAggregator(
            service_registry=mock_service_registry, time_service=mock_time_service, runtime=mock_runtime
        )

    @pytest.mark.asyncio
    async def test_collect_service_returns_healthy_metrics(self, aggregator):
        """
        REGRESSION TEST: Verify healthy service metrics are not overwritten.

        GIVEN a service with healthy metrics
        WHEN collect_service() is called
        THEN it returns the service's actual healthy=True metrics

        This test would have failed with the bug where the return statement
        was outdented outside the except block, causing healthy metrics to be
        overwritten with healthy=False.
        """
        # Create a mock service with healthy metrics
        mock_service = Mock()
        mock_service.__class__.__name__ = "TestService"
        mock_service.get_metrics = AsyncMock(
            return_value={
                "uptime_seconds": 120.0,
                "error_count": 0.0,
                "requests_handled": 50.0,
                "error_rate": 0.0,
            }
        )

        # Mock the internal methods
        with patch.object(aggregator, "_get_service_from_registry", return_value=mock_service):
            with patch.object(
                aggregator,
                "_try_collect_metrics",
                return_value=ServiceTelemetryData(
                    healthy=True, uptime_seconds=120.0, error_count=0, requests_handled=50, error_rate=0.0
                ),
            ):
                result = await aggregator.collect_service("test_service")

        # CRITICAL: Verify healthy=True is preserved
        assert isinstance(result, ServiceTelemetryData)
        assert result.healthy is True, "BUG: healthy=True was overwritten to False"
        assert result.uptime_seconds == 120.0
        assert result.requests_handled == 50
        assert result.error_count == 0

    @pytest.mark.asyncio
    async def test_collect_service_exception_returns_unhealthy(self, aggregator):
        """
        GIVEN a service that raises an exception during collection
        WHEN collect_service() is called
        THEN it returns healthy=False fallback metrics

        This verifies the except block correctly returns unhealthy status.
        """
        mock_service = Mock()
        mock_service.__class__.__name__ = "FailingService"
        mock_service.get_metrics = AsyncMock(side_effect=RuntimeError("Service failed"))

        with patch.object(aggregator, "_get_service_from_registry", return_value=mock_service):
            with patch.object(aggregator, "_try_collect_metrics", side_effect=RuntimeError("Collection failed")):
                result = await aggregator.collect_service("failing_service")

        # Should return unhealthy fallback
        assert isinstance(result, ServiceTelemetryData)
        assert result.healthy is False
        assert result.uptime_seconds == 0.0
        assert result.error_count == 0
        assert result.requests_handled == 0
        assert result.error_rate == 0.0

    @pytest.mark.asyncio
    async def test_collect_service_no_metrics_returns_unhealthy(self, aggregator):
        """
        GIVEN a service with no metrics available (returns None)
        WHEN collect_service() is called
        THEN it returns healthy=False fallback metrics

        This tests the fallback path when _try_collect_metrics returns None.
        """
        mock_service = Mock()
        mock_service.__class__.__name__ = "NoMetricsService"
        mock_service.get_metrics = None  # Service has no get_metrics method

        with patch.object(aggregator, "_get_service_from_registry", return_value=mock_service):
            with patch.object(aggregator, "_try_collect_metrics", return_value=None):
                result = await aggregator.collect_service("no_metrics_service")

        # Should return unhealthy fallback
        assert isinstance(result, ServiceTelemetryData)
        assert result.healthy is False
        assert result.uptime_seconds == 0.0
        assert result.error_count == 0
        assert result.requests_handled == 0
        assert result.error_rate == 0.0

    @pytest.mark.asyncio
    async def test_collect_service_multiple_services_mixed_health(self, aggregator):
        """
        GIVEN multiple services with different health statuses
        WHEN collect_service() is called for each
        THEN each returns its actual health status without cross-contamination

        This ensures the bug fix prevents healthy services from being
        incorrectly marked as unhealthy.
        """
        # Create healthy service
        healthy_service = Mock()
        healthy_service.__class__.__name__ = "HealthyService"

        # Create unhealthy service
        unhealthy_service = Mock()
        unhealthy_service.__class__.__name__ = "UnhealthyService"

        # Mock registry to return different services
        def mock_get_service(service_name):
            if service_name == "healthy_service":
                return healthy_service
            elif service_name == "unhealthy_service":
                return unhealthy_service
            return None

        # Mock metrics collection
        def mock_try_collect(service):
            if service == healthy_service:
                return ServiceTelemetryData(
                    healthy=True, uptime_seconds=100.0, error_count=0, requests_handled=25, error_rate=0.0
                )
            elif service == unhealthy_service:
                return ServiceTelemetryData(
                    healthy=False, uptime_seconds=10.0, error_count=5, requests_handled=10, error_rate=0.5
                )
            return None

        with patch.object(aggregator, "_get_service_from_registry", side_effect=mock_get_service):
            with patch.object(aggregator, "_try_collect_metrics", side_effect=mock_try_collect):
                # Collect from healthy service
                healthy_result = await aggregator.collect_service("healthy_service")

                # Collect from unhealthy service
                unhealthy_result = await aggregator.collect_service("unhealthy_service")

        # Verify healthy service is healthy
        assert healthy_result.healthy is True, "Healthy service should remain healthy"
        assert healthy_result.uptime_seconds == 100.0

        # Verify unhealthy service is unhealthy
        assert unhealthy_result.healthy is False, "Unhealthy service should be unhealthy"
        assert unhealthy_result.error_count == 5

    @pytest.mark.asyncio
    async def test_collect_service_from_bus_calls_appropriate_handler(self, aggregator):
        """
        GIVEN a bus service (ends with '_bus')
        WHEN collect_service() is called
        THEN it uses the bus collection logic

        This ensures the special bus handling path works correctly.
        """
        # Mock the bus collection to return appropriate data
        mock_bus_data = ServiceTelemetryData(
            healthy=True, uptime_seconds=200.0, error_count=0, requests_handled=100, error_rate=0.0
        )

        # The method tries to get the bus from the agent
        mock_agent = Mock()
        mock_wise_bus = Mock()
        mock_wise_bus.get_metrics = Mock(return_value={"uptime_seconds": 200.0, "healthy": True})
        mock_agent.wise_bus = mock_wise_bus

        aggregator.service_registry._agent = mock_agent

        result = await aggregator.collect_service("wise_bus")

        # Should process bus metrics
        assert isinstance(result, ServiceTelemetryData)

    @pytest.mark.asyncio
    async def test_collect_service_from_adapter_calls_appropriate_handler(self, aggregator):
        """
        GIVEN an adapter service (api, discord, cli)
        WHEN collect_service() is called
        THEN it uses the adapter collection logic
        """
        # Mock runtime adapters
        mock_adapter = Mock()
        mock_adapter.__class__.__name__ = "ApiAdapter"
        mock_adapter.adapter_id = "api_instance1"
        mock_adapter.get_metrics = AsyncMock(
            return_value={"uptime_seconds": 300.0, "error_count": 0, "requests_handled": 150, "healthy": True}
        )

        aggregator.runtime.adapters = [mock_adapter]

        result = await aggregator.collect_service("api")

        # Adapter collection returns dict of instances
        assert isinstance(result, (dict, ServiceTelemetryData))

    @pytest.mark.asyncio
    async def test_collect_service_from_component_works(self, aggregator):
        """
        GIVEN a component service (service_registry, agent_processor)
        WHEN collect_service() is called
        THEN it collects metrics appropriately
        """
        # Mock the service registry component
        mock_registry = Mock()
        mock_registry.get_metrics = Mock(
            return_value={"healthy": True, "uptime_seconds": 400.0, "services_registered": 35}
        )

        aggregator.runtime.service_registry = mock_registry

        result = await aggregator.collect_service("service_registry")

        # Component returns ServiceTelemetryData
        assert isinstance(result, ServiceTelemetryData)
