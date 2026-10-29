"""The Accord segment adapter over the vendored CIRISClient pipeline -- offline.

No model is called anywhere in this file. ``localize.call_model`` is replaced by
a deterministic fake, and ``urllib.request.urlopen`` is made to explode, so a
regression that reached the network would fail the test rather than spend.
"""

from __future__ import annotations

import importlib.resources
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

REPO = Path(__file__).resolve().parents[2]
LOCALIZATION = REPO / "localization"
LOCALIZED = REPO / "ciris_engine" / "data" / "localized"

sys.path.insert(0, str(LOCALIZATION))

import accord_localize as AL  # noqa: E402
import accord_segments as seg  # noqa: E402

EN_TEXT = (LOCALIZED / "accord_1.2b_en.txt").read_text(encoding="utf-8")
LOCALES = sorted(p.stem.split("_")[-1] for p in LOCALIZED.glob("accord_1.2b_*.txt"))


@pytest.fixture(autouse=True)
def _isolate_modules(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """localize.py and the shim are import-time configured; never leak them."""
    for var in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "LOCALIZE_PROVIDER", "LOCALIZE_LADDER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("LOCALIZE_REVIEW_MODEL", "fake/judge")

    def no_network(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("a test reached the network")

    monkeypatch.setattr("urllib.request.urlopen", no_network)
    yield
    for name in ("localize", "check_localization_sync", "glossary"):
        sys.modules.pop(name, None)


# ─────────────────────────────────────────────────────────────────────────────
# Segmentation
# ─────────────────────────────────────────────────────────────────────────────


def test_english_round_trip_is_byte_identical() -> None:
    doc = seg.parse(EN_TEXT)
    assert seg.reassemble(doc) == EN_TEXT
    # ...and through the values path too, which is what a locale write uses.
    assert seg.reassemble(doc, doc.segments()) == EN_TEXT
    assert len(doc.slots) > 300


@pytest.mark.parametrize("lang", LOCALES)
def test_every_shipped_locale_round_trips(lang: str) -> None:
    text = (LOCALIZED / f"accord_1.2b_{lang}.txt").read_text(encoding="utf-8")
    assert seg.reassemble(seg.parse(text)) == text


def test_keys_are_stable_lowercase_and_unique() -> None:
    doc = seg.parse(EN_TEXT)
    keys = [s.key for s in doc.slots]
    assert len(keys) == len(set(keys))
    for key in keys:
        assert re.fullmatch(r"accord\.[a-z0-9_]+\.(meta\.(title|description)|s\d{2}\.(title|l\d{2}))", key), key
    assert doc.units() == ["section0", "v1", "v2", "v3", "v4", "v5", "v6", "v7", "v8", "v9", "annexes"]
    assert "accord.section0.s01.title" in keys
    assert doc.segments()["accord.section0.s01.title"] == "I. The Quiet Threshold"
    assert doc.segments()["accord.v1.meta.description"] == "Awakened Ethical Awareness"


def test_structure_is_never_a_segment() -> None:
    doc = seg.parse(EN_TEXT)
    for slot in doc.slots:
        for line in slot.render().split("\n"):
            assert not line.startswith(seg.MARKER)
            assert line.strip() != "---"
            assert not seg.FORMULA.search(line), line
    # The provenance preamble stays verbatim (shipped locales keep it English).
    assert all(isinstance(p, str) for p in doc.pieces[:3])


def test_reassembly_refuses_a_partial_locale() -> None:
    doc = seg.parse(EN_TEXT)
    values = doc.segments()
    values.pop(next(iter(values)))
    with pytest.raises(KeyError):
        seg.reassemble(doc, values)


def test_passage_rules() -> None:
    """The old accord_i18n.py guard, per line: none of these may pass."""
    doc = seg.parse(EN_TEXT)
    by_kind: Dict[str, seg.Slot] = {}
    for slot in doc.slots:
        by_kind.setdefault(slot.kind, slot)
    item, h2, line = by_kind["item"], by_kind["h2"], by_kind["line"]
    assert seg.passage_problems(item, item.text) == []
    assert seg.passage_problems(h2, "Titel\nzwei") != []
    assert any("line break" in p for p in seg.passage_problems(line, line.text + "\n\nmore"))
    assert any("structure" in p for p in seg.passage_problems(line, "## a heading"))
    assert any("structure" in p for p in seg.passage_problems(line, "---"))
    assert any("structure" in p for p in seg.passage_problems(line, seg.MARKER + "main/v1.mdx"))
    assert any("front-matter" in p for p in seg.passage_problems(line, "title: x"))
    assert any("list marker" in p for p in seg.passage_problems(line, "* " + line.text))
    assert any("formula" in p for p in seg.passage_problems(line, "V(k) = 1"))
    cc = next(s for s in doc.slots if seg.CC_REF.search(s.text))
    assert any("CC references" in p for p in seg.passage_problems(cc, seg.CC_REF.sub("CC", cc.text)))
    assert any("withdrawn" in p for p in seg.passage_problems(line, line.text + " Ethilogics"))
    long_line = next(s for s in doc.slots if s.kind == "line" and len(s.text.split()) > 6)
    assert any("untranslated" in p for p in seg.passage_problems(long_line, long_line.text, "de"))
    assert any("script" in p for p in seg.passage_problems(long_line, long_line.text + " x", "am"))


def test_formulas_and_markup_prefixes_live_in_the_skeleton() -> None:
    doc = seg.parse(EN_TEXT)
    verbatim = [p for p in doc.pieces if isinstance(p, str)]
    for formula in ("J = k_eff", "ST = ceil("):
        assert any(formula in v for v in verbatim), formula
        assert not any(formula in s.text for s in doc.slots), formula
    items = [s for s in doc.slots if s.kind == "item"]
    assert items and all(seg._LIST_ITEM.match(s.prefix) for s in items)
    assert all(not s.text.startswith(("* ", "- ")) for s in items)


# ─────────────────────────────────────────────────────────────────────────────
# The adapter end to end, with a fake model
# ─────────────────────────────────────────────────────────────────────────────


def _fake_translation(lang: str, english: str) -> str:
    # Marker-preserving: list lines keep their leading marker; CC refs and **
    # survive because the English is kept and only a tag is appended per line.
    return "\n".join(f"{line} ⟦{lang}⟧" for line in english.split("\n"))


class FakeModel:
    """Stands in for localize.call_model. Translate, review, repair -- no I/O."""

    def __init__(self, L: Any, *, poison: str = "") -> None:
        self.L = L
        self.poison = poison
        self.calls: List[str] = []

    def __call__(self, model: str, system: str, messages: List[Dict[str, Any]], *, batch: bool = False) -> Any:
        text = "\n\n".join(part["text"] for m in messages for part in m["content"])
        lang = re.search(r"TARGET LANGUAGE: (\w+)", text).group(1)  # type: ignore[union-attr]
        if system == self.L.SYSTEM_REVIEW:
            self.calls.append("review")
            pairs = json.loads(text.split("REVIEW THESE (source -> translation):\n", 1)[1])
            return self.L.Reply(json.dumps({k: [] for k in pairs}), 10, 10)
        if system == self.L.SYSTEM_TRANSLATE:
            self.calls.append("translate")
            source = json.loads(text.split("ENGLISH SOURCE STRINGS", 1)[1].split(":\n", 1)[1].split("\n\nTARGET")[0])
            keys = re.findall(r"^- (accord\.\S+)$", text.split("TRANSLATE THESE KEYS:\n", 1)[1], re.M)
            out = {}
            for k in keys:
                out[k] = "bad\n\nblank" if k == self.poison else _fake_translation(lang, source[k])
            return self.L.Reply(json.dumps({"translations": out, "refusals": {}}), 10, 10)
        self.calls.append("repair")
        return self.L.Reply(json.dumps({"translations": {}, "refusals": {}}), 10, 10)


@pytest.fixture
def tree(tmp_path: Path) -> Dict[str, Path]:
    """A localized/ dir holding only what the adapter reads, plus a stage dir."""
    loc = tmp_path / "localized"
    loc.mkdir()
    shutil.copy(LOCALIZED / "accord_1.2b_en.txt", loc / "accord_1.2b_en.txt")
    manifest = json.loads((LOCALIZED / "manifest.json").read_text(encoding="utf-8"))
    manifest["languages"] = {k: v for k, v in manifest["languages"].items() if k in ("en", "yo", "de")}
    (loc / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    for lang in ("yo", "de"):
        shutil.copy(LOCALIZED / f"{lang}.json", loc / f"{lang}.json")
    return {"loc": loc, "stage": tmp_path / "stage"}


def _run(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path], *extra: str, poison: str = "") -> Dict[str, Any]:
    seen: Dict[str, Any] = {}
    real_install = AL.install

    def install(L: Any, stage: Any, tms: Any) -> None:
        real_install(L, stage, tms)
        fake = FakeModel(L, poison=poison)
        L.call_model = fake
        seen["fake"] = fake
        seen["L"] = L

    monkeypatch.setattr(AL, "install", install)
    seen["rc"] = AL.main(
        ["--version", "1.2b", "--stage-dir", str(tree["stage"]), "--localized-dir", str(tree["loc"]), *extra]
    )
    return seen


def test_translate_lane_reassembles_a_file_the_real_loader_loads(
    monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]
) -> None:
    out = _run(monkeypatch, tree, "--lane", "translate", "--lang", "yo", "--max-keys", "5000")
    assert out["rc"] == 0
    assert "translate" in out["fake"].calls and "review" in out["fake"].calls
    target = tree["loc"] / "accord_1.2b_yo.txt"
    assert target.is_file()
    assert not (tree["loc"] / "accord_1.2b_de.txt").exists(), "only the selected locale is written"

    # Through the REAL loader. Its integrity registry pins the shipped yo file,
    # which this synthetic one is not, so the pin is lifted for this read only.
    from ciris_engine.logic.utils import constants

    monkeypatch.delitem(constants.ETHICS_TEXT_EXPECTED_HASHES, "accord_1.2b_yo.txt")
    real_files = importlib.resources.files

    def files(package: str) -> Any:
        return tree["loc"] if package == "ciris_engine.data.localized" else real_files(package)

    monkeypatch.setattr(importlib.resources, "files", files)
    loaded = constants._load_localized_accord_file("yo", "1.2b")
    assert loaded == target.read_text(encoding="utf-8")

    en = seg.parse(EN_TEXT)
    aligned, skipped = seg.align(en, seg.parse(loaded))
    assert not skipped
    assert aligned == {k: _fake_translation("yo", v) for k, v in en.segments().items()}
    # Same skeleton as the English (every structural line identical), plus the
    # one provenance label line that says what this file is.
    en_struct = [p for p in en.pieces if isinstance(p, str)]
    lo_struct = [p for p in seg.parse(loaded).pieces if isinstance(p, str)]
    label = AL.LABEL.format(name="Accord", version="1.2b")
    assert label.startswith("// Machine translation of the English Accord 1.2b -- "), "default label unchanged"
    assert label in lo_struct and "review_status: machine_reviewed" in label
    lo_struct.remove(label)
    assert lo_struct == en_struct

    verify = ["--version", "1.2b", "--stage-dir", str(tree["stage"]), "--localized-dir", str(tree["loc"]), "--verify"]
    assert AL.main(verify) == 0


def test_english_rebuilt_from_segments_passes_the_pinned_integrity_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ciris_engine.logic.utils import constants

    doc = seg.parse(EN_TEXT)
    (tmp_path / "accord_1.2b_en.txt").write_text(seg.reassemble(doc, doc.segments()), encoding="utf-8")
    real_files = importlib.resources.files
    monkeypatch.setattr(
        importlib.resources,
        "files",
        lambda package: tmp_path if package == "ciris_engine.data.localized" else real_files(package),
    )
    # _verify_ethics_text_integrity raises on any byte that differs from the pin.
    assert "accord_1.2b_en.txt" in constants.ETHICS_TEXT_EXPECTED_HASHES
    assert constants._load_localized_accord_file("en", "1.2b") == EN_TEXT


def test_a_rejected_passage_is_withheld_and_no_partial_file_is_written(
    monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]
) -> None:
    poison = "accord.v9.s01.title"
    out = _run(monkeypatch, tree, "--lane", "translate", "--lang", "yo", "--max-keys", "5000", poison=poison)
    assert out["rc"] == 1, "a key the ladder could not render fails the run"
    assert not (tree["loc"] / "accord_1.2b_yo.txt").exists(), "a partial locale must never become a file"
    bundle = json.loads((tree["stage"] / "yo.json").read_text(encoding="utf-8"))
    flat = AL.flatten(bundle)
    assert poison not in flat
    assert len(flat) == len(seg.parse(EN_TEXT).slots) - 1, "the accepted work is banked"
    assert out["fake"].calls.count("translate") >= 1 + len(out["L"].LADDER) - 1


