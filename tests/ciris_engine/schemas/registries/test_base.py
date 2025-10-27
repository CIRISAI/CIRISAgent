"""Tests for registry schemas."""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.registries.base import (
    CircuitBreakerStats,
    HandlerInfo,
    ProviderInfo,
    RegistryInfo,
    ServiceMetadata,
    ServiceTypeInfo,
)


class TestServiceMetadata:
    """Tests for ServiceMetadata schema."""

    def test_valid_service_metadata(self):
        """Test creating valid ServiceMetadata."""
        metadata = ServiceMetadata(
            version="1.0.0",
            description="Test service",
            author="Test Author",
            additional_info={"license": "MIT", "repo": "https://github.com/test/test"},
        )

        assert metadata.version == "1.0.0"
        assert metadata.description == "Test service"
        assert metadata.author == "Test Author"
        assert metadata.additional_info["license"] == "MIT"

    def test_service_metadata_with_defaults(self):
        """Test ServiceMetadata with default values."""
        metadata = ServiceMetadata()

        assert metadata.version is None
        assert metadata.description is None
        assert metadata.author is None
        assert metadata.additional_info == {}


class TestProviderInfo:
    """Tests for ProviderInfo schema."""

    def test_valid_provider_info(self):
        """Test creating valid ProviderInfo."""
        provider = ProviderInfo(
            name="test_provider",
            priority="HIGH",
            priority_group=1,
            strategy="round_robin",
            capabilities=["call_llm", "call_llm_structured"],
            metadata={"region": "us-west", "model": "claude"},
            circuit_breaker_state="closed",
        )

        assert provider.name == "test_provider"
        assert provider.priority == "HIGH"
        assert provider.priority_group == 1
        assert provider.strategy == "round_robin"
        assert "call_llm" in provider.capabilities
        assert provider.metadata["region"] == "us-west"
        assert provider.circuit_breaker_state == "closed"

    def test_provider_info_with_defaults(self):
        """Test ProviderInfo with default values."""
        provider = ProviderInfo(
            name="minimal_provider",
            priority="NORMAL",
            strategy="first",
        )

        assert provider.name == "minimal_provider"
        assert provider.priority_group == 0
        assert provider.capabilities == []
        assert provider.metadata == {}
        assert provider.circuit_breaker_state is None

    def test_provider_info_missing_required_fields(self):
        """Test that missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            ProviderInfo(name="test")

        errors = exc_info.value.errors()
        assert len(errors) == 2
        error_fields = {e["loc"][0] for e in errors}
        assert "priority" in error_fields
        assert "strategy" in error_fields


class TestServiceTypeInfo:
    """Tests for ServiceTypeInfo schema."""

    def test_valid_service_type_info(self):
        """Test creating valid ServiceTypeInfo."""
        providers = [
            ProviderInfo(
                name="provider1",
                priority="HIGH",
                strategy="first",
            ),
            ProviderInfo(
                name="provider2",
                priority="NORMAL",
                strategy="first",
            ),
        ]

        service_type = ServiceTypeInfo(providers=providers)

        assert len(service_type.providers) == 2
        assert service_type.providers[0].name == "provider1"
        assert service_type.providers[1].name == "provider2"

    def test_service_type_info_empty(self):
        """Test ServiceTypeInfo with no providers."""
        service_type = ServiceTypeInfo()

        assert service_type.providers == []


class TestHandlerInfo:
    """Tests for HandlerInfo schema."""

    def test_valid_handler_info(self):
        """Test creating valid HandlerInfo."""
        service_types = {
            "llm": ServiceTypeInfo(
                providers=[
                    ProviderInfo(name="openai", priority="HIGH", strategy="first"),
                ]
            ),
            "memory": ServiceTypeInfo(
                providers=[
                    ProviderInfo(name="neo4j", priority="NORMAL", strategy="first"),
                ]
            ),
        }

        handler = HandlerInfo(services=service_types)

        assert len(handler.services) == 2
        assert "llm" in handler.services
        assert "memory" in handler.services
        assert handler.services["llm"].providers[0].name == "openai"

    def test_handler_info_empty(self):
        """Test HandlerInfo with no services."""
        handler = HandlerInfo()

        assert handler.services == {}


class TestCircuitBreakerStats:
    """Tests for CircuitBreakerStats schema."""

    def test_valid_circuit_breaker_stats(self):
        """Test creating valid CircuitBreakerStats."""
        stats = CircuitBreakerStats(
            state="closed",
            failure_count=2,
            success_count=98,
            last_failure_time="2025-01-27T10:00:00Z",
            last_success_time="2025-01-27T10:05:00Z",
        )

        assert stats.state == "closed"
        assert stats.failure_count == 2
        assert stats.success_count == 98
        assert stats.last_failure_time == "2025-01-27T10:00:00Z"
        assert stats.last_success_time == "2025-01-27T10:05:00Z"

    def test_circuit_breaker_stats_open(self):
        """Test CircuitBreakerStats for open circuit."""
        stats = CircuitBreakerStats(
            state="open",
            failure_count=5,
            success_count=0,
            last_failure_time="2025-01-27T10:00:00Z",
        )

        assert stats.state == "open"
        assert stats.failure_count == 5
        assert stats.success_count == 0
        assert stats.last_success_time is None

    def test_circuit_breaker_stats_with_defaults(self):
        """Test CircuitBreakerStats with default values."""
        stats = CircuitBreakerStats(state="half-open")

        assert stats.state == "half-open"
        assert stats.failure_count == 0
        assert stats.success_count == 0
        assert stats.last_failure_time is None
        assert stats.last_success_time is None


class TestRegistryInfo:
    """Tests for RegistryInfo schema."""

    def test_valid_registry_info(self):
        """Test creating valid RegistryInfo."""
        provider1 = ProviderInfo(name="provider1", priority="HIGH", strategy="first")
        provider2 = ProviderInfo(name="provider2", priority="NORMAL", strategy="first")

        registry = RegistryInfo(
            handlers={
                "handler1": {
                    "llm": [provider1],
                    "memory": [provider2],
                }
            },
            global_services={
                "telemetry": [provider1],
            },
            circuit_breaker_stats={
                "provider1": CircuitBreakerStats(state="closed", failure_count=0, success_count=100),
            },
        )

        assert "handler1" in registry.handlers
        assert "llm" in registry.handlers["handler1"]
        assert len(registry.handlers["handler1"]["llm"]) == 1
        assert "telemetry" in registry.global_services
        assert "provider1" in registry.circuit_breaker_stats
        assert registry.circuit_breaker_stats["provider1"].state == "closed"

    def test_registry_info_empty(self):
        """Test RegistryInfo with empty data."""
        registry = RegistryInfo()

        assert registry.handlers == {}
        assert registry.global_services == {}
        assert registry.circuit_breaker_stats == {}

    def test_registry_info_complex_structure(self):
        """Test RegistryInfo with complex nested structure."""
        providers = [
            ProviderInfo(name=f"provider{i}", priority="NORMAL", strategy="first") for i in range(3)
        ]

        registry = RegistryInfo(
            handlers={
                "handler1": {
                    "llm": providers[:2],
                    "memory": providers[2:],
                },
                "handler2": {
                    "llm": providers[:1],
                },
            },
            global_services={
                "telemetry": providers[:1],
                "audit": providers[1:2],
            },
        )

        assert len(registry.handlers) == 2
        assert len(registry.handlers["handler1"]["llm"]) == 2
        assert len(registry.handlers["handler2"]["llm"]) == 1
        assert len(registry.global_services) == 2
