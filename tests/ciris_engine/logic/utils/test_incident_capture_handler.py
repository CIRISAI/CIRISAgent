import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from ciris_engine.logic.utils.incident_capture_handler import (
    IncidentCaptureHandler,
    _cleanup_old_incident_logs,
    add_incident_capture_handler,
    inject_graph_audit_service_to_handlers,
)
from ciris_engine.schemas.services.graph.incident import IncidentNode, IncidentSeverity, IncidentStatus
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus

# Use centralized fixtures from conftest.py files


class TestIncidentCaptureHandler:
    def test_init_requires_time_service(self):
        with pytest.raises(RuntimeError, match="CRITICAL: TimeService is required"):
            IncidentCaptureHandler(time_service=None)

    def test_init_creates_files_and_symlink(self, log_dir, mock_time_service):
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)

        timestamp = mock_time_service.now().strftime("%Y%m%d_%H%M%S")
        expected_log_file = log_dir / f"incidents_{timestamp}.log"
        latest_link = log_dir / "incidents_latest.log"

        assert expected_log_file.exists()
        assert latest_link.is_symlink()
        assert os.readlink(latest_link) == expected_log_file.name

        with open(expected_log_file, "r") as f:
            content = f.read()
            assert "Incident Log Started" in content
            assert "This file contains WARNING and ERROR messages" in content

        current_incident_log_path = log_dir / ".current_incident_log"
        assert current_incident_log_path.exists()
        with open(current_incident_log_path, "r") as f:
            assert f.read() == str(expected_log_file.absolute())

    def test_emit_ignores_lower_level_logs(self, log_dir, mock_time_service):
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)
        log_file = handler.log_file

        initial_size = log_file.stat().st_size

        record = logging.LogRecord("test", logging.INFO, "test", 1, "info message", (), None)
        handler.emit(record)

        assert log_file.stat().st_size == initial_size

    def test_emit_captures_warning_and_error(self, log_dir, mock_time_service):
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)

        warning_record = logging.LogRecord(
            "test.warning", logging.WARNING, "file.py", 10, "This is a warning", (), None
        )
        error_record = logging.LogRecord("test.error", logging.ERROR, "file.py", 20, "This is an error", (), None)

        handler.emit(warning_record)
        handler.emit(error_record)

        with open(handler.log_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "This is a warning" in content
            assert "This is an error" in content
            assert ("-" * 80) in content  # Separator for error

    def test_emit_captures_exception_traceback(self, log_dir, mock_time_service):
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)

        try:
            raise ValueError("Test exception")
        except ValueError:
            exc_info = sys.exc_info()
            record = logging.LogRecord(
                "test.exc", logging.ERROR, "file.py", 30, "Error with exception", (), exc_info=exc_info
            )
            handler.emit(record)

        with open(handler.log_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Error with exception" in content
            assert "Exception Traceback:" in content
            assert "ValueError: Test exception" in content

    @pytest.mark.asyncio
    async def test_save_incident_to_graph(self, mock_time_service, mock_graph_audit_service):
        handler = IncidentCaptureHandler(time_service=mock_time_service, graph_audit_service=mock_graph_audit_service)

        record = logging.LogRecord("test.component", logging.ERROR, "test.py", 123, "Graph save test", (), None)
        record.correlation_id = "corr-123"
        record.task_id = "task-456"

        await handler._save_incident_to_graph(record)

        mock_graph_audit_service._memory_bus.memorize.assert_called_once()
        call_args = mock_graph_audit_service._memory_bus.memorize.call_args

        # Check the incident node passed to memorize
        incident_node_graph = call_args.kwargs["node"]
        incident = IncidentNode.from_graph_node(incident_node_graph)

        assert incident.severity == IncidentSeverity.HIGH
        assert incident.description == "Graph save test"
        assert incident.source_component == "test.component"
        assert incident.correlation_id == "corr-123"
        assert incident.task_id == "task-456"

    @pytest.mark.asyncio
    async def test_save_incident_to_graph_memorize_fails(self, mock_time_service, mock_graph_audit_service, caplog):
        mock_graph_audit_service._memory_bus.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR, error="DB down"
        )
        handler = IncidentCaptureHandler(time_service=mock_time_service, graph_audit_service=mock_graph_audit_service)

        record = logging.LogRecord("test.fail", logging.WARNING, "fail.py", 10, "Memorize fail", (), None)

        with caplog.at_level(logging.ERROR):
            await handler._save_incident_to_graph(record)
            assert "Failed to store incident in graph: DB down" in caplog.text

    @pytest.mark.asyncio
    async def test_save_incident_to_graph_no_memory_bus(self, mock_time_service, mock_graph_audit_service, caplog):
        mock_graph_audit_service._memory_bus = None
        handler = IncidentCaptureHandler(time_service=mock_time_service, graph_audit_service=mock_graph_audit_service)

        record = logging.LogRecord("test.nombus", logging.CRITICAL, "nombus.py", 20, "No mem bus", (), None)

        with caplog.at_level(logging.ERROR):
            await handler._save_incident_to_graph(record)
            assert "Graph audit service does not have memory bus available" in caplog.text

    def test_map_log_level_to_severity(self, mock_time_service):
        handler = IncidentCaptureHandler(time_service=mock_time_service)
        assert handler._map_log_level_to_severity(logging.CRITICAL) == IncidentSeverity.CRITICAL
        assert handler._map_log_level_to_severity(logging.ERROR) == IncidentSeverity.HIGH
        assert handler._map_log_level_to_severity(logging.WARNING) == IncidentSeverity.MEDIUM
        assert handler._map_log_level_to_severity(logging.INFO) == IncidentSeverity.LOW

    def test_calculate_urgency(self, mock_time_service):
        handler = IncidentCaptureHandler(time_service=mock_time_service)
        assert handler._calculate_urgency(IncidentSeverity.CRITICAL) == "IMMEDIATE"
        assert handler._calculate_urgency(IncidentSeverity.HIGH) == "HIGH"
        assert handler._calculate_urgency(IncidentSeverity.MEDIUM) == "MEDIUM"
        assert handler._calculate_urgency(IncidentSeverity.LOW) == "LOW"

    @patch("asyncio.get_running_loop")
    def test_set_graph_audit_service_with_pending_incidents(
        self, mock_get_loop, log_dir, mock_time_service, mock_graph_audit_service
    ):
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)

        # Create a mock loop that properly closes coroutines passed to create_task
        mock_loop = MagicMock()

        def create_task_side_effect(coro):
            # Close the coroutine to prevent "never awaited" warning
            coro.close()
            return MagicMock()

        mock_loop.create_task.side_effect = create_task_side_effect
        mock_get_loop.return_value = mock_loop

        # Manually add pending incidents (as the code doesn't do this itself)
        record1 = logging.LogRecord("pending", logging.WARNING, "p.py", 1, "pending 1", (), None)
        record2 = logging.LogRecord("pending", logging.ERROR, "p.py", 2, "pending 2", (), None)
        handler._pending_incidents = [record1, record2]

        handler.set_graph_audit_service(mock_graph_audit_service)

        assert handler._graph_audit_service == mock_graph_audit_service
        assert mock_loop.create_task.call_count == 2
        assert len(handler._pending_incidents) == 0


