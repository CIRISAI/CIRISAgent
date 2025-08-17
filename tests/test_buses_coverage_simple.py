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
    service.timestamp = MagicMock(return_value=1234567890.0)  # Return a float for timestamp
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

    async def test_send_message(self, mock_registry, mock_time_service):
        """Test send_message method."""
        bus = CommunicationBus(mock_registry, mock_time_service)

        # Mock service
        service = AsyncMock()
        service.send_message = AsyncMock(return_value=True)
        mock_registry.get_services_by_type.return_value = [service]

        # Test send_message_sync
        result = await bus.send_message_sync("test_channel", "message", "test_handler")

        assert result is True
        assert bus._messages_sent > 0

    async def test_fetch_messages(self, mock_registry, mock_time_service):
        """Test fetch_messages method."""
        bus = CommunicationBus(mock_registry, mock_time_service)

        service = AsyncMock()
        # The service must have get_capabilities method
        service.get_capabilities = MagicMock(return_value=MagicMock(actions=["fetch_messages"]))
        service.fetch_messages = AsyncMock(
            return_value=[{"content": "test", "timestamp": "2024-01-01T00:00:00Z", "author": "user"}]
        )

        # Mock both get_services_by_type and get_service
        mock_registry.get_services_by_type.return_value = [service]
        mock_registry.get_service = AsyncMock(return_value=service)

        messages = await bus.fetch_messages("channel123", 10, "test_handler")

        assert len(messages) == 1
        assert bus._messages_received > 0


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

    async def test_call_llm_structured(self, mock_registry, mock_time_service):
        """Test call_llm_structured method."""
        from pydantic import BaseModel

        from ciris_engine.schemas.runtime.resources import ResourceUsage
        from ciris_engine.schemas.services.capabilities import LLMCapabilities

        class TestModel(BaseModel):
            result: str

        bus = LLMBus(mock_registry, mock_time_service)

        # Mock service with proper capabilities and health
        service = MagicMock()
        # Create a mock that has actions but NOT supports_operation_list (to avoid the first check)
        caps_mock = MagicMock(spec=["actions"])  # spec limits which attributes exist
        caps_mock.actions = [LLMCapabilities.CALL_LLM_STRUCTURED.value]
        service.get_capabilities = MagicMock(return_value=caps_mock)
        service.is_healthy = AsyncMock(return_value=True)
        service.call_llm_structured = AsyncMock(
            return_value=(TestModel(result="success"), ResourceUsage(tokens_used=100))
        )

        # Mock registry to return the service
        mock_registry.get_services_by_type.return_value = [service]

        # Mock get_provider_info to return proper structure for priority lookup
        # The code looks for ServiceType.LLM (the enum) not ServiceType.LLM.value (the string)
        mock_registry.get_provider_info = MagicMock(
            return_value={
                "services": {
                    ServiceType.LLM: [  # Use the enum, not the value
                        {"name": f"TestService_{id(service)}", "priority": "NORMAL", "metadata": {}}
                    ]
                }
            }
        )

        messages = [{"role": "user", "content": "test"}]
        result, usage = await bus.call_llm_structured(messages, TestModel)

        assert result.result == "success"
        assert usage.tokens_used == 100


# =============================================================================
# MEMORY BUS - Focus on the 29.3% coverage
# =============================================================================


class TestMemoryBusCoverage:
    """Increase MemoryBus coverage from 29.3%"""

    def test_init(self, mock_registry, mock_time_service):
        """Test initialization."""
        bus = MemoryBus(mock_registry, mock_time_service)

        assert bus.service_type == ServiceType.MEMORY
        assert bus._operation_count == 0

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test metrics method."""
        bus = MemoryBus(mock_registry, mock_time_service)

        metrics = bus.get_metrics()

        assert isinstance(metrics, dict)
        assert "memory_operations_total" in metrics
        assert "memory_errors_total" in metrics
        assert "memory_broadcasts" in metrics
        assert "memory_uptime_seconds" in metrics

    async def test_memorize_basic(self, mock_registry, mock_time_service):
        """Test basic memorize operation."""
        bus = MemoryBus(mock_registry, mock_time_service)

        # Mock memory service with capabilities
        memory_service = AsyncMock()
        memory_service.get_capabilities = MagicMock(return_value=MagicMock(actions=["memorize"]))
        memory_service.memorize = AsyncMock(return_value=MagicMock(status="ok"))

        # Mock both get_services_by_type and get_service
        mock_registry.get_services_by_type.return_value = [memory_service]
        mock_registry.get_service = AsyncMock(return_value=memory_service)

        # Test memorize
        from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

        node = GraphNode(id="test", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={})

        result = await bus.memorize(node)

        memory_service.memorize.assert_called_once()
        assert bus._operation_count > 0


# =============================================================================
# TOOL BUS - Focus on the 26.3% coverage
# =============================================================================


class TestToolBusCoverage:
    """Increase ToolBus coverage from 26.3%"""

    def test_init(self, mock_registry, mock_time_service):
        """Test initialization."""
        bus = ToolBus(mock_registry, mock_time_service)

        assert bus.service_type == ServiceType.TOOL
        assert bus._executions_count == 0
        assert bus._errors_count == 0

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test metrics."""
        bus = ToolBus(mock_registry, mock_time_service)

        # Set some metrics
        bus._cached_tools_count = 5
        bus._executions_count = 100
        bus._errors_count = 10

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
        tool_service.get_available_tools = AsyncMock(return_value=["test_tool", "other_tool"])
        tool_service.execute_tool = AsyncMock(return_value=MagicMock(success=True))

        # Mock registry to return our service
        mock_registry.get_services_by_type.return_value = [tool_service]
        # Also mock the internal _services attribute that ToolBus checks
        mock_registry._services = {ServiceType.TOOL: [MagicMock(instance=tool_service)]}

        result = await bus.execute_tool("test_tool", {"param": "value"})

        tool_service.execute_tool.assert_called_once()
        assert bus._executions_count > 0


# =============================================================================
# WISE BUS - Focus on increasing from 69.2%
# =============================================================================


class TestWiseBusCoverage:
    """Increase WiseBus coverage from 69.2% to 80%"""

    def test_init(self, mock_registry, mock_time_service):
        """Test initialization."""
        bus = WiseBus(mock_registry, mock_time_service)

        assert bus.service_type == ServiceType.WISE_AUTHORITY
        assert bus.PROHIBITED_CAPABILITIES is not None
        # PROHIBITED_CAPABILITIES is a dict of categories with sets of capabilities
        assert isinstance(bus.PROHIBITED_CAPABILITIES, dict)
        # Check that medical capabilities are prohibited
        assert "MEDICAL" in bus.PROHIBITED_CAPABILITIES

    def test_get_metrics(self, mock_registry, mock_time_service):
        """Test metrics."""
        bus = WiseBus(mock_registry, mock_time_service)

        # Set some metrics
        bus._requests_count = 100
        bus._deferrals_count = 20

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

        # Test prohibited capability - use one that's actually in the flattened set
        # We need to check against actual capabilities in the PROHIBITED_CAPABILITIES dict
        # "diagnosis" is in MEDICAL_CAPABILITIES
        result = bus._is_capability_allowed("diagnosis")
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
