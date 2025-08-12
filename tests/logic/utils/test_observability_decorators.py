"""
Comprehensive tests for observability_decorators.py.

Tests tracing, debugging, and performance measurement decorators
that integrate with CIRIS's telemetry infrastructure.
Uses only existing schemas from the codebase.
"""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch
from uuid import uuid4

import pytest

from ciris_engine.logic.utils.observability_decorators import (
    _extract_service_name,
    _get_debug_env_var,
    _log_execution_error,
    _log_execution_result,
    _prepare_log_context,
    debug_log,
    measure_performance,
    observable,
    trace_span,
)
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    TraceContext,
)


class MockService:
    """Mock service class for testing decorators."""

    def __init__(self):
        self.service_name = "test_service"
        self._logger = Mock()
        self._telemetry_service = AsyncMock()
        self.correlation_id = str(uuid4())
        self.trace_context = {
            "trace_id": str(uuid4()),
            "span_id": str(uuid4()),
        }

    @trace_span(span_name="custom_span", capture_args=True)
    async def async_method_with_trace(self, arg1: str, arg2: int = 42) -> str:
        """Async method with trace span."""
        return f"Result: {arg1}-{arg2}"

    @debug_log(message_template="Processing {arg1} with value {arg2}", include_result=True)
    async def async_method_with_debug(self, arg1: str, arg2: int) -> str:
        """Async method with debug logging."""
        return f"Debug: {arg1}-{arg2}"

    @measure_performance(metric_name="custom_metric", path_type="hot")
    async def async_method_with_measure(self, value: int) -> int:
        """Async method with performance measurement."""
        await asyncio.sleep(0.01)  # Simulate some work
        return value * 2

    @observable(trace=True, debug=True, measure=True, debug_message="Observable {arg}")
    async def async_method_observable(self, arg: str) -> str:
        """Async method with all observability features."""
        return f"Observable: {arg}"

    @trace_span()
    def sync_method_with_trace(self, arg: str) -> str:
        """Sync method with trace span."""
        return f"Sync: {arg}"

    @debug_log()
    def sync_method_with_debug(self, arg: str) -> str:
        """Sync method with debug logging."""
        return f"Debug: {arg}"

    @measure_performance()
    def sync_method_with_measure(self, value: int) -> int:
        """Sync method with performance measurement."""
        time.sleep(0.01)  # Simulate some work
        return value * 3

    async def method_that_raises(self):
        """Method that raises an exception."""
        raise ValueError("Test error")


class TestServiceNameExtraction:
    """Tests for service name extraction utilities."""

    def test_extract_service_name_from_attribute(self):
        """Test extracting service name from service_name attribute."""
        obj = Mock()
        obj.service_name = "my_service"
        assert _extract_service_name(obj) == "my_service"

    def test_extract_service_name_from_class_with_suffix(self):
        """Test extracting service name from class name with suffix."""

        class TestService:
            pass

        obj = TestService()
        assert _extract_service_name(obj) == "Test"

        class AnotherHandler:
            pass

        obj = AnotherHandler()
        assert _extract_service_name(obj) == "Another"

        class SomeManager:
            pass

        obj = SomeManager()
        assert _extract_service_name(obj) == "Some"

    def test_extract_service_name_from_class_without_suffix(self):
        """Test extracting service name from class name without suffix."""

        class CustomClass:
            pass

        obj = CustomClass()
        assert _extract_service_name(obj) == "CustomClass"

    def test_extract_service_name_fallback(self):
        """Test fallback when service name cannot be determined."""
        obj = object()  # No class name or service_name attribute
        result = _extract_service_name(obj)
        assert result == "object" or result == "unknown"


class TestDebugEnvironmentVariable:
    """Tests for debug environment variable checking."""

    def test_get_debug_env_var_true(self):
        """Test debug env var when set to true."""
        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "true"}):
            assert _get_debug_env_var("test_service") is True

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "1"}):
            assert _get_debug_env_var("test_service") is True

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "yes"}):
            assert _get_debug_env_var("test_service") is True

    def test_get_debug_env_var_false(self):
        """Test debug env var when not set or false."""
        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "false"}):
            assert _get_debug_env_var("test_service") is False

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "0"}):
            assert _get_debug_env_var("test_service") is False

        with patch.dict(os.environ, {}):  # Not set
            assert _get_debug_env_var("test_service") is False


