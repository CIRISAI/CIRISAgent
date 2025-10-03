import asyncio
import signal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.utils import runtime_utils


@pytest.fixture
def mock_runtime():
    """Provides a mock CIRISRuntime instance."""
    runtime = MagicMock()
    runtime.run = AsyncMock()
    runtime.shutdown = AsyncMock()
    runtime.request_shutdown = MagicMock()
    runtime._shutdown_event = asyncio.Event()
    return runtime


@pytest.mark.asyncio
class TestRuntimeUtils:

    @patch("ciris_engine.logic.utils.runtime_utils.ConfigBootstrap.load_essential_config", new_callable=AsyncMock)
    async def test_load_config(self, mock_load_essential):
        """Test that load_config correctly calls the bootstrap loader."""
        await runtime_utils.load_config("/path/to/config.yaml", cli_overrides={"key": "value"})

        mock_load_essential.assert_awaited_once()
        call_args = mock_load_essential.call_args
        assert call_args.kwargs["config_path"] == Path("/path/to/config.yaml")
        assert call_args.kwargs["cli_overrides"] == {"key": "value"}

    @patch("asyncio.get_running_loop")
    async def test_run_with_shutdown_handler_happy_path(self, mock_get_loop, mock_runtime):
        """Test the normal execution path without errors or signals."""
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        await runtime_utils.run_with_shutdown_handler(mock_runtime)

        mock_runtime.run.assert_awaited_once_with(None)  # Positional argument, not keyword
        assert mock_loop.add_signal_handler.call_count == 2
        assert mock_loop.remove_signal_handler.call_count == 2

    @patch("asyncio.get_running_loop")
    async def test_run_with_shutdown_handler_runtime_exception(self, mock_get_loop, mock_runtime, caplog):
        """Test that shutdown is called when runtime.run() raises an exception."""
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop
        mock_runtime.run.side_effect = RuntimeError("Test Exception")

        await runtime_utils.run_with_shutdown_handler(mock_runtime)

        mock_runtime.request_shutdown.assert_called_once_with("Runtime error: Test Exception")
        mock_runtime.shutdown.assert_awaited_once()
        assert "Runtime execution failed: Test Exception" in caplog.text

    @patch("asyncio.get_running_loop")
    async def test_signal_handler_logic(self, mock_get_loop, mock_runtime):
        """Test the internal signal_handler function's logic."""
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop

        # This call sets up the handlers
        await runtime_utils.run_with_shutdown_handler(mock_runtime)

        # Get the actual handler function that was passed to the mock
        signal_handler_func = mock_loop.add_signal_handler.call_args_list[0].args[1]

        # First call: should request shutdown
        signal_handler_func()
        mock_runtime.request_shutdown.assert_called_once()

        # Second call: should be ignored
        signal_handler_func()
        mock_runtime.request_shutdown.assert_called_once()  # Still called only once

    @patch("asyncio.get_running_loop")
    async def test_unsupported_signal_handling(self, mock_get_loop, mock_runtime, caplog):
        """Test graceful continuation when signal handlers are not supported."""
        mock_loop = MagicMock()
        mock_loop.add_signal_handler.side_effect = NotImplementedError
        mock_get_loop.return_value = mock_loop

        await runtime_utils.run_with_shutdown_handler(mock_runtime)

        mock_runtime.run.assert_awaited_once()
        assert "Signal handler for" in caplog.text
        assert "could not be set" in caplog.text
