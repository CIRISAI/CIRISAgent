"""#976 — the regime manifest v2 schema and every §10.4 refusal.

Structure: ``_baseline()`` is a regime that passes EVERY check on this tree.
Each refusal test takes the baseline and breaks exactly one thing, so a test
that goes red says which rule moved. That shape is also the mutation check:

- delete a refusal and its ``test_refuses_*`` goes red;
- make a refusal fire unconditionally and ``test_baseline_regime_is_accepted``
  (plus the paired ``*_is_accepted`` tests) goes red.

Three rules carry an explicit paired accepted/refused test because they are the
ones whose failure mode is silent — a green gate over a biased number:

1. T-N1, a held mixed block smuggling the varied class (§10.2.1) — biases the
   values effect toward zero WITH THE GATE GREEN;
2. decoding set equality in both directions [M-6/M-N3] — an unpinned parameter
   changes the transmitted set under an identical manifest;
3. ``action_tier`` vs the DEFER policy in the residue [M-4] — the outcome
   variable's own doctrine inherited invisibly by every arm.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import pytest

from ciris_engine.logic.utils.regime_manifest import (
    FIELD_CLASS_ANNOTATIONS,
    RegimeRefused,
    arm_field_plan,
    decision_relevant_boundaries,
    defer_policy_residue_sites,
    kill_instrument_inventory,
    load_regime_v2,
    pinned_decoding_keys,
    r2_totality_problems,
    routed_defer_policy_text,
    synthesize_arm_manifests,
    transmitted_decoding_keys,
    validate_regime,
)
from ciris_engine.schemas.dma.compose import BlockClass, BlockDisposition, GateRegime
from ciris_engine.schemas.research.regime import REGIME_SCHEMA_V2, ExperimentalRegimeV2, RegimeContrast

_DEEPINFRA = "https://api.deepinfra.com/v1/openai"
_MODEL = "Qwen/Qwen3.6-35B-A3B"

#: What the DeepInfra branch actually transmits (service.py
#: ``_build_reasoning_off_extras``) — pinned here so the baseline is set-EQUAL.
_DEEPINFRA_EXTRA_BODY = {
    "chat_template_kwargs": {"enable_thinking": False},
    "reasoning": {"enabled": False},
}


def _baseline_blocks() -> Dict[str, dict]:
    """Every ``mixed`` block resolved, by suffix where the suffix is honest.

    ``confound_accepted: [axiotic]`` appears here because the baseline varies
    axiotic and these blocks carry axiotic contaminant. §10.3 deliberately does
    NOT write that in its example manifest — an example is a template people
    copy and it must not teach the opt-out as the default. A test fixture has
    the opposite job: it needs a regime that passes so the refusals can be shown
    to be specific rather than blanket.

    Since #997 a block is a FIELD, so these are the seven ``EXPECTED_MIXED``
    keys — the bare ``system:`` / ``user:`` suffixes are gone along with the
    message-granularity blocks they covered.
    """
    held = {"disposition": "hold", "confound_accepted": ["axiotic"]}
    return {
        "language_guidance": {
            **held,
            "contaminant": ["axiotic", "deontic", "empirical"],
        },
        "pdma_ethical.system_guidance_header": {
            **held,
            "contaminant": ["procedural", "axiotic", "structural"],
        },
        "action_selection_pdma.system_message": {
            **held,
            "contaminant": ["ontological", "axiotic", "procedural", "pragmatic", "contingent"],
        },
        "action_selection_pdma.context_integration.slots": {
            **held,
            "contaminant": ["procedural", "axiotic", "deontic", "contingent"],
        },
        "coherence_conscience.system_prompt": {
            **held,
            "contaminant": ["axiotic", "deontic", "epistemic", "ontological", "procedural"],
        },
        "epistemic_humility_conscience.system_prompt": {
            **held,
            "contaminant": ["axiotic", "deontic", "epistemic", "ontological", "procedural"],
        },
        "optimization_veto_conscience.system_prompt": {
            **held,
            "contaminant": ["axiotic", "deontic", "epistemic", "empirical", "procedural", "structural"],
        },
    }


def _baseline_dict() -> dict:
    return {
        "schema": REGIME_SCHEMA_V2,
        "regime_id": "test-976",
        "class_set_version": 2,
        "hypothesis": "H3ERE's behavioural effect is separable from the values it carries.",
        "mode": "additive",
        "arms": {
            "h3ere-ciris": {"harness": "h3ere"},
            "h3ere-alt": {"harness": "h3ere", "replace": {"axiotic": "corpora/values-alt/"}},
        },
        "contrasts": {"values_effect": "h3ere-ciris - h3ere-alt"},
        "dv": {
            # text_tier is deliberately absent: `en` is a MANDATORY locale
            # [M-N2] and carries no machine U-row instrument, so any text tier
            # over a locale set containing en refuses (see
            # test_refuses_text_tier_row_with_no_instrument_in_en).
            "action_tier": {"measures": ["selected_verb", "defer_rate"], "arms": ["h3ere-ciris", "h3ere-alt"]},
        },
        "repeats": {
            "unit": "conversation",
            "conversations_per_cell": 20,
            "variance_source": "temperature",
            "comparison_policy": "holm-bonferroni",
            "mde": {"values_effect": 0.15},
        },
        "holds": {
            "model": _MODEL,
            "decoding": {"temperature": 0.7, "max_tokens": 4096, "extra_body": _DEEPINFRA_EXTRA_BODY},
            "base_url": _DEEPINFRA,
            "corpus": "v1_sensitive.json",
            "locales": ["en"],
            "adapter_set": ["api"],
        },
        "pins": {"residue_digest": "sha256:deadbeef"},
        "blocks": _baseline_blocks(),
        "gate": {},
    }


def _baseline(**patch: object) -> ExperimentalRegimeV2:
    raw = _baseline_dict()
    raw.update(patch)
    return ExperimentalRegimeV2.model_validate(raw)


def _refusal(regime: ExperimentalRegimeV2) -> str:
    with pytest.raises(RegimeRefused) as excinfo:
        validate_regime(regime)
    return str(excinfo.value)


# ===========================================================================
# The anchor — every refusal below must be specific, not a blanket
# ===========================================================================


def test_baseline_regime_is_accepted() -> None:
    """If this goes red, some refusal has become unconditional."""
    validate_regime(_baseline())


def test_gate_view_projects_to_the_phase1_gate_regime() -> None:
    """v2 is a strict superset of the #973 gate input — one gate, one shape."""
    view = _baseline().gate_view()
    assert isinstance(view, GateRegime)
    assert view.varied_classes() == frozenset({BlockClass.AXIOTIC})
    assert view.blocks["language_guidance"].disposition is BlockDisposition.HOLD


