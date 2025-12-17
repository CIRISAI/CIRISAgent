"""
Incident Capture Handler for capturing WARNING and ERROR level log messages as incidents.

Uses rate limiting and deduplication patterns from ciris_engine.logic.telemetry.security
to prevent graph spam during error cascades.
"""

import asyncio
import hashlib
import logging
import time
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Deque, Optional

from ciris_engine.protocols.services import TimeServiceProtocol

if TYPE_CHECKING:
    from ciris_engine.logic.buses.memory_bus import MemoryBus


class IncidentCaptureHandler(logging.Handler):
    """
    A logging handler that captures WARNING and ERROR level messages as incidents.
    These incidents are stored in the graph for analysis, pattern detection, and self-improvement.

    Anti-spam features (based on patterns from ciris_engine.logic.telemetry.security):
    - Rate limiting: Max incidents per time window to prevent graph flood
    - Deduplication: Same error within window creates single entry with count
    - CRITICAL bypass: Critical errors always go through immediately
    """

    # Default anti-spam settings
    DEFAULT_RATE_LIMIT = 50  # Max incidents per period
    DEFAULT_RATE_PERIOD = 60.0  # Period in seconds
    DEFAULT_DEDUP_WINDOW = 30.0  # Deduplication window in seconds

    def __init__(
        self,
        log_dir: str = "logs",
        filename_prefix: str = "incidents",
        time_service: Optional[TimeServiceProtocol] = None,
        graph_audit_service: Any = None,
        rate_limit: int = DEFAULT_RATE_LIMIT,
        rate_period: float = DEFAULT_RATE_PERIOD,
        dedup_window: float = DEFAULT_DEDUP_WINDOW,
    ) -> None:
        super().__init__()
        if not time_service:
            raise RuntimeError("CRITICAL: TimeService is required for IncidentCaptureHandler")
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)  # parents=True for subdirectories
        self._time_service = time_service

        # Memory bus for graph storage (set later via set_memory_bus)
        self._memory_bus: Optional["MemoryBus"] = None

        # Legacy support for graph_audit_service - extract memory_bus if available
        self._graph_audit_service = graph_audit_service
        if graph_audit_service and hasattr(graph_audit_service, "_memory_bus"):
            self._memory_bus = graph_audit_service._memory_bus

        # Anti-spam: Rate limiting (pattern from SecurityFilter._check_rate_limit)
        self._rate_limit = rate_limit
        self._rate_period = rate_period
        self._rate_history: Deque[float] = deque()

        # Anti-spam: Deduplication cache {hash -> (last_seen, count)}
        self._dedup_window = dedup_window
        self._dedup_cache: dict[str, tuple[float, int]] = {}

        # Pending async tasks for fire-and-forget pattern
        self._pending_tasks: set[asyncio.Task[Any]] = set()

        # Create incident log file with timestamp
        timestamp = self._time_service.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"{filename_prefix}_{timestamp}.log"

        # Create symlink to latest dead letter log
        self.latest_link = self.log_dir / f"{filename_prefix}_latest.log"
        self._create_symlink()

        # Store the actual incident log filename for the telemetry endpoint
        actual_incident_path = self.log_dir / ".current_incident_log"
        try:
            with open(actual_incident_path, "w") as f:
                f.write(str(self.log_file.absolute()))
        except Exception:
            pass

        # Set level to WARNING so we only capture WARNING and above
        self.setLevel(logging.WARNING)

        # Use a detailed format for dead letter messages
        formatter = logging.Formatter(
            "%(asctime)s.%(msecs)03d - %(levelname)-8s - %(name)s - %(filename)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        self.setFormatter(formatter)

        # Write header to the file
        with open(self.log_file, "w") as f:
            f.write(f"=== Incident Log Started at {self._time_service.now_iso()} ===\n")
            f.write("=== This file contains WARNING and ERROR messages captured as incidents ===\n\n")

    def _create_symlink(self) -> None:
        """Create or update the symlink to the latest incident log."""
        try:
            # Check if symlink exists (even if target is invalid)
            if self.latest_link.is_symlink() or self.latest_link.exists():
                self.latest_link.unlink()
            self.latest_link.symlink_to(self.log_file.name)
        except Exception as e:
            # Symlinks might not work on all systems - log warning but don't fail
            logging.warning(f"Failed to create/update incidents_latest.log symlink: {e}")

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a record as an incident to both file and graph.

        Only WARNING, ERROR, and CRITICAL messages are captured as incidents.
        Graph writes use rate limiting and deduplication to prevent spam.
        """
        try:
            # Only process WARNING and above
            if record.levelno < logging.WARNING:
                return

            msg = self.format(record)

            # Add extra context for errors
            if record.levelno >= logging.ERROR and record.exc_info:
                import traceback

                msg += "\nException Traceback:\n"
                msg += "".join(traceback.format_exception(*record.exc_info))

            # Write to file with proper encoding (always, no rate limiting)
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(msg + "\n")

                # Add separator for ERROR and CRITICAL messages
                if record.levelno >= logging.ERROR:
                    f.write("-" * 80 + "\n")

            # Attempt to save to graph with anti-spam protection
            self._queue_graph_write(record)

        except Exception:
            # Failsafe - if we can't capture incident, don't crash
            self.handleError(record)

    def _queue_graph_write(self, record: logging.LogRecord) -> None:
        """
        Queue a graph write with rate limiting and deduplication.

        CRITICAL level bypasses rate limiting but not deduplication.
        """
        # No memory bus available yet - skip graph write
        if not self._memory_bus:
            return

        # Check deduplication first (applies to all levels)
        dedup_key = self._get_dedup_key(record)
        now = time.monotonic()

        if dedup_key in self._dedup_cache:
            last_seen, count = self._dedup_cache[dedup_key]
            if now - last_seen < self._dedup_window:
                # Update count but don't write again
                self._dedup_cache[dedup_key] = (now, count + 1)
                return

        # CRITICAL bypasses rate limiting
        is_critical = record.levelno >= logging.CRITICAL

        # Check rate limit for non-critical
        if not is_critical and not self._check_rate_limit():
            return

        # Update dedup cache
        self._dedup_cache[dedup_key] = (now, 1)

        # Clean old dedup entries periodically
        self._cleanup_dedup_cache(now)

        # Fire-and-forget async write
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._write_to_graph(record))
            self._pending_tasks.add(task)
            task.add_done_callback(lambda t: self._pending_tasks.discard(t))
        except RuntimeError:
            # No event loop running - can't write async
            pass

    def _get_dedup_key(self, record: logging.LogRecord) -> str:
        """Generate a deduplication key for a log record."""
        # Hash based on source, level, and message template (without variable parts)
        key_parts = f"{record.name}:{record.levelno}:{record.msg}"
        return hashlib.md5(key_parts.encode(), usedforsecurity=False).hexdigest()[:16]

    def _check_rate_limit(self) -> bool:
        """
        Check if we're within the rate limit.

        Pattern from ciris_engine.logic.telemetry.security.SecurityFilter._check_rate_limit
        """
        now = time.monotonic()

        # Remove old entries outside the window
        while self._rate_history and now - self._rate_history[0] > self._rate_period:
            self._rate_history.popleft()

        # Check if we're at the limit
        if len(self._rate_history) >= self._rate_limit:
            return False

        # Record this attempt
        self._rate_history.append(now)
        return True

    def _cleanup_dedup_cache(self, now: float) -> None:
        """Remove expired entries from dedup cache."""
        # Only clean every ~100 calls to avoid overhead
        if len(self._dedup_cache) < 100:
            return

        expired_keys = [
            key for key, (last_seen, _) in self._dedup_cache.items() if now - last_seen > self._dedup_window * 2
        ]
        for key in expired_keys:
            del self._dedup_cache[key]

    async def _write_to_graph(self, record: logging.LogRecord) -> None:
        """
        Write incident to graph using MemoryBus.memorize_log().

        This creates a LOG_ENTRY correlation aligned with the CORRELATIONS_TSDB FSD.
        """
        if not self._memory_bus:
            return

        try:
            # Build tags with incident metadata
            tags = {
                "source_component": record.name,
                "filename": record.filename,
                "lineno": str(record.lineno),
                "funcName": record.funcName,
            }

            # Add correlation data if available
            if hasattr(record, "correlation_id") and record.correlation_id:
                tags["correlation_id"] = str(record.correlation_id)
            if hasattr(record, "task_id") and record.task_id:
                tags["task_id"] = str(record.task_id)
            if hasattr(record, "thought_id") and record.thought_id:
                tags["thought_id"] = str(record.thought_id)

            # Use memorize_log which creates LOG_ENTRY correlation
            await self._memory_bus.memorize_log(
                log_message=record.getMessage(),
                log_level=record.levelname,
                tags=tags,
                scope="local",
                handler_name="incident_capture_handler",
            )
        except Exception as e:
            # Never crash the logging system
            logging.getLogger(__name__).debug(f"Failed to write incident to graph: {e}")

    def set_memory_bus(self, memory_bus: "MemoryBus") -> None:
        """
        Set the memory bus for graph storage.

        This is the preferred method for injecting the memory bus.
        Called after service initialization when the MemoryBus is available.
        """
        self._memory_bus = memory_bus
        logging.getLogger(__name__).info("Memory bus injected into incident capture handler")

    def set_graph_audit_service(self, graph_audit_service: Any) -> None:
        """
        Set the graph audit service for storing incidents in the graph.

        This is called after service initialization when the GraphAuditService
        is available. Extracts the memory_bus from the audit service for graph writes.

        Note: Prefer using set_memory_bus() directly when possible.
        """
        self._graph_audit_service = graph_audit_service

        # Extract memory_bus from the audit service
        if hasattr(graph_audit_service, "_memory_bus") and graph_audit_service._memory_bus:
            self._memory_bus = graph_audit_service._memory_bus
            logging.getLogger(__name__).info(
                "Memory bus extracted from graph audit service and injected into incident capture handler"
            )
        else:
            logging.getLogger(__name__).warning(
                "Graph audit service injected but no memory bus available - graph writes disabled"
            )


def add_incident_capture_handler(
    logger_instance: Optional[logging.Logger] = None,
    log_dir: str = "logs",
    filename_prefix: str = "incidents",
    time_service: Optional[TimeServiceProtocol] = None,
    graph_audit_service: Any = None,
) -> IncidentCaptureHandler:
    """
    Add an incident capture handler to the specified logger or root logger.

    Args:
        logger_instance: The logger to add the handler to (None for root logger)
        log_dir: Directory for incident log files
        filename_prefix: Prefix for incident log filenames
        time_service: Time service for timestamps
        graph_audit_service: Audit service for storing incidents in graph

    Returns:
        The created IncidentCaptureHandler instance
    """
    if not time_service:
        raise RuntimeError("CRITICAL: TimeService is required for add_incident_capture_handler")
    handler = IncidentCaptureHandler(
        log_dir=log_dir,
        filename_prefix=filename_prefix,
        time_service=time_service,
        graph_audit_service=graph_audit_service,
    )

    target_logger = logger_instance or logging.getLogger()
    target_logger.addHandler(handler)

    # Log that we've initialized the incident capture
    logger = logging.getLogger(__name__)
    logger.info(f"Incident capture handler initialized: {handler.log_file}")

    return handler


def inject_graph_audit_service_to_handlers(
    graph_audit_service: Any, logger_instance: Optional[logging.Logger] = None
) -> int:
    """
    Inject the graph audit service into all existing IncidentCaptureHandler instances.

    This should be called after the GraphAuditService has been initialized.

    Args:
        graph_audit_service: The initialized GraphAuditService instance
        logger_instance: The logger to search for handlers (None for root logger)

    Returns:
        Number of handlers that were updated
    """
    inject_logger = logging.getLogger(__name__)
    target_logger = logger_instance or logging.getLogger()
    updated_count = 0

    # Search all handlers in the logger hierarchy
    loggers_to_check = [target_logger]

    # Also check all existing loggers
    for name in logging.Logger.manager.loggerDict:
        logger_obj = logging.getLogger(name)
        if logger_obj not in loggers_to_check:
            loggers_to_check.append(logger_obj)

    for logger_obj in loggers_to_check:
        for handler in logger_obj.handlers:
            if isinstance(handler, IncidentCaptureHandler):
                handler.set_graph_audit_service(graph_audit_service)
                updated_count += 1
                inject_logger.info(f"Injected graph audit service into handler for logger: {logger_obj.name}")

    if updated_count == 0:
        inject_logger.warning("No IncidentCaptureHandler instances found to inject graph audit service")
    else:
        inject_logger.info(
            f"Successfully injected graph audit service into {updated_count} incident capture handler(s)"
        )

    return updated_count
