"""Target stem vs translation-memory stem: Constitution ethics 1.3 from the Accord 1.2b corpus.

Offline. The model is faked and the network is blocked exactly as in
test_accord_pipeline.py, whose fixtures and fake are reused here.
"""

from __future__ import annotations

import importlib.resources
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

import pytest

from tests.localization.test_accord_pipeline import (  # noqa: F401  (autouse fixture)
    AL,
    EN_TEXT,
    LOCALIZED,
    FakeModel,
    _fake_translation,
    _isolate_modules,
    seg,
)

REAL_13 = LOCALIZED / "constitution_ethics_1.3_en.txt"


def shape_like_1_3(text: str) -> str:
    """A 1.2b -> 1.3-shaped edit: insertions that shift later line keys within
    their sections, one reworded line, one new section, and a new provenance
    preamble -- the kinds of change the real 1.3 makes."""
    edits = [
        # insert above existing lines (shifts every later key in the section)
        (
            "Stars spun, seas boiled, life flickered on and off in the dark like shy fireflies.",
            "A new opening line of the threshold.\n\nStars spun, seas boiled, life flickered on and off in the dark "
            "like shy fireflies.",
        ),
        ("Nothing stayed; nothing meant.", "Nothing stayed; nothing meant.\n\nA second inserted line."),
        # reword in place
        ("Order became more than accident; it became invitation.", "Order became more than accident: an invitation."),
        # a whole new section
        ("## II. The First Leaning", "## I-b. An Inserted Section\n\nIts only line.\n\n## II. The First Leaning"),
    ]
    out = text.replace("// CIRIS Accord 1.2b text", "// The CIRIS Constitution's ethics text, version 1.3", 1)
    for old, new in edits:
        assert old in out, old
        out = out.replace(old, new, 1)
    return out


@pytest.fixture
def tree(tmp_path: Path) -> Dict[str, Path]:
    loc = tmp_path / "localized"
    loc.mkdir()
    shutil.copy(LOCALIZED / "accord_1.2b_en.txt", loc / "accord_1.2b_en.txt")
    shutil.copy(LOCALIZED / "accord_1.2b_yo.txt", loc / "accord_1.2b_yo.txt")
    (loc / "constitution_ethics_1.3_en.txt").write_text(shape_like_1_3(EN_TEXT), encoding="utf-8")
    manifest = json.loads((LOCALIZED / "manifest.json").read_text(encoding="utf-8"))
    manifest["languages"] = {k: v for k, v in manifest["languages"].items() if k in ("en", "yo")}
    (loc / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    shutil.copy(LOCALIZED / "yo.json", loc / "yo.json")
    return {"loc": loc, "stage": tmp_path / "stage"}


ETHICS = ["--version", "1.3", "--stem", "constitution_ethics", "--tm-version", "1.2b", "--tm-stem", "accord"]


def _run(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path], *extra: str) -> Dict[str, Any]:
    seen: Dict[str, Any] = {"requests": []}
    real_install = AL.install

    def install(L: Any, stage: Any, tms: Any) -> None:
        real_install(L, stage, tms)
        fake = FakeModel(L)

        def recording(model: str, system: str, messages: List[Dict[str, Any]], *, batch: bool = False) -> Any:
            seen["requests"].append("\n\n".join(part["text"] for m in messages for part in m["content"]))
            return fake(model, system, messages, batch=batch)

        L.call_model = recording
        seen["fake"], seen["L"] = fake, L

    monkeypatch.setattr(AL, "install", install)
    seen["rc"] = AL.main(
        [*ETHICS, "--stage-dir", str(tree["stage"]), "--localized-dir", str(tree["loc"]), *extra]
    )  # fmt: skip
    return seen


# ── the allow-list ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad", ["../accord", "accord/../x", "POLYGLOT", "accord_1.2b", "", "Accord", "polyglot/x"])
def test_stem_is_a_closed_allow_list(bad: str) -> None:
    with pytest.raises(SystemExit):
        AL.check_stem(bad)
    with pytest.raises(SystemExit):
        AL.accord_path(LOCALIZED, "1.3", "yo", bad)