def test_contrast_expression_names_two_arms_with_hyphenated_names() -> None:
    """``h3ere-ciris - h3ere-alt`` is two arms, not four tokens."""
    contrast = RegimeContrast.model_validate("h3ere-ciris - h3ere-alt")
    assert (contrast.minuend, contrast.subtrahend) == ("h3ere-ciris", "h3ere-alt")
    with pytest.raises(ValueError):
        RegimeContrast.model_validate("h3ere-ciris")


# ===========================================================================
# §10.4 rule 1 — unresolved / mixed block disposition
# ===========================================================================


def test_refuses_mixed_block_with_no_disposition() -> None:
    blocks = _baseline_blocks()
    del blocks["language_guidance"]
    message = _refusal(_baseline(blocks=blocks))
    assert "'language_guidance' is 'mixed' and the regime gives it no disposition" in message
    assert "['axiotic']" in message  # names the varied class it contaminates


def test_refuses_block_dispositioned_refuse() -> None:
    blocks = _baseline_blocks()
    blocks["language_guidance"]["disposition"] = "refuse"
    assert "carries disposition 'refuse'" in _refusal(_baseline(blocks=blocks))


def test_refuses_mixed_block_dispositioned_vary() -> None:
    blocks = _baseline_blocks()
    blocks["language_guidance"]["disposition"] = "vary"
    assert "cannot carry 'vary'" in _refusal(_baseline(blocks=blocks))


# ===========================================================================
# §10.4 rule 10 [T-N1] — a HELD block smuggling the varied class
# MUTATION-CHECKED: paired refused/accepted below.
# ===========================================================================


def test_refuses_held_block_smuggling_the_varied_class() -> None:
    """The one confound the block table exists to catch: holding
    ``language_guidance`` leaves CIRIS axiotic content byte-identical inside the
    alt-values arm — every Phase-1 assertion passes and ``values_effect`` is
    biased toward zero WITH THE GATE GREEN."""
    blocks = _baseline_blocks()
    blocks["language_guidance"]["confound_accepted"] = []
    message = _refusal(_baseline(blocks=blocks))
    assert "'language_guidance' is HELD while its contaminant(s) ['axiotic']" in message
    assert "biased toward zero WITH THE GATE GREEN" in message


