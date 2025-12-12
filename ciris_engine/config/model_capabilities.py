"""
Pydantic models for LLM model capabilities configuration.

This module provides type-safe models for loading and validating
LLM model capabilities data from the on-device configuration file.
Used by the wizard for BYOK model selection.

BYOK Wizard Integration Pattern
===============================

When user selects "Bring Your Own Key" (BYOK) in the setup wizard:

1. User selects provider (OpenAI, Anthropic, etc.)
2. Wizard loads models for that provider:

   ```python
   from ciris_engine.config import get_model_capabilities

   config = get_model_capabilities()
   provider_models = config.get_compatible_models(provider_name="openai")
   ```

3. Display models grouped by compatibility:
   - RECOMMENDED: ciris_recommended=True (green checkmark)
   - COMPATIBLE: ciris_compatible=True (yellow checkmark)
   - ADVANCED OVERRIDE: ciris_compatible=False (warning icon)

4. For each model, show:
   - display_name
   - capabilities (vision, tool_use icons)
   - tier (default/fast/premium)
   - notes (if any)

5. If user selects incompatible model (Advanced override):
   ```python
   is_compat, issues = config.check_model_compatibility(provider, model_id)
   # Show issues as warnings, allow override
   ```

6. Vision-capable model filtering:
   ```python
   vision_models = config.get_models_with_vision(provider_name="openai")
   ```

All data is on-device in MODEL_CAPABILITIES.json - no external API calls.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelCapabilities(BaseModel):
    """Capabilities flags for an LLM model."""

    tool_use: bool = Field(..., description="Native function/tool calling support")
    structured_output: bool = Field(..., description="Reliable JSON output for tool calls")
    vision: bool = Field(default=False, description="Image/multimodal input support")
    json_mode: bool = Field(default=False, description="JSON mode for structured responses")
    streaming: bool = Field(default=True, description="Streaming response support")

    model_config = ConfigDict(extra="forbid")


class ModelInfo(BaseModel):
    """Information about a specific LLM model."""

    display_name: str = Field(..., description="Human-readable model name")
    architecture: Optional[str] = Field(default=None, description="Model architecture (dense, moe, etc)")
    active_params: Optional[str] = Field(default=None, description="Active parameters per token")
    context_window: int = Field(..., gt=0, description="Maximum context window in tokens")
    capabilities: ModelCapabilities = Field(..., description="Model capabilities")
    underlying_providers: Optional[List[str]] = Field(default=None, description="For aggregators: underlying providers")
    tier: str = Field(..., description="Performance tier (default, fast, fallback, premium, legacy)")
    ciris_compatible: bool = Field(..., description="Meets CIRIS minimum requirements")
    ciris_recommended: bool = Field(default=False, description="Recommended for CIRIS use")
    rejection_reason: Optional[str] = Field(default=None, description="Why model is not compatible")
    notes: Optional[str] = Field(default=None, description="Additional notes")

    model_config = ConfigDict(extra="forbid")


class ProviderModels(BaseModel):
    """Models available from a specific provider."""

    display_name: str = Field(..., description="Human-readable provider name")
    api_base: Optional[str] = Field(default=None, description="Provider API base URL")
    note: Optional[str] = Field(default=None, description="Provider notes")
    models: Dict[str, ModelInfo] = Field(..., description="Available models")

    model_config = ConfigDict(extra="forbid")


class RejectedModel(BaseModel):
    """Model that was tested and rejected."""

    display_name: str = Field(..., description="Human-readable model name")
    rejection_reason: str = Field(..., description="Why the model was rejected")
    tested_date: Optional[str] = Field(default=None, description="When the model was tested")

    model_config = ConfigDict(extra="forbid")


class TierInfo(BaseModel):
    """Information about a performance tier."""

    description: str = Field(..., description="Tier description")
    typical_latency_ms: Optional[str] = Field(default=None, description="Typical latency range")
    use_case: str = Field(..., description="Recommended use case")

    model_config = ConfigDict(extra="forbid")


class CirisRequirements(BaseModel):
    """CIRIS agent requirements for model compatibility."""

    min_context_window: int = Field(..., gt=0, description="Minimum context window (tokens)")
    preferred_context_window: int = Field(..., gt=0, description="Preferred context window (tokens)")
    max_combined_cost_per_million_cents: float = Field(
        ..., ge=0, description="Max combined cost per million tokens (cents)"
    )
    min_provider_count: int = Field(..., ge=1, description="Minimum number of providers for fallback")
    required_capabilities: List[str] = Field(..., description="Required capability flags")
    recommended_capabilities: List[str] = Field(default_factory=list, description="Recommended capabilities")

    model_config = ConfigDict(extra="forbid")


class CapabilitiesMetadata(BaseModel):
    """Metadata about the capabilities configuration."""

    schema_version: str = Field(..., description="Schema version for compatibility")
    ciris_requirements_version: str = Field(..., description="CIRIS requirements version")
    update_frequency: str = Field(..., description="How often data is updated")
    sources: List[str] = Field(..., description="Data sources")

    model_config = ConfigDict(extra="forbid")


class ModelCapabilitiesConfig(BaseModel):
    """Complete LLM model capabilities configuration."""

    version: str = Field(..., description="Configuration version")
    last_updated: datetime = Field(..., description="Last update timestamp")
    metadata: CapabilitiesMetadata = Field(..., description="Configuration metadata")
    ciris_requirements: CirisRequirements = Field(..., description="CIRIS compatibility requirements")
    providers: Dict[str, ProviderModels] = Field(..., description="Provider configurations")
    rejected_models: Dict[str, RejectedModel] = Field(default_factory=dict, description="Models tested and rejected")
    tiers: Dict[str, TierInfo] = Field(..., description="Performance tier definitions")

    model_config = ConfigDict(extra="forbid")

    @field_validator("version")
    @classmethod
    def validate_semver(cls, v: str) -> str:
        """Validate semantic versioning format."""
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError("Version must be in semantic versioning format (x.y.z)")
        return v

    @classmethod
    def load_from_file(cls, path: Optional[str] = None) -> "ModelCapabilitiesConfig":
        """
        Load capabilities configuration from JSON file.

        Args:
            path: Optional path to capabilities file. If None, uses default location.

        Returns:
            ModelCapabilitiesConfig instance

        Raises:
            FileNotFoundError: If capabilities file doesn't exist
            ValueError: If JSON is invalid or doesn't match schema
        """
        path_str: str
        if path is None:
            config_dir = Path(__file__).parent
            path_str = str(config_dir / "MODEL_CAPABILITIES.json")
        else:
            path_str = path

        path_obj = Path(path_str)
        if not path_obj.exists():
            raise FileNotFoundError(f"Model capabilities file not found: {path_obj}")

        try:
            with open(path_obj, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in capabilities configuration: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load capabilities configuration: {e}")

    def get_provider_models(self, provider_name: str) -> Optional[Dict[str, ModelInfo]]:
        """
        Get all models for a specific provider.

        Args:
            provider_name: Name of the provider (e.g., 'openai', 'openrouter')

        Returns:
            Dict of model_id -> ModelInfo if provider found, None otherwise
        """
        provider = self.providers.get(provider_name)
        if not provider:
            return None
        return provider.models

    def get_model(self, provider_name: str, model_id: str) -> Optional[ModelInfo]:
        """
        Get a specific model by provider and model ID.

        Args:
            provider_name: Name of the provider
            model_id: Model identifier

        Returns:
            ModelInfo if found, None otherwise
        """
        provider = self.providers.get(provider_name)
        if not provider:
            return None
        return provider.models.get(model_id)

    def get_compatible_models(self, provider_name: Optional[str] = None) -> List[Tuple[str, str, ModelInfo]]:
        """
        Get all CIRIS-compatible models.

        Args:
            provider_name: Optional provider to filter by

        Returns:
            List of (provider_name, model_id, ModelInfo) tuples
        """
        models = []
        providers = (
            {provider_name: self.providers[provider_name]}
            if provider_name and provider_name in self.providers
            else self.providers
        )

        for prov_name, provider in providers.items():
            for model_id, model_info in provider.models.items():
                if model_info.ciris_compatible:
                    models.append((prov_name, model_id, model_info))

        return models

    def get_recommended_models(self, provider_name: Optional[str] = None) -> List[Tuple[str, str, ModelInfo]]:
        """
        Get CIRIS-recommended models.

        Args:
            provider_name: Optional provider to filter by

        Returns:
            List of (provider_name, model_id, ModelInfo) tuples
        """
        return [
            (prov, model_id, info)
            for prov, model_id, info in self.get_compatible_models(provider_name)
            if info.ciris_recommended
        ]

    def get_models_by_tier(self, tier: str, provider_name: Optional[str] = None) -> List[Tuple[str, str, ModelInfo]]:
        """
        Get models by performance tier.

        Args:
            tier: Tier name (default, fast, fallback, premium, legacy)
            provider_name: Optional provider to filter by

        Returns:
            List of (provider_name, model_id, ModelInfo) tuples
        """
        return [
            (prov, model_id, info)
            for prov, model_id, info in self.get_compatible_models(provider_name)
            if info.tier == tier
        ]

    def get_models_with_vision(self, provider_name: Optional[str] = None) -> List[Tuple[str, str, ModelInfo]]:
        """
        Get models with vision/multimodal support.

        Args:
            provider_name: Optional provider to filter by

        Returns:
            List of (provider_name, model_id, ModelInfo) tuples
        """
        return [
            (prov, model_id, info)
            for prov, model_id, info in self.get_compatible_models(provider_name)
            if info.capabilities.vision
        ]

    def check_model_compatibility(self, provider_name: str, model_id: str) -> Tuple[bool, List[str]]:
        """
        Check if a model meets CIRIS requirements.

        Args:
            provider_name: Provider name
            model_id: Model identifier

        Returns:
            Tuple of (is_compatible, list of issues)
        """
        model = self.get_model(provider_name, model_id)
        if not model:
            return False, [f"Model not found: {provider_name}/{model_id}"]

        issues = []
        reqs = self.ciris_requirements

        # Check context window
        if model.context_window < reqs.min_context_window:
            issues.append(f"Context window {model.context_window} < minimum {reqs.min_context_window}")

        # Check required capabilities
        for cap in reqs.required_capabilities:
            if not getattr(model.capabilities, cap, False):
                issues.append(f"Missing required capability: {cap}")

        # Note recommended capabilities (not blocking)
        missing_recommended = []
        for cap in reqs.recommended_capabilities:
            if not getattr(model.capabilities, cap, False):
                missing_recommended.append(cap)
        if missing_recommended:
            issues.append(f"Missing recommended (non-blocking): {', '.join(missing_recommended)}")

        # Check if model has rejection reason
        if model.rejection_reason:
            issues.append(f"Previously rejected: {model.rejection_reason}")

        is_compatible = len([i for i in issues if "non-blocking" not in i]) == 0
        return is_compatible, issues

    def list_providers(self) -> List[Tuple[str, str]]:
        """
        List all available providers.

        Returns:
            List of (provider_id, display_name) tuples
        """
        return [(pid, prov.display_name) for pid, prov in self.providers.items()]


# Global configuration instance
_capabilities_config: Optional[ModelCapabilitiesConfig] = None


def get_model_capabilities(reload: bool = False) -> ModelCapabilitiesConfig:
    """
    Get the global model capabilities configuration instance.

    Args:
        reload: If True, reload configuration from file

    Returns:
        ModelCapabilitiesConfig instance
    """
    global _capabilities_config

    if _capabilities_config is None or reload:
        _capabilities_config = ModelCapabilitiesConfig.load_from_file()

    return _capabilities_config


__all__ = [
    "ModelCapabilities",
    "ModelInfo",
    "ProviderModels",
    "CirisRequirements",
    "ModelCapabilitiesConfig",
    "get_model_capabilities",
    "TierInfo",
    "RejectedModel",
    "CapabilitiesMetadata",
]
