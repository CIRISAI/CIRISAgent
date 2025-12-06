"""
Schemas for config validator operations.

These replace all Dict[str, Any] usage in logic/utils/config_validator.py.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import ConfigDict, ConfigValue


class ConfigData(BaseModel):
    """Configuration data for validation."""

    llm_services: ConfigDict = Field(default_factory=dict, description="LLM services config")
    database: ConfigDict = Field(default_factory=dict, description="Database config")
    secrets: ConfigDict = Field(default_factory=dict, description="Secrets config")
    additional_config: ConfigDict = Field(default_factory=dict, description="Other configuration")


class LLMConfig(BaseModel):
    """LLM configuration."""

    openai: ConfigDict = Field(default_factory=dict, description="OpenAI config")
    additional_providers: ConfigDict = Field(default_factory=dict, description="Other LLM providers")


# OpenAIConfig moved to schemas/config/core.py to avoid duplication


class DatabaseValidationConfig(BaseModel):
    """Database configuration for validation."""

    db_filename: Optional[str] = Field(None, description="Database filename")
    additional_settings: ConfigDict = Field(default_factory=dict, description="Other database settings")


class MaskedConfigResult(BaseModel):
    """Result of masking sensitive configuration values."""

    masked_config: ConfigDict = Field(..., description="Configuration with masked sensitive values")
    masked_count: int = Field(0, description="Number of values masked")
    masked_paths: List[str] = Field(default_factory=list, description="Paths that were masked")


class NestedValueUpdate(BaseModel):
    """Represents a nested value update operation."""

    target_object: ConfigDict = Field(..., description="Object to update")
    path: str = Field(..., description="Dot-separated path")
    value: ConfigValue = Field(..., description="Value to set")
    original_value: Optional[ConfigValue] = Field(None, description="Original value before update")
