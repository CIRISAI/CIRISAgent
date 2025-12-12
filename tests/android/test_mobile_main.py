"""Tests for Android on-device mobile_main.py entrypoint.

This module tests the mobile entrypoint used by the Android app via Chaquopy.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Prevent side effects during imports
os.environ["CIRIS_IMPORT_MODE"] = "true"
os.environ["CIRIS_MOCK_LLM"] = "true"


class TestSetupAndroidEnvironment:
    """Tests for setup_android_environment() function."""

    def test_not_running_on_android_logs_warning(self, caplog):
        """Test that a warning is logged when ANDROID_DATA is not set."""
        # Ensure ANDROID_DATA is not set
        env_backup = os.environ.pop("ANDROID_DATA", None)
        try:
            # Import fresh to avoid module caching issues
            from android.app.src.main.python import mobile_main

            with caplog.at_level("WARNING"):
                mobile_main.setup_android_environment()

            assert "ANDROID_DATA not set - not running on Android?" in caplog.text
        finally:
            if env_backup:
                os.environ["ANDROID_DATA"] = env_backup

    def test_android_environment_creates_directories(self, tmp_path):
        """Test that required directories are created on Android."""
        # Create a mock Android data directory
        android_data = tmp_path / "data"
        android_data.mkdir()

        env_backup = {
            "ANDROID_DATA": os.environ.get("ANDROID_DATA"),
            "CIRIS_HOME": os.environ.get("CIRIS_HOME"),
            "CIRIS_DATA_DIR": os.environ.get("CIRIS_DATA_DIR"),
            "CIRIS_DB_PATH": os.environ.get("CIRIS_DB_PATH"),
            "CIRIS_LOG_DIR": os.environ.get("CIRIS_LOG_DIR"),
        }

        try:
            # Set Android environment
            os.environ["ANDROID_DATA"] = str(android_data)
            # Clear any existing CIRIS env vars
            for key in [
                "CIRIS_HOME",
                "CIRIS_DATA_DIR",
                "CIRIS_DB_PATH",
                "CIRIS_LOG_DIR",
            ]:
                os.environ.pop(key, None)

            from android.app.src.main.python import mobile_main

            mobile_main.setup_android_environment()

            # Check directories were created
            ciris_home = android_data / "data" / "ai.ciris.mobile" / "files" / "ciris"
            assert ciris_home.exists()
            assert (ciris_home / "databases").exists()
            assert (ciris_home / "logs").exists()

            # Check environment variables were set
            assert os.environ.get("CIRIS_HOME") == str(ciris_home)
            assert os.environ.get("CIRIS_DATA_DIR") == str(ciris_home)
            assert os.environ.get("CIRIS_DB_PATH") == str(ciris_home / "databases" / "ciris.db")
            assert os.environ.get("CIRIS_LOG_DIR") == str(ciris_home / "logs")

            # Check Android-specific settings
            assert os.environ.get("CIRIS_OFFLINE_MODE") == "true"
            assert os.environ.get("CIRIS_CLOUD_SYNC") == "false"
            assert os.environ.get("CIRIS_MAX_WORKERS") == "1"
            assert os.environ.get("CIRIS_API_HOST") == "0.0.0.0"
            assert os.environ.get("CIRIS_API_PORT") == "8080"
        finally:
            # Restore environment
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

    def test_android_environment_loads_env_file(self, tmp_path, caplog):
        """Test that .env file is loaded if present."""
        # Create mock Android structure
        android_data = tmp_path / "data"
        android_data.mkdir()

        app_data = android_data / "data" / "ai.ciris.mobile" / "files" / "ciris"
        app_data.mkdir(parents=True)

        # Create .env file
        env_file = app_data / ".env"
        env_file.write_text("OPENAI_API_KEY=test-key-12345\nOPENAI_API_BASE=http://test.api\n")

        env_backup = {
            "ANDROID_DATA": os.environ.get("ANDROID_DATA"),
            "CIRIS_HOME": os.environ.get("CIRIS_HOME"),
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
            "OPENAI_API_BASE": os.environ.get("OPENAI_API_BASE"),
        }

        try:
            os.environ["ANDROID_DATA"] = str(android_data)
            for key in ["CIRIS_HOME", "OPENAI_API_KEY", "OPENAI_API_BASE"]:
                os.environ.pop(key, None)

            from android.app.src.main.python import mobile_main

            with caplog.at_level("INFO"):
                mobile_main.setup_android_environment()

            # Verify .env was loaded
            assert "Loading configuration from" in caplog.text
            assert os.environ.get("OPENAI_API_KEY") == "test-key-12345"
            assert os.environ.get("OPENAI_API_BASE") == "http://test.api"
        finally:
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

    def test_android_environment_handles_missing_env_file(self, tmp_path, caplog):
        """Test graceful handling when .env file is missing."""
        android_data = tmp_path / "data"
        android_data.mkdir()

        env_backup = {"ANDROID_DATA": os.environ.get("ANDROID_DATA")}

        try:
            os.environ["ANDROID_DATA"] = str(android_data)
            os.environ.pop("CIRIS_HOME", None)

            from android.app.src.main.python import mobile_main

            with caplog.at_level("INFO"):
                mobile_main.setup_android_environment()

            assert "No .env file" in caplog.text
        finally:
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)


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
        mock_asyncio_run = MagicMock()

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

        with patch(
            "android.app.src.main.python.mobile_main.setup_android_environment",
            mock_setup,
        ):
            with patch(
                "android.app.src.main.python.mobile_main.asyncio.run",
                side_effect=KeyboardInterrupt(),
            ):
                from android.app.src.main.python import mobile_main

                with caplog.at_level("INFO"):
                    mobile_main.main()

                assert "Server stopped by user" in caplog.text

    def test_main_reraises_exceptions(self):
        """Test that main() re-raises unexpected exceptions."""
        mock_setup = MagicMock()

        with patch(
            "android.app.src.main.python.mobile_main.setup_android_environment",
            mock_setup,
        ):
            with patch(
                "android.app.src.main.python.mobile_main.asyncio.run",
                side_effect=ValueError("Test error"),
            ):
                from android.app.src.main.python import mobile_main

                with pytest.raises(ValueError, match="Test error"):
                    mobile_main.main()


class TestModuleAttributes:
    """Tests for module-level attributes and logging configuration."""

    def test_module_has_logger(self):
        """Test that the module has a logger configured."""
        from android.app.src.main.python import mobile_main

        assert hasattr(mobile_main, "logger")
        assert mobile_main.logger.name == "android.app.src.main.python.mobile_main"

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

    def test_low_resource_optimization_defaults(self, tmp_path):
        """Test that low-resource optimization defaults are set."""
        android_data = tmp_path / "data"
        android_data.mkdir()

        env_backup = {
            "ANDROID_DATA": os.environ.get("ANDROID_DATA"),
            "CIRIS_MAX_WORKERS": os.environ.get("CIRIS_MAX_WORKERS"),
            "CIRIS_LOG_LEVEL": os.environ.get("CIRIS_LOG_LEVEL"),
        }

        try:
            os.environ["ANDROID_DATA"] = str(android_data)
            for key in ["CIRIS_MAX_WORKERS", "CIRIS_LOG_LEVEL", "CIRIS_HOME"]:
                os.environ.pop(key, None)

            from android.app.src.main.python import mobile_main

            mobile_main.setup_android_environment()

            # Verify low-resource defaults
            assert os.environ.get("CIRIS_MAX_WORKERS") == "1"
            assert os.environ.get("CIRIS_LOG_LEVEL") == "INFO"
        finally:
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)

    def test_offline_mode_enabled(self, tmp_path):
        """Test that offline mode is enabled for Android."""
        android_data = tmp_path / "data"
        android_data.mkdir()

        env_backup = {"ANDROID_DATA": os.environ.get("ANDROID_DATA")}

        try:
            os.environ["ANDROID_DATA"] = str(android_data)
            os.environ.pop("CIRIS_HOME", None)

            from android.app.src.main.python import mobile_main

            mobile_main.setup_android_environment()

            assert os.environ.get("CIRIS_OFFLINE_MODE") == "true"
            assert os.environ.get("CIRIS_CLOUD_SYNC") == "false"
        finally:
            for key, value in env_backup.items():
                if value is not None:
                    os.environ[key] = value
                else:
                    os.environ.pop(key, None)
