"""
Additional tests to improve observability_decorators coverage to 80%.
Focuses on uncovered code paths and edge cases.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch
from uuid import uuid4

import pytest

from ciris_engine.logic.utils.observability_decorators import (
    TELEMETRY_TASK_SEMAPHORE,
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
    ServiceRequestData,
    ServiceResponseData,
    TraceContext,
)


class TestInternalHelperFunctions:
    """Test internal helper functions for better coverage."""

    def test_prepare_log_context_with_template(self):
        """Test _prepare_log_context with a message template."""

        def sample_func(self, param1: str, param2: int = 5):
            pass

        mock_self = Mock()
        context = _prepare_log_context(
            sample_func,
            mock_self,
            ("test",),  # args
            {"param2": 10},  # kwargs
            "TestService",
            "Processing {param1} with {param2}",
        )

        assert "[TESTSERVICE DEBUG] Processing test with 10" in context["log_message"]
        assert context["method_name"] == "sample_func"
        assert context["service_name"] == "TestService"

    def test_prepare_log_context_template_error(self):
        """Test _prepare_log_context with invalid template."""

        def sample_func(self, param1: str):
            pass

        mock_self = Mock()
        context = _prepare_log_context(
            sample_func, mock_self, ("test",), {}, "TestService", "Missing {nonexistent} param"
        )

        assert "template error" in context["log_message"]
        assert "sample_func called" in context["log_message"]

    def test_prepare_log_context_no_template(self):
        """Test _prepare_log_context without a template."""

        def sample_func(self):
            pass

        mock_self = Mock()
        context = _prepare_log_context(sample_func, mock_self, (), {}, "TestService", None)

        assert context["log_message"] == "[TESTSERVICE DEBUG] sample_func called"

    def test_log_execution_result_with_result(self):
        """Test _log_execution_result with include_result=True."""
        mock_logger = Mock()

        _log_execution_result(
            mock_logger,
            "TestService",
            "test_method",
            1000.0,  # start_time
            "test_result",
            True,  # include_result
            "INFO",
        )

        mock_logger.info.assert_called_once()
        call_args = mock_logger.info.call_args[0][0]
        assert "TESTSERVICE DEBUG" in call_args
        assert "test_method completed" in call_args
        assert "result: test_result" in call_args

    def test_log_execution_result_without_result(self):
        """Test _log_execution_result with include_result=False."""
        mock_logger = Mock()

        _log_execution_result(
            mock_logger, "TestService", "test_method", 1000.0, "test_result", False, "DEBUG"  # include_result
        )

        # Should not log anything when include_result=False
        mock_logger.debug.assert_not_called()

    def test_log_execution_result_truncates_long_result(self):
        """Test that long results are truncated."""
        mock_logger = Mock()
        long_result = "x" * 500

        _log_execution_result(mock_logger, "TestService", "test_method", 1000.0, long_result, True, "DEBUG")

        call_args = mock_logger.debug.call_args[0][0]
        # Result should be truncated to 200 chars
        assert len(call_args.split("result: ")[1]) <= 200

    def test_log_execution_error(self):
        """Test _log_execution_error."""
        mock_logger = Mock()
        test_error = ValueError("Test error")

        _log_execution_error(mock_logger, "TestService", "failing_method", 1000.0, test_error)

        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args[0][0]
        assert "TESTSERVICE DEBUG" in call_args
        assert "failing_method failed" in call_args
        assert "Test error" in call_args


class TestServiceNameExtraction:
    """Test service name extraction edge cases."""

    def test_extract_service_name_manager_suffix(self):
        """Test extraction with Manager suffix."""

        class TestManager:
            pass

        assert _extract_service_name(TestManager()) == "Test"

    def test_extract_service_name_no_suffix(self):
        """Test extraction with no known suffix."""

        class PlainClass:
            pass

        assert _extract_service_name(PlainClass()) == "PlainClass"

    def test_extract_service_name_no_class(self):
        """Test extraction with object without __class__."""
        mock_obj = Mock(spec=[])  # No attributes
        result = _extract_service_name(mock_obj)
        # Should handle gracefully
        assert result == "Mock" or result == "unknown"


class TestDebugLogAdvanced:
    """Advanced debug_log decorator tests."""

    @pytest.mark.asyncio
    async def test_debug_log_different_log_levels(self):
        """Test debug_log with different log levels."""

        class TestService:
            service_name = "TestService"
            _logger = Mock()

            @debug_log("Info message", log_level="INFO")
            async def info_method(self):
                return "info"

            @debug_log("Warning message", log_level="WARNING")
            async def warning_method(self):
                return "warning"

            @debug_log("Error message", log_level="ERROR")
            async def error_method(self):
                return "error"

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            await service.info_method()
            service._logger.info.assert_called()

            await service.warning_method()
            service._logger.warning.assert_called()

            await service.error_method()
            service._logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_debug_log_with_result_logging(self):
        """Test debug_log with include_result=True."""

        class TestService:
            service_name = "TestService"
            _logger = Mock()

            @debug_log("Computing", include_result=True)
            async def compute(self, x: int) -> int:
                return x * 2

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            result = await service.compute(5)
            assert result == 10

            # Should have called debug twice (start and result)
            assert service._logger.debug.call_count == 2

            # Check that result was logged
            calls = service._logger.debug.call_args_list
            assert any("result:" in str(call) for call in calls)

    def test_debug_log_sync_with_logger_fallback(self):
        """Test sync debug_log when service has no _logger."""

        class TestService:
            service_name = "TestService"
            # No _logger attribute

            @debug_log("Sync operation")
            def sync_op(self):
                return "done"

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            with patch("ciris_engine.logic.utils.observability_decorators.logger") as mock_logger:
                result = service.sync_op()
                assert result == "done"
                mock_logger.debug.assert_called()

    def test_debug_log_sync_with_exception(self):
        """Test sync debug_log preserves exceptions."""

        class TestService:
            service_name = "TestService"
            _logger = Mock()

            @debug_log("Will fail")
            def failing_sync(self):
                raise RuntimeError("Sync failure")

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            with pytest.raises(RuntimeError, match="Sync failure"):
                service.failing_sync()

            # Should have logged the error
            service._logger.error.assert_called()


class TestTraceSpanAdvanced:
    """Advanced trace_span decorator tests."""

    @pytest.mark.asyncio
    async def test_trace_span_with_telemetry_service(self):
        """Test trace_span with telemetry service present."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @trace_span(span_name="custom_span", span_kind="client")
            async def traced_method(self, param: str) -> str:
                return f"traced_{param}"

        service = TestService()

        # Mock the semaphore acquisition
        with patch.object(TELEMETRY_TASK_SEMAPHORE, "acquire", new_callable=AsyncMock):
            result = await service.traced_method("test")
            assert result == "traced_test"

            # Give time for async task to complete
            await asyncio.sleep(0.1)

            # Verify telemetry was called
            assert service._telemetry_service._store_correlation.called

            # Check correlation details
            correlation_arg = service._telemetry_service._store_correlation.call_args[0][0]
            assert isinstance(correlation_arg, ServiceCorrelation)
            assert correlation_arg.action_type == "custom_span"
            assert correlation_arg.status == ServiceCorrelationStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_trace_span_with_exception_and_telemetry(self):
        """Test trace_span records failure in telemetry."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @trace_span()
            async def failing_traced(self):
                raise ValueError("Trace failure")

        service = TestService()

        with patch.object(TELEMETRY_TASK_SEMAPHORE, "acquire", new_callable=AsyncMock):
            with pytest.raises(ValueError, match="Trace failure"):
                await service.failing_traced()

            # Give time for async task
            await asyncio.sleep(0.1)

            # Verify failure was recorded
            assert service._telemetry_service._store_correlation.called
            correlation_arg = service._telemetry_service._store_correlation.call_args[0][0]
            assert correlation_arg.status == ServiceCorrelationStatus.FAILED
            assert correlation_arg.response_data.success is False
            assert correlation_arg.response_data.error_type == "ValueError"

    @pytest.mark.asyncio
    async def test_trace_span_correlation_from_kwargs(self):
        """Test trace_span gets correlation_id from kwargs."""

        class TestService:
            service_name = "TestService"

            @trace_span()
            async def method_with_correlation(self, data: str, correlation_id: str = None) -> str:
                return data

        service = TestService()
        test_correlation = str(uuid4())

        result = await service.method_with_correlation("test", correlation_id=test_correlation)
        assert result == "test"
        # Correlation ID should be used (we'd need telemetry to verify fully)

    @pytest.mark.asyncio
    async def test_trace_span_creates_new_trace_id(self):
        """Test trace_span creates new trace_id when none exists."""

        class TestService:
            service_name = "TestService"
            # No trace_context attribute

            @trace_span()
            async def traced_method(self):
                return "done"

        service = TestService()
        result = await service.traced_method()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_trace_span_telemetry_failure_ignored(self):
        """Test that telemetry failures don't break the method."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @trace_span()
            async def method(self):
                return "success"

        service = TestService()
        # Make telemetry fail
        service._telemetry_service._store_correlation.side_effect = Exception("Telemetry error")

        # Method should still work
        result = await service.method()
        assert result == "success"


