"""Matrix expansion and execution.

Expansion is pure: :func:`expand_cells` turns the declarations in
``dimensions.py`` into ``MatrixCell`` objects with no I/O, so the shape of a
run can be inspected (and unit-tested) before anything is spent.

Execution runs providers concurrently and cells within a provider serially —
concurrency across providers costs nothing, concurrency within one provider
buys a rate-limit 429 that pollutes the results it was meant to speed up.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from . import analysis
from .dimensions import (
    CORE_INJECTIONS,
    DEFAULT_MAX_LIVE_CALLS,
    DEFAULT_PROVIDERS,
    PROVIDERS,
    InjectionSpec,
    ProviderSpec,
)
from .preflight import build_status, skip_reason
from .probes import FixtureExecutor, ProbeExecutor
from .product_bridge import LLMValidationRequest, get_model_capabilities, to_verdict, validate_api_key_for_provider
from .redaction import Redactor
from .schemas import (
    CellResult,
    CredentialMode,
    ExpectedCause,
    FindingKind,
    KeyLiveness,
    KeyStatus,
    LLMProbeOutcome,
    MatrixCell,
    ModelSelector,
    ProbeKind,
    ProviderSummary,
    QuirkFinding,
    QuirksReport,
    severity_rank,
)

_SLUG = re.compile(r"[^A-Za-z0-9]+")

# Stand-in credential for --dry-run. Not a secret and not a valid key at any
# provider; it exists only so the product's pre-network gate takes the same
# branch it would with a real key present.
DRY_RUN_PLACEHOLDER_KEY = "sk-dry-run-placeholder-not-a-credential"


def _slug(value: Optional[str]) -> str:
    if not value:
        return "none"
    return _SLUG.sub("-", value).strip("-").lower()


class MatrixOptions(BaseModel):
    """Everything that varies between runs."""

    providers: List[str] = Field(default_factory=lambda: list(DEFAULT_PROVIDERS))
    dry_run: bool = Field(default=True, description="Replay fixtures instead of calling providers")
    include_catalogue: bool = Field(
        default=False, description="Sweep every model in MODEL_CAPABILITIES.json — the expensive axis"
    )
    include_option_probes: bool = Field(
        default=False, description="max_tokens-over-cap and alternate-base-URL probes (these generate tokens)"
    )
    include_models_list: bool = Field(default=True, description="Query each provider's live /models listing (free)")
    max_live_calls: int = Field(default=DEFAULT_MAX_LIVE_CALLS, ge=0, description="Refuse to start above this")
    concurrency: int = Field(default=3, ge=1, le=8, description="Providers probed at once")
    report_dir: Optional[str] = Field(default=None, description="Where to write the report; None = qa_reports/…")
    preflight_only: bool = Field(
        default=False,
        description="Establish credential liveness for each provider and stop. One minimal call per provider, "
        "no grading — the cheapest possible answer to 'which of these keys still work?'",
    )

    model_config = ConfigDict(extra="forbid")


# ─────────────────────────────────────────────────────────────────────────────
# Expansion
# ─────────────────────────────────────────────────────────────────────────────


def _resolve_model(selector: ModelSelector, spec: ProviderSpec) -> Optional[str]:
    if selector is ModelSelector.CHEAP:
        return spec.cheap_model
    if selector is ModelSelector.OMITTED:
        return None
    if selector is ModelSelector.NONEXISTENT:
        return spec.nonexistent_model
    if selector is ModelSelector.WRONG_CASE:
        return spec.wrong_case_model
    if selector is ModelSelector.GATED:
        return spec.gated_model
    if selector is ModelSelector.POLICY_BLOCKED:
        return spec.policy_blocked_model
    return None


def _injection_applies(injection: InjectionSpec, spec: ProviderSpec) -> bool:
    if injection.requires is None:
        return _resolve_model(injection.model_selector, spec) is not None or (
            injection.model_selector is ModelSelector.OMITTED
        )
    return getattr(spec, injection.requires, None) is not None


def expand_cells(options: MatrixOptions) -> List[MatrixCell]:
    """Expand the declarations into concrete cells. No I/O."""
    capabilities = get_model_capabilities()
    cells: List[MatrixCell] = []

    for provider_id in options.providers:
        spec = PROVIDERS[provider_id]

        if options.include_models_list and spec.supports_models_list:
            cells.append(
                MatrixCell(
                    cell_id=f"{provider_id}/models-list/valid",
                    provider=provider_id,
                    probe=ProbeKind.MODELS_LIST,
                    credential=CredentialMode.VALID,
                    model_selector=ModelSelector.CATALOGUE,
                    requested_model=None,
                    base_url=None,
                    client_base_url=None,
                    expected_cause=ExpectedCause.SUCCESS,
                    rationale="Does the picker the user chooses from come from the provider, or from a "
                    "cached file presented as if it came from the provider?",
                    costs_tokens=False,
                )
            )

        for injection in CORE_INJECTIONS:
            if not _injection_applies(injection, spec):
                continue
            model = _resolve_model(injection.model_selector, spec)
            cells.append(
                MatrixCell(
                    cell_id=f"{provider_id}/chat/{injection.credential.value}/{injection.model_selector.value}",
                    provider=provider_id,
                    probe=ProbeKind.CHAT_MINIMAL,
                    credential=injection.credential,
                    model_selector=injection.model_selector,
                    requested_model=model,
                    base_url=spec.base_url,
                    client_base_url=None,
                    expected_cause=injection.expected_cause,
                    rationale=injection.rationale,
                )
            )

        if options.include_catalogue:
            catalogue = capabilities.get_provider_models(provider_id) or {}
            for model_id in sorted(catalogue):
                cells.append(
                    MatrixCell(
                        cell_id=f"{provider_id}/chat/valid/catalogue/{_slug(model_id)}",
                        provider=provider_id,
                        probe=ProbeKind.CHAT_MINIMAL,
                        credential=CredentialMode.VALID,
                        model_selector=ModelSelector.CATALOGUE,
                        requested_model=model_id,
                        base_url=spec.base_url,
                        client_base_url=None,
                        expected_cause=ExpectedCause.SUCCESS,
                        rationale="Every model CIRIS offers must actually answer. A catalogue entry that "
                        "cannot complete is a recommendation to fail.",
                    )
                )

        if options.include_option_probes:
            cells.append(
                MatrixCell(
                    cell_id=f"{provider_id}/chat/valid/over-cap",
                    provider=provider_id,
                    probe=ProbeKind.CHAT_MAX_TOKENS_OVER_CAP,
                    credential=CredentialMode.VALID,
                    model_selector=ModelSelector.CHEAP,
                    requested_model=spec.cheap_model,
                    base_url=spec.base_url,
                    client_base_url=None,
                    expected_cause=ExpectedCause.UNKNOWN,
                    rationale=(
                        f"Documented max_tokens cap of {spec.max_tokens_cap}: does exceeding it error?"
                        if spec.max_tokens_cap
                        else "No documented cap: does this provider accept a max_tokens its peers reject?"
                    ),
                )
            )
            if spec.advertised_base_url and spec.advertised_base_url != spec.base_url:
                cells.append(
                    MatrixCell(
                        cell_id=f"{provider_id}/chat/valid/advertised-base-url",
                        provider=provider_id,
                        probe=ProbeKind.CHAT_ALT_BASE_URL,
                        credential=CredentialMode.VALID,
                        model_selector=ModelSelector.CHEAP,
                        requested_model=spec.cheap_model,
                        base_url=spec.advertised_base_url,
                        client_base_url=spec.advertised_base_url,
                        expected_cause=ExpectedCause.UNKNOWN,
                        rationale="The wizard advertises this base URL as the provider default but validates "
                        "against a different one. Does the advertised URL work at all?",
                    )
                )

    return cells


# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────


_NO_FIXTURE = "no recorded fixture for this cell — capture one with --live --update-fixtures"


def _synthetic_preflight_cell(spec: ProviderSpec) -> MatrixCell:
    """A minimal happy-path cell, for expansions that filtered the baseline out.

    Liveness has to be established for every selected provider or the run
    cannot tell a stale credential from a provider quirk, so this is
    manufactured rather than skipped.
    """
    return MatrixCell(
        cell_id=f"{spec.provider_id}/preflight/valid/cheap",
        provider=spec.provider_id,
        probe=ProbeKind.CHAT_MINIMAL,
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.CHEAP,
        requested_model=spec.cheap_model,
        base_url=spec.base_url,
        client_base_url=None,
        expected_cause=ExpectedCause.SUCCESS,
        rationale="Credential liveness probe: one minimal completion, so a stale key is reported as a stale "
        "key rather than graded as provider behaviour.",
    )


def _is_missing_fixture(outcome: LLMProbeOutcome) -> bool:
    """A dry-run cell with nothing recorded is skipped, not graded.

    Grading it would invent findings about provider behaviour the corpus has
    never observed — the opposite of what a fixture replay is for.
    """
    return outcome.exception_type == "llm_matrix.NoFixture"


class BudgetExceeded(RuntimeError):
    """Raised before any call when the expansion is larger than the budget."""


class LLMMatrix:
    """Runs an expanded matrix and produces a :class:`QuirksReport`."""

    def __init__(self, options: MatrixOptions, fixtures: Optional[Dict[str, LLMProbeOutcome]] = None) -> None:
        self.options = options
        self.redactor = Redactor()
        self.keys: Dict[str, Optional[str]] = {}
        # Whether the key FILE exists. Tracked separately from `keys` so the
        # report tells the truth in --dry-run, where `keys` holds a placeholder.
        self.key_files_present: Dict[str, bool] = {}
        self.executor = (
            FixtureExecutor(self.redactor, fixtures or {}) if options.dry_run else ProbeExecutor(self.redactor)
        )
        self.live_model_ids: Dict[str, List[str]] = {}
        # Credential verdict per provider, established before any grading.
        self.key_statuses: Dict[str, KeyStatus] = {}

    # ── credentials ────────────────────────────────────────────────────────

    def load_keys(self) -> None:
        """Read each selected provider's key file.

        Values are registered with the redactor and held in memory only. They
        are never logged, never written to the report, and never echoed — the
        only externally visible fact is whether the file existed.
        """
        for provider_id in self.options.providers:
            spec = PROVIDERS[provider_id]
            path = Path(spec.key_file).expanduser()
            self.key_files_present[provider_id] = path.exists()
            if self.options.dry_run:
                # A non-secret placeholder, so the product's pre-network key
                # gate sees a present-but-unverified key and behaves the way it
                # would live. Using None here would make every dry-run cell
                # look like a blank-key cell.
                self.keys[provider_id] = DRY_RUN_PLACEHOLDER_KEY
                continue
            try:
                value = path.read_text(encoding="utf-8").strip()
            except OSError:
                self.keys[provider_id] = None
                continue
            self.keys[provider_id] = value or None
            self.redactor.register(value)

    def _credential_for(self, cell: MatrixCell, spec: ProviderSpec) -> Optional[str]:
        real = self.keys.get(cell.provider)
        if cell.credential is CredentialMode.VALID:
            return real
        if cell.credential is CredentialMode.INVALID:
            return spec.invalid_key
        if cell.credential is CredentialMode.ABSENT:
            return ""
        if cell.credential is CredentialMode.MALFORMED:
            return f"{real}\n" if real else None
        return real

    # ── budget ─────────────────────────────────────────────────────────────

    def estimate_live_calls(self, cells: Sequence[MatrixCell]) -> int:
        """Calls that will actually generate tokens.

        Excludes listings, static audits, and cells the product's pre-network
        key gate rejects before a socket is opened. The liveness preflight is
        counted because it is a real call — it just happens to be the baseline
        cell the sweep was already going to make.
        """
        if self.options.preflight_only:
            return len(self.options.providers)
        return sum(1 for c in cells if c.costs_tokens and c.credential is not CredentialMode.ABSENT)

    # ── run ────────────────────────────────────────────────────────────────

    async def _run_cell(self, cell: MatrixCell, spec: ProviderSpec) -> CellResult:
        api_key = self._credential_for(cell, spec)

        if not self.options.dry_run and api_key is None and cell.credential is not CredentialMode.ABSENT:
            return CellResult(
                cell=cell,
                outcome=LLMProbeOutcome(succeeded=False),
                skipped_reason=f"no credential available at {spec.key_file}",
            )

        # The product refuses some configurations before it ever opens a
        # socket (`_validate_api_key_for_provider`). Reproduce that gate here
        # so a blank-key cell is graded on the product's real behaviour and
        # costs nothing.
        request = LLMValidationRequest(
            provider=cell.provider,
            api_key=api_key or "",
            base_url=cell.client_base_url,
            model=cell.requested_model,
        )
        gate = validate_api_key_for_provider(request)
        if gate is not None:
            outcome = LLMProbeOutcome(
                succeeded=False,
                exception_type="(product pre-network gate)",
                exception_str=None,
                effective_model=cell.requested_model,
            )
            verdict = to_verdict(gate)
            result = CellResult(cell=cell, outcome=outcome, classifier=verdict)
            result.findings = analysis.grade_cell(cell, outcome, verdict, spec)
            return result

        if cell.probe is ProbeKind.MODELS_LIST:
            outcome, listing = await self.executor.run_models_list(cell, api_key or "")
            if _is_missing_fixture(outcome):
                return CellResult(cell=cell, outcome=outcome, skipped_reason=_NO_FIXTURE)
            if outcome.succeeded and not outcome.listed_model_ids_truncated:
                self.live_model_ids[cell.provider] = list(outcome.listed_model_ids)
            result = CellResult(cell=cell, outcome=outcome, listing=listing.source)
            result.findings = analysis.analyse_listing(cell, outcome, listing)
            return result

        outcome, verdict = await self.executor.run_chat(cell, spec, api_key or "")
        if _is_missing_fixture(outcome):
            return CellResult(cell=cell, outcome=outcome, skipped_reason=_NO_FIXTURE)
        echoed = cell.cell_id in self.executor.credential_echo_cells
        result = CellResult(cell=cell, outcome=outcome, classifier=verdict)
        findings: List[QuirkFinding] = analysis.grade_cell(cell, outcome, verdict, spec, credential_echoed=echoed)

        catalogue_ids = list((get_model_capabilities().get_provider_models(cell.provider) or {}).keys())
        findings.extend(analysis.fabrication_findings(cell, outcome, catalogue_ids))
        findings.extend(analysis.listed_but_unusable(cell, outcome, self.live_model_ids.get(cell.provider, [])))
        result.findings = findings
        return result

    # ── preflight ──────────────────────────────────────────────────────────

    @staticmethod
    def _baseline_cell(provider_id: str, cells: Sequence[MatrixCell]) -> Optional[MatrixCell]:
        """The valid-key/cheap-model cell, which doubles as the liveness probe."""
        return next(
            (
                c
                for c in cells
                if c.probe is ProbeKind.CHAT_MINIMAL
                and c.credential is CredentialMode.VALID
                and c.model_selector is ModelSelector.CHEAP
            ),
            None,
        )

    async def _preflight(
        self, provider_id: str, spec: ProviderSpec, cells: Sequence[MatrixCell]
    ) -> Tuple[KeyStatus, Optional[CellResult]]:
        """Establish whether this provider's credential works, before grading.

        Returns the verdict and, when a call was made, the cell result carrying
        the evidence. That result's findings are suppressed unless the key is
        live: a dead credential answering 401 to a happy-path probe is an
        operations fact, not a defect in the wizard.
        """
        if self.options.dry_run:
            return build_status(provider_id, spec.key_file, None, key_present=True), None

        if self.keys.get(provider_id) is None:
            return (
                build_status(
                    provider_id, spec.key_file, None, key_present=self.key_files_present.get(provider_id, False)
                ),
                None,
            )

        cell = self._baseline_cell(provider_id, cells)
        if cell is None:
            # Nothing in this expansion exercises the happy path (a filtered
            # run), so synthesise one. It is a single max_tokens=1 call and it
            # is counted in estimate_live_calls, so the budget stays honest.
            cell = _synthetic_preflight_cell(spec)

        outcome, verdict = await self.executor.run_chat(cell, spec, self.keys[provider_id] or "")
        status = build_status(provider_id, spec.key_file, outcome, key_present=True)

        if status.liveness is KeyLiveness.LIVE:
            result = CellResult(cell=cell, outcome=outcome, classifier=verdict)
            result.findings = analysis.grade_cell(cell, outcome, verdict, spec)
        else:
            # Recorded so the evidence is in the report, but graded as skipped.
            result = CellResult(cell=cell, outcome=outcome, classifier=verdict, skipped_reason=skip_reason(status))
        return status, result

    async def _run_provider(self, provider_id: str, cells: Sequence[MatrixCell]) -> List[CellResult]:
        spec = PROVIDERS[provider_id]
        results: List[CellResult] = []

        status, preflight_result = await self._preflight(provider_id, spec, cells)
        self.key_statuses[provider_id] = status
        probed_cell_id = preflight_result.cell.cell_id if preflight_result is not None else None
        if preflight_result is not None:
            results.append(preflight_result)

        if self.options.preflight_only:
            return results

        # Listing first: it is free and it populates live_model_ids, which the
        # LISTED_BUT_UNUSABLE check for later cells depends on.
        ordered = sorted(cells, key=lambda c: 0 if c.probe is ProbeKind.MODELS_LIST else 1)
        for cell in ordered:
            if cell.cell_id == probed_cell_id:
                continue  # already run as the preflight
            skipped = self._gate(cell, status)
            if skipped is not None:
                results.append(skipped)
                continue
            results.append(await self._run_cell(cell, spec))
        return results

    def _gate(self, cell: MatrixCell, status: KeyStatus) -> Optional[CellResult]:
        """Skip a cell the credential cannot support — with a reason, not a failure.

        Cells that inject a synthetic key (INVALID) or no key at all (ABSENT)
        are kept whatever the verdict: they test the provider and the product,
        not our account, so a stale credential of ours costs no coverage there.
        """
        if cell.credential in (CredentialMode.INVALID, CredentialMode.ABSENT):
            return None
        blocked = status.blocks_token_spend if cell.costs_tokens else status.blocks_real_key_cells
        if not blocked:
            return None
        return CellResult(
            cell=cell,
            outcome=LLMProbeOutcome(succeeded=False),
            skipped_reason=skip_reason(status),
        )

    async def run(self) -> QuirksReport:
        cells = expand_cells(self.options)
        estimated = self.estimate_live_calls(cells)
        if not self.options.dry_run and estimated > self.options.max_live_calls:
            raise BudgetExceeded(
                f"expansion needs {estimated} token-generating calls, budget is "
                f"{self.options.max_live_calls}. Raise it with --max-live-calls if that is intended."
            )

        self.load_keys()

        by_provider: Dict[str, List[MatrixCell]] = {}
        for cell in cells:
            by_provider.setdefault(cell.provider, []).append(cell)

        semaphore = asyncio.Semaphore(self.options.concurrency)

        async def guarded(provider_id: str) -> List[CellResult]:
            async with semaphore:
                return await self._run_provider(provider_id, by_provider[provider_id])

        gathered = await asyncio.gather(*(guarded(p) for p in by_provider))
        results: List[CellResult] = [r for group in gathered for r in group]

        if self.options.preflight_only:
            return self._build_report(results, [])

        # Static audits: no network, so they run in every mode including
        # --dry-run, and they are where our own tables get checked.
        results.extend(analysis.static_table_audit())

        # Catalogue reconciliation needs both sides, so it runs after the sweep.
        capabilities = get_model_capabilities()
        reconciliation: List[QuirkFinding] = []
        for provider_id in self.options.providers:
            catalogue_ids = list((capabilities.get_provider_models(provider_id) or {}).keys())
            reconciliation.extend(
                analysis.catalogue_divergence(provider_id, catalogue_ids, self.live_model_ids.get(provider_id, []))
            )

        return self._build_report(results, reconciliation)

    # ── report assembly ────────────────────────────────────────────────────

    def _build_report(self, results: List[CellResult], extra_findings: List[QuirkFinding]) -> QuirksReport:
        findings = [f for r in results for f in r.findings] + extra_findings
        findings.sort(key=lambda f: (severity_rank(f.severity), f.provider, f.cell_id))

        capabilities = get_model_capabilities()
        summaries: List[ProviderSummary] = []
        for provider_id in self.options.providers:
            provider_results = [r for r in results if r.cell.provider == provider_id]
            by_severity: Dict[str, int] = {}
            for finding in findings:
                if finding.provider == provider_id:
                    by_severity[finding.severity.value] = by_severity.get(finding.severity.value, 0) + 1
            summaries.append(
                ProviderSummary(
                    provider=provider_id,
                    cells_run=sum(1 for r in provider_results if r.skipped_reason is None),
                    cells_skipped=sum(1 for r in provider_results if r.skipped_reason is not None),
                    live_calls=sum(
                        1
                        for r in provider_results
                        if r.skipped_reason is None and r.cell.costs_tokens and not r.outcome.from_fixture
                    ),
                    findings_by_severity=by_severity,
                    catalogue_model_count=len(capabilities.get_provider_models(provider_id) or {}),
                    live_model_count=(
                        len(self.live_model_ids[provider_id]) if provider_id in self.live_model_ids else None
                    ),
                    key_available=self.key_files_present.get(provider_id, False),
                    key_liveness=(
                        self.key_statuses[provider_id].liveness
                        if provider_id in self.key_statuses
                        else KeyLiveness.NOT_PROBED
                    ),
                )
            )

        gradeable = [
            r
            for r in results
            if r.classifier is not None
            and r.skipped_reason is None
            and r.cell.expected_cause not in (ExpectedCause.SUCCESS, ExpectedCause.UNKNOWN)
            and not r.outcome.succeeded
        ]
        gapped = [
            r
            for r in gradeable
            if any(f.kind in (FindingKind.MISLEADING_ERROR, FindingKind.UNCLASSIFIED_ERROR) for f in r.findings)
        ]
        gap_rate = (len(gapped) / len(gradeable)) if gradeable else 0.0

        return QuirksReport(
            mode="dry-run" if self.options.dry_run else "live",
            providers_selected=list(self.options.providers),
            key_statuses=[self.key_statuses[p] for p in self.options.providers if p in self.key_statuses],
            total_cells=len(results),
            total_live_calls=self.executor.live_call_count,
            findings=findings,
            provider_summaries=summaries,
            results=results,
            classifier_gap_rate=round(gap_rate, 4),
        )


__all__ = ["BudgetExceeded", "LLMMatrix", "MatrixOptions", "expand_cells"]
