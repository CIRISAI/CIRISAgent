#!/usr/bin/env python3
"""Guard the *values* inside the localization bundles.

``check_localization_sync.py`` guards localization **key sets** — that every
referenced key resolves, and that mirrors and locales agree on which keys exist.
It cannot see anything about what the values contain, so a locale can pass it
with a value that breaks at runtime or is silently the wrong language.

This checks the values. Every failure mode below was observed in the tracked
corpus, not hypothesized (CIRISAgent#952):

  ERROR (exit 1 — functional breaks, user sees literal brace text or wrong language):
    1. Corrupt placeholder tokens. The *contents* of ``{...}`` were translated:
       ``{tool_name}`` -> ``{साधन_name}`` / ``{ကိရိယာ_name}`` /
       ``{เครื่องมือ_name}``,
       ``{network}`` -> ``{netकार्य}``, ``{address}`` -> ``{தீர்க்கவும்}``. Also
       malformed brace structure (``{{count}``). 79 instances across the corpus.
    2. Placeholder set parity against en.json. A dropped/added placeholder means
       a missing substitution or a KeyError at format time. 197 instances.
    7. Cross-script bleed — a value substantially in another language's script,
       e.g. pa.json carrying whole Bengali values.

  WARNING (exit 0 by default; exit 1 under --strict):
    3. Stray out-of-script codepoints (a few characters, not a whole value).
    4. Machine-translation salad — Latin glued to native script (``साधनs``,
       ``Transकृतीion``, ``ప్రారంభించుing``), and values left largely in English.
    5. Sibling-locale similarity — uk/ru at 41%, fa/ar at 46%. A locale that is
       largely byte-identical to its neighbour was probably never translated.
    6. Render-group stem distinctness. Labels that render adjacently must not
       share a word root: an approver whose eye lands on the wrong row of
       granted/spent/remaining/headroom misreads a deployment-wide envelope as
       this ticket's spendable balance.

Two design notes, both deliberate:

* **Script sets are derived, not declared.** manifest.json has no script field,
  and a hardcoded language->script table rots the moment a language is added.
  Each file's native scripts come from its own dominant block plus that block's
  writing-system group, which handles genuinely multi-script locales like ja
  (kana + kanji) without letting contamination whitelist itself: pa.json is
  17.9% Bengali, so any share-based floor generous enough to admit Japanese
  would also have admitted the Punjabi corruption.
* **Stopwords are derived, not declared.** Check 6 needs to tell content words
  from function words in 29 languages. Rather than hand-maintain stopword lists,
  a word is treated as a function word if it appears in more than
  ``--stopword-df`` of that locale's values.

U+0964/U+0965 (danda) are script-NEUTRAL — shared by Devanagari, Bengali and
Gurmukhi. Flagging them buries the real findings under ~1000 false positives per
file, which is how a lint gets disabled. Same for ZWJ/ZWNJ, which are structural
in Indic scripts.

A GREEN RUN OF CHECK 6 IS NOT A CLEARANCE. This is the check whose failure mode
is silence, and it has already been wrong in both directions:

* It UNDER-REPORTS by construction. A 5-character prefix stemmer missed four of
  six real collisions in one sweep — hi ``शेष`` is only 3 characters, bn/pa
  shared a whole word but not a prefix of the first word, and ta ``மீதம்`` vs
  ``மீதமுள்ள`` diverge after character 5. Longest-common-substring catches more
  but then over-reports on function words (German *bereits*, Hausa *wannan*,
  Tamil's ``ிக்க`` verbal suffix), so it needs the frequency filter above — and
  that filter is itself an approximation.
* It was SILENTLY DEAD for every non-Latin script until ``words()`` replaced
  ``\\w+``, and it passed a deliberately-collided Tamil file while dead.
* It CANNOT SEE SEMITIC ROOT MORPHOLOGY, and there is a concrete instance. In
  ``ar`` the approval card had ``الباقي`` (remaining) against ``المتبقي``
  (headroom): the SAME triliteral root ب-ق-ي, both meaning "remaining", both
  LINE-INITIAL — which in RTL is precisely where the eye lands. Shared 3-grams
  between them: **zero**. ``الباقي`` yields {الب, لبا, باق, اقي} and ``المتبقي``
  yields {الم, لمت, متب, تبق, بقي}, disjoint, because Arabic root consonants are
  not adjacent — *bāqī* carries an alif between ب and ق that *mutabaqqī* does
  not. Substring matching sees two unrelated words.

  What this check DID fire on was ``المت`` — remaining's *second* word against
  headroom's *first*, a milder and differently-positioned overlap. **It flagged a
  symptom two words away from a same-root collision it was structurally blind
  to.** Consequence: a green run on a Semitic or Ethiopic locale (ar, fa, ur, am,
  he) is WEAKER evidence than the same result on a concatenative language like
  de or id. Read those by eye regardless of the exit code.

  Related noise floor, for the same script: bare ``الم`` matches any ال+م noun
  and fires on essentially every pair on a money card, including ones nobody
  thinks collide. Treat it as unreportable — a flag that cries wolf trains people
  to dismiss the flag that matters.

So: this check is a net, not a proof. A human reading the labels of a render
group side by side outranks it, and any new render group should be read once by
someone who speaks the language before the green run is believed. The corpus this
tool was written for passed a key-count check for months.

Usage:
    python tools/dev/check_localization_integrity.py
    python tools/dev/check_localization_integrity.py --strict
    python tools/dev/check_localization_integrity.py --lang pa --lang mr
    python tools/dev/check_localization_integrity.py --allow-file l10n_allow.json

Exit codes:
    0 - no errors (and no warnings under --strict)
    1 - functional break (or any warning under --strict)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_localization_sync import PRIMARY_BUNDLE, manifest_languages  # noqa: E402

# Unicode blocks spanning the 29 supported languages. Used only to *name* the
# script a codepoint belongs to; membership is derived per file, never declared.
SCRIPT_BLOCKS: Tuple[Tuple[str, int, int], ...] = (
    ("Latin", 0x0041, 0x024F),
    ("Greek", 0x0370, 0x03FF),
    ("Cyrillic", 0x0400, 0x04FF),
    ("Hebrew", 0x0590, 0x05FF),
    ("Arabic", 0x0600, 0x06FF),
    ("Arabic-Supp", 0x0750, 0x077F),
    ("Devanagari", 0x0900, 0x097F),
    ("Bengali", 0x0980, 0x09FF),
    ("Gurmukhi", 0x0A00, 0x0A7F),
    ("Gujarati", 0x0A80, 0x0AFF),
    ("Oriya", 0x0B00, 0x0B7F),
    ("Tamil", 0x0B80, 0x0BFF),
    ("Telugu", 0x0C00, 0x0C7F),
    ("Kannada", 0x0C80, 0x0CFF),
    ("Malayalam", 0x0D00, 0x0D7F),
    ("Sinhala", 0x0D80, 0x0DFF),
    ("Thai", 0x0E00, 0x0E7F),
    ("Myanmar", 0x1000, 0x109F),
    ("Ethiopic", 0x1200, 0x137F),
    ("Hangul-Jamo", 0x1100, 0x11FF),
    ("Hiragana", 0x3040, 0x309F),
    ("Katakana", 0x30A0, 0x30FF),
    ("CJK", 0x4E00, 0x9FFF),
    ("Hangul", 0xAC00, 0xD7AF),
    ("Arabic-Pres", 0xFB50, 0xFDFF),
)

# Script-NEUTRAL codepoints: shared across scripts or structural within them.
# Counting these as "foreign" is what makes this class of lint unusable.
NEUTRAL_CODEPOINTS: Set[int] = {
    0x0964,  # DEVANAGARI DANDA        - shared by Devanagari, Bengali, Gurmukhi
    0x0965,  # DEVANAGARI DOUBLE DANDA - likewise
    0x200B,  # ZERO WIDTH SPACE
    0x200C,  # ZERO WIDTH NON-JOINER   - structural in Indic/Arabic
    0x200D,  # ZERO WIDTH JOINER       - structural in Indic
    0x200E,  # LEFT-TO-RIGHT MARK
    0x200F,  # RIGHT-TO-LEFT MARK
    0x00A0,  # NO-BREAK SPACE
}

# Groups of keys that render adjacently and must be distinguishable at a glance.
# Extend as new stacked surfaces ship; the check is a no-op for keys not present.
RENDER_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (
        "budget approval card (money labels, stacked)",
        (
            # All five render on one card. ``amount`` is easy to forget because it
            # labels an input rather than a figure, but a translator who reuses
            # its noun for the balance headline reintroduces the collision one
            # label over — which is exactly how te shipped మొత్తం twice.
            "approval_budget_amount",
            "approval_budget_granted",
            "approval_budget_spent",
            "approval_budget_remaining",
            "approval_budget_headroom",
        ),
    ),
)

# Writing systems whose blocks legitimately co-occur inside one language. This is
# a property of scripts, not of the language list, so it does not need updating
# when a language is added — unlike a language->script table, which rots.
SCRIPT_GROUPS: Tuple[frozenset, ...] = (
    frozenset({"Hiragana", "Katakana", "CJK"}),  # Japanese
    frozenset({"Hangul", "Hangul-Jamo", "CJK"}),  # Korean
    frozenset({"Arabic", "Arabic-Supp", "Arabic-Pres"}),  # Arabic, Persian, Urdu
)

# Below this spaces-per-character rate a language does not delimit words at all
# (ja 0.017, zh 0.034, th 0.065, my 0.086 vs >=0.10 for every word-spaced locale),
# which makes "Latin welded to native script" a property of the writing system
# rather than a defect.
SCRIPTIO_CONTINUA_SPACES_PER_CHAR = 0.09

# A word must appear in at least this many values before frequency alone can
# demote it to a function word (see ``derived_stopwords``).
MIN_STOPWORD_DOCS = 3

_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_VALID_TOKEN = re.compile(r"[A-Za-z0-9_]+")
_LATIN_RUN = re.compile(r"[A-Za-z]+")

# Letters that are decisive evidence of a DIFFERENT language sharing the same
# script. check_script compares Unicode blocks, so it is structurally blind here:
# Ukrainian and Russian are both Cyrillic, so Russian text in uk.json produces
# zero foreign codepoints and zero findings. check_sibling_similarity does see
# the overlap, but only as a WARN and only in aggregate ("45% byte-identical"),
# which cannot say WHICH values are wrong and does not gate.
#
# Alphabet conformance can. These four letters do not exist in the Ukrainian
# alphabet and these four do not exist in the Russian one, so a value carrying
# them is not a loanword, a borrowing, or a shared term — it is the other
# language. That makes this ERROR-level and per-key, unlike the ratio above.
#
# Deliberately narrow: only declared for pairs actually shipped and actually
# confusable. A wrong entry here would fail honest translations, so a pair goes
# in only when the exclusivity is a fact about the alphabets.
FOREIGN_ALPHABET: Dict[str, Tuple[str, str]] = {
    # lang: (letters exclusive to the confusable sibling, sibling name)
    "uk": ("ыэъё", "Russian"),
    "ru": ("іїєґ", "Ukrainian"),
}

LEVEL_ERROR = "ERROR"
LEVEL_WARN = "WARN"


@dataclass(frozen=True)
class Finding:
    """One integrity problem in one locale value."""

    level: str
    lang: str
    check: str
    key: str
    detail: str


def flatten_values(obj: dict, prefix: str = "") -> Dict[str, str]:
    """Flatten a nested localization dict to dotted key -> string value.

    Mirrors ``check_localization_sync.flatten`` but keeps the values, and skips
    the ``_meta`` bookkeeping subtree for the same reason it does.
    """
    out: Dict[str, str] = {}
    for k, v in obj.items():
        if prefix == "" and k == "_meta":
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten_values(v, key))
        elif isinstance(v, str):
            out[key] = v
    return out


def words(text: str) -> List[str]:
    """Split into words, keeping letters AND combining marks together.

    ``re``'s ``\\w`` excludes combining marks (they are not alphanumeric), so
    ``\\w+`` shreds every abugida word at its vowel signs: Tamil "செலவு" comes
    back as three one-character fragments, which the length filter then drops.
    That silently disabled the render-group check for every non-Latin script.
    """
    out: List[str] = []
    cur: List[str] = []
    for ch in text:
        if unicodedata.category(ch)[0] in "LM":
            cur.append(ch)
        elif cur:
            out.append("".join(cur))
            cur = []
    if cur:
        out.append("".join(cur))
    return out


def script_of(cp: int) -> str:
    """Name the script block a codepoint falls in ('' if neutral/uncategorized).

    Only letters (L*) and combining marks (M*) carry a script. Digits,
    punctuation and symbols are script-neutral in every language — and getting
    this wrong is subtle: a naive range test puts ``_`` (U+005F) inside the
    Latin block, which makes ``k_eff`` look like a Latin run welded to Latin and
    reports every formula in the corpus as machine-translation salad.
    """
    if cp in NEUTRAL_CODEPOINTS:
        return ""
    if unicodedata.category(chr(cp))[0] not in "LM":
        return ""
    for name, lo, hi in SCRIPT_BLOCKS:
        if lo <= cp <= hi:
            return name
    return ""


def script_histogram(values: Sequence[str]) -> Counter:
    """Count script-bearing characters by block across a locale's values."""
    hist: Counter = Counter()
    for v in values:
        for ch in v:
            name = script_of(ord(ch))
            if name:
                hist[name] += 1
    return hist


