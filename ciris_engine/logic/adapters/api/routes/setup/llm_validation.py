"""LLM validation and model listing functions for CIRIS setup module.

This module handles LLM configuration validation and live model queries
for the setup wizard.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from ciris_engine.config.model_capabilities import get_model_capabilities

from .models import ListModelsResponse, LiveModelInfo, LLMProvider, LLMValidationRequest, LLMValidationResponse

logger = logging.getLogger(__name__)

# Constants for live model listing
_PROVIDER_BASE_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
}

_LIST_MODELS_TIMEOUT = 10.0  # seconds


def _get_llm_providers() -> List[LLMProvider]:
    """Get list of supported LLM providers."""
    return [
        LLMProvider(
            id="openai",
            name="OpenAI",
            description="Official OpenAI API (GPT-4, GPT-5.2, etc.)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url=None,
            default_model="gpt-5.2",
            examples=[
                "GPT-5.2 Thinking",
                "GPT-4o",
            ],
        ),
        LLMProvider(
            id="anthropic",
            name="Anthropic",
            description="Claude models (Claude Sonnet 4.5, Opus 4.5, Haiku 4.5)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url=None,
            default_model="claude-sonnet-4-5-20250929",
            examples=[
                "Claude Sonnet 4.5",
                "Claude Opus 4.5",
                "Claude Haiku 4.5",
            ],
        ),
        LLMProvider(
            id="openrouter",
            name="OpenRouter",
            description="Access 100+ models via OpenRouter",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://openrouter.ai/api/v1",
            default_model="meta-llama/llama-4-maverick",
            examples=[
                "Llama 4 Maverick",
                "GPT-4o via OpenRouter",
            ],
        ),
        LLMProvider(
            id="groq",
            name="Groq",
            description="Ultra-fast LPU inference (Llama 3.3, Mixtral)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://api.groq.com/openai/v1",
            default_model="llama-3.3-70b-versatile",
            examples=[
                "Llama 3.3 70B Versatile",
                "Llama 3.2 90B Vision",
            ],
        ),
        LLMProvider(
            id="together",
            name="Together AI",
            description="High-performance open models",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://api.together.xyz/v1",
            default_model="meta-llama/Llama-3.3-70B-Instruct-Turbo",
            examples=[
                "Llama 3.3 70B Turbo",
                "Llama Vision Free",
            ],
        ),
        LLMProvider(
            id="google",
            name="Google AI",
            description="Gemini models (Gemini 2.0, 1.5 Pro)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://generativelanguage.googleapis.com/v1beta",
            default_model="gemini-2.0-flash-exp",
            examples=[
                "Gemini 2.0 Flash",
                "Gemini 1.5 Pro",
            ],
        ),
        LLMProvider(
            id="local",
            name="Local LLM",
            description="Local LLM server (Ollama, LM Studio, vLLM, etc.)",
            requires_api_key=False,
            requires_base_url=True,
            requires_model=True,
            default_base_url="http://localhost:11434",
            default_model="llama3",
            examples=[
                "Ollama: http://localhost:11434",
                "LM Studio: http://localhost:1234/v1",
                "vLLM: http://localhost:8000/v1",
                "LocalAI: http://localhost:8080/v1",
            ],
        ),
        LLMProvider(
            id="other",
            name="Other",
            description="Any OpenAI-compatible API endpoint",
            requires_api_key=True,
            requires_base_url=True,
            requires_model=True,
            default_base_url=None,
            default_model=None,
            examples=[
                "Custom endpoints",
                "Private deployments",
            ],
        ),
    ]


def _validate_api_key_for_provider(config: LLMValidationRequest) -> Optional[LLMValidationResponse]:
    """Validate API key based on provider type.

    Returns:
        LLMValidationResponse if validation fails, None if valid
    """
    if config.provider == "openai":
        if not config.api_key or config.api_key == "your_openai_api_key_here":
            return LLMValidationResponse(
                valid=False,
                message="Invalid API key",
                error="OpenAI requires a valid API key starting with 'sk-'",
            )
    elif config.provider not in ("local", "local_inference") and not config.api_key:
        # Other non-local providers need API key
        return LLMValidationResponse(valid=False, message="API key required", error="This provider requires an API key")
    return None


def _classify_llm_connection_error(error: Exception, base_url: Optional[str]) -> LLMValidationResponse:
    """Classify and format LLM connection errors.

    Args:
        error: The exception that occurred
        base_url: The base URL being connected to (None for providers with fixed endpoints)

    Returns:
        Formatted error response
    """
    error_str = str(error)

    if "401" in error_str or "Unauthorized" in error_str or "authentication_error" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Authentication failed",
            error="Invalid API key. Please check your credentials.",
        )
    if "invalid_api_key" in error_str.lower() or "invalid x-api-key" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Authentication failed",
            error="Invalid API key. Please check your credentials.",
        )
    if "404" in error_str or "Not Found" in error_str:
        # Check if it's a model not found error (common with Anthropic)
        if "model:" in error_str.lower() or "not_found_error" in error_str.lower():
            return LLMValidationResponse(
                valid=False,
                message="Model not found",
                error="Model not found. Please check the model name (e.g., claude-3-5-sonnet-20241022).",
            )
        if base_url:
            return LLMValidationResponse(
                valid=False,
                message="Endpoint not found",
                error=f"Could not reach {base_url}. Please check the URL.",
            )
        return LLMValidationResponse(
            valid=False,
            message="Endpoint not found",
            error="Could not reach the API endpoint. Please check your configuration.",
        )
    if "timeout" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Connection timeout",
            error="Could not connect to LLM server. Please check if it's running.",
        )
    if "connection" in error_str.lower() and "refused" in error_str.lower():
        return LLMValidationResponse(
            valid=False,
            message="Connection refused",
            error="Could not connect to the LLM server. Please check if it's running.",
        )
    return LLMValidationResponse(valid=False, message="Connection failed", error=f"Error: {error_str}")


def _log_validation_start(config: LLMValidationRequest) -> None:
    """Log validation start details."""
    logger.info("[VALIDATE_LLM] " + "=" * 50)
    logger.info(f"[VALIDATE_LLM] Starting validation for provider: {config.provider}")
    logger.info(
        f"[VALIDATE_LLM] API key provided: {bool(config.api_key)} (length: {len(config.api_key) if config.api_key else 0})"
    )
    logger.info(
        f"[VALIDATE_LLM] API key prefix: {config.api_key[:20] + '...' if config.api_key and len(config.api_key) > 20 else config.api_key}"
    )
    logger.info(f"[VALIDATE_LLM] Base URL: {config.base_url}")
    logger.info(f"[VALIDATE_LLM] Model: {config.model}")


def _detect_ollama(base_url: Optional[str]) -> bool:
    """Check if a base URL points to an Ollama instance."""
    if not base_url:
        return False
    return ":11434" in base_url


def _get_provider_base_url(provider: str, base_url: Optional[str]) -> Optional[str]:
    """Resolve the base URL for a provider, using known defaults if not provided."""
    if base_url:
        return base_url
    return _PROVIDER_BASE_URLS.get(provider)


async def _validate_openai_compatible(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate OpenAI-compatible API connection."""
    from openai import AsyncOpenAI

    # Build client configuration
    client_kwargs: Dict[str, Any] = {"api_key": config.api_key or "local"}

    # Resolve base URL using provider defaults
    resolved_base_url = _get_provider_base_url(config.provider, config.base_url)
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url

    logger.info(f"[VALIDATE_LLM] Creating OpenAI client with base_url: {client_kwargs.get('base_url', 'default')}")

    client = AsyncOpenAI(**client_kwargs)
    model_to_test = config.model or "gpt-3.5-turbo"

    # Try max_tokens first, fall back to max_completion_tokens for reasoning models
    try:
        await client.chat.completions.create(
            model=model_to_test,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
        )
    except Exception as token_err:
        error_str = str(token_err).lower()
        if "max_tokens" in error_str and "max_completion_tokens" in error_str:
            logger.info("[VALIDATE_LLM] Model requires max_completion_tokens, retrying...")
            await client.chat.completions.create(
                model=model_to_test,
                messages=[{"role": "user", "content": "Hi"}],
                max_completion_tokens=1,
            )
        else:
            raise

    logger.info(f"[VALIDATE_LLM] SUCCESS! Test completion worked with model: {model_to_test}")
    return LLMValidationResponse(
        valid=True,
        message=f"Connection successful! Model '{model_to_test}' is available.",
        error=None,
    )


