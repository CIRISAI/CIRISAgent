"""QA-runner face of the LLM provider conformance matrix.

The matrix itself lives in ``tools/qa_runner/modules/llm_matrix/`` and is fully
usable standalone::

    python3 -m tools.qa_runner.modules.llm_matrix --dry-run
    python3 -m tools.qa_runner.modules.llm_matrix --live

This file adapts it to the runner's module contract — ``Tests(client, console)``
plus ``await run()`` returning ``[{"test":…, "status":…, "error":…}]`` — so it
can be selected as ``python3 -m tools.qa_runner llm_matrix`` once the three
registration lines below are added. They are NOT added here: registration means
editing ``config.py``, ``runner.py`` and ``_module_metadata.py``, and a parallel
effort is refactoring the code under test.

To wire it up:

1. ``tools/qa_runner/config.py`` — add to ``QAModule``::

       LLM_MATRIX = "llm_matrix"  # Live LLM provider conformance matrix

   and a branch in ``get_module_tests`` returning ``[]`` (SDK-style module,
   handled by the runner). Do NOT add it to ``ALL_MODULE_SEQUENCE``: it makes
   live calls that cost money and needs six provider keys, which puts it in
   the same exclusion class as ``billing_integration``.

2. ``tools/qa_runner/modules/_module_metadata.py`` — add to ``_REGISTRY``::

       QAModule.LLM_MATRIX: ("tools.qa_runner.modules.llm_matrix_tests", "LLMMatrixTests"),

3. ``tools/qa_runner/runner.py`` — add ``QAModule.LLM_MATRIX`` to the
   no-server set near line 505 and to the SDK class map near line 1584.

Default posture when run through the runner is ``--dry-run``: a module that
spends money the moment someone types its name is a module that gets run by
accident. Live mode is opt-in via ``live=True``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from .llm_matrix import LLMMatrix, MatrixOptions
from .llm_matrix.dimensions import DEFAULT_MAX_LIVE_CALLS, DEFAULT_PROVIDERS
from .llm_matrix.fixtures import load_fixtures
from .llm_matrix.report import default_report_dir, render_console, write_report
from .llm_matrix.schemas import FindingKind, KeyLiveness, KeyStatus, QuirksReport, Severity, severity_rank

# ──────────────────────────────────────────────────────────────────────
# Module-metadata contract per tools/qa_runner/modules/_module_metadata.py.
#
# The matrix talks to LLM providers directly. There is no CIRIS agent in the
# loop, nothing to wake, and no database to wipe — the code under test is the
# setup wizard's validation helpers, imported and called in-process.
# ──────────────────────────────────────────────────────────────────────
REQUIRES_LIVE_LLM = False
LIVE_LLM_DEFAULTS: Dict[str, str] = {}
SERVER_ENV: Dict[str, str] = {}
WIPE_DATA_ON_START = False
REQUIRES_CIRIS_SERVER = False


class LLMMatrixTests:
    """Sweep provider × model × credential × probe and report the quirks.

    One runner "test" per finding severity band plus one per provider column,
    so a failure in the runner's summary names the thing that broke rather
    than just saying the module failed.
    """

    REQUIRES_LIVE_LLM = REQUIRES_LIVE_LLM
    LIVE_LLM_DEFAULTS = LIVE_LLM_DEFAULTS
    SERVER_ENV = SERVER_ENV
    WIPE_DATA_ON_START = WIPE_DATA_ON_START
    REQUIRES_CIRIS_SERVER = REQUIRES_CIRIS_SERVER

    def __init__(
        self,
        client: Any = None,
        console: Optional[Console] = None,
        live: bool = False,
        providers: Optional[List[str]] = None,
        include_catalogue: bool = False,
        include_option_probes: bool = False,
        max_live_calls: int = DEFAULT_MAX_LIVE_CALLS,
        preflight_only: bool = False,
        report_dir: Optional[Path] = None,
        fail_on: Severity = Severity.CRITICAL,
        api_port: int = 8080,  # ignored; kept for runner ctor compatibility
    ) -> None:
        self.client = client  # unused: no CIRIS agent in this module's loop
        self.console = console or Console()
        self.options = MatrixOptions(
            providers=providers or list(DEFAULT_PROVIDERS),
            dry_run=not live,
            include_catalogue=include_catalogue,
            include_option_probes=include_option_probes,
            include_models_list=True,
            max_live_calls=max_live_calls,
            preflight_only=preflight_only,
        )
        self.report_dir = report_dir or default_report_dir()
        self.fail_on = fail_on
        self.report: Optional[QuirksReport] = None
        self.results: List[Dict[str, Any]] = []

    async def run(self) -> List[Dict[str, Any]]:
        """Run the matrix and translate its findings into runner results."""
        fixtures = load_fixtures() if self.options.dry_run else {}
        matrix = LLMMatrix(self.options, fixtures=fixtures)
        self.report = await matrix.run()

        render_console(self.report, self.console)
        written = write_report(self.report, self.report_dir)
        self.console.print(f"[dim]report: {written}[/dim]")

        self._record_findings()
        self._record_columns()
        return self.results

    # ── result translation ─────────────────────────────────────────────

    def _record(self, test: str, passed: bool, error: Optional[str] = None) -> None:
        self.results.append({"test": test, "status": "✅ PASS" if passed else "❌ FAIL", "error": error})

    def _record_findings(self) -> None:
        """One result per finding kind, failing at or above ``fail_on``."""
        assert self.report is not None
        threshold = severity_rank(self.fail_on)
        by_kind: Dict[FindingKind, List[str]] = {}
        for finding in self.report.findings:
            by_kind.setdefault(finding.kind, []).append(f"{finding.cell_id}: {finding.summary}")

        for kind in FindingKind:
            hits = by_kind.get(kind, [])
            if not hits:
                continue
            worst = min(
                (severity_rank(f.severity) for f in self.report.findings if f.kind is kind),
                default=len(Severity),
            )
            passed = worst > threshold
            self._record(
                f"no_{kind.value}",
                passed,
                None if passed else f"{len(hits)} occurrence(s); first: {hits[0]}",
            )

    def _record_columns(self) -> None:
        """One result per provider: was its column measurable, and did it hold?

        A provider whose credential is not live is recorded as PASS. That is
        deliberate: a stale key is an operations fact about our account, not a
        defect in the wizard, and failing the suite for it trains people to
        ignore the suite. The credential verdict and the remedy go to the
        console and to ``report.key_statuses`` instead, where they are
        actionable.
        """
        assert self.report is not None
        for summary in self.report.provider_summaries:
            provider = summary.provider
            if summary.key_liveness not in (KeyLiveness.LIVE, KeyLiveness.NOT_PROBED):
                self._record(f"provider_column_{provider}", True, None)
                continue

            baseline = next(
                (
                    r
                    for r in self.report.results
                    if r.cell.provider == provider
                    and r.cell.model_selector.value == "cheap"
                    and r.cell.credential.value == "valid"
                ),
                None,
            )
            if baseline is None or baseline.skipped_reason is not None:
                self._record(f"provider_column_{provider}", True, None)
                continue
            self._record(
                f"provider_column_{provider}",
                baseline.outcome.succeeded,
                (
                    None
                    if baseline.outcome.succeeded
                    else f"HTTP {baseline.outcome.http_status}: {baseline.outcome.provider_error_message}"
                ),
            )

    @property
    def keys_needing_reprovisioning(self) -> List[KeyStatus]:
        """Credentials a human must re-issue. Empty before ``run()``.

        Excludes valid-but-unfunded accounts by construction — re-issuing one
        of those fixes nothing, and putting it on this list sends someone to do
        the wrong work.
        """
        return self.report.keys_needing_reprovisioning() if self.report else []


def main() -> int:
    """Convenience entry point mirroring the package CLI's dry-run default."""
    tests = LLMMatrixTests()
    asyncio.run(tests.run())
    return 0


__all__ = ["LLMMatrixTests"]
