# CRITICAL: Prevent side effects during imports
import os

os.environ["CIRIS_IMPORT_MODE"] = "true"
os.environ["CIRIS_MOCK_LLM"] = "true"

import asyncio
from typing import List
from unittest.mock import AsyncMock, MagicMock

from click.testing import CliRunner

import main
from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime


def test_cli_offline_non_interactive(monkeypatch):
    """Ensure CLI mode works with the mock LLM service."""
    monkeypatch.setattr(main, "load_config", AsyncMock(return_value=MagicMock(discord_home_channel_id="cli")))

    # Mock CIRISRuntime constructor and methods
    runtime_mock = MagicMock(spec=CIRISRuntime)
    runtime_mock.initialize = AsyncMock()
    runtime_mock.shutdown = AsyncMock()
    runtime_mock.startup_channel_id = "cli"
    runtime_mock._shutdown_complete = True  # Mark as shutdown complete to prevent monitor task from forcing exit
    runtime_mock._shutdown_event = AsyncMock()  # Mock the shutdown event for new event-based approach

    def mock_runtime_init(modes: List[str], **kwargs):
        return runtime_mock

    monkeypatch.setattr(
        "ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime.__new__", lambda cls, *args, **kwargs: runtime_mock
    )
    monkeypatch.setattr(
        "ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime.__init__", lambda self, *args, **kwargs: None
    )

    monkeypatch.setattr(main, "_run_runtime", AsyncMock())

    # Mock os._exit to prevent actual exit
    def mock_exit(code):
        pass  # Don't actually exit

    monkeypatch.setattr("os._exit", mock_exit)

    real_run = asyncio.run

    def fake_run(coro):
        real_run(coro)

    monkeypatch.setattr("asyncio.run", fake_run)

    result = CliRunner().invoke(main.main, ["--adapter", "cli", "--no-interactive", "--mock-llm"])
    assert result.exit_code == 0
    runtime_mock.initialize.assert_called_once()
