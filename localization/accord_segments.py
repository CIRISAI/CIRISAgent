"""Segment the CIRIS Accord into stable keys, and put it back together.

AGENT-OWNED. This is not part of the vendored CIRISClient pipeline (see
``localization/VENDORED.md``); it is the adapter that lets that key-based
pipeline translate a long prose document.

The vendored ``localize.py`` translates FLAT DOTTED KEYS. The Accord is ~1,100
lines of covenant prose in an MDX-derived text format. This module turns the
English source into ``{key: line}`` plus a *skeleton* -- everything that is
structure rather than prose -- and turns a ``{key: translated line}`` map back
into the exact file format ``_load_localized_accord_file`` loads.

ONE KEY PER NON-BLANK LINE. The shipped translations agree with the English on
non-blank lines far more often than on blank-line paragraphs (lists and
paragraphs were re-wrapped by translators; lines mostly were not), so line keys
are what the translation memory can actually be aligned on. They also keep each
request small enough that a non-Latin locale's reply fits the output cap.

Round trip is LOSSLESS by construction and by test: ``reassemble(parse(src))``
returns ``src`` byte for byte. The skeleton keeps every blank line, fence,
marker, formula and markup prefix; only line text is replaced.

Key scheme (lowercase ASCII, nested on ``.`` by the writer)::

    accord.<unit>.meta.title          front-matter value (``title: ...``)
    accord.<unit>.meta.description    front-matter value (``description: ...``)
    accord.<unit>.sNN.title           the NNth ``## `` heading of the unit
    accord.<unit>.sNN.lBB             the BBth translatable line of section NN

``<unit>`` is the ``// content/sections/<path>`` stem (``main/v1.mdx`` ->
``v1``, ``foreword/section0.mdx`` -> ``section0``); a front-matter block with
no marker (the Annexes) is named from its English ``title:`` (``annexes``).
``s00`` is whatever precedes a unit's first ``## `` heading. Keys are positional
within one section only. A line whose English changes keeps its key; the value
translated from the old English is invalidated by its recorded source digest
(``source_digest``), never left in place -- see ``accord_localize.Stage``.

Never segmented (verbatim in the skeleton, never sent to a model): the
provenance preamble before the first marker (every shipped locale keeps it in
English), ``// content/sections/`` markers, ``---`` fences and rules,
front-matter keys, formula lines, and any line with no letters in it.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Union

KEY_ROOT = "accord"

MARKER = "// content/sections/"

#: Lines that must survive translation byte-for-byte. A formula that has been
#: "translated" is a different formula. ``tools/accord_i18n.py``'s set, plus
#: the stewardship-tier formula (``ST = ceil(...)``).
FORMULA = re.compile(r"J = k_eff|k_eff = k /|^\s*\*\*C ∝|V\(k\) =|ST = ceil\(")

#: Constitution references, which stay exactly as written in every locale.
CC_REF = re.compile(r"CC \d+(?:\.\d+)*")

#: Claims CC 1.0-rc4 withdrew (``tools/accord_i18n.py``). If one appears in a
#: translation and not in its English line, it came from a stale source.
WITHDRAWN = (
    "topologically improbable",
    "Ethilogics",
    "∝ 1/J",
    "O(1)",
    "O(n)",
    "computationally natural",
    "structurally favored",
    "not a metaphor",
)

#: One representative codepoint range per non-Latin script, to catch a line
#: that came back in English while claiming to be a translation.
SCRIPT = {
    "am": "ሀ-፿",
    "ar": "؀-ۿ",
    "fa": "؀-ۿ",
    "ur": "؀-ۿ",
    "bn": "ঀ-৿",
    "hi": "ऀ-ॿ",
    "mr": "ऀ-ॿ",
    "pa": "਀-੿",
    "ta": "஀-௿",
    "te": "ఀ-౿",
    "th": "฀-๿",
    "my": "က-႟",
    "ja": "぀-ヿ一-鿿",
    "ko": "가-힯",
    "zh": "一-鿿",
    "ru": "Ѐ-ӿ",
    "uk": "Ѐ-ӿ",
}

_HEADING = re.compile(r"^(#{2,6}) (.*)$")
_LIST_ITEM = re.compile(r"^\s*(?:[*-]|\d+\.) ")
_FRONT_MATTER_KEY = re.compile(r"^(title|description): (.*)$")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")


@dataclass(frozen=True)
class Slot:
    """One translatable line and how it sits in the file."""

    key: str
    kind: str  # meta | h2 | h3 | comment | item | line
    prefix: str  # markup kept verbatim in front of the text ("## ", "title: ", "// ", "")
    text: str

    def render(self) -> str:
        return self.prefix + self.text


Piece = Union[str, Slot]


@dataclass
class Document:
    """An accord text as skeleton pieces. Every piece is exactly one line."""

    pieces: List[Piece] = field(default_factory=list)

    @property
    def slots(self) -> List[Slot]:
        return [p for p in self.pieces if isinstance(p, Slot)]

    def segments(self) -> Dict[str, str]:
        return {s.key: s.text for s in self.slots}

    def units(self) -> List[str]:
        seen: List[str] = []
        for s in self.slots:
            unit = s.key.split(".")[1]
            if unit not in seen:
                seen.append(unit)
        return seen


def _slug(path: str) -> str:
    stem = path.strip()
    if stem.endswith(".mdx"):
        stem = stem[: -len(".mdx")]
    stem = stem.rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]+", "_", stem.lower()).strip("_")


def _has_letters(text: str) -> bool:
    return any(ch.isalpha() for ch in text)


def _front_matter_title(lines: Sequence[str], i: int) -> str:
    for k in range(i + 1, min(i + 8, len(lines))):
        m = _FRONT_MATTER_KEY.match(lines[k])
        if m and m.group(1) == "title":
            return m.group(2)
        if lines[k].strip() == "---":
            break
    return ""


def _opens_front_matter(lines: Sequence[str], i: int) -> bool:
    if lines[i].strip() != "---":
        return False
    k = i + 1
    while k < len(lines) and lines[k].strip() == "":
        k += 1
    return k < len(lines) and _FRONT_MATTER_KEY.match(lines[k]) is not None


def parse(text: str) -> Document:
    """Split ``text`` into skeleton lines and keyed slots. Lossless."""
    lines = text.split("\n")
    doc = Document()
    unit: Optional[str] = None
    section = 0
    line_no = 0
    in_front_matter = False
    unit_ordinal = 0
    used_units: Dict[str, int] = {}

    def key(tail: str) -> str:
        assert unit is not None
        return f"{KEY_ROOT}.{unit}.{tail}"

    def open_unit(slug: str) -> None:
        nonlocal unit, section, line_no, unit_ordinal
        slug = slug or f"u{unit_ordinal:02d}"
        n = used_units.get(slug, 0)
        used_units[slug] = n + 1
        unit = slug if n == 0 else f"{slug}_{n + 1}"
        section = 0
        line_no = 0
        unit_ordinal += 1

    def body(kind: str, prefix: str, content: str) -> None:
        nonlocal line_no
        line_no += 1
        doc.pieces.append(Slot(key(f"s{section:02d}.l{line_no:02d}"), kind, prefix, content))

    for i, line in enumerate(lines):
        if in_front_matter:
            if line.strip() == "---":
                in_front_matter = False
                doc.pieces.append(line)
                continue
            fm = _FRONT_MATTER_KEY.match(line)
            if fm and _has_letters(fm.group(2)):
                doc.pieces.append(Slot(key(f"meta.{fm.group(1)}"), "meta", f"{fm.group(1)}: ", fm.group(2)))
            else:
                doc.pieces.append(line)
            continue

        if line.startswith(MARKER):
            open_unit(_slug(line[len(MARKER) :]))
            doc.pieces.append(line)
            continue

        if _opens_front_matter(lines, i):
            # A marker in the three lines above already opened this unit; a bare
            # front-matter block (the Annexes) opens one of its own.
            if not any(lines[j].startswith(MARKER) for j in range(max(0, i - 3), i)):
                open_unit(_slug(_front_matter_title(lines, i)))
            in_front_matter = True
            doc.pieces.append(line)
            continue

        if unit is None or line.strip() in ("", "---") or FORMULA.search(line) or not _has_letters(line):
            doc.pieces.append(line)
            continue

        heading = _HEADING.match(line)
        if heading:
            if len(heading.group(1)) == 2:
                section += 1
                line_no = 0
                doc.pieces.append(Slot(key(f"s{section:02d}.title"), "h2", "## ", heading.group(2)))
            else:
                body("h3", heading.group(1) + " ", heading.group(2))
            continue

        if line.startswith("// "):
            body("comment", "// ", line[3:])
            continue

        item = _LIST_ITEM.match(line)
        if item:
            body("item", item.group(0), line[item.end() :])
        else:
            indent = line[: len(line) - len(line.lstrip())]
            body("line", indent, line[len(indent) :])

    return doc


def reassemble(doc: Document, values: Optional[Dict[str, str]] = None) -> str:
    """Render ``doc`` with ``values`` substituted for its slots.

    ``values=None`` renders the source itself. A slot missing from ``values``
    raises: a partial locale is never written as a file, because the only thing
    that could fill the gap is English, and English under a non-English locale
    is the silent demotion this pipeline exists to prevent.
    """
    out: List[str] = []
    missing: List[str] = []
    for piece in doc.pieces:
        if isinstance(piece, str):
            out.append(piece)
            continue
        if values is None:
            out.append(piece.render())
            continue
        text = values.get(piece.key)
        if text is None or not text.strip():
            missing.append(piece.key)
            continue
        out.append(piece.prefix + text)
    if missing:
        raise KeyError(f"{len(missing)} segment(s) have no value: {', '.join(missing[:5])}")
    return "\n".join(out)


def source_digest(text: str) -> str:
    """Short digest of one English line -- what a translation was made from."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Structural rules for a translated line (the old accord_i18n.py guard, per line)
