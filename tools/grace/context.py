"""
Work context management - preserve state across breaks.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class WorkContext:
    """Manages work context and state."""

    def __init__(self) -> None:
        """Initialize context manager."""
        try:
            self.context_dir = Path.home() / ".grace"
            self.context_dir.mkdir(exist_ok=True)
            self.context_file = self.context_dir / "context.json"
        except (PermissionError, OSError):
            # Fallback for CI environments where home dir might not be writable
            self.context_dir = Path("/tmp/.grace")
            self.context_dir.mkdir(exist_ok=True)
            self.context_file = self.context_dir / "context.json"
        # Anti-Goodhart: Removed work_log - tracking hours incentivizes wrong behavior

    def save(self, message: str = "") -> None:
        """Save current work context."""
        try:
            context = {
                "timestamp": datetime.now().isoformat(),
                "git_branch": self._get_git_branch(),
                "last_commit": self._get_last_commit(),
                "uncommitted": self._has_uncommitted_changes(),
                "message": message,
            }

            with open(self.context_file, "w") as f:
                json.dump(context, f, indent=2)
        except (PermissionError, OSError):
            # Gracefully handle file system issues in CI environments
            pass

    def load(self) -> Optional[Dict[str, Any]]:
        """Load saved context."""
        try:
            if not self.context_file.exists():
                return None
            with open(self.context_file) as f:
                return json.load(f)
        except (FileNotFoundError, PermissionError, OSError, json.JSONDecodeError):
            # Gracefully handle file system issues in CI environments
            return None

    # Removed time tracking methods - Goodhart's Law:
    # "When a measure becomes a target, it ceases to be a good measure."
    # Tracking hours optimizes for time spent, not problems solved.
    # Quality software emerges from clear thinking, not clock watching.

    def _get_git_branch(self) -> str:
        """Get current git branch."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception:
            return "unknown"

    def _get_last_commit(self) -> str:
        """Get last commit message."""
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except Exception:
            return "no commits"

    def _has_uncommitted_changes(self) -> bool:
        """Check for uncommitted changes."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                check=True,
            )
            return bool(result.stdout.strip())
        except Exception:
            return False
