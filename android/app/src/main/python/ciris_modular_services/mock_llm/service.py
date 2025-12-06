import logging
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple, Type

import instructor
from pydantic import BaseModel

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import LLMService as MockLLMServiceProtocol
from ciris_engine.protocols.services.runtime.llm import MessageDict
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus

from .responses import create_response

logger = logging.getLogger(__name__)


class MockInstructorClient:
    """Mock instructor-patched client that properly handles response_model parameter."""

    def __init__(self, base_client: Any) -> None:
        self.base_client = base_client
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *args: Any, response_model: Optional[Type[BaseModel]] = None, **kwargs: Any) -> Any:
        # This is the instructor-patched version that should always receive response_model
        if response_model is None:
            # This should NOT happen - instructor always passes response_model
            logger.error("MockInstructorClient received response_model=None - this indicates a bug!")
            raise ValueError("Instructor client should always receive response_model")

        # Forward to base client with response_model preserved
        return await self.base_client._create(*args, response_model=response_model, **kwargs)


class MockPatchedClient:
    """A client that mimics instructor.patch() behavior for our mock."""

    def __init__(self, original_client: Any, mode: Optional[str] = None) -> None:
        self.original_client = original_client
        self.mode = mode
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._patched_create))

    async def _patched_create(self, *args: Any, **kwargs: Any) -> Any:
        """Intercept instructor-patched calls and route to our mock."""
        logger.debug(f"Patched client _create called with kwargs: {list(kwargs.keys())}")

        # Extract the response_model from kwargs
        response_model = kwargs.get("response_model")
        logger.debug(f"Patched client response_model: {response_model}")

        # Route to the original mock client's _create method
        return await self.original_client._create(*args, **kwargs)


