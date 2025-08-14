"""
Tests for domain-aware LLM routing in LLMBus.

These tests ensure that LLM requests are properly routed to domain-specific
models (e.g., medical, legal, financial) while maintaining backward compatibility.
"""

import asyncio
from datetime import datetime
from typing import List, Tuple
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from pydantic import BaseModel, Field

from ciris_engine.logic.buses.llm_bus import DistributionStrategy, LLMBus
from ciris_engine.logic.registries.base import Priority, ServiceRegistry
from ciris_engine.protocols.services import LLMService
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.capabilities import LLMCapabilities


class TestResponse(BaseModel):
    """Test response model for structured output."""

    answer: str = Field(..., description="The answer")
    confidence: float = Field(..., ge=0.0, le=1.0)


class MockLLMService(LLMService):
    """Mock LLM service for testing."""

    def __init__(self, domain: str = "general", model: str = "gpt-4"):
        self.domain = domain
        self.model = model
        self.call_count = 0
        self.is_healthy_flag = True

    def get_capabilities(self):
        """Return capabilities."""
        return MagicMock(
            supports_operation_list=[LLMCapabilities.CALL_LLM_STRUCTURED.value],
            actions=[LLMCapabilities.CALL_LLM_STRUCTURED.value],
        )

    async def is_healthy(self) -> bool:
        """Check health status."""
        return self.is_healthy_flag

    async def call_llm_structured(
        self,
        messages: List[dict],
        response_model,
        max_tokens: int = 1024,
        temperature: float = 0.0,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Generate structured output."""
        self.call_count += 1

        response = TestResponse(answer=f"Response from {self.domain} model ({self.model})", confidence=0.95)

        usage = ResourceUsage(
            tokens_used=100,
            tokens_input=50,
            tokens_output=50,
            model_used=self.model,
            cost_cents=0.1,
            carbon_grams=0.01,
            energy_kwh=0.001,
        )

        return response, usage


class TestDomainAwareLLMRouting:
    """Test domain-aware routing in LLMBus."""

    @pytest.fixture
    def time_service(self):
        """Create mock time service."""
        mock = MagicMock(spec=TimeServiceProtocol)
        mock.now.return_value = datetime.now()
        mock.timestamp.return_value = 1234567890.0
        return mock

    @pytest.fixture
    def telemetry_service(self):
        """Create mock telemetry service."""
        mock = AsyncMock(spec=TelemetryServiceProtocol)
        return mock

    @pytest.fixture
    def service_registry(self):
        """Create mock service registry."""
        return ServiceRegistry()

    @pytest.fixture
    def llm_bus(self, service_registry, time_service, telemetry_service):
        """Create LLMBus instance."""
        return LLMBus(
            service_registry=service_registry,
            time_service=time_service,
            telemetry_service=telemetry_service,
            distribution_strategy=DistributionStrategy.LATENCY_BASED,
        )

    @pytest.mark.asyncio
    async def test_medical_domain_routing(self, llm_bus, service_registry):
        """Test that medical domain requests route to medical LLM."""
        # Register multiple LLM services
        general_llm = MockLLMService(domain="general", model="gpt-4")
        medical_llm = MockLLMService(domain="medical", model="llama3-medical-70b")
        legal_llm = MockLLMService(domain="legal", model="legal-bert")

        # Register with appropriate metadata
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=general_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "general", "model": "gpt-4"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "medical", "model": "llama3-medical-70b"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=legal_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "legal", "model": "legal-bert"},
        )

        # Make a medical domain request
        messages = [{"role": "user", "content": "Analyze patient symptoms"}]

        response, usage = await llm_bus.call_llm_structured(
            messages=messages,
            response_model=TestResponse,
            handler_name="medical_handler",
            domain="medical",  # Request medical domain
        )

        # Verify medical LLM was called
        assert medical_llm.call_count == 1
        assert general_llm.call_count == 0
        assert legal_llm.call_count == 0
        assert "medical" in response.answer.lower()
        assert usage.model_used == "llama3-medical-70b"

    @pytest.mark.asyncio
    async def test_fallback_to_general_when_domain_unavailable(self, llm_bus, service_registry):
        """Test fallback to general LLM when specific domain is unavailable."""
        # Only register general LLM
        general_llm = MockLLMService(domain="general", model="gpt-4")

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=general_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "general", "model": "gpt-4"},
        )

        # Request medical domain (not available)
        messages = [{"role": "user", "content": "Legal question"}]

        response, usage = await llm_bus.call_llm_structured(
            messages=messages,
            response_model=TestResponse,
            handler_name="legal_handler",
            domain="legal",  # Request legal domain (not available)
        )

        # Should fallback to general
        assert general_llm.call_count == 1
        assert "general" in response.answer.lower()

    @pytest.mark.asyncio
    async def test_no_domain_uses_all_services(self, llm_bus, service_registry):
        """Test that requests without domain can use any service."""
        # Register multiple LLM services
        general_llm = MockLLMService(domain="general", model="gpt-4")
        medical_llm = MockLLMService(domain="medical", model="llama3-medical-70b")

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=general_llm,
            priority=Priority.HIGH,  # Higher priority
            metadata={"domain": "general", "model": "gpt-4"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "medical", "model": "llama3-medical-70b"},
        )

        # Request without domain
        messages = [{"role": "user", "content": "General question"}]

        response, usage = await llm_bus.call_llm_structured(
            messages=messages,
            response_model=TestResponse,
            handler_name="general_handler",
            # No domain specified
        )

        # Should use highest priority (general)
        assert general_llm.call_count == 1
        assert medical_llm.call_count == 0

    @pytest.mark.asyncio
    async def test_domain_priority_boost(self, llm_bus, service_registry):
        """Test that domain-specific services get priority boost."""
        # Register two medical LLMs with different base priorities
        medical_primary = MockLLMService(domain="medical", model="llama3-medical-70b")
        medical_backup = MockLLMService(domain="medical", model="biogpt")
        general_llm = MockLLMService(domain="general", model="gpt-4")

        # Medical backup has better base priority
        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_backup,
            priority=Priority.HIGH,
            metadata={"domain": "medical", "model": "biogpt"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_primary,
            priority=Priority.NORMAL,
            metadata={"domain": "medical", "model": "llama3-medical-70b"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=general_llm,
            priority=Priority.CRITICAL,  # Best base priority
            metadata={"domain": "general", "model": "gpt-4"},
        )

        # Request medical domain
        messages = [{"role": "user", "content": "Medical analysis"}]

        response, usage = await llm_bus.call_llm_structured(
            messages=messages, response_model=TestResponse, handler_name="medical_handler", domain="medical"
        )

        # Should use medical_backup (HIGH priority beats NORMAL even with boost)
        assert medical_backup.call_count == 1
        assert medical_primary.call_count == 0
        assert general_llm.call_count == 0

    @pytest.mark.asyncio
    async def test_failover_within_domain(self, llm_bus, service_registry):
        """Test failover to another service within same domain."""
        # Register two medical LLMs
        medical_primary = MockLLMService(domain="medical", model="llama3-medical-70b")
        medical_backup = MockLLMService(domain="medical", model="biogpt")

        # Make primary fail
        medical_primary.call_llm_structured = AsyncMock(side_effect=Exception("Primary medical LLM failed"))

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_primary,
            priority=Priority.HIGH,
            metadata={"domain": "medical", "model": "llama3-medical-70b"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_backup,
            priority=Priority.NORMAL,
            metadata={"domain": "medical", "model": "biogpt"},
        )

        # Request medical domain
        messages = [{"role": "user", "content": "Medical question"}]

        response, usage = await llm_bus.call_llm_structured(
            messages=messages, response_model=TestResponse, handler_name="medical_handler", domain="medical"
        )

        # Should failover to backup
        assert medical_backup.call_count == 1
        assert "medical" in response.answer.lower()
        assert usage.model_used == "biogpt"

    @pytest.mark.asyncio
    async def test_circuit_breaker_per_domain(self, llm_bus, service_registry):
        """Test that circuit breakers work independently per domain."""
        medical_llm = MockLLMService(domain="medical", model="llama3-medical-70b")
        general_llm = MockLLMService(domain="general", model="gpt-4")

        # Make medical LLM fail repeatedly to trip circuit breaker
        fail_count = 0

        async def failing_medical_call(*args, **kwargs):
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 5:  # Fail first 5 times
                raise Exception("Medical LLM error")
            return TestResponse(answer="Recovery", confidence=0.9), ResourceUsage(
                tokens_used=100, model_used="llama3-medical-70b"
            )

        medical_llm.call_llm_structured = failing_medical_call

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_llm,
            priority=Priority.HIGH,
            metadata={"domain": "medical", "model": "llama3-medical-70b"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=general_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "general", "model": "gpt-4"},
        )

        # Configure circuit breaker to trip after 3 failures
        llm_bus.circuit_breaker_config = {"failure_threshold": 3, "recovery_timeout": 60.0, "success_threshold": 2}

        # Try medical domain multiple times to trip circuit
        for i in range(3):
            try:
                await llm_bus.call_llm_structured(
                    messages=[{"role": "user", "content": f"Medical Q{i}"}],
                    response_model=TestResponse,
                    handler_name="medical_handler",
                    domain="medical",
                )
            except RuntimeError:
                pass  # Expected to fail

        # General domain should still work
        response, usage = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "General question"}],
            response_model=TestResponse,
            handler_name="general_handler",
            domain="general",
        )

        assert general_llm.call_count == 1
        assert "general" in response.answer.lower()

    @pytest.mark.asyncio
    async def test_backward_compatibility_without_domain(self, llm_bus, service_registry):
        """Test backward compatibility when domain parameter is not used."""
        general_llm = MockLLMService(domain="general", model="gpt-4")

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=general_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "general", "model": "gpt-4"},
        )

        # Old-style call without domain parameter
        messages = [{"role": "user", "content": "Question"}]

        response, usage = await llm_bus.call_llm_structured(
            messages=messages,
            response_model=TestResponse,
            handler_name="handler",
            # No domain parameter - backward compatibility
        )

        assert general_llm.call_count == 1
        assert response is not None
        assert usage is not None

    @pytest.mark.asyncio
    async def test_multiple_domains_registered(self, llm_bus, service_registry):
        """Test system with multiple specialized domains."""
        # Register LLMs for different domains
        domains = {
            "general": MockLLMService("general", "gpt-4"),
            "medical": MockLLMService("medical", "llama3-medical-70b"),
            "legal": MockLLMService("legal", "legal-bert"),
            "financial": MockLLMService("financial", "finbert"),
            "scientific": MockLLMService("scientific", "scigpt"),
        }

        for domain, service in domains.items():
            service_registry.register_service(
                service_type=ServiceType.LLM,
                provider=service,
                priority=Priority.NORMAL,
                metadata={"domain": domain, "model": service.model},
            )

        # Test each domain routes correctly
        test_cases = [
            ("medical", "patient symptoms"),
            ("legal", "contract review"),
            ("financial", "market analysis"),
            ("scientific", "research paper"),
        ]

        for domain, content in test_cases:
            # Reset call counts
            for service in domains.values():
                service.call_count = 0

            # Make domain-specific request
            response, usage = await llm_bus.call_llm_structured(
                messages=[{"role": "user", "content": content}],
                response_model=TestResponse,
                handler_name=f"{domain}_handler",
                domain=domain,
            )

            # Verify correct service was called
            assert domains[domain].call_count == 1
            assert domain in response.answer.lower()

            # Verify others weren't called
            for other_domain, other_service in domains.items():
                if other_domain != domain:
                    assert other_service.call_count == 0

    @pytest.mark.asyncio
    async def test_domain_filtering_with_unhealthy_services(self, llm_bus, service_registry):
        """Test that unhealthy services are filtered out even if domain matches."""
        medical_primary = MockLLMService(domain="medical", model="llama3-medical-70b")
        medical_backup = MockLLMService(domain="medical", model="biogpt")

        # Make primary unhealthy
        medical_primary.is_healthy_flag = False

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_primary,
            priority=Priority.HIGH,
            metadata={"domain": "medical", "model": "llama3-medical-70b"},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_backup,
            priority=Priority.NORMAL,
            metadata={"domain": "medical", "model": "biogpt"},
        )

        # Request medical domain
        response, usage = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Medical question"}],
            response_model=TestResponse,
            handler_name="medical_handler",
            domain="medical",
        )

        # Should use backup (primary is unhealthy)
        assert medical_primary.call_count == 0
        assert medical_backup.call_count == 1
        assert usage.model_used == "biogpt"


class TestDomainRoutingIntegration:
    """Integration tests for domain routing with real-world scenarios."""

    @pytest.mark.asyncio
    async def test_medical_dsdma_integration(self):
        """Test integration with medical DSDMA calling LLMBus."""
        # Setup
        time_service = MagicMock(spec=TimeServiceProtocol)
        time_service.now.return_value = datetime.now()
        time_service.timestamp.return_value = 1234567890.0

        service_registry = ServiceRegistry()
        llm_bus = LLMBus(
            service_registry=service_registry,
            time_service=time_service,
            distribution_strategy=DistributionStrategy.LATENCY_BASED,
        )

        # Register medical and general LLMs
        medical_llm = MockLLMService(domain="medical", model="llama3-medical-70b")
        general_llm = MockLLMService(domain="general", model="gpt-4")

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=medical_llm,
            priority=Priority.HIGH,
            metadata={"domain": "medical", "model": "llama3-medical-70b", "offline": True},
        )

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=general_llm,
            priority=Priority.NORMAL,
            metadata={"domain": "general", "model": "gpt-4"},
        )

        # Simulate medical DSDMA call
        messages = [
            {"role": "system", "content": "You are a medical AI assistant."},
            {"role": "user", "content": "Analyze these symptoms: fever, cough, fatigue"},
        ]

        # Medical DSDMA would call with domain="medical"
        response, usage = await llm_bus.call_llm_structured(
            messages=messages,
            response_model=TestResponse,
            handler_name="medical_dsdma",
            domain="medical",  # Critical: Routes to medical LLM
            temperature=0.0,  # Medical needs deterministic responses
            max_tokens=2048,  # Medical may need longer responses
        )

        # Verify medical LLM was used
        assert medical_llm.call_count == 1
        assert general_llm.call_count == 0
        assert usage.model_used == "llama3-medical-70b"
        assert "medical" in response.answer.lower()

    @pytest.mark.asyncio
    async def test_legal_domain_with_compliance(self):
        """Test legal domain routing with compliance metadata."""
        time_service = MagicMock(spec=TimeServiceProtocol)
        time_service.now.return_value = datetime.now()
        time_service.timestamp.return_value = 1234567890.0

        service_registry = ServiceRegistry()
        llm_bus = LLMBus(service_registry=service_registry, time_service=time_service)

        # Register legal LLM with compliance metadata
        legal_llm = MockLLMService(domain="legal", model="legal-bert-large")

        service_registry.register_service(
            service_type=ServiceType.LLM,
            provider=legal_llm,
            priority=Priority.HIGH,
            metadata={
                "domain": "legal",
                "model": "legal-bert-large",
                "jurisdiction": "US",
                "bar_certified": True,
                "last_training": "2024-01",
            },
        )

        # Legal document analysis request
        response, usage = await llm_bus.call_llm_structured(
            messages=[{"role": "user", "content": "Review this contract clause"}],
            response_model=TestResponse,
            handler_name="legal_analyzer",
            domain="legal",
        )

        assert legal_llm.call_count == 1
        assert usage.model_used == "legal-bert-large"
        assert "legal" in response.answer.lower()


# Run tests with: pytest tests/logic/buses/test_llm_bus_domain_routing.py -v
