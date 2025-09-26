"""
Centralized fixtures for LLM service testing.

This module provides comprehensive mocks and fixtures for all LLM-related tests,
reducing duplication and ensuring consistent test setups.
"""

import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, Dict, List

import pytest
from pydantic import BaseModel

from ciris_engine.logic.services.runtime.llm_service import OpenAICompatibleClient, OpenAIConfig
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.resources import ResourceUsage


class MockInstructorRetryException(Exception):
    """Mock InstructorRetryException for testing."""

    def __init__(self, message: str, *args, **kwargs):
        super().__init__(message, *args, **kwargs)
        self.message = message

    def __str__(self):
        return self.message


class TestResponse(BaseModel):
    """Standard test response model for LLM testing."""

    message: str
    status: str = "ok"
    confidence: float = 0.95


class MockTimeService:
    """Enhanced mock time service with configurable time."""

    def __init__(self, fixed_time: datetime = None):
        self.fixed_time = fixed_time or datetime(2025, 1, 1, 12, 0, 0)
        self._timestamp_counter = 0

    def now(self) -> datetime:
        return self.fixed_time

    def now_iso(self) -> str:
        return self.fixed_time.isoformat()

    def timestamp(self) -> float:
        # Return incrementing timestamps for latency calculations
        self._timestamp_counter += 1
        return self.fixed_time.timestamp() + (self._timestamp_counter * 0.1)


