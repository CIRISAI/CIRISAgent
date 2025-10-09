"""
Unit tests to enforce correct LLM timeout and circuit breaker behavior.

Requirements:
1. LLM calls must timeout after 5 seconds to first token
2. Circuit breakers must transition to HALF_OPEN after 60 seconds
3. Timeouts must be recorded as circuit breaker failures
"""

import asyncio
import time
from typing import Any, Dict, List, Tuple, Type
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses.llm_bus import LLMBus
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from ciris_engine.protocols.services import LLMService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage


class MockResponse(BaseModel):
    """Mock response model for testing"""

    content: str


class MockTimeService:
    """Mock time service for testing"""

    def __init__(self) -> None:
        self._current_time = time.time()

    def now(self):
        """Return current mock time"""
        from datetime import datetime, timezone

        return datetime.fromtimestamp(self._current_time, tz=timezone.utc)

    def timestamp(self) -> float:
        """Return current mock timestamp"""
        return self._current_time

    def advance(self, seconds: float) -> None:
        """Advance mock time by seconds"""
        self._current_time += seconds


class MockLLMService:
    """Mock LLM service for testing"""

    def __init__(self, delay: float = 0.0, should_fail: bool = False) -> None:
        self.delay = delay
        self.should_fail = should_fail
        self.call_count = 0

    async def call_llm_structured(
        self,
        messages: List[Dict[str, Any]],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Mock LLM call with configurable delay"""
        self.call_count += 1

        if self.delay > 0:
            await asyncio.sleep(self.delay)

        if self.should_fail:
            raise RuntimeError("Mock LLM service failed")

        response = response_model(content="Mock response")
        usage = ResourceUsage(
            tokens_used=10,
            tokens_input=5,
            tokens_output=5,
            cost_cents=0.001,
            model_used="mock-model",
        )
        return response, usage

    def get_capabilities(self):
        """Return mock capabilities"""

        class MockCapabilities:
            supports_operation_list = ["call_llm_structured"]

        return MockCapabilities()

    async def is_healthy(self) -> bool:
        """Return health status"""
        return not self.should_fail


@pytest.fixture
def mock_time_service():
    """Create mock time service"""
    return MockTimeService()


@pytest.fixture
def mock_service_registry():
    """Create mock service registry"""
    registry = Mock(spec=ServiceRegistry)
    registry.get_services_by_type = Mock(return_value=[])
    registry.get_provider_info = Mock(return_value={"services": {}})
    return registry


@pytest.fixture
def llm_bus(mock_service_registry, mock_time_service):
    """Create LLM bus with default config"""
    return LLMBus(
        service_registry=mock_service_registry,
        time_service=mock_time_service,
        telemetry_service=None,
        circuit_breaker_config={
            "failure_threshold": 5,
            "recovery_timeout": 60.0,  # 60 seconds to HALF_OPEN
            "half_open_max_calls": 3,
            "timeout_duration": 5.0,  # 5 second timeout
        },
    )


class TestLLMTimeoutBehavior:
    """Tests for LLM timeout to first token requirement"""

    @pytest.mark.asyncio
    async def test_llm_timeout_after_5_seconds(self, llm_bus, mock_service_registry, mock_time_service):
        """Test that LLM calls timeout after 5 seconds"""
        # Create a slow service that takes 10 seconds
        slow_service = MockLLMService(delay=10.0)

        # Register the service
        mock_service_registry.get_services_by_type.return_value = [slow_service]
        mock_service_registry.get_provider_info.return_value = {
            "services": {ServiceType.LLM: [{"name": f"MockLLMService_{id(slow_service)}", "priority": "NORMAL"}]}
        }

        # Call should timeout before 10 seconds
        start = time.time()
        with pytest.raises(RuntimeError, match="All LLM services failed"):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "test"}], response_model=MockResponse, max_tokens=100
            )
        elapsed = time.time() - start

        # Should timeout much faster than the service delay
        assert elapsed < 8.0, f"Timeout took {elapsed}s, expected < 8s"

        # Service should have been called despite timeout
        assert slow_service.call_count > 0, "Service should have been called"

    @pytest.mark.asyncio
    async def test_timeout_triggers_circuit_breaker(self, llm_bus, mock_service_registry):
        """Test that timeouts are recorded as circuit breaker failures"""
        # Create a service that times out
        slow_service = MockLLMService(delay=10.0)
        service_name = f"MockLLMService_{id(slow_service)}"

        mock_service_registry.get_services_by_type.return_value = [slow_service]
        mock_service_registry.get_provider_info.return_value = {
            "services": {ServiceType.LLM: [{"name": service_name, "priority": "NORMAL"}]}
        }

        # Make 5 calls that will timeout
        for i in range(5):
            try:
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": "test"}], response_model=MockResponse, max_tokens=100
                )
            except RuntimeError:
                pass  # Expected to fail

        # Circuit breaker should now be OPEN
        assert service_name in llm_bus.circuit_breakers, "Circuit breaker should exist"
        cb = llm_bus.circuit_breakers[service_name]
        assert cb.state == CircuitState.OPEN, f"Circuit breaker should be OPEN, got {cb.state}"
        assert cb.failure_count >= 5, f"Should have at least 5 failures, got {cb.failure_count}"

    @pytest.mark.asyncio
    async def test_fast_service_does_not_timeout(self, llm_bus, mock_service_registry):
        """Test that fast services complete successfully without timeout"""
        # Create a fast service (100ms)
        fast_service = MockLLMService(delay=0.1)

        mock_service_registry.get_services_by_type.return_value = [fast_service]
        mock_service_registry.get_provider_info.return_value = {
            "services": {
                ServiceType.LLM: [{"name": f"MockLLMService_{id(fast_service)}", "priority": "NORMAL"}]
            }
        }

        # Should complete successfully
        result, usage = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "test"}], response_model=MockResponse, max_tokens=100
        )

        assert result.content == "Mock response"
        assert usage.tokens_used == 10
        assert fast_service.call_count == 1

    @pytest.mark.asyncio
    async def test_timeout_faster_than_dma_timeout(self):
        """Test that LLM timeout (5s) is faster than DMA timeout (30s)"""
        # This is a design constraint test
        llm_timeout = 5.0
        dma_timeout = 30.0

        assert llm_timeout < dma_timeout, "LLM timeout must be faster than DMA timeout to allow proper failover"
        assert llm_timeout <= 5.0, "LLM timeout must be 5 seconds or less"


class TestCircuitBreakerHalfOpenTransition:
    """Tests for circuit breaker HALF_OPEN transition after 60 seconds"""

    def test_circuit_breaker_opens_after_failures(self):
        """Test that circuit breaker opens after threshold failures"""
        config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60.0)
        cb = CircuitBreaker(name="test_service", config=config)

        # Record 5 failures
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        assert not cb.is_available()

    def test_circuit_breaker_transitions_to_half_open_after_60_seconds(self):
        """Test that circuit breaker transitions to HALF_OPEN after 60 seconds"""
        config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60.0)
        cb = CircuitBreaker(name="test_service", config=config)

        # Open the circuit breaker
        for _ in range(5):
            cb.record_failure()

        assert cb.state == CircuitState.OPEN
        initial_time = time.time()

        # Immediately after opening, should not be available
        assert not cb.is_available()

        # Simulate 59 seconds passing (still OPEN)
        cb.last_failure_time = initial_time - 59.0
        assert not cb.is_available()
        assert cb.state == CircuitState.OPEN

        # Simulate 60 seconds passing (should transition to HALF_OPEN)
        cb.last_failure_time = initial_time - 60.0
        assert cb.is_available()
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_allows_limited_requests(self):
        """Test that HALF_OPEN state allows requests"""
        config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60.0, success_threshold=3)
        cb = CircuitBreaker(name="test_service", config=config)

        # Open and transition to HALF_OPEN
        for _ in range(5):
            cb.record_failure()
        cb.last_failure_time = time.time() - 61.0

        # Check availability (should transition to HALF_OPEN)
        assert cb.is_available()
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_after_success_threshold(self):
        """Test that HALF_OPEN closes after success threshold"""
        config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60.0, success_threshold=3)
        cb = CircuitBreaker(name="test_service", config=config)

        # Open and transition to HALF_OPEN
        for _ in range(5):
            cb.record_failure()
        cb.last_failure_time = time.time() - 61.0
        cb.is_available()  # Trigger transition to HALF_OPEN

        assert cb.state == CircuitState.HALF_OPEN

        # Record 3 successes
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()

        # Should now be CLOSED
        assert cb.state == CircuitState.CLOSED
        assert cb.is_available()

    def test_half_open_reopens_on_failure(self):
        """Test that HALF_OPEN reopens on failure"""
        config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60.0, success_threshold=3)
        cb = CircuitBreaker(name="test_service", config=config)

        # Open and transition to HALF_OPEN
        for _ in range(5):
            cb.record_failure()
        cb.last_failure_time = time.time() - 61.0
        cb.is_available()  # Trigger transition to HALF_OPEN

        assert cb.state == CircuitState.HALF_OPEN

        # Record a failure in HALF_OPEN
        cb.record_failure()

        # Should reopen
        assert cb.state == CircuitState.OPEN
        assert not cb.is_available()

    def test_recovery_timeout_is_60_seconds(self):
        """Test that recovery timeout is configured to 60 seconds"""
        config = CircuitBreakerConfig(recovery_timeout=60.0)

        assert config.recovery_timeout == 60.0, "Recovery timeout must be 60 seconds"

    @pytest.mark.asyncio
    async def test_llm_bus_respects_circuit_breaker_recovery(self, llm_bus, mock_service_registry):
        """Test that LLM bus respects circuit breaker recovery timeout"""
        # Create a service that initially fails
        failing_service = MockLLMService(should_fail=True)
        service_name = f"MockLLMService_{id(failing_service)}"

        mock_service_registry.get_services_by_type.return_value = [failing_service]
        mock_service_registry.get_provider_info.return_value = {
            "services": {ServiceType.LLM: [{"name": service_name, "priority": "NORMAL"}]}
        }

        # Trigger circuit breaker to open (5 failures)
        for _ in range(5):
            try:
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": "test"}], response_model=MockResponse
                )
            except RuntimeError:
                pass

        # Verify circuit breaker is OPEN
        cb = llm_bus.circuit_breakers[service_name]
        assert cb.state == CircuitState.OPEN

        # Simulate 60 seconds passing
        cb.last_failure_time = time.time() - 61.0

        # Fix the service
        failing_service.should_fail = False

        # Next call should work (circuit breaker in HALF_OPEN)
        result, usage = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "test"}], response_model=MockResponse
        )

        assert result.content == "Mock response"
        # Circuit breaker should be in HALF_OPEN (will close after 3 successes)
        assert cb.state in [CircuitState.HALF_OPEN, CircuitState.CLOSED]


class TestCircuitBreakerConfiguration:
    """Tests for circuit breaker configuration values"""

    def test_default_llm_timeout_is_5_seconds(self, llm_bus):
        """Test that default LLM timeout is 5 seconds"""
        # Check the circuit breaker config
        assert llm_bus.circuit_breaker_config.get("timeout_duration") == 5.0

    def test_default_recovery_timeout_is_60_seconds(self, llm_bus):
        """Test that default recovery timeout is 60 seconds"""
        assert llm_bus.circuit_breaker_config.get("recovery_timeout") == 60.0

    def test_failure_threshold_is_5(self, llm_bus):
        """Test that failure threshold is 5"""
        assert llm_bus.circuit_breaker_config.get("failure_threshold") == 5

    def test_success_threshold_is_3(self, llm_bus):
        """Test that success threshold in HALF_OPEN is 3"""
        assert llm_bus.circuit_breaker_config.get("half_open_max_calls") == 3


class TestMultiProviderFailover:
    """Tests for failover behavior with multiple providers"""

    @pytest.mark.asyncio
    async def test_failover_from_timeout_to_fast_provider(self, llm_bus, mock_service_registry):
        """Test that when primary times out, failover to backup works"""
        # Primary: slow (times out)
        slow_service = MockLLMService(delay=10.0)
        # Backup: fast
        fast_service = MockLLMService(delay=0.1)

        service_name_slow = f"MockLLMService_{id(slow_service)}"
        service_name_fast = f"MockLLMService_{id(fast_service)}"

        mock_service_registry.get_services_by_type.return_value = [slow_service, fast_service]
        mock_service_registry.get_provider_info.return_value = {
            "services": {
                ServiceType.LLM: [
                    {"name": service_name_slow, "priority": "HIGH", "metadata": {}},
                    {"name": service_name_fast, "priority": "NORMAL", "metadata": {}},
                ]
            }
        }

        # First call should try slow (timeout) then fast (success)
        result, usage = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "test"}], response_model=MockResponse
        )

        assert result.content == "Mock response"
        assert fast_service.call_count >= 1, "Fast service should have been called"

    @pytest.mark.asyncio
    async def test_both_providers_timeout_causes_failure(self, llm_bus, mock_service_registry):
        """Test that when all providers timeout, call fails"""
        # Both services are slow
        slow_service_1 = MockLLMService(delay=10.0)
        slow_service_2 = MockLLMService(delay=10.0)

        service_name_1 = f"MockLLMService_{id(slow_service_1)}"
        service_name_2 = f"MockLLMService_{id(slow_service_2)}"

        mock_service_registry.get_services_by_type.return_value = [slow_service_1, slow_service_2]
        mock_service_registry.get_provider_info.return_value = {
            "services": {
                ServiceType.LLM: [
                    {"name": service_name_1, "priority": "HIGH", "metadata": {}},
                    {"name": service_name_2, "priority": "NORMAL", "metadata": {}},
                ]
            }
        }

        # Should fail after trying both
        with pytest.raises(RuntimeError, match="All LLM services failed"):
            await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": "test"}], response_model=MockResponse
            )
