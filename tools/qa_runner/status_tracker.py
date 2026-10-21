"""
QA Status Tracker

Manages the consolidated QA status file that tracks all module results.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from rich.console import Console
from rich.table import Table

# Default status file location
DEFAULT_STATUS_FILE = Path(__file__).parent.parent.parent / "qa_reports" / "qa_status.json"


def load_status(status_file: Optional[Path] = None) -> Dict:
    """Load the QA status from file."""
    path = status_file or DEFAULT_STATUS_FILE
    if not path.exists():
        return {"modules": {}, "summary": {"total_modules": 0, "passing": 0, "failing": 0, "not_run": 0}}

    with open(path) as f:
        return json.load(f)


def save_status(status: Dict, status_file: Optional[Path] = None) -> None:
    """Save the QA status to file."""
    path = status_file or DEFAULT_STATUS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)

    status["last_updated"] = datetime.now(timezone.utc).isoformat()
    _update_summary(status)

    with open(path, "w") as f:
        json.dump(status, f, indent=2)


def update_module_status(
    module_name: str,
    passed: int,
    failed: int,
    total: int,
    duration_seconds: float,
    status_file: Optional[Path] = None,
) -> None:
    """Update a single module's status after a test run."""
    status = load_status(status_file)

    # Determine status
    if total == 0:
        module_status = "not_run"
    elif failed == 0:
        module_status = "passing"
    else:
        module_status = "failing"

    # Preserve existing context if present
    existing = status["modules"].get(module_name, {})
    existing_context = existing.get("context") if isinstance(existing, dict) else None

    status["modules"][module_name] = {
        "last_run": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "failed": failed,
        "total": total,
        "status": module_status,
        "duration_seconds": round(duration_seconds, 2),
        "context": existing_context,  # Preserve context
    }

    save_status(status, status_file)


def update_module_context(
    module_name: str,
    context: str,
    bypass_warning: Optional[str] = None,
    status_file: Optional[Path] = None,
) -> None:
    """Update a module's context description and bypass warning."""
    status = load_status(status_file)

    if module_name not in status["modules"]:
        # Create minimal entry if doesn't exist
        status["modules"][module_name] = {
            "last_run": None,
            "passed": 0,
            "failed": 0,
            "total": 0,
            "status": "not_run",
            "duration_seconds": 0,
        }

    # Update context
    if isinstance(status["modules"][module_name], dict):
        status["modules"][module_name]["context"] = context
        if bypass_warning:
            status["modules"][module_name]["bypass_warning"] = bypass_warning
        elif "bypass_warning" in status["modules"][module_name]:
            del status["modules"][module_name]["bypass_warning"]

    save_status(status, status_file)


def _is_module_entry(value) -> bool:
    """Check if a value is a module entry (dict) vs a comment (string)."""
    return isinstance(value, dict) and "status" in value


def _update_summary(status: Dict) -> None:
    """Update the summary section based on module statuses."""
    modules = status.get("modules", {})

    # Filter out comment entries (strings starting with _comment)
    module_entries = {k: v for k, v in modules.items() if _is_module_entry(v)}

    passing = sum(1 for m in module_entries.values() if m.get("status") == "passing")
    failing = sum(1 for m in module_entries.values() if m.get("status") == "failing")
    not_run = sum(1 for m in module_entries.values() if m.get("status") == "not_run")

    status["summary"] = {
        "total_modules": len(module_entries),
        "passing": passing,
        "failing": failing,
        "not_run": not_run,
    }


def print_status_dashboard(status_file: Optional[Path] = None, console: Optional[Console] = None) -> None:
    """Print a formatted status dashboard to the console."""
    if console is None:
        console = Console()

    status = load_status(status_file)
    summary = status.get("summary", {})
    modules = status.get("modules", {})
    version = status.get("version", "unknown")
    last_updated = status.get("last_updated", "never")

    # Header
    console.print()
    console.print(f"[bold cyan]CIRIS QA Status Dashboard[/bold cyan] - v{version}")
    console.print(f"[dim]Last updated: {last_updated}[/dim]")
    console.print()

    # Summary
    total = summary.get("total_modules", 0)
    passing = summary.get("passing", 0)
    failing = summary.get("failing", 0)
    not_run = summary.get("not_run", 0)

    console.print(f"[bold]Summary:[/bold] {passing}/{total} passing, {failing} failing, {not_run} not run")

    if total > 0:
        pct = (passing / total) * 100
        if pct == 100:
            console.print(f"[bold green]Coverage: {pct:.0f}% COMPLETE[/bold green]")
        elif pct >= 80:
            console.print(f"[bold yellow]Coverage: {pct:.0f}%[/bold yellow]")
        else:
            console.print(f"[bold red]Coverage: {pct:.0f}%[/bold red]")

    console.print()

    # Table
    table = Table(title="Module Status", show_header=True, header_style="bold")
    table.add_column("Module", style="cyan", width=25)
    table.add_column("Status", width=10)
    table.add_column("Passed", justify="right", width=8)
    table.add_column("Failed", justify="right", width=8)
    table.add_column("Duration", justify="right", width=10)
    table.add_column("Last Run", width=20)

    # Filter out comment entries
    module_entries = {k: v for k, v in modules.items() if _is_module_entry(v)}

    # Sort modules: failing first, then passing, then not_run
    def sort_key(item):
        status = item[1].get("status", "not_run")
        if status == "failing":
            return (0, item[0])
        elif status == "passing":
            return (1, item[0])
        else:
            return (2, item[0])

    sorted_modules = sorted(module_entries.items(), key=sort_key)

    for name, data in sorted_modules:
        mod_status = data.get("status", "not_run")
        passed = data.get("passed", 0)
        failed = data.get("failed", 0)
        duration = data.get("duration_seconds", 0)
        last_run = data.get("last_run")

        # Format status with color
        if mod_status == "passing":
            status_str = "[green]PASSING[/green]"
        elif mod_status == "failing":
            status_str = "[red]FAILING[/red]"
        else:
            status_str = "[dim]NOT RUN[/dim]"

        # Format last run
        if last_run:
            try:
                dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                last_run_str = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                last_run_str = last_run[:16]
        else:
            last_run_str = "-"

        # Format duration
        duration_str = f"{duration:.1f}s" if duration > 0 else "-"

        table.add_row(
            name,
            status_str,
            str(passed) if passed > 0 else "-",
            str(failed) if failed > 0 else "-",
            duration_str,
            last_run_str,
        )

    console.print(table)
    console.print()


def get_failing_modules(status_file: Optional[Path] = None) -> list:
    """Get list of failing module names."""
    status = load_status(status_file)
    modules = status.get("modules", {})
    return [name for name, data in modules.items() if _is_module_entry(data) and data.get("status") == "failing"]


def get_not_run_modules(status_file: Optional[Path] = None) -> list:
    """Get list of modules that haven't been run."""
    status = load_status(status_file)
    modules = status.get("modules", {})
    return [name for name, data in modules.items() if _is_module_entry(data) and data.get("status") == "not_run"]