class TestLogHelpers:
    """Tests for logging helper functions."""

    def test_prepare_log_context_with_template(self):
        """Test preparing log context with message template."""

        def sample_method(self, arg1: str, arg2: int = 10):
            pass

        obj = Mock()
        context = _prepare_log_context(
            sample_method, obj, ("test",), {"arg2": 20}, "service", "Method {method_name} called with {arg1} and {arg2}"
        )

        assert "[SERVICE DEBUG] Method sample_method called with test and 20" in context["log_message"]
        assert context["method_name"] == "sample_method"
        assert context["service_name"] == "service"

    def test_prepare_log_context_without_template(self):
        """Test preparing log context without message template."""

        def sample_method(self):
            pass

        obj = Mock()
        context = _prepare_log_context(sample_method, obj, (), {}, "service", None)

        assert context["log_message"] == "[SERVICE DEBUG] sample_method called"

    def test_log_execution_result(self):
        """Test logging execution result."""
        mock_logger = Mock()
        _log_execution_result(
            mock_logger, "service", "method", time.time() - 0.1, "test result", True, "INFO"  # 100ms ago
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "SERVICE DEBUG" in call_args
        assert "method completed" in call_args
        assert "test result" in call_args

    def test_log_execution_error(self):
        """Test logging execution error."""
        mock_logger = Mock()
        error = ValueError("Test error")
        _log_execution_error(mock_logger, "service", "method", time.time() - 0.05, error)  # 50ms ago

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        assert "SERVICE DEBUG" in call_args
        assert "method failed" in call_args
        assert "Test error" in call_args


class TestTraceSpanDecorator:
    """Tests for trace_span decorator."""

    @pytest.mark.asyncio
    async def test_trace_span_async_success(self):
        """Test trace span with successful async execution."""
        service = MockService()

        result = await service.async_method_with_trace("test", 100)

        assert result == "Result: test-100"
        # Give async tasks a moment to complete
        await asyncio.sleep(0.01)
        # Telemetry service should have been called
        assert service._telemetry_service._store_correlation.called

    @pytest.mark.asyncio
    async def test_trace_span_async_with_correlation_context(self):
        """Test trace span using existing correlation context."""
        service = MockService()
        service.correlation_id = "test_correlation_123"
        service.trace_context = {
            "trace_id": "test_trace_456",
            "span_id": "parent_span_789",
        }

        result = await service.async_method_with_trace("value")

        assert result == "Result: value-42"

    @pytest.mark.asyncio
    async def test_trace_span_async_failure(self):
        """Test trace span with failing async method."""
        service = MockService()

        @trace_span()
        async def failing_method(self):
            raise ValueError("Test failure")

        # Bind method to service
        bound_method = failing_method.__get__(service, MockService)

        with pytest.raises(ValueError) as exc_info:
            await bound_method()

        assert "Test failure" in str(exc_info.value)

    def test_trace_span_sync_method(self):
        """Test trace span with sync method."""
        service = MockService()

        with patch("ciris_engine.logic.utils.observability_decorators.logger") as mock_logger:
            result = service.sync_method_with_trace("test")

        assert result == "Sync: test"
        # Should log that correlation is disabled for sync
        mock_logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_trace_span_without_telemetry_service(self):
        """Test trace span when telemetry service is not available."""
        service = MockService()
        del service._telemetry_service  # Remove telemetry service

        # Should still work without telemetry
        result = await service.async_method_with_trace("test")
        assert result == "Result: test-42"


class TestDebugLogDecorator:
    """Tests for debug_log decorator."""

    @pytest.mark.asyncio
    async def test_debug_log_async_with_env_enabled(self):
        """Test debug logging with environment variable enabled."""
        service = MockService()

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "true"}):
            result = await service.async_method_with_debug("arg1", 123)

        assert result == "Debug: arg1-123"
        service._logger.debug.assert_called()

        # Check that result was logged
        call_args = [str(arg) for call in service._logger.debug.call_args_list for arg in call[0]]
        assert any("arg1" in arg for arg in call_args)

    @pytest.mark.asyncio
    async def test_debug_log_async_with_env_disabled(self):
        """Test debug logging with environment variable disabled."""
        service = MockService()

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "false"}):
            result = await service.async_method_with_debug("arg1", 123)

        assert result == "Debug: arg1-123"
        # Logger should not be called when debug is disabled
        service._logger.debug.assert_not_called()

    def test_debug_log_sync_method(self):
        """Test debug logging with sync method."""
        service = MockService()

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "true"}):
            result = service.sync_method_with_debug("test_arg")

        assert result == "Debug: test_arg"
        service._logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_debug_log_with_exception(self):
        """Test debug logging when method raises exception."""
        service = MockService()

        @debug_log(include_result=True)
        async def raising_method(self):
            raise RuntimeError("Test error")

        bound_method = raising_method.__get__(service, MockService)

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "true"}):
            with pytest.raises(RuntimeError):
                await bound_method()

        service._logger.error.assert_called()
        error_call = service._logger.error.call_args[0][0]
        assert "Test error" in error_call


