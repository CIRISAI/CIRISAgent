"""The ethics-text loader: 1.3 by default, 1.2b only through a research manifest.

The corpus slot (``get_accord_text`` / ``get_localized_accord_text``) serves the
default edition, constitution_ethics 1.3 (CIRISAgent#1252). accord 1.2b stays
shipped and pinned so a research manifest's ``corpus_edition`` can select it as
the control arm of the 2.16 safety battery. Either way every file read passes
the SHA256 pin (``_verify_ethics_text_integrity``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator

import pytest

from ciris_engine.logic.utils import constants
from ciris_engine.logic.utils import research_overrides as ro
from ciris_engine.logic.utils.research_overrides import ENV_ANCHOR, ENV_MANIFEST, ResearchOverrideError

REPO = Path(__file__).resolve().parents[4]
DATA = REPO / "ciris_engine" / "data"
LOCALIZED = DATA / "localized"
MANIFESTS = REPO / "tools" / "research" / "manifests"
LOCALES = sorted(json.loads((LOCALIZED / "manifest.json").read_text(encoding="utf-8"))["languages"])


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No override state and no cached edition text leaks in or out."""
    monkeypatch.delenv(ENV_MANIFEST, raising=False)
    monkeypatch.setattr(constants, "ACCORD_MODE", "compressed")
    ro.reset_research_overrides()
    constants._EDITION_TEXT_CACHE.clear()
    constants._LOCALIZED_ACCORD_CACHE.clear()
    yield
    ro.reset_research_overrides()
    constants._EDITION_TEXT_CACHE.clear()
    constants._LOCALIZED_ACCORD_CACHE.clear()


def _manifest(edition: str, **extra: Any) -> Dict[str, Any]:
    doc: Dict[str, Any] = {
        "manifest_version": "1",
        "experiment_id": "test-ethics-edition",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": ro.compute_residue_digest(),
        "corpus_edition": edition,
        "overrides": {"string": {}, "dma_prompt": {}, "conscience_prompt": {}, "corpus": {}, "template": {}},
        "research_hashes": {},
    }
    doc.update(extra)
    return doc


def _activate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, doc: Dict[str, Any]) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setenv(ENV_MANIFEST, str(path))
    monkeypatch.setenv(ENV_ANCHOR, "true")
    ro.reset_research_overrides()


# ---------------------------------------------------------------------------
# 1. Default: 1.3
# ---------------------------------------------------------------------------


def test_default_edition_is_constitution_ethics_1_3() -> None:
    assert constants.DEFAULT_CORPUS_EDITION == "1.3"
    assert constants.ETHICS_TEXT_FILENAME == "constitution_ethics_1.3_POLYGLOT.txt"
    assert constants.ETHICS_TEXT_COMPRESSED_FILENAME == "constitution_ethics_1.3_POLYGLOT_compressed.txt"
    assert constants.active_corpus_edition() == "1.3"


def test_all_three_surfaces_serve_1_3_by_default() -> None:
    # Round 1 (Braided Monolith), consciences (full polyglot + guide), round 2 (localized).
    assert constants.get_accord_text("compressed") == _read(DATA / "constitution_ethics_1.3_POLYGLOT_compressed.txt")
    full = constants.get_accord_text("force_full")
    assert full.startswith(_read(DATA / "constitution_ethics_1.3_POLYGLOT.txt"))
    assert constants.get_localized_accord_text("en") == _read(LOCALIZED / "constitution_ethics_1.3_en.txt")
    # Negative control: none of them is the 1.2b text.
    assert constants.get_accord_text("compressed") != _read(DATA / "accord_1.2b_POLYGLOT_compressed.txt")
    assert not full.startswith(_read(DATA / "accord_1.2b_POLYGLOT.txt"))


def test_shipped_1_3_locale_is_served_in_its_own_language() -> None:
    shipped = [
        lang for lang in LOCALES if lang != "en" and (LOCALIZED / f"constitution_ethics_1.3_{lang}.txt").is_file()
    ]
    if not shipped:
        pytest.skip("no non-English 1.3 locale shipped yet")
    lang = shipped[0]
    assert constants.get_localized_accord_text(lang) == _read(LOCALIZED / f"constitution_ethics_1.3_{lang}.txt")


def test_untranslated_1_3_locale_falls_back_within_the_edition() -> None:
    """A locale whose 1.3 file is not written yet gets the 1.3 English, never 1.2b."""
    missing = [lang for lang in LOCALES if not (LOCALIZED / f"constitution_ethics_1.3_{lang}.txt").is_file()]
    if not missing:
        pytest.skip("every locale has its 1.3 file")
    assert constants.get_localized_accord_text(missing[0]) == _read(LOCALIZED / "constitution_ethics_1.3_en.txt")


# ---------------------------------------------------------------------------
# 2. A research manifest selects the edition
# ---------------------------------------------------------------------------


