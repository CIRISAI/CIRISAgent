"""Report rendering — console for a human, JSON for a machine.

The console view leads with the classifier gap table, because that is the
question the module exists to answer: for each way an LLM configuration can be
wrong, does CIRIS tell the user what is actually wrong?

The JSON file is ``QuirksReport.model_dump_json()``. It contains no credential
material — every recorded string was redacted at capture time in ``probes.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from .schemas import FindingKind, KeyLiveness, ProbeKind, QuirksReport, Severity

_SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "cyan",
    Severity.INFO: "dim",
}

_LIVENESS_STYLE = {
    KeyLiveness.LIVE: "green",
    KeyLiveness.NO_CREDIT: "yellow",
    KeyLiveness.EXPIRED_OR_REVOKED: "bold red",
    KeyLiveness.RATE_LIMITED: "yellow",
    KeyLiveness.OTHER: "yellow",
    KeyLiveness.MISSING: "bold red",
    KeyLiveness.NOT_PROBED: "dim",
}

_HEADLINE_KINDS = (
    FindingKind.MISLEADING_ERROR,
    FindingKind.UNCLASSIFIED_ERROR,
    FindingKind.FABRICATED_MODEL,
    FindingKind.CREDENTIAL_ECHOED,
)


def default_report_dir(base: Optional[str] = None) -> Path:
    """``qa_reports/llm_matrix/<UTC timestamp>/`` unless told otherwise."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    root = Path(base) if base else Path("qa_reports") / "llm_matrix"
    return root / stamp


def write_report(report: QuirksReport, report_dir: Path) -> Path:
    """Write ``quirks_report.json`` and return its path."""
    report_dir.mkdir(parents=True, exist_ok=True)
    target = report_dir / "quirks_report.json"
    target.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return target


def render_console(report: QuirksReport, console: Console, verbose: bool = False) -> None:
    """Print the human-facing view."""
    console.print()
    console.rule(f"[bold]LLM provider conformance matrix — {report.mode}[/bold]")

    # Credential liveness first. Every number below it is conditional on this
    # table, and a reader who skips it will misread a stale key as a defect.
    _render_key_liveness(report, console)
    _render_gap_table(report, console)
    _render_findings(report, console, verbose=verbose)
    _render_provider_summary(report, console)
    _render_footer(report, console)


def _render_key_liveness(report: QuirksReport, console: Console) -> None:
    """Which credentials work — and, separately, which need re-issuing."""
    if not report.key_statuses:
        return

    table = Table(title="Credential liveness", title_style="bold", header_style="bold")
    table.add_column("provider")
    table.add_column("key file")
    table.add_column("status")
    table.add_column("HTTP", justify="right")
    table.add_column("provider said")

    for status in report.key_statuses:
        style = _LIVENESS_STYLE[status.liveness]
        message = (status.provider_message or "").strip().replace("\n", " ")
        table.add_row(
            status.provider,
            status.key_file,
            f"[{style}]{status.liveness.value}[/{style}]",
            str(status.http_status or "—"),
            (message[:70] + "…") if len(message) > 70 else (message or "—"),
        )
    console.print(table)

    needs = report.keys_needing_reprovisioning()
    if needs:
        console.print("\n[bold red]KEYS NEEDING RE-PROVISIONING[/bold red]")
        for status in needs:
            console.print(f"  [bold]{status.provider}[/bold] — {status.key_file}")
            console.print(f"    {status.remedy}")

    # Called out separately on purpose: re-issuing one of these fixes nothing.
    no_credit = [k for k in report.key_statuses if k.liveness is KeyLiveness.NO_CREDIT]
    if no_credit:
        console.print("\n[bold yellow]VALID KEY, EMPTY ACCOUNT — do not re-issue[/bold yellow]")
        for status in no_credit:
            console.print(f"  [bold]{status.provider}[/bold] — {status.remedy}")

    skipped = [r for r in report.results if r.skipped_reason and "is not live" in r.skipped_reason]
    if skipped:
        providers = sorted({r.cell.provider for r in skipped})
        console.print(
            f"\n[dim]{len(skipped)} cell(s) skipped across {', '.join(providers)} because the credential is "
            "not live. Skipped, not failed — nothing about those providers was measured this run.[/dim]"
        )


