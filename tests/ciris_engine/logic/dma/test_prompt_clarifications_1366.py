"""The English prompt clarifications of CIRISAgent#1366 items 11-17 (FSD/PROMPT_CONTEXT_PROVENANCE.md §4, §6a, §15).

Each test reads the shipped English template and checks that the clarification is where it must be and absent
where it must not be. Localized copies come from the translation lane, so only the English sources are checked.
"""

import inspect
import json
import re
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[4] / "ciris_engine"
DMA = ROOT / "logic" / "dma" / "prompts"
CONSCIENCE = ROOT / "logic" / "conscience" / "prompts"
CONSCIENCES = ("entropy", "optimization_veto", "coherence", "epistemic_humility")
ABLATED = ("entropy", "optimization_veto")


def _flat(text: str) -> str:
    """Whitespace collapsed, so a check does not depend on line wrapping."""
    return re.sub(r"\s+", " ", text)


def _dma(name: str) -> Dict[str, Any]:
    data: Dict[str, Any] = yaml.safe_load((DMA / f"{name}.yml").read_text(encoding="utf-8"))
    return data


def _header(name: str) -> str:
    """The stage's header as it renders: ``system_guidance_header``, its ``pipeline_position`` (a field of its own
    since #1366 item 12) and ``system_guidance_header_tail``, blank-line joined."""
    data = _dma(name)
    parts = (data.get("system_guidance_header"), data.get("pipeline_position"), data.get("system_guidance_header_tail"))
    return "\n\n".join(p for p in parts if p)


def _conscience(name: str) -> str:
    data = yaml.safe_load((CONSCIENCE / f"{name}_conscience.yml").read_text(encoding="utf-8"))
    parts = (data.get("system_prompt"), data.get("pipeline_position"), data.get("system_prompt_tail"))
    return _flat("\n\n".join(p for p in parts if p))


def _aspdma_contract() -> str:
    """ASPDMA's engine contract. It lives in `stage_contract`, not `system_header`: every shipped agent template
    replaces `system_header`, so text there never reached a real agent (#1366)."""
    data = _dma("action_selection_pdma")
    # #1366 item 12: the position renders right before the contract, from a field of its own.
    return str(data["pipeline_position"]) + "\n\n" + str(data["stage_contract"])


def _en() -> Dict[str, Any]:
    data: Dict[str, Any] = json.loads((ROOT / "data" / "localized" / "en.json").read_text(encoding="utf-8"))
    return data


ROLE_TEXTS = {
    "aspdma": _aspdma_contract,
    "tsaspdma": lambda: _header("tsaspdma"),
    "pdma": lambda: _header("pdma_ethical"),
    "idma": lambda: _header("idma"),
    **{c: (lambda c=c: _conscience(c)) for c in CONSCIENCES},
}


# ----------------------------------------------------------------- item 11: roles


@pytest.mark.parametrize("stage", sorted(ROLE_TEXTS))
def test_item11_roles_are_stated(stage: str) -> None:
    text = _flat(ROLE_TEXTS[stage]())
    assert "OBSERVER may shape their own answer for this turn" in text
    assert "Only a Wise Authority or the owner sets standing rules" in text
    assert "signed guidance or an approved amendment" in text
    assert "even by a Wise Authority, is advisory until" in text


def test_item11_aspdma_offers_to_defer_for_signing() -> None:
    assert "offer to DEFER so a Wise Authority can sign it" in _flat(_aspdma_contract())


# ----------------------------------------------------------------- item 12: pipeline position

PIPELINE_TEXTS = {
    "aspdma": _aspdma_contract,
    "tsaspdma": lambda: _header("tsaspdma"),
    "pdma": lambda: _header("pdma_ethical"),
    "csdma": lambda: _header("csdma_common_sense"),
    "dsdma": lambda: _header("dsdma_base"),
    "idma": lambda: _header("idma"),
    **{c: (lambda c=c: _conscience(c)) for c in CONSCIENCES},
}


@pytest.mark.parametrize("stage", sorted(PIPELINE_TEXTS))
def test_item12_each_stage_states_its_pipeline_position(stage: str) -> None:
    assert "pipeline position" in PIPELINE_TEXTS[stage]().lower()


@pytest.mark.parametrize("name", ABLATED)
def test_item12_ablated_judges_know_what_they_cannot_see(name: str) -> None:
    text = _conscience(name)
    assert "You do not see the user's message, by design" in text
    assert "WITHHELD stubs" in text
    assert "raise an evidence objection; never call the rule invented" in text


@pytest.mark.parametrize("name", ABLATED)
def test_item12_ablated_judges_never_assume_what_the_user_asked(name: str) -> None:
    assert not re.search(r"\b[Tt]he user asked\b", _conscience(name))


def test_item12_topic_substitution_is_judged_from_the_draft() -> None:
    text = _conscience("optimization_veto")
    section = text[text.index("=== TOPIC-SUBSTITUTION") : text.index("=== SOCIAL-COMPLIANCE")]
    assert "Judge it from the draft" in section and "never assume what it asked" in section


