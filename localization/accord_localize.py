#!/usr/bin/env python3
"""Translate the CIRIS Accord through the vendored CIRISClient pipeline.

AGENT-OWNED adapter (see ``localization/VENDORED.md``). The pipeline itself --
translate -> evaluate (MQM, different-family judge) -> repair, glossary,
translation memory, cacheable English prefix, placeholder contract -- is
``localization/localize.py``, vendored byte-identical. Every hook below is a
module attribute of the vendored module that its own functions look up at call
time; no vendored file is edited. This module:

1. SEGMENTS the English accord (``accord_<version>_en.txt``) into one key per
   non-blank line (``accord_segments.py``) and stages them as a key bundle the
   pipeline reads: ``localization/accord/<version>/{en,manifest,<lang>}.json``.
2. SEEDS each locale's bundle from what exists: the committed bundle, keeping a
   value only while the English it was translated from is unchanged (each value
   records that English's digest; a value whose digest matches a line that MOVED
   is carried to its new key), or -- on first contact -- the shipped
   ``accord_<version>_<lang>.txt`` aligned line by line within each section.
   A section whose shape does not align is left unseeded, never guessed.
3. Points TRANSLATION MEMORY at the previous accord (``--tm-version``, default
   1.2b), aligned the same way. A line that has a shipped translation of its
   previous wording sees it first. The vendored anchor caps (240 chars per
   anchor, 6,000 per request) are sized for UI labels; the accord's anchors use
   their own (``ACCORD_MAX_ANCHOR_CHARS``), so the 26 English lines over 240
   characters keep their memory.
4. Replaces the UI-string prompt wording with Accord wording (the guide's §3
   rules and the placeholder contract are carried over unchanged), and adds the
   accord guard's rules (formulas, CC references, markers, fences, headings,
   withdrawn claims, script, untranslated English) to the structural check.
5. GLOSSARY: every glossary marks ``ACCORD`` ``[DEPRECATED]``, so an Accord run
   would be told, for its own title, "retiring term, do not coin a rendering".
   For accord runs that row is dropped, and the name is pinned to how this
   language's shipped edition renders it (the translation memory) instead.
6. Runs the lanes ONE UNIT AT A TIME, because the pipeline sends a language's
   whole selection in one request and a whole accord does not fit in one reply.
   ``--units`` narrows a run to named units; selection within a unit stays
   diff-driven (only what is missing), unlike ``--keys``, which re-selects every
   matching key.
7. REASSEMBLES every complete locale into
   ``ciris_engine/data/localized/accord_<version>_<lang>.txt`` -- skeleton plus
   values, the format ``_load_localized_accord_file`` loads -- with a provenance
   line stating ``status: draft / review_status: machine_reviewed``. A partial
   locale is never written as a file: the only filler would be English.
8. EXTRA TRANSLATION MEMORY (``--extra-tm DIR``, repeatable): the translated
   strings of the CIRIS website (``src/i18n/{dictionaries,chrome}``), the
   CIRISClient apps and the agent's own UI bundle become extra TERMINOLOGY
   anchors, after the accord TM's and on their own bound (``EXTRA_*``), ranked
   website > client > agent UI. They are never values: only the accord TM seeds.
   Without the flag, every request is byte-identical to what it was before.

Never touched: the polyglot accords (``accord_*_POLYGLOT*.txt``) and
``ciris_engine/data/localized/polyglot/``. Those load universally and are not
translations (localization/CLAUDE.md). Nothing here writes a per-locale
``localized/<lang>/`` directory.

Usage (every localize.py flag passes through)::

    # 1.3 is the renamed corpus: constitution_ethics_1.3_<lang>.txt, with the
    # shipped accord_1.2b_<lang>.txt as translation memory (--stem / --tm-stem).
    E13='--version 1.3 --stem constitution_ethics --tm-version 1.2b --tm-stem accord'
    python3 localization/accord_localize.py $E13 --segments
    python3 localization/accord_localize.py $E13 --seed-exact-tm --units section0 --lane translate --dry-run
    python3 localization/accord_localize.py $E13 --extra-tm ~/ciris-website --extra-tm ~/CIRISClient \
        --extra-tm . --units section0 --lane translate --dry-run
    python3 localization/accord_localize.py --version 1.3 --segments
    python3 localization/accord_localize.py --version 1.3 --check
    python3 localization/accord_localize.py --version 1.3 --units section0 --lane translate --dry-run
    python3 localization/accord_localize.py --version 1.3 --units 'v1 v2' --lane translate --mode batch \
        --max-keys 2600
    python3 localization/accord_localize.py --version 1.3 --lane evaluate --keys 'accord.v9.*' --lang yo
    python3 localization/accord_localize.py --version 1.3 --verify

Nothing in this file calls a model. Every call is ``localize.py``'s.
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, FrozenSet, Iterable, List, NamedTuple, Optional, Sequence, Set, Tuple

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import accord_segments as seg  # noqa: E402
import lane_backoff  # noqa: E402

LOCALIZED = REPO_ROOT / "ciris_engine" / "data" / "localized"
STAGE_ROOT = HERE / "accord"
DEFAULT_TM_VERSION = "1.2b"

_VERSION = re.compile(r"^\d+\.\d+[a-z]?$")

#: Translation-memory budget per request. The vendored UI default (240 / 6000)
#: would leave every accord line over 240 characters with no memory at all.
ACCORD_ANCHOR_LIMIT = 80
ACCORD_MAX_ANCHOR_CHARS = 1600
ACCORD_MAX_ANCHOR_BLOCK_CHARS = 24000
#: A same-key anchor is used only if its English still resembles the new
#: English: keys are positional within a section, so a rewritten section can
#: put a different line under an old key.
SAME_KEY_MIN_SIMILARITY = 0.3

#: localize.py flags under which a run must not write anything.
READ_ONLY_FLAGS = ("--check", "--dry-run", "--glossary-report")

#: Glossary rows dropped for accord runs (see the module docstring, point 5).
ACCORD_GLOSSARY_DROP = ("ACCORD",)

#: The document families this adapter may read and write, by filename stem
#: (``<stem>_<version>_<lang>.txt``). A CLOSED list: the stem arrives from a
#: workflow input, and anything not named here could be a path.
#: ``constitution_ethics`` is the Accord's successor (1.3 onward); ``accord`` is
#: every shipped edition up to 1.2b, and the translation memory for 1.3.
STEMS: Dict[str, Tuple[str, str]] = {
    # stem: (prose name for prompts, short name for the provenance label)
    "accord": ("the CIRIS Accord", "Accord"),
    "constitution_ethics": (
        "the CIRIS Constitution's ethics text (the successor of the Accord)",
        "Constitution ethics text",
    ),
}
DEFAULT_STEM = "accord"

#: Written into every reassembled locale file, after the provenance preamble.
LABEL = (
    "// Machine translation of the English {name} {version} -- status: draft / "
    "review_status: machine_reviewed (vendored CIRISClient localize pipeline; MQM-reviewed "
    "by a model of a different family; not native-reviewed)."
)

_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9']+")
#: ``{key: (english, shipped translation)}`` -- one locale's translation memory.
TM = Dict[str, Tuple[str, str]]

_STOP = {"the", "a", "an", "and", "or", "to", "of", "is", "in", "for", "this", "that"}


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────


def check_version(version: str) -> str:
    if not _VERSION.match(version):
        raise SystemExit(f"[refuse] {version!r} is not an accord version like 1.3 or 1.2b")
    return version


def check_stem(stem: str) -> str:
    if stem not in STEMS:
        raise SystemExit(f"[refuse] {stem!r} is not a document stem this adapter knows: {sorted(STEMS)}")
    return stem


def accord_path(localized: Path, version: str, lang: str, stem: str = DEFAULT_STEM) -> Path:
    """The per-locale file the loader reads. Never a polyglot artifact."""
    if not re.fullmatch(r"[a-z]{2,3}", lang):
        raise SystemExit(f"[refuse] {lang!r} is not a locale code")
    path = localized / f"{check_stem(stem)}_{check_version(version)}_{lang}.txt"
    if "POLYGLOT" in path.name or path.parent != localized:
        raise SystemExit(f"[refuse] {path} is not a per-locale accord path")
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Bundles
# ─────────────────────────────────────────────────────────────────────────────


def nest(flat: Dict[str, str]) -> Dict[str, Any]:
    """Dotted keys -> nested objects, in the order given."""
    out: Dict[str, Any] = {}
    for key, value in flat.items():
        node = out
        parts = key.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return out


def flatten(obj: Dict[str, Any], prefix: str = "") -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in obj.items():
        if not prefix and k == "_meta":
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        elif isinstance(v, str):
            out[key] = v
    return out


def write_json(path: Path, doc: Dict[str, Any]) -> None:
    # Same serialisation as localize.insert, so a lane write is a minimal diff.
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def agent_languages(localized: Path) -> Dict[str, Dict[str, Any]]:
    langs: Dict[str, Dict[str, Any]] = read_json(localized / "manifest.json")["languages"]
    return langs


def locale_meta(localized: Path, lang: str) -> Dict[str, Any]:
    """``_meta`` for a staged bundle: identity from the agent's own bundle."""
    meta: Dict[str, Any] = {"language": lang, "language_name": lang, "direction": "ltr"}
    ui = localized / f"{lang}.json"
    if ui.is_file():
        src = read_json(ui).get("_meta", {})
        for name in ("language", "language_name", "direction"):
            if name in src:
                meta[name] = src[name]
    return meta


