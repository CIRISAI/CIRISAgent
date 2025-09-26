"""
Comprehensive test coverage for LLM Pricing Calculator.

Targets 80% coverage by testing all methods, edge cases, and error scenarios.
Covers cost calculation, environmental impact, model patterns, and configuration management.
"""

import logging
from unittest.mock import Mock, patch
from datetime import datetime
import pytest

from ciris_engine.logic.services.runtime.llm_service.pricing_calculator import LLMPricingCalculator
from ciris_engine.config.pricing_models import (
    PricingConfig, ProviderConfig, ModelConfig, EnvironmentalFactors,
    EnergyEstimates, CarbonIntensity, FallbackPricing, PricingMetadata
)
from ciris_engine.schemas.runtime.resources import ResourceUsage


class TestLLMPricingCalculatorComprehensive:
    """Comprehensive test coverage for LLM Pricing Calculator."""

    def setup_method(self):
        """Set up test fixtures."""
        # Create a mock pricing config with test data
        self.mock_openai_config = ModelConfig(
            input_cost=15.0,
            output_cost=60.0,
            context_window=128000,
            active=True,
            deprecated=False,
            effective_date="2024-07-18",
            description="GPT-4o model"
        )

        self.mock_anthropic_config = ModelConfig(
            input_cost=300.0,
            output_cost=1500.0,
            context_window=200000,
            active=True,
            deprecated=False,
            effective_date="2024-06-20",
            description="Claude-3 Opus"
        )

        self.mock_fallback_config = ModelConfig(
            input_cost=100.0,
            output_cost=100.0,
            context_window=4096,
            active=True,
            deprecated=False,
            effective_date="2024-01-01",
            description="Unknown model fallback"
        )

        # Create mock providers
        self.mock_openai_provider = ProviderConfig(
            display_name="OpenAI",
            base_url="https://api.openai.com",
            models={
                "gpt-4o": self.mock_openai_config,
                "gpt-4o-mini": ModelConfig(
                    input_cost=1.5,
                    output_cost=6.0,
                    context_window=128000,
                    active=True,
                    deprecated=False,
                    effective_date="2024-07-18",
                    description="GPT-4o mini"
                ),
                "gpt-4-turbo": ModelConfig(
                    input_cost=100.0,
                    output_cost=300.0,
                    context_window=128000,
                    active=True,
                    deprecated=False,
                    effective_date="2024-04-09",
                    description="GPT-4 Turbo"
                ),
                "gpt-3.5-turbo": ModelConfig(
                    input_cost=5.0,
                    output_cost=15.0,
                    context_window=16385,
                    active=False,
                    deprecated=True,
                    effective_date="2023-06-13",
                    description="GPT-3.5 Turbo (deprecated)"
                )
            }
        )

        self.mock_anthropic_provider = ProviderConfig(
            display_name="Anthropic",
            base_url="https://api.anthropic.com",
            models={
                "claude-3-opus": self.mock_anthropic_config,
                "claude-3-sonnet": ModelConfig(
                    input_cost=300.0,
                    output_cost=1500.0,
                    context_window=200000,
                    active=True,
                    deprecated=False,
                    effective_date="2024-02-29",
                    description="Claude-3 Sonnet"
                ),
                "claude-3-haiku": ModelConfig(
                    input_cost=25.0,
                    output_cost=125.0,
                    context_window=200000,
                    active=True,
                    deprecated=False,
                    effective_date="2024-03-07",
                    description="Claude-3 Haiku"
                )
            }
        )

        self.mock_together_provider = ProviderConfig(
            display_name="Together",
            base_url="https://api.together.xyz",
            models={
                "llama-3.1-405b-instruct": ModelConfig(
                    input_cost=300.0,
                    output_cost=300.0,
                    context_window=131072,
                    active=True,
                    deprecated=False,
                    effective_date="2024-07-23",
                    description="Llama 3.1 405B Instruct"
                ),
                "llama-3.1-70b-instruct": ModelConfig(
                    input_cost=88.0,
                    output_cost=88.0,
                    context_window=131072,
                    active=True,
                    deprecated=False,
                    effective_date="2024-07-23",
                    description="Llama 3.1 70B Instruct"
                )
            }
        )

        self.mock_lambda_provider = ProviderConfig(
            display_name="Lambda Labs",
            base_url="https://api.lambdalabs.com",
            models={
                "llama-4-maverick-17b-128e-instruct-fp8": ModelConfig(
                    input_cost=30.0,
                    output_cost=30.0,
                    context_window=131072,
                    active=True,
                    deprecated=False,
                    effective_date="2024-09-01",
                    description="Llama 4 Maverick 17B"
                )
            }
        )

        # Create mock environmental factors
        self.mock_env_factors = EnvironmentalFactors(
            energy_estimates=EnergyEstimates(
                model_patterns={
                    "gpt-4": {"kwh_per_1k_tokens": 0.0048},
                    "claude-3": {"kwh_per_1k_tokens": 0.0051},
                    "llama": {"kwh_per_1k_tokens": 0.0032},
                    "unknown": {"kwh_per_1k_tokens": 0.005},
                    "default": {"kwh_per_1k_tokens": 0.005}
                }
            ),
            carbon_intensity=CarbonIntensity(
                global_average_g_co2_per_kwh=429.0,
                regions={
                    "us": 386.0,
                    "eu": 296.0
                }
            )
        )

        # Create mock pricing config
        self.mock_pricing_config = PricingConfig(
            version="1.0.0",
            last_updated=datetime.now(),
            metadata=PricingMetadata(
                update_frequency="daily",
                currency="USD",
                units="per_million_tokens",
                sources=["OpenAI", "Anthropic", "Together"],
                schema_version="1.0"
            ),
            providers={
                "openai": self.mock_openai_provider,
                "anthropic": self.mock_anthropic_provider,
                "together": self.mock_together_provider,
                "lambda_labs": self.mock_lambda_provider
            },
            environmental_factors=self.mock_env_factors,
            fallback_pricing=FallbackPricing(
                unknown_model=self.mock_fallback_config,
                deprecated_model=self.mock_fallback_config
            )
        )

    def test_initialization_with_config(self):
        """Test initialization with provided pricing configuration."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        assert calculator.pricing_config == self.mock_pricing_config

    def test_initialization_without_config(self):
        """Test initialization without pricing configuration (loads from file)."""
        with patch('ciris_engine.logic.services.runtime.llm_service.pricing_calculator.get_pricing_config') as mock_get_config:
            mock_get_config.return_value = self.mock_pricing_config

            calculator = LLMPricingCalculator()

            assert calculator.pricing_config == self.mock_pricing_config
            mock_get_config.assert_called_once()

    def test_calculate_cost_and_impact_known_model(self):
        """Test cost and impact calculation for known model."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        result = calculator.calculate_cost_and_impact(
            model_name="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            provider_name="openai"
        )

        # Verify ResourceUsage structure
        assert isinstance(result, ResourceUsage)
        assert result.tokens_used == 1500
        assert result.tokens_input == 1000
        assert result.tokens_output == 500
        assert result.model_used == "gpt-4o"

        # Verify cost calculation: (1000/1M * 15.0) + (500/1M * 60.0) = 0.015 + 0.030 = 0.045 cents
        expected_cost = (1000 / 1_000_000) * 15.0 + (500 / 1_000_000) * 60.0
        assert abs(result.cost_cents - expected_cost) < 0.001

        # Verify environmental impact
        assert result.energy_kwh > 0
        assert result.carbon_grams > 0

    def test_calculate_cost_and_impact_without_provider(self):
        """Test cost calculation when provider name is not specified."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        result = calculator.calculate_cost_and_impact(
            model_name="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500
        )

        assert isinstance(result, ResourceUsage)
        assert result.tokens_used == 1500
        assert result.model_used == "gpt-4o"
        # Cost should be calculated using gpt-4o pricing
        expected_cost = (1000 / 1_000_000) * 15.0 + (500 / 1_000_000) * 60.0
        assert abs(result.cost_cents - expected_cost) < 0.001

    def test_calculate_cost_and_impact_with_region(self):
        """Test cost calculation with specific region for carbon intensity."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        result = calculator.calculate_cost_and_impact(
            model_name="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            region="us"
        )

        assert isinstance(result, ResourceUsage)
        assert result.carbon_grams > 0
        # US carbon intensity should be used

    def test_get_model_config_exact_match(self):
        """Test _get_model_config with exact provider and model match."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        config = calculator._get_model_config("gpt-4o", "openai")

        assert config == self.mock_openai_config

    def test_get_model_config_find_across_providers(self):
        """Test _get_model_config finding model across all providers."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        config = calculator._get_model_config("claude-3-opus", None)

        assert config == self.mock_anthropic_config

    def test_get_model_config_pattern_matching_openai(self):
        """Test _get_model_config with OpenAI pattern matching."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        # Test gpt-4o-mini pattern
        config = calculator._get_model_config("gpt-4o-mini-2024-07-18", None)
        assert config.input_cost == 1.5  # gpt-4o-mini pricing

        # Test gpt-4o pattern
        config = calculator._get_model_config("gpt-4o-2024-05-13", None)
        assert config.input_cost == 15.0  # gpt-4o pricing

        # Test gpt-4-turbo pattern
        config = calculator._get_model_config("gpt-4-turbo-preview", None)
        assert config.input_cost == 100.0  # gpt-4-turbo pricing

        # Test gpt-3.5-turbo pattern
        config = calculator._get_model_config("gpt-3.5-turbo-0125", None)
        assert config.input_cost == 5.0  # gpt-3.5-turbo pricing

    def test_get_model_config_pattern_matching_anthropic(self):
        """Test _get_model_config with Anthropic pattern matching."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        # Test Claude Opus pattern
        config = calculator._get_model_config("claude-3-opus-20240229", None)
        assert config.input_cost == 300.0  # claude-3-opus pricing

        # Test Claude Sonnet pattern
        config = calculator._get_model_config("claude-3-sonnet-20240229", None)
        assert config.input_cost == 300.0  # claude-3-sonnet pricing

        # Test Claude Haiku pattern
        config = calculator._get_model_config("claude-3-haiku-20240307", None)
        assert config.input_cost == 25.0  # claude-3-haiku pricing

    def test_get_model_config_pattern_matching_llama(self):
        """Test _get_model_config with Llama pattern matching."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        # Test Llama 405B pattern
        config = calculator._get_model_config("llama-3.1-405b-instruct-turbo", None)
        assert config.input_cost == 300.0  # llama-3.1-405b pricing

        # Test Llama 70B pattern
        config = calculator._get_model_config("llama-3.1-70b-instruct", None)
        assert config.input_cost == 88.0  # llama-3.1-70b pricing

        # Test Llama 17B/Maverick pattern
        config = calculator._get_model_config("llama-4-maverick-17b-custom", None)
        assert config.input_cost == 30.0  # llama-4-maverick-17b pricing

    def test_get_model_config_fallback_pricing(self):
        """Test _get_model_config fallback to unknown model pricing."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        config = calculator._get_model_config("unknown-model-123", None)

        assert config == self.mock_fallback_config

    def test_try_pattern_matching_no_match(self):
        """Test _try_pattern_matching returns None for unmatched patterns."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        config = calculator._try_pattern_matching("random-model-name")

        assert config is None

    def test_calculate_energy_consumption(self):
        """Test _calculate_energy_consumption method."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        energy = calculator._calculate_energy_consumption("gpt-4o", 10000)

        # Should use GPT-4 energy estimate: 10000/1000 * 0.0048 = 0.048 kWh
        expected = (10000 / 1000) * 0.0048
        assert abs(energy - expected) < 0.001

    def test_calculate_carbon_emissions_default_region(self):
        """Test _calculate_carbon_emissions with default (global) region."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        carbon = calculator._calculate_carbon_emissions(0.1)  # 0.1 kWh

        # Should use global average: 0.1 * 429.0 = 42.9 grams
        expected = 0.1 * 429.0
        assert abs(carbon - expected) < 0.001

    def test_calculate_carbon_emissions_specific_region(self):
        """Test _calculate_carbon_emissions with specific region."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        carbon_us = calculator._calculate_carbon_emissions(0.1, "us")
        carbon_eu = calculator._calculate_carbon_emissions(0.1, "eu")

        # US: 0.1 * 386.0 = 38.6 grams
        assert abs(carbon_us - 38.6) < 0.001
        # EU: 0.1 * 296.0 = 29.6 grams
        assert abs(carbon_eu - 29.6) < 0.001

    def test_get_model_info_with_provider(self):
        """Test get_model_info with specified provider."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        info = calculator.get_model_info("gpt-4o", "openai")

        assert info["model_name"] == "gpt-4o"
        assert info["provider_name"] == "openai"
        assert info["input_cost_per_million"] == 15.0
        assert info["output_cost_per_million"] == 60.0
        assert info["context_window"] == 128000
        assert info["active"] is True
        assert info["deprecated"] is False
        assert info["description"] == "GPT-4o model"
        assert "energy_per_1k_tokens" in info
        assert "carbon_intensity_global" in info

    def test_get_model_info_without_provider(self):
        """Test get_model_info without provider (auto-detection)."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        info = calculator.get_model_info("claude-3-opus")

        assert info["model_name"] == "claude-3-opus"
        assert info["provider_name"] == "anthropic"
        assert info["input_cost_per_million"] == 300.0

    def test_list_available_models_active_only(self):
        """Test list_available_models with active_only=True."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        models = calculator.list_available_models(active_only=True)

        # Should exclude gpt-3.5-turbo (deprecated/inactive)
        model_names = [m["model_name"] for m in models]
        assert "gpt-4o" in model_names
        assert "claude-3-opus" in model_names
        assert "gpt-3.5-turbo" not in model_names

    def test_list_available_models_all_models(self):
        """Test list_available_models with active_only=False."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        models = calculator.list_available_models(active_only=False)

        # Should include all models including inactive/deprecated
        model_names = [m["model_name"] for m in models]
        assert "gpt-4o" in model_names
        assert "claude-3-opus" in model_names
        assert "gpt-3.5-turbo" in model_names  # Now included

    def test_list_available_models_specific_provider(self):
        """Test list_available_models for specific provider."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        models = calculator.list_available_models(provider_name="anthropic", active_only=True)

        # Should only include Anthropic models
        provider_names = set(m["provider_name"] for m in models)
        assert provider_names == {"anthropic"}

        model_names = [m["model_name"] for m in models]
        assert "claude-3-opus" in model_names
        assert "claude-3-sonnet" in model_names
        assert "claude-3-haiku" in model_names

    def test_list_available_models_specific_provider_all_models(self):
        """Test list_available_models for specific provider with all models."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        models = calculator.list_available_models(provider_name="openai", active_only=False)

        # Should include all OpenAI models including inactive
        model_names = [m["model_name"] for m in models]
        assert "gpt-4o" in model_names
        assert "gpt-3.5-turbo" in model_names  # Inactive but included

    def test_reload_pricing_config(self):
        """Test reload_pricing_config method."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        new_config = Mock()
        new_config.version = "2.0.0"

        with patch('ciris_engine.logic.services.runtime.llm_service.pricing_calculator.get_pricing_config') as mock_get_config:
            mock_get_config.return_value = new_config

            calculator.reload_pricing_config()

            assert calculator.pricing_config == new_config
            mock_get_config.assert_called_once_with(reload=True)

    def test_logging_behavior(self, caplog):
        """Test logging behavior for debugging and warnings."""
        with caplog.at_level(logging.DEBUG):
            calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

            # Test successful calculation with debug logging
            calculator.calculate_cost_and_impact("gpt-4o", 1000, 500, "openai")

            # Check debug logs
            debug_logs = [record for record in caplog.records if record.levelno == logging.DEBUG]
            assert any("Initialized pricing calculator" in record.message for record in debug_logs)
            assert any("Found exact config for" in record.message for record in debug_logs)
            assert any("Calculated usage for" in record.message for record in debug_logs)

    def test_logging_fallback_warning(self, caplog):
        """Test warning logging for fallback pricing."""
        with caplog.at_level(logging.WARNING):
            calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

            # Use unknown model to trigger fallback
            calculator.calculate_cost_and_impact("unknown-model", 1000, 500)

            # Check warning logs
            warning_logs = [record for record in caplog.records if record.levelno == logging.WARNING]
            assert any("No pricing found for model unknown-model" in record.message for record in warning_logs)

    def test_edge_case_zero_tokens(self):
        """Test calculation with zero tokens."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        result = calculator.calculate_cost_and_impact("gpt-4o", 0, 0)

        assert result.tokens_used == 0
        assert result.tokens_input == 0
        assert result.tokens_output == 0
        assert result.cost_cents == 0.0
        assert result.energy_kwh == 0.0
        assert result.carbon_grams == 0.0

    def test_edge_case_large_token_counts(self):
        """Test calculation with very large token counts."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        result = calculator.calculate_cost_and_impact("gpt-4o", 1_000_000, 500_000)

        assert result.tokens_used == 1_500_000
        # Cost: (1M/1M * 15.0) + (500K/1M * 60.0) = 15.0 + 30.0 = 45.0 cents
        expected_cost = 15.0 + 30.0
        assert abs(result.cost_cents - expected_cost) < 0.001

    def test_provider_specific_metadata_handling(self):
        """Test handling of provider-specific metadata."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        info = calculator.get_model_info("gpt-4o", "openai")

        # Should handle provider_specific field (even if None)
        assert "provider_specific" in info
        # In our test config, provider_specific is None
        assert info["provider_specific"] is None

    def test_context_window_in_model_info(self):
        """Test context window information in model info."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        info = calculator.get_model_info("claude-3-opus", "anthropic")

        assert info["context_window"] == 200000  # Claude-3 context window

    def test_deprecated_model_handling(self):
        """Test handling of deprecated models."""
        calculator = LLMPricingCalculator(pricing_config=self.mock_pricing_config)

        info = calculator.get_model_info("gpt-3.5-turbo", "openai")

        assert info["deprecated"] is True
        assert info["active"] is False