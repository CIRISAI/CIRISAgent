#!/usr/bin/env python3
"""The CIRIS glossaries: canonical terminology, per language, as pipeline input.

29 files at ``localization/glossaries/{code}_glossary.md`` — 28 languages plus
``TEMPLATE``. Each is a set of markdown tables whose first column is English
and whose second is the target language, followed (in 24 of them) by a
``## Cultural Considerations`` block of prose that is worth more than the
tables: it is where "address users with the formal እርስዎ, not አንተ/አንቺ" lives,
and that is the kind of thing a translator gets wrong once and a glossary
prevents forever.

WHY THIS IS A MODULE AND NOT A PROMPT STRING. Glossary-first is the one
practice CIRISAgent's LESSONS_LEARNED.md credits unreservedly: terminology is
frozen BEFORE translation so ACCORD, the guide, the UI strings and the DMA
prompts cannot disagree about what "Wise Authority" is. Injecting the glossary
into every request is how a pipeline keeps that promise without a human in the
loop, and injecting only the RELEVANT terms is how it keeps doing so without
spending the context window on 3,045 pairs.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Tuple

GLOSSARY_DIR = Path(__file__).resolve().parent / "glossaries"

# Prose sections worth carrying into a request, in the order they are shown.
# `Cultural Considerations` owns its `###` children (Formality Level,
# Honorifics, Script Considerations…) — the parser must not treat those as
# section boundaries, or the block silently reads as empty. It did, once.
PROSE_SECTIONS: Tuple[str, ...] = (
    "Cultural Considerations",
    "Notes for Translators",
    "Formality Level",
    "Script Considerations",
    "Honorifics",
)

_H2 = re.compile(r"^##(?!#)\s+(.*)$")

#: A term whose target cell opens with this is RETIRING. Its recorded rendering
#: stays visible as history and stops being authoritative — see [deprecated].
DEPRECATED_MARK = "[DEPRECATED]"
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")


@lru_cache(maxsize=64)
def _parse(code: str) -> Tuple[Tuple[Tuple[str, str], ...], Tuple[Tuple[str, str], ...]]:
    """(term pairs, prose sections) for one language. Cached: 29 files, many calls."""
    path = GLOSSARY_DIR / f"{code}_glossary.md"
    if not path.is_file():
        return (), ()
    terms: Dict[str, str] = {}
    prose: Dict[str, List[str]] = {}
    section = None
    lines = path.read_text(encoding="utf-8").splitlines()
    # The first row of EVERY table is its header, whatever it says. Only rows
    # whose first cell was literally "English" used to be skipped, so the
    # Version History table's "| Version | Date | Changes |" became the
    # canonical term "Version -> Date" in 24 languages and the judge enforced
    # it ("must be followed even if it appears odd").
    header_rows = {
        i for i, line in enumerate(lines[:-1])
        if line.startswith("|") and lines[i + 1].startswith("|")
        and all(set(c.strip()) <= set("-: ") for c in lines[i + 1].strip().strip("|").split("|"))
    }
    for i, line in enumerate(lines):
        head = _H2.match(line)
        if head:
            section = head.group(1).strip()
            prose.setdefault(section, [])
            continue
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 2 or not cells[0] or not cells[1]:
                continue
            if set(cells[0]) <= set("-: ") or set(cells[1]) <= set("-: "):
                continue  # the table's rule row
            if cells[0].lower() == "english" or i in header_rows:
                continue  # its header
            # setdefault, not assignment: the first table to define a term wins,
            # and the tables are ordered most-canonical-first (Core Action Verbs,
            # Core Concepts, then the feature-specific ones bolted on later).
            terms.setdefault(cells[0], cells[1])
        elif section is not None:
            prose[section].append(line)
    kept = tuple(
        (name, "\n".join(prose[name]).strip())
        for name in PROSE_SECTIONS
        if prose.get(name) and "\n".join(prose[name]).strip()
    )
    return tuple(terms.items()), kept


def _is_deprecated(rendering: str) -> bool:
    return rendering.strip().startswith(DEPRECATED_MARK)


def deprecated(code: str) -> Dict[str, str]:
    """English -> the retiring rendering, for terms marked [DEPRECATED].

    Kept separate from [terms] rather than deleted, because a deprecated entry
    still has work to do: it is what stops a model coining a NEW rendering for a
    term the product is retiring. What it must not do is out-argue the corpus.
    """
    return {e: t for e, t in _parse(code)[0] if _is_deprecated(t)}


def terms(code: str) -> Dict[str, str]:
    """English -> target, for every LIVE canonical term this language pins.

    Deprecated entries are excluded on purpose. ACCORD is the worked example:
    one glossary row covered both a document (a proper name) and a role
    (`accord holder`, a common noun), so it produced a different answer per
    language forever — four strategies across 28 — and the reviewers cited the
    shipped corpus against it, correctly. A retiring term must not out-argue the
    strings users are already reading (CIRISClient#5).
    """
    return {e: t for e, t in _parse(code)[0] if not _is_deprecated(t)}


def guidance(code: str) -> List[Tuple[str, str]]:
    """(section title, prose) for the language-specific rules worth sending."""
    return list(_parse(code)[1])


def _mentions(english: str, texts: List[str]) -> bool:
    """Does `english` occur in `texts`? Whole-word for single words.

    Shared by [relevant] and the retiring-terms block so a term cannot be
    considered relevant by one and invisible to the other.
    """
    probe = english.strip().lower()
    if not probe:
        return False
    hay = " \n ".join(texts).lower()
    if _WORD.fullmatch(english.strip()):
        return re.search(rf"\b{re.escape(probe)}\b", hay) is not None
    return probe in hay


def relevant(code: str, texts: List[str], *, limit: int = 60) -> Dict[str, str]:
    """The glossary terms that actually occur in `texts`.

    Whole-word, case-insensitive, longest-first so "Wise Authority" is matched
    before "Authority". A request carrying 3,045 pairs is a request that has
    spent its attention budget before it reads the strings; a request carrying
    the eleven that appear is one the model can actually obey.
    """
    all_terms = terms(code)
    if not all_terms:
        return {}
    hits: List[Tuple[int, str]] = []
    for english in all_terms:
        if _mentions(english, texts):
            hits.append((len(english), english))
    hits.sort(key=lambda p: (-p[0], p[1]))
    return {e: all_terms[e] for _, e in hits[:limit]}


class GlossaryMissing(RuntimeError):
    """No usable glossary for a language the pipeline was asked to translate.

    Not a warning. Every request is documented as carrying the canonical
    terminology, and a language whose glossary is missing, misnamed, or parses
    to nothing would be drafted WITHOUT it while the structural guard — which
    has no opinion about word choice — reported green. That is the shape
    AGENTS.md forbids: a parser that finds nothing where the construct plainly
    exists must fail loudly, not pass.
    """


def require(codes: List[str]) -> None:
    """Refuse before the first model call if any language has no glossary.

    Checked up front, for all of them, rather than per request: discovering it
    on language 19 of 28 means the first 18 were already drafted and paid for.
    """
    empty = sorted(c for c in codes if not terms(c))
    if empty:
        raise GlossaryMissing(
            "no canonical terminology for: " + ", ".join(empty) + ". Expected "
            + ", ".join(f"{GLOSSARY_DIR.name}/{c}_glossary.md" for c in empty)
            + " to exist and to contain at least one English|target table row. "
            "Every request is supposed to carry the glossary; drafting without "
            "one produces terminology drift that no structural check can see."
        )


def block(code: str, texts: List[str]) -> str:
    """The glossary payload for one request, or "" when nothing applies."""
    hits = relevant(code, texts)
    out: List[str] = []
    if hits:
        out.append(
            "CANONICAL TERMINOLOGY (from the CIRIS glossary for this language — "
            "these are decided, not suggestions; use them exactly).\n"
            "CASE IS NOT NORMATIVE HERE: the glossary tables write terms in the "
            "case that reads well IN A TABLE, so apply the target language's own "
            "sentence casing rather than copying the capitalisation shown. A "
            "reviewer once rejected a correct Yoruba rendering for not being in "
            "the ALL CAPS its glossary row happened to use.\n"
            "IF A SHIPPED ANCHOR BELOW USES A DIFFERENT RENDERING OF ONE OF THESE "
            "TERMS, SAY SO rather than silently picking one: the corpus and the "
            "glossary can disagree, and which of them is right is not yours to "
            "decide inside a single string."
        )
        out += [f"  {e}  ->  {t}" for e, t in hits.items()]
    retiring = {e: t for e, t in deprecated(code).items()
                if _mentions(e, texts)}
    if retiring:
        out.append(
            "\nRETIRING TERMINOLOGY — these appear in the source and the glossary "
            "NO LONGER PINS THEM:\n"
            + "\n".join(
                f"  {e}  (was: {t.replace(DEPRECATED_MARK, '').strip()})"
                for e, t in retiring.items()
            )
            + "\nRender them the way the ANCHOR TRANSLATIONS below already do, and "
            "do not coin a new rendering. The product is retiring these terms, so "
            "a fresh translation would entrench something on its way out — and "
            "the shipped strings are what users are reading today."
        )

    for title, text in guidance(code):
        out.append(f"\n{title.upper()} (this language's standing rules):\n{text}")
    return "\n".join(out)


def coverage() -> Dict[str, int]:
    """code -> term count. Used by the CLI's --glossary-report."""
    return {
        p.name.split("_")[0]: len(terms(p.name.split("_")[0]))
        for p in sorted(GLOSSARY_DIR.glob("*_glossary.md"))
    }


if __name__ == "__main__":  # a quick look at what the pipeline will send
    import sys

    code = sys.argv[1] if len(sys.argv) > 1 else "yo"
    probe = sys.argv[2:] or ["Defer to the Wise Authority", "Observe the node"]
    print(f"# {code}: {len(terms(code))} terms, {len(guidance(code))} prose section(s)")
    print(block(code, probe))