def _render_gap_table(report: QuirksReport, console: Console) -> None:
    """The headline: true cause versus what the user is told."""
    rows = [
        r
        for r in report.results
        if r.classifier is not None and r.cell.probe is not ProbeKind.STATIC_AUDIT and r.skipped_reason is None
    ]
    if not rows:
        return

    table = Table(
        title="What went wrong  →  what CIRIS says went wrong",
        title_style="bold",
        header_style="bold",
        show_lines=False,
    )
    table.add_column("provider")
    table.add_column("injection")
    table.add_column("HTTP")
    table.add_column("true cause")
    table.add_column("rendered to user")
    table.add_column("gap", justify="center")

    for result in sorted(rows, key=lambda r: (r.cell.provider, r.cell.cell_id)):
        gapped = any(f.kind in _HEADLINE_KINDS for f in result.findings)
        marker, style = ("✗", "bold red") if gapped else ("·", "dim")
        verdict = result.classifier
        assert verdict is not None  # guarded by the filter above
        table.add_row(
            result.cell.provider,
            f"{result.cell.credential.value}/{result.cell.model_selector.value}",
            str(result.outcome.http_status or "—"),
            result.cell.expected_cause.value,
            verdict.rendered_cause.value,
            f"[{style}]{marker}[/{style}]",
        )
    console.print(table)


def _render_findings(report: QuirksReport, console: Console, verbose: bool) -> None:
    if not report.findings:
        console.print("\n[green]No findings.[/green]")
        return

    console.print(f"\n[bold]{len(report.findings)} finding(s)[/bold]")
    for finding in report.findings:
        style = _SEVERITY_STYLE[finding.severity]
        console.print(f"\n[{style}]{finding.severity.value.upper():8}[/{style}] [bold]{finding.kind.value}[/bold]")
        console.print(f"  {finding.summary}")
        console.print(f"  [dim]cell:[/dim] {finding.cell_id}")
        if finding.truth:
            console.print(f"  [dim]provider said:[/dim] {finding.truth}")
        if finding.rendered:
            console.print(f"  [dim]CIRIS says:  [/dim] {finding.rendered}")
        if verbose:
            for line in finding.detail.splitlines():
                console.print(f"  [dim]{line}[/dim]")


def _render_provider_summary(report: QuirksReport, console: Console) -> None:
    table = Table(title="Per-provider", title_style="bold", header_style="bold")
    table.add_column("provider")
    table.add_column("key", justify="center")
    table.add_column("cells", justify="right")
    table.add_column("skipped", justify="right")
    table.add_column("liveness")
    table.add_column("catalogue", justify="right")
    table.add_column("live /models", justify="right")
    table.add_column("findings")

    for summary in report.provider_summaries:
        findings = (
            ", ".join(f"{count} {sev}" for sev, count in sorted(summary.findings_by_severity.items()))
            if summary.findings_by_severity
            else "—"
        )
        table.add_row(
            summary.provider,
            "✓" if summary.key_available else "—",
            str(summary.cells_run),
            str(summary.cells_skipped),
            f"[{_LIVENESS_STYLE[summary.key_liveness]}]{summary.key_liveness.value}[/]",
            str(summary.catalogue_model_count),
            "—" if summary.live_model_count is None else str(summary.live_model_count),
            findings,
        )
    console.print()
    console.print(table)


def _render_footer(report: QuirksReport, console: Console) -> None:
    counts = report.count_by_severity()
    console.print()
    console.print(
        f"[bold]classifier gap rate:[/bold] {report.classifier_gap_rate:.0%} "
        "[dim](failure cells whose user-facing message contradicted the real cause)[/dim]"
    )
    console.print(f"[bold]live calls made:[/bold] {report.total_live_calls}   [bold]cells:[/bold] {report.total_cells}")
    if counts:
        console.print("[bold]findings:[/bold] " + ", ".join(f"{n} {sev}" for sev, n in sorted(counts.items())))


__all__ = ["default_report_dir", "render_console", "write_report"]
