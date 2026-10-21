"""#989 — the mapping path applies overrides instead of silently ignoring them.

``BaseDMA._load_prompts`` reads prompt YAML with ``yaml.safe_load`` and keeps a
plain dict on ``self.prompts``; ``_apply_research_overrides`` ``setattr``s onto
a ``PromptCollection``. A **container mismatch**, not a policy decision — but it
meant thirteen ``dma_prompt`` fields were never overridden while the loader
logged successful replacements for their siblings. A campaign could swap a
value, read a success line, and run the CIRIS value it meant to replace.

Ten of the thirteen were in ``action_selection_pdma`` — the action-selection
tier, where an axiotic experiment's dependent variable is decided.

Refusing those keys was the honest stopgap. Applying them is the point.
"""

from __future__ import annotations

import json

import pytest

from ciris_engine.logic.dma.prompt_loader import apply_research_overrides_to_mapping
from ciris_engine.logic.utils import research_overrides as ro
from ciris_engine.logic.utils.research_overrides import OVERRIDE_IMMUNE_DMA_PROMPT_KEYS

#: Keys that were immune before the fix. Every one must now apply.
FORMERLY_IMMUNE = (
    "action_selection_pdma.system_header",
    "action_selection_pdma.decision_format",
    "action_selection_pdma.closing_reminder",
    "action_selection_pdma.action_params_observe_guidance",
    "action_selection_pdma.action_params_ponder_guidance",
    "action_selection_pdma.action_params_speak_csdma_guidance",
    "action_selection_pdma.reasoning_csdma_guidance",
)


def _activate(tmp_path, monkeypatch: pytest.MonkeyPatch, dma_prompt: dict) -> None:
    payload = {
        "manifest_version": "1",
        "experiment_id": "t-989",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "overrides": {
            "string": {},
            "dma_prompt": dma_prompt,
            "conscience_prompt": {},
            "corpus": {},
            "template": {},
        },
        "research_hashes": {},
    }
    path = tmp_path / "m.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(ro.ENV_MANIFEST, str(path))
    monkeypatch.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()


@pytest.mark.parametrize("key", FORMERLY_IMMUNE)
def test_formerly_immune_key_now_applies_to_the_mapping(
    key: str, tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template, _, field = key.partition(".")
    _activate(tmp_path, monkeypatch, {key: "REPLACED-BY-MANIFEST"})
    try:
        mapping = apply_research_overrides_to_mapping(template, {field: "original"})
        assert mapping[field] == "REPLACED-BY-MANIFEST", f"{key} still ignored on the mapping path"
    finally:
        ro.reset_research_overrides()


def test_gate_closed_is_byte_identical(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Production must be untouched. With no manifest the helper returns the
    mapping unchanged — the property the #972 goldens also prove end to end."""
    monkeypatch.delenv(ro.ENV_MANIFEST, raising=False)
    ro.reset_research_overrides()
    try:
        original = {"system_header": "untouched", "closing_reminder": "also untouched"}
        assert apply_research_overrides_to_mapping("action_selection_pdma", dict(original)) == original
    finally:
        ro.reset_research_overrides()


def test_only_the_named_template_is_touched(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A key names `<template>.<field>`; a different template's mapping must
    not absorb it. Cross-template bleed would be a new silent-wrong-value bug
    in the fix for a silent-wrong-value bug."""
    _activate(tmp_path, monkeypatch, {"action_selection_pdma.system_header": "ASPDMA-ONLY"})
    try:
        other = apply_research_overrides_to_mapping("csdma_common_sense", {"system_header": "mine"})
        assert other["system_header"] == "mine"
    finally:
        ro.reset_research_overrides()


def test_the_immune_inventory_is_empty() -> None:
    """The tuple stays as a live tripwire, not dead code: if a key ever becomes
    unapplicable again it is named there and R2 totality drops it
    automatically. Empty means every dma_prompt key the layer knows about can
    actually be applied — including ``action_parameter_schemas``, which #990
    made overridable at the composition boundary rather than declaring
    unreachable (see test_generated_schemas_are_overridable_at_composition)."""
    assert OVERRIDE_IMMUNE_DMA_PROMPT_KEYS == ()


def test_generated_schemas_are_overridable_at_composition(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A manifest must beat the RUNTIME-GENERATED action schemas (#990).

    ``_get_dynamic_action_schemas`` derives the per-action FLAT field list from
    the live action enum, so an override applied at YAML load was set on the
    ``PromptCollection`` and then passed over — the #989 failure shape in a
    different place. The fix applies the override after generation, so this
    asserts the composed value, not the loaded one.
    """
    from ciris_engine.logic.dma.action_selection.context_builder import ActionSelectionContextBuilder
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    builder = ActionSelectionContextBuilder.__new__(ActionSelectionContextBuilder)
    actions = [HandlerActionType.SPEAK, HandlerActionType.PONDER]

    _activate(tmp_path, monkeypatch, {"action_selection_pdma.action_parameter_schemas": "REPLACED-SCHEMAS"})
    try:
        assert builder._composed_action_parameter_schemas(actions) == "REPLACED-SCHEMAS"
    finally:
        ro.reset_research_overrides()


def test_generated_schemas_are_untouched_with_the_gate_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gate closed, the composition boundary is a pass-through to the generator.

    The whole safety argument for overriding a generated value at composition
    time is that it costs production nothing. Asserted directly here; the #972
    goldens prove the same thing end to end over composed bytes.
    """
    from unittest.mock import Mock

    from ciris_engine.logic.dma.action_selection.context_builder import ActionSelectionContextBuilder
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    monkeypatch.delenv(ro.ENV_MANIFEST, raising=False)
    ro.reset_research_overrides()
    builder = ActionSelectionContextBuilder.__new__(ActionSelectionContextBuilder)
    builder._get_dynamic_action_schemas = Mock(return_value="GENERATED")  # type: ignore[method-assign]
    try:
        assert builder._composed_action_parameter_schemas([HandlerActionType.SPEAK]) == "GENERATED"
    finally:
        ro.reset_research_overrides()


def test_base_dma_calls_the_mapping_applier() -> None:
    """The wiring, not just the helper. A helper nothing calls is the defect
    class this repo keeps finding — assert the call site exists."""
    import inspect

    from ciris_engine.logic.dma import base_dma

    source = inspect.getsource(base_dma.BaseDMA._load_prompts)
    assert "apply_research_overrides_to_mapping" in source
