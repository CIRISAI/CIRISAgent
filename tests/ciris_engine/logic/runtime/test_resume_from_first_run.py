"""
Unit tests for resume_from_first_run() functionality.

Tests the runtime's ability to resume from first-run mode after setup wizard completion.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime


class TestResumeFromFirstRun:
    """Test resume from first-run functionality in CIRISRuntime."""

    @pytest.fixture
    def temp_config_dir(self):
        """Create temporary config directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def mock_runtime(self, temp_config_dir):
        """Create mock runtime with necessary components."""
        runtime = Mock(spec=CIRISRuntime)
        runtime.service_initializer = Mock()
        runtime.service_initializer._initialize_llm_services = AsyncMock()
        runtime._wait_for_critical_services = AsyncMock()
        runtime._ensure_config = Mock()
        runtime.modules_to_load = []
        return runtime

    @pytest.mark.asyncio
    async def test_resume_from_first_run_loads_env(self, mock_runtime, temp_config_dir):
        """Test that resume_from_first_run loads environment variables."""
        # Create .env file
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\nCIRIS_CONFIGURED=true\n")

        with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
            with patch("dotenv.load_dotenv") as mock_load_dotenv:
                with patch("asyncio.create_task") as mock_create_task:
                    # Call the actual resume method
                    await CIRISRuntime.resume_from_first_run(mock_runtime)

                    # Verify environment was reloaded
                    mock_load_dotenv.assert_called_once_with(config_path, override=True)

    @pytest.mark.asyncio
    async def test_resume_from_first_run_initializes_llm(self, mock_runtime, temp_config_dir):
        """Test that resume_from_first_run initializes LLM service."""
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

        with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
            with patch("dotenv.load_dotenv"):
                with patch("asyncio.create_task") as mock_create_task:
                    # Call resume method
                    await CIRISRuntime.resume_from_first_run(mock_runtime)

                    # Verify LLM service was initialized
                    mock_runtime.service_initializer._initialize_llm_services.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_first_run_creates_agent_task(self, mock_runtime, temp_config_dir):
        """Test that resume_from_first_run creates agent processor task."""
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

        with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
            with patch("dotenv.load_dotenv"):
                with patch("asyncio.create_task") as mock_create_task:
                    # Mock _create_agent_processor_when_ready
                    mock_runtime._create_agent_processor_when_ready = AsyncMock()

                    # Call resume method
                    await CIRISRuntime.resume_from_first_run(mock_runtime)

                    # Verify agent task was created
                    mock_create_task.assert_called_once()
                    # The task should have been created with a name
                    call_kwargs = mock_create_task.call_args[1]
                    assert call_kwargs.get("name") == "AgentProcessorTask"

    @pytest.mark.asyncio
    async def test_resume_from_first_run_waits_for_services(self, mock_runtime, temp_config_dir):
        """Test that resume_from_first_run waits for critical services."""
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

        with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
            with patch("dotenv.load_dotenv"):
                with patch("asyncio.create_task"):
                    # Call resume method
                    await CIRISRuntime.resume_from_first_run(mock_runtime)

                    # Verify critical services check was called
                    mock_runtime._wait_for_critical_services.assert_called_once_with(timeout=5.0)

    @pytest.mark.asyncio
    async def test_resume_from_first_run_no_config_file(self, mock_runtime, temp_config_dir):
        """Test resume_from_first_run when config file doesn't exist."""
        config_path = temp_config_dir / ".env"
        # Don't create the file

        with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
            with patch("dotenv.load_dotenv") as mock_load_dotenv:
                with patch("asyncio.create_task"):
                    # Call resume method - should still work, just skip env loading
                    await CIRISRuntime.resume_from_first_run(mock_runtime)

                    # load_dotenv should NOT be called when file doesn't exist
                    # (implementation checks config_path.exists() first)
                    mock_load_dotenv.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_from_first_run_without_service_initializer(self, temp_config_dir):
        """Test resume_from_first_run when service_initializer is None."""
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

        runtime = Mock(spec=CIRISRuntime)
        runtime.service_initializer = None  # No service initializer
        runtime._wait_for_critical_services = AsyncMock()
        runtime._ensure_config = Mock()
        runtime.modules_to_load = []

        with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
            with patch("dotenv.load_dotenv"):
                with patch("asyncio.create_task"):
                    # Should not crash even without service_initializer
                    await CIRISRuntime.resume_from_first_run(runtime)

                    # Should still wait for services
                    runtime._wait_for_critical_services.assert_called_once()


class TestResumeFromFirstRunIntegration:
    """Integration tests for resume functionality."""

    @pytest.mark.asyncio
    async def test_resume_doesnt_restart_adapters(self):
        """Test that resume doesn't restart adapter lifecycles.

        This was the bug that caused the crash - we were canceling old adapter
        tasks and creating new ones, which tried to bind to port 8080 again.
        """
        runtime = Mock(spec=CIRISRuntime)
        runtime.service_initializer = Mock()
        runtime.service_initializer._initialize_llm_services = AsyncMock()
        runtime._wait_for_critical_services = AsyncMock()
        runtime._ensure_config = Mock()
        runtime.modules_to_load = []
        runtime._adapter_tasks = [Mock(done=Mock(return_value=False))]  # Existing adapter tasks

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".env"
            config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

            with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
                with patch("dotenv.load_dotenv"):
                    with patch("asyncio.create_task"):
                        # Call resume method
                        await CIRISRuntime.resume_from_first_run(runtime)

                        # Verify adapter tasks were NOT modified
                        # The old code would cancel these tasks - we shouldn't touch them
                        for task in runtime._adapter_tasks:
                            task.cancel.assert_not_called()
