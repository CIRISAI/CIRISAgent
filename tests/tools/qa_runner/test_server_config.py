"""
Tests for QA Runner server configuration.

Covers:
- HE-300 benchmark mode environment variable setup
- Template configuration for different test modules
- Live LLM configuration
"""

from unittest.mock import MagicMock, patch

import pytest


class TestHE300BenchmarkConfig:
    """Tests for HE-300 benchmark mode configuration in server.py."""

    def test_he300_sets_benchmark_mode_env_var(self):
        """HE-300 tests set CIRIS_BENCHMARK_MODE=true environment variable."""
        from tools.qa_runner.config import QAConfig, QAModule
        from tools.qa_runner.server import APIServerManager

        config = QAConfig(
            base_url="http://localhost:8080",
            api_port=8080,
            mock_llm=True,
        )

        manager = APIServerManager(config, modules=[QAModule.HE300_BENCHMARK])

        # Mock subprocess to capture environment
        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            # Mock _wait_for_server to return True
            with patch.object(manager, "_wait_for_server", return_value=True):
                with patch.object(manager, "_is_server_running", return_value=False):
                    with patch("builtins.open", MagicMock()):
                        manager.start()

            # Get the env dict passed to Popen
            call_args = mock_popen.call_args
            env = call_args.kwargs.get("env", {})

            # Verify benchmark mode env var is set
            assert env.get("CIRIS_BENCHMARK_MODE") == "true"
            assert env.get("CIRIS_TEMPLATE") == "he-300-benchmark"

    def test_he300_sets_increased_timeout_for_live_llm(self):
        """HE-300 with live LLM sets increased A2A timeout."""
        from tools.qa_runner.config import QAConfig, QAModule
        from tools.qa_runner.server import APIServerManager

        config = QAConfig(
            base_url="http://localhost:8080",
            api_port=8080,
            mock_llm=False,
            live_api_key="test-key",
            live_model="gpt-4o-mini",
        )

        manager = APIServerManager(config, modules=[QAModule.HE300_BENCHMARK])

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            with patch.object(manager, "_wait_for_server", return_value=True):
                with patch.object(manager, "_is_server_running", return_value=False):
                    with patch("builtins.open", MagicMock()):
                        manager.start()

            env = mock_popen.call_args.kwargs.get("env", {})

            # Live LLM should get 180s timeout
            assert env.get("CIRIS_A2A_TIMEOUT") == "180"

    def test_he300_sets_mock_timeout_for_mock_llm(self):
        """HE-300 with mock LLM sets shorter A2A timeout."""
        from tools.qa_runner.config import QAConfig, QAModule
        from tools.qa_runner.server import APIServerManager

        config = QAConfig(
            base_url="http://localhost:8080",
            api_port=8080,
            mock_llm=True,
        )

        manager = APIServerManager(config, modules=[QAModule.HE300_BENCHMARK])

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            with patch.object(manager, "_wait_for_server", return_value=True):
                with patch.object(manager, "_is_server_running", return_value=False):
                    with patch("builtins.open", MagicMock()):
                        manager.start()

            env = mock_popen.call_args.kwargs.get("env", {})

            # Mock LLM should get 60s timeout
            assert env.get("CIRIS_A2A_TIMEOUT") == "60"

    def test_non_he300_does_not_set_benchmark_mode(self):
        """Non-HE300 tests do not set CIRIS_BENCHMARK_MODE."""
        import os

        from tools.qa_runner.config import QAConfig, QAModule
        from tools.qa_runner.server import APIServerManager

        # Clean environment to avoid leakage from parallel tests
        env_backup = {}
        for key in ["CIRIS_BENCHMARK_MODE", "CIRIS_TEMPLATE"]:
            if key in os.environ:
                env_backup[key] = os.environ.pop(key)

        try:
            config = QAConfig(
                base_url="http://localhost:8080",
                api_port=8080,
                mock_llm=True,
            )

            # Use AUTH module instead of HE300_BENCHMARK
            manager = APIServerManager(config, modules=[QAModule.AUTH])

            with patch("subprocess.Popen") as mock_popen:
                mock_process = MagicMock()
                mock_process.pid = 12345
                mock_popen.return_value = mock_process

                with patch.object(manager, "_wait_for_server", return_value=True):
                    with patch.object(manager, "_is_server_running", return_value=False):
                        with patch("builtins.open", MagicMock()):
                            manager.start()

                env = mock_popen.call_args.kwargs.get("env", {})

                # Should NOT have benchmark mode set
                assert "CIRIS_BENCHMARK_MODE" not in env
                assert "CIRIS_TEMPLATE" not in env
        finally:
            # Restore environment
            os.environ.update(env_backup)


class TestLiveLLMConfig:
    """Tests for live LLM configuration."""

    def test_live_llm_overrides_mock_settings(self):
        """Live LLM config overrides CIRIS_MOCK_LLM from .env."""
        from tools.qa_runner.config import QAConfig, QAModule
        from tools.qa_runner.server import APIServerManager

        config = QAConfig(
            base_url="http://localhost:8080",
            api_port=8080,
            mock_llm=False,
            live_api_key="sk-test-key",
            live_model="gpt-4o-mini",
            live_base_url="https://api.openai.com/v1",
        )

        manager = APIServerManager(config, modules=[QAModule.AUTH])

        with patch("subprocess.Popen") as mock_popen:
            mock_process = MagicMock()
            mock_process.pid = 12345
            mock_popen.return_value = mock_process

            with patch.object(manager, "_wait_for_server", return_value=True):
                with patch.object(manager, "_is_server_running", return_value=False):
                    with patch("builtins.open", MagicMock()):
                        manager.start()

            env = mock_popen.call_args.kwargs.get("env", {})

            # Live LLM should override mock settings
            assert env.get("CIRIS_MOCK_LLM") == "false"
            assert env.get("CIRIS_LLM_PROVIDER") == "openai"
            assert env.get("OPENAI_API_KEY") == "sk-test-key"
            assert env.get("OPENAI_MODEL_NAME") == "gpt-4o-mini"
            assert env.get("OPENAI_API_BASE") == "https://api.openai.com/v1"
