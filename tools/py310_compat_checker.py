#!/usr/bin/env python3
"""
Python 3.10 Compatibility Checker

Scans the CIRIS codebase for Python 3.11+ features that won't work
on Android (Chaquopy uses Python 3.10).

Usage:
    python -m tools.py310_compat_checker [--fix] [--verbose] [path]
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Patterns for features introduced in Python 3.11+
INCOMPATIBLE_PATTERNS: Dict[str, Dict[str, str]] = {
    # asyncio.timeout (3.11+)
    r"asyncio\.timeout\s*\(": {
        "feature": "asyncio.timeout",
        "version": "3.11",
        "fix": "Use asyncio.wait_for() or add _async_timeout polyfill",
        "severity": "error",
    },
    # tomllib (3.11+) - standard library
    r"^import tomllib|^from tomllib": {
        "feature": "tomllib (stdlib)",
        "version": "3.11",
        "fix": "Use tomli package instead",
        "severity": "error",
    },
    # ExceptionGroup (3.11+)
    r"ExceptionGroup|BaseExceptionGroup": {
        "feature": "ExceptionGroup",
        "version": "3.11",
        "fix": "Use exceptiongroup backport package",
        "severity": "error",
    },
    # TaskGroup (3.11+)
    r"asyncio\.TaskGroup": {
        "feature": "asyncio.TaskGroup",
        "version": "3.11",
        "fix": "Use anyio.create_task_group() or manual task management",
        "severity": "error",
    },
    # Self type (3.11+)
    r"from typing import.*\bSelf\b|typing\.Self": {
        "feature": "typing.Self",
        "version": "3.11",
        "fix": "Use typing_extensions.Self",
        "severity": "error",
    },
    # LiteralString (3.11+)
    r"from typing import.*\bLiteralString\b|typing\.LiteralString": {
        "feature": "typing.LiteralString",
        "version": "3.11",
        "fix": "Use typing_extensions.LiteralString",
        "severity": "error",
    },
    # Required/NotRequired for TypedDict (3.11+) - already in typing_extensions
    r"from typing import.*\bRequired\b|from typing import.*\bNotRequired\b": {
        "feature": "typing.Required/NotRequired",
        "version": "3.11",
        "fix": "Use typing_extensions.Required/NotRequired",
        "severity": "warning",
    },
    # StrEnum (3.11+)
    r"from enum import.*\bStrEnum\b|enum\.StrEnum": {
        "feature": "enum.StrEnum",
        "version": "3.11",
        "fix": "Use (str, Enum) base classes instead",
        "severity": "error",
    },
    # New string methods (3.11+)
    r"\.removeprefix\(|\.removesuffix\(": {
        "feature": "str.removeprefix/removesuffix",
        "version": "3.9",  # Actually 3.9, so should be fine
        "fix": "These are available in 3.9+, should be OK",
        "severity": "info",
    },
    # cbrt, exp2 in math (3.11+)
    r"math\.cbrt|math\.exp2": {
        "feature": "math.cbrt/exp2",
        "version": "3.11",
        "fix": "Use pow(x, 1/3) or 2**x instead",
        "severity": "error",
    },
    # datetime.UTC (3.11+)
    r"datetime\.UTC\b": {
        "feature": "datetime.UTC",
        "version": "3.11",
        "fix": "Use datetime.timezone.utc instead",
        "severity": "error",
    },
    # Walrus operator := in comprehensions with same name (edge case bug fixed in 3.11)
    # This is too complex to regex check
}

# Python 3.12+ features (even more incompatible)
PY312_PATTERNS: Dict[str, Dict[str, str]] = {
    # Type parameter syntax (3.12+)
    r"def \w+\[": {
        "feature": "Type parameter syntax def func[T](...)",
        "version": "3.12",
        "fix": "Use TypeVar instead",
        "severity": "error",
    },
    r"class \w+\[": {
        "feature": "Type parameter syntax class Foo[T]",
        "version": "3.12",
        "fix": "Use Generic[T] instead",
        "severity": "error",
    },
    # f-string improvements (nested quotes) - hard to detect
}


@dataclass
class Issue:
    """Represents a compatibility issue found in the code."""

    file: Path
    line: int
    column: int
    feature: str
    version: str
    fix: str
    severity: str
    code_snippet: str


def scan_file(filepath: Path, verbose: bool = False) -> List[Issue]:
    """Scan a single Python file for compatibility issues."""
    issues: List[Issue] = []

    try:
        content = filepath.read_text(encoding="utf-8")
        lines = content.split("\n")
    except Exception as e:
        if verbose:
            print(f"  Warning: Could not read {filepath}: {e}")
        return issues

    # Skip test files and virtual environments
    path_str = str(filepath)
    if any(skip in path_str for skip in ["/tests/", "/.venv/", "/venv/", "/__pycache__/", "/site-packages/"]):
        return issues

    # Check each pattern
    all_patterns = {**INCOMPATIBLE_PATTERNS, **PY312_PATTERNS}

    for pattern, info in all_patterns.items():
        regex = re.compile(pattern, re.MULTILINE)
        for match in regex.finditer(content):
            # Calculate line number
            line_start = content.count("\n", 0, match.start()) + 1
            col = match.start() - content.rfind("\n", 0, match.start())

            # Get code snippet
            snippet = lines[line_start - 1].strip() if line_start <= len(lines) else ""

            issues.append(
                Issue(
                    file=filepath,
                    line=line_start,
                    column=col,
                    feature=info["feature"],
                    version=info["version"],
                    fix=info["fix"],
                    severity=info["severity"],
                    code_snippet=snippet[:100],
                )
            )

    # Also try to parse the AST to catch syntax-level issues
    try:
        ast.parse(content, filename=str(filepath))
    except SyntaxError as e:
        # This might indicate 3.12+ syntax
        issues.append(
            Issue(
                file=filepath,
                line=e.lineno or 0,
                column=e.offset or 0,
                feature="Syntax incompatibility",
                version="unknown",
                fix="Check for Python 3.12+ syntax",
                severity="error",
                code_snippet=str(e.text or "")[:100],
            )
        )

    return issues


def scan_directory(directory: Path, verbose: bool = False) -> List[Issue]:
    """Scan all Python files in a directory."""
    all_issues: List[Issue] = []

    py_files = list(directory.rglob("*.py"))
    if verbose:
        print(f"Scanning {len(py_files)} Python files...")

    for filepath in py_files:
        issues = scan_file(filepath, verbose)
        all_issues.extend(issues)
        if verbose and issues:
            print(f"  Found {len(issues)} issues in {filepath}")

    return all_issues


def print_report(issues: List[Issue], verbose: bool = False) -> None:
    """Print a formatted report of issues found."""
    if not issues:
        print("\n" + "=" * 60)
        print("Python 3.10 Compatibility Check: PASSED")
        print("=" * 60)
        print("No Python 3.11+ features detected.")
        return

    # Group by severity
    errors = [i for i in issues if i.severity == "error"]
    warnings = [i for i in issues if i.severity == "warning"]
    infos = [i for i in issues if i.severity == "info"]

    print("\n" + "=" * 60)
    print("Python 3.10 Compatibility Check: ISSUES FOUND")
    print("=" * 60)
    print(f"\nTotal issues: {len(issues)}")
    print(f"  Errors:   {len(errors)}")
    print(f"  Warnings: {len(warnings)}")
    print(f"  Info:     {len(infos)}")

    if errors:
        print("\n" + "-" * 60)
        print("ERRORS (Must fix for Python 3.10)")
        print("-" * 60)
        for issue in errors:
            print(f"\n{issue.file}:{issue.line}")
            print(f"  Feature: {issue.feature} (Python {issue.version}+)")
            print(f"  Code: {issue.code_snippet}")
            print(f"  Fix: {issue.fix}")

    if warnings:
        print("\n" + "-" * 60)
        print("WARNINGS (Should review)")
        print("-" * 60)
        for issue in warnings:
            print(f"\n{issue.file}:{issue.line}")
            print(f"  Feature: {issue.feature} (Python {issue.version}+)")
            print(f"  Code: {issue.code_snippet}")
            print(f"  Fix: {issue.fix}")

    if verbose and infos:
        print("\n" + "-" * 60)
        print("INFO")
        print("-" * 60)
        for issue in infos:
            print(f"\n{issue.file}:{issue.line}")
            print(f"  Feature: {issue.feature}")


def generate_fix_suggestions(issues: List[Issue]) -> Dict[Path, List[Tuple[int, str, str]]]:
    """Generate suggested fixes for issues."""
    fixes: Dict[Path, List[Tuple[int, str, str]]] = {}

    for issue in issues:
        if issue.severity != "error":
            continue

        if issue.file not in fixes:
            fixes[issue.file] = []

        if "asyncio.timeout" in issue.feature:
            fixes[issue.file].append(
                (
                    issue.line,
                    "asyncio.timeout",
                    "Add _async_timeout polyfill (see ciris_runtime_helpers.py for example)",
                )
            )

    return fixes


def main():
    parser = argparse.ArgumentParser(description="Check Python 3.10 compatibility")
    parser.add_argument("path", nargs="?", default=".", help="Path to scan (default: current directory)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--fix", action="store_true", help="Show detailed fix suggestions")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    # Determine scan path
    scan_path = Path(args.path).resolve()
    if not scan_path.exists():
        print(f"Error: Path does not exist: {scan_path}")
        sys.exit(1)

    print(f"Scanning for Python 3.11+ features in: {scan_path}")
    print("(Android uses Python 3.10 via Chaquopy)\n")

    # Scan
    if scan_path.is_file():
        issues = scan_file(scan_path, args.verbose)
    else:
        issues = scan_directory(scan_path, args.verbose)

    # Output
    if args.json:
        import json

        output = [
            {
                "file": str(i.file),
                "line": i.line,
                "feature": i.feature,
                "version": i.version,
                "fix": i.fix,
                "severity": i.severity,
            }
            for i in issues
        ]
        print(json.dumps(output, indent=2))
    else:
        print_report(issues, args.verbose)

        if args.fix and issues:
            fixes = generate_fix_suggestions(issues)
            if fixes:
                print("\n" + "=" * 60)
                print("FIX SUGGESTIONS")
                print("=" * 60)
                for filepath, file_fixes in fixes.items():
                    print(f"\n{filepath}:")
                    for line, feature, suggestion in file_fixes:
                        print(f"  Line {line}: {suggestion}")

    # Exit code
    errors = [i for i in issues if i.severity == "error"]
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
