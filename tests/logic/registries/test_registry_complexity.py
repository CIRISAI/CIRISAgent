"""
Tests for registry refactoring to verify functionality unchanged.

Tests the refactored register_service() and helper methods to ensure:
1. Basic registration works
2. LLM mock/real service mixing validation works
3. Circuit breakers are created correctly
4. Priorities and capabilities work
5. All edge cases behave identically
"""

import pytest

from ciris_engine.logic.registries.base import (
    Priority,
    SelectionStrategy,
    ServiceRegistry,
)
from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerConfig
from ciris_engine.schemas.runtime.enums import ServiceType


class MockService:
    """Mock service for testing"""

    def __init__(self, name: str = "test"):
        self.name = name


class MockLLMService:
    """Mock LLM service for testing"""

    def __init__(self, name: str = "test"):
        self.name = name


class RealLLMService:
    """Real LLM service for testing"""

    def __init__(self, name: str = "test"):
        self.name = name


class TestBasicRegistration:
    """Test basic service registration functionality"""

    def test_register_service_basic(self) -> None:
        """Test basic service registration"""
        registry = ServiceRegistry()
        service = MockService()

        provider_name = registry.register_service(
            service_type=ServiceType.MEMORY,
            provider=service,
            priority=Priority.NORMAL,
        )

        assert provider_name.startswith("MockService_")
        assert ServiceType.MEMORY in registry._services
        assert len(registry._services[ServiceType.MEMORY]) == 1
        assert registry._registrations_total == 1

    def test_register_service_with_capabilities(self) -> None:
        """Test registration with capabilities"""
        registry = ServiceRegistry()
        service = MockService()

        provider_name = registry.register_service(
            service_type=ServiceType.MEMORY,
            provider=service,
            priority=Priority.HIGH,
            capabilities=["graph", "vector"],
        )

        providers = registry._services[ServiceType.MEMORY]
        assert len(providers) == 1
        assert providers[0].capabilities == ["graph", "vector"]
        assert providers[0].priority == Priority.HIGH

    def test_register_service_with_metadata(self) -> None:
        """Test registration with metadata"""
        registry = ServiceRegistry()
        service = MockService()

        metadata = {"provider": "test", "version": "1.0"}
        provider_name = registry.register_service(
            service_type=ServiceType.MEMORY,
            provider=service,
            metadata=metadata,
        )

        providers = registry._services[ServiceType.MEMORY]
        assert providers[0].metadata == metadata

    def test_register_service_with_circuit_breaker_config(self) -> None:
        """Test registration with custom circuit breaker config"""
        registry = ServiceRegistry()
        service = MockService()

        cb_config = CircuitBreakerConfig(failure_threshold=5, recovery_timeout=60.0)
        provider_name = registry.register_service(
            service_type=ServiceType.MEMORY,
            provider=service,
            circuit_breaker_config=cb_config,
        )

        assert provider_name in registry._circuit_breakers
        cb = registry._circuit_breakers[provider_name]
        assert cb.config.failure_threshold == 5
        assert cb.config.recovery_timeout == 60.0

    def test_register_service_with_priority_group(self) -> None:
        """Test registration with priority group"""
        registry = ServiceRegistry()
        service = MockService()

        provider_name = registry.register_service(
            service_type=ServiceType.MEMORY,
            provider=service,
            priority_group=2,
            strategy=SelectionStrategy.ROUND_ROBIN,
        )

        providers = registry._services[ServiceType.MEMORY]
        assert providers[0].priority_group == 2
        assert providers[0].strategy == SelectionStrategy.ROUND_ROBIN

    def test_register_multiple_services_sorted_by_priority(self) -> None:
        """Test that multiple services are sorted by priority"""
        registry = ServiceRegistry()

        service1 = MockService("low")
        service2 = MockService("high")
        service3 = MockService("critical")

        registry.register_service(ServiceType.MEMORY, service1, Priority.LOW)
        registry.register_service(ServiceType.MEMORY, service2, Priority.HIGH)
        registry.register_service(ServiceType.MEMORY, service3, Priority.CRITICAL)

        providers = registry._services[ServiceType.MEMORY]
        assert len(providers) == 3
        assert providers[0].priority == Priority.CRITICAL
        assert providers[1].priority == Priority.HIGH
        assert providers[2].priority == Priority.LOW


