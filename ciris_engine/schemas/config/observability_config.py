"""
Observability service configuration models.

This module provides typed configuration for observability services:
- TelemetryService
- AuditService
- TSDBConsolidationService
"""

from pathlib import Path
from typing import TYPE_CHECKING, Union

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ciris_engine.schemas.config.essential import EssentialConfig


class TelemetryConfig(BaseModel):
    """Configuration for TelemetryService.

    Currently minimal as TelemetryService uses injected dependencies
    and doesn't require environment-based configuration.
    """

    pass


class AuditConfig(BaseModel):
    """Configuration for AuditService."""

    export_path: str = Field(
        default="audit_logs.jsonl", description="Path for audit log exports (file path or just filename)"
    )
    export_format: str = Field(default="jsonl", description="Audit export format")
    enable_hash_chain: bool = Field(default=True, description="Enable cryptographic hash chain")
    db_path: Union[str, Path] = Field(
        description="Path to audit database (SQLite path or PostgreSQL connection string)"
    )
    key_path: Path = Field(description="Path to audit signing keys")
    retention_days: int = Field(default=90, ge=1, description="Audit log retention in days")

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "AuditConfig":
        """Create from EssentialConfig.

        Args:
            essential_config: EssentialConfig instance

        Returns:
            AuditConfig with resolved paths
        """
        from ciris_engine.logic.config.db_paths import get_audit_db_full_path

        return cls(
            export_path="audit_logs.jsonl",  # Standard audit log path (hardcoded in service_initializer.py:899)
            export_format="jsonl",
            enable_hash_chain=True,
            db_path=get_audit_db_full_path(essential_config),  # str (SQLite path or Postgres URL)
            key_path=essential_config.security.audit_key_path,  # Correct field name
            retention_days=essential_config.security.audit_retention_days,  # From essential config
        )


class TSDBConfig(BaseModel):
    """Configuration for TSDBConsolidationService.

    Note: TSDBConsolidationService uses MemoryBus, not a separate database.
    This config model is minimal with only operational parameters.
    """

    consolidation_interval_hours: int = Field(
        default=6, frozen=True, description="Time-series consolidation interval (frozen at 6 hours)"
    )
    raw_retention_hours: int = Field(default=72, ge=24, description="How long to keep raw metrics before consolidation")

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "TSDBConfig":
        """Create from EssentialConfig.

        Args:
            essential_config: EssentialConfig instance

        Returns:
            TSDBConfig with frozen consolidation interval
        """
        return cls(
            consolidation_interval_hours=6,  # Frozen value
            raw_retention_hours=72,
        )


class ObservabilityConfig(BaseModel):
    """Complete observability service configuration."""

    telemetry: TelemetryConfig
    audit: AuditConfig
    tsdb: TSDBConfig

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "ObservabilityConfig":
        """Load all observability config from essential config.

        Args:
            essential_config: EssentialConfig instance

        Returns:
            Complete observability configuration
        """
        return cls(
            telemetry=TelemetryConfig(),
            audit=AuditConfig.from_essential_config(essential_config),
            tsdb=TSDBConfig.from_essential_config(essential_config),
        )
