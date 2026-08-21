"""The single seam between this harness and the product.

Everything the matrix borrows from ``ciris_engine`` is imported here and
nowhere else. Two reasons:

1. The harness must grade the REAL classifier, not a copy of it. Re-deriving
   the branch logic would make the report describe a fiction. So the exception
   captured off the wire is handed to the product's own
   ``_classify_llm_connection_error`` and whatever it returns is recorded.
2. ``setup/llm_validation.py`` is under active refactor. When a symbol moves,
   exactly one file needs fixing, and :func:`bridge_status` says so out loud
   instead of the matrix silently degrading.

Nothing in this module makes a network call.
"""

from __future__ import annotations

import inspect
from typing import Callable, List, Optional, Tuple

from .schemas import ClassifierVerdict, RenderedCause

# ─────────────────────────────────────────────────────────────────────────────
# Product imports. Guarded so a moved symbol produces a legible failure.
# ─────────────────────────────────────────────────────────────────────────────

_IMPORT_ERROR: Optional[str] = None

try:
    from ciris_engine.config.model_capabilities import (  # noqa: F401
        ModelCapabilitiesConfig,
        ModelInfo,
        get_model_capabilities,
    )
    from ciris_engine.logic.adapters.api.routes.setup.llm_validation import (
        _PROVIDER_BASE_URLS,
        _build_fallback_response,
        _classify_llm_connection_error,
        _fetch_live_models,
        _get_llm_providers,
        _get_provider_base_url,
        _list_models_for_provider,
        _validate_api_key_for_provider,
    )
    from ciris_engine.logic.adapters.api.routes.setup.models import (  # noqa: F401
        ListModelsResponse,
        LiveModelInfo,
        LLMProvider,
        LLMValidationRequest,
        LLMValidationResponse,
    )
except Exception as exc:  # pragma: no cover - exercised only when the product moves
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
    raise


def bridge_status() -> str:
    """Human-readable statement of what the harness bound to."""
    module = inspect.getmodule(_classify_llm_connection_error)
    return f"bound to {module.__name__ if module else '?'} " f"({len(_PROVIDER_BASE_URLS)} entries in base-URL table)"


# ─────────────────────────────────────────────────────────────────────────────
# Constants the product uses that the matrix must know about.
#
# These are duplicated here on purpose — the product hardcodes them inline, so
# there is no symbol to import. `verify_product_constants()` reads the product
# source and confirms each is still literally present; a mismatch is reported
# as a TABLE_DIVERGENCE finding rather than being silently wrong.
# ─────────────────────────────────────────────────────────────────────────────

# `_validate_openai_compatible`: model_to_test = config.model or "gpt-3.5-turbo"
FABRICATED_MODEL_OPENAI_COMPATIBLE = "gpt-3.5-turbo"
# `_validate_anthropic_connection`: model_to_test = config.model or "claude-haiku-4-5-20251001"
FABRICATED_MODEL_ANTHROPIC = "claude-haiku-4-5-20251001"
# `_validate_google_connection`: model_to_test = config.model or "gemini-2.0-flash"
FABRICATED_MODEL_GOOGLE = "gemini-2.0-flash"
# `_validate_google_connection` hardcodes this, ignoring config.base_url.
GOOGLE_VALIDATOR_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def fabricated_model_for(provider: str) -> str:
    """The model the product substitutes when the user chose none."""
    if provider == "anthropic":
        return FABRICATED_MODEL_ANTHROPIC
    if provider == "google":
        return FABRICATED_MODEL_GOOGLE
    return FABRICATED_MODEL_OPENAI_COMPATIBLE


def verify_product_constants() -> List[Tuple[str, str, bool]]:
    """Confirm the duplicated constants above still appear in the product source.

    Returns ``(constant_name, value, still_present)`` triples so the caller can
    turn a False into a finding.
    """
    import ciris_engine.logic.adapters.api.routes.setup.llm_validation as llm_validation

    try:
        source = inspect.getsource(llm_validation)
    except OSError:  # pragma: no cover - source always available in a checkout
        return []

    checks = [
        ("FABRICATED_MODEL_OPENAI_COMPATIBLE", FABRICATED_MODEL_OPENAI_COMPATIBLE),
        ("FABRICATED_MODEL_ANTHROPIC", FABRICATED_MODEL_ANTHROPIC),
        ("FABRICATED_MODEL_GOOGLE", FABRICATED_MODEL_GOOGLE),
        ("GOOGLE_VALIDATOR_BASE_URL", GOOGLE_VALIDATOR_BASE_URL),
    ]
    return [(name, value, f'"{value}"' in source) for name, value in checks]


