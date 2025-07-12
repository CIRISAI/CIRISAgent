"""OpenAI Compatible LLM Service with Circuit Breaker Integration."""

import json
import re
import logging
import psutil
from typing import List, Optional, Tuple, Type, cast, Dict, Any, Callable, Awaitable

from pydantic import BaseModel, Field
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError, InternalServerError
import instructor

from ciris_engine.protocols.services import LLMService as LLMServiceProtocol
from ciris_engine.protocols.services.runtime.llm import MessageDict
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.runtime.protocols_core import LLMStatus
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.llm import JSONExtractionResult
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.capabilities import LLMCapabilities
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError
from ciris_engine.logic.services.base_service import BaseService

# Configuration class for OpenAI-compatible LLM services
class OpenAIConfig(BaseModel):
    api_key: str = Field(default="")
    model_name: str = Field(default="gpt-4o-mini")
    base_url: Optional[str] = Field(default=None)
    instructor_mode: str = Field(default="JSON")
    max_retries: int = Field(default=3)
    timeout_seconds: int = Field(default=30)

logger = logging.getLogger(__name__)

class OpenAICompatibleClient(BaseService, LLMServiceProtocol):
    """Client for interacting with OpenAI-compatible APIs with circuit breaker protection."""

    def __init__(
        self, 
        *,  # Force keyword-only arguments
        config: Optional[OpenAIConfig] = None, 
        telemetry_service: Optional[TelemetryServiceProtocol] = None,
        time_service: Optional[TimeServiceProtocol] = None,
        service_name: Optional[str] = None,
        version: str = "1.0.0"
    ) -> None:
        # Set telemetry_service before calling super().__init__
        # because _register_dependencies is called in the base constructor
        self.telemetry_service = telemetry_service
        
        # Initialize base service
        super().__init__(
            time_service=time_service,
            service_name=service_name or "llm_service",
            version=version
        )
        
        # CRITICAL: Check if we're in mock LLM mode
        import os
        import sys
        if os.environ.get('MOCK_LLM') or '--mock-llm' in ' '.join(sys.argv):
            raise RuntimeError(
                "CRITICAL BUG: OpenAICompatibleClient is being initialized while mock LLM is enabled!\n"
                "This should never happen - the mock LLM module should prevent this initialization.\n"
                "Stack trace will show where this is being called from."
            )
        
        if config is None:
            # Use default config - should be injected
            self.openai_config = OpenAIConfig()
        else:
            self.openai_config = config

        # Initialize retry configuration
        self.max_retries = min(getattr(self.openai_config, 'max_retries', 3), 3)
        self.base_delay = 1.0
        self.max_delay = 30.0
        self.retryable_exceptions = (APIConnectionError, RateLimitError)
        self.non_retryable_exceptions = (APIStatusError, instructor.exceptions.InstructorRetryException)  # type: ignore[attr-defined]

        circuit_config = CircuitBreakerConfig(
            failure_threshold=5,        # Open after 5 consecutive failures
            recovery_timeout=10.0,      # Wait 10 seconds before testing recovery
            success_threshold=2,        # Close after 2 successful calls
            timeout_duration=30.0       # 30 second API timeout
        )
        self.circuit_breaker = CircuitBreaker("llm_service", circuit_config)

        api_key = self.openai_config.api_key
        base_url = self.openai_config.base_url
        model_name = self.openai_config.model_name or 'gpt-4o-mini'

        # Require API key - no automatic fallback to mock
        if not api_key:
            raise RuntimeError("No OpenAI API key found. Please set OPENAI_API_KEY environment variable.")

        # Initialize OpenAI client
        self.model_name = model_name
        timeout = getattr(self.openai_config, 'timeout', 30.0)  # Shorter default timeout
        max_retries = 0  # Disable OpenAI client retries - we handle our own

        try:
            self.client = AsyncOpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=max_retries
            )

            instructor_mode = getattr(self.openai_config, 'instructor_mode', 'json')
            self.instruct_client = instructor.from_openai(
                self.client,
                mode=instructor.Mode.JSON if instructor_mode.lower() == 'json' else instructor.Mode.TOOLS
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}")
        
        # Memory tracking (process is inherited from BaseService)
        self._response_cache: Dict[str, Any] = {}  # Simple response cache
        self._max_cache_size = 100  # Maximum cache entries
        
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

    def _get_metadata(self) -> Dict[str, Any]:
        """Get service-specific metadata."""
        return {
            "model": self.model_name,
            "instructor_mode": getattr(self.openai_config, 'instructor_mode', 'JSON'),
            "timeout_seconds": getattr(self.openai_config, 'timeout_seconds', 30),
            "max_retries": self.max_retries,
            "circuit_breaker_state": self.circuit_breaker.get_stats().get("state", "unknown")
        }

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect service-specific metrics."""
        import sys
        
        cb_stats = self.circuit_breaker.get_stats()
        
        # Calculate cache size
        cache_size_mb = 0.0
        try:
            cache_size = sys.getsizeof(self._response_cache)
            cache_size_mb = cache_size / 1024 / 1024
        except Exception:
            pass
        
        # Build custom metrics
        metrics = {
            # Circuit breaker metrics
            "circuit_breaker_state": 1.0 if cb_stats.get("state") == "open" else (0.5 if cb_stats.get("state") == "half_open" else 0.0),
            "consecutive_failures": float(cb_stats.get("consecutive_failures", 0)),
            "recovery_attempts": float(cb_stats.get("recovery_attempts", 0)),
            "last_failure_age_seconds": float(cb_stats.get("last_failure_age", 0)),
            "success_rate": cb_stats.get("success_rate", 1.0),
            "call_count": float(cb_stats.get("call_count", 0)),
            "failure_count": float(cb_stats.get("failure_count", 0)),
            
            # Cache metrics
            "cache_size_mb": cache_size_mb,
            "cache_entries": float(len(self._response_cache)),
            "response_cache_hit_rate": 0.0,  # TODO: Track cache hits
            
            # Performance metrics
            "avg_response_time_ms": 0.0,  # TODO: Track response times
            
            # Model pricing info
            "model_cost_per_1k_tokens": 0.15 if "gpt-4o-mini" in self.model_name else 2.5,  # Cents
            "retry_delay_base": self.base_delay,
            "retry_delay_max": self.max_delay,
            
            # Model configuration
            "model_timeout_seconds": float(getattr(self.openai_config, 'timeout_seconds', 30)),
            "model_max_retries": float(self.max_retries)
        }
        
        return metrics

    def _extract_json_from_response(self, raw: str) -> JSONExtractionResult:
        """Extract and parse JSON from LLM response (private method)."""
        return self._extract_json(raw)

    @classmethod
    def _extract_json(cls, raw: str) -> JSONExtractionResult:
        """Extract and parse JSON from LLM response (private method)."""
        json_pattern = r'```json\s*(\{.*?\})\s*```'
        match = re.search(json_pattern, raw, re.DOTALL)

        if match:
            json_str = match.group(1)
        else:
            if raw.strip().startswith('{') and raw.strip().endswith('}'):
                json_str = raw.strip()
            else:
                json_str = raw.strip()
        try:
            parsed = json.loads(json_str)
            return JSONExtractionResult(
                success=True,
                data=parsed
            )
        except json.JSONDecodeError:
            try:
                parsed_retry = json.loads(json_str.replace("'", '"'))
                return JSONExtractionResult(
                    success=True,
                    data=parsed_retry
                )
            except json.JSONDecodeError:
                return JSONExtractionResult(
                    success=False,
                    error="Failed to parse JSON",
                    raw_content=raw[:200]  # First 200 chars
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
        
        # No mock service integration - LLMService and MockLLMService are separate
        logger.debug(f"Structured LLM call for {response_model.__name__}")

        # Check circuit breaker before making call
        self.circuit_breaker.check_and_raise()

        async def _make_structured_call(
            msg_list: List[dict],
            resp_model: Type[BaseModel],
            max_toks: int,
            temp: float,
        ) -> Tuple[BaseModel, ResourceUsage]:

            try:
                # Use instructor but capture the completion for usage data
                response, completion = await self.instruct_client.chat.completions.create_with_completion(
                    model=self.model_name,
                    messages=cast(List, msg_list),
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
                total_tokens = getattr(usage, "total_tokens", 0)
                prompt_tokens = getattr(usage, "prompt_tokens", 0)
                completion_tokens = getattr(usage, "completion_tokens", 0)

                # Calculate costs based on model
                input_cost_cents = 0.0
                output_cost_cents = 0.0

                if self.model_name.startswith("gpt-4o-mini"):
                    input_cost_cents = (prompt_tokens / 1_000_000) * 15.0  # $0.15 per 1M
                    output_cost_cents = (completion_tokens / 1_000_000) * 60.0  # $0.60 per 1M
                elif self.model_name.startswith("gpt-4o"):
                    input_cost_cents = (prompt_tokens / 1_000_000) * 250.0  # $2.50 per 1M
                    output_cost_cents = (completion_tokens / 1_000_000) * 1000.0  # $10.00 per 1M
                elif self.model_name.startswith("gpt-4-turbo"):
                    input_cost_cents = (prompt_tokens / 1_000_000) * 1000.0  # $10.00 per 1M
                    output_cost_cents = (completion_tokens / 1_000_000) * 3000.0  # $30.00 per 1M
                elif self.model_name.startswith("gpt-3.5-turbo"):
                    input_cost_cents = (prompt_tokens / 1_000_000) * 50.0  # $0.50 per 1M
                    output_cost_cents = (completion_tokens / 1_000_000) * 150.0  # $1.50 per 1M
                elif "llama" in self.model_name.lower() or "Llama" in self.model_name:
                    # Llama models - typically much cheaper or free if self-hosted
                    # Using conservative estimates for cloud-hosted Llama
                    input_cost_cents = (prompt_tokens / 1_000_000) * 10.0  # $0.10 per 1M
                    output_cost_cents = (completion_tokens / 1_000_000) * 10.0  # $0.10 per 1M
                elif "claude" in self.model_name.lower():
                    # Claude models
                    input_cost_cents = (prompt_tokens / 1_000_000) * 300.0  # $3.00 per 1M
                    output_cost_cents = (completion_tokens / 1_000_000) * 1500.0  # $15.00 per 1M
                else:
                    # Default/unknown model - use conservative estimate
                    input_cost_cents = (prompt_tokens / 1_000_000) * 20.0
                    output_cost_cents = (completion_tokens / 1_000_000) * 20.0

                total_cost_cents = input_cost_cents + output_cost_cents

                # Estimate carbon footprint
                # Energy usage varies by model size and hosting
                if "llama" in self.model_name.lower() and "17B" in self.model_name:
                    # Llama 17B model - more efficient than larger models
                    energy_kwh = (total_tokens / 1000) * 0.0002  # Lower energy use
                elif "gpt-4" in self.model_name:
                    # GPT-4 models use more compute
                    energy_kwh = (total_tokens / 1000) * 0.0005
                else:
                    # Default estimate
                    energy_kwh = (total_tokens / 1000) * 0.0003

                carbon_grams = energy_kwh * 500.0  # 500g CO2 per kWh global average

                usage_obj = ResourceUsage(
                    tokens_used=total_tokens,
                    tokens_input=prompt_tokens,
                    tokens_output=completion_tokens,
                    cost_cents=total_cost_cents,
                    carbon_grams=carbon_grams,
                    energy_kwh=energy_kwh,
                    model_used=self.model_name
                )

                # Record token usage in telemetry
                if self.telemetry_service and usage_obj.tokens_used > 0:
                    await self.telemetry_service.record_metric("llm_tokens_used", usage_obj.tokens_used)
                    await self.telemetry_service.record_metric("llm_api_call_structured")

                return response, usage_obj

            except (APIConnectionError, RateLimitError, InternalServerError, instructor.exceptions.InstructorRetryException) as e:  # type: ignore[attr-defined]
                # Record failure with circuit breaker
                self.circuit_breaker.record_failure()
                # Track error in base service
                self._track_error(e)

                # Special handling for timeout cascades
                if isinstance(e, instructor.exceptions.InstructorRetryException) and "timed out" in str(e):  # type: ignore[attr-defined]
                    logger.error(f"LLM structured timeout detected, circuit breaker recorded failure: {e}")
                    raise TimeoutError("LLM API timeout in structured call - circuit breaker activated") from e

                logger.warning(f"LLM structured API error recorded by circuit breaker: {e}")
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
        if hasattr(self, '_response_times') and self._response_times:
            avg_response_time = sum(self._response_times) / len(self._response_times)

        return LLMStatus(
            available=self.circuit_breaker.is_available(),
            model=self.model_name,
            usage={
                "total_calls": cb_stats.get("call_count", 0),
                "failed_calls": cb_stats.get("failure_count", 0),
                "success_rate": cb_stats.get("success_rate", 1.0)
            },
            rate_limit_remaining=None,  # Would need to track from API responses
            response_time_avg=avg_response_time
        )

    async def _retry_with_backoff(
        self,
        func: Callable[..., Awaitable[Tuple[BaseModel, ResourceUsage]]],
        *args: Any,
        **kwargs: Any
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Retry with exponential backoff (private method)."""
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                return await func(*args, **kwargs)
            except self.retryable_exceptions as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    import asyncio
                    await asyncio.sleep(delay)
                    continue
                raise
            except self.non_retryable_exceptions:
                raise

        if last_exception:
            raise last_exception
        raise RuntimeError("Retry logic failed without exception")
