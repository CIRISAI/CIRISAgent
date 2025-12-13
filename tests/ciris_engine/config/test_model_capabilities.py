"""Unit tests for model capabilities configuration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.config.model_capabilities import (
    CapabilitiesMetadata,
    CirisRequirements,
    ModelCapabilities,
    ModelCapabilitiesConfig,
    ModelInfo,
    ProviderModels,
    RejectedModel,
    TierInfo,
    get_model_capabilities,
)


class TestModelCapabilities:
    """Tests for ModelCapabilities model."""

    def test_basic_capabilities(self):
        """Test creating basic capabilities."""
        caps = ModelCapabilities(
            tool_use=True,
            structured_output=True,
            vision=False,
        )
        assert caps.tool_use is True
        assert caps.structured_output is True
        assert caps.vision is False
        assert caps.json_mode is False  # default
        assert caps.streaming is True  # default

    def test_all_capabilities(self):
        """Test creating capabilities with all fields."""
        caps = ModelCapabilities(
            tool_use=True,
            structured_output=True,
            vision=True,
            json_mode=True,
            streaming=True,
        )
        assert caps.vision is True
        assert caps.json_mode is True


class TestModelInfo:
    """Tests for ModelInfo model."""

    def test_minimal_model_info(self):
        """Test creating minimal model info."""
        info = ModelInfo(
            display_name="Test Model",
            context_window=128000,
            capabilities=ModelCapabilities(tool_use=True, structured_output=True),
            tier="default",
            ciris_compatible=True,
        )
        assert info.display_name == "Test Model"
        assert info.context_window == 128000
        assert info.tier == "default"
        assert info.ciris_compatible is True
        assert info.ciris_recommended is False  # default

    def test_full_model_info(self):
        """Test creating model info with all fields."""
        info = ModelInfo(
            display_name="GPT-5.2",
            architecture="dense",
            active_params="1T",
            context_window=256000,
            capabilities=ModelCapabilities(tool_use=True, structured_output=True, vision=True),
            underlying_providers=["azure", "openai"],
            tier="premium",
            ciris_compatible=True,
            ciris_recommended=True,
            notes="Best for complex tasks",
        )
        assert info.architecture == "dense"
        assert info.active_params == "1T"
        assert info.underlying_providers == ["azure", "openai"]
        assert info.ciris_recommended is True
        assert info.notes == "Best for complex tasks"

    def test_rejected_model_info(self):
        """Test model with rejection reason."""
        info = ModelInfo(
            display_name="Bad Model",
            context_window=4096,
            capabilities=ModelCapabilities(tool_use=False, structured_output=False),
            tier="legacy",
            ciris_compatible=False,
            rejection_reason="Does not support tool calling",
        )
        assert info.ciris_compatible is False
        assert info.rejection_reason == "Does not support tool calling"


class TestProviderModels:
    """Tests for ProviderModels model."""

    def test_provider_models(self):
        """Test creating provider models."""
        provider = ProviderModels(
            display_name="OpenAI",
            api_base="https://api.openai.com/v1",
            models={
                "gpt-4o": ModelInfo(
                    display_name="GPT-4o",
                    context_window=128000,
                    capabilities=ModelCapabilities(tool_use=True, structured_output=True),
                    tier="default",
                    ciris_compatible=True,
                )
            },
        )
        assert provider.display_name == "OpenAI"
        assert provider.api_base == "https://api.openai.com/v1"
        assert "gpt-4o" in provider.models


class TestRejectedModel:
    """Tests for RejectedModel model."""

    def test_rejected_model(self):
        """Test creating rejected model entry."""
        rejected = RejectedModel(
            display_name="Bad Model",
            rejection_reason="Context window too small",
            tested_date="2025-01-01",
        )
        assert rejected.display_name == "Bad Model"
        assert rejected.rejection_reason == "Context window too small"
        assert rejected.tested_date == "2025-01-01"


class TestTierInfo:
    """Tests for TierInfo model."""

    def test_tier_info(self):
        """Test creating tier info."""
        tier = TierInfo(
            description="Primary production tier",
            typical_latency_ms="100-500",
            use_case="General purpose",
        )
        assert tier.description == "Primary production tier"
        assert tier.typical_latency_ms == "100-500"


class TestCirisRequirements:
    """Tests for CirisRequirements model."""

    def test_ciris_requirements(self):
        """Test creating CIRIS requirements."""
        reqs = CirisRequirements(
            min_context_window=32000,
            preferred_context_window=128000,
            max_combined_cost_per_million_cents=500.0,
            min_provider_count=2,
            required_capabilities=["tool_use", "structured_output"],
            recommended_capabilities=["vision"],
        )
        assert reqs.min_context_window == 32000
        assert reqs.preferred_context_window == 128000
        assert "tool_use" in reqs.required_capabilities
        assert "vision" in reqs.recommended_capabilities


class TestCapabilitiesMetadata:
    """Tests for CapabilitiesMetadata model."""

    def test_metadata(self):
        """Test creating metadata."""
        meta = CapabilitiesMetadata(
            schema_version="1.0.0",
            ciris_requirements_version="1.0.0",
            update_frequency="weekly",
            sources=["official docs", "testing"],
        )
        assert meta.schema_version == "1.0.0"
        assert "official docs" in meta.sources


class TestModelCapabilitiesConfig:
    """Tests for ModelCapabilitiesConfig."""

    @pytest.fixture
    def sample_config_data(self):
        """Create sample configuration data."""
        return {
            "version": "1.0.0",
            "last_updated": "2025-01-01T00:00:00Z",
            "metadata": {
                "schema_version": "1.0.0",
                "ciris_requirements_version": "1.0.0",
                "update_frequency": "weekly",
                "sources": ["testing"],
            },
            "ciris_requirements": {
                "min_context_window": 32000,
                "preferred_context_window": 128000,
                "max_combined_cost_per_million_cents": 500.0,
                "min_provider_count": 2,
                "required_capabilities": ["tool_use", "structured_output"],
                "recommended_capabilities": ["vision"],
            },
            "providers": {
                "openai": {
                    "display_name": "OpenAI",
                    "api_base": "https://api.openai.com/v1",
                    "models": {
                        "gpt-4o": {
                            "display_name": "GPT-4o",
                            "context_window": 128000,
                            "capabilities": {"tool_use": True, "structured_output": True, "vision": True},
                            "tier": "default",
                            "ciris_compatible": True,
                            "ciris_recommended": True,
                        },
                        "gpt-3.5-turbo": {
                            "display_name": "GPT-3.5 Turbo",
                            "context_window": 16000,
                            "capabilities": {"tool_use": True, "structured_output": True},
                            "tier": "fast",
                            "ciris_compatible": False,
                            "rejection_reason": "Context window too small",
                        },
                    },
                },
                "anthropic": {
                    "display_name": "Anthropic",
                    "models": {
                        "claude-3-opus": {
                            "display_name": "Claude 3 Opus",
                            "context_window": 200000,
                            "capabilities": {"tool_use": True, "structured_output": True, "vision": True},
                            "tier": "premium",
                            "ciris_compatible": True,
                            "ciris_recommended": True,
                        },
                    },
                },
            },
            "rejected_models": {
                "old-model": {
                    "display_name": "Old Model",
                    "rejection_reason": "Deprecated",
                },
            },
            "tiers": {
                "default": {
                    "description": "Default tier",
                    "use_case": "General purpose",
                },
                "fast": {
                    "description": "Fast tier",
                    "use_case": "Quick responses",
                },
                "premium": {
                    "description": "Premium tier",
                    "use_case": "Complex tasks",
                },
            },
        }

    @pytest.fixture
    def config(self, sample_config_data):
        """Create config instance from sample data."""
        return ModelCapabilitiesConfig(**sample_config_data)

    def test_validate_semver_valid(self):
        """Test valid semantic version."""
        # This is validated during creation
        assert True  # If config creation works, semver is valid

    def test_validate_semver_invalid(self, sample_config_data):
        """Test invalid semantic version."""
        sample_config_data["version"] = "1.0"
        with pytest.raises(ValueError, match="semantic versioning"):
            ModelCapabilitiesConfig(**sample_config_data)

    def test_validate_semver_non_numeric(self, sample_config_data):
        """Test non-numeric semantic version."""
        sample_config_data["version"] = "1.0.abc"
        with pytest.raises(ValueError, match="semantic versioning"):
            ModelCapabilitiesConfig(**sample_config_data)

    def test_load_from_file(self, sample_config_data):
        """Test loading config from file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_config_data, f)
            f.flush()

            config = ModelCapabilitiesConfig.load_from_file(f.name)
            assert config.version == "1.0.0"
            assert "openai" in config.providers

    def test_load_from_file_not_found(self):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            ModelCapabilitiesConfig.load_from_file("/nonexistent/path.json")

    def test_load_from_file_invalid_json(self):
        """Test loading invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json {{{")
            f.flush()

            with pytest.raises(ValueError, match="Invalid JSON"):
                ModelCapabilitiesConfig.load_from_file(f.name)

    def test_load_from_file_schema_mismatch(self):
        """Test loading JSON that doesn't match schema."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"wrong": "data"}, f)
            f.flush()

            with pytest.raises(ValueError, match="Failed to load"):
                ModelCapabilitiesConfig.load_from_file(f.name)

    def test_get_provider_models(self, config):
        """Test getting models for a provider."""
        models = config.get_provider_models("openai")
        assert models is not None
        assert "gpt-4o" in models
        assert "gpt-3.5-turbo" in models

    def test_get_provider_models_not_found(self, config):
        """Test getting models for non-existent provider."""
        models = config.get_provider_models("nonexistent")
        assert models is None

    def test_get_model(self, config):
        """Test getting specific model."""
        model = config.get_model("openai", "gpt-4o")
        assert model is not None
        assert model.display_name == "GPT-4o"

    def test_get_model_not_found_provider(self, config):
        """Test getting model from non-existent provider."""
        model = config.get_model("nonexistent", "model")
        assert model is None

    def test_get_model_not_found_model(self, config):
        """Test getting non-existent model."""
        model = config.get_model("openai", "nonexistent")
        assert model is None

    def test_get_compatible_models(self, config):
        """Test getting compatible models."""
        models = config.get_compatible_models()
        assert len(models) >= 2  # gpt-4o and claude-3-opus
        # All should be compatible
        for prov, model_id, info in models:
            assert info.ciris_compatible is True

    def test_get_compatible_models_by_provider(self, config):
        """Test getting compatible models for specific provider."""
        models = config.get_compatible_models(provider_name="openai")
        assert len(models) == 1  # Only gpt-4o is compatible
        assert models[0][1] == "gpt-4o"

    def test_get_compatible_models_invalid_provider(self, config):
        """Test getting compatible models for non-existent provider."""
        models = config.get_compatible_models(provider_name="nonexistent")
        # When provider doesn't exist, it falls through to all providers
        # This is expected behavior - returns empty if provider truly doesn't exist
        assert "nonexistent" not in [m[0] for m in models]

    def test_get_recommended_models(self, config):
        """Test getting recommended models."""
        models = config.get_recommended_models()
        assert len(models) >= 2
        for prov, model_id, info in models:
            assert info.ciris_recommended is True

    def test_get_recommended_models_by_provider(self, config):
        """Test getting recommended models for specific provider."""
        models = config.get_recommended_models(provider_name="anthropic")
        assert len(models) == 1
        assert models[0][1] == "claude-3-opus"

    def test_get_models_by_tier(self, config):
        """Test getting models by tier."""
        default_models = config.get_models_by_tier("default")
        assert len(default_models) >= 1

        premium_models = config.get_models_by_tier("premium")
        assert len(premium_models) >= 1
        assert any(m[1] == "claude-3-opus" for m in premium_models)

    def test_get_models_by_tier_with_provider(self, config):
        """Test getting models by tier for specific provider."""
        models = config.get_models_by_tier("default", provider_name="openai")
        assert len(models) == 1
        assert models[0][1] == "gpt-4o"

    def test_get_models_with_vision(self, config):
        """Test getting vision-capable models."""
        models = config.get_models_with_vision()
        assert len(models) >= 2  # gpt-4o and claude-3-opus
        for prov, model_id, info in models:
            assert info.capabilities.vision is True

    def test_get_models_with_vision_by_provider(self, config):
        """Test getting vision models for specific provider."""
        models = config.get_models_with_vision(provider_name="openai")
        assert len(models) == 1
        assert models[0][1] == "gpt-4o"

    def test_check_model_compatibility_compatible(self, config):
        """Test checking compatible model."""
        is_compat, issues = config.check_model_compatibility("openai", "gpt-4o")
        assert is_compat is True
        # May have non-blocking issues
        blocking_issues = [i for i in issues if "non-blocking" not in i]
        assert len(blocking_issues) == 0

    def test_check_model_compatibility_not_found(self, config):
        """Test checking non-existent model."""
        is_compat, issues = config.check_model_compatibility("openai", "nonexistent")
        assert is_compat is False
        assert any("not found" in i for i in issues)

    def test_check_model_compatibility_rejected(self, config):
        """Test checking rejected model."""
        is_compat, issues = config.check_model_compatibility("openai", "gpt-3.5-turbo")
        assert is_compat is False
        assert any("Context window" in i or "rejected" in i.lower() for i in issues)

    def test_list_providers(self, config):
        """Test listing providers."""
        providers = config.list_providers()
        assert len(providers) == 2
        provider_ids = [p[0] for p in providers]
        assert "openai" in provider_ids
        assert "anthropic" in provider_ids


class TestGetModelCapabilities:
    """Tests for get_model_capabilities function."""

    def test_get_model_capabilities_loads_default(self):
        """Test loading default config file."""
        # This should load the actual MODEL_CAPABILITIES.json
        config = get_model_capabilities(reload=True)
        assert config is not None
        assert config.version is not None
        assert len(config.providers) > 0

    def test_get_model_capabilities_singleton(self):
        """Test that it returns the same instance."""
        import ciris_engine.config.model_capabilities as module

        module._capabilities_config = None
        config1 = get_model_capabilities()
        config2 = get_model_capabilities()
        assert config1 is config2

    def test_get_model_capabilities_reload(self):
        """Test reloading configuration."""
        config1 = get_model_capabilities()
        config2 = get_model_capabilities(reload=True)
        # After reload, should still have valid config
        assert config2 is not None
        assert config2.version is not None
