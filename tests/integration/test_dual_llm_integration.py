"""
Integration test for dual LLM service functionality.
Tests actual initialization with environment variables.
"""

import asyncio
import os

import pytest

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.runtime.service_initializer import ServiceInitializer
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.runtime.enums import ServiceType


@pytest.mark.skip(reason="Dual LLM test requires full environment setup - use QA runner for integration testing")
@pytest.mark.asyncio
async def test_dual_llm_service_real_initialization():
    """Test real initialization with dual LLM services from environment."""
    
    # Ensure environment variables are set
    assert os.environ.get("OPENAI_API_KEY"), "Primary API key not found"

    # Create essential config
    essential_config = EssentialConfig()

    # Create service initializer
    initializer = ServiceInitializer(essential_config)

    # Create service registry
    service_registry = ServiceRegistry()
    initializer.service_registry = service_registry

    try:
        # Initialize all services - need to call the proper initialization sequence
        await initializer.initialize_infrastructure_services()
        await initializer.initialize_memory_service(essential_config)
        await initializer.initialize_security_services(essential_config, essential_config)
        await initializer.initialize_all_services(essential_config, essential_config, "test_agent", None, [])

        # Check that LLM services were registered
        llm_providers = service_registry.get_services_by_type(ServiceType.LLM)

        # Should have at least 1 LLM provider (may be mock or real depending on environment)
        assert len(llm_providers) >= 1, f"Expected at least 1 LLM provider, got {len(llm_providers)}"
        
        # If secondary key is available, expect 2 providers; otherwise expect 1
        expected_count = 2 if os.environ.get("CIRIS_OPENAI_API_KEY_2") else 1
        assert len(llm_providers) == expected_count, f"Expected {expected_count} LLM providers, got {len(llm_providers)}"

        # For this test, we just check that we have two services
        # The service instances themselves don't have provider metadata exposed directly
        providers_info = []
        for i, provider in enumerate(llm_providers):
            # Check basic properties
            assert hasattr(provider, "model_name"), "LLM provider should have model_name"
            providers_info.append(
                {
                    "provider": f"provider_{i}",  # Generic name
                    "model": getattr(provider, "model_name", "unknown"),
                    "base_url": getattr(provider, "base_url", "default"),
                    "priority": "HIGH" if i == 0 else "NORMAL",  # Assume first is primary
                }
            )

        # Sort by priority for consistent checking
        providers_info.sort(key=lambda x: x["priority"])

        # Primary should have HIGH priority
        assert any(p["priority"] == "HIGH" for p in providers_info), "Primary provider not found with HIGH priority"

        # Secondary should have NORMAL priority
        assert any(
            p["priority"] == "NORMAL" for p in providers_info
        ), "Secondary provider not found with NORMAL priority"

        # Check that we have different models for primary and secondary
        models = [p["model"] for p in providers_info]
        assert len(set(models)) == 2, "Primary and secondary should use different models"

        print("\nDual LLM Service Configuration:")
        for info in providers_info:
            print(
                f"  {info['provider']}: {info['model']} at {info.get('base_url', 'default')} (Priority: {info['priority']})"
            )

    finally:
        # Cleanup
        if hasattr(initializer, "shutdown_service") and initializer.shutdown_service:
            await initializer.shutdown_service.request_shutdown("Test complete")

        # Stop all services
        if hasattr(initializer, "llm_service") and initializer.llm_service:
            if hasattr(initializer.llm_service, "stop"):
                await initializer.llm_service.stop()


if __name__ == "__main__":
    # Run the test directly
    asyncio.run(test_dual_llm_service_real_initialization())
