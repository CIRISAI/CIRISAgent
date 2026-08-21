"""Finding detection — where the matrix stops observing and starts judging.

Three families of check:

* **Gap analysis** (:func:`grade_cell`). Each cell carries an
  ``ExpectedCause`` derived from its injection — the truth, known a priori.
  The product's classifier produces a ``RenderedCause`` — what the user is
  told. Where those disagree, the user is sent to fix the wrong thing. This is
  the headline output and the defect class behind the incident that motivated
  the module.
* **Catalogue reconciliation** (:func:`analyse_listing`,
  :func:`catalogue_divergence`). Our on-device catalogue versus the provider's
  live ``/models`` versus what a request for that model actually does. Three
  sources that are supposed to agree.
* **Static table audit** (:func:`static_table_audit`). Contradictions between
  our own tables, found with no network at all — so they are caught in
  ``--dry-run`` and in CI.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set

from .dimensions import PROBE_MAX_TOKENS, PROVIDERS, ProviderSpec
from .product_bridge import (
    GOOGLE_VALIDATOR_BASE_URL,
    PROVIDER_BASE_URL_TABLE,
    ListModelsResponse,
    fabricated_model_for,
    get_llm_providers,
    get_model_capabilities,
    verify_product_constants,
)
from .schemas import (
    CellResult,
    ClassifierVerdict,
    CredentialMode,
    ExpectedCause,
    FindingKind,
    LLMProbeOutcome,
    MatrixCell,
    ModelSelector,
    ProbeKind,
    QuirkFinding,
    RenderedCause,
    Severity,
)

# The cause the classifier would have to render for the user to be pointed at
# the right remedy. An expected cause absent from this table (POLICY_BLOCKED,
# QUOTA) has NO branch in the product that can express it — every rendering is
# wrong, which is itself the finding.
_ACCEPTABLE_RENDERINGS: Dict[ExpectedCause, Set[RenderedCause]] = {
    ExpectedCause.SUCCESS: {RenderedCause.SUCCESS},
    ExpectedCause.AUTH: {RenderedCause.AUTH},
    ExpectedCause.MODEL_NOT_FOUND: {RenderedCause.MODEL_NOT_FOUND},
    ExpectedCause.MODEL_ACCESS_DENIED: {RenderedCause.AUTH, RenderedCause.MODEL_NOT_FOUND},
    ExpectedCause.ENDPOINT: {RenderedCause.ENDPOINT, RenderedCause.REFUSED, RenderedCause.TIMEOUT},
}

# HTTP statuses a provider is expected to use for each injected cause. A status
# outside the set is a provider quirk worth knowing even when our classifier
# happens to cope.
_EXPECTED_STATUSES: Dict[ExpectedCause, Set[int]] = {
    ExpectedCause.AUTH: {401, 403},
    ExpectedCause.MODEL_NOT_FOUND: {400, 404},
    ExpectedCause.MODEL_ACCESS_DENIED: {401, 402, 403, 404},
    ExpectedCause.POLICY_BLOCKED: {403, 404},
    ExpectedCause.QUOTA: {402, 429},
}

# "Check your network / check your URL" told to a user whose actual problem is
# a key, a model name, or a privacy setting is the worst outcome in the set:
# it is confidently wrong and sends them somewhere with nothing to fix.
_MISDIRECTION_TO_INFRASTRUCTURE = {RenderedCause.ENDPOINT, RenderedCause.REFUSED, RenderedCause.TIMEOUT}


def _finding(
    kind: FindingKind,
    severity: Severity,
    cell: MatrixCell,
    summary: str,
    detail: str,
    truth: Optional[str] = None,
    rendered: Optional[str] = None,
) -> QuirkFinding:
    return QuirkFinding(
        kind=kind,
        severity=severity,
        cell_id=cell.cell_id,
        provider=cell.provider,
        summary=summary,
        detail=detail,
        truth=truth,
        rendered=rendered,
    )


def _truth_line(outcome: LLMProbeOutcome) -> str:
    """One line describing what the provider actually said."""
    bits: List[str] = []
    if outcome.http_status is not None:
        bits.append(f"HTTP {outcome.http_status}")
    if outcome.exception_type:
        bits.append(outcome.exception_type)
    if outcome.provider_error_code:
        bits.append(f"code={outcome.provider_error_code}")
    if outcome.provider_error_message:
        bits.append(f'"{outcome.provider_error_message}"')
    return " | ".join(bits) if bits else "(no detail captured)"


def _bare_model_id(model_id: str) -> str:
    """Strip Google's ``models/`` namespace prefix; leave every other id alone."""
    return model_id[len("models/") :] if model_id.startswith("models/") else model_id


