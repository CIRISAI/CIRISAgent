import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.utils.logging_config import _cleanup_old_logs, setup_basic_logging


# Mock Time Service
class MockTimeService:
    def __init__(self, now_time=None):
        from datetime import datetime

        self._now = now_time or datetime(2025, 9, 7, 18, 0, 0)

    def now(self):
        return self._now

    def strftime(self, format_str):
        return self._now.strftime(format_str)


@pytest.fixture
def mock_time_service():
    """Provides a mock time service instance."""
    return MockTimeService()


@pytest.fixture
def clean_logger():
    """Fixture to get a clean logger and reset it after the test."""
    logger = logging.getLogger("test_logger")
    # Backup original state
    original_handlers = logger.handlers[:]
    original_level = logger.level
    original_propagate = logger.propagate

    # Provide a clean logger for the test
    logger.handlers = []
    logger.setLevel(logging.NOTSET)
    logger.propagate = True

    yield logger

    # Restore original state
    logger.handlers = original_handlers
    logger.setLevel(original_level)
    logger.propagate = original_propagate


# Corrected patch paths to target where the objects are defined, not where they are used.
@patch("ciris_engine.logic.utils.incident_capture_handler.add_incident_capture_handler")
@patch("ciris_engine.logic.config.env_utils.get_env_var", return_value=None)
class TestSetupBasicLogging:

    def test_console_logging_only(self, mock_get_env, mock_add_incident, clean_logger):
        setup_basic_logging(
            logger_instance=clean_logger, log_to_file=False, console_output=True, enable_incident_capture=False
        )
        assert len(clean_logger.handlers) == 1
        assert isinstance(clean_logger.handlers[0], logging.StreamHandler)
        assert clean_logger.level == logging.INFO  # Default level
        mock_add_incident.assert_not_called()

    def test_file_logging_requires_time_service(self, mock_get_env, mock_add_incident):
        with pytest.raises(RuntimeError, match="CRITICAL: TimeService is required"):
            setup_basic_logging(log_to_file=True, time_service=None)

    def test_file_logging_creates_files(
        self, mock_get_env, mock_add_incident, clean_logger, mock_time_service, tmp_path
    ):
        log_dir = tmp_path / "test_logs"
        setup_basic_logging(
            logger_instance=clean_logger,
            log_to_file=True,
            console_output=False,
            log_dir=str(log_dir),
            time_service=mock_time_service,
            enable_incident_capture=False,
        )

        assert len(clean_logger.handlers) == 1
        assert isinstance(clean_logger.handlers[0], logging.FileHandler)

        timestamp = mock_time_service.now().strftime("%Y%m%d_%H%M%S")
        expected_log_file = log_dir / f"ciris_agent_{timestamp}.log"
        latest_link = log_dir / "latest.log"

        assert log_dir.exists()
        assert expected_log_file.exists()
        assert latest_link.is_symlink()
        assert os.readlink(latest_link) == expected_log_file.name

    def test_env_var_overrides_level(self, mock_get_env, mock_add_incident, clean_logger):
        mock_get_env.return_value = "DEBUG"
        setup_basic_logging(
            logger_instance=clean_logger, level=logging.INFO, log_to_file=False, enable_incident_capture=False
        )
        assert clean_logger.level == logging.DEBUG

    def test_prefix_is_added_to_formatter(self, mock_get_env, mock_add_incident, clean_logger):
        setup_basic_logging(
            logger_instance=clean_logger,
            prefix="[TEST_PREFIX]",
            log_to_file=False,
            console_output=True,
            enable_incident_capture=False,
        )
        formatter = clean_logger.handlers[0].formatter
        assert formatter._fmt.startswith("[TEST_PREFIX]")

    def test_incident_capture_enabled(self, mock_get_env, mock_add_incident, clean_logger, mock_time_service, tmp_path):
        log_dir = str(tmp_path / "logs")
        setup_basic_logging(
            logger_instance=clean_logger, log_dir=log_dir, time_service=mock_time_service, enable_incident_capture=True
        )
        mock_add_incident.assert_called_once_with(
            clean_logger, log_dir=log_dir, time_service=mock_time_service, graph_audit_service=None
        )

    def test_sets_library_log_levels(self, mock_get_env, mock_add_incident):
        setup_basic_logging(log_to_file=False, enable_incident_capture=False)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("discord").level == logging.WARNING
        assert logging.getLogger("openai").level == logging.WARNING

    def test_prints_banner_for_file_only_logging(
        self, mock_get_env, mock_add_incident, mock_time_service, tmp_path, capsys
    ):
        log_dir = str(tmp_path / "logs")
        setup_basic_logging(
            log_to_file=True,
            console_output=False,
            log_dir=log_dir,
            time_service=mock_time_service,
            enable_incident_capture=True,
        )

        captured = capsys.readouterr()
        assert "LOGGING INITIALIZED" in captured.out
        assert "SEE DETAILED LOGS AT" in captured.out
        assert "Incident capture" in captured.out

    def test_logger_propagate_is_false(self, mock_get_env, mock_add_incident, clean_logger):
        setup_basic_logging(logger_instance=clean_logger, log_to_file=False)
        assert not clean_logger.propagate

    def test_file_logging_uses_rotating_handler(
        self, mock_get_env, mock_add_incident, clean_logger, mock_time_service, tmp_path
    ):
        """Test that file logging uses RotatingFileHandler instead of FileHandler."""
        log_dir = tmp_path / "test_logs"
        setup_basic_logging(
            logger_instance=clean_logger,
            log_to_file=True,
            console_output=False,
            log_dir=str(log_dir),
            time_service=mock_time_service,
            enable_incident_capture=False,
        )

        assert len(clean_logger.handlers) == 1
        assert isinstance(clean_logger.handlers[0], RotatingFileHandler)

        # Verify rotation settings (5MB max, 3 backups)
        handler = clean_logger.handlers[0]
        assert handler.maxBytes == 5 * 1024 * 1024
        assert handler.backupCount == 3


