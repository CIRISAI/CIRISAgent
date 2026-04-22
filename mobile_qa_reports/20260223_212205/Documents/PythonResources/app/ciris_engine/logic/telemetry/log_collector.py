"""
Log Correlation Collector

Captures application logs and stores them as correlations in the TSDB,
enabling time-series queries and agent introspection of log data.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

from ciris_engine.logic.persistence.models.correlations import add_correlation
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.telemetry.core import CorrelationType, ServiceCorrelation, ServiceCorrelationStatus


class TSDBLogHandler(logging.Handler):
    """Logging handler that stores logs as TSDB correlations."""

    def __init__(self, tags: Optional[Dict[str, str]] = None, time_service: Optional[TimeServiceProtocol] = None):
        super().__init__()
        self.tags = tags or {}
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._time_service = time_service

    def emit(self, record: logging.LogRecord) -> None:
        """Process log record and store as correlation."""
        try:
            from ciris_engine.schemas.telemetry.core import LogData

            # Create LogData for the log entry
            log_data = LogData(
                log_level=record.levelname,
                log_message=self.format(record),
                logger_name=record.name,
                module_name=record.module or "unknown",
                function_name=record.funcName or "unknown",
                line_number=record.lineno,
                extra_fields={
                    "pathname": record.pathname,
                    "thread": str(record.thread),
                    "process": str(record.process),
                },
            )

            # Create the correlation with log data
            timestamp = datetime.fromtimestamp(record.created, timezone.utc)
            log_correlation = ServiceCorrelation(
                correlation_id=str(uuid4()),
                service_type="logging",
                handler_name="log_collector",
                action_type="log_entry",
                correlation_type=CorrelationType.LOG_ENTRY,
                timestamp=timestamp,
                created_at=timestamp,
                updated_at=timestamp,
                log_data=log_data,
                tags={
                    **self.tags,
                    "logger": record.name,
                    "level": record.levelname,
                    "module": record.module or "unknown",
                },
                status=ServiceCorrelationStatus.COMPLETED,
                retention_policy="raw",
            )

            if self._async_loop and self._async_loop.is_running():
                self._async_loop.create_task(self._store_log_correlation(log_correlation))
            else:
                if self._time_service:
                    add_correlation(log_correlation, self._time_service)
                else:
                    # Skip if no time service available
                    print("Warning: TSDBLogHandler requires time_service to store correlations")

        except Exception as e:
            print(f"Failed to store log correlation: {e}")

    async def _store_log_correlation(self, correlation: ServiceCorrelation) -> None:
        """Store log correlation asynchronously."""
        try:
            if self._time_service:
                add_correlation(correlation, self._time_service)
            else:
                print("Warning: TSDBLogHandler requires time_service to store correlations")
        except Exception as e:
            print(f"Failed to store log correlation in TSDB: {e}")

    def set_async_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Set the async event loop for asynchronous storage."""
        self._async_loop = loop


class LogCorrelationCollector:
    """
    Service that configures logging to store logs in TSDB.

    This collector sets up logging handlers that capture log entries
    and store them as correlations, enabling time-series queries.
    """

    def __init__(
        self,
        log_levels: Optional[List[str]] = None,
        tags: Optional[Dict[str, str]] = None,
        loggers: Optional[List[str]] = None,
    ):
        """
        Initialize the log collector.

        Args:
            log_levels: Log levels to capture (default: WARNING and above)
            tags: Global tags to add to all log correlations
            loggers: Specific logger names to attach to (default: root logger)
        """
        self.log_levels = log_levels or ["WARNING", "ERROR", "CRITICAL"]
        self.tags = tags or {"source": "ciris_agent"}
        self.loggers: List[Optional[str]] = list(loggers) if loggers is not None else [None]  # None means root logger
        self.handlers: List[TSDBLogHandler] = []

    async def start(self) -> None:
        """Start collecting logs."""
        # Get current event loop
        loop = asyncio.get_event_loop()

        # Create handlers for each logger
        for logger_name in self.loggers:
            handler = TSDBLogHandler(tags=self.tags)
            handler.set_async_loop(loop)

            # Set formatter
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)

            # Set level based on configured levels
            min_level = min(getattr(logging, level) for level in self.log_levels)
            handler.setLevel(min_level)

            # Add handler to logger
            if logger_name is None:
                logger = logging.getLogger()
            else:
                logger = logging.getLogger(logger_name)

            logger.addHandler(handler)
            self.handlers.append(handler)

        logging.info("Log correlation collector started")

    async def stop(self) -> None:
        """Stop collecting logs."""
        for i, handler in enumerate(self.handlers):
            try:
                logger_name = self.loggers[i] if i < len(self.loggers) else None
                if logger_name is None:
                    logger = logging.getLogger()
                else:
                    logger = logging.getLogger(logger_name)

                logger.removeHandler(handler)
                handler.close()
            except Exception as e:
                logging.warning(f"Error removing handler: {e}")

        self.handlers.clear()
        logging.info("Log correlation collector stopped")

    def add_logger(self, logger_name: str) -> None:
        """Add a new logger to collect from."""
        if logger_name not in self.loggers:
            self.loggers.append(logger_name)

            # If already started, add handler now
            if self.handlers:
                loop = asyncio.get_event_loop()
                handler = TSDBLogHandler(tags=self.tags)
                handler.set_async_loop(loop)

                formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
                handler.setFormatter(formatter)

                min_level = min(getattr(logging, level) for level in self.log_levels)
                handler.setLevel(min_level)

                logger = logging.getLogger(logger_name)
                logger.addHandler(handler)
                self.handlers.append(handler)
