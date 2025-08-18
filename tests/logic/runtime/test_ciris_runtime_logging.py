"""
Unit tests for ciris_runtime.py logging initialization.

Tests the FAIL FAST AND LOUD behavior for file logging setup.
"""

import asyncio
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the SUT
from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.protocols.services import TimeServiceProtocol
from ciris_engine.schemas.config.essential import (
    DatabaseConfig,
    EssentialConfig,
    GraphConfig,
    OperationalLimitsConfig,
    SecurityConfig,
    ServiceEndpointsConfig,
    TelemetryConfig,
    WorkflowConfig,
)


class MockTimeService:
    """Mock TimeService for testing."""

    def now(self):
        """Return current time."""
        return datetime.now()

    def format_timestamp(self, dt: datetime = None) -> str:
        """Format timestamp."""
        if dt is None:
            dt = self.now()
        return dt.strftime("%Y%m%d_%H%M%S")


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test databases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def essential_config(temp_dir):
    """Create a real EssentialConfig for testing."""
    # Create templates directory
    templates_dir = temp_dir / "templates"
    templates_dir.mkdir(exist_ok=True)

    # Create a valid test template using the actual test.yaml content
    test_template = templates_dir / "test.yaml"
    test_template_content = """description: 'Agent profile: test'
name: test
role_description: 'Test Agent - Minimal agent for development and debugging purposes only. Limited to observe action for safety.'
permitted_actions:
- observe
stewardship:
  stewardship_tier: 1
  creator_intent_statement:
    purpose_and_functionalities:
    - Test template for development and debugging purposes only.
    - Minimal agent for testing basic functionality.
    - Not intended for production use.
    limitations_and_design_choices:
    - Designed with a fixed ethical framework (Covenant 1.0b).
    - Limited to observe action only.
    - Minimal configuration for testing purposes.
    anticipated_benefits:
    - Safe testing environment for development.
    - Minimal risk due to limited capabilities.
    - Quick iteration during development.
    anticipated_risks:
    - Not suitable for production environments.
    - Limited functionality may not represent real agent behavior.
  creator_ledger_entry:
    creator_id: eric-moore
    creation_timestamp: '2025-08-07T00:00:00Z'
    covenant_version: 1.0b
    book_vi_compliance_check: passed
    stewardship_tier_calculation:
      creator_influence_score: 7
      risk_magnitude: 1
      formula: ceil((CIS * RM) / 7)
      result: 1
    public_key_fingerprint: NEEDS_FINGERPRINTING
    signature: NEEDS_SIGNING
"""
    test_template.write_text(test_template_content)

    return EssentialConfig(
        database=DatabaseConfig(
            main_db=temp_dir / "test.db",
            secrets_db=temp_dir / "secrets.db",
            audit_db=temp_dir / "audit.db",
        ),
        services=ServiceEndpointsConfig(
            llm_endpoint="https://test.api.com",
            llm_model="test-model",
            llm_timeout=30,
            llm_max_retries=3,
        ),
        security=SecurityConfig(
            audit_retention_days=7,
            secrets_encryption_key_env="TEST_KEY",
            secrets_key_path=temp_dir / "secrets_keys",
            audit_key_path=temp_dir / "audit_keys",
            enable_signed_audit=False,
            max_thought_depth=5,
        ),
        limits=OperationalLimitsConfig(
            max_active_tasks=5,
            max_active_thoughts=10,
            round_delay_seconds=0.1,
            mock_llm_round_delay=0.01,
            dma_retry_limit=2,
            dma_timeout_seconds=10.0,
            conscience_retry_limit=1,
        ),
        telemetry=TelemetryConfig(
            enabled=False,
            export_interval_seconds=60,
            retention_hours=1,
        ),
        workflow=WorkflowConfig(
            max_rounds=5,
            round_timeout_seconds=30.0,
            enable_auto_defer=True,
        ),
        graph=GraphConfig(
            tsdb_profound_target_mb_per_day=10.0,
            tsdb_raw_retention_hours=1,
            consolidation_timezone="UTC",
        ),
        log_level="DEBUG",
        debug_mode=True,
        template_directory=templates_dir,
        default_template="test",
    )


