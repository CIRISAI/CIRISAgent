"""
Governance service configuration models.

This module provides typed configuration for governance services:
- AdaptiveFilterService
- SelfObservationService
- VisibilityService
- ConsentService
"""

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field, field_validator

if TYPE_CHECKING:
    from ciris_engine.schemas.config.essential import EssentialConfig


class AdaptiveFilterConfig(BaseModel):
    """Configuration for AdaptiveFilterService.

    Currently minimal as AdaptiveFilterService uses injected dependencies
    (LLMBus, WiseBus, MemoryBus) and doesn't require environment-based config.
    """

    pass


class SelfObservationConfig(BaseModel):
    """Configuration for SelfObservationService."""

    variance_threshold: float = Field(
        default=0.15, ge=0.0, le=1.0, description="Identity variance alert threshold (0.0-1.0)"
    )
    observation_interval_hours: int = Field(default=24, ge=1, description="Hours between self-observation cycles")

    @field_validator("variance_threshold")
    @classmethod
    def validate_threshold_range(cls, v: float) -> float:
        """Ensure threshold is in valid range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"variance_threshold must be between 0.0 and 1.0, got {v}")
        return v


class VisibilityConfig(BaseModel):
    """Configuration for VisibilityService.

    Note: VisibilityService uses the main SQLite database (get_sqlite_db_full_path).
    """

    db_path: Path = Field(description="Path to main database (shared with other services)")

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "VisibilityConfig":
        """Create from EssentialConfig.

        Args:
            essential_config: EssentialConfig instance

        Returns:
            VisibilityConfig with resolved paths
        """
        from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path

        return cls(db_path=Path(get_sqlite_db_full_path(essential_config)))


class ConsentConfig(BaseModel):
    """Configuration for ConsentService.

    Note: ConsentService uses the main SQLite database (get_sqlite_db_full_path).
    """

    db_path: Path = Field(description="Path to main database (shared with other services)")

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "ConsentConfig":
        """Create from EssentialConfig.

        Args:
            essential_config: EssentialConfig instance

        Returns:
            ConsentConfig with resolved paths
        """
        from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path

        return cls(db_path=Path(get_sqlite_db_full_path(essential_config)))


class GovernanceConfig(BaseModel):
    """Complete governance service configuration."""

    adaptive_filter: AdaptiveFilterConfig
    self_observation: SelfObservationConfig
    visibility: VisibilityConfig
    consent: ConsentConfig

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "GovernanceConfig":
        """Load all governance config from essential config.

        Args:
            essential_config: EssentialConfig instance

        Returns:
            Complete governance configuration
        """
        return cls(
            adaptive_filter=AdaptiveFilterConfig(),
            self_observation=SelfObservationConfig(),
            visibility=VisibilityConfig.from_essential_config(essential_config),
            consent=ConsentConfig.from_essential_config(essential_config),
        )
