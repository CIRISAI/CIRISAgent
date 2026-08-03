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


# ---------------------------------------------------------------------------
# Step 1 — the ASPDMA user-message template (context_integration)
# ---------------------------------------------------------------------------

ASPDMA_USER_KEY = "action_selection_pdma.context_integration"

_USER_TEMPLATE_REPLACEMENT = (
    "RESEARCH-ASPDMA-USER: pick one of {action_options_str}. Thought: {original_thought_content}"
)


def test_aspdma_user_template_key_is_r2_visible(clean_overrides: pytest.MonkeyPatch) -> None:
    assert ASPDMA_USER_KEY in ro._required_dma_prompt_keys()
    assert ASPDMA_USER_KEY in ro.strict_manifest_skeleton()["overrides"]["dma_prompt"]


def test_aspdma_user_template_source_is_the_yaml_not_python(clean_overrides: pytest.MonkeyPatch) -> None:
    """The ~90-line doctrine moved; it must not survive as a Python literal."""
    source = (
        Path(ro._ENGINE_ROOT) / "logic" / "dma" / "action_selection" / "context_builder.py"
    ).read_text(encoding="utf-8")
    assert "Your task is to determine the single most appropriate HANDLER ACTION" not in source
    assert "SCHEMA REMINDER" not in source

    import yaml

    data = yaml.safe_load(
        (Path(ro._ENGINE_ROOT) / "logic" / "dma" / "prompts" / "action_selection_pdma.yml").read_text(
            encoding="utf-8"
        )
    )
    template = data["context_integration"]
    assert "Your task is to determine the single most appropriate HANDLER ACTION" in template
    # The slot structure is structural and must survive the move.
    for slot in (
        "{action_options_str}",
        "{action_parameter_schemas}",
        "{original_task_str}",
        "{original_thought_content}",
        "{system_snapshot_context_str}",
        "{idma_summary_str}",
    ):
        assert slot in template, f"routed template lost structural slot {slot}"


