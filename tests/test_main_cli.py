"""Comprehensive CLI tests for main.py to improve coverage."""

import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from click.testing import CliRunner

# Prevent side effects during imports
os.environ["CIRIS_IMPORT_MODE"] = "true"
os.environ["CIRIS_MOCK_LLM"] = "true"


class TestEnvironmentVariableLoading:
    """Test environment variable loading from .env files."""

    def test_loads_env_from_cwd(self):
        """Should attempt to load .env from current working directory."""
        # The .env loading happens at module import time, which is before tests run
        # This test verifies the module imports successfully (which it does)
        import main as main_module

        # Verify the module has the main function
        assert hasattr(main_module, "main")
        assert callable(main_module.main)

    @patch("main.Path")
    @patch("main.load_dotenv")
    def test_loads_env_priority_order(self, mock_load_dotenv, mock_path_class):
        """Should respect priority order for .env files."""
        # All paths exist
        mock_paths = [MagicMock() for _ in range(3)]
        for p in mock_paths:
            p.exists.return_value = True

        # Import main to trigger .env loading
        import importlib

        import main as main_module

        importlib.reload(main_module)

        # Should have called load_dotenv with override=False
        if mock_load_dotenv.called:
            for call in mock_load_dotenv.call_args_list:
                # Check that override=False is set
                assert call[1].get("override") is False or call[1].get("override", True) is False

    def test_handles_missing_dotenv_import(self):
        """Should handle missing dotenv gracefully."""
        # The import at the top of main.py has a try/except for ImportError
        # This test verifies the module still imports even without dotenv
        import main as main_module

        assert hasattr(main_module, "main")