def test_changed_english_invalidates_only_that_passage(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]) -> None:
    assert _run(monkeypatch, tree, "--lane", "translate", "--lang", "yo", "--max-keys", "5000")["rc"] == 0
    src = tree["loc"] / "accord_1.2b_en.txt"
    changed = EN_TEXT.replace("Nothing stayed; nothing meant.", "Nothing stayed; nothing yet meant.")
    assert changed != EN_TEXT
    src.write_text(changed, encoding="utf-8")
    stats = AL.Stage("1.2b", stage_dir=tree["stage"], localized=tree["loc"]).build()
    assert stats["yo"]["present"] == stats["yo"]["total"] - 1
    assert stats["yo"]["stale_dropped"] == 1


def test_a_line_that_moves_keeps_its_translation(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]) -> None:
    assert _run(monkeypatch, tree, "--lane", "translate", "--lang", "yo", "--max-keys", "5000")["rc"] == 0
    anchor = "Stars spun, seas boiled, life flickered on and off in the dark like shy fireflies."
    assert anchor in EN_TEXT
    (tree["loc"] / "accord_1.2b_en.txt").write_text(
        EN_TEXT.replace(anchor, "A brand new opening line.\n\n" + anchor), encoding="utf-8"
    )
    stats = AL.Stage("1.2b", stage_dir=tree["stage"], localized=tree["loc"]).build()
    # Every later line of that section shifted key; only the new line is missing.
    assert stats["yo"]["moved"] >= 2
    assert stats["yo"]["present"] == stats["yo"]["total"] - 1


