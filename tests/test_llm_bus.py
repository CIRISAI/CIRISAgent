"""
Comprehensive tests for LLM Bus architecture

Tests:
- Multi-provider scenarios
- Provider failover mechanisms
- Load distribution strategies (round-robin, latency-based, random, least-loaded)
- Circuit breaker functionality
- Health checks
- Service registration/deregistration
- Priority-based selection
- Thread safety and concurrent access patterns
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import List, Tuple, Type
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.logic.registries.circuit_breaker import CircuitState
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage


class MockResponseModel(BaseModel):
    """Mock response model for testing (not a test class - renamed to avoid pytest collection)"""

    message: str
    confidence: float = 1.0


class MockTimeService:
    """Mock time service for testing"""

    def __init__(self):
        self.current_time = datetime.now(timezone.utc)
        self.frozen = False

    def now(self) -> datetime:
        if self.frozen:
            return self.current_time
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        return self.now().timestamp()

    def freeze(self, dt: datetime = None):
        self.frozen = True
        if dt:
            self.current_time = dt

    def advance(self, seconds: float):
        if self.frozen:
            self.current_time += timedelta(seconds=seconds)


class MockLLMService:
    """Mock LLM service for testing"""

    def __init__(self, name: str, latency_ms: float = 100, failure_rate: float = 0.0):
        self.name = name
        self.latency_ms = latency_ms
        self.failure_rate = failure_rate
        self.call_count = 0
        self.healthy = True
        self.capabilities = ["call_llm_structured", "get_available_models"]

    async def call_llm_structured(
        self,
        messages: List[dict],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Simulate LLM call with configurable latency and failure"""
        self.call_count += 1

        # Simulate latency
        await asyncio.sleep(self.latency_ms / 1000)

        # Simulate failures
        if random.random() < self.failure_rate:
            raise RuntimeError(f"{self.name} simulated failure")

        # Return test response
        response = MockResponseModel(message=f"Response from {self.name}")
        usage = ResourceUsage(
            tokens_used=100,
            tokens_input=50,
            tokens_output=50,
            cost_cents=0.01,
            model_used=f"{self.name}-model",
            carbon_grams=0.001,
            energy_kwh=0.0001,
        )

        return response, usage

    async def is_healthy(self) -> bool:
        return self.healthy

    async def get_available_models(self) -> List[str]:
        return [f"{self.name}-model-1", f"{self.name}-model-2"]

    def get_capabilities(self):
        """Return capabilities object"""

        class Capabilities:
            supports_operation_list = ["call_llm_structured", "get_available_models"]

        return Capabilities()


class MockTelemetryService:
    """Mock telemetry service for testing"""

    def __init__(self):
        self.metrics = []

    async def record_metric(self, metric_name: str, value: float, handler_name: str, tags: dict = None):
        self.metrics.append({"name": metric_name, "value": value, "handler": handler_name, "tags": tags or {}})


@pytest.fixture
def time_service():
    """Provide mock time service"""
    return MockTimeService()


@pytest.fixture
def telemetry_service():
    """Provide mock telemetry service"""
    return MockTelemetryService()


@pytest.fixture(scope="function")
def service_registry():
    """Provide service registry with isolated scope per test"""
    return ServiceRegistry()


@pytest.fixture
def llm_bus(service_registry, time_service, telemetry_service):
    """Provide LLM bus instance"""
    bus = LLMBus(
        service_registry=service_registry,
        time_service=time_service,
        telemetry_service=telemetry_service,
        distribution_strategy=DistributionStrategy.ROUND_ROBIN,
        circuit_breaker_config={"failure_threshold": 3, "recovery_timeout": 5.0, "half_open_max_calls": 2},
    )
    # Clear any existing state
    bus.clear_circuit_breakers()
    return bus