class TestCleanupOldLogs:
    """Tests for the _cleanup_old_logs helper function."""

    def test_cleanup_removes_oldest_files(self, tmp_path):
        """Test that cleanup removes oldest files when over keep_count."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create 7 log files with different modification times
        import time

        for i in range(7):
            log_file = log_dir / f"ciris_agent_{i:02d}.log"
            log_file.write_text(f"content {i}")
            # Set modification time to space them out
            mtime = time.time() - (7 - i) * 100
            os.utime(log_file, (mtime, mtime))

        # Keep only 3 files
        _cleanup_old_logs(log_dir, prefix="ciris_agent_", keep_count=3)

        remaining = list(log_dir.glob("ciris_agent_*.log"))
        assert len(remaining) == 3

        # Verify the newest 3 are kept (04, 05, 06)
        remaining_names = sorted(f.name for f in remaining)
        assert remaining_names == ["ciris_agent_04.log", "ciris_agent_05.log", "ciris_agent_06.log"]

    def test_cleanup_does_nothing_when_under_keep_count(self, tmp_path):
        """Test that cleanup does nothing when file count <= keep_count."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create 3 log files
        for i in range(3):
            (log_dir / f"ciris_agent_{i}.log").write_text(f"content {i}")

        _cleanup_old_logs(log_dir, prefix="ciris_agent_", keep_count=5)

        remaining = list(log_dir.glob("ciris_agent_*.log"))
        assert len(remaining) == 3

    def test_cleanup_handles_empty_directory(self, tmp_path):
        """Test that cleanup handles empty directory gracefully."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Should not raise
        _cleanup_old_logs(log_dir, prefix="ciris_agent_", keep_count=5)

    def test_cleanup_handles_nonexistent_directory(self, tmp_path):
        """Test that cleanup handles nonexistent directory gracefully."""
        log_dir = tmp_path / "nonexistent"

        # Should not raise
        _cleanup_old_logs(log_dir, prefix="ciris_agent_", keep_count=5)

    def test_cleanup_only_matches_prefix(self, tmp_path):
        """Test that cleanup only removes files matching the prefix."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        import time

        # Create matching files
        for i in range(5):
            log_file = log_dir / f"ciris_agent_{i}.log"
            log_file.write_text(f"content {i}")
            mtime = time.time() - (5 - i) * 100
            os.utime(log_file, (mtime, mtime))

        # Create non-matching files
        (log_dir / "other_file.log").write_text("other")
        (log_dir / "incidents_0.log").write_text("incident")

        _cleanup_old_logs(log_dir, prefix="ciris_agent_", keep_count=2)

        # Only 2 ciris_agent files should remain
        ciris_files = list(log_dir.glob("ciris_agent_*.log"))
        assert len(ciris_files) == 2

        # Other files should be untouched
        assert (log_dir / "other_file.log").exists()
        assert (log_dir / "incidents_0.log").exists()

    def test_cleanup_includes_rotation_backups(self, tmp_path):
        """Test that cleanup includes rotation backup files (.log.1, .log.2)."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        import time

        # Create main log files and their backups
        for i in range(3):
            base = log_dir / f"ciris_agent_{i}.log"
            base.write_text(f"content {i}")
            mtime = time.time() - (3 - i) * 100
            os.utime(base, (mtime, mtime))

            # Create backup files
            backup1 = log_dir / f"ciris_agent_{i}.log.1"
            backup1.write_text(f"backup1 {i}")
            os.utime(backup1, (mtime - 1, mtime - 1))

        # Total: 6 files (3 main + 3 backups)
        all_files = list(log_dir.glob("ciris_agent_*.log*"))
        assert len(all_files) == 6

        # Keep only 2
        _cleanup_old_logs(log_dir, prefix="ciris_agent_", keep_count=2)

        remaining = list(log_dir.glob("ciris_agent_*.log*"))
        assert len(remaining) == 2