def label_locale(text: str, version: str, stem: str = DEFAULT_STEM) -> str:
    """Insert the provenance label after the leading ``//`` preamble block."""
    lines = text.split("\n")
    i = 0
    while i < len(lines) and lines[i].startswith("// ") and not lines[i].startswith(seg.MARKER):
        i += 1
    lines.insert(i, LABEL.format(name=STEMS[check_stem(stem)][1], version=version))
    return "\n".join(lines)


class Stage:
    """The staged key bundle for one accord version."""

    def __init__(
        self,
        version: str,
        *,
        stage_dir: Optional[Path] = None,
        localized: Path = LOCALIZED,
        stem: str = DEFAULT_STEM,
    ) -> None:
        self.version = check_version(version)
        self.stem = check_stem(stem)
        self.localized = localized
        self.dir = stage_dir or default_stage_dir(version, stem)
        #: Exact-English translation-memory matches to seed as values (opt-in).
        self.seed_tm: Dict[str, TM] = {}
        #: --extra-tm corpora (website, client, agent UI): ANCHORS ONLY. Nothing
        #: in Stage reads this to seed or write a value; install() hands it to
        #: anchors_for.
        self.extra_tm: Dict[str, List[ExtraAnchor]] = {}
        source = accord_path(localized, version, "en", stem)
        if not source.is_file():
            raise SystemExit(
                f"[refuse] no English source at {source}. The pipeline translates FROM "
                f"the English source; land it first (CIRISAgent#1252 / #1256 for constitution_ethics 1.3)."
            )
        self.source_text = source.read_text(encoding="utf-8")
        self.doc = seg.parse(self.source_text)
        if seg.reassemble(self.doc) != self.source_text:  # pragma: no cover - the parser's contract
            raise SystemExit("[refuse] the segmenter does not round-trip this source; refusing to stage it")
        self.en: Dict[str, str] = self.doc.segments()
        self.slots: Dict[str, seg.Slot] = {s.key: s for s in self.doc.slots}
        self.digests = {k: seg.source_digest(v) for k, v in self.en.items()}
        self.languages = [lang for lang in agent_languages(localized) if lang != "en"]

    def render(self, lang: str, values: Dict[str, str]) -> str:
        """The file a complete locale is written as."""
        return label_locale(seg.reassemble(self.doc, values), self.version, self.stem)

    # -- building ------------------------------------------------------------

    def build(self) -> Dict[str, Dict[str, int]]:
        """Write en.json, manifest.json and one bundle per locale. Returns stats."""
        self.dir.mkdir(parents=True, exist_ok=True)
        en_doc: Dict[str, Any] = {"_meta": {"language": "en", "language_name": "English", "direction": "ltr"}}
        en_doc.update(nest(self.en))
        write_json(self.dir / "en.json", en_doc)
        manifest = {
            "version": f"accord-{self.version}",
            "description": "Staged CIRIS Accord segments (generated by localization/accord_localize.py)",
            "languages": {code: {} for code in ["en", *self.languages]},
        }
        write_json(self.dir / "manifest.json", manifest)
        stats: Dict[str, Dict[str, int]] = {}
        for lang in self.languages:
            values, origin = self._seed(lang)
            meta = locale_meta(self.localized, lang)
            meta.update(
                {
                    "accord_version": self.version,
                    "status": "draft",
                    "review_status": "machine_reviewed",
                    "source_digests": {k: self.digests[k] for k in self.en if k in values},
                }
            )
            doc: Dict[str, Any] = {"_meta": meta}
            doc.update(nest({k: values[k] for k in self.en if k in values}))
            write_json(self.dir / f"{lang}.json", doc)
            stats[lang] = {"present": len(values), "total": len(self.en), **origin}
        return stats

    def _clean(self, lang: str, values: Dict[str, str]) -> Dict[str, str]:
        return {
            k: v
            for k, v in values.items()
            if k in self.slots and v.strip() and not seg.passage_problems(self.slots[k], v, lang)
        }

    def _seed(self, lang: str) -> Tuple[Dict[str, str], Dict[str, int]]:
        bundle = self.dir / f"{lang}.json"
        if bundle.is_file():
            doc = read_json(bundle)
            recorded: Dict[str, str] = doc.get("_meta", {}).get("source_digests", {})
            values = flatten(doc)
            kept = {k: v for k, v in values.items() if k in self.en and recorded.get(k) == self.digests[k]}
            # A line that MOVED (an insertion above it shifted its key) keeps its
            # translation: the digest of the English it came from is unchanged.
            by_digest: Dict[str, List[str]] = {}
            for k, v in values.items():
                if k in recorded and v.strip():
                    by_digest.setdefault(recorded[k], []).append(v)
            moved = 0
            for k in self.en:
                if k not in kept:
                    candidates = set(by_digest.get(self.digests[k], []))
                    if len(candidates) == 1:
                        kept[k] = candidates.pop()
                        moved += 1
            kept = self._clean(lang, kept)
            # Anything else was made from English that no longer exists in this
            # form: it is dropped, so the diff-driven lane retranslates it.
            dropped = sum(1 for k in values if k not in kept)
            return kept, {"stale_dropped": dropped, "moved": moved}
        shipped = accord_path(self.localized, self.version, lang, self.stem)
        if shipped.is_file():
            aligned, skipped = seg.align(self.doc, seg.parse(shipped.read_text(encoding="utf-8")))
            kept = self._clean(lang, aligned)
            return kept, {"sections_unaligned": len(skipped), "guard_rejected": len(aligned) - len(kept)}
        tm = self.seed_tm.get(lang)
        if tm:
            # OPT-IN (--seed-exact-tm): an English line that is byte-identical to
            # a line of the previous edition takes that edition's shipped
            # translation as its value -- the corpus users already read -- instead
            # of a fresh draft. Only unambiguous matches, and only lines the
            # accord guard accepts; everything else is left to the lanes.
            by_text: Dict[str, Set[str]] = {}
            for english, shipped_text in tm.values():
                by_text.setdefault(english, set()).add(shipped_text)
            exact = {k: next(iter(by_text[t])) for k, t in self.en.items() if len(by_text.get(t, ())) == 1}
            kept = self._clean(lang, exact)
            return kept, {"seeded_exact_from_tm": len(kept)}
        return {}, {}

    # -- after a run -----------------------------------------------------------

    def finalize(self, *, write_files: bool = True) -> Dict[str, str]:
        """Record digests for new values; reassemble complete locales."""
        result: Dict[str, str] = {}
        for lang in self.languages:
            bundle = self.dir / f"{lang}.json"
            if not bundle.is_file():
                continue
            doc = read_json(bundle)
            meta = doc.setdefault("_meta", {})
            digests: Dict[str, str] = meta.setdefault("source_digests", {})
            values = flatten(doc)
            for key in values:
                if key in self.en and key not in digests:
                    digests[key] = self.digests[key]  # written by this run, from this English
            meta["source_digests"] = {k: digests[k] for k in self.en if k in digests}
            write_json(bundle, doc)
            have = {k: v for k, v in values.items() if k in self.en and v.strip()}
            if len(have) < len(self.en):
                result[lang] = f"partial {len(have)}/{len(self.en)}"
                continue
            if write_files:
                target = accord_path(self.localized, self.version, lang, self.stem)
                target.write_text(self.render(lang, have), encoding="utf-8")
                result[lang] = f"complete -> {target.name}"
            else:
                result[lang] = "complete"
        return result

    def verify(self) -> List[str]:
        """Offline gate: everything that must hold for what a lane committed."""
        problems: List[str] = []
        if seg.reassemble(self.doc) != self.source_text:
            problems.append("English source does not round-trip through the segmenter")
        for lang in self.languages:
            bundle = self.dir / f"{lang}.json"
            if not bundle.is_file():
                continue
            values = flatten(read_json(bundle))
            for key, text in values.items():
                slot = self.slots.get(key)
                if slot is None:
                    problems.append(f"{lang}: {key} is not a segment of the English source")
                    continue
                for why in seg.passage_problems(slot, text, lang):
                    problems.append(f"{lang}: {key}: {why}")
            shipped = accord_path(self.localized, self.version, lang, self.stem)
            if all(values.get(k, "").strip() for k in self.en) and shipped.is_file():
                if shipped.read_text(encoding="utf-8") != self.render(lang, values):
                    problems.append(f"{lang}: {shipped.name} differs from its reassembled bundle")
        for lang in self.languages:
            mirror = self.localized / lang
            if mirror.is_dir() and any(mirror.glob("accord*")):
                problems.append(f"{lang}: per-locale accord mirror at {mirror} (polyglot artifacts load universally)")
        return problems


