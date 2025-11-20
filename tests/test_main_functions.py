"""Unit tests for main.py helper functions."""

import asyncio
import json
import signal
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from tests.fixtures.mocks import MockRuntime


class TestSetupSignalHandlers:
    """Test signal handler setup."""

    @patch("main.signal.signal")
    def test_registers_sigterm_handler(self, mock_signal):
        """Should register SIGTERM handler."""
        from main import setup_signal_handlers

        mock_runtime = MockRuntime()
        setup_signal_handlers(mock_runtime)

        # Check SIGTERM was registered
        calls = mock_signal.call_args_list
        sigterm_registered = any(call[0][0] == signal.SIGTERM for call in calls)
        assert sigterm_registered

    @patch("main.signal.signal")
    def test_registers_sigint_handler(self, mock_signal):
        """Should register SIGINT handler."""
        from main import setup_signal_handlers

        mock_runtime = MockRuntime()
        setup_signal_handlers(mock_runtime)

        # Check SIGINT was registered
        calls = mock_signal.call_args_list
        sigint_registered = any(call[0][0] == signal.SIGINT for call in calls)
        assert sigint_registered

    @patch("main.signal.signal")
    def test_signal_handler_requests_shutdown(self, mock_signal):
        """Signal handler should request graceful shutdown."""
        from main import setup_signal_handlers

        mock_runtime = MockRuntime()
        setup_signal_handlers(mock_runtime)

        # Get the registered handler
        signal_handler = None
        for call in mock_signal.call_args_list:
            if call[0][0] == signal.SIGTERM:
                signal_handler = call[0][1]
                break

        assert signal_handler is not None

        # Trigger the signal handler
        signal_handler(signal.SIGTERM, None)

        # Should have requested shutdown
        assert mock_runtime._shutdown_reason is not None
        assert "Signal" in mock_runtime._shutdown_reason or str(signal.SIGTERM) in mock_runtime._shutdown_reason

    @patch("main.signal.signal")
    def test_second_signal_raises_keyboard_interrupt(self, mock_signal):
        """Second signal should force immediate exit."""
        from main import setup_signal_handlers

        mock_runtime = MockRuntime()
        setup_signal_handlers(mock_runtime)

        # Get the registered handler
        signal_handler = None
        for call in mock_signal.call_args_list:
            if call[0][0] == signal.SIGTERM:
                signal_handler = call[0][1]
                break

        # First signal
        signal_handler(signal.SIGTERM, None)

        # Second signal should raise
        with pytest.raises(KeyboardInterrupt, match="Forced shutdown"):
            signal_handler(signal.SIGTERM, None)

    @patch("main.signal.signal")
    def test_signal_handler_with_exception(self, mock_signal):
        """Signal handler should handle exceptions during shutdown."""
        from main import setup_signal_handlers

        mock_runtime = MockRuntime()

        # Make request_shutdown raise an exception
        def raise_error(reason):
            raise RuntimeError("Shutdown failed")

        mock_runtime.request_shutdown = raise_error
        setup_signal_handlers(mock_runtime)

        # Get the registered handler
        signal_handler = None
        for call in mock_signal.call_args_list:
            if call[0][0] == signal.SIGTERM:
                signal_handler = call[0][1]
                break

        # Should raise KeyboardInterrupt even when shutdown fails
        with pytest.raises(KeyboardInterrupt, match="Shutdown error"):
            signal_handler(signal.SIGTERM, None)


class TestSetupGlobalExceptionHandler:
    """Test global exception handler setup."""

    def test_installs_exception_hook(self):
        """Should install custom exception hook."""
        from main import setup_global_exception_handler

        original_hook = sys.excepthook
        try:
            setup_global_exception_handler()
            assert sys.excepthook != original_hook
        finally:
            sys.excepthook = original_hook

    def test_allows_keyboard_interrupt(self):
        """Should allow KeyboardInterrupt to pass through."""
        from main import setup_global_exception_handler

        original_hook = sys.excepthook
        try:
            setup_global_exception_handler()

            # Mock the original excepthook
            with patch("sys.__excepthook__") as mock_original:
                sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
                mock_original.assert_called_once()
        finally:
            sys.excepthook = original_hook

    def test_logs_uncaught_exceptions(self):
        """Should log uncaught exceptions."""
        from main import setup_global_exception_handler

        original_hook = sys.excepthook
        try:
            setup_global_exception_handler()

            with patch("main.logger") as mock_logger:
                exc = RuntimeError("Test error")
                sys.excepthook(RuntimeError, exc, None)

                # Should have logged the error
                assert mock_logger.error.call_count >= 1
                error_calls = [str(call) for call in mock_logger.error.call_args_list]
                assert any("UNCAUGHT EXCEPTION" in str(call) for call in error_calls)
        finally:
            sys.excepthook = original_hook