class TestLLMServiceMixingValidation:
    """Test LLM service mock/real mixing validation"""

    def test_register_mock_llm_service(self) -> None:
        """Test registering a mock LLM service"""
        registry = ServiceRegistry()
        service = MockLLMService()

        provider_name = registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
        )

        assert ServiceType.LLM in registry._services
        assert len(registry._services[ServiceType.LLM]) == 1

    def test_register_real_llm_service(self) -> None:
        """Test registering a real LLM service"""
        registry = ServiceRegistry()
        service = RealLLMService()

        provider_name = registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
        )

        assert ServiceType.LLM in registry._services
        assert len(registry._services[ServiceType.LLM]) == 1

    def test_prevent_mixing_mock_after_real(self) -> None:
        """Test that mock service cannot be registered after real service"""
        registry = ServiceRegistry()

        # Register real service first
        real_service = RealLLMService()
        registry.register_service(ServiceType.LLM, real_service)

        # Try to register mock service
        mock_service = MockLLMService()
        with pytest.raises(RuntimeError) as exc_info:
            registry.register_service(ServiceType.LLM, mock_service)

        assert "SECURITY VIOLATION" in str(exc_info.value)
        assert "mock" in str(exc_info.value)
        assert "real" in str(exc_info.value)

    def test_prevent_mixing_real_after_mock(self) -> None:
        """Test that real service cannot be registered after mock service"""
        registry = ServiceRegistry()

        # Register mock service first
        mock_service = MockLLMService()
        registry.register_service(ServiceType.LLM, mock_service)

        # Try to register real service
        real_service = RealLLMService()
        with pytest.raises(RuntimeError) as exc_info:
            registry.register_service(ServiceType.LLM, real_service)

        assert "SECURITY VIOLATION" in str(exc_info.value)
        assert "real" in str(exc_info.value)
        assert "mock" in str(exc_info.value)

    def test_allow_multiple_mock_services(self) -> None:
        """Test that multiple mock services can be registered"""
        registry = ServiceRegistry()

        mock1 = MockLLMService("mock1")
        mock2 = MockLLMService("mock2")

        registry.register_service(ServiceType.LLM, mock1)
        registry.register_service(ServiceType.LLM, mock2)

        assert len(registry._services[ServiceType.LLM]) == 2

    def test_prevent_multiple_real_services(self) -> None:
        """Test that multiple real services cannot be registered (current behavior)"""
        registry = ServiceRegistry()

        # The current implementation prevents registering multiple LLM services of the same type
        # Whether this is intentional or a bug, we preserve the behavior during refactoring
        real1 = RealLLMService("real1")
        real2 = RealLLMService("real2")

        registry.register_service(ServiceType.LLM, real1)

        # Second real service should be blocked
        with pytest.raises(RuntimeError) as exc_info:
            registry.register_service(ServiceType.LLM, real2)

        assert "SECURITY VIOLATION" in str(exc_info.value)
        assert len(registry._services[ServiceType.LLM]) == 1

    def test_mock_detection_via_metadata(self) -> None:
        """Test mock detection via metadata field"""
        registry = ServiceRegistry()

        # Register with mock metadata
        service1 = RealLLMService()  # Real class but mock metadata
        registry.register_service(
            ServiceType.LLM,
            service1,
            metadata={"provider": "mock"},
        )

        # Try to register real service
        service2 = RealLLMService()
        with pytest.raises(RuntimeError) as exc_info:
            registry.register_service(ServiceType.LLM, service2)

        assert "SECURITY VIOLATION" in str(exc_info.value)


