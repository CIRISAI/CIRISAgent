"""
Simple test for dual LLM service initialization with mock LLM support.
"""

import asyncio
import os

import pytest
import pytest_asyncio

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.runtime.service_initializer import ServiceInitializer
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.enums import ServiceType


@pytest.fixture(autouse=True)
def enable_mock_llm():
    """Ensure mock LLM is enabled for integration tests."""
    original = os.environ.get("CIRIS_MOCK_LLM")
    os.environ["CIRIS_MOCK_LLM"] = "true"
    yield
    if original is not None:
        os.environ["CIRIS_MOCK_LLM"] = original
    else:
        os.environ.pop("CIRIS_MOCK_LLM", None)


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_dual_llm_direct():
    """Test LLM initialization directly with mock LLM."""
    # Verify mock LLM is enabled
    assert os.environ.get("CIRIS_MOCK_LLM") == "true", "Mock LLM must be enabled"

    print(f"Mock LLM enabled: {os.environ.get('CIRIS_MOCK_LLM')}")
    print(f"Primary API key present: {bool(os.environ.get('OPENAI_API_KEY'))}")
    print(f"Secondary API key present: {bool(os.environ.get('CIRIS_OPENAI_API_KEY_2'))}")

    # Create essential config
    essential_config = EssentialConfig()

    # Create service initializer
    initializer = ServiceInitializer(essential_config)

    # Set up minimal dependencies
    initializer.service_registry = ServiceRegistry()
    initializer.time_service = TimeService()

    # Create a mock telemetry service
    initializer.telemetry_service = GraphTelemetryService(
        memory_bus=None, time_service=initializer.time_service  # OK for this test
    )

    # Initialize LLM services
    await initializer._initialize_llm_services(essential_config)

    # Check results
    llm_services = initializer.service_registry.get_services_by_type(ServiceType.LLM)

    print(f"\nFound {len(llm_services)} LLM services")

    # Get provider info
    provider_info = initializer.service_registry.get_provider_info(service_type=ServiceType.LLM)
    print(f"\nProvider info: {provider_info}")

    # Check global services directly
    if hasattr(initializer.service_registry, "_global_services"):
        global_llm = initializer.service_registry._global_services.get(ServiceType.LLM, [])
        print(f"\nFound {len(global_llm)} global LLM providers:")

        for provider in global_llm:
            print(f"  - Name: {provider.name}")
            print(f"    Priority: {provider.priority.name}")
            if provider.metadata:
                print(f"    Provider: {getattr(provider.metadata, 'provider', None)}")
                print(f"    Model: {getattr(provider.metadata, 'model', None)}")
                print(f"    Base URL: {getattr(provider.metadata, 'base_url', 'default')}")
            print()

        # With mock LLM, we should have at least 1 provider
        # If dual LLM is configured, we'll have 2
        print(f"Found {len(global_llm)} LLM providers")
        assert len(global_llm) >= 1, f"Expected at least 1 LLM provider, got {len(global_llm)}"

        # If we have multiple providers, verify priorities
        if len(global_llm) > 1:
            priorities = [p.priority.name for p in global_llm]
            assert "HIGH" in priorities, "No HIGH priority provider found"
            # Secondary providers typically have NORMAL or lower priority
            print(f"Dual LLM configuration detected with priorities: {priorities}")

    print("✓ LLM service test passed with mock LLM!")

    # Cleanup
    for service in llm_services:
        if hasattr(service, "stop"):
            try:
                await service.stop()
            except Exception as e:
                print(f"Warning: Error stopping service: {e}")


if __name__ == "__main__":
    asyncio.run(test_dual_llm_direct())
