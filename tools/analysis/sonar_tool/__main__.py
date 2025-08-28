#!/usr/bin/env python3
"""
SonarCloud Tool CLI

Usage:
    python -m tools.sonar_tool analyze              # Comprehensive coverage analysis
    python -m tools.sonar_tool tech-debt            # Technical debt analysis
    python -m tools.sonar_tool status               # Quick quality status
    python -m tools.sonar_tool hotspots             # List security hotspots
    python -m tools.sonar_tool find <pattern>       # Find file coverage by pattern
    python -m tools.sonar_tool analyze --export     # Export analysis as JSON
"""

import argparse
import sys
from pathlib import Path

from .commands import CommandHandler

# Configuration
SONAR_TOKEN_FILE = Path.home() / ".sonartoken"


def main():
    parser = argparse.ArgumentParser(
        description="SonarCloud Tool - Comprehensive code quality analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Analyze command (default)
    analyze_parser = subparsers.add_parser("analyze", help="Run comprehensive coverage analysis")
    analyze_parser.add_argument("--export", action="store_true", help="Export analysis as JSON")

    # Tech debt command
    debt_parser = subparsers.add_parser("tech-debt", help="Analyze technical debt")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show quick quality status")

    # Hotspots command
    hotspots_parser = subparsers.add_parser("hotspots", help="List security hotspots")
    hotspots_parser.add_argument(
        "--status", choices=["TO_REVIEW", "REVIEWED", "SAFE", "FIXED"], default="TO_REVIEW", help="Filter by status"
    )

    # Find command
    find_parser = subparsers.add_parser("find", help="Find file coverage by pattern")
    find_parser.add_argument("pattern", help="Pattern to search for in file paths")

    args = parser.parse_args()

    # Default to analyze if no command given
    if not args.command:
        args.command = "analyze"
        args.export = False

    # Load token
    if not SONAR_TOKEN_FILE.exists():
        print(f"Error: Token file not found at {SONAR_TOKEN_FILE}")
        print("Please save your SonarCloud token to ~/.sonartoken")
        sys.exit(1)

    token = SONAR_TOKEN_FILE.read_text().strip()
    handler = CommandHandler(token)

    # Execute command
    try:
        if args.command == "analyze":
            handler.analyze_coverage(export_json=args.export)
        elif args.command == "tech-debt":
            handler.analyze_tech_debt()
        elif args.command == "status":
            handler.quick_status()
        elif args.command == "hotspots":
            handler.list_hotspots(status=args.status)
        elif args.command == "find":
            handler.find_file_coverage(args.pattern)
        else:
            parser.print_help()

    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
