"""Comprehensive unit tests for LLM Service with focus on achieving 80% coverage."""

import asyncio
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIConnectionError, APIStatusError, RateLimitError
from pydantic import BaseModel

from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError
from ciris_engine.logic.services.runtime.llm_service import OpenAICompatibleClient, OpenAIConfig
from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.protocols_core import LLMStatus
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.core import ServiceCapabilities

# No need to add path since we're in the proper test structure


class TestResponse(BaseModel):
    """Test response model."""

    message: str
    status: str = "ok"


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    service = MagicMock(spec=TimeServiceProtocol)
    service.now.return_value = datetime(2025, 1, 1, 12, 0, 0)
    service.now_iso.return_value = "2025-01-01T12:00:00"
    return service


@pytest.fixture
def mock_telemetry_service():
    """Create a mock telemetry service."""
    service = MagicMock(spec=TelemetryServiceProtocol)
    service.record_metric = AsyncMock()
    service.log_event = AsyncMock()
    return service


@pytest.fixture
def llm_config():
    """Create a test LLM configuration."""
    return OpenAIConfig(
        api_key="test-key-12345",
        model_name="gpt-4o-mini",
        base_url=None,
        instructor_mode="JSON",
        max_retries=3,
        timeout_seconds=30,
    )


@pytest.fixture
def llm_service(llm_config, mock_time_service, mock_telemetry_service):
    """Create an LLM service for testing with mocked dependencies."""
    # Mock environment to prevent mock LLM detection
    with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False):
        with patch("sys.argv", []):
            # Mock the OpenAI client to avoid authentication errors
            with patch("ciris_engine.logic.services.runtime.llm_service.AsyncOpenAI") as mock_openai:
                with patch("ciris_engine.logic.services.runtime.llm_service.instructor") as mock_instructor:
                    # Set up mock clients
                    mock_client = MagicMock()
                    mock_client.close = AsyncMock()
                    mock_openai.return_value = mock_client

                    mock_instruct_client = MagicMock()
                    mock_instruct_client.chat = MagicMock()
                    mock_instruct_client.chat.completions = MagicMock()
                    mock_instruct_client.chat.completions.create_with_completion = AsyncMock()
                    mock_instructor.from_openai.return_value = mock_instruct_client
                    mock_instructor.Mode.JSON = "JSON"
                    mock_instructor.Mode.TOOLS = "TOOLS"

                    service = OpenAICompatibleClient(
                        config=llm_config,
                        time_service=mock_time_service,
                        telemetry_service=mock_telemetry_service,
                        service_name="test_llm_service",
                        version="1.0.0",
                    )

                    # Ensure the mocked clients are set
                    service.client = mock_client
                    service.instruct_client = mock_instruct_client

                    # Set up proper response times for metrics
                    service._response_times = []

                    return service


