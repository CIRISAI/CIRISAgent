"""
Unit tests for resume_from_first_run() functionality.

Tests the runtime's ability to resume from first-run mode after setup wizard completion.
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

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
        runtime = MagicMock(spec=CIRISRuntime)
        runtime.service_initializer = MagicMock()
        runtime.service_initializer._initialize_llm_services = AsyncMock()
        runtime.service_initializer.initialize_all_services = AsyncMock()
        runtime.service_initializer.load_modules = AsyncMock()
        runtime.service_initializer.auth_service = MagicMock()
        runtime._wait_for_critical_services = AsyncMock()
        runtime._ensure_config = MagicMock()
        runtime._ensure_config.return_value.default_template = "default"
        runtime._ensure_config.return_value.load_env_vars = MagicMock()
        runtime._build_components = AsyncMock()
        runtime._reinitialize_billing_provider = AsyncMock()
        runtime._register_adapter_services_for_resume = AsyncMock()
        runtime._perform_startup_maintenance = AsyncMock()
        runtime._create_startup_node = AsyncMock()
        runtime._create_agent_processor_when_ready = AsyncMock()
        runtime.modules_to_load = []
        runtime.adapters = []
        runtime.essential_config = MagicMock()
        runtime.startup_channel_id = None

        # Identity-related attributes - use MagicMock that returns async mock for initialize_identity
        mock_identity_manager = MagicMock()
        mock_identity_manager.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test-agent"))
        runtime.identity_manager = mock_identity_manager
        runtime.time_service = MagicMock()
        runtime.agent_identity = MagicMock(agent_id="test-agent")
        runtime.maintenance_service = MagicMock()
        runtime.service_registry = MagicMock()
        return runtime

    @pytest.mark.asyncio
    async def test_resume_from_first_run_loads_env(self, mock_runtime, temp_config_dir):
        """Test that resume_from_first_run calls the environment reload helper."""
        # Create .env file
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\nCIRIS_CONFIGURED=true\n")

        # Mock the helper method to track calls
        mock_runtime._resume_reload_environment = MagicMock(return_value=MagicMock())

        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as mock_identity_cls:
            mock_identity_cls.return_value.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test"))
            with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
                # Call the actual resume method
                await CIRISRuntime.resume_from_first_run(mock_runtime)

                # Verify the environment reload helper was called
                mock_runtime._resume_reload_environment.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_first_run_initializes_llm(self, mock_runtime, temp_config_dir):
        """Test that resume_from_first_run calls the LLM initialization helper."""
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

        # Mock the helper method to track calls
        mock_runtime._resume_initialize_llm = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as mock_identity_cls:
            mock_identity_cls.return_value.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test"))
            with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
                # Call resume method
                await CIRISRuntime.resume_from_first_run(mock_runtime)

                # Verify LLM initialization helper was called
                mock_runtime._resume_initialize_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_from_first_run_creates_agent_task(self, mock_runtime, temp_config_dir):
        """Test that resume_from_first_run creates agent processor task."""
        config_path = temp_config_dir / ".env"
        config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as mock_identity_cls:
            mock_identity_cls.return_value.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test"))
            with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
                with patch("dotenv.load_dotenv"):
                    with patch("asyncio.create_task") as mock_create_task:
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

        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as mock_identity_cls:
            mock_identity_cls.return_value.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test"))
            with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
                with patch("dotenv.load_dotenv"):
                    with patch("asyncio.create_task"):
                        # Call resume method
                        await CIRISRuntime.resume_from_first_run(mock_runtime)

                        # Verify critical services check was called with 10s timeout
                        mock_runtime._wait_for_critical_services.assert_called_once_with(timeout=10.0)

    @pytest.mark.asyncio
    async def test_resume_from_first_run_no_config_file(self, mock_runtime, temp_config_dir):
        """Test resume_from_first_run when config file doesn't exist."""
        config_path = temp_config_dir / ".env"
        # Don't create the file

        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as mock_identity_cls:
            mock_identity_cls.return_value.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test"))
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

        runtime = MagicMock(spec=CIRISRuntime)
        runtime.service_initializer = None  # No service initializer
        runtime._wait_for_critical_services = AsyncMock()
        runtime._ensure_config = MagicMock()
        runtime._ensure_config.return_value.default_template = "default"
        runtime._ensure_config.return_value.load_env_vars = MagicMock()
        runtime._build_components = AsyncMock()
        runtime._reinitialize_billing_provider = AsyncMock()
        runtime._register_adapter_services_for_resume = AsyncMock()
        runtime._perform_startup_maintenance = AsyncMock()
        runtime._create_startup_node = AsyncMock()
        runtime._create_agent_processor_when_ready = AsyncMock()
        runtime.modules_to_load = []
        runtime.adapters = []
        runtime.essential_config = MagicMock()
        runtime.startup_channel_id = None
        runtime.identity_manager = MagicMock()
        runtime.identity_manager.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test-agent"))
        runtime.time_service = MagicMock()
        runtime.agent_identity = MagicMock(agent_id="test-agent")
        runtime.maintenance_service = None  # No maintenance service either
        runtime.service_registry = None

        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as mock_identity_cls:
            mock_identity_cls.return_value.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test"))
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
        runtime = MagicMock(spec=CIRISRuntime)
        runtime.service_initializer = MagicMock()
        runtime.service_initializer._initialize_llm_services = AsyncMock()
        runtime.service_initializer.initialize_all_services = AsyncMock()
        runtime.service_initializer.load_modules = AsyncMock()
        runtime.service_initializer.auth_service = MagicMock()
        runtime._wait_for_critical_services = AsyncMock()
        runtime._ensure_config = MagicMock()
        runtime._ensure_config.return_value.default_template = "default"
        runtime._ensure_config.return_value.load_env_vars = MagicMock()
        runtime._build_components = AsyncMock()
        runtime._reinitialize_billing_provider = AsyncMock()
        runtime._register_adapter_services_for_resume = AsyncMock()
        runtime._perform_startup_maintenance = AsyncMock()
        runtime._create_startup_node = AsyncMock()
        runtime._create_agent_processor_when_ready = AsyncMock()
        runtime.modules_to_load = []
        runtime.adapters = []
        runtime.essential_config = MagicMock()
        runtime.startup_channel_id = None
        runtime.identity_manager = MagicMock()
        runtime.identity_manager.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test-agent"))
        runtime.time_service = MagicMock()
        runtime.agent_identity = MagicMock(agent_id="test-agent")
        runtime.maintenance_service = MagicMock()
        runtime.service_registry = MagicMock()
        runtime._adapter_tasks = [MagicMock(done=MagicMock(return_value=False))]  # Existing adapter tasks

        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / ".env"
            config_path.write_text("OPENAI_API_KEY=sk-test-key\n")

            with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as mock_identity_cls:
                mock_identity_cls.return_value.initialize_identity = AsyncMock(return_value=MagicMock(agent_id="test"))
                with patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=config_path):
                    with patch("dotenv.load_dotenv"):
                        with patch("asyncio.create_task"):
                            # Call resume method
                            await CIRISRuntime.resume_from_first_run(runtime)

                            # Verify adapter tasks were NOT modified
                            # The old code would cancel these tasks - we shouldn't touch them
                            for task in runtime._adapter_tasks:
                                task.cancel.assert_not_called()