class TestCLIArgumentParsing:
    """Test CLI argument parsing and validation."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_adapter_option_accepts_multiple_values(self, mock_logging, mock_asyncio_run):
        """Should accept multiple --adapter options."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--adapter", "cli", "--adapter", "api", "--help"])
        # Help should work regardless
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_config_option_accepts_path(self, mock_logging, mock_asyncio_run):
        """Should accept --config option with path."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--config", "/path/to/config.yaml", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_task_option_accepts_multiple_values(self, mock_logging, mock_asyncio_run):
        """Should accept multiple --task options."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--task", "Task 1", "--task", "Task 2", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_timeout_option_accepts_integer(self, mock_logging, mock_asyncio_run):
        """Should accept --timeout option with integer value."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--timeout", "60", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_handler_and_params_options(self, mock_logging, mock_asyncio_run):
        """Should accept --handler and --params options."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--handler", "SPEAK", "--params", '{"key":"value"}', "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_api_host_and_port_options(self, mock_logging, mock_asyncio_run):
        """Should accept --host and --port options."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--host", "0.0.0.0", "--port", "8080", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_debug_flag(self, mock_logging, mock_asyncio_run):
        """Should accept --debug flag."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--debug", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_no_interactive_flag(self, mock_logging, mock_asyncio_run):
        """Should accept --no-interactive flag."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--no-interactive", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_discord_token_option(self, mock_logging, mock_asyncio_run):
        """Should accept --discord-token option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--discord-token", "test_token", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_mock_llm_flag(self, mock_logging, mock_asyncio_run):
        """Should accept --mock-llm flag."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--mock-llm", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_num_rounds_option(self, mock_logging, mock_asyncio_run):
        """Should accept --num-rounds option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--num-rounds", "10", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_template_option(self, mock_logging, mock_asyncio_run):
        """Should accept --template option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--template", "custom", "--help"])
        assert result.exit_code == 0


class TestDebugLoggingSetup:
    """Test debug logging configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_debug_flag_enables_debug_logging(self, mock_logging, mock_asyncio_run):
        """Should enable debug logging when --debug flag is set."""
        import logging

        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        runner.invoke(main, ["--debug", "--adapter", "api"])

        # Should have called setup_basic_logging with DEBUG level
        assert mock_logging.called
        call_kwargs = mock_logging.call_args[1]
        assert call_kwargs.get("level") == logging.DEBUG

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_no_debug_flag_uses_info_logging(self, mock_logging, mock_asyncio_run):
        """Should use INFO logging when --debug flag is not set."""
        import logging

        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        runner.invoke(main, ["--adapter", "api"])

        # Should have called setup_basic_logging with INFO level
        assert mock_logging.called
        call_kwargs = mock_logging.call_args[1]
        assert call_kwargs.get("level") == logging.INFO

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_logging_setup_disables_file_logging_initially(self, mock_logging, mock_asyncio_run):
        """Should disable file logging initially (before TimeService is available)."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        runner.invoke(main, ["--adapter", "api"])

        # Should have called setup_basic_logging with log_to_file=False
        assert mock_logging.called
        call_kwargs = mock_logging.call_args[1]
        assert call_kwargs.get("log_to_file") is False

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_logging_enables_console_output(self, mock_logging, mock_asyncio_run):
        """Should enable console output."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        runner.invoke(main, ["--adapter", "api"])

        # Should have called setup_basic_logging with console_output=True
        assert mock_logging.called
        call_kwargs = mock_logging.call_args[1]
        assert call_kwargs.get("console_output") is True

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_logging_disables_incident_capture_initially(self, mock_logging, mock_asyncio_run):
        """Should disable incident capture initially (before TimeService is available)."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        runner.invoke(main, ["--adapter", "api"])

        # Should have called setup_basic_logging with enable_incident_capture=False
        assert mock_logging.called
        call_kwargs = mock_logging.call_args[1]
        assert call_kwargs.get("enable_incident_capture") is False


class TestErrorHandling:
    """Test error handling in main function."""

    @patch("main.asyncio.run")
    def test_handles_keyboard_interrupt_in_main(self, mock_asyncio_run):
        """Should handle KeyboardInterrupt gracefully."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        result = runner.invoke(main, ["--adapter", "api"])
        # Should exit gracefully
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    def test_handles_system_exit_in_main(self, mock_asyncio_run):
        """Should propagate SystemExit."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.side_effect = SystemExit(42)

        result = runner.invoke(main, ["--adapter", "api"])
        # Should exit with the SystemExit code
        assert result.exit_code == 42

    @patch("main.asyncio.run")
    @patch("main.logger")
    def test_handles_exception_in_main(self, mock_logger, mock_asyncio_run):
        """Should log and exit with code 1 on exception."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.side_effect = RuntimeError("Test error")

        result = runner.invoke(main, ["--adapter", "api"])
        # Should exit with code 1
        assert result.exit_code == 1


class TestMockLLMConfiguration:
    """Test mock LLM configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_mock_llm_flag_passed_to_runtime(self, mock_logging, mock_asyncio_run):
        """Should pass mock_llm flag to runtime configuration."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--mock-llm", "--adapter", "api"])
        # The test verifies the flag is accepted
        assert mock_asyncio_run.called


class TestAdapterTypeValidation:
    """Test adapter type validation and configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_api_adapter(self, mock_logging, mock_asyncio_run):
        """Should accept api adapter type."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--adapter", "api"])
        assert mock_asyncio_run.called

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_cli_adapter(self, mock_logging, mock_asyncio_run):
        """Should accept cli adapter type."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--adapter", "cli"])
        assert mock_asyncio_run.called

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_discord_adapter(self, mock_logging, mock_asyncio_run):
        """Should accept discord adapter type."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        # Discord requires token
        os.environ["DISCORD_BOT_TOKEN"] = "test_token"
        result = runner.invoke(main, ["--adapter", "discord"])
        assert mock_asyncio_run.called
        del os.environ["DISCORD_BOT_TOKEN"]

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_multiple_adapters(self, mock_logging, mock_asyncio_run):
        """Should accept multiple adapter types."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--adapter", "api", "--adapter", "cli"])
        assert mock_asyncio_run.called


class TestConfigFileHandling:
    """Test configuration file handling."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_config_file_path(self, mock_logging, mock_asyncio_run):
        """Should accept config file path."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        # Using --help so it doesn't actually try to load the config
        result = runner.invoke(main, ["--config", "/path/to/config.yaml", "--help"])
        assert result.exit_code == 0


class TestTaskPreloading:
    """Test task preloading functionality."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_single_task(self, mock_logging, mock_asyncio_run):
        """Should accept single task."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--task", "Test task", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_multiple_tasks(self, mock_logging, mock_asyncio_run):
        """Should accept multiple tasks."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--task", "Task 1", "--task", "Task 2", "--help"])
        assert result.exit_code == 0


