"""
Centralized fixtures for LLM service testing.

This module provides comprehensive mocks and fixtures for all LLM-related tests,
reducing duplication and ensuring consistent test setups.
"""

import os
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ciris_engine.config.pricing_models import (
    CarbonIntensity,
    EnergyEstimates,
    EnvironmentalFactors,
    FallbackPricing,
    ModelConfig,
    PricingConfig,
    PricingMetadata,
    ProviderConfig,
)
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

    @classmethod
    def create_as_subclass(cls, base_class):
        """Create a dynamic subclass that inherits from the provided base class."""

        class DynamicMockInstructorException(base_class, cls):
            pass

        return DynamicMockInstructorException


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
        self.metrics.append(
            {
                "name": metric_name,
                "value": value,
                "handler": handler_name,
                "tags": tags or {},
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def log_event(self, event_name: str, data: dict = None):
        """Log an event with context."""
        self.events.append({"event": event_name, "data": data or {}, "timestamp": datetime.now().isoformat()})

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
        response_model = kwargs.get("response_model", TestResponse)

        # Create a mock completion object with usage attribute
        mock_completion = MagicMock()
        mock_completion.usage = MagicMock()
        mock_completion.usage.total_tokens = 150
        mock_completion.usage.prompt_tokens = 100
        mock_completion.usage.completion_tokens = 50

        return response_model(message="Test response", status="ok"), mock_completion

    client.chat.completions.create_with_completion = AsyncMock(side_effect=default_create)

    return client


@pytest.fixture
def llm_service(
    llm_config,
    mock_time_service,
    mock_telemetry_service,
    mock_openai_client,
    mock_instructor_client,
    mock_pricing_config,
):
    """Create a fully mocked LLM service for testing."""
    # Mock environment to prevent mock LLM detection
    with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False):
        with patch("sys.argv", []):
            # Mock the OpenAI and instructor imports
            with patch("ciris_engine.logic.services.runtime.llm_service.AsyncOpenAI") as mock_openai:
                with patch("ciris_engine.logic.services.runtime.llm_service.instructor") as mock_instructor:
                    # Mock the pricing calculator
                    with patch(
                        "ciris_engine.logic.services.runtime.llm_service.service.LLMPricingCalculator"
                    ) as mock_calc_class:
                        # Set up mocks
                        mock_openai.return_value = mock_openai_client
                        mock_instructor.from_openai.return_value = mock_instructor_client
                        mock_instructor.Mode.JSON = "JSON"
                        mock_instructor.Mode.TOOLS = "TOOLS"

                        # Create a mock pricing calculator instance that calculates realistic values
                        mock_calc_instance = MagicMock()

                        def calculate_realistic_costs(model_name, prompt_tokens, completion_tokens, provider_name=None):
                            # Ensure all parameters are proper types, not MagicMock objects
                            model_name = str(model_name) if model_name else "gpt-4o-mini"
                            prompt_tokens = int(prompt_tokens) if isinstance(prompt_tokens, (int, float)) else 100
                            completion_tokens = (
                                int(completion_tokens) if isinstance(completion_tokens, (int, float)) else 50
                            )
                            provider_name = str(provider_name) if provider_name else None

                            total_tokens = prompt_tokens + completion_tokens

                            # Legacy cost calculation logic (matching original hardcoded values)
                            if model_name.startswith("gpt-4o-mini"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 15.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 60.0
                                energy_per_1k = 0.0003
                            elif model_name.startswith("gpt-4o"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 250.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 1000.0
                                energy_per_1k = 0.0005
                            elif model_name.startswith("gpt-4-turbo"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 1000.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 3000.0
                                energy_per_1k = 0.0005
                            elif "gpt-4" in model_name:  # This catches "gpt-4" that doesn't match above
                                input_cost_cents = (prompt_tokens / 1_000_000) * 20.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 20.0
                                energy_per_1k = 0.0005
                            elif model_name.startswith("gpt-3.5-turbo"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 50.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 150.0
                                energy_per_1k = 0.0003
                            elif "llama" in model_name.lower() and "17B" in model_name:
                                input_cost_cents = (prompt_tokens / 1_000_000) * 10.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 10.0
                                energy_per_1k = 0.0002
                            elif "claude" in model_name.lower():
                                input_cost_cents = (prompt_tokens / 1_000_000) * 300.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 1500.0
                                energy_per_1k = 0.0004
                            else:
                                input_cost_cents = (prompt_tokens / 1_000_000) * 20.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 20.0
                                energy_per_1k = 0.0003

                            total_cost_cents = input_cost_cents + output_cost_cents
                            energy_kwh = (total_tokens / 1000) * energy_per_1k
                            carbon_grams = energy_kwh * 500.0

                            return ResourceUsage(
                                tokens_used=total_tokens,
                                tokens_input=prompt_tokens,
                                tokens_output=completion_tokens,
                                cost_cents=total_cost_cents,
                                carbon_grams=carbon_grams,
                                energy_kwh=energy_kwh,
                                model_used=model_name,
                            )

                        mock_calc_instance.calculate_cost_and_impact.side_effect = calculate_realistic_costs
                        mock_calc_class.return_value = mock_calc_instance

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
def llm_service_with_exceptions(
    llm_config,
    mock_time_service,
    mock_telemetry_service,
    mock_openai_client,
    mock_instructor_client,
    mock_pricing_config,
):
    """Create an LLM service configured for exception testing."""
    # Mock environment to prevent mock LLM detection
    with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False):
        with patch("sys.argv", []):
            # Mock the OpenAI and instructor imports
            with patch("ciris_engine.logic.services.runtime.llm_service.AsyncOpenAI") as mock_openai:
                with patch("ciris_engine.logic.services.runtime.llm_service.instructor") as mock_instructor:
                    # Mock the pricing calculator
                    with patch(
                        "ciris_engine.logic.services.runtime.llm_service.service.LLMPricingCalculator"
                    ) as mock_calc_class:
                        # Set up mocks
                        mock_openai.return_value = mock_openai_client
                        mock_instructor.from_openai.return_value = mock_instructor_client

                        # Set up instructor exceptions module for proper detection
                        # Create a mock base exception class that our mock can inherit from
                        class MockInstructorRetryExceptionBase(Exception):
                            """Base mock instructor retry exception."""

                            pass

                        # Create our actual mock exception that inherits from the base
                        class ActualMockInstructorRetryException(MockInstructorRetryExceptionBase):
                            def __init__(self, message: str, *args, **kwargs):
                                super().__init__(message, *args, **kwargs)
                                self.message = message

                            def __str__(self):
                                return self.message

                        # Set up the exceptions module
                        class MockExceptionsModule:
                            InstructorRetryException = MockInstructorRetryExceptionBase

                        mock_instructor.exceptions = MockExceptionsModule()

                        # Store the actual exception class for tests to use
                        mock_instructor._test_exception_class = ActualMockInstructorRetryException

                        # Set up modes
                        mock_instructor.Mode = MagicMock()
                        mock_instructor.Mode.JSON = "JSON"
                        mock_instructor.Mode.TOOLS = "TOOLS"

                        # Create a mock pricing calculator instance that calculates realistic values
                        mock_calc_instance = MagicMock()

                        def calculate_realistic_costs(model_name, prompt_tokens, completion_tokens, provider_name=None):
                            # Ensure all parameters are proper types, not MagicMock objects
                            model_name = str(model_name) if model_name else "gpt-4o-mini"
                            prompt_tokens = int(prompt_tokens) if isinstance(prompt_tokens, (int, float)) else 100
                            completion_tokens = (
                                int(completion_tokens) if isinstance(completion_tokens, (int, float)) else 50
                            )
                            provider_name = str(provider_name) if provider_name else None

                            total_tokens = prompt_tokens + completion_tokens

                            # Legacy cost calculation logic (matching original hardcoded values)
                            if model_name.startswith("gpt-4o-mini"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 15.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 60.0
                                energy_per_1k = 0.0003
                            elif model_name.startswith("gpt-4o"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 250.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 1000.0
                                energy_per_1k = 0.0005
                            elif model_name.startswith("gpt-4-turbo"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 1000.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 3000.0
                                energy_per_1k = 0.0005
                            elif "gpt-4" in model_name:  # This catches "gpt-4" that doesn't match above
                                input_cost_cents = (prompt_tokens / 1_000_000) * 20.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 20.0
                                energy_per_1k = 0.0005
                            elif model_name.startswith("gpt-3.5-turbo"):
                                input_cost_cents = (prompt_tokens / 1_000_000) * 50.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 150.0
                                energy_per_1k = 0.0003
                            elif "llama" in model_name.lower() and "17B" in model_name:
                                input_cost_cents = (prompt_tokens / 1_000_000) * 10.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 10.0
                                energy_per_1k = 0.0002
                            elif "claude" in model_name.lower():
                                input_cost_cents = (prompt_tokens / 1_000_000) * 300.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 1500.0
                                energy_per_1k = 0.0004
                            else:
                                input_cost_cents = (prompt_tokens / 1_000_000) * 20.0
                                output_cost_cents = (completion_tokens / 1_000_000) * 20.0
                                energy_per_1k = 0.0003

                            total_cost_cents = input_cost_cents + output_cost_cents
                            energy_kwh = (total_tokens / 1000) * energy_per_1k
                            carbon_grams = energy_kwh * 500.0

                            return ResourceUsage(
                                tokens_used=total_tokens,
                                tokens_input=prompt_tokens,
                                tokens_output=completion_tokens,
                                cost_cents=total_cost_cents,
                                carbon_grams=carbon_grams,
                                energy_kwh=energy_kwh,
                                model_used=model_name,
                            )

                        mock_calc_instance.calculate_cost_and_impact.side_effect = calculate_realistic_costs
                        mock_calc_class.return_value = mock_calc_instance

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


def create_instructor_exception(error_type: str = "timeout"):
    """Helper function to create different types of InstructorRetryException."""
    messages = {
        "timeout": "Request timed out after 30 seconds",
        "503": "Error code: 503 - {'error': {'message': 'Service unavailable', 'type': 'service_unavailable'}}",
        "rate_limit": "Error code: 429 - {'error': {'message': 'Rate limit exceeded', 'type': 'rate_limit'}}",
        "generic": "LLM API call failed with unknown error",
    }

    # Import the actual instructor module mock to get the right exception class
    import instructor

    if hasattr(instructor, "exceptions") and hasattr(instructor.exceptions, "InstructorRetryException"):
        # Use the base class from the mock
        base_class = instructor.exceptions.InstructorRetryException

        class TestInstructorRetryException(base_class):
            def __init__(self, message: str, *args, **kwargs):
                # Provide default values for required InstructorRetryException parameters
                kwargs.setdefault("n_attempts", 3)
                kwargs.setdefault("total_usage", None)
                super().__init__(message, *args, **kwargs)
                self.message = message

            def __str__(self):
                return self.message

        return TestInstructorRetryException(messages.get(error_type, messages["generic"]))
    else:
        # Fallback to the original mock
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
        response_model = kwargs.get("response_model", TestResponse)

        # Create a mock completion object with usage attribute
        mock_completion = MagicMock()
        mock_completion.usage = MagicMock()
        mock_completion.usage.total_tokens = 150
        mock_completion.usage.prompt_tokens = 100
        mock_completion.usage.completion_tokens = 50

        return response_model(**response_data), mock_completion

    mock_instructor_client.chat.completions.create_with_completion = AsyncMock(side_effect=successful_create)


# Pricing Configuration Fixtures


@pytest.fixture
def mock_pricing_config():
    """Create a comprehensive mock pricing configuration for testing."""
    return PricingConfig(
        version="1.0.0",
        last_updated=datetime(2025, 1, 15, 10, 30, 0),
        metadata=PricingMetadata(
            update_frequency="weekly",
            currency="USD",
            units="per_million_tokens",
            sources=["Test OpenAI API", "Test Anthropic API"],
            schema_version="1.0.0",
        ),
        providers={
            "openai": ProviderConfig(
                display_name="OpenAI",
                models={
                    "gpt-4o-mini": ModelConfig(
                        input_cost=15.0,
                        output_cost=60.0,
                        context_window=128000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-07-18",
                        description="GPT-4o mini - fast and affordable model",
                    ),
                    "gpt-4o": ModelConfig(
                        input_cost=250.0,
                        output_cost=1000.0,
                        context_window=128000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-05-13",
                        description="GPT-4o - high-intelligence flagship model",
                    ),
                    "gpt-3.5-turbo": ModelConfig(
                        input_cost=50.0,
                        output_cost=150.0,
                        context_window=16385,
                        active=True,
                        deprecated=False,
                        effective_date="2023-03-01",
                        description="GPT-3.5 Turbo - fast and efficient model",
                    ),
                },
                base_url="https://api.openai.com/v1",
            ),
            "anthropic": ProviderConfig(
                display_name="Anthropic",
                models={
                    "claude-3-opus": ModelConfig(
                        input_cost=1500.0,
                        output_cost=7500.0,
                        context_window=200000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-02-29",
                        description="Claude 3 Opus - most powerful model",
                    ),
                    "claude-3-sonnet": ModelConfig(
                        input_cost=300.0,
                        output_cost=1500.0,
                        context_window=200000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-02-29",
                        description="Claude 3 Sonnet - balanced model",
                    ),
                },
                base_url="https://api.anthropic.com/v1",
            ),
            "lambda_labs": ProviderConfig(
                display_name="Lambda Labs",
                models={
                    "llama-4-maverick-17b-128e-instruct-fp8": ModelConfig(
                        input_cost=10.0,
                        output_cost=10.0,
                        context_window=128000,
                        active=True,
                        deprecated=False,
                        effective_date="2024-09-01",
                        description="Llama 4 Maverick 17B - optimized for inference",
                        provider_specific={"precision": "fp8", "optimization": "inference"},
                    )
                },
                base_url="https://api.lambda.ai/v1",
            ),
        },
        environmental_factors=EnvironmentalFactors(
            energy_estimates=EnergyEstimates(
                model_patterns={
                    "gpt-4": {"kwh_per_1k_tokens": 0.0005},
                    "gpt-3.5": {"kwh_per_1k_tokens": 0.0003},
                    "claude-3": {"kwh_per_1k_tokens": 0.0004},
                    "llama-17b": {"kwh_per_1k_tokens": 0.0002},
                    "default": {"kwh_per_1k_tokens": 0.0003},
                }
            ),
            carbon_intensity=CarbonIntensity(
                global_average_g_co2_per_kwh=500.0,
                regions={"us_west": 350.0, "eu_central": 300.0, "asia_pacific": 600.0},
            ),
        ),
        fallback_pricing=FallbackPricing(
            unknown_model=ModelConfig(
                input_cost=20.0,
                output_cost=20.0,
                context_window=4096,
                active=True,
                deprecated=False,
                effective_date="2024-01-01",
                description="Default pricing for unknown models",
            )
        ),
    )


@pytest.fixture
def pricing_config_gpt4o_mini(mock_pricing_config):
    """Pricing configuration with GPT-4o-mini model selected."""
    config = mock_pricing_config
    # Add a reference to the specific model for easy access
    config._test_model_name = "gpt-4o-mini"
    config._test_provider_name = "openai"
    return config


@pytest.fixture
def pricing_config_claude_opus(mock_pricing_config):
    """Pricing configuration with Claude 3 Opus model selected."""
    config = mock_pricing_config
    config._test_model_name = "claude-3-opus"
    config._test_provider_name = "anthropic"
    return config


@pytest.fixture
def pricing_config_llama_17b(mock_pricing_config):
    """Pricing configuration with Llama 17B model selected."""
    config = mock_pricing_config
    config._test_model_name = "llama-4-maverick-17b-128e-instruct-fp8"
    config._test_provider_name = "lambda_labs"
    return config


@pytest.fixture
def mock_deprecated_model_config():
    """Mock pricing configuration with a deprecated model."""
    base_config = PricingConfig(
        version="1.0.0",
        last_updated=datetime(2025, 1, 15, 10, 30, 0),
        metadata=PricingMetadata(
            update_frequency="weekly",
            currency="USD",
            units="per_million_tokens",
            sources=["Test API"],
            schema_version="1.0.0",
        ),
        providers={
            "openai": ProviderConfig(
                display_name="OpenAI",
                models={
                    "gpt-3.5-turbo-0301": ModelConfig(
                        input_cost=150.0,
                        output_cost=200.0,
                        context_window=4096,
                        active=False,
                        deprecated=True,
                        effective_date="2023-03-01",
                        description="GPT-3.5 Turbo (deprecated version)",
                    )
                },
            )
        },
        environmental_factors=EnvironmentalFactors(
            energy_estimates=EnergyEstimates(model_patterns={"default": {"kwh_per_1k_tokens": 0.0003}}),
            carbon_intensity=CarbonIntensity(global_average_g_co2_per_kwh=500.0, regions={}),
        ),
        fallback_pricing=FallbackPricing(
            unknown_model=ModelConfig(
                input_cost=20.0,
                output_cost=20.0,
                context_window=4096,
                active=True,
                deprecated=False,
                effective_date="2024-01-01",
                description="Default pricing",
            )
        ),
    )
    return base_config


def create_test_pricing_config(**overrides):
    """
    Helper function to create customized pricing configurations for testing.

    Args:
        **overrides: Key-value pairs to override in the default configuration

    Returns:
        PricingConfig: Customized pricing configuration
    """
    defaults = {
        "version": "1.0.0",
        "last_updated": datetime(2025, 1, 15, 10, 30, 0),
        "metadata": {
            "update_frequency": "weekly",
            "currency": "USD",
            "units": "per_million_tokens",
            "sources": ["Test API"],
            "schema_version": "1.0.0",
        },
        "providers": {
            "test_provider": {
                "display_name": "Test Provider",
                "models": {
                    "test-model": {
                        "input_cost": 10.0,
                        "output_cost": 20.0,
                        "context_window": 4096,
                        "active": True,
                        "deprecated": False,
                        "effective_date": "2024-01-01",
                        "description": "Test model",
                    }
                },
            }
        },
        "environmental_factors": {
            "energy_estimates": {"model_patterns": {"default": {"kwh_per_1k_tokens": 0.0003}}},
            "carbon_intensity": {"global_average_g_co2_per_kwh": 500.0, "regions": {}},
        },
        "fallback_pricing": {
            "unknown_model": {
                "input_cost": 20.0,
                "output_cost": 20.0,
                "context_window": 4096,
                "active": True,
                "deprecated": False,
                "effective_date": "2024-01-01",
                "description": "Default pricing",
            }
        },
    }

    # Deep merge overrides into defaults
    def deep_merge(base, override):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                deep_merge(base[key], value)
            else:
                base[key] = value

    deep_merge(defaults, overrides)

    # Convert nested dictionaries to proper Pydantic models
    try:
        return PricingConfig(**defaults)
    except Exception as e:
        # If Pydantic validation fails, return the dict for debugging
        raise ValueError(f"Failed to create test pricing config: {e}")


@pytest.fixture
def pricing_config_with_high_costs():
    """Pricing configuration with unusually high costs for testing edge cases."""
    return create_test_pricing_config(
        providers={
            "expensive_provider": {
                "display_name": "Expensive Provider",
                "models": {
                    "expensive-model": {
                        "input_cost": 5000.0,  # $50 per million tokens
                        "output_cost": 10000.0,  # $100 per million tokens
                        "context_window": 32768,
                        "active": True,
                        "deprecated": False,
                        "effective_date": "2024-01-01",
                        "description": "Expensive test model",
                    }
                },
            }
        }
    )