def _rendered_line(verdict: Optional[ClassifierVerdict]) -> str:
    if verdict is None:
        return "(not classified)"
    return f'"{verdict.message}" — {verdict.error or "(no error text)"}'


# ─────────────────────────────────────────────────────────────────────────────
# Gap analysis
# ─────────────────────────────────────────────────────────────────────────────


def grade_cell(
    cell: MatrixCell,
    outcome: LLMProbeOutcome,
    verdict: Optional[ClassifierVerdict],
    spec: Optional[ProviderSpec] = None,
    credential_echoed: bool = False,
) -> List[QuirkFinding]:
    """Compare ground truth against what the product tells the user."""
    findings: List[QuirkFinding] = []
    truth = _truth_line(outcome)
    rendered = _rendered_line(verdict)

    if credential_echoed:
        findings.append(
            _finding(
                FindingKind.CREDENTIAL_ECHOED,
                Severity.CRITICAL,
                cell,
                "API key material appeared in the error text",
                "The provider's error body or the SDK's exception rendering contained the API key. The "
                "product logs str(exception) verbatim at ERROR level in _validate_llm_connection, so this "
                "path writes a live credential into the application log. The matrix redacted the value "
                "before recording it; the log does not.",
                truth="(withheld)",
                rendered=rendered,
            )
        )

    # Transport-level failure: nothing to grade, but say so rather than
    # counting it as a classifier gap. The product's pre-network key gate also
    # has no HTTP status and is NOT a transport failure — it is the product
    # correctly refusing before it opens a socket.
    if not outcome.succeeded and outcome.http_status is None and outcome.exception_type:
        if "NoFixture" not in outcome.exception_type and not outcome.exception_type.startswith("(product"):
            findings.append(
                _finding(
                    FindingKind.TRANSPORT_ERROR,
                    Severity.LOW if cell.expected_cause is ExpectedCause.UNKNOWN else Severity.MEDIUM,
                    cell,
                    "No HTTP response — transport-level failure",
                    "The call never reached an HTTP status, so the provider's behaviour for this injection "
                    "is unknown. Re-run before treating anything in this cell as a product defect.",
                    truth=truth,
                    rendered=rendered,
                )
            )

    if cell.expected_cause is ExpectedCause.UNKNOWN:
        # Exploratory cell — still worth flagging an unclassified rendering.
        if verdict is not None and verdict.rendered_cause is RenderedCause.UNCLASSIFIED:
            findings.append(_unclassified_finding(cell, truth, rendered, verdict))
        return findings

    if cell.expected_cause is ExpectedCause.SUCCESS:
        if not outcome.succeeded:
            findings.append(
                _finding(
                    FindingKind.STATUS_ANOMALY,
                    Severity.HIGH,
                    cell,
                    "Baseline call failed — this provider's whole column is suspect",
                    "The valid-key/cheap-model happy path did not succeed. Until this passes, every other "
                    "finding for this provider may be an artefact of a stale key, an exhausted balance, or "
                    f"a decommissioned model rather than a product defect. Provider note: "
                    f"{spec.notes if spec else '(none)'}",
                    truth=truth,
                    rendered=rendered,
                )
            )
        elif outcome.completion_tokens is not None and outcome.completion_tokens > PROBE_MAX_TOKENS:
            findings.append(
                _finding(
                    FindingKind.OPTION_IGNORED,
                    Severity.LOW,
                    cell,
                    f"max_tokens={PROBE_MAX_TOKENS} ignored — {outcome.completion_tokens} tokens generated",
                    "The provider generated more completion tokens than max_tokens permitted. Harmless for "
                    "validation, but it means max_tokens is not a reliable spend ceiling at this provider.",
                    truth=truth,
                )
            )
        return findings

    # Every remaining expectation is a failure injection.
    if outcome.succeeded:
        findings.append(
            _finding(
                FindingKind.UNEXPECTED_SUCCESS,
                Severity.INFO,
                cell,
                f"Injection '{cell.model_selector.value}/{cell.credential.value}' succeeded anyway",
                "The provider accepted a call the injection expected it to reject. Usually means the "
                "account's entitlements changed, or the model id chosen for this injection is no longer "
                "gated. Update dimensions.py rather than treating it as a pass.",
                truth=truth,
            )
        )
        return findings

    if verdict is None:
        return findings

    findings.extend(_status_anomaly(cell, outcome, truth))

    if verdict.rendered_cause is RenderedCause.UNCLASSIFIED:
        findings.append(_unclassified_finding(cell, truth, rendered, verdict))
        return findings

    acceptable = _ACCEPTABLE_RENDERINGS.get(cell.expected_cause, set())
    if verdict.rendered_cause in acceptable:
        return findings

    findings.append(_misleading_finding(cell, verdict, truth, rendered))
    return findings