async def _validate_anthropic_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate Anthropic API connection using native SDK."""
    try:
        import anthropic

        logger.info("[VALIDATE_LLM] Using Anthropic SDK for validation")
        client = anthropic.AsyncAnthropic(api_key=config.api_key)

        # Try a minimal completion
        model_to_test = config.model or "claude-haiku-4-5-20251001"
        await client.messages.create(
            model=model_to_test,
            max_tokens=1,
            messages=[{"role": "user", "content": "Hi"}],
        )  # Validation only - response not needed
        logger.info(f"[VALIDATE_LLM] SUCCESS! Anthropic test completion worked with model: {model_to_test}")
        return LLMValidationResponse(
            valid=True,
            message=f"Connection successful! Model '{model_to_test}' is available.",
            error=None,
        )
    except ImportError:
        logger.error("[VALIDATE_LLM] Anthropic SDK not installed")
        return LLMValidationResponse(
            valid=False,
            message="SDK not installed",
            error="Anthropic SDK not installed. Run: pip install anthropic",
        )
    except Exception as e:
        logger.error(f"[VALIDATE_LLM] Anthropic API call FAILED: {type(e).__name__}: {e}")
        return _classify_llm_connection_error(e, "api.anthropic.com")


async def _validate_google_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate Google AI (Gemini) connection using OpenAI-compatible endpoint."""
    try:
        from openai import AsyncOpenAI

        # Google's OpenAI-compatible endpoint
        base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        logger.info(f"[VALIDATE_LLM] Using Google OpenAI-compatible endpoint: {base_url}")

        client = AsyncOpenAI(api_key=config.api_key, base_url=base_url)

        # Try a minimal completion
        model_to_test = config.model or "gemini-2.0-flash"
        await client.chat.completions.create(
            model=model_to_test,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
        )  # Validation only - response not needed
        logger.info(f"[VALIDATE_LLM] SUCCESS! Google test completion worked with model: {model_to_test}")
        return LLMValidationResponse(
            valid=True,
            message=f"Connection successful! Model '{model_to_test}' is available.",
            error=None,
        )
    except Exception as e:
        logger.error(f"[VALIDATE_LLM] Google API call FAILED: {type(e).__name__}: {e}")
        return _classify_llm_connection_error(e, "https://generativelanguage.googleapis.com")