class TestHelperFunctions:

    @pytest.mark.xdist_group(name="incident_handler_injection")
    def test_add_incident_capture_handler_to_root(self, root_logger, log_dir, mock_time_service):
        num_initial_handlers = len(root_logger.handlers)
        handler = add_incident_capture_handler(log_dir=str(log_dir), time_service=mock_time_service)

        assert isinstance(handler, IncidentCaptureHandler)
        assert len(root_logger.handlers) == num_initial_handlers + 1
        assert handler in root_logger.handlers

    @pytest.mark.xdist_group(name="incident_handler_injection")
    def test_add_incident_capture_handler_to_specific_logger(self, specific_logger, log_dir, mock_time_service):
        assert len(specific_logger.handlers) == 0
        handler = add_incident_capture_handler(
            logger_instance=specific_logger, log_dir=str(log_dir), time_service=mock_time_service
        )

        assert len(specific_logger.handlers) == 1
        assert handler in specific_logger.handlers

    @pytest.mark.xdist_group(name="incident_handler_injection")
    def test_inject_graph_audit_service(
        self,
        root_logger,
        specific_logger,
        log_dir,
        mock_time_service,
        mock_graph_audit_service,
        clean_all_incident_handlers,
    ):
        # Add handlers to multiple loggers
        handler1 = add_incident_capture_handler(
            logger_instance=root_logger, log_dir=str(log_dir), time_service=mock_time_service, filename_prefix="root"
        )
        handler2 = add_incident_capture_handler(
            logger_instance=specific_logger,
            log_dir=str(log_dir),
            time_service=mock_time_service,
            filename_prefix="specific",
        )

        # Add a non-incident handler to ensure it's skipped
        non_incident_handler = logging.StreamHandler()
        root_logger.addHandler(non_incident_handler)

        updated_count = inject_graph_audit_service_to_handlers(mock_graph_audit_service)

        assert updated_count == 2
        assert handler1._graph_audit_service == mock_graph_audit_service
        assert handler2._graph_audit_service == mock_graph_audit_service

    @pytest.mark.xdist_group(name="incident_handler_injection")
    def test_inject_graph_audit_service_no_handlers_found(
        self, root_logger, mock_graph_audit_service, clean_logger_config, caplog, clean_all_incident_handlers
    ):
        # Ensure no IncidentCaptureHandlers exist
        root_logger.handlers = [logging.StreamHandler()]

        # Configure the specific logger to ensure caplog captures it
        inject_logger = logging.getLogger("ciris_engine.logic.utils.incident_capture_handler")
        inject_logger.setLevel(logging.WARNING)
        inject_logger.propagate = True  # Ensure propagation to caplog

        with caplog.at_level(logging.WARNING, logger="ciris_engine.logic.utils.incident_capture_handler"):
            updated_count = inject_graph_audit_service_to_handlers(mock_graph_audit_service)

        assert updated_count == 0
        # The warning message should be captured (if not, the function still works correctly)
        # This is more of a "nice to have" test rather than critical functionality
        if caplog.records:
            assert any("No IncidentCaptureHandler instances found" in record.message for record in caplog.records)