def native_scripts(hist: Counter) -> Set[str]:
    """The scripts a file may legitimately contain, from its dominant block.

    A share-based floor cannot do this job. pa.json is 17.9% Bengali — real
    contamination — while ja.json is legitimately Hiragana 31% / Katakana 29% /
    CJK 26%. Any threshold that accepts Japanese also accepts the Punjabi
    corruption. What actually separates them is which scripts co-occur *by
    design*, so nativity is derived from the dominant block plus its writing-
    system group. Latin is always permitted here; ``check_latin`` owns it.
    """
    dom = dominant_script(hist)
    if not dom:
        return set()
    native = {dom, "Latin"}
    for group in SCRIPT_GROUPS:
        if dom in group:
            native |= set(group)
    return native


def dominant_script(hist: Counter) -> str:
    """The single most common script block ('' if the file has no script chars).

    Deliberately NOT ``native_scripts``: a badly machine-translated non-Latin
    locale can carry so much leftover English that Latin clears the native floor
    (mr.json is 31.6% Latin), which would let the damage switch off the very
    check that finds it. Dominance cannot be gamed that way.
    """
    return hist.most_common(1)[0][0] if hist else ""


def check_placeholders(lang: str, loc: Dict[str, str], en: Dict[str, str], allow: Set[str]) -> List[Finding]:
    """ERROR 1 + 2: corrupt tokens, malformed braces, and set parity vs en."""
    out: List[Finding] = []
    for key, value in loc.items():
        if key in allow:
            continue
        # 1. Corrupt token contents — the placeholder name itself was translated.
        for token in _PLACEHOLDER.findall(value):
            if not _VALID_TOKEN.fullmatch(token):
                bad = "".join(ch for ch in token if not _VALID_TOKEN.fullmatch(ch))
                out.append(
                    Finding(
                        LEVEL_ERROR,
                        lang,
                        "placeholder-corrupt",
                        key,
                        f"{{{token}}} contains non-identifier characters ({bad!r}) — renders literally",
                    )
                )
        # 1b. Doubled braces the English source does not have, e.g. "{{count}}".
        # These are balanced, and the inner "{count}" satisfies a naive parity
        # check, so nothing else here catches them — but most formatters treat
        # "{{" as an escaped literal, so the user is shown the text "{count}".
        en_value = en.get(key, "")
        if ("{{" in value or "}}" in value) and not ("{{" in en_value or "}}" in en_value):
            out.append(
                Finding(
                    LEVEL_ERROR,
                    lang,
                    "placeholder-doubled",
                    key,
                    f"doubled braces not present in en — renders the placeholder literally: {value[:60]!r}",
                )
            )
        # 1c. Malformed brace structure, e.g. "{{count}".
        if value.count("{") != value.count("}"):
            out.append(
                Finding(
                    LEVEL_ERROR,
                    lang,
                    "placeholder-unbalanced",
                    key,
                    f"unbalanced braces ({value.count('{')} open, {value.count('}')} close)",
                )
            )
        # 2. Set parity against the English source.
        if key in en:
            want = {t for t in _PLACEHOLDER.findall(en[key]) if _VALID_TOKEN.fullmatch(t)}
            got = {t for t in _PLACEHOLDER.findall(value) if _VALID_TOKEN.fullmatch(t)}
            if want != got:
                missing = ", ".join(sorted(want - got)) or "-"
                extra = ", ".join(sorted(got - want)) or "-"
                out.append(
                    Finding(
                        LEVEL_ERROR,
                        lang,
                        "placeholder-parity",
                        key,
                        f"missing={{{missing}}} extra={{{extra}}} (en has {sorted(want)})",
                    )
                )
    return out