class MockTelemetryService:
    """Enhanced mock telemetry service with metric tracking."""

    def __init__(self):
        self.metrics: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []

    async def record_metric(self, metric_name: str, value: float = 1.0, handler_name: str = None, tags: dict = None):
        """Record a metric with full context."""
        self.metrics.append({
            "name": metric_name,
            "value": value,
            "handler": handler_name,
            "tags": tags or {},
            "timestamp": datetime.now().isoformat()
        })

    async def log_event(self, event_name: str, data: dict = None):
        """Log an event with context."""
        self.events.append({
            "event": event_name,
            "data": data or {},
            "timestamp": datetime.now().isoformat()
        })

    def get_metrics_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Get all metrics with a specific name."""
        return [m for m in self.metrics if m["name"] == name]

    def clear(self):
        """Clear all recorded metrics and events."""
        self.metrics.clear()
        self.events.clear()


@pytest.fixture
def mock_time_service():
    """Create a mock time service with consistent timestamps."""
    return MockTimeService()


@pytest.fixture
def mock_telemetry_service():
    """Create a mock telemetry service with metric tracking."""
    return MockTelemetryService()


@pytest.fixture
def llm_config():
    """Create a standard test LLM configuration."""
    return OpenAIConfig(
        api_key="test-key-12345",
        model_name="gpt-4o-mini",
        base_url=None,
        instructor_mode="JSON",
        max_retries=3,
        timeout_seconds=30,
    )


@pytest.fixture
def llm_config_lambda():
    """Create a Lambda Labs LLM configuration for fallback testing."""
    return OpenAIConfig(
        api_key="lambda-test-key-67890",
        model_name="llama-4-maverick-17b-128e-instruct-fp8",
        base_url="https://api.lambda.ai/v1",
        instructor_mode="JSON",
        max_retries=3,
        timeout_seconds=30,
    )


@pytest.fixture
def mock_openai_client():
    """Create a fully mocked OpenAI client with configurable responses."""
    client = MagicMock()
    client.close = AsyncMock()

    # Setup default successful responses
    client.chat.completions.create = AsyncMock()

    return client


@pytest.fixture
def mock_instructor_client():
    """Create a fully mocked instructor client with configurable responses."""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()

    # Setup default successful response
    async def default_create(*args, **kwargs):
        response_model = kwargs.get('response_model', TestResponse)
        return response_model(message="Test response", status="ok"), ResourceUsage(
            tokens_used=150,
            tokens_input=100,
            tokens_output=50,
            cost_cents=0.15,
            model_used="gpt-4o-mini",
            carbon_grams=0.01,
            energy_kwh=0.001
        )

    client.chat.completions.create_with_completion = AsyncMock(side_effect=default_create)

    return client


@pytest.fixture
def llm_service(llm_config, mock_time_service, mock_telemetry_service,
               mock_openai_client, mock_instructor_client):
    """Create a fully mocked LLM service for testing."""
    # Mock environment to prevent mock LLM detection
    with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False):
        with patch("sys.argv", []):
            # Mock the OpenAI and instructor imports
            with patch("ciris_engine.logic.services.runtime.llm_service.AsyncOpenAI") as mock_openai:
                with patch("ciris_engine.logic.services.runtime.llm_service.instructor") as mock_instructor:
                    # Set up mocks
                    mock_openai.return_value = mock_openai_client
                    mock_instructor.from_openai.return_value = mock_instructor_client
                    mock_instructor.Mode.JSON = "JSON"
                    mock_instructor.Mode.TOOLS = "TOOLS"

                    # Create service
                    service = OpenAICompatibleClient(
                        config=llm_config,
                        time_service=mock_time_service,
                        telemetry_service=mock_telemetry_service,
                        service_name="test_llm_service",
                        version="1.0.0",
                    )

                    # Ensure the mocked clients are properly set
                    service.client = mock_openai_client
                    service.instruct_client = mock_instructor_client
                    service._response_times = []

                    return service


@pytest.fixture
def llm_service_with_exceptions(llm_config, mock_time_service, mock_telemetry_service,
                               mock_openai_client, mock_instructor_client):
    """Create an LLM service configured for exception testing."""
    # Mock environment to prevent mock LLM detection
    with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False):
        with patch("sys.argv", []):
            # Mock the OpenAI and instructor imports
            with patch("ciris_engine.logic.services.runtime.llm_service.AsyncOpenAI") as mock_openai:
                with patch("ciris_engine.logic.services.runtime.llm_service.instructor") as mock_instructor:
                    # Set up mocks
                    mock_openai.return_value = mock_openai_client
                    mock_instructor.from_openai.return_value = mock_instructor_client

                    # Set up instructor exceptions module for proper detection
                    mock_instructor.exceptions = MagicMock()
                    mock_instructor.exceptions.InstructorRetryException = MockInstructorRetryException

                    # Set up modes
                    mock_instructor.Mode = MagicMock()
                    mock_instructor.Mode.JSON = "JSON"
                    mock_instructor.Mode.TOOLS = "TOOLS"

                    # Create service
                    service = OpenAICompatibleClient(
                        config=llm_config,
                        time_service=mock_time_service,
                        telemetry_service=mock_telemetry_service,
                        service_name="test_llm_service",
                        version="1.0.0",
                    )

                    # Ensure the mocked clients are properly set
                    service.client = mock_openai_client
                    service.instruct_client = mock_instructor_client
                    service._response_times = []

                    return service


def create_instructor_exception(error_type: str = "timeout") -> MockInstructorRetryException:
    """Helper function to create different types of InstructorRetryException."""
    messages = {
        "timeout": "Request timed out after 30 seconds",
        "503": "Error code: 503 - {'error': {'message': 'Service unavailable', 'type': 'service_unavailable'}}",
        "rate_limit": "Error code: 429 - {'error': {'message': 'Rate limit exceeded', 'type': 'rate_limit'}}",
        "generic": "LLM API call failed with unknown error"
    }

    return MockInstructorRetryException(messages.get(error_type, messages["generic"]))


# Helper functions for test setup
def setup_instructor_exception(mock_instructor_client, exception_type: str = "timeout"):
    """Configure the instructor client to raise a specific exception type."""
    exception = create_instructor_exception(exception_type)
    mock_instructor_client.chat.completions.create_with_completion.side_effect = exception


def setup_successful_response(mock_instructor_client, response_data: dict = None):
    """Configure the instructor client for successful responses."""
    response_data = response_data or {"message": "Test response", "status": "ok"}

    async def successful_create(*args, **kwargs):
        response_model = kwargs.get('response_model', TestResponse)
        return response_model(**response_data), ResourceUsage(
            tokens_used=150,
            tokens_input=100,
            tokens_output=50,
            cost_cents=0.15,
            model_used="gpt-4o-mini",
            carbon_grams=0.01,
            energy_kwh=0.001
        )

    mock_instructor_client.chat.completions.create_with_completion = AsyncMock(side_effect=successful_create)