async def _validate_llm_connection(config: LLMValidationRequest) -> LLMValidationResponse:
    """Validate LLM configuration by attempting a connection."""
    _log_validation_start(config)

    try:
        # Validate API key for provider type
        api_key_error = _validate_api_key_for_provider(config)
        if api_key_error:
            logger.warning(f"[VALIDATE_LLM] API key validation FAILED: {api_key_error.error}")
            return api_key_error

        logger.info("[VALIDATE_LLM] API key format validation passed")

        # Route to provider-specific validators
        if config.provider == "anthropic":
            return await _validate_anthropic_connection(config)
        if config.provider == "google":
            return await _validate_google_connection(config)

        # OpenAI-compatible providers
        return await _validate_openai_compatible(config)

    except Exception as e:
        logger.error(f"[VALIDATE_LLM] API call FAILED: {type(e).__name__}: {e}")
        result = _classify_llm_connection_error(e, config.base_url)
        logger.error(f"[VALIDATE_LLM] Classified error - valid: {result.valid}, error: {result.error}")
        return result


# =============================================================================
# LIVE MODEL LISTING HELPER FUNCTIONS
# =============================================================================


async def _list_models_openai_compatible(api_key: str, base_url: Optional[str]) -> List[LiveModelInfo]:
    """Query models from an OpenAI-compatible API endpoint."""
    from openai import AsyncOpenAI

    client_kwargs: Dict[str, Any] = {"api_key": api_key or "local", "timeout": _LIST_MODELS_TIMEOUT}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = AsyncOpenAI(**client_kwargs)
    models_page = await asyncio.wait_for(client.models.list(), timeout=_LIST_MODELS_TIMEOUT)

    result: List[LiveModelInfo] = []
    for model in models_page.data:
        result.append(LiveModelInfo(id=model.id, display_name=model.id, source="live"))
    return result


