"""Tests for Android on-device mobile_main.py entrypoint.

This module tests the mobile entrypoint used by the Android app via Chaquopy.
"""

import asyncio
import importlib
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Prevent side effects during imports
os.environ["CIRIS_IMPORT_MODE"] = "true"
os.environ["CIRIS_MOCK_LLM"] = "true"


def _reload_mobile_main():
    """Reload mobile_main module to get fresh state."""
    import android.app.src.main.python.mobile_main as mobile_main
    importlib.reload(mobile_main)
    return mobile_main


class TestSetupAndroidEnvironment:
    """Tests for setup_android_environment() function."""

    def test_not_running_on_android_logs_warning(self, monkeypatch, caplog):
        """Test that a warning is logged when ANDROID_DATA is not set."""
        # Use monkeypatch to safely remove ANDROID_DATA
        monkeypatch.delenv("ANDROID_DATA", raising=False)
        monkeypatch.delenv("CIRIS_HOME", raising=False)

        mobile_main = _reload_mobile_main()

        with caplog.at_level("WARNING"):
            mobile_main.setup_android_environment()

        assert "ANDROID_DATA not set - not running on Android?" in caplog.text

    def test_android_environment_creates_directories(self, tmp_path, monkeypatch):
        """Test that required directories are created on Android."""
        # Create a mock CIRIS home directory
        ciris_home = tmp_path / "ciris"
        ciris_home.mkdir()
        data_dir = ciris_home / "data"
        data_dir.mkdir()
        logs_dir = ciris_home / "logs"

        # Use monkeypatch for proper isolation in parallel test runs
        monkeypatch.setenv("ANDROID_DATA", str(tmp_path / "data"))
        # Clear any existing CIRIS env vars
        for key in [
            "CIRIS_HOME",
            "CIRIS_DATA_DIR",
            "CIRIS_DB_PATH",
            "CIRIS_LOG_DIR",
            "CIRIS_OFFLINE_MODE",
            "CIRIS_CLOUD_SYNC",
            "CIRIS_MAX_WORKERS",
            "CIRIS_API_HOST",
            "CIRIS_API_PORT",
            "CIRIS_LOG_LEVEL",
        ]:
            monkeypatch.delenv(key, raising=False)

        # Mock path resolution to use our test paths
        with patch(
            "ciris_engine.logic.utils.path_resolution.ensure_ciris_home_env",
            return_value=ciris_home,
        ):
            with patch(
                "ciris_engine.logic.utils.path_resolution.get_data_dir",
                return_value=data_dir,
            ):
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_logs_dir",
                    return_value=logs_dir,
                ):
                    mobile_main = _reload_mobile_main()
                    mobile_main.setup_android_environment()

        # Check logs directory was created
        assert logs_dir.exists()

        # Check Android-specific settings
        assert os.environ.get("CIRIS_OFFLINE_MODE") == "true"
        assert os.environ.get("CIRIS_CLOUD_SYNC") == "false"
        assert os.environ.get("CIRIS_MAX_WORKERS") == "1"
        assert os.environ.get("CIRIS_API_HOST") == "0.0.0.0"
        assert os.environ.get("CIRIS_API_PORT") == "8080"

    def test_android_environment_loads_env_file(self, tmp_path, monkeypatch, caplog):
        """Test that .env file is loaded if present."""
        # Create mock CIRIS home with .env file
        ciris_home = tmp_path / "ciris"
        ciris_home.mkdir()
        data_dir = ciris_home / "data"
        data_dir.mkdir()
        logs_dir = ciris_home / "logs"

        # Create .env file
        env_file = ciris_home / ".env"
        env_file.write_text("OPENAI_API_KEY=test-key-12345\nOPENAI_API_BASE=http://test.api\n")

        # Use monkeypatch for proper isolation in parallel test runs
        monkeypatch.setenv("ANDROID_DATA", str(tmp_path / "data"))
        for key in ["CIRIS_HOME", "OPENAI_API_KEY", "OPENAI_API_BASE"]:
            monkeypatch.delenv(key, raising=False)

        # Mock path resolution to use our test paths
        with patch(
            "ciris_engine.logic.utils.path_resolution.ensure_ciris_home_env",
            return_value=ciris_home,
        ):
            with patch(
                "ciris_engine.logic.utils.path_resolution.get_data_dir",
                return_value=data_dir,
            ):
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_logs_dir",
                    return_value=logs_dir,
                ):
                    mobile_main = _reload_mobile_main()

                    with caplog.at_level("INFO"):
                        mobile_main.setup_android_environment()

        # Verify .env was loaded
        assert "Loading configuration from" in caplog.text
        assert os.environ.get("OPENAI_API_KEY") == "test-key-12345"
        assert os.environ.get("OPENAI_API_BASE") == "http://test.api"

    def test_android_environment_handles_missing_env_file(self, tmp_path, monkeypatch, caplog):
        """Test graceful handling when .env file is missing."""
        # Create mock CIRIS home WITHOUT .env file
        ciris_home = tmp_path / "ciris"
        ciris_home.mkdir()
        data_dir = ciris_home / "data"
        data_dir.mkdir()
        logs_dir = ciris_home / "logs"

        # Use monkeypatch for proper isolation in parallel test runs
        monkeypatch.setenv("ANDROID_DATA", str(tmp_path / "data"))
        monkeypatch.delenv("CIRIS_HOME", raising=False)

        # Mock path resolution to use our test paths
        with patch(
            "ciris_engine.logic.utils.path_resolution.ensure_ciris_home_env",
            return_value=ciris_home,
        ):
            with patch(
                "ciris_engine.logic.utils.path_resolution.get_data_dir",
                return_value=data_dir,
            ):
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_logs_dir",
                    return_value=logs_dir,
                ):
                    mobile_main = _reload_mobile_main()

                    with caplog.at_level("INFO"):
                        mobile_main.setup_android_environment()

        assert "No .env file" in caplog.text