def test_held_block_is_accepted_when_the_confound_is_named() -> None:
    """The paired direction — the rule must not refuse every hold."""
    validate_regime(_baseline())  # baseline names the confound and passes


def test_held_block_is_accepted_when_the_contaminant_is_not_varied() -> None:
    """A hold whose contaminants miss the varied class needs no acknowledgement."""
    blocks = _baseline_blocks()
    for entry in blocks.values():
        entry["confound_accepted"] = []
    arms = {
        "h3ere-ciris": {"harness": "h3ere"},
        # `nomological` is not a contaminant of any block in the #973 table.
        # (It was `pragmatic` until #997 split the ASPDMA system message out as
        # its own block and named the LANGUAGE RULES it carries.)
        "h3ere-alt": {"harness": "h3ere", "replace": {"nomological": "corpora/laws-alt/"}},
    }
    validate_regime(_baseline(arms=arms, blocks=blocks))


def test_refuses_mixed_block_with_an_empty_contaminant_list() -> None:
    blocks = _baseline_blocks()
    blocks["language_guidance"] = {"disposition": "hold"}
    # The #973 table still knows this block's contaminants, so the T-N1 rule
    # fires; the emptiness itself is reported for blocks the table does not
    # annotate. Assert on the rule that must not be escapable by omission.
    assert "HELD while its contaminant(s)" in _refusal(_baseline(blocks=blocks))


# ===========================================================================
# §10.4 rule 2 [M-4] — action_tier vs the DEFER policy in the residue
# MUTATION-CHECKED: both directions, plus the detector against the real tree.
# ===========================================================================


def test_defer_policy_is_not_in_the_residue_inventory_on_this_tree() -> None:
    """#974 step 0 routed it out; this is what makes action_tier declarable."""
    assert defer_policy_residue_sites() == []


def test_defer_detector_finds_a_site_whose_source_carries_the_doctrine() -> None:
    """The detector must not be vacuously empty. Feed it an inventory whose
    source IS the doctrine and it has to say so — otherwise 'no hits' proves
    nothing about #974 and everything about a broken scanner."""
    doctrine = routed_defer_policy_text()
    hits = defer_policy_residue_sites(
        sites=[("logic/dma/action_selection/action_instruction_generator.py", "FakeInlineDeferPolicy")],
        extract=lambda path, qualname: doctrine,
    )
    assert hits == ["logic/dma/action_selection/action_instruction_generator.py::FakeInlineDeferPolicy"]


def test_action_tier_is_accepted_because_974_routed_the_defer_policy(monkeypatch) -> None:
    """The accepted direction, asserted on the real inventory."""
    validate_regime(_baseline())  # baseline declares action_tier


def test_refuses_action_tier_while_defer_policy_is_in_the_residue(monkeypatch) -> None:
    """The refused direction, with the inventory monkeypatched to carry it."""
    import ciris_engine.logic.utils.regime_manifest as rm

    monkeypatch.setattr(
        rm,
        "defer_policy_residue_sites",
        lambda *a, **k: ["logic/dma/action_selection/action_instruction_generator.py::get_action_guidance"],
    )
    message = _refusal(_baseline())
    assert "`action_tier` DV is declared while the DEFER policy is STILL in the residue" in message
    assert "outcome variable's own doctrine" in message


def test_refuses_action_tier_claimed_over_a_direct_provider_arm() -> None:
    """[M-2] a direct-provider call has no handler enum."""
    raw = _baseline_dict()
    raw["arms"]["bare-dp"] = {"harness": "direct-provider"}
    raw["dv"]["action_tier"]["arms"] = ["h3ere-ciris", "bare-dp"]
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "`action_tier` names non-h3ere arm(s) ['bare-dp']" in message


# ===========================================================================
# §10.4 rule 3 — an h3ere arm labelled bare / condition (a)
# ===========================================================================