def test_units_scope_a_run_and_stay_diff_driven(monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]) -> None:
    out = _run(monkeypatch, tree, "--units", "section0", "--lane", "translate", "--lang", "yo", "--max-keys", "100")
    assert out["rc"] == 0
    flat = AL.flatten(json.loads((tree["stage"] / "yo.json").read_text(encoding="utf-8")))
    assert flat and all(k.startswith("accord.section0.") for k in flat)
    assert not (tree["loc"] / "accord_1.2b_yo.txt").exists(), "one unit is a partial locale"
    calls = len(out["fake"].calls)
    again = _run(monkeypatch, tree, "--units", "section0", "--lane", "translate", "--lang", "yo", "--max-keys", "100")
    assert again["rc"] == 0 and again["fake"].calls == [], f"nothing missing, so no call (first run made {calls})"
    with pytest.raises(SystemExit):
        AL.main(["--version", "1.2b", "--stage-dir", str(tree["stage"]), "--localized-dir", str(tree["loc"]),
                 "--units", "nope", "--lane", "translate"])  # fmt: skip


def test_accept_minor_takes_only_lines_whose_objections_are_all_minor(
    monkeypatch: pytest.MonkeyPatch, tree: Dict[str, Path]
) -> None:
    minor = "accord.section0.s01.l01"
    major = "accord.section0.s01.l02"
    unrated = "accord.section0.s01.l03"
    verdicts = {
        minor: [{"category": "terminology", "severity": "minor", "span": "x", "note": "prefer y"}],
        major: [{"category": "accuracy", "severity": "major", "span": "x", "note": "meaning changed"}],
        unrated: [{"category": "terminology", "span": "x", "note": "no severity given"}],
    }

    class Judged(FakeModel):
        def __call__(self, model: str, system: str, messages: List[Dict[str, Any]], *, batch: bool = False) -> Any:
            reply = super().__call__(model, system, messages, batch=batch)
            if system != self.L.SYSTEM_REVIEW:
                return reply
            found = json.loads(reply.text)
            return self.L.Reply(json.dumps({k: verdicts.get(k, v) for k, v in found.items()}), 10, 10)

    monkeypatch.setitem(globals(), "FakeModel", Judged)
    log = tree["stage"].parent / "candidates.jsonl"
    out = _run(
        monkeypatch, tree, "--units", "section0", "--lane", "translate", "--lang", "yo", "--candidate-log", str(log)
    )
    assert out["rc"] == 1, "the three judged lines are withheld by the lane"
    flat = AL.flatten(json.loads((tree["stage"] / "yo.json").read_text(encoding="utf-8")))
    assert not {minor, major, unrated} & set(flat)

    base = ["--version", "1.2b", "--stage-dir", str(tree["stage"]), "--localized-dir", str(tree["loc"])]
    assert AL.main([*base, "--accept-minor", str(log)]) == 0
    doc = json.loads((tree["stage"] / "yo.json").read_text(encoding="utf-8"))
    flat = AL.flatten(doc)
    assert minor in flat and major not in flat and unrated not in flat
    [entry] = doc["_meta"][AL.ACCEPTED_MINOR]
    assert entry["key"] == minor and entry["text"] == flat[minor]
    assert entry["objections"] == ["minor/terminology: prefer y"]
    assert doc["_meta"]["review_status"] == "machine_reviewed"
    # The record survives the next staging, as long as the line is unchanged.
    AL.Stage("1.2b", stage_dir=tree["stage"], localized=tree["loc"]).build()
    assert json.loads((tree["stage"] / "yo.json").read_text(encoding="utf-8"))["_meta"][AL.ACCEPTED_MINOR] == [entry]