def _status_anomaly(cell: MatrixCell, outcome: LLMProbeOutcome, truth: str) -> List[QuirkFinding]:
    expected_statuses = _EXPECTED_STATUSES.get(cell.expected_cause)
    if not expected_statuses or outcome.http_status is None:
        return []
    if outcome.http_status in expected_statuses:
        return []
    return [
        _finding(
            FindingKind.STATUS_ANOMALY,
            Severity.MEDIUM,
            cell,
            f"HTTP {outcome.http_status} for a {cell.expected_cause.value} condition "
            f"(expected one of {sorted(expected_statuses)})",
            "This provider does not use the conventional status for this failure. Any classifier that "
            "substring-matches on the status code will mis-bucket it here while working elsewhere.",
            truth=truth,
        )
    ]


def _unclassified_finding(cell: MatrixCell, truth: str, rendered: str, verdict: ClassifierVerdict) -> QuirkFinding:
    return _finding(
        FindingKind.UNCLASSIFIED_ERROR,
        Severity.HIGH,
        cell,
        "Fell through to the raw-error branch — user sees the provider's own text",
        "No branch of _classify_llm_connection_error matched, so the user is shown 'Connection failed' "
        "plus the raw exception string. That string is provider jargon, is not localised, and in the "
        "worst case contains a URL or an id the user cannot act on.",
        truth=truth,
        rendered=rendered,
    )


def _misleading_finding(cell: MatrixCell, verdict: ClassifierVerdict, truth: str, rendered: str) -> QuirkFinding:
    misdirected_to_infra = verdict.rendered_cause in _MISDIRECTION_TO_INFRASTRUCTURE
    if cell.expected_cause is ExpectedCause.POLICY_BLOCKED:
        severity = Severity.CRITICAL
        remedy = (
            "The remedy is a PRIVACY SETTING at the provider (OpenRouter: "
            "https://openrouter.ai/settings/privacy), not anything in CIRIS. No branch of the classifier "
            "can currently express that, so the user is guaranteed to be sent somewhere useless."
        )
    elif misdirected_to_infra:
        severity = Severity.CRITICAL
        remedy = (
            "The user is told to check their endpoint or network. Their endpoint and network are fine. "
            f"The actual remedy is a {cell.expected_cause.value.replace('_', ' ')} fix."
        )
    else:
        severity = Severity.HIGH
        remedy = (
            f"The message describes a {verdict.rendered_cause.value.replace('_', ' ')} problem; the actual "
            f"problem is {cell.expected_cause.value.replace('_', ' ')}. Different remedy, same screen."
        )

    return _finding(
        FindingKind.MISLEADING_ERROR,
        severity,
        cell,
        f"True cause '{cell.expected_cause.value}' rendered to the user as '{verdict.rendered_cause.value}'",
        f"{remedy}\n\nCell rationale: {cell.rationale}",
        truth=truth,
        rendered=rendered,
    )


