"""
CIRIS Agent CLI - Thin wrapper around main.py for pip-installed usage.

This provides a 'ciris-agent' command that preserves all existing Click functionality
from main.py without reinventing the wheel.

Usage after 'pip install ciris-agent':
    ciris-agent --adapter api --port 8000
    ciris-agent --adapter cli
    ciris-agent --adapter discord --discord-token TOKEN
"""

import sys
from pathlib import Path


def main() -> None:
    """
    Entry point for the ciris-agent CLI command.

    This is a thin wrapper that delegates to main.py, preserving all existing
    Click CLI functionality without modification.
    """
    # Ensure parent directory is in path so we can import main
    parent_dir = Path(__file__).parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    # Import and run the existing main() function from main.py
    # This preserves all Click decorators, options, and logic
    try:
        import main as ciris_main

        ciris_main.main()
    except ImportError as e:
        print(f"ERROR: Failed to import main module: {e}", file=sys.stderr)
        print("This should not happen in a properly installed package.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
