"""Repair the localized ACCORD texts from the English canon, section by section.

WHAT THIS DOES. It regenerates each localized accord from the English canon,
section by section, so every file ends up structurally identical to the canon.
That is deliberately more than the #1140 content fix, because the corpus was
not uniform enough to patch: `ha` is missing Sections VI-IX outright (no
ratchet content anywhere in the file), `ta` and `te` carry only 4 of 11
section markers and `ta`'s Book IX is untranslated English, and section
identity for the front-matter-delimited blocks is language-dependent. A
section-scoped patch over that leaves a corpus nobody can reason about; a
regeneration from one source makes markers, section set, and content agree by
construction.

WHY A PIPELINE AND NOT A PATCH. The 29 localized accord texts are what the
action-selection DMAs put in front of the model, and they are translations of
`localized/accord_1.2b_en.txt`. When the canon changes -- as it did catching up
to CIRIS Constitution 1.0-rc4 (#1140) -- every translation carries the old
claims until it is re-translated. Hand-patching them is not viable: `ha` has no
Book IX at all, `ta`'s is untranslated English, and `ko`/`ur`/`my` do not share
the others' block shape, so one structural rule silently cuts the wrong span in
at least three files. Regenerating a section from the canon fixes shape and
content together.

GROUNDING. A cold translator invents its own terminology, and this corpus has
settled terminology. Three anchors go into every prompt, in this order:

  1. `prompts.language_guidance` from `localized/{lang}.json` -- up to ~20 KB of
     canonical operating rules for that language, with explicit term pairs and
     register rules. This is the authority when it and the model disagree.
  2. A glossary built by diffing `localized/en.json` against `{lang}.json` for
     keys whose English carries a domain term, so the model sees how this
     project already renders "Wise Authority", "deferral", "flourishing".
  3. In-domain prose exemplars from the same file and from ciris-website's
     dictionaries -- how this project writes long-form prose in that language.

Those corpora are machine translations repaired by the website's own pipeline
and spot-verified; they are not human-reviewed. They are used as terminology
and register anchors, which is what they are good for, and neither they nor
this pipeline's output should be described as approved translation.

STRUCTURE IS ASSERTED, NOT REQUESTED. The guard rejects a section whose formula
lines are not byte-identical, whose CC references went missing, which still
carries a withdrawn claim, which came back identical to the English, or which
came back in the wrong script. That catches the failure modes machine
translation actually has here -- it does not catch disfluency, so output stays
machine-translated pending native review.

    python3 tools/accord_i18n.py --plan
    python3 tools/accord_i18n.py --sections 'main/v9*' --lang de --lang fr
    python3 tools/accord_i18n.py --check
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
LOCALIZED = ROOT / "ciris_engine" / "data" / "localized"
CANON = LOCALIZED / "accord_1.2b_en.txt"
STATE = LOCALIZED / ".accord_i18n_state.json"
WEBSITE_DICTS = Path(os.environ.get("CIRIS_WEBSITE_DICTS", Path.home() / "ciris-website" / "src" / "i18n" / "dictionaries"))

MODEL = os.environ.get("ACCORD_I18N_MODEL", "anthropic/claude-sonnet-5")
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

#: Lines that must survive translation byte-for-byte. A formula that has been
#: "translated" is a different formula.
VERBATIM = re.compile(r"J = k_eff|k_eff = k /|^\s*\*\*C ∝|V\(k\) =")

#: Claims CC 1.0-rc4 withdrew (CC 6.2.1, 6.2.5). If one survives in any script,
#: the section was translated from a stale source.
WITHDRAWN = ("topologically improbable", "Ethilogics", "∝ 1/J", "O(1)", "O(n)",
             "computationally natural", "structurally favored", "not a metaphor")

#: Terms whose settled rendering the glossary should show the model.
DOMAIN = ("Wise Authority", "deferral", "flourishing", "stewardship", "coherence",
          "Accord", "covenant", "attestation", "federation", "consent", "conscience")

#: One representative codepoint range per non-Latin script, to catch a section
#: that came back in English (or empty) while claiming to be a translation.
SCRIPT = {
    "am": "ሀ-፿", "ar": "؀-ۿ", "fa": "؀-ۿ", "ur": "؀-ۿ",
    "bn": "ঀ-৿", "hi": "ऀ-ॿ", "mr": "ऀ-ॿ", "pa": "਀-੿",
    "ta": "஀-௿", "te": "ఀ-౿", "th": "฀-๿", "my": "က-႟",
    "ja": "぀-ヿ一-鿿", "ko": "가-힯", "zh": "一-鿿",
    "ru": "Ѐ-ӿ", "uk": "Ѐ-ӿ",
}


@dataclass
class Section:
    path: str          # e.g. "main/v9.mdx"
    marker: int        # line index of the '// content/sections/...' marker
    body_start: int    # first body line (after the front matter)
    end: int           # exclusive


def parse(text: str) -> Tuple[List[str], List[Section]]:
    """Split an accord text into sections.

    A section starts at a `// content/sections/...` marker OR at a bare
    front-matter block, and ends where the next one starts. Both forms are
    needed: the English canon introduces its Annexes with front matter and no
    marker, so keying only on markers made Book IX swallow every Annex -- 119
    lines where the Book is 76, which the heading-count guard then read as the
    model dropping seven headings. It was the parser.
    """
    lines = text.split("\n")

    def opens_front_matter(i: int) -> bool:
        if lines[i].strip() != "---":
            return False
        k = i + 1
        while k < len(lines) and lines[k].strip() == "":
            k += 1
        return k < len(lines) and lines[k].startswith(("title:", "description:"))

    bounds: List[Tuple[int, str]] = []
    for i, l in enumerate(lines):
        if l.startswith("// content/sections/"):
            bounds.append((i, l.split("// content/sections/", 1)[1].strip()))
        elif opens_front_matter(i) and not any(
            lines[j].startswith("// content/sections/") for j in range(max(0, i - 3), i)
        ):
            title = next((lines[k].split(":", 1)[1].strip() for k in range(i, min(i + 6, len(lines)))
                          if lines[k].startswith("title:")), f"block{i}")
            bounds.append((i, title.lower().replace(" ", "_")))

    out: List[Section] = []
    for n, (i, path) in enumerate(bounds):
        fence = [k for k in range(i, min(i + 14, len(lines))) if lines[k].strip() == "---"]
        body = fence[1] + 1 if len(fence) >= 2 else i + 1
        end = bounds[n + 1][0] if n + 1 < len(bounds) else len(lines)
        while end - 1 > body and lines[end - 1].strip() == "":
            end -= 1
        out.append(Section(path, i, body, end))
    return lines, out


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def _flat(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _flat(v, f"{prefix}{k}.")
    elif isinstance(obj, str):
        yield prefix[:-1], obj


def grounding(lang: str) -> str:
    """language_guidance + a domain glossary + in-domain prose, for one language."""
    parts: List[str] = []
    tgt_p, en_p = LOCALIZED / f"{lang}.json", LOCALIZED / "en.json"
    tgt = dict(_flat(json.loads(tgt_p.read_text(encoding="utf-8")))) if tgt_p.exists() else {}
    en = dict(_flat(json.loads(en_p.read_text(encoding="utf-8")))) if en_p.exists() else {}

    lg = tgt.get("prompts.language_guidance", "")
    if lg:
        parts.append("=== CANONICAL LANGUAGE GUIDANCE (the authority on register and "
                     f"terminology for {lang}; it outranks your own preference) ===\n{lg[:14000]}")

    pairs = [f"  {en[k]!r}\n    -> {tgt[k]!r}"
             for k in sorted(set(en) & set(tgt))
             if 12 < len(en[k]) < 180 and any(t.lower() in en[k].lower() for t in DOMAIN)][:40]
    if pairs:
        parts.append("=== HOW THIS PROJECT ALREADY RENDERS ITS TERMS (follow these) ===\n" + "\n".join(pairs))

    prose = sorted((v for k, v in tgt.items() if 250 < len(v) < 1500 and "language_guidance" not in k),
                   key=len, reverse=True)[:3]
    web = WEBSITE_DICTS / f"{lang}.json"
    if web.exists():
        wd = dict(_flat(json.loads(web.read_text(encoding="utf-8"))))
        prose += sorted((v for v in wd.values() if 250 < len(v) < 1300), key=len, reverse=True)[:3]
    if prose:
        parts.append("=== IN-DOMAIN PROSE IN THIS LANGUAGE (match this voice) ===\n\n"
                     + "\n\n---\n\n".join(p[:1200] for p in prose))
    return "\n\n".join(parts)


PROMPT = """You are producing the {lang_name} ({lang}) edition of the CIRIS Accord, a
governance covenant. Translate the SECTION below from the English canon. It replaces
the existing {lang} text, which was translated from a superseded source.

