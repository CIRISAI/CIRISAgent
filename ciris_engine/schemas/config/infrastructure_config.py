"""
Infrastructure service configuration models.

This module provides typed configuration for infrastructure services:
- ResourceMonitorService (billing/credits)
- DatabaseMaintenanceService
"""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class CreditProviderType(str, Enum):
    """Credit provider backend types."""

    BILLING = "billing"  # Full CIRIS billing backend
    SIMPLE = "simple"  # Simple free credit provider


class BillingConfig(BaseModel):
    """Configuration for CIRIS billing provider."""

    enabled: bool = Field(default=False, description="Enable CIRIS billing backend")
    api_key: Optional[str] = Field(default=None, description="Billing API key (required if enabled=True)")
    base_url: str = Field(default="https://billing.ciris.ai", description="Billing service base URL")
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0, description="Request timeout in seconds")
    cache_ttl_seconds: int = Field(default=15, ge=0, le=300, description="Credit check cache TTL")
    fail_open: bool = Field(default=False, description="Allow access if billing service is down")

    @field_validator("api_key")
    @classmethod
    def validate_api_key_if_enabled(cls, v: Optional[str], info) -> Optional[str]:
        """Validate API key is provided if billing is enabled."""
        if info.data.get("enabled") and not v:
            raise ValueError("api_key is required when billing is enabled")
        return v

    @classmethod
    def from_env(cls) -> "BillingConfig":
        """Load from environment variables.

        Environment Variables:
            CIRIS_BILLING_ENABLED: "true"|"false"
            CIRIS_BILLING_API_KEY: API key string
            CIRIS_BILLING_API_URL: Base URL
            CIRIS_BILLING_TIMEOUT_SECONDS: Timeout in seconds
            CIRIS_BILLING_CACHE_TTL_SECONDS: Cache TTL in seconds
            CIRIS_BILLING_FAIL_OPEN: "true"|"false"
        """
        import os

        return cls(
            enabled=os.getenv("CIRIS_BILLING_ENABLED", "false").lower() == "true",
            api_key=os.getenv("CIRIS_BILLING_API_KEY"),
            base_url=os.getenv("CIRIS_BILLING_API_URL", "https://billing.ciris.ai"),
            timeout_seconds=float(os.getenv("CIRIS_BILLING_TIMEOUT_SECONDS", "5.0")),
            cache_ttl_seconds=int(os.getenv("CIRIS_BILLING_CACHE_TTL_SECONDS", "15")),
            fail_open=os.getenv("CIRIS_BILLING_FAIL_OPEN", "false").lower() == "true",
        )


class SimpleCreditConfig(BaseModel):
    """Configuration for simple free credit provider."""

    free_uses: int = Field(default=0, ge=0, description="Number of free uses per OAuth user")

    @classmethod
    def from_env(cls) -> "SimpleCreditConfig":
        """Load from environment variables.

        Environment Variables:
            CIRIS_SIMPLE_FREE_USES: Number of free uses
        """
        import os

        return cls(free_uses=int(os.getenv("CIRIS_SIMPLE_FREE_USES", "0")))


class ResourceMonitorConfig(BaseModel):
    """Configuration for ResourceMonitorService."""

    credit_provider: CreditProviderType = Field(
        default=CreditProviderType.SIMPLE, description="Which credit provider to use"
    )
    billing: Optional[BillingConfig] = Field(
        default=None, description="Billing provider config (required if credit_provider=billing)"
    )
    simple: Optional[SimpleCreditConfig] = Field(
        default=None, description="Simple provider config (required if credit_provider=simple)"
    )

    @field_validator("billing")
    @classmethod
    def validate_billing_config(cls, v: Optional[BillingConfig], info) -> Optional[BillingConfig]:
        """Ensure billing config is provided if billing provider selected."""
        if info.data.get("credit_provider") == CreditProviderType.BILLING and not v:
            raise ValueError("billing config required when credit_provider=billing")
        return v

    @field_validator("simple")
    @classmethod
    def validate_simple_config(cls, v: Optional[SimpleCreditConfig], info) -> Optional[SimpleCreditConfig]:
        """Ensure simple config is provided if simple provider selected."""
        if info.data.get("credit_provider") == CreditProviderType.SIMPLE and not v:
            raise ValueError("simple config required when credit_provider=simple")
        return v

    @classmethod
    def from_env(cls) -> "ResourceMonitorConfig":
        """Load from environment, auto-detecting provider type."""
        billing_config = BillingConfig.from_env()
        simple_config = SimpleCreditConfig.from_env()

        # Auto-detect provider type
        provider_type = CreditProviderType.BILLING if billing_config.enabled else CreditProviderType.SIMPLE

        return cls(
            credit_provider=provider_type,
            billing=billing_config if provider_type == CreditProviderType.BILLING else None,
            simple=simple_config if provider_type == CreditProviderType.SIMPLE else None,
        )


class DatabaseMaintenanceConfig(BaseModel):
    """Configuration for DatabaseMaintenanceService."""

    archive_dir_path: Path = Field(default=Path("data_archive"), description="Directory for archived data")
    archive_older_than_hours: int = Field(default=24, ge=1, description="Archive data older than N hours")


class InfrastructureConfig(BaseModel):
    """Complete infrastructure service configuration."""

    resource_monitor: ResourceMonitorConfig
    maintenance: DatabaseMaintenanceConfig

    @classmethod
    def from_env(cls) -> "InfrastructureConfig":
        """Load all infrastructure config from environment."""
        return cls(
            resource_monitor=ResourceMonitorConfig.from_env(),
            maintenance=DatabaseMaintenanceConfig(),  # Uses defaults for now
        )
