"""
Configuration test fixtures.

Provides pricing configuration fixtures for config module tests.
"""

from datetime import datetime, timezone

import pytest

from ciris_engine.config.pricing_models import (
    CarbonIntensity,
    EnergyEstimates,
    EnvironmentalFactors,
    FallbackPricing,
    ModelConfig,
    PricingConfig,
    PricingMetadata,
    ProviderConfig,
)


@pytest.fixture
def mock_pricing_config():
    """Create a comprehensive mock pricing configuration for testing."""
    return PricingConfig(
        version="1.0.0",
        last_updated=datetime.now(timezone.utc),
        metadata=PricingMetadata(
            update_frequency="weekly",
            currency="USD",
            units="per_million_tokens",
            sources=["OpenAI API", "Anthropic API"],
            schema_version="1.0.0",
        ),
        providers={
            "openai": ProviderConfig(
                display_name="OpenAI",
                models={
                    "gpt-4o-mini": ModelConfig(
                        input_cost=15.0,
                        output_cost=60.0,
                        context_window=128000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-07-18",
                        description="GPT-4o Mini - cost-efficient small model",
                    ),
                    "gpt-4o": ModelConfig(
                        input_cost=250.0,
                        output_cost=1000.0,
                        context_window=128000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-05-13",
                        description="GPT-4o - flagship model",
                    ),
                },
                base_url="https://api.openai.com/v1",
            ),
            "anthropic": ProviderConfig(
                display_name="Anthropic",
                models={
                    "claude-3-opus": ModelConfig(
                        input_cost=1500.0,
                        output_cost=7500.0,
                        context_window=200000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-02-29",
                        description="Claude 3 Opus - most powerful model",
                    ),
                    "claude-3-sonnet": ModelConfig(
                        input_cost=300.0,
                        output_cost=1500.0,
                        context_window=200000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-02-29",
                        description="Claude 3 Sonnet - balanced model",
                    ),
                    "claude-3-haiku": ModelConfig(
                        input_cost=25.0,
                        output_cost=125.0,
                        context_window=200000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-03-07",
                        description="Claude 3 Haiku - fastest model",
                    ),
                },
                base_url="https://api.anthropic.com/v1",
            ),
        },
        environmental_factors=EnvironmentalFactors(
            energy_estimates=EnergyEstimates(
                model_patterns={
                    "gpt-4": {"kwh_per_1k_tokens": 0.0005},
                    "claude": {"kwh_per_1k_tokens": 0.0004},
                    "default": {"kwh_per_1k_tokens": 0.0003},
                }
            ),
            carbon_intensity=CarbonIntensity(
                global_average_g_co2_per_kwh=500.0, regions={"us_west": 350.0, "us_east": 450.0, "europe": 300.0}
            ),
        ),
        fallback_pricing=FallbackPricing(
            unknown_model=ModelConfig(
                input_cost=20.0,
                output_cost=20.0,
                context_window=4096,
                active=True,
                deprecated=False,
                effective_date="2024-01-01",
                description="Default pricing for unknown models",
            )
        ),
    )


@pytest.fixture
def mock_deprecated_model_config():
    """Create a pricing config with deprecated models for testing exclusions."""
    return PricingConfig(
        version="1.0.0",
        last_updated=datetime.now(timezone.utc),
        metadata=PricingMetadata(
            update_frequency="weekly",
            currency="USD",
            units="per_million_tokens",
            sources=["Test API"],
            schema_version="1.0.0",
        ),
        providers={
            "test_provider": ProviderConfig(
                display_name="Test Provider",
                models={
                    "deprecated-model": ModelConfig(
                        input_cost=100.0,
                        output_cost=200.0,
                        context_window=4096,
                        active=False,
                        deprecated=True,
                        effective_date="2023-01-01",
                        description="Deprecated test model",
                    )
                },
            )
        },
        environmental_factors=EnvironmentalFactors(
            energy_estimates=EnergyEstimates(model_patterns={"default": {"kwh_per_1k_tokens": 0.0003}}),
            carbon_intensity=CarbonIntensity(global_average_g_co2_per_kwh=500.0, regions={}),
        ),
        fallback_pricing=FallbackPricing(
            unknown_model=ModelConfig(
                input_cost=20.0,
                output_cost=20.0,
                context_window=4096,
                active=True,
                deprecated=False,
                effective_date="2024-01-01",
                description="Default pricing",
            )
        ),
    )


__all__ = ["mock_pricing_config", "mock_deprecated_model_config"]
