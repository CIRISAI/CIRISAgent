"""
Tests for infrastructure service configuration models.
"""

import os
from unittest.mock import patch

import pytest

from ciris_engine.schemas.config.infrastructure_config import (
    BillingConfig,
    CreditProviderType,
    DatabaseMaintenanceConfig,
    InfrastructureConfig,
    ResourceMonitorConfig,
    SimpleCreditConfig,
)


class TestBillingConfig:
    """Tests for BillingConfig model."""

    def test_from_env_loads_all_variables(self):
        """BillingConfig.from_env() loads all environment variables correctly."""
        env = {
            "CIRIS_BILLING_ENABLED": "true",
            "CIRIS_BILLING_API_KEY": "test-key-123",
            "CIRIS_BILLING_API_URL": "https://custom-billing.example.com",
            "CIRIS_BILLING_TIMEOUT_SECONDS": "10.5",
            "CIRIS_BILLING_CACHE_TTL_SECONDS": "30",
            "CIRIS_BILLING_FAIL_OPEN": "true",
        }

        with patch.dict(os.environ, env, clear=True):
            config = BillingConfig.from_env()

        assert config.enabled is True
        assert config.api_key == "test-key-123"
        assert config.base_url == "https://custom-billing.example.com"
        assert config.timeout_seconds == 10.5
        assert config.cache_ttl_seconds == 30
        assert config.fail_open is True

    def test_from_env_uses_defaults(self):
        """BillingConfig.from_env() uses defaults when env vars not set."""
        with patch.dict(os.environ, {}, clear=True):
            config = BillingConfig.from_env()

        assert config.enabled is False
        assert config.api_key is None
        assert config.base_url == "https://billing.ciris.ai"
        assert config.timeout_seconds == 5.0
        assert config.cache_ttl_seconds == 15
        assert config.fail_open is False

    def test_validation_fails_when_enabled_without_api_key(self):
        """BillingConfig validation fails when enabled=True but no API key."""
        with pytest.raises(ValueError, match="api_key is required when billing is enabled"):
            BillingConfig(enabled=True, api_key=None)

    def test_validation_succeeds_when_disabled_without_api_key(self):
        """BillingConfig allows missing API key when enabled=False."""
        config = BillingConfig(enabled=False, api_key=None)
        assert config.enabled is False
        assert config.api_key is None

    def test_validation_succeeds_when_enabled_with_api_key(self):
        """BillingConfig validates successfully with API key when enabled."""
        config = BillingConfig(enabled=True, api_key="test-key")
        assert config.enabled is True
        assert config.api_key == "test-key"


class TestSimpleCreditConfig:
    """Tests for SimpleCreditConfig model."""

    def test_from_env_loads_free_uses(self):
        """SimpleCreditConfig.from_env() loads CIRIS_SIMPLE_FREE_USES."""
        with patch.dict(os.environ, {"CIRIS_SIMPLE_FREE_USES": "100"}):
            config = SimpleCreditConfig.from_env()

        assert config.free_uses == 100

    def test_from_env_uses_default_zero(self):
        """SimpleCreditConfig.from_env() defaults to 0 free uses."""
        with patch.dict(os.environ, {}, clear=True):
            config = SimpleCreditConfig.from_env()

        assert config.free_uses == 0


class TestResourceMonitorConfig:
    """Tests for ResourceMonitorConfig model."""

    def test_from_env_auto_detects_billing_provider(self):
        """ResourceMonitorConfig.from_env() auto-detects billing when enabled."""
        env = {"CIRIS_BILLING_ENABLED": "true", "CIRIS_BILLING_API_KEY": "test-key"}

        with patch.dict(os.environ, env, clear=True):
            config = ResourceMonitorConfig.from_env()

        assert config.credit_provider == CreditProviderType.BILLING
        assert config.billing is not None
        assert config.billing.enabled is True
        assert config.simple is None

    def test_from_env_auto_detects_simple_provider(self):
        """ResourceMonitorConfig.from_env() auto-detects simple when billing disabled."""
        env = {"CIRIS_SIMPLE_FREE_USES": "50"}

        with patch.dict(os.environ, env, clear=True):
            config = ResourceMonitorConfig.from_env()

        assert config.credit_provider == CreditProviderType.SIMPLE
        assert config.simple is not None
        assert config.simple.free_uses == 50
        assert config.billing is None

    def test_validation_requires_billing_config_when_billing_provider(self):
        """ResourceMonitorConfig requires billing config when provider=billing."""
        with pytest.raises(ValueError, match="billing config required when credit_provider=billing"):
            ResourceMonitorConfig(credit_provider=CreditProviderType.BILLING, billing=None)

    def test_validation_requires_simple_config_when_simple_provider(self):
        """ResourceMonitorConfig requires simple config when provider=simple."""
        with pytest.raises(ValueError, match="simple config required when credit_provider=simple"):
            ResourceMonitorConfig(credit_provider=CreditProviderType.SIMPLE, simple=None)


class TestDatabaseMaintenanceConfig:
    """Tests for DatabaseMaintenanceConfig model."""

    def test_default_values(self):
        """DatabaseMaintenanceConfig uses sensible defaults."""
        config = DatabaseMaintenanceConfig()

        assert config.archive_dir_path.name == "data_archive"
        assert config.archive_older_than_hours == 24


class TestInfrastructureConfig:
    """Tests for complete InfrastructureConfig."""

    def test_from_env_creates_complete_config(self):
        """InfrastructureConfig.from_env() creates complete configuration."""
        env = {"CIRIS_SIMPLE_FREE_USES": "25"}

        with patch.dict(os.environ, env, clear=True):
            config = InfrastructureConfig.from_env()

        assert isinstance(config.resource_monitor, ResourceMonitorConfig)
        assert isinstance(config.maintenance, DatabaseMaintenanceConfig)
        assert config.resource_monitor.credit_provider == CreditProviderType.SIMPLE
        assert config.resource_monitor.simple.free_uses == 25
