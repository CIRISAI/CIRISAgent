"""Multi-Provider LLM Service with Circuit Breaker Integration.

Supports native SDKs for:
- OpenAI (GPT models)
- Anthropic (Claude models)
- Google (Gemini models)
"""

import json
import logging
import os
import re
import time
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type, Union, cast

import instructor
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    AuthenticationError,
    InternalServerError,
    RateLimitError,
)
from pydantic import BaseModel, ConfigDict, Field


class LLMProvider(str, Enum):
    """Supported LLM providers."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OPENAI_COMPATIBLE = "openai_compatible"  # For OpenRouter, Groq, Together, etc.


from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import LLMService as LLMServiceProtocol
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.protocols.services.runtime.llm import MessageDict
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.protocols_core import LLMStatus, LLMUsageStatistics
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.capabilities import LLMCapabilities
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.llm import ExtractedJSONData, JSONExtractionResult

from .pricing_calculator import LLMPricingCalculator

# Type alias for error context dict used in error handling
ErrorContext = Dict[str, Any]


def _build_ciris_proxy_metadata(
    task_id: Optional[str],
    thought_id: Optional[str],
    retry_state: Dict[str, Any],
    resp_model_name: str,
) -> Dict[str, Any]:
    """Build metadata dict for CIRIS proxy requests.

    Args:
        task_id: Task ID for billing (required for CIRIS proxy)
        thought_id: Optional thought ID for tracing
        retry_state: Dict tracking retry count/error/request_id
        resp_model_name: Name of the response model for logging

    Returns:
        Dict with metadata including interaction_id and retry info

    Raises:
        RuntimeError: If task_id is None (required for billing)
    """
    import hashlib
    import uuid

    if not task_id:
        raise RuntimeError(
            f"BILLING BUG: task_id is required for CIRIS proxy but was None "
            f"(thought_id={thought_id}, model={resp_model_name})"
        )
    interaction_id = hashlib.sha256(task_id.encode()).hexdigest()[:32]

    metadata: Dict[str, Any] = {"interaction_id": interaction_id}

    if retry_state["count"] > 0:
        metadata["retry_count"] = retry_state["count"]
        if retry_state["previous_error"]:
            metadata["previous_error"] = retry_state["previous_error"]
        if retry_state["original_request_id"]:
            metadata["original_request_id"] = retry_state["original_request_id"]
        logger.info(
            f"[LLM_RETRY] attempt={retry_state['count']} "
            f"prev_error={retry_state['previous_error']} "
            f"interaction_id={interaction_id}"
        )
    else:
        retry_state["original_request_id"] = uuid.uuid4().hex[:12]
        metadata["request_id"] = retry_state["original_request_id"]
        logger.info(
            f"[LLM_REQUEST] interaction_id={interaction_id} "
            f"request_id={retry_state['original_request_id']} "
            f"thought_id={thought_id} model={resp_model_name}"
        )

    return metadata


def _build_openrouter_provider_config() -> Dict[str, Any]:
    """Build provider config for OpenRouter requests from environment variables.

    Environment variables:
        OPENROUTER_PROVIDER_ORDER: comma-separated preferred providers
        OPENROUTER_IGNORE_PROVIDERS: comma-separated providers to skip

    Returns:
        Dict with provider ordering/ignore preferences, empty if none configured
    """
    provider_config: Dict[str, Any] = {}

    provider_order = os.environ.get("OPENROUTER_PROVIDER_ORDER", "")
    if provider_order:
        provider_config["order"] = [p.strip() for p in provider_order.split(",") if p.strip()]

    ignore_providers = os.environ.get("OPENROUTER_IGNORE_PROVIDERS", "")
    if ignore_providers:
        provider_config["ignore"] = [p.strip() for p in ignore_providers.split(",") if p.strip()]

    if provider_config:
        logger.info(f"[OPENROUTER] Using provider config: {provider_config}")

    return provider_config


def _log_multimodal_content(
    msg_list: List[MessageDict],
    model_name: str,
    thought_id: Optional[str],
    resp_model_name: str,
) -> int:
    """Log details about multimodal (vision) content in messages.

    Args:
        msg_list: List of message dicts
        model_name: The model being called
        thought_id: Optional thought ID for tracing
        resp_model_name: Name of the response model

    Returns:
        Number of images found in the messages
    """
    image_count = 0
    total_image_bytes = 0

    for msg in msg_list:
        content = msg.get("content", "")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "image_url":
                    image_count += 1
                    url = block.get("image_url", {}).get("url", "")
                    if url.startswith("data:image"):
                        total_image_bytes += len(url)

    if image_count > 0:
        logger.info(
            f"[VISION_DEBUG] Sending to proxy: model={model_name}, "
            f"images={image_count}, image_data_bytes={total_image_bytes}, "
            f"thought_id={thought_id}, response_model={resp_model_name}"
        )

    return image_count


def _handle_instructor_retry_exception(
    error: Exception,
    error_context: ErrorContext,
    circuit_breaker: "CircuitBreaker",
) -> None:
    """Handle InstructorRetryException with detailed error categorization.

    This function categorizes the error, logs appropriate messages, and raises
    the appropriate exception type. It always raises an exception.

    Args:
        error: The InstructorRetryException
        error_context: Dict with model, provider, response_model, etc.
        circuit_breaker: The circuit breaker instance for recording failures

    Raises:
        RuntimeError: For most error types
        TimeoutError: For timeout errors
    """
    error_str = str(error).lower()
    full_error = str(error)

    # Check for rate limit first - DON'T record as circuit breaker failure
    is_rate_limit = (
        ERROR_PATTERN_RATE_LIMIT in error_str
        or ERROR_PATTERN_429 in error_str
        or ERROR_PATTERN_RATE_LIMIT_UNDERSCORE in error_str
    )

    if not is_rate_limit:
        circuit_breaker.record_failure()

    # Schema validation errors
    if _is_validation_error(error_str):
        _log_instructor_error(
            "SCHEMA VALIDATION", error_context, full_error, extra=f"Expected Schema: {error_context['response_model']}"
        )
        raise RuntimeError(
            f"LLM response validation failed for {error_context['response_model']} - "
            "circuit breaker activated for failover"
        ) from error

    # Timeout errors
    if _is_timeout_error(error_str):
        _log_instructor_error("TIMEOUT", error_context, full_error, extra="Request exceeded timeout")
        raise TimeoutError("LLM API timeout - circuit breaker activated") from error

    # Service unavailable / 503 errors
    if _is_service_unavailable_error(error_str):
        _log_instructor_error("SERVICE UNAVAILABLE (503)", error_context, full_error)
        raise RuntimeError("LLM service unavailable (503) - circuit breaker activated for failover") from error

    # Rate limit / 429 errors
    if is_rate_limit:
        logger.warning(
            f"LLM RATE LIMIT (429) - Provider quota exceeded (NOT counting as CB failure).\n"
            f"  Model: {error_context['model']}\n"
            f"  Provider: {error_context['provider']}\n"
            f"  CB State: {error_context['circuit_breaker_state']} "
            f"(not incrementing - rate limits are transient)\n"
            f"  Error: {full_error[:300]}"
        )
        raise RuntimeError("LLM rate limit exceeded (429) - will be retried by LLM bus") from error

    # Context length / token limit exceeded errors
    if _is_context_length_error(error_str):
        _log_instructor_error("CONTEXT_LENGTH_EXCEEDED", error_context, full_error)
        raise RuntimeError("CONTEXT_LENGTH_EXCEEDED: Input too long - reduce message history or context") from error

    # Content filtering / guardrail errors
    if _is_content_filter_error(error_str):
        _log_instructor_error("CONTENT FILTER / GUARDRAIL", error_context, full_error)
        raise RuntimeError("LLM content filter triggered - circuit breaker activated for failover") from error

    # Generic instructor error
    _log_instructor_error("INSTRUCTOR ERROR", error_context, full_error, extra=f"Error Type: {type(error).__name__}")
    raise RuntimeError("LLM API call failed - circuit breaker activated for failover") from error


def _is_context_length_error(error_str: str) -> bool:
    """Check if error string indicates a context length exceeded error."""
    context_patterns = ["context_length", "maximum context", "context length", "token limit", "too many tokens"]
    if any(pattern in error_str for pattern in context_patterns):
        return True
    return "max_tokens" in error_str and "exceed" in error_str


def _is_validation_error(error_str: str) -> bool:
    """Check if error string indicates a validation error."""
    return "validation" in error_str or "validationerror" in error_str


def _is_timeout_error(error_str: str) -> bool:
    """Check if error string indicates a timeout error."""
    return "timed out" in error_str or "timeout" in error_str


def _is_service_unavailable_error(error_str: str) -> bool:
    """Check if error string indicates service unavailable (503)."""
    return "service unavailable" in error_str or "503" in error_str


def _is_content_filter_error(error_str: str) -> bool:
    """Check if error string indicates content filtering triggered."""
    filter_patterns = ["content_filter", "content policy", "safety"]
    return any(pattern in error_str for pattern in filter_patterns)


def _log_instructor_error(
    error_type: str,
    error_context: ErrorContext,
    full_error: str,
    extra: Optional[str] = None,
) -> None:
    """Log an instructor error with consistent formatting.

    Args:
        error_type: Type label for the error (e.g., "TIMEOUT", "VALIDATION")
        error_context: Dict with model, provider, response_model, etc.
        full_error: Full error message string
        extra: Optional extra line to include in log
    """
    extra_line = f"\n  {extra}" if extra else ""
    logger.error(
        f"LLM {error_type} - Error occurred.\n"
        f"  Model: {error_context['model']}\n"
        f"  Provider: {error_context['provider']}{extra_line}\n"
        f"  CB State: {error_context['circuit_breaker_state']} "
        f"({error_context['consecutive_failures']} consecutive failures)\n"
        f"  Error: {full_error[:500]}"
    )


def _handle_generic_llm_exception(
    error: Exception,
    model_name: str,
    base_url: str,
    resp_model_name: str,
    circuit_breaker: "CircuitBreaker",
) -> None:
    """Handle generic exceptions not caught by other handlers.

    This function always raises an exception.

    Args:
        error: The exception that was raised
        model_name: The model being called
        base_url: The provider base URL
        resp_model_name: Name of the response model
        circuit_breaker: The circuit breaker instance

    Raises:
        RuntimeError: Always raises with error context
    """
    error_str_lower = str(error).lower()
    is_rate_limit = (
        ERROR_PATTERN_RATE_LIMIT in error_str_lower
        or ERROR_PATTERN_429 in error_str_lower
        or ERROR_PATTERN_RATE_LIMIT_UNDERSCORE in error_str_lower
    )

    if not is_rate_limit:
        circuit_breaker.record_failure()

    error_msg = str(error).strip() if str(error).strip() else f"<{type(error).__name__} with no message>"

    if is_rate_limit:
        logger.warning(
            f"LLM RATE LIMIT (429) - NOT counting as CB failure.\n"
            f"  Model: {model_name}\n"
            f"  Provider: {base_url or 'default'}\n"
            f"  Will be retried by LLM bus. Error: {error_msg[:300]}"
        )
    else:
        logger.error(
            f"LLM UNEXPECTED ERROR - {type(error).__name__}.\n"
            f"  Model: {model_name}\n"
            f"  Provider: {base_url or 'default'}\n"
            f"  Expected Schema: {resp_model_name}\n"
            f"  Error: {error_msg[:500]}"
        )
    raise RuntimeError(f"LLM call failed ({type(error).__name__}): {error_msg[:300]}") from error


# Configuration class for LLM services (supports multiple providers)
class OpenAIConfig(BaseModel):
    """Configuration for LLM services. Supports OpenAI, Anthropic, and Google."""

    api_key: str = Field(default="")
    model_name: str = Field(default="gpt-4o-mini")
    base_url: Optional[str] = Field(default=None)
    instructor_mode: str = Field(default="JSON")
    max_retries: int = Field(default=3)
    timeout_seconds: int = Field(default=5)
    # Provider selection - defaults to openai for backward compatibility
    provider: LLMProvider = Field(default=LLMProvider.OPENAI)

    model_config = ConfigDict(protected_namespaces=())


def _detect_provider_from_env() -> LLMProvider:
    """Detect LLM provider from environment variables.

    Checks LLM_PROVIDER first, then falls back to detecting based on
    which API key is set.
    """
    # Explicit provider setting takes precedence
    provider_env = os.environ.get("LLM_PROVIDER", "").lower()
    if provider_env:
        if provider_env in ("anthropic", "claude"):
            return LLMProvider.ANTHROPIC
        elif provider_env in ("google", "gemini"):
            return LLMProvider.GOOGLE
        elif provider_env == "openai":
            return LLMProvider.OPENAI
        elif provider_env in ("openai_compatible", "openrouter", "groq", "together"):
            return LLMProvider.OPENAI_COMPATIBLE

    # Auto-detect based on which API key is set
    if os.environ.get("ANTHROPIC_API_KEY"):
        return LLMProvider.ANTHROPIC
    if os.environ.get("GOOGLE_API_KEY"):
        return LLMProvider.GOOGLE

    # Default to OpenAI (or OpenAI-compatible if base_url is set)
    if os.environ.get("OPENAI_API_BASE"):
        return LLMProvider.OPENAI_COMPATIBLE
    return LLMProvider.OPENAI


def _get_api_key_for_provider(provider: LLMProvider) -> str:
    """Get the appropriate API key for the given provider."""
    if provider == LLMProvider.ANTHROPIC:
        return os.environ.get("ANTHROPIC_API_KEY", "")
    elif provider == LLMProvider.GOOGLE:
        return os.environ.get("GOOGLE_API_KEY", "")
    else:
        # OpenAI and OpenAI-compatible use OPENAI_API_KEY
        return os.environ.get("OPENAI_API_KEY", "")


logger = logging.getLogger(__name__)

# Error pattern constants (DRY principle)
ERROR_PATTERN_RATE_LIMIT = "rate limit"
ERROR_PATTERN_RATE_LIMIT_UNDERSCORE = "rate_limit"
ERROR_PATTERN_429 = "429"

# Type for structured call functions that can be retried
StructuredCallFunc = Callable[
    [List[MessageDict], Type[BaseModel], int, float], Awaitable[Tuple[BaseModel, ResourceUsage]]
]


class OpenAICompatibleClient(BaseService, LLMServiceProtocol):
    """Client for interacting with OpenAI-compatible APIs with circuit breaker protection."""

    def __init__(
        self,
        *,  # Force keyword-only arguments
        config: Optional[OpenAIConfig] = None,
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        service_name: Optional[str] = None,
        version: str = "1.0.0",
    ) -> None:
        # Set telemetry_service before calling super().__init__
        # because _register_dependencies is called in the base constructor
        self.telemetry_service = telemetry_service

        # Initialize config BEFORE calling super().__init__
        # This ensures openai_config exists when _check_dependencies is called
        if config is None:
            # Use default config - should be injected
            self.openai_config = OpenAIConfig()
        else:
            self.openai_config = config

        # Initialize circuit breaker BEFORE calling super().__init__
        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,  # Open after 5 consecutive failures
            recovery_timeout=60.0,  # Wait 60 seconds before testing recovery
            success_threshold=2,  # Close after 2 successful calls
            timeout_duration=5.0,  # 5 second API timeout
        )
        self.circuit_breaker = CircuitBreaker("llm_service", circuit_config)

        # Initialize base service
        super().__init__(time_service=time_service, service_name=service_name or "llm_service", version=version)

        # CRITICAL: Check if we're in mock LLM mode
        import os
        import sys

        if os.environ.get("MOCK_LLM") or "--mock-llm" in " ".join(sys.argv):
            raise RuntimeError(
                "CRITICAL BUG: OpenAICompatibleClient is being initialized while mock LLM is enabled!\n"
                "This should never happen - the mock LLM module should prevent this initialization.\n"
                "Stack trace will show where this is being called from."
            )

        # Initialize retry configuration
        self.max_retries = min(getattr(self.openai_config, "max_retries", 3), 3)
        self.base_delay = 1.0
        self.max_delay = 30.0
        self.retryable_exceptions = (APIConnectionError, RateLimitError)
        # Note: We can't check for instructor.exceptions.InstructorRetryException at import time
        # because it might not exist. We'll check it at runtime instead.
        self.non_retryable_exceptions = (APIStatusError,)

        api_key = self.openai_config.api_key
        base_url = self.openai_config.base_url
        model_name = self.openai_config.model_name or "gpt-4o-mini"
        provider = getattr(self.openai_config, "provider", LLMProvider.OPENAI)

        # Store provider for later use
        self.provider = provider

        # Require API key - no automatic fallback to mock
        if not api_key:
            provider_name = provider.value if hasattr(provider, "value") else str(provider)
            raise RuntimeError(
                f"No API key found for {provider_name}. Please set the appropriate API key environment variable."
            )

        # Initialize client based on provider
        self.model_name = model_name
        timeout = self.openai_config.timeout_seconds

        try:
            self._initialize_provider_client(provider, api_key, base_url, model_name, timeout)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize {provider.value} client: {e}")

    def _initialize_provider_client(
        self, provider: LLMProvider, api_key: str, base_url: Optional[str], model_name: str, timeout: int
    ) -> None:
        """Initialize the appropriate client based on provider.

        Args:
            provider: The LLM provider to use
            api_key: API key for authentication
            base_url: Optional base URL override
            model_name: Model name/identifier
            timeout: Request timeout in seconds
        """
        instructor_mode = getattr(self.openai_config, "instructor_mode", "json").lower()

        if provider == LLMProvider.ANTHROPIC:
            self._init_anthropic_client(api_key, model_name, timeout)
        elif provider == LLMProvider.GOOGLE:
            self._init_google_client(api_key, model_name, timeout)
        else:
            # OpenAI or OpenAI-compatible providers
            self._init_openai_client(api_key, base_url, model_name, timeout, instructor_mode)

    def _init_openai_client(
        self, api_key: str, base_url: Optional[str], model_name: str, timeout: int, instructor_mode: str
    ) -> None:
        """Initialize OpenAI or OpenAI-compatible client."""
        max_retries = 0  # Disable OpenAI client retries - we handle our own
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)

        mode_map = {
            "json": instructor.Mode.JSON,
            "tools": instructor.Mode.TOOLS,
            "md_json": instructor.Mode.MD_JSON,
        }
        selected_mode = mode_map.get(instructor_mode, instructor.Mode.JSON)
        self.instruct_client = instructor.from_openai(self.client, mode=selected_mode)
        logger.info(f"Initialized OpenAI client with model={model_name}, mode={selected_mode}")

    def _init_anthropic_client(self, api_key: str, model_name: str, timeout: int) -> None:
        """Initialize native Anthropic client for Claude models.

        Falls back to OpenAI-compatible mode if SDK not available (e.g., on mobile).
        """
        try:
            import anthropic
        except ImportError:
            # Fall back to OpenAI-compatible mode (e.g., via OpenRouter)
            # This happens on mobile where native SDK has unsupported dependencies
            logger.warning(
                "Anthropic SDK not available - falling back to OpenAI-compatible mode. "
                "For native Anthropic support, install: pip install anthropic"
            )
            # Use OpenAI client with OpenRouter base URL for Claude access
            base_url = os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
            self._init_openai_client(api_key, base_url, model_name, timeout, "json")
            return

        # Create async Anthropic client
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)

        # Use instructor with Anthropic - ANTHROPIC_TOOLS mode for best results
        self.instruct_client = instructor.from_anthropic(self.client, mode=instructor.Mode.ANTHROPIC_TOOLS)
        logger.info(f"Initialized native Anthropic client with model={model_name}")

    def _init_google_client(self, api_key: str, model_name: str, timeout: int) -> None:
        """Initialize native Google client for Gemini models.

        Falls back to OpenAI-compatible mode if SDK not available (e.g., on mobile).
        """
        try:
            import google.generativeai as genai
        except ImportError:
            # Fall back to OpenAI-compatible mode (e.g., via OpenRouter)
            # This happens on mobile where native SDK may have unsupported dependencies
            logger.warning(
                "Google Generative AI SDK not available - falling back to OpenAI-compatible mode. "
                "For native Google support, install: pip install google-generativeai"
            )
            # Use OpenAI client with OpenRouter base URL for Gemini access
            base_url = os.environ.get("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
            self._init_openai_client(api_key, base_url, model_name, timeout, "json")
            return

        # Configure Google API
        genai.configure(api_key=api_key)

        # Use instructor's from_provider for Google with async support
        # Format: "google/model-name"
        provider_string = f"google/{model_name}"
        self.instruct_client = instructor.from_provider(
            provider_string,
            async_client=True,
        )
        # Store a reference to the genai module for potential direct access
        self.client = genai
        logger.info(f"Initialized native Google Gemini client with model={model_name}")

        # Metrics tracking (no caching - we never cache LLM responses)
        self._response_times: List[float] = []  # List of response times in ms
        self._max_response_history = 100  # Keep last 100 response times
        self._total_api_calls = 0
        self._successful_api_calls = 0

        # LLM-specific metrics tracking for v1.4.3 telemetry
        self._total_requests = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_cents = 0.0
        self._total_errors = 0

        # Initialize pricing calculator for accurate cost and impact calculation
        self.pricing_calculator = LLMPricingCalculator()

    # Required BaseService abstract methods

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.LLM

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [LLMCapabilities.CALL_LLM_STRUCTURED.value]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        # LLM service requires API key and circuit breaker to be functional
        has_api_key = bool(self.openai_config.api_key)
        circuit_breaker_ready = self.circuit_breaker is not None
        return has_api_key and circuit_breaker_ready

    # Override optional BaseService methods

    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        if self.telemetry_service:
            self._dependencies.add("TelemetryService")

    async def _on_start(self) -> None:
        """Custom startup logic for LLM service."""
        logger.info(f"OpenAI Compatible LLM Service started with model: {self.model_name}")
        logger.info(f"Circuit breaker initialized: {self.circuit_breaker.get_stats()}")

    async def _on_stop(self) -> None:
        """Custom cleanup logic for LLM service."""
        await self.client.close()
        logger.info("OpenAI Compatible LLM Service stopped")

    def update_api_key(self, new_api_key: str) -> None:
        """Update the API key and reset circuit breaker.

        Called when Android TokenRefreshManager provides a fresh Google ID token.
        This is critical for ciris.ai proxy authentication which uses JWT tokens
        that expire after ~1 hour.
        """
        if not new_api_key:
            logger.warning("[LLM_TOKEN] Attempted to update with empty API key - ignoring")
            return

        old_key_preview = self.openai_config.api_key[:20] + "..." if self.openai_config.api_key else "None"
        new_key_preview = new_api_key[:20] + "..."

        # Update config
        self.openai_config.api_key = new_api_key

        # Update the OpenAI client's API key
        # The AsyncOpenAI client stores the key and uses it for all requests
        self.client.api_key = new_api_key

        # Also update instructor client if it has a reference to the key
        if hasattr(self.instruct_client, "client") and hasattr(self.instruct_client.client, "api_key"):
            self.instruct_client.client.api_key = new_api_key

        # Reset circuit breaker to allow immediate retry
        self.circuit_breaker.reset()

        logger.info(
            "[LLM_TOKEN] API key updated and circuit breaker reset:\n"
            "  Old key: %s\n"
            "  New key: %s\n"
            "  Circuit breaker state: %s",
            old_key_preview,
            new_key_preview,
            self.circuit_breaker.get_stats().get("state", "unknown"),
        )

    async def handle_token_refreshed(self, signal: str, resource: str) -> None:
        """Handle token_refreshed signal from ResourceMonitor.

        Called when Android's TokenRefreshManager has updated .env with a fresh
        Google ID token and the ResourceMonitor has reloaded environment variables.

        This is the signal handler registered with ResourceMonitor.signal_bus.

        Args:
            signal: The signal name ("token_refreshed")
            resource: The resource that was refreshed ("openai_api_key")
        """
        logger.info("[LLM_TOKEN] Received token_refreshed signal: %s for %s", signal, resource)

        # Read fresh API key from environment
        new_api_key = os.environ.get("OPENAI_API_KEY", "")

        if not new_api_key:
            logger.warning("[LLM_TOKEN] No OPENAI_API_KEY found in environment after refresh")
            return

        # Check if key actually changed
        if new_api_key == self.openai_config.api_key:
            logger.info("[LLM_TOKEN] API key unchanged after refresh - just resetting circuit breaker")
            self.circuit_breaker.reset()
            return

        # Update the key
        self.update_api_key(new_api_key)
        logger.info("[LLM_TOKEN] Token refresh complete - LLM service ready for requests")

    def _get_client(self) -> AsyncOpenAI:
        """Return the OpenAI client instance (private method)."""
        return self.client

    async def is_healthy(self) -> bool:
        """Check if service is healthy - used by buses and registries."""
        # Call parent class health check first
        base_healthy = await super().is_healthy()
        # Also check circuit breaker status
        return base_healthy and self.circuit_breaker.is_available()

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get base capabilities
        capabilities = super().get_capabilities()

        # Add custom metadata using model_copy
        if capabilities.metadata:
            capabilities.metadata = capabilities.metadata.model_copy(
                update={
                    "model": self.model_name,
                    "instructor_mode": getattr(self.openai_config, "instructor_mode", "JSON"),
                    "timeout_seconds": getattr(self.openai_config, "timeout_seconds", 30),
                    "max_retries": self.max_retries,
                    "circuit_breaker_state": self.circuit_breaker.get_stats().get("state", "unknown"),
                }
            )

        return capabilities

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect service-specific metrics."""
        cb_stats = self.circuit_breaker.get_stats()

        # Calculate average response time
        avg_response_time_ms = 0.0
        if self._response_times:
            avg_response_time_ms = sum(self._response_times) / len(self._response_times)

        # Calculate API success rate
        api_success_rate = 0.0
        if self._total_api_calls > 0:
            api_success_rate = self._successful_api_calls / self._total_api_calls

        # Build custom metrics
        metrics = {
            # Circuit breaker metrics
            "circuit_breaker_state": (
                1.0 if cb_stats.get("state") == "open" else (0.5 if cb_stats.get("state") == "half_open" else 0.0)
            ),
            "consecutive_failures": float(cb_stats.get("consecutive_failures", 0)),
            "recovery_attempts": float(cb_stats.get("recovery_attempts", 0)),
            "last_failure_age_seconds": float(cb_stats.get("last_failure_age", 0)),
            "success_rate": cb_stats.get("success_rate", 1.0),
            "call_count": float(cb_stats.get("call_count", 0)),
            "failure_count": float(cb_stats.get("failure_count", 0)),
            # Performance metrics (no caching)
            "avg_response_time_ms": avg_response_time_ms,
            "max_response_time_ms": max(self._response_times) if self._response_times else 0.0,
            "min_response_time_ms": min(self._response_times) if self._response_times else 0.0,
            "total_api_calls": float(self._total_api_calls),
            "successful_api_calls": float(self._successful_api_calls),
            "api_success_rate": api_success_rate,
            # Model pricing info
            "model_cost_per_1k_tokens": 0.15 if "gpt-4o-mini" in self.model_name else 2.5,  # Cents
            "retry_delay_base": self.base_delay,
            "retry_delay_max": self.max_delay,
            # Model configuration
            "model_timeout_seconds": float(getattr(self.openai_config, "timeout_seconds", 30)),
            "model_max_retries": float(self.max_retries),
        }

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all LLM metrics including base, custom, and v1.4.3 specific metrics.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        # Add v1.4.3 specific LLM metrics
        metrics.update(
            {
                "llm_requests_total": float(self._total_requests),
                "llm_tokens_input": float(self._total_input_tokens),
                "llm_tokens_output": float(self._total_output_tokens),
                "llm_tokens_total": float(self._total_input_tokens + self._total_output_tokens),
                "llm_cost_cents": self._total_cost_cents,
                "llm_errors_total": float(self._total_errors),
                "llm_uptime_seconds": self._calculate_uptime(),
            }
        )

        return metrics

    def _extract_json_from_response(self, raw: str) -> JSONExtractionResult:
        """Extract and parse JSON from LLM response (private method)."""
        return self._extract_json(raw)

    @classmethod
    def _extract_json(cls, raw: str) -> JSONExtractionResult:
        """Extract and parse JSON from LLM response (private method)."""
        json_pattern = r"```json\s*(\{.*?\})\s*```"
        match = re.search(json_pattern, raw, re.DOTALL)

        if match:
            json_str = match.group(1)
        else:
            json_str = raw.strip()
        try:
            parsed = json.loads(json_str)
            return JSONExtractionResult(success=True, data=ExtractedJSONData(**parsed))
        except json.JSONDecodeError:
            try:
                parsed_retry = json.loads(json_str.replace("'", '"'))
                return JSONExtractionResult(success=True, data=ExtractedJSONData(**parsed_retry))
            except json.JSONDecodeError:
                return JSONExtractionResult(
                    success=False, error="Failed to parse JSON", raw_content=raw[:200]  # First 200 chars
                )

    async def call_llm_structured(
        self,
        messages: List[MessageDict],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        thought_id: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Make a structured LLM call with circuit breaker protection.

        Args:
            messages: List of message dicts for the LLM
            response_model: Pydantic model for structured response
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            thought_id: Optional thought ID for tracing (last 8 chars used)
            task_id: Optional task ID for tracing (last 8 chars used)
        """
        self._track_request()
        self._total_requests += 1
        logger.debug(f"Structured LLM call for {response_model.__name__}")
        self.circuit_breaker.check_and_raise()

        retry_state: Dict[str, Any] = {"count": 0, "previous_error": None, "original_request_id": None}

        async def _make_structured_call(
            msg_list: List[MessageDict],
            resp_model: Type[BaseModel],
            max_toks: int,
            temp: float,
        ) -> Tuple[BaseModel, ResourceUsage]:
            try:
                extra_kwargs = self._build_extra_kwargs(task_id, thought_id, resp_model.__name__, retry_state)
                image_count = _log_multimodal_content(msg_list, self.model_name, thought_id, resp_model.__name__)

                response, completion = await self.instruct_client.chat.completions.create_with_completion(
                    model=self.model_name,
                    messages=cast(Any, msg_list),
                    response_model=resp_model,
                    max_retries=0,
                    max_tokens=max_toks,
                    temperature=temp,
                    **extra_kwargs,
                )

                self._log_completion_details(completion, image_count, thought_id)
                return await self._process_successful_response(response, completion)

            except AuthenticationError as e:
                self._handle_auth_error(e)
                raise

            except (APIConnectionError, RateLimitError, InternalServerError) as e:
                self._handle_provider_error(e)
                raise

            except Exception as e:
                self._handle_general_exception(e, resp_model.__name__)
                raise  # Should not reach here as _handle_general_exception always raises

        try:
            return await self._retry_with_backoff(
                _make_structured_call, messages, response_model, max_tokens, temperature, retry_state=retry_state
            )
        except CircuitBreakerError:
            logger.warning("LLM service circuit breaker is open, failing fast")
            raise
        except TimeoutError:
            logger.warning("LLM structured service timeout, failing fast to prevent retry cascade")
            raise

    def _build_extra_kwargs(
        self,
        task_id: Optional[str],
        thought_id: Optional[str],
        resp_model_name: str,
        retry_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build extra kwargs for the LLM API call based on provider."""
        extra_kwargs: Dict[str, Any] = {}
        base_url = self.openai_config.base_url or ""

        if "ciris.ai" in base_url or "ciris-services" in base_url:
            metadata = _build_ciris_proxy_metadata(task_id, thought_id, retry_state, resp_model_name)
            extra_kwargs["extra_body"] = {"metadata": metadata}
        elif "openrouter.ai" in base_url:
            provider_config = _build_openrouter_provider_config()
            if provider_config:
                extra_kwargs["extra_body"] = {"provider": provider_config}

        return extra_kwargs

    def _log_completion_details(self, completion: Any, image_count: int, thought_id: Optional[str]) -> None:
        """Log completion details for debugging."""
        if image_count > 0:
            actual_model = getattr(completion, "model", "unknown")
            logger.info(
                f"[VISION_DEBUG] Proxy response: requested={self.model_name}, "
                f"actual_model={actual_model}, thought_id={thought_id}"
            )

        provider_name = getattr(completion, "provider", None)
        base_url = self.openai_config.base_url or ""
        if provider_name and "openrouter.ai" in base_url:
            logger.info(f"[OPENROUTER] SUCCESS - Provider: {provider_name}, Model: {self.model_name}")

    async def _process_successful_response(
        self, response: BaseModel, completion: Any
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Process a successful LLM response and return usage data."""
        usage = completion.usage
        self.circuit_breaker.record_success()

        prompt_tokens = getattr(usage, "prompt_tokens", 0)
        completion_tokens = getattr(usage, "completion_tokens", 0)

        usage_obj = self.pricing_calculator.calculate_cost_and_impact(
            model_name=self.model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider_name="openai",
        )

        self._total_input_tokens += prompt_tokens
        self._total_output_tokens += completion_tokens
        self._total_cost_cents += usage_obj.cost_cents

        # Record token usage in telemetry
        if self.telemetry_service and usage_obj.tokens_used > 0:
            await self.telemetry_service.record_metric("llm_tokens_used", usage_obj.tokens_used)
            await self.telemetry_service.record_metric("llm_api_call_structured")

        return response, usage_obj

    def _handle_auth_error(self, e: AuthenticationError) -> None:
        """Handle authentication errors (401)."""
        self._track_error(e)
        self._total_errors += 1
        base_url = self.openai_config.base_url or ""

        if "ciris.ai" in base_url:
            self.circuit_breaker.force_open(reason="ciris.ai 401 - billing or token error")
            logger.error(
                f"LLM AUTHENTICATION ERROR (401) - ciris.ai billing or token error.\n"
                f"  Model: {self.model_name}\n"
                f"  Provider: {base_url}\n"
                f"  Circuit breaker forced open immediately.\n"
                f"  Writing token refresh signal..."
            )
            self._signal_token_refresh_needed()
        else:
            self.circuit_breaker.record_failure()
            logger.error(
                f"LLM AUTHENTICATION ERROR (401) - Invalid API key.\n"
                f"  Model: {self.model_name}\n"
                f"  Provider: {base_url}\n"
                f"  Error: {e}"
            )

    def _handle_provider_error(self, e: Exception) -> None:
        """Handle provider-specific errors (connection, rate limit, internal server)."""
        self._track_error(e)
        self._total_errors += 1

        error_details = {
            "error_type": type(e).__name__,
            "model": self.model_name,
            "base_url": self.openai_config.base_url or "default",
            "circuit_breaker_state": self.circuit_breaker.state.value,
        }

        if isinstance(e, RateLimitError):
            logger.warning(
                f"LLM RATE LIMIT (429) - NOT counting as CB failure. Provider: {error_details['base_url']}, "
                f"Model: {error_details['model']}. Will be retried by LLM bus. Error: {e}"
            )
        elif isinstance(e, InternalServerError):
            self._handle_internal_server_error(e, error_details)
        elif isinstance(e, APIConnectionError):
            logger.error(
                f"LLM CONNECTION ERROR - Provider: {error_details['base_url']}, "
                f"Model: {error_details['model']}, CB State: {error_details['circuit_breaker_state']}. "
                f"Failed to connect to provider: {e}"
            )
        else:
            logger.error(
                f"LLM API ERROR ({error_details['error_type']}) - Provider: {error_details['base_url']}, "
                f"Model: {error_details['model']}, CB State: {error_details['circuit_breaker_state']}. "
                f"Error: {e}"
            )

    def _handle_internal_server_error(self, e: InternalServerError, error_details: Dict[str, Any]) -> None:
        """Handle internal server errors, including billing errors."""
        error_str = str(e).lower()

        if "billing service error" in error_str or "billing error" in error_str:
            from ciris_engine.logic.adapters.base_observer import BillingServiceError

            self.circuit_breaker.force_open(reason="Billing service error")
            logger.error(
                f"LLM BILLING ERROR - Provider: {error_details['base_url']}, "
                f"Model: {error_details['model']}. Billing service returned error: {e}"
            )
            raise BillingServiceError(
                message=f"LLM billing service error. Please check your account status or try again later. Details: {e}",
                status_code=402,
            ) from e
        else:
            logger.error(
                f"LLM PROVIDER ERROR (500) - Provider: {error_details['base_url']}, "
                f"Model: {error_details['model']}, CB State: {error_details['circuit_breaker_state']}. "
                f"Provider returned internal server error: {e}"
            )

    def _handle_general_exception(self, e: Exception, resp_model_name: str) -> None:
        """Handle general exceptions including instructor retry exceptions."""
        # Check if this is an instructor retry exception
        if hasattr(instructor, "exceptions") and hasattr(instructor.exceptions, "InstructorRetryException"):
            if isinstance(e, instructor.exceptions.InstructorRetryException):
                self._track_error(e)
                self._total_errors += 1
                error_context: ErrorContext = {
                    "model": self.model_name,
                    "provider": self.openai_config.base_url or "default",
                    "response_model": resp_model_name,
                    "circuit_breaker_state": self.circuit_breaker.state.value,
                    "consecutive_failures": self.circuit_breaker.consecutive_failures,
                }
                _handle_instructor_retry_exception(e, error_context, self.circuit_breaker)

        # Generic exception handling
        self._track_error(e)
        self._total_errors += 1
        _handle_generic_llm_exception(
            e, self.model_name, self.openai_config.base_url or "", resp_model_name, self.circuit_breaker
        )

    def _get_status(self) -> LLMStatus:
        """Get detailed status including circuit breaker metrics (private method)."""
        # Get circuit breaker stats
        cb_stats = self.circuit_breaker.get_stats()

        # Calculate average response time if we have metrics
        avg_response_time = None
        if hasattr(self, "_response_times") and self._response_times:
            avg_response_time = sum(self._response_times) / len(self._response_times)

        return LLMStatus(
            available=self.circuit_breaker.is_available(),
            model=self.model_name,
            usage=LLMUsageStatistics(
                total_calls=cb_stats.get("call_count", 0),
                failed_calls=cb_stats.get("failure_count", 0),
                success_rate=cb_stats.get("success_rate", 1.0),
            ),
            rate_limit_remaining=None,  # Would need to track from API responses
            response_time_avg=avg_response_time,
        )

    async def _retry_with_backoff(
        self,
        func: StructuredCallFunc,
        messages: List[MessageDict],
        response_model: Type[BaseModel],
        max_tokens: int,
        temperature: float,
        retry_state: Optional[Dict[str, Any]] = None,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Retry with exponential backoff (private method).

        Args:
            func: The callable to retry
            messages: LLM messages
            response_model: Pydantic response model
            max_tokens: Max tokens
            temperature: Temperature
            retry_state: Optional dict to track retry info for CIRIS proxy metadata
                         {"count": int, "previous_error": str, "original_request_id": str}
        """
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return await func(messages, response_model, max_tokens, temperature)
            except self.retryable_exceptions as e:
                last_exception = e

                # Categorize error for retry metadata
                error_category = self._categorize_llm_error(e)

                # Update retry state for next attempt's metadata
                if retry_state is not None:
                    retry_state["count"] = attempt + 1
                    retry_state["previous_error"] = error_category

                if attempt < self.max_retries - 1:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    logger.warning(
                        f"[LLM_RETRY_SCHEDULED] attempt={attempt + 1}/{self.max_retries} "
                        f"error={error_category} delay={delay:.1f}s"
                    )
                    import asyncio

                    await asyncio.sleep(delay)
                    continue
                raise
            except self.non_retryable_exceptions:
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Retry logic failed without exception")

    @staticmethod
    def _categorize_llm_error(error: Exception) -> str:
        """Categorize an LLM error for retry metadata.

        Returns error category string for proxy correlation:
        - TIMEOUT: Request timed out
        - CONNECTION_ERROR: Could not connect
        - RATE_LIMIT: Rate limit exceeded (429)
        - CONTEXT_LENGTH_EXCEEDED: Input too long (400)
        - VALIDATION_ERROR: Response didn't match schema
        - AUTH_ERROR: Authentication failed (401)
        - INTERNAL_ERROR: Provider error (500/503)
        - UNKNOWN: Unrecognized error
        """
        error_str = str(error).lower()

        # Check for timeout errors
        if "timeout" in error_str or "timed out" in error_str:
            return "TIMEOUT"

        # Check for connection errors
        if isinstance(error, APIConnectionError):
            if "timeout" in error_str:
                return "TIMEOUT"
            return "CONNECTION_ERROR"

        # Check for rate limit
        if isinstance(error, RateLimitError) or ERROR_PATTERN_RATE_LIMIT in error_str or ERROR_PATTERN_429 in error_str:
            return "RATE_LIMIT"

        # Check for context length exceeded
        if (
            "context_length" in error_str
            or "maximum context" in error_str
            or "context length" in error_str
            or "token limit" in error_str
            or "too many tokens" in error_str
        ):
            return "CONTEXT_LENGTH_EXCEEDED"

        # Check for validation errors
        if "validation" in error_str or "validationerror" in error_str:
            return "VALIDATION_ERROR"

        # Check for auth errors
        if isinstance(error, AuthenticationError) or "401" in error_str or "unauthorized" in error_str:
            return "AUTH_ERROR"

        # Check for server errors
        if isinstance(error, InternalServerError) or "500" in error_str or "503" in error_str:
            return "INTERNAL_ERROR"

        return "UNKNOWN"

    def _signal_token_refresh_needed(self) -> None:
        """Write a signal file to indicate token refresh is needed (for ciris.ai).

        This file is monitored by the Android app to trigger Google silentSignIn().
        The signal file is written to CIRIS_HOME/.token_refresh_needed
        """
        import os
        from pathlib import Path

        try:
            # Get CIRIS_HOME from environment (set by mobile_main.py on Android)
            ciris_home = os.getenv("CIRIS_HOME")
            if not ciris_home:
                # Fallback for non-Android environments
                from ciris_engine.logic.utils.path_resolution import get_ciris_home

                ciris_home = str(get_ciris_home())

            signal_file = Path(ciris_home) / ".token_refresh_needed"
            signal_file.write_text(str(time.time()))
            logger.info(f"Token refresh signal written to: {signal_file}")
        except Exception as e:
            logger.error(f"Failed to write token refresh signal: {e}")