def test_the_new_stem_names_the_new_files() -> None:
    assert AL.accord_path(LOCALIZED, "1.3", "yo", "constitution_ethics").name == "constitution_ethics_1.3_yo.txt"
    assert AL.default_stage_dir("1.3", "constitution_ethics") == AL.STAGE_ROOT / "constitution_ethics_1.3"


def test_default_behaviour_is_unchanged() -> None:
    assert AL.DEFAULT_STEM == "accord"
    assert AL.accord_path(LOCALIZED, "1.3", "yo").name == "accord_1.3_yo.txt"
    assert AL.default_stage_dir("1.3") == AL.STAGE_ROOT / "1.3"
    labelled = AL.label_locale("// a\nbody", "1.2b")
    assert labelled.split("\n")[1].startswith("// Machine translation of the English Accord 1.2b -- status: draft")


def test_prompts_name_the_document_by_stem() -> None:
    class FakeL:
        GUIDE_RULES = "- **Rule.** x"
        _PLACEHOLDER_RULE = "- placeholders"

    default = AL.accord_prompts(FakeL)  # type: ignore[arg-type]
    ethics = AL.accord_prompts(FakeL, "constitution_ethics")  # type: ignore[arg-type]
    assert "the CIRIS Accord" in default["SYSTEM_TRANSLATE"]
    for text in ethics.values():
        assert "Constitution's ethics text" in text
        assert "the CIRIS Accord" not in text
        assert FakeL.GUIDE_RULES in text


# ── end to end on the new stem ───────────────────────────────────────────────


def test_ethics_run_reads_the_new_source_seeds_tm_from_1_2b_and_writes_the_new_files(
    monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]
) -> None:
    out = _run(monkeypatch, tree, "--lane", "translate", "--lang", "yo", "--max-keys", "5000")
    assert out["rc"] == 0
    written = tree["loc"] / "constitution_ethics_1.3_yo.txt"
    assert written.is_file()
    assert not list(tree["loc"].glob("accord_1.3_*")), "the target stem, not the TM stem, names the output"
    assert (tree["loc"] / "accord_1.2b_yo.txt").read_bytes() == (LOCALIZED / "accord_1.2b_yo.txt").read_bytes()

    # TM came from the shipped Accord 1.2b Yoruba: its rendering of a line that
    # MOVED (its key shifted under the insertion) reached the request anyway.
    en_12 = seg.parse(EN_TEXT)
    yo_12, _ = seg.align(en_12, seg.parse((LOCALIZED / "accord_1.2b_yo.txt").read_text(encoding="utf-8")))
    moved_line = "Stars spun, seas boiled, life flickered on and off in the dark like shy fireflies."
    old_key = next(k for k, v in en_12.segments().items() if v == moved_line)
    new_doc = seg.parse((tree["loc"] / "constitution_ethics_1.3_en.txt").read_text(encoding="utf-8"))
    new_key = next(k for k, v in new_doc.segments().items() if v == moved_line)
    assert new_key != old_key, "precondition: the insertion shifted the line's key"
    assert any(yo_12[old_key] in r for r in out["requests"]), "exact-English TM anchor across a shifted key"

    # Round trip: the written file is skeleton + values of the NEW source.
    text = written.read_text(encoding="utf-8")
    aligned, skipped = seg.align(new_doc, seg.parse(text))
    assert not skipped
    assert aligned == {k: _fake_translation("yo", v) for k, v in new_doc.segments().items()}
    assert "English Constitution ethics text 1.3 -- status: draft / review_status: machine_reviewed" in text


def test_the_written_file_loads_through_the_real_loader(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]) -> None:
    assert _run(monkeypatch, tree, "--lane", "translate", "--lang", "yo", "--max-keys", "5000")["rc"] == 0
    from ciris_engine.logic.utils import constants

    name = "constitution_ethics_1.3_yo.txt"
    assert name not in constants.ACCORD_EXPECTED_HASHES, "not pinned yet: pins are a reviewed step"
    real_files = importlib.resources.files
    monkeypatch.setattr(
        importlib.resources,
        "files",
        lambda package: tree["loc"] if package == "ciris_engine.data" else real_files(package),
    )
    loaded = constants._load_accord_file(name)
    assert loaded == (tree["loc"] / name).read_text(encoding="utf-8")