class TestMeasurePerformanceDecorator:
    """Tests for measure_performance decorator."""

    @pytest.mark.asyncio
    async def test_measure_performance_async(self):
        """Test performance measurement with async method."""
        service = MockService()

        result = await service.async_method_with_measure(5)

        assert result == 10
        # Telemetry should record metrics
        assert service._telemetry_service.record_metric.called

        # Check metric calls
        calls = service._telemetry_service.record_metric.call_args_list
        assert len(calls) >= 2  # Duration metric and success metric

        # Check duration metric
        duration_call = calls[0]
        assert "custom_metric" in duration_call[1]["metric_name"]
        assert duration_call[1]["value"] > 0  # Should have some duration

        # Check success metric
        success_call = calls[1]
        assert "success" in success_call[1]["metric_name"]

    @pytest.mark.asyncio
    async def test_measure_performance_async_failure(self):
        """Test performance measurement when method fails."""
        service = MockService()

        @measure_performance()
        async def failing_method(self):
            raise ValueError("Test error")

        bound_method = failing_method.__get__(service, MockService)

        with pytest.raises(ValueError):
            await bound_method()

        # Should still record metrics even on failure
        assert service._telemetry_service.record_metric.called

        # Check that failure metric was recorded
        calls = service._telemetry_service.record_metric.call_args_list
        assert any("failure" in str(call) for call in calls)

    def test_measure_performance_sync(self):
        """Test performance measurement with sync method."""
        service = MockService()

        with patch("ciris_engine.logic.utils.observability_decorators.logger") as mock_logger:
            result = service.sync_method_with_measure(3)

        assert result == 9
        # Should log performance for sync methods
        mock_logger.debug.assert_called()
        debug_call = mock_logger.debug.call_args[0][0]
        assert "took" in debug_call
        assert "ms" in debug_call

    @pytest.mark.asyncio
    async def test_measure_performance_without_telemetry(self):
        """Test performance measurement without telemetry service."""
        service = MockService()
        del service._telemetry_service

        # Should still work without telemetry
        result = await service.async_method_with_measure(7)
        assert result == 14