class TestStartMobileRuntime:
    """Tests for start_mobile_runtime() async function."""

    @pytest.mark.asyncio
    async def test_runtime_initialization(self):
        """Test that runtime is properly initialized with correct config."""
        mock_runtime = MagicMock()
        mock_runtime.initialize = AsyncMock()
        mock_runtime.run = AsyncMock()
        mock_runtime.shutdown = AsyncMock()

        with patch.dict(
            os.environ,
            {
                "CIRIS_HOME": "/tmp/test_ciris",
                "OPENAI_API_BASE": "http://test.api",
            },
        ):
            # Patch at the source module where CIRISRuntime is imported
            with patch(
                "ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime",
                return_value=mock_runtime,
            ) as mock_runtime_class:
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_ciris_home",
                    return_value=Path("/tmp/test_ciris"),
                ):
                    with patch(
                        "ciris_engine.logic.utils.path_resolution.get_data_dir",
                        return_value=Path("/tmp/test_ciris/data"),
                    ):
                        from android.app.src.main.python import mobile_main

                        await mobile_main.start_mobile_runtime()

                        # Verify runtime was created with correct parameters
                        mock_runtime_class.assert_called_once()
                        call_kwargs = mock_runtime_class.call_args.kwargs

                        assert call_kwargs["adapter_types"] == ["api"]
                        assert call_kwargs["interactive"] is False
                        assert call_kwargs["host"] == "0.0.0.0"
                        assert call_kwargs["port"] == 8080

                        # Verify lifecycle methods were called
                        mock_runtime.initialize.assert_awaited_once()
                        mock_runtime.run.assert_awaited_once()
                        mock_runtime.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_runtime_handles_keyboard_interrupt(self):
        """Test that KeyboardInterrupt is handled gracefully."""
        mock_runtime = MagicMock()
        mock_runtime.initialize = AsyncMock()
        mock_runtime.run = AsyncMock(side_effect=KeyboardInterrupt())
        mock_runtime.shutdown = AsyncMock()
        mock_runtime.request_shutdown = MagicMock()

        with patch.dict(os.environ, {"CIRIS_HOME": "/tmp/test_ciris"}):
            with patch(
                "ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime",
                return_value=mock_runtime,
            ):
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_ciris_home",
                    return_value=Path("/tmp/test_ciris"),
                ):
                    with patch(
                        "ciris_engine.logic.utils.path_resolution.get_data_dir",
                        return_value=Path("/tmp/test_ciris/data"),
                    ):
                        from android.app.src.main.python import mobile_main

                        await mobile_main.start_mobile_runtime()

                        mock_runtime.request_shutdown.assert_called_once()
                        assert "User interrupt" in str(mock_runtime.request_shutdown.call_args)
                        mock_runtime.shutdown.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_runtime_handles_exception(self, caplog):
        """Test that runtime errors are handled and logged."""
        mock_runtime = MagicMock()
        mock_runtime.initialize = AsyncMock()
        mock_runtime.run = AsyncMock(side_effect=RuntimeError("Test error"))
        mock_runtime.shutdown = AsyncMock()
        mock_runtime.request_shutdown = MagicMock()

        with patch.dict(os.environ, {"CIRIS_HOME": "/tmp/test_ciris"}):
            with patch(
                "ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime",
                return_value=mock_runtime,
            ):
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_ciris_home",
                    return_value=Path("/tmp/test_ciris"),
                ):
                    with patch(
                        "ciris_engine.logic.utils.path_resolution.get_data_dir",
                        return_value=Path("/tmp/test_ciris/data"),
                    ):
                        from android.app.src.main.python import mobile_main

                        await mobile_main.start_mobile_runtime()

                        mock_runtime.request_shutdown.assert_called_once()
                        call_arg = str(mock_runtime.request_shutdown.call_args)
                        assert "Error" in call_arg
                        mock_runtime.shutdown.assert_awaited_once()


