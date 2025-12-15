"""OpenAI Compatible LLM Service with Circuit Breaker Integration."""

import json
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type, cast

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


# Configuration class for OpenAI-compatible LLM services
class OpenAIConfig(BaseModel):
    api_key: str = Field(default="")
    model_name: str = Field(default="gpt-4o-mini")
    base_url: Optional[str] = Field(default=None)
    instructor_mode: str = Field(default="JSON")
    max_retries: int = Field(default=3)
    timeout_seconds: int = Field(default=5)

    model_config = ConfigDict(protected_namespaces=())


logger = logging.getLogger(__name__)

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

        # Require API key - no automatic fallback to mock
        if not api_key:
            raise RuntimeError("No OpenAI API key found. Please set OPENAI_API_KEY environment variable.")

        # Initialize OpenAI client
        self.model_name = model_name
        timeout = self.openai_config.timeout_seconds  # Use the configured timeout value
        max_retries = 0  # Disable OpenAI client retries - we handle our own

        try:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)

            instructor_mode = getattr(self.openai_config, "instructor_mode", "json").lower()
            mode_map = {
                "json": instructor.Mode.JSON,
                "tools": instructor.Mode.TOOLS,
                "md_json": instructor.Mode.MD_JSON,
            }
            selected_mode = mode_map.get(instructor_mode, instructor.Mode.JSON)
            self.instruct_client = instructor.from_openai(self.client, mode=selected_mode)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}")

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
        # Track the request
        self._track_request()
        # Track LLM-specific request
        self._total_requests += 1

        # No mock service integration - LLMService and MockLLMService are separate
        logger.debug(f"Structured LLM call for {response_model.__name__}")

        # Check circuit breaker before making call
        self.circuit_breaker.check_and_raise()

        # Track retry state for metadata
        retry_state: Dict[str, Any] = {"count": 0, "previous_error": None, "original_request_id": None}

        async def _make_structured_call(
            msg_list: List[MessageDict],
            resp_model: Type[BaseModel],
            max_toks: int,
            temp: float,
        ) -> Tuple[BaseModel, ResourceUsage]:

            try:
                # Use instructor but capture the completion for usage data
                # Note: We cast to Any because instructor expects OpenAI-specific message types
                # but we use our own MessageDict protocol for type safety at the service boundary

                # Build extra kwargs for CIRIS proxy (requires interaction_id)
                # NOTE: CIRIS proxy charges per unique interaction_id, so we use task_id only
                # All thoughts within the same task share one credit
                extra_kwargs: Dict[str, Any] = {}
                base_url = self.openai_config.base_url or ""
                if "ciris.ai" in base_url or "ciris-services" in base_url:
                    # Hash task_id for billing (irreversible, same task = same hash = 1 credit)
                    import hashlib
                    import uuid

                    if not task_id:
                        raise RuntimeError(
                            f"BILLING BUG: task_id is required for CIRIS proxy but was None "
                            f"(thought_id={thought_id}, model={resp_model.__name__})"
                        )
                    interaction_id = hashlib.sha256(task_id.encode()).hexdigest()[:32]

                    # Build metadata for CIRIS proxy
                    metadata: Dict[str, Any] = {"interaction_id": interaction_id}

                    # Add retry info if this is a retry attempt
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
                        # First attempt - generate request ID for correlation
                        retry_state["original_request_id"] = uuid.uuid4().hex[:12]
                        metadata["request_id"] = retry_state["original_request_id"]
                        logger.info(
                            f"[LLM_REQUEST] interaction_id={interaction_id} "
                            f"request_id={retry_state['original_request_id']} "
                            f"thought_id={thought_id} model={resp_model.__name__}"
                        )

                    extra_kwargs["extra_body"] = {"metadata": metadata}

                # DEBUG: Log multimodal content details for proxy team diagnostics
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
                        f"[VISION_DEBUG] Sending to proxy: model={self.model_name}, "
                        f"images={image_count}, image_data_bytes={total_image_bytes}, "
                        f"thought_id={thought_id}, response_model={resp_model.__name__}"
                    )

                response, completion = await self.instruct_client.chat.completions.create_with_completion(
                    model=self.model_name,
                    messages=cast(Any, msg_list),
                    response_model=resp_model,
                    max_retries=0,  # Disable instructor retries completely
                    max_tokens=max_toks,
                    temperature=temp,
                    **extra_kwargs,
                )

                # DEBUG: Log proxy response details
                if image_count > 0:
                    actual_model = getattr(completion, "model", "unknown")
                    logger.info(
                        f"[VISION_DEBUG] Proxy response: requested={self.model_name}, "
                        f"actual_model={actual_model}, thought_id={thought_id}"
                    )

                # Extract usage data from completion
                usage = completion.usage

                # Record success with circuit breaker
                self.circuit_breaker.record_success()

                # Extract token counts
                prompt_tokens = getattr(usage, "prompt_tokens", 0)
                completion_tokens = getattr(usage, "completion_tokens", 0)

                # Calculate costs and environmental impact using pricing calculator
                usage_obj = self.pricing_calculator.calculate_cost_and_impact(
                    model_name=self.model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    provider_name="openai",  # Since this is OpenAI-compatible client
                )

                # Track metrics for get_metrics() method
                self._total_input_tokens += prompt_tokens
                self._total_output_tokens += completion_tokens
                self._total_cost_cents += usage_obj.cost_cents

                # Record token usage in telemetry
                if self.telemetry_service and usage_obj.tokens_used > 0:
                    await self.telemetry_service.record_metric("llm_tokens_used", usage_obj.tokens_used)
                    await self.telemetry_service.record_metric("llm_api_call_structured")

                return response, usage_obj

            except AuthenticationError as e:
                # Handle 401 Unauthorized - likely expired token or billing issue for ciris.ai
                self._track_error(e)
                self._total_errors += 1

                base_url = self.openai_config.base_url or ""
                if "ciris.ai" in base_url:
                    # Force circuit breaker open immediately (don't wait for failure threshold)
                    # This prevents burning credits on repeated failures
                    self.circuit_breaker.force_open(reason="ciris.ai 401 - billing or token error")
                    # Write signal file for Android to trigger token refresh
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
                raise

            except (APIConnectionError, RateLimitError, InternalServerError) as e:
                # Record failure with circuit breaker
                self.circuit_breaker.record_failure()
                # Track error in base service
                self._track_error(e)
                # Track LLM-specific error
                self._total_errors += 1

                # Enhanced error logging for provider errors
                error_type = type(e).__name__
                error_details = {
                    "error_type": error_type,
                    "model": self.model_name,
                    "base_url": self.openai_config.base_url or "default",
                    "circuit_breaker_state": self.circuit_breaker.state.value,
                }

                if isinstance(e, RateLimitError):
                    logger.error(
                        f"LLM RATE LIMIT ERROR - Provider: {error_details['base_url']}, "
                        f"Model: {error_details['model']}, CB State: {error_details['circuit_breaker_state']}. "
                        f"Error: {e}"
                    )
                elif isinstance(e, InternalServerError):
                    error_str = str(e).lower()
                    # Check for billing service errors - should be surfaced to user
                    if "billing service error" in error_str or "billing error" in error_str:
                        from ciris_engine.logic.adapters.base_observer import BillingServiceError

                        # Force circuit breaker open - don't retry billing errors
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
                elif isinstance(e, APIConnectionError):
                    logger.error(
                        f"LLM CONNECTION ERROR - Provider: {error_details['base_url']}, "
                        f"Model: {error_details['model']}, CB State: {error_details['circuit_breaker_state']}. "
                        f"Failed to connect to provider: {e}"
                    )
                else:
                    logger.error(
                        f"LLM API ERROR ({error_type}) - Provider: {error_details['base_url']}, "
                        f"Model: {error_details['model']}, CB State: {error_details['circuit_breaker_state']}. "
                        f"Error: {e}"
                    )
                raise
            except Exception as e:
                # Check if this is an instructor retry exception (includes timeouts, 503 errors, rate limits, etc.)
                if hasattr(instructor, "exceptions") and hasattr(instructor.exceptions, "InstructorRetryException"):
                    if isinstance(e, instructor.exceptions.InstructorRetryException):
                        # Record failure for circuit breaker regardless of specific error type
                        self.circuit_breaker.record_failure()
                        self._track_error(e)
                        # Track LLM-specific error
                        self._total_errors += 1

                        # Build error context for better debugging
                        error_context = {
                            "model": self.model_name,
                            "provider": self.openai_config.base_url or "default",
                            "response_model": resp_model.__name__,
                            "circuit_breaker_state": self.circuit_breaker.state.value,
                            "consecutive_failures": self.circuit_breaker.consecutive_failures,
                        }

                        # Provide specific error messages for different failure types
                        error_str = str(e).lower()
                        full_error = str(e)

                        # Check for schema validation errors
                        if "validation" in error_str or "validationerror" in error_str:
                            # Extract validation details
                            logger.error(
                                f"LLM SCHEMA VALIDATION ERROR - Response did not match expected schema.\n"
                                f"  Model: {error_context['model']}\n"
                                f"  Provider: {error_context['provider']}\n"
                                f"  Expected Schema: {error_context['response_model']}\n"
                                f"  CB State: {error_context['circuit_breaker_state']} "
                                f"({error_context['consecutive_failures']} consecutive failures)\n"
                                f"  Validation Details: {full_error[:500]}"
                            )
                            raise RuntimeError(
                                f"LLM response validation failed for {resp_model.__name__} - "
                                "circuit breaker activated for failover"
                            ) from e

                        # Check for timeout errors
                        elif "timed out" in error_str or "timeout" in error_str:
                            logger.error(
                                f"LLM TIMEOUT ERROR - Request exceeded {self.openai_config.timeout_seconds}s timeout.\n"
                                f"  Model: {error_context['model']}\n"
                                f"  Provider: {error_context['provider']}\n"
                                f"  CB State: {error_context['circuit_breaker_state']} "
                                f"({error_context['consecutive_failures']} consecutive failures)\n"
                                f"  Error: {full_error[:300]}"
                            )
                            raise TimeoutError(
                                f"LLM API timeout ({self.openai_config.timeout_seconds}s) "
                                "- circuit breaker activated"
                            ) from e

                        # Check for service unavailable / 503 errors
                        elif "service unavailable" in error_str or "503" in error_str:
                            logger.error(
                                f"LLM SERVICE UNAVAILABLE (503) - Provider temporarily down.\n"
                                f"  Model: {error_context['model']}\n"
                                f"  Provider: {error_context['provider']}\n"
                                f"  CB State: {error_context['circuit_breaker_state']} "
                                f"({error_context['consecutive_failures']} consecutive failures)\n"
                                f"  Error: {full_error[:300]}"
                            )
                            raise RuntimeError(
                                "LLM service unavailable (503) - circuit breaker activated for failover"
                            ) from e

                        # Check for rate limit / 429 errors
                        elif "rate limit" in error_str or "429" in error_str:
                            logger.error(
                                f"LLM RATE LIMIT (429) - Provider quota exceeded.\n"
                                f"  Model: {error_context['model']}\n"
                                f"  Provider: {error_context['provider']}\n"
                                f"  CB State: {error_context['circuit_breaker_state']} "
                                f"({error_context['consecutive_failures']} consecutive failures)\n"
                                f"  Error: {full_error[:300]}"
                            )
                            raise RuntimeError(
                                "LLM rate limit exceeded (429) - circuit breaker activated for failover"
                            ) from e

                        # Check for context length / token limit exceeded errors (400)
                        elif (
                            "context_length" in error_str
                            or "maximum context" in error_str
                            or "context length" in error_str
                            or "token limit" in error_str
                            or "too many tokens" in error_str
                            or "max_tokens" in error_str
                            and "exceed" in error_str
                        ):
                            logger.error(
                                f"LLM CONTEXT_LENGTH_EXCEEDED - Input too long for model.\n"
                                f"  Model: {error_context['model']}\n"
                                f"  Provider: {error_context['provider']}\n"
                                f"  CB State: {error_context['circuit_breaker_state']} "
                                f"({error_context['consecutive_failures']} consecutive failures)\n"
                                f"  Error: {full_error[:500]}"
                            )
                            raise RuntimeError(
                                "CONTEXT_LENGTH_EXCEEDED: Input too long - reduce message history or context"
                            ) from e

                        # Check for content filtering / guardrail errors
                        elif "content_filter" in error_str or "content policy" in error_str or "safety" in error_str:
                            logger.error(
                                f"LLM CONTENT FILTER / GUARDRAIL - Request blocked by provider safety systems.\n"
                                f"  Model: {error_context['model']}\n"
                                f"  Provider: {error_context['provider']}\n"
                                f"  CB State: {error_context['circuit_breaker_state']} "
                                f"({error_context['consecutive_failures']} consecutive failures)\n"
                                f"  Error: {full_error[:300]}"
                            )
                            raise RuntimeError(
                                "LLM content filter triggered - circuit breaker activated for failover"
                            ) from e

                        # Generic instructor error with enhanced logging
                        else:
                            logger.error(
                                f"LLM INSTRUCTOR ERROR - Unspecified failure.\n"
                                f"  Model: {error_context['model']}\n"
                                f"  Provider: {error_context['provider']}\n"
                                f"  Expected Schema: {error_context['response_model']}\n"
                                f"  CB State: {error_context['circuit_breaker_state']} "
                                f"({error_context['consecutive_failures']} consecutive failures)\n"
                                f"  Error Type: {type(e).__name__}\n"
                                f"  Error: {full_error[:500]}"
                            )
                            raise RuntimeError("LLM API call failed - circuit breaker activated for failover") from e
                # Re-raise other exceptions
                raise

        # Implement retry logic with OpenAI-specific error handling
        try:
            return await self._retry_with_backoff(
                _make_structured_call,
                messages,
                response_model,
                max_tokens,
                temperature,
                retry_state=retry_state,  # Pass retry state for CIRIS proxy metadata
            )
        except CircuitBreakerError:
            # Don't retry if circuit breaker is open
            logger.warning("LLM service circuit breaker is open, failing fast")
            raise
        except TimeoutError:
            # Don't retry timeout errors to prevent cascades
            logger.warning("LLM structured service timeout, failing fast to prevent retry cascade")
            raise

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
        if isinstance(error, RateLimitError) or "rate limit" in error_str or "429" in error_str:
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