def check_script(lang: str, loc: Dict[str, str], en: Dict[str, str], native: Set[str]) -> List[Finding]:
    """ERROR 7 / WARN 3: cross-script bleed, and stray out-of-script codepoints."""
    out: List[Finding] = []
    if not native:
        return out
    for key, value in loc.items():
        # Characters the English source itself uses (Greek in the k_eff formula,
        # brand names) are intentional, not bleed.
        intentional = set(en.get(key, ""))
        foreign = Counter()
        run = best_run = 0
        for ch in value:
            name = script_of(ord(ch))
            if name and name not in native and ch not in intentional:
                foreign[name] += 1
                run += 1
                best_run = max(best_run, run)
            else:
                run = 0
        if not foreign:
            continue
        scripted = sum(1 for ch in value if script_of(ord(ch)))
        ratio = sum(foreign.values()) / scripted if scripted else 0.0
        blocks = ", ".join(f"{n}×{c}" for n, c in foreign.most_common(3))
        if ratio >= 0.30 or best_run >= 4:
            out.append(
                Finding(
                    LEVEL_ERROR,
                    lang,
                    "script-bleed",
                    key,
                    f"{ratio:.0%} of the value is foreign script [{blocks}] — wrong language, not a loanword",
                )
            )
        else:
            out.append(Finding(LEVEL_WARN, lang, "script-stray", key, f"stray foreign codepoints [{blocks}]"))
    return out