# ─────────────────────────────────────────────────────────────────────────────
# Translation memory: the previous accord, aligned
# ─────────────────────────────────────────────────────────────────────────────


def default_stage_dir(version: str, stem: str = DEFAULT_STEM) -> Path:
    """``localization/accord/<version>`` for the Accord (unchanged), else
    ``localization/accord/<stem>_<version>``."""
    check_version(version)
    return STAGE_ROOT / (version if check_stem(stem) == DEFAULT_STEM else f"{stem}_{version}")


def build_tm(localized: Path, tm_version: str, lang: str, tm_stem: str = DEFAULT_STEM) -> TM:
    """``{key: (english, shipped translation)}`` from the previous accord.

    Lines the accord guard would reject (left in English, wrong script, a
    dropped CC reference) are not memory: an anchor teaches by example.
    """
    en_path = accord_path(localized, tm_version, "en", tm_stem)
    lo_path = accord_path(localized, tm_version, lang, tm_stem)
    if not en_path.is_file() or not lo_path.is_file():
        return {}
    en_doc = seg.parse(en_path.read_text(encoding="utf-8"))
    aligned, _ = seg.align(en_doc, seg.parse(lo_path.read_text(encoding="utf-8")))
    slots = {s.key: s for s in en_doc.slots}
    return {
        k: (slots[k].text, v) for k, v in aligned.items() if v.strip() and not seg.passage_problems(slots[k], v, lang)
    }


def _tokens(text: str) -> Set[str]:
    return {w.lower() for w in _TOKEN.findall(text)} - _STOP


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0 if a.strip() == b.strip() else 0.0
    return len(ta & tb) / len(ta | tb)


def make_anchors(
    tms: Dict[str, TM], extra: Optional[Dict[str, List["ExtraAnchor"]]] = None
) -> Callable[..., List[Tuple[str, str, str]]]:
    """An ``anchors_for`` with localize.py's signature, over the accord TM.

    ``extra`` (``--extra-tm``) adds terminology anchors from the website and app
    corpora AFTER the accord TM's, on their own budget, so the accord TM's
    anchors are exactly what they are without it.
    """
    if not extra:
        return _accord_anchors(tms)
    accord = _accord_anchors(tms)

    def anchors_for(
        lang: str, needed: Sequence[str], en_flat: Dict[str, Any], *, limit: int = ACCORD_ANCHOR_LIMIT
    ) -> List[Tuple[str, str, str]]:
        return accord(lang, needed, en_flat, limit=limit) + extra_anchors(extra.get(lang, []), needed, en_flat)

    return anchors_for