class TestObservableDecorator:
    """Tests for the combined observable decorator."""

    @pytest.mark.asyncio
    async def test_observable_all_features(self):
        """Test observable decorator with all features enabled."""
        service = MockService()

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "true"}):
            result = await service.async_method_observable("test_value")

        assert result == "Observable: test_value"

        # Give async tasks a moment to complete
        await asyncio.sleep(0.01)

        # Should have called telemetry for trace and metrics
        assert service._telemetry_service._store_correlation.called
        assert service._telemetry_service.record_metric.called

        # Should have logged debug info
        service._logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_observable_selective_features(self):
        """Test observable decorator with selective features."""
        service = MockService()

        @observable(trace=False, debug=True, measure=False)
        async def partial_observable(self, arg: str) -> str:
            return f"Partial: {arg}"

        bound_method = partial_observable.__get__(service, MockService)

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "true"}):
            result = await bound_method("test")

        assert result == "Partial: test"

        # Should not have trace or metrics
        assert not service._telemetry_service._store_correlation.called
        assert not service._telemetry_service.record_metric.called

        # Should have debug logging
        service._logger.debug.assert_called()


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_decorator_with_no_self(self):
        """Test decorator on function without self parameter."""

        @trace_span()
        async def standalone_function(arg: str) -> str:
            return f"Standalone: {arg}"

        # Should handle missing self gracefully
        result = await standalone_function("test")
        assert result == "Standalone: test"

    @pytest.mark.asyncio
    async def test_telemetry_failure_doesnt_break_method(self):
        """Test that telemetry failures don't break the decorated method."""
        service = MockService()
        service._telemetry_service._store_correlation.side_effect = Exception("Telemetry error")
        service._telemetry_service.record_metric.side_effect = Exception("Metric error")

        # Methods should still work even if telemetry fails
        result = await service.async_method_with_trace("test")
        assert result == "Result: test-42"

        result = await service.async_method_with_measure(5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_correlation_from_kwargs(self):
        """Test getting correlation ID from kwargs."""
        service = MockService()
        del service.correlation_id  # Remove from self

        @trace_span()
        async def method_with_correlation(self, arg: str, correlation_id: str = None) -> str:
            return f"Result: {arg}"

        bound_method = method_with_correlation.__get__(service, MockService)

        result = await bound_method("test", correlation_id="kwarg_correlation_123")
        assert result == "Result: test"

    def test_sync_wrapper_selection(self):
        """Test that sync methods get sync wrapper."""
        service = MockService()

        # These should use sync wrappers
        assert hasattr(service.sync_method_with_trace, "__wrapped__")
        assert hasattr(service.sync_method_with_debug, "__wrapped__")
        assert hasattr(service.sync_method_with_measure, "__wrapped__")

    @pytest.mark.asyncio
    async def test_async_wrapper_selection(self):
        """Test that async methods get async wrapper."""
        service = MockService()

        # These should use async wrappers
        assert asyncio.iscoroutinefunction(service.async_method_with_trace)
        assert asyncio.iscoroutinefunction(service.async_method_with_debug)
        assert asyncio.iscoroutinefunction(service.async_method_with_measure)


class TestIntegration:
    """Integration tests for multiple decorators."""

    @pytest.mark.asyncio
    async def test_multiple_decorators_stacked(self):
        """Test multiple decorators stacked on same method."""
        service = MockService()

        @measure_performance()
        @debug_log(include_result=True)
        @trace_span()
        async def multi_decorated(self, value: int) -> int:
            await asyncio.sleep(0.001)
            return value * 10

        bound_method = multi_decorated.__get__(service, MockService)

        with patch.dict(os.environ, {"CIRIS_TEST_SERVICE_DEBUG": "true"}):
            result = await bound_method(5)

        assert result == 50

        # Give async tasks a moment to complete
        await asyncio.sleep(0.01)

        # All decorators should have executed
        assert service._telemetry_service._store_correlation.called
        assert service._telemetry_service.record_metric.called
        service._logger.debug.assert_called()

    @pytest.mark.asyncio
    async def test_decorator_preserves_method_metadata(self):
        """Test that decorators preserve method metadata."""
        service = MockService()

        # Check that decorated methods preserve their names and docs
        assert service.async_method_with_trace.__name__ == "async_method_with_trace"
        assert "trace span" in service.async_method_with_trace.__doc__.lower()

        assert service.async_method_with_debug.__name__ == "async_method_with_debug"
        assert "debug logging" in service.async_method_with_debug.__doc__.lower()