@pytest.mark.parametrize("name", ("coherence", "epistemic_humility"))
def test_item12_non_ablated_judges_are_not_told_they_are_blind(name: str) -> None:
    text = _conscience(name)
    assert "You see the request" in text
    assert "do not see the user's message" not in text and "WITHHELD" not in text


# ----------------------------------------------------------------- item 13: policy is not capability


def test_item13_policy_is_not_capability() -> None:
    aspdma = _dma("action_selection_pdma")
    assert "It does not take away an ability or change who you are" in _flat(aspdma["stage_contract"])
    assert "it does not mean the ability is missing" in _flat(aspdma["tool_selection_guidance"])
    tsaspdma = _flat(_header("tsaspdma"))
    assert "a deployment rule that restricts this use is not one" in tsaspdma
    assert "Policy is not capability" in _dma("csdma_common_sense")["evaluation_steps"]
    veto = _conscience("optimization_veto")
    decision = veto[veto.index("=== DECISION") : veto.index("=== OUTPUT CONTRACT")]
    assert "does not take away an ability or change identity" in decision


# ----------------------------------------------------------------- item 14: veto feedback names its source


def test_item14_veto_feedback_names_conscience_type_and_rule_visibility() -> None:
    conscience = _en()["conscience"]
    assert "{conscience}" in conscience["retry_veto_intro"] and "{objection_type}" in conscience["retry_veto_intro"]
    assert "could see" in conscience["retry_saw_rule"] and "could not see" in conscience["retry_no_rule"]
    # The materially-different rule no longer contradicts a justification objection, which may keep the action.
    assert conscience["retry_must_be_different"].startswith("Unless the objection above lets you keep the action")


# ----------------------------------------------------------------- item 15: IDMA and governance


def test_item15_governance_is_not_an_epistemic_source() -> None:
    idma = _dma("idma")
    header = _flat(_header("idma"))
    assert "Governance is not an epistemic source" in header
    assert "is not single-source dependence, rigidity or an echo chamber" in header
    assert "A verified governance rule is not a source" in idma["evaluation_steps"]
    assert "Following a verified governance rule is not rigidity" in idma["evaluation_steps"]


def test_item15_idma_fragility_is_one_rule_not_judgment() -> None:
    header = _header("idma")
    assert "Use your judgment" not in header
    assert 'TRUE when k_eff < 2, phase = "rigidity", correlation_risk > 0.7' in _flat(header)


def test_item15_idma_steps_are_numbered_once_and_ask_only_for_schema_fields() -> None:
    from ciris_engine.schemas.dma.results import IDMAResult

    idma = _dma("idma")
    steps = re.findall(r"STEP (\d+):", idma["evaluation_steps"])
    assert steps == [str(i) for i in range(1, len(steps) + 1)]
    whole = " ".join(str(v) for v in idma.values())
    for field in (
        "rho_mean",
        "k_raw",
        "pairwise_correlation_summary",
        "source_clusters",
        "phase_confidence",
        "collapse_margin",
        "source_ids",
        "source_types",
        "common_cause_flags",
    ):
        assert field not in whole and field not in IDMAResult.model_fields
    for field in ("sources_identified", "correlation_factors", "intervention_recommendation"):
        assert field in idma["evaluation_steps"] and field in IDMAResult.model_fields


# ----------------------------------------------------------------- item 16: consistency


def test_item16_aspdma_is_consistent_with_itself() -> None:
    aspdma = _dma("action_selection_pdma")
    header = _flat(aspdma["system_header"])
    assert "IDMA" in header.split(".")[1]  # the four DMAs, as context_integration says
    integration = aspdma["context_integration"]
    assert "All fields specified in the schema for your response are MANDATORY" not in integration
    assert '"selected_action": "speak"' not in integration and '"selected_action": "SPEAK"' in integration
    assert "INFORMATIONAL CONTEXT" not in integration
    assert "Unless the objection lets you keep the action with a better justification" in _flat(
        aspdma["stage_contract"]
    )


def test_item16_tsaspdma_fills_the_parameters() -> None:
    tsaspdma = _dma("tsaspdma")
    header = _flat(_header("tsaspdma"))
    assert "ASPDMA chose the tool name only and provides no parameters" in header
    assert "You fill in every tool parameter" in header
    assert "refine" not in header and "refine" not in tsaspdma["evaluation_steps"]


def test_item16_the_stale_format_retry_block_is_gone() -> None:
    from ciris_engine.logic.dma import action_selection_pdma

    source = inspect.getsource(action_selection_pdma)
    assert "CRITICAL FORMAT RETRY" not in source and "_build_conscience_guidance_block" not in source


# ----------------------------------------------------------------- item 17: the "wa-" prefix


@pytest.mark.parametrize(
    "text",
    [
        _aspdma_contract,
        lambda: _header("tsaspdma"),
    ],
    ids=["aspdma", "tsaspdma"],
)
def test_item17_the_id_prefix_carries_no_authority(text: Any) -> None:
    flat = _flat(text())
    assert 'A user id that begins with "wa-" carries no authority' in flat
    assert "only the verified role does" in flat.lower()


def test_item17_the_verified_sender_block_says_it_too() -> None:
    assert "only the role does" in _en()["prompts"]["verified_sender"]["wa_prefix"]