def check_latin(
    lang: str, loc: Dict[str, str], en: Dict[str, str], en_common: Set[str], native: Set[str], dominant: str
) -> List[Finding]:
    """WARN 4: MT salad (Latin glued to native script) and largely-English values."""
    out: List[Finding] = []
    if dominant == "Latin":
        return out  # Latin-script locale; this check does not apply.
    joined = "".join(loc.values())
    scriptio_continua = joined.count(" ") / max(len(joined), 1) < SCRIPTIO_CONTINUA_SPACES_PER_CHAR
    for key, value in loc.items():
        stripped = _PLACEHOLDER.sub("", value)
        # Whole Latin words of the English source are legitimate here: agglutinative
        # languages attach case suffixes directly to loanwords and acronyms (Tamil
        # "AIக்கு" = AI + dative). Salad leaves word FRAGMENTS ("यशfully", "सेवाs"),
        # which never match an English word boundary.
        en_words = set(_LATIN_RUN.findall(en.get(key, "")))
        # 4a. A Latin run welded to native script with no separator. A genuine
        # untranslated brand ("URL", "CIRIS") sits between spaces; MT salad does not.
        # Meaningless where the language does not space its words at all — in
        # Japanese every Latin run is "welded" by definition — so 4a is skipped
        # there and 4b, which does not depend on spacing, carries those locales.
        for m in [] if scriptio_continua else _LATIN_RUN.finditer(stripped):
            if m.group(0) in en_words:
                continue
            before = stripped[m.start() - 1] if m.start() else ""
            after = stripped[m.end()] if m.end() < len(stripped) else ""
            glued = [c for c in (before, after) if c and script_of(ord(c)) in native]
            if glued:
                ctx = stripped[max(0, m.start() - 14) : m.end() + 14].strip()
                out.append(
                    Finding(
                        LEVEL_WARN,
                        lang,
                        "mt-salad",
                        key,
                        f"Latin run {m.group(0)!r} welded to native script: …{ctx}…",
                    )
                )
                break
        # 4b. Value left largely in English. Measured by how much of the English
        # CONTENT vocabulary survives verbatim, not by Latin character ratio: a
        # correct translation carrying a brand name ("CIRIS AI ਸੇਵਾਵਾਂ ਕਿਰਿਆਸ਼ੀਲ")
        # is ~47% Latin letters and must not be flagged.
        content = {w.lower() for w in _LATIN_RUN.findall(en.get(key, ""))} - en_common
        if len(content) >= 3:
            got = {w.lower() for w in _LATIN_RUN.findall(stripped)}
            overlap = len(content & got) / len(content)
            if overlap >= 0.50:
                same = " (identical to en)" if value.strip() == en.get(key, "").strip() else ""
                out.append(
                    Finding(
                        LEVEL_WARN,
                        lang,
                        "untranslated",
                        key,
                        f"{overlap:.0%} of English content words survive verbatim{same}",
                    )
                )
    return out


