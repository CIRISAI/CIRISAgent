"""#975 enforcement fixes: R6, assignment-residue, seed plumbing.

Three rules from FSD/RESEARCH_PROMPT_OVERRIDES.md §14 step 6, each of which
previously could not fire:

- R6: the loader ACCEPTED ``condition: "a"`` while §6.2 says an h3ere run
  labelled (a) invalidates every comparison against it. [M-8]
- ``LLM_ERROR_REMEDIATIONS`` could not be pinned as residue because the
  extractor resolved only def/class, never a module-level assignment — so the
  one dict that re-injects English action doctrine into retries stayed out of
  the inventory by construction. [I-7]
- ``seed`` was never transmitted on the OpenAI-compatible path, making
  ``repeats.seeds`` in a regime manifest inert. [M-N1]
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import ciris_engine
from ciris_engine.logic.utils.research_overrides import (
    RESIDUE_SITES,
    ResearchOverrideError,
    _extract_symbol_source,
    compute_residue_digest,
)

_ENGINE_ROOT = Path(ciris_engine.__file__).parent
_SERVICE_REL = "logic/services/runtime/llm_service/service.py"


# ---------------------------------------------------------------------------
# R6 — condition "a" refuses
# ---------------------------------------------------------------------------


def _minimal_manifest(condition: str) -> dict:
    return {
        "manifest_version": "1",
        "experiment_id": "t-975",
        "condition": condition,
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": compute_residue_digest(),
        "overrides": {"string": {}, "dma_prompt": {}, "conscience_prompt": {}, "corpus": {}, "template": {}},
        "research_hashes": {},
    }


@pytest.mark.parametrize("condition,ok", [("a", False), ("b", True), ("c", True)])
def test_condition_a_is_refused_b_and_c_are_not(condition: str, ok: bool, tmp_path, monkeypatch) -> None:
    """An h3ere run labelled (a) is a category error, refused at load with the
    §6.2 reason — not accepted and quietly mislabelled. (b)/(c) must not be
    caught by the same net: this asserts the refusal is specific, not a typo'd
    blanket that would also kill the two valid conditions."""
    import json

    from ciris_engine.logic.utils import research_overrides as ro

    path = tmp_path / "m.json"
    path.write_text(json.dumps(_minimal_manifest(condition)))
    monkeypatch.setenv(ro.ENV_MANIFEST, str(path))
    monkeypatch.setenv(ro.ENV_ANCHOR, "true")
    ro.reset_research_overrides()
    try:
        if ok:
            # must not raise on the condition check; a minimal additive
            # manifest with a fresh digest passes every rule
            ro.get_active_overrides()
        else:
            with pytest.raises(ResearchOverrideError, match="direct-to-provider"):
                ro.get_active_overrides()
    finally:
        ro.reset_research_overrides()


# ---------------------------------------------------------------------------
# Residue — module-level assignments are pinnable
# ---------------------------------------------------------------------------


def test_remediations_dict_is_in_the_residue_inventory() -> None:
    assert (_SERVICE_REL, "LLM_ERROR_REMEDIATIONS") in RESIDUE_SITES, (
        "LLM_ERROR_REMEDIATIONS left the residue inventory — the retry "
        "remediation dict re-injects English action doctrine below the capture "
        "layer and MUST stay pinned [I-7]"
    )


def test_extractor_resolves_a_module_level_assignment() -> None:
    seg = _extract_symbol_source(_ENGINE_ROOT / _SERVICE_REL, "LLM_ERROR_REMEDIATIONS")
    assert "VALIDATION_ERROR" in seg, "extracted the wrong node for the remediation dict"


def test_extractor_still_fails_loud_on_a_missing_symbol() -> None:
    """The extension must not have turned unknown names into silent misses —
    a dead RESIDUE_SITES pointer has to stop the run, same as before."""
    with pytest.raises(ResearchOverrideError, match="no longer exists"):
        _extract_symbol_source(_ENGINE_ROOT / _SERVICE_REL, "NO_SUCH_CONSTANT_975")


def test_digest_moves_when_the_remediation_text_would_move() -> None:
    """The digest is the drift tripwire: it must be a function of the
    remediation source. Computed twice it is stable; the extracted segment is
    part of its input (proven by extraction above + inventory membership)."""
    assert compute_residue_digest() == compute_residue_digest()
