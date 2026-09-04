"""LLM validation and model listing functions for CIRIS setup module.

This module handles LLM configuration validation and live model queries
for the setup wizard.
"""

import asyncio
import os
import logging
from typing import Any, Dict, List, Optional

from ciris_engine.config.model_capabilities import get_model_capabilities

from .models import ListModelsResponse, LiveModelInfo, LLMProvider, LLMValidationRequest, LLMValidationResponse
from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log
from ciris_engine.logic.services.runtime.llm_service.model_listing import (
    SDK_ANTHROPIC,
    SDK_GOOGLE,
    SDK_OPENAI,
    list_model_ids,
)

logger = logging.getLogger(__name__)

# Constants for live model listing
# This table is not only for listing models: `_get_provider_base_url` reads it
# when the wizard finishes, and whatever it returns is what lands in .env as
# OPENAI_API_BASE (routes/setup/config.py:442). A provider the wizard offers but
# this table does not name therefore writes OPENAI_API_BASE="" — and an empty
# base URL is not an error, it is the OpenAI default, so the agent silently
# sends that provider's key to api.openai.com. Any id added to the client's
# provider dropdown must appear here too.
_PROVIDER_BASE_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "deepinfra": "https://api.deepinfra.com/v1/openai",
}

# OpenRouter serves ~420 models; that payload over a consumer connection does not
# reliably complete in 10s, and a timeout here is indistinguishable from a broken
# provider to the user because the wizard silently shows cached data instead.
# Overridable so an operator on a slow link can raise it without a rebuild.
_LIST_MODELS_TIMEOUT = float(os.environ.get("CIRIS_LIST_MODELS_TIMEOUT_SECONDS", "30"))