class TestLLMBusBasics:
    """Test basic LLM bus functionality"""

    @pytest.mark.asyncio
    async def test_single_provider_success(self, llm_bus, service_registry):
        """Test successful call with single provider"""
        # Register a mock LLM service
        mock_service = MockLLMService("TestLLM", latency_ms=50)
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=mock_service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},  # Mark as mock provider
        )

        # Make a call
        messages = [{"role": "user", "content": "Test"}]
        result, usage = await llm_bus.call_llm_structured(
            messages=messages, response_model=MockResponseModel, handler_name="test"
        )

        assert isinstance(result, MockResponseModel)
        assert result.message == "Response from TestLLM"
        assert usage.tokens_used == 100
        assert mock_service.call_count == 1

    @pytest.mark.asyncio
    async def test_no_providers_error(self, llm_bus):
        """Test error when no providers available"""
        with pytest.raises(RuntimeError, match="No LLM services available"):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel, handler_name="test"
            )

    @pytest.mark.asyncio
    async def test_circuit_breaker_skips_to_lower_priority(self, llm_bus, service_registry):
        """Test that services with open circuit breakers are skipped in favor of lower priority services"""
        # Register healthy and unhealthy services
        healthy_service = MockLLMService("HealthyLLM")
        failing_service = MockLLMService("FailingLLM", failure_rate=1.0)

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=failing_service,
            priority=Priority.HIGH,  # Higher priority but will fail
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=healthy_service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )

        # Make a call - should try high priority, fail, then use normal priority
        result, _ = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel
        )

        assert result.message == "Response from HealthyLLM"
        assert failing_service.call_count == 1  # High priority tried once per retry config (1 retry)
        assert healthy_service.call_count == 1  # Normal priority succeeded


class TestDistributionStrategies:
    """Test different load distribution strategies"""

    @pytest.mark.asyncio
    async def test_round_robin_distribution(self, service_registry, time_service, telemetry_service):
        """Test round-robin distribution across providers"""
        # Create bus with round-robin strategy
        bus = LLMBus(
            service_registry=service_registry,
            time_service=time_service,
            telemetry_service=telemetry_service,
            distribution_strategy=DistributionStrategy.ROUND_ROBIN,
        )

        # Register multiple services at same priority
        services = [MockLLMService(f"LLM-{i}") for i in range(3)]
        for service in services:
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                capabilities=["call_llm_structured"],
                metadata={"provider": "mock"},
            )

        # Make multiple calls
        for i in range(6):
            result, _ = await bus.call_llm_structured(
                messages=[{"role": "user", "content": f"Test {i}"}], response_model=MockResponseModel
            )
            # Should cycle through services
            expected_service = services[i % 3]
            assert result.message == f"Response from {expected_service.name}"

        # Check call counts
        for service in services:
            assert service.call_count == 2

    @pytest.mark.asyncio
    async def test_latency_based_distribution(self, service_registry, time_service, telemetry_service):
        """Test latency-based distribution"""
        # Create bus with latency-based strategy
        bus = LLMBus(
            service_registry=service_registry,
            time_service=time_service,
            telemetry_service=telemetry_service,
            distribution_strategy=DistributionStrategy.LATENCY_BASED,
        )

        # Register services with different latencies
        fast_service = MockLLMService("FastLLM", latency_ms=10)
        slow_service = MockLLMService("SlowLLM", latency_ms=200)

        for service in [fast_service, slow_service]:
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                capabilities=["call_llm_structured"],
                metadata={"provider": "mock"},
            )

        # Make initial calls to build up latency metrics
        for i in range(2):
            await bus.call_llm_structured(
                messages=[{"role": "user", "content": f"Test warmup {i}"}], response_model=MockResponseModel
            )

        # Reset call counts
        initial_fast_count = fast_service.call_count
        initial_slow_count = slow_service.call_count

        # Subsequent calls should prefer fast service based on latency
        fast_service_calls = 0
        for i in range(5):
            result, _ = await bus.call_llm_structured(
                messages=[{"role": "user", "content": f"Test {i+2}"}], response_model=MockResponseModel
            )
            if "FastLLM" in result.message:
                fast_service_calls += 1

        # Fast service should get most of the calls after warmup
        assert fast_service_calls >= 4  # At least 4 out of 5 calls

    @pytest.mark.asyncio
    async def test_least_loaded_distribution(self, service_registry, time_service, telemetry_service):
        """Test least-loaded distribution strategy"""
        # Create bus with least-loaded strategy
        bus = LLMBus(
            service_registry=service_registry,
            time_service=time_service,
            telemetry_service=telemetry_service,
            distribution_strategy=DistributionStrategy.LEAST_LOADED,
        )

        # Register multiple services
        services = [MockLLMService(f"LLM-{i}") for i in range(3)]
        for service in services:
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                capabilities=["call_llm_structured"],
                metadata={"provider": "mock"},
            )

        # Make calls - should distribute evenly
        for i in range(6):
            await bus.call_llm_structured(
                messages=[{"role": "user", "content": f"Test {i}"}], response_model=MockResponseModel
            )

        # All services should have equal call counts
        assert all(s.call_count == 2 for s in services)


