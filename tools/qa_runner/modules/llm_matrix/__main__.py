"""CLI for the LLM provider conformance matrix.

    # No network, no keys, no spend — replays the recorded corpus through the
    # product's live classifier. This is what CI runs.
    python3 -m tools.qa_runner.modules.llm_matrix --dry-run

    # Live core sweep across all six providers (~40 token-generating calls,
    # max_tokens=1 each). --live is required; there is no way to reach the
    # network by accident.
    python3 -m tools.qa_runner.modules.llm_matrix --live

    # One provider, verbose, with the option probes that generate tokens.
    python3 -m tools.qa_runner.modules.llm_matrix --live -p openrouter \\
        --include-option-probes --verbose

    # The expensive axis: every model in MODEL_CAPABILITIES.json (22 models).
    python3 -m tools.qa_runner.modules.llm_matrix --live --include-catalogue \\
        --max-live-calls 200

    # Which of the six keys still work? One minimal call per provider,
    # no grading. Run this first when keys may have rotated.
    python3 -m tools.qa_runner.modules.llm_matrix --preflight-only

    # Re-record the dry-run corpus from live behaviour (writes to the report
    # dir for review; never overwrites the in-tree file).
    python3 -m tools.qa_runner.modules.llm_matrix --live --update-fixtures

Exit codes: 0 = no finding above the fail threshold, 1 = findings at or above
it, 2 = the run could not be performed (budget refused, unknown provider).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from .dimensions import DEFAULT_MAX_LIVE_CALLS, DEFAULT_PROVIDERS, PROVIDERS
from .fixtures import fixtures_from_report, load_fixtures, write_fixtures
from .matrix import BudgetExceeded, LLMMatrix, MatrixOptions, expand_cells
from .product_bridge import bridge_status
from .report import default_report_dir, render_console, write_report
from .schemas import QuirksReport, Severity, severity_rank

_FAIL_LEVELS = [s.value for s in Severity]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.qa_runner.modules.llm_matrix",
        description="Live-API LLM provider conformance matrix: provider × model × credential × probe.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--live",
        action="store_true",
        help="Make real API calls. Costs real money. Without this the run is a fixture replay.",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Default. Replay recorded provider behaviour through the live classifier. No network.",
    )
    parser.add_argument(
        "-p",
        "--provider",
        action="append",
        dest="providers",
        choices=sorted(PROVIDERS),
        help="Restrict to one provider; repeatable. Default: all six.",
    )
    parser.add_argument(
        "--include-catalogue",
        action="store_true",
        help="Probe every model in MODEL_CAPABILITIES.json (22 models). The expensive axis.",
    )
    parser.add_argument(
        "--include-option-probes",
        action="store_true",
        help="Add the max_tokens-over-cap and advertised-base-URL probes. These generate tokens.",
    )
    parser.add_argument(
        "--no-models-list",
        action="store_true",
        help="Skip the live /models listing (which is free and catches catalogue drift).",
    )
    parser.add_argument(
        "--max-live-calls",
        type=int,
        default=DEFAULT_MAX_LIVE_CALLS,
        help=f"Refuse to start if the expansion exceeds this many token-generating calls (default {DEFAULT_MAX_LIVE_CALLS}).",
    )
    parser.add_argument("--concurrency", type=int, default=3, help="Providers probed at once (default 3).")
    parser.add_argument("--report-dir", default=None, help="Where to write quirks_report.json.")
    parser.add_argument(
        "--update-fixtures",
        action="store_true",
        help="Write the observed outcomes as a fixture corpus in the report dir, for review.",
    )
    parser.add_argument(
        "--fail-on",
        default="critical",
        choices=_FAIL_LEVELS + ["never"],
        help="Exit non-zero when a finding at or above this severity exists (default: critical).",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Only answer 'which of these keys still work?'. One minimal call per provider, no grading. "
        "Implies --live.",
    )
    parser.add_argument("--plan", action="store_true", help="Print the expansion and exit without running anything.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each finding's full detail.")
    return parser


def _options_from_args(args: argparse.Namespace) -> MatrixOptions:
    return MatrixOptions(
        providers=args.providers or list(DEFAULT_PROVIDERS),
        # --preflight-only is inherently a live operation: the whole point is
        # to contact the providers. Requiring --live alongside it would be
        # ceremony, since it cannot spend more than one minimal call per key.
        dry_run=not (args.live or args.preflight_only),
        include_catalogue=args.include_catalogue,
        include_option_probes=args.include_option_probes,
        include_models_list=not args.no_models_list,
        max_live_calls=args.max_live_calls,
        concurrency=args.concurrency,
        report_dir=args.report_dir,
        preflight_only=args.preflight_only,
    )


def _print_plan(options: MatrixOptions, console: Console) -> None:
    cells = expand_cells(options)
    console.print(f"[bold]{len(cells)} cells[/bold] across {len(options.providers)} provider(s)")
    costed = sum(1 for c in cells if c.costs_tokens and c.credential.value != "absent")
    console.print(f"[bold]{costed}[/bold] of them make a token-generating call\n")
    for cell in cells:
        marker = "$" if cell.costs_tokens and cell.credential.value != "absent" else " "
        console.print(f" {marker} {cell.cell_id}  [dim]expect={cell.expected_cause.value}[/dim]")


def _exit_code(report: QuirksReport, fail_on: str) -> int:
    if fail_on == "never":
        return 0
    threshold = severity_rank(Severity(fail_on))
    return 1 if any(severity_rank(f.severity) <= threshold for f in report.findings) else 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    options = _options_from_args(args)

    console.print(f"[dim]product bridge: {bridge_status()}[/dim]")

    if args.plan:
        _print_plan(options, console)
        return 0

    if options.dry_run:
        fixtures = load_fixtures()
        if not fixtures:
            console.print(
                "[yellow]No fixture corpus found — the dry run will exercise the harness and the static "
                "table audit, but has no recorded provider behaviour to re-grade. Capture one with "
                "--live --update-fixtures.[/yellow]"
            )
        matrix = LLMMatrix(options, fixtures=fixtures)
    else:
        matrix = LLMMatrix(options)

    try:
        report = asyncio.run(matrix.run())
    except BudgetExceeded as exc:
        console.print(f"[bold red]Refused to start:[/bold red] {exc}")
        return 2

    render_console(report, console, verbose=args.verbose)

    report_dir = Path(options.report_dir) if options.report_dir else default_report_dir()
    written = write_report(report, report_dir)
    console.print(f"\n[dim]report:[/dim] {written}")

    if args.update_fixtures:
        corpus_path = report_dir / "fixtures.json"
        write_fixtures(fixtures_from_report(report), corpus_path)
        console.print(f"[dim]fixtures:[/dim] {corpus_path}  [dim](review, then copy over the in-tree file)[/dim]")

    return _exit_code(report, args.fail_on)


if __name__ == "__main__":
    sys.exit(main())
