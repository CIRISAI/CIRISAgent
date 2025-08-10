#!/usr/bin/env python3
"""
Grace Shepherd - CI guidance specifically for Claude.

This tool helps Claude (AI assistant) properly shepherd code through CI
by enforcing good habits and preventing common mistakes.
"""

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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

    def check_ci_status(self):
        """Actually check CI status (after appropriate wait)."""
        # This would integrate with the actual CI system
        # For now, return mock status
        return {"running": True, "phase": "Testing", "tests_passed": 1089, "tests_total": 1180, "elapsed": "12:34"}

    def analyze_failure(self, failure_type: str):
        """Provide specific guidance for CI failures."""
        guidance = {
            "dict_any": """
                ❌ FAILURE: Dict[str, Any] detected

                1. Find what data this Dict contains
                2. Search for existing schema:
                   grep -r "class.*Schema.*BaseModel" --include="*.py" | grep -i [relevant_term]
                3. Common schemas you missed:
                   - AuditEventData for audit events
                   - ServiceMetrics for metrics
                   - SystemSnapshot for system state
                4. Use the existing schema. Don't create a new one.
            """,
            "mypy": """
                ❌ FAILURE: Type checking failed

                This is almost always because you:
                1. Used Dict[str, Any] somewhere
                2. Created a new schema instead of using existing one
                3. Forgot to import the proper type

                Fix: Search for and use existing schemas.
            """,
            "black": """
                ❌ FAILURE: Formatting issues

                Simple fix:
                1. Run: black .
                2. Commit the changes
                3. Push again

                But first: Did you create any new Dict[str, Any]? Fix that first.
            """,
        }

        click.secho(guidance.get(failure_type, "Unknown failure type"), fg="red")

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
        click.echo(f"Phase: {status['phase']}")
        click.echo(f"Tests: {status['tests_passed']}/{status['tests_total']}")
        click.echo(f"Elapsed: {status['elapsed']}")
        click.echo("\nCheck again in 10 minutes:")
        click.echo("  python -m tools.grace shepherd status")
    else:
        click.secho("\n✅ CI Complete!", fg="green")
        click.echo("Run: python -m tools.grace shepherd results")

    click.echo("\n" + "=" * 60)
    click.secho("Remember: Don't check again for 10 minutes!", fg="yellow")


@cli.command()
@click.argument("failure_type", required=False)
def analyze(failure_type: Optional[str] = None):
    """Analyze CI failure and provide guidance."""
    shepherd = CIShepherd()

    click.clear()
    click.secho("🌟 Grace CI Shepherd - Failure Analysis", fg="cyan", bold=True)
    click.echo("=" * 60)

    if not failure_type:
        click.echo("\n🔍 Analyzing CI logs...\n")
        # Would actually analyze logs here
        failure_type = "dict_any"  # Mock detection

    click.secho("BEFORE YOU FIX ANYTHING:", fg="red", bold=True)
    click.echo("\n1. Did you create new Dict[str, Any]? → Remove it")
    click.echo("2. Did you create a new schema? → Find the existing one")
    click.echo("3. Did you skip searching? → Go search now\n")

    shepherd.analyze_failure(failure_type)

    click.echo("\n" + "=" * 60)
    click.secho("Fix the root cause, not the symptom!", fg="yellow")


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
