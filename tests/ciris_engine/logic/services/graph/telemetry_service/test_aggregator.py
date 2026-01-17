"""Tests for TelemetryAggregator module.

Tests the enterprise telemetry aggregation functionality extracted
from the main service.py file.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.services.graph.telemetry_service.aggregator import (
    ConsolidationCandidate,
    GracePolicy,
    MemoryType,
    TelemetryAggregator,
)
from ciris_engine.schemas.services.graph.telemetry import ServiceTelemetryData


class TestMemoryType:
    """Tests for MemoryType enum."""

    def test_memory_type_values(self):
        """Test MemoryType enum has expected values."""
        assert MemoryType.OPERATIONAL.value == "operational"
        assert MemoryType.BEHAVIORAL.value == "behavioral"
        assert MemoryType.SOCIAL.value == "social"
        assert MemoryType.IDENTITY.value == "identity"
        assert MemoryType.WISDOM.value == "wisdom"

    def test_memory_type_is_string_enum(self):
        """Test MemoryType values are strings."""
        for memory_type in MemoryType:
            assert isinstance(memory_type.value, str)


class TestGracePolicy:
    """Tests for GracePolicy enum."""

    def test_grace_policy_values(self):
        """Test GracePolicy enum has expected values."""
        assert GracePolicy.FORGIVE_ERRORS.value == "forgive_errors"
        assert GracePolicy.EXTEND_PATIENCE.value == "extend_patience"
        assert GracePolicy.ASSUME_GOOD_INTENT.value == "assume_good_intent"
        assert GracePolicy.RECIPROCAL_GRACE.value == "reciprocal_grace"


class TestConsolidationCandidate:
    """Tests for ConsolidationCandidate dataclass."""

    def test_consolidation_candidate_creation(self):
        """Test creating a ConsolidationCandidate."""
        candidate = ConsolidationCandidate(
            memory_ids=["mem1", "mem2", "mem3"],
            memory_type=MemoryType.OPERATIONAL,
            time_span=timedelta(hours=1),
            total_size=1024,
            grace_applicable=True,
            grace_reasons=["pattern_detected"],
        )

        assert candidate.memory_ids == ["mem1", "mem2", "mem3"]
        assert candidate.memory_type == MemoryType.OPERATIONAL
        assert candidate.time_span == timedelta(hours=1)
        assert candidate.total_size == 1024
        assert candidate.grace_applicable is True
        assert candidate.grace_reasons == ["pattern_detected"]


class TestTelemetryAggregatorInit:
    """Tests for TelemetryAggregator initialization."""

    def test_init_with_all_parameters(self):
        """Test initializing with all parameters."""
        service_registry = Mock()
        time_service = Mock()
        runtime = Mock()

        aggregator = TelemetryAggregator(
            service_registry=service_registry,
            time_service=time_service,
            runtime=runtime,
        )

        assert aggregator.service_registry == service_registry
        assert aggregator.time_service == time_service
        assert aggregator.runtime == runtime
        assert aggregator.cache == {}
        assert aggregator.cache_ttl == timedelta(seconds=30)

    def test_init_without_runtime(self):
        """Test initializing without runtime."""
        service_registry = Mock()
        time_service = Mock()

        aggregator = TelemetryAggregator(
            service_registry=service_registry,
            time_service=time_service,
        )

        assert aggregator.runtime is None


class TestTelemetryAggregatorCategories:
    """Tests for TelemetryAggregator service categories."""

    def test_categories_structure(self):
        """Test CATEGORIES has expected structure."""
        expected_categories = [
            "buses",
            "graph",
            "infrastructure",
            "governance",
            "runtime",
            "tools",
            "adapters",
            "components",
            "covenant",
        ]

        for category in expected_categories:
            assert category in TelemetryAggregator.CATEGORIES

    def test_buses_category(self):
        """Test buses category has expected services."""
        buses = TelemetryAggregator.CATEGORIES["buses"]
        expected = ["llm_bus", "memory_bus", "communication_bus", "wise_bus", "tool_bus", "runtime_control_bus"]
        assert buses == expected

    def test_graph_category(self):
        """Test graph category has expected services."""
        graph = TelemetryAggregator.CATEGORIES["graph"]
        expected = ["memory", "config", "telemetry", "audit", "incident_management", "tsdb_consolidation"]
        assert graph == expected


class TestTelemetryAggregatorServiceCollection:
    """Tests for service collection methods."""

    @pytest.fixture
    def aggregator(self):
        """Create a TelemetryAggregator with mocked dependencies."""
        service_registry = Mock()
        time_service = Mock()
        time_service.now.return_value = datetime.now(timezone.utc)
        runtime = Mock()

        return TelemetryAggregator(
            service_registry=service_registry,
            time_service=time_service,
            runtime=runtime,
        )

    def test_get_service_from_runtime_with_mapping(self, aggregator):
        """Test getting service from runtime with valid mapping."""
        mock_service = Mock()
        aggregator.runtime.memory_service = mock_service

        result = aggregator._get_service_from_runtime("memory")
        assert result == mock_service

    def test_get_service_from_runtime_no_mapping(self, aggregator):
        """Test getting service from runtime with invalid name."""
        result = aggregator._get_service_from_runtime("unknown_service")
        assert result is None

    def test_get_service_from_runtime_no_runtime(self, aggregator):
        """Test getting service when runtime is None."""
        aggregator.runtime = None
        result = aggregator._get_service_from_runtime("memory")
        assert result is None


class TestTelemetryAggregatorMetricsCollection:
    """Tests for metrics collection methods."""

    @pytest.fixture
    def aggregator(self):
        """Create a TelemetryAggregator with mocked dependencies."""
        service_registry = Mock()
        service_registry.get_all_services.return_value = []
        time_service = Mock()
        time_service.now.return_value = datetime.now(timezone.utc)
        runtime = Mock()
        runtime.adapters = []

        return TelemetryAggregator(
            service_registry=service_registry,
            time_service=time_service,
            runtime=runtime,
        )

    @pytest.mark.asyncio
    async def test_try_get_metrics_method_async(self, aggregator):
        """Test collecting metrics via async get_metrics method."""
        mock_service = Mock()
        mock_metrics = ServiceTelemetryData(
            healthy=True,
            uptime_seconds=100.0,
            error_count=0,
            requests_handled=50,
            error_rate=0.0,
        )
        mock_service.get_metrics = AsyncMock(return_value=mock_metrics)

        result = await aggregator._try_get_metrics_method(mock_service)
        assert result == mock_metrics

    @pytest.mark.asyncio
    async def test_try_get_metrics_method_sync(self, aggregator):
        """Test collecting metrics via sync get_metrics method."""
        mock_service = Mock()
        mock_metrics = ServiceTelemetryData(
            healthy=True,
            uptime_seconds=200.0,
            error_count=1,
            requests_handled=100,
            error_rate=0.01,
        )
        mock_service.get_metrics = Mock(return_value=mock_metrics)

        result = await aggregator._try_get_metrics_method(mock_service)
        assert result == mock_metrics

    @pytest.mark.asyncio
    async def test_try_get_metrics_no_method(self, aggregator):
        """Test when service has no get_metrics method."""
        mock_service = Mock(spec=[])  # No get_metrics

        result = await aggregator._try_get_metrics_method(mock_service)
        assert result is None

    def test_convert_dict_to_telemetry(self, aggregator):
        """Test converting dict metrics to ServiceTelemetryData."""
        metrics_dict = {
            "uptime_seconds": 123.4,
            "error_count": 5,
            "request_count": 100,
            "error_rate": 0.05,
            "healthy": True,
        }

        result = aggregator._convert_dict_to_telemetry(metrics_dict, "test_service")

        assert isinstance(result, ServiceTelemetryData)
        assert result.uptime_seconds == 123.4
        assert result.error_count == 5
        assert result.requests_handled == 100
        assert result.error_rate == 0.05
        assert result.healthy is True


class TestTelemetryAggregatorFallbackMetrics:
    """Tests for fallback metrics behavior."""

    @pytest.fixture
    def aggregator(self):
        """Create a TelemetryAggregator."""
        return TelemetryAggregator(
            service_registry=Mock(),
            time_service=Mock(),
            runtime=Mock(),
        )

    def test_get_fallback_metrics_returns_unhealthy(self, aggregator):
        """Test that fallback metrics indicate unhealthy service."""
        result = aggregator.get_fallback_metrics("any_service")

        assert isinstance(result, ServiceTelemetryData)
        assert result.healthy is False
        assert result.uptime_seconds == 0.0
        assert result.error_count == 0
        assert result.requests_handled == 0
        assert result.error_rate == 0.0


class TestTelemetryAggregatorCovenantMetrics:
    """Tests for covenant metrics computation."""

    @pytest.fixture
    def aggregator(self):
        """Create a TelemetryAggregator."""
        return TelemetryAggregator(
            service_registry=Mock(),
            time_service=Mock(),
            runtime=Mock(),
        )

    def test_compute_covenant_metrics_empty(self, aggregator):
        """Test computing covenant metrics with empty telemetry."""
        telemetry = {"governance": {}}

        result = aggregator.compute_covenant_metrics(telemetry)

        assert "wise_authority_deferrals" in result
        assert "filter_matches" in result
        assert "thoughts_processed" in result
        assert "self_observation_insights" in result

    def test_compute_covenant_metrics_with_data(self, aggregator):
        """Test computing covenant metrics with governance data."""
        telemetry = {
            "governance": {
                "wise_authority": ServiceTelemetryData(
                    healthy=True,
                    uptime_seconds=1000.0,
                    error_count=0,
                    requests_handled=50,
                    error_rate=0.0,
                    custom_metrics={"deferral_count": 10, "guidance_requests": 50},
                ),
                "adaptive_filter": ServiceTelemetryData(
                    healthy=True,
                    uptime_seconds=1000.0,
                    error_count=0,
                    requests_handled=100,
                    error_rate=0.0,
                    custom_metrics={"filter_actions": 25},
                ),
            }
        }

        result = aggregator.compute_covenant_metrics(telemetry)

        assert result["wise_authority_deferrals"] == 10
        assert result["thoughts_processed"] == 50
        assert result["filter_matches"] == 25


class TestTelemetryAggregatorAggregates:
    """Tests for aggregate calculation."""

    @pytest.fixture
    def aggregator(self):
        """Create a TelemetryAggregator."""
        return TelemetryAggregator(
            service_registry=Mock(),
            time_service=Mock(),
            runtime=Mock(),
        )

    def test_calculate_aggregates_empty(self, aggregator):
        """Test calculating aggregates with empty telemetry."""
        telemetry = {"graph": {}, "infrastructure": {}}

        result = aggregator.calculate_aggregates(telemetry)

        assert result["system_healthy"] is True  # 0 >= 0 * 0.9
        assert result["services_online"] == 0
        assert result["services_total"] == 0
        assert result["overall_error_rate"] == 0.0

    def test_calculate_aggregates_with_services(self, aggregator):
        """Test calculating aggregates with services."""
        telemetry = {
            "graph": {
                "memory": ServiceTelemetryData(
                    healthy=True,
                    uptime_seconds=100.0,
                    error_count=0,
                    requests_handled=50,
                    error_rate=0.0,
                ),
                "config": ServiceTelemetryData(
                    healthy=True,
                    uptime_seconds=100.0,
                    error_count=1,
                    requests_handled=25,
                    error_rate=0.04,
                ),
            },
            "covenant": {},  # Should be skipped
        }

        result = aggregator.calculate_aggregates(telemetry)

        assert result["services_total"] == 2
        assert result["services_online"] == 2
        assert result["total_errors"] == 1
        assert result["total_requests"] == 75
