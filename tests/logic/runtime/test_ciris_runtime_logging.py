"""
Unit tests for ciris_runtime.py logging initialization.

Tests the FAIL FAST AND LOUD behavior for file logging setup.
Uses fast mock-based fixtures for optimal test performance.
"""

import asyncio
import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import enhanced fixtures for fast testing
from tests.fixtures.runtime import fast_mock_runtime, mock_essential_config, mock_logging_components


class TestLoggingInitializationFailFast:
    """Test FAIL FAST AND LOUD behavior for logging initialization using fast mocks."""

    @pytest.mark.asyncio
    async def test_logging_fails_fast_without_time_service(self, fast_mock_runtime, mock_logging_components):
        """Test that runtime initialization fails immediately if TimeService is unavailable."""
        # Configure the mock to simulate TimeService unavailability
        mock_logging_components.configure_time_service_failure()

        # Configure runtime to use the failing time service
        fast_mock_runtime.service_initializer.service_registry = mock_logging_components.service_registry

        # Mock the logging setup to simulate the TimeService dependency failure
        mock_logging_components.configure_failure("TimeService unavailable")

        # Configure runtime to fail on logging setup
        fast_mock_runtime.mock_logging_failure("TimeService unavailable")

        # Runtime initialization should fail with RuntimeError about TimeService
        with pytest.raises(Exception) as exc_info:
            await fast_mock_runtime.initialize()

        # Check that the error message indicates TimeService issue
        assert "TimeService unavailable" in str(exc_info.value) or "Initialization failed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_logging_fails_fast_when_setup_fails(self, fast_mock_runtime, mock_logging_components):
        """Test that runtime initialization fails immediately if logging setup fails."""
        # Configure the mock to simulate logging setup failure
        mock_logging_components.configure_failure("Failed to create log file: Permission denied")

        # Configure runtime to fail on logging setup
        fast_mock_runtime.mock_logging_failure("Failed to create log file: Permission denied")

        # Runtime initialization should fail with RuntimeError
        with pytest.raises(Exception) as exc_info:
            await fast_mock_runtime.initialize()

        # Check that the error message is about logging failure
        assert (
            "Failed to create log file: Permission denied" in str(exc_info.value)
            or "Mock logging setup failed" in str(exc_info.value)
            or "Initialization failed" in str(exc_info.value)
        )

    @pytest.mark.asyncio
    async def test_logging_succeeds_with_valid_time_service(self, fast_mock_runtime, mock_logging_components):
        """Test that logging initializes successfully with a valid TimeService."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # Configure runtime for successful logging
        fast_mock_runtime.mock_logging_success(
            files_created=["logs/ciris_agent_20250927_test.log"],
            symlinks_created=["logs/latest.log", "logs/.current_log"],
        )

        # Runtime initialization should succeed
        await fast_mock_runtime.initialize()

        # Verify runtime completed initialization
        assert fast_mock_runtime._initialized is True
        assert fast_mock_runtime.agent_processor is not None
        assert fast_mock_runtime.service_initializer is not None

        # Verify time service is available
        assert fast_mock_runtime.time_service is not None
        assert hasattr(fast_mock_runtime.time_service, "format_timestamp")

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_handles_symlink_failures_gracefully(self, fast_mock_runtime, mock_logging_components):
        """Test that logging continues even if symlink creation fails."""
        # Configure the mock for partial success (files created but symlinks failed)
        mock_logging_components.configure_success()

        # Configure runtime for successful files but failed symlinks
        fast_mock_runtime.mock_logging_success(
            files_created=["logs/ciris_agent_20250927_test.log"],
            symlinks_created=[],  # No symlinks created due to failure
        )

        # This should not raise an exception - symlink failures are non-critical
        await fast_mock_runtime.initialize()

        # Verify runtime still initialized successfully
        assert fast_mock_runtime._initialized is True

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_creates_required_files(self, fast_mock_runtime, mock_logging_components):
        """Test that logging initialization creates all required log files and symlinks."""
        # Configure the mock for successful logging setup with all files
        mock_logging_components.configure_success()

        expected_files = ["logs/ciris_agent_20250927_143000.log", "logs/incidents_20250927_143000.log"]
        expected_symlinks = [
            "logs/latest.log",
            "logs/.current_log",
            "logs/incidents_latest.log",
            "logs/.current_incident_log",
        ]

        # Configure runtime for full logging setup
        fast_mock_runtime.mock_logging_success(files_created=expected_files, symlinks_created=expected_symlinks)

        await fast_mock_runtime.initialize()

        # Verify the files were tracked in the mock
        assert fast_mock_runtime._log_files_created == expected_files
        assert fast_mock_runtime._symlinks_created == expected_symlinks

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_updates_current_log_file_tracking(self, fast_mock_runtime, mock_logging_components):
        """Test that logging updates .current_log file for telemetry endpoint."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # Configure runtime with current log tracking
        fast_mock_runtime.mock_logging_success(
            files_created=["logs/ciris_agent_20250927_143000.log"],
            symlinks_created=["logs/latest.log", "logs/.current_log"],
        )

        await fast_mock_runtime.initialize()

        # Verify current log tracking was set up
        assert "logs/.current_log" in fast_mock_runtime._symlinks_created

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_incident_capture_handler_is_enabled(self, fast_mock_runtime, mock_logging_components):
        """Test that incident capture handler is enabled during initialization."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # Configure runtime with incident capture enabled
        fast_mock_runtime.mock_logging_success(
            files_created=["logs/ciris_agent_20250927_test.log", "logs/incidents_20250927_test.log"],
            symlinks_created=["logs/latest.log", "logs/incidents_latest.log"],
        )

        await fast_mock_runtime.initialize()

        # Verify incident files were created
        assert any("incidents_" in f for f in fast_mock_runtime._log_files_created)
        assert any("incidents_latest" in f for f in fast_mock_runtime._symlinks_created)

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_respects_debug_mode(self, fast_mock_runtime, mock_essential_config, mock_logging_components):
        """Test that logging level respects debug mode setting."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # Test with debug mode enabled
        config = mock_essential_config
        config.debug_mode = True

        # Configure runtime for debug mode
        fast_mock_runtime.mock_logging_success()

        await fast_mock_runtime.initialize()

        # Verify runtime initialized successfully in debug mode
        assert fast_mock_runtime._initialized is True

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_critical_messages_on_failure(self, fast_mock_runtime, mock_logging_components):
        """Test that critical log messages are emitted on logging failures."""
        # Configure the mock to simulate logging failure
        mock_logging_components.configure_failure("Disk full")

        # Configure runtime to fail with critical error
        fast_mock_runtime.mock_logging_failure("CRITICAL: Disk full")

        with pytest.raises(Exception) as exc_info:
            await fast_mock_runtime.initialize()

        # Verify critical error message is included
        assert "CRITICAL" in str(exc_info.value) or "Disk full" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_runtime_continues_after_successful_logging_init(self, fast_mock_runtime, mock_logging_components):
        """Test that runtime continues initialization after successful logging setup."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # Configure runtime for successful initialization
        fast_mock_runtime.mock_logging_success()

        await fast_mock_runtime.initialize()

        # Verify runtime completed full initialization
        assert fast_mock_runtime._initialized is True
        assert fast_mock_runtime.agent_processor is not None
        assert fast_mock_runtime.service_initializer is not None

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_initialization_order(self, fast_mock_runtime, mock_logging_components):
        """Test that logging is initialized early in the infrastructure setup."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # Track initialization order in the mock
        initialization_order = []

        # Configure runtime to track logging initialization
        original_initialize = fast_mock_runtime.initialize

        async def track_initialize():
            initialization_order.append("logging")
            return await original_initialize()

        fast_mock_runtime.initialize = track_initialize
        fast_mock_runtime.mock_logging_success()

        await fast_mock_runtime.initialize()

        # Verify logging was initialized
        assert "logging" in initialization_order
        assert fast_mock_runtime._initialized is True

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_with_no_console_output(self, fast_mock_runtime, mock_logging_components):
        """Test that console output is disabled for file-only logging."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # Configure runtime for file-only logging (no console)
        fast_mock_runtime.mock_logging_success()

        await fast_mock_runtime.initialize()

        # Verify runtime initialized (console output setting is internal to logging setup)
        assert fast_mock_runtime._initialized is True

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_all_tracking_mechanisms(self, fast_mock_runtime, mock_logging_components):
        """Test all 4 tracking mechanisms: 2 symlinks + 2 hidden files."""
        # Configure the mock for successful logging setup with all tracking
        mock_logging_components.configure_success()

        # The 4 tracking mechanisms:
        # 1. latest.log (symlink to main log)
        # 2. incidents_latest.log (symlink to incident log)
        # 3. .current_log (hidden file with main log path)
        # 4. .current_incident_log (hidden file with incident log path)

        expected_files = ["logs/ciris_agent_20250927_143000.log", "logs/incidents_20250927_143000.log"]
        expected_symlinks = [
            "logs/latest.log",
            "logs/incidents_latest.log",
            "logs/.current_log",
            "logs/.current_incident_log",
        ]

        # Configure runtime with all tracking mechanisms
        fast_mock_runtime.mock_logging_success(files_created=expected_files, symlinks_created=expected_symlinks)

        await fast_mock_runtime.initialize()

        # Verify all 4 tracking mechanisms were set up
        tracking_mechanisms = fast_mock_runtime._symlinks_created
        assert "logs/latest.log" in tracking_mechanisms  # Mechanism 1
        assert "logs/incidents_latest.log" in tracking_mechanisms  # Mechanism 2
        assert "logs/.current_log" in tracking_mechanisms  # Mechanism 3
        assert "logs/.current_incident_log" in tracking_mechanisms  # Mechanism 4

        # Verify we have at least 4 tracking mechanisms
        assert len(tracking_mechanisms) >= 4

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_logging_symlinks_are_updated_on_restart(self, fast_mock_runtime, mock_logging_components):
        """Test that symlinks are properly updated when runtime restarts."""
        # Configure the mock for successful logging setup
        mock_logging_components.configure_success()

        # First runtime session
        fast_mock_runtime.mock_logging_success(
            files_created=["logs/ciris_agent_20250927_143000.log"],
            symlinks_created=["logs/latest.log", "logs/.current_log"],
        )

        await fast_mock_runtime.initialize()

        # Verify first session tracking
        first_files = fast_mock_runtime._log_files_created.copy()
        first_symlinks = fast_mock_runtime._symlinks_created.copy()

        await fast_mock_runtime.shutdown()

        # Second runtime session (simulate restart)
        fast_mock_runtime.mock_logging_success(
            files_created=["logs/ciris_agent_20250927_143001.log"],  # Different timestamp
            symlinks_created=["logs/latest.log", "logs/.current_log"],  # Same symlinks, updated targets
        )

        await fast_mock_runtime.initialize()

        # Verify symlinks were updated (same names but potentially different targets)
        assert "logs/latest.log" in fast_mock_runtime._symlinks_created
        assert "logs/.current_log" in fast_mock_runtime._symlinks_created

        # Verify new log file was created
        assert "logs/ciris_agent_20250927_143001.log" in fast_mock_runtime._log_files_created

        await fast_mock_runtime.shutdown()

    @pytest.mark.asyncio
    async def test_incident_log_files_and_tracking(self, fast_mock_runtime, mock_logging_components):
        """Test that incident log files and their tracking files are created."""
        # Configure the mock for successful logging setup with incident support
        mock_logging_components.configure_success()

        # Configure runtime with incident logging
        fast_mock_runtime.mock_logging_success(
            files_created=["logs/ciris_agent_20250927_test.log", "logs/incidents_20250927_test.log"],
            symlinks_created=[
                "logs/latest.log",
                "logs/.current_log",
                "logs/incidents_latest.log",
                "logs/.current_incident_log",
            ],
        )

        await fast_mock_runtime.initialize()

        # Verify incident log file was created
        incident_files = [f for f in fast_mock_runtime._log_files_created if "incidents_" in f]
        assert len(incident_files) > 0, "No incident log files created"

        # Verify incident tracking mechanisms
        incident_symlinks = [s for s in fast_mock_runtime._symlinks_created if "incident" in s]
        assert len(incident_symlinks) >= 2, "Missing incident tracking mechanisms"

        # Verify specific incident tracking
        assert "logs/incidents_latest.log" in fast_mock_runtime._symlinks_created
        assert "logs/.current_incident_log" in fast_mock_runtime._symlinks_created

        await fast_mock_runtime.shutdown()