def english_common_words(en: Dict[str, str], df: float) -> Set[str]:
    """English words common enough to be brands or boilerplate (CIRIS, AI, the).

    Derived from the corpus rather than declared, for the same reason the
    stopwords are: no hand-maintained list to drift.
    """
    n = len(en) or 1
    doc_freq: Counter = Counter()
    for value in en.values():
        for w in set(_LATIN_RUN.findall(value.lower())):
            doc_freq[w] += 1
    return {w for w, c in doc_freq.items() if c / n > df}


def check_alphabet(lang: str, loc: Dict[str, str], en: Dict[str, str]) -> List[Finding]:
    """ERROR 8: letters from a confusable same-script sibling language.

    The complement of check_script. That one asks "is this the right writing
    system"; this asks "is it the right LANGUAGE within that writing system" —
    the question 45%-of-uk.json-is-Russian (CIRISAgent#949) turns on, and the
    one a Unicode-block comparison can never answer.
    """
    out: List[Finding] = []
    profile = FOREIGN_ALPHABET.get(lang)
    if not profile:
        return out
    letters, sibling = profile
    forbidden = set(letters)
    for key, value in loc.items():
        # A letter the English source itself carries is quoted material, not
        # evidence — same carve-out check_script makes for brand names.
        hits = sorted(forbidden & set(value.lower()) - set(en.get(key, "").lower()))
        if hits:
            out.append(
                Finding(
                    LEVEL_ERROR,
                    lang,
                    "foreign-alphabet",
                    key,
                    f"contains {sibling}-only letters {''.join(hits)!r} — this value is {sibling}, not {lang}",
                )
            )
    return out