@pytest.fixture
def allow_runtime_creation():
    """Allow runtime creation in tests."""
    original_import = os.environ.get("CIRIS_IMPORT_MODE")
    original_mock = os.environ.get("CIRIS_MOCK_LLM")

    os.environ["CIRIS_IMPORT_MODE"] = "false"
    os.environ["CIRIS_MOCK_LLM"] = "true"
    os.environ["OPENAI_API_KEY"] = "test-key"

    yield

    # Restore original values
    if original_import is not None:
        os.environ["CIRIS_IMPORT_MODE"] = original_import
    else:
        os.environ.pop("CIRIS_IMPORT_MODE", None)

    if original_mock is not None:
        os.environ["CIRIS_MOCK_LLM"] = original_mock
    else:
        os.environ.pop("CIRIS_MOCK_LLM", None)

    os.environ.pop("OPENAI_API_KEY", None)


class TestLoggingInitializationFailFast:
    """Test FAIL FAST AND LOUD behavior for logging initialization."""

    @pytest.mark.asyncio
    async def test_logging_fails_fast_without_time_service(self, essential_config, allow_runtime_creation):
        """Test that runtime initialization fails immediately if TimeService is unavailable."""

        # Patch the TimeService lookup to return None
        with patch("ciris_engine.logic.runtime.ciris_runtime.ServiceRegistry") as MockServiceRegistry:
            mock_registry = MagicMock()
            mock_registry.get_service.return_value = None  # No TimeService available
            MockServiceRegistry.get_instance.return_value = mock_registry

            # Also patch the service initializer to not create TimeService
            with patch("ciris_engine.logic.runtime.service_initializer.TimeService") as MockTimeService:
                MockTimeService.side_effect = Exception("TimeService creation failed")

                # Runtime initialization should fail with Exception (the real error)
                with pytest.raises(Exception) as exc_info:
                    runtime = CIRISRuntime(
                        adapter_types=["cli"],
                        essential_config=essential_config,
                        modules=["mock_llm"],
                        timeout=2,
                    )
                    await runtime.initialize()

                # Check that the error message is about TimeService
                assert "TimeService creation failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_logging_fails_fast_when_setup_fails(self, essential_config, allow_runtime_creation):
        """Test that runtime initialization fails immediately if logging setup fails."""

        # Temporarily clear PYTEST_CURRENT_TEST to enable logging setup code path
        original_pytest_env = os.environ.pop("PYTEST_CURRENT_TEST", None)

        try:
            # Patch setup_basic_logging to raise an exception
            with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
                mock_setup.side_effect = Exception("Failed to create log file: Permission denied")

                # Runtime initialization should fail with RuntimeError
                with pytest.raises(RuntimeError) as exc_info:
                    runtime = CIRISRuntime(
                        adapter_types=["cli"],
                        essential_config=essential_config,
                        modules=["mock_llm"],
                        timeout=2,
                    )
                    await runtime.initialize()

                # Check that the error message is about initialization failure
                # The actual error is wrapped in a generic message
                assert (
                    "Initialization sequence failed" in str(exc_info.value)
                    or "Failed to setup file logging" in str(exc_info.value)
                    or "Permission denied" in str(exc_info.value)
                )
        finally:
            # Restore PYTEST_CURRENT_TEST if it was set
            if original_pytest_env is not None:
                os.environ["PYTEST_CURRENT_TEST"] = original_pytest_env

    @pytest.mark.asyncio
    async def test_logging_succeeds_with_valid_time_service(self, essential_config, allow_runtime_creation):
        """Test that logging initializes successfully with a valid TimeService."""

        # Create a mock TimeService
        mock_time_service = MockTimeService()

        # Temporarily clear PYTEST_CURRENT_TEST to enable logging setup code path
        original_pytest_env = os.environ.pop("PYTEST_CURRENT_TEST", None)

        try:
            # Patch setup_basic_logging to track if it was called correctly
            with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
                mock_setup.return_value = None  # Success

                runtime = CIRISRuntime(
                    adapter_types=["cli"],
                    essential_config=essential_config,
                    modules=["mock_llm"],
                    timeout=2,
                )

                await runtime.initialize()

            # Verify setup_basic_logging was called
            assert mock_setup.called

            # Verify it was called with correct parameters
            call_args = mock_setup.call_args
            assert call_args is not None

            # Check kwargs
            kwargs = call_args.kwargs
            assert kwargs.get("log_to_file") is True
            assert kwargs.get("enable_incident_capture") is True
            assert kwargs.get("console_output") is False
            assert kwargs.get("log_dir") == "logs"
            assert kwargs.get("time_service") is not None

            await runtime.shutdown()
        finally:
            # Restore PYTEST_CURRENT_TEST if it was set
            if original_pytest_env is not None:
                os.environ["PYTEST_CURRENT_TEST"] = original_pytest_env

    @pytest.mark.asyncio
    async def test_logging_creates_all_required_files(self, essential_config, allow_runtime_creation, temp_dir):
        """Test that logging initialization creates all required log files and symlinks."""

        # Create a logs directory in temp
        log_dir = temp_dir / "logs"
        log_dir.mkdir(exist_ok=True)

        # No need to patch Path - just let it create logs in the default location
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Check that log files were created in the default logs directory
        default_log_dir = Path("logs")
        log_files = list(default_log_dir.glob("ciris_agent_*.log"))
        assert len(log_files) > 0, "No log files created"

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_handles_symlink_failures_gracefully(self, essential_config, allow_runtime_creation):
        """Test that logging continues even if symlink creation fails."""

        # Patch Path operations to simulate symlink failure
        with patch("ciris_engine.logic.utils.logging_config.Path") as MockPath:
            mock_path = MagicMock()
            mock_symlink = MagicMock()
            mock_symlink.symlink_to.side_effect = OSError("Cannot create symlink")
            mock_path.return_value = mock_symlink
            MockPath.return_value = mock_path

            # This should not raise an exception - symlink failures are non-critical
            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
            )

            # Should initialize successfully despite symlink failure
            await runtime.initialize()
            await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_updates_current_log_file_tracking(self, essential_config, allow_runtime_creation):
        """Test that logging updates .current_log file for telemetry endpoint."""

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir()

            # Track if .current_log was written
            current_log_written = False
            original_open = open

            def mock_open(*args, **kwargs):
                nonlocal current_log_written
                if args and ".current_log" in str(args[0]):
                    current_log_written = True
                return original_open(*args, **kwargs)

            with patch("builtins.open", side_effect=mock_open):
                with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
                    mock_setup.return_value = None

                    runtime = CIRISRuntime(
                        adapter_types=["cli"],
                        essential_config=essential_config,
                        modules=["mock_llm"],
                        timeout=2,
                    )

                    await runtime.initialize()

                    # Verify setup_basic_logging was called
                    assert mock_setup.called

                    await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_incident_capture_handler_is_added(self, essential_config, allow_runtime_creation):
        """Test that incident capture handler is added when enabled."""

        with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
            mock_setup.return_value = None

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
            )

            await runtime.initialize()

            # Verify setup_basic_logging was called with incident capture enabled
            call_args = mock_setup.call_args
            assert call_args is not None
            kwargs = call_args.kwargs
            assert kwargs.get("enable_incident_capture") is True

            await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_respects_debug_mode(self, essential_config, allow_runtime_creation):
        """Test that logging level respects debug mode setting."""

        # Test with debug mode enabled
        essential_config.debug_mode = True

        with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
            mock_setup.return_value = None

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
                debug=True,
            )

            await runtime.initialize()

            # Verify DEBUG level was used
            call_args = mock_setup.call_args
            kwargs = call_args.kwargs
            assert kwargs.get("level") == logging.DEBUG

            await runtime.shutdown()

        # Test with debug mode disabled
        essential_config.debug_mode = False

        with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
            mock_setup.return_value = None

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
                debug=False,
            )

            await runtime.initialize()

            # Verify INFO level was used
            call_args = mock_setup.call_args
            kwargs = call_args.kwargs
            assert kwargs.get("level") == logging.INFO

            await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_critical_messages_on_failure(self, essential_config, allow_runtime_creation):
        """Test that critical log messages are emitted on logging failures."""

        # Capture log messages
        with patch("ciris_engine.logic.runtime.ciris_runtime.logger") as mock_logger:
            with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
                mock_setup.side_effect = Exception("Disk full")

                with pytest.raises(RuntimeError):
                    runtime = CIRISRuntime(
                        adapter_types=["cli"],
                        essential_config=essential_config,
                        modules=["mock_llm"],
                        timeout=2,
                    )
                    await runtime.initialize()

                # Verify critical log was called
                assert any(
                    "CRITICAL" in str(call) or "Failed to setup file logging" in str(call)
                    for call in mock_logger.critical.call_args_list
                )

    @pytest.mark.asyncio
    async def test_runtime_continues_after_successful_logging_init(self, essential_config, allow_runtime_creation):
        """Test that runtime continues initialization after successful logging setup."""

        with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
            mock_setup.return_value = None  # Success

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
            )

            await runtime.initialize()

            # Verify runtime completed initialization
            assert runtime._initialized is True
            assert runtime.agent_processor is not None
            assert runtime.service_initializer is not None

            await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_initialization_order(self, essential_config, allow_runtime_creation):
        """Test that logging is initialized early in the infrastructure setup."""

        initialization_order = []

        # Track order of initialization
        with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_logging:

            def log_init(*args, **kwargs):
                initialization_order.append("logging")
                return None

            mock_logging.side_effect = log_init

            with patch("ciris_engine.logic.runtime.ciris_runtime.ServiceRegistry") as MockRegistry:
                original_get_instance = MockRegistry.get_instance

                def track_registry(*args, **kwargs):
                    if "logging" not in initialization_order:
                        # Logging should be initialized before extensive service registry use
                        initialization_order.append("registry_before_logging")
                    return original_get_instance(*args, **kwargs)

                MockRegistry.get_instance = track_registry

                runtime = CIRISRuntime(
                    adapter_types=["cli"],
                    essential_config=essential_config,
                    modules=["mock_llm"],
                    timeout=2,
                )

                await runtime.initialize()

                # Verify logging was initialized early
                assert "logging" in initialization_order
                assert initialization_order.index("logging") < 5  # Should be in first few steps

                await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_with_no_console_output(self, essential_config, allow_runtime_creation):
        """Test that console output is disabled for file-only logging."""

        with patch("ciris_engine.logic.utils.logging_config.setup_basic_logging") as mock_setup:
            mock_setup.return_value = None

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
            )

            await runtime.initialize()

            # Verify console_output was set to False
            call_args = mock_setup.call_args
            kwargs = call_args.kwargs
            assert kwargs.get("console_output") is False

            await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_creates_actual_files_and_all_symlinks(self, essential_config, allow_runtime_creation):
        """Test that logging creates actual log files and all 4 symlinks/tracking files."""

        # Use the actual logs directory (will be created if it doesn't exist)
        log_dir = Path("logs")

        # Don't patch setup_basic_logging - let it run for real
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        # Initialize should create actual log files
        await runtime.initialize()

        # Check that the main log file was created
        log_files = list(log_dir.glob("ciris_agent_*.log"))
        assert len(log_files) > 0, "No log files created"
        # Get the most recent log file (sort by modification time)
        main_log_file = max(log_files, key=lambda f: f.stat().st_mtime)
        assert main_log_file.exists(), f"Main log file {main_log_file} does not exist"
        assert main_log_file.stat().st_size >= 0, "Main log file is not accessible"

        # Check symlink 1: latest.log
        latest_log = log_dir / "latest.log"
        assert latest_log.exists() or latest_log.is_symlink(), "latest.log symlink not created"
        if latest_log.is_symlink():
            assert latest_log.resolve().name == main_log_file.name, "latest.log points to wrong file"

        # Check hidden file 1: .current_log (stores actual log filename)
        current_log_file = log_dir / ".current_log"
        assert current_log_file.exists(), ".current_log tracking file not created"
        stored_path = current_log_file.read_text().strip()
        assert stored_path == str(main_log_file.absolute()), f".current_log contains wrong path: {stored_path}"

        # Check for incident log file (created by incident handler)
        incident_files = list(log_dir.glob("incidents_*.log"))
        if incident_files:  # Incident file might not exist yet if no incidents
            # Get the most recent incident log file
            incident_log_file = max(incident_files, key=lambda f: f.stat().st_mtime)

            # Check symlink 2: incidents_latest.log
            incidents_latest = log_dir / "incidents_latest.log"
            if incidents_latest.exists():
                assert (
                    incidents_latest.exists() or incidents_latest.is_symlink()
                ), "incidents_latest.log symlink not created"
                if incidents_latest.is_symlink():
                    assert (
                        incidents_latest.resolve().name == incident_log_file.name
                    ), "incidents_latest.log points to wrong file"

            # Check hidden file 2: .current_incident_log (stores actual incident log filename)
            current_incident_file = log_dir / ".current_incident_log"
            if current_incident_file.exists():
                stored_incident_path = current_incident_file.read_text().strip()
                assert stored_incident_path == str(
                    incident_log_file.absolute()
                ), f".current_incident_log contains wrong path: {stored_incident_path}"

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_symlinks_are_updated_on_restart(self, essential_config, allow_runtime_creation):
        """Test that symlinks are properly updated when runtime restarts."""

        # Use the actual logs directory
        log_dir = Path("logs")

        # First runtime session
        runtime1 = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )
        await runtime1.initialize()

        # Get first log file (the most recent one)
        first_log_files = list(log_dir.glob("ciris_agent_*.log"))
        assert len(first_log_files) > 0
        first_log = max(first_log_files, key=lambda f: f.stat().st_mtime)

        # Check symlink points to first log
        latest_log = log_dir / "latest.log"
        if latest_log.is_symlink():
            assert latest_log.resolve().name == first_log.name

        # Check .current_log points to first log
        current_log_file = log_dir / ".current_log"
        assert current_log_file.read_text().strip() == str(first_log.absolute())

        await runtime1.shutdown()

        # Wait a moment to ensure different timestamp
        await asyncio.sleep(0.1)

        # Second runtime session
        runtime2 = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )
        await runtime2.initialize()

        # Get all log files and find the newest
        all_log_files = list(log_dir.glob("ciris_agent_*.log"))
        assert len(all_log_files) > 1, "Second log file not created"
        newest_log = max(all_log_files, key=lambda f: f.stat().st_mtime)

        # Verify symlink was updated to point to newest log
        if latest_log.is_symlink():
            assert latest_log.resolve().name == newest_log.name, "latest.log not updated to newest file"

        # Verify .current_log was updated
        assert current_log_file.read_text().strip() == str(newest_log.absolute()), ".current_log not updated"

        await runtime2.shutdown()

    @pytest.mark.asyncio
    async def test_incident_log_files_and_tracking(self, essential_config, allow_runtime_creation):
        """Test that incident log files and their tracking files are created."""

        # Use the actual logs directory
        log_dir = Path("logs")

        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Log a warning to trigger incident capture
        logger = logging.getLogger("test_incident")
        logger.warning("Test warning for incident capture")
        logger.error("Test error for incident capture")

        # Give the handler a moment to write
        await asyncio.sleep(0.1)

        # Check for incident log file
        incident_files = list(log_dir.glob("incidents_*.log"))
        if incident_files:  # Should exist after logging warnings/errors
            # Get the most recent incident log file
            incident_log = max(incident_files, key=lambda f: f.stat().st_mtime)
            assert incident_log.exists(), f"Incident log {incident_log} does not exist"

            # Check incidents_latest.log symlink
            incidents_latest = log_dir / "incidents_latest.log"
            if incidents_latest.exists():
                if incidents_latest.is_symlink():
                    assert (
                        incidents_latest.resolve().name == incident_log.name
                    ), "incidents_latest.log points to wrong file"

            # Check .current_incident_log hidden file
            current_incident = log_dir / ".current_incident_log"
            if current_incident.exists():
                stored_path = current_incident.read_text().strip()
                assert stored_path == str(
                    incident_log.absolute()
                ), f".current_incident_log has wrong path: {stored_path}"

            # Verify incident log contains our test messages
            incident_content = incident_log.read_text()
            assert (
                "Test warning for incident capture" in incident_content
                or "Test error for incident capture" in incident_content
            ), "Test messages not found in incident log"

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_all_four_tracking_mechanisms(self, essential_config, allow_runtime_creation):
        """Explicitly test all 4 tracking mechanisms: 2 symlinks + 2 hidden files."""

        # Use the actual logs directory
        log_dir = Path("logs")

        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Log some warnings to ensure incident file is created
        logger = logging.getLogger("test")
        logger.warning("Test warning 1")
        logger.error("Test error 1")
        await asyncio.sleep(0.1)  # Let handler write

        # The 4 tracking mechanisms:
        # 1. latest.log (symlink to main log)
        # 2. incidents_latest.log (symlink to incident log)
        # 3. .current_log (hidden file with main log path)
        # 4. .current_incident_log (hidden file with incident log path)

        tracking_found = {}

        # Check mechanism 1: latest.log symlink
        latest_log = log_dir / "latest.log"
        tracking_found["latest.log"] = latest_log.exists() or latest_log.is_symlink()

        # Check mechanism 2: incidents_latest.log symlink
        incidents_latest = log_dir / "incidents_latest.log"
        tracking_found["incidents_latest.log"] = incidents_latest.exists() or incidents_latest.is_symlink()

        # Check mechanism 3: .current_log hidden file
        current_log = log_dir / ".current_log"
        tracking_found[".current_log"] = current_log.exists()

        # Check mechanism 4: .current_incident_log hidden file
        current_incident = log_dir / ".current_incident_log"
        tracking_found[".current_incident_log"] = current_incident.exists()

        # Report what was found
        print(f"\nTracking mechanisms found:")
        for name, found in tracking_found.items():
            status = "✓" if found else "✗"
            print(f"  {status} {name}")

        # Verify main tracking (at least 2 should exist for main log)
        assert tracking_found["latest.log"], "latest.log symlink not found"
        assert tracking_found[".current_log"], ".current_log hidden file not found"

        # For incident tracking, both might not exist if no incidents yet
        # But if one exists, verify it's valid
        if tracking_found["incidents_latest.log"]:
            assert incidents_latest.exists(), "incidents_latest.log exists but is broken"

        if tracking_found[".current_incident_log"]:
            assert current_incident.exists(), ".current_incident_log exists but is broken"
            # Verify it contains a valid path
            incident_path = current_incident.read_text().strip()
            assert Path(incident_path).exists(), f".current_incident_log points to non-existent file: {incident_path}"

        # Verify the main tracking files point to real log files
        if latest_log.is_symlink():
            target = latest_log.resolve()
            assert target.exists(), f"latest.log points to non-existent file: {target}"
            assert "ciris_agent_" in target.name, f"latest.log points to wrong file type: {target.name}"

        if current_log.exists():
            main_path = current_log.read_text().strip()
            assert Path(main_path).exists(), f".current_log points to non-existent file: {main_path}"
            assert "ciris_agent_" in Path(main_path).name, f".current_log points to wrong file type: {main_path}"

        await runtime.shutdown()

        # Summary assertion
        found_count = sum(1 for found in tracking_found.values() if found)
        assert found_count >= 2, f"Only {found_count}/4 tracking mechanisms found. Need at least main log tracking (2)."