class TestMain:
    """Tests for main() function."""

    def test_main_calls_setup_and_runtime(self):
        """Test that main() calls setup and starts the runtime."""
        mock_setup = MagicMock()

        def close_coroutine(coro):
            """Close coroutine to prevent 'never awaited' warnings."""
            coro.close()

        mock_asyncio_run = MagicMock(side_effect=close_coroutine)

        with patch(
            "android.app.src.main.python.mobile_main.setup_android_environment",
            mock_setup,
        ):
            with patch("android.app.src.main.python.mobile_main.asyncio.run", mock_asyncio_run):
                from android.app.src.main.python import mobile_main

                mobile_main.main()

                mock_setup.assert_called_once()
                mock_asyncio_run.assert_called_once()

    def test_main_handles_keyboard_interrupt(self, caplog):
        """Test that main() handles KeyboardInterrupt gracefully."""
        mock_setup = MagicMock()

        def close_and_raise(coro):
            """Close coroutine and raise KeyboardInterrupt."""
            coro.close()
            raise KeyboardInterrupt()

        with patch(
            "android.app.src.main.python.mobile_main.setup_android_environment",
            mock_setup,
        ):
            with patch(
                "android.app.src.main.python.mobile_main.asyncio.run",
                side_effect=close_and_raise,
            ):
                from android.app.src.main.python import mobile_main

                with caplog.at_level("INFO"):
                    mobile_main.main()

                assert "Server stopped by user" in caplog.text

    def test_main_handles_exceptions_and_exits(self, caplog):
        """Test that main() handles exceptions and calls sys.exit(1)."""
        mock_setup = MagicMock()

        def close_and_raise(coro):
            """Close coroutine and raise ValueError."""
            coro.close()
            raise ValueError("Test error")

        with patch(
            "android.app.src.main.python.mobile_main.setup_android_environment",
            mock_setup,
        ):
            with patch(
                "android.app.src.main.python.mobile_main.asyncio.run",
                side_effect=close_and_raise,
            ):
                with patch("android.app.src.main.python.mobile_main.sys.exit") as mock_exit:
                    from android.app.src.main.python import mobile_main

                    with caplog.at_level("ERROR"):
                        mobile_main.main()

                    # Verify exception was logged and sys.exit(1) was called
                    assert "Server error: Test error" in caplog.text
                    mock_exit.assert_called_once_with(1)


