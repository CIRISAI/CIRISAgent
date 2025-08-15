"""
CI/CD monitoring and guidance for Grace.
Helps track build status, detect blocks, and guide through failures.
Includes Claude-specific guidance from the shepherd.
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class CIMonitor:
    """Monitor CI/CD status and provide guidance."""

    # Claude's bad habits we need to prevent
    CLAUDE_ANTIPATTERNS = [
        "Creating new Dict[str, Any] instead of using existing schemas",
        "Making NewSchemaV2 when OriginalSchema already exists",
        "Checking CI status every 30 seconds (wasteful anxiety)",
        "Creating 'temporary' helper classes that duplicate existing ones",
        "Writing elaborate abstractions instead of using what's there",
    ]

    # Common schemas that exist (reminder for Claude)
    EXISTING_SCHEMAS = {
        "audit": "AuditEventData - ciris_engine/schemas/services/graph/audit.py",
        "metrics": "ServiceMetrics - ciris_engine/schemas/services/telemetry.py",
        "snapshot": "SystemSnapshot - ciris_engine/schemas/runtime/system_snapshot.py",
        "queue": "ProcessingQueueItem - ciris_engine/schemas/processors/base.py",
        "channel": "ChannelContext (system) vs AdapterChannelContext (adapter)",
        "response": "ActionResponse - ciris_engine/schemas/processors/actions.py",
        "config": "ServiceConfig - ciris_engine/schemas/config/service.py",
        "thought": "ThoughtSchema - ciris_engine/schemas/thought.py",
        "guidance": "GuidanceRequest/Response - ciris_engine/schemas/wise_authority.py",
    }

    # Minimum time between CI checks (10 minutes)
    MIN_CHECK_INTERVAL = timedelta(minutes=10)

    def __init__(self):
        """Initialize CI monitor."""
        self.last_check_file = Path("/tmp/.grace_ci_last_check")
        self.start_time = None

    def check_prs(self) -> str:
        """Check status of all open PRs."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--state",
                    "open",
                    "--json",
                    "number,title,headRefName,mergeable,mergeStateStatus,statusCheckRollup",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return "❌ Could not fetch PR status"

            prs = json.loads(result.stdout)
            if not prs:
                return "No open PRs"

            message = []
            for pr in prs:
                num = pr.get("number", "?")
                branch = pr.get("headRefName", "unknown")
                mergeable = pr.get("mergeable", "UNKNOWN")
                merge_state = pr.get("mergeStateStatus", "UNKNOWN")

                # Build status line
                status_parts = []

                # Check conflicts first - they block everything
                if mergeable == "CONFLICTING":
                    status_parts.append("🚨 CONFLICT")
                elif merge_state == "BLOCKED":
                    status_parts.append("⚠️ BLOCKED")

                # Check CI status
                checks = pr.get("statusCheckRollup", [])
                if checks:
                    pending = sum(1 for c in checks if c.get("status") != "COMPLETED")
                    failed = sum(1 for c in checks if c.get("conclusion") == "FAILURE")

                    if pending:
                        status_parts.append(f"⏳ {pending} pending")
                    elif failed:
                        status_parts.append(f"❌ {failed} failed")
                    else:
                        status_parts.append("✅ Passed")

                message.append(f"PR #{num} ({branch}): {' | '.join(status_parts)}")

            return "\n".join(message)

        except Exception as e:
            return f"Error checking PRs: {e}"

    def check_builds(self) -> str:
        """Check Build and Deploy runs across branches."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--workflow",
                    "Build and Deploy",
                    "--limit",
                    "5",
                    "--json",
                    "databaseId,status,conclusion,headBranch,createdAt",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return "❌ Could not fetch builds"

            runs = json.loads(result.stdout)
            if not runs:
                return "No recent builds"

            # Group by branch
            branches = {}
            for run in runs:
                branch = run.get("headBranch", "unknown")
                if branch not in branches:
                    branches[branch] = run

            message = []
            for branch, run in branches.items():
                status = run.get("status", "unknown")
                conclusion = run.get("conclusion", "pending")

                if status == "in_progress":
                    symbol = "⏳"
                    desc = "Running"
                elif conclusion == "success":
                    symbol = "✅"
                    desc = "Success"
                elif conclusion == "failure":
                    symbol = "❌"
                    desc = "Failed"
                else:
                    symbol = "⚠️"
                    desc = conclusion

                message.append(f"{symbol} {branch}: {desc}")

            return "\n".join(message)

        except Exception as e:
            return f"Error checking builds: {e}"

    def check_current_ci(self) -> str:
        """Check CI for current branch."""
        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

            # Get latest run
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--branch",
                    branch,
                    "--limit",
                    "1",
                    "--json",
                    "status,conclusion,name,startedAt",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return f"❌ Could not check CI for {branch}"

            runs = json.loads(result.stdout)
            if not runs:
                return f"No CI runs for {branch}"

            run = runs[0]
            status = run.get("status", "unknown")
            conclusion = run.get("conclusion", "pending")
            name = run.get("name", "Unknown")

            if status == "in_progress":
                # Calculate elapsed time
                started = run.get("startedAt", "")
                if started:
                    start_time = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    elapsed = datetime.now(start_time.tzinfo) - start_time
                    minutes = int(elapsed.total_seconds() / 60)
                    return f"⏳ {name} running ({minutes}m elapsed)"
                return f"⏳ {name} running"
            elif conclusion == "success":
                return f"✅ {name} passed"
            elif conclusion == "failure":
                return f"❌ {name} failed"
            else:
                return f"⚠️ {name}: {conclusion}"

        except Exception as e:
            return f"Error checking CI: {e}"

    def should_check_ci(self) -> tuple[bool, str]:
        """Check if enough time has passed since last CI check."""
        if not self.last_check_file.exists():
            return True, ""

        try:
            last_check = datetime.fromisoformat(self.last_check_file.read_text().strip())
            elapsed = (datetime.now() - last_check).total_seconds() / 60

            if elapsed < 10:
                remaining = 10 - int(elapsed)
                return False, f"(wait {remaining}m before checking again)"
            return True, ""
        except:
            return True, ""

    def record_check(self):
        """Record that we just checked CI."""
        self.last_check_file.write_text(datetime.now().isoformat())

    def get_reminders(self) -> str:
        """Get schema and antipattern reminders for Claude."""
        reminders = ["🧠 Schema Reminders:"]
        for key, schema in self.EXISTING_SCHEMAS.items():
            reminders.append(f"  • {key}: {schema}")

        reminders.append("\n⚠️ Avoid These Patterns:")
        for pattern in self.CLAUDE_ANTIPATTERNS:
            reminders.append(f"  • {pattern}")

        return "\n".join(reminders)

    def analyze_failure(self, run_id: Optional[int] = None) -> str:
        """Analyze CI failure and provide guidance."""
        try:
            # Get failed logs
            cmd = ["gh", "run", "view"]
            if run_id:
                cmd.append(str(run_id))
            cmd.extend(["--log-failed", "--repo", "CIRISAI/CIRISAgent"])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                return "Could not fetch failure logs"

            logs = result.stdout
            if not logs:
                return "No failure logs available"

            # Analyze common patterns
            analysis = []

            if "Dict[str, Any]" in logs:
                analysis.append("🚨 Dict[str, Any] detected - a schema already exists!")
            if "ModuleNotFoundError" in logs:
                analysis.append("📦 Import error - check module paths")
            if "FAILED" in logs:
                failed_count = logs.count("FAILED")
                analysis.append(f"❌ {failed_count} test failures detected")
            if "SonarQube" in logs or "Quality Gate" in logs:
                analysis.append("📊 SonarCloud quality gate issue")

            if analysis:
                return "CI Failure Analysis:\n" + "\n".join(analysis)
            return "Check logs manually for details"

        except Exception as e:
            return f"Error analyzing failure: {e}"

    def get_failure_hints(self) -> str:
        """Get hints for common CI failures."""
        hints = [
            "Common CI failures:",
            "• Dict[str, Any] - Use existing schemas instead",
            "• Import errors - Check all imports",
            "• Test failures - Run locally first",
            "",
            "Remember these exist:",
        ]

        for category, schema in self.EXISTING_SCHEMAS.items():
            hints.append(f"• {category}: {schema}")

        return "\n".join(hints)
