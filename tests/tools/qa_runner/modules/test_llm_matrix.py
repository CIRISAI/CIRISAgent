"""Tests for the LLM provider conformance matrix.

None of these need a network or a provider key. The live sweep is gated behind
``-m live`` and skips cleanly when the key files are absent.

The interesting tests are the ones in ``TestClassifierGapDetection``: they feed
verbatim recordings of real provider errors through the PRODUCT's own
``_classify_llm_connection_error`` and assert the matrix notices when the
user-facing message contradicts the real cause. Those recordings were captured
live on 2026-08-21; each docstring says which provider said what.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.qa_runner.modules.llm_matrix import analysis
from tools.qa_runner.modules.llm_matrix.dimensions import CORE_INJECTIONS, PROVIDERS
from tools.qa_runner.modules.llm_matrix.fixtures import FIXTURES_PATH, load_fixtures
from tools.qa_runner.modules.llm_matrix.matrix import BudgetExceeded, LLMMatrix, MatrixOptions, expand_cells
from tools.qa_runner.modules.llm_matrix.preflight import build_status, classify_liveness, skip_reason
from tools.qa_runner.modules.llm_matrix.probes import _extract_error_fields
from tools.qa_runner.modules.llm_matrix.product_bridge import (
    ReplayedProviderError,
    classifier_base_url,
    classify_connection_error,
    fabricated_model_for,
    rendered_cause_for,
    verify_product_constants,
)
from tools.qa_runner.modules.llm_matrix.redaction import MASK, Redactor
from tools.qa_runner.modules.llm_matrix.schemas import (
    CredentialMode,
    ExpectedCause,
    FindingKind,
    KeyLiveness,
    LLMProbeOutcome,
    MatrixCell,
    ModelSelector,
    ProbeKind,
    RenderedCause,
    Severity,
)

# ─────────────────────────────────────────────────────────────────────────────
# Expansion
# ─────────────────────────────────────────────────────────────────────────────


class TestExpansion:
    def test_default_expansion_covers_every_provider(self):
        cells = expand_cells(MatrixOptions())
        covered = {c.provider for c in cells}
        assert covered == set(PROVIDERS)

    def test_cell_ids_are_unique(self):
        cells = expand_cells(MatrixOptions(include_catalogue=True, include_option_probes=True))
        ids = [c.cell_id for c in cells]
        assert len(ids) == len(set(ids))

    def test_catalogue_axis_comes_from_the_shipped_catalogue(self):
        """The model axis must track MODEL_CAPABILITIES.json, not a copy of it."""
        from ciris_engine.config.model_capabilities import get_model_capabilities

        cells = expand_cells(MatrixOptions(providers=["openai"], include_catalogue=True))
        catalogue_cells = {c.requested_model for c in cells if c.model_selector is ModelSelector.CATALOGUE}
        expected = set(get_model_capabilities().get_provider_models("openai") or {})
        assert expected.issubset(catalogue_cells)

    def test_injection_requiring_an_absent_field_is_skipped(self):
        """anthropic declares no gated model, so it gets no gated cell."""
        cells = expand_cells(MatrixOptions(providers=["anthropic"]))
        assert not any(c.model_selector is ModelSelector.GATED for c in cells)

    def test_policy_blocked_cell_exists_only_where_declared(self):
        cells = expand_cells(MatrixOptions())
        providers = {c.provider for c in cells if c.model_selector is ModelSelector.POLICY_BLOCKED}
        assert providers == {"openrouter"}

    def test_listings_and_blank_key_cells_are_free(self):
        cells = expand_cells(MatrixOptions())
        for cell in cells:
            if cell.probe is ProbeKind.MODELS_LIST:
                assert not cell.costs_tokens

    def test_every_injection_declares_a_rationale(self):
        """A cell nobody can explain is a cell nobody will maintain."""
        for injection in CORE_INJECTIONS:
            assert len(injection.rationale) > 40


# ─────────────────────────────────────────────────────────────────────────────
# Budget
# ─────────────────────────────────────────────────────────────────────────────


class TestBudget:
    @pytest.mark.asyncio
    async def test_live_run_refuses_to_exceed_the_budget(self):
        options = MatrixOptions(dry_run=False, include_catalogue=True, max_live_calls=1)
        with pytest.raises(BudgetExceeded):
            await LLMMatrix(options).run()

    def test_blank_key_cells_are_not_counted_against_the_budget(self):
        """The product refuses those before it opens a socket, so they are free."""
        options = MatrixOptions(providers=["openai"])
        matrix = LLMMatrix(options)
        cells = expand_cells(options)
        absent = [c for c in cells if c.credential is CredentialMode.ABSENT]
        assert absent, "expansion should contain a blank-key cell"
        assert matrix.estimate_live_calls(cells) == sum(
            1 for c in cells if c.costs_tokens and c.credential is not CredentialMode.ABSENT
        )

    @pytest.mark.asyncio
    async def test_dry_run_makes_no_calls(self):
        report = await LLMMatrix(MatrixOptions(dry_run=True), fixtures=load_fixtures()).run()
        assert report.total_live_calls == 0
        assert report.mode == "dry-run"


# ─────────────────────────────────────────────────────────────────────────────
# Redaction
# ─────────────────────────────────────────────────────────────────────────────


class TestRedaction:
    def test_registered_secret_is_masked(self):
        redactor = Redactor()
        redactor.register("sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789")
        text = "Incorrect API key sk-or-v1-abcdefghijklmnopqrstuvwxyz0123456789 provided"
        assert "abcdefghij" not in redactor.scrub(text)
        assert MASK in redactor.scrub(text)

    @pytest.mark.parametrize(
        "token",
        [
            "sk-ant-api03-" + "a" * 40,
            "sk-or-v1-" + "b" * 40,
            "sk-proj-" + "c" * 40,
            "gsk_" + "d" * 40,
            "AIzaSy" + "e" * 34,
            "f" * 64,
        ],
    )
    def test_unregistered_token_shapes_are_masked_too(self, token):
        """A key we never loaded — echoed by a provider, or from another account."""
        redactor = Redactor()
        assert token not in redactor.scrub(f"error: {token} rejected")
        assert redactor.contains_credential(token)

    def test_bearer_header_is_masked(self):
        redactor = Redactor()
        scrubbed = redactor.scrub("Authorization: Bearer whatever-shape-this-is")
        assert "whatever-shape-this-is" not in scrubbed

    def test_account_identifier_is_masked_but_is_not_a_credential(self):
        redactor = Redactor()
        body = "{'error': {'message': 'nope'}, 'user_id': 'user_37cgII9x1owAgtieizNIpico'}"
        assert "user_37cgII9x1owAgtieizNIpico" not in redactor.scrub(body)
        assert not redactor.contains_credential(body)

    def test_short_values_are_not_registered(self):
        """A blank or tiny key must not mask unrelated text."""
        redactor = Redactor()
        redactor.register("")
        redactor.register("abc")
        assert redactor.scrub("abc def") == "abc def"

    def test_excerpt_truncates_and_scrubs(self):
        redactor = Redactor()
        redactor.register("sk-proj-" + "z" * 40)
        excerpt = redactor.excerpt("sk-proj-" + "z" * 40 + " " + "x" * 5000, limit=100)
        assert "zzzz" not in excerpt
        assert len(excerpt) < 200


# ─────────────────────────────────────────────────────────────────────────────
# Product bridge
# ─────────────────────────────────────────────────────────────────────────────


class TestProductBridge:
    def test_constants_still_match_the_product_source(self):
        """The harness mirrors constants the product hardcodes inline."""
        drifted = [name for name, _, present in verify_product_constants() if not present]
        assert not drifted, f"update product_bridge.py: {drifted}"

    def test_fabricated_model_matches_the_product_defaults(self):
        assert fabricated_model_for("openrouter") == "gpt-3.5-turbo"
        assert fabricated_model_for("together") == "gpt-3.5-turbo"
        assert fabricated_model_for("anthropic").startswith("claude-")
        assert fabricated_model_for("google").startswith("gemini-")

    def test_classifier_base_url_matches_the_product_call_sites(self):
        """Dropdown providers send no base_url, and that changes the message."""
        assert classifier_base_url("anthropic", None) == "api.anthropic.com"
        assert classifier_base_url("google", None).startswith("https://generativelanguage")
        assert classifier_base_url("openrouter", None) is None
        assert classifier_base_url("openrouter", "https://x") == "https://x"

    def test_every_classifier_branch_maps_to_a_rendered_cause(self):
        """A branch the matrix cannot name would silently grade as unclassified."""
        samples = {
            "Error code: 401 - unauthorized": RenderedCause.AUTH,
            "Error code: 404 - not_found_error model: x": RenderedCause.MODEL_NOT_FOUND,
            "Error code: 404 - Not Found": RenderedCause.ENDPOINT,
            "read timeout": RenderedCause.TIMEOUT,
            "connection refused": RenderedCause.REFUSED,
            "something nobody has seen": RenderedCause.UNCLASSIFIED,
        }
        for rendering, expected in samples.items():
            response = classify_connection_error(ReplayedProviderError(rendering), None)
            assert rendered_cause_for(response) is expected, rendering


# ─────────────────────────────────────────────────────────────────────────────
# Gap detection against real recorded provider errors
# ─────────────────────────────────────────────────────────────────────────────


def _chat_cell(provider: str, expected: ExpectedCause, selector: ModelSelector, model: str) -> MatrixCell:
    return MatrixCell(
        cell_id=f"{provider}/test/{selector.value}",
        provider=provider,
        probe=ProbeKind.CHAT_MINIMAL,
        credential=CredentialMode.VALID,
        model_selector=selector,
        requested_model=model,
        base_url=PROVIDERS[provider].base_url,
        client_base_url=None,
        expected_cause=expected,
        rationale="regression fixture for the classifier gap this module exists to measure",
    )


def _grade(provider: str, expected: ExpectedCause, selector: ModelSelector, model: str, rendering: str):
    cell = _chat_cell(provider, expected, selector, model)
    outcome = LLMProbeOutcome(
        succeeded=False,
        http_status=int(rendering.split("Error code: ")[1][:3]) if "Error code: " in rendering else None,
        exception_type="recorded",
        exception_str=rendering,
    )
    response = classify_connection_error(ReplayedProviderError(rendering), classifier_base_url(provider, None))
    from tools.qa_runner.modules.llm_matrix.product_bridge import to_verdict

    verdict = to_verdict(response)
    return verdict, analysis.grade_cell(cell, outcome, verdict, PROVIDERS[provider])


class TestClassifierGapDetection:
    def test_openrouter_routing_restriction_is_reported_as_an_endpoint_problem(self):
        """OpenRouter, 2026-08-21. The incident that motivated this module.

        A 404 whose remedy is a provider-side routing/privacy setting is
        rendered as "Could not reach the API endpoint", sending the user to
        inspect a network that is working perfectly.
        """
        rendering = (
            "Error code: 404 - {'error': {'message': \"No allowed providers are available for the "
            "selected model.\", 'code': 404}}"
        )
        verdict, findings = _grade(
            "openrouter",
            ExpectedCause.POLICY_BLOCKED,
            ModelSelector.POLICY_BLOCKED,
            "meta-llama/llama-3.3-70b-instruct",
            rendering,
        )
        assert verdict.rendered_cause is RenderedCause.ENDPOINT
        assert "Could not reach the API endpoint" in (verdict.error or "")
        misleading = [f for f in findings if f.kind is FindingKind.MISLEADING_ERROR]
        assert misleading and misleading[0].severity is Severity.CRITICAL

    def test_openai_unknown_model_is_reported_as_an_endpoint_problem(self):
        """OpenAI, 2026-08-21. The most common user error of all.

        The model-not-found branch only matches Anthropic's phrasing
        (``not_found_error`` / ``model:``). OpenAI says "The model `x` does not
        exist", matches neither, and falls into the endpoint branch.
        """
        rendering = (
            "Error code: 404 - {'error': {'message': 'The model `gpt-4o-mini-typo` does not exist or you "
            "do not have access to it.', 'type': 'invalid_request_error', 'code': 'model_not_found'}}"
        )
        verdict, findings = _grade(
            "openai", ExpectedCause.MODEL_NOT_FOUND, ModelSelector.NONEXISTENT, "gpt-4o-mini-typo", rendering
        )
        assert verdict.rendered_cause is RenderedCause.ENDPOINT
        assert any(f.kind is FindingKind.MISLEADING_ERROR for f in findings)

    def test_anthropic_model_not_found_is_the_one_case_that_works(self):
        """Anthropic, whose 404 body carries the literal ``not_found_error``."""
        rendering = (
            "Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', "
            "'message': 'model: claude-typo'}}"
        )
        verdict, findings = _grade(
            "anthropic", ExpectedCause.MODEL_NOT_FOUND, ModelSelector.NONEXISTENT, "claude-typo", rendering
        )
        assert verdict.rendered_cause is RenderedCause.MODEL_NOT_FOUND
        assert not [f for f in findings if f.kind is FindingKind.MISLEADING_ERROR]

    def test_google_invalid_key_is_unclassifiable(self):
        """Google, 2026-08-21: a bad key answers 400, not 401."""
        rendering = (
            "Error code: 400 - [{'error': {'code': 400, 'message': 'Please pass a valid API key', "
            "'status': 'INVALID_ARGUMENT'}}]"
        )
        verdict, findings = _grade("google", ExpectedCause.AUTH, ModelSelector.CHEAP, "gemini-3.6-flash", rendering)
        assert verdict.rendered_cause is RenderedCause.UNCLASSIFIED
        assert any(f.kind is FindingKind.UNCLASSIFIED_ERROR for f in findings)

    def test_anthropic_out_of_credit_answers_400_not_402(self):
        """Anthropic, 2026-08-21: billing failure arrives as a 400."""
        rendering = (
            "Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': "
            "'Your credit balance is too low to access the Anthropic API.'}}"
        )
        verdict, findings = _grade(
            "anthropic", ExpectedCause.QUOTA, ModelSelector.CHEAP, "claude-haiku-4-5-20251001", rendering
        )
        assert verdict.rendered_cause is RenderedCause.UNCLASSIFIED
        assert any(f.kind is FindingKind.STATUS_ANOMALY for f in findings)

    def test_a_correct_rendering_produces_no_gap_finding(self):
        rendering = "Error code: 401 - {'error': {'message': 'Invalid API Key'}}"
        cell = _chat_cell("groq", ExpectedCause.AUTH, ModelSelector.CHEAP, "llama-3.3-70b-versatile")
        cell = cell.model_copy(update={"credential": CredentialMode.INVALID})
        outcome = LLMProbeOutcome(succeeded=False, http_status=401, exception_str=rendering)
        from tools.qa_runner.modules.llm_matrix.product_bridge import to_verdict

        verdict = to_verdict(classify_connection_error(ReplayedProviderError(rendering), None))
        findings = analysis.grade_cell(cell, outcome, verdict, PROVIDERS["groq"])
        assert verdict.rendered_cause is RenderedCause.AUTH
        assert not findings


class TestFabricationDetection:
    def test_omitted_model_is_always_a_finding(self):
        cell = _chat_cell("openrouter", ExpectedCause.MODEL_NOT_FOUND, ModelSelector.OMITTED, None)
        outcome = LLMProbeOutcome(succeeded=True, http_status=200, effective_model="gpt-3.5-turbo")
        findings = analysis.fabrication_findings(cell, outcome, catalogue_ids=[])
        assert len(findings) == 1
        assert findings[0].kind is FindingKind.FABRICATED_MODEL
        assert findings[0].severity is Severity.CRITICAL
        assert "gpt-3.5-turbo" in findings[0].summary

    def test_a_chosen_model_is_not_a_fabrication(self):
        cell = _chat_cell("openai", ExpectedCause.SUCCESS, ModelSelector.CHEAP, "gpt-4o-mini")
        outcome = LLMProbeOutcome(succeeded=True, http_status=200, effective_model="gpt-4o-mini")
        assert analysis.fabrication_findings(cell, outcome, ["gpt-4o-mini"]) == []


class TestStaticAudit:
    """Runs with no network at all — this is what CI gets for free."""

    def test_audit_produces_results_that_carry_findings(self):
        results = analysis.static_table_audit()
        assert results
        assert any(r.findings for r in results)

    def test_fabricated_default_is_flagged_for_every_provider_that_cannot_serve_it(self):
        results = analysis.static_table_audit()
        flagged = {
            f.provider
            for r in results
            for f in r.findings
            if f.kind is FindingKind.FABRICATED_MODEL and r.cell.probe is ProbeKind.STATIC_AUDIT
        }
        # gpt-3.5-turbo is not in these providers' catalogues at all.
        assert {"openrouter", "together", "groq"}.issubset(flagged)

    def test_every_wizard_provider_has_a_catalogue_entry_or_is_flagged(self):
        from tools.qa_runner.modules.llm_matrix.product_bridge import get_llm_providers, get_model_capabilities

        catalogue = set(get_model_capabilities().providers)
        exempt = {"local", "other", "mobile_local"}
        missing = {p.id for p in get_llm_providers()} - catalogue - exempt
        flagged = {
            f.provider
            for r in analysis.static_table_audit()
            for f in r.findings
            if f.kind is FindingKind.EMPTY_MODEL_LIST
        }
        assert missing == flagged


class TestCatalogueReconciliation:
    def test_google_namespace_prefix_does_not_manufacture_findings(self):
        """Google's OpenAI shim returns ``models/x``; the catalogue stores ``x``."""
        findings = analysis.catalogue_divergence(
            "google", ["gemini-3.6-flash"], ["models/gemini-3.6-flash", "models/gemini-2.5-flash"]
        )
        assert findings == []

    def test_a_genuinely_absent_model_is_reported(self):
        findings = analysis.catalogue_divergence("openai", ["gpt-4o-mini", "gpt-ghost"], ["gpt-4o-mini"])
        assert len(findings) == 1
        assert findings[0].kind is FindingKind.CATALOGUE_STALE
        assert "gpt-ghost" in findings[0].summary

    def test_an_empty_live_list_proves_nothing(self):
        """A failed listing must not be read as 'the provider has no models'."""
        assert analysis.catalogue_divergence("openai", ["gpt-4o-mini"], []) == []