class TestModuleAttributes:
    """Tests for module-level attributes and logging configuration."""

    def test_module_has_logger(self):
        """Test that the module has a logger configured."""
        from android.app.src.main.python import mobile_main

        assert hasattr(mobile_main, "logger")
        # Logger name is "mobile_main" when imported directly (not via android.app path)
        assert mobile_main.logger.name == "mobile_main"

    def test_module_functions_exist(self):
        """Test that all expected functions exist."""
        from android.app.src.main.python import mobile_main

        assert hasattr(mobile_main, "setup_android_environment")
        assert callable(mobile_main.setup_android_environment)

        assert hasattr(mobile_main, "start_mobile_runtime")
        assert callable(mobile_main.start_mobile_runtime)

        assert hasattr(mobile_main, "main")
        assert callable(mobile_main.main)


class TestEnvironmentVariableDefaults:
    """Tests for environment variable default values."""

    def test_low_resource_optimization_defaults(self, tmp_path, monkeypatch):
        """Test that low-resource optimization defaults are set."""
        ciris_home = tmp_path / "ciris"
        ciris_home.mkdir()
        data_dir = ciris_home / "data"
        data_dir.mkdir()
        logs_dir = ciris_home / "logs"

        # Use monkeypatch for proper isolation in parallel test runs
        monkeypatch.setenv("ANDROID_DATA", str(tmp_path / "data"))
        for key in ["CIRIS_MAX_WORKERS", "CIRIS_LOG_LEVEL", "CIRIS_HOME"]:
            monkeypatch.delenv(key, raising=False)

        # Mock path resolution to use our test paths
        with patch(
            "ciris_engine.logic.utils.path_resolution.ensure_ciris_home_env",
            return_value=ciris_home,
        ):
            with patch(
                "ciris_engine.logic.utils.path_resolution.get_data_dir",
                return_value=data_dir,
            ):
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_logs_dir",
                    return_value=logs_dir,
                ):
                    mobile_main = _reload_mobile_main()
                    mobile_main.setup_android_environment()

        # Verify low-resource defaults
        assert os.environ.get("CIRIS_MAX_WORKERS") == "1"
        assert os.environ.get("CIRIS_LOG_LEVEL") == "INFO"

    def test_offline_mode_enabled(self, tmp_path, monkeypatch):
        """Test that offline mode is enabled for Android."""
        ciris_home = tmp_path / "ciris"
        ciris_home.mkdir()
        data_dir = ciris_home / "data"
        data_dir.mkdir()
        logs_dir = ciris_home / "logs"

        # Use monkeypatch for proper isolation in parallel test runs
        monkeypatch.setenv("ANDROID_DATA", str(tmp_path / "data"))
        monkeypatch.delenv("CIRIS_HOME", raising=False)

        # Mock path resolution to use our test paths
        with patch(
            "ciris_engine.logic.utils.path_resolution.ensure_ciris_home_env",
            return_value=ciris_home,
        ):
            with patch(
                "ciris_engine.logic.utils.path_resolution.get_data_dir",
                return_value=data_dir,
            ):
                with patch(
                    "ciris_engine.logic.utils.path_resolution.get_logs_dir",
                    return_value=logs_dir,
                ):
                    mobile_main = _reload_mobile_main()
                    mobile_main.setup_android_environment()

        assert os.environ.get("CIRIS_OFFLINE_MODE") == "true"
        assert os.environ.get("CIRIS_CLOUD_SYNC") == "false"