def _accord_anchors(tms: Dict[str, TM]) -> Callable[..., List[Tuple[str, str, str]]]:
    def anchors_for(
        lang: str, needed: Sequence[str], en_flat: Dict[str, Any], *, limit: int = ACCORD_ANCHOR_LIMIT
    ) -> List[Tuple[str, str, str]]:
        tm = tms.get(lang, {})
        picked: List[Tuple[str, str, str]] = []
        seen: Set[str] = set()

        def take(key: str) -> None:
            if key in seen or key not in tm:
                return
            english, shipped = tm[key]
            if len(english) > ACCORD_MAX_ANCHOR_CHARS or len(shipped) > ACCORD_MAX_ANCHOR_CHARS:
                return
            picked.append((key, english, shipped))
            seen.add(key)

        # 0. The previous edition's translation of this EXACT English line,
        #    wherever it sat. 1.2b -> 1.3 inserts lines, which shifts keys within
        #    a section; the text, not the key, is what identifies the line.
        by_text: Dict[str, List[str]] = {}
        for tm_key, (english, _) in tm.items():
            by_text.setdefault(english, []).append(tm_key)
        for key in needed:
            for tm_key in by_text.get(str(en_flat.get(key, "")), [])[:1]:
                take(tm_key)
        # 1. The previous translation of THIS key, where it still is one.
        for key in needed:
            if key in tm and _similarity(tm[key][0], str(en_flat.get(key, ""))) >= SAME_KEY_MIN_SIMILARITY:
                take(key)
        # 2. How this edition renders the document's own name (see point 5).
        texts = " ".join(str(en_flat.get(k, "")) for k in needed)
        if re.search(r"\bAccord\b", texts, re.I) and not any(re.search(r"\bAccord\b", e, re.I) for _, e, _ in picked):
            for key in sorted(tm, key=lambda k: len(tm[k][0])):
                if re.search(r"\bAccord\b", tm[key][0], re.I):
                    take(key)
                    break
        # 3. Lines that share vocabulary with what is being translated.
        want: Set[str] = set()
        for key in needed:
            want |= _tokens(str(en_flat.get(key, "")))
        if want:
            scored = []
            for key, (english, _) in tm.items():
                toks = _tokens(english)
                hit = len(want & toks)
                if hit and key not in seen:
                    scored.append((hit / len(toks | want), hit, key))
            for _, _, key in sorted(scored, key=lambda s: (-s[0], -s[1], s[2])):
                if len(picked) >= limit:
                    break
                take(key)
        out: List[Tuple[str, str, str]] = []
        budget = ACCORD_MAX_ANCHOR_BLOCK_CHARS
        for key, english, shipped in picked[:limit]:
            cost = len(key) + len(english) + len(shipped) + 16
            if cost > budget:
                continue
            out.append((key, english, shipped))
            budget -= cost
        return out

    return anchors_for


# ─────────────────────────────────────────────────────────────────────────────
# Extra translation memory: the website and app corpora (--extra-tm), anchors only
# ─────────────────────────────────────────────────────────────────────────────
#
# Users read CIRIS in three more places than the Accord: the website, the apps,
# and the agent's own interface. Each has its own machine-translated, MQM-judged
# corpus. Anchors from them keep a shared term reading the same way everywhere.
#
# They are ANCHORS, never values: nothing here reaches Stage.seed_tm, a bundle
# or a written file. Only the accord TM seeds (--seed-exact-tm).


class ExtraAnchor(NamedTuple):
    """One (English, translation) pair from an extra corpus, as an anchor."""

    rank: int  # 1 website, 2 client, 3 agent UI (the accord TM is 0)
    key: str  # "<source>:<flat key>", so the prompt says where it came from
    english: str
    text: str
    tokens: FrozenSet[str]


#: ``(source name, rank, bundle dirs relative to the corpus root)``. A root is
#: recognised by these layouts, and anything else is refused. The client's
#: androidApp / iosApp / desktopApp bundles are byte-identical mirrors of the
#: shared one, so only the shared one is read.
EXTRA_LAYOUTS: Tuple[Tuple[str, int, Tuple[str, ...]], ...] = (
    ("website", 1, ("src/i18n/dictionaries", "src/i18n/chrome")),
    ("client", 2, ("client/shared/src/desktopMain/resources/localization",)),
    ("agent-ui", 3, ("ciris_engine/data/localized",)),
)

#: Bounds, per request (one request = one language x one unit). Per KEY of the
#: unit at most EXTRA_PER_KEY anchors, round-robin across keys; per request at
#: most EXTRA_ANCHOR_LIMIT anchors and EXTRA_MAX_BLOCK_CHARS characters. These
#: are UI strings: an anchor longer than EXTRA_MAX_ANCHOR_CHARS is a paragraph,
#: not a term.
EXTRA_PER_KEY = 2
EXTRA_ANCHOR_LIMIT = 24
EXTRA_MAX_BLOCK_CHARS = 3000
EXTRA_MAX_ANCHOR_CHARS = 120
#: An entry is a candidate for a line only when EVERY content word of it occurs
#: in the line (a term or phrase the line uses, not one that shares a word), it
#: has at most this many content words, and -- if it is a single word -- that
#: word is at least EXTRA_MIN_SINGLE_WORD letters and not a function word. UI
#: corpora are full of "Next", "Open", "Who": as anchors those are noise, and an
#: imperative button sense can mislead.
EXTRA_MAX_TERM_WORDS = 5
EXTRA_MIN_SINGLE_WORD = 6
_EXTRA_STOP = frozenset(
    """about above after again against all also am any are as at be because been before being below between
    both but by can cannot could did do does doing down during each either else even ever every few from
    further had has have having he her here hers him his how if into it its itself just least less let like
    may me might more most much must my neither never no nor not now of off on once one only other ought our
    ours out over own per rather same shall she should since so some still such than their theirs them then
    there these they those though through thus till too under until up upon us very via was we were what
    when where whether which while who whom whose why will with within without would yet you your yours
    another anything everything nothing something someone everyone nobody whatever whichever""".split()
)

#: File-level ``_meta.status`` / ``_meta.review_status`` values that exclude a
#: whole file. ``draft`` / ``needs_native_review`` / ``machine_reviewed`` are NOT
#: here: they are the lifecycle stamp of every machine-translated file in all
#: four corpora (the accord TM itself is ``draft / machine_reviewed``), each of
#: which went through the MQM judge. A file that says it never did is excluded.
EXTRA_REJECTED_STATUSES = frozenset(
    {"unreviewed", "untranslated", "stub", "placeholder", "wip", "pending", "rejected", "machine_unreviewed"}
)
#: Review findings this severe on a value that is still current exclude it.
EXTRA_REJECTED_SEVERITIES = frozenset({"critical", "major"})

_HTML = re.compile(r"<[A-Za-z/!]")
_PLACEHOLDERISH = re.compile(r"\{[^}]*\}|%\d*\$?[sdf@]|\$\{")
_ACCORD_NAME = re.compile(r"\bAccord\b", re.I)


def _flat_strings(obj: Any, prefix: str = "") -> Dict[str, str]:
    """Nested JSON -> flat dotted keys. Arrays, non-strings and ``_``-prefixed
    subtrees (``_meta``) are skipped."""
    out: Dict[str, str] = {}
    if not isinstance(obj, dict):
        return out
    for k, v in obj.items():
        if not isinstance(k, str) or k.startswith("_"):
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat_strings(v, key))
        elif isinstance(v, str):
            out[key] = v
    return out


