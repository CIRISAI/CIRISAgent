"""
Simple, focused tests to increase bus coverage to 80%+ for SonarCloud.

Focus on testing the actual code paths that exist in the buses,
not hypothetical functionality.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.buses.communication_bus import CommunicationBus
from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus, ServiceMetrics
from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.buses.runtime_control_bus import RuntimeControlBus
from ciris_engine.logic.buses.tool_bus import ToolBus
from ciris_engine.logic.buses.wise_bus import WiseBus
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.schemas.runtime.enums import ServiceType


@pytest.fixture
def mock_registry():
    """Mock service registry."""
    registry = MagicMock(spec=ServiceRegistry)
    registry.get_services_by_type = MagicMock(return_value=[])
    return registry


@pytest.fixture
def mock_time_service():
    """Mock time service."""
    service = MagicMock()
    service.now = MagicMock(return_value=datetime.now(timezone.utc))
    return service


# =============================================================================
# COMMUNICATION BUS - Focus on untested paths
# =============================================================================


class TestCommunicationBusCoverage:
    """Increase CommunicationBus coverage from 42.9%"""

    def test_init_and_get_metrics(self, mock_registry, mock_time_service):
        """Test initialization and metrics."""
        bus = CommunicationBus(mock_registry, mock_time_service)

        # Test get_metrics exists and returns dict
        metrics = bus.get_metrics()
        assert isinstance(metrics, dict)
        assert "communication_messages_sent" in metrics
        assert "communication_broadcasts" in metrics
        assert "communication_uptime_seconds" in metrics

    async def test_broadcast(self, mock_registry, mock_time_service):
        """Test broadcast method."""
        bus = CommunicationBus(mock_registry, mock_time_service)

        # Mock services
        service1 = AsyncMock()
        service1.send_message = AsyncMock(return_value=True)
        service2 = AsyncMock()
        service2.send_message = AsyncMock(return_value=False)

        mock_registry.get_services_by_type.return_value = [service1, service2]

        # Test broadcast
        results = await bus.broadcast("channel", "message", {})

        assert len(results) == 2
        assert bus._broadcasts > 0

    async def test_send_to_user(self, mock_registry, mock_time_service):
        """Test send_to_user method."""
        bus = CommunicationBus(mock_registry, mock_time_service)

        service = AsyncMock()
        service.send_to_user = AsyncMock(return_value=True)
        mock_registry.get_services_by_type.return_value = [service]

        result = await bus.send_to_user("user123", "Hello")

        assert result is True
        assert bus._messages_sent > 0


# =============================================================================
# LLM BUS - Focus on the 11.1% coverage
# =============================================================================


class TestLLMBusCoverage:
    """Increase LLMBus coverage from 11.1%"""

    def test_service_metrics_class(self):
        """Test ServiceMetrics calculations."""
        metrics = ServiceMetrics()

        # Test initial state
        assert metrics.average_latency_ms == 0.0
        assert metrics.failure_rate == 0.0

        # Test with data
        metrics.total_requests = 100
        metrics.failed_requests = 10
        metrics.total_latency_ms = 5000.0

        assert metrics.average_latency_ms == 50.0
        assert metrics.failure_rate == 0.1

    def test_init_with_strategies(self, mock_registry, mock_time_service):
        """Test initialization with different distribution strategies."""
        # Round robin
        bus1 = LLMBus(mock_registry, mock_time_service, distribution_strategy=DistributionStrategy.ROUND_ROBIN)
        assert bus1.distribution_strategy == DistributionStrategy.ROUND_ROBIN

        # Latency based
        bus2 = LLMBus(mock_registry, mock_time_service, distribution_strategy=DistributionStrategy.LATENCY_BASED)
        assert bus2.distribution_strategy == DistributionStrategy.LATENCY_BASED

        # Random
        bus3 = LLMBus(mock_registry, mock_time_service, distribution_strategy=DistributionStrategy.RANDOM)
        assert bus3.distribution_strategy == DistributionStrategy.RANDOM

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test get_metrics method."""
        bus = LLMBus(mock_registry, mock_time_service)

        # Initialize some metrics
        bus.service_metrics["test_service"] = ServiceMetrics(
            total_requests=50, failed_requests=5, total_latency_ms=2500
        )

        metrics = bus.get_metrics()

        assert isinstance(metrics, dict)
        assert "llm_requests_total" in metrics
        assert "llm_providers_available" in metrics
        assert "llm_circuit_breakers_open" in metrics
        assert "llm_uptime_seconds" in metrics

    async def test_record_metrics(self, mock_registry, mock_time_service):
        """Test metric recording."""
        telemetry = AsyncMock()
        telemetry.memorize_metric = AsyncMock()

        bus = LLMBus(mock_registry, mock_time_service, telemetry_service=telemetry)

        # Record some metrics
        await bus._record_metric("test_metric", 42.0)

        telemetry.memorize_metric.assert_called()


