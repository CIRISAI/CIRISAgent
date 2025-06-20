"""OpenAI Compatible LLM Service with Circuit Breaker Integration."""

import json
import re
import logging
from typing import Dict, Any, Optional, Type, List, Tuple, Union, cast

from pydantic import BaseModel
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError
import instructor

from ciris_engine.adapters.base import Service
from ciris_engine.protocols.services import LLMService
from ciris_engine.config.config_manager import get_config
from ciris_engine.schemas.config_schemas_v1 import OpenAIConfig, LLMServicesConfig
from ciris_engine.schemas.foundational_schemas_v1 import ResourceUsage
from ciris_engine.schemas.protocol_schemas_v1 import LLMStatus
from ciris_engine.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerError

logger = logging.getLogger(__name__)


class OpenAICompatibleClient(LLMService):
    """Client for interacting with OpenAI-compatible APIs with circuit breaker protection."""

    def __init__(self, config: Optional[OpenAIConfig] = None, telemetry_service: Optional[Any] = None) -> None:
        if config is None:
            app_cfg = get_config()
            self.openai_config = app_cfg.llm_services.openai
        else:
            self.openai_config = config
        
        self.telemetry_service = telemetry_service
        
        # Continue with normal OpenAI client initialization
        retry_config = {
            "retry": {
                "global": {
                    "max_retries": min(getattr(self.openai_config, 'max_retries', 3), 3),  # Cap at 3 to prevent cascades
                    "base_delay": 1.0,
                    "max_delay": 30.0,  # Shorter max delay for faster failure detection
                },
                "api_call": {
                    "retryable_exceptions": (APIConnectionError, RateLimitError),
                    "non_retryable_exceptions": (APIStatusError, instructor.exceptions.InstructorRetryException)  # type: ignore[attr-defined]
                }
            }
        }
        super().__init__(config=retry_config)

        circuit_config = CircuitBreakerConfig(
            failure_threshold=3,        # Open after 3 consecutive failures
            recovery_timeout=300.0,     # Wait 5 minutes before testing recovery
            success_threshold=2,        # Close after 2 successful calls
            timeout_duration=30.0       # 30 second API timeout
        )
        self.circuit_breaker = CircuitBreaker("llm_service", circuit_config)

        api_key = self.openai_config.api_key
        base_url = self.openai_config.base_url
        model_name = self.openai_config.model_name or 'gpt-4o-mini'
        
        # If no API key in config, fall back to mock LLM
        if not api_key:
            try:
                from ciris_engine.services.mock_llm.service import MockLLMService
                self._is_mock = True
                self._mock_service: Optional[MockLLMService] = MockLLMService()
                self.model_name = 'mock-model'
                return
            except Exception as e:
                raise RuntimeError(f"No OpenAI API key found and mock LLM fallback failed: {e}")
        
        # Continue with real OpenAI client initialization
        self._is_mock = False
        self._mock_service = None
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
                mode=instructor.Mode.JSON if instructor_mode == 'json' else instructor.Mode.TOOLS
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}")

    async def start(self) -> None:
        """Start the LLM service."""
        if self._is_mock and self._mock_service:
            await self._mock_service.start()
            logger.info("Mock LLM Service started")
            return
            
        await super().start()
        logger.info(f"OpenAI Compatible LLM Service started with model: {self.model_name}")
        logger.info(f"Circuit breaker initialized: {self.circuit_breaker.get_stats()}")

    async def stop(self) -> None:
        """Stop the LLM service."""
        if self._is_mock and self._mock_service:
            await self._mock_service.stop()
            return
            
        await super().stop()
        await self.client.close()
        logger.info("OpenAI Compatible LLM Service stopped")

    def _get_client(self) -> AsyncOpenAI:
        """Return the OpenAI client instance (private method)."""
        return self.client

    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the LLM service."""
        # Delegate to mock service if using mock
        if self._is_mock:
            base_health = await super().health_check()
            return {
                **base_health,
                "model_name": self.model_name,
                "service_type": "mock",
                "status": "healthy"
            }
            
        base_health = await super().health_check()
        
        cb_stats = self.circuit_breaker.get_stats()
        
        return {
            **base_health,
            "model_name": self.model_name,
            "circuit_breaker": cb_stats,
            "status": "healthy" if self.circuit_breaker.is_available() else "degraded"
        }

    def _extract_json_from_response(self, raw: str) -> Dict[str, Any]:
        """Extract and parse JSON from LLM response."""
        return self.extract_json(raw)
    
    @classmethod
    def extract_json(cls, raw: str) -> Dict[str, Any]:
        """Extract and parse JSON from LLM response."""
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
            parsed: Dict[str, Any] = json.loads(json_str)
            return parsed
        except json.JSONDecodeError:
            try:
                parsed_retry: Dict[str, Any] = json.loads(json_str.replace("'", '"'))
                return parsed_retry
            except json.JSONDecodeError:
                return {"error": f"Failed to parse JSON. Raw content snippet: {raw}"}


    async def call_llm_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Make a structured LLM call with circuit breaker protection."""
        # Delegate to mock service if using mock
        if self._is_mock and self._mock_service:
            return await self._mock_service.call_llm_structured(
                messages, response_model, max_tokens, temperature, **kwargs
            )
            
        logger.debug(f"Structured LLM call for {response_model.__name__}")
        
        # Check circuit breaker before making call
        self.circuit_breaker.check_and_raise()
        
        async def _make_structured_call(
            msgs: List[Dict[str, str]],
            resp_model: Type[BaseModel],
            max_toks: int,
            temp: float,
            extra_kwargs: Dict[str, Any]
        ) -> Tuple[BaseModel, ResourceUsage]:
            # Convert messages to the format expected by OpenAI  
            formatted_messages = [{"role": msg.get("role", "user"), "content": msg.get("content", "")} for msg in msgs]
            
            try:
                response = await self.instruct_client.chat.completions.create(
                    model=self.model_name,
                    messages=cast(Any, formatted_messages),
                    response_model=resp_model,
                    max_retries=0,  # Disable instructor retries completely
                    max_tokens=max_toks,
                    temperature=temp,
                    **extra_kwargs,
                )
                
                # Record success with circuit breaker
                self.circuit_breaker.record_success()
                
                usage = getattr(response, "usage", None)
                usage_obj = ResourceUsage(
                    tokens_used=getattr(usage, "total_tokens", 0)
                )
                
                # Record token usage in telemetry
                if self.telemetry_service and usage_obj.tokens_used > 0:
                    await self.telemetry_service.record_metric("llm_tokens_used", usage_obj.tokens_used)
                    await self.telemetry_service.record_metric("llm_api_call_structured")
                
                return response, usage_obj
                
            except (APIConnectionError, RateLimitError, instructor.exceptions.InstructorRetryException) as e:  # type: ignore[attr-defined]
                # Record failure with circuit breaker
                self.circuit_breaker.record_failure()
                
                # Special handling for timeout cascades
                if isinstance(e, instructor.exceptions.InstructorRetryException) and "timed out" in str(e):  # type: ignore[attr-defined]
                    logger.error(f"LLM structured timeout detected, circuit breaker recorded failure: {e}")
                    raise TimeoutError("LLM API timeout in structured call - circuit breaker activated") from e
                
                logger.warning(f"LLM structured API error recorded by circuit breaker: {e}")
                raise
            
        # Use base class retry with OpenAI-specific error handling
        try:
            # Type assertion: retry_with_backoff handles async functions properly
            return await self.retry_with_backoff(
                _make_structured_call,  # type: ignore[arg-type]
                messages,
                response_model,
                max_tokens,
                temperature,
                kwargs,
                **self.get_retry_config("api_call")
            )
        except CircuitBreakerError:
            # Don't retry if circuit breaker is open
            logger.warning("LLM service circuit breaker is open, failing fast")
            raise
        except TimeoutError:
            # Don't retry timeout errors to prevent cascades
            logger.warning("LLM structured service timeout, failing fast to prevent retry cascade")
            raise



    async def get_status(self) -> LLMStatus:
        """Get detailed status including circuit breaker metrics."""
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