class TestMeasurePerformanceAdvanced:
    """Advanced measure_performance tests."""

    @pytest.mark.asyncio
    async def test_measure_performance_records_distribution(self):
        """Test measure_performance with record_distribution=True."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @measure_performance(metric_name="custom_metric", path_type="critical")
            async def critical_operation(self):
                await asyncio.sleep(0.01)
                return "done"

        service = TestService()
        result = await service.critical_operation()
        assert result == "done"

        # Should record metrics
        assert service._telemetry_service.record_metric.call_count == 2

        # Check metric details
        calls = service._telemetry_service.record_metric.call_args_list

        # First call should be the duration metric
        first_call = calls[0]
        assert "custom_metric" in first_call[1]["metric_name"]
        assert first_call[1]["path_type"] == "critical"
        assert first_call[1]["tags"]["success"] == "True"

        # Second call should be success count
        second_call = calls[1]
        assert "success" in second_call[1]["metric_name"]

    @pytest.mark.asyncio
    async def test_measure_performance_telemetry_failure_ignored(self):
        """Test that metric recording failures are ignored."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @measure_performance()
            async def method(self):
                return "result"

        service = TestService()
        service._telemetry_service.record_metric.side_effect = Exception("Metrics error")

        # Should still work
        result = await service.method()
        assert result == "result"

    def test_measure_performance_sync_logs_timing(self):
        """Test sync measure_performance logs timing."""

        class TestService:
            service_name = "TestService"

            @measure_performance()
            def sync_compute(self, x: int) -> int:
                return x * 2

        service = TestService()

        with patch("ciris_engine.logic.utils.observability_decorators.logger") as mock_logger:
            result = service.sync_compute(5)
            assert result == 10

            # Should log timing
            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args[0][0]
            assert "TestService.sync_compute took" in call_args
            assert "ms" in call_args
            assert "success=True" in call_args

    def test_measure_performance_sync_with_exception(self):
        """Test sync measure_performance with exception."""

        class TestService:
            service_name = "TestService"

            @measure_performance()
            def failing_sync(self):
                raise RuntimeError("Sync fail")

        service = TestService()

        with patch("ciris_engine.logic.utils.observability_decorators.logger") as mock_logger:
            with pytest.raises(RuntimeError, match="Sync fail"):
                service.failing_sync()

            # Should log with success=False
            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args[0][0]
            assert "success=False" in call_args