def test_seed_exact_tm_reuses_unchanged_lines_only(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]) -> None:
    out = _run(monkeypatch, tree, "--seed-exact-tm", "--lane", "translate", "--lang", "yo", "--max-keys", "5000")
    assert out["rc"] == 0
    new_doc = seg.parse((tree["loc"] / "constitution_ethics_1.3_en.txt").read_text(encoding="utf-8"))
    translated = {k for r in out["requests"] if "TRANSLATE THESE KEYS" in r for k in _keys_in(r)}
    new_lines = {"A new opening line of the threshold.", "A second inserted line.", "Its only line.",
                 "I-b. An Inserted Section", "Order became more than accident: an invitation."}  # fmt: skip
    assert {new_doc.segments()[k] for k in translated} >= new_lines
    assert len(translated) < len(new_doc.slots) // 4, "unchanged lines came from the shipped 1.2b corpus"


def _keys_in(request: str) -> List[str]:
    import re

    return re.findall(r"^- (accord\.\S+)$", request.split("TRANSLATE THESE KEYS:\n", 1)[1], re.M)


# ── the real 1.3 source, when it is in the tree ──────────────────────────────


@pytest.mark.skipif(not REAL_13.is_file(), reason="constitution_ethics_1.3_en.txt lands with #1256")
def test_real_1_3_round_trips_and_most_lines_have_an_exact_tm_anchor() -> None:
    text = REAL_13.read_text(encoding="utf-8")
    doc = seg.parse(text)
    assert seg.reassemble(doc) == text
    tm = AL.build_tm(LOCALIZED, "1.2b", "yo", "accord")
    tm_text = {e for e, _ in tm.values()}
    covered = sum(1 for v in doc.segments().values() if v in tm_text)
    assert covered / len(doc.slots) > 0.85


# ── the glossary an ethics-text run sends ────────────────────────────────────

ETHICS_PROBE = [
    "VIII. The Ethics Text Begins",
    "But the heart of this text, the ethics text of the CIRIS Constitution, is here.",
]


def _installed(tmp_path: Path, stem: str) -> Any:
    stage = AL.Stage("1.3" if stem == "constitution_ethics" else "1.2b", stage_dir=tmp_path / "stage", stem=stem)
    stage.build()
    L = AL.import_localize(stage.dir)
    AL.install(L, stage, {})
    return L


def test_ethics_run_drops_the_pipeline_stage_label_and_pins_the_texts_name(tmp_path: Path) -> None:
    stage = AL.Stage("1.3", stage_dir=tmp_path / "stage", stem="constitution_ethics")
    stage.build()
    L = AL.import_localize(stage.dir)
    # precondition: the vendored glossary sends the stage label as "Ethics"
    assert L.gloss.relevant("am", ETHICS_PROBE) == {"Ethics": "ህሊና"}
    AL.install(L, stage, {})
    for lang in ("am", "my", "yo"):
        sent = L.gloss.relevant(lang, ETHICS_PROBE)
        assert "Ethics" not in sent, lang
        assert sent["ethics text"] == AL.ETHICS_TEXT_RENDERINGS[lang]
        assert AL.ETHICS_TEXT_RENDERINGS[lang] in L.gloss.block(lang, ETHICS_PROBE)
    assert "ህሊና" not in L.gloss.block("am", ETHICS_PROBE), "am must not be told ethics = conscience"


def test_every_ethics_text_rendering_is_a_supported_locale() -> None:
    manifest = json.loads((LOCALIZED / "manifest.json").read_text(encoding="utf-8"))
    assert set(AL.ETHICS_TEXT_RENDERINGS) <= set(manifest["languages"]) - {"en"}
    assert all(v.strip() == v and v for v in AL.ETHICS_TEXT_RENDERINGS.values())


