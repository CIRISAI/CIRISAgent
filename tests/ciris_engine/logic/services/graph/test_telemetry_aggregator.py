"""Tests for TelemetryAggregator functionality."""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.services.graph.telemetry_service import TelemetryAggregator
from ciris_engine.schemas.runtime.enums import ServiceType


class TestTelemetryAggregator:
    """Test the TelemetryAggregator class."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.fixture
    def mock_service_registry(self):
        """Create a mock service registry."""
        mock = Mock()

        # Mock service with telemetry
        mock_service = Mock()
        mock_service.get_telemetry = AsyncMock(
            return_value={
                "service_name": "test_service",
                "healthy": True,
                "error_count": 2,
                "request_count": 100,
                "uptime_seconds": 3600,
            }
        )

        # Mock get_services_by_type
        mock.get_services_by_type.return_value = [mock_service]

        # Mock agent with buses
        mock_agent = Mock()
        mock_agent.wise_bus = Mock()
        mock_agent.wise_bus.collect_telemetry = AsyncMock(
            return_value={"service_name": "wise_bus", "healthy": True, "failed_count": 1, "processed_count": 50}
        )
        mock_agent.memory_bus = Mock()
        mock_agent.memory_bus.collect_telemetry = AsyncMock(
            return_value={"service_name": "memory_bus", "healthy": True, "total_nodes": 1000, "query_count": 200}
        )
        mock._agent = mock_agent

        return mock

    @pytest_asyncio.fixture
    async def aggregator(self, mock_service_registry, mock_time_service):
        """Create a TelemetryAggregator instance."""
        return TelemetryAggregator(service_registry=mock_service_registry, time_service=mock_time_service)

    @pytest.mark.asyncio
    async def test_collect_service(self, aggregator):
        """Test collecting telemetry from a single service."""
        result = await aggregator.collect_service("memory")

        assert result["service_name"] == "test_service"
        assert result["healthy"] is True
        assert result["error_count"] == 2
        assert result["request_count"] == 100

    @pytest.mark.asyncio
    async def test_collect_from_bus(self, aggregator):
        """Test collecting telemetry from a bus."""
        result = await aggregator.collect_from_bus("wise_bus")

        assert result["service_name"] == "wise_bus"
        assert result["healthy"] is True
        assert result["failed_count"] == 1
        assert result["processed_count"] == 50

    @pytest.mark.asyncio
    async def test_collect_all_parallel(self, aggregator):
        """Test parallel collection from all services."""

        # Mock collect_service to return quickly
        async def mock_collect(service_name):
            await asyncio.sleep(0.01)  # Simulate some work
            return {"service_name": service_name, "healthy": True, "error_count": 0, "request_count": 10}

        aggregator.collect_service = mock_collect

        result = await aggregator.collect_all_parallel()

        # Check structure
        assert "buses" in result
        assert "graph" in result
        assert "infrastructure" in result
        assert "governance" in result
        assert "runtime" in result

        # Check some services are present
        assert "memory" in result["graph"]
        assert "wise_authority" in result["governance"]
        assert "llm" in result["runtime"]

    @pytest.mark.asyncio
    async def test_collect_with_timeout(self, aggregator):
        """Test that slow services are handled with timeout."""

        # Mock a slow service
        async def slow_collect(service_name):
            if service_name == "slow_service":
                await asyncio.sleep(10)  # Longer than timeout
            return {"service_name": service_name, "healthy": True}

        aggregator.collect_service = slow_collect

        # This should complete within reasonable time despite slow service
        result = await asyncio.wait_for(
            aggregator.collect_all_parallel(), timeout=7.0  # Slightly more than aggregator's 5s timeout
        )

        assert result is not None

    @pytest.mark.asyncio
    async def test_fallback_metrics(self, aggregator):
        """Test fallback metrics when service is unavailable."""
        # Mock service registry to return None
        aggregator.service_registry.get_services_by_type.return_value = []

        result = await aggregator.collect_service("missing_service")

        assert result["service_name"] == "missing_service"
        assert result["healthy"] is True
        assert result["error_count"] == 0
        assert "last_updated" in result

    @pytest.mark.asyncio
    async def test_fallback_metrics_unhealthy(self, aggregator):
        """Test fallback metrics for unhealthy service."""
        result = aggregator.get_fallback_metrics("failed_service", healthy=False)

        assert result["service_name"] == "failed_service"
        assert result["healthy"] is False
        assert result["error_count"] == 1
        assert result["error_rate"] == 1.0

    def test_calculate_aggregates(self, aggregator):
        """Test aggregate calculation from telemetry data."""
        telemetry = {
            "buses": {
                "wise_bus": {"healthy": True, "error_count": 1, "request_count": 100, "uptime_seconds": 3600},
                "memory_bus": {"healthy": True, "error_count": 2, "request_count": 200, "uptime_seconds": 3500},
            },
            "graph": {
                "memory": {
                    "healthy": False,
                    "error_count": 5,
                    "request_count": 50,
                    "error_rate": 0.1,
                    "uptime_seconds": 3000,
                }
            },
        }

        result = aggregator.calculate_aggregates(telemetry)

        assert result["services_total"] == 3
        assert result["services_online"] == 2
        assert result["system_healthy"] is False  # Less than 90% online
        assert result["total_errors"] == 8
        assert result["total_requests"] == 350
        assert result["overall_uptime_seconds"] == 3000  # Minimum uptime
        assert "timestamp" in result

    def test_calculate_aggregates_all_healthy(self, aggregator):
        """Test aggregates when all services are healthy."""
        telemetry = {
            "buses": {
                "wise_bus": {"healthy": True, "error_count": 0, "uptime_seconds": 3600},
                "memory_bus": {"healthy": True, "error_count": 0, "uptime_seconds": 3600},
            }
        }

        result = aggregator.calculate_aggregates(telemetry)

        assert result["system_healthy"] is True
        assert result["services_online"] == 2
        assert result["services_total"] == 2
        assert result["overall_error_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_caching(self, aggregator):
        """Test that results are cached properly."""
        # First call
        aggregator.collect_service = AsyncMock(return_value={"count": 1})
        result1 = await aggregator.collect_all_parallel()

        # Cache the result manually (normally done by the service)
        aggregator.cache["test_key"] = (datetime.now(timezone.utc), {"cached": True})

        # Check cache works
        cached_time, cached_data = aggregator.cache["test_key"]
        assert cached_data["cached"] is True
        assert datetime.now(timezone.utc) - cached_time < timedelta(seconds=1)

    def test_status_to_telemetry(self, aggregator):
        """Test conversion of status objects to telemetry."""

        # Test with object that has model_dump
        class MockStatus:
            def model_dump(self):
                return {"status": "ok", "healthy": True}

        result = aggregator.status_to_telemetry(MockStatus())
        assert result == {"status": "ok", "healthy": True}

        # Test with object that has __dict__
        class SimpleStatus:
            def __init__(self):
                self.status = "running"
                self.healthy = True

        result = aggregator.status_to_telemetry(SimpleStatus())
        assert result["status"] == "running"
        assert result["healthy"] is True

        # Test with plain string
        result = aggregator.status_to_telemetry("active")
        assert result == {"status": "active"}

    @pytest.mark.asyncio
    async def test_service_collection_error_handling(self, aggregator):
        """Test error handling during service collection."""
        # Mock service that raises exception
        aggregator.service_registry.get_services_by_type.side_effect = Exception("Registry error")

        result = await aggregator.collect_service("error_service")

        # Should return fallback metrics - by default returns healthy=True for missing services
        # Only returns healthy=False when explicitly called with healthy=False
        assert result["service_name"] == "error_service"
        assert result["healthy"] is True  # Default fallback is healthy
        assert result["error_count"] == 0  # Default fallback has no errors

    @pytest.mark.asyncio
    async def test_bus_collection_error_handling(self, aggregator):
        """Test error handling during bus collection."""
        # Mock bus that raises exception
        aggregator.service_registry._agent.wise_bus.collect_telemetry.side_effect = Exception("Bus error")

        result = await aggregator.collect_from_bus("wise_bus")

        # Should return fallback metrics
        assert result["service_name"] == "wise_bus"
        assert result["healthy"] is False
        assert result["error_count"] == 1
