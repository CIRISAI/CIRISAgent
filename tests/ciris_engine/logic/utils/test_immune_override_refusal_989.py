"""#989 — refuse an override the layer cannot apply, rather than logging a lie.

``BaseDMA._load_prompts`` opens the prompt YAML directly with ``yaml.safe_load``;
``_apply_research_overrides`` is reached only from
``DMAPromptLoader.load_prompt_template``. Fields an evaluator consumes through
its own ``self.prompts`` therefore never see the manifest — while the loader
still logs ``replaced [...]`` for the template's applicable keys.

Every other coverage gap found in this window UNDER-claims: a key the gate
cannot see. This one OVER-claims: a replacement the log asserts and the bytes
deny. A campaign could swap a value, read a success line, and run the CIRIS
value it meant to replace. So the manifest refuses.
"""

from __future__ import annotations

import json

import pytest

from ciris_engine.logic.utils import research_overrides as ro
from ciris_engine.logic.utils.research_overrides import (
    OVERRIDE_IMMUNE_DMA_PROMPT_KEYS,
    ResearchOverrideError,
)


def _manifest(tmp_path, dma_prompt: dict) -> str:
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
    return str(path)


@pytest.mark.parametrize("key", OVERRIDE_IMMUNE_DMA_PROMPT_KEYS)
def test_every_immune_key_is_refused(key: str, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Each measured-immune key refuses by name, with the mechanism stated —
    an operator who set it must learn WHY it cannot work, not just that it
    was rejected."""
    monkeypatch.setenv(ro.ENV_MANIFEST, _manifest(tmp_path, {key: "REPLACED"}))
    monkeypatch.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()
    try:
        with pytest.raises(ResearchOverrideError) as exc:
            ro.get_active_overrides()
        message = str(exc.value)
        assert key in message
        assert "BaseDMA._load_prompts" in message, "the refusal must name the mechanism"
        assert "#989" in message
    finally:
        ro.reset_research_overrides()


def test_an_applicable_key_is_still_accepted(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal must be surgical. `action_params_defer_guidance` routes
    through DMAPromptLoader (#974 step 0 put it there and proved replaceability),
    so it must NOT be caught — a blanket template-level refusal would undo the
    DEFER policy's routing, which is TORQUE arm-D's precondition."""
    key = "action_selection_pdma.action_params_defer_guidance"
    assert key not in OVERRIDE_IMMUNE_DMA_PROMPT_KEYS
    monkeypatch.setenv(ro.ENV_MANIFEST, _manifest(tmp_path, {key: "REPLACED"}))
    monkeypatch.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()
    try:
        manifest = ro.get_active_overrides()
        assert manifest is not None
        assert manifest.overrides.dma_prompt[key] == "REPLACED"
    finally:
        ro.reset_research_overrides()


def test_the_inventory_is_not_empty_and_names_the_action_tier() -> None:
    """Ten of the thirteen sit in action_selection_pdma — the tier where an
    axiotic experiment's dependent variable is decided. If this assertion ever
    fails because the inventory shrank, #989 option 1 landed and the tuple must
    be re-measured, not merely edited."""
    assert len(OVERRIDE_IMMUNE_DMA_PROMPT_KEYS) == 13
    aspdma = [k for k in OVERRIDE_IMMUNE_DMA_PROMPT_KEYS if k.startswith("action_selection_pdma.")]
    assert len(aspdma) == 10


def test_immune_keys_all_exist_in_their_templates() -> None:
    """A stale inventory naming a field that no longer exists would refuse a
    key an operator cannot even set — the drift check R1 performs for the
    manifest, applied to this list."""
    from ciris_engine.logic.dma.prompt_loader import get_prompt_loader

    loader = get_prompt_loader("en")
    for key in OVERRIDE_IMMUNE_DMA_PROMPT_KEYS:
        template, _, field = key.partition(".")
        collection = loader.load_prompt_template(template)
        assert hasattr(collection, field), f"{key} names a field {template} no longer defines"
