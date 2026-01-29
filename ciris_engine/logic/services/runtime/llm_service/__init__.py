"""Multi-Provider LLM Service module.

Supports native SDKs for:
- OpenAI (GPT models)
- Anthropic (Claude models)
- Google (Gemini models)
"""

import instructor

# Import dependencies used by tests for mocking
from openai import AsyncOpenAI

# Re-export CircuitBreaker for backwards compatibility
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker

from .service import (
    LLMProvider,
    OpenAICompatibleClient,
    OpenAIConfig,
    _detect_provider_from_env,
    _get_api_key_for_provider,
)

# Export the main classes and dependencies for external use
__all__ = [
    "OpenAICompatibleClient",
    "OpenAIConfig",
    "LLMProvider",
    "_detect_provider_from_env",
    "_get_api_key_for_provider",
    "AsyncOpenAI",
    "instructor",
    "CircuitBreaker",
]