def _file_status(doc: Dict[str, Any]) -> Optional[str]:
    meta = doc.get("_meta")
    if not isinstance(meta, dict):
        return None
    for field in ("status", "review_status"):
        value = meta.get(field)
        if isinstance(value, str) and value.strip().lower() in EXTRA_REJECTED_STATUSES:
            return f"{field}={value}"
    return None


def _flagged_keys(root: Path, lang: str) -> Set[str]:
    """Keys a corpus's own review flagged for ``lang``, where it records them.

    The website's pipeline writes ``localization/hard-cases/`` (git-ignored, so
    present only in a local checkout): ``hard-cases-*.json`` cases are strings
    the judge rejected or the ladder could not fix, and ``review-<lang>-*.json``
    holds MQM findings. A judge-rejected key, or a critical/major finding on a
    value that is still current, is not an exemplar.
    """
    hard = root / "localization" / "hard-cases"
    out: Set[str] = set()
    if not hard.is_dir():
        return out
    for path in sorted(hard.glob("hard-cases-*.json")):
        try:
            cases = read_json(path).get("cases", [])
        except (OSError, ValueError):
            continue
        for case in cases if isinstance(cases, list) else []:
            if isinstance(case, dict) and case.get("lang") == lang and isinstance(case.get("key"), str):
                out.add(case["key"])
    for path in sorted(hard.glob(f"review-{lang}-*.json")):
        try:
            findings = read_json(path).get("findings", {})
        except (OSError, ValueError):
            continue
        bundle = path.stem.split("-", 2)[-1]
        current: Dict[str, str] = {}
        for d in EXTRA_LAYOUTS[0][2]:
            if Path(d).name == bundle and (root / d / f"{lang}.json").is_file():
                current = _flat_strings(read_json(root / d / f"{lang}.json"))
        for key, finding in findings.items() if isinstance(findings, dict) else []:
            if not isinstance(finding, dict):
                continue
            severe = any(
                isinstance(e, dict) and e.get("severity") in EXTRA_REJECTED_SEVERITIES
                for e in finding.get("errors", [])
            )
            if severe and current.get(key) == finding.get(lang):
                out.add(key)
    return out


def _usable(english: str, text: str, lang: str) -> Optional[str]:
    """Why this pair is not an anchor, or None."""
    e, t = english.strip(), text.strip()
    if not e or not t:
        return "empty"
    if e == t:
        return "same_as_english"
    if len(e) > EXTRA_MAX_ANCHOR_CHARS or len(t) > EXTRA_MAX_ANCHOR_CHARS:
        return "too_long"
    if "\n" in e or "\n" in t or _HTML.search(e) or _HTML.search(t):
        return "markup"
    if _PLACEHOLDERISH.search(e) or _PLACEHOLDERISH.search(t):
        return "placeholder"
    if _ACCORD_NAME.search(e):
        # The document's own name is pinned to the accord TM's rendering.
        return "names_the_accord"
    if any(claim in e or claim in t for claim in seg.WITHDRAWN):
        return "withdrawn_claim"
    rng = seg.SCRIPT.get(lang)
    if rng and not re.search(f"[{rng}]", t):
        return "wrong_script"
    terms = _term_tokens(e)
    if not terms or len(terms) > EXTRA_MAX_TERM_WORDS:
        return "not_a_term"
    if len(terms) == 1 and len(next(iter(terms))) < EXTRA_MIN_SINGLE_WORD:
        return "not_a_term"
    return None


def _term_tokens(text: str) -> FrozenSet[str]:
    return frozenset(_tokens(text) - _EXTRA_STOP)


class ExtraCorpus(NamedTuple):
    name: str
    rank: int
    root: Path
    commit: str


def detect_extra(root: Path) -> List[ExtraCorpus]:
    """The corpora a ``--extra-tm`` root holds. Refuses a root that holds none."""
    root = root.resolve()
    found = []
    for name, rank, dirs in EXTRA_LAYOUTS:
        if any((root / d / "en.json").is_file() for d in dirs):
            found.append(ExtraCorpus(name, rank, root, _commit_of(root)))
    if not found:
        layouts = ", ".join(f"{n}: {' | '.join(d)}" for n, _, d in EXTRA_LAYOUTS)
        raise SystemExit(f"[refuse] --extra-tm {root}: no known corpus layout ({layouts})")
    return found


def _commit_of(root: Path) -> str:
    """The checkout's commit, for provenance; read-only. Only the root's OWN
    repository: a plain directory inside another checkout is "unknown", not
    its parent's HEAD."""
    if not (root / ".git").exists():
        return "unknown"
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() if out.returncode == 0 else "unknown"


def load_extra_tm(
    roots: Sequence[Path], langs: Sequence[str]
) -> Tuple[Dict[str, List[ExtraAnchor]], List[Tuple[ExtraCorpus, Dict[str, Dict[str, int]]]]]:
    """``{lang: [anchors]}`` from every root, plus per-corpus stats.

    De-duplicated by English across corpora: the same label in the website and
    the client is ONE anchor, from the higher-ranked corpus.
    """
    corpora = sorted((c for r in roots for c in detect_extra(Path(r))), key=lambda c: c.rank)
    seen_roots: Set[Tuple[str, Path]] = set()
    out: Dict[str, List[ExtraAnchor]] = {lang: [] for lang in langs}
    taken: Dict[str, Set[str]] = {lang: set() for lang in langs}
    report: List[Tuple[ExtraCorpus, Dict[str, Dict[str, int]]]] = []
    dirs_of = {name: dirs for name, _, dirs in EXTRA_LAYOUTS}
    for corpus in corpora:
        if (corpus.name, corpus.root) in seen_roots:
            continue
        seen_roots.add((corpus.name, corpus.root))
        stats: Dict[str, Dict[str, int]] = {}
        for lang in langs:
            s: Dict[str, int] = {}
            flagged = _flagged_keys(corpus.root, lang)
            for d in dirs_of[corpus.name]:
                en_path, lo_path = corpus.root / d / "en.json", corpus.root / d / f"{lang}.json"
                if not en_path.is_file() or not lo_path.is_file():
                    continue
                lo_doc = read_json(lo_path)
                why_file = _file_status(lo_doc)
                en_flat, lo_flat = _flat_strings(read_json(en_path)), _flat_strings(lo_doc)
                if why_file:
                    s["file_" + why_file.split("=")[0]] = s.get("file_" + why_file.split("=")[0], 0) + len(lo_flat)
                    continue
                for key in sorted(lo_flat):
                    english = en_flat.get(key)
                    if english is None:
                        why: Optional[str] = "no_english"
                    elif key in flagged:
                        why = "review_flagged"
                    else:
                        why = _usable(english, lo_flat[key], lang)
                    if why is None and english is not None:
                        norm = " ".join(english.split()).lower()
                        if norm in taken[lang]:
                            why = "duplicate"
                        else:
                            taken[lang].add(norm)
                            out[lang].append(
                                ExtraAnchor(
                                    corpus.rank,
                                    f"{corpus.name}:{key}",
                                    english.strip(),
                                    lo_flat[key].strip(),
                                    frozenset(_tokens(english)),
                                )
                            )
                    s[why or "kept"] = s.get(why or "kept", 0) + 1
            stats[lang] = s
        report.append((corpus, stats))
    return out, report


