"""
Comprehensive metric tests for runtime objects - CircuitBreaker and ServiceRegistry.

These objects are core runtime components that provide resilience and service discovery.
They track their own metrics independently of traditional services.
"""

import asyncio
import time
from typing import Dict, Set
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.registries.base import Priority, SelectionStrategy, ServiceRegistry
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState
from ciris_engine.schemas.runtime.enums import ServiceType
from tests.test_metrics_base import BaseMetricsTest


class TestCircuitBreakerMetrics:
    """Test CircuitBreaker metrics collection and state tracking."""

    # Expected CircuitBreaker metrics (10 total)
    CIRCUIT_BREAKER_METRICS = {
        "cb_test_service_state",
        "cb_test_service_total_calls",
        "cb_test_service_total_failures",
        "cb_test_service_total_successes",
        "cb_test_service_success_rate",
        "cb_test_service_consecutive_failures",
        "cb_test_service_recovery_attempts",
        "cb_test_service_state_transitions",
        "cb_test_service_time_in_open_state_sec",
        "cb_test_service_last_failure_age_sec",
    }

    def assert_required_metrics(self, metrics: Dict[str, float], required: Set[str]):
        """Assert that all required metrics are present and valid."""
        for metric in required:
            assert metric in metrics, f"Required metric '{metric}' not found"
            assert isinstance(
                metrics[metric], (int, float)
            ), f"Metric '{metric}' is not numeric: {type(metrics[metric])}"

    def assert_all_metrics_are_floats(self, metrics: Dict[str, float]):
        """Assert all metric values are floats."""
        for key, value in metrics.items():
            assert isinstance(value, (int, float)), f"Metric {key} is not numeric: {type(value)}"
            # Ensure it can be converted to float
            float(value)

    @pytest.fixture
    def circuit_breaker(self):
        """Create a circuit breaker for testing."""
        config = CircuitBreakerConfig(
            failure_threshold=3, recovery_timeout=5.0, success_threshold=2, timeout_duration=10.0
        )
        return CircuitBreaker("test_service", config)

    @pytest.fixture
    def fast_recovery_breaker(self):
        """Create a circuit breaker with fast recovery for testing."""
        config = CircuitBreakerConfig(
            failure_threshold=2, recovery_timeout=0.1, success_threshold=1, timeout_duration=1.0  # Very fast recovery
        )
        return CircuitBreaker("fast_service", config)

    def test_circuit_breaker_metrics_structure(self, circuit_breaker):
        """Test that circuit breaker returns expected metrics."""
        metrics = circuit_breaker.get_metrics()

        # Check it's a dict with expected metrics
        assert isinstance(metrics, dict)
        assert (
            len(metrics) == 14
        ), f"Expected 14 metrics (10 prefixed + 4 v1.4.3), got {len(metrics)}: {list(metrics.keys())}"

        # Check all expected metrics are present
        self.assert_required_metrics(metrics, self.CIRCUIT_BREAKER_METRICS)

        # Check all values are floats
        self.assert_all_metrics_are_floats(metrics)

    def test_initial_state_metrics(self, circuit_breaker):
        """Test initial state metrics are correct."""
        metrics = circuit_breaker.get_metrics()

        # State should be CLOSED (0.0)
        assert metrics["cb_test_service_state"] == 0.0

        # All counts should be zero initially
        assert metrics["cb_test_service_total_calls"] == 0.0
        assert metrics["cb_test_service_total_failures"] == 0.0
        assert metrics["cb_test_service_total_successes"] == 0.0
        assert metrics["cb_test_service_consecutive_failures"] == 0.0
        assert metrics["cb_test_service_recovery_attempts"] == 0.0
        assert metrics["cb_test_service_state_transitions"] == 0.0

        # Success rate should be 1.0 (no failures yet)
        assert metrics["cb_test_service_success_rate"] == 1.0

        # Time metrics should be zero
        assert metrics["cb_test_service_time_in_open_state_sec"] == 0.0
        assert metrics["cb_test_service_last_failure_age_sec"] == 0.0

    def test_success_recording_metrics(self, circuit_breaker):
        """Test that recording successes updates metrics correctly."""
        # Record some successes
        circuit_breaker.record_success()
        circuit_breaker.record_success()
        circuit_breaker.record_success()

        metrics = circuit_breaker.get_metrics()

        # Check call tracking
        assert metrics["cb_test_service_total_calls"] == 3.0
        assert metrics["cb_test_service_total_successes"] == 3.0
        assert metrics["cb_test_service_total_failures"] == 0.0

        # Success rate should be 1.0
        assert metrics["cb_test_service_success_rate"] == 1.0

        # Consecutive failures should be 0
        assert metrics["cb_test_service_consecutive_failures"] == 0.0

        # State should still be CLOSED
        assert metrics["cb_test_service_state"] == 0.0

    def test_failure_recording_metrics(self, circuit_breaker):
        """Test that recording failures updates metrics correctly."""
        # Record some failures
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()

        metrics = circuit_breaker.get_metrics()

        # Check call tracking
        assert metrics["cb_test_service_total_calls"] == 2.0
        assert metrics["cb_test_service_total_failures"] == 2.0
        assert metrics["cb_test_service_total_successes"] == 0.0

        # Success rate should be 0.0
        assert metrics["cb_test_service_success_rate"] == 0.0

        # Consecutive failures should match
        assert metrics["cb_test_service_consecutive_failures"] == 2.0

        # Last failure age should be very small (recent)
        assert 0.0 <= metrics["cb_test_service_last_failure_age_sec"] <= 1.0

    def test_state_transition_to_open_metrics(self, circuit_breaker):
        """Test metrics when circuit breaker opens."""
        # Record enough failures to open the circuit (threshold = 3)
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()  # This should open the circuit

        metrics = circuit_breaker.get_metrics()

        # State should be OPEN (1.0)
        assert metrics["cb_test_service_state"] == 1.0

        # Should have recorded one state transition
        assert metrics["cb_test_service_state_transitions"] == 1.0

        # All calls should be failures
        assert metrics["cb_test_service_total_calls"] == 3.0
        assert metrics["cb_test_service_total_failures"] == 3.0
        assert metrics["cb_test_service_success_rate"] == 0.0

    def test_state_transition_to_half_open_metrics(self, fast_recovery_breaker):
        """Test metrics when circuit breaker transitions to half-open."""
        # Open the circuit
        fast_recovery_breaker.record_failure()
        fast_recovery_breaker.record_failure()  # threshold = 2

        assert fast_recovery_breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.15)  # recovery_timeout = 0.1

        # Check availability (should trigger transition to HALF_OPEN)
        available = fast_recovery_breaker.is_available()
        assert available
        assert fast_recovery_breaker.state == CircuitState.HALF_OPEN

        metrics = fast_recovery_breaker.get_metrics()

        # State should be HALF_OPEN (0.5)
        assert metrics["cb_fast_service_state"] == 0.5

        # Should have recorded two state transitions (CLOSED->OPEN->HALF_OPEN)
        assert metrics["cb_fast_service_state_transitions"] == 2.0

        # Should have recorded one recovery attempt
        assert metrics["cb_fast_service_recovery_attempts"] == 1.0

        # Should have some time in open state
        assert metrics["cb_fast_service_time_in_open_state_sec"] > 0.0

    def test_recovery_success_metrics(self, fast_recovery_breaker):
        """Test metrics when circuit breaker recovers successfully."""
        # Open the circuit
        fast_recovery_breaker.record_failure()
        fast_recovery_breaker.record_failure()

        # Wait and transition to half-open
        time.sleep(0.15)
        fast_recovery_breaker.is_available()

        # Record success to close circuit (success_threshold = 1)
        fast_recovery_breaker.record_success()

        metrics = fast_recovery_breaker.get_metrics()

        # State should be CLOSED (0.0)
        assert metrics["cb_fast_service_state"] == 0.0

        # Should have recorded three state transitions (CLOSED->OPEN->HALF_OPEN->CLOSED)
        assert metrics["cb_fast_service_state_transitions"] == 3.0

        # Should have one recovery attempt
        assert metrics["cb_fast_service_recovery_attempts"] == 1.0

        # Should have accumulated time in open state
        assert metrics["cb_fast_service_time_in_open_state_sec"] > 0.0

    def test_mixed_success_failure_metrics(self, circuit_breaker):
        """Test metrics with mixed success and failure patterns."""
        # Mixed pattern: success, failure, success, failure, failure
        circuit_breaker.record_success()
        circuit_breaker.record_failure()
        circuit_breaker.record_success()
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()

        metrics = circuit_breaker.get_metrics()

        # Check totals
        assert metrics["cb_test_service_total_calls"] == 5.0
        assert metrics["cb_test_service_total_successes"] == 2.0
        assert metrics["cb_test_service_total_failures"] == 3.0

        # Success rate should be 2/5 = 0.4
        assert abs(metrics["cb_test_service_success_rate"] - 0.4) < 0.001

        # Consecutive failures should be 2 (last two calls)
        assert metrics["cb_test_service_consecutive_failures"] == 2.0

    def test_time_in_open_state_accumulation(self, fast_recovery_breaker):
        """Test that time in open state accumulates correctly across multiple opens."""
        # First open cycle
        fast_recovery_breaker.record_failure()
        fast_recovery_breaker.record_failure()
        time.sleep(0.05)  # Spend some time open

        # Transition to half-open and immediately fail (goes back to open)
        time.sleep(0.1)  # Wait for recovery timeout
        fast_recovery_breaker.is_available()  # Triggers HALF_OPEN
        fast_recovery_breaker.record_failure()  # Back to OPEN

        time.sleep(0.05)  # More time open

        # Close the circuit
        time.sleep(0.1)  # Wait for recovery timeout
        fast_recovery_breaker.is_available()  # Triggers HALF_OPEN
        fast_recovery_breaker.record_success()  # CLOSED

        metrics = fast_recovery_breaker.get_metrics()

        # Should have accumulated time from both open periods
        assert metrics["cb_fast_service_time_in_open_state_sec"] >= 0.1

        # Should have two recovery attempts
        assert metrics["cb_fast_service_recovery_attempts"] == 2.0

    def test_circuit_breaker_metrics_validation(self, circuit_breaker):
        """Test that all circuit breaker metrics pass validation."""
        # Generate some activity
        for i in range(10):
            if i % 3 == 0:
                circuit_breaker.record_failure()
            else:
                circuit_breaker.record_success()

        metrics = circuit_breaker.get_metrics()

        # All values should be floats
        self.assert_all_metrics_are_floats(metrics)

        # All values should be non-negative
        for key, value in metrics.items():
            assert value >= 0, f"Metric {key} should be non-negative: {value}"

        # Success rate should be between 0 and 1
        assert 0.0 <= metrics["cb_test_service_success_rate"] <= 1.0

        # State should be 0.0, 0.5, or 1.0
        state_value = metrics["cb_test_service_state"]
        assert state_value in [0.0, 0.5, 1.0], f"Invalid state value: {state_value}"


