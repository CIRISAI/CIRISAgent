import logging
import os
from unittest.mock import patch, MagicMock

import pytest

from ciris_engine.logic.utils.logging_config import setup_basic_logging

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
@patch('ciris_engine.logic.utils.incident_capture_handler.add_incident_capture_handler')
@patch('ciris_engine.logic.config.env_utils.get_env_var', return_value=None)
class TestSetupBasicLogging:

    def test_console_logging_only(self, mock_get_env, mock_add_incident, clean_logger):
        setup_basic_logging(
            logger_instance=clean_logger,
            log_to_file=False,
            console_output=True,
            enable_incident_capture=False
        )
        assert len(clean_logger.handlers) == 1
        assert isinstance(clean_logger.handlers[0], logging.StreamHandler)
        assert clean_logger.level == logging.INFO # Default level
        mock_add_incident.assert_not_called()

    def test_file_logging_requires_time_service(self, mock_get_env, mock_add_incident):
        with pytest.raises(RuntimeError, match="CRITICAL: TimeService is required"):
            setup_basic_logging(log_to_file=True, time_service=None)

    def test_file_logging_creates_files(self, mock_get_env, mock_add_incident, clean_logger, mock_time_service, tmp_path):
        log_dir = tmp_path / "test_logs"
        setup_basic_logging(
            logger_instance=clean_logger,
            log_to_file=True,
            console_output=False,
            log_dir=str(log_dir),
            time_service=mock_time_service,
            enable_incident_capture=False
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
            logger_instance=clean_logger,
            level=logging.INFO,
            log_to_file=False,
            enable_incident_capture=False
        )
        assert clean_logger.level == logging.DEBUG

    def test_prefix_is_added_to_formatter(self, mock_get_env, mock_add_incident, clean_logger):
        setup_basic_logging(
            logger_instance=clean_logger,
            prefix="[TEST_PREFIX]",
            log_to_file=False,
            console_output=True,
            enable_incident_capture=False
        )
        formatter = clean_logger.handlers[0].formatter
        assert formatter._fmt.startswith("[TEST_PREFIX]")

    def test_incident_capture_enabled(self, mock_get_env, mock_add_incident, clean_logger, mock_time_service, tmp_path):
        log_dir = str(tmp_path / "logs")
        setup_basic_logging(
            logger_instance=clean_logger,
            log_dir=log_dir,
            time_service=mock_time_service,
            enable_incident_capture=True
        )
        mock_add_incident.assert_called_once_with(
            clean_logger,
            log_dir=log_dir,
            time_service=mock_time_service,
            graph_audit_service=None
        )

    def test_sets_library_log_levels(self, mock_get_env, mock_add_incident):
        setup_basic_logging(log_to_file=False, enable_incident_capture=False)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("discord").level == logging.WARNING
        assert logging.getLogger("openai").level == logging.WARNING

    def test_prints_banner_for_file_only_logging(self, mock_get_env, mock_add_incident, mock_time_service, tmp_path, capsys):
        log_dir = str(tmp_path / "logs")
        setup_basic_logging(
            log_to_file=True,
            console_output=False,
            log_dir=log_dir,
            time_service=mock_time_service,
            enable_incident_capture=True
        )

        captured = capsys.readouterr()
        assert "LOGGING INITIALIZED" in captured.out
        assert "SEE DETAILED LOGS AT" in captured.out
        assert "Incident capture" in captured.out

    def test_logger_propagate_is_false(self, mock_get_env, mock_add_incident, clean_logger):
        setup_basic_logging(logger_instance=clean_logger, log_to_file=False)
        assert not clean_logger.propagate