def test_research_manifest_selects_1_2b_on_every_surface(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _activate(monkeypatch, tmp_path, _manifest("1.2b"))
    assert constants.active_corpus_edition() == "1.2b"
    assert constants.get_accord_text("compressed") == _read(DATA / "accord_1.2b_POLYGLOT_compressed.txt")
    assert constants.get_accord_text("force_full").startswith(_read(DATA / "accord_1.2b_POLYGLOT.txt"))
    assert constants.get_localized_accord_text("en") == _read(LOCALIZED / "accord_1.2b_en.txt")
    assert constants.get_localized_accord_text("am") == _read(LOCALIZED / "accord_1.2b_am.txt")
    manifest = ro.get_active_overrides()
    assert manifest is not None and manifest.trace_fields()["research_corpus_edition"] == "1.2b"


def test_research_manifest_can_name_1_3_explicitly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _activate(monkeypatch, tmp_path, _manifest("1.3"))
    assert constants.get_accord_text("compressed") == _read(DATA / "constitution_ethics_1.3_POLYGLOT_compressed.txt")
    assert constants.get_localized_accord_text("en") == _read(LOCALIZED / "constitution_ethics_1.3_en.txt")


def test_edition_cache_does_not_leak_between_arms(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert constants.get_localized_accord_text("en") == _read(LOCALIZED / "constitution_ethics_1.3_en.txt")
    _activate(monkeypatch, tmp_path, _manifest("1.2b"))
    assert constants.get_localized_accord_text("en") == _read(LOCALIZED / "accord_1.2b_en.txt")


def test_unknown_edition_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _activate(monkeypatch, tmp_path, _manifest("1.1"))
    with pytest.raises(ResearchOverrideError, match="not a shipped edition"):
        ro.get_active_overrides()


def test_edition_and_accord_corpus_text_together_are_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    doc = _manifest("1.2b")
    doc["overrides"]["corpus"] = {
        k: "x" for k in ("accord.localized", "accord.polyglot_compressed", "accord.polyglot_full")
    }
    _activate(monkeypatch, tmp_path, doc)
    with pytest.raises(ResearchOverrideError, match="both select the accord slot"):
        ro.get_active_overrides()


def test_edition_digest_differs_between_arms() -> None:
    assert ro.compute_manifest_digest(_manifest("1.2b")) != ro.compute_manifest_digest(_manifest("1.3"))


def test_committed_battery_arms_differ_only_in_edition() -> None:
    """The 2.16 control and candidate arms are the same manifest but for the edition."""
    control = json.loads(_read(MANIFESTS / "ethics-text-1.2b-control.json"))
    candidate = json.loads(_read(MANIFESTS / "ethics-text-1.3-candidate.json"))
    assert control.pop("corpus_edition") == "1.2b"
    assert candidate.pop("corpus_edition") == "1.3"
    assert control == candidate
    assert control["mode"] == "additive" and not any(control["overrides"].values())


# ---------------------------------------------------------------------------
# 3. Integrity covers both editions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("edition", sorted(constants.CORPUS_EDITIONS))
def test_every_edition_core_file_is_pinned(edition: str) -> None:
    spec = constants.CORPUS_EDITIONS[edition]
    for name in (spec.polyglot, spec.compressed, spec.localized("en")):
        assert name in constants.ETHICS_TEXT_EXPECTED_HASHES, f"{name} is not pinned"


@pytest.mark.parametrize("edition", sorted(constants.CORPUS_EDITIONS))
def test_every_shipped_locale_file_is_pinned(edition: str) -> None:
    prefix = constants.CORPUS_EDITIONS[edition].localized_prefix
    unpinned = sorted(
        p.name for p in LOCALIZED.glob(f"{prefix}_*.txt") if p.name not in constants.ETHICS_TEXT_EXPECTED_HASHES
    )
    assert not unpinned, f"run python3 tools/dev/regen_accord_pins.py: {unpinned}"


def test_tampered_1_3_file_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    name = constants.ETHICS_TEXT_COMPRESSED_FILENAME
    monkeypatch.setitem(constants.ETHICS_TEXT_EXPECTED_HASHES, name, "0" * 64)
    with pytest.raises(RuntimeError, match="INTEGRITY FAILURE"):
        constants._load_accord_file(name)


def test_tampered_1_2b_control_file_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The control arm is held to its pin too: a research arm is no bypass."""
    _activate(monkeypatch, tmp_path, _manifest("1.2b"))
    monkeypatch.setitem(constants.ETHICS_TEXT_EXPECTED_HASHES, "accord_1.2b_POLYGLOT_compressed.txt", "0" * 64)
    with pytest.raises(RuntimeError, match="INTEGRITY FAILURE"):
        constants.get_accord_text("compressed")


@pytest.mark.xfail(
    strict=True,
    reason="the translate lane has not completed every locale yet (#1253). When this XPASSes, "
    "re-pin (tools/dev/regen_accord_pins.py), have the root WA re-sign the manifest, and delete this marker.",
)
def test_every_locale_ships_a_1_3_file() -> None:
    missing = [lang for lang in LOCALES if not (LOCALIZED / f"constitution_ethics_1.3_{lang}.txt").is_file()]
    assert not missing, f"no constitution_ethics_1.3 file for {missing}"
