"""
Essential tests for observability decorators.
Focus on behavior, not implementation details.
"""

import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.utils.observability_decorators import (
    _extract_service_name,
    _get_debug_env_var,
    debug_log,
    measure_performance,
    observable,
    trace_span,
)


class TestDebugLogBehavior:
    """Test that debug_log respects environment variables and doesn't break methods."""

    @pytest.mark.asyncio
    async def test_decorator_respects_env_var(self):
        """Test that decorator only logs when env var is set."""

        class TestService:
            service_name = "TestService"

            @debug_log("Processing: {value}")
            async def process(self, value: str) -> str:
                return f"processed_{value}"

        service = TestService()

        # Should work with debug OFF
        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "false"}):
            result = await service.process("test")
            assert result == "processed_test"

        # Should work with debug ON
        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            result = await service.process("test")
            assert result == "processed_test"

    def test_sync_method_support(self):
        """Test that decorator works with sync methods."""

        class TestService:
            service_name = "TestService"

            @debug_log("Sync processing")
            def process_sync(self, value: str) -> str:
                return f"sync_{value}"

        service = TestService()
        result = service.process_sync("test")
        assert result == "sync_test"


class TestMeasurePerformanceBehavior:
    """Test that measure_performance doesn't break methods."""

    @pytest.mark.asyncio
    async def test_decorator_with_telemetry(self):
        """Test that decorator works when telemetry service exists."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @measure_performance(path_type="hot")
            async def compute(self, x: int, y: int) -> int:
                return x + y

        service = TestService()
        result = await service.compute(5, 3)
        assert result == 8

        # Verify telemetry was called
        assert service._telemetry_service.record_metric.called

    @pytest.mark.asyncio
    async def test_decorator_without_telemetry(self):
        """Test that decorator works without telemetry service."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = None

            @measure_performance()
            async def compute(self, x: int, y: int) -> int:
                return x + y

        service = TestService()
        result = await service.compute(5, 3)
        assert result == 8  # Should not crash


class TestTraceSpanBehavior:
    """Test that trace_span decorator works correctly."""

    @pytest.mark.asyncio
    async def test_trace_span_basic(self):
        """Test basic trace span functionality."""

        class TestService:
            service_name = "TestService"

            @trace_span(span_name="test_operation")
            async def operation(self, param: str) -> str:
                return f"result_{param}"

        service = TestService()
        result = await service.operation("test")
        assert result == "result_test"

    @pytest.mark.asyncio
    async def test_trace_span_with_context(self):
        """Test trace span with existing context."""

        class TestService:
            service_name = "TestService"
            correlation_id = "test-correlation-123"
            trace_context = {"trace_id": "trace-456", "span_id": "parent-span-789"}

            @trace_span()
            async def operation(self, param: str) -> str:
                return f"traced_{param}"

        service = TestService()
        result = await service.operation("value")
        assert result == "traced_value"

    def test_trace_span_sync_method(self):
        """Test trace span on sync methods."""

        class TestService:
            service_name = "TestService"

            @trace_span()
            def sync_operation(self, x: int) -> int:
                return x * 2

        service = TestService()
        result = service.sync_operation(5)
        assert result == 10


class TestObservableDecorator:
    """Test the combined observable decorator."""

    @pytest.mark.asyncio
    async def test_observable_all_features(self):
        """Test observable with all features enabled."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @observable(trace=True, debug=True, measure=True, debug_message="Processing: {value}")
            async def process_all(self, value: str) -> str:
                return f"all_{value}"

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            service = TestService()
            result = await service.process_all("test")
            assert result == "all_test"
            assert service._telemetry_service.record_metric.called

    @pytest.mark.asyncio
    async def test_observable_partial_features(self):
        """Test observable with only some features."""

        class TestService:
            service_name = "TestService"

            @observable(trace=False, debug=False, measure=True)
            async def process_partial(self, value: str) -> str:
                return f"partial_{value}"

        service = TestService()
        result = await service.process_partial("test")
        assert result == "partial_test"


class TestHelperFunctions:
    """Test helper functions."""

    def test_get_debug_env_var(self):
        """Test environment variable checking."""
        with patch.dict(os.environ, {"CIRIS_MYSERVICE_DEBUG": "true"}):
            assert _get_debug_env_var("MyService") is True

        with patch.dict(os.environ, {"CIRIS_MYSERVICE_DEBUG": "false"}):
            assert _get_debug_env_var("MyService") is False

        with patch.dict(os.environ, {}):
            assert _get_debug_env_var("MyService") is False

    def test_extract_service_name(self):
        """Test service name extraction."""

        # With service_name attribute
        class ServiceWithName:
            service_name = "CustomName"

        assert _extract_service_name(ServiceWithName()) == "CustomName"

        # With Service suffix
        class MyTestService:
            pass

        assert _extract_service_name(MyTestService()) == "MyTest"

        # With Handler suffix
        class MyHandler:
            pass

        assert _extract_service_name(MyHandler()) == "My"


class TestExceptionHandling:
    """Test decorator behavior with exceptions."""

    @pytest.mark.asyncio
    async def test_debug_log_with_exception(self):
        """Test debug logging preserves exceptions."""

        class TestService:
            service_name = "TestService"
            _logger = Mock()

            @debug_log("Processing: {value}")
            async def failing_method(self, value: str):
                raise ValueError(f"Failed on {value}")

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            with pytest.raises(ValueError, match="Failed on test"):
                await service.failing_method("test")

    @pytest.mark.asyncio
    async def test_measure_performance_with_exception(self):
        """Test performance measurement with exceptions."""

        class TestService:
            service_name = "TestService"
            _telemetry_service = AsyncMock()

            @measure_performance()
            async def failing_compute(self):
                raise RuntimeError("Compute failed")

        service = TestService()

        with pytest.raises(RuntimeError, match="Compute failed"):
            await service.failing_compute()

        # Should still record metrics
        assert service._telemetry_service.record_metric.call_count == 2
        # Check that failure metric was recorded
        calls = service._telemetry_service.record_metric.call_args_list
        assert any("failure" in str(call) for call in calls)


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_debug_log_missing_parameter(self):
        """Test debug log with invalid template parameters."""

        class TestService:
            service_name = "TestService"
            _logger = Mock()

            @debug_log("Missing param: {nonexistent}")
            async def method_with_bad_template(self, value: str) -> str:
                return value

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_TESTSERVICE_DEBUG": "true"}):
            # Should not crash, just handle gracefully
            result = await service.method_with_bad_template("test")
            assert result == "test"

    @pytest.mark.asyncio
    async def test_trace_span_no_capture_args(self):
        """Test trace span without capturing arguments."""

        class TestService:
            service_name = "TestService"

            @trace_span(capture_args=False)
            async def secret_operation(self, secret: str) -> str:
                return "done"

        service = TestService()
        result = await service.secret_operation("password123")
        assert result == "done"

    def test_service_name_override(self):
        """Test service name override in debug_log."""

        class TestService:
            service_name = "TestService"
            _logger = Mock()

            @debug_log("Custom message", service_name_override="CUSTOM")
            def custom_method(self) -> str:
                return "custom"

        service = TestService()

        with patch.dict(os.environ, {"CIRIS_CUSTOM_DEBUG": "true"}):
            result = service.custom_method()
            assert result == "custom"
