"""OpenAI Compatible LLM Service module."""

import instructor

# Import dependencies used by tests for mocking
from openai import AsyncOpenAI

# Re-export CircuitBreaker for backwards compatibility
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker

from .service import OpenAICompatibleClient, OpenAIConfig

# Export the main classes and dependencies for external use
__all__ = ["OpenAICompatibleClient", "OpenAIConfig", "AsyncOpenAI", "instructor", "CircuitBreaker"]
