"""Tests for unified telemetry SDK methods."""

import json
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_sdk.resources.telemetry import TelemetryResource
from ciris_sdk.transport import Transport


@pytest.fixture
def mock_transport():
    """Create mock transport."""
    return Mock(spec=Transport)


@pytest.fixture
def telemetry_resource(mock_transport):
    """Create telemetry resource with mock transport."""
    return TelemetryResource(mock_transport)


class TestUnifiedTelemetryMethods:
    """Test unified telemetry SDK methods."""

    @pytest.mark.asyncio
    async def test_get_unified_telemetry_default(self, telemetry_resource, mock_transport):
        """Test get_unified_telemetry with default parameters."""
        mock_response = {
            "system_healthy": True,
            "services_online": 21,
            "services_total": 21,
            "overall_error_rate": 0.01,
            "overall_uptime_seconds": 86400,
            "performance": {
                "avg_latency_ms": 45,
                "throughput_rps": 150,
            },
            "alerts": [],
            "warnings": [],
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_unified_telemetry()

        mock_transport.request.assert_called_once_with(
            "GET", "/v1/telemetry/unified", params={"view": "summary", "format": "json", "live": "false"}
        )
        assert result == mock_response
        assert result["system_healthy"] is True
        assert result["services_online"] == 21

    @pytest.mark.asyncio
    async def test_get_unified_telemetry_detailed_view(self, telemetry_resource, mock_transport):
        """Test get_unified_telemetry with detailed view."""
        mock_response = {
            "system_healthy": True,
            "buses": {
                "llm_bus": {"healthy": True, "request_count": 1000},
                "memory_bus": {"healthy": True, "query_count": 500},
            },
            "graph_services": {
                "memory": {"total_nodes": 10000},
                "config": {"config_version": "1.0.0"},
            },
            "infrastructure": {
                "resource_monitor": {"cpu_percent": 45, "memory_mb": 2048},
            },
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_unified_telemetry(view="detailed")

        mock_transport.request.assert_called_once_with(
            "GET", "/v1/telemetry/unified", params={"view": "detailed", "format": "json", "live": "false"}
        )
        assert "buses" in result
        assert "graph_services" in result
        assert result["buses"]["llm_bus"]["request_count"] == 1000

    @pytest.mark.asyncio
    async def test_get_unified_telemetry_with_category(self, telemetry_resource, mock_transport):
        """Test get_unified_telemetry with category filter."""
        mock_response = {
            "buses": {
                "llm_bus": {"healthy": True, "request_count": 1000},
            },
            "_metadata": {
                "view": "detailed",
                "category": "buses",
            },
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_unified_telemetry(view="detailed", category="buses")

        mock_transport.request.assert_called_once_with(
            "GET",
            "/v1/telemetry/unified",
            params={"view": "detailed", "format": "json", "live": "false", "category": "buses"},
        )
        assert "buses" in result
        assert result["_metadata"]["category"] == "buses"

    @pytest.mark.asyncio
    async def test_get_unified_telemetry_live(self, telemetry_resource, mock_transport):
        """Test get_unified_telemetry with live data."""
        mock_response = {
            "system_healthy": True,
            "_metadata": {
                "cached": False,
            },
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_unified_telemetry(live=True)

        mock_transport.request.assert_called_once_with(
            "GET", "/v1/telemetry/unified", params={"view": "summary", "format": "json", "live": "true"}
        )
        assert result["_metadata"]["cached"] is False

    @pytest.mark.asyncio
    async def test_get_unified_telemetry_prometheus_format(self, telemetry_resource, mock_transport):
        """Test get_unified_telemetry with Prometheus format."""
        mock_response = "ciris_system_healthy 1\nciris_services_online 21"

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_unified_telemetry(format="prometheus")

        mock_transport.request.assert_called_once_with(
            "GET",
            "/v1/telemetry/unified",
            params={"view": "summary", "format": "prometheus", "live": "false"},
            raw_response=True,
        )
        assert "ciris_system_healthy 1" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_get_all_metrics(self, telemetry_resource, mock_transport):
        """Test get_all_metrics convenience method."""
        mock_response = {
            "system_healthy": True,
            "buses": {"llm_bus": {"healthy": True}},
            "graph_services": {"memory": {"total_nodes": 1000}},
            "infrastructure": {"resource_monitor": {"cpu_percent": 50}},
            "governance": {"wise_authority": {"deferrals_pending": 0}},
            "runtime": {"llm": {"tokens_used": 5000}},
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_all_metrics()

        mock_transport.request.assert_called_once_with(
            "GET", "/v1/telemetry/unified", params={"view": "detailed", "format": "json", "live": "true"}
        )
        assert "buses" in result
        assert "graph_services" in result
        assert "infrastructure" in result
        assert "governance" in result
        assert "runtime" in result

    @pytest.mark.asyncio
    async def test_get_metric_by_path_simple(self, telemetry_resource, mock_transport):
        """Test get_metric_by_path with simple path."""
        mock_response = {
            "system_healthy": True,
            "services_online": 21,
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_metric_by_path("system_healthy")

        assert result is True

    @pytest.mark.asyncio
    async def test_get_metric_by_path_nested(self, telemetry_resource, mock_transport):
        """Test get_metric_by_path with nested path."""
        mock_response = {
            "infrastructure": {
                "resource_monitor": {
                    "cpu_percent": 45,
                    "memory_mb": 2048,
                }
            }
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.get_metric_by_path("infrastructure.resource_monitor.cpu_percent")

        assert result == 45

    @pytest.mark.asyncio
    async def test_get_metric_by_path_not_found(self, telemetry_resource, mock_transport):
        """Test get_metric_by_path with invalid path."""
        mock_response = {
            "system_healthy": True,
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        with pytest.raises(KeyError, match="Metric not found"):
            await telemetry_resource.get_metric_by_path("invalid.path.to.metric")

    @pytest.mark.asyncio
    async def test_check_system_health(self, telemetry_resource, mock_transport):
        """Test check_system_health convenience method."""
        mock_response = {
            "healthy": True,
            "services": {"online": 21, "total": 21},
            "alerts": [],
            "warnings": [],
        }

        mock_transport.request = AsyncMock(return_value=mock_response)

        result = await telemetry_resource.check_system_health()

        mock_transport.request.assert_called_once_with(
            "GET", "/v1/telemetry/unified", params={"view": "health", "format": "json", "live": "true"}
        )
        assert result["healthy"] is True
        assert result["services"]["online"] == 21
        assert len(result["alerts"]) == 0

    @pytest.mark.asyncio
    async def test_get_unified_telemetry_all_views(self, telemetry_resource, mock_transport):
        """Test all available views."""
        views = ["summary", "health", "operational", "performance", "reliability", "detailed"]

        for view in views:
            mock_response = {"view": view, "data": "test"}
            mock_transport.request = AsyncMock(return_value=mock_response)

            result = await telemetry_resource.get_unified_telemetry(view=view)

            mock_transport.request.assert_called_with(
                "GET", "/v1/telemetry/unified", params={"view": view, "format": "json", "live": "false"}
            )
            assert result["view"] == view

    @pytest.mark.asyncio
    async def test_get_unified_telemetry_all_categories(self, telemetry_resource, mock_transport):
        """Test all available categories."""
        categories = ["buses", "graph", "infrastructure", "governance", "runtime", "adapters", "components", "all"]

        for category in categories:
            mock_response = {"category": category, "data": "test"}
            mock_transport.request = AsyncMock(return_value=mock_response)

            result = await telemetry_resource.get_unified_telemetry(category=category)

            expected_params = {"view": "summary", "format": "json", "live": "false", "category": category}
            mock_transport.request.assert_called_with("GET", "/v1/telemetry/unified", params=expected_params)
            assert result["category"] == category