class TestServiceRegistryMetrics:
    """Test ServiceRegistry metrics collection and tracking."""

    # Expected ServiceRegistry metrics (10 total)
    SERVICE_REGISTRY_METRICS = {
        "registry_total_services",
        "registry_service_types",
        "registry_circuit_breakers",
        "registry_open_breakers",
        "registry_service_lookups",
        "registry_service_hits",
        "registry_service_misses",
        "registry_hit_rate",
        "registry_health_check_failures",
        "registry_max_open_breakers",
    }

    def assert_required_metrics(self, metrics: Dict[str, float], required: Set[str]):
        """Assert that all required metrics are present and valid."""
        for metric in required:
            assert metric in metrics, f"Required metric '{metric}' not found"
            assert isinstance(
                metrics[metric], (int, float)
            ), f"Metric '{metric}' is not numeric: {type(metrics[metric])}"

    def assert_all_metrics_are_floats(self, metrics: Dict[str, float]):
        """Assert all metric values are floats."""
        for key, value in metrics.items():
            assert isinstance(value, (int, float)), f"Metric {key} is not numeric: {type(value)}"
            # Ensure it can be converted to float
            float(value)

    @pytest.fixture
    def service_registry(self):
        """Create a service registry for testing."""
        return ServiceRegistry()

    @pytest.fixture
    def mock_service(self):
        """Create a mock service for registration."""
        service = MagicMock()
        service.is_healthy = AsyncMock(return_value=True)
        return service

    @pytest.fixture
    def unhealthy_service(self):
        """Create a mock service that fails health checks."""
        service = MagicMock()
        service.is_healthy = AsyncMock(return_value=False)
        return service

    def test_service_registry_metrics_structure(self, service_registry):
        """Test that service registry returns expected metrics."""
        metrics = service_registry.get_metrics()

        # Check it's a dict with expected metrics
        assert isinstance(metrics, dict)
        assert (
            len(metrics) == 16
        ), f"Expected 16 metrics (10 detailed + 4 v1.4.3 + 2 health), got {len(metrics)}: {list(metrics.keys())}"

        # Check all expected metrics are present
        self.assert_required_metrics(metrics, self.SERVICE_REGISTRY_METRICS)

        # Check all values are floats
        self.assert_all_metrics_are_floats(metrics)

    def test_initial_registry_metrics(self, service_registry):
        """Test initial registry metrics are correct."""
        metrics = service_registry.get_metrics()

        # Should start with zero services
        assert metrics["registry_total_services"] == 0.0
        assert metrics["registry_service_types"] == 0.0
        assert metrics["registry_circuit_breakers"] == 0.0
        assert metrics["registry_open_breakers"] == 0.0

        # No lookups initially
        assert metrics["registry_service_lookups"] == 0.0
        assert metrics["registry_service_hits"] == 0.0
        assert metrics["registry_service_misses"] == 0.0
        assert metrics["registry_hit_rate"] == 0.0

        # No health check failures initially
        assert metrics["registry_health_check_failures"] == 0.0
        assert metrics["registry_max_open_breakers"] == 0.0

    def test_service_registration_metrics(self, service_registry, mock_service):
        """Test that service registration updates metrics."""
        # Create separate service instances to avoid same object registration issues
        service1 = MagicMock()
        service1.is_healthy = AsyncMock(return_value=True)
        service2 = MagicMock()
        service2.is_healthy = AsyncMock(return_value=True)

        # Register services
        service_registry.register_service(ServiceType.LLM, service1, Priority.NORMAL)
        service_registry.register_service(ServiceType.MEMORY, service2, Priority.HIGH)

        metrics = service_registry.get_metrics()

        # Should have 2 services
        assert metrics["registry_total_services"] == 2.0

        # Should have 2 service types
        assert metrics["registry_service_types"] == 2.0

        # Should have 2 circuit breakers (one per service)
        assert metrics["registry_circuit_breakers"] == 2.0

        # No open breakers initially
        assert metrics["registry_open_breakers"] == 0.0

    async def test_service_lookup_hit_metrics(self, service_registry, mock_service):
        """Test that successful service lookups update hit metrics."""
        # Register a service
        service_registry.register_service(ServiceType.LLM, mock_service, Priority.NORMAL)

        # Perform successful lookups
        result1 = await service_registry.get_service("test_handler", ServiceType.LLM)
        result2 = await service_registry.get_service("test_handler", ServiceType.LLM)

        assert result1 is not None
        assert result2 is not None

        metrics = service_registry.get_metrics()

        # Should have 2 lookups and 2 hits
        assert metrics["registry_service_lookups"] == 2.0
        assert metrics["registry_service_hits"] == 2.0
        assert metrics["registry_service_misses"] == 0.0

        # Hit rate should be 1.0 (100%)
        assert metrics["registry_hit_rate"] == 1.0

    async def test_service_lookup_miss_metrics(self, service_registry):
        """Test that failed service lookups update miss metrics."""
        # Try to get a service that doesn't exist
        result1 = await service_registry.get_service("test_handler", ServiceType.LLM)
        result2 = await service_registry.get_service("test_handler", ServiceType.MEMORY)

        assert result1 is None
        assert result2 is None

        metrics = service_registry.get_metrics()

        # Should have 2 lookups and 2 misses
        assert metrics["registry_service_lookups"] == 2.0
        assert metrics["registry_service_hits"] == 0.0
        assert metrics["registry_service_misses"] == 2.0

        # Hit rate should be 0.0 (0%)
        assert metrics["registry_hit_rate"] == 0.0

    async def test_mixed_lookup_metrics(self, service_registry, mock_service):
        """Test hit rate calculation with mixed lookup results."""
        # Register one service
        service_registry.register_service(ServiceType.LLM, mock_service, Priority.NORMAL)

        # Mix of successful and failed lookups
        await service_registry.get_service("test", ServiceType.LLM)  # hit
        await service_registry.get_service("test", ServiceType.MEMORY)  # miss
        await service_registry.get_service("test", ServiceType.LLM)  # hit
        await service_registry.get_service("test", ServiceType.AUDIT)  # miss

        metrics = service_registry.get_metrics()

        # Should have 4 lookups, 2 hits, 2 misses
        assert metrics["registry_service_lookups"] == 4.0
        assert metrics["registry_service_hits"] == 2.0
        assert metrics["registry_service_misses"] == 2.0

        # Hit rate should be 0.5 (50%)
        assert abs(metrics["registry_hit_rate"] - 0.5) < 0.001

    async def test_health_check_failure_metrics(self, service_registry, unhealthy_service):
        """Test that health check failures are tracked."""
        # Register an unhealthy service
        service_registry.register_service(ServiceType.LLM, unhealthy_service, Priority.NORMAL)

        # Try to get the unhealthy service (should fail health check)
        result = await service_registry.get_service("test", ServiceType.LLM)

        assert result is None  # Should fail due to health check

        metrics = service_registry.get_metrics()

        # Should have recorded a health check failure
        assert metrics["registry_health_check_failures"] >= 1.0

        # Should be a miss since service was unhealthy
        assert metrics["registry_service_misses"] == 1.0

    def test_circuit_breaker_open_tracking(self, service_registry):
        """Test tracking of open circuit breakers."""
        # Create separate service instances
        service1 = MagicMock()
        service1.is_healthy = AsyncMock(return_value=True)
        service2 = MagicMock()
        service2.is_healthy = AsyncMock(return_value=True)

        # Register services
        provider1 = service_registry.register_service(ServiceType.LLM, service1, Priority.NORMAL)
        provider2 = service_registry.register_service(ServiceType.MEMORY, service2, Priority.HIGH)

        # Open circuit breakers by recording failures
        cb1 = service_registry._circuit_breakers[provider1]
        cb2 = service_registry._circuit_breakers[provider2]

        # Open first circuit breaker
        for _ in range(5):  # Default threshold is 5
            cb1.record_failure()

        metrics = service_registry.get_metrics()

        # Should have 1 open breaker
        assert metrics["registry_open_breakers"] == 1.0
        assert metrics["registry_max_open_breakers"] == 1.0

        # Open second circuit breaker
        for _ in range(5):
            cb2.record_failure()

        metrics = service_registry.get_metrics()

        # Should have 2 open breakers
        assert metrics["registry_open_breakers"] == 2.0
        assert metrics["registry_max_open_breakers"] == 2.0

    def test_multiple_service_registration_metrics(self, service_registry):
        """Test metrics with multiple services of same and different types."""
        # Create multiple mock services
        service1 = MagicMock()
        service2 = MagicMock()
        service3 = MagicMock()

        # Register multiple services
        service_registry.register_service(ServiceType.LLM, service1, Priority.HIGH)
        service_registry.register_service(ServiceType.LLM, service2, Priority.NORMAL)  # Same type
        service_registry.register_service(ServiceType.MEMORY, service3, Priority.HIGH)

        metrics = service_registry.get_metrics()

        # Should have 3 total services
        assert metrics["registry_total_services"] == 3.0

        # Should have 2 service types (LLM and MEMORY)
        assert metrics["registry_service_types"] == 2.0

        # Should have 3 circuit breakers
        assert metrics["registry_circuit_breakers"] == 3.0

    def test_service_unregistration_metrics(self, service_registry):
        """Test that unregistering services updates metrics."""
        # Create separate service instances
        service1 = MagicMock()
        service1.is_healthy = AsyncMock(return_value=True)
        service2 = MagicMock()
        service2.is_healthy = AsyncMock(return_value=True)

        # Register services
        provider1 = service_registry.register_service(ServiceType.LLM, service1, Priority.NORMAL)
        provider2 = service_registry.register_service(ServiceType.MEMORY, service2, Priority.HIGH)

        initial_metrics = service_registry.get_metrics()
        assert initial_metrics["registry_total_services"] == 2.0
        assert initial_metrics["registry_circuit_breakers"] == 2.0

        # Unregister one service
        success = service_registry.unregister(provider1)
        assert success

        metrics = service_registry.get_metrics()

        # Should have 1 service and 1 circuit breaker remaining
        assert metrics["registry_total_services"] == 1.0
        assert metrics["registry_circuit_breakers"] == 1.0

    def test_registry_metrics_validation(self, service_registry, mock_service):
        """Test that all registry metrics pass validation."""
        # Register some services and generate activity
        service_registry.register_service(ServiceType.LLM, mock_service, Priority.NORMAL)
        service_registry.register_service(ServiceType.MEMORY, mock_service, Priority.HIGH)

        # Generate some lookup activity
        asyncio.run(self._generate_lookup_activity(service_registry))

        metrics = service_registry.get_metrics()

        # All values should be floats
        self.assert_all_metrics_are_floats(metrics)

        # All values should be non-negative
        for key, value in metrics.items():
            assert value >= 0, f"Metric {key} should be non-negative: {value}"

        # Hit rate should be between 0 and 1
        assert 0.0 <= metrics["registry_hit_rate"] <= 1.0

        # Consistency checks
        total_lookups = metrics["registry_service_lookups"]
        hits = metrics["registry_service_hits"]
        misses = metrics["registry_service_misses"]

        # Hits + misses should equal total lookups
        assert abs((hits + misses) - total_lookups) < 0.001

        # If there are lookups, hit rate should match calculation
        if total_lookups > 0:
            expected_hit_rate = hits / total_lookups
            assert abs(metrics["registry_hit_rate"] - expected_hit_rate) < 0.001

    async def _generate_lookup_activity(self, service_registry):
        """Generate various lookup activity for testing."""
        # Mix of hits and misses
        await service_registry.get_service("test", ServiceType.LLM)  # hit
        await service_registry.get_service("test", ServiceType.MEMORY)  # hit
        await service_registry.get_service("test", ServiceType.AUDIT)  # miss
        await service_registry.get_service("test", ServiceType.RUNTIME_CONTROL)  # miss

    def test_circuit_breaker_max_tracking(self, service_registry):
        """Test that max open breakers is tracked correctly."""
        # Create separate service instances
        service1 = MagicMock()
        service1.is_healthy = AsyncMock(return_value=True)
        service2 = MagicMock()
        service2.is_healthy = AsyncMock(return_value=True)
        service3 = MagicMock()
        service3.is_healthy = AsyncMock(return_value=True)

        # Register multiple services
        provider1 = service_registry.register_service(ServiceType.LLM, service1, Priority.NORMAL)
        provider2 = service_registry.register_service(ServiceType.MEMORY, service2, Priority.HIGH)
        provider3 = service_registry.register_service(ServiceType.AUDIT, service3, Priority.LOW)

        # Open breakers sequentially and check max tracking
        cb1 = service_registry._circuit_breakers[provider1]
        cb2 = service_registry._circuit_breakers[provider2]
        cb3 = service_registry._circuit_breakers[provider3]

        # Open first breaker
        for _ in range(5):
            cb1.record_failure()

        metrics = service_registry.get_metrics()
        assert metrics["registry_max_open_breakers"] == 1.0

        # Open second breaker
        for _ in range(5):
            cb2.record_failure()

        metrics = service_registry.get_metrics()
        assert metrics["registry_max_open_breakers"] == 2.0

        # Close first breaker (should still track max)
        cb1.reset()

        metrics = service_registry.get_metrics()
        assert metrics["registry_open_breakers"] == 1.0  # Only cb2 still open
        assert metrics["registry_max_open_breakers"] == 2.0  # Max should persist

    async def test_registry_comprehensive_scenario(self, service_registry):
        """Test comprehensive scenario with multiple services and activities."""
        # Create separate service instances to avoid circuit breaker sharing
        healthy_service1 = MagicMock()
        healthy_service1.is_healthy = AsyncMock(return_value=True)

        unhealthy_service = MagicMock()
        unhealthy_service.is_healthy = AsyncMock(return_value=False)

        healthy_service2 = MagicMock()
        healthy_service2.is_healthy = AsyncMock(return_value=True)

        # Register services
        provider1 = service_registry.register_service(ServiceType.LLM, healthy_service1, Priority.HIGH)
        provider2 = service_registry.register_service(ServiceType.MEMORY, unhealthy_service, Priority.NORMAL)
        provider3 = service_registry.register_service(ServiceType.AUDIT, healthy_service2, Priority.LOW)

        # Generate mixed activity
        await service_registry.get_service("test", ServiceType.LLM)  # hit (healthy)
        await service_registry.get_service("test", ServiceType.MEMORY)  # miss (unhealthy)
        await service_registry.get_service("test", ServiceType.AUDIT)  # hit (healthy)
        await service_registry.get_service("test", ServiceType.COMMUNICATION)  # miss (not registered)

        # Break one circuit breaker
        cb1 = service_registry._circuit_breakers[provider1]
        for _ in range(5):
            cb1.record_failure()

        metrics = service_registry.get_metrics()

        # Verify comprehensive metrics
        assert metrics["registry_total_services"] == 3.0
        assert metrics["registry_service_types"] == 3.0
        assert metrics["registry_circuit_breakers"] == 3.0
        assert metrics["registry_open_breakers"] == 1.0
        assert metrics["registry_service_lookups"] == 4.0
        assert metrics["registry_service_hits"] == 2.0
        assert metrics["registry_service_misses"] == 2.0
        assert abs(metrics["registry_hit_rate"] - 0.5) < 0.001
        assert metrics["registry_health_check_failures"] >= 1.0
        assert metrics["registry_max_open_breakers"] == 1.0
