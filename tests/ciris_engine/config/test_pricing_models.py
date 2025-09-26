"""
Comprehensive unit tests for LLM pricing configuration models.

Tests cover validation, loading, querying, and edge cases for the
pricing configuration system.
"""

import json
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest
from pydantic import ValidationError

from ciris_engine.config.pricing_models import (
    PricingConfig, ProviderConfig, ModelConfig, PricingMetadata,
    EnvironmentalFactors, EnergyEstimates, CarbonIntensity, FallbackPricing,
    get_pricing_config
)


class TestModelConfig:
    """Test suite for ModelConfig validation and functionality."""

    def test_valid_model_config(self):
        """Test creation of valid model configuration."""
        config = ModelConfig(
            input_cost=15.0,
            output_cost=60.0,
            context_window=128000,
            active=True,
            deprecated=False,
            effective_date="2024-07-18",
            description="Test model"
        )

        assert config.input_cost == 15.0
        assert config.output_cost == 60.0
        assert config.context_window == 128000
        assert config.active is True
        assert config.deprecated is False
        assert config.effective_date == "2024-07-18"
        assert config.description == "Test model"
        assert config.provider_specific is None

    def test_model_config_with_provider_specific(self):
        """Test model configuration with provider-specific metadata."""
        config = ModelConfig(
            input_cost=10.0,
            output_cost=10.0,
            context_window=128000,
            active=True,
            deprecated=False,
            effective_date="2024-09-01",
            description="Llama model",
            provider_specific={
                "precision": "fp8",
                "optimization": "inference"
            }
        )

        assert config.provider_specific["precision"] == "fp8"
        assert config.provider_specific["optimization"] == "inference"

    def test_negative_costs_validation(self):
        """Test that negative costs are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ModelConfig(
                input_cost=-5.0,
                output_cost=60.0,
                context_window=128000,
                active=True,
                deprecated=False,
                effective_date="2024-07-18"
            )

        assert "greater than or equal to 0" in str(exc_info.value)

    def test_zero_context_window_validation(self):
        """Test that zero context window is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ModelConfig(
                input_cost=15.0,
                output_cost=60.0,
                context_window=0,
                active=True,
                deprecated=False,
                effective_date="2024-07-18"
            )

        assert "greater than 0" in str(exc_info.value)

    def test_invalid_date_format(self):
        """Test that invalid date formats are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            ModelConfig(
                input_cost=15.0,
                output_cost=60.0,
                context_window=128000,
                active=True,
                deprecated=False,
                effective_date="2024/07/18"  # Wrong format
            )

        assert "Date must be in YYYY-MM-DD format" in str(exc_info.value)

    def test_valid_date_formats(self):
        """Test various valid date formats."""
        valid_dates = ["2024-01-01", "2024-12-31", "2023-02-28"]

        for date in valid_dates:
            config = ModelConfig(
                input_cost=15.0,
                output_cost=60.0,
                context_window=128000,
                active=True,
                deprecated=False,
                effective_date=date
            )
            assert config.effective_date == date


class TestPricingConfig:
    """Test suite for PricingConfig functionality."""

    def test_semver_validation(self, mock_pricing_config):
        """Test semantic versioning validation."""
        # Valid versions
        valid_versions = ["1.0.0", "10.20.30", "0.0.1"]
        for version in valid_versions:
            config = mock_pricing_config
            config.version = version
            assert config.version == version

        # Invalid versions
        invalid_versions = ["1.0", "1.0.0.1", "v1.0.0", "1.0.0-beta"]
        for version in invalid_versions:
            with pytest.raises(ValidationError):
                PricingConfig(
                    version=version,
                    last_updated=datetime.now(),
                    metadata=mock_pricing_config.metadata,
                    providers=mock_pricing_config.providers,
                    environmental_factors=mock_pricing_config.environmental_factors,
                    fallback_pricing=mock_pricing_config.fallback_pricing
                )

    def test_get_model_config_success(self, mock_pricing_config):
        """Test successful model configuration retrieval."""
        config = mock_pricing_config.get_model_config("openai", "gpt-4o-mini")

        assert config is not None
        assert config.input_cost == 15.0
        assert config.output_cost == 60.0
        assert config.active is True

    def test_get_model_config_missing_provider(self, mock_pricing_config):
        """Test model configuration retrieval with missing provider."""
        config = mock_pricing_config.get_model_config("nonexistent", "gpt-4o-mini")
        assert config is None

    def test_get_model_config_missing_model(self, mock_pricing_config):
        """Test model configuration retrieval with missing model."""
        config = mock_pricing_config.get_model_config("openai", "nonexistent-model")
        assert config is None

    def test_find_model_by_name_success(self, mock_pricing_config):
        """Test successful model finding by name."""
        result = mock_pricing_config.find_model_by_name("gpt-4o-mini")

        assert result is not None
        provider_name, model_config = result
        assert provider_name == "openai"
        assert model_config.input_cost == 15.0

    def test_find_model_by_name_not_found(self, mock_pricing_config):
        """Test model finding with non-existent model."""
        result = mock_pricing_config.find_model_by_name("nonexistent-model")
        assert result is None

    def test_get_energy_estimate_exact_match(self, mock_pricing_config):
        """Test energy estimate with exact model match."""
        estimate = mock_pricing_config.get_energy_estimate("gpt-4")
        assert estimate == 0.0005

    def test_get_energy_estimate_pattern_match(self, mock_pricing_config):
        """Test energy estimate with pattern matching."""
        estimate = mock_pricing_config.get_energy_estimate("gpt-4o-mini")
        assert estimate == 0.0005  # Should match "gpt-4" pattern

    def test_get_energy_estimate_default(self, mock_pricing_config):
        """Test energy estimate fallback to default."""
        estimate = mock_pricing_config.get_energy_estimate("unknown-model")
        assert estimate == 0.0003  # Default value

    def test_get_carbon_intensity_with_region(self, mock_pricing_config):
        """Test carbon intensity with specific region."""
        intensity = mock_pricing_config.get_carbon_intensity("us_west")
        assert intensity == 350.0

    def test_get_carbon_intensity_default(self, mock_pricing_config):
        """Test carbon intensity fallback to global average."""
        intensity = mock_pricing_config.get_carbon_intensity("unknown_region")
        assert intensity == 500.0  # Global average

        intensity_none = mock_pricing_config.get_carbon_intensity(None)
        assert intensity_none == 500.0

    def test_get_fallback_pricing(self, mock_pricing_config):
        """Test fallback pricing retrieval."""
        fallback = mock_pricing_config.get_fallback_pricing()

        assert fallback.input_cost == 20.0
        assert fallback.output_cost == 20.0
        assert fallback.active is True

    def test_list_active_models_all_providers(self, mock_pricing_config):
        """Test listing all active models."""
        models = mock_pricing_config.list_active_models()

        # Should include all active, non-deprecated models
        model_names = [model_name for _, model_name, _ in models]
        assert "gpt-4o-mini" in model_names
        assert "gpt-4o" in model_names
        assert "claude-3-opus" in model_names

        # All should be active
        for _, _, model_config in models:
            assert model_config.active is True
            assert model_config.deprecated is False

    def test_list_active_models_specific_provider(self, mock_pricing_config):
        """Test listing active models for specific provider."""
        models = mock_pricing_config.list_active_models("openai")

        # Should only include OpenAI models
        provider_names = [provider_name for provider_name, _, _ in models]
        assert all(name == "openai" for name in provider_names)

        model_names = [model_name for _, model_name, _ in models]
        assert "gpt-4o-mini" in model_names
        assert "gpt-4o" in model_names

    def test_list_active_models_excludes_deprecated(self, mock_deprecated_model_config):
        """Test that deprecated models are excluded from active list."""
        models = mock_deprecated_model_config.list_active_models()

        # Should not include any models since the only model is deprecated
        assert len(models) == 0


class TestPricingConfigLoading:
    """Test suite for pricing configuration file loading."""

    def test_load_from_file_success(self, mock_pricing_config):
        """Test successful loading from file."""
        # Create a temporary file with valid JSON
        config_data = {
            "version": "1.0.0",
            "last_updated": "2025-01-15T10:30:00Z",
            "metadata": {
                "update_frequency": "weekly",
                "currency": "USD",
                "units": "per_million_tokens",
                "sources": ["Test API"],
                "schema_version": "1.0.0"
            },
            "providers": {
                "test_provider": {
                    "display_name": "Test Provider",
                    "models": {
                        "test-model": {
                            "input_cost": 10.0,
                            "output_cost": 20.0,
                            "context_window": 4096,
                            "active": True,
                            "deprecated": False,
                            "effective_date": "2024-01-01",
                            "description": "Test model"
                        }
                    }
                }
            },
            "environmental_factors": {
                "energy_estimates": {
                    "model_patterns": {"default": {"kwh_per_1k_tokens": 0.0003}}
                },
                "carbon_intensity": {
                    "global_average_g_co2_per_kwh": 500.0,
                    "regions": {}
                }
            },
            "fallback_pricing": {
                "unknown_model": {
                    "input_cost": 20.0,
                    "output_cost": 20.0,
                    "context_window": 4096,
                    "active": True,
                    "deprecated": False,
                    "effective_date": "2024-01-01",
                    "description": "Default pricing"
                }
            }
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config_data, f)
            temp_path = f.name

        try:
            loaded_config = PricingConfig.load_from_file(temp_path)
            assert loaded_config.version == "1.0.0"
            assert "test_provider" in loaded_config.providers
        finally:
            Path(temp_path).unlink()

    def test_load_from_file_not_found(self):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError) as exc_info:
            PricingConfig.load_from_file("/nonexistent/path/pricing.json")

        assert "Pricing configuration file not found" in str(exc_info.value)

    def test_load_from_file_invalid_json(self):
        """Test loading from file with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("{ invalid json }")
            temp_path = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                PricingConfig.load_from_file(temp_path)

            assert "Invalid JSON in pricing configuration" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    def test_load_from_file_validation_error(self):
        """Test loading from file with validation errors."""
        invalid_config = {
            "version": "invalid_version",  # Should be semver
            "providers": {}  # Missing required fields
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(invalid_config, f)
            temp_path = f.name

        try:
            with pytest.raises(ValueError) as exc_info:
                PricingConfig.load_from_file(temp_path)

            assert "Failed to load pricing configuration" in str(exc_info.value)
        finally:
            Path(temp_path).unlink()

    @patch('ciris_engine.config.pricing_models.Path.exists')
    @patch('builtins.open', new_callable=mock_open)
    def test_load_from_default_path(self, mock_file, mock_exists):
        """Test loading from default path when no path specified."""
        mock_exists.return_value = True
        mock_file.return_value.read.return_value = json.dumps({
            "version": "1.0.0",
            "last_updated": "2025-01-15T10:30:00Z",
            "metadata": {
                "update_frequency": "weekly",
                "currency": "USD",
                "units": "per_million_tokens",
                "sources": ["Test"],
                "schema_version": "1.0.0"
            },
            "providers": {},
            "environmental_factors": {
                "energy_estimates": {"model_patterns": {"default": {"kwh_per_1k_tokens": 0.0003}}},
                "carbon_intensity": {"global_average_g_co2_per_kwh": 500.0, "regions": {}}
            },
            "fallback_pricing": {
                "unknown_model": {
                    "input_cost": 20.0, "output_cost": 20.0, "context_window": 4096,
                    "active": True, "deprecated": False, "effective_date": "2024-01-01",
                    "description": "Default"
                }
            }
        })

        # This should not raise an exception
        config = PricingConfig.load_from_file()
        assert config.version == "1.0.0"


class TestGetPricingConfig:
    """Test suite for global pricing configuration management."""

    @patch('ciris_engine.config.pricing_models.PricingConfig.load_from_file')
    def test_get_pricing_config_first_call(self, mock_load):
        """Test first call to get_pricing_config loads from file."""
        mock_config = MagicMock()
        mock_load.return_value = mock_config

        # Clear the global state
        import ciris_engine.config.pricing_models
        ciris_engine.config.pricing_models._pricing_config = None

        result = get_pricing_config()

        mock_load.assert_called_once()
        assert result == mock_config

    @patch('ciris_engine.config.pricing_models.PricingConfig.load_from_file')
    def test_get_pricing_config_cached(self, mock_load):
        """Test subsequent calls use cached configuration."""
        mock_config = MagicMock()
        mock_load.return_value = mock_config

        # Clear and set global state
        import ciris_engine.config.pricing_models
        ciris_engine.config.pricing_models._pricing_config = mock_config

        result = get_pricing_config()

        # Should not call load_from_file again
        mock_load.assert_not_called()
        assert result == mock_config

    @patch('ciris_engine.config.pricing_models.PricingConfig.load_from_file')
    def test_get_pricing_config_reload(self, mock_load):
        """Test reload=True forces reload from file."""
        mock_config = MagicMock()
        mock_load.return_value = mock_config

        # Set existing config
        import ciris_engine.config.pricing_models
        ciris_engine.config.pricing_models._pricing_config = MagicMock()

        result = get_pricing_config(reload=True)

        mock_load.assert_called_once()
        assert result == mock_config


class TestProviderConfig:
    """Test suite for ProviderConfig functionality."""

    def test_provider_config_minimal(self):
        """Test minimal provider configuration."""
        config = ProviderConfig(
            display_name="Test Provider",
            models={
                "test-model": ModelConfig(
                    input_cost=10.0,
                    output_cost=20.0,
                    context_window=4096,
                    active=True,
                    deprecated=False,
                    effective_date="2024-01-01"
                )
            }
        )

        assert config.display_name == "Test Provider"
        assert "test-model" in config.models
        assert config.rate_limits is None
        assert config.base_url is None

    def test_provider_config_full(self):
        """Test full provider configuration with all optional fields."""
        from ciris_engine.config.pricing_models import RateLimits

        config = ProviderConfig(
            display_name="Full Provider",
            models={
                "test-model": ModelConfig(
                    input_cost=10.0,
                    output_cost=20.0,
                    context_window=4096,
                    active=True,
                    deprecated=False,
                    effective_date="2024-01-01"
                )
            },
            rate_limits={
                "tier_1": RateLimits(rpm=500, tpm=30000)
            },
            base_url="https://api.example.com/v1"
        )

        assert config.display_name == "Full Provider"
        assert config.rate_limits["tier_1"].rpm == 500
        assert config.base_url == "https://api.example.com/v1"


# Import MagicMock for the test
from unittest.mock import MagicMock