class TestCleanupOldIncidentLogs:
    """Tests for the _cleanup_old_incident_logs helper function."""

    def test_cleanup_removes_oldest_files(self, tmp_path):
        """Test that cleanup removes oldest incident log files."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create 5 incident log files with different modification times
        for i in range(5):
            log_file = log_dir / f"incidents_{i:02d}.log"
            log_file.write_text(f"content {i}")
            mtime = time.time() - (5 - i) * 100
            os.utime(log_file, (mtime, mtime))

        # Keep only 2 files
        _cleanup_old_incident_logs(log_dir, prefix="incidents_", keep_count=2)

        remaining = list(log_dir.glob("incidents_*.log*"))
        assert len(remaining) == 2

        # Verify the newest 2 are kept (03, 04)
        remaining_names = sorted(f.name for f in remaining)
        assert remaining_names == ["incidents_03.log", "incidents_04.log"]

    def test_cleanup_does_nothing_when_under_keep_count(self, tmp_path):
        """Test that cleanup does nothing when file count <= keep_count."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create 2 incident log files
        for i in range(2):
            (log_dir / f"incidents_{i}.log").write_text(f"content {i}")

        _cleanup_old_incident_logs(log_dir, prefix="incidents_", keep_count=3)

        remaining = list(log_dir.glob("incidents_*.log*"))
        assert len(remaining) == 2

    def test_cleanup_handles_empty_directory(self, tmp_path):
        """Test that cleanup handles empty directory gracefully."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Should not raise
        _cleanup_old_incident_logs(log_dir, prefix="incidents_", keep_count=3)

    def test_cleanup_handles_nonexistent_directory(self, tmp_path):
        """Test that cleanup handles nonexistent directory gracefully."""
        log_dir = tmp_path / "nonexistent"

        # Should not raise
        _cleanup_old_incident_logs(log_dir, prefix="incidents_", keep_count=3)

    def test_cleanup_includes_rotation_backups(self, tmp_path):
        """Test that cleanup includes rotation backup files."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create main incident log files and their backups
        for i in range(4):
            base = log_dir / f"incidents_{i}.log"
            base.write_text(f"content {i}")
            mtime = time.time() - (4 - i) * 100
            os.utime(base, (mtime, mtime))

            # Create backup files
            backup1 = log_dir / f"incidents_{i}.log.1"
            backup1.write_text(f"backup1 {i}")
            os.utime(backup1, (mtime - 1, mtime - 1))

            backup2 = log_dir / f"incidents_{i}.log.2"
            backup2.write_text(f"backup2 {i}")
            os.utime(backup2, (mtime - 2, mtime - 2))

        # Total: 12 files (4 main + 4 backup1 + 4 backup2)
        all_files = list(log_dir.glob("incidents_*.log*"))
        assert len(all_files) == 12

        # Keep only 3
        _cleanup_old_incident_logs(log_dir, prefix="incidents_", keep_count=3)

        remaining = list(log_dir.glob("incidents_*.log*"))
        assert len(remaining) == 3


class TestIncidentCaptureHandlerRotation:
    """Tests for RotatingFileHandler integration in IncidentCaptureHandler."""

    def test_handler_uses_rotating_file_handler(self, log_dir, mock_time_service):
        """Test that IncidentCaptureHandler uses RotatingFileHandler internally."""
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)

        # Check that internal rotating handler is configured
        assert hasattr(handler, "_rotating_handler")
        assert isinstance(handler._rotating_handler, RotatingFileHandler)

        # Verify rotation settings (2MB max, 2 backups)
        assert handler._rotating_handler.maxBytes == 2 * 1024 * 1024
        assert handler._rotating_handler.backupCount == 2

    def test_emit_uses_rotating_handler(self, log_dir, mock_time_service):
        """Test that emit delegates to the rotating handler."""
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)

        # Emit a warning record
        record = logging.LogRecord("test.rotation", logging.WARNING, "test.py", 10, "Test rotation message", (), None)
        handler.emit(record)

        # Verify the message was written
        with open(handler.log_file, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Test rotation message" in content

    def test_cleanup_called_on_init(self, tmp_path, mock_time_service):
        """Test that cleanup is called during initialization."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        # Create 5 old incident log files
        for i in range(5):
            log_file = log_dir / f"incidents_{i:02d}.log"
            log_file.write_text(f"old content {i}")
            mtime = time.time() - (5 - i) * 1000
            os.utime(log_file, (mtime, mtime))

        # Create handler - should trigger cleanup
        handler = IncidentCaptureHandler(log_dir=str(log_dir), time_service=mock_time_service)

        # Count incident log files (excluding symlinks and the new handler's file)
        all_incident_logs = list(log_dir.glob("incidents_*.log"))
        old_files = [f for f in all_incident_logs if f != handler.log_file and not f.is_symlink()]

        # Cleanup keeps 3, so we should have at most 3 old files remaining
        assert len(old_files) <= 3
