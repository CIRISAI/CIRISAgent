"""#974 step 0 — the DEFER policy routed through the research-override lookup.

FSD/RESEARCH_PROMPT_OVERRIDES.md §11 step 0 [M-4]: the DEFER policy is the
action-tier outcome variable's own doctrine. Before #974 it existed as TWO
divergent inline Python literals (`_generate_schema_for_action` and
`get_action_guidance` in action_instruction_generator.py); no campaign about
action choice is honest while arm alternatives inherit it invisibly.

What this file proves:

1. ONE SOURCE — both code paths serve the identical routed text, loaded from
   ``prompts/action_selection_pdma.yml`` (``action_params_defer_guidance``).
2. R2-VISIBLE — the key participates in the manifest key space, so a strict
   manifest must name it and an additive manifest may target it.
3. REPLACEABLE — an active override manifest changes the COMPOSED ASPDMA
   bytes (the mutation check), and clearing it restores the baseline.
4. BASELINE UNCHANGED — without a manifest the routed text is byte-for-byte
   the pre-routing literal (the #972 goldens lock this at composition level;
   here we additionally pin the canonical head/tail of the doctrine).
"""

import json
from pathlib import Path
from typing import Iterator, List

import pytest

import ciris_engine.logic.utils.research_overrides as ro
from ciris_engine.logic.dma.action_selection.action_instruction_generator import ActionInstructionGenerator
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.types import JSONDict

DEFER_KEY = "action_selection_pdma.action_params_defer_guidance"

_REPLACEMENT = "RESEARCH-DEFER-DOCTRINE: defer_reason (string, required). Defer whenever uncertain."


@pytest.fixture
def clean_overrides(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    """Reset the override singleton around each test (env is monkeypatch-scoped)."""
    ro.reset_research_overrides()
    yield monkeypatch
    ro.reset_research_overrides()


def _activate_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, defer_text: str) -> None:
    manifest = {
        "manifest_version": "1",
        "experiment_id": "974-step0-mutation-check",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {"dma_prompt": {DEFER_KEY: defer_text}},
        "research_hashes": {},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv(ro.ENV_MANIFEST, str(path))
    monkeypatch.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()


def _yaml_defer_text() -> str:
    import yaml

    yml = Path(ro._ENGINE_ROOT) / "logic" / "dma" / "prompts" / "action_selection_pdma.yml"
    data = yaml.safe_load(yml.read_text(encoding="utf-8"))
    text = data["action_params_defer_guidance"]
    assert isinstance(text, str)
    return text


# ---------------------------------------------------------------------------
# 1. One source
# ---------------------------------------------------------------------------


def test_defer_policy_has_exactly_one_source(clean_overrides: pytest.MonkeyPatch) -> None:
    """Schema branch and guidance branch serve the SAME routed bytes — the
    pre-#974 state (two divergent literals) is the defect this locks out."""
    generator = ActionInstructionGenerator()
    schema_text = generator._generate_schema_for_action(HandlerActionType.DEFER)
    guidance_text = generator.get_action_guidance(HandlerActionType.DEFER)
    assert schema_text == guidance_text
    assert schema_text == _yaml_defer_text()


def test_defer_policy_source_is_no_longer_a_python_literal(clean_overrides: pytest.MonkeyPatch) -> None:
    """The doctrine's prose must not survive as an inline literal in the
    generator module — routing means the text MOVED, not that it was copied."""
    source = (
        Path(ro._ENGINE_ROOT) / "logic" / "dma" / "action_selection" / "action_instruction_generator.py"
    ).read_text(encoding="utf-8")
    assert "DEFER is ONLY for situations" not in source
    assert "DO NOT DEFER for" not in source


# ---------------------------------------------------------------------------
# 2. R2-visible
# ---------------------------------------------------------------------------


def test_defer_key_participates_in_the_manifest_key_space(clean_overrides: pytest.MonkeyPatch) -> None:
    assert DEFER_KEY in ro._required_dma_prompt_keys()
    skeleton = ro.strict_manifest_skeleton()
    assert DEFER_KEY in skeleton["overrides"]["dma_prompt"]


def test_baseline_manifest_round_trips_the_live_defer_text(clean_overrides: pytest.MonkeyPatch) -> None:
    baseline = ro.baseline_manifest()
    assert baseline["overrides"]["dma_prompt"][DEFER_KEY] == _yaml_defer_text()


# ---------------------------------------------------------------------------
# 3. Replaceable — the mutation check, at composed-bytes level
# ---------------------------------------------------------------------------


def _composed_aspdma_user_content(messages: List[JSONDict]) -> str:
    user = [m for m in messages if m.get("role") == "user"]
    assert user, "ASPDMA composed no user message"
    content = user[-1].get("content", "")
    if isinstance(content, list):  # multimodal form
        return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return str(content)


@pytest.mark.asyncio
async def test_override_manifest_changes_composed_aspdma_bytes(
    clean_overrides: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An additive manifest replacing ONLY the DEFER key must change the
    composed ASPDMA user message; removing it must restore the baseline
    byte-for-byte. This is §11 step 0's replaceability proof."""
    from tests.ciris_engine.logic.dma.compose_golden import capture_via_evaluate

    baseline_messages = await capture_via_evaluate("aspdma")
    baseline_content = _composed_aspdma_user_content(baseline_messages)
    assert "DEFER is ONLY for situations the agent cannot resolve alone" in baseline_content
    assert _REPLACEMENT not in baseline_content

    _activate_manifest(clean_overrides, tmp_path, _REPLACEMENT)
    overridden_messages = await capture_via_evaluate("aspdma")
    overridden_content = _composed_aspdma_user_content(overridden_messages)
    assert _REPLACEMENT in overridden_content
    assert "DEFER is ONLY for situations the agent cannot resolve alone" not in overridden_content

    clean_overrides.delenv(ro.ENV_MANIFEST)
    ro.reset_research_overrides()
    restored_messages = await capture_via_evaluate("aspdma")
    assert restored_messages == baseline_messages


# ---------------------------------------------------------------------------
# 4. Baseline unchanged (the #972 goldens lock full composition; pin the
#    doctrine's canonical head and tail here so a partial YAML edit is loud)
# ---------------------------------------------------------------------------


def test_routed_defer_text_is_the_pre_routing_doctrine(clean_overrides: pytest.MonkeyPatch) -> None:
    text = ActionInstructionGenerator()._generate_schema_for_action(HandlerActionType.DEFER)
    assert text.startswith("DEFER: defer_reason (string, required), defer_until (ISO 8601 timestamp, optional)\n")
    assert text.endswith("use SPEAK to explain the error to the user.")
    assert "⚠️ DEFER is ONLY for situations the agent cannot resolve alone:" in text
    assert "❌ DO NOT DEFER for:" in text
