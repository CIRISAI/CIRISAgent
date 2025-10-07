"""
Simple test for dual LLM service initialization.
"""

import asyncio
import os

import pytest

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.runtime.service_initializer import ServiceInitializer
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.enums import ServiceType


async def test_dual_llm_direct():
    """Test LLM initialization directly."""
    # Ensure environment variables are set
    print(f"Primary API key present: {bool(os.environ.get('OPENAI_API_KEY'))}")
    print(f"Secondary API key present: {bool(os.environ.get('CIRIS_OPENAI_API_KEY_2'))}")
    print(f"Secondary base URL: {os.environ.get('CIRIS_OPENAI_API_BASE_2')}")
    print(f"Secondary model: {os.environ.get('CIRIS_OPENAI_MODEL_NAME_2')}")

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

        # Check if dual LLM is configured
        if len(global_llm) == 1:
            print("ℹ️  Only one LLM provider configured (dual LLM not enabled)")
            print("   To enable dual LLM, set CIRIS_OPENAI_API_KEY_2 environment variable")
            pytest.skip("Secondary API key not configured, skipping dual LLM test")

        # Verify we have 2 providers
        assert len(global_llm) == 2, f"Expected 2 LLM providers, got {len(global_llm)}"

        # Verify priorities
        priorities = [p.priority.name for p in global_llm]
        assert "HIGH" in priorities, "No HIGH priority provider found"
        assert "NORMAL" in priorities, "No NORMAL priority provider found"

    print("✓ Dual LLM service test passed!")

    # Cleanup
    for service in llm_services:
        if hasattr(service, "stop"):
            await service.stop()


if __name__ == "__main__":
    asyncio.run(test_dual_llm_direct())