def extra_anchors(
    pool: Sequence[ExtraAnchor], needed: Sequence[str], en_flat: Dict[str, Any]
) -> List[Tuple[str, str, str]]:
    """Terminology anchors for one request, bounded (see EXTRA_* above).

    An entry is a candidate for a line when every content word of it occurs in
    that line: a term the line uses. Candidates rank by the summed rarity (idf
    over the pool) of their words -- multi-word and rarer terms first -- then
    corpus rank (website, client, agent UI), then brevity. Each key contributes
    at most EXTRA_PER_KEY, taken round-robin so every line gets its best term
    before any line gets its second; the result is emitted grouped by corpus
    rank.
    """
    if not pool:
        return []
    df: Dict[str, int] = {}
    index: Dict[str, List[int]] = {}
    for i, a in enumerate(pool):
        for t in a.tokens - _EXTRA_STOP:
            df[t] = df.get(t, 0) + 1
            index.setdefault(t, []).append(i)
    n = len(pool)

    def idf(t: str) -> float:
        return math.log((n + 1) / (df.get(t, 0) + 1)) + 1.0

    per_key: List[List[Tuple[float, int]]] = []
    for key in needed:
        # Containment is over ALL the entry's words, function words included,
        # so "No Memories" is not offered to a line about memories.
        line = frozenset(_tokens(str(en_flat.get(key, ""))))
        cands: Dict[int, float] = {}
        for t in line - _EXTRA_STOP:
            for i in index.get(t, []):
                if i not in cands and pool[i].tokens <= line:
                    cands[i] = sum(idf(x) for x in pool[i].tokens - _EXTRA_STOP)
        ranked = sorted(cands.items(), key=lambda c: (-c[1], pool[c[0]].rank, len(pool[c[0]].english), pool[c[0]].key))
        per_key.append([(score, i) for i, score in ranked])
    # A key's anchors are its top EXTRA_PER_KEY candidates (shared with another
    # key, they appear once); round-robin by depth, so every key's best comes
    # before any key's second.
    chosen: List[Tuple[float, int]] = []
    seen: Set[int] = set()
    for depth in range(EXTRA_PER_KEY):
        for cands_k in per_key:
            if depth < len(cands_k) and cands_k[depth][1] not in seen:
                chosen.append(cands_k[depth])
                seen.add(cands_k[depth][1])
    out: List[Tuple[float, int]] = []
    budget = EXTRA_MAX_BLOCK_CHARS
    for score, i in chosen[:EXTRA_ANCHOR_LIMIT]:
        a = pool[i]
        cost = len(a.key) + len(a.english) + len(a.text) + 16
        if cost > budget:
            continue
        out.append((score, i))
        budget -= cost
    out.sort(key=lambda c: (pool[c[1]].rank, -c[0], pool[c[1]].key))
    return [(pool[i].key, pool[i].english, pool[i].text) for _, i in out]


def print_extra_report(report: Sequence[Tuple[ExtraCorpus, Dict[str, Dict[str, int]]]]) -> None:
    """One line per corpus: provenance (commit) and what was kept or skipped."""
    for corpus, stats in report:
        kept = sum(s.get("kept", 0) for s in stats.values())
        skipped: Dict[str, int] = {}
        for s in stats.values():
            for why, count in s.items():
                if why != "kept":
                    skipped[why] = skipped.get(why, 0) + count
        why_text = ", ".join(f"{k}={v}" for k, v in sorted(skipped.items()))
        print(
            f"[extra-tm] {corpus.name} (rank {corpus.rank}) {corpus.root.name}@{corpus.commit}: "
            f"{kept} anchor(s) across {len(stats)} locale(s); skipped {why_text or 'none'}"
        )


_EXTRA_RULE = """
ANCHORS FROM THE WEBSITE AND APPS. Anchor keys that start with "website:",
"client:" or "agent-ui:" are NOT lines of this document. They are this
language's shipped strings from the CIRIS website, the CIRIS apps and the
agent's own interface: what its users already read. They are there for the
TERMS they share with these lines, so one concept reads the same way
everywhere, and for register. They do not override the CANONICAL TERMINOLOGY
block, nor the document's own name as the previous edition renders it, and a
UI label's brevity is not a model for this document's voice."""

_EXTRA_RULE_REVIEW = (
    _EXTRA_RULE + "\nA term rendered as those anchors render it is not a terminology finding on that ground alone."
)
# ─────────────────────────────────────────────────────────────────────────────

_ACCORD_RULES = """- These lines are the CIRIS Accord: a governance covenant the agent reads
  before it acts. Keep its voice -- philosophical, at times poetic, never a
  manual. Translate; do not summarise, expand, explain or add notes, and do not
  carry over any claim that is not in the English line.
- Each key is ONE LINE of the document, in order; neighbouring keys are the
  surrounding lines, for context. Return one line per key: no line breaks.
  Markup at the start of a line (heading marks, list markers) is not shown to
  you and is restored around your text -- do not add any.
- Keep inline markers where the source has them: `**bold**`, `*italic*`.
- These stay exactly as written, in Latin script: every "CC n.n.n" reference,
  RATCHET#17, M-1, PDMA, WBD, LensCore, J, k_eff, λ_op, σ, ρ̄, k, CIRIS, and any
  formula.
- The document's own name, "Accord", is rendered exactly as the ANCHOR
  TRANSLATIONS (this language's shipped previous edition) render it. Do not coin
  a new rendering, and a reviewer must not report the anchors' rendering."""