RULES, in order of precedence:
1. Structural lines are reproduced BYTE-FOR-BYTE, never translated:
   - any line beginning `// content/sections/`
   - every `---` front-matter fence
   - any line carrying a formula (J = ..., k_eff = ..., V(k) = ...)
2. Front-matter KEYS (`title:`, `description:`) stay in English; translate only their
   VALUES.
3. These stay exactly as written, in Latin script: every "CC n.n.n" reference,
   RATCHET#17, M-1, PDMA, WBD, LensCore, J, k_eff, λ_op, σ, ρ̄, k.
4. Markdown structure is preserved exactly: heading levels, list markers, bold/italic
   markers, blank lines, and the number and order of paragraphs.
5. The canonical language guidance above outranks your own stylistic preference.
6. Translate the prose. Do not summarise, expand, explain, or add notes. Do not carry
   over any claim that is not in the English source.

Return ONLY the translated section, starting at its first line. No preamble, no code
fence, no commentary."""


def call(system: str, user: str, model: str, key: str) -> str:
    req = urllib.request.Request(
        ENDPOINT,
        # Sized to the input, not fixed. main/v6 is 13 KB of English, and Amharic,
        # Bengali and Burmese expand well past one token per character -- a flat
        # 16k budget stopped mid-section and came back as content=None, which is
        # what the first pass's rejects were.
        data=json.dumps({"model": model, "max_tokens": max(16000, min(64000, len(user) * 6)),
                         "temperature": 0.2,
                         "messages": [{"role": "system", "content": system},
                                      {"role": "user", "content": user}]}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "X-Title": "CIRIS accord i18n"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        body = json.loads(r.read().decode())
    if "choices" not in body:
        raise RuntimeError(f"no choices in response: {json.dumps(body)[:300]}")
    choice = body["choices"][0]
    content = (choice.get("message") or {}).get("content")
    if not content:
        # A refusal, a filter, or a length stop with nothing emitted. It arrives
        # as content=None and used to surface as AttributeError on .strip(),
        # which reads like a bug in the pipeline rather than a model outcome.
        raise RuntimeError(f"empty content (finish_reason={choice.get('finish_reason')!r})")
    return content.strip()


def guard(lang: str, english: str, got: str) -> List[str]:
    """Everything we can assert without a native speaker."""
    bad: List[str] = []
    if not got.strip():
        return ["empty"]
    en_f = [l.strip() for l in english.split("\n") if VERBATIM.search(l)]
    got_f = [l.strip() for l in got.split("\n") if VERBATIM.search(l)]
    if en_f != got_f:
        bad.append(f"formula lines differ (want {len(en_f)}, got {len(got_f)})")
    en_cc = sorted(re.findall(r"CC \d+\.\d+(?:\.\d+)?", english))
    if en_cc and sorted(re.findall(r"CC \d+\.\d+(?:\.\d+)?", got)) != en_cc:
        bad.append("CC references dropped or altered")
    for w in WITHDRAWN:
        if w in got and w not in english:
            bad.append(f"withdrawn claim reintroduced: {w!r}")
    if lang != "en" and got.strip() == english.strip():
        bad.append("identical to the English source (untranslated)")
    rng = SCRIPT.get(lang)
    if rng and not re.search(f"[{rng}]", got):
        bad.append(f"no {lang} script in the output")
    en_h = [l for l in english.split("\n") if l.startswith("#")]
    got_h = [l for l in got.split("\n") if l.startswith("#")]
    if len(en_h) != len(got_h):
        bad.append(f"heading count {len(got_h)} != English {len(en_h)}")
    # Structural lines are the file's skeleton: a translated marker or a lost
    # fence turns the section into something the parser cannot find again.
    en_m = [l for l in english.split("\n") if l.startswith("// content/sections/")]
    got_m = [l for l in got.split("\n") if l.startswith("// content/sections/")]
    if en_m != got_m:
        bad.append("section marker line altered or dropped")
    en_d = sum(1 for l in english.split("\n") if l.strip() == "---")
    got_d = sum(1 for l in got.split("\n") if l.strip() == "---")
    if en_d != got_d:
        bad.append(f"front-matter fences {got_d} != English {en_d}")
    for key in ("title:", "description:"):
        if sum(1 for l in english.split("\n") if l.startswith(key)) != \
           sum(1 for l in got.split("\n") if l.startswith(key)):
            bad.append(f"front-matter key {key!r} count changed")
    return bad


CACHE = LOCALIZED / ".accord_i18n_cache"


def units_of(canon_lines: List[str], secs: List[Section]) -> List[Tuple[str, str]]:
    """(path, full section text) for the whole canon, preamble first."""
    out = [("preamble", "\n".join(canon_lines[: secs[0].marker]).rstrip("\n"))]
    for n, sec in enumerate(secs):
        end = secs[n + 1].marker if n + 1 < len(secs) else len(canon_lines)
        out.append((sec.path, "\n".join(canon_lines[sec.marker:end]).rstrip("\n")))
    return out


def chunk(text: str, limit: int = 5000) -> List[str]:
    """Split a long section at `## ` headings, merging pieces under the limit.

    The marker line and front matter ride with the first piece, so every chunk
    is still a well-formed fragment the prompt's structural rules apply to.
    """
    if len(text) <= limit:
        return [text]
    lines = text.split("\n")
    cuts = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if len(cuts) < 2:
        return [text]
    pieces, start = [], 0
    for c in cuts[1:] + [len(lines)]:
        pieces.append("\n".join(lines[start:c]))
        start = c
    out: List[str] = []
    for piece in pieces:
        if out and len(out[-1]) + len(piece) < limit:
            out[-1] = out[-1] + "\n" + piece
        else:
            out.append(piece)
    return out


def translate_unit(lang: str, path: str, english: str, ground: str, model: str, key: str,
                   name: str) -> Tuple[str, Optional[str], List[str]]:
    """Cached, guarded translation of one section. Returns (path, text|None, problems)."""
    slot = CACHE / lang / f"{path.replace('/', '_')}.{sha(english)}.txt"
    if slot.exists():
        return path, slot.read_text(encoding="utf-8"), []
    if path == "preamble":
        # Provenance, not prose: it names a repository, a commit and the CC
        # sections this text instantiates. It is identical in every language on
        # purpose, so it is copied rather than sent to a translator -- and the
        # "identical to English" guard would otherwise reject it, correctly, for
        # a property we want.
        slot.parent.mkdir(parents=True, exist_ok=True)
        slot.write_text(english, encoding="utf-8")
        return path, english, []
    system = (ground + "\n\n" if ground else "") + PROMPT.format(lang=lang, lang_name=name)
    try:
        # LARGE SECTIONS GET SPLIT. main/v6 is 13 KB and came back with one
        # heading where the English has seven -- in Indonesian as readily as in
        # Amharic, so this is the model summarising a long document, not an
        # output budget or a script that expands. Chunking at `## ` boundaries
        # keeps each request short enough to be translated rather than
        # abridged, and the guard still judges the reassembled section.
        parts = chunk(english)
        got = "\n".join(call(system, c, model, key) for c in parts) if len(parts) > 1 \
            else call(system, english, model, key)
    except Exception as exc:  # noqa: BLE001 -- one unit's failure must not end the run
        return path, None, [f"{type(exc).__name__}: {exc}"]
    got = re.sub(r"^```[a-z]*\n|\n```$", "", got.strip())
    bad = guard(lang, english, got)
    if bad:
        return path, None, bad
    slot.parent.mkdir(parents=True, exist_ok=True)
    slot.write_text(got, encoding="utf-8")
    return path, got, []


def main() -> int:
    import concurrent.futures as cf

    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", action="append", default=[], help="language code; repeatable. Empty = all")
    ap.add_argument("--sections", action="append", default=[], help="fnmatch over section paths; empty = the whole document")
    ap.add_argument("--plan", action="store_true", help="show what would run; no API call")
    ap.add_argument("--check", action="store_true", help="guard what is on disk; no API call")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()

    canon_lines, canon_secs = parse(CANON.read_text(encoding="utf-8"))
    canon_units = units_of(canon_lines, canon_secs)
    if args.sections:
        canon_units = [(p, t) for p, t in canon_units
                       if p == "preamble" or any(fnmatch.fnmatch(p, g) for g in args.sections)]
    langs = args.lang or sorted(
        p.stem.split("_")[-1] for p in LOCALIZED.glob("accord_1.2b_*.txt") if not p.stem.endswith("_en"))
    names = {}
    mf = LOCALIZED / "manifest.json"
    if mf.exists():
        raw = json.loads(mf.read_text(encoding="utf-8")).get("languages", {})
        names = {k: (v.get("name") if isinstance(v, dict) else v) for k, v in raw.items()} if isinstance(raw, dict) else {}

    todo = [(l, p, t) for l in langs for p, t in canon_units
            if not (CACHE / l / f"{p.replace('/', '_')}.{sha(t)}.txt").exists()]
    print(f"model={args.model}  langs={len(langs)}  sections={len(canon_units)}  "
          f"units={len(langs) * len(canon_units)}  to translate={len(todo)}  workers={args.workers}",
          flush=True)

    if args.check:
        rc = 0
        for lang in langs:
            f = LOCALIZED / f"accord_1.2b_{lang}.txt"
            have = {s.path for s in parse(f.read_text(encoding="utf-8"))[1]}
            miss = [p for p, _ in canon_units if p != "preamble" and p not in have]
            if miss:
                print(f"  {lang}: missing {miss}"); rc = 1
        print("check complete" + ("" if rc else " — every language carries the canon's sections"))
        return rc
    if args.plan:
        for l, p, _ in todo[:40]:
            print(f"  {l:4} {p}")
        if len(todo) > 40:
            print(f"  ... and {len(todo) - 40} more")
        return 0

    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        kf = Path.home() / ".openrouter_key"
        key = kf.read_text().strip() if kf.exists() else ""
    if not key:
        print("no OPENROUTER_API_KEY"); return 1

    grounds = {l: grounding(l) for l in langs}
    problems: Dict[str, List[str]] = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(translate_unit, l, p, t, grounds[l], args.model, key,
                          names.get(l, l)): (l, p) for l, p, t in todo}
        done = 0
        for fut in cf.as_completed(futs):
            lang, path = futs[fut]
            _, text, bad = fut.result()
            done += 1
            if bad:
                problems.setdefault(lang, []).append(f"{path}: {'; '.join(bad)}")
                print(f"  [REJECT] {lang} {path}: {'; '.join(bad)}", flush=True)
            elif done % 20 == 0:
                print(f"  ... {done}/{len(todo)}", flush=True)

    # Assemble only languages whose every section is cached: a half-translated
    # accord on disk is worse than the stale one it replaced.
    written = 0
    for lang in langs:
        parts = []
        for p, t in canon_units:
            slot = CACHE / lang / f"{p.replace('/', '_')}.{sha(t)}.txt"
            if not slot.exists():
                parts = []
                break
            parts.append(slot.read_text(encoding="utf-8"))
        if not parts:
            print(f"  [HOLD] {lang}: incomplete, file left as it was")
            continue
        (LOCALIZED / f"accord_1.2b_{lang}.txt").write_text("\n\n".join(parts) + "\n", encoding="utf-8")
        written += 1
    print(f"\n{written}/{len(langs)} languages regenerated. "
          f"{sum(len(v) for v in problems.values())} unit(s) rejected. "
          "Machine translation pending native review.", flush=True)
    return 0 if written == len(langs) else 1


if __name__ == "__main__":
    raise SystemExit(main())