class TestCreateThought:
    """Test thought creation helper."""

    @patch("main.Thought")
    def test_creates_valid_thought(self, mock_thought_class):
        """Should create a valid Thought object."""
        from main import _create_thought

        # Mock the Thought constructor to avoid context validation
        mock_thought = MagicMock()
        mock_thought_class.return_value = mock_thought

        thought = _create_thought()

        # Verify Thought was called with correct parameters
        mock_thought_class.assert_called_once()
        call_kwargs = mock_thought_class.call_args[1]
        assert "thought_id" in call_kwargs
        assert "source_task_id" in call_kwargs
        assert call_kwargs["thought_type"] == "standard"
        assert call_kwargs["status"] == ThoughtStatus.PENDING
        assert call_kwargs["content"] == "manual invocation"
        assert "context" in call_kwargs

    @patch("main.Thought")
    def test_thought_has_timestamps(self, mock_thought_class):
        """Thought should have valid timestamps."""
        from main import _create_thought

        mock_thought = MagicMock()
        mock_thought_class.return_value = mock_thought

        _create_thought()

        # Verify timestamps were set
        call_kwargs = mock_thought_class.call_args[1]
        created_at = datetime.fromisoformat(call_kwargs["created_at"].replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(call_kwargs["updated_at"].replace("Z", "+00:00"))

        # Should be recent (within last minute)
        now = datetime.now(timezone.utc)
        assert (now - created_at).total_seconds() < 60
        assert (now - updated_at).total_seconds() < 60

    @patch("main.Thought")
    def test_thought_ids_are_unique(self, mock_thought_class):
        """Each thought should have unique IDs."""
        from main import _create_thought

        mock_thought1 = MagicMock()
        mock_thought2 = MagicMock()
        mock_thought_class.side_effect = [mock_thought1, mock_thought2]

        _create_thought()
        _create_thought()

        # Verify IDs are unique
        call1_kwargs = mock_thought_class.call_args_list[0][1]
        call2_kwargs = mock_thought_class.call_args_list[1][1]
        assert call1_kwargs["thought_id"] != call2_kwargs["thought_id"]
        assert call1_kwargs["source_task_id"] != call2_kwargs["source_task_id"]


class TestExecuteHandler:
    """Test direct handler execution."""

    @pytest.mark.asyncio
    @patch("main._create_thought")
    async def test_executes_handler_with_no_params(self, mock_create_thought):
        """Should execute handler without parameters."""
        from main import _execute_handler

        # Mock thought creation with proper string values
        mock_thought = MagicMock()
        mock_thought.thought_id = "test-thought-id"
        mock_thought.source_task_id = "test-task-id"
        mock_thought.content = "manual invocation"
        mock_thought.status = ThoughtStatus.PENDING
        mock_create_thought.return_value = mock_thought

        mock_runtime = MockRuntime()
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock()

        mock_runtime.agent_processor.action_dispatcher.handlers = {HandlerActionType.SPEAK: mock_handler}
        mock_runtime.startup_channel_id = "test_channel"

        await _execute_handler(mock_runtime, "SPEAK", None)

        # Handler should have been called
        mock_handler.handle.assert_called_once()
        call_args = mock_handler.handle.call_args[0]
        result, thought, context = call_args

        assert isinstance(result, ActionSelectionDMAResult)
        assert result.selected_action == HandlerActionType.SPEAK
        # action_parameters is a Pydantic object, not an empty dict
        assert result.action_parameters is not None

    @pytest.mark.asyncio
    @patch("main._create_thought")
    async def test_executes_handler_with_params(self, mock_create_thought):
        """Should execute handler with JSON parameters."""
        from main import _execute_handler

        # Mock thought creation with proper string values
        mock_thought = MagicMock()
        mock_thought.thought_id = "test-thought-id"
        mock_thought.source_task_id = "test-task-id"
        mock_thought.content = "manual invocation"
        mock_thought.status = ThoughtStatus.PENDING
        mock_create_thought.return_value = mock_thought

        mock_runtime = MockRuntime()
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock()

        mock_runtime.agent_processor.action_dispatcher.handlers = {HandlerActionType.SPEAK: mock_handler}
        mock_runtime.startup_channel_id = "test_channel"

        params = json.dumps({"content": "test response"})
        await _execute_handler(mock_runtime, "SPEAK", params)

        # Handler should have been called with params
        mock_handler.handle.assert_called_once()
        call_args = mock_handler.handle.call_args[0]
        result = call_args[0]

        # action_parameters is a Pydantic object (SpeakParams), check the content field
        assert hasattr(result.action_parameters, "content")
        assert result.action_parameters.content == "test response"

    @pytest.mark.asyncio
    async def test_raises_if_no_processor(self):
        """Should raise if agent processor not initialized."""
        from main import _execute_handler

        mock_runtime = MockRuntime()
        mock_runtime.agent_processor = None

        with pytest.raises(RuntimeError, match="Agent processor not initialized"):
            await _execute_handler(mock_runtime, "SPEAK", None)

    @pytest.mark.asyncio
    async def test_raises_if_handler_not_found(self):
        """Should raise if handler not registered."""
        from main import _execute_handler

        mock_runtime = MockRuntime()
        mock_runtime.agent_processor.action_dispatcher.handlers = {}  # No handlers registered

        with pytest.raises(ValueError, match="Handler .* not registered"):
            await _execute_handler(mock_runtime, "SPEAK", None)


class TestRunRuntime:
    """Test runtime execution with timeout handling."""

    @pytest.mark.asyncio
    async def test_runs_without_timeout(self):
        """Should run runtime without timeout."""
        from main import _run_runtime

        mock_runtime = MockRuntime()
        mock_runtime.run = AsyncMock()

        await _run_runtime(mock_runtime, timeout=None, num_rounds=5)

        mock_runtime.run.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_runs_with_timeout_completes_normally(self):
        """Should complete normally if runtime finishes before timeout."""
        from main import _run_runtime

        mock_runtime = MockRuntime()

        async def quick_run(rounds):
            await asyncio.sleep(0.1)

        mock_runtime.run = quick_run

        # 5 second timeout, completes in 0.1 seconds
        await _run_runtime(mock_runtime, timeout=5, num_rounds=1)

        # Should complete without calling shutdown - check via _shutdown_reason
        assert mock_runtime._shutdown_reason is None

    @pytest.mark.asyncio
    async def test_handles_timeout_gracefully(self):
        """Should handle timeout and request graceful shutdown."""
        from main import _run_runtime

        mock_runtime = MockRuntime()
        mock_runtime.shutdown = AsyncMock()

        async def slow_run(rounds):
            await asyncio.sleep(10)  # Longer than timeout

        mock_runtime.run = slow_run

        # 0.5 second timeout
        await _run_runtime(mock_runtime, timeout=0.5, num_rounds=1)

        # Should have requested shutdown
        assert mock_runtime._shutdown_reason is not None
        assert "timeout" in mock_runtime._shutdown_reason.lower()

    @pytest.mark.asyncio
    async def test_handles_keyboard_interrupt(self):
        """Should handle KeyboardInterrupt gracefully."""
        from main import _run_runtime

        mock_runtime = MockRuntime()
        mock_runtime.shutdown = AsyncMock()

        async def interrupted_run(rounds):
            raise KeyboardInterrupt()

        mock_runtime.run = interrupted_run

        await _run_runtime(mock_runtime, timeout=None)

        # Should have requested shutdown
        assert mock_runtime._shutdown_reason is not None
        assert "interrupt" in mock_runtime._shutdown_reason.lower()

    @pytest.mark.asyncio
    async def test_handles_runtime_exception(self):
        """Should handle runtime exceptions and shutdown."""
        from main import _run_runtime

        mock_runtime = MockRuntime()
        mock_runtime.shutdown = AsyncMock()

        async def failing_run(rounds):
            raise RuntimeError("Test error")

        mock_runtime.run = failing_run

        with pytest.raises(RuntimeError, match="Test error"):
            await _run_runtime(mock_runtime, timeout=None)

        # Should have attempted shutdown
        assert mock_runtime._shutdown_reason is not None


class TestMainFunction:
    """Test main CLI function entry point."""

    @patch("main.load_config")
    @patch("main.setup_basic_logging")
    def test_main_requires_async_context(self, mock_logging, mock_config):
        """Main function creates async context."""
        from main import main

        # Mock config loading
        mock_config.return_value = AsyncMock()

        # Mock the Click runner
        from click.testing import CliRunner

        runner = CliRunner()

        # Test help works
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Unified CIRIS agent entry point" in result.output

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_main_sets_up_logging(self, mock_logging, mock_asyncio_run):
        """Main should set up logging before running."""
        from click.testing import CliRunner

        from main import main

        runner = CliRunner()

        # Mock asyncio.run to avoid actual execution
        mock_asyncio_run.return_value = None

        runner.invoke(main, ["--adapter", "api"])

        # Should have set up logging
        assert mock_logging.called

    def test_main_has_correct_options(self):
        """Main should have all required CLI options."""
        from main import main

        # Check that main has expected parameters
        param_names = [param.name for param in main.params]

        expected_params = [
            "adapter_types_list",
            "template",
            "config_file_path",
            "task",
            "timeout",
            "handler",
            "params",
            "api_host",
            "api_port",
            "debug",
            "cli_interactive",
            "discord_bot_token",
            "mock_llm",
            "num_rounds",
        ]

        for expected in expected_params:
            assert expected in param_names, f"Missing parameter: {expected}"


class TestMainEdgeCases:
    """Test edge cases and error handling in main."""

    def test_main_has_mock_llm_option(self):
        """Main should have --mock-llm option."""
        from main import main

        param_names = [param.name for param in main.params]
        assert "mock_llm" in param_names


class TestHelperFunctionIntegration:
    """Integration tests for helper functions working together."""

    def test_signal_handler_and_exception_handler_coexist(self):
        """Signal and exception handlers should work together."""
        from main import setup_global_exception_handler, setup_signal_handlers

        original_hook = sys.excepthook
        try:
            # Set up both handlers
            setup_global_exception_handler()
            mock_runtime = MockRuntime()
            setup_signal_handlers(mock_runtime)

            # Both should be installed
            assert sys.excepthook != original_hook
            # Signal handlers registered (can't easily verify without sending signals)
        finally:
            sys.excepthook = original_hook

    @pytest.mark.asyncio
    @patch("main._create_thought")
    async def test_execute_handler_creates_valid_thought(self, mock_create_thought):
        """Execute handler should create valid thought with correct fields."""
        from main import _execute_handler

        # Mock thought creation with proper string values
        mock_thought = MagicMock()
        mock_thought.thought_id = "test-thought-id"
        mock_thought.source_task_id = "test-task-id"
        mock_thought.content = "manual invocation"
        mock_thought.status = ThoughtStatus.PENDING
        mock_create_thought.return_value = mock_thought

        mock_runtime = MockRuntime()
        mock_handler = MagicMock()
        mock_handler.handle = AsyncMock()

        mock_runtime.agent_processor.action_dispatcher.handlers = {HandlerActionType.SPEAK: mock_handler}
        mock_runtime.startup_channel_id = "test_channel"

        await _execute_handler(mock_runtime, "SPEAK", None)

        # Verify thought was created and passed to handler
        mock_create_thought.assert_called_once()
        call_args = mock_handler.handle.call_args[0]
        thought = call_args[1]

        assert thought.content == "manual invocation"
        assert thought.status == ThoughtStatus.PENDING
