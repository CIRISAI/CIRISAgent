#!/usr/bin/env python3
"""
Grace Shepherd - CI guidance specifically for Claude.

This tool helps Claude (AI assistant) properly shepherd code through CI
by enforcing good habits and preventing common mistakes.
"""

import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import click


class CIShepherd:
    """Guide Claude through CI with patience and wisdom."""

    # Claude's bad habits we need to prevent
    CLAUDE_ANTIPATTERNS = [
        "Creating new Dict[str, Any] instead of using existing schemas",
        "Making NewSchemaV2 when OriginalSchema already exists",
        "Checking CI status every 30 seconds (wasteful anxiety)",
        "Creating 'temporary' helper classes that duplicate existing ones",
        "Writing elaborate abstractions instead of using what's there",
    ]

    # Schemas Claude frequently reinvents
    COMMONLY_FORGOTTEN_SCHEMAS = {
        "audit": "AuditEventData - ciris_engine/schemas/services/graph/audit.py",
        "metrics": "ServiceMetrics - ciris_engine/schemas/services/telemetry.py",
        "snapshot": "SystemSnapshot - ciris_engine/schemas/runtime/system_snapshot.py",
        "queue": "ProcessingQueueItem - ciris_engine/schemas/processors/base.py",
        "channel": "ChannelContext (system) vs AdapterChannelContext (adapter)",
        "response": "ActionResponse - ciris_engine/schemas/processors/actions.py",
        "config": "ServiceConfig - ciris_engine/schemas/config/service.py",
        "thought": "ThoughtSchema - ciris_engine/schemas/thought.py",
    }

    def __init__(self):
        self.start_time = None
        self.last_check = None

    def show_waiting_screen(self, elapsed_minutes: int = 0):
        """Show the waiting screen with reminders for Claude."""
        click.clear()
        click.secho("🌟 Grace CI Shepherd", fg="cyan", bold=True)
        click.echo("=" * 60)

        if elapsed_minutes < 10:
            remaining = 10 - elapsed_minutes
            click.secho(f"\n⏰ CI is running. Check again in {remaining} minutes.\n", fg="yellow")

            click.secho("WHILE YOU WAIT - REMEMBER THESE RULES:", fg="red", bold=True)
            click.echo("\n1. 🚫 NO NEW SCHEMAS without searching first:")
            click.echo("   grep -r 'class.*YourThingHere' --include='*.py'")
            click.echo("   If it exists, USE IT.\n")

            click.echo("2. 🚫 NO Dict[str, Any] EVER:")
            click.echo("   There's ALWAYS an existing schema.")
            click.echo("   Check these common ones you forget:\n")

            for category, schema in self.COMMONLY_FORGOTTEN_SCHEMAS.items():
                click.echo(f"   • {category:10} → {schema}")

            click.echo("\n3. 🚫 NO CHECKING before 10 minutes:")
            click.echo("   CI takes 12-15 minutes. Checking won't make it faster.\n")

            click.secho("YOUR NEXT ALLOWED ACTION:", fg="green", bold=True)
            click.echo(f"In {remaining} minutes, run:")
            click.echo("  python -m tools.grace shepherd status\n")

            click.secho("WHAT TO DO NOW:", fg="cyan")
            click.echo("  Option 1: Search for existing schemas you might need")
            click.echo("  Option 2: Review the code you pushed")
            click.echo("  Option 3: Just wait. It's okay to just wait.\n")

            click.echo("=" * 60)
            click.secho(f"Time remaining: {remaining} minutes", fg="yellow")
            click.secho("Seriously Claude, stop checking. See you in 10 minutes.", fg="yellow")

        else:
            click.secho("\n✅ Okay, you can check now!\n", fg="green")
            click.echo("Run: python -m tools.grace shepherd status")

    def get_main_ci_status(self) -> Dict[str, Any]:
        """Get CI status for main branch."""
        try:
            # Get latest run on main branch
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--branch",
                    "main",
                    "--limit",
                    "1",
                    "--json",
                    "databaseId,status,conclusion,name,startedAt,headSha",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                runs = json.loads(result.stdout)
                if runs:
                    return runs[0]
        except Exception as e:
            click.echo(f"Error getting main CI status: {e}", err=True)
        return None

    def get_pr_ci_status(self, pr_number: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get CI status for PRs."""
        try:
            if pr_number:
                # Get specific PR
                result = subprocess.run(
                    ["gh", "pr", "view", str(pr_number), "--repo", "CIRISAI/CIRISAgent", "--json", "statusCheckRollup"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                # Get all open PRs
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
                        "number,title,headRefName,statusCheckRollup",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception as e:
            click.echo(f"Error getting PR CI status: {e}", err=True)
        return []

    def get_run_details(self, run_id: int) -> Dict[str, Any]:
        """Get detailed information about a specific CI run."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "view",
                    str(run_id),
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--json",
                    "status,conclusion,jobs,startedAt,updatedAt",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout:
                return json.loads(result.stdout)
        except Exception as e:
            click.echo(f"Error getting run details: {e}", err=True)
        return {}

    def check_ci_status(self):
        """Actually check CI status (after appropriate wait)."""
        # Get the current branch
        try:
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5
            )
            current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        except:
            current_branch = "unknown"

        # Get CI status for current branch
        try:
            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--branch",
                    current_branch,
                    "--limit",
                    "1",
                    "--json",
                    "databaseId,status,conclusion,name,startedAt,updatedAt",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout:
                runs = json.loads(result.stdout)
                if runs:
                    run = runs[0]
                    run_id = run.get("databaseId")

                    # Get detailed run info
                    details = self.get_run_details(run_id) if run_id else {}

                    # Find test job
                    test_job = None
                    for job in details.get("jobs", []):
                        if "Test" in job.get("name", ""):
                            test_job = job
                            break

                    # Calculate elapsed time
                    elapsed = "unknown"
                    if run.get("startedAt"):
                        start = datetime.fromisoformat(run["startedAt"].replace("Z", "+00:00"))
                        if run.get("status") == "completed" and run.get("updatedAt"):
                            end = datetime.fromisoformat(run["updatedAt"].replace("Z", "+00:00"))
                        else:
                            end = datetime.now(start.tzinfo)
                        elapsed_delta = end - start
                        elapsed = (
                            f"{int(elapsed_delta.total_seconds() // 60)}:{int(elapsed_delta.total_seconds() % 60):02d}"
                        )

                    return {
                        "running": run.get("status") != "completed",
                        "phase": test_job.get("status", "Unknown") if test_job else "Waiting",
                        "conclusion": run.get("conclusion", "pending"),
                        "run_id": run_id,
                        "branch": current_branch,
                        "elapsed": elapsed,
                        "test_job": test_job,
                    }
        except Exception as e:
            click.echo(f"Error checking CI status: {e}", err=True)

        # Fallback if something goes wrong
        return {"running": True, "phase": "Unknown", "branch": current_branch, "elapsed": "unknown"}

    def enforce_wait(self) -> bool:
        """Enforce 10-minute wait between checks."""
        if not self.last_check:
            self.last_check = datetime.now()
            return True

        elapsed = (datetime.now() - self.last_check).total_seconds() / 60
        if elapsed < 10:
            remaining = 10 - int(elapsed)
            click.secho(f"\n🛑 STOP! You checked {int(elapsed)} minutes ago.", fg="red", bold=True)
            click.secho(f"Wait {remaining} more minutes.\n", fg="red")
            click.echo("Claude, you're being impatient. CI doesn't run faster if you check more.")
            click.echo("\nWhile you wait, search for existing schemas:")
            click.echo("  grep -r 'class.*Schema.*BaseModel' --include='*.py'\n")
            return False

        self.last_check = datetime.now()
        return True

    def get_test_failures(self, run_id: int) -> Dict[str, Any]:
        """Get basic failure info from a CI run."""
        try:
            # Get job details
            result = subprocess.run(
                ["gh", "run", "view", str(run_id), "--repo", "CIRISAI/CIRISAgent", "--json", "jobs,conclusion,name"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode != 0:
                return {"error": "Could not fetch run details"}

            data = json.loads(result.stdout)
            jobs = data.get("jobs", [])

            # Find failed test job
            for job in jobs:
                if "Test" in job.get("name", "") and job.get("conclusion") == "failure":
                    return {
                        "run_id": run_id,
                        "run_name": data.get("name", "Unknown"),
                        "conclusion": data.get("conclusion", "unknown"),
                        "failed_job": job.get("name", "Test"),
                        "failed_step": next(
                            (s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"),
                            "Unknown step",
                        ),
                    }

            return {"error": "No test failures found"}

        except Exception as e:
            return {"error": str(e)}


@click.group()
def cli():
    """Grace Shepherd - Guide Claude through CI patiently."""
    pass


@cli.command()
def wait():
    """Start waiting for CI (enforces 10-minute check intervals)."""
    shepherd = CIShepherd()
    shepherd.show_waiting_screen(0)


@cli.command()
def status():
    """Check CI status (only allowed every 10 minutes)."""
    shepherd = CIShepherd()

    # Load last check time from temp file
    state_file = Path("/tmp/.grace_shepherd_state")
    if state_file.exists():
        last_check_str = state_file.read_text().strip()
        shepherd.last_check = datetime.fromisoformat(last_check_str)

    if not shepherd.enforce_wait():
        return

    # Save check time
    state_file.write_text(datetime.now().isoformat())

    # Actually check status
    status = shepherd.check_ci_status()

    click.clear()
    click.secho("🌟 Grace CI Shepherd - Status Check", fg="cyan", bold=True)
    click.echo("=" * 60)

    if status["running"]:
        click.secho(f"\n⏳ CI Still Running", fg="yellow")
        click.echo(f"Branch: {status.get('branch', 'unknown')}")
        click.echo(f"Phase: {status['phase']}")
        click.echo(f"Run ID: {status.get('run_id', 'unknown')}")
        click.echo(f"Elapsed: {status['elapsed']}")

        # Show test job details if available
        if status.get("test_job"):
            test_job = status["test_job"]
            click.echo(f"\nTest Job:")
            click.echo(f"  Status: {test_job.get('status', 'unknown')}")
            if test_job.get("steps"):
                # Count completed steps
                completed = sum(1 for s in test_job["steps"] if s.get("status") == "completed")
                total = len(test_job["steps"])
                click.echo(f"  Steps: {completed}/{total} completed")

        click.echo("\nCheck again in 10 minutes:")
        click.echo("  python -m tools.grace shepherd status")
    else:
        conclusion = status.get("conclusion", "unknown")
        if conclusion == "success":
            click.secho(f"\n✅ CI Complete - SUCCESS!", fg="green", bold=True)
        elif conclusion == "failure":
            click.secho(f"\n❌ CI Complete - FAILED", fg="red", bold=True)
            click.echo("\nRun: python -m tools.grace shepherd analyze")
        else:
            click.secho(f"\n⚠️ CI Complete - {conclusion}", fg="yellow")

        click.echo(f"\nBranch: {status.get('branch', 'unknown')}")
        click.echo(f"Run ID: {status.get('run_id', 'unknown')}")
        click.echo(f"Duration: {status['elapsed']}")

    click.echo("\n" + "=" * 60)
    click.secho("Remember: Don't check again for 10 minutes!", fg="yellow")


@cli.command()
def prs():
    """Show CI status for all open PRs on CIRISAI/CIRISAgent."""
    shepherd = CIShepherd()

    click.clear()
    click.secho("🌟 Grace CI Shepherd - PR Status", fg="cyan", bold=True)
    click.echo("=" * 60)

    prs = shepherd.get_pr_ci_status()

    if not prs:
        click.echo("\nNo open PRs found on CIRISAI/CIRISAgent.")
        return

    click.echo(f"\nFound {len(prs)} open PR(s) on CIRISAI/CIRISAgent:\n")

    for pr in prs:
        pr_num = pr.get("number", "?")
        title = pr.get("title", "Unknown")
        branch = pr.get("headRefName", "unknown")

        click.echo(f"PR #{pr_num}: {title}")
        click.echo(f"  Branch: {branch}")

        # Check status checks
        checks = pr.get("statusCheckRollup", [])
        if checks:
            passed = sum(1 for c in checks if c.get("conclusion") == "SUCCESS")
            failed = sum(1 for c in checks if c.get("conclusion") == "FAILURE")
            pending = sum(1 for c in checks if c.get("status") != "COMPLETED")

            if pending:
                click.secho(f"  Status: ⏳ {pending} checks pending", fg="yellow")
            elif failed:
                click.secho(f"  Status: ❌ {failed} checks failed", fg="red")
            else:
                click.secho(f"  Status: ✅ All {passed} checks passed", fg="green")
        else:
            click.echo("  Status: No checks")
        click.echo()


@cli.command()
@click.argument("run_id", required=False, type=int)
def analyze(run_id: Optional[int] = None):
    """Show what failed in CI."""
    shepherd = CIShepherd()

    click.clear()
    click.secho("🌟 Grace CI Shepherd - Failure Analysis", fg="cyan", bold=True)
    click.echo("=" * 60)

    # Get latest failed run if not specified
    if not run_id:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5
            )
            branch = result.stdout.strip() if result.returncode == 0 else "main"

            result = subprocess.run(
                [
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    "CIRISAI/CIRISAgent",
                    "--branch",
                    branch,
                    "--status",
                    "failure",
                    "--limit",
                    "1",
                    "--json",
                    "databaseId",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0 and result.stdout:
                runs = json.loads(result.stdout)
                if runs:
                    run_id = runs[0]["databaseId"]
                else:
                    click.secho("\n✅ No failed runs on current branch!", fg="green")
                    return
        except:
            click.secho("\n❌ Could not find failed runs", fg="red")
            return

    # Get failure info
    click.echo(f"\nChecking run {run_id}...\n")
    failure_info = shepherd.get_test_failures(run_id)

    if "error" in failure_info:
        click.secho(f"❌ {failure_info['error']}", fg="red")
    else:
        click.secho("Failed CI Run:", fg="red", bold=True)
        click.echo(f"  Run: {failure_info.get('run_name', 'Unknown')}")
        click.echo(f"  Failed Job: {failure_info.get('failed_job', 'Unknown')}")
        click.echo(f"  Failed Step: {failure_info.get('failed_step', 'Unknown')}")
        click.echo(f"\nTo see full logs:")
        click.echo(f"  gh run view {run_id} --repo CIRISAI/CIRISAgent --log-failed")

    click.echo("\n" + "=" * 60)
    click.secho("Common causes:", fg="yellow")
    click.echo("1. Dict[str, Any] - search for existing schemas instead")
    click.echo("2. Import errors - check your imports")
    click.echo("3. Test failures - run tests locally first")


@cli.command()
def remind():
    """Show reminders about schemas and patterns."""
    click.clear()
    click.secho("🌟 Grace Shepherd - Schema Reminders", fg="cyan", bold=True)
    click.echo("=" * 60)

    click.secho("\n📚 EXISTING SCHEMAS YOU KEEP FORGETTING:", fg="yellow", bold=True)

    shepherd = CIShepherd()
    for category, schema in shepherd.COMMONLY_FORGOTTEN_SCHEMAS.items():
        click.echo(f"\n{category.upper()}:")
        click.echo(f"  {schema}")

    click.secho("\n🔍 HOW TO SEARCH:", fg="green", bold=True)
    click.echo("\n# Find any schema:")
    click.echo("grep -r 'class.*Schema.*BaseModel' --include='*.py'")

    click.echo("\n# Find specific concept:")
    click.echo("grep -r 'class.*Audit' --include='*.py'")
    click.echo("grep -r 'class.*Metric' --include='*.py'")
    click.echo("grep -r 'class.*Config' --include='*.py'")

    click.secho("\n⚠️ YOUR ANTIPATTERNS:", fg="red", bold=True)
    for i, pattern in enumerate(shepherd.CLAUDE_ANTIPATTERNS, 1):
        click.echo(f"\n{i}. {pattern}")

    click.echo("\n" + "=" * 60)
    click.secho("The schema you need already exists. Find it. Use it.", fg="cyan")


if __name__ == "__main__":
    cli()
