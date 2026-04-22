"""
LLM pricing calculator using external configuration.

This module provides cost and environmental impact calculations
for LLM usage based on external pricing configuration.
"""

import logging
from typing import Dict, List, Optional, Tuple

from ciris_engine.config.pricing_models import ModelConfig, PricingConfig, get_pricing_config
from ciris_engine.schemas.runtime.resources import ResourceUsage

logger = logging.getLogger(__name__)


class LLMPricingCalculator:
    """
    Calculator for LLM costs and environmental impact.

    Uses external pricing configuration to calculate costs, energy consumption,
    and carbon emissions for LLM API calls.
    """

    def __init__(self, pricing_config: Optional[PricingConfig] = None):
        """
        Initialize the pricing calculator.

        Args:
            pricing_config: Optional pricing configuration. If None, loads from file.
        """
        self.pricing_config = pricing_config or get_pricing_config()
        logger.debug(f"Initialized pricing calculator with config version {self.pricing_config.version}")

    def calculate_cost_and_impact(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider_name: Optional[str] = None,
        region: Optional[str] = None,
    ) -> ResourceUsage:
        """
        Calculate comprehensive resource usage for an LLM call.

        Args:
            model_name: Name of the LLM model used
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            provider_name: Optional provider name (if known)
            region: Optional region for carbon intensity calculation

        Returns:
            ResourceUsage: Complete resource usage information
        """
        total_tokens = prompt_tokens + completion_tokens

        # Get model configuration
        model_config = self._get_model_config(model_name, provider_name)

        # Calculate costs
        input_cost_cents = (prompt_tokens / 1_000_000) * model_config.input_cost
        output_cost_cents = (completion_tokens / 1_000_000) * model_config.output_cost
        total_cost_cents = input_cost_cents + output_cost_cents

        # Calculate environmental impact
        energy_kwh = self._calculate_energy_consumption(model_name, total_tokens)
        carbon_grams = self._calculate_carbon_emissions(energy_kwh, region)

        # Determine the provider name for metadata
        if provider_name is None:
            result = self.pricing_config.find_model_by_name(model_name)
            if result:
                provider_name, _ = result

        logger.debug(
            f"Calculated usage for {model_name}: "
            f"{total_tokens} tokens, ${total_cost_cents/100:.4f}, "
            f"{energy_kwh:.6f} kWh, {carbon_grams:.3f}g CO2"
        )

        return ResourceUsage(
            tokens_used=total_tokens,
            tokens_input=prompt_tokens,
            tokens_output=completion_tokens,
            cost_cents=total_cost_cents,
            carbon_grams=carbon_grams,
            energy_kwh=energy_kwh,
            model_used=model_name,
        )

    def _get_model_config(self, model_name: str, provider_name: Optional[str]) -> ModelConfig:
        """
        Get model configuration, with fallback to unknown model pricing.

        Args:
            model_name: Name of the model
            provider_name: Optional provider name

        Returns:
            ModelConfig: Configuration for the model or fallback
        """
        # Try exact provider + model lookup first
        if provider_name:
            config = self.pricing_config.get_model_config(provider_name, model_name)
            if config:
                logger.debug(f"Found exact config for {provider_name}/{model_name}")
                return config

        # Try finding model across all providers
        result = self.pricing_config.find_model_by_name(model_name)
        if result:
            found_provider, model_config = result
            logger.debug(f"Found model {model_name} in provider {found_provider}")
            return model_config

        # Try pattern matching with hardcoded model patterns
        pattern_config = self._try_pattern_matching(model_name)
        if pattern_config:
            return pattern_config

        # Fall back to unknown model pricing
        logger.warning(f"No pricing found for model {model_name}, using fallback pricing")
        return self.pricing_config.get_fallback_pricing()

    def _try_pattern_matching(self, model_name: str) -> Optional[ModelConfig]:
        """
        Try to match model name against known patterns for compatibility.

        This provides backward compatibility with existing hardcoded model matching.

        Args:
            model_name: Name of the model to match

        Returns:
            ModelConfig or None: Matched configuration if found
        """
        model_lower = model_name.lower()

        # OpenAI patterns
        if model_lower.startswith("gpt-4o-mini"):
            return self.pricing_config.get_model_config("openai", "gpt-4o-mini")
        elif model_lower.startswith("gpt-4o"):
            return self.pricing_config.get_model_config("openai", "gpt-4o")
        elif model_lower.startswith("gpt-4-turbo"):
            return self.pricing_config.get_model_config("openai", "gpt-4-turbo")
        elif model_lower.startswith("gpt-3.5-turbo"):
            return self.pricing_config.get_model_config("openai", "gpt-3.5-turbo")

        # Anthropic patterns
        elif "claude" in model_lower:
            if "opus" in model_lower:
                return self.pricing_config.get_model_config("anthropic", "claude-3-opus")
            elif "sonnet" in model_lower:
                return self.pricing_config.get_model_config("anthropic", "claude-3-sonnet")
            elif "haiku" in model_lower:
                return self.pricing_config.get_model_config("anthropic", "claude-3-haiku")

        # Llama patterns
        elif "llama" in model_lower:
            if "405b" in model_lower:
                return self.pricing_config.get_model_config("together", "llama-3.1-405b-instruct")
            elif "70b" in model_lower:
                return self.pricing_config.get_model_config("together", "llama-3.1-70b-instruct")
            elif "17b" in model_lower or "maverick" in model_lower:
                return self.pricing_config.get_model_config("lambda_labs", "llama-4-maverick-17b-128e-instruct-fp8")

        return None

    def _calculate_energy_consumption(self, model_name: str, total_tokens: int) -> float:
        """
        Calculate energy consumption for the model call.

        Args:
            model_name: Name of the model
            total_tokens: Total tokens used

        Returns:
            float: Energy consumption in kWh
        """
        kwh_per_1k_tokens = self.pricing_config.get_energy_estimate(model_name)
        return (total_tokens / 1000) * kwh_per_1k_tokens

    def _calculate_carbon_emissions(self, energy_kwh: float, region: Optional[str] = None) -> float:
        """
        Calculate carbon emissions for the energy consumption.

        Args:
            energy_kwh: Energy consumption in kWh
            region: Optional region for carbon intensity

        Returns:
            float: Carbon emissions in grams CO2
        """
        carbon_intensity = self.pricing_config.get_carbon_intensity(region)
        return energy_kwh * carbon_intensity

    def get_model_info(self, model_name: str, provider_name: Optional[str] = None) -> Dict[str, object]:
        """
        Get detailed information about a model.

        Args:
            model_name: Name of the model
            provider_name: Optional provider name

        Returns:
            dict: Model information including costs, limits, and metadata
        """
        model_config = self._get_model_config(model_name, provider_name)

        # Find the provider if not specified
        if provider_name is None:
            result = self.pricing_config.find_model_by_name(model_name)
            if result:
                provider_name, _ = result

        return {
            "model_name": model_name,
            "provider_name": provider_name,
            "input_cost_per_million": model_config.input_cost,
            "output_cost_per_million": model_config.output_cost,
            "context_window": model_config.context_window,
            "active": model_config.active,
            "deprecated": model_config.deprecated,
            "description": model_config.description,
            "provider_specific": model_config.provider_specific,
            "energy_per_1k_tokens": self.pricing_config.get_energy_estimate(model_name),
            "carbon_intensity_global": self.pricing_config.get_carbon_intensity(),
        }

    def list_available_models(
        self, provider_name: Optional[str] = None, active_only: bool = True
    ) -> List[Dict[str, object]]:
        """
        List available models with their pricing information.

        Args:
            provider_name: Optional provider to filter by
            active_only: Whether to include only active models

        Returns:
            list: List of model information dictionaries
        """
        if active_only:
            models = self.pricing_config.list_active_models(provider_name)
        else:
            # Get all models regardless of status
            models = []
            providers = (
                {provider_name: self.pricing_config.providers[provider_name]}
                if provider_name
                else self.pricing_config.providers
            )

            for prov_name, provider in providers.items():
                for model_name, model_config in provider.models.items():
                    models.append((prov_name, model_name, model_config))

        return [
            {
                "provider_name": prov_name,
                "model_name": model_name,
                "input_cost_per_million": config.input_cost,
                "output_cost_per_million": config.output_cost,
                "context_window": config.context_window,
                "active": config.active,
                "deprecated": config.deprecated,
                "description": config.description,
            }
            for prov_name, model_name, config in models
        ]

    def reload_pricing_config(self) -> None:
        """Reload pricing configuration from file."""
        self.pricing_config = get_pricing_config(reload=True)
        logger.info(f"Reloaded pricing configuration, version {self.pricing_config.version}")


__all__ = ["LLMPricingCalculator"]
