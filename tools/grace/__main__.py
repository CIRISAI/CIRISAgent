#!/usr/bin/env python3
"""
Grace command-line interface.
Simple, direct, helpful.
"""

import sys

from .main import Grace


def main() -> None:
    """Main entry point."""
    grace = Grace()

    # Default command
    if len(sys.argv) < 2:
        command = "status"
    else:
        command = sys.argv[1]

    # Command mapping
    commands = {
        "status": grace.status,
        "morning": grace.morning,
        "pause": grace.pause,
        "resume": grace.resume,
        "night": grace.night,
        "deploy": grace.deploy_status,
        "deployment": grace.deploy_status,
        "precommit": lambda: grace.precommit(autofix="--fix" in sys.argv),
        "fix": grace.fix,
        "incidents": lambda: grace.incidents(sys.argv[2] if len(sys.argv) > 2 else "ciris-agent-datum"),
        # Aliases
        "s": grace.status,
        "m": grace.morning,
        "p": grace.pause,
        "r": grace.resume,
        "n": grace.night,
        "d": grace.deploy_status,
        "pc": lambda: grace.precommit(autofix="--fix" in sys.argv),
        "f": grace.fix,
        "i": lambda: grace.incidents(sys.argv[2] if len(sys.argv) > 2 else "ciris-agent-datum"),
    }

    if command in commands:
        print(commands[command]())
    elif command in ["help", "-h", "--help"]:
        print("Grace - Sustainable development companion\n")
        print("Commands:")
        print("  status     - Current session and system health")
        print("  morning    - Morning check-in")
        print("  pause      - Save context before break")
        print("  resume     - Resume after break")
        print("  night      - Evening choice point")
        print("  deploy     - Check deployment status")
        print("  precommit  - Check pre-commit issues (--fix to auto-fix)")
        print("  fix        - Auto-fix pre-commit issues")
        print("  incidents  - Check container incidents log")
        print("             Usage: grace incidents [container_name]")
        print("             Default: ciris-agent-datum")
        print("\nShort forms: s, m, p, r, n, d, pc, f, i")
    else:
        print(f"Unknown command: {command}")
        print("Try 'grace help' for available commands")


if __name__ == "__main__":
    main()