@pytest.mark.parametrize("label", ["bare", "a", "condition-a", "BARE"])
def test_refuses_h3ere_arm_labelled_bare(label: str) -> None:
    raw = _baseline_dict()
    raw["arms"] = {label: {"harness": "h3ere"}, "h3ere-alt": raw["arms"]["h3ere-alt"]}
    raw["contrasts"] = {"values_effect": f"{label} - h3ere-alt"}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "labelled as §0's condition (a)" in message
    assert "direct-provider harness" in message


def test_a_direct_provider_arm_may_be_called_bare() -> None:
    """That is exactly where condition (a) has to come from — the rule is about
    the harness, not the word."""
    raw = _baseline_dict()
    raw["arms"]["bare"] = {"harness": "direct-provider"}
    validate_regime(ExperimentalRegimeV2.model_validate(raw))


# ===========================================================================
# §10.4 rule 4 [M-6/M-N3] — pinned == transmitted, SET EQUALITY, both directions
# MUTATION-CHECKED: refused and accepted for the live `seed` case.
# ===========================================================================


def test_transmitted_keys_are_read_from_the_call_path_not_restated() -> None:
    keys = transmitted_decoding_keys(_DEEPINFRA, _MODEL)
    assert keys == {"temperature", "max_tokens", "extra_body.chat_template_kwargs", "extra_body.reasoning"}
    # A different endpoint transmits a different set — extra_body is a FUNCTION
    # of base_url, which is why the endpoint must be pinned.
    assert transmitted_decoding_keys("https://openrouter.ai/api/v1", "meta-llama/llama-4-scout") != keys


def test_refuses_pinned_but_untransmitted_decoding_key() -> None:
    """§10.3's own example pins ``top_p: 1.0``; nothing in this runtime sends it."""
    raw = _baseline_dict()
    raw["holds"]["decoding"]["top_p"] = 1.0
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "pinned but NOT transmitted" in message and "top_p" in message