def _get_llm_providers() -> List[LLMProvider]:
    """Get list of supported LLM providers.

    Note: CIRIS Proxy is not listed here as it's determined at first-run setup
    and managed internally with multi-region failover. These are the BYOK providers
    that users can configure as primary or secondary alongside CIRIS.
    """
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
            default_model="qwen/qwen3.6-35b-a3b",
            examples=[
                "Qwen3.6 35B A3B",
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
            id="deepinfra",
            name="DeepInfra",
            description="vLLM-backed open models (Qwen, DeepSeek, Llama)",
            requires_api_key=True,
            requires_base_url=False,
            requires_model=True,
            default_base_url="https://api.deepinfra.com/v1/openai",
            default_model="Qwen/Qwen3.6-35B-A3B",
            examples=[
                "Qwen3.6 35B A3B",
                "DeepSeek V3",
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
    if config.api_key and config.api_key != config.api_key.strip():
        # A pasted key with a trailing newline produces a LOCAL connection error
        # whose str() is just "Connection error." — observed on every provider —
        # so the user is sent to their network for a clipboard problem. Catch it
        # where the information still exists.
        return LLMValidationResponse(
            valid=False,
            message="API key has stray whitespace",
            error="The API key starts or ends with whitespace or a newline — re-paste it without them.",
        )
    if config.provider not in ("local", "local_inference", "mobile_local") and not config.api_key:
        # Non-keyless providers need an API key. `mobile_local` runs an
        # on-device OpenAI-compatible server on loopback so no external
        # credential is required — same as `local` / `local_inference`.
        # This mirrors the allowlist used in `complete.py::_save_setup_config`.
        return LLMValidationResponse(valid=False, message="API key required", error="This provider requires an API key")
    return None


# What each structured fault slug means TO THE USER, as (headline, remedy).
# The remedy names the action that actually fixes the fault — the live matrix
# measured a 45% rate of messages that contradicted the real cause, and every
# entry here was a cell in that gap: model_not_found and policy_blocked both
# read "check your endpoint", and insufficient_quota read "replace your key"
# (which replaces a working key and fixes nothing).
_FAULT_RESPONSES = {
    "model_not_found": (
        "Model not found",
        "The provider does not serve this model (it may have been retired). "
        "List the provider's models and pick one it actually offers.",
    ),
    "invalid_api_key": (
        "Authentication failed",
        "The provider rejected the API key. Check the key — including stray whitespace — "
        "or issue a new one.",
    ),
    "rate_limited": (
        "Rate limited",
        "The provider is rate-limiting this key. Wait a moment and try again.",
    ),
    "insufficient_quota": (
        "Out of credit",
        "The key is valid but the account has no credit. Add funds in the provider's "
        "billing settings — replacing the key will not help.",
    ),
    "policy_blocked": (
        "Blocked by data policy",
        "No endpoint for this model satisfies the request's data-retention/routing "
        "constraints. Choose a different model, or review the provider's privacy "
        "settings if you manage them.",
    ),
}


def _classify_llm_connection_error(error: Exception, base_url: Optional[str]) -> LLMValidationResponse:
    """Classify an LLM connection error into the user's actual remedy.

    TYPED FIRST, PROSE LAST. The provider's structured verdict — its
    ``body.error.code``, its status, its own body message — is read by
    ``_root_provider_fault``, the same walker the runtime health surface uses,
    so setup and the running agent diagnose a fault identically. Substring
    matching over ``str(error)`` remains only as the final fallback for
    transport-level failures that carry no provider body at all, because that is
    where the 45% classifier gap came from: a 404 whose body named the missing
    MODEL was read as an unreachable ENDPOINT, and the user was sent to check a
    network that was fine.
    """
    from ciris_engine.logic.services.runtime.llm_service.service import _root_provider_fault

    fault = _root_provider_fault(error)
    if fault in _FAULT_RESPONSES:
        headline, remedy = _FAULT_RESPONSES[fault]
        return LLMValidationResponse(valid=False, message=headline, error=remedy)

    # Transport-level failures: no provider body to read, so the exception TYPE
    # is the evidence. openai's typed exceptions cover the SDK paths.
    try:
        from openai import APIConnectionError, APITimeoutError

        if isinstance(error, APITimeoutError):
            return LLMValidationResponse(
                valid=False,
                message="Connection timeout",
                error="The provider did not answer in time. Check the endpoint URL and your network.",
            )
        if isinstance(error, APIConnectionError):
            return LLMValidationResponse(
                valid=False,
                message="Connection failed",
                error=(
                    f"Could not connect to {base_url}. Check the URL and that the server is running."
                    if base_url
                    else "Could not connect to the provider. Check your network and the endpoint URL."
                ),
            )
    except ImportError:  # pragma: no cover - openai is a hard dependency
        pass

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
    # The key's PREFIX is not a safe thing to log. `sk-` is 3 characters, so
    # `[:20]` published 17 characters of the secret — and on the else-branch,
    # a key of 20 characters or fewer was logged in full. The line above
    # already reports presence and length, which is everything this log was
    # actually used to diagnose (empty key, whitespace, wrong variable).
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
    from ciris_engine.logic.services.runtime.llm_service.service import build_request_extra_body

    # Build client configuration
    client_kwargs: Dict[str, Any] = {"api_key": config.api_key or "local"}

    # Resolve base URL using provider defaults
    resolved_base_url = _get_provider_base_url(config.provider, config.base_url)
    if resolved_base_url:
        client_kwargs["base_url"] = resolved_base_url

    logger.info(f"[VALIDATE_LLM] Creating OpenAI client with base_url: {client_kwargs.get('base_url', 'default')}")

    client = AsyncOpenAI(**client_kwargs)
    model_to_test = config.model or ""  # unreachable empty: _validate_llm_connection refuses first

    # SAME request shaping as the pipeline (CIRISAgent Lane A). Validating with a
    # bare completion asked the provider a different question than the agent will
    # actually ask, so setup could bless a configuration the pipeline then
    # refused. With zero-data-retention that gap inverts the guarantee: omitting
    # the policy makes validation MORE likely to succeed, so a privacy-
    # constrained user would be told their setup works precisely because the
    # check dropped the constraint they asked for.
    extra_body = build_request_extra_body(
        resolved_base_url or "",
        model_to_test,
        require_zero_data_retention=config.require_zero_data_retention,
    )

    # Try max_tokens first, fall back to max_completion_tokens for reasoning models
    try:
        await client.chat.completions.create(
            model=model_to_test,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
            extra_body=extra_body,
        )
    except Exception as token_err:
        error_str = str(token_err).lower()
        if "max_tokens" in error_str and "max_completion_tokens" in error_str:
            logger.info("[VALIDATE_LLM] Model requires max_completion_tokens, retrying...")
            await client.chat.completions.create(
                model=model_to_test,
                messages=[{"role": "user", "content": "Hi"}],
                max_completion_tokens=1,
                extra_body=extra_body,
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
        model_to_test = config.model or ""  # unreachable empty: _validate_llm_connection refuses first
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
        model_to_test = config.model or ""  # unreachable empty: _validate_llm_connection refuses first
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
        # On-device inference has no remote endpoint to probe — the
        # capability probe in the mobile adapter is the real validation
        # step. Returning success here matches the mobile client's
        # short-circuit for `mobile_local` and prevents the backend from
        # trying to hit a non-existent endpoint with OpenAI defaults.
        if config.provider == "mobile_local":
            logger.info("[VALIDATE_LLM] mobile_local: on-device inference, skipping remote probe")
            return LLMValidationResponse(
                valid=True,
                message="On-device inference — no remote endpoint to validate",
                error=None,
            )

        # NO MODEL, NO VALIDATION. The fallbacks this replaces substituted a
        # per-provider guess (an OpenAI 3.5-era model, a Claude, a Gemini) and posted it
        # as though the user had chosen it. Same class as CIRISAgent#1078, on
        # the setup path. Two ways that answered falsely: on providers that DO
        # serve the guess (OpenAI, OpenRouter) it returned 200 and the wizard
        # said "Connection successful!" for a model the user never picked and
        # the catalogue marks incompatible; on providers that do not, the 404
        # was blamed on the network. A validation is a statement about the
        # user's ACTUAL configuration or it is nothing.
        if not (config.model or "").strip():
            return LLMValidationResponse(
                valid=False,
                message="No model selected",
                error=(
                    "Select a model before validating. List the provider's models first — "
                    "validation tests the exact provider + key + model you will run with, "
                    "so there is nothing meaningful to test until a model is chosen."
                ),
            )

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
    ids = await asyncio.wait_for(
        list_model_ids(SDK_OPENAI, api_key, base_url, timeout=_LIST_MODELS_TIMEOUT),
        timeout=_LIST_MODELS_TIMEOUT,
    )
    return [LiveModelInfo(id=i, display_name=i, source="live") for i in ids]


async def _list_models_anthropic(api_key: str) -> List[LiveModelInfo]:
    """Query models from the Anthropic API using the native SDK."""
    ids = await asyncio.wait_for(
        list_model_ids(SDK_ANTHROPIC, api_key, timeout=_LIST_MODELS_TIMEOUT),
        timeout=_LIST_MODELS_TIMEOUT,
    )
    return [LiveModelInfo(id=i, display_name=i, source="live") for i in ids]


async def _list_models_google(api_key: str) -> List[LiveModelInfo]:
    """Query models from Google AI using the google-genai SDK."""
    ids = await asyncio.wait_for(
        list_model_ids(SDK_GOOGLE, api_key, timeout=_LIST_MODELS_TIMEOUT),
        timeout=_LIST_MODELS_TIMEOUT,
    )
    return [LiveModelInfo(id=i, display_name=i, source="live") for i in ids]


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
    except asyncio.TimeoutError:
        # Named separately because the remedy differs: nothing is misconfigured,
        # the catalogue just did not arrive in time. Told apart from a broken
        # provider, this is a retry; lumped in with one, it is a support ticket.
        logger.warning(
            "[LIST_MODELS] provider=%s url=%s TIMED OUT after %.0fs listing models — "
            "showing cached data. Raise CIRIS_LIST_MODELS_TIMEOUT_SECONDS if this recurs.",
            sanitize_for_log(config.provider),
            sanitize_for_log(_get_provider_base_url(config.provider, config.base_url) or "default"),
            _LIST_MODELS_TIMEOUT,
        )
        return _build_fallback_response(
            config.provider,
            f"timed out after {_LIST_MODELS_TIMEOUT:.0f}s",
        )
    except Exception as e:
        # LOG THE EXCEPTION. The previous version logged only that something went
        # wrong, so seven consecutive failures in a real user's log said nothing
        # about why — and the wizard then presented cached models as though they
        # had been confirmed against their key. A fallback nobody can diagnose is
        # worse than an error, because it looks like success.
        logger.warning(
            "[LIST_MODELS] provider=%s url=%s live query FAILED (%s): %s — showing cached data",
            sanitize_for_log(config.provider),
            sanitize_for_log(_get_provider_base_url(config.provider, config.base_url) or "default"),
            type(e).__name__,
            sanitize_for_log(str(e)[:300]),
            exc_info=True,
        )
        return _build_fallback_response(config.provider, f"{type(e).__name__}: {e}")

    annotated = _annotate_models_with_capabilities(live_models, config.provider)
    sorted_models = _sort_models(annotated)

    return ListModelsResponse(
        provider=config.provider,
        models=sorted_models,
        total_count=len(sorted_models),
        source="live",
    )
