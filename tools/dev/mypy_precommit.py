#!/usr/bin/env python3
"""
Mypy pre-commit hook wrapper.

Runs mypy on changed files and reports issues without blocking the commit.
This allows developers to see type errors early while not interrupting flow.

Exit code is always 0 (success) to avoid blocking commits.
Errors are printed with a clear warning header.
"""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run mypy on provided files and report results."""
    if len(sys.argv) < 2:
        return 0

    files = sys.argv[1:]

    # Filter to only Python files in ciris_engine or ciris_adapters
    relevant_files = [
        f for f in files if f.endswith(".py") and (f.startswith("ciris_engine/") or f.startswith("ciris_adapters/"))
    ]

    if not relevant_files:
        return 0

    # Run mypy on the relevant files
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "mypy",
                "--config-file=mypy.ini",
                "--ignore-missing-imports",
                "--no-error-summary",
            ]
            + relevant_files,
            capture_output=True,
            text=True,
            timeout=120,
        )

        # Check if there were any errors
        if result.returncode != 0 and result.stdout.strip():
            # Count errors
            error_lines = [line for line in result.stdout.split("\n") if ": error:" in line]
            error_count = len(error_lines)

            if error_count > 0:
                print("\n" + "=" * 60)
                print(f"⚠️  MYPY: {error_count} type error(s) found (informational)")
                print("=" * 60)
                print(result.stdout)
                print("=" * 60)
                print("💡 Tip: Fix these before pushing to avoid CI failures")
                print("=" * 60 + "\n")

        # Also print any stderr (warnings, etc.)
        if result.stderr.strip():
            # Filter out common noise
            stderr_lines = [line for line in result.stderr.split("\n") if line.strip() and "note:" not in line.lower()]
            if stderr_lines:
                print("\n".join(stderr_lines))

    except subprocess.TimeoutExpired:
        print("⚠️  MYPY: Timed out (skipping)")
    except FileNotFoundError:
        print("⚠️  MYPY: Not installed (skipping)")
    except Exception as e:
        print(f"⚠️  MYPY: Error running mypy: {e}")

    # Always return 0 to not block commits
    return 0


if __name__ == "__main__":
    sys.exit(main())