# ─────────────────────────────────────────────────────────────────────────────


def passage_problems(slot: Slot, translated: str, lang: Optional[str] = None) -> List[str]:
    """Why ``translated`` cannot stand in for ``slot`` in the file. Empty = fine.

    Structure (markers, fences, headings, front-matter keys, formulas) is in the
    skeleton and cannot be damaged by a value; these checks stop a value from
    INTRODUCING structure, and enforce what the accord guard always enforced.
    None of them says the translation is good -- that is the evaluate lane.
    """
    bad: List[str] = []
    if "\n" in translated or "\r" in translated:
        bad.append("a segment is one line; the translation contains a line break")
    stripped = translated.strip()
    if stripped == "---" or translated.startswith(MARKER) or _HEADING.match(translated) or stripped.startswith("#"):
        bad.append("translation introduces structure (a fence, marker or heading)")
    if slot.kind != "comment" and translated.startswith("//"):
        bad.append("translation introduces a comment line")
    if slot.kind != "meta" and _FRONT_MATTER_KEY.match(translated):
        bad.append("translation introduces a front-matter key")
    if slot.kind == "line" and _LIST_ITEM.match(translated) and not _LIST_ITEM.match(slot.text):
        bad.append("translation introduces a list marker")
    if FORMULA.search(translated):
        bad.append("translation introduces a formula line the source does not have")
    if sorted(CC_REF.findall(slot.text)) != sorted(CC_REF.findall(translated)):
        bad.append("CC references dropped or altered")
    if slot.text.count("**") != translated.count("**"):
        bad.append("bold markers (**) differ from the source")
    for claim in WITHDRAWN:
        if claim in translated and claim not in slot.text:
            bad.append(f"withdrawn claim reintroduced: {claim!r}")
    if lang and lang != "en" and len(_LATIN_WORD.findall(slot.text)) >= 4:
        if translated.strip() == slot.text.strip():
            bad.append("identical to the English source (untranslated)")
        rng = SCRIPT.get(lang)
        if rng and not re.search(f"[{rng}]", translated):
            bad.append(f"no {lang} script in the translation")
    return bad