def test_glossary_does_not_retire_the_documents_own_name(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    stage = AL.Stage("1.2b", stage_dir=tmp_path / "stage")
    stage.build()
    L = AL.import_localize(stage.dir)
    probe = ["The CIRIS Accord binds the agent."]
    assert "RETIRING" in L.gloss.block("yo", probe), "precondition: the vendored glossary retires ACCORD"
    AL.install(L, stage, {})
    assert "RETIRING" not in L.gloss.block("yo", probe)
    assert "Accord" in L.SYSTEM_TRANSLATE and "ANCHOR" in L.SYSTEM_TRANSLATE
    assert L.GUIDE_RULES in L.SYSTEM_REVIEW, "the guide's section 3 rules are carried into the accord prompts"


def test_check_against_the_agent_tree(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """localize.py --check, through the adapter, over the real shipped 1.2b."""
    rc = AL.main(["--version", "1.2b", "--stage-dir", str(tmp_path / "stage"), "--check"])
    out = capsys.readouterr().out
    # Missing = sections whose shape diverged from the English (pt, zh) plus
    # shipped lines the accord guard rejects (lines left in English, e.g. the
    # front-matter descriptions de kept untranslated). Both get retranslated.
    assert rc == 1
    assert re.search(r"^pt: \d+ missing", out, re.M)
    de = re.search(r"^de: (\d+) missing", out, re.M)
    assert de and int(de.group(1)) < 20


def test_ui_target_check_runs_against_the_agent_bundle() -> None:
    env = {k: v for k, v in os.environ.items() if k not in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY")}
    env["LOCALIZE_TARGET"] = "ui"
    proc = subprocess.run(
        [sys.executable, str(LOCALIZATION / "localize.py"), "--check"],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO,
        timeout=60,
    )
    assert proc.returncode in (0, 1), proc.stderr
    assert "all languages at parity" in proc.stdout or "missing" in proc.stdout


# ─────────────────────────────────────────────────────────────────────────────
# Translation memory and the invariants around polyglot artifacts
# ─────────────────────────────────────────────────────────────────────────────


def test_translation_memory_prefers_the_previous_rendering_of_the_same_passage() -> None:
    tm = AL.build_tm(LOCALIZED, "1.2b", "de")
    assert tm["accord.section0.s01.title"] == ("I. The Quiet Threshold", "I. Die Stille Schwelle")
    anchors = AL.make_anchors({"de": tm})
    en = seg.parse(EN_TEXT).segments()
    got = anchors("de", ["accord.section0.s01.title"], en)
    assert got[0][0] == "accord.section0.s01.title"
    assert sum(len(k) + len(e) + len(t) + 16 for k, e, t in got) <= AL.ACCORD_MAX_ANCHOR_BLOCK_CHARS


def test_paths_never_touch_polyglot_artifacts(tmp_path: Path) -> None:
    assert AL.accord_path(LOCALIZED, "1.3", "yo").name == "accord_1.3_yo.txt"
    with pytest.raises(SystemExit):
        AL.check_version("1.2b_POLYGLOT")
    with pytest.raises(SystemExit):
        AL.accord_path(LOCALIZED, "1.3", "../polyglot")


def test_verify_flags_a_per_locale_accord_mirror(tree: Dict[str, Path]) -> None:
    stage = AL.Stage("1.2b", stage_dir=tree["stage"], localized=tree["loc"])
    stage.build()
    assert stage.verify() == []
    (tree["loc"] / "yo").mkdir()
    (tree["loc"] / "yo" / "accord_1.2b_POLYGLOT.txt").write_text("x", encoding="utf-8")
    assert any("mirror" in p for p in stage.verify())


def test_no_per_locale_mirror_exists_in_the_real_tree() -> None:
    for lang in LOCALES:
        mirror = LOCALIZED / lang
        assert not (mirror.is_dir() and any(mirror.glob("accord*"))), mirror


# ─────────────────────────────────────────────────────────────────────────────
# Read-only by default: the live bundles are never touched outside a lane run
# ─────────────────────────────────────────────────────────────────────────────


def _snapshot(*roots: Path) -> Dict[str, str]:
    import hashlib

    out: Dict[str, str] = {}
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                out[p.relative_to(REPO).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def test_the_agent_string_loader_still_reads_its_own_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    """The regression #1253 shipped: a *.json at localization/ top level makes
    _get_localization_dir() adopt localization/ (CIRIS_HOME is the repo root in
    a dev checkout), and every get_string / language_guidance read goes empty."""
    from ciris_engine.logic.utils import localization as loc

    monkeypatch.delenv("CIRIS_LOCALIZATION_DIR", raising=False)
    assert not list(LOCALIZATION.glob("*.json")), "no JSON at localization/ top level"
    assert loc._get_localization_dir().resolve() == LOCALIZED.resolve()


def test_read_only_modes_never_mutate_anything(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    before = _snapshot(LOCALIZED, LOCALIZATION)
    common = ["--version", "1.2b"]
    assert AL.main([*common, "--segments"]) == 0
    AL.main([*common, "--check"])
    AL.main([*common, "--lane", "translate", "--lang", "yo", "--dry-run", "--max-keys", "5000"])
    AL.main([*common, "--glossary-report"])
    AL.main([*common, "--verify"])
    for name in ("localize", "check_localization_sync", "glossary"):
        sys.modules.pop(name, None)
    monkeypatch.setenv("LOCALIZE_TARGET", "ui")
    import importlib

    ui = importlib.import_module("localize")
    assert ui.CANONICAL.resolve() == LOCALIZED.resolve()
    monkeypatch.setattr(sys, "argv", ["localize.py", "--check"])
    ui.main()
    capsys.readouterr()
    assert _snapshot(LOCALIZED, LOCALIZATION) == before


# ─────────────────────────────────────────────────────────────────────────────
# --mode batch (run 38598155352: rung 0 404'd for every locale)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("flags", [["--mode", "batch"], ["--mode=batch"]])
def test_batch_mode_is_refused_before_anything_is_staged(flags: List[str]) -> None:
    """OpenRouter serves ``:batch`` slugs only through its async batch API; the
    chat endpoint answers 404, so rung 0 was lost and the report halved costs
    that were billed in full."""
    before = _snapshot(LOCALIZED, LOCALIZATION)
    with pytest.raises(SystemExit, match="--mode batch"):
        AL.main(["--version", "1.2b", "--lane", "translate", "--lang", "yo", *flags])
    assert _snapshot(LOCALIZED, LOCALIZATION) == before


def test_fast_mode_is_not_refused() -> None:
    AL.refuse_batch_mode(["--lane", "translate", "--mode", "fast"])
    AL.refuse_batch_mode(["--keys", "batch"])  # a value named batch is not the mode


@pytest.mark.parametrize("flags", [["--mode", "batch"], ["--mode=batch"]])
def test_run_lane_refuses_batch_mode_for_both_targets(flags: List[str]) -> None:
    for target in ("accord", "ui"):
        env = {**os.environ, "TARGET": target, "LANE": "translate", "ACCORD_VERSION": "1.2b"}
        env.pop("OPENROUTER_API_KEY", None)
        proc = subprocess.run(
            ["bash", str(LOCALIZATION / "run_lane.sh"), *flags],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert proc.returncode == 2, (target, proc.stdout, proc.stderr)
        assert "--mode batch" in proc.stderr


def test_no_i18n_workflow_offers_batch_mode() -> None:
    for wf in sorted((REPO / ".github" / "workflows").glob("i18n-*.yml")):
        assert "[fast, batch]" not in wf.read_text(encoding="utf-8"), wf.name


# ─────────────────────────────────────────────────────────────────────────────
# Drafting rung and glossary hooks (VENDORED.md, "Local divergences")
# ─────────────────────────────────────────────────────────────────────────────


def _fresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **env: str) -> Any:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    stage = AL.Stage("1.2b", stage_dir=tmp_path / "stage")
    stage.build()
    L = AL.import_localize(stage.dir)
    vendored = L.LADDER
    AL.install(L, stage, {})
    return L, vendored


def test_the_drafting_rung_is_muse_and_only_rung_0_moves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    L, vendored = _fresh(tmp_path, monkeypatch, LOCALIZE_PROVIDER="openrouter")
    assert vendored[0].startswith("anthropic/"), "precondition: the vendored drafter is Claude"
    assert L.LADDER[0] == AL.ACCORD_DRAFTER == "meta/muse-spark-1.3"
    assert L.LADDER[1:] == vendored[1:], "the repair rungs are the vendored ones"
    assert L.PRICE[AL.ACCORD_DRAFTER] == (1.25, 4.25), "the spend report prices the new rung"
    assert all(m in L.PRICE for m in L.LADDER)


def test_an_explicit_ladder_still_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    L, _ = _fresh(tmp_path, monkeypatch, LOCALIZE_PROVIDER="openrouter", LOCALIZE_LADDER="a/x,b/y")
    assert L.LADDER == ("a/x", "b/y")


def test_a_term_seen_only_inside_a_longer_term_is_not_sent() -> None:
    def mentions(term: str, texts: List[str]) -> bool:
        return re.search(rf"\b{re.escape(term.lower())}\b", " ".join(texts).lower()) is not None

    only_inside = ["a post-quantum decentralized constitutional mesh"]
    assert AL.drop_contained(["Constitutional Mesh", "Constitutional"], only_inside, mentions) == [
        "Constitutional Mesh"
    ]
    both = ["Defer to the Wise Authority.", "Authority is earned."]
    assert AL.drop_contained(["Wise Authority", "Authority"], both, mentions) == ["Wise Authority", "Authority"]
    assert AL.drop_contained(["Authority"], ["Wise Authority"], mentions) == ["Authority"], "no longer term chosen"


def test_relevant_drops_contained_terms_through_the_vendored_glossary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    L, _ = _fresh(tmp_path, monkeypatch)
    probe = ["The Trust Topology is public."]
    vendored = L.gloss.terms("yo")
    assert "Trust Topology" in vendored and "Trust" in vendored, "precondition"
    sent = L.gloss.relevant("yo", probe)
    assert "Trust Topology" in sent and "Trust" not in sent
    assert "Trust" in L.gloss.relevant("yo", probe + ["Trust is earned."])


def test_translation_master_substitutes_only_the_two_terms_of_art() -> None:
    m = AL.translation_master
    assert m("a conformance condition, which the wire alone decides (CC 1.13.3).") == (
        "a conformance condition, which the signed records nodes exchange alone decide (CC 1.13.3)."
    )
    assert m("nothing on the wire can make it") == "nothing in the signed records nodes exchange can make it"
    assert m("however conformant its wire behaviour is: the wire judges conformance") == (
        "however conformant its behaviour in the signed records nodes exchange is: "
        "the signed records nodes exchange judge conformance"
    )
    assert m("The wire carries it: consent") == "The signed records nodes exchange carry it: consent"
    assert m("In this text, *the wire* means the signed records") == (
        "In this text, the English term *the wire* means the signed records"
    )
    assert m("a person with unconditional standing and a person's standing") == (
        "a person with an unconditional place under the guarantees and a person's place under the guarantees"
    )
    for untouched in ("a standing roster", "the standing class", "Care is not standing", "more moral standing"):
        assert m(untouched) == untouched


def test_the_ethics_master_is_derived_and_keys_the_digests() -> None:
    stage = AL.Stage("1.3", stem="constitution_ethics")
    changed = {k for k in stage.en if stage.en[k] != stage.canon[k]}
    assert changed, "the 1.3 canon uses both terms of art"
    for k, text in stage.en.items():
        assert re.sub(r"\*the wire\*", "", text).lower().count("the wire") == 0, k
        assert stage.digests[k] == seg.source_digest(text)
    # The shipped canon is untouched: the skeleton still reassembles it.
    assert seg.reassemble(stage.doc) == stage.source_text
    assert AL.Stage("1.2b").en == AL.Stage("1.2b").canon, "the accord keeps translating its canon"