class TestHelperMethods:
    """Test the extracted helper methods"""

    def test_is_mock_service_by_class_name(self) -> None:
        """Test _is_mock_service detects mock by class name"""
        registry = ServiceRegistry()

        mock_service = MockLLMService()
        assert registry._is_mock_service(mock_service, None)

        real_service = RealLLMService()
        assert not registry._is_mock_service(real_service, None)

    def test_is_mock_service_by_metadata(self) -> None:
        """Test _is_mock_service detects mock by metadata"""
        registry = ServiceRegistry()

        service = RealLLMService()
        assert registry._is_mock_service(service, {"provider": "mock"})
        assert not registry._is_mock_service(service, {"provider": "openai"})
        assert not registry._is_mock_service(service, None)

    def test_create_service_provider(self) -> None:
        """Test _create_service_provider creates correct provider"""
        registry = ServiceRegistry()
        service = MockService()

        sp = registry._create_service_provider(
            service_type=ServiceType.MEMORY,
            name="test_provider",
            instance=service,
            priority=Priority.HIGH,
            capabilities=["test"],
            circuit_breaker_config=None,
            metadata={"key": "value"},
            priority_group=1,
            strategy=SelectionStrategy.ROUND_ROBIN,
        )

        assert sp.name == "test_provider"
        assert sp.instance is service
        assert sp.priority == Priority.HIGH
        assert sp.capabilities == ["test"]
        assert sp.metadata == {"key": "value"}
        assert sp.priority_group == 1
        assert sp.strategy == SelectionStrategy.ROUND_ROBIN
        assert sp.circuit_breaker is not None
        assert "test_provider" in registry._circuit_breakers

    def test_build_llm_mixing_error(self) -> None:
        """Test _build_llm_mixing_error formats error correctly"""
        registry = ServiceRegistry()

        error = registry._build_llm_mixing_error(
            is_mock=True,
            existing_is_mock=False,
            existing_name="RealService",
            provider_name="MockService",
        )

        assert "SECURITY VIOLATION" in error
        assert "mock" in error
        assert "real" in error
        assert "RealService" in error
        assert "MockService" in error


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_register_to_new_service_type(self) -> None:
        """Test registering to a new service type initializes list"""
        registry = ServiceRegistry()
        service = MockService()

        assert ServiceType.AUDIT not in registry._services

        registry.register_service(ServiceType.AUDIT, service)

        assert ServiceType.AUDIT in registry._services
        assert len(registry._services[ServiceType.AUDIT]) == 1

    def test_default_parameters(self) -> None:
        """Test that default parameters work correctly"""
        registry = ServiceRegistry()
        service = MockService()

        provider_name = registry.register_service(
            service_type=ServiceType.MEMORY,
            provider=service,
        )

        provider = registry._services[ServiceType.MEMORY][0]
        assert provider.priority == Priority.NORMAL
        assert provider.capabilities == []
        assert provider.metadata == {}
        assert provider.priority_group == 0
        assert provider.strategy == SelectionStrategy.FALLBACK
        assert provider.circuit_breaker is not None

    def test_empty_capabilities_list(self) -> None:
        """Test registering with empty capabilities list"""
        registry = ServiceRegistry()
        service = MockService()

        registry.register_service(
            ServiceType.MEMORY,
            service,
            capabilities=[],
        )

        provider = registry._services[ServiceType.MEMORY][0]
        assert provider.capabilities == []

    def test_registrations_total_counter(self) -> None:
        """Test that registrations_total counter increments"""
        registry = ServiceRegistry()

        assert registry._registrations_total == 0

        registry.register_service(ServiceType.MEMORY, MockService())
        assert registry._registrations_total == 1

        registry.register_service(ServiceType.AUDIT, MockService())
        assert registry._registrations_total == 2

        registry.register_service(ServiceType.LLM, MockLLMService())
        assert registry._registrations_total == 3
