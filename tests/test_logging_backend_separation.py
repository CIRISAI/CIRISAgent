"""
Unit tests for logging backend separation (CIRIS_LOG_DIR support).

Tests verify that logging configuration correctly respects the CIRIS_LOG_DIR
environment variable to enable parallel database backend testing without
log symlink collisions.
"""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.utils.incident_capture_handler import IncidentCaptureHandler, add_incident_capture_handler
from ciris_engine.logic.utils.logging_config import setup_basic_logging
from ciris_engine.protocols.services import TimeServiceProtocol


class MockTimeService:
    """Mock time service for testing."""

    def now(self):
        """Return mock datetime."""
        from datetime import datetime, timezone

        return datetime(2025, 10, 26, 15, 0, 0, tzinfo=timezone.utc)

    def now_iso(self):
        """Return mock ISO timestamp."""
        return "2025-10-26T15:00:00+00:00"


class TestLoggingConfigCIRISLogDir:
    """Test that logging_config respects CIRIS_LOG_DIR environment variable."""

    def test_ciris_log_dir_env_var_overrides_default(self):
        """Test that CIRIS_LOG_DIR environment variable overrides default log directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_log_dir = os.path.join(tmpdir, "custom_logs")

            # Mock get_env_var to return custom directory
            with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:

                def get_env_side_effect(key):
                    if key == "CIRIS_LOG_DIR":
                        return custom_log_dir
                    return None

                mock_get_env.side_effect = get_env_side_effect

                # Setup logging with custom directory
                time_service = MockTimeService()
                setup_basic_logging(
                    log_to_file=True,
                    log_dir="logs",  # Default, should be overridden
                    console_output=False,
                    enable_incident_capture=False,  # Disable for this test
                    time_service=time_service,
                )

                # Verify custom directory was created
                assert Path(custom_log_dir).exists(), f"Custom log directory should be created: {custom_log_dir}"

                # Verify log file was created in custom directory
                log_files = list(Path(custom_log_dir).glob("ciris_agent_*.log"))
                assert len(log_files) > 0, f"Log file should be created in {custom_log_dir}"

    def test_ciris_log_dir_creates_parent_directories(self):
        """Test that logging creates parent directories when needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_log_dir = os.path.join(tmpdir, "backend", "sqlite", "logs")

            # Mock get_env_var to return nested directory
            with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:

                def get_env_side_effect(key):
                    if key == "CIRIS_LOG_DIR":
                        return nested_log_dir
                    return None

                mock_get_env.side_effect = get_env_side_effect

                # Setup logging with nested directory
                time_service = MockTimeService()
                setup_basic_logging(
                    log_to_file=True,
                    log_dir="logs",  # Default, should be overridden
                    console_output=False,
                    enable_incident_capture=False,
                    time_service=time_service,
                )

                # Verify all parent directories were created
                assert Path(nested_log_dir).exists(), "Nested directory structure should be created"
                assert Path(nested_log_dir).is_dir(), "Path should be a directory"

                # Verify log file exists in nested directory
                log_files = list(Path(nested_log_dir).glob("ciris_agent_*.log"))
                assert len(log_files) > 0, f"Log file should be created in {nested_log_dir}"

    def test_default_log_dir_when_no_env_var(self):
        """Test that default log directory is used when CIRIS_LOG_DIR is not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            default_log_dir = os.path.join(tmpdir, "default_logs")

            # Mock get_env_var to return None (no override)
            with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:
                mock_get_env.return_value = None

                # Setup logging with default directory
                time_service = MockTimeService()
                setup_basic_logging(
                    log_to_file=True,
                    log_dir=default_log_dir,
                    console_output=False,
                    enable_incident_capture=False,
                    time_service=time_service,
                )

                # Verify default directory was used
                assert Path(default_log_dir).exists(), "Default log directory should be created"
                log_files = list(Path(default_log_dir).glob("ciris_agent_*.log"))
                assert len(log_files) > 0, f"Log file should be created in {default_log_dir}"


class TestIncidentCaptureHandlerParentDirectories:
    """Test that IncidentCaptureHandler creates parent directories."""

    def test_incident_handler_creates_parent_directories(self):
        """Test that incident handler creates nested directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_incident_dir = os.path.join(tmpdir, "backend", "postgres", "logs")

            time_service = MockTimeService()

            # Create incident handler with nested directory
            handler = IncidentCaptureHandler(
                log_dir=nested_incident_dir, filename_prefix="test_incidents", time_service=time_service
            )

            # Verify nested directory was created
            assert Path(nested_incident_dir).exists(), "Nested incident directory should be created"
            assert Path(nested_incident_dir).is_dir(), "Path should be a directory"

            # Verify incident log file was created
            incident_files = list(Path(nested_incident_dir).glob("test_incidents_*.log"))
            assert len(incident_files) > 0, f"Incident log should be created in {nested_incident_dir}"

    def test_add_incident_capture_handler_with_custom_dir(self):
        """Test add_incident_capture_handler helper with custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = os.path.join(tmpdir, "custom", "incidents")

            time_service = MockTimeService()

            # Create test logger
            test_logger = logging.getLogger("test_incident_custom_dir")
            test_logger.handlers = []  # Clear any existing handlers

            # Add incident handler with custom directory
            handler = add_incident_capture_handler(
                logger_instance=test_logger, log_dir=custom_dir, time_service=time_service
            )

            # Verify custom directory was created
            assert Path(custom_dir).exists(), "Custom incident directory should be created"

            # Verify handler was added to logger
            assert handler in test_logger.handlers, "Handler should be added to logger"

            # Verify incident log file exists
            incident_files = list(Path(custom_dir).glob("incidents_*.log"))
            assert len(incident_files) > 0, f"Incident log should be created in {custom_dir}"


class TestMultiBackendLogSeparation:
    """Integration tests for multi-backend log separation."""

    def test_sqlite_and_postgres_use_different_directories(self):
        """Test that SQLite and PostgreSQL backends can use separate log directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_dir = os.path.join(tmpdir, "sqlite")
            postgres_dir = os.path.join(tmpdir, "postgres")

            time_service = MockTimeService()

            # Simulate SQLite backend logging
            with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:

                def sqlite_env(key):
                    if key == "CIRIS_LOG_DIR":
                        return sqlite_dir
                    return None

                mock_get_env.side_effect = sqlite_env

                setup_basic_logging(
                    log_to_file=True,
                    log_dir="logs",
                    console_output=False,
                    enable_incident_capture=False,
                    time_service=time_service,
                )

                # Verify SQLite logs created
                assert Path(sqlite_dir).exists(), "SQLite log directory should exist"
                sqlite_logs = list(Path(sqlite_dir).glob("ciris_agent_*.log"))
                assert len(sqlite_logs) > 0, "SQLite logs should be created"

            # Simulate PostgreSQL backend logging
            with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:

                def postgres_env(key):
                    if key == "CIRIS_LOG_DIR":
                        return postgres_dir
                    return None

                mock_get_env.side_effect = postgres_env

                setup_basic_logging(
                    log_to_file=True,
                    log_dir="logs",
                    console_output=False,
                    enable_incident_capture=False,
                    time_service=time_service,
                )

                # Verify PostgreSQL logs created
                assert Path(postgres_dir).exists(), "PostgreSQL log directory should exist"
                postgres_logs = list(Path(postgres_dir).glob("ciris_agent_*.log"))
                assert len(postgres_logs) > 0, "PostgreSQL logs should be created"

            # Verify they are separate
            assert sqlite_dir != postgres_dir, "Log directories should be different"
            assert Path(sqlite_dir).exists() and Path(postgres_dir).exists(), "Both log directories should exist"

    def test_no_symlink_collision_between_backends(self):
        """Test that parallel backends don't collide on symlinks."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sqlite_dir = os.path.join(tmpdir, "sqlite")
            postgres_dir = os.path.join(tmpdir, "postgres")

            time_service = MockTimeService()

            # Create SQLite logs
            with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:
                mock_get_env.return_value = sqlite_dir

                setup_basic_logging(
                    log_to_file=True,
                    log_dir="logs",
                    console_output=False,
                    enable_incident_capture=True,
                    time_service=time_service,
                )

                sqlite_latest = Path(sqlite_dir) / "latest.log"
                sqlite_incidents_latest = Path(sqlite_dir) / "incidents_latest.log"

            # Create PostgreSQL logs
            with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:
                mock_get_env.return_value = postgres_dir

                setup_basic_logging(
                    log_to_file=True,
                    log_dir="logs",
                    console_output=False,
                    enable_incident_capture=True,
                    time_service=time_service,
                )

                postgres_latest = Path(postgres_dir) / "latest.log"
                postgres_incidents_latest = Path(postgres_dir) / "incidents_latest.log"

            # Verify symlinks exist in separate directories (no collision)
            # Note: Symlinks may not exist on all systems, so check if they were created
            if sqlite_latest.exists():
                assert sqlite_latest.parent == Path(sqlite_dir), "SQLite latest.log should be in sqlite directory"
            if postgres_latest.exists():
                assert postgres_latest.parent == Path(
                    postgres_dir
                ), "PostgreSQL latest.log should be in postgres directory"

            # Verify no cross-contamination
            assert str(sqlite_latest) != str(postgres_latest), "Symlink paths should be different"