class TestOpenAICompatibleClient:
    """Test suite for OpenAICompatibleClient."""

    def test_initialization(self, llm_config, mock_time_service, mock_telemetry_service):
        """Test service initialization with various configurations."""
        # Test normal initialization
        with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False):
            with patch("sys.argv", []):
                with patch("ciris_engine.logic.services.runtime.llm_service.AsyncOpenAI"):
                    with patch("ciris_engine.logic.services.runtime.llm_service.instructor"):
                        service = OpenAICompatibleClient(
                            config=llm_config, time_service=mock_time_service, telemetry_service=mock_telemetry_service
                        )
                        assert service.model_name == "gpt-4o-mini"
                        assert service.max_retries == 3
                        assert service.base_delay == 1.0
                        assert service.max_delay == 30.0
                        # Cache has been removed per policy

    def test_initialization_mock_llm_error(self, llm_config, mock_time_service):
        """Test that initialization fails when mock LLM is enabled."""
        with patch.dict(os.environ, {"MOCK_LLM": "1"}):
            with pytest.raises(RuntimeError) as exc_info:
                OpenAICompatibleClient(config=llm_config, time_service=mock_time_service)
            assert "CRITICAL BUG" in str(exc_info.value)
            assert "mock LLM is enabled" in str(exc_info.value)

    def test_initialization_no_api_key(self, mock_time_service):
        """Test that initialization fails without API key."""
        config = OpenAIConfig(api_key="")
        with patch.dict(os.environ, {"MOCK_LLM": ""}, clear=False):
            with patch("sys.argv", []):
                with pytest.raises(RuntimeError) as exc_info:
                    OpenAICompatibleClient(config=config, time_service=mock_time_service)
                assert "No OpenAI API key found" in str(exc_info.value)

    def test_get_service_type(self, llm_service):
        """Test get_service_type returns correct enum."""
        assert llm_service.get_service_type() == ServiceType.LLM

    def test_get_actions(self, llm_service):
        """Test _get_actions returns correct action list."""
        actions = llm_service._get_actions()
        assert len(actions) == 1
        assert "call_llm_structured" in actions[0]

    def test_check_dependencies(self, llm_service):
        """Test dependency checking."""
        assert llm_service._check_dependencies() is True

        # Test with missing API key
        llm_service.openai_config.api_key = ""
        assert llm_service._check_dependencies() is False

        # Test with missing circuit breaker
        llm_service.openai_config.api_key = "test-key"
        llm_service.circuit_breaker = None
        assert llm_service._check_dependencies() is False

    def test_register_dependencies(self, llm_service):
        """Test dependency registration."""
        # Clear dependencies first
        llm_service._dependencies.clear()

        # Register dependencies
        llm_service._register_dependencies()

        # Should have TimeService from BaseService and TelemetryService
        assert "TimeService" in llm_service._dependencies
        assert "TelemetryService" in llm_service._dependencies

    @pytest.mark.asyncio
    async def test_lifecycle(self, llm_service):
        """Test service lifecycle methods."""
        # Start
        await llm_service.start()
        assert llm_service._started

        # Stop
        await llm_service.stop()
        assert not llm_service._started
        llm_service.client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_healthy(self, llm_service):
        """Test health check including circuit breaker."""
        # Mock the parent is_healthy method to return True
        with patch("ciris_engine.logic.services.base_service.BaseService.is_healthy", return_value=True):
            # Initially healthy
            assert await llm_service.is_healthy() is True

            # Simulate circuit breaker open
            llm_service.circuit_breaker.is_available = MagicMock(return_value=False)
            assert await llm_service.is_healthy() is False

    def test_get_capabilities(self, llm_service):
        """Test get_capabilities with custom metadata."""
        caps = llm_service.get_capabilities()
        assert isinstance(caps, ServiceCapabilities)
        assert caps.service_name == "test_llm_service"
        assert caps.version == "1.0.0"
        assert len(caps.actions) > 0

        # Check custom metadata
        assert caps.metadata["model"] == "gpt-4o-mini"
        assert caps.metadata["instructor_mode"] == "JSON"
        assert caps.metadata["timeout_seconds"] == 30
        assert caps.metadata["max_retries"] == 3
        assert "circuit_breaker_state" in caps.metadata

    def test_collect_custom_metrics(self, llm_service):
        """Test custom metrics collection."""
        # Mock circuit breaker stats
        llm_service.circuit_breaker.get_stats = MagicMock(
            return_value={
                "state": "closed",
                "consecutive_failures": 2,
                "recovery_attempts": 1,
                "last_failure_age": 60,
                "success_rate": 0.95,
                "call_count": 100,
                "failure_count": 5,
            }
        )

        # Set response times for metrics
        llm_service._response_times = [100, 200, 150]

        metrics = llm_service._collect_custom_metrics()

        # Check circuit breaker metrics
        assert metrics["circuit_breaker_state"] == 0.0  # closed = 0.0
        assert metrics["consecutive_failures"] == 2.0
        assert metrics["recovery_attempts"] == 1.0
        assert metrics["last_failure_age_seconds"] == 60.0
        assert metrics["success_rate"] == 0.95
        assert metrics["call_count"] == 100.0
        assert metrics["failure_count"] == 5.0

        # Check response time metrics
        assert "avg_response_time_ms" in metrics
        assert metrics["avg_response_time_ms"] == 150.0  # average of [100, 200, 150]

        # Check model pricing
        assert metrics["model_cost_per_1k_tokens"] == 0.15  # gpt-4o-mini

        # Check configuration metrics
        assert metrics["model_timeout_seconds"] == 30.0
        assert metrics["model_max_retries"] == 3.0

    def test_extract_json(self, llm_service):
        """Test JSON extraction from various response formats."""
        # Test with properly formatted JSON in code block
        raw = '```json\n{"result": "test", "value": 42}\n```'
        result = llm_service._extract_json(raw)
        assert result.success is True
        assert result.data["result"] == "test"
        assert result.data["value"] == 42

        # Test with plain JSON
        raw = '{"message": "hello"}'
        result = llm_service._extract_json(raw)
        assert result.success is True
        assert result.data["message"] == "hello"

        # Test with single quotes (should be converted)
        raw = "{'key': 'value'}"
        result = llm_service._extract_json(raw)
        assert result.success is True
        assert result.data["key"] == "value"

        # Test with invalid JSON
        raw = "not json at all"
        result = llm_service._extract_json(raw)
        assert result.success is False
        assert result.error == "Failed to parse JSON"
        assert "not json at all" in result.raw_content

    @pytest.mark.asyncio
    async def test_call_llm_structured_success(self, llm_service):
        """Test successful structured LLM call."""
        # Mock the response
        mock_result = TestResponse(message="Hello", status="success")
        mock_completion = MagicMock()
        mock_completion.usage = MagicMock(total_tokens=150, prompt_tokens=100, completion_tokens=50)

        llm_service.instruct_client.chat.completions.create_with_completion.return_value = (
            mock_result,
            mock_completion,
        )

        messages = [{"role": "user", "content": "Test message"}]
        result, usage = await llm_service.call_llm_structured(
            messages=messages, response_model=TestResponse, max_tokens=1024, temperature=0.7
        )

        assert isinstance(result, TestResponse)
        assert result.message == "Hello"
        assert result.status == "success"

        assert isinstance(usage, ResourceUsage)
        assert usage.tokens_used == 150
        assert usage.tokens_input == 100
        assert usage.tokens_output == 50
        assert usage.model_used == "gpt-4o-mini"

        # Check telemetry was recorded
        llm_service.telemetry_service.record_metric.assert_any_call("llm_tokens_used", 150)
        llm_service.telemetry_service.record_metric.assert_any_call("llm_api_call_structured")

        # Check circuit breaker recorded success (it's a real CircuitBreaker, not a mock)
        # So we can't assert_called_once on it

    @pytest.mark.asyncio
    async def test_call_llm_structured_retry_logic(self, llm_service):
        """Test retry logic for transient failures."""
        call_count = 0

        async def mock_create(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise APIConnectionError(request=MagicMock(), message="Connection failed")

            mock_completion = MagicMock()
            mock_completion.usage = MagicMock(total_tokens=100, prompt_tokens=80, completion_tokens=20)
            return TestResponse(message="Success after retry"), mock_completion

        llm_service.instruct_client.chat.completions.create_with_completion = mock_create

        result, usage = await llm_service.call_llm_structured(
            messages=[{"role": "user", "content": "Test"}],
            response_model=TestResponse,
            max_tokens=1024,
            temperature=0.0,
        )

        assert result.message == "Success after retry"
        assert call_count == 3  # Failed twice, succeeded on third

    @pytest.mark.asyncio
    async def test_call_llm_structured_circuit_breaker_open(self, llm_service):
        """Test behavior when circuit breaker is open."""
        llm_service.circuit_breaker.check_and_raise = MagicMock(
            side_effect=CircuitBreakerError("Circuit breaker is open")
        )

        with pytest.raises(CircuitBreakerError) as exc_info:
            await llm_service.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=TestResponse
            )

        assert "Circuit breaker is open" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_llm_structured_timeout_error(self, llm_service):
        """Test handling of timeout errors."""
        # For now, test with a generic timeout error since we can't mock instructor exceptions
        llm_service.instruct_client.chat.completions.create_with_completion = AsyncMock(
            side_effect=TimeoutError("Request timed out")
        )

        # Test timeout error handling
        with pytest.raises(TimeoutError) as exc_info:
            await llm_service.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=TestResponse
            )

        assert "Request timed out" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_call_llm_structured_non_retryable_error(self, llm_service):
        """Test handling of non-retryable errors."""
        # Create a mock response object
        mock_response = MagicMock()
        mock_response.status_code = 400

        error = APIStatusError(message="Bad request", response=mock_response, body={})

        llm_service.instruct_client.chat.completions.create_with_completion = AsyncMock(side_effect=error)

        with pytest.raises(APIStatusError) as exc_info:
            await llm_service.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=TestResponse
            )

        # Should fail immediately without retry
        llm_service.instruct_client.chat.completions.create_with_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_llm_structured_max_retries_exceeded(self, llm_service):
        """Test max retries exceeded."""
        llm_service.instruct_client.chat.completions.create_with_completion = AsyncMock(
            side_effect=RateLimitError(message="Rate limit exceeded", response=MagicMock(), body={})
        )

        with pytest.raises(RateLimitError):
            await llm_service.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=TestResponse
            )

        # Should retry max_retries times
        assert llm_service.instruct_client.chat.completions.create_with_completion.call_count == 3

    def test_get_status(self, llm_service):
        """Test _get_status method."""
        # Mock circuit breaker stats
        llm_service.circuit_breaker.get_stats = MagicMock(
            return_value={"call_count": 100, "failure_count": 5, "success_rate": 0.95}
        )
        llm_service.circuit_breaker.is_available = MagicMock(return_value=True)

        # Add mock response times
        llm_service._response_times = [100, 200, 150]

        status = llm_service._get_status()

        assert isinstance(status, LLMStatus)
        assert status.available is True
        assert status.model == "gpt-4o-mini"
        assert status.usage.total_calls == 100
        assert status.usage.failed_calls == 5
        assert status.usage.success_rate == 0.95
        assert status.response_time_avg == 150.0

    @pytest.mark.asyncio
    async def test_retry_with_backoff(self, llm_service):
        """Test exponential backoff retry logic."""
        call_times = []

        async def mock_func(*args, **kwargs):
            call_times.append(asyncio.get_event_loop().time())
            if len(call_times) < 3:
                raise APIConnectionError(request=MagicMock(), message="Connection failed")
            return TestResponse(message="Success"), MagicMock()

        # Mock sleep to track delays
        sleep_calls = []
        original_sleep = asyncio.sleep

        async def mock_sleep(delay):
            sleep_calls.append(delay)
            return await original_sleep(0.01)  # Short sleep for testing

        with patch("asyncio.sleep", mock_sleep):
            result, _ = await llm_service._retry_with_backoff(mock_func, [], TestResponse, 1024, 0.0)

        assert result.message == "Success"
        assert len(sleep_calls) == 2  # Two retries before success
        assert sleep_calls[0] == 1.0  # First retry: base_delay * 2^0
        assert sleep_calls[1] == 2.0  # Second retry: base_delay * 2^1

    @pytest.mark.asyncio
    async def test_cost_calculation_models(self, llm_service):
        """Test cost calculation for different models."""
        test_cases = [
            ("gpt-4o-mini", 0.15, 0.60),
            ("gpt-4o", 2.50, 10.00),
            ("gpt-4-turbo", 10.00, 30.00),
            ("gpt-3.5-turbo", 0.50, 1.50),
            ("llama-17B", 0.10, 0.10),
            ("claude-3-opus", 3.00, 15.00),
            ("unknown-model", 0.20, 0.20),
        ]

        for model_name, expected_input_cost_per_1k, expected_output_cost_per_1k in test_cases:
            llm_service.model_name = model_name

            mock_completion = MagicMock()
            mock_completion.usage = MagicMock(total_tokens=2000, prompt_tokens=1000, completion_tokens=1000)

            llm_service.instruct_client.chat.completions.create_with_completion.return_value = (
                TestResponse(message="Test"),
                mock_completion,
            )

            _, usage = await llm_service.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=TestResponse
            )

            # Calculate expected costs (per million tokens)
            expected_input_cost = (1000 / 1_000_000) * expected_input_cost_per_1k * 100
            expected_output_cost = (1000 / 1_000_000) * expected_output_cost_per_1k * 100
            expected_total = expected_input_cost + expected_output_cost

            assert abs(usage.cost_cents - expected_total) < 0.01

    @pytest.mark.asyncio
    async def test_carbon_footprint_calculation(self, llm_service):
        """Test carbon footprint calculation for different models."""
        test_cases = [
            ("llama-17B", 0.0002),  # Lower energy use
            ("gpt-4", 0.0005),  # Higher energy use
            ("gpt-3.5-turbo", 0.0003),  # Default
        ]

        for model_name, energy_per_1k_tokens in test_cases:
            llm_service.model_name = model_name

            mock_completion = MagicMock()
            mock_completion.usage = MagicMock(total_tokens=1000, prompt_tokens=500, completion_tokens=500)

            llm_service.instruct_client.chat.completions.create_with_completion.return_value = (
                TestResponse(message="Test"),
                mock_completion,
            )

            _, usage = await llm_service.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=TestResponse
            )

            expected_energy = energy_per_1k_tokens
            expected_carbon = expected_energy * 500.0  # 500g CO2 per kWh

            assert abs(usage.energy_kwh - expected_energy) < 0.0001
            assert abs(usage.carbon_grams - expected_carbon) < 0.1

    def test_initialization_with_tools_mode(self, mock_time_service):
        """Test initialization with TOOLS instructor mode."""
        config = OpenAIConfig(api_key="test-key", instructor_mode="TOOLS")

        # Remove MOCK_LLM from environment to avoid RuntimeError
        mock_env = {}
        if "MOCK_LLM" in os.environ:
            mock_env = {k: v for k, v in os.environ.items() if k != "MOCK_LLM"}
        
        with patch.dict(os.environ, mock_env, clear=True):
            with patch("sys.argv", []):
                with patch("ciris_engine.logic.services.runtime.llm_service.service.AsyncOpenAI"):
                    with patch("ciris_engine.logic.services.runtime.llm_service.service.instructor") as mock_instructor:
                        mock_instructor.Mode.TOOLS = "TOOLS"
                        mock_instructor.from_openai = MagicMock()

                        service = OpenAICompatibleClient(config=config, time_service=mock_time_service)

                        # Verify TOOLS mode was used
                        mock_instructor.from_openai.assert_called_once()
                        call_args = mock_instructor.from_openai.call_args
                        assert call_args[1]["mode"] == "TOOLS"

    def test_initialization_with_base_url(self, mock_time_service):
        """Test initialization with custom base URL."""
        config = OpenAIConfig(api_key="test-key", base_url="https://custom.openai.com/v1")

        # Remove MOCK_LLM from environment to avoid RuntimeError
        mock_env = {}
        if "MOCK_LLM" in os.environ:
            mock_env = {k: v for k, v in os.environ.items() if k != "MOCK_LLM"}
        
        with patch.dict(os.environ, mock_env, clear=True):
            with patch("sys.argv", []):
                with patch("ciris_engine.logic.services.runtime.llm_service.service.AsyncOpenAI") as mock_openai:
                    with patch("ciris_engine.logic.services.runtime.llm_service.service.instructor"):
                        service = OpenAICompatibleClient(config=config, time_service=mock_time_service)

                        # Verify base_url was passed to AsyncOpenAI
                        mock_openai.assert_called_once()
                        call_kwargs = mock_openai.call_args[1]
                        assert call_kwargs["base_url"] == "https://custom.openai.com/v1"

    @pytest.mark.asyncio
    async def test_error_tracking(self, llm_service):
        """Test that errors are tracked in base service."""
        error = APIConnectionError(request=MagicMock(), message="Test error")

        llm_service.instruct_client.chat.completions.create_with_completion = AsyncMock(side_effect=error)

        with pytest.raises(APIConnectionError):
            await llm_service.call_llm_structured(
                messages=[{"role": "user", "content": "Test"}], response_model=TestResponse
            )

        # Check error was tracked
        status = llm_service.get_status()
        assert status.metrics["error_count"] > 0

    def test_get_client_private_method(self, llm_service):
        """Test _get_client returns the OpenAI client."""
        client = llm_service._get_client()
        assert client is llm_service.client

    def test_extract_json_from_response_private_method(self, llm_service):
        """Test _extract_json_from_response delegates to _extract_json."""
        raw = '{"test": "value"}'
        result = llm_service._extract_json_from_response(raw)
        assert result.success is True
        assert result.data["test"] == "value"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