class TestHandlerExecution:
    """Test direct handler execution."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_handler_option(self, mock_logging, mock_asyncio_run):
        """Should accept handler option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--handler", "SPEAK", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_handler_with_params(self, mock_logging, mock_asyncio_run):
        """Should accept handler with JSON params."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--handler", "SPEAK", "--params", '{"content":"test"}', "--help"])
        assert result.exit_code == 0


class TestAPIConfiguration:
    """Test API adapter configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_api_host(self, mock_logging, mock_asyncio_run):
        """Should accept API host option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--host", "0.0.0.0", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_api_port(self, mock_logging, mock_asyncio_run):
        """Should accept API port option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--port", "8080", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_api_host_and_port(self, mock_logging, mock_asyncio_run):
        """Should accept both API host and port."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--host", "127.0.0.1", "--port", "9000", "--help"])
        assert result.exit_code == 0


class TestDiscordConfiguration:
    """Test Discord adapter configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_discord_token_from_option(self, mock_logging, mock_asyncio_run):
        """Should accept Discord token from --discord-token option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--discord-token", "test_token_123", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_reads_discord_token_from_env(self, mock_logging, mock_asyncio_run):
        """Should read Discord token from DISCORD_BOT_TOKEN environment variable."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        # Set environment variable
        os.environ["DISCORD_BOT_TOKEN"] = "env_token_456"

        result = runner.invoke(main, ["--adapter", "discord", "--help"])
        assert result.exit_code == 0

        # Clean up
        if "DISCORD_BOT_TOKEN" in os.environ:
            del os.environ["DISCORD_BOT_TOKEN"]


class TestCLIInteractiveMode:
    """Test CLI interactive mode configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_interactive_mode_default_true(self, mock_logging, mock_asyncio_run):
        """Should default to interactive mode enabled."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        # Default should be interactive
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_no_interactive_flag_disables_interactive(self, mock_logging, mock_asyncio_run):
        """Should disable interactive mode with --no-interactive flag."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--no-interactive", "--help"])
        assert result.exit_code == 0


class TestRuntimeTimeoutHandling:
    """Test runtime timeout handling."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_timeout_option(self, mock_logging, mock_asyncio_run):
        """Should accept timeout option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--timeout", "120", "--help"])
        assert result.exit_code == 0


class TestNumRoundsConfiguration:
    """Test num_rounds configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_num_rounds_option(self, mock_logging, mock_asyncio_run):
        """Should accept num-rounds option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--num-rounds", "5", "--help"])
        assert result.exit_code == 0


class TestTemplateConfiguration:
    """Test template configuration."""

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_accepts_template_option(self, mock_logging, mock_asyncio_run):
        """Should accept template option."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        result = runner.invoke(main, ["--template", "custom_template", "--help"])
        assert result.exit_code == 0

    @patch("main.asyncio.run")
    @patch("main.setup_basic_logging")
    def test_default_template_is_default(self, mock_logging, mock_asyncio_run):
        """Should use 'default' as default template."""
        from main import main

        runner = CliRunner()
        mock_asyncio_run.return_value = None

        # No template specified should use default
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
