from types import SimpleNamespace
from typing import Any, Optional, List, Dict, Type, Tuple
import instructor
import logging

from pydantic import BaseModel
from ciris_engine.logic.adapters.base import Service
from ciris_engine.protocols.services import LLMService as MockLLMServiceProtocol
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.runtime.enums import ServiceType

from .responses import create_response
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type

logger = logging.getLogger(__name__)

class MockInstructorClient:
    """Mock instructor-patched client that properly handles response_model parameter."""
    
    def __init__(self, base_client: Any) -> None:
        self.base_client = base_client
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
    
    async def _create(self, *args: Any, response_model: Optional[Type[BaseModel]] = None, **kwargs: Any):
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
    
    async def _patched_create(self, *args: Any, **kwargs: Any):
        """Intercept instructor-patched calls and route to our mock."""
        logger.debug(f"Patched client _create called with kwargs: {list(kwargs.keys())}")
        
        # Extract the response_model from kwargs
        response_model = kwargs.get('response_model')
        logger.debug(f"Patched client response_model: {response_model}")
        
        # Route to the original mock client's _create method
        return await self.original_client._create(*args, **kwargs)

class MockLLMClient:
    """Lightweight stand-in for an OpenAI-compatible client that supports instructor patching."""

    def __init__(self) -> None:
        self.model_name = "mock-model"
        self.client = self
        self.instruct_client = MockInstructorClient(self)
        
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create)
        )
        
        self._original_create = self._create
        
        self._original_instructor_patch = instructor.patch
        MockLLMClient._instance = self  # type: ignore[attr-defined]
        instructor.patch = lambda *args, **kwargs: MockLLMClient._mock_instructor_patch(*args, **kwargs)

    @staticmethod
    def _mock_instructor_patch(*args: Any, **kwargs: Any):
        """Override instructor.patch to return our mock patched client."""
        # Extract client from args if provided
        client = args[0] if args else kwargs.get('client')
        mode = args[1] if len(args) > 1 else kwargs.get('mode')
        
        logger.debug(f"instructor.patch called on {type(client) if client else 'None'} with mode {mode}")
        
        # Get the instance reference
        instance = getattr(MockLLMClient, '_instance', None)
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

    async def _create(self, *args: Any, response_model: Optional[Type[BaseModel]] = None, **kwargs: Any):
        """
        Create method that instructor.patch() will call.
        Must return responses in OpenAI API format for instructor to parse correctly.
        """
        logger.info(f"[DEBUG TIMING] MockLLMClient._create called with response_model: {response_model}")
        logger.debug(f"_create called with response_model: {response_model}")
        
        # Extract messages for context analysis  
        messages = kwargs.get('messages', [])
        
        # Remove messages from kwargs to avoid duplicate parameter error
        filtered_kwargs = {k: v for k, v in kwargs.items() if k != 'messages'}
        
        # Call our response generator with messages as explicit parameter
        response = create_response(response_model, messages=messages, **filtered_kwargs)
        
        logger.debug(f"Generated response type: {type(response)}")
        return response
    
    def __getattr__(self, name: str):
        """Support dynamic attribute access for instructor compatibility."""
        if name in ['_acreate']:
            return self._create
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

class MockLLMService(Service, MockLLMServiceProtocol):
    """Mock LLM service used for offline testing."""

    def __init__(self, *_: Any, **__: Any) -> None:
        super().__init__()
        self._client: Optional[MockLLMClient] = None
        self.model_name = "mock-model"
    
    def get_service_type(self) -> ServiceType:
        """Get the service type."""
        return ServiceType.LLM

    async def start(self) -> None:
        await super().start()
        self._client = MockLLMClient()

    async def stop(self) -> None:
        self._client = None
        await super().stop()

    def get_capabilities(self) -> Dict[str, Any]:
        """Return service capabilities."""
        return {
            "service_name": "MockLLMService",
            "capabilities": ["call_llm_structured"],
            "version": "1.0.0",
            "model": self.model_name
        }

    def get_status(self) -> Dict[str, Any]:
        """Return current service status."""
        return {
            "healthy": self._client is not None,
            "service_name": "MockLLMService",
            "status": "running" if self._client else "stopped",
            "details": {
                "model": self.model_name,
                "mock": True
            }
        }

    async def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return self._client is not None

    def _get_client(self) -> MockLLMClient:
        if not self._client:
            raise RuntimeError("MockLLMService has not been started")
        return self._client

    async def call_llm_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[BaseModel],
        max_tokens: int = 1024,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Tuple[BaseModel, ResourceUsage]:
        """Mock implementation of structured LLM call."""
        logger.info(f"[DEBUG TIMING] MockLLMService.call_llm_structured called with response_model: {response_model}")
        if not self._client:
            raise RuntimeError("MockLLMService has not been started")
        
        logger.debug(f"Mock call_llm_structured with response_model: {response_model}")
        
        response = await self._client._create(
            messages=messages,
            response_model=response_model,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )
        
        # Simulate llama4scout resource usage from together.ai
        # Estimate input tokens from messages
        input_tokens = int(sum(len(msg.get('content', '').split()) * 1.3 for msg in messages))  # ~1.3 tokens per word
        output_tokens = max_tokens // 4  # Assume ~25% of max tokens used on average
        
        # Ensure minimum token counts for testing
        if input_tokens == 0:
            input_tokens = 50  # Default minimum for non-empty requests
        if output_tokens == 0:
            output_tokens = 25  # Default minimum output
        
        usage = ResourceUsage(
            tokens_used=input_tokens + output_tokens,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            # Together.ai pricing for Llama models: ~$0.0002/1K input, $0.0003/1K output tokens
            # $0.0002 per 1K tokens = $0.0002/1000 per token
            cost_cents=(input_tokens * 0.0002/1000 + output_tokens * 0.0003/1000) * 100,  # Convert to cents
            # Energy estimates: ~0.0001 kWh per 1K tokens (efficient model)
            energy_kwh=(input_tokens + output_tokens) * 0.0001 / 1000,
            # Carbon: ~0.5g CO2 per kWh (US grid average)
            carbon_grams=((input_tokens + output_tokens) * 0.0001 / 1000) * 500,
            model_used="llama4scout (mock)"
        )
        
        return response, usage