class TestCircuitBreaker:
    """Test circuit breaker functionality"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_on_failures(self, llm_bus, service_registry, time_service):
        """Test circuit breaker opens after threshold failures"""
        # Register a failing service
        failing_service = MockLLMService("FailingLLM", failure_rate=1.0)
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=failing_service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )
        # Try multiple calls - should fail
        for i in range(3):
            with pytest.raises(RuntimeError, match="All LLM services failed"):
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": f"Test {i}"}], response_model=MockResponseModel
                )

        # Circuit breaker should be open
        cb = llm_bus.circuit_breakers[f"MockLLMService_{id(failing_service)}"]
        assert cb.state == CircuitState.OPEN

        # Further calls should fail immediately without calling service
        initial_count = failing_service.call_count
        with pytest.raises(RuntimeError):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel
            )
        assert failing_service.call_count == initial_count  # No new calls

    @pytest.mark.asyncio
    async def test_circuit_breaker_recovery(self, llm_bus, service_registry, time_service):
        """Test circuit breaker recovery after timeout"""
        # Use real time patching since circuit breaker uses time.time()
        import time as time_module

        # Register service that fails initially then recovers
        service = MockLLMService("RecoveringLLM")
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )

        # Cause failures to open circuit
        service.failure_rate = 1.0
        for i in range(3):
            with pytest.raises(RuntimeError):
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": f"Test {i}"}], response_model=MockResponseModel
                )

        # Verify circuit is open
        cb = llm_bus.circuit_breakers[f"MockLLMService_{id(service)}"]
        assert cb.state == CircuitState.OPEN

        # Service recovers
        service.failure_rate = 0.0

        # Mock time to simulate recovery timeout passing
        original_time = time_module.time
        with patch("time.time", return_value=original_time() + 6.0):
            # Circuit should allow half-open attempts
            result, _ = await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "Test recovery"}], response_model=MockResponseModel
            )

            assert result.message == "Response from RecoveringLLM"

            # After successful calls, circuit should close
            for i in range(2):
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": f"Test {i}"}], response_model=MockResponseModel
                )

            assert cb.state == CircuitState.CLOSED


class TestPriorityFailover:
    """Test priority-based failover mechanisms"""

    @pytest.mark.asyncio
    async def test_failover_by_priority(self, llm_bus, service_registry):
        """Test failover from high to low priority providers"""
        # Register services at different priorities
        high_priority = MockLLMService("HighPriority", failure_rate=1.0)
        normal_priority = MockLLMService("NormalPriority", failure_rate=0.0)
        low_priority = MockLLMService("LowPriority", failure_rate=0.0)

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=high_priority,
            priority=Priority.HIGH,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=normal_priority,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=low_priority,
            priority=Priority.LOW,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )

        # Call should try high priority first, fail, then use normal priority
        result, _ = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel
        )

        assert result.message == "Response from NormalPriority"
        assert high_priority.call_count == 1  # Tried once per retry config (1 retry)
        assert normal_priority.call_count == 1  # Succeeded
        assert low_priority.call_count == 0  # Not needed

    @pytest.mark.asyncio
    async def test_all_priorities_fail(self, llm_bus, service_registry, caplog):
        """Test error when all priority levels fail, and verify log verbosity reduction"""
        import logging

        caplog.set_level(logging.WARNING)  # Capture both WARNING and ERROR

        # Register failing services at all priorities
        for priority in [Priority.HIGH, Priority.NORMAL, Priority.LOW]:
            service = MockLLMService(f"{priority.name}LLM", failure_rate=1.0)
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=priority,
                capabilities=["call_llm_structured"],
                metadata={"provider": "mock"},
            )

        # First call - should log full errors for each service
        with pytest.raises(RuntimeError, match="All LLM services failed"):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel
            )

        # Count ERROR level logs from first attempt (one per service after retries)
        first_error_count = sum(1 for record in caplog.records if record.levelname == "ERROR")
        assert first_error_count == 3, "Should have 3 ERROR logs (one per failing service after retries)"

        # Clear log capture
        caplog.clear()

        # Second call - should log warnings instead of full errors (log verbosity reduction)
        with pytest.raises(RuntimeError, match="All LLM services failed"):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel
            )

        # Second attempt should have 0 ERROR logs (all converted to WARNING due to log dedup)
        second_error_count = sum(1 for record in caplog.records if record.levelname == "ERROR")
        second_warning_count = sum(1 for record in caplog.records if record.levelname == "WARNING")

        assert second_error_count == 0, "Should have 0 ERROR logs on repeated failures"
        # With 1 retry: 3 services × (1 exhausted warning + 1 repeated warning) = 6
        assert second_warning_count == 6, "Should have 6 WARNING logs (2 per service with 1 retry)"


class TestConcurrentAccess:
    """Test thread safety and concurrent access patterns"""

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, llm_bus, service_registry):
        """Test multiple concurrent requests"""
        # Register multiple services
        services = [MockLLMService(f"LLM-{i}", latency_ms=50) for i in range(3)]
        for service in services:
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                capabilities=["call_llm_structured"],
                metadata={"provider": "mock"},
            )
        # Make concurrent requests
        tasks = []
        for i in range(10):
            task = llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": f"Concurrent test {i}"}], response_model=MockResponseModel
            )
            tasks.append(task)

        # Wait for all to complete
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert len(results) == 10
        for result, _ in results:
            assert isinstance(result, MockResponseModel)

        # Calls should be distributed
        total_calls = sum(s.call_count for s in services)
        assert total_calls == 10

    @pytest.mark.asyncio
    async def test_concurrent_registration(self, llm_bus, service_registry):
        """Test concurrent service registration"""

        async def register_service(name: str, delay: float):
            await asyncio.sleep(delay)
            service = MockLLMService(name)
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                capabilities=["call_llm_structured"],
                metadata={"provider": "mock"},
            )
            return service

        # Register services concurrently
        tasks = [register_service(f"Concurrent-{i}", i * 0.01) for i in range(5)]
        services = await asyncio.gather(*tasks)

        # All should be registered
        assert len(services) == 5

        # Should be able to use any of them
        result, _ = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel
        )
        assert "Concurrent" in result.message


class TestTelemetry:
    """Test telemetry and metrics collection"""

    @pytest.mark.asyncio
    async def test_telemetry_recording(self, llm_bus, service_registry):
        """Test that telemetry is properly recorded"""
        # Register service
        service = MockLLMService("TelemetryLLM")
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )
        # Make calls
        for i in range(3):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": f"Test {i}"}],
                response_model=MockResponseModel,
                handler_name="test_handler",
            )

        # Check telemetry
        telemetry = llm_bus.telemetry_service
        assert len(telemetry.metrics) > 0

        # Should have token, cost, latency metrics
        metric_names = {m["name"] for m in telemetry.metrics}
        assert "llm.tokens.total" in metric_names
        assert "llm.tokens.input" in metric_names
        assert "llm.tokens.output" in metric_names
        assert "llm.cost.cents" in metric_names
        assert "llm.latency.ms" in metric_names

        # Check tags
        for metric in telemetry.metrics:
            if metric["name"] == "llm.tokens.total":
                assert metric["handler"] == "test_handler"
                assert metric["tags"]["service"] == f"MockLLMService_{id(service)}"
                assert metric["tags"]["model"] == "TelemetryLLM-model"

    @pytest.mark.asyncio
    async def test_service_stats(self, llm_bus, service_registry):
        """Test service statistics tracking"""
        # Register services
        fast_service = MockLLMService("Fast", latency_ms=10)
        slow_service = MockLLMService("Slow", latency_ms=100, failure_rate=0.2)

        for service in [fast_service, slow_service]:
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                capabilities=["call_llm_structured"],
                metadata={"provider": "mock"},
            )
        # Make multiple calls
        success_count = 0
        failure_count = 0
        for i in range(10):
            try:
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": f"Test {i}"}], response_model=MockResponseModel
                )
                success_count += 1
            except RuntimeError:
                failure_count += 1

        # Get stats
        stats = llm_bus.get_service_stats()

        # Should have stats for both services
        assert len(stats) >= 2

        # Check stats structure
        for service_name, service_stats in stats.items():
            assert "total_requests" in service_stats
            assert "failed_requests" in service_stats
            assert "failure_rate" in service_stats
            assert "average_latency_ms" in service_stats
            assert "circuit_breaker_state" in service_stats


class TestMessageNormalization:
    """Test message normalization and None value filtering"""

    @pytest.mark.asyncio
    async def test_none_values_stripped_from_llm_messages(self, llm_bus, service_registry):
        """Test that None values are stripped from LLMMessage objects during normalization"""
        from ciris_engine.schemas.services.llm import LLMMessage

        # Register a mock service that can inspect the messages it receives
        received_messages = []

        class InspectingLLMService(MockLLMService):
            async def call_llm_structured(
                self,
                messages: List[dict],
                response_model: Type[BaseModel],
                max_tokens: int = 1024,
                temperature: float = 0.0,
                **kwargs,
            ) -> Tuple[BaseModel, ResourceUsage]:
                # Capture the messages for inspection
                received_messages.extend(messages)
                return await super().call_llm_structured(messages, response_model, max_tokens, temperature, **kwargs)

        service = InspectingLLMService("Inspector")
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )

        # Create LLMMessage with name=None (default)
        messages = [
            LLMMessage(role="system", content="You are a helpful assistant"),  # name will be None by default
            LLMMessage(role="user", content="Hello"),
        ]

        # Make the call
        await llm_bus.call_llm_structured(messages=messages, response_model=MockResponseModel)

        # Verify messages were normalized and None values were stripped
        assert len(received_messages) == 2
        for msg in received_messages:
            assert "role" in msg
            assert "content" in msg
            # name field should NOT be present if it was None
            assert "name" not in msg or msg["name"] is not None

    @pytest.mark.asyncio
    async def test_none_values_stripped_from_dict_messages(self, llm_bus, service_registry):
        """Test that None values are stripped from dict messages during normalization"""
        received_messages = []

        class InspectingLLMService(MockLLMService):
            async def call_llm_structured(
                self,
                messages: List[dict],
                response_model: Type[BaseModel],
                max_tokens: int = 1024,
                temperature: float = 0.0,
                **kwargs,
            ) -> Tuple[BaseModel, ResourceUsage]:
                received_messages.extend(messages)
                return await super().call_llm_structured(messages, response_model, max_tokens, temperature, **kwargs)

        service = InspectingLLMService("Inspector")
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock"},
        )

        # Create dict messages with None values
        messages = [
            {"role": "system", "content": "You are helpful", "name": None},  # name is explicitly None
            {"role": "user", "content": "Test", "name": None},
        ]

        # Make the call
        await llm_bus.call_llm_structured(messages=messages, response_model=MockResponseModel)

        # Verify None values were stripped
        assert len(received_messages) == 2
        for msg in received_messages:
            assert "role" in msg
            assert "content" in msg
            assert "name" not in msg  # None values should be stripped


class TestEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_capability_filtering(self, llm_bus, service_registry):
        """Test that services are filtered by capabilities"""
        # Register service without required capability
        limited_service = MockLLMService("Limited")
        limited_service.capabilities = ["other_capability"]

        # Override get_capabilities to return limited capabilities
        def limited_get_capabilities():
            class Capabilities:
                supports_operation_list = ["other_capability"]

            return Capabilities()

        limited_service.get_capabilities = limited_get_capabilities

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=limited_service,
            capabilities=["other_capability"],
            metadata={"provider": "mock"},
        )

        # Should fail as no service has call_llm_structured capability
        with pytest.raises(RuntimeError, match="No LLM services available"):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=MockResponseModel
            )

    @pytest.mark.asyncio
    async def test_get_available_models(self, llm_bus, service_registry):
        """Test getting available models from services"""
        # Register service
        service = MockLLMService("ModelProvider")
        service_registry.register_service(
            service_type=ServiceType.LLM, provider=service, capabilities=["get_available_models"]
        )

        # Get models
        models = await llm_bus.get_available_models()

        assert len(models) == 2
        assert "ModelProvider-model-1" in models
        assert "ModelProvider-model-2" in models

    @pytest.mark.asyncio
    async def test_bus_lifecycle(self, llm_bus):
        """Test bus start/stop lifecycle"""
        # Start the bus
        await llm_bus.start()
        assert llm_bus._running

        # Stop the bus
        await llm_bus.stop()
        assert not llm_bus._running

        # Start again
        await llm_bus.start()
        assert llm_bus._running

        # Double start should be safe
        await llm_bus.start()
        assert llm_bus._running

        # Clean stop
        await llm_bus.stop()

    @pytest.mark.asyncio
    async def test_security_mock_real_mixing(self, service_registry, time_service, telemetry_service):
        """Test that mixing mock and real LLM services is prevented"""
        bus = LLMBus(service_registry=service_registry, time_service=time_service, telemetry_service=telemetry_service)

        # Register mock service
        mock_service = MockLLMService("MockLLM")
        service_registry.register_service(
            service_type=ServiceType.LLM, provider=mock_service, metadata={"provider": "mock"}
        )

        # Try to register real service - should fail
        # Create a class without "Mock" in the name
        class RealLLMService:
            def __init__(self, name):
                self.name = name

        real_service = RealLLMService("RealLLM")
        with pytest.raises(RuntimeError, match="SECURITY VIOLATION"):
            service_registry.register_service(
                service_type=ServiceType.LLM, provider=real_service, metadata={"provider": "openai"}
            )


class TestServiceUnavailableFailover:
    """Test failover specifically for 503 Service Unavailable scenarios."""

    @pytest.mark.asyncio
    async def test_503_error_triggers_failover_to_secondary_provider(self, llm_bus, service_registry):
        """Test that 503 Service Unavailable from primary triggers immediate failover to secondary."""

        # Create primary service that fails with 503-like errors
        class ServiceUnavailableLLMService(MockLLMService):
            def __init__(self, name):
                super().__init__(name)
                self.should_fail = True

            async def call_llm_structured(self, messages, response_model, max_tokens=1024, temperature=0.0, **kwargs):
                self.call_count += 1  # Track calls even if they fail
                if self.should_fail:
                    # Simulate the same type of error that would cause circuit breaker activation
                    raise RuntimeError("LLM service unavailable - circuit breaker activated for failover")
                return await super().call_llm_structured(messages, response_model, max_tokens, temperature, **kwargs)

        # Create secondary service that always succeeds
        primary_service = ServiceUnavailableLLMService("Together.AI")
        secondary_service = MockLLMService("Lambda.AI")

        # Register primary with high priority - mark as mock to avoid security conflicts
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=primary_service,
            priority=Priority.HIGH,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock", "domain": "general", "original_provider": "together"},
        )

        # Register secondary with normal priority - mark as mock to avoid security conflicts
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=secondary_service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock", "domain": "general", "original_provider": "lambda"},
        )

        # First call should fail on primary, succeed on secondary
        result, usage = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Test failover"}], response_model=MockResponseModel
        )

        # Should get response from secondary service
        assert result.message == "Response from Lambda.AI"
        assert primary_service.call_count == 1  # Primary tried once per retry config (1 retry)
        assert secondary_service.call_count == 1  # Secondary provided the response

        # Trigger enough failures to open circuit breaker (default threshold is 5)
        primary_service.call_count = 0
        secondary_service.call_count = 0

        # Make 4 more calls to reach the failure threshold
        for i in range(4):
            try:
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": f"Trigger failure {i}"}], response_model=MockResponseModel
                )
            except:
                pass  # Expected to succeed on secondary after primary fails

        # Verify circuit breaker opened for primary service
        primary_service_name = f"ServiceUnavailableLLMService_{id(primary_service)}"
        assert primary_service_name in llm_bus.circuit_breakers

        # Reset counts and test circuit breaker behavior
        primary_service.call_count = 0
        secondary_service.call_count = 0

        result2, usage2 = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Test circuit breaker"}], response_model=MockResponseModel
        )

        assert result2.message == "Response from Lambda.AI"
        assert primary_service.call_count == 0  # Primary was skipped due to circuit breaker
        assert secondary_service.call_count == 1  # Only secondary was called

    @pytest.mark.asyncio
    async def test_both_providers_503_error_propagates(self, llm_bus, service_registry):
        """Test that when both providers fail with 503, the error is properly propagated."""

        class FailingLLMService(MockLLMService):
            async def call_llm_structured(self, messages, response_model, max_tokens=1024, temperature=0.0, **kwargs):
                self.call_count += 1  # Track calls even if they fail
                raise RuntimeError("LLM service unavailable - circuit breaker activated for failover")

        # Register two failing services
        primary_service = FailingLLMService("Together.AI")
        secondary_service = FailingLLMService("Lambda.AI")

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=primary_service,
            priority=Priority.HIGH,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock", "original_provider": "together"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=secondary_service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock", "original_provider": "lambda"},
        )

        # Should fail with appropriate error after trying both providers
        with pytest.raises(RuntimeError) as exc_info:
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "Test all failing"}], response_model=MockResponseModel
            )

        # Should indicate all services failed
        assert "All LLM services failed" in str(exc_info.value)

        # Both services should have been tried (1 retry each per config)
        assert primary_service.call_count == 1
        assert secondary_service.call_count == 1

    @pytest.mark.asyncio
    async def test_primary_recovery_after_503_failover(self, llm_bus, service_registry, time_service):
        """Test that primary service can recover after 503 errors and circuit breaker recovery."""

        class RecoverableLLMService(MockLLMService):
            def __init__(self, name):
                super().__init__(name)
                self.should_fail = True

            async def call_llm_structured(self, messages, response_model, max_tokens=1024, temperature=0.0, **kwargs):
                if self.should_fail:
                    self.call_count += 1  # Track calls that fail
                    raise RuntimeError("LLM service unavailable - circuit breaker activated for failover")
                return await super().call_llm_structured(messages, response_model, max_tokens, temperature, **kwargs)

        primary_service = RecoverableLLMService("Together.AI")
        secondary_service = MockLLMService("Lambda.AI")

        # Register services - mark as mock to avoid security conflicts
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=primary_service,
            priority=Priority.HIGH,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock", "original_provider": "together"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=secondary_service,
            priority=Priority.NORMAL,
            capabilities=["call_llm_structured"],
            metadata={"provider": "mock", "original_provider": "lambda"},
        )

        # Initial call fails over to secondary
        result1, _ = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Initial call"}], response_model=MockResponseModel
        )
        assert result1.message == "Response from Lambda.AI"

        # Primary service recovers
        primary_service.should_fail = False

        # Simulate circuit breaker recovery timeout
        primary_service_name = f"RecoverableLLMService_{id(primary_service)}"
        cb = llm_bus.circuit_breakers[primary_service_name]

        # Manually trigger circuit breaker recovery for testing
        cb.reset()

        # Next call should try primary again and succeed
        primary_service.call_count = 0
        secondary_service.call_count = 0

        result2, _ = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Recovery test"}], response_model=MockResponseModel
        )

        assert result2.message == "Response from Together.AI"
        assert primary_service.call_count == 1  # Primary was called and succeeded
        assert secondary_service.call_count == 0  # Secondary wasn't needed
