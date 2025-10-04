"""
Log file reader for telemetry endpoint.
Reads actual log files from disk instead of audit entries.
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, List, Optional

from ciris_engine.schemas.api.telemetry import LogContext

logger = logging.getLogger(__name__)

# Import LogEntry from the models file where it's defined
from .telemetry_models import LogEntry


class LogFileReader:
    """Reads and parses log files from disk."""

    LOG_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) - ([^-]+) - (\w+) - (.*)$")

    def __init__(self, logs_dir: str = "/app/logs"):
        self.logs_dir = Path(logs_dir)

    def _get_actual_log_files(self) -> tuple[Optional[Path], Optional[Path]]:
        """Get the actual log files from CURRENT logging handlers first, then fall back to stored paths."""
        main_log_file = None
        incident_log_file = None

        # CRITICAL FIX: Always check current logging handlers FIRST
        # This ensures we get the current session's log files, not stale ones
        import logging

        root_logger = logging.getLogger()

        for handler in root_logger.handlers:
            if isinstance(handler, logging.FileHandler):
                filename = Path(handler.baseFilename)
                if filename.exists():  # Only use if file actually exists
                    if "incident" in filename.name and incident_log_file is None:
                        incident_log_file = filename
                        logger.debug(f"Found incident log from handler: {incident_log_file}")
                    elif main_log_file is None:
                        main_log_file = filename
                        logger.debug(f"Found main log from handler: {main_log_file}")

        # Only use stored filenames if we couldn't find from handlers
        # AND verify the files actually exist and are recent
        if main_log_file is None:
            current_log_path = self.logs_dir / ".current_log"
            if current_log_path.exists():
                try:
                    with open(current_log_path, "r") as f:
                        stored_path = Path(f.read().strip())
                        # Verify the file exists and was modified recently (within last hour)
                        if stored_path.exists():
                            import time

                            file_age = time.time() - stored_path.stat().st_mtime
                            if file_age < 3600:  # Less than 1 hour old
                                main_log_file = stored_path
                                logger.debug(f"Using stored main log: {main_log_file}")
                            else:
                                logger.debug(f"Stored main log too old: {file_age:.0f} seconds")
                except (IOError, OSError, ValueError) as e:
                    logger.debug(f"Failed to read current log path: {e}")

        if incident_log_file is None:
            current_incident_path = self.logs_dir / ".current_incident_log"
            if current_incident_path.exists():
                try:
                    with open(current_incident_path, "r") as f:
                        stored_path = Path(f.read().strip())
                        # Verify the file exists and was modified recently
                        if stored_path.exists():
                            import time

                            file_age = time.time() - stored_path.stat().st_mtime
                            if file_age < 3600:  # Less than 1 hour old
                                incident_log_file = stored_path
                                logger.debug(f"Using stored incident log: {incident_log_file}")
                            else:
                                logger.debug(f"Stored incident log too old: {file_age:.0f} seconds")
                except (IOError, OSError, ValueError) as e:
                    logger.debug(f"Failed to read current incident log path: {e}")

        # Last resort: try symlinks (but these might be stale)
        if main_log_file is None:
            latest_log = self.logs_dir / "latest.log"
            if latest_log.exists():
                try:
                    main_log_file = latest_log.resolve()
                except (OSError, RuntimeError) as e:
                    logger.debug(f"Failed to resolve latest log symlink: {e}")
                    main_log_file = latest_log

        if incident_log_file is None:
            incidents_log = self.logs_dir / "incidents_latest.log"
            if incidents_log.exists():
                try:
                    incident_log_file = incidents_log.resolve()
                except (OSError, RuntimeError) as e:
                    logger.debug(f"Failed to resolve incidents log symlink: {e}")
                    incident_log_file = incidents_log

        return main_log_file, incident_log_file

    def read_logs(
        self,
        level: Optional[str] = None,
        service: Optional[str] = None,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        include_incidents: bool = True,
    ) -> List[LogEntry]:
        """Read logs from files and return as LogEntry objects."""
        logs = []

        # Get actual log files instead of using symlinks
        main_log_file, incident_log_file = self._get_actual_log_files()

        # Read from main log file
        if main_log_file and main_log_file.exists():
            logs.extend(self._parse_log_file(main_log_file, level, service, limit, start_time, end_time))

        # Read from incidents log if requested
        if include_incidents and len(logs) < limit and incident_log_file and incident_log_file.exists():
            logs.extend(
                self._parse_log_file(incident_log_file, level, service, limit - len(logs), start_time, end_time)
            )

        # Sort by timestamp ascending (oldest first, newest last)
        logs.sort(key=lambda x: x.timestamp, reverse=False)

        # Return the most recent logs (last N entries)
        return logs[-limit:] if len(logs) > limit else logs

    def _parse_log_file(
        self,
        file_path: Path,
        level: Optional[str] = None,
        service: Optional[str] = None,
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[LogEntry]:
        """Parse a single log file."""
        logs = []

        try:
            # Read file from end (most recent logs)
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                # Read more lines than needed to account for filtering
                # but cap it to avoid reading huge files
                read_lines = min(limit * 20, 10000)
                lines = self._tail(f, read_lines)

                # Process lines in order (they're already in chronological order from tail)
                for line in lines:
                    entry = self._parse_log_line(line)
                    if entry:
                        # Apply filters
                        if level and entry.level != level.upper():
                            continue
                        if service and service.lower() not in entry.service.lower():
                            continue
                        if start_time and entry.timestamp < start_time:
                            continue
                        if end_time and entry.timestamp > end_time:
                            continue

                        logs.append(entry)

        except Exception as e:
            # Log parsing error, but don't fail the endpoint
            print(f"Error reading log file {file_path}: {e}")

        return logs

    def _tail(self, file_obj: IO[str], num_lines: int) -> List[str]:
        """Read last N lines from a file efficiently."""
        # For large files, seek to end and read backwards
        file_obj.seek(0, 2)  # Go to end of file
        file_size = file_obj.tell()

        if file_size == 0:
            return []

        # Read chunk size (adjust based on expected line length)
        chunk_size = min(file_size, 8192)
        lines: List[str] = []
        position = file_size

        while len(lines) < num_lines + 1 and position > 0:
            # Calculate how much to read
            read_size = min(chunk_size, position)
            position -= read_size

            # Seek to position and read
            file_obj.seek(position)
            chunk = file_obj.read(read_size)

            # Split into lines
            chunk_lines = chunk.split("\n")

            # Combine with existing lines
            if lines:
                # Last line from previous chunk might be incomplete
                chunk_lines[-1] += lines[0]
                lines = chunk_lines + lines[1:]
            else:
                lines = chunk_lines

        # Remove empty lines and return last N non-empty lines
        lines = [line for line in lines if line.strip()]
        return lines[-num_lines:]

    def _parse_log_line(self, line: str) -> Optional[LogEntry]:
        """Parse a single log line into a LogEntry."""
        line = line.strip()
        if not line:
            return None

        match = self.LOG_PATTERN.match(line)
        if not match:
            return None

        timestamp_str, module, level, message = match.groups()

        try:
            # Parse timestamp and make it timezone-aware (UTC)
            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
            timestamp = timestamp.replace(tzinfo=timezone.utc)

            # Extract service name from module
            service = module.strip().split(".")[0]

            # Try to extract JSON context from message
            context_data = {}
            if "{" in message and "}" in message:
                try:
                    # Find JSON in message
                    json_start = message.find("{")
                    json_end = message.rfind("}") + 1
                    json_str = message[json_start:json_end]
                    context_data = json.loads(json_str)
                    # Remove JSON from message
                    message = message[:json_start].strip() + message[json_end:].strip()
                except (json.JSONDecodeError, ValueError) as e:
                    logger.debug(f"Failed to parse JSON from log message: {e}")
                    pass

            # Build log entry
            return LogEntry(
                timestamp=timestamp,
                level=level.upper(),
                service=service,
                message=message.strip(),
                context=LogContext(
                    trace_id=context_data.get("trace_id"),
                    correlation_id=context_data.get("correlation_id"),
                    user_id=context_data.get("user_id"),
                    entity_id=context_data.get("entity_id"),
                    error_details=context_data.get("error_details") if level.upper() in ["ERROR", "CRITICAL"] else None,
                    metadata=context_data,
                ),
                trace_id=context_data.get("trace_id") or context_data.get("correlation_id"),
            )
        except Exception:
            # If parsing fails, return None
            return None


# Global instance
log_reader = LogFileReader()
