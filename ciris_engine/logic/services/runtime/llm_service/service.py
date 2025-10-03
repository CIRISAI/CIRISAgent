"""OpenAI Compatible LLM Service with Circuit Breaker Integration."""

import json
import logging
import re
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple, Type, cast

import instructor
from openai import APIConnectionError, APIStatusError, AsyncOpenAI, InternalServerError, RateLimitError
from pydantic import BaseModel, Field

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
    timeout_seconds: int = Field(default=30)


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
            recovery_timeout=10.0,  # Wait 10 seconds before testing recovery
            success_threshold=2,  # Close after 2 successful calls
            timeout_duration=30.0,  # 30 second API timeout
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
        timeout = getattr(self.openai_config, "timeout", 30.0)  # Shorter default timeout
        max_retries = 0  # Disable OpenAI client retries - we handle our own

        try:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=max_retries)

            instructor_mode = getattr(self.openai_config, "instructor_mode", "json")
            self.instruct_client = instructor.from_openai(
                self.client, mode=instructor.Mode.JSON if instructor_mode.lower() == "json" else instructor.Mode.TOOLS
            )
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

        # Add custom metadata
        if capabilities.metadata:
            capabilities.metadata.update(
                {
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
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Make a structured LLM call with circuit breaker protection."""
        # Track the request
        self._track_request()
        # Track LLM-specific request
        self._total_requests += 1

        # No mock service integration - LLMService and MockLLMService are separate
        logger.debug(f"Structured LLM call for {response_model.__name__}")

        # Check circuit breaker before making call
        self.circuit_breaker.check_and_raise()

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
                response, completion = await self.instruct_client.chat.completions.create_with_completion(
                    model=self.model_name,
                    messages=cast(Any, msg_list),
                    response_model=resp_model,
                    max_retries=0,  # Disable instructor retries completely
                    max_tokens=max_toks,
                    temperature=temp,
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

            except (APIConnectionError, RateLimitError, InternalServerError) as e:
                # Record failure with circuit breaker
                self.circuit_breaker.record_failure()
                # Track error in base service
                self._track_error(e)
                # Track LLM-specific error
                self._total_errors += 1
                logger.warning(f"LLM structured API error recorded by circuit breaker: {e}")
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

                        # Provide specific error messages for different failure types
                        error_str = str(e).lower()
                        if "timed out" in error_str:
                            logger.error(f"LLM structured timeout detected, circuit breaker recorded failure: {e}")
                            raise TimeoutError("LLM API timeout in structured call - circuit breaker activated") from e
                        elif "service unavailable" in error_str or "503" in error_str:
                            logger.error(f"LLM service unavailable (503), circuit breaker recorded failure: {e}")
                            raise RuntimeError(
                                "LLM service unavailable - circuit breaker activated for failover"
                            ) from e
                        else:
                            logger.error(f"LLM structured call failed, circuit breaker recorded failure: {e}")
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
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Retry with exponential backoff (private method)."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return await func(messages, response_model, max_tokens, temperature)
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = min(self.base_delay * (2**attempt), self.max_delay)
                    import asyncio

                    await asyncio.sleep(delay)
                    continue
                raise
            except self.non_retryable_exceptions:
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Retry logic failed without exception")