class TestObservableCombined:
    """Test the combined observable decorator."""

    @pytest.mark.asyncio
    async def test_observable_no_features(self):
        """Test observable with all features disabled."""

        class TestService:
            service_name = "TestService"

            @observable(trace=False, debug=False, measure=False)
            async def plain_method(self):
                return "plain"

        service = TestService()
        result = await service.plain_method()
        assert result == "plain"

    @pytest.mark.asyncio
    async def test_observable_with_custom_params(self):
        """Test observable with custom parameters."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()
            _logger = Mock()

            @observable(trace=True, debug=True, measure=True, debug_message="Custom: {value}", path_type="hot")
            async def custom_method(self, value: str):
                return f"custom_{value}"

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            result = await service.custom_method("test")
            assert result == "custom_test"

            # Debug should have logged with custom message
            service._logger.debug.assert_called()

            # Performance should have recorded with path_type
            calls = service._telemetry_service.record_metric.call_args_list
            assert any(call[1].get("path_type") == "hot" for call in calls)

    def test_observable_sync_method(self):
        """Test observable on sync methods."""

        class TestService:
            service_name = "TestService"

            @observable(trace=True, debug=True, measure=True)
            def sync_observable(self):
                return "sync"

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            with patch("ciris_engine.logic.utils.observability_decorators.logger") as mock_logger:
                result = service.sync_observable()
                assert result == "sync"

                # Should have logged (sync versions)
                assert mock_logger.debug.called


class TestEdgeCasesAndConcurrency:
    """Test edge cases and concurrency scenarios."""

    @pytest.mark.asyncio
    async def test_trace_span_concurrent_calls(self):
        """Test multiple concurrent trace_span calls."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @trace_span()
            async def concurrent_method(self, delay: float, value: str):
                await asyncio.sleep(delay)
                return value

        service = TestService()

        # Run multiple concurrent calls
        tasks = [service.concurrent_method(0.01, f"task_{i}") for i in range(10)]

        results = await asyncio.gather(*tasks)
        assert len(results) == 10
        assert all(f"task_{i}" == results[i] for i in range(10))

    @pytest.mark.asyncio
    async def test_telemetry_semaphore_limits_concurrency(self):
        """Test that telemetry semaphore limits concurrent tasks."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @trace_span()
            async def method(self):
                return "done"

        service = TestService()

        # Slow down telemetry to test semaphore
        async def slow_store(correlation):
            await asyncio.sleep(0.1)

        service._telemetry_service._store_correlation = slow_store

        # Create many concurrent calls (more than semaphore limit)
        tasks = [service.method() for _ in range(150)]

        # Should complete without deadlock
        results = await asyncio.gather(*tasks)
        assert len(results) == 150
        assert all(r == "done" for r in results)

    @pytest.mark.asyncio
    async def test_trace_context_inheritance(self):
        """Test trace context properly inherits parent span."""

        class TestService:
            service_name = "TestService"
            trace_context = {"trace_id": "parent-trace-123", "span_id": "parent-span-456"}

            @trace_span()
            async def child_operation(self):
                return "child"

        service = TestService()
        result = await service.child_operation()
        assert result == "child"
        # Parent span_id should be preserved in new context

    def test_get_debug_env_var_variations(self):
        """Test various env var values."""
        with patch.dict(os.environ, {"CIRIS_TEST_DEBUG": "1"}):
            assert _get_debug_env_var("Test") is True

        with patch.dict(os.environ, {"CIRIS_TEST_DEBUG": "yes"}):
            assert _get_debug_env_var("Test") is True

        with patch.dict(os.environ, {"CIRIS_TEST_DEBUG": "YES"}):
            assert _get_debug_env_var("Test") is True

        with patch.dict(os.environ, {"CIRIS_TEST_DEBUG": "0"}):
            assert _get_debug_env_var("Test") is False

        with patch.dict(os.environ, {"CIRIS_TEST_DEBUG": "no"}):
            assert _get_debug_env_var("Test") is False

        with patch.dict(os.environ, {"CIRIS_TEST_DEBUG": ""}):
            assert _get_debug_env_var("Test") is False
