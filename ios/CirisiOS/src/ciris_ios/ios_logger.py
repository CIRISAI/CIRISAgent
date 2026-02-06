"""
iOS Logging Module for CIRIS KMP.

Provides structured logging to files that can be accessed via the API
or displayed in a debug view.

Log files are written to ~/Documents/ciris/logs/
- kmp_runtime.log - Main runtime log (rotating, keeps last 3)
- kmp_startup.log - Startup sequence only
- kmp_errors.log - Errors only
- swift_bridge.log - Swift-side logs (written by Swift)
"""

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# Log directory
_LOG_DIR: Optional[Path] = None
_INITIALIZED = False


# Custom formatters
class IOSFormatter(logging.Formatter):
    """Formatter with iOS-friendly output."""

    def format(self, record: logging.LogRecord) -> str:
        # Add timestamp, level, component, message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level = record.levelname[0]  # D, I, W, E
        component = record.name.replace("ciris.", "")

        # Format: [TIME] L [COMPONENT] message
        base = f"[{timestamp}] {level} [{component}] {record.getMessage()}"

        # Add exception info if present
        if record.exc_info:
            base += "\n" + "".join(traceback.format_exception(*record.exc_info))

        return base


def get_log_dir() -> Path:
    """Get or create the log directory."""
    global _LOG_DIR
    if _LOG_DIR is None:
        _LOG_DIR = Path.home() / "Documents" / "ciris" / "logs"
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def init_logging(component: str = "kmp") -> logging.Logger:
    """
    Initialize iOS logging system.

    Args:
        component: Component name (e.g., "kmp", "runtime", "watchdog")

    Returns:
        Logger instance for the component
    """
    global _INITIALIZED

    log_dir = get_log_dir()

    # Create logger
    logger = logging.getLogger(f"ciris.{component}")
    logger.setLevel(logging.DEBUG)

    # Only set up handlers once for root ciris logger
    root_logger = logging.getLogger("ciris")
    if not _INITIALIZED:
        root_logger.setLevel(logging.DEBUG)

        # Clear any existing handlers
        root_logger.handlers.clear()

        formatter = IOSFormatter()

        # 1. Main runtime log (all messages)
        main_log = log_dir / "kmp_runtime.log"
        # Rotate if too large (>1MB)
        if main_log.exists() and main_log.stat().st_size > 1_000_000:
            _rotate_log(main_log)

        main_handler = logging.FileHandler(main_log, mode="a", encoding="utf-8")
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(formatter)
        root_logger.addHandler(main_handler)

        # 2. Error log (errors only)
        error_log = log_dir / "kmp_errors.log"
        error_handler = logging.FileHandler(error_log, mode="a", encoding="utf-8")
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)

        # 3. Console/stdout (for Xcode console when debugging)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        _INITIALIZED = True

        # Log startup marker
        root_logger.info("=" * 60)
        root_logger.info(f"CIRIS iOS KMP Logger initialized at {datetime.now().isoformat()}")
        root_logger.info(f"Log directory: {log_dir}")
        root_logger.info("=" * 60)

    return logger


def _rotate_log(log_path: Path, keep: int = 3):
    """Rotate a log file, keeping the last N versions."""
    for i in range(keep - 1, 0, -1):
        old = log_path.with_suffix(f".{i}.log")
        new = log_path.with_suffix(f".{i + 1}.log")
        if old.exists():
            if new.exists():
                new.unlink()
            old.rename(new)

    if log_path.exists():
        backup = log_path.with_suffix(".1.log")
        if backup.exists():
            backup.unlink()
        log_path.rename(backup)


def log_phase(logger: logging.Logger, phase: str, status: str = "START", details: str = ""):
    """
    Log a phase transition with clear markers.

    Args:
        logger: Logger instance
        phase: Phase name (e.g., "STARTUP", "RUNTIME", "SHUTDOWN")
        status: Status (START, OK, FAIL, END)
        details: Additional details
    """
    marker = ">>>" if status == "START" else "<<<" if status in ("OK", "END") else "!!!"
    msg = f"{marker} PHASE: {phase} [{status}]"
    if details:
        msg += f" - {details}"

    if status == "FAIL":
        logger.error(msg)
    else:
        logger.info(msg)


def log_step(logger: logging.Logger, step: str, status: str = "...", details: str = ""):
    """
    Log a step within a phase.

    Args:
        logger: Logger instance
        step: Step name
        status: Status indicator
        details: Additional details
    """
    msg = f"  [{status}] {step}"
    if details:
        msg += f": {details}"
    logger.info(msg)


def write_status_file(status: dict):
    """
    Write a JSON status file that Swift can read.

    Args:
        status: Dictionary with status information
    """
    status_path = get_log_dir().parent / "runtime_status.json"
    status["timestamp"] = datetime.now().isoformat()
    status["timestamp_unix"] = time.time()

    try:
        with open(status_path, "w") as f:
            json.dump(status, f, indent=2)
    except Exception as e:
        print(f"[ios_logger] Failed to write status file: {e}")


def read_status_file() -> Optional[dict]:
    """Read the runtime status file."""
    status_path = get_log_dir().parent / "runtime_status.json"
    try:
        if status_path.exists():
            with open(status_path) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def get_recent_logs(lines: int = 100, log_type: str = "runtime") -> str:
    """
    Get recent log entries.

    Args:
        lines: Number of lines to return
        log_type: Type of log ("runtime", "errors", "startup", "swift")

    Returns:
        String with recent log entries
    """
    log_dir = get_log_dir()

    log_files = {
        "runtime": log_dir / "kmp_runtime.log",
        "errors": log_dir / "kmp_errors.log",
        "startup": log_dir / "kmp_startup.log",
        "swift": log_dir / "swift_bridge.log",
    }

    log_file = log_files.get(log_type, log_files["runtime"])

    if not log_file.exists():
        return f"No {log_type} log file found"

    try:
        with open(log_file, "r") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])
    except Exception as e:
        return f"Error reading log: {e}"


def get_all_logs_summary() -> dict:
    """Get a summary of all log files."""
    log_dir = get_log_dir()

    summary = {"log_directory": str(log_dir), "files": {}}

    for log_file in log_dir.glob("*.log"):
        try:
            stat = log_file.stat()
            summary["files"][log_file.name] = {
                "size_bytes": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "lines": sum(1 for _ in open(log_file)),
            }
        except Exception as e:
            summary["files"][log_file.name] = {"error": str(e)}

    return summary


def _human_size(size: int) -> str:
    """Convert bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