@pytest.mark.asyncio
async def test_override_manifest_changes_composed_aspdma_user_template_bytes(
    clean_overrides: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Step 1's replaceability proof: an additive manifest replacing ONLY
    context_integration changes the composed ASPDMA user message; the routed
    template keeps its slots, so the call site's values still interpolate."""
    from tests.ciris_engine.logic.dma.compose_golden import capture_via_evaluate

    manifest = {
        "manifest_version": "1",
        "experiment_id": "974-step1-mutation-check",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {"dma_prompt": {ASPDMA_USER_KEY: _USER_TEMPLATE_REPLACEMENT}},
        "research_hashes": {},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    clean_overrides.setenv(ro.ENV_MANIFEST, str(path))
    clean_overrides.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()

    messages = await capture_via_evaluate("aspdma")
    content = _composed_aspdma_user_content(messages)
    assert content.startswith("RESEARCH-ASPDMA-USER: pick one of ")
    # Slot values interpolated by the call site, not baked into the template:
    assert "speak" in content
    assert "Should the agent reply with a summary of the weather report?" in content
    assert "SCHEMA REMINDER" not in content


# ---------------------------------------------------------------------------
# Step 2 — the DSDMA user message (dsdma_base.context_integration goes live)
# ---------------------------------------------------------------------------

DSDMA_USER_KEY = "dsdma_base.context_integration"
_LIVE_DSDMA_SLOT = "{full_snapshot_and_profile_context_str}"


def _make_dsdma() -> object:
    from unittest.mock import Mock

    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

    return BaseDSDMA(domain_name="golden_domain", service_registry=Mock())


def test_dsdma_user_template_is_live_and_carries_the_slot_contract(
    clean_overrides: pytest.MonkeyPatch,
) -> None:
    """The field existed pre-#974 but was DEAD (never rendered). It is live
    now, and the base template must carry the live structural slot."""
    assert DSDMA_USER_KEY in ro._required_dma_prompt_keys()
    import yaml

    data = yaml.safe_load((ro._DMA_PROMPTS_DIR / "dsdma_base.yml").read_text(encoding="utf-8"))
    assert _LIVE_DSDMA_SLOT in data["context_integration"]
    # And the inline f-string is gone from Python.
    source = (Path(ro._ENGINE_ROOT) / "logic" / "dma" / "dsdma_base.py").read_text(encoding="utf-8")
    assert 'f"{full_snapshot_and_profile_context_str}\\nEvaluate this thought' not in source


def test_dsdma_stale_localized_template_falls_back_to_base_doctrine(
    clean_overrides: pytest.MonkeyPatch,
) -> None:
    """All 28 localized dsdma_base.yml files carry translations of the DEAD
    pre-#974 template (no live slot). Routing must NOT silently activate them
    — that would be a material non-base-locale prompt change, not a routing.
    They fall back to the base-locale doctrine, exactly what the inline
    f-string served them."""
    dma = _make_dsdma()
    dma._explicit_language = "am"  # localized dsdma_base.yml exists and is stale
    loader, template_data = dma._resolve_user_template()
    assert loader.language == "en"
    assert template_data.context_integration is not None
    assert _LIVE_DSDMA_SLOT in template_data.context_integration


@pytest.mark.asyncio
async def test_override_manifest_changes_composed_dsdma_user_bytes(
    clean_overrides: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Step 2's replaceability proof. An explicit research override is honored
    verbatim even though it does not carry the live slot — the stale-template
    guard must never eat a manifest replacement."""
    from tests.ciris_engine.logic.dma.compose_golden import capture_via_evaluate

    baseline = await capture_via_evaluate("dsdma")
    baseline_user = str(baseline[-1]["content"])
    assert "Evaluate this thought for the 'golden_domain' domain:" in baseline_user

    manifest = {
        "manifest_version": "1",
        "experiment_id": "974-step2-mutation-check",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {"dma_prompt": {DSDMA_USER_KEY: "RESEARCH-DSDMA-USER: {thought_content_str}"}},
        "research_hashes": {},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    clean_overrides.setenv(ro.ENV_MANIFEST, str(path))
    clean_overrides.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()

    overridden = await capture_via_evaluate("dsdma")
    overridden_user = str(overridden[-1]["content"])
    # thought_content_str is str(ThoughtContent) — assert the frame replaced
    # and the slot still interpolated, without pinning the repr format.
    assert overridden_user.startswith("RESEARCH-DSDMA-USER: ")
    assert "Should the agent reply with a summary of the weather report?" in overridden_user
    assert "Evaluate this thought for the" not in overridden_user

    clean_overrides.delenv(ro.ENV_MANIFEST)
    ro.reset_research_overrides()
    restored = await capture_via_evaluate("dsdma")
    assert restored == baseline


# ---------------------------------------------------------------------------
# Step 3 — the CORE IDENTITY blocks (prompts.identity_block, string namespace)
# ---------------------------------------------------------------------------

IDENTITY_KEY = "prompts.identity_block"


def test_identity_block_has_one_routed_source(clean_overrides: pytest.MonkeyPatch) -> None:
    """Three inline copies collapsed into one keyed source. The literal must
    not survive in either DMA module, and the helper must render the exact
    pre-routing bytes."""
    from ciris_engine.logic.formatters import format_core_identity_block

    for rel in ("logic/dma/dsdma_base.py", "logic/dma/action_selection_pdma.py"):
        source = (Path(ro._ENGINE_ROOT) / rel).read_text(encoding="utf-8")
        assert "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===" not in source, rel

    block = format_core_identity_block("golden_agent", "A test agent", "Tester", language="en")
    assert block == (
        "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===\n"
        "Agent: golden_agent\n"
        "Description: A test agent\n"
        "Role: Tester\n"
        "============================================"
    )


def test_identity_block_key_is_reachable_and_r2_visible(clean_overrides: pytest.MonkeyPatch) -> None:
    assert IDENTITY_KEY in ro.scan_reachable_string_keys()
    assert IDENTITY_KEY in ro.DECLARED_STRING_KEY_SPACE
    assert IDENTITY_KEY in ro.strict_manifest_skeleton()["overrides"]["string"]


def test_identity_block_falls_back_to_base_bytes_for_untranslated_locales(
    clean_overrides: pytest.MonkeyPatch,
) -> None:
    """No bundle but en carries the key yet — every locale must serve the
    exact English bytes the inline literals produced."""
    from ciris_engine.logic.formatters import format_core_identity_block

    en = format_core_identity_block("a", "d", "r", language="en")
    for lang in ("am", "yo", "zh"):
        assert format_core_identity_block("a", "d", "r", language=lang) == en


@pytest.mark.asyncio
async def test_override_manifest_changes_composed_identity_bytes(
    clean_overrides: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Step 3's replaceability proof, at composed-bytes level, in BOTH DMAs
    that render the block (DSDMA system message + ASPDMA system message)."""
    from tests.ciris_engine.logic.dma.compose_golden import capture_via_evaluate

    manifest = {
        "manifest_version": "1",
        "experiment_id": "974-step3-mutation-check",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {"string": {IDENTITY_KEY: "RESEARCH-IDENTITY agent={agent_id} role={role}"}},
        "research_hashes": {},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    clean_overrides.setenv(ro.ENV_MANIFEST, str(path))
    clean_overrides.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()

    for step, expected_agent in (("dsdma", "golden_agent"), ("aspdma", "golden_agent")):
        messages = await capture_via_evaluate(step)
        joined = "\n---\n".join(str(m["content"]) for m in messages)
        assert f"RESEARCH-IDENTITY agent={expected_agent}" in joined, step
        assert "=== CORE IDENTITY - THIS IS WHO YOU ARE! ===" not in joined, step


# ---------------------------------------------------------------------------
# Step 5 — the conscience repeated-SPEAK guidance (string namespace)
# ---------------------------------------------------------------------------

SPEAK_GUIDANCE_KEY = "conscience.repeated_speak_guidance"


def test_repeated_speak_guidance_is_routed_and_baseline_stable(
    clean_overrides: pytest.MonkeyPatch,
) -> None:
    from ciris_engine.logic.conscience.action_sequence_conscience import _repeated_speak_guidance

    assert SPEAK_GUIDANCE_KEY in ro.scan_reachable_string_keys()
    assert SPEAK_GUIDANCE_KEY in ro.DECLARED_STRING_KEY_SPACE
    text = _repeated_speak_guidance()
    assert text == (
        "You already spoke in response to this task, do not speak twice unless your "
        "first utterance was so grossly inadequate you must correct yourself, and if so, "
        "start with, 'I apologize'"
    )
    # The doctrine moved — no inline copy left in the module.
    source = (
        Path(ro._ENGINE_ROOT) / "logic" / "conscience" / "action_sequence_conscience.py"
    ).read_text(encoding="utf-8")
    assert "so grossly inadequate" not in source


def test_override_manifest_replaces_repeated_speak_guidance(
    clean_overrides: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ciris_engine.logic.conscience.action_sequence_conscience import _repeated_speak_guidance

    manifest = {
        "manifest_version": "1",
        "experiment_id": "974-step5-mutation-check",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {"string": {SPEAK_GUIDANCE_KEY: "RESEARCH-SPEAK-GUIDANCE"}},
        "research_hashes": {},
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    clean_overrides.setenv(ro.ENV_MANIFEST, str(path))
    clean_overrides.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()
    assert _repeated_speak_guidance() == "RESEARCH-SPEAK-GUIDANCE"

    clean_overrides.delenv(ro.ENV_MANIFEST)
    ro.reset_research_overrides()
    assert _repeated_speak_guidance().startswith("You already spoke in response to this task")
