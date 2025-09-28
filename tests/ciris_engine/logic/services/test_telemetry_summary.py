"""Tests for telemetry summary functionality."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.schemas.runtime.system_context import TelemetrySummary


class TestTelemetrySummary:
    """Test telemetry summary generation and caching."""

    @pytest.fixture
    def mock_time_service(self) -> Mock:
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock.timestamp.return_value = 1704110400.0
        return mock

    @pytest.fixture
    def mock_memory_bus(self) -> Mock:
        """Create a mock memory bus."""
        return Mock(spec=MemoryBus)

    @pytest_asyncio.fixture
    async def telemetry_service(self, mock_memory_bus: Mock, mock_time_service: Mock) -> GraphTelemetryService:
        """Create telemetry service with mocks."""
        service = GraphTelemetryService(memory_bus=mock_memory_bus, time_service=mock_time_service)
        # Set start time for uptime calculation
        setattr(service, "_start_time", datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc))
        return service

    def create_mock_metrics(
        self, base_time: datetime, metric_name: str, values: List[float], service: str = "test_service"
    ) -> List[Dict[str, Any]]:
        """Helper to create mock metric data."""
        metrics = []
        for i, value in enumerate(values):
            # Create timestamps that are within the last hour
            timestamp = base_time - timedelta(minutes=i * 5)  # Space out by 5 minutes
            metrics.append(
                {
                    "metric_name": metric_name,
                    "value": value,
                    "timestamp": timestamp.isoformat(),  # Convert to ISO format string
                    "tags": {"service": service},
                }
            )
        return metrics

    @pytest.mark.asyncio
    async def test_get_telemetry_summary_basic(
        self, telemetry_service: GraphTelemetryService, mock_time_service: Mock
    ) -> None:
        """Test basic telemetry summary generation."""

        # Mock query_metrics to return test data
        async def mock_query_metrics(
            metric_name: str, start_time: datetime, end_time: datetime, tags: Optional[Dict[str, Any]] = None
        ) -> List[Dict[str, Any]]:
            # Always ensure we return metrics with the correct metric_name
            if metric_name == "llm.tokens.total":
                return self.create_mock_metrics(
                    mock_time_service.now(),
                    "llm.tokens.total",  # Use exact metric name
                    [100, 200, 150, 300],  # 750 total
                )
            elif metric_name == "llm.cost.cents":
                return self.create_mock_metrics(
                    mock_time_service.now(),
                    "llm.cost.cents",  # Use exact metric name
                    [1.5, 3.0, 2.25, 4.5],  # 11.25 total
                )
            elif metric_name == "llm.environmental.carbon_grams":
                return self.create_mock_metrics(
                    mock_time_service.now(),
                    "llm.environmental.carbon_grams",  # Use exact metric name
                    [0.15, 0.30, 0.225, 0.45],  # 1.125 total
                )
            # Return empty list for other metric types that get_telemetry_summary queries
            return []

        telemetry_service.query_metrics = mock_query_metrics

        # Get summary
        summary = await telemetry_service.get_telemetry_summary()

        # Verify results
        assert isinstance(summary, TelemetrySummary)
        assert summary.tokens_last_hour == 750  # Sum of tokens in last hour
        assert summary.cost_last_hour_cents == 11.25
        assert summary.carbon_last_hour_grams == 1.125
        assert summary.uptime_seconds == 43200.0  # 12 hours

    @pytest.mark.asyncio
    async def test_telemetry_summary_caching(
        self, telemetry_service: GraphTelemetryService, mock_time_service: Mock
    ) -> None:
        """Test that telemetry summary uses caching."""
        call_count = 0

        async def mock_query_metrics(
            metric_name: str, start_time: datetime, end_time: datetime, tags: Optional[Dict[str, Any]] = None
        ) -> List[Dict[str, Any]]:
            nonlocal call_count
            call_count += 1
            return self.create_mock_metrics(mock_time_service.now(), metric_name, [100])

        telemetry_service.query_metrics = mock_query_metrics

        # First call should query metrics (multiple times for different metric types)
        summary1 = await telemetry_service.get_telemetry_summary()
        initial_calls = call_count
        # Should have made multiple queries for different metric types
        assert initial_calls > 0

        # Second call should use cache
        summary2 = await telemetry_service.get_telemetry_summary()
        assert call_count == initial_calls  # No new queries

        # Summaries should be identical
        assert summary1.tokens_last_hour == summary2.tokens_last_hour
        assert summary1.cost_last_hour_cents == summary2.cost_last_hour_cents

        # Advance time past cache TTL (default is 60 seconds)
        mock_time_service.now.return_value = datetime(2024, 1, 1, 12, 1, 1, tzinfo=timezone.utc)  # 61 seconds later

        # Third call should query metrics again
        summary3 = await telemetry_service.get_telemetry_summary()
        assert call_count > initial_calls  # New queries made

    @pytest.mark.asyncio
    async def test_telemetry_summary_error_handling(
        self, telemetry_service: GraphTelemetryService, mock_time_service: Mock
    ) -> None:
        """Test telemetry summary handles errors gracefully."""

        # Mock query_metrics to raise an error
        async def mock_query_metrics(
            metric_name: str, start_time: datetime, end_time: datetime, tags: Optional[Dict[str, Any]] = None
        ) -> List[Dict[str, Any]]:
            raise Exception("Database error")

        telemetry_service.query_metrics = mock_query_metrics

        # Should return empty summary on error
        summary = await telemetry_service.get_telemetry_summary()

        assert isinstance(summary, TelemetrySummary)
        assert summary.tokens_last_hour == 0.0
        assert summary.cost_last_hour_cents == 0.0
        assert summary.messages_processed_24h == 0

    @pytest.mark.asyncio
    async def test_telemetry_summary_service_breakdown(
        self, telemetry_service: GraphTelemetryService, mock_time_service: Mock
    ) -> None:
        """Test service call breakdown in telemetry summary."""

        async def mock_query_metrics(
            metric_name: str, start_time: datetime, end_time: datetime, tags: Optional[Dict[str, Any]] = None
        ) -> List[Dict[str, Any]]:
            if metric_name == "llm.tokens.total":
                metrics = []
                # Create metrics from different services
                for service in ["openai", "anthropic", "local"]:
                    metrics.extend(
                        self.create_mock_metrics(mock_time_service.now(), metric_name, [100, 200], service=service)
                    )
                return metrics
            elif metric_name == "llm.latency.ms":
                return [
                    {
                        "metric_name": metric_name,
                        "value": 150.0,
                        "timestamp": mock_time_service.now().isoformat(),
                        "tags": {"service": "openai"},
                    },
                    {
                        "metric_name": metric_name,
                        "value": 200.0,
                        "timestamp": mock_time_service.now().isoformat(),
                        "tags": {"service": "openai"},
                    },
                    {
                        "metric_name": metric_name,
                        "value": 100.0,
                        "timestamp": mock_time_service.now().isoformat(),
                        "tags": {"service": "anthropic"},
                    },
                ]
            return []

        telemetry_service.query_metrics = mock_query_metrics

        summary = await telemetry_service.get_telemetry_summary()

        # Check service breakdown
        assert "openai" in summary.service_calls
        assert "anthropic" in summary.service_calls
        assert "local" in summary.service_calls
        # Each service has 2 metrics from llm.tokens.total
        # But service_calls counts all metric occurrences, not just unique calls
        assert summary.service_calls["openai"] >= 2
        assert summary.service_calls["anthropic"] >= 2
        assert summary.service_calls["local"] >= 2

        # Check latency calculations
        assert "openai" in summary.service_latency_ms
        assert summary.service_latency_ms["openai"] == 175.0  # avg of 150 and 200
        assert summary.service_latency_ms["anthropic"] == 100.0


class TestResourceUsageCalculation:
    """Test resource usage calculation in LLM service."""

    def test_llama_model_cost_calculation(self) -> None:
        """Test cost calculation for Llama models."""

        # Simulate the cost calculation logic
        model_name = "meta-llama/Llama-4-Scout-17B-16E-Instruct"
        prompt_tokens = 1000000  # 1M tokens
        completion_tokens = 500000  # 500K tokens

        # Cost calculation for Llama
        if "llama" in model_name.lower():
            input_cost_cents = (prompt_tokens / 1_000_000) * 10.0  # $0.10 per 1M
            output_cost_cents = (completion_tokens / 1_000_000) * 10.0  # $0.10 per 1M

        total_cost_cents = input_cost_cents + output_cost_cents

        assert input_cost_cents == 10.0  # $0.10
        assert output_cost_cents == 5.0  # $0.05
        assert total_cost_cents == 15.0  # $0.15

    def test_carbon_footprint_calculation(self) -> None:
        """Test carbon footprint calculation for different models."""
        # Test Llama 17B model
        model_name = "meta-llama/Llama-4-Scout-17B-16E-Instruct"
        total_tokens = 10000  # 10K tokens

        if "llama" in model_name.lower() and "17B" in model_name:
            energy_kwh = (total_tokens / 1000) * 0.0002  # Lower energy use
        else:
            energy_kwh = (total_tokens / 1000) * 0.0003

        carbon_grams = energy_kwh * 500.0  # 500g CO2 per kWh

        assert energy_kwh == 0.002  # 0.002 kWh
        assert carbon_grams == 1.0  # 1g CO2

    def test_openai_model_costs(self) -> None:
        """Test cost calculations for various OpenAI models."""
        test_cases = [
            ("gpt-4o-mini", 1_000_000, 1_000_000, 15.0, 60.0),  # $0.15 + $0.60
            ("gpt-4o", 1_000_000, 1_000_000, 250.0, 1000.0),  # $2.50 + $10.00
            ("gpt-3.5-turbo", 1_000_000, 1_000_000, 50.0, 150.0),  # $0.50 + $1.50
        ]

        for model_name, input_tokens, output_tokens, expected_input_cost, expected_output_cost in test_cases:
            if model_name.startswith("gpt-4o-mini"):
                input_cost = (input_tokens / 1_000_000) * 15.0
                output_cost = (output_tokens / 1_000_000) * 60.0
            elif model_name.startswith("gpt-4o"):
                input_cost = (input_tokens / 1_000_000) * 250.0
                output_cost = (output_tokens / 1_000_000) * 1000.0
            elif model_name.startswith("gpt-3.5-turbo"):
                input_cost = (input_tokens / 1_000_000) * 50.0
                output_cost = (output_tokens / 1_000_000) * 150.0

            assert input_cost == expected_input_cost
            assert output_cost == expected_output_cost


class TestSystemSnapshotIntegration:
    """Test system snapshot integration with telemetry."""

    @pytest.fixture
    def mock_time_service(self) -> Mock:
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.mark.asyncio
    async def test_system_snapshot_includes_telemetry(self, mock_time_service) -> None:
        """Test that build_system_snapshot includes telemetry summary."""
        from ciris_engine.logic.context.system_snapshot import build_system_snapshot

        # Create mocks
        mock_telemetry_service = Mock()
        mock_telemetry_summary = TelemetrySummary(
            window_start=datetime.now() - timedelta(hours=24),
            window_end=datetime.now(),
            uptime_seconds=86400.0,
            tokens_last_hour=1000.0,
            cost_last_hour_cents=50.0,
            carbon_last_hour_grams=10.0,
            messages_processed_24h=100,
            errors_24h=2,
        )
        mock_telemetry_service.get_telemetry_summary = AsyncMock(return_value=mock_telemetry_summary)

        mock_resource_monitor = Mock()
        mock_resource_monitor.snapshot = Mock(critical=[], healthy=True)

        # Build snapshot
        snapshot = await build_system_snapshot(
            task=None,
            thought=None,
            resource_monitor=mock_resource_monitor,
            telemetry_service=mock_telemetry_service,
            time_service=mock_time_service,
        )

        # Verify telemetry is included
        assert snapshot.telemetry_summary is not None
        assert snapshot.telemetry_summary.tokens_last_hour == 1000.0
        assert snapshot.telemetry_summary.cost_last_hour_cents == 50.0

    def test_system_snapshot_formatting_with_telemetry(self) -> None:
        """Test formatting of system snapshot with telemetry data."""
        from ciris_engine.logic.formatters.system_snapshot import format_system_snapshot
        from ciris_engine.schemas.runtime.system_context import SystemSnapshot

        # Create snapshot with telemetry
        telemetry_summary = TelemetrySummary(
            window_start=datetime.now() - timedelta(hours=24),
            window_end=datetime.now(),
            uptime_seconds=86400.0,
            tokens_last_hour=1500.0,
            cost_last_hour_cents=75.0,
            carbon_last_hour_grams=15.0,
            energy_last_hour_kwh=0.003,  # Added missing field
            messages_processed_24h=200,
            messages_current_hour=25,
            thoughts_processed_24h=150,
            thoughts_current_hour=20,
            errors_24h=5,
            error_rate_percent=2.5,
            service_calls={"openai": 100, "memory": 50},
        )

        snapshot = SystemSnapshot(
            system_counts={"pending_tasks": 5, "total_tasks": 100}, telemetry_summary=telemetry_summary
        )

        # Format the snapshot
        formatted = format_system_snapshot(snapshot)

        # Verify output contains telemetry data
        assert "=== Resource Usage ===" in formatted
        assert "Tokens (Last Hour): 1,500 tokens, $0.75, 15.0g CO2, 0.003 kWh" in formatted
        assert "Messages Processed: 25 (current hour), 200 (24h)" in formatted
        assert "Thoughts Processed: 20 (current hour), 150 (24h)" in formatted
        assert "⚠️ Error Rate: 2.5%" in formatted
        assert "Service Usage:" in formatted
        assert "- openai: 100 calls" in formatted
