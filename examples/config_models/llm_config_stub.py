"""
Example stub for LLMConfig

This file shows the structure of LLM configuration models.
It is NOT executable - just a reference for Phase 1 implementation.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InstructorMode(str, Enum):
    """Instructor library modes."""

    JSON = "JSON"
    MD_JSON = "MD_JSON"
    TOOLS = "TOOLS"


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider.

    Environment Variables (Primary):
        OPENAI_API_KEY: API key
        INSTRUCTOR_MODE: JSON|MD_JSON|TOOLS
        (base_url, model_name, timeout, retries come from EssentialConfig)

    Environment Variables (Secondary):
        CIRIS_OPENAI_API_KEY_2: API key
        CIRIS_OPENAI_API_BASE_2: Base URL (optional, uses default if not set)
        CIRIS_OPENAI_MODEL_NAME_2: Model name (optional, uses default if not set)
    """

    api_key: str
    base_url: str = Field(default="https://api.openai.com/v1")
    model_name: str = Field(default="gpt-4o-mini")
    instructor_mode: InstructorMode = Field(default=InstructorMode.JSON)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)


class LLMConfig(BaseModel):
    """Complete LLM service configuration.

    Handles primary and optional secondary LLM providers.
    """

    primary: Optional[LLMProviderConfig] = None
    secondary: Optional[LLMProviderConfig] = None
    skip_initialization: bool = Field(default=False, description="Set True when mock LLM module detected")

    @classmethod
    def from_env_and_essential(
        cls, essential_config: "EssentialConfig", skip_llm_init: bool = False  # type: ignore
    ) -> "LLMConfig":
        """Load from environment and essential config."""
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


# Example usage:
if __name__ == "__main__":
    # Mock essential config
    class MockEssentialConfig:
        class services:
            llm_endpoint = "https://api.openai.com/v1"
            llm_model = "gpt-4o-mini"
            llm_timeout = 30
            llm_max_retries = 3

    # Load config
    config = LLMConfig.from_env_and_essential(MockEssentialConfig(), skip_llm_init=False)

    if config.skip_initialization:
        print("LLM initialization skipped (mock mode)")
    elif config.primary:
        print(f"Primary LLM: {config.primary.model_name} @ {config.primary.base_url}")
        if config.secondary:
            print(f"Secondary LLM: {config.secondary.model_name} @ {config.secondary.base_url}")
    else:
        print("No LLM configured (missing OPENAI_API_KEY)")
