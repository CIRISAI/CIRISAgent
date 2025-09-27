#!/usr/bin/env python3
"""
Grace pre-commit hook - Smart gatekeeper for code quality.

Fails on critical issues, reports quality concerns as reminders.
Runs checks concurrently for speed.
"""

import asyncio
import subprocess
import sys
from typing import List, Optional, Tuple


async def run_command_async(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command asynchronously and return exit code, stdout, stderr."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return proc.returncode or 0, stdout.decode(), stderr.decode()
    except asyncio.TimeoutError:
        return 1, "", "Command timed out"
    except Exception as e:
        return 1, "", str(e)


async def check_syntax_errors() -> Optional[str]:
    """Check for Python syntax errors."""
    code, stdout, stderr = await run_command_async(["python", "-m", "py_compile", "main.py"])
    if code != 0:
        return "❌ CRITICAL: Python syntax errors detected"
    return None


async def check_merge_conflicts() -> Optional[str]:
    """Check for merge conflicts."""
    code, stdout, _ = await run_command_async(["git", "diff", "--check"])
    if "conflict" in stdout.lower():
        return "❌ CRITICAL: Merge conflicts detected"
    return None


async def check_private_keys() -> Optional[str]:
    """Check for private keys in staged files."""
    code, stdout, _ = await run_command_async(["git", "diff", "--cached", "--name-only"])
    dangerous_files = []
    for file in stdout.splitlines():
        if any(pattern in file.lower() for pattern in [".pem", ".key", "id_rsa", "id_dsa", ".env"]):
            dangerous_files.append(file)

    if dangerous_files:
        return f"❌ CRITICAL: Possible secrets in: {', '.join(dangerous_files)}"
    return None


async def check_ruff_issues() -> Optional[str]:
    """Check ruff linting issues."""
    code, stdout, _ = await run_command_async(["pre-commit", "run", "ruff", "--all-files"])
    if code != 0:
        # Count specific error types
        error_count = stdout.count("F841") + stdout.count("E402") + stdout.count("E741") + stdout.count("F821")
        if error_count > 0:
            return f"📝 Ruff: {error_count} linting issues to clean up"
    return None


async def check_mypy_issues() -> Optional[str]:
    """Check mypy type annotation issues."""
    code, stdout, _ = await run_command_async(["pre-commit", "run", "mypy", "--all-files"])
    if code != 0:
        # Extract error count from mypy output
        for line in stdout.splitlines():
            if "Found" in line and "error" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.isdigit():
                        return f"📝 MyPy: {part} type annotation issues"
                return "📝 MyPy: Multiple type annotation issues"
    return None


async def check_dict_any_violations() -> Optional[str]:
    """Check Dict[str, Any] violations."""
    code, stdout, _ = await run_command_async(["python", "tools/audit_dict_any_usage.py"])
    if "PRODUCTION CODE VIOLATIONS" in stdout:
        for line in stdout.splitlines():
            if "Occurrences:" in line and "PRODUCTION" in stdout[: stdout.index(line)]:
                count = line.split(":")[1].strip().split()[0]
                return f"📝 Dict[str, Any]: {count} violations of 'No Dicts' principle"
    return None


async def run_formatters() -> List[str]:
    """Run auto-formatters in parallel and return list of files modified."""
    modified_files = []

    # Run black, isort, and version.py in parallel
    black_task = run_command_async(["black", ".", "--exclude=venv", "--line-length=120"])
    isort_task = run_command_async(["isort", ".", "--skip=venv", "--profile=black", "--line-length=120"])
    version_task = run_command_async(["python", "version.py"])

    black_result, isort_result, version_result = await asyncio.gather(black_task, isort_task, version_task)

    if "reformatted" in black_result[1]:
        for line in black_result[1].splitlines():
            if "reformatted" in line:
                modified_files.append("Black formatted files")
                break

    if "Fixing" in isort_result[1]:
        modified_files.append("isort sorted imports")

    if version_result[0] == 0 and "BUILD_INFO.txt has been created" in version_result[1]:
        modified_files.append("updated BUILD_INFO.txt")

    return modified_files


async def check_critical_issues() -> Tuple[bool, List[str]]:
    """Check for critical issues that should block commits."""
    # Run all critical checks in parallel
    tasks = [
        check_syntax_errors(),
        check_merge_conflicts(),
        check_private_keys(),
    ]

    results = await asyncio.gather(*tasks)
    critical_issues = [issue for issue in results if issue is not None]

    return len(critical_issues) == 0, critical_issues


async def check_quality_issues() -> List[str]:
    """Check for quality issues that should be reported but not block."""
    # Run all quality checks in parallel
    tasks = [
        check_ruff_issues(),
        check_mypy_issues(),
        check_dict_any_violations(),
    ]

    results = await asyncio.gather(*tasks)
    reminders = [reminder for reminder in results if reminder is not None]

    return reminders


async def check_remaining_changes() -> List[str]:
    """Check what files are still modified after formatting."""
    code, stdout, _ = await run_command_async(["git", "diff", "--name-only"])
    return stdout.strip().split("\n") if stdout.strip() else []


async def auto_commit_build_info() -> bool:
    """Auto-commit BUILD_INFO.txt if it's the only remaining change."""
    try:
        # Stage BUILD_INFO.txt
        await run_command_async(["git", "add", "BUILD_INFO.txt"])

        # Commit with --no-verify to bypass hooks
        code, _, _ = await run_command_async(
            [
                "git",
                "commit",
                "--no-verify",
                "-m",
                "chore: auto-update BUILD_INFO.txt\n\n🤖 Auto-committed by Grace Smart Gatekeeper",
            ]
        )

        return code == 0
    except Exception:
        return False


async def main():
    """Main pre-commit hook logic."""
    print("\n🌟 Grace Pre-commit Check")
    print("=" * 50)

    # Run formatters first (they modify files)
    print("Running auto-formatters...")
    formatted = await run_formatters()
    if formatted:
        print(f"  ✨ Auto-formatted: {', '.join(formatted)}")

    # Check if only BUILD_INFO.txt remains after formatting
    remaining_changes = await check_remaining_changes()
    if len(remaining_changes) == 1 and remaining_changes[0] == "BUILD_INFO.txt":
        print("  📝 BUILD_INFO.txt updated - include it in your commit manually")
        # DISABLED: Auto-commit clutters git log
        # if await auto_commit_build_info():
        #     print("  ✅ BUILD_INFO.txt auto-committed successfully")
        #     print("\n🎉 All changes committed! Grace Smart Gatekeeper complete.")
        #     print("=" * 50)
        #     return 0

    # Run critical and quality checks in parallel
    critical_task = check_critical_issues()
    quality_task = check_quality_issues()

    (passed, critical_issues), reminders = await asyncio.gather(critical_task, quality_task)

    if not passed:
        print("\n⛔ COMMIT BLOCKED - Critical Issues Found:")
        for issue in critical_issues:
            print(f"  {issue}")
        print("\nThese must be fixed before committing.")
        return 1

    if reminders:
        print("\n✅ Commit allowed with quality reminders:")
        print("\nQuality improvements to consider when you have time:")
        for reminder in reminders:
            print(f"  {reminder}")
        print("\n💡 Run 'python -m tools.grace precommit' for detailed fixes")
        print("These won't block your commit, just gentle reminders. 🌱")
    else:
        print("\n🎉 Excellent! All checks passed!")

    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