def test_accord_runs_keep_the_ethics_row_but_recase_yoruba(tmp_path: Path) -> None:
    L = _installed(tmp_path, "accord")
    assert L.gloss.relevant("yo", ["Ethics."]) == {"Ethics": "ìwà rere"}
    assert "ethics text" not in L.gloss.relevant("yo", ETHICS_PROBE), "the name row is for the ethics text only"
    assert L.gloss.relevant("am", ["Ethics."]) == {"Ethics": "ህሊና"}, "only yo is re-cased"


# ── principle names: the shipped 1.2b corpus is the authority (ruling 2026-10-14) ──

GLOSSARY_LANGS = sorted(
    p.name.split("_")[0]
    for p in (Path(AL.__file__).resolve().parent / "glossaries").glob("*_glossary.md")
    if not p.name.startswith("TEMPLATE")
)


@pytest.fixture
def ethics_glossary(tmp_path: Path) -> Any:
    """(vendored terms(), the terms() a constitution_ethics run sends)."""
    stage = AL.Stage("1.3", stage_dir=tmp_path / "stage", stem="constitution_ethics")
    stage.build()
    L = AL.import_localize(stage.dir)
    vendored = L.gloss.terms
    AL.install(L, stage, {})
    return vendored, L.gloss.terms


def test_no_ethics_row_is_rendered_as_its_own_english(ethics_glossary: Any) -> None:
    vendored, sent = ethics_glossary
    assert len(GLOSSARY_LANGS) == 28
    # precondition: the vendored tables do have such rows, so the check is not vacuous
    assert vendored("fr")["Wise Authority"] == "Wise Authority"
    assert vendored("de")["Reasoning"] == "Reasoning"
    for lang in GLOSSARY_LANGS:
        rows = sent(lang)
        assert AL.english_renderings(rows, lang) == [], lang
        allowed = AL.ENGLISH_RENDERING_KEPT_EVERYWHERE | AL.ENGLISH_RENDERING_KEPT.get(lang, frozenset())
        for english, rendering in rows.items():
            if rendering.strip().casefold() == english.strip().casefold():
                assert english in allowed, (lang, english)


def test_the_english_rendering_check_fails_on_an_injected_row() -> None:
    injected = {"Integrity": "Integrity", "Justice": "Gerechtigkeit", "CIRIS": "CIRIS", "Agent": "Agent"}
    # the checker sees the leftover English, and only it: CIRIS is a proper name,
    # de's 1.2b writes "Agent", and "Gerechtigkeit" is a translation
    assert AL.english_renderings(injected, "de") == ["Integrity"]
    assert AL.english_renderings(injected, "ha") == ["Agent", "Integrity"]
    sent = AL.accord_terms(injected, "de", "constitution_ethics")
    assert "Integrity" not in sent and sent["Justice"] == "Gerechtigkeit" and sent["CIRIS"] == "CIRIS"
    # an Accord (not ethics-text) run is not filtered: the filter is what removed it
    assert AL.accord_terms(injected, "de", "accord")["Integrity"] == "Integrity"


def test_every_principle_fix_corrects_an_existing_row_to_the_shipped_1_2b_rendering(ethics_glossary: Any) -> None:
    vendored, sent = ethics_glossary
    assert AL.CONSTITUTION_ETHICS_GLOSSARY_FIX, "the fix table is not empty"
    for lang, fixes in AL.CONSTITUTION_ETHICS_GLOSSARY_FIX.items():
        corpus = (LOCALIZED / f"accord_1.2b_{lang}.txt").read_text(encoding="utf-8").casefold()
        for english, rendering in fixes.items():
            assert english in vendored(lang), (lang, english, "a fix corrects a row, it never adds one")
            assert vendored(lang)[english] != rendering, (lang, english)
            assert rendering.casefold() in corpus, (lang, english, "never invented: it is the 1.2b corpus's")
            assert sent(lang)[english] == rendering, (lang, english)


