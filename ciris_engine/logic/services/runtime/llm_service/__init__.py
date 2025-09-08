"""OpenAI Compatible LLM Service module."""

from .service import OpenAICompatibleClient, OpenAIConfig

# Import dependencies used by tests for mocking
from openai import AsyncOpenAI
import instructor

# Re-export CircuitBreaker for backwards compatibility
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker

# Export the main classes and dependencies for external use
__all__ = ["OpenAICompatibleClient", "OpenAIConfig", "AsyncOpenAI", "instructor", "CircuitBreaker"]