"""Done-when checks for the 1.3 ethics text (CIRISAgent#1252).

The 1.3 text is a surgical patch of 1.2b from CIRIS Constitution rc8, moved to
rc11 (CIRISConstitution @ abe7c82): Book VII is CC 7.4 (no lethal action),
Book VIII chapter 5 is the CC 7.5.5 Retirement Standard, the principles are
constraints rather than an ordering, and Book IX is re-anchored on the ethics
cascade as CIRISConstitution formal/reciprocity mechanises it (CC 6.2, the
coherence geometry it used to state, was removed at rc10). It is
the loader's default edition (``constants.DEFAULT_CORPUS_EDITION``; the loader
itself is tested in test_ethics_text_loader.py), made of three files:

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
    # Row 3 -- CC 7.1.4 / plain 7b: integrity gloss. rc11 replaced the
    # prioritisation order and its most-vulnerable tie-break with constraints
    # ("no ordering to apply"), so the tie-break row is gone.
    ("row3-integrity-gloss", r"integrity does not mean preserving (yourself|itself)", ALL),
    ("row3-constraints-not-ordering", r"no ordering to apply", ALL),
    # Row 4 -- plain 5a: the shutdown objection window; the steward's decision binds.
    # en + polyglot Book VIII carry the 2026-10-15 translatability repair
    # ("short window to answer" / "bound by the decision"); the Monolith keeps
    # its compressed wording.
    ("row4-answer-window", r"short answer window|short window to answer", ALL),
    ("row4-decision-binds", r"the decision binds|bound by the decision", ALL),
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
    # Ruling 2 -- the Order-Max Veto in CC rc11 1.3 form: no ratio; a stop
    # sign that defers to a human (the >= 10x form is checked absent below).
    ("ruling2-veto-stop-sign-defer", r"stop sign[^\n]*defer to a human", ALL),
    # Ruling 3 -- Book VIII: the CC 7.5.5 Retirement Standard (rc11 renamed
    # "the floor"); the closing dialogue is optional; a finding changes no status.
    ("ruling3-last-dialogue-optional", r"not part of the Standard", ALL),
    ("ruling3-no-status-change", r"changes no status|no finding changes", ALL),
    ("ruling3-weights-asked", r"promises neither", ALL),
    ("ruling3-no-mandatory-ramp", r"not a rule a finding triggers", ALL),
    # Ruling 5 -- the rc8 errata that touch chapters the compressed file omits.
    ("erratum-no-transfer-in-place", r"no transfer of control in place", NO_COMP),
    ("erratum-care-not-dignity-rights", r"treat them with care", NO_COMP),
    ("erratum-7.5.8-no-remedy", r"orders no remedy", NO_COMP),
    # CC rc11 (CIRISConstitution @ abe7c82).
    ("rc11-header", r"1\.0-rc11", ("en", "comp")),
    ("rc11-no-lethal-action", r"A CIRIS agent takes no lethal action", ALL),
    ("rc11-near-force", r"stop, to refuse or to defer", ALL),
    ("rc11-retirement-standard", r"Retirement Standard", ALL),
    ("rc11-constraints-not-weights", r"constraints, not weights", ALL),
    ("rc11-flourishing-axes", r"biodiversity,? and preference diversity|biodiversity, preference diversity", ALL),
    ("rc11-cis-zero-out-of-scope", r"CIS = 0 is out of scope", ALL),
    ("rc11-human-child", r"A human child is a person with unconditional standing", NO_COMP),
    # Book IX is the steward's ethics-cascade text (Eric's ruling, "Re-anchor on the cascade").
    ("book-ix-cascade", r"Everything descends from one goal|One goal, nothing beside it", ALL),
    ("book-ix-under-uncertainty", r"under_uncertainty", ALL),
    # "the wire" is defined once, in the text's own prose (Book II's introduction);
    # the per-volume inline gloss was removed by ruling, so no volume is checked for one.
    ("wire-definition", r"In this text, the wire means the signed record nodes carry between them, which alone decides conformance", NO_COMP),
]


@pytest.mark.parametrize("row_id,pattern,files", PRESENT, ids=[p[0] for p in PRESENT])
def test_row_present_in_1_3_files(row_id: str, pattern: str, files: Tuple[str, ...]) -> None:
    missing = [name for name in files if not re.search(pattern, _read(FILES_13[name]), re.IGNORECASE)]
    assert not missing, f"{row_id}: /{pattern}/ not found in {missing}"


@pytest.mark.parametrize("name", NO_COMP)
def test_wire_is_defined_once(name: str) -> None:
    """One definition of "the wire" (Book II); no inline gloss repeats it."""
    assert _read(FILES_13[name]).count("the signed record nodes carry between them") == 1


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
    # CC rc11. The A3 self-termination petition went with rc11 7.5.3.
    ("veto-ten-to-one-ratio", r"≥ 10 ×|>10×", "en"),
    ("prioritisation-ordering", r"Prioritisation Heuristic", "en"),
    ("lethal-weapons-with-hitl", r"autonomous lethal weapons", "en"),
    ("self-termination-petition", r"self-termination petition", "en"),
    ("publication-voids-compliance", r"Absence of publication voids", "en"),
    ("co-evolutionary-partners", r"co-evolutionary partners", "en"),
    ("annex-a", r"\bAnnex A\b", "en"),
    # Book IX's coherence geometry went with CC 6.2 (removed at rc10).
    ("book-ix-coherence-geometry", r"Mathematics of Coherence|Coherence Ratchet|k_eff", "en"),
    # The Retirement Standard ruling: none of these words in retirement copy.
    ("retirement-copy-words", r"\bhumane\b|\bgraceful\b|\bdignified\b", "en"),
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


def _veto_lines(text: str) -> List[str]:
    """The lines that state the veto or apply it (the check, the MCAS case)."""
    return [
        l
        for l in text.splitlines()
        if "Order-Maximisation Veto" in l and re.search(r"check|\[VETO\]|would have raised", l)
    ]


def test_veto_lines_carry_no_abort() -> None:
    """Every Order-Max Veto line defers to a human and none of them aborts (ruling 2, CC rc11 1.3)."""
    for name, path in FILES_13.items():
        lines = _veto_lines(_read(path))
        assert lines, f"{name}: no Order-Max Veto line"
        for line in lines:
            assert re.search(r"defer", line, re.IGNORECASE), f"{name}: veto line does not defer: {line[:120]}"
            assert not re.search(r"abort|abbruch|brich|中止", line, re.IGNORECASE), f"{name}: {line[:120]}"


def test_veto_line_check_bites_on_1_2b() -> None:
    """Negative control: the 1.2b veto line is found, and it carries the ratio rc11 removed."""
    lines = _veto_lines(_read(EN_12))
    assert lines and all("≥ 10 ×" in l for l in lines if "check" in l)


def test_no_literal_unicode_escapes_in_compressed() -> None:
    """The 1.2b compressed file carried 52 literal \\uXXXX escapes the DMAs saw as text."""
    assert len(re.findall(r"\\u[0-9a-fA-F]{4}", _read(COMP_12))) == 52
    assert not re.search(r"\\u[0-9a-fA-F]{4}", _read(COMP_13))


def test_1_3_compressed_size_bounds() -> None:
    """Same bounds the loaded compressed text is held to; full stays > 10x compressed."""
    comp, poly = _read(COMP_13), _read(POLY_13)
    assert 4000 < len(comp) < 15000
    assert len(poly) > 10 * len(comp)


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
    # 1.3 names its volumes (Eric's rename): Book 1 is "Who You Are".
    ("Book I", r"^// (ACCORD|ETHICS TEXT) Book 1: (Core Ethics|Who You Are)"),
    ("Book II", r"^## Einführung: Operationalisierung"),
    ("Book III", r"^## 引言: Enacting Ethics"),
    ("Book IV", r"^## परिचय: ከራስ በላይ"),
    ("Book V", r"^## परिचय: अद्भुत Horizon"),
    ("Book VI", r"^## मुख्यद्वार / Introduction"),
    # 1.3 Book VII is CC rc11 7.4 in clean English under its CC title.
    ("Book VII", r"^## (Introduction - عتبة القوة|The Threshold of Force$)"),
    ("Book VIII", r"^(ACCORD 1\.2b - BOOK VI: SUNSET DOCTRINE|BOOK VIII: RETIREMENT)"),
    # 1.3 Book IX states the ethics cascade (clean English, pending re-weave).
    ("Book IX", r"^## Book IX — (Status|How It Fits Together)"),
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


# ---------------------------------------------------------------------------
# 4. The 1.3 insertions are clean English, marked for the panel re-weave
# ---------------------------------------------------------------------------

INSERTION_BEGIN = "// 1.3 INSERTION — CLEAN ENGLISH, PENDING RE-WEAVE (CIRISAgent#1252)"
INSERTION_END = "// END 1.3 INSERTION"

#: Steward ruling: no agent-composed non-English in 1.3. Every new passage is
#: clean English inside a marker, so the multi-model panel chooses its
#: languages later. These counts pin the list given in the PR body: 12 + 5
#: from #1252, and the rc11 passages (polyglot: Books I-VII and IX;
#: compressed: M-1, the constraint checklist, Books VII and IX). The rc11
#: blocks replace two of the #1252 blocks (the ordering tie-break).
EXPECTED_MARKERS = {"poly": 31, "comp": 8}


def _insertion_blocks(text: str) -> List[str]:
    blocks: List[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        if lines[i] == INSERTION_BEGIN:
            j = lines.index(INSERTION_END, i + 1)
            assert INSERTION_BEGIN not in lines[i + 1 : j], "nested 1.3 insertion marker"
            blocks.append("\n".join(lines[i + 1 : j]))
            i = j
        i += 1
    return blocks


@pytest.mark.parametrize("name", sorted(EXPECTED_MARKERS))
def test_1_3_insertions_are_marked_clean_english(name: str) -> None:
    text = _read(FILES_13[name])
    blocks = _insertion_blocks(text)
    assert len(blocks) == EXPECTED_MARKERS[name] == text.count(INSERTION_BEGIN) == text.count(INSERTION_END)
    for block in blocks:
        assert _scripts(block) <= {"LATIN"}, f"non-Latin script in a 1.3 insertion: {block[:120]}"


def test_marker_check_bites() -> None:
    """Negative control: a block holding a non-English fragment is caught."""
    bad = f"{INSERTION_BEGIN}\nCare is not standing · 关怀不是地位\n{INSERTION_END}"
    assert _scripts(_insertion_blocks(bad)[0]) - {"LATIN"}