class TestErrorBodyParsing:
    @pytest.mark.parametrize(
        "body,expected_code,expected_fragment",
        [
            ({"error": {"message": "boom", "code": "model_not_found"}}, "model_not_found", "boom"),
            ({"type": "error", "error": {"type": "not_found_error", "message": "model: x"}}, "not_found_error", "x"),
            ({"error": {"code": 404, "message": "gone", "status": "NOT_FOUND"}}, "404", "gone"),
            ({"error": {"message": "credit", "code": "credit_limit"}}, "credit_limit", "credit"),
        ],
    )
    def test_provider_error_shapes(self, body, expected_code, expected_fragment):
        code, message = _extract_error_fields(body)
        assert code == expected_code
        assert expected_fragment in message

    def test_unparseable_body_is_not_an_exception(self):
        assert _extract_error_fields("<html>502 Bad Gateway</html>") == (None, None)
        assert _extract_error_fields(None) == (None, None)


class TestFixtureCorpus:
    def test_corpus_is_loadable(self):
        assert load_fixtures(), "the shipped corpus should not be empty"

    def test_corpus_carries_no_credential_material(self):
        """Belt and braces: the corpus is committed, so it gets checked here too."""
        redactor = Redactor()
        raw = FIXTURES_PATH.read_text(encoding="utf-8")
        offenders = [line for line in raw.splitlines() if redactor.contains_credential(line)]
        assert not offenders, offenders[:3]

    def test_corpus_cell_ids_all_exist_in_the_current_expansion(self):
        """A fixture for a cell that no longer exists is dead weight."""
        known = {c.cell_id for c in expand_cells(MatrixOptions(include_catalogue=True, include_option_probes=True))}
        stale = set(load_fixtures()) - known
        assert not stale, f"fixtures reference cells the matrix no longer generates: {sorted(stale)}"

    def test_corpus_entries_parse_as_typed_outcomes(self):
        """load_fixtures parses at the boundary, so a drifted corpus fails loudly."""
        for cell_id, outcome in load_fixtures().items():
            assert isinstance(outcome, LLMProbeOutcome), cell_id


