"""
Example stub for InfrastructureConfig

This file shows the structure of infrastructure configuration models.
It is NOT executable - just a reference for Phase 1 implementation.
"""

from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CreditProviderType(str, Enum):
    """Credit provider backend types."""

    BILLING = "billing"
    SIMPLE = "simple"


class BillingConfig(BaseModel):
    """Configuration for CIRIS billing provider.

    Environment Variables:
        CIRIS_BILLING_ENABLED: "true"|"false" → enabled
        CIRIS_BILLING_API_KEY: API key → api_key
        CIRIS_BILLING_API_URL: URL → base_url
        CIRIS_BILLING_TIMEOUT_SECONDS: seconds → timeout_seconds
        CIRIS_BILLING_CACHE_TTL_SECONDS: seconds → cache_ttl_seconds
        CIRIS_BILLING_FAIL_OPEN: "true"|"false" → fail_open
    """

    enabled: bool = Field(default=False)
    api_key: Optional[str] = Field(default=None)
    base_url: str = Field(default="https://billing.ciris.ai")
    timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    cache_ttl_seconds: int = Field(default=15, ge=0, le=300)
    fail_open: bool = Field(default=False)

    @field_validator("api_key")
    @classmethod
    def validate_api_key_if_enabled(cls, v: Optional[str], info) -> Optional[str]:
        """Validate API key is provided if billing is enabled."""
        if info.data.get("enabled") and not v:
            raise ValueError("api_key is required when billing is enabled")
        return v

    @classmethod
    def from_env(cls) -> "BillingConfig":
        """Load from environment variables."""
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
    """Configuration for simple free credit provider.

    Environment Variables:
        CIRIS_SIMPLE_FREE_USES: number → free_uses
    """

    free_uses: int = Field(default=0, ge=0)

    @classmethod
    def from_env(cls) -> "SimpleCreditConfig":
        """Load from environment variables."""
        import os

        return cls(free_uses=int(os.getenv("CIRIS_SIMPLE_FREE_USES", "0")))


class ResourceMonitorConfig(BaseModel):
    """Configuration for ResourceMonitorService.

    Auto-detects provider type based on CIRIS_BILLING_ENABLED.
    """

    credit_provider: CreditProviderType
    billing: Optional[BillingConfig] = None
    simple: Optional[SimpleCreditConfig] = None

    @field_validator("billing")
    @classmethod
    def validate_billing_config(cls, v: Optional[BillingConfig], info) -> Optional[BillingConfig]:
        if info.data.get("credit_provider") == CreditProviderType.BILLING and not v:
            raise ValueError("billing config required when credit_provider=billing")
        return v

    @field_validator("simple")
    @classmethod
    def validate_simple_config(cls, v: Optional[SimpleCreditConfig], info) -> Optional[SimpleCreditConfig]:
        if info.data.get("credit_provider") == CreditProviderType.SIMPLE and not v:
            raise ValueError("simple config required when credit_provider=simple")
        return v

    @classmethod
    def from_env(cls) -> "ResourceMonitorConfig":
        """Load from environment, auto-detecting provider type."""
        billing_config = BillingConfig.from_env()
        simple_config = SimpleCreditConfig.from_env()

        provider_type = CreditProviderType.BILLING if billing_config.enabled else CreditProviderType.SIMPLE

        return cls(
            credit_provider=provider_type,
            billing=billing_config if provider_type == CreditProviderType.BILLING else None,
            simple=simple_config if provider_type == CreditProviderType.SIMPLE else None,
        )


class DatabaseMaintenanceConfig(BaseModel):
    """Configuration for DatabaseMaintenanceService."""

    archive_dir_path: Path = Field(default=Path("data_archive"))
    archive_older_than_hours: int = Field(default=24, ge=1)


class InfrastructureConfig(BaseModel):
    """Complete infrastructure service configuration."""

    resource_monitor: ResourceMonitorConfig
    maintenance: DatabaseMaintenanceConfig

    @classmethod
    def from_env(cls) -> "InfrastructureConfig":
        """Load all infrastructure config from environment."""
        return cls(
            resource_monitor=ResourceMonitorConfig.from_env(),
            maintenance=DatabaseMaintenanceConfig(),
        )


# Example usage:
if __name__ == "__main__":
    # Load config from environment
    config = InfrastructureConfig.from_env()

    print(f"Credit provider: {config.resource_monitor.credit_provider}")
    if config.resource_monitor.billing:
        print(f"Billing enabled: {config.resource_monitor.billing.enabled}")
        print(f"Billing URL: {config.resource_monitor.billing.base_url}")
    if config.resource_monitor.simple:
        print(f"Free uses: {config.resource_monitor.simple.free_uses}")