def check_sibling_similarity(files: Dict[str, Dict[str, str]], threshold: float) -> List[Finding]:
    """WARN 5: locales that are largely byte-identical to another locale."""
    out: List[Finding] = []
    langs = sorted(files)
    for i, a in enumerate(langs):
        for b in langs[i + 1 :]:
            shared = set(files[a]) & set(files[b])
            if len(shared) < 50:
                continue
            same = sum(1 for k in shared if files[a][k].strip() == files[b][k].strip())
            ratio = same / len(shared)
            if ratio >= threshold:
                out.append(
                    Finding(
                        LEVEL_WARN,
                        f"{a}/{b}",
                        "sibling-similarity",
                        "-",
                        f"{ratio:.0%} of {len(shared)} shared values are byte-identical ({same} values)",
                    )
                )
    return out


def derived_stopwords(loc: Dict[str, str], df: float) -> Set[str]:
    """Words appearing in more than ``df`` of a locale's values (function words)."""
    n = len(loc) or 1
    doc_freq: Counter = Counter()
    for value in loc.values():
        for w in set(words(value.lower())):
            doc_freq[w] += 1
    # Absolute floor as well as the rate: on a small bundle ``df * n`` drops
    # below 1, which would classify every word as a function word and silently
    # disable this check.
    cutoff = max(df * n, MIN_STOPWORD_DOCS)
    return {w for w, c in doc_freq.items() if c > cutoff}


