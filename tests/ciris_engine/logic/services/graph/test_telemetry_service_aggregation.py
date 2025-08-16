"""Tests for GraphTelemetryService aggregation functionality."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService, TelemetryAggregator
from ciris_engine.schemas.runtime.enums import ServiceType


class TestGraphTelemetryServiceAggregation:
    """Test the GraphTelemetryService aggregation methods."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.fixture
    def mock_memory_bus(self):
        """Create a mock memory bus."""
        mock = Mock()
        mock.memorize = AsyncMock()
        mock.recall = AsyncMock(return_value=[])
        return mock

    @pytest.fixture
    def mock_service_registry(self):
        """Create a mock service registry."""
        mock = Mock()

        # Mock a service
        service = Mock()
        service.get_telemetry = AsyncMock(
            return_value={"service_name": "test_service", "healthy": True, "error_count": 0}
        )

        mock.get_services_by_type.return_value = [service]

        # Mock agent with buses
        mock_agent = Mock()
        mock._agent = mock_agent

        return mock

    @pytest_asyncio.fixture
    async def telemetry_service(self, mock_memory_bus, mock_time_service):
        """Create a GraphTelemetryService instance."""
        service = GraphTelemetryService(memory_bus=mock_memory_bus, time_service=mock_time_service)
        return service

    @pytest.mark.asyncio
    async def test_get_aggregated_telemetry_no_registry(self, telemetry_service):
        """Test aggregated telemetry when registry not set."""
        result = await telemetry_service.get_aggregated_telemetry()

        assert "error" in result
        assert result["error"] == "Telemetry aggregator not initialized"
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_get_aggregated_telemetry_with_registry(self, telemetry_service, mock_service_registry):
        """Test aggregated telemetry with registry set."""
        telemetry_service._set_service_registry(mock_service_registry)

        # Mock the aggregator
        mock_aggregator = Mock(spec=TelemetryAggregator)
        mock_aggregator.cache = {}
        mock_aggregator.cache_ttl = timedelta(seconds=30)

        mock_telemetry_data = {
            "buses": {"wise_bus": {"healthy": True}},
            "graph": {"memory": {"healthy": True}},
            "infrastructure": {"time": {"healthy": True}},
        }

        mock_aggregator.collect_all_parallel = AsyncMock(return_value=mock_telemetry_data)
        mock_aggregator.calculate_aggregates = Mock(
            return_value={"system_healthy": True, "services_online": 3, "services_total": 3, "overall_error_rate": 0.0}
        )

        telemetry_service._telemetry_aggregator = mock_aggregator

        result = await telemetry_service.get_aggregated_telemetry()

        assert result["system_healthy"] is True
        assert result["services_online"] == 3
        assert result["services_total"] == 3
        assert result["overall_error_rate"] == 0.0
        assert "services" in result
        assert "_metadata" in result
        assert result["_metadata"]["collection_method"] == "parallel"

    @pytest.mark.asyncio
    async def test_get_aggregated_telemetry_cache_hit(self, telemetry_service, mock_service_registry):
        """Test that cached results are returned when available."""
        telemetry_service._set_service_registry(mock_service_registry)

        # Create aggregator with cached data
        aggregator = TelemetryAggregator(
            service_registry=mock_service_registry, time_service=telemetry_service._time_service
        )

        # Pre-populate cache
        cached_data = {"system_healthy": True, "services_online": 5, "cached": True}
        aggregator.cache["aggregated_telemetry"] = (datetime.now(timezone.utc), cached_data.copy())

        telemetry_service._telemetry_aggregator = aggregator

        result = await telemetry_service.get_aggregated_telemetry()

        assert result["_cache_hit"] is True
        assert result["system_healthy"] is True
        assert result["services_online"] == 5

    @pytest.mark.asyncio
    async def test_get_aggregated_telemetry_cache_expired(self, telemetry_service, mock_service_registry):
        """Test that expired cache is not used."""
        telemetry_service._set_service_registry(mock_service_registry)

        aggregator = TelemetryAggregator(
            service_registry=mock_service_registry, time_service=telemetry_service._time_service
        )

        # Pre-populate cache with old data
        old_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        aggregator.cache["aggregated_telemetry"] = (old_time, {"old_data": True})

        # Mock fresh collection
        aggregator.collect_all_parallel = AsyncMock(return_value={"buses": {}, "graph": {}})
        aggregator.calculate_aggregates = Mock(return_value={"system_healthy": True, "fresh_data": True})

        telemetry_service._telemetry_aggregator = aggregator

        result = await telemetry_service.get_aggregated_telemetry()

        # Should have fresh data, not cached
        assert "_cache_hit" not in result
        assert "fresh_data" in result
        assert result["fresh_data"] is True

    @pytest.mark.asyncio
    async def test_aggregator_initialization(self, telemetry_service, mock_service_registry):
        """Test that aggregator is initialized on first use."""
        telemetry_service._set_service_registry(mock_service_registry)

        # Initially no aggregator
        assert telemetry_service._telemetry_aggregator is None

        # Mock the aggregator methods
        with patch.object(TelemetryAggregator, "collect_all_parallel", AsyncMock(return_value={"buses": {}})):
            with patch.object(TelemetryAggregator, "calculate_aggregates", Mock(return_value={"system_healthy": True})):

                result = await telemetry_service.get_aggregated_telemetry()

                # Aggregator should now be initialized
                assert telemetry_service._telemetry_aggregator is not None
                assert isinstance(telemetry_service._telemetry_aggregator, TelemetryAggregator)

    @pytest.mark.asyncio
    async def test_get_aggregated_telemetry_full_integration(self, telemetry_service, mock_service_registry):
        """Test full integration with actual aggregator."""
        telemetry_service._set_service_registry(mock_service_registry)

        # Mock services to return telemetry
        mock_service_registry.get_services_by_type.return_value = [
            Mock(
                get_telemetry=AsyncMock(
                    return_value={"service_name": "service1", "healthy": True, "error_count": 1, "request_count": 100}
                )
            )
        ]

        # Mock buses on agent
        mock_agent = Mock()
        mock_agent.wise_bus = Mock(
            collect_telemetry=AsyncMock(return_value={"service_name": "wise_bus", "healthy": True, "provider_count": 2})
        )
        mock_service_registry._agent = mock_agent

        result = await telemetry_service.get_aggregated_telemetry()

        assert "system_healthy" in result
        assert "services" in result
        assert "_metadata" in result

        # Check that services structure exists
        assert isinstance(result["services"], dict)

        # Verify metadata
        metadata = result["_metadata"]
        assert metadata["collection_method"] == "parallel"
        assert metadata["cache_ttl_seconds"] == 30
        assert "timestamp" in metadata
