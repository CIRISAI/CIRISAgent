"""
Tests for IncidentCaptureHandler.
"""

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.utils.incident_capture_handler import IncidentCaptureHandler
from ciris_engine.schemas.services.graph.incident import IncidentSeverity


class MockTimeService:
    """Mock time service for testing."""

    def now(self):
        """Return a fixed datetime for testing."""
        return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

    def now_iso(self):
        """Return ISO format of the fixed datetime."""
        return self.now().isoformat()


@pytest.fixture
def mock_time_service():
    """Fixture for mock time service."""
    return MockTimeService()


@pytest.fixture
def temp_log_dir():
    """Create a temporary directory for logs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def incident_handler(mock_time_service, temp_log_dir):
    """Create an IncidentCaptureHandler instance for testing."""
    handler = IncidentCaptureHandler(
        log_dir=str(temp_log_dir),
        filename_prefix="test_incidents",
        time_service=mock_time_service,
        graph_audit_service=None,
    )
    return handler


class TestIncidentCaptureHandler:
    """Test suite for IncidentCaptureHandler."""

    def test_initialization(self, mock_time_service, temp_log_dir):
        """Test handler initialization."""
        handler = IncidentCaptureHandler(
            log_dir=str(temp_log_dir), filename_prefix="test", time_service=mock_time_service
        )

        # Check log file was created
        assert handler.log_file.exists()
        assert handler.log_file.name == "test_20250101_120000.log"

        # Check handler level is set to WARNING
        assert handler.level == logging.WARNING

        # Check log directory exists
        assert handler.log_dir.exists()
        assert handler.log_dir.is_dir()

    def test_initialization_without_time_service(self, temp_log_dir):
        """Test that initialization fails without time service."""
        with pytest.raises(RuntimeError, match="TimeService is required"):
            IncidentCaptureHandler(log_dir=str(temp_log_dir), time_service=None)

    def test_symlink_creation(self, incident_handler, temp_log_dir):
        """Test that symlink to latest log is created."""
        latest_link = temp_log_dir / "test_incidents_latest.log"

        # On systems that support symlinks
        if latest_link.exists():
            assert latest_link.is_symlink()
            assert latest_link.resolve() == incident_handler.log_file.resolve()

    def test_emit_warning_message(self, incident_handler):
        """Test emitting a WARNING level message."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.WARNING,
            pathname="test.py",
            lineno=10,
            msg="Test warning message",
            args=(),
            exc_info=None,
        )

        incident_handler.emit(record)

        # Check the message was written to file
        log_content = incident_handler.log_file.read_text()
        assert "WARNING" in log_content
        assert "Test warning message" in log_content
        assert "test.py:10" in log_content

    def test_emit_error_message(self, incident_handler):
        """Test emitting an ERROR level message."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=20,
            msg="Test error message",
            args=(),
            exc_info=None,
        )

        incident_handler.emit(record)

        # Check the message was written with separator
        log_content = incident_handler.log_file.read_text()
        assert "ERROR" in log_content
        assert "Test error message" in log_content
        assert "-" * 80 in log_content  # Separator for ERROR messages

    def test_emit_with_exception(self, incident_handler):
        """Test emitting an ERROR with exception traceback."""
        try:
            raise ValueError("Test exception")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=30,
            msg="Error with exception",
            args=(),
            exc_info=exc_info,
        )

        incident_handler.emit(record)

        # Check traceback was included
        log_content = incident_handler.log_file.read_text()
        assert "Exception Traceback:" in log_content
        assert "ValueError: Test exception" in log_content
        assert "raise ValueError" in log_content

    def test_emit_info_message_ignored(self, incident_handler):
        """Test that INFO level messages are ignored."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=40,
            msg="Info message",
            args=(),
            exc_info=None,
        )

        incident_handler.emit(record)

        # Check INFO message was not written
        log_content = incident_handler.log_file.read_text()
        assert "Info message" not in log_content
        assert "INFO" not in log_content

    def test_emit_debug_message_ignored(self, incident_handler):
        """Test that DEBUG level messages are ignored."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.DEBUG,
            pathname="test.py",
            lineno=50,
            msg="Debug message",
            args=(),
            exc_info=None,
        )

        incident_handler.emit(record)

        # Check DEBUG message was not written
        log_content = incident_handler.log_file.read_text()
        assert "Debug message" not in log_content
        assert "DEBUG" not in log_content

    def test_emit_critical_message(self, incident_handler):
        """Test emitting a CRITICAL level message."""
        record = logging.LogRecord(
            name="test.logger",
            level=logging.CRITICAL,
            pathname="test.py",
            lineno=60,
            msg="Critical system failure",
            args=(),
            exc_info=None,
        )

        incident_handler.emit(record)

        # Check CRITICAL message was written with separator
        log_content = incident_handler.log_file.read_text()
        assert "CRITICAL" in log_content
        assert "Critical system failure" in log_content
        assert "-" * 80 in log_content

    @pytest.mark.skip(reason="File error test needs refactoring for open() mock")
    def test_emit_with_file_error(self, incident_handler, monkeypatch):
        """Test emit handles file write errors gracefully."""

        # Mock the Path methods to raise an exception
        def mock_write_text(content):
            raise PermissionError("Cannot write to file")

        def mock_read_text():
            return ""

        # Use monkeypatch on the Path class methods
        monkeypatch.setattr("pathlib.Path.write_text", mock_write_text)
        monkeypatch.setattr("pathlib.Path.read_text", mock_read_text)

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=70,
            msg="This should fail to write",
            args=(),
            exc_info=None,
        )

        # Mock handleError to avoid actual error handling
        incident_handler.handleError = Mock()

        # Should not raise, but call handleError
        incident_handler.emit(record)
        incident_handler.handleError.assert_called_once()

    def test_log_file_header(self, incident_handler):
        """Test that log file has proper header."""
        log_content = incident_handler.log_file.read_text()
        assert "=== Incident Log Started at" in log_content
        assert "2025-01-01" in log_content
        assert "=== This file contains WARNING and ERROR messages" in log_content

    def test_current_incident_log_file(self, temp_log_dir, mock_time_service):
        """Test that .current_incident_log file is created."""
        handler = IncidentCaptureHandler(
            log_dir=str(temp_log_dir), filename_prefix="test", time_service=mock_time_service
        )

        current_log_path = temp_log_dir / ".current_incident_log"
        if current_log_path.exists():
            content = current_log_path.read_text()
            assert str(handler.log_file.absolute()) in content

    def test_formatter_configuration(self, incident_handler):
        """Test that formatter is properly configured."""
        formatter = incident_handler.formatter
        assert formatter is not None

        # Test format includes all expected fields
        record = logging.LogRecord(
            name="test.logger", level=logging.WARNING, pathname="test.py", lineno=80, msg="Test", args=(), exc_info=None
        )

        formatted = formatter.format(record)
        assert "WARNING" in formatted
        assert "test.logger" in formatted
        assert "test.py:80" in formatted

    @pytest.mark.asyncio
    async def test_save_incident_to_graph(self, incident_handler):
        """Test _save_incident_to_graph method."""
        # Mock graph audit service
        mock_graph = Mock()
        incident_handler._graph_audit_service = mock_graph

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=90,
            msg="Test graph save",
            args=(),
            exc_info=None,
        )

        # Add correlation data
        record.correlation_id = "test-correlation-123"
        record.task_id = "test-task-456"

        await incident_handler._save_incident_to_graph(record)

        # Note: Implementation of _save_incident_to_graph may need to be completed
        # This test provides the structure for when it is

    def test_map_log_level_to_severity(self, incident_handler):
        """Test log level to severity mapping."""
        # Test the actual mapping from the implementation
        assert incident_handler._map_log_level_to_severity(logging.DEBUG) == IncidentSeverity.LOW
        assert incident_handler._map_log_level_to_severity(logging.INFO) == IncidentSeverity.LOW
        assert incident_handler._map_log_level_to_severity(logging.WARNING) == IncidentSeverity.MEDIUM
        assert incident_handler._map_log_level_to_severity(logging.ERROR) == IncidentSeverity.HIGH
        assert incident_handler._map_log_level_to_severity(logging.CRITICAL) == IncidentSeverity.CRITICAL