# ─────────────────────────────────────────────────────────────────────────────
# Branch fingerprinting
#
# `LLMValidationResponse.message` is unique per branch of
# `_classify_llm_connection_error`, so it identifies which branch fired without
# re-implementing the predicate chain (which would drift the moment the product
# reorders it).
# ─────────────────────────────────────────────────────────────────────────────

_MESSAGE_TO_CAUSE = {
    "Authentication failed": RenderedCause.AUTH,
    "Model not found": RenderedCause.MODEL_NOT_FOUND,
    "Endpoint not found": RenderedCause.ENDPOINT,
    "Connection timeout": RenderedCause.TIMEOUT,
    "Connection refused": RenderedCause.REFUSED,
    "Connection failed": RenderedCause.UNCLASSIFIED,
    "Invalid API key": RenderedCause.AUTH,
    "API key required": RenderedCause.AUTH,
    "SDK not installed": RenderedCause.SDK_MISSING,
}


def rendered_cause_for(response: "LLMValidationResponse") -> RenderedCause:
    """Map a product verdict onto the cause it communicates to the user."""
    if response.valid:
        return RenderedCause.SUCCESS
    return _MESSAGE_TO_CAUSE.get(response.message, RenderedCause.UNCLASSIFIED)


def classifier_base_url(provider: str, client_base_url: Optional[str]) -> Optional[str]:
    """The ``base_url`` argument the product hands to its classifier.

    Not the URL the request went to. The three call sites differ:

      ``_validate_anthropic_connection`` → the literal ``"api.anthropic.com"``
      ``_validate_google_connection``    → the literal generativelanguage root
      everything else                    → ``config.base_url`` **as the client
                                            sent it**, which is ``None`` for
                                            every provider the dropdown
                                            resolves internally.

    That last case is load-bearing: with ``base_url=None`` the endpoint branch
    renders "Could not reach the API endpoint. Please check your
    configuration." — the exact sentence a user gets for an OpenRouter data-
    policy rejection. Passing the resolved URL here instead would make the
    matrix report a friendlier message than the product actually shows.
    """
    if provider == "anthropic":
        return "api.anthropic.com"
    if provider == "google":
        return "https://generativelanguage.googleapis.com"
    return client_base_url


def to_verdict(response: "LLMValidationResponse") -> ClassifierVerdict:
    """Convert a product verdict into the matrix's recorded form."""
    return ClassifierVerdict(
        valid=response.valid,
        message=response.message,
        error=response.error,
        rendered_cause=rendered_cause_for(response),
    )


class ReplayedProviderError(Exception):
    """A recorded provider failure, re-raised for ``--dry-run``.

    ``_classify_llm_connection_error`` reads nothing but ``str(error)``, so an
    exception whose ``str()`` is a verbatim recording of a real SDK exception
    drives the real classifier down the real branch. The dry run therefore
    grades the same code the live run does — it only skips the wire.
    """

    def __init__(self, rendered: str, exception_type: str = "recorded") -> None:
        super().__init__(rendered)
        self._rendered = rendered
        self.exception_type = exception_type

    def __str__(self) -> str:
        return self._rendered


# Re-exported so callers need only import this module.
classify_connection_error: Callable[..., "LLMValidationResponse"] = _classify_llm_connection_error
validate_api_key_for_provider: Callable[..., Optional["LLMValidationResponse"]] = _validate_api_key_for_provider
get_provider_base_url = _get_provider_base_url
get_llm_providers = _get_llm_providers
list_models_for_provider = _list_models_for_provider
fetch_live_models = _fetch_live_models
build_fallback_response = _build_fallback_response
PROVIDER_BASE_URL_TABLE = _PROVIDER_BASE_URLS


__all__ = [
    # Product types, re-exported so callers never import ciris_engine directly.
    "ListModelsResponse",
    "LLMProvider",
    "LLMValidationRequest",
    "LLMValidationResponse",
    "LiveModelInfo",
    "ModelCapabilitiesConfig",
    "ModelInfo",
    # Harness surface.
    "FABRICATED_MODEL_ANTHROPIC",
    "FABRICATED_MODEL_GOOGLE",
    "FABRICATED_MODEL_OPENAI_COMPATIBLE",
    "GOOGLE_VALIDATOR_BASE_URL",
    "PROVIDER_BASE_URL_TABLE",
    "ReplayedProviderError",
    "bridge_status",
    "build_fallback_response",
    "classifier_base_url",
    "classify_connection_error",
    "fabricated_model_for",
    "fetch_live_models",
    "get_llm_providers",
    "get_model_capabilities",
    "get_provider_base_url",
    "list_models_for_provider",
    "rendered_cause_for",
    "to_verdict",
    "validate_api_key_for_provider",
    "verify_product_constants",
]