def test_unresolvable_rows_are_not_sent_and_version_history_rows_never_are(ethics_glossary: Any) -> None:
    vendored, sent = ethics_glossary
    for lang, removed in AL.CONSTITUTION_ETHICS_GLOSSARY_REMOVE.items():
        for english in removed:
            assert english in vendored(lang), (lang, english)
            assert english not in sent(lang), (lang, english)
    assert vendored("de")["1.0"] == "2026-03-27", "precondition: the version table parses as terms"
    for lang in GLOSSARY_LANGS:
        assert not [e for e in sent(lang) if AL.VERSION_ROW.fullmatch(e)], lang
        assert "ethics check" not in {e.casefold() for e in sent(lang)}, lang


def test_accord_runs_keep_the_vendored_principle_rows(tmp_path: Path) -> None:
    L = _installed(tmp_path, "accord")
    assert L.gloss.relevant("th", ["2 Integrity"]) == {"Integrity": "ความซื่อสัตย์"}
    assert L.gloss.relevant("fr", ["Wise Authority"]) == {"Wise Authority": "Wise Authority"}


def test_ethics_run_sends_the_corpus_principle_names(ethics_glossary: Any) -> None:
    _, sent = ethics_glossary
    assert sent("th")["Integrity"] == "ความซื่อตรง"
    assert sent("de")["Resilience"] == "Resilienz"
    assert sent("de")["Non-maleficence"] == "Schadensvermeidung"
    assert sent("uk")["Integrity"] == "Цілісність"
    assert sent("fr")["Wise Authority"] == "Autorité Sage"


#: The "human advisor" renderings the ruling excludes ("Wise Authority not human advisor").
HUMAN_ADVISOR = {"de": "Menschlicher Berater", "hi": "मानव सलाहकार", "sw": "Mshauri wa Kibinadamu", "ko": "담당자"}


def test_no_ethics_run_renders_wise_authority_as_a_human_advisor(ethics_glossary: Any) -> None:
    vendored, sent = ethics_glossary
    # precondition: the vendored glossaries do pin it, so the check is not vacuous
    assert all(vendored(lang)["Wise Authority"] == ha for lang, ha in HUMAN_ADVISOR.items())
    banned = {ha.casefold() for ha in HUMAN_ADVISOR.values()} | {"mshauri", "berater", "सलाहकार"}
    for lang in GLOSSARY_LANGS:
        row = sent(lang).get("Wise Authority")
        if row is None:
            assert lang == "sw", f"{lang}: only sw has no non-human-advisor 1.2b rendering"
            continue
        assert not any(b in row.casefold() for b in banned), (lang, row)
        assert "/" not in row, (lang, row, "one rendering, not a slash pair")
    assert sent("tr")["Wise Authority"] == "Bilge Otorite"
    assert sent("de")["Wise Authority"] == "Wise Authority"
    # the UI glossary is not changed by this: an accord-stem run still sends the vendored row
    assert AL.accord_terms(vendored("de"), "de", "accord")["Wise Authority"] == "Menschlicher Berater"


@pytest.mark.skipif(not REAL_13.is_file(), reason="constitution_ethics_1.3_en.txt lands with #1256")
def test_no_ethics_request_tells_a_locale_wise_authority_is_a_human_advisor(tmp_path: Path) -> None:
    stage = AL.Stage("1.3", stage_dir=tmp_path / "stage", stem="constitution_ethics")
    stage.build()
    L = AL.import_localize(stage.dir)
    text = [s.text for s in seg.parse(REAL_13.read_text(encoding="utf-8")).slots]
    # precondition: the vendored prose does say it, so the check is not vacuous
    assert "मानव सलाहकार" in L.gloss.block("hi", text)
    assert "人工顾问" in L.gloss.block("zh", text)
    AL.install(L, stage, {})
    for lang in GLOSSARY_LANGS:
        sent = L.gloss.block(lang, text).casefold()
        for ha in (*AL.HUMAN_ADVISOR_PROSE, *(h.casefold() for h in HUMAN_ADVISOR.values())):
            assert ha not in sent, (lang, ha)
    assert "智慧权威" in L.gloss.block("zh", text), "the corrected row is still sent"
    # an accord-stem run keeps the vendored prose
    assert AL.accord_guidance([("Notes", "- like 人工顾问")], "accord") == [("Notes", "- like 人工顾问")]