class MockLLMClient:
    """Lightweight stand-in for an OpenAI-compatible client that supports instructor patching."""

    def __init__(self) -> None:
        self.model_name = "mock-model"
        self.client = self
        self.instruct_client = MockInstructorClient(self)

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        self._original_create = self._create

        self._original_instructor_patch = instructor.patch
        MockLLMClient._instance = self  # type: ignore[attr-defined]
        instructor.patch = lambda *args, **kwargs: MockLLMClient._mock_instructor_patch(*args, **kwargs)

    @staticmethod
    def _mock_instructor_patch(*args: Any, **kwargs: Any) -> Any:
        """Override instructor.patch to return our mock patched client."""
        # Extract client from args if provided
        client = args[0] if args else kwargs.get("client")
        mode = args[1] if len(args) > 1 else kwargs.get("mode")

        logger.debug(f"instructor.patch called on {type(client) if client else 'None'} with mode {mode}")

        # Get the instance reference
        instance = getattr(MockLLMClient, "_instance", None)
        if not instance:
            raise RuntimeError("MockLLMClient instance not available for patch")

        # If they're trying to patch our mock client, return our special patched version
        if client is instance or client is instance.client:
            return MockPatchedClient(instance, mode)

        # Otherwise, use the original instructor.patch (for real clients)
        if client:
            return instance._original_instructor_patch(client, mode=mode, **kwargs)
        else:
            # If no client provided, call original with args and kwargs
            return instance._original_instructor_patch(*args, **kwargs)

    async def _create(self, *args: Any, response_model: Optional[Type[BaseModel]] = None, **kwargs: Any) -> Any:
        """
        Create method that instructor.patch() will call.
        Must return responses in OpenAI API format for instructor to parse correctly.
        """
        logger.debug(f"[DEBUG TIMING] MockLLMClient._create called with response_model: {response_model}")
        logger.debug(f"_create called with response_model: {response_model}")

        # Extract messages for context analysis
        messages = kwargs.get("messages", [])

        # Remove messages from kwargs to avoid duplicate parameter error
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != "messages"}

        # Call our response generator with messages as explicit parameter
        response = create_response(response_model, messages=messages, **filtered_kwargs)

        logger.debug(f"Generated response type: {type(response)}")
        return response

    def __getattr__(self, name: str) -> Any:
        """Support dynamic attribute access for instructor compatibility."""
        if name in ["_acreate"]:
            return self._create
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class MockLLMService(BaseService, MockLLMServiceProtocol):
    """Mock LLM service used for offline testing."""

    def __init__(self, *_: Any, **kwargs: Any) -> None:
        # Initialize BaseService with service name
        super().__init__(service_name="MockLLMService", **kwargs)
        self._client: Optional[MockLLMClient] = None
        self.model_name = "mock-model"

        # Metrics tracking for get_metrics (use float for time.time())
        self._start_time_float: Optional[float] = None
        self._total_requests = 0
        self._total_errors = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost_cents = 0.0

    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.LLM

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["call_llm_structured", "extract_json"]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        return True  # Mock service has no external dependencies

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect service-specific metrics."""
        return {
            "total_requests": float(self._total_requests),
            "total_errors": float(self._total_errors),
            "total_input_tokens": float(self._total_input_tokens),
            "total_output_tokens": float(self._total_output_tokens),
            "total_cost_cents": self._total_cost_cents,
        }

    async def start(self) -> None:
        await super().start()
        self._client = MockLLMClient()
        import time

        self._start_time_float = time.time()

    async def stop(self) -> None:
        self._client = None
        await super().stop()

    def get_capabilities(self) -> ServiceCapabilities:
        """Return service capabilities."""
        return ServiceCapabilities(
            service_name="MockLLMService",
            actions=["call_llm_structured"],
            version="1.0.0",
        )

    def get_status(self) -> ServiceStatus:
        """Return current service status."""
        import time

        uptime = time.time() - self._start_time_float if self._start_time_float else 0.0
        return ServiceStatus(
            service_name="MockLLMService",
            service_type="llm",
            is_healthy=self._client is not None,
            uptime_seconds=uptime,
        )

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self._client is not None

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all LLM metrics including base, custom, and v1.4.3 specific metrics.
        Following the pattern from LLMService.
        """
        import time

        uptime = time.time() - self._start_time_float if self._start_time_float else 0.0

        # Return v1.4.3 compliant LLM metrics
        return {
            # Base metrics
            "uptime_seconds": uptime,
            "request_count": float(self._total_requests),
            "error_count": float(self._total_errors),
            "error_rate": self._total_errors / max(1, self._total_requests),
            # v1.4.3 specific LLM metrics
            "llm_requests_total": float(self._total_requests),
            "llm_tokens_input": float(self._total_input_tokens),
            "llm_tokens_output": float(self._total_output_tokens),
            "llm_tokens_total": float(self._total_input_tokens + self._total_output_tokens),
            "llm_cost_cents": self._total_cost_cents,
            "llm_errors_total": float(self._total_errors),
            "llm_uptime_seconds": uptime,
        }

    def _get_client(self) -> MockLLMClient:
        if not self._client:
            raise RuntimeError("MockLLMService has not been started")
        return self._client

    async def call_llm_structured(
        self,
        messages: List[MessageDict],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Mock implementation of structured LLM call."""
        logger.debug(f"[DEBUG TIMING] MockLLMService.call_llm_structured called with response_model: {response_model}")
        if not self._client:
            raise RuntimeError("MockLLMService has not been started")

        logger.debug(f"Mock call_llm_structured with response_model: {response_model}")

        # Track request
        self._total_requests += 1

        try:
            response = await self._client._create(
                messages=messages,
                response_model=response_model,
                max_tokens=max_tokens,
                temperature=temperature,
                **kwargs,
            )
        except Exception as e:
            self._total_errors += 1
            raise

        # Simulate llama4scout resource usage from together.ai
        # Estimate input tokens from messages
        input_tokens = int(sum(len(msg.get("content", "").split()) * 1.3 for msg in messages))  # ~1.3 tokens per word
        output_tokens = max_tokens // 4  # Assume ~25% of max tokens used on average

        # Ensure minimum token counts for testing
        if input_tokens == 0:
            input_tokens = 50  # Default minimum for non-empty requests
        if output_tokens == 0:
            output_tokens = 25  # Default minimum output

        # Calculate cost in cents
        cost_cents = (input_tokens * 0.0002 / 1000 + output_tokens * 0.0003 / 1000) * 100

        # Track metrics for get_metrics
        self._total_input_tokens += input_tokens
        self._total_output_tokens += output_tokens
        self._total_cost_cents += cost_cents

        usage = ResourceUsage(
            tokens_used=input_tokens + output_tokens,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            # Together.ai pricing for Llama models: ~$0.0002/1K input, $0.0003/1K output tokens
            # $0.0002 per 1K tokens = $0.0002/1000 per token
            cost_cents=cost_cents,  # Convert to cents
            # Energy estimates: ~0.0001 kWh per 1K tokens (efficient model)
            energy_kwh=(input_tokens + output_tokens) * 0.0001 / 1000,
            # Carbon: ~0.5g CO2 per kWh (US grid average)
            carbon_grams=((input_tokens + output_tokens) * 0.0001 / 1000) * 500,
            model_used="llama4scout (mock)",
        )

        return response, usage