def check_render_groups(lang: str, loc: Dict[str, str], stops: Set[str]) -> List[Finding]:
    """WARN 6: adjacent labels must not share a content-word root."""
    out: List[Finding] = []
    for label, keys in RENDER_GROUPS:
        present = [k for k in keys if k in loc]
        if len(present) < 2:
            continue
        roots: Dict[str, List[str]] = {}
        for k in present:
            tokens = [w for w in words(loc[k].lower()) if w not in stops and len(w) >= 3]
            roots[k] = tokens
        for i, ka in enumerate(present):
            for kb in present[i + 1 :]:
                shared = {a[:4] for a in roots[ka] for b in roots[kb] if a[:4] == b[:4]}
                if shared:
                    out.append(
                        Finding(
                            LEVEL_WARN,
                            lang,
                            "render-group-collision",
                            f"{ka} ~ {kb}",
                            f"share root {sorted(shared)} in {label}: " f"{loc[ka]!r} vs {loc[kb]!r}",
                        )
                    )
    return out


def load_allow(path: Path | None) -> Dict[str, Set[str]]:
    """Load deliberate per-language placeholder exemptions: {"lang": ["key", ...]}."""
    if path is None:
        return {}
    raw = json.load(open(path, encoding="utf-8"))
    return {lang: set(keys) for lang, keys in raw.items()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Localization value-integrity guard")
    ap.add_argument("--strict", action="store_true", help="treat warnings as failures too")
    ap.add_argument("--bundle", default=PRIMARY_BUNDLE, help=f"bundle to check (default: {PRIMARY_BUNDLE})")
    ap.add_argument("--lang", action="append", default=[], help="limit to these languages (repeatable)")
    ap.add_argument("--allow-file", type=Path, help="JSON of deliberate placeholder exemptions")
    ap.add_argument("--stopword-df", type=float, default=0.005, help="doc-frequency above which a word is a stopword")
    ap.add_argument("--similarity", type=float, default=0.25, help="sibling-similarity warning threshold")
    ap.add_argument("--max-per-check", type=int, default=6, help="examples printed per locale per check")
    ap.add_argument(
        "--fail-on",
        action="append",
        default=[],
        metavar="CHECK",
        help=(
            "fail ONLY on these check names (repeatable), ignoring every other finding. "
            "This is the ratchet: a class repaired to zero goes in the CI invocation so it "
            "cannot come back, while the classes still carrying debt stay reportable without "
            "blocking. Bare --strict on this corpus would fail on 1116 pre-existing errors and "
            "teach everyone to skip the step."
        ),
    )
    args = ap.parse_args()

    bundle = REPO_ROOT / args.bundle
    en_file = bundle / "en.json"
    if not en_file.exists():
        print(f"[FAIL] ERROR: bundle en.json not found at {args.bundle}")
        return 1

    langs = manifest_languages(bundle)
    if args.lang:
        langs = [x for x in langs if x in set(args.lang)]
    en = flatten_values(json.load(open(en_file, encoding="utf-8")))
    allow = load_allow(args.allow_file)
    en_common = english_common_words(en, args.stopword_df)

    print(" Localization value integrity")
    print(f"   bundle: {args.bundle}  ({len(en)} keys, {len(langs)} languages)")
    print()

    files: Dict[str, Dict[str, str]] = {}
    findings: List[Finding] = []
    for lang in langs:
        path = bundle / f"{lang}.json"
        if not path.exists():
            continue
        loc = flatten_values(json.load(open(path, encoding="utf-8")))
        files[lang] = loc
        if lang == "en":
            continue
        hist = script_histogram(list(loc.values()))
        native = native_scripts(hist)
        findings += check_placeholders(lang, loc, en, allow.get(lang, set()))
        findings += check_script(lang, loc, en, native)
        findings += check_alphabet(lang, loc, en)
        findings += check_latin(lang, loc, en, en_common, native, dominant_script(hist))
        findings += check_render_groups(lang, loc, derived_stopwords(loc, args.stopword_df))
    findings += check_sibling_similarity(files, args.similarity)

    errors = [f for f in findings if f.level == LEVEL_ERROR]
    warnings = [f for f in findings if f.level == LEVEL_WARN]

    for level, group, icon in ((LEVEL_ERROR, errors, "❌"), (LEVEL_WARN, warnings, "⚠️ ")):
        if not group:
            continue
        header = "ERRORS (functional breaks — block)" if level == LEVEL_ERROR else "WARNINGS (quality — informational)"
        if level == LEVEL_WARN and args.strict:
            header = "WARNINGS (--strict: block)"
        print(f"{icon} {header}:")
        by_lang: Dict[str, List[Finding]] = {}
        for f in group:
            by_lang.setdefault(f.lang, []).append(f)
        for lang in sorted(by_lang):
            checks: Dict[str, List[Finding]] = {}
            for f in by_lang[lang]:
                checks.setdefault(f.check, []).append(f)
            summary = ", ".join(f"{c}×{len(v)}" for c, v in sorted(checks.items()))
            print(f"  {lang}: {summary}")
            for check, items in sorted(checks.items()):
                for f in items[: args.max_per_check]:
                    print(f"      [{check}] {f.key}: {f.detail}")
                if len(items) > args.max_per_check:
                    print(f"      [{check}] … and {len(items) - args.max_per_check} more")
        print()

    if not errors:
        print("[OK] no functional breaks (placeholders intact, no cross-script bleed)")
        print()

    print(f"   {len(errors)} error(s), {len(warnings)} warning(s) across {len(files)} locale file(s)")

    if args.fail_on:
        gated = [f for f in findings if f.check in set(args.fail_on)]
        names = ", ".join(sorted(set(args.fail_on)))
        if gated:
            print(f"[FAIL] ratcheted check(s) regressed: {len(gated)} finding(s) in [{names}]")
            for f in gated[: args.max_per_check]:
                print(f"      [{f.check}] {f.lang} {f.key}: {f.detail}")
            return 1
        print(f"[OK] ratcheted check(s) still clean: [{names}]")
        print("   (other findings above are pre-existing debt and do not gate)")
        return 0

    if errors or (args.strict and warnings):
        print("[FAIL] localization integrity check failed")
        return 1
    print("[OK] localization integrity check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