class TestReportShape:
    @pytest.mark.asyncio
    async def test_report_serialises_and_round_trips(self, tmp_path: Path):
        from tools.qa_runner.modules.llm_matrix.report import write_report
        from tools.qa_runner.modules.llm_matrix.schemas import QuirksReport

        report = await LLMMatrix(MatrixOptions(dry_run=True), fixtures=load_fixtures()).run()
        written = write_report(report, tmp_path)
        reloaded = QuirksReport(**json.loads(written.read_text(encoding="utf-8")))
        assert reloaded.total_cells == report.total_cells
        assert len(reloaded.findings) == len(report.findings)

    @pytest.mark.asyncio
    async def test_gap_rate_is_a_fraction(self):
        report = await LLMMatrix(MatrixOptions(dry_run=True), fixtures=load_fixtures()).run()
        assert 0.0 <= report.classifier_gap_rate <= 1.0

    @pytest.mark.asyncio
    async def test_dry_run_report_contains_no_credential_material(self):
        report = await LLMMatrix(MatrixOptions(dry_run=True), fixtures=load_fixtures()).run()
        redactor = Redactor()
        assert not redactor.contains_credential(report.model_dump_json())


class TestCredentialLiveness:
    """A stale key must read as a stale key, never as a provider quirk.

    Every recording below was observed live on 2026-08-21 against the six key
    files in the owner's home directory.
    """

    def test_a_working_key_is_live(self):
        liveness, remedy = classify_liveness(LLMProbeOutcome(succeeded=True, http_status=200))
        assert liveness is KeyLiveness.LIVE
        assert "None" in remedy

    def test_groq_401_needs_reprovisioning(self):
        """Groq, HTTP 401 "Invalid API Key" — the key in ~/.groq_key is dead."""
        outcome = LLMProbeOutcome(succeeded=False, http_status=401, provider_error_message="Invalid API Key")
        liveness, remedy = classify_liveness(outcome)
        assert liveness is KeyLiveness.EXPIRED_OR_REVOKED
        assert "Re-issue" in remedy
        status = build_status("groq", "~/.groq_key", outcome, key_present=True)
        assert status.needs_reprovisioning is True
        assert status.blocks_real_key_cells is True

    def test_together_402_is_no_credit_not_a_dead_key(self):
        """Together, HTTP 402 code=credit_limit. Re-issuing the key fixes nothing."""
        outcome = LLMProbeOutcome(
            succeeded=False,
            http_status=402,
            provider_error_code="credit_limit",
            provider_error_message="Credit limit exceeded, please add credits.",
        )
        liveness, remedy = classify_liveness(outcome)
        assert liveness is KeyLiveness.NO_CREDIT
        assert "Do NOT re-issue" in remedy
        status = build_status("together", "~/.together_key", outcome, key_present=True)
        assert status.needs_reprovisioning is False

    def test_anthropic_signals_no_credit_with_a_400(self):
        """The ambiguity this classifier exists for.

        Anthropic reports an exhausted balance as HTTP 400, the same status
        Google uses for a REJECTED KEY. Only the message separates them, so a
        status-code-only classifier would put Anthropic on the
        re-provisioning list and waste someone's afternoon.
        """
        outcome = LLMProbeOutcome(
            succeeded=False,
            http_status=400,
            provider_error_code="invalid_request_error",
            provider_error_message="Your credit balance is too low to access the Anthropic API.",
        )
        liveness, _ = classify_liveness(outcome)
        assert liveness is KeyLiveness.NO_CREDIT
        assert build_status("anthropic", "~/.anthropic_key", outcome, key_present=True).needs_reprovisioning is False

    def test_google_signals_a_bad_key_with_the_same_400(self):
        """Same status as Anthropic's out-of-credit, opposite remedy."""
        outcome = LLMProbeOutcome(
            succeeded=False, http_status=400, provider_error_message="Please pass a valid API key"
        )
        liveness, _ = classify_liveness(outcome)
        assert liveness is KeyLiveness.EXPIRED_OR_REVOKED
        assert build_status("google", "~/.google_key", outcome, key_present=True).needs_reprovisioning is True

    def test_rate_limited_is_transient_not_reprovisionable(self):
        outcome = LLMProbeOutcome(succeeded=False, http_status=429, provider_error_message="Rate limit reached")
        liveness, remedy = classify_liveness(outcome)
        assert liveness is KeyLiveness.RATE_LIMITED
        assert "Nothing to re-provision" in remedy
        assert build_status("groq", "~/.groq_key", outcome, key_present=True).needs_reprovisioning is False

    def test_404_means_the_model_is_wrong_not_the_key(self):
        """The provider routed the request, so the credential was accepted."""
        outcome = LLMProbeOutcome(
            succeeded=False, http_status=404, provider_error_message="This model is no longer available."
        )
        status = build_status("google", "~/.google_key", outcome, key_present=True)
        assert status.liveness is KeyLiveness.OTHER
        assert status.needs_reprovisioning is False
        assert "cheap_model" in status.remedy

    def test_missing_key_file_is_reported_not_crashed(self):
        status = build_status("groq", "~/.groq_key", None, key_present=False)
        assert status.liveness is KeyLiveness.MISSING
        assert status.needs_reprovisioning is True

    def test_dry_run_reports_not_probed(self):
        status = build_status("openai", "~/.openai_key", None, key_present=True)
        assert status.liveness is KeyLiveness.NOT_PROBED
        assert status.blocks_real_key_cells is False

    def test_no_credit_blocks_spend_but_not_free_cells(self):
        """A funded-out account can still serve a free /models listing."""
        outcome = LLMProbeOutcome(succeeded=False, http_status=402, provider_error_message="Credit limit exceeded")
        status = build_status("together", "~/.together_key", outcome, key_present=True)
        assert status.blocks_token_spend is True
        assert status.blocks_real_key_cells is False

    def test_skip_reason_says_skipped_not_failed(self):
        outcome = LLMProbeOutcome(succeeded=False, http_status=401, provider_error_message="Invalid API Key")
        reason = skip_reason(build_status("groq", "~/.groq_key", outcome, key_present=True))
        assert "not live" in reason and "not failed" in reason
        assert "~/.groq_key" in reason

    def test_status_never_carries_a_key_value(self):
        outcome = LLMProbeOutcome(succeeded=False, http_status=401, provider_error_message="Invalid API Key")
        status = build_status("groq", "~/.groq_key", outcome, key_present=True)
        assert not Redactor().contains_credential(status.model_dump_json())


