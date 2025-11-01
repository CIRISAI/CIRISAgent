"""
LLM service configuration models.

This module provides typed configuration for LLM services with support
for primary/secondary providers and fallback scenarios.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InstructorMode(str, Enum):
    """Instructor library modes for structured output."""

    JSON = "JSON"
    MD_JSON = "MD_JSON"
    TOOLS = "TOOLS"


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    api_key: str = Field(description="API key for LLM provider")
    base_url: str = Field(default="https://api.openai.com/v1", description="API base URL")
    model_name: str = Field(default="gpt-4o-mini", description="Model identifier")
    instructor_mode: InstructorMode = Field(
        default=InstructorMode.JSON, description="Instructor mode for structured output"
    )
    timeout_seconds: int = Field(default=30, ge=1, le=300, description="Request timeout")
    max_retries: int = Field(default=3, ge=0, le=10, description="Maximum retry attempts")


class LLMConfig(BaseModel):
    """Complete LLM service configuration."""

    primary: Optional[LLMProviderConfig] = Field(
        default=None, description="Primary LLM provider (required unless mock mode)"
    )
    secondary: Optional[LLMProviderConfig] = Field(default=None, description="Secondary LLM provider for fallback")
    skip_initialization: bool = Field(default=False, description="Skip LLM init (set by mock module detection)")

    @classmethod
    def from_env_and_essential(cls, essential_config, skip_llm_init: bool = False) -> "LLMConfig":
        """Load from environment and essential config.

        Environment Variables:
            OPENAI_API_KEY: Primary LLM API key
            INSTRUCTOR_MODE: Instructor mode (JSON|MD_JSON|TOOLS)
            CIRIS_OPENAI_API_KEY_2: Secondary LLM key (optional)
            CIRIS_OPENAI_API_BASE_2: Secondary LLM base URL (optional)
            CIRIS_OPENAI_MODEL_NAME_2: Secondary LLM model (optional)

        Args:
            essential_config: EssentialConfig instance
            skip_llm_init: Skip initialization (for mock mode)

        Returns:
            LLMConfig with optional primary/secondary providers
        """
        import os

        if skip_llm_init:
            return cls(skip_initialization=True)

        # Primary LLM
        primary_key = os.getenv("OPENAI_API_KEY", "")
        primary_config = None
        if primary_key:
            primary_config = LLMProviderConfig(
                api_key=primary_key,
                base_url=essential_config.services.llm_endpoint,
                model_name=essential_config.services.llm_model,
                instructor_mode=InstructorMode(os.getenv("INSTRUCTOR_MODE", "JSON")),
                timeout_seconds=essential_config.services.llm_timeout,
                max_retries=essential_config.services.llm_max_retries,
            )

        # Secondary LLM (optional)
        secondary_key = os.getenv("CIRIS_OPENAI_API_KEY_2", "")
        secondary_config = None
        if secondary_key:
            secondary_config = LLMProviderConfig(
                api_key=secondary_key,
                base_url=os.getenv("CIRIS_OPENAI_API_BASE_2", essential_config.services.llm_endpoint),
                model_name=os.getenv("CIRIS_OPENAI_MODEL_NAME_2", essential_config.services.llm_model),
                instructor_mode=InstructorMode(os.getenv("INSTRUCTOR_MODE", "JSON")),
                timeout_seconds=essential_config.services.llm_timeout,
                max_retries=essential_config.services.llm_max_retries,
            )

        return cls(
            primary=primary_config,
            secondary=secondary_config,
            skip_initialization=False,
        )
