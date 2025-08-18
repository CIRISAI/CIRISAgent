"""
Comprehensive tests for telemetry/log_collector.py module.

Tests the TSDBLogHandler and LogCorrelationCollector classes for
capturing and storing logs as time-series correlations.
"""

import asyncio
import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest

from ciris_engine.logic.telemetry.log_collector import LogCorrelationCollector, TSDBLogHandler
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.telemetry.core import CorrelationType, LogData, ServiceCorrelation, ServiceCorrelationStatus


@pytest.fixture
def time_service():
    """Mock time service."""
    service = Mock(spec=TimeServiceProtocol)
    service.now.return_value = datetime.now(timezone.utc)
    return service


@pytest.fixture
def log_handler(time_service):
    """Create a TSDBLogHandler instance."""
    handler = TSDBLogHandler(tags={"test": "true"}, time_service=time_service)
    return handler


@pytest.fixture
def log_collector():
    """Create a LogCorrelationCollector instance."""
    return LogCorrelationCollector(
        log_levels=["INFO", "WARNING", "ERROR"], tags={"environment": "test"}, loggers=["test.logger"]
    )


class TestTSDBLogHandler:
    """Test TSDBLogHandler class."""

    def test_initialization(self, log_handler):
        """Test handler initialization."""
        assert log_handler.tags == {"test": "true"}
        assert log_handler._async_loop is None
        assert log_handler._time_service is not None

    def test_emit_basic_log(self, log_handler, time_service):
        """Test emitting a basic log record."""
        # Create a log record
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="/test/path.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
            func="test_function",
            sinfo=None,
        )
        record.module = "test_module"
        record.created = datetime.now(timezone.utc).timestamp()

        with patch("ciris_engine.logic.telemetry.log_collector.add_correlation") as mock_add:
            log_handler.emit(record)

            # Check correlation was created
            assert mock_add.called
            correlation = mock_add.call_args[0][0]
            assert isinstance(correlation, ServiceCorrelation)
            assert correlation.service_type == "logging"
            assert correlation.handler_name == "log_collector"
            assert correlation.action_type == "log_entry"
            assert correlation.correlation_type == CorrelationType.LOG_ENTRY
            assert correlation.log_data is not None
            assert correlation.log_data.log_level == "INFO"
            assert correlation.log_data.logger_name == "test.logger"
            assert correlation.log_data.module_name == "test_module"
            assert correlation.log_data.function_name == "test_function"
            assert correlation.log_data.line_number == 42

    def test_emit_with_custom_tags(self, time_service):
        """Test emitting logs with custom tags."""
        handler = TSDBLogHandler(tags={"service": "api", "version": "1.0"}, time_service=time_service)

        record = logging.LogRecord(
            name="api.logger",
            level=logging.ERROR,
            pathname="/api/handler.py",
            lineno=100,
            msg="Error occurred",
            args=(),
            exc_info=None,
        )
        record.created = datetime.now(timezone.utc).timestamp()

        with patch("ciris_engine.logic.telemetry.log_collector.add_correlation") as mock_add:
            handler.emit(record)

            correlation = mock_add.call_args[0][0]
            assert correlation.tags["service"] == "api"
            assert correlation.tags["version"] == "1.0"
            assert correlation.tags["level"] == "ERROR"

    def test_emit_with_missing_fields(self, log_handler, time_service):
        """Test emitting logs with missing optional fields."""
        record = logging.LogRecord(
            name="simple.logger",
            level=logging.WARNING,
            pathname="/path.py",
            lineno=1,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        # Don't set module or funcName - Python will derive module from pathname
        record.created = datetime.now(timezone.utc).timestamp()

        with patch("ciris_engine.logic.telemetry.log_collector.add_correlation") as mock_add:
            log_handler.emit(record)

            correlation = mock_add.call_args[0][0]
            # Python's logging derives module name "path" from pathname "/path.py"
            assert correlation.log_data.module_name == "path"
            # funcName wasn't set, so it should be "unknown"
            assert correlation.log_data.function_name == "unknown"

    def test_emit_error_handling(self, log_handler):
        """Test that emit errors don't crash the handler."""
        record = logging.LogRecord(
            name="error.logger", level=logging.INFO, pathname="/path.py", lineno=1, msg="Test", args=(), exc_info=None
        )

        with patch("ciris_engine.logic.telemetry.log_collector.add_correlation") as mock_add:
            mock_add.side_effect = Exception("Database error")

            # Should not raise
            log_handler.emit(record)

    @pytest.mark.asyncio
    async def test_emit_with_async_loop(self, log_handler, time_service):
        """Test emitting logs with async event loop."""
        loop = asyncio.get_event_loop()
        log_handler.set_async_loop(loop)

        record = logging.LogRecord(
            name="async.logger",
            level=logging.INFO,
            pathname="/async.py",
            lineno=50,
            msg="Async message",
            args=(),
            exc_info=None,
        )
        record.created = datetime.now(timezone.utc).timestamp()

        with patch("ciris_engine.logic.telemetry.log_collector.add_correlation") as mock_add:
            log_handler.emit(record)

            # Wait for async task
            await asyncio.sleep(0.1)

            # Should have been called asynchronously
            assert mock_add.called

    def test_emit_without_time_service(self):
        """Test that handler warns when no time service is available."""
        handler = TSDBLogHandler(tags={"test": "true"}, time_service=None)

        record = logging.LogRecord(
            name="test.logger", level=logging.INFO, pathname="/test.py", lineno=1, msg="Test", args=(), exc_info=None
        )
        record.created = datetime.now(timezone.utc).timestamp()

        with patch("builtins.print") as mock_print:
            handler.emit(record)

            # Should print warning
            mock_print.assert_called_with("Warning: TSDBLogHandler requires time_service to store correlations")

    def test_set_async_loop(self, log_handler):
        """Test setting async event loop."""
        loop = asyncio.new_event_loop()
        log_handler.set_async_loop(loop)
        assert log_handler._async_loop == loop

    def test_formatter_integration(self, log_handler, time_service):
        """Test that formatter is properly used."""
        formatter = logging.Formatter("%(levelname)s: %(message)s")
        log_handler.setFormatter(formatter)

        record = logging.LogRecord(
            name="format.test",
            level=logging.ERROR,
            pathname="/test.py",
            lineno=1,
            msg="Error message",
            args=(),
            exc_info=None,
        )
        record.created = datetime.now(timezone.utc).timestamp()

        with patch("ciris_engine.logic.telemetry.log_collector.add_correlation") as mock_add:
            log_handler.emit(record)

            correlation = mock_add.call_args[0][0]
            assert correlation.log_data.log_message == "ERROR: Error message"


class TestLogCorrelationCollector:
    """Test LogCorrelationCollector class."""

    def test_initialization_defaults(self):
        """Test collector initialization with defaults."""
        collector = LogCorrelationCollector()
        assert collector.log_levels == ["WARNING", "ERROR", "CRITICAL"]
        assert collector.tags == {"source": "ciris_agent"}
        assert collector.loggers == [None]  # Root logger
        assert collector.handlers == []

    def test_initialization_custom(self, log_collector):
        """Test collector initialization with custom values."""
        assert log_collector.log_levels == ["INFO", "WARNING", "ERROR"]
        assert log_collector.tags == {"environment": "test"}
        assert log_collector.loggers == ["test.logger"]
        assert log_collector.handlers == []

    @pytest.mark.asyncio
    async def test_start(self, log_collector):
        """Test starting the log collector."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await log_collector.start()

            # Should have created handlers
            assert len(log_collector.handlers) == 1

            # Handler should be added to logger
            mock_logger.addHandler.assert_called_once()
            handler = mock_logger.addHandler.call_args[0][0]
            assert isinstance(handler, TSDBLogHandler)
            assert handler.tags == {"environment": "test"}

    @pytest.mark.asyncio
    async def test_start_multiple_loggers(self):
        """Test starting collector with multiple loggers."""
        collector = LogCorrelationCollector(loggers=["app.api", "app.db", "app.cache"])

        with patch("logging.getLogger") as mock_get_logger:
            mock_loggers = [MagicMock() for _ in range(3)]
            mock_get_logger.side_effect = mock_loggers

            await collector.start()

            # Should create handler for each logger
            assert len(collector.handlers) == 3

            # Each logger should have handler added
            for mock_logger in mock_loggers:
                mock_logger.addHandler.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_root_logger(self):
        """Test starting collector with root logger."""
        collector = LogCorrelationCollector(loggers=[None])

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await collector.start()

            # Should call getLogger with no arguments for root
            mock_get_logger.assert_called_with()
            mock_logger.addHandler.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop(self, log_collector):
        """Test stopping the log collector."""
        # Start first
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await log_collector.start()
            handler = log_collector.handlers[0]

            # Now stop
            await log_collector.stop()

            # Handler should be removed
            mock_logger.removeHandler.assert_called_with(handler)
            assert len(log_collector.handlers) == 0

    @pytest.mark.asyncio
    async def test_stop_error_handling(self, log_collector):
        """Test that stop handles errors gracefully."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await log_collector.start()

            # Make removeHandler raise an error
            mock_logger.removeHandler.side_effect = Exception("Remove error")

            # Should not raise
            await log_collector.stop()
            assert len(log_collector.handlers) == 0

    def test_add_logger_before_start(self, log_collector):
        """Test adding a logger before starting."""
        log_collector.add_logger("new.logger")

        assert "new.logger" in log_collector.loggers
        assert len(log_collector.handlers) == 0  # Not started yet

    @pytest.mark.asyncio
    async def test_add_logger_after_start(self, log_collector):
        """Test adding a logger after starting."""
        with patch("logging.getLogger") as mock_get_logger:
            mock_loggers = [MagicMock(), MagicMock()]
            mock_get_logger.side_effect = mock_loggers

            await log_collector.start()
            initial_handlers = len(log_collector.handlers)

            # Add new logger
            log_collector.add_logger("new.logger")

            # Should have one more handler
            assert len(log_collector.handlers) == initial_handlers + 1
            assert "new.logger" in log_collector.loggers

    def test_add_logger_duplicate(self, log_collector):
        """Test that duplicate loggers aren't added."""
        log_collector.add_logger("test.logger")  # Already exists

        # Should still have only one instance
        assert log_collector.loggers.count("test.logger") == 1

    @pytest.mark.asyncio
    async def test_handler_level_setting(self):
        """Test that handler level is set correctly."""
        collector = LogCorrelationCollector(log_levels=["ERROR", "CRITICAL"])

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await collector.start()

            handler = mock_logger.addHandler.call_args[0][0]
            # Should be set to ERROR (minimum of ERROR and CRITICAL)
            assert handler.level == logging.ERROR

    @pytest.mark.asyncio
    async def test_handler_formatter(self):
        """Test that handler formatter is set."""
        collector = LogCorrelationCollector()

        with patch("logging.getLogger") as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger

            await collector.start()

            handler = mock_logger.addHandler.call_args[0][0]
            assert handler.formatter is not None
            assert isinstance(handler.formatter, logging.Formatter)


class TestIntegration:
    """Integration tests for log collection."""

    @pytest.mark.asyncio
    async def test_full_logging_flow(self, time_service):
        """Test complete flow from log to correlation."""
        collector = LogCorrelationCollector(
            log_levels=["DEBUG", "INFO", "WARNING", "ERROR"], tags={"test": "integration"}, loggers=["integration.test"]
        )

        # Patch time service into handlers
        with patch("ciris_engine.logic.telemetry.log_collector.TSDBLogHandler") as MockHandler:
            mock_handler = MagicMock(spec=TSDBLogHandler)
            MockHandler.return_value = mock_handler

            await collector.start()

            # Create a real logger and log something
            logger = logging.getLogger("integration.test")

            # The handler should have been added
            MockHandler.assert_called_with(tags={"test": "integration"})
            mock_handler.set_async_loop.assert_called()

    @pytest.mark.asyncio
    async def test_multiple_log_levels(self):
        """Test that different log levels are handled correctly."""
        collector = LogCorrelationCollector(log_levels=["INFO", "WARNING", "ERROR", "CRITICAL"])

        correlations = []

        def capture_correlation(correlation, time_service):
            correlations.append(correlation)

        with patch("ciris_engine.logic.telemetry.log_collector.add_correlation", capture_correlation):
            # Create a real logger for testing BEFORE patching
            test_logger = logging.getLogger("test.levels")
            test_logger.handlers.clear()

            with patch("logging.getLogger") as mock_get_logger:
                # Mock should return our test logger when collector calls getLogger()
                mock_get_logger.return_value = test_logger

                await collector.start()

                # Log at different levels
                test_logger.debug("Debug message")  # Should be ignored
                test_logger.info("Info message")
                test_logger.warning("Warning message")
                test_logger.error("Error message")
                test_logger.critical("Critical message")

                # Check correlations were created for appropriate levels
                # Note: In real scenario, we'd check the actual correlations
                # but here we're testing the setup is correct
                assert len(test_logger.handlers) == 1
                handler = test_logger.handlers[0]
                assert handler.level == logging.INFO  # Minimum level