class TestLivenessGating:
    """Cells a dead credential cannot support are skipped, and produce no findings."""

    def _matrix_with_status(self, liveness: KeyLiveness, http_status: int):
        matrix = LLMMatrix(MatrixOptions(providers=["groq"], dry_run=False))
        outcome = LLMProbeOutcome(succeeded=False, http_status=http_status, provider_error_message="Invalid API Key")
        return matrix, build_status("groq", "~/.groq_key", outcome, key_present=True)

    def test_real_key_cells_are_skipped_for_a_dead_key(self):
        matrix, status = self._matrix_with_status(KeyLiveness.EXPIRED_OR_REVOKED, 401)
        cell = _chat_cell("groq", ExpectedCause.SUCCESS, ModelSelector.CHEAP, "llama-3.3-70b-versatile")
        skipped = matrix._gate(cell, status)
        assert skipped is not None
        assert skipped.findings == []
        assert "not live" in (skipped.skipped_reason or "")

    @pytest.mark.parametrize("credential", [CredentialMode.INVALID, CredentialMode.ABSENT])
    def test_synthetic_credential_cells_still_run(self, credential):
        """Those inject a fake key or none; our stale key is irrelevant to them."""
        matrix, status = self._matrix_with_status(KeyLiveness.EXPIRED_OR_REVOKED, 401)
        cell = _chat_cell("groq", ExpectedCause.AUTH, ModelSelector.CHEAP, "llama-3.3-70b-versatile").model_copy(
            update={"credential": credential}
        )
        assert matrix._gate(cell, status) is None

    def test_free_cells_still_run_for_an_unfunded_account(self):
        matrix = LLMMatrix(MatrixOptions(providers=["together"], dry_run=False))
        outcome = LLMProbeOutcome(succeeded=False, http_status=402, provider_error_message="Credit limit exceeded")
        status = build_status("together", "~/.together_key", outcome, key_present=True)
        listing = _chat_cell("together", ExpectedCause.SUCCESS, ModelSelector.CATALOGUE, None).model_copy(
            update={"probe": ProbeKind.MODELS_LIST, "costs_tokens": False}
        )
        assert matrix._gate(listing, status) is None

    def test_token_cells_are_skipped_for_an_unfunded_account(self):
        matrix = LLMMatrix(MatrixOptions(providers=["together"], dry_run=False))
        outcome = LLMProbeOutcome(succeeded=False, http_status=402, provider_error_message="Credit limit exceeded")
        status = build_status("together", "~/.together_key", outcome, key_present=True)
        cell = _chat_cell("together", ExpectedCause.SUCCESS, ModelSelector.CHEAP, "x")
        assert matrix._gate(cell, status) is not None

    @pytest.mark.asyncio
    async def test_preflight_only_costs_one_call_per_provider(self):
        options = MatrixOptions(providers=["openai", "groq"], dry_run=False, preflight_only=True)
        assert LLMMatrix(options).estimate_live_calls([]) == 2