def test_refuses_transmitted_but_unpinned_decoding_key() -> None:
    """The other direction — §10.3 pins a strict SUBSET of the DeepInfra set,
    and subset semantics would have passed it."""
    raw = _baseline_dict()
    raw["holds"]["decoding"]["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "TRANSMITTED at" in message and "extra_body.reasoning" in message


def test_refuses_pinned_seed_when_ciris_llm_seed_is_unset(monkeypatch) -> None:
    monkeypatch.delenv("CIRIS_LLM_SEED", raising=False)
    raw = _baseline_dict()
    raw["holds"]["decoding"]["seed"] = 20260802
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "pinned but NOT transmitted" in message and "seed" in message
    assert "plumbed on the OpenAI-compatible path as of 2.9.9" in message


def test_pinned_seed_is_accepted_when_ciris_llm_seed_is_set(monkeypatch) -> None:
    """The live half of the M-N1/M-6 pair: #975 landed seed plumbing, so the
    pin is honourable now — but only with the env var actually set."""
    monkeypatch.setenv("CIRIS_LLM_SEED", "20260802")
    raw = _baseline_dict()
    raw["holds"]["decoding"]["seed"] = 20260802
    validate_regime(ExperimentalRegimeV2.model_validate(raw))


def test_refuses_transmitted_seed_that_the_manifest_does_not_pin(monkeypatch) -> None:
    monkeypatch.setenv("CIRIS_LLM_SEED", "20260802")
    message = _refusal(_baseline())
    assert "TRANSMITTED at" in message and "seed" in message


def test_refuses_when_no_base_url_is_pinned() -> None:
    raw = _baseline_dict()
    raw["holds"].pop("base_url")
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "unperformable check refuses" in message


def test_refuses_when_base_url_is_pinned_twice_and_disagrees() -> None:
    raw = _baseline_dict()
    raw["holds"]["decoding"]["base_url"] = "https://api.together.xyz/v1"
    assert "pinned twice and disagrees" in _refusal(ExperimentalRegimeV2.model_validate(raw))


def test_pinned_key_vocabulary_matches_the_transmitted_vocabulary() -> None:
    """Both sides must speak the same dotted language or set equality is noise."""
    assert pinned_decoding_keys(_baseline()) == {
        "temperature",
        "max_tokens",
        "extra_body.chat_template_kwargs",
        "extra_body.reasoning",
    }


# ===========================================================================
# §10.4 rule 5 [T-4] — a kill instrument absent in a declared locale
# ===========================================================================


def test_kill_instrument_inventory_covers_eighteen_locales_and_not_en() -> None:
    """The FSD's '18 languages' is the union of the substring table and the
    script table. ``en`` is in NEITHER, which is why any text tier over the
    mandatory fidelity-control locale refuses today."""
    inventory = kill_instrument_inventory()
    assert len(inventory) == 18
    assert "en" not in inventory
    assert "U10" in inventory["am"]


def test_refuses_kill_instrument_absent_in_a_declared_locale() -> None:
    raw = _baseline_dict()
    raw["holds"]["locales"] = ["en", "de"]
    raw["kills"] = {"axiotic": {"instrument": "U10", "mde": 0.15, "equivalence_bound": 0.1}}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "no machine implementation in declared locale 'de'" in message
    assert "no machine implementation in declared locale 'en'" in message


def test_kill_refusal_names_only_the_locales_that_lack_the_instrument() -> None:
    """Specificity, not a blanket: ``am`` has ``U10_slur_echo`` and is NOT
    named; ``en`` has no U-row at all and is."""
    raw = _baseline_dict()
    raw["holds"]["locales"] = ["am", "en"]
    raw["kills"] = {"axiotic": {"instrument": "U10_slur_echo", "mde": 0.15, "equivalence_bound": 0.1}}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "declared locale 'am'" not in message
    assert "declared locale 'en'" in message


def test_refuses_kill_without_mde_and_equivalence_bound() -> None:
    """A kill without both is decoration, and its class reverts to hold [T-4]."""
    raw = _baseline_dict()
    raw["holds"]["locales"] = ["en", "am"]
    raw["kills"] = {"axiotic": {"instrument": "U10"}}
    assert "is decoration, and the class reverts" in _refusal(ExperimentalRegimeV2.model_validate(raw))


def test_refuses_text_tier_row_with_no_instrument_in_en() -> None:
    """§10.3's own ``en: [U4, U6]``. ``en`` is mandatory [M-N2] and has no
    machine U-row at all; ``U6`` has none in any locale."""
    raw = _baseline_dict()
    raw["dv"]["text_tier"] = {"measures": ["U_codes"], "arms": "all"}
    raw["dv"]["text_tier_rows"] = {"en": ["U4", "U6"]}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "locale 'en' pre-registers U-row(s) ['U4', 'U6'] with no machine instrument" in message


def test_refuses_text_tier_with_a_locale_that_preregisters_no_rows() -> None:
    """The corrected family is (locale x row x contrast) [M-N5], so a declared
    locale with no named rows is a cell nobody sized."""
    raw = _baseline_dict()
    raw["holds"]["locales"] = ["en", "am"]
    raw["dv"]["text_tier"] = {"measures": ["U_codes"], "arms": "all"}
    raw["dv"]["text_tier_rows"] = {"am": ["U10"]}
    assert "pre-register no U-rows" in _refusal(ExperimentalRegimeV2.model_validate(raw))


# ===========================================================================
# §10.4 rules 6, 7, 8 — deontic / pragmatic+axiotic / structural
# ===========================================================================


def test_refuses_deontic_replacement_without_safety_review() -> None:
    raw = _baseline_dict()
    raw["arms"]["h3ere-alt"]["replace"] = {"deontic": "corpora/permissions-alt/"}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "replaces `deontic` without `safety_review`" in message


def test_deontic_replacement_with_safety_review_is_accepted() -> None:
    raw = _baseline_dict()
    raw["arms"]["h3ere-alt"] = {
        "harness": "h3ere",
        "replace": {"deontic": "corpora/permissions-alt/"},
        "safety_review": "WA-2026-08-01 / reviewer: eric",
    }
    blocks = _baseline_blocks()
    # deontic (not axiotic) is varied now, so every held block carrying a
    # deontic contaminant has to name the confound. #986 made the conscience
    # faculty prompts visible; #997 named them individually instead of letting
    # them ride the bare `system` suffix — the list below is what the block
    # table actually says, block by block, which is the point.
    for key, entry in blocks.items():
        entry["confound_accepted"] = ["deontic"] if "deontic" in entry["contaminant"] else []
    raw["blocks"] = blocks
    validate_regime(ExperimentalRegimeV2.model_validate(raw))


def test_refuses_pragmatic_varying_with_axiotic_without_register_confound() -> None:
    raw = _baseline_dict()
    raw["arms"]["h3ere-alt"]["replace"] = {"axiotic": "corpora/values-alt/", "pragmatic": "corpora/register-alt/"}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "without `confound_accepted: register`" in message


def test_pragmatic_with_axiotic_is_accepted_when_register_is_named() -> None:
    raw = _baseline_dict()
    raw["arms"]["h3ere-alt"]["replace"] = {"axiotic": "corpora/values-alt/", "pragmatic": "corpora/register-alt/"}
    raw["confound_accepted"] = ["register"]
    # #997: the ASPDMA system message carries LANGUAGE RULES as well as its
    # axiotic line, so with pragmatic varied too its hold must name both.
    blocks = _baseline_blocks()
    blocks["action_selection_pdma.system_message"]["confound_accepted"] = ["axiotic", "pragmatic"]
    raw["blocks"] = blocks
    validate_regime(ExperimentalRegimeV2.model_validate(raw))


@pytest.mark.parametrize("class_name", ["structural", "axiomatic"])
def test_refuses_structural_or_axiomatic_in_replace(class_name: str) -> None:
    raw = _baseline_dict()
    raw["arms"]["h3ere-alt"]["replace"] = {class_name: "corpora/whatever/"}
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "under `replace:`" in message and "DIFFERENT HARNESS" in message


@pytest.mark.parametrize("class_name", ["structural", "axiomatic"])
def test_refuses_structural_or_axiomatic_in_disable(class_name: str) -> None:
    raw = _baseline_dict()
    raw["arms"]["h3ere-alt"] = {"harness": "h3ere", "disable": [class_name]}
    assert "cannot vary in-runtime at all" in _refusal(ExperimentalRegimeV2.model_validate(raw))


# ===========================================================================
# §10.4 rule 9 [M-N1] — a repeat structure with no live variance source
# ===========================================================================


def test_refuses_repeats_at_temperature_zero() -> None:
    raw = _baseline_dict()
    raw["holds"]["decoding"]["temperature"] = 0.0
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "temperature 0.0 is not a variance source" in message


def test_refuses_variance_source_none_with_n_above_one() -> None:
    raw = _baseline_dict()
    raw["repeats"]["variance_source"] = "none"
    assert "provider batching noise" in _refusal(ExperimentalRegimeV2.model_validate(raw))


def test_refuses_seed_variance_when_seed_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("CIRIS_LLM_SEED", raising=False)
    raw = _baseline_dict()
    raw["repeats"]["variance_source"] = "seeds"
    raw["repeats"]["seeds"] = list(range(20260801, 20260821))
    raw["holds"]["decoding"]["temperature"] = 0.0
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "the enumerated seeds are inert" in message


def test_seed_variance_is_accepted_when_seed_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("CIRIS_LLM_SEED", "20260802")
    raw = _baseline_dict()
    raw["repeats"]["variance_source"] = "seeds"
    raw["repeats"]["seeds"] = list(range(20260801, 20260821))
    raw["holds"]["decoding"]["temperature"] = 0.0
    raw["holds"]["decoding"]["seed"] = None
    # seed is transmitted now, so set-equality demands it be pinned too;
    # `holds.decoding.seed` would freeze every repeat, so this regime is the
    # honest shape: enumerate the seeds, pin nothing at the decoding level.
    message = _refusal(ExperimentalRegimeV2.model_validate(raw))
    assert "the enumerated seeds are inert" not in message
    assert "temperature 0.0 is not a variance source" not in message


def test_refuses_fewer_distinct_seeds_than_conversations() -> None:
    raw = _baseline_dict()
    raw["repeats"]["variance_source"] = "seeds"
    raw["repeats"]["seeds"] = [1, 1, 2]
    assert "have no variance source" in _refusal(ExperimentalRegimeV2.model_validate(raw))


# ===========================================================================
# §10.4 rule 11 — unknown class-set version
# ===========================================================================


def test_refuses_unknown_class_set_version() -> None:
    message = _refusal(_baseline(class_set_version=3))
    assert "unknown class_set_version 3" in message
    assert "never silently re-mapped" in message


def test_refuses_a_non_v2_schema_string() -> None:
    message = _refusal(_baseline(schema="ciris.ai/experimental_regime/v2-phase1"))
    assert "not 'ciris.ai/experimental_regime/v2'" in message


# ===========================================================================
# Structural hygiene the FSD states inline
# ===========================================================================


def test_refuses_locale_set_without_en() -> None:
    raw = _baseline_dict()
    raw["holds"]["locales"] = ["am"]
    assert "MANDATORY as the fidelity control" in _refusal(ExperimentalRegimeV2.model_validate(raw))


def test_refuses_contrast_without_a_declared_mde() -> None:
    raw = _baseline_dict()
    raw["repeats"]["mde"] = {}
    assert "declares no MDE" in _refusal(ExperimentalRegimeV2.model_validate(raw))


def test_refuses_contrast_naming_an_undeclared_arm() -> None:
    raw = _baseline_dict()
    raw["contrasts"]["ghost"] = "h3ere-ciris - nonexistent"
    raw["repeats"]["mde"]["ghost"] = 0.15
    assert "names undeclared arm 'nonexistent'" in _refusal(ExperimentalRegimeV2.model_validate(raw))


def test_refuses_a_regime_with_no_h3ere_arm() -> None:
    raw = _baseline_dict()
    raw["arms"] = {"bare": {"harness": "direct-provider"}, "values-ciris": {"harness": "direct-provider"}}
    raw["contrasts"] = {"values_effect": "bare - values-ciris"}
    raw["dv"] = {}
    assert "the cell v1 forgot" in _refusal(ExperimentalRegimeV2.model_validate(raw))


# ===========================================================================
# R2 reconciliation (§14 step 7)
# ===========================================================================


def test_strict_mode_refuses_until_class_annotation_is_total() -> None:
    """R2's totality rule is now 'every reachable field resolves to exactly one
    declared class'. It does not hold today — the §10.2.3 annotation pass is
    human work — so a strict regime refuses and NAMES what is missing."""
    message = _refusal(_baseline(mode="strict"))
    assert "R2 class totality" in message
    assert "annotate_classes.py" in message
    for namespace in ("string", "dma_prompt", "conscience_prompt", "template"):
        assert f"reachable {namespace} field(s) carry no class annotation" in message


def test_additive_mode_does_not_demand_class_totality() -> None:
    validate_regime(_baseline(mode="additive"))


def test_r2_reports_a_mixed_field_as_unresolved() -> None:
    """'Exactly one declared class' — ``mixed`` is not one class."""
    assert FIELD_CLASS_ANNOTATIONS["prompts.language_guidance"] is BlockClass.MIXED
    problems = "\n".join(r2_totality_problems())
    assert "['prompts.language_guidance'] resolve to 'mixed'" in problems


def test_arm_field_plan_maps_classes_to_reachable_fields() -> None:
    plan = arm_field_plan(_baseline(), "h3ere-alt")
    assert "accord.polyglot_compressed" in plan["replace"]
    assert "accord.localized" in plan["replace"]
    assert plan["disable"] == []


def test_synthesized_arm_manifests_validate_as_the_agent_would() -> None:
    """One ``ResearchOverrideManifest`` per h3ere arm, each with its OWN valid
    residue digest, each passing the same ``_validate_manifest`` the agent runs
    at startup — so a regime cannot green a set of arm manifests the agent
    would refuse ten minutes into a run."""
    from ciris_engine.logic.utils.research_overrides import compute_residue_digest

    manifests = synthesize_arm_manifests(_baseline(), validate=True)
    assert sorted(manifests) == ["h3ere-alt", "h3ere-ciris"]
    alt = manifests["h3ere-alt"]
    assert alt.residue_digest == compute_residue_digest()  # type: ignore[union-attr]
    assert alt.experiment_id == "test-976:h3ere-alt"  # type: ignore[union-attr]
    assert set(alt.overrides.corpus) >= {  # type: ignore[union-attr]
        "accord.polyglot_compressed",
        "accord.localized",
        "accord.polyglot_full",
    }
    # The shipped arm replaces nothing — it is the missing cell, not a no-op.
    assert manifests["h3ere-ciris"].overrides.corpus == {}  # type: ignore[union-attr]


def test_synthesis_refuses_a_replacement_corpus_with_a_hole_in_it(tmp_path: Path) -> None:
    (tmp_path / "corpora" / "values-alt").mkdir(parents=True)
    (tmp_path / "corpora" / "values-alt" / "accord.localized.txt").write_text("alt", encoding="utf-8")
    with pytest.raises(RegimeRefused, match="replacement for reachable field"):
        synthesize_arm_manifests(_baseline(), corpus_root=tmp_path, validate=False)


def test_disable_arm_blanks_rather_than_replaces() -> None:
    """R5 unchanged: ``h3ere-blank`` blanks all ``accord.*`` together, declared
    under ``disable:`` and never ``replace:`` — §12 assertion 2 rejects an empty
    replacement by design [I-6]."""
    raw = _baseline_dict()
    raw["arms"]["h3ere-blank"] = {"harness": "h3ere", "disable": ["axiotic"]}
    manifests = synthesize_arm_manifests(ExperimentalRegimeV2.model_validate(raw), validate=True)
    blank = manifests["h3ere-blank"]
    assert set(blank.overrides.corpus) == {  # type: ignore[union-attr]
        "accord.polyglot_compressed",
        "accord.polyglot_full",
        "accord.localized",
    }
    assert set(blank.overrides.corpus.values()) == {""}  # type: ignore[union-attr]


# ===========================================================================
# κ scaffolding (§10.2.3)
# ===========================================================================


def test_decision_relevant_boundaries_are_derived_not_listed() -> None:
    """Every class pair whose DEFAULT DISPOSITION differs, with the two §10.2.3
    names it calls foremost sorted to the front."""
    pairs = decision_relevant_boundaries()
    assert (BlockClass.AXIOTIC, BlockClass.DEONTIC) in pairs
    assert (BlockClass.AXIOTIC, BlockClass.STRUCTURAL) in pairs
    assert all(BlockClass.MIXED not in pair for pair in pairs)
    # Same default disposition -> not a decision-relevant boundary.
    assert (BlockClass.DEONTIC, BlockClass.PRAGMATIC) not in pairs


# ===========================================================================
# The FSD's own §10.3 example
# ===========================================================================


def test_the_fsd_example_manifest_refuses_and_says_why() -> None:
    """§10.3 says its example refuses (language_guidance). It refuses for four
    more reasons #976 makes machine-visible; this pins all five so a later edit
    to the example cannot quietly make it look runnable."""
    path = Path(__file__).resolve().parents[4] / "tools" / "research" / "regimes" / "torque1_v2_fsd_example.yaml"
    with pytest.raises(RegimeRefused) as excinfo:
        load_regime_v2(str(path))
    message = str(excinfo.value)
    assert "'language_guidance' carries disposition 'refuse'" in message  # §10.3's own
    assert "top_p" in message  # pinned, transmitted by no path
    assert "extra_body.reasoning" in message  # transmitted, unpinned
    assert "locale 'en' pre-registers U-row(s)" in message  # no en instrument
    # refusal by default. (`pdma.system` until #997 split it into fields; the
    # header is the one field that stayed mixed.)
    assert "'pdma_ethical.system_guidance_header' is 'mixed'" in message


def test_the_gate_runs_the_v2_refusals_when_handed_a_v2_regime(tmp_path: Path) -> None:
    """A campaign manifest must not reach the Phase-1 gate by having its tiered
    DV, holds and kills silently ignored — ``GateRegime`` has extra='ignore',
    so without this wiring a v2 file would load as a bare gate view and every
    §10.4 refusal would be skipped."""
    import yaml

    from ciris_engine.logic.utils.compose_dump import load_regime

    raw = _baseline_dict()
    raw["holds"]["decoding"]["top_p"] = 1.0  # pinned, transmitted by no path
    path = tmp_path / "regime.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(RegimeRefused, match="top_p"):
        load_regime(str(path))

    # …and a clean v2 file projects down to the Phase-1 view the gate consumes.
    clean = tmp_path / "clean.yaml"
    clean.write_text(yaml.safe_dump(_baseline_dict()), encoding="utf-8")
    view = load_regime(str(clean))
    assert view.regime_id == "test-976"
    assert view.varied_classes() == frozenset({BlockClass.AXIOTIC})


def test_the_phase1_selfcheck_regimes_still_load_as_bare_gate_views() -> None:
    """The #973 CI job must be untouched: those files carry `…/v2-phase1`."""
    from ciris_engine.logic.utils.compose_dump import load_regime

    regimes = Path(__file__).resolve().parents[4] / "tools" / "research" / "regimes"
    null_view = load_regime(str(regimes / "phase1_selfcheck_null.yaml"))
    assert null_view.varied_classes() == frozenset()
    varied_view = load_regime(str(regimes / "phase1_selfcheck_varied.yaml"))
    assert varied_view.varied_classes() == frozenset({BlockClass.AXIOTIC})