async def _list_models_anthropic(api_key: str) -> List[LiveModelInfo]:
    """Query models from the Anthropic API using the native SDK."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    result: List[LiveModelInfo] = []

    page = await asyncio.wait_for(client.models.list(limit=100), timeout=_LIST_MODELS_TIMEOUT)
    for model in page.data:
        display = getattr(model, "display_name", model.id)
        result.append(LiveModelInfo(id=model.id, display_name=display, source="live"))

    while page.has_next_page():
        page = await asyncio.wait_for(page.get_next_page(), timeout=_LIST_MODELS_TIMEOUT)
        for model in page.data:
            display = getattr(model, "display_name", model.id)
            result.append(LiveModelInfo(id=model.id, display_name=display, source="live"))

    return result


async def _google_models_to_list(client: Any) -> List[Any]:
    """Collect Google models into a list (helper to work with asyncio.wait_for)."""
    result = []
    async for model in client.aio.models.list(config={"query_base": True}):
        result.append(model)
    return result


async def _list_models_google(api_key: str) -> List[LiveModelInfo]:
    """Query models from Google AI using the google-genai SDK."""
    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        raw_models = await asyncio.wait_for(_google_models_to_list(client), timeout=_LIST_MODELS_TIMEOUT)

        result: List[LiveModelInfo] = []
        for model in raw_models:
            model_name = model.name or ""
            # Strip "models/" prefix that Google returns
            model_id = model_name.replace("models/", "") if model_name.startswith("models/") else model_name
            display = getattr(model, "display_name", None) or model_id
            result.append(LiveModelInfo(id=model_id, display_name=display, source="live"))
        return result
    except ImportError:
        # Fall back to OpenAI-compatible endpoint
        return await _list_models_openai_compatible(api_key, "https://generativelanguage.googleapis.com/v1beta/openai/")


async def _list_models_ollama(base_url: str) -> List[LiveModelInfo]:
    """Query models from an Ollama instance via /api/tags."""
    from urllib.parse import urlparse

    import httpx

    # Validate and sanitize the URL to prevent injection
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Ollama URL must use http or https scheme")

    # Reconstruct a safe URL from parsed components
    safe_base = f"{parsed.scheme}://{parsed.netloc}"

    async with httpx.AsyncClient(timeout=_LIST_MODELS_TIMEOUT) as client:
        response = await client.get(f"{safe_base}/api/tags")
        response.raise_for_status()
        data = response.json()

    result: List[LiveModelInfo] = []
    for model in data.get("models", []):
        model_name = model.get("name", "")
        result.append(LiveModelInfo(id=model_name, display_name=model_name, source="live"))
    return result


def _annotate_models_with_capabilities(models: List[LiveModelInfo], provider_id: str) -> List[LiveModelInfo]:
    """Cross-reference live models with MODEL_CAPABILITIES.json for CIRIS compatibility.

    Returns a new list of annotated models. Models found in the capabilities DB
    are enriched with compatibility info; unknown models are passed through unchanged.
    """
    try:
        config = get_model_capabilities()
    except Exception:
        return list(models)

    provider_models = config.get_provider_models(provider_id)
    if provider_models is None:
        return list(models)

    annotated: List[LiveModelInfo] = []
    for model in models:
        known_info = provider_models.get(model.id)
        if known_info is not None:
            annotated.append(
                LiveModelInfo(
                    id=model.id,
                    display_name=known_info.display_name,
                    ciris_compatible=known_info.ciris_compatible,
                    ciris_recommended=known_info.ciris_recommended,
                    tier=known_info.tier,
                    capabilities=known_info.capabilities,
                    context_window=known_info.context_window,
                    notes=known_info.notes or known_info.rejection_reason,
                    source="both",
                )
            )
        else:
            annotated.append(model)

    return annotated


def _sort_models(models: List[LiveModelInfo]) -> List[LiveModelInfo]:
    """Sort models: recommended first, then compatible, unknown, incompatible."""

    def sort_key(m: LiveModelInfo) -> tuple[int, str]:
        if m.ciris_recommended:
            priority = 0
        elif m.ciris_compatible is True:
            priority = 1
        elif m.ciris_compatible is None:
            priority = 2
        else:
            priority = 3
        return (priority, m.display_name.lower())

    return sorted(models, key=sort_key)


def _get_static_fallback_models(provider_id: str) -> List[LiveModelInfo]:
    """Load models from MODEL_CAPABILITIES.json as a static fallback."""
    try:
        config = get_model_capabilities()
    except Exception:
        return []

    provider_models = config.get_provider_models(provider_id)
    if provider_models is None:
        return []

    result: List[LiveModelInfo] = []
    for model_id, info in provider_models.items():
        result.append(
            LiveModelInfo(
                id=model_id,
                display_name=info.display_name,
                ciris_compatible=info.ciris_compatible,
                ciris_recommended=info.ciris_recommended,
                tier=info.tier,
                capabilities=info.capabilities,
                context_window=info.context_window,
                notes=info.notes or info.rejection_reason,
                source="static",
            )
        )
    return result


def _build_fallback_response(provider_id: str, error_msg: str) -> ListModelsResponse:
    """Build a response from static capabilities data when live query fails."""
    fallback_models = _get_static_fallback_models(provider_id)
    sorted_models = _sort_models(fallback_models)
    return ListModelsResponse(
        provider=provider_id,
        models=sorted_models,
        total_count=len(sorted_models),
        source="static",
        error=f"Live query failed: {error_msg}. Showing cached model data.",
    )


async def _fetch_live_models(config: LLMValidationRequest) -> List[LiveModelInfo]:
    """Dispatch to provider-specific model listing function."""
    if config.provider == "anthropic":
        return await _list_models_anthropic(config.api_key)
    if config.provider == "google":
        return await _list_models_google(config.api_key)
    if config.provider == "local" and _detect_ollama(config.base_url):
        return await _list_models_ollama(config.base_url or "http://localhost:11434")

    resolved_url = _get_provider_base_url(config.provider, config.base_url)
    return await _list_models_openai_compatible(config.api_key, resolved_url)


async def _list_models_for_provider(config: LLMValidationRequest) -> ListModelsResponse:
    """Query provider for models and annotate with CIRIS compatibility."""
    # Validate API key first (reuse existing helper)
    api_key_error = _validate_api_key_for_provider(config)
    if api_key_error and config.provider != "local":
        return _build_fallback_response(config.provider, api_key_error.error or "Invalid API key")

    try:
        live_models = await _fetch_live_models(config)
    except Exception as e:
        logger.warning("[LIST_MODELS] Live query failed, falling back to static data")
        return _build_fallback_response(config.provider, str(e))

    annotated = _annotate_models_with_capabilities(live_models, config.provider)
    sorted_models = _sort_models(annotated)

    return ListModelsResponse(
        provider=config.provider,
        models=sorted_models,
        total_count=len(sorted_models),
        source="live",
    )