def fabrication_findings(
    cell: MatrixCell, outcome: LLMProbeOutcome, catalogue_ids: Sequence[str]
) -> List[QuirkFinding]:
    """Findings specific to the OMITTED-model injection."""
    if cell.model_selector is not ModelSelector.OMITTED:
        return []
    substituted = outcome.effective_model or fabricated_model_for(cell.provider)
    in_catalogue = substituted in set(catalogue_ids)
    severity = Severity.HIGH if in_catalogue else Severity.CRITICAL
    return [
        _finding(
            FindingKind.FABRICATED_MODEL,
            severity,
            cell,
            f"No model chosen → product silently sent '{substituted}' to {cell.provider}",
            "The wizard substitutes a hardcoded model when the user leaves the field empty, then reports "
            "success or failure as if the user had chosen it. "
            + (
                "The substituted id is not in this provider's catalogue at all, so validation can only "
                "fail — and the failure names a model the user never typed."
                if not in_catalogue
                else "The substituted id exists here, so validation may PASS against a model the user did "
                "not pick and will not get."
            ),
            truth=_truth_line(outcome),
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Catalogue reconciliation
# ─────────────────────────────────────────────────────────────────────────────


def analyse_listing(cell: MatrixCell, outcome: LLMProbeOutcome, listing: ListModelsResponse) -> List[QuirkFinding]:
    """Findings from a MODELS_LIST cell."""
    findings: List[QuirkFinding] = []

    if listing.source == "static":
        findings.append(
            _finding(
                FindingKind.SILENT_FALLBACK,
                Severity.HIGH,
                cell,
                "Live model query failed; user shown the cached catalogue",
                "_list_models_for_provider caught the failure and returned static data. The server-side log "
                "line for this path records no exception detail ('Live query failed, falling back to static "
                "data'), so an operator debugging it has nothing to go on — the cause survives only in the "
                "response body's error field, which a client is free to ignore.",
                truth=outcome.exception_str or "(no detail)",
                rendered=f"source={listing.source}, {listing.total_count} models shown",
            )
        )

    if listing.total_count == 0:
        findings.append(
            _finding(
                FindingKind.EMPTY_MODEL_LIST,
                Severity.HIGH,
                cell,
                "Model picker would be empty",
                "Neither the live query nor the static fallback produced a model. The user is left with a "
                "picker containing nothing and no explanation of why — the state that forces them to type a "
                "model id by hand, which is where the model-name failure modes start.",
                truth=outcome.exception_str or "(no detail)",
            )
        )

    return findings


def catalogue_divergence(provider: str, catalogue_ids: Sequence[str], live_ids: Sequence[str]) -> List[QuirkFinding]:
    """Models CIRIS offers that the provider's live listing does not contain."""
    if not live_ids:
        return []
    # Google's OpenAI-compatibility shim returns ids as "models/gemini-…" while
    # its native SDK path strips the prefix, and MODEL_CAPABILITIES.json stores
    # the bare form. Compare on the bare form so the prefix does not manufacture
    # a stale finding for every Google model at once.
    live = {_bare_model_id(m) for m in live_ids}
    catalogue_ids = [_bare_model_id(m) for m in catalogue_ids]
    findings: List[QuirkFinding] = []
    synthetic_cell = MatrixCell(
        cell_id=f"{provider}/catalogue-reconcile",
        provider=provider,
        probe=ProbeKind.MODELS_LIST,
        credential=CredentialMode.VALID,
        model_selector=ModelSelector.CATALOGUE,
        expected_cause=ExpectedCause.UNKNOWN,
        rationale="Reconcile MODEL_CAPABILITIES.json against the provider's live /models listing.",
        costs_tokens=False,
    )
    for model_id in catalogue_ids:
        if model_id not in live:
            findings.append(
                _finding(
                    FindingKind.CATALOGUE_STALE,
                    Severity.MEDIUM,
                    synthetic_cell,
                    f"MODEL_CAPABILITIES offers '{model_id}' but {provider} does not list it",
                    "The wizard will show this model as a selectable, CIRIS-annotated option. Choosing it "
                    "produces a model-not-found error that the user has no way to anticipate, because CIRIS "
                    "itself recommended it.",
                    truth=f"absent from {provider} /models ({len(live)} models listed)",
                )
            )
    return findings


def listed_but_unusable(cell: MatrixCell, outcome: LLMProbeOutcome, live_ids: Sequence[str]) -> List[QuirkFinding]:
    """A catalogue model the provider lists, then refuses to serve."""
    if cell.model_selector is not ModelSelector.CATALOGUE or outcome.succeeded:
        return []
    if not cell.requested_model or cell.requested_model not in set(live_ids):
        return []
    if outcome.http_status is None or outcome.http_status >= 500:
        return []
    return [
        _finding(
            FindingKind.LISTED_BUT_UNUSABLE,
            Severity.HIGH,
            cell,
            f"'{cell.requested_model}' is in {cell.provider}'s live /models but rejects a request",
            "The provider's own listing endpoint advertises this model and its completions endpoint refuses "
            "it. Any picker built from /models — ours included — will offer a choice that cannot work, and "
            "no amount of catalogue curation on our side fixes it.",
            truth=_truth_line(outcome),
        )
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Static table audit — no network, runs in --dry-run and in CI
# ─────────────────────────────────────────────────────────────────────────────


def static_table_audit() -> List[CellResult]:
    """Contradictions between the product's own tables.

    Returns ``CellResult`` objects (rather than bare findings) so static audits
    appear in the report alongside live cells and are counted the same way.
    """
    results: List[CellResult] = []
    capabilities = get_model_capabilities()
    wizard_providers = get_llm_providers()
    catalogue_providers = set(capabilities.providers.keys())

    def audit_cell(name: str, rationale: str, provider: str = "-") -> MatrixCell:
        return MatrixCell(
            cell_id=f"static/{name}",
            provider=provider,
            probe=ProbeKind.STATIC_AUDIT,
            credential=CredentialMode.VALID,
            model_selector=ModelSelector.CATALOGUE,
            expected_cause=ExpectedCause.UNKNOWN,
            rationale=rationale,
            costs_tokens=False,
        )

    ok_outcome = LLMProbeOutcome(succeeded=True, http_status=None, latency_ms=0.0)

    # 1. A provider the wizard offers with no catalogue entry shows an empty
    #    picker the moment its live listing fails.
    for provider in wizard_providers:
        if provider.id in ("local", "other", "mobile_local"):
            continue
        if provider.id in catalogue_providers:
            continue
        cell = audit_cell(
            f"catalogue-missing-{provider.id}",
            "Every provider in the wizard dropdown needs a MODEL_CAPABILITIES entry, or its static "
            "fallback is empty.",
            provider.id,
        )
        results.append(
            CellResult(
                cell=cell,
                outcome=ok_outcome,
                findings=[
                    _finding(
                        FindingKind.EMPTY_MODEL_LIST,
                        Severity.HIGH,
                        cell,
                        f"Wizard offers '{provider.id}' but MODEL_CAPABILITIES.json has no entry for it",
                        "_get_static_fallback_models returns [] for an unknown provider, so if the live "
                        "/models query fails for any reason the picker is empty with no explanation. Every "
                        "id in _get_llm_providers() needs a catalogue entry or an explicit exemption.",
                        truth=f"catalogue providers: {sorted(catalogue_providers)}",
                    )
                ],
            )
        )

    # 2. A provider whose key lands in OPENAI_API_KEY but which is absent from
    #    the base-URL table persists OPENAI_API_BASE="" — the OpenAI default.
    key_var_special_cases = {"anthropic", "google"}
    for provider in wizard_providers:
        if not provider.requires_api_key or provider.requires_base_url:
            continue
        if provider.id in ("openai",) or provider.id in key_var_special_cases:
            continue
        if provider.id in PROVIDER_BASE_URL_TABLE:
            continue
        cell = audit_cell(
            f"base-url-missing-{provider.id}",
            "_get_provider_base_url falls back to the OpenAI default for any id missing from the table.",
            provider.id,
        )
        results.append(
            CellResult(
                cell=cell,
                outcome=ok_outcome,
                findings=[
                    _finding(
                        FindingKind.TABLE_DIVERGENCE,
                        Severity.CRITICAL,
                        cell,
                        f"'{provider.id}' is offered by the wizard but absent from _PROVIDER_BASE_URLS",
                        'The wizard writes OPENAI_API_BASE="" for this provider, and an empty base URL is '
                        "not an error — it is the OpenAI default. The agent would send this provider's key "
                        "to api.openai.com.",
                        truth=f"table: {sorted(PROVIDER_BASE_URL_TABLE)}",
                    )
                ],
            )
        )

    # 3. The model the wizard fabricates when the user picks none.
    for provider_id in sorted(PROVIDERS):
        substituted = fabricated_model_for(provider_id)
        provider_models = capabilities.get_provider_models(provider_id) or {}
        info = provider_models.get(substituted)
        if info is not None and info.ciris_compatible:
            continue
        cell = audit_cell(
            f"fabricated-model-{provider_id}",
            "The wizard's no-model-chosen fallback must at least be a model CIRIS itself would accept.",
            provider_id,
        )
        if info is None:
            summary = f"'{substituted}' is fabricated for {provider_id} but is not in its catalogue"
            detail = (
                "With no model chosen, the wizard sends this id to the selected provider regardless of "
                "whether the provider has ever heard of it. Validation cannot succeed, and the resulting "
                "error names a model the user never typed."
            )
            severity = Severity.CRITICAL
        else:
            summary = f"'{substituted}' is fabricated for {provider_id} and is ciris_compatible=false"
            detail = (
                f"MODEL_CAPABILITIES.json rejects this model "
                f"({info.rejection_reason or 'marked incompatible'}), yet it is what the wizard probes with "
                "when the user picks nothing. A green checkmark here certifies a model CIRIS will not run."
            )
            severity = Severity.HIGH
        results.append(
            CellResult(
                cell=cell,
                outcome=ok_outcome,
                findings=[_finding(FindingKind.FABRICATED_MODEL, severity, cell, summary, detail, truth=substituted)],
            )
        )

    # 4. Google is validated against one endpoint and configured with another.
    google = next((p for p in wizard_providers if p.id == "google"), None)
    if google is not None and google.default_base_url != GOOGLE_VALIDATOR_BASE_URL:
        cell = audit_cell(
            "google-base-url-divergence",
            "The endpoint the wizard validates should be the endpoint it persists.",
            "google",
        )
        results.append(
            CellResult(
                cell=cell,
                outcome=ok_outcome,
                findings=[
                    _finding(
                        FindingKind.TABLE_DIVERGENCE,
                        Severity.MEDIUM,
                        cell,
                        "Google's advertised base URL is not the one the validator probes",
                        "_validate_google_connection hardcodes the OpenAI-compatibility shim and ignores "
                        "config.base_url entirely, while _get_llm_providers advertises the native v1beta "
                        "root as the default. A green validation therefore says nothing about the URL that "
                        "gets written to .env.",
                        truth=f"validator probes {GOOGLE_VALIDATOR_BASE_URL}",
                        rendered=f"wizard advertises {google.default_base_url}",
                    )
                ],
            )
        )

    # 5. Constants this harness duplicates from the product, drifted.
    for name, value, still_present in verify_product_constants():
        if still_present:
            continue
        cell = audit_cell(f"constant-drift-{name}", "The harness mirrors inline product constants.")
        results.append(
            CellResult(
                cell=cell,
                outcome=ok_outcome,
                findings=[
                    _finding(
                        FindingKind.TABLE_DIVERGENCE,
                        Severity.MEDIUM,
                        cell,
                        f"Harness constant {name}='{value}' no longer appears in llm_validation.py",
                        "product_bridge.py duplicates constants the product hardcodes inline. This one has "
                        "changed, so cells derived from it are testing something the product no longer does. "
                        "Update product_bridge.py.",
                    )
                ],
            )
        )

    return results


__all__ = [
    "analyse_listing",
    "catalogue_divergence",
    "fabrication_findings",
    "grade_cell",
    "listed_but_unusable",
    "static_table_audit",
]
