#!/usr/bin/env python3
"""
Grace: A companion for sustainable development.

Helps maintain work-life balance while building meaningful software.
Tracks your natural rhythm, preserves context across breaks, and
suggests appropriate tasks based on time, energy, and commitments.
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class GraceFlow:
    """Manages developer flow with awareness of natural rhythms."""

    # Your actual schedule - discovered through conversation
    SESSIONS = {
        "morning": (7, 10),  # Peak creative time
        "midday": (12, 14),  # Good for reviews/fixes
        "evening": (17, 19),  # Mechanical tasks
        "night": (22, 24),  # Deep work (optional)
    }

    TRANSITIONS = {
        10: "break - kids/life",
        14: "nap - restore",
        19: "family - dinner/bath/bedtime",
        22: "choice point - rest or code?",
    }

    def __init__(self):
        """Initialize Grace with context awareness."""
        self.context_dir = Path.home() / ".grace"
        self.context_dir.mkdir(exist_ok=True)
        self.context_file = self.context_dir / "context.json"
        self.work_log = self.context_dir / "work_log.json"

    def get_current_session(self) -> Optional[str]:
        """Determine which session we're currently in."""
        hour = datetime.now().hour
        for session_name, (start, end) in self.SESSIONS.items():
            if start <= hour < end:
                return session_name
        return None

    def get_next_transition(self) -> Tuple[int, str]:
        """Find the next transition point."""
        hour = datetime.now().hour
        for transition_hour in sorted(self.TRANSITIONS.keys()):
            if transition_hour > hour:
                return transition_hour, self.TRANSITIONS[transition_hour]
        # Next day's first transition
        first_hour = min(self.TRANSITIONS.keys())
        return first_hour, self.TRANSITIONS[first_hour]

    def save_context(self, message: str = "") -> None:
        """Save current work context for resumption later."""
        context = {
            "timestamp": datetime.now().isoformat(),
            "session": self.get_current_session(),
            "git_branch": self._get_git_branch(),
            "last_commit": self._get_last_commit(),
            "uncommitted_changes": self._has_uncommitted_changes(),
            "message": message,
        }

        with open(self.context_file, "w") as f:
            json.dump(context, f, indent=2)

    def load_context(self) -> Optional[Dict]:
        """Load the last saved context."""
        if not self.context_file.exists():
            return None
        with open(self.context_file) as f:
            return json.load(f)

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
        except subprocess.CalledProcessError:
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
        except subprocess.CalledProcessError:
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
        except subprocess.CalledProcessError:
            return False

    def _get_recent_work_hours(self, days: int = 7) -> List[float]:
        """Get work hours for recent days."""
        if not self.work_log.exists():
            return []

        with open(self.work_log) as f:
            log = json.load(f)

        cutoff = datetime.now() - timedelta(days=days)
        recent_hours = []

        for date_str, hours in log.items():
            date = datetime.fromisoformat(date_str)
            if date > cutoff:
                recent_hours.append(hours)

        return recent_hours

    def log_work_time(self, hours: float) -> None:
        """Log work hours for today."""
        log = {}
        if self.work_log.exists():
            with open(self.work_log) as f:
                log = json.load(f)

        today = datetime.now().date().isoformat()
        log[today] = log.get(today, 0) + hours

        with open(self.work_log, "w") as f:
            json.dump(log, f, indent=2)

    def check_production_status(self) -> Dict[str, str]:
        """Check production systems status."""
        status = {}

        # Check agents.ciris.ai (production)
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "-o",
                    "/dev/null",
                    "-w",
                    "%{http_code}",
                    "https://agents.ciris.ai/api/datum/v1/system/health",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            status["production"] = "UP" if result.stdout.strip() == "200" else f"DOWN ({result.stdout.strip()})"
        except Exception:
            status["production"] = "UNREACHABLE"

        # Check Datum specifically
        try:
            result = subprocess.run(
                [
                    "curl",
                    "-s",
                    "https://agents.ciris.ai/api/datum/v1/agent/status",
                    "-H",
                    "Authorization: Bearer admin:ciris_admin_password",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if "datum" in result.stdout.lower():
                status["datum"] = "RUNNING"
            else:
                status["datum"] = "CHECK NEEDED"
        except Exception:
            status["datum"] = "UNREACHABLE"

        # Check CI/CD (GitHub Actions)
        try:
            result = subprocess.run(
                ["gh", "run", "list", "--repo", "CIRISAI/CIRISAgent", "--limit", "1", "--json", "status,conclusion"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                import json

                runs = json.loads(result.stdout)
                if runs:
                    run = runs[0]
                    status["ci_cd"] = run.get("conclusion", run.get("status", "UNKNOWN")).upper()
                else:
                    status["ci_cd"] = "NO RECENT RUNS"
            else:
                status["ci_cd"] = "CHECK MANUALLY"
        except Exception:
            status["ci_cd"] = "GH CLI NOT CONFIGURED"

        # Check SonarCloud quality gate
        try:
            result = subprocess.run(
                ["python", "tools/sonar.py", "quality-gate"], capture_output=True, text=True, timeout=10
            )
            if "OK" in result.stdout:
                status["quality"] = "PASSING"
            elif "ERROR" in result.stdout:
                status["quality"] = "FAILING"
            else:
                status["quality"] = "UNKNOWN"
        except Exception:
            status["quality"] = "CHECK MANUALLY"

        # Quick type safety check using mypy toolkit
        try:
            result = subprocess.run(
                ["python", "-m", "ciris_mypy_toolkit", "check-protocols", "--quiet"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                status["type_safety"] = "✓"
            else:
                status["type_safety"] = "✗"
        except Exception:
            status["type_safety"] = "?"

        return status

    def morning(self) -> str:
        """Morning session guidance."""
        hour = datetime.now().hour
        if hour < 7:
            return "Good morning! Starting early today. Remember to pace yourself."
        elif hour > 10:
            return "Morning session has passed. Consider starting with the midday session at noon."

        message = "Good morning. Checking systems...\n\n"

        # Check production status first
        prod_status = self.check_production_status()

        message += "=== SYSTEM STATUS ===\n"
        message += f"Production: {prod_status.get('production', 'UNKNOWN')}\n"
        message += f"Datum Agent: {prod_status.get('datum', 'UNKNOWN')}\n"
        message += f"CI/CD: {prod_status.get('ci_cd', 'UNKNOWN')}\n"
        message += f"Code Quality: {prod_status.get('quality', 'UNKNOWN')}\n"
        message += "\n"

        # Prioritize based on status
        if prod_status.get("production") != "UP" or prod_status.get("datum") != "RUNNING":
            message += "🔴 PRODUCTION ISSUE DETECTED\n"
            message += "Priority: Check production immediately\n"
            message += "Command: ssh -i ~/.ssh/ciris_deploy root@108.61.119.117\n"
        elif prod_status.get("ci_cd") in ["FAILURE", "FAILED"]:
            message += "⚠️ CI/CD FAILURE\n"
            message += "Priority: Check recent PR/build failures\n"
            message += "Command: gh run list --repo CIRISAI/CIRISAgent\n"
        elif prod_status.get("quality") == "FAILING":
            message += "📊 Quality Gate Failing\n"
            message += "Priority: Address code quality issues\n"
            message += "Command: python tools/sonar.py list --severity CRITICAL\n"
        else:
            message += "✅ All systems operational\n\n"

            # Check last night's work
            context = self.load_context()
            if context:
                last_work = datetime.fromisoformat(context["timestamp"])
                if last_work.date() == datetime.now().date() - timedelta(days=1):
                    if last_work.hour >= 23:
                        message += f"You worked until {last_work.strftime('%I:%M %p')} last night.\n"
                        message += "Start gently today. Pick something satisfying but not demanding.\n\n"
                        return message

            message += "Fresh mind time - 3 hours until break.\n"
            message += "Best for: Architecture decisions, complex problem solving\n\n"
            message += "Command: claude code --continue\n"

        message += "\nStopping point: 10 AM - natural break for family"
        return message

    def resume(self) -> str:
        """Resume work after a break."""
        session = self.get_current_session()
        context = self.load_context()

        if not session:
            next_hour, next_desc = self.get_next_transition()
            return f"Not in a work session. Next session starts at {next_hour}:00."

        message = f"Welcome back. {session.capitalize()} session.\n"

        if context:
            if context.get("uncommitted_changes"):
                message += "You have uncommitted changes from earlier.\n"
                message += f"Last commit: {context.get('last_commit', 'unknown')}\n\n"

        if session == "midday":
            message += "2 hours until nap time.\n"
            message += "Best for: Completing morning's work, code review"
        elif session == "evening":
            message += "2 hours until family dinner.\n"
            message += "Energy: Post-nap clarity\n"
            message += "Best for: Mechanical tasks, documentation, test writing"

        return message

    def night(self) -> str:
        """Night session choice point."""
        # Count recent late nights
        recent_hours = self._get_recent_work_hours(3)
        late_nights = sum(1 for h in recent_hours if h > 8)

        message = "Choice point. How are you feeling?\n\n"
        message += f"Today's work: {recent_hours[-1] if recent_hours else 0:.1f} hours already logged\n"

        if late_nights >= 2:
            message += f"You've had {late_nights} long days recently.\n"
            message += "Recommendation: Rest tonight. The code will be here tomorrow.\n"
        else:
            message += "If you proceed: Pick something you WANT to explore\n"
            message += "If you rest: You've already done good work today\n"

        return message

    def status(self) -> str:
        """Current status and context."""
        session = self.get_current_session()
        next_hour, next_desc = self.get_next_transition()

        message = f"Current time: {datetime.now().strftime('%I:%M %p')}\n"

        if session:
            message += f"Session: {session}\n"
            _, end = self.SESSIONS[session]
            remaining = end - datetime.now().hour
            message += f"Time remaining: {remaining} hour(s)\n"
        else:
            message += "Not in a work session\n"

        message += f"\nNext transition: {next_hour}:00 - {next_desc}\n"

        # Git status
        message += f"\nGit branch: {self._get_git_branch()}\n"
        if self._has_uncommitted_changes():
            message += "Uncommitted changes: YES\n"

        return message

    def pause(self) -> str:
        """Pause work and save context."""
        self.save_context("Pausing for break")

        # Log approximate work time
        session = self.get_current_session()
        if session:
            start, _ = self.SESSIONS[session]
            hours_worked = (datetime.now().hour - start) + (datetime.now().minute / 60)
            self.log_work_time(hours_worked)

        return (
            "Context saved. Take your break.\n"
            "When you return, run: grace resume\n\n"
            "Your work is safely paused. Go be present."
        )

    def check_deployment(self) -> str:
        """Check if latest fixes are deployed to production."""

        message = "🔍 Deployment Status Check\n"
        message += "─" * 40 + "\n"

        # Check CI/CD status
        try:
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--limit",
                    "1",
                    "--json",
                    "status,conclusion,headSha",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ci_status = "UNKNOWN"
            ci_conclusion = ""
            if result.returncode == 0:
                runs = json.loads(result.stdout)
                if runs:
                    run = runs[0]
                    ci_status = run.get("status", "UNKNOWN")
                    ci_conclusion = run.get("conclusion", "")
                    commit = run.get("headSha", "")[:7]
                    message += f"CI/CD: {ci_status}"
                    if ci_conclusion:
                        message += f" ({ci_conclusion})"
                    message += f" [{commit}]\n"
        except Exception as e:
            message += f"CI/CD: Error checking - {e}\n"
            ci_status = "UNKNOWN"
            ci_conclusion = ""

        # Check if OAuth fix is live
        try:
            response = subprocess.run(
                ["curl", "-s", "https://agents.ciris.ai"], capture_output=True, text=True, timeout=10
            )
            if response.returncode == 0:
                if "/api/${agent.agent_id}/v1/auth/oauth/" in response.stdout:
                    message += "OAuth Fix: ✅ DEPLOYED!\n"
                    message += "\n🎉 agents.ciris.ai has the new SDK! Go test good buddy! 🎉\n"
                    message += "\nTest these:\n"
                    message += "  1. Regular login (user/pass)\n"
                    message += "  2. OAuth login (Google)\n"
                    message += "  3. OAuth login (Discord)\n"
                elif "/api/${agent.agent_id}/auth/oauth/" in response.stdout:
                    message += "OAuth Fix: ❌ Old version still running\n"
                    if ci_status == "in_progress":
                        message += "\n⏳ CI/CD still building... ETA: 10-15 min\n"
                    elif ci_conclusion == "success":
                        message += "\n🚀 Build done, deploying... ETA: 2-5 min\n"
                    else:
                        message += "\n⏰ Not yet, please keep waiting...\n"
                else:
                    message += "OAuth Fix: ❓ Cannot determine version\n"
        except Exception as e:
            message += f"OAuth Fix: Error checking - {e}\n"

        return message

    def check(self) -> str:
        """Quick production check without full morning routine."""
        message = "=== QUICK SYSTEM CHECK ===\n"

        prod_status = self.check_production_status()

        # Use symbols for quick visual scan
        symbols = {
            "UP": "✅",
            "RUNNING": "✅",
            "PASSING": "✅",
            "SUCCESS": "✅",
            "DOWN": "🔴",
            "FAILING": "🔴",
            "FAILED": "🔴",
            "FAILURE": "🔴",
            "UNREACHABLE": "⚠️",
            "CHECK NEEDED": "⚠️",
            "CHECK MANUALLY": "⚠️",
            "UNKNOWN": "❓",
            "NO RECENT RUNS": "➖",
            "GH CLI NOT CONFIGURED": "➖",
        }

        def get_symbol(status_value):
            for key, symbol in symbols.items():
                if key in status_value.upper():
                    return symbol
            return "❓"

        prod = prod_status.get("production", "UNKNOWN")
        datum = prod_status.get("datum", "UNKNOWN")
        ci = prod_status.get("ci_cd", "UNKNOWN")
        quality = prod_status.get("quality", "UNKNOWN")
        type_safety = prod_status.get("type_safety", "?")

        message += f"{get_symbol(prod)} Production: {prod}\n"
        message += f"{get_symbol(datum)} Datum: {datum}\n"
        message += f"{get_symbol(ci)} CI/CD: {ci}\n"
        message += f"{get_symbol(quality)} SonarCloud: {quality}\n"
        message += f"{type_safety} Type Safety\n"

        # Quick action if needed
        if "DOWN" in prod or "UNREACHABLE" in prod or datum not in ["RUNNING", "UP"]:
            message += "\n🔴 ACTION REQUIRED: Production issue detected!"
        elif "FAIL" in ci:
            message += "\n⚠️ CI/CD needs attention"
        elif quality == "FAILING":
            message += "\n📊 Quality gate needs attention"
        else:
            message += "\n✅ All systems operational"

        return message


def main():
    """Main entry point for grace tool."""
    grace = GraceFlow()

    if len(sys.argv) < 2:
        command = "status"
    else:
        command = sys.argv[1]

    commands = {
        "morning": grace.morning,
        "resume": grace.resume,
        "night": grace.night,
        "status": grace.status,
        "pause": grace.pause,
        "check": grace.check,  # Quick production check
        "deployment": grace.check_deployment,  # Check if latest fixes are deployed
        "deploy": grace.check_deployment,  # Alias
        "start": grace.morning,  # Alias
        "evening": grace.resume,  # Context-aware resume
    }

    if command in commands:
        print(commands[command]())
    else:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