class TestRunnerModule:
    @pytest.mark.asyncio
    async def test_module_defaults_to_dry_run(self, tmp_path: Path):
        """A module that spends money on its default invocation is a trap."""
        from tools.qa_runner.modules.llm_matrix_tests import LLMMatrixTests

        tests = LLMMatrixTests(report_dir=tmp_path)
        assert tests.options.dry_run is True
        results = await tests.run()
        assert results
        assert all({"test", "status"} <= set(r) for r in results)

    @pytest.mark.asyncio
    async def test_reprovisioning_list_is_empty_before_a_run(self, tmp_path: Path):
        from tools.qa_runner.modules.llm_matrix_tests import LLMMatrixTests

        assert LLMMatrixTests(report_dir=tmp_path).keys_needing_reprovisioning == []

    @pytest.mark.asyncio
    async def test_a_dead_key_does_not_fail_the_module(self, tmp_path: Path):
        """The owner expects to re-provision keys; that must not fail the suite."""
        from tools.qa_runner.modules.llm_matrix_tests import LLMMatrixTests

        tests = LLMMatrixTests(report_dir=tmp_path)
        results = await tests.run()
        columns = [r for r in results if r["test"].startswith("provider_column_")]
        assert columns
        assert all("PASS" in r["status"] for r in columns)

    def test_module_declares_no_ciris_server(self):
        from tools.qa_runner.modules.llm_matrix_tests import LLMMatrixTests

        assert LLMMatrixTests.REQUIRES_CIRIS_SERVER is False
        assert LLMMatrixTests.WIPE_DATA_ON_START is False


# ─────────────────────────────────────────────────────────────────────────────
# Live sweep — opt-in, skipped without keys
# ─────────────────────────────────────────────────────────────────────────────


def _has_key(provider: str) -> bool:
    return Path(PROVIDERS[provider].key_file).expanduser().exists()


@pytest.mark.live
class TestLiveSweep:
    @pytest.mark.asyncio
    @pytest.mark.skipif(not _has_key("openai"), reason="requires ~/.openai_key")
    @pytest.mark.skipif(
        os.environ.get("CIRIS_QA_ALLOW_LIVE_LLM_MATRIX") != "1",
        reason="live LLM calls cost money; set CIRIS_QA_ALLOW_LIVE_LLM_MATRIX=1 to opt in",
    )
    async def test_openai_baseline_answers(self):
        options = MatrixOptions(providers=["openai"], dry_run=False, include_models_list=False, max_live_calls=10)
        report = await LLMMatrix(options).run()
        baseline = next(
            r
            for r in report.results
            if r.cell.model_selector is ModelSelector.CHEAP and r.cell.credential is CredentialMode.VALID
        )
        assert baseline.outcome.succeeded, baseline.outcome.provider_error_message
