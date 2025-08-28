"""
Base classes and utilities for database tools.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


class BaseDBTool:
    """Base class for all database tools."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize with database connection."""
        if db_path is None:
            # Import locally to avoid circular imports
            import sys

            sys.path.insert(0, str(Path(__file__).parent.parent.parent))
            from ciris_engine.logic.config import get_sqlite_db_full_path

            db_path = get_sqlite_db_full_path()

        self.db_path = db_path
        self.audit_db_path = Path(self.db_path).parent / "ciris_audit.db"

    def get_connection(self, db_path: Optional[str] = None) -> sqlite3.Connection:
        """Get database connection with row factory."""
        path = db_path or self.db_path
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn

    def format_size(self, bytes: int) -> str:
        """Format bytes as human-readable size."""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes < 1024.0:
                return f"{bytes:.2f} {unit}"
            bytes /= 1024.0
        return f"{bytes:.2f} TB"

    def format_timedelta(self, td: timedelta) -> str:
        """Format timedelta as human-readable string."""
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)

    def parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse various timestamp formats to timezone-aware datetime."""
        if not timestamp_str:
            return datetime.now(timezone.utc)

        # Handle Z suffix
        if "Z" in timestamp_str:
            timestamp_str = timestamp_str.replace("Z", "+00:00")

        # Try parsing ISO format
        try:
            dt = datetime.fromisoformat(timestamp_str)
            # Ensure timezone aware
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            # Fallback
            return datetime.now(timezone.utc)


class ReportFormatter:
    """Utilities for formatting reports."""

    @staticmethod
    def print_section(title: str, width: int = 80):
        """Print a section header."""
        print("\n" + "=" * width)
        print(f" {title} ".center(width))
        print("=" * width)

    @staticmethod
    def print_subsection(title: str, width: int = 60):
        """Print a subsection header."""
        print(f"\n{title}")
        print("-" * len(title))

    @staticmethod
    def format_table(headers: list, rows: list, widths: Optional[list] = None) -> str:
        """Format data as a table."""
        if not widths:
            widths = [20] * len(headers)

        # Header
        header_line = " | ".join(h[:w].ljust(w) for h, w in zip(headers, widths))
        separator = "-+-".join("-" * w for w in widths)

        lines = [header_line, separator]

        # Rows
        for row in rows:
            row_line = " | ".join(str(cell)[:w].ljust(w) for cell, w in zip(row, widths))
            lines.append(row_line)

        return "\n".join(lines)