# =============================================================================
# MEMORY BUS - Focus on the 29.3% coverage
# =============================================================================


class TestMemoryBusCoverage:
    """Increase MemoryBus coverage from 29.3%"""

    def test_init(self, mock_registry, mock_time_service):
        """Test initialization."""
        telemetry = AsyncMock()
        bus = MemoryBus(mock_registry, mock_time_service, telemetry_service=telemetry)

        assert bus.service_type == ServiceType.MEMORY
        assert bus._telemetry_service == telemetry

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test metrics method."""
        bus = MemoryBus(mock_registry, mock_time_service)

        metrics = bus.get_metrics()

        assert isinstance(metrics, dict)
        assert "memory_operations_total" in metrics
        assert "memory_cache_size" in metrics
        assert "memory_cache_hits" in metrics
        assert "memory_uptime_seconds" in metrics

    async def test_memorize_basic(self, mock_registry, mock_time_service):
        """Test basic memorize operation."""
        bus = MemoryBus(mock_registry, mock_time_service)

        # Mock memory service
        memory_service = AsyncMock()
        memory_service.memorize = AsyncMock(return_value=MagicMock(status="ok"))
        mock_registry.get_services_by_type.return_value = [memory_service]

        # Test memorize
        from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

        node = GraphNode(id="test", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})

        result = await bus.memorize(node)

        memory_service.memorize.assert_called_once()
        assert bus._operations_total > 0


# =============================================================================
# TOOL BUS - Focus on the 26.3% coverage
# =============================================================================


class TestToolBusCoverage:
    """Increase ToolBus coverage from 26.3%"""

    def test_init(self, mock_registry, mock_time_service):
        """Test initialization."""
        bus = ToolBus(mock_registry, mock_time_service)

        assert bus.service_type == ServiceType.TOOL
        assert bus._tools_available == 0
        assert bus._executions_total == 0

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test metrics."""
        bus = ToolBus(mock_registry, mock_time_service)

        # Set some metrics
        bus._tools_available = 5
        bus._executions_total = 100
        bus._execution_errors = 10

        metrics = bus.get_metrics()

        assert isinstance(metrics, dict)
        assert metrics["tool_executions_total"] == 100
        assert metrics["tool_execution_errors"] == 10
        assert metrics["tools_available"] == 5

    async def test_execute_tool(self, mock_registry, mock_time_service):
        """Test tool execution."""
        bus = ToolBus(mock_registry, mock_time_service)

        # Mock tool service
        tool_service = AsyncMock()
        tool_service.execute_tool = AsyncMock(return_value=MagicMock(success=True))
        mock_registry.get_services_by_type.return_value = [tool_service]

        result = await bus.execute_tool("test_tool", {"param": "value"})

        tool_service.execute_tool.assert_called_once()
        assert bus._executions_total > 0


# =============================================================================
# WISE BUS - Focus on increasing from 69.2%
# =============================================================================


class TestWiseBusCoverage:
    """Increase WiseBus coverage from 69.2% to 80%"""

    def test_init(self, mock_registry, mock_time_service):
        """Test initialization."""
        bus = WiseBus(mock_registry, mock_time_service)

        assert bus.service_type == ServiceType.WISE_AUTHORITY
        assert len(bus.PROHIBITED_CAPABILITIES) > 0
        assert "medical" in bus.PROHIBITED_CAPABILITIES[0]

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test metrics."""
        bus = WiseBus(mock_registry, mock_time_service)

        # Set some metrics
        bus._guidance_requests = 100
        bus._deferrals = 20

        metrics = bus.get_metrics()

        assert isinstance(metrics, dict)
        assert metrics["wise_guidance_requests"] == 100
        assert metrics["wise_guidance_deferrals"] == 20

    async def test_check_capability_allowed(self, mock_registry, mock_time_service):
        """Test capability checking."""
        bus = WiseBus(mock_registry, mock_time_service)

        # Test allowed capability
        result = bus._is_capability_allowed("weather_analysis")
        assert result is True

        # Test prohibited capability
        result = bus._is_capability_allowed("medical_diagnosis")
        assert result is False


# =============================================================================
# RUNTIME CONTROL BUS - Already at 81.3%
# =============================================================================


class TestRuntimeControlBusCoverage:
    """Maintain RuntimeControlBus at 81.3%"""

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test metrics."""
        bus = RuntimeControlBus(mock_registry, mock_time_service)

        metrics = bus.get_metrics()

        assert isinstance(metrics, dict)
        assert "runtime_control_commands" in metrics
        assert "runtime_control_uptime_seconds" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
