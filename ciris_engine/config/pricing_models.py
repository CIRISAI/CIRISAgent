"""
Pydantic models for LLM pricing configuration.

This module provides type-safe models for loading and validating
LLM provider pricing data from external configuration files.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelConfig(BaseModel):
    """Configuration for a specific LLM model."""

    input_cost: float = Field(..., ge=0.0, description="Input cost in cents per million tokens")
    output_cost: float = Field(..., ge=0.0, description="Output cost in cents per million tokens")
    context_window: int = Field(..., gt=0, description="Maximum context window in tokens")
    active: bool = Field(..., description="Whether this model is currently active")
    deprecated: bool = Field(default=False, description="Whether this model is deprecated")
    effective_date: str = Field(..., description="Date when pricing became effective (YYYY-MM-DD)")
    description: Optional[str] = Field(None, description="Human-readable model description")
    provider_specific: Optional[Dict[str, str]] = Field(default=None, description="Provider-specific metadata")

    @field_validator("effective_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        """Validate date format is YYYY-MM-DD."""
        try:
            datetime.strptime(v, "%Y-%m-%d")
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class RateLimits(BaseModel):
    """Rate limiting configuration."""

    rpm: int = Field(..., gt=0, description="Requests per minute")
    tpm: int = Field(..., gt=0, description="Tokens per minute")


class ProviderConfig(BaseModel):
    """Configuration for an LLM provider."""

    display_name: str = Field(..., description="Human-readable provider name")
    models: Dict[str, ModelConfig] = Field(..., description="Available models")
    rate_limits: Optional[Dict[str, RateLimits]] = Field(default=None, description="Rate limiting tiers")
    base_url: Optional[str] = Field(None, description="Provider's base API URL")


class EnergyEstimates(BaseModel):
    """Energy consumption estimates for models."""

    model_patterns: Dict[str, Dict[str, float]] = Field(..., description="Energy consumption by model pattern")

    model_config = ConfigDict(protected_namespaces=())


class CarbonIntensity(BaseModel):
    """Carbon intensity data by region."""

    global_average_g_co2_per_kwh: float = Field(..., ge=0.0, description="Global average CO2 grams per kWh")
    regions: Dict[str, float] = Field(..., description="CO2 grams per kWh by region")


class EnvironmentalFactors(BaseModel):
    """Environmental impact calculation factors."""

    energy_estimates: EnergyEstimates
    carbon_intensity: CarbonIntensity


class FallbackPricing(BaseModel):
    """Fallback pricing for unknown models."""

    unknown_model: ModelConfig = Field(..., description="Default pricing for unknown models")


class PricingMetadata(BaseModel):
    """Metadata about the pricing configuration."""

    update_frequency: str = Field(..., description="How often pricing is updated")
    currency: str = Field(..., description="Currency for all pricing")
    units: str = Field(..., description="Units for pricing (e.g., per_million_tokens)")
    sources: List[str] = Field(..., description="Data sources for pricing")
    schema_version: str = Field(..., description="Schema version for compatibility")


class PricingConfig(BaseModel):
    """Complete LLM pricing configuration."""

    version: str = Field(..., description="Configuration version")
    last_updated: datetime = Field(..., description="Last update timestamp")
    metadata: PricingMetadata = Field(..., description="Configuration metadata")
    providers: Dict[str, ProviderConfig] = Field(..., description="Provider configurations")
    environmental_factors: EnvironmentalFactors = Field(..., description="Environmental impact factors")
    fallback_pricing: FallbackPricing = Field(..., description="Fallback pricing for unknown models")

    @field_validator("version")
    @classmethod
    def validate_semver(cls, v: str) -> str:
        """Validate semantic versioning format."""
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("Version must be in semantic versioning format (x.y.z)")
        return v

    @classmethod
    def load_from_file(cls, path: Optional[str] = None) -> "PricingConfig":
        """
        Load pricing configuration from JSON file.

        Args:
            path: Optional path to pricing file. If None, uses default location.

        Returns:
            PricingConfig instance

        Raises:
            FileNotFoundError: If pricing file doesn't exist
            ValueError: If JSON is invalid or doesn't match schema
        """
        # Ensure we have a valid path string first
        path_str: str
        if path is None:
            # Default path relative to this module
            config_dir = Path(__file__).parent
            path_str = str(config_dir / "PRICING_DATA.json")
        else:
            path_str = path

        # Convert to Path object for file operations
        path_obj = Path(path_str)
        if not path_obj.exists():
            raise FileNotFoundError(f"Pricing configuration file not found: {path_obj}")

        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in pricing configuration: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load pricing configuration: {e}")

    def get_model_config(self, provider_name: str, model_name: str) -> Optional[ModelConfig]:
        """
        Get configuration for a specific model.

        Args:
            provider_name: Name of the provider (e.g., 'openai')
            model_name: Name of the model (e.g., 'gpt-4o-mini')

        Returns:
            ModelConfig if found, None otherwise
        """
        provider = self.providers.get(provider_name)
        if not provider:
            return None
        return provider.models.get(model_name)

    def find_model_by_name(self, model_name: str) -> Optional[tuple[str, ModelConfig]]:
        """
        Find a model by name across all providers.

        Args:
            model_name: Name of the model to find

        Returns:
            Tuple of (provider_name, ModelConfig) if found, None otherwise
        """
        for provider_name, provider in self.providers.items():
            if model_name in provider.models:
                return provider_name, provider.models[model_name]
        return None

    def get_energy_estimate(self, model_name: str) -> float:
        """
        Get energy consumption estimate for a model.

        Args:
            model_name: Name of the model

        Returns:
            Energy consumption in kWh per 1k tokens
        """
        patterns = self.environmental_factors.energy_estimates.model_patterns

        # Try exact match first
        if model_name in patterns:
            return patterns[model_name]["kwh_per_1k_tokens"]

        # Try pattern matching
        for pattern, values in patterns.items():
            if pattern != "default" and pattern.lower() in model_name.lower():
                return values["kwh_per_1k_tokens"]

        # Return default
        return patterns["default"]["kwh_per_1k_tokens"]

    def get_carbon_intensity(self, region: Optional[str] = None) -> float:
        """
        Get carbon intensity for a region.

        Args:
            region: Optional region name

        Returns:
            CO2 grams per kWh
        """
        if region and region in self.environmental_factors.carbon_intensity.regions:
            return self.environmental_factors.carbon_intensity.regions[region]
        return self.environmental_factors.carbon_intensity.global_average_g_co2_per_kwh

    def get_fallback_pricing(self) -> ModelConfig:
        """Get fallback pricing for unknown models."""
        return self.fallback_pricing.unknown_model

    def list_active_models(self, provider_name: Optional[str] = None) -> List[tuple[str, str, ModelConfig]]:
        """
        List all active models.

        Args:
            provider_name: Optional provider to filter by

        Returns:
            List of (provider_name, model_name, ModelConfig) tuples
        """
        models = []
        providers = {provider_name: self.providers[provider_name]} if provider_name else self.providers

        for prov_name, provider in providers.items():
            for model_name, model_config in provider.models.items():
                if model_config.active and not model_config.deprecated:
                    models.append((prov_name, model_name, model_config))

        return models


# Default pricing configuration instance
_pricing_config: Optional[PricingConfig] = None


def get_pricing_config(reload: bool = False) -> PricingConfig:
    """
    Get the global pricing configuration instance.

    Args:
        reload: If True, reload configuration from file

    Returns:
        PricingConfig instance
    """
    global _pricing_config

    if _pricing_config is None or reload:
        _pricing_config = PricingConfig.load_from_file()

    return _pricing_config


__all__ = [
    "ModelConfig",
    "ProviderConfig",
    "PricingConfig",
    "get_pricing_config",
    "RateLimits",
    "EnvironmentalFactors",
    "PricingMetadata",
    "FallbackPricing",
]