def accord_prompts(L: ModuleType, stem: str = DEFAULT_STEM) -> Dict[str, str]:
    rules: str = L.GUIDE_RULES
    placeholder: str = L._PLACEHOLDER_RULE
    translate = (
        "You translate lines of the CIRIS Accord, the covenant of the CIRIS ethical "
        "AI agent, into ONE target language. The agent ships in 29 languages; this "
        "edition is what it reads in the user's language.\n\n"
        "Rules, all of them hard:\n"
        "- Return ONLY a JSON object. No markdown fences, no commentary.\n"
        '- The object has two members: "translations" (key -> translated line) and\n'
        '  "refusals" (key -> one-sentence reason). Every requested key appears in\n'
        "  exactly one of them.\n"
        f"{placeholder}\n{_ACCORD_RULES}\n"
        "- The CANONICAL TERMINOLOGY block is decided, not advisory. Use those renderings\n"
        "  exactly, including diacritics and tone marks.\n"
        "- The ANCHOR TRANSLATIONS are this language's shipped edition of the PREVIOUS\n"
        "  Accord. Where a line is unchanged in meaning, stay close to its anchor; match\n"
        "  their register, formality and terminology throughout.\n"
        '- USE "refusals" ONLY IF YOU GENUINELY CANNOT PRODUCE A FAITHFUL TRANSLATION.\n'
        "  A refusal is routed to a stronger model rather than shipped. Never return\n"
        "  English text as a translation, never transliterate the English, and never\n"
        "  invent a plausible-looking line you do not stand behind.\n\n"
        "WHAT WENT WRONG BEFORE. Every one of these was a real finding on a real run of\n"
        "this pipeline, in some language:\n" + rules
    )
    review = (
        "You are an independent translation quality reviewer for the CIRIS Accord, the "
        "covenant of the CIRIS ethical AI agent. You did not write these translations.\n\n"
        "Annotate each one with MQM error spans. Categories: accuracy (mistranslation,\n"
        "omission, addition), fluency (grammar, spelling, unnatural phrasing, and\n"
        "NON-WORDS OR WORD-SALAD), terminology (disagrees with the canonical glossary\n"
        "supplied), style (register or voice wrong for a covenant), locale (script,\n"
        "numerals, punctuation, direction wrong for this language).\n"
        "Severities: critical (the reader is misled, or the line is unusable),\n"
        "major (clearly wrong but the intent survives), minor (a nit).\n\n"
        "Return ONLY a JSON object mapping each key to a list of error objects:\n"
        '  {"accord.v1.s01.l01": [{"category":"accuracy","severity":"major",\n'
        '      "span":"<the offending text>","note":"<what is wrong>",\n'
        '      "suggestion":"<what it should be>"}],\n'
        '   "accord.v1.s01.title": []}\n'
        "An empty list means no error found. Every key you were given must appear.\n\n"
        f"Judge hard and specifically:\n{placeholder}\n{_ACCORD_RULES}\n"
        "- A line that is fluent but says something the English does not is ACCURACY\n"
        "  critical, not style. An obligation softened or strengthened (must/should/may)\n"
        "  is accuracy critical: this text governs what the agent does.\n"
        "- A line containing invented or garbled words in the target language is\n"
        "  FLUENCY critical. This is the failure a structural check cannot see and the\n"
        "  one you are most needed for.\n"
        "- A term that disagrees with the CANONICAL TERMINOLOGY block is TERMINOLOGY.\n"
        "- Do NOT invent errors to look thorough. An empty list is the correct and\n"
        "  expected answer for a good translation. Agreement with the glossary is not a\n"
        "  finding, and neither is differing from a glossary row's table casing.\n\n"
        "LOOK FOR THESE SPECIFICALLY. Each is a defect this pipeline has actually shipped\n"
        "past a structural gate, in some language, on some run:\n" + rules
    )
    repair = (
        "You are correcting CIRIS Accord translations that a reviewer rejected. You will "
        "receive the English line, the current translation, and the reviewer's MQM "
        "findings for each key.\n\n"
        "Rules:\n"
        '- Return ONLY a JSON object with "translations" (key -> corrected line) and\n'
        '  "refusals" (key -> reason), exactly as the translation lane uses.\n'
        "- FIX WHAT WAS FOUND. Do not rewrite what was not flagged.\n"
        "- If you judge a finding to be WRONG, return the current translation unchanged\n"
        '  and say so in "refusals".\n'
        f"{placeholder}\n{_ACCORD_RULES}\n"
        "- The CANONICAL TERMINOLOGY block wins every terminology dispute.\n\n"
        "THE DEFECTS YOU ARE MOST LIKELY CORRECTING. Each has been a real finding here:\n" + rules
    )
    doc = STEMS[check_stem(stem)][0]
    out = {"SYSTEM_TRANSLATE": translate, "SYSTEM_REVIEW": review, "SYSTEM_REPAIR": repair}
    if doc != STEMS[DEFAULT_STEM][0]:
        out = {k: v.replace("the CIRIS Accord", doc).replace("CIRIS Accord translations", f"translations of {doc}")
               for k, v in out.items()}  # fmt: skip
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Wiring the vendored module
# ─────────────────────────────────────────────────────────────────────────────


class Context:
    """What the hooks need to know about the current pass."""

    keys: Optional[Set[str]] = None  # the unit being run (None = all)
    lang: Optional[str] = None  # the language being drafted or repaired


def import_localize(stage_dir: Path) -> ModuleType:
    """Import vendored localize.py against the staged accord bundle."""
    os.environ["LOCALIZE_TARGET"] = "accord"
    os.environ["LOCALIZE_ACCORD_STAGE"] = str(stage_dir.resolve())
    for name in ("localize", "check_localization_sync", "glossary"):
        sys.modules.pop(name, None)
    # The vendored module, unmodified; typed as a plain module on purpose -- it
    # is not ours to annotate, and every hook below is set with setattr.
    return importlib.import_module("localize")


def install(L: ModuleType, stage: Stage, tms: Dict[str, TM]) -> None:
    """Point the vendored module's hooks at the accord."""
    # Concurrent lane shards share one provider key: wait out 402/429/5xx in
    # place instead of letting the vendored code read them as a dead rung.
    lane_backoff.install(L)
    for name, text in accord_prompts(L, stage.stem).items():
        if stage.extra_tm:
            text += _EXTRA_RULE_REVIEW if name == "SYSTEM_REVIEW" else _EXTRA_RULE
        setattr(L, name, text)
    setattr(L, "anchors_for", make_anchors(tms, stage.extra_tm))

    # Glossary: the deprecated ACCORD row is the document's own name here.
    upstream_deprecated = L.gloss.deprecated

    def deprecated(code: str) -> Dict[str, str]:
        rows: Dict[str, str] = upstream_deprecated(code)
        return {e: t for e, t in rows.items() if e.strip().upper() not in ACCORD_GLOSSARY_DROP}

    setattr(L.gloss, "deprecated", deprecated)

    # Which language a structural check is about: the vendored check does not
    # take one, and the script / untranslated rules need it.
    upstream_translate_lane = L.translate_lane
    upstream_repair_once = L._repair_once

    def translate_lane(lang: str, *args: Any, **kwargs: Any) -> Any:
        Context.lang = lang
        try:
            return upstream_translate_lane(lang, *args, **kwargs)
        finally:
            Context.lang = None

    def repair_once(lang: str, *args: Any, **kwargs: Any) -> Any:
        Context.lang = lang
        try:
            return upstream_repair_once(lang, *args, **kwargs)
        finally:
            Context.lang = None

    setattr(L, "translate_lane", translate_lane)
    setattr(L, "_repair_once", repair_once)

    upstream_structural = L.structural_problems

    def structural_problems(keys: Sequence[str], en_flat: Dict[str, Any], got: Dict[str, str]) -> Dict[str, str]:
        bad: Dict[str, str] = upstream_structural(keys, en_flat, got)
        for key in keys:
            if key in bad or key not in stage.slots or not isinstance(got.get(key), str):
                continue
            problems = seg.passage_problems(stage.slots[key], got[key], Context.lang)
            if problems:
                bad[key] = "; ".join(problems)
        return bad

    setattr(L, "structural_problems", structural_problems)

    upstream_missing = L.missing_by_language

    def missing_by_language() -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
        en_flat, missing = upstream_missing()
        if Context.keys is None:
            return en_flat, missing
        keep = Context.keys
        en_flat = {k: v for k, v in en_flat.items() if k in keep}
        missing = {lang: [k for k in ks if k in keep] for lang, ks in missing.items()}
        return en_flat, {lang: ks for lang, ks in missing.items() if ks}

    setattr(L, "missing_by_language", missing_by_language)


