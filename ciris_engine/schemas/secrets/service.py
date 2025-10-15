"""
Schemas for secrets service operations.

These schemas define the data structures used by the secrets service.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict

from ..runtime.enums import SensitivityLevel


class SecretRecallResult(BaseModel):
    """Result of secret recall operation."""

    found: bool = Field(..., description="Whether the secret was found")
    value: Optional[str] = Field(None, description="Decrypted secret value")
    error: Optional[str] = Field(None, description="Error message if failed")

    model_config = ConfigDict(extra="forbid")


class DecapsulationContext(BaseModel):
    """Context for decapsulating secrets in parameters."""

    action_type: str = Field(..., description="Type of action being executed")
    thought_id: str = Field(..., description="ID of thought executing the action")
    user_id: Optional[str] = Field(None, description="ID of user if applicable")

    model_config = ConfigDict(extra="forbid")


class PatternConfig(BaseModel):
    """Configuration for a secret detection pattern."""

    name: str = Field(..., description="Pattern name")
    pattern: str = Field(..., description="Regex pattern")
    sensitivity: SensitivityLevel = Field(..., description="Sensitivity level")
    enabled: bool = Field(True, description="Whether pattern is enabled")

    model_config = ConfigDict(extra="forbid")


class SensitivityConfig(BaseModel):
    """Configuration for sensitivity levels."""

    level: SensitivityLevel = Field(..., description="Sensitivity level")
    redaction_enabled: bool = Field(True, description="Whether to redact at this level")
    audit_enabled: bool = Field(True, description="Whether to audit at this level")

    model_config = ConfigDict(extra="forbid")


class FilterStats(BaseModel):
    """Statistics from filter operations."""

    patterns_updated: int = Field(0, description="Number of patterns updated")
    sensitivity_levels_updated: int = Field(0, description="Number of sensitivity levels updated")

    model_config = ConfigDict(extra="forbid")


class FilterUpdateRequest(BaseModel):
    """Request to update filter configuration."""

    patterns: Optional[List[PatternConfig]] = Field(None, description="Pattern updates")
    sensitivity_config: Optional[Dict[str, SensitivityConfig]] = Field(None, description="Sensitivity updates")

    model_config = ConfigDict(extra="forbid")


class FilterUpdateResult(BaseModel):
    """Result of filter update operation."""

    success: bool = Field(..., description="Whether update succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    results: Optional[List[JSONDict]] = Field(None, description="Update results as attribute dictionaries")
    accessor: Optional[str] = Field(None, description="Accessor who performed update")
    stats: Optional[FilterStats] = Field(None, description="Update statistics")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "SecretRecallResult",
    "DecapsulationContext",
    "PatternConfig",
    "SensitivityConfig",
    "FilterStats",
    "FilterUpdateRequest",
    "FilterUpdateResult",
]