# ─────────────────────────────────────────────────────────────────────────────
# Alignment: a shipped locale file against an English skeleton
# ─────────────────────────────────────────────────────────────────────────────


def _section_of(key: str) -> str:
    return key.rsplit(".", 1)[0]


def _shape(slots: Sequence[Slot]) -> List[Tuple[str, str, str]]:
    return [(s.key.rsplit(".", 1)[1], s.kind, s.prefix if s.kind in ("item", "h3") else "") for s in slots]


def align(english: Document, localized: Document) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Map the locale's lines onto the English keys, section by section.

    Returns ``(aligned, skipped)``: ``aligned`` is ``{english_key: locale_text}``
    for every section whose shape (slot kinds, order, list and heading markers)
    matches exactly; ``skipped`` is ``{section: reason}`` for those that do not.
    A positional pairing across a section whose shape differs would pair the
    wrong lines silently, so those sections are left unseeded, not guessed.

    Units are paired by order when both sides have the same number of units,
    else by name -- a locale may translate an Annex title, never a marker.
    """
    en_units = english.units()
    lo_units = localized.units()
    if len(en_units) == len(lo_units):
        unit_map = dict(zip(lo_units, en_units))
    else:
        unit_map = {u: u for u in lo_units if u in en_units}

    def by_section(doc: Document, rename: Optional[Dict[str, str]] = None) -> Dict[str, List[Slot]]:
        grouped: Dict[str, List[Slot]] = {}
        for s in doc.slots:
            parts = s.key.split(".")
            if rename is not None:
                if parts[1] not in rename:
                    continue
                parts[1] = rename[parts[1]]
            k = ".".join(parts)
            grouped.setdefault(_section_of(k), []).append(Slot(k, s.kind, s.prefix, s.text))
        return grouped

    en_sec = by_section(english)
    lo_sec = by_section(localized, unit_map)
    aligned: Dict[str, str] = {}
    skipped: Dict[str, str] = {}
    for sec, en_slots in en_sec.items():
        lo_slots = lo_sec.get(sec)
        if lo_slots is None:
            skipped[sec] = "section absent in the locale"
            continue
        if _shape(en_slots) != _shape(lo_slots):
            skipped[sec] = f"shape differs ({len(en_slots)} vs {len(lo_slots)} line(s))"
            continue
        for e, lo in zip(en_slots, lo_slots):
            aligned[e.key] = lo.text
    return aligned, skipped
