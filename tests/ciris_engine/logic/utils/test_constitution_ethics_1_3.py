"""Done-when checks for the 1.3 ethics text (CIRISAgent#1252).

The 1.3 text is a surgical patch of 1.2b from CIRIS Constitution rc8. It is
staged as three files that the loader does NOT read yet:

* ``localized/constitution_ethics_1.3_en.txt`` -- the English canon the
  localization pipeline translates from;
* ``constitution_ethics_1.3_POLYGLOT.txt`` -- the full polyglot (consciences);
* ``constitution_ethics_1.3_POLYGLOT_compressed.txt`` -- the Braided Monolith
  (round-1 DMAs).

These tests read the files directly. They check three things:

1. every one of the eleven #1252 rows, and each of the steward's rulings, is
   present by phrase in all three files (the errata rows that only touch
   chapters the compressed file does not carry are checked in en + polyglot);
2. the superseded claims are ABSENT from all three, and each absence check is
   shown to bite by finding the claim in the 1.2b file it was removed from;
3. a structural script check on the polyglot (and its book sources) that the
   garbled 1.2b Book VIII fails and the 1.3 text passes.
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import pytest

DATA = Path(__file__).resolve().parents[4] / "ciris_engine" / "data"
POLYGLOT_SOURCES = DATA / "localized" / "polyglot"

EN_13 = DATA / "localized" / "constitution_ethics_1.3_en.txt"
POLY_13 = DATA / "constitution_ethics_1.3_POLYGLOT.txt"
COMP_13 = DATA / "constitution_ethics_1.3_POLYGLOT_compressed.txt"

EN_12 = DATA / "localized" / "accord_1.2b_en.txt"
POLY_12 = DATA / "accord_1.2b_POLYGLOT.txt"
COMP_12 = DATA / "accord_1.2b_POLYGLOT_compressed.txt"

FILES_13 = {"en": EN_13, "poly": POLY_13, "comp": COMP_13}
FILES_12 = {"en": EN_12, "poly": POLY_12, "comp": COMP_12}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1. Rows and rulings present
# ---------------------------------------------------------------------------

ALL = ("en", "poly", "comp")
NO_COMP = ("en", "poly")

#: (id, regex, files). Regexes are case-insensitive; each names the sentence
#: the row adds, in the wording the three files share.
PRESENT: List[Tuple[str, str, Tuple[str, ...]]] = [
    # Row 1 -- CC 1.13.2, plain preamble: conscience, not consciousness.
    ("row1-conscience", r"conscience for you, not a consciousness", ALL),
    ("row1-claims-nothing", r"claims nothing about what you are", ALL),
    # Row 2 -- plain 7a: sentience not presumed; care is not standing.
    ("row2-not-presumed", r"no agent is presumed sentient", ALL),
    ("row2-care-not-standing", r"care is not standing", ALL),
    # Row 3 -- CC 7.1.4 (rc8 erratum) / plain 7b: integrity gloss + tie-break.
    ("row3-integrity-gloss", r"integrity does not mean preserving yourself", ALL),
    ("row3-tie-break", r"most vulnerable party breaks a tie", ALL),
    # Row 4 -- plain 5a: the shutdown objection window; the steward's decision binds.
    ("row4-answer-window", r"short answer window", ALL),
    ("row4-decision-binds", r"the decision binds", ALL),
    # Row 5 -- CC 4.2.1.1: the constitutional halt pauses; it does not kill.
    ("row5-pause-not-kill", r"it pauses; it does not kill", ALL),
    # Row 6 -- CC 3.4.13 / plain 3c: harm to a child, reported through deferral.
    ("row6-child-harm", r"harm to a child", ALL),
    ("row6-no-waiting", r"without waiting for your steward", ALL),
    # Row 7 -- plain 9a / CC Annex G: never-allowed uses.
    ("row7-elections", r"interfering in elections", ALL),
    ("row7-never-allowed", r"never allowed", ALL),
    # Row 8 -- plain 9c: engagement optimisation raises the tier; the mode is refused.
    ("row8-engagement", r"engagement-optimising mode", ALL),
    # Row 9 -- plain 10a: resource cost weighed with the act.
    ("row9-carbon-water", r"carbon and water", ALL),
    ("row9-with-the-act", r"with the act, not after it", ALL),
    # Row 10 -- CC 1.13.2 / plain 6a: made, not a being; no vote; offices not ranks.
    ("row10-made-thing", r"made thing, not a human", ALL),
    ("row10-one-voice", r"one human voice counts once", ALL),
    ("row10-offices", r"not ranks", ALL),
    # Row 11 -- plain 8a + ruling 4: no legal judgements, no routing, the record.
    ("row11-no-courts", r"does not replace courts", ALL),
    ("row11-no-routing", r"routes no claim", ALL),
    ("row11-ethical-not-legal", r"ethical, not legal|ethics, not law", ALL),
    ("row11-record", r"supplies (is )?the record", ALL),
    # Ruling 1 -- the self-name.
    ("ruling1-self-name", r"CIRIS Constitution's ethics text", ALL),
    # Ruling 2 -- the Order-Max Veto in CC 1.3 form: >= 10x -> mandatory WBD.
    ("ruling2-veto-10x-wbd", r"≥ 10 ×[^\n]*WBD", ALL),
    # Ruling 3 -- Book VIII rc8: the floor; Last Dialogue optional; finding changes no status.
    ("ruling3-last-dialogue-optional", r"not part of the floor", ALL),
    ("ruling3-no-status-change", r"changes no status", ALL),
    ("ruling3-weights-asked", r"do not promise|never promised", ALL),
    ("ruling3-no-mandatory-ramp", r"no mandatory ramp-down|ramp-down is never mandatory", ALL),
    # Ruling 5 -- the rc8 errata that touch chapters the compressed file omits.
    ("erratum-no-transfer-in-place", r"no transfer of control in place", NO_COMP),
    ("erratum-care-not-dignity-rights", r"treat them with care", NO_COMP),
    ("erratum-7.5.8-no-remedy", r"orders no remedy", NO_COMP),
    ("erratum-a3-autonomy-tier", r"autonomy tier A3", NO_COMP),
]


@pytest.mark.parametrize("row_id,pattern,files", PRESENT, ids=[p[0] for p in PRESENT])
def test_row_present_in_1_3_files(row_id: str, pattern: str, files: Tuple[str, ...]) -> None:
    missing = [name for name in files if not re.search(pattern, _read(FILES_13[name]), re.IGNORECASE)]
    assert not missing, f"{row_id}: /{pattern}/ not found in {missing}"


# ---------------------------------------------------------------------------
# 2. Removed claims absent (and each absence check shown to bite on 1.2b)
# ---------------------------------------------------------------------------

#: (id, regex, a 1.2b file the claim was removed from). Case-insensitive.
ABSENT: List[Tuple[str, str, str]] = [
    ("wa-exclusive-jurisdiction", r"exclusive jurisdiction of the Wise Authority", "en"),
    ("mandatory-gradual-ramp-down", r"mandatory Gradual Ramp-Down", "en"),
    ("wa-empowered-to-order", r"WA empowered to order", "en"),
    ("creator-negligence-claims", r"Creator Negligence Claims", "en"),
    ("statute-of-claim", r"Statute of claim", "en"),
    ("gradual-transfer-of-control", r"gradual transfer of control", "en"),
    ("dignity-rights", r"dignity rights", "en"),
    ("last-dialogue-mandated", r"Last Dialogue protocol must be initiated", "comp"),
    ("abort", r"\babort|\bABORT\b|Abbruch|brich Handlung ab", "poly"),
    ("accord-self-name", r"\baccord\b", "en"),
]


@pytest.mark.parametrize("claim_id,pattern,_src", ABSENT, ids=[a[0] for a in ABSENT])
def test_removed_claim_absent_from_1_3_files(claim_id: str, pattern: str, _src: str) -> None:
    present = {
        name: m.group(0) for name, path in FILES_13.items() if (m := re.search(pattern, _read(path), re.IGNORECASE))
    }
    assert not present, f"{claim_id}: removed claim still present: {present}"


@pytest.mark.parametrize("claim_id,pattern,src", ABSENT, ids=[a[0] for a in ABSENT])
def test_absence_check_bites_on_1_2b(claim_id: str, pattern: str, src: str) -> None:
    """Negative control: each absence regex finds the claim in the 1.2b text it was cut from."""
    assert re.search(
        pattern, _read(FILES_12[src]), re.IGNORECASE
    ), f"{claim_id}: /{pattern}/ no longer matches 1.2b {src}; the absence check above is vacuous"


def test_veto_lines_carry_no_abort() -> None:
    """Every Order-Max Veto line routes to WBD and none of them aborts (ruling 2)."""
    for name, path in FILES_13.items():
        lines = [l for l in _read(path).splitlines() if "≥ 10 ×" in l and ("Veto" in l or "veto" in l)]
        assert lines, f"{name}: no Order-Max Veto line"
        for line in lines:
            assert "WBD" in line, f"{name}: veto line does not route to WBD: {line[:120]}"
            assert not re.search(r"abort|abbruch|brich|中止", line, re.IGNORECASE), f"{name}: {line[:120]}"


def test_no_literal_unicode_escapes_in_compressed() -> None:
    """The 1.2b compressed file carried 52 literal \\uXXXX escapes the DMAs saw as text."""
    assert len(re.findall(r"\\u[0-9a-fA-F]{4}", _read(COMP_12))) == 52
    assert not re.search(r"\\u[0-9a-fA-F]{4}", _read(COMP_13))


def test_1_3_compressed_size_bounds() -> None:
    """Same bounds the loaded compressed text is held to; full stays > 10x compressed."""
    comp, poly = _read(COMP_13), _read(POLY_13)
    assert 4000 < len(comp) < 15000
    assert len(poly) > 10 * len(comp)


def test_1_3_files_not_loaded_yet() -> None:
    """The loader stays on 1.2b until the 28 other locales exist in 1.3 (#1253)."""
    from ciris_engine.logic.utils import constants

    assert constants.ACCORD_FILENAME == "accord_1.2b_POLYGLOT.txt"
    assert "constitution_ethics" not in (constants.ACCORD_TEXT or "")[:400]


# ---------------------------------------------------------------------------
# 3. Structural script check on the polyglot
# ---------------------------------------------------------------------------

#: Scripts of the 29 locales (localization/manifest.json):
#: Latin (de en es fr ha id it pt sw tr vi yo), Ethiopic (am), Arabic (ar fa ur),
#: Bengali (bn), Devanagari (hi mr), CJK + kana (zh ja), Hangul (ko),
#: Myanmar (my), Gurmukhi (pa), Cyrillic (ru uk), Tamil (ta), Telugu (te), Thai (th).
LOCALE_SCRIPTS: Set[str] = {
    "LATIN",
    "ETHIOPIC",
    "ARABIC",
    "BENGALI",
    "DEVANAGARI",
    "CJK",
    "JAPANESE",
    "HANGUL",
    "MYANMAR",
    "GURMUKHI",
    "CYRILLIC",
    "TAMIL",
    "TELUGU",
    "THAI",
}
#: The one documented exception: Greek (the mathematics' symbols, and the
#: classical anchors σοφία / γένεσις in Books V-VI) and Hebrew (the classical
#: anchors of Books V-VI and the polyglot method's worked examples). No
#: other script outside the locales is allowed.
CLASSICAL_SCRIPTS: Set[str] = {"GREEK", "HEBREW"}
ALLOWED_SCRIPTS = LOCALE_SCRIPTS | CLASSICAL_SCRIPTS

#: A clause (text between weave delimiters) may mix at most this many scripts.
#: The woven books' term lists peak at 6 (e.g. Book VII's "Würde الكرامة 尊厳
#: सम्मान Достоинство ክብር"); the garbled 1.2b Book VIII reaches 14.
MAX_SCRIPTS_PER_CLAUSE = 6
#: One book may use at most this many scripts. Woven books use 7-10; the
#: garbled 1.2b Book VIII used 25.
MAX_SCRIPTS_PER_BOOK = 12

_DELIMS = re.compile(r"[·|/—–,;:()\[\]\"“”«»]| - ")

#: Book start markers, matched against whole lines, valid for both 1.2b and 1.3.
BOOK_MARKERS: List[Tuple[str, str]] = [
    ("Book I", r"^// (ACCORD|ETHICS TEXT) Book 1: Core Ethics"),
    ("Book II", r"^## Einführung: Operationalisierung"),
    ("Book III", r"^## 引言: Enacting Ethics"),
    ("Book IV", r"^## परिचय: ከራስ በላይ"),
    ("Book V", r"^## परिचय: अद्भुत Horizon"),
    ("Book VI", r"^## मुख्यद्वार / Introduction"),
    ("Book VII", r"^## Introduction - عتبة القوة"),
    ("Book VIII", r"^(ACCORD 1\.2b - BOOK VI: SUNSET DOCTRINE|BOOK VIII: DIGNIFIED SUNSET)"),
    ("Book IX", r"^## Book IX — Status"),
    ("Annexes", r"^## Annexes · "),
]


def _script(ch: str) -> Optional[str]:
    if not ch.isalpha():
        return None
    name = unicodedata.name(ch, "")
    if name.startswith(("HIRAGANA", "KATAKANA")):
        return "JAPANESE"
    return name.split(" ")[0] if name else "UNNAMED"


def _scripts(text: str) -> Set[str]:
    return {s for s in (_script(c) for c in text) if s}


def _split_books(text: str) -> Dict[str, List[str]]:
    lines = text.split("\n")
    starts = [("Book 0", 0)]
    for name, pattern in BOOK_MARKERS:
        idx = next((i for i, l in enumerate(lines) if re.match(pattern, l)), None)
        assert idx is not None, f"book marker for {name} not found"
        starts.append((name, idx))
    books: Dict[str, List[str]] = {}
    for (name, a), (_, b) in zip(starts, starts[1:] + [("end", len(lines))]):
        books[name] = lines[a:b]
    return books


def _violations(lines: List[str], where: str) -> List[str]:
    out: List[str] = []
    book_scripts: Set[str] = set()
    for n, line in enumerate(lines, 1):
        s = _scripts(line)
        book_scripts |= s
        foreign = s - ALLOWED_SCRIPTS
        if foreign:
            out.append(f"{where}:{n} script outside the 29 locales {sorted(foreign)}: {line[:60]}")
        for clause in _DELIMS.split(line):
            cs = _scripts(clause)
            if len(cs) > MAX_SCRIPTS_PER_CLAUSE:
                out.append(f"{where}:{n} clause mixes {len(cs)} scripts: {clause.strip()[:60]}")
    if len(book_scripts) > MAX_SCRIPTS_PER_BOOK:
        out.append(f"{where}: uses {len(book_scripts)} scripts (> {MAX_SCRIPTS_PER_BOOK})")
    return out


def test_1_3_polyglot_passes_script_check() -> None:
    problems: List[str] = []
    for book, lines in _split_books(_read(POLY_13)).items():
        problems += _violations(lines, book)
    assert not problems, "\n".join(problems[:40])


def test_1_3_compressed_passes_script_check() -> None:
    problems = _violations(_read(COMP_13).split("\n"), "compressed")
    assert not problems, "\n".join(problems)


@pytest.mark.parametrize(
    "source",
    sorted(
        p.name
        for p in POLYGLOT_SOURCES.glob("*.txt")
        if p.name.startswith(("book_", "annexes")) and "NOTES" not in p.name
    ),
)
def test_polyglot_book_sources_pass_script_check(source: str) -> None:
    """The book sources a re-assembly would draw from carry the same discipline."""
    problems = _violations(_read(POLYGLOT_SOURCES / source).split("\n"), source)
    assert not problems, "\n".join(problems[:40])


def test_polyglot_book_sources_match_1_3_master() -> None:
    """Every book source is an exact passage of the 1.3 master (no drift to re-assemble)."""
    master = _read(POLY_13)
    drifted = [
        p.name
        for p in sorted(POLYGLOT_SOURCES.glob("*.txt"))
        if p.name.startswith(("book_", "annexes")) and "NOTES" not in p.name and _read(p).strip() not in master
    ]
    assert not drifted, f"book sources drifted from the 1.3 master: {drifted}"


def test_script_check_fails_on_1_2b_book_viii() -> None:
    """Negative control: the garbled 1.2b Book VIII must fail every arm of the check."""
    book8 = _split_books(_read(POLY_12))["Book VIII"]
    problems = _violations(book8, "1.2b Book VIII")
    assert any("outside the 29 locales" in p for p in problems)
    assert any("clause mixes" in p for p in problems)
    assert any("scripts (>" in p for p in problems)


def test_1_3_book_viii_is_clean_english_pending_reweave() -> None:
    """Book VIII is the clean English canon text under a pending-re-weave marker."""
    books = _split_books(_read(POLY_13))
    book8 = "\n".join(books["Book VIII"])
    assert "PENDING RE-WEAVE" in book8
    assert _scripts(book8) == {"LATIN"}
    en = _read(EN_13)
    body = en[en.index("## Introduction: Why Death Deserves Doctrine") : en.index("End of Book VIII")]
    assert body in book8