def units_of(stage: Stage) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for key in stage.en:
        out.setdefault(key.split(".")[1], set()).add(key)
    return out


def run_localize(L: ModuleType, argv: Sequence[str]) -> int:
    saved = sys.argv
    sys.argv = ["localize.py", *argv]
    try:
        rc: int = L.main()
    except SystemExit as exc:  # localize refuses with SystemExit; keep going per unit
        code = exc.code
        if isinstance(code, int):
            rc = code
        else:
            print(code)
            rc = 1
    finally:
        sys.argv = saved
    return rc


def _merge_reports(paths: Iterable[Tuple[str, Path]], out: Path) -> None:
    merged: Dict[str, Any] = {}
    for unit, path in paths:
        if path.is_file():
            merged[unit] = read_json(path)
            path.unlink()
    write_json(out, merged)


def segments_report(stage: Stage) -> None:
    n = len(stage.en)
    chars = sum(len(v) for v in stage.en.values())
    langs = len(stage.languages)
    print(f"accord {stage.version}: {n} segment(s), {chars:,} English chars, {langs} target locale(s)")
    for unit, keys in units_of(stage).items():
        uchars = sum(len(stage.en[k]) for k in keys)
        print(
            f"  {unit:<12} {len(keys):>4} segment(s) {uchars:>7,} chars  x{langs} = {len(keys) * langs:>6,} key-values"
        )
    print(f"  full pass: {n} x {langs} = {n * langs:,} key-values")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--version", default=os.environ.get("ACCORD_VERSION", DEFAULT_TM_VERSION))
    ap.add_argument("--tm-version", default=DEFAULT_TM_VERSION, help="previous accord used as translation memory")
    ap.add_argument("--stem", default=DEFAULT_STEM, help=f"target filename stem, one of {sorted(STEMS)}")
    ap.add_argument("--tm-stem", default=DEFAULT_STEM, help="filename stem of the translation-memory edition")
    ap.add_argument(
        "--seed-exact-tm",
        action="store_true",
        help="seed lines whose English is unchanged from the TM edition with its shipped translation",
    )
    ap.add_argument(
        "--extra-tm",
        action="append",
        type=Path,
        default=[],
        metavar="DIR",
        help="a ciris-website, CIRISClient or CIRISAgent checkout whose translated strings become extra "
        "terminology anchors (never values); repeatable",
    )
    ap.add_argument("--units", default="", help="space-separated units to run (default: all, one at a time)")
    ap.add_argument("--stage-dir", type=Path, default=None, help=argparse.SUPPRESS)
    ap.add_argument("--localized-dir", type=Path, default=LOCALIZED, help=argparse.SUPPRESS)
    ap.add_argument("--segments", action="store_true", help="print the segment plan and run size, then exit")
    ap.add_argument("--verify", action="store_true", help="offline gate over the staged bundles and files")
    ap.add_argument("--no-reassemble", action="store_true", help="do not write accord files after the run")
    args, rest = ap.parse_known_args(argv)

    # READ-ONLY unless this is a lane run that may write. --check, --dry-run,
    # --glossary-report, --segments and --verify never touch the live bundles
    # (ciris_engine/data/localized) or the committed stage: a read-only pass
    # stages into a throwaway copy of the committed stage.
    read_only = args.segments or args.verify or any(f in rest for f in READ_ONLY_FLAGS)
    scratch: Optional[tempfile.TemporaryDirectory[str]] = None
    check_stem(args.stem)
    check_stem(args.tm_stem)
    stage_dir = args.stage_dir or default_stage_dir(args.version, args.stem)
    if read_only and not args.verify:
        scratch = tempfile.TemporaryDirectory(prefix="accord-stage-")
        if stage_dir.is_dir():
            shutil.copytree(stage_dir, scratch.name, dirs_exist_ok=True)
        stage_dir = Path(scratch.name)
    try:
        stage = Stage(args.version, stage_dir=stage_dir, localized=args.localized_dir, stem=args.stem)
        return _main(args, rest, stage)
    finally:
        if scratch is not None:
            scratch.cleanup()


def _main(args: argparse.Namespace, rest: List[str], stage: Stage) -> int:
    if args.segments:
        segments_report(stage)
        return 0
    if args.verify:
        problems = stage.verify()
        for p in problems:
            print(f"[FAIL] {p}")
        print("[OK] accord bundles verify" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0

    units = units_of(stage)
    wanted = args.units.split()
    unknown = [u for u in wanted if u not in units]
    if unknown:
        raise SystemExit(f"[refuse] unknown unit(s) {unknown}; this accord has {list(units)}")

    tms = {lang: build_tm(stage.localized, args.tm_version, lang, args.tm_stem) for lang in stage.languages}
    if args.seed_exact_tm:
        stage.seed_tm = tms
    if args.extra_tm:
        stage.extra_tm, extra_report = load_extra_tm(args.extra_tm, stage.languages)
        print_extra_report(extra_report)
    stats = stage.build()
    for lang, s in sorted(stats.items()):
        extra = ", ".join(f"{k}={v}" for k, v in s.items() if k not in ("present", "total") and v)
        print(f"[stage] {lang}: {s['present']}/{s['total']}" + (f" ({extra})" if extra else ""))

    L = import_localize(stage.dir)
    install(L, stage, tms)

    passthrough = list(rest)
    if any(flag in passthrough for flag in ("--check", "--glossary-report")):
        if wanted:
            Context.keys = set().union(*(units[u] for u in wanted))
        try:
            return run_localize(L, passthrough)
        finally:
            Context.keys = None

    report: Optional[Path] = None
    if "--report" in passthrough:
        i = passthrough.index("--report")
        report = Path(passthrough[i + 1])
        del passthrough[i : i + 2]

    patterns = [passthrough[i + 1] for i, a in enumerate(passthrough[:-1]) if a == "--keys"]
    rc = 0
    written: List[Tuple[str, Path]] = []
    for unit, keys in units.items():
        if wanted and unit not in wanted:
            continue
        if patterns and not any(fnmatch.fnmatch(k, p) for k in keys for p in patterns):
            continue  # localize.py refuses a selection that matches nothing
        Context.keys = keys
        print(f"\n=== accord {stage.version} :: {unit} ({len(keys)} segment(s)) ===")
        argv_unit = list(passthrough)
        if report is not None:
            part = report.with_name(f"{report.stem}.{unit}{report.suffix}")
            argv_unit += ["--report", str(part)]
            written.append((unit, part))
        rc = max(rc, run_localize(L, argv_unit))
    Context.keys = None
    if report is not None:
        _merge_reports(written, report)

    if "--dry-run" not in passthrough:
        for lang, status in sorted(stage.finalize(write_files=not args.no_reassemble).items()):
            print(f"[accord] {lang}: {status}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
