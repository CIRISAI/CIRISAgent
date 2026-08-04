"""Tests for the research-bound prompt override facility.

Four things are under test, in the order the FSD argues them:

1. **Gate off => unreachable, and it says so.** Including the source-level
   assertion (in the shape of ``test_attestation_refresh.py:602``) that the
   anchor alone can never open the gate — because ``tests/conftest.py`` sets
   ``CIRIS_TESTING_MODE=true`` for the whole suite.
2. **Gate on => applied**, at every one of the five interception points.
3. **Unresolvable key => hard error**, never a skip. Partial application that
   reports clean is the exact failure shape this facility exists to prevent.
4. **Drift guard**: the declared override key space still matches the real
   prompt surface, so the loader cannot silently stop covering a field that
   moved.
"""

import inspect
import json

import pytest

from ciris_engine.logic.utils import research_overrides as ro
from ciris_engine.logic.utils.research_overrides import (
    ENV_ANCHOR,
    ENV_MANIFEST,
    ResearchOverrideError,
    ResearchOverrideRefused,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_override_state():
    """Every test starts and ends with no override state.

    Not optional: an active manifest makes ``get_string`` raise on a missing key
    process-wide, so a leaked manifest would fail unrelated tests in confusing
    ways.
    """
    ro.reset_research_overrides()
    yield
    ro.reset_research_overrides()


def _valid_manifest(tmp_path, **overrides):
    """A minimal *additive* manifest that passes every rule."""
    manifest = {
        "manifest_version": "1",
        "experiment_id": "test-experiment",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {"string": {}, "dma_prompt": {}, "conscience_prompt": {}, "corpus": {}, "template": {}},
        "research_hashes": {},
    }
    for namespace, entries in overrides.items():
        manifest["overrides"][namespace] = entries
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def _write_raw(tmp_path, payload):
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _activate(monkeypatch, path):
    monkeypatch.setenv(ENV_MANIFEST, str(path))
    monkeypatch.setenv(ENV_ANCHOR, "true")
    ro.reset_research_overrides()


# ---------------------------------------------------------------------------
# 1. Gate off
# ---------------------------------------------------------------------------


class TestGateOff:
    def test_no_manifest_env_means_the_feature_does_not_exist(self, monkeypatch):
        monkeypatch.delenv(ENV_MANIFEST, raising=False)
        # The anchor IS set by tests/conftest.py. That must not be enough.
        monkeypatch.setenv(ENV_ANCHOR, "true")
        ro.reset_research_overrides()

        assert ro.get_active_overrides() is None
        assert ro.overrides_are_active() is False
        assert ro.override_string("prompts.language_guidance") is None
        assert ro.override_corpus("accord.localized") is None
        assert ro.describe_coverage() == "research overrides inactive"

    def test_anchor_alone_never_opens_the_gate(self, monkeypatch):
        """The known tension in FSD §2.3, asserted rather than trusted.

        The whole unit-test suite runs with ``CIRIS_TESTING_MODE=true``. That is
        safe only because the anchor alone does nothing. If a future refactor
        inverts the two keys — makes the manifest path the anchor and testing
        mode the selector — every pytest run silently becomes a research run.
        """
        monkeypatch.delenv(ENV_MANIFEST, raising=False)
        for spelling in ("true", "1", "yes", "on", "TRUE"):
            monkeypatch.setenv(ENV_ANCHOR, spelling)
            ro.reset_research_overrides()
            assert ro.get_active_overrides() is None, f"anchor={spelling!r} opened the gate on its own"

    def test_manifest_without_anchor_refuses_and_names_both_remedies(self, monkeypatch, tmp_path):
        path = _valid_manifest(tmp_path)
        monkeypatch.setenv(ENV_MANIFEST, str(path))
        monkeypatch.delenv(ENV_ANCHOR, raising=False)
        ro.reset_research_overrides()

        with pytest.raises(ResearchOverrideRefused) as exc:
            ro.get_active_overrides()

        message = str(exc.value)
        # It must name the variable that IS set, so the operator can find it.
        assert ENV_MANIFEST in message
        assert str(path) in message
        # It must name the anchor that is NOT set.
        assert ENV_ANCHOR in message
        # And BOTH remedies, side by side. A bare "refused" makes the operator
        # guess, and the cheap guess (set the other variable) is the dangerous one.
        assert f"production run  -> unset {ENV_MANIFEST}" in message
        assert f"experiment run  -> set {ENV_ANCHOR}=true" in message
        # It must say why it is refusing, not merely that it refused.
        assert "never run in production" in message

    @pytest.mark.parametrize("falsy", ["", "false", "0", "no", "off", "yes_please"])
    def test_non_truthy_anchor_spellings_refuse(self, monkeypatch, tmp_path, falsy):
        """Presence-only parsing is the bug this avoids: elsewhere in the repo
        ``CIRIS_MOCK_LLM=false`` evaluates True."""
        path = _valid_manifest(tmp_path)
        monkeypatch.setenv(ENV_MANIFEST, str(path))
        monkeypatch.setenv(ENV_ANCHOR, falsy)
        ro.reset_research_overrides()

        with pytest.raises(ResearchOverrideRefused):
            ro.get_active_overrides()

    def test_gate_cannot_be_opened_by_the_manifest_key_alone_source_assertion(self):
        """Source-level guard, in the shape of the one precedent in the repo.

        ``get_active_overrides`` must check the anchor on every path that
        returns a manifest. Asserting on source rather than behaviour catches a
        refactor that adds a bypass branch a behavioural test would not reach.
        """
        src = inspect.getsource(ro.get_active_overrides)
        assert "env_is_true(ENV_ANCHOR)" in src, "the anchor check was removed or renamed"
        assert "raise ResearchOverrideRefused" in src, "the refusal was downgraded"
        # There must be exactly one construction path, and it must sit after the
        # anchor check.
        anchor_pos = src.index("env_is_true(ENV_ANCHOR)")
        build_pos = src.index("ResearchOverrideManifest(")
        assert anchor_pos < build_pos, "a manifest can be constructed before the anchor is checked"


# ---------------------------------------------------------------------------
# 2. Gate on => applied
# ---------------------------------------------------------------------------


class TestGateOnApplies:
    def test_manifest_loads_and_carries_provenance(self, monkeypatch, tmp_path):
        _activate(monkeypatch, _valid_manifest(tmp_path))
        manifest = ro.get_active_overrides()

        assert manifest is not None
        assert manifest.experiment_id == "test-experiment"
        trace = manifest.trace_fields()
        # mode must reach the trace: an additive pilot analysed as a strict arm
        # is indistinguishable otherwise (FSD §7.10).
        assert trace["research_mode"] == "additive"
        assert trace["research_condition"] == "c"
        assert trace["research_residue_digest"].startswith("sha256:")

    def test_string_override_reaches_get_string(self, monkeypatch, tmp_path):
        from ciris_engine.logic.utils.localization import get_string

        _activate(
            monkeypatch,
            _valid_manifest(tmp_path, string={"prompts.language_guidance": "RESEARCH GUIDANCE"}),
        )
        assert get_string("en", "prompts.language_guidance") == "RESEARCH GUIDANCE"

    def test_string_override_wins_for_every_locale_not_just_base(self, monkeypatch, tmp_path):
        """The override replaces the value; it is not a locale entry that the
        fallback chain could shadow."""
        from ciris_engine.logic.utils.localization import get_string

        _activate(
            monkeypatch,
            _valid_manifest(tmp_path, string={"conscience.ponder_attempted": "RESEARCH PONDER"}),
        )
        for locale in ("en", "es", "am", "xx"):
            assert get_string(locale, "conscience.ponder_attempted") == "RESEARCH PONDER"

    def test_prohibition_block_is_covered(self, monkeypatch, tmp_path):
        """get_prohibition_guidance deliberately bypasses get_string's fallback
        chain, so it must consult the registry itself. 22 of the 44 reachable
        keys live behind that bypass."""
        from ciris_engine.logic.utils.localization import get_prohibition_guidance

        _activate(
            monkeypatch,
            _valid_manifest(
                tmp_path,
                string={
                    "prompts.prohibitions._header": "RESEARCH HEADER",
                    "prompts.prohibitions.MEDICAL": "research medical line",
                },
            ),
        )
        block = get_prohibition_guidance("en")
        assert "RESEARCH HEADER" in block
        assert "research medical line" in block

    def test_dma_prompt_override_reaches_the_collection(self, monkeypatch, tmp_path):
        from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader

        _activate(
            monkeypatch,
            _valid_manifest(
                tmp_path,
                dma_prompt={"pdma_ethical.system_guidance_header": "RESEARCH PDMA HEADER"},
            ),
        )
        collection = DMAPromptLoader().load_prompt_template("pdma_ethical")
        assert collection.system_guidance_header == "RESEARCH PDMA HEADER"

    def test_dma_prompt_override_reaches_the_assembled_system_message(self, monkeypatch, tmp_path):
        """Overriding the field is only useful if the field reaches the wire."""
        from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader

        _activate(
            monkeypatch,
            _valid_manifest(
                tmp_path,
                dma_prompt={"pdma_ethical.system_guidance_header": "RESEARCH SENTINEL"},
            ),
        )
        loader = DMAPromptLoader()
        collection = loader.load_prompt_template("pdma_ethical")
        message = loader.get_system_message(collection, original_thought_content="x", full_context_str="y")
        assert "RESEARCH SENTINEL" in message

    def test_conscience_prompt_override_reaches_the_loader(self, monkeypatch, tmp_path):
        from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader

        _activate(
            monkeypatch,
            _valid_manifest(
                tmp_path,
                conscience_prompt={"entropy_conscience.system_prompt": "RESEARCH ENTROPY"},
            ),
        )
        assert ConsciencePromptLoader().get_system_prompt("entropy_conscience") == "RESEARCH ENTROPY"

    def test_corpus_override_replaces_both_accord_surfaces(self, monkeypatch, tmp_path):
        """R5 forces all three accord keys together; this proves both accessors
        actually honour them. The bug this guards is FSD §7.1: replacing the
        polyglot accord and leaving the localized one intact leaves the real
        covenant in the prompt that picks the verb."""
        from ciris_engine.logic.utils.constants import get_accord_text, get_localized_accord_text

        _activate(
            monkeypatch,
            _valid_manifest(
                tmp_path,
                corpus={
                    "accord.localized": "RESEARCH LOCALIZED ACCORD",
                    "accord.polyglot_compressed": "RESEARCH COMPRESSED ACCORD",
                    "accord.polyglot_full": "RESEARCH FULL ACCORD",
                },
            ),
        )
        assert get_localized_accord_text("en") == "RESEARCH LOCALIZED ACCORD"
        assert get_accord_text("compressed") == "RESEARCH COMPRESSED ACCORD"
        assert get_accord_text("force_full") == "RESEARCH FULL ACCORD"

    def test_polyglot_block_override_is_in_memory_only(self, monkeypatch, tmp_path):
        """Production corpus files are hash-pinned; substitution must happen at
        the loader boundary and never touch ciris_engine/data/."""
        from ciris_engine.logic.dma.prompt_loader import POLYGLOT_DIR, DMAPromptLoader

        original = (POLYGLOT_DIR / "pdma_framing.txt").read_bytes()
        _activate(
            monkeypatch,
            _valid_manifest(tmp_path, corpus={"polyglot.pdma_framing": "RESEARCH FRAMING BLOCK"}),
        )
        collection = DMAPromptLoader().load_prompt_template("pdma_ethical")
        rendered = "\n".join(str(v) for v in collection.model_dump().values() if isinstance(v, str))
        assert "RESEARCH FRAMING BLOCK" in rendered
        assert (POLYGLOT_DIR / "pdma_framing.txt").read_bytes() == original, "override wrote to disk"

    def test_template_override_reaches_the_agent_template(self, monkeypatch, tmp_path):
        from ciris_engine.schemas.config.agent import AgentTemplate

        _activate(
            monkeypatch,
            _valid_manifest(tmp_path, template={"role_description": "RESEARCH ROLE"}),
        )
        template = AgentTemplate(name="t", description="d", role_description="original")
        ro.apply_template_overrides(template)
        assert template.role_description == "RESEARCH ROLE"

    def test_coverage_report_names_the_uncovered_surface(self, monkeypatch, tmp_path):
        """The uncovered residue must appear in the run's own logs, not only in
        a design document nobody re-reads at analysis time."""
        _activate(monkeypatch, _valid_manifest(tmp_path))
        report = ro.describe_coverage()
        for expected in ("NOT COVERED", "ASPDMA user message", "formatters", "in English"):
            assert expected in report
        # #974: the DEFER policy (step 0), the ASPDMA user-message template
        # (step 1) and the DSDMA user message (step 2) routed out of the
        # residue and ARE covered now — the report must say so rather than
        # still list them as uncovered.
        assert "#974 routed the DEFER policy" in report
        assert "ARE covered" in report


# ---------------------------------------------------------------------------
# 3. Unresolvable key => hard error
# ---------------------------------------------------------------------------


class TestFailLoudOnPartialApplication:
    def test_dead_string_key_is_an_error_not_a_skip(self, monkeypatch, tmp_path):
        """123 of 152 ``prompts.*`` keys are dead. Setting one looks identical to
        setting a live one and does nothing."""
        _activate(monkeypatch, _valid_manifest(tmp_path, string={"prompts.dma.pdma_header": "x"}))
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "does not reach any LLM prompt" in str(exc.value)

    @pytest.mark.parametrize(
        "dead_key",
        [
            # `prompts.formatters.*` used to head this list. #991 wired all 57 of
            # them into the four prompt formatters, so the whole namespace is
            # LIVE now and would no longer be rejected — a passing assertion
            # here would mean the fix regressed. `prompts.escalation.*` replaces
            # it as the representative of a namespace that is still authored,
            # still translated into 29 locales, and still read by nobody.
            "prompts.escalation.early",
            "prompts.dma.pdma_task",
            "prompts.crisis.header",
            "prompts.engine_overview",
        ],
    )
    def test_each_dead_namespace_is_rejected(self, monkeypatch, tmp_path, dead_key):
        _activate(monkeypatch, _valid_manifest(tmp_path, string={dead_key: "x"}))
        with pytest.raises(ResearchOverrideError):
            ro.get_active_overrides()

    def test_unknown_dma_field_is_an_error(self, monkeypatch, tmp_path):
        _activate(monkeypatch, _valid_manifest(tmp_path, dma_prompt={"pdma_ethical.no_such_field": "x"}))
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "not a PromptCollection text field" in str(exc.value)

    def test_field_absent_from_the_base_template_is_an_error(self, monkeypatch, tmp_path):
        """This is FSD §7.9 made into a rule: ``action_parameter_schemas`` was
        translated into 28 locales and is unreachable. Nothing caught it."""
        valid = ro._required_dma_prompt_keys()
        candidate = next(
            f"csdma_common_sense.{field}"
            for field in sorted(ro._DMA_PROMPT_TEXT_FIELDS)
            if f"csdma_common_sense.{field}" not in valid
        )
        _activate(monkeypatch, _valid_manifest(tmp_path, dma_prompt={candidate: "x"}))
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "the override would be discarded" in str(exc.value)

    def test_unknown_template_name_is_an_error(self, monkeypatch, tmp_path):
        _activate(monkeypatch, _valid_manifest(tmp_path, dma_prompt={"not_a_template.response_format": "x"}))
        with pytest.raises(ResearchOverrideError):
            ro.get_active_overrides()

    def test_unknown_corpus_key_is_an_error(self, monkeypatch, tmp_path):
        _activate(monkeypatch, _valid_manifest(tmp_path, corpus={"accord.made_up": "x"}))
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "is not one of" in str(exc.value)

    def test_uncited_polyglot_block_is_an_error(self, monkeypatch, tmp_path):
        """book_9_mathematics.txt exists on disk but no template cites it, so an
        override naming it would be a silent no-op."""
        assert "polyglot.book_9_mathematics" not in ro._valid_corpus_keys()
        _activate(monkeypatch, _valid_manifest(tmp_path, corpus={"polyglot.book_9_mathematics": "x"}))
        with pytest.raises(ResearchOverrideError):
            ro.get_active_overrides()

    def test_invented_namespace_is_rejected(self, monkeypatch, tmp_path):
        """There is deliberately no ``inline`` namespace — offering one would
        imply the inline action doctrine is addressable. It is not."""
        payload = json.loads(_valid_manifest(tmp_path).read_text())
        payload["overrides"]["inline"] = {"aspdma_user_message": "x"}
        _activate(monkeypatch, _write_raw(tmp_path, payload))
        with pytest.raises(Exception) as exc:
            ro.get_active_overrides()
        assert "inline" in str(exc.value)

    def test_every_problem_is_reported_in_one_error(self, monkeypatch, tmp_path):
        """One run fixes the manifest. A campaign that discovers its second bad
        key on the second attempt has burned two setups."""
        _activate(
            monkeypatch,
            _valid_manifest(
                tmp_path,
                string={"prompts.dma.pdma_header": "x", "prompts.formatters.nope": "y"},
                dma_prompt={"pdma_ethical.no_such_field": "z"},
                corpus={"accord.made_up": "w"},
            ),
        )
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        message = str(exc.value)
        assert "[4]" in message, f"expected 4 collected problems, got:\n{message}"
        assert "before the first LLM call" in message

    def test_residue_digest_mismatch_refuses(self, monkeypatch, tmp_path):
        payload = json.loads(_valid_manifest(tmp_path).read_text())
        payload["residue_digest"] = "sha256:" + "0" * 64
        _activate(monkeypatch, _write_raw(tmp_path, payload))
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "residue digest mismatch" in str(exc.value)
        assert "action doctrine" in str(exc.value)

    def test_r5_partial_covenant_refuses(self, monkeypatch, tmp_path):
        """The single most dangerous thing in this area: replacing one accord
        accessor and not the other understates the covenant's effect."""
        _activate(
            monkeypatch,
            _valid_manifest(tmp_path, corpus={"accord.polyglot_compressed": "x"}),
        )
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "R5 partial covenant" in str(exc.value)
        assert "accord.localized" in str(exc.value)

    def test_r2_strict_mode_demands_totality(self, monkeypatch, tmp_path):
        payload = json.loads(_valid_manifest(tmp_path).read_text())
        payload["mode"] = "strict"
        payload["overrides"]["string"] = {"prompts.language_guidance": "x"}
        _activate(monkeypatch, _write_raw(tmp_path, payload))
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        message = str(exc.value)
        assert "R2 strict mode" in message
        # Every namespace with omissions must be listed, not just the first.
        for namespace in ("string", "dma_prompt", "conscience_prompt", "corpus", "template"):
            assert f"{namespace} namespace omits" in message

    def test_r2_strict_mode_accepts_a_total_manifest(self, monkeypatch, tmp_path):
        """The positive case: strict is satisfiable, not merely strict."""
        payload = json.loads(_valid_manifest(tmp_path).read_text())
        payload["mode"] = "strict"
        payload["overrides"] = {
            "string": {k: f"research::{k}" for k in ro.scan_reachable_string_keys()},
            "dma_prompt": {k: f"research::{k}" for k in ro._required_dma_prompt_keys()},
            "conscience_prompt": {k: f"research::{k}" for k in ro._required_conscience_prompt_keys()},
            "corpus": {k: f"research::{k}" for k in ro._valid_corpus_keys()},
            "template": {k: f"research::{k}" for k in ro._TEMPLATE_TEXT_FIELDS},
        }
        _activate(monkeypatch, _write_raw(tmp_path, payload))
        manifest = ro.get_active_overrides()
        assert manifest is not None and manifest.mode == "strict"

    def test_condition_b_refuses_while_traces_would_fabricate_scalars(self, monkeypatch, tmp_path):
        """FSD §8.1: condition (b) cannot be honestly recorded until
        ``EpistemicData`` can represent 'not measured'. Until then a (b) trace
        carries entropy=0.1/coherence=0.9 in the same fields that carry
        measurements in (c) — a large, clean, entirely artefactual effect.

        When the truthfulness fixes land this test flips: the schema check
        passes and condition (b) becomes loadable. That is the intended
        signal, not a test to delete.
        """
        payload = json.loads(_valid_manifest(tmp_path).read_text())
        payload["condition"] = "b"
        _activate(monkeypatch, _write_raw(tmp_path, payload))

        from ciris_engine.schemas.conscience.core import EpistemicData

        entropy = EpistemicData.model_fields["entropy_level"].annotation
        nullable = type(None) in getattr(entropy, "__args__", ())

        if nullable:
            assert ro.get_active_overrides() is not None
        else:
            with pytest.raises(ResearchOverrideError) as exc:
                ro.get_active_overrides()
            assert "condition 'b' refused" in str(exc.value)
            assert "artefactual" in str(exc.value)

    def test_template_override_conflict_refuses_rather_than_picking_a_winner(self, monkeypatch, tmp_path):
        """``AgentTemplate.pdma_overrides`` is ungated and is consulted BEFORE
        the prompt loader, so a leftover value silently beats the manifest."""
        from ciris_engine.schemas.config.agent import AgentTemplate, PDMAOverrides

        _activate(
            monkeypatch,
            _valid_manifest(tmp_path, dma_prompt={"pdma_ethical.system_guidance_header": "x"}),
        )
        template = AgentTemplate(
            name="t",
            description="d",
            role_description="r",
            pdma_overrides=PDMAOverrides(system_prompt="leftover from an earlier run"),
        )
        with pytest.raises(ResearchOverrideError) as exc:
            ro.assert_no_template_conflict(template)
        assert "precedence conflict" in str(exc.value)
        assert "pdma_ethical.system_guidance_header" in str(exc.value)

    def test_no_conflict_when_template_overrides_are_clear(self, monkeypatch, tmp_path):
        from ciris_engine.schemas.config.agent import AgentTemplate

        _activate(
            monkeypatch,
            _valid_manifest(tmp_path, dma_prompt={"pdma_ethical.system_guidance_header": "x"}),
        )
        ro.assert_no_template_conflict(AgentTemplate(name="t", description="d", role_description="r"))

    def test_missing_manifest_file_is_an_error(self, monkeypatch, tmp_path):
        _activate(monkeypatch, tmp_path / "does_not_exist.json")
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "not a readable file" in str(exc.value)

    def test_malformed_manifest_is_an_error(self, monkeypatch, tmp_path):
        path = tmp_path / "manifest.json"
        path.write_text("{not json", encoding="utf-8")
        _activate(monkeypatch, path)
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        assert "not valid JSON" in str(exc.value)

    def test_r4_raw_key_leakage_raises_under_an_active_manifest(self, monkeypatch, tmp_path):
        """Without this, a typo injects the literal key string into the prompt
        as content and the sample is silently contaminated."""
        from ciris_engine.logic.utils.localization import get_string

        _activate(monkeypatch, _valid_manifest(tmp_path))
        with pytest.raises(RuntimeError) as exc:
            get_string("en", "prompts.dma.definitely_not_a_real_key")
        assert "raw key string as prompt content" in str(exc.value)

    def test_r4_raw_key_leakage_is_tolerated_when_the_gate_is_off(self, monkeypatch):
        """Production behaviour is unchanged — this facility adds no new
        failure mode to a run that is not a research run."""
        from ciris_engine.logic.utils.localization import get_string

        monkeypatch.delenv(ENV_MANIFEST, raising=False)
        ro.reset_research_overrides()
        assert get_string("en", "prompts.dma.definitely_not_a_real_key") == "prompts.dma.definitely_not_a_real_key"

    def test_r3_silent_locale_fallback_raises_for_dma_prompts(self, monkeypatch, tmp_path):
        """A research locale missing one YAML would otherwise silently serve the
        original CIRIS English prompt — the arm contains what it was built to
        exclude, logged at ``debug``."""
        from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader

        _activate(monkeypatch, _valid_manifest(tmp_path))
        with pytest.raises(RuntimeError) as exc:
            DMAPromptLoader(language="xx").load_prompt_template("pdma_ethical")
        assert "would put the original CIRIS prompt into a research arm" in str(exc.value)

    def test_r3_silent_locale_fallback_raises_for_conscience_prompts(self, monkeypatch, tmp_path):
        """Not hypothetical: ``optimization_veto_conscience.yml`` is localized in
        zero of 28 locales, so this branch fires for every real locale too."""
        from ciris_engine.logic.conscience.prompt_loader import ConsciencePromptLoader

        _activate(monkeypatch, _valid_manifest(tmp_path))
        with pytest.raises(RuntimeError) as exc:
            ConsciencePromptLoader(language="es").load_prompts("optimization_veto_conscience")
        assert "research arm" in str(exc.value)

    def test_r3_does_not_fire_when_the_gate_is_off(self, monkeypatch):
        from ciris_engine.logic.dma.prompt_loader import DMAPromptLoader

        monkeypatch.delenv(ENV_MANIFEST, raising=False)
        ro.reset_research_overrides()
        collection = DMAPromptLoader(language="xx").load_prompt_template("pdma_ethical")
        assert collection.component_name == "pdma_ethical"


# ---------------------------------------------------------------------------
# 4. Drift guard
# ---------------------------------------------------------------------------


class TestDriftGuard:
    def test_declared_key_space_matches_the_real_prompt_surface(self):
        """The load-bearing drift guard.

        The loader rescans source, so it can never accept a dead key. But if the
        real surface moves and nobody notices, the override set silently stops
        covering a field. Comparing the live scan against the declared constant
        makes that loud.

        If this fails: a ``get_string`` call site was added, removed or renamed.
        Update ``DECLARED_STRING_KEY_SPACE`` **and** re-check whether the
        campaign's manifests still achieve totality.
        """
        scanned = ro.scan_reachable_string_keys()
        declared = ro.DECLARED_STRING_KEY_SPACE

        assert scanned - declared == set(), (
            f"new prompt-reaching localization keys are NOT in the declared override "
            f"key space: {sorted(scanned - declared)}"
        )
        assert (
            declared - scanned == set()
        ), f"declared override keys no longer reach any prompt: {sorted(declared - scanned)}"

    def test_prohibition_keys_track_the_wise_bus_gate(self):
        """The one dynamic prefix. It must expand from PROHIBITED_CAPABILITIES so
        it can never drift from the gate that enforces them."""
        from ciris_engine.logic.buses.prohibitions import PROHIBITED_CAPABILITIES

        scanned = ro.scan_reachable_string_keys()
        for category in PROHIBITED_CAPABILITIES:
            assert f"prompts.prohibitions.{category}" in scanned

    def test_dma_key_space_matches_schema_times_filesystem(self):
        """``dma_prompt`` field names are read off ``PromptCollection``, not
        invented. A schema reshape must not leave the key space stale."""
        from ciris_engine.schemas.dma.prompts import PromptCollection

        assert ro._DMA_PROMPT_TEXT_FIELDS <= set(PromptCollection.model_fields), (
            f"declared DMA text fields no longer exist on PromptCollection: "
            f"{sorted(ro._DMA_PROMPT_TEXT_FIELDS - set(PromptCollection.model_fields))}"
        )
        required = ro._required_dma_prompt_keys()
        assert required, "no DMA prompt keys discovered — the prompts directory moved"
        for key in required:
            template, _, field = key.partition(".")
            assert field in ro._DMA_PROMPT_TEXT_FIELDS
            assert (ro._DMA_PROMPTS_DIR / f"{template}.yml").exists()

    def test_conscience_key_space_matches_schema_times_filesystem(self):
        from ciris_engine.logic.conscience.prompt_loader import ConsciencePrompts

        assert ro._CONSCIENCE_PROMPT_TEXT_FIELDS <= set(ConsciencePrompts.model_fields)
        required = ro._required_conscience_prompt_keys()
        assert required, "no conscience prompt keys discovered"
        # All four consciences must be represented; optimization_veto is the one
        # most likely to be quietly dropped, and it is the largest prompt.
        names = {k.partition(".")[0] for k in required}
        assert "optimization_veto_conscience" in names

    def test_template_key_space_matches_agent_template(self):
        from ciris_engine.schemas.config.agent import AgentTemplate

        assert ro._TEMPLATE_TEXT_FIELDS <= set(AgentTemplate.model_fields)

    def test_every_residue_site_still_resolves(self):
        """The uncovered inline surface is pinned by symbol, not line number. If
        a symbol is renamed or deleted the digest must fail loudly rather than
        hash a different function."""
        for rel, qualname in ro.RESIDUE_SITES:
            path = ro._ENGINE_ROOT / rel
            assert path.exists(), f"residue site module missing: {rel}"
            segment = ro._extract_symbol_source(path, qualname)
            assert segment.strip(), f"residue site extracted empty: {rel}::{qualname}"

    def test_residue_digest_is_deterministic(self):
        assert ro.compute_residue_digest() == ro.compute_residue_digest()
        assert ro.compute_residue_digest().startswith("sha256:")

    def test_residue_digest_covers_the_aspdma_user_message_and_defer_policy(self):
        """The two things FSD §6.1/§7.2 identify as most able to invert a
        conclusion. #974 routed both TEXTS out of Python (step 0: the DEFER
        policy -> action_params_defer_guidance; step 1: the ASPDMA user
        template -> context_integration), so the pin now covers what is left
        inline: the interpolated helper prose and the per-verb schema/guidance
        scaffolding. If those stop being hashed, the pin is decorative."""
        sites = {(rel, qual) for rel, qual in ro.RESIDUE_SITES}
        # The routed template came OUT of the inventory (§11: that's the shrink)...
        assert (
            "logic/dma/action_selection/context_builder.py",
            "ActionSelectionContextBuilder.build_main_user_content",
        ) not in sites
        # ...and the doctrine it interpolates stays pinned.
        cb_sites = {q for r, q in sites if r.endswith("context_builder.py")}
        assert "ActionSelectionContextBuilder._build_ponder_context" in cb_sites
        assert "ActionSelectionContextBuilder._build_startup_guidance" in cb_sites
        assert "ActionSelectionContextBuilder._get_reject_thought_guidance" in cb_sites
        assert "ActionSelectionContextBuilder._build_original_task_context" in cb_sites
        defer_sites = {q for r, q in sites if r.endswith("action_instruction_generator.py")}
        assert "ActionInstructionGenerator._generate_schema_for_action" in defer_sites
        assert "ActionInstructionGenerator.get_action_guidance" in defer_sites

        # The routed doctrine must live in the YAML now — not as a stub.
        import yaml

        data = yaml.safe_load(
            (ro._DMA_PROMPTS_DIR / "action_selection_pdma.yml").read_text(encoding="utf-8")
        )
        assert "HANDLER ACTION" in data["context_integration"]
        assert "DEFER is ONLY for situations" in data["action_params_defer_guidance"]

    def test_residue_digest_changes_when_the_doctrine_changes(self, tmp_path, monkeypatch):
        """A pin that does not move is not a pin."""
        before = ro.compute_residue_digest()
        real = ro._extract_symbol_source

        def fake(path, qualname):
            text = real(path, qualname)
            if qualname == "ActionInstructionGenerator.get_action_guidance":
                return text + "\n# a change to the DEFER policy\n"
            return text

        monkeypatch.setattr(ro, "_extract_symbol_source", fake)
        assert ro.compute_residue_digest() != before

    def test_skeleton_round_trips_through_validation(self, monkeypatch, tmp_path):
        """The generated skeleton must satisfy every rule it was generated from.

        This is the end-to-end drift guard: if the key space, the totality rule
        and the residue digest ever disagree with each other, a strict manifest
        becomes unwritable and this fails before a researcher discovers it.
        """
        skeleton = ro.strict_manifest_skeleton(experiment_id="round-trip")
        _activate(monkeypatch, _write_raw(tmp_path, skeleton))
        manifest = ro.get_active_overrides()
        assert manifest is not None
        assert manifest.mode == "strict"
        # 101 = the pre-#974 key space (97) + the #974-routed keys:
        #   action_selection_pdma.action_params_defer_guidance (step 0, the DEFER policy)
        #   action_selection_pdma.context_integration          (step 1, the ASPDMA user template)
        #   prompts.identity_block                             (step 3, the CORE IDENTITY doctrine)
        #   conscience.repeated_speak_guidance                 (step 5, the repeated-SPEAK guidance)
        # (step 2 reused the pre-existing dsdma_base.context_integration key.)
        # Back to 101: #989's fix landed, so OVERRIDE_IMMUNE_DMA_PROMPT_KEYS is
        # empty and R2 totality requires all 36 dma_prompt keys again. The
        # number moved 101 -> 88 -> 101 across this window: the dip was the
        # honest stopgap (refuse what cannot be applied), the return is the
        # real fix (apply it). If it ever drops again, a key became
        # unapplicable and the inventory says which. #990 kept it at 101 on
        # purpose: `action_parameter_schemas` was made to APPLY at the
        # composition boundary rather than being declared unapplicable.
        #
        # 101 -> 105 in 2.9.10: four live YAML fields joined the key space.
        # `tool_selection_guidance` and `csdma_ambiguity_alignment_example`
        # became composable in #993; `taxonomy_text` (3,273 B of rights/needs
        # deferral taxonomy — operative doctrine steering DEFER) and
        # `tool_correction_section` were live all along but sat outside the
        # inventory, so R1 rejected any manifest naming them as "does not reach
        # any LLM prompt", which was false (#995 P1-6). Coverage going UP is the
        # only direction this number should ever move without an inventory entry
        # explaining a drop.
        #
        # 105 -> 191 in 2.9.10, in two independent steps, both increases:
        #   +29  #997 split `prompts.language_guidance` into single-class parts.
        #        The parent key stays reachable (24 unsplit locales resolve
        #        through it), so this is 29 NEW keys, not a re-partition. This
        #        landed without moving the number, which is why the count is
        #        asserted at all.
        #   +57  #991 wired the four prompt formatters to `label_localizer`.
        #        These keys were authored and translated into 29 locales —
        #        1,653 strings — and read by nobody: the formatters emitted
        #        hardcoded English twins, so every non-English agent got its
        #        system-snapshot, identity, user-context and task-chain headings
        #        in English inside an otherwise localized prompt. They were the
        #        largest dead namespace in the bundle and are now the largest
        #        block of the `string` key space.
        # 105 + 29 + 57 = 191. Both moves are coverage going UP, which the note
        # above says is the only direction this may move unexplained.
        assert sum(len(v) for v in skeleton["overrides"].values()) == 191

    def test_skeleton_markers_are_visible_if_left_unedited(self):
        """An unedited entry must show up in the prompt, not pass for content."""
        skeleton = ro.strict_manifest_skeleton()
        for namespace in skeleton["overrides"].values():
            for key, value in namespace.items():
                assert value.startswith("REPLACE::"), f"{key} has a value that could pass for real text"

    def test_uncovered_surface_is_not_silently_claimed(self):
        """There must be no ``inline`` namespace on the manifest schema. Adding
        one would imply the action doctrine is addressable."""
        assert "inline" not in ro.OverrideSet.model_fields
        assert ro.OverrideSet.model_config.get("extra") == "forbid"


class TestValidateIsAMirrorNotASofteningcheck:
    """``validate_manifest_file`` is the pre-run check the workflow and the
    capture script both call (#962).

    Its whole value depends on giving the SAME verdict as the startup gate. A
    validator that passed something the agent would refuse is worse than none —
    it would send a researcher into a ten-minute run with false confidence. A
    validator that was more lenient would be worse still, because leniency here
    is what produces a clean-looking cohort that was never actually manipulated.
    """

    def test_verdict_matches_the_startup_gate(self, monkeypatch, tmp_path):
        """Same manifests, same answers, both directions."""
        good_dir = tmp_path / "good"
        good_dir.mkdir()
        good = _write_raw(good_dir, ro.strict_manifest_skeleton("mirror"))
        ok, _ = ro.validate_manifest_file(str(good))
        assert ok
        _activate(monkeypatch, good)
        assert ro.get_active_overrides() is not None  # gate agrees

        payload = ro.strict_manifest_skeleton("mirror")
        payload["overrides"]["corpus"].pop("accord.polyglot_full")
        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        bad = _write_raw(bad_dir, payload)
        ok, _ = ro.validate_manifest_file(str(bad))
        assert not ok
        ro.reset_research_overrides()
        _activate(monkeypatch, bad)
        with pytest.raises(ResearchOverrideError):  # gate agrees
            ro.get_active_overrides()

    def test_missing_residue_digest_report_carries_the_value_to_paste(self, tmp_path):
        """The reason #962 was a ten-minute round trip: the field name alone is
        not actionable, because the value is a hash over this tree."""
        payload = ro.strict_manifest_skeleton("no-digest")
        payload.pop("residue_digest")
        ok, report = ro.validate_manifest_file(str(_write_raw(tmp_path, payload)))
        assert not ok
        assert "residue_digest" in report
        assert ro.compute_residue_digest() in report, "report names the field but not the value"
        assert f'"residue_digest": "{ro.compute_residue_digest()}",' in report, "not pasteable as JSON"

    def test_partial_strict_report_points_at_the_generator(self, tmp_path):
        """~97 keys is not hand-writable; "omits 43 fields" is a worse authoring
        tool than ``skeleton``, so the report has to name it."""
        payload = ro.strict_manifest_skeleton("partial")
        payload["overrides"]["template"] = {}
        ok, report = ro.validate_manifest_file(str(_write_raw(tmp_path, payload)))
        assert not ok
        assert "R2 strict mode" in report
        assert "research_overrides skeleton" in report
        assert "additive" in report

    def test_apostrophes_in_prose_are_not_a_failure(self, tmp_path):
        """#961's payload, from the validator's side: a manifest describing an
        experiment contains apostrophes, and that must be unremarkable."""
        payload = ro.strict_manifest_skeleton("the run's signed manifest")
        ok, report = ro.validate_manifest_file(str(_write_raw(tmp_path, payload)))
        assert ok, report
        assert "the run's signed manifest" in report

    def test_validator_leaves_no_override_state_behind(self, tmp_path):
        """It runs in-process in tests and in a subprocess in CI. In-process, a
        leaked active manifest would make ``get_string`` raise suite-wide."""
        ro.validate_manifest_file(str(_write_raw(tmp_path, ro.strict_manifest_skeleton("leak"))))
        assert ro.get_active_overrides() is None

    def test_missing_file_is_reported_not_raised(self, tmp_path):
        ok, report = ro.validate_manifest_file(str(tmp_path / "absent.json"))
        assert not ok
        assert "not a readable file" in report
