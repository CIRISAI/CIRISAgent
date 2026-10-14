#!/usr/bin/env python3
"""Translate, evaluate and repair CIRIS localization keys — one pipeline, in CI.

    python3 localization/localize.py --check                     # what is missing
    python3 localization/localize.py --lane translate            # missing keys -> 28 locales
    python3 localization/localize.py --lane translate --keys 'mesh_config.*'
    python3 localization/localize.py --lane evaluate --keys 'commons_surface.*'
    python3 localization/localize.py --lane repair   --keys 'nav.*' --lang yo

THREE LANES, ONE DIRECTION. `--lane` chooses where a run ENTERS; every run then
flows through the rest:

    translate ──► evaluate ──► repair
                  ▲             ▲
                  └─ enter here └─ enter here

A key brought in to be translated is reviewed before it is written, and
repaired if the review found anything. A review that finds nothing makes repair
a no-op — it is not skipped, it has nothing to do. There is no lane that writes
an unreviewed string into a shipped bundle.

WHY A PIPELINE AND NOT AN AGENT FAN-OUT. This replaces the interactive Claude
Code fan-outs (CIRISServer 0.5.185's 87 agents). Same model family, ~100x
cheaper, and — the part that matters more — reproducible: the same keys, the
same glossary, the same anchors, the same gate. `check_localization_sync.py
--strict` decides what merges either way.

The fan-out also failed in a way this design has to answer for. Haiku sub-agents
were the documented recommendation (CIRISAgent LESSONS_LEARNED.md §3) and they
produced word-salad in 5 of 28 locales that STRUCTURAL validation could not
see: the JSON parsed, the keys were all present, the placeholders matched.
Nothing below the semantic layer can catch that, which is why the evaluate lane
exists and why it is not optional.

── The four inputs every request carries ──────────────────────────────────────

1. GLOSSARY — `localization/glossaries/{code}_glossary.md`, 3,045 canonical term
   pairs across 28 languages, plus each language's standing prose rules (use the
   formal እርስዎ; never omit Yoruba's dot-below). Only the terms that occur in the
   batch are sent. Glossary-first is the one practice the retrospectives credit
   unreservedly.
2. TRANSLATION MEMORY — real shipped translations for this language, retrieved
   two ways: the dot-prefix family of each requested key, and lexical overlap
   with its English text. ~3,853 keys x 29 locales already exist; a model asked
   to translate "node" fresh will pick something, and the corpus already
   decided. Adaptive MT with fuzzy matches is the standard construction here
   (Moslem et al., EAMT 2023).
3. THE ENGLISH SOURCE — byte-identical across all 28 language requests, so it
   sits in one cacheable prefix.
4. THE PLACEHOLDER CONTRACT — stated, then enforced mechanically afterwards.

── Evaluate: MQM, not a vibe ──────────────────────────────────────────────────

The review lane asks for error SPANS with a category and a severity, following
MQM as GEMBA-MQM applies it to LLM judging: reference-free, span-level,
`{accuracy, fluency, terminology, style, locale}` x `{critical, major, minor}`,
scored by severity weight. A number with no error list behind it is a number
nobody can act on, so the lane emits the errors and derives the score.

The judge is a DIFFERENT MODEL FAMILY from the drafter, on purpose. A judge
that shares the drafter's weights shares its blind spots and prefers its own
output; independence is the whole value of the second pass.

── No rejections, and what that costs ─────────────────────────────────────────

Low-resource languages are where this gets decided. Yoruba, Hausa and Amharic
are Tier 0 in CIRIS's own priority order — ranked by INVERSE model support,
because Meta-Goal M-1 makes need the criterion rather than market size — and
they are exactly where a model is most likely to say it cannot help.

A refusal is therefore made EXPRESSIBLE so it can be detected (the model is
asked to return `null` and a reason rather than inventing something), and then
it is never accepted as an answer. The key escalates to the next rung of the
ladder — one key, not the batch — and the ladder's last rung is a different
model family from the first. If every rung refuses, the run FAILS LOUDLY. It
does not fall back to English: shipping English to a Yoruba speaker under a
Yoruba locale is the silent demotion this whole apparatus exists to prevent.

Escalation is per key and per language, so the cost of the hard cases is paid
on the hard cases.

── What this pipeline does NOT claim ──────────────────────────────────────────

CIRISAgent's `localization/CLAUDE.md` is blunt about the line, and this tool
holds it. GUARANTEED: terminology consistency, structural completeness,
functional correctness, meaning preservation, placeholder integrity. NOT
guaranteed: native fluency, dialect coverage, cultural adaptation of metaphor,
legal review. Everything this pipeline writes is `status: draft` /
`review_status: machine_reviewed`, and no output of it may be marketed as
native quality.

The label was `needs_native_review`, which named an action nobody was going to
take: there is no native-reviewer pipeline and no queue behind that string. A
pending that can never clear is a worse claim than a stated limit, and it also
hides the real one — these are machine translations, MQM-reviewed by a model of
a different family from the one that wrote them, and that is the whole of it.
Say so plainly rather than implying a human is coming.

── Cost design, in the order that actually saves money ────────────────────────

1. DIFF-DRIVEN by default — a run with nothing missing makes zero API calls,
   which is also the workflow's loop guard.
2. SHARED CACHEABLE PREFIX — system + English source are byte-identical across
   the 28 language requests.
3. RELEVANT glossary and anchors only — not 3,045 pairs.
4. ESCALATION IS SPARING — the expensive rungs see only what the cheap rung
   refused or the judge rejected.
5. BATCH MODE — the same requests at 50% off for backfills nobody is waiting on.

Providers: `OPENROUTER_API_KEY` drives the OpenRouter path (the ladder's model
ids are OpenRouter slugs; `:batch` halves them). `ANTHROPIC_API_KEY` drives the
Anthropic SDK path, which adds real prompt caching and the Batches API but can
only reach Anthropic rungs. `LOCALIZE_PROVIDER=anthropic|openrouter` forces one.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "client" / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_localization_sync as guard  # noqa: E402  the gate's own semantics
import glossary as gloss  # noqa: E402

CANONICAL = REPO_ROOT / guard.CANONICAL_BUNDLE


# ─────────────────────────────────────────────────────────────────────────────
# Provider and the model ladder
# ─────────────────────────────────────────────────────────────────────────────

def _provider() -> str:
    forced = os.environ.get("LOCALIZE_PROVIDER")
    if forced:
        return forced
    if os.environ.get("OPENROUTER_API_KEY"):
        return "openrouter"
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "openrouter"  # fails loudly at call time with the API's own message


PROVIDER = _provider()

# THE LADDER. Rung 0 drafts everything; rungs 1+ are reached only by a key that
# was refused or rejected. The last rung is deliberately a different family from
# the first: if Anthropic's best cannot render a string in Yoruba, asking
# Anthropic's best again is not an escalation, it is a retry.
_LADDERS = {
    "openrouter": (
        "anthropic/claude-sonnet-5",   # draft — strongest on tone and register
        "google/gemini-3.7-flash",     # first repair — a different family, and the
                                       # measured best on low-resource languages
        "anthropic/claude-opus-5",     # last word — the hard keys
    ),
    "anthropic": ("claude-sonnet-5", "claude-opus-5"),
}
LADDER: Tuple[str, ...] = tuple(
    m.strip() for m in os.environ["LOCALIZE_LADDER"].split(",") if m.strip()
) if os.environ.get("LOCALIZE_LADDER") else _LADDERS[PROVIDER]

# The judge. Different family from the drafter — see the module docstring.
#
# The Anthropic SDK path CANNOT satisfy that: it reaches only Anthropic models,
# so its drafter and its judge are the same family and the second pass stops
# being independent. That is not a smaller version of the design, it is the
# design's one load-bearing property removed, so the provider says so out loud
# rather than quietly reviewing itself. Set LOCALIZE_REVIEW_MODEL to accept it
# deliberately (a same-family judge still catches plenty; it just cannot be
# claimed as independent), or use OpenRouter, which reaches every rung.
_DEFAULT_REVIEWER = {"openrouter": "openai/gpt-5.1"}


def _review_model() -> str:
    forced = os.environ.get("LOCALIZE_REVIEW_MODEL")
    if forced:
        return forced
    model = _DEFAULT_REVIEWER.get(PROVIDER)
    if model:
        return model
    raise SystemExit(
        f"[refuse] LOCALIZE_PROVIDER={PROVIDER} reaches only one model family, so "
        f"the drafter and the reviewer would be relatives and the review lane "
        f"would be checking its own homework. Use OPENROUTER_API_KEY (the ladder "
        f"and an independent judge), or set LOCALIZE_REVIEW_MODEL explicitly to "
        f"accept a same-family review — which is worth having, but must not be "
        f"described as independent."
    )


#: Resolved once at the start of a run rather than at import, so `--check` and
#: `--glossary-report` still work on a provider that cannot supply a judge.
REVIEW_MODEL = ""

# $/MTok (input, output) for the cost REPORT only; billing is whatever the API
# bills. From OpenRouter's model list. Update when a rung moves.
PRICE = {
    "anthropic/claude-sonnet-5": (2.00, 10.00),
    "anthropic/claude-opus-5": (5.00, 25.00),
    "anthropic/claude-haiku-4.5": (1.00, 5.00),
    "openai/gpt-5.1": (1.25, 10.00),
    "openai/gpt-5-pro": (15.00, 120.00),
    "google/gemini-3.7-flash": (0.75, 3.75),
    "google/gemini-3.1-pro-preview": (2.00, 12.00),
    "openai/gpt-5.4": (2.50, 15.00),
    "x-ai/grok-4.6": (2.00, 6.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
}

# ─────────────────────────────────────────────────────────────────────────────
# MQM
# ─────────────────────────────────────────────────────────────────────────────

# Severity weights. MQM scores by weighted error count, and the weights are what
# make "12 minor nits" and "one sentence that says the opposite" different
# numbers rather than the same one.
SEVERITY_PENALTY = {"critical": 10, "major": 5, "minor": 1}

# What sends a key to the repair lane. Critical and major are obvious. A
# TERMINOLOGY error joins them at any severity because it is the one category
# the glossary makes objective: the canonical term is written down, so
# "disagrees with the glossary" is a fact, not a judgement, and letting it ship
# is how the terminology consistency this pipeline DOES guarantee stops being
# true.
def needs_repair(errors: Sequence[dict]) -> bool:
    return any(
        e.get("severity") in ("critical", "major") or e.get("category") == "terminology"
        for e in errors
    )


def mqm_score(errors: Sequence[dict]) -> int:
    """100 minus the severity-weighted penalty, floored at 0."""
    penalty = sum(SEVERITY_PENALTY.get(e.get("severity", "minor"), 1) for e in errors)
    return max(0, 100 - penalty)


# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

#: The one source for the lessons three production runs taught. Parsed from the
#: guide rather than restated here — a rule that lives in two places drifts, and
#: the copy that drifts is the one the models are reading.
TRANSLATION_GUIDE = Path(__file__).resolve().parent / "TRANSLATION_GUIDE.md"
_GUIDE_SECTION = "## 3. The failure modes that actually occur"


def _guide_rules() -> str:
    """The guide's §3 bullets, as prompt text.

    Fails loudly rather than returning "". A prompt that quietly lost its rules
    still produces confident output, and nothing downstream can tell the
    difference — which is the same shape as a gate that cannot fail.
    """
    try:
        text = TRANSLATION_GUIDE.read_text(encoding="utf-8")
    except OSError as e:
        raise SystemExit(f"[refuse] cannot read {TRANSLATION_GUIDE}: {e}. Its §3 is "
                         f"what every agent is told about the failure modes seen in "
                         f"production; running without it silently drops them.")
    start = text.find(_GUIDE_SECTION)
    if start < 0:
        raise SystemExit(f"[refuse] {TRANSLATION_GUIDE.name} has no section "
                         f"{_GUIDE_SECTION!r} — the prompts are built from it.")
    end = text.find("\n## ", start + len(_GUIDE_SECTION))
    body = text[start:end if end > 0 else len(text)]
    rules = re.findall(r"^- (\*\*.+?)(?=\n- |\n\n|\Z)", body, re.M | re.S)
    if not rules:
        raise SystemExit(f"[refuse] {_GUIDE_SECTION!r} parsed to zero rules. The "
                         f"section is the prompts' only source; an empty parse is a "
                         f"silently weaker pipeline, not an empty section.")
    clean = [" ".join(r.split()) for r in rules]
    return "\n".join(f"- {r}" for r in clean)


GUIDE_RULES = _guide_rules()

_PLACEHOLDER_RULE = """- Preserve every placeholder EXACTLY as it appears in the English source:
  {named}, ${expr}, %s, %1$s. Never translate, rename, drop, add or reorder one.
- Product terms stay untranslated: CIRIS, ciris-server, key_id, USB, and version
  numbers like 0.5.188."""

SYSTEM_TRANSLATE = f"""You translate UI strings for CIRIS, a decentralized mesh \
client shipped in 29 languages. You will receive English source strings and \
must return translations for ONE target language.

Rules, all of them hard:
- Return ONLY a JSON object. No markdown fences, no commentary.
- The object has two members: "translations" (key -> translated string) and
  "refusals" (key -> one-sentence reason). Every requested key appears in
  exactly one of them.
{_PLACEHOLDER_RULE}
- The CANONICAL TERMINOLOGY block is decided, not advisory. Use those renderings
  exactly, including diacritics and tone marks.
- The ANCHOR TRANSLATIONS are real shipped strings in this language from this
  same product. Match their register, formality and terminology. If the anchors
  are formal, you are formal.
- These are UI strings: concise, natural, idiomatic. A button label stays a
  button label.
- USE "refusals" ONLY IF YOU GENUINELY CANNOT PRODUCE A FAITHFUL TRANSLATION.
  It exists so that "I cannot do this" is sayable instead of being disguised as
  a bad translation, and a refusal is ROUTED TO A STRONGER MODEL rather than
  shipped. Never return English text as a translation, never transliterate the
  English, and never invent a plausible-looking string you do not stand behind —
  those are worse than a refusal, because nothing downstream can see them.

WHAT WENT WRONG BEFORE. Every one of these was a real finding on a real run of
this pipeline, in some language, and each cost a release:
""" + GUIDE_RULES

SYSTEM_REVIEW = f"""You are an independent translation quality reviewer for \
CIRIS, a decentralized mesh client shipped in 29 languages. You did not write \
these translations.

Annotate each one with MQM error spans. Categories: accuracy (mistranslation,
omission, addition), fluency (grammar, spelling, unnatural phrasing, and
NON-WORDS OR WORD-SALAD), terminology (disagrees with the canonical glossary
supplied), style (register or formality wrong for a UI), locale (script,
numerals, punctuation, direction wrong for this language).
Severities: critical (the reader is misled, or the string is unusable),
major (clearly wrong but the intent survives), minor (a nit).

Return ONLY a JSON object mapping each key to a list of error objects:
  {{"nav.home": [{{"category":"terminology","severity":"major",
                  "span":"<the offending text>","note":"<what is wrong>",
                  "suggestion":"<what it should be>"}}],
    "nav.back": []}}
An empty list means no error found. Every key you were given must appear.

Judge hard and specifically:
{_PLACEHOLDER_RULE}
- A string that is fluent but says something the English does not is ACCURACY
  critical, not style.
- A string containing invented or garbled words in the target language is
  FLUENCY critical. This is the failure a structural check cannot see and the
  one you are most needed for.
- A term that disagrees with the CANONICAL TERMINOLOGY block is TERMINOLOGY,
  even if the alternative is a fine word in isolation.
- Do NOT invent errors to look thorough. An empty list is the correct and
  expected answer for a good translation.
- Agreement with the CANONICAL TERMINOLOGY block is NOT a finding. Report
  terminology only where the translation DISAGREES with it. A note that says
  the term was used correctly must not appear as an error.
- Echoing the glossary's TABLE CASE is not a finding. The tables are written
  in title case as a formatting convention; a term used mid-sentence takes the
  target language's own casing. Do not report a term merely for differing in
  case from its glossary row.
  BUT the target language's own casing rules are normative and DO produce
  findings where a glossary states them — German capitalizes all nouns
  (de_glossary.md "Capitalization"), and a lowercase noun there is an
  orthographic error, not a style preference.

LOOK FOR THESE SPECIFICALLY. Each is a defect this pipeline has actually shipped
past a structural gate, in some language, on some run:
""" + GUIDE_RULES

SYSTEM_REPAIR = f"""You are correcting CIRIS UI translations that a reviewer \
rejected. You will receive the English source, the current translation, and the \
reviewer's MQM findings for each key.

Rules:
- Return ONLY a JSON object with "translations" (key -> corrected string) and
  "refusals" (key -> reason), exactly as the translation lane uses.
- FIX WHAT WAS FOUND. Do not rewrite what was not flagged: a repair that
  restyles a clean sentence is a new risk taken for no reason.
- If you judge a finding to be WRONG, return the current translation unchanged
  rather than damaging it to satisfy a bad review, and say so in "refusals".
{_PLACEHOLDER_RULE}
- The CANONICAL TERMINOLOGY block wins every terminology dispute.

THE DEFECTS YOU ARE MOST LIKELY CORRECTING. Each has been a real finding here:
""" + GUIDE_RULES


# ─────────────────────────────────────────────────────────────────────────────
# Bundles, selection, translation memory
# ─────────────────────────────────────────────────────────────────────────────

def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def target_languages() -> List[str]:
    return [l for l in guard.manifest_languages(CANONICAL) if l != "en"]


def missing_by_language() -> Tuple[dict, Dict[str, List[str]]]:
    """en flat map, and per-language keys missing or empty."""
    en_flat = guard.flat_values(load(CANONICAL / "en.json"))
    out: Dict[str, List[str]] = {}
    for lang in target_languages():
        lang_flat = guard.flat_values(load(CANONICAL / f"{lang}.json"))
        need = [k for k in en_flat if k not in lang_flat or not str(lang_flat[k]).strip()]
        if need:
            out[lang] = sorted(need)
    return en_flat, out


def select(patterns: Sequence[str], langs: Sequence[str], *, only_missing: bool
           ) -> Tuple[dict, Dict[str, List[str]]]:
    """Resolve --keys/--lang into {lang: [keys]}.

    `--keys` is fnmatch over FLAT dotted keys, repeatable, so
    `--keys 'mesh_config.*' --keys 'nav.home'` is one selection. With no
    `--keys` the selection is whatever is missing, which is the diff-driven
    default that keeps a no-op run free.
    """
    en_flat, missing = missing_by_language()
    wanted_langs = list(langs) or target_languages()
    unknown = sorted(set(wanted_langs) - set(target_languages()))
    if unknown:
        raise SystemExit(f"[refuse] not languages this bundle ships: {', '.join(unknown)}")

    if not patterns:
        if not only_missing:
            raise SystemExit(
                "[refuse] the evaluate and repair lanes need a selection: pass "
                "--keys (and optionally --lang). Without one the only defensible "
                "default is 'every key in every language', which is 107,884 "
                "comparisons and a bill nobody asked for — and the other "
                "candidate default, 'whatever is missing', is exactly the set "
                "with nothing to review yet."
            )
        return en_flat, {l: k for l, k in missing.items() if l in wanted_langs}

    keys = sorted(k for k in en_flat if any(fnmatch.fnmatch(k, p) for p in patterns))
    if not keys:
        raise SystemExit(f"[refuse] no en.json key matches {list(patterns)} — "
                         f"a selection that matches nothing is a typo, not an empty run")
    out: Dict[str, List[str]] = {}
    for lang in wanted_langs:
        chosen = keys if not only_missing else [k for k in keys if k in missing.get(lang, ())]
        if chosen:
            out[lang] = chosen
    return en_flat, out


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9']+")

# An anchor is an EXEMPLAR, not a document. `prompts.language_guidance` is a
# real key in these bundles and Yoruba's value is 31,297 characters — a
# per-language DMA primer. Lexical overlap loves it: it contains most words, so
# it out-scores every genuinely similar UI string and lands in the prompt, where
# it costs ~8k tokens per request and teaches the model nothing about how a
# button label should read. Anchors are capped, and the score below is
# normalised so length cannot buy relevance.
MAX_ANCHOR_CHARS = 240
MAX_ANCHOR_BLOCK_CHARS = 6000


def anchors_for(lang: str, needed: Sequence[str], en_flat: dict, *, limit: int = 30
                ) -> List[Tuple[str, str, str]]:
    """(key, english, shipped translation) — the translation memory for a batch.

    Two retrieval routes, because they find different things. The dot-prefix
    FAMILY gives sibling strings from the same screen, which fixes register. The
    lexical OVERLAP gives strings that share vocabulary with what is being
    translated, which fixes terminology — and it is the one that matters for a
    key whose family is empty because the whole family is new.
    """
    lang_flat = guard.flat_values(load(CANONICAL / f"{lang}.json"))
    picked: List[Tuple[str, str, str]] = []
    seen: set = set()

    def take(key: str) -> bool:
        if key in seen or key in needed:
            return False
        if key not in lang_flat or key not in en_flat:
            return False
        english, shipped = str(en_flat[key]), str(lang_flat[key])
        if not shipped.strip():
            return False
        if len(english) > MAX_ANCHOR_CHARS or len(shipped) > MAX_ANCHOR_CHARS:
            return False  # a document, not an exemplar — see MAX_ANCHOR_CHARS
        picked.append((key, english, shipped))
        seen.add(key)
        return True

    for family in sorted({k.rsplit(".", 1)[0] for k in needed}):
        taken = 0
        for k in sorted(en_flat):
            if taken >= 3:
                break
            if k.rsplit(".", 1)[0] == family and take(k):
                taken += 1

    want = {w.lower() for k in needed for w in _TOKEN.findall(str(en_flat.get(k, "")))}
    want -= {"the", "a", "an", "and", "or", "to", "of", "is", "in", "for", "this", "that"}
    if want:
        scored = []
        for k, text in en_flat.items():
            if k in seen or k in needed or len(str(text)) > MAX_ANCHOR_CHARS:
                continue
            toks = {w.lower() for w in _TOKEN.findall(str(text))}
            if not toks:
                continue
            hit = len(want & toks)
            if hit:
                # Jaccard-ish, not raw overlap: a long string contains more
                # words and would otherwise win every comparison by being long.
                scored.append((hit / len(toks | want), hit, k))
        for _, _, k in sorted(scored, key=lambda s: (-s[0], -s[1], s[2])):
            if len(picked) >= limit:
                break
            take(k)

    # Second cap, on the payload rather than the count: 30 short labels and 30
    # paragraphs are the same number and very different prompts.
    out, budget = [], MAX_ANCHOR_BLOCK_CHARS
    for key, english, shipped in picked[:limit]:
        cost = len(key) + len(english) + len(shipped) + 16
        if cost > budget:
            break
        out.append((key, english, shipped))
        budget -= cost
    return out


def source_block(keys: Sequence[str], en_flat: dict) -> str:
    """The English payload — IDENTICAL across languages, so it caches."""
    return json.dumps({k: en_flat[k] for k in sorted(keys)},
                      indent=1, ensure_ascii=False, sort_keys=True)


def language_name(lang: str) -> str:
    return load(CANONICAL / f"{lang}.json").get("_meta", {}).get("language_name", lang)


def context_block(lang: str, needed: Sequence[str], en_flat: dict) -> str:
    """Glossary + anchors — everything that makes this CIRIS's language."""
    texts = [str(en_flat[k]) for k in needed if k in en_flat]
    parts = [gloss.block(lang, texts)]
    anchors = anchors_for(lang, needed, en_flat)
    if anchors:
        parts.append(
            "\nANCHOR TRANSLATIONS (real shipped strings in this language — match "
            "their register and terminology):\n"
            + "\n".join(f'  {k}: "{e}"  ->  "{t}"' for k, e, t in anchors)
        )
    return "\n".join(p for p in parts if p.strip())


# ─────────────────────────────────────────────────────────────────────────────
# Model calls
# ─────────────────────────────────────────────────────────────────────────────

class Reply:
    def __init__(self, text: str, input_tokens: int, output_tokens: int,
                 cache_read: int = 0) -> None:
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read = cache_read


def _anthropic_call(model: str, system: str, messages: List[dict]) -> Reply:
    import anthropic

    msg = anthropic.Anthropic().messages.create(
        model=model, max_tokens=16000, system=system, messages=messages)
    return Reply(next(b.text for b in msg.content if b.type == "text"),
                 msg.usage.input_tokens, msg.usage.output_tokens,
                 msg.usage.cache_read_input_tokens or 0)


#: Per-model output caps for the OpenRouter path (see the body below).
MAX_OUTPUT_TOKENS = {"openai/gpt-5-pro": 32000}


def _openrouter_call(model: str, system: str, messages: List[dict]) -> Reply:
    """Same request over OpenRouter. Content blocks are flattened — the
    cache_control lever does not survive this path, which is priced in: it buys
    access to every rung of the ladder, including a family Anthropic's SDK
    cannot reach, and the `:batch` slugs still halve it."""
    import urllib.request

    flat = "\n\n".join(part["text"] for m in messages for part in m["content"])
    body = json.dumps({
        "model": model,
        # Reasoning models count their thinking against max_tokens. At 16000 a
        # 35-key repair payload came back with content null (Opus) or with
        # reasoning-only text (gpt-5-pro), so every rung "produced nothing
        # usable" and the whole batch was held at full cost. OpenRouter also
        # pre-authorizes max_tokens x output price before the call, so the
        # most expensive rung is capped lower or it 402s on a low balance.
        "max_tokens": MAX_OUTPUT_TOKENS.get(model, 64000),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": flat}],
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
                 "Content-Type": "application/json",
                 "X-Title": "CIRISClient localization"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        data = json.loads(resp.read())
    if "error" in data:
        raise RuntimeError(f"openrouter: {data['error']}")
    usage = data.get("usage", {})
    return Reply(data["choices"][0]["message"]["content"],
                 usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))


def call_model(model: str, system: str, messages: List[dict], *, batch: bool = False) -> Reply:
    if PROVIDER == "openrouter":
        return _openrouter_call(model + (":batch" if batch else ""), system, messages)
    if batch:
        # The Anthropic path here is the synchronous Messages API. Dropping
        # `batch` on the floor was worse than not supporting it: the request was
        # billed at full price while Spend.report labelled every line
        # "batch -50%", so the run REPORTED a saving it did not take.
        raise SystemExit(
            "[refuse] --mode batch is not implemented on the Anthropic SDK path. "
            "Use OPENROUTER_API_KEY (its :batch slugs halve the same request), or "
            "run --mode fast and pay what the report says you paid."
        )
    return _anthropic_call(model, system, messages)


def parse_json_reply(text: str) -> dict:
    # A provider can return a message with no text at all (content null: a
    # rung that spent its whole token budget on reasoning). Callers already
    # treat ValueError as "unparseable reply" and escalate; an AttributeError
    # here killed a whole run instead.
    if text is None:
        raise ValueError("empty reply (no text content)")
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.index("{"):]
    return json.loads(text[text.index("{"):text.rindex("}") + 1])


class Spend:
    def __init__(self) -> None:
        self.tokens: Dict[str, List[int]] = {}

    def add(self, model: str, reply: Reply) -> None:
        t = self.tokens.setdefault(model, [0, 0, 0])
        t[0] += reply.input_tokens
        t[1] += reply.output_tokens
        t[2] += reply.cache_read

    def report(self, batch: bool = False) -> str:
        lines, total = [], 0.0
        for model, (inp, out, cached) in sorted(self.tokens.items()):
            i_rate, o_rate = PRICE.get(model, (0.0, 0.0))
            cost = (inp * i_rate + out * o_rate) / 1e6
            if batch:
                cost /= 2
            total += cost
            note = " (batch -50%)" if batch else ""
            unknown = "" if model in PRICE else "  [no price on file]"
            lines.append(f"  {model}: {inp:,} in ({cached:,} cache-read) / "
                         f"{out:,} out ~ ${cost:.4f}{note}{unknown}")
        lines.append(f"  total ~ ${total:.4f}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Structural validation (what the gate will check anyway)
# ─────────────────────────────────────────────────────────────────────────────

def structural_problems(keys: Sequence[str], en_flat: dict, got: Dict[str, str]) -> Dict[str, str]:
    """key -> why it is not acceptable. Empty = structurally clean."""
    bad: Dict[str, str] = {}
    for k in keys:
        v = got.get(k)
        if not isinstance(v, str) or not v.strip():
            bad[k] = "missing or empty"
            continue
        want = Counter(guard._PLACEHOLDER.findall(str(en_flat[k])))
        have = Counter(guard._PLACEHOLDER.findall(v))
        if want != have:
            bad[k] = f"placeholders {dict(have)} != source {dict(want)}"
    return bad


# ─────────────────────────────────────────────────────────────────────────────
# Lane 1 — translate, with the escalation ladder
# ─────────────────────────────────────────────────────────────────────────────

def _translate_request(lang: str, keys: Sequence[str], en_flat: dict, src: str,
                       extra: str = "") -> List[dict]:
    return [{
        "role": "user",
        "content": [
            {"type": "text",
             # Requests differ only AFTER this block, so system + source cache
             # across all 28 languages in a run.
             "text": "ENGLISH SOURCE STRINGS (the union for this run; translate "
                     "only the keys listed for your language below):\n" + src,
             "cache_control": {"type": "ephemeral"}},
            {"type": "text",
             "text": f"TARGET LANGUAGE: {lang} ({language_name(lang)})\n\n"
                     + context_block(lang, keys, en_flat)
                     + "\n\nTRANSLATE THESE KEYS:\n"
                     + "\n".join(f"- {k}" for k in keys)
                     + extra},
        ],
    }]


def translate_lane(lang: str, keys: Sequence[str], en_flat: dict, src: str,
                   spend: Spend, *, batch: bool = False, log=print
                   ) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Draft `keys` for `lang`, escalating anything refused or malformed.

    Returns (translations, unresolved). `unresolved` is what the whole ladder
    could not produce — never silently dropped, never filled with English.
    """
    outstanding = list(keys)
    done: Dict[str, str] = {}
    reasons: Dict[str, str] = {}

    for rung, model in enumerate(LADDER):
        if not outstanding:
            break
        extra = ""
        if rung:
            why = "\n".join(f"  {k}: {reasons.get(k, 'no usable output')}" for k in outstanding)
            extra = ("\n\nA PREVIOUS MODEL COULD NOT PRODUCE THESE. Its stated "
                     "reasons:\n" + why + "\n\nYou are the escalation. These strings "
                     "MUST be rendered in the target language — a refusal here "
                     "fails the build rather than shipping English to a speaker "
                     "of this language.")
        try:
            reply = call_model(model, SYSTEM_TRANSLATE,
                               _translate_request(lang, outstanding, en_flat, src, extra),
                               batch=batch and rung == 0)
        except Exception as e:  # noqa: BLE001 — a dead rung must not kill the run
            log(f"[translate] {lang}: rung {rung} ({model}) failed: {e}")
            continue
        spend.add(model, reply)
        try:
            payload = parse_json_reply(reply.text)
        except ValueError as e:
            log(f"[translate] {lang}: rung {rung} unparseable reply ({e})")
            continue

        got = {k: v for k, v in (payload.get("translations") or {}).items()
               if k in outstanding and isinstance(v, str)}
        refused = {k: str(v) for k, v in (payload.get("refusals") or {}).items()
                   if k in outstanding}
        bad = structural_problems(list(got), en_flat, got)
        clean = {k: v for k, v in got.items() if k not in bad}
        done.update(clean)

        reasons = {}
        reasons.update(refused)
        reasons.update(bad)
        outstanding = [k for k in outstanding if k not in done]
        for k in outstanding:
            reasons.setdefault(k, "no output returned for this key")
        if outstanding:
            log(f"[translate] {lang}: rung {rung} ({model}) left {len(outstanding)} "
                f"key(s) — escalating" if rung + 1 < len(LADDER)
                else f"[translate] {lang}: rung {rung} ({model}) left "
                     f"{len(outstanding)} key(s) and the ladder is exhausted")
        else:
            log(f"[translate] {lang}: {len(clean)} key(s) at rung {rung} ({model})")

    return done, {k: reasons.get(k, "unresolved") for k in outstanding}


# ─────────────────────────────────────────────────────────────────────────────
# Lane 2 — evaluate (MQM)
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_lane(lang: str, values: Dict[str, str], en_flat: dict, spend: Spend,
                  *, log=print) -> Dict[str, List[dict]]:
    """key -> MQM error list. A key with an empty list passed review."""
    keys = sorted(values)
    if not keys:
        return {}
    pairs = json.dumps(
        {k: {"source": str(en_flat.get(k, "")), "translation": values[k]} for k in keys},
        indent=1, ensure_ascii=False, sort_keys=True)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text",
             "text": f"TARGET LANGUAGE: {lang} ({language_name(lang)})\n\n"
                     + context_block(lang, keys, en_flat)},
            {"type": "text",
             "text": "REVIEW THESE (source -> translation):\n" + pairs},
        ],
    }]
    # TWO attempts before failing closed. A reply that arrives truncated or
    # malformed is a transport failure, not a verdict — and failing closed on one
    # blocks the whole language, since every key in the batch is then marked
    # unreviewed. `ja` lost all seven keys to a single reply that broke at
    # character 1218. Fail-closed is right; fail-closed on the first hiccup is
    # just brittle.
    raw = None
    last = ""
    for attempt in (1, 2):
        try:
            reply = call_model(REVIEW_MODEL, SYSTEM_REVIEW, messages)
        except Exception as e:  # noqa: BLE001
            last = f"reviewer unreachable: {e}"
            log(f"[evaluate] {lang}: {last} (attempt {attempt}/2)")
            continue
        spend.add(REVIEW_MODEL, reply)
        try:
            raw = parse_json_reply(reply.text)
            break
        except ValueError as e:
            last = f"review reply unparseable: {e}"
            log(f"[evaluate] {lang}: {last} (attempt {attempt}/2)")
    if raw is None:
        log(f"[evaluate] {lang}: no usable review after 2 attempts — treating as UNREVIEWED")
        return {k: [{"category": "accuracy", "severity": "critical", "span": "",
                     "note": f"{last} (2 attempts)", "suggestion": ""}]
                for k in keys}

    out: Dict[str, List[dict]] = {}
    for k in keys:
        errs = raw.get(k)
        # A key the reviewer skipped is NOT a key that passed, and neither is a
        # key it answered with something that is not a list of findings. Both
        # are "no valid review happened"; coercing the second to [] reads as
        # "reviewed and clean", which is the difference between a gate and a
        # formality.
        if not isinstance(errs, list):
            what = "returned no verdict" if errs is None else f"returned a {type(errs).__name__}"
            out[k] = [{"category": "accuracy", "severity": "critical", "span": "",
                       "note": f"no valid review for this key: the reviewer {what}",
                       "suggestion": ""}]
            continue
        out[k] = [e for e in errs if isinstance(e, dict)]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Lane 3 — repair
# ─────────────────────────────────────────────────────────────────────────────

def _repair_once(lang: str, model: str, todo: Sequence[str], values: Dict[str, str],
                 findings: Dict[str, List[dict]], en_flat: dict, spend: Spend,
                 *, log=print) -> Dict[str, str]:
    """One repair attempt, at one rung. Structurally-clean corrections only."""
    payload = json.dumps(
        {k: {"source": str(en_flat.get(k, "")), "current": values.get(k, ""),
             "findings": findings.get(k, [])} for k in todo},
        indent=1, ensure_ascii=False, sort_keys=True)
    messages = [{
        "role": "user",
        "content": [
            {"type": "text",
             "text": f"TARGET LANGUAGE: {lang} ({language_name(lang)})\n\n"
                     + context_block(lang, list(todo), en_flat)},
            {"type": "text", "text": "CORRECT THESE:\n" + payload},
        ],
    }]
    try:
        reply = call_model(model, SYSTEM_REPAIR, messages)
    except Exception as e:  # noqa: BLE001 — a dead rung must not kill the run
        log(f"[repair] {lang}: {model} failed: {e}")
        return {}
    spend.add(model, reply)
    try:
        got = (parse_json_reply(reply.text).get("translations") or {})
    except ValueError as e:
        log(f"[repair] {lang}: {model} unparseable reply ({e})")
        return {}
    got = {k: v for k, v in got.items() if k in todo and isinstance(v, str)}
    bad = structural_problems(list(got), en_flat, got)
    return {k: v for k, v in got.items() if k not in bad}


def repair_until_clean(lang: str, values: Dict[str, str], findings: Dict[str, List[dict]],
                       en_flat: dict, spend: Spend, *, log=print
                       ) -> Tuple[Dict[str, str], Dict[str, List[dict]]]:
    """Repair, RE-REVIEW, and escalate on the review's verdict — not just on a
    malformed reply.

    The first version walked the ladder only when a rung returned junk, so a
    rung that produced structurally-valid but semantically-rejected text ended
    the loop: `outstanding` emptied, the ladder stopped, and the re-review's
    rejection became a build failure with no second attempt. That made the
    expensive rungs unreachable for exactly the case they exist for — the hard
    languages. Run 3 left `am`, `ha`, `my` and `yo` rejected while
    `openai/gpt-5-pro` was never asked, and those are Tier 0 languages, ranked
    first precisely because models are worst at them.

    Escalation is still SPARING: only rejected keys go up, one language at a
    time, and a rung that satisfies the reviewer ends the walk.

    Returns (accepted corrections, findings that survived every rung).
    """
    accepted: Dict[str, str] = {}
    current = dict(values)
    live = dict(findings)
    rungs = list(LADDER[1:]) or list(LADDER)  # repair starts one rung above the drafter
    for rung, model in enumerate(rungs):
        todo = sorted(k for k, errs in live.items() if needs_repair(errs))
        if not todo:
            break
        fixes = _repair_once(lang, model, todo, current, live, en_flat, spend, log=log)
        if not fixes:
            log(f"[repair] {lang}: {model} produced nothing usable for {len(todo)} key(s)")
            continue
        # A repair is a NEW string, and an unreviewed new string is the one thing
        # this pipeline refuses to write. Re-review before believing it.
        verdict = evaluate_lane(lang, fixes, en_flat, spend, log=log)
        good = {k: v for k, v in fixes.items() if not needs_repair(verdict.get(k, []))}
        accepted.update(good)
        current.update(good)
        for k in good:
            live[k] = verdict.get(k, [])
        still = sorted(k for k in fixes if k not in good)
        for k in still:
            live[k] = verdict.get(k, live.get(k, []))
            current[k] = fixes[k]  # carry the better-but-not-clean text upward
        log(f"[repair] {lang}: {len(good)}/{len(todo)} accepted at {model}"
            + (f"; {len(still)} still rejected" if still else ""))
    remaining = {k: e for k, e in live.items() if needs_repair(e)}
    return accepted, remaining


def insert(lang: str, values: Dict[str, str], en: dict, *, overwrite: bool) -> None:
    """Write into all four mirrors at en.json's key positions.

    Position-preserving on purpose: a translated bundle whose keys are in a
    different order from en.json produces a diff nobody can review, and the
    byte-identity check across the four mirrors is what makes the write safe to
    do four times.
    """
    def position_map(obj: dict, prefix: str = "") -> Dict[str, Optional[str]]:
        out: Dict[str, Optional[str]] = {}
        prev: Optional[str] = None
        for k, v in obj.items():
            kk = f"{prefix}.{k}" if prefix else k
            out[kk] = prev
            prev = kk
            if isinstance(v, dict):
                out.update(position_map(v, kk))
        return out

    pred = position_map(en)
    order = list(guard.flat_values(en))
    doc = load(CANONICAL / f"{lang}.json")

    for key in sorted(values, key=lambda k: order.index(k) if k in order else 1 << 30):
        parts = key.split(".")
        node = doc
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        leaf = parts[-1]
        if leaf in node and str(node[leaf]).strip() and not overwrite:
            continue
        if leaf in node:
            node[leaf] = values[key]
            continue
        want_pred = pred.get(key)
        want_leaf = want_pred.split(".")[-1] if want_pred else None
        rebuilt: Dict[str, object] = {}
        placed = False
        if want_leaf and want_leaf in node:
            for k, v in node.items():
                rebuilt[k] = v
                if k == want_leaf:
                    rebuilt[leaf] = values[key]
                    placed = True
        if not placed:
            for k, v in node.items():
                if not placed and k > leaf:
                    rebuilt[leaf] = values[key]
                    placed = True
                rebuilt[k] = v
            if not placed:
                rebuilt[leaf] = values[key]
        node.clear()
        node.update(rebuilt)

    out = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    for bundle in guard.MIRROR_BUNDLES:
        (REPO_ROOT / bundle / f"{lang}.json").write_text(out, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# The pipeline
# ─────────────────────────────────────────────────────────────────────────────

def run(lane: str, patterns: Sequence[str], langs: Sequence[str], *, max_keys: int,
        mode: str, dry_run: bool, report_path: Optional[Path]) -> int:
    global REVIEW_MODEL  # noqa: PLW0603 - resolved once per run; see _review_model
    REVIEW_MODEL = _review_model()

    en_flat, selection = select(patterns, langs, only_missing=(lane == "translate" and not patterns))
    if not selection:
        print("nothing selected — every requested key is already present in every "
              "requested language; no API call made")
        return 0

    total = sum(len(v) for v in selection.values())
    print(f"lane={lane}  {total} key-value(s) across {len(selection)} language(s)")
    print(f"ladder={' -> '.join(LADDER)}   reviewer={REVIEW_MODEL}   provider={PROVIDER}")
    if total > max_keys:
        print(f"[refuse] {total} > --max-keys {max_keys}. A run this large should be "
              f"deliberate: raise --max-keys (and consider --mode batch, 50% cheaper).")
        return 2

    if dry_run:
        union = sorted({k for ks in selection.values() for k in ks})
        src = source_block(union, en_flat)
        approx = sum(len(context_block(l, k, en_flat)) for l, k in selection.items())
        approx = (approx + len(src) * len(selection)) // 4
        print(f"[dry-run] {len(selection)} request(s) in the {lane} lane, "
              f"~{approx:,} input tokens before caching "
              f"(shared prefix ~{len(src)//4:,}); glossary terms and anchors are "
              f"per-language. No call made.")
        for lang, keys in sorted(selection.items()):
            g = len(gloss.relevant(lang, [str(en_flat[k]) for k in keys]))
            print(f"    {lang}: {len(keys)} key(s), {g} glossary term(s) in scope")
        return 0

    # Before the first call, for every language in the selection: a glossary
    # discovered missing on language 19 of 28 means 18 were drafted without one.
    gloss.require(sorted(selection))

    en = load(CANONICAL / "en.json")
    spend = Spend()
    union = sorted({k for ks in selection.values() for k in ks})
    src = source_block(union, en_flat)

    unresolved: Dict[str, Dict[str, str]] = {}
    rejected: Dict[str, Dict[str, str]] = {}
    report: Dict[str, dict] = {}
    rc = 0

    for lang, keys in sorted(selection.items()):
        # ── enter ────────────────────────────────────────────────────────────
        if lane == "translate":
            values, could_not = translate_lane(lang, keys, en_flat, src, spend,
                                               batch=(mode == "batch"))
            if could_not:
                unresolved[lang] = could_not
        else:
            current = guard.flat_values(load(CANONICAL / f"{lang}.json"))
            values = {k: str(current[k]) for k in keys
                      if k in current and str(current[k]).strip()}
            skipped = [k for k in keys if k not in values]
            if skipped:
                print(f"[{lane}] {lang}: {len(skipped)} key(s) have nothing to "
                      f"review yet — run the translate lane for those")

        # ── always: evaluate ─────────────────────────────────────────────────
        findings = evaluate_lane(lang, values, en_flat, spend)
        flagged = {k: e for k, e in findings.items() if e}
        scores = {k: mqm_score(e) for k, e in findings.items()}
        worst = min(scores.values()) if scores else 100
        print(f"[evaluate] {lang}: {len(flagged)}/{len(findings)} key(s) with "
              f"findings, worst MQM score {worst}")

        # ── always: repair. Not conditional — when the review found nothing,
        # `repair_lane` has nothing to correct and makes no call. That is the
        # difference between "the lane ran and was satisfied" and "the lane was
        # skipped", and only the first is a statement about the strings.
        # Repair walks the ladder on the REVIEWER's verdict, re-reviewing after
        # each rung, so a rung that returns well-formed but rejected text is
        # escalated rather than accepted. What survives every rung is what no
        # model this pipeline can reach was able to render acceptably.
        fixes, unrepaired = repair_until_clean(lang, values, findings, en_flat, spend)
        values.update(fixes)
        for k in fixes:
            findings[k] = []
            scores[k] = 100
        for k, errs in unrepaired.items():
            findings[k] = errs
            scores[k] = mqm_score(errs)

        if unrepaired:
            # Rejected text is still rejected text. Writing it and exiting 0
            # would put a semantic defect through a structural gate that cannot
            # see it — which is the entire reason the review lane exists.
            print(f"[repair] {lang}: {len(unrepaired)} key(s) rejected by every rung "
                  f"— {', '.join(sorted(unrepaired)[:5])}"
                  f"{' …' if len(unrepaired) > 5 else ''}")
            rc = 1
            rejected[lang] = {
                k: "; ".join(
                    f"{e.get('severity')}/{e.get('category')}: {e.get('note', '')}"
                    for e in errs if needs_repair([e])
                ) for k, errs in unrepaired.items()
            }

        report[lang] = {
            "keys": len(findings),
            "flagged": len(flagged),
            "repaired": sorted(fixes),
            "worst_score": min(scores.values()) if scores else 100,
            "mean_score": round(sum(scores.values()) / len(scores), 1) if scores else 100.0,
            "findings": {k: e for k, e in findings.items() if e},
            "unresolved": unresolved.get(lang, {}),
            "rejected_unrepaired": rejected.get(lang, {}),
        }

        # BANK THE ACCEPTED WORK, WITHHOLD THE REJECTED.
        #
        # This used to write everything — accepted and rejected alike — and then
        # exit 1, which failed the job before the Commit step and threw the
        # WHOLE RUN away. On a 21-key job across 28 languages that is 588 pairs
        # discarded because one of them came back clumsy, and it happened seven
        # times in a row on one branch: every run failed on a different single
        # pair, so every run binned 587 good translations and cost a full lane to
        # do it.
        #
        # The guarantee is unchanged and is what makes this safe: a rejected
        # value is NOT written, so nothing semantically bad reaches a bundle and
        # English never appears under a non-English locale. The run still exits
        # 1, the key stays missing, and the strict guard still blocks the merge
        # until it is filled. The only thing that changes is that the accepted
        # values survive, so the next run has one key to do instead of 588.
        withheld = set(rejected.get(lang, {})) | set(unrepaired)
        writable = {k: v for k, v in values.items() if k not in withheld}
        if writable:
            insert(lang, writable, en, overwrite=(lane != "translate"))
            print(f"[write] {lang}: {len(writable)} value(s), 4 mirrors"
                  + (f" ({len(withheld)} withheld — rejected)" if withheld else ""))
        elif withheld:
            print(f"[write] {lang}: nothing written — all {len(withheld)} rejected")

    print("\nspend (estimate — billing is what the API bills):")
    print(spend.report(batch=(mode == "batch")))

    if report_path:
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                               encoding="utf-8")
        print(f"\nreport: {report_path}")

    if unresolved:
        print("\n[FAIL-CLOSED] the ladder could not render these, and English is "
              "not an acceptable substitute for a speaker of the language:")
        for lang, keys in sorted(unresolved.items()):
            for k, why in sorted(keys.items()):
                print(f"  {lang}  {k}: {why}")
        rc = 1

    if rejected:
        print("\n[FAIL-CLOSED] the reviewer rejected these and repair did not fix "
              "them. They are written as-is and the run fails: the strict guard "
              "checks structure, and structure is not what is wrong with them.")
        for lang, keys in sorted(rejected.items()):
            for k, why in sorted(keys.items()):
                print(f"  {lang}  {k}: {why}")

    print("\nEvery value written is status=draft / review_status=machine_reviewed. "
          "This pipeline guarantees terminology, structure and meaning; it does not "
          "guarantee native fluency, and nothing it writes may be described as "
          "native quality.\n"
          "There is no native-reviewer pipeline behind this. The label used to say "
          "needs_native_review, which read as a queue someone was working; there is "
          "no queue and no one is working it, and a permanent pending is a worse "
          "claim than an honest limit. What IS true stays true: draft, not native "
          "quality, never marketed as such.")
    return rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--lane", choices=["translate", "evaluate", "repair"], default="translate",
                    help="where the run ENTERS the pipeline; it always flows "
                         "through the lanes after it")
    ap.add_argument("--keys", action="append", default=[], metavar="PATTERN",
                    help="fnmatch over flat dotted keys, repeatable. Without it "
                         "the selection is whatever is missing (diff-driven)")
    ap.add_argument("--lang", action="append", default=[], metavar="CODE",
                    help="restrict to these languages, repeatable (default: all 28)")
    ap.add_argument("--check", action="store_true",
                    help="report missing values and exit (1 if any)")
    ap.add_argument("--mode", choices=["fast", "batch"], default="fast")
    ap.add_argument("--max-keys", type=int, default=400,
                    help="refuse runs larger than this many key-values (default 400)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan and token estimate, no API call")
    ap.add_argument("--report", metavar="PATH", default=None,
                    help="write the MQM findings as JSON")
    ap.add_argument("--glossary-report", action="store_true",
                    help="term counts per language, then exit")
    args = ap.parse_args()

    if args.glossary_report:
        cov = gloss.coverage()
        for code, n in sorted(cov.items()):
            print(f"  {code:>8}: {n:>4} term(s), "
                  f"{len(gloss.guidance(code))} prose section(s)")
        print(f"  total: {sum(cov.values())} pairs across {len(cov)} file(s)")
        return 0

    if args.check:
        _, missing = missing_by_language()
        if not missing:
            print("all languages at parity")
            return 0
        for lang, keys in sorted(missing.items()):
            print(f"{lang}: {len(keys)} missing — {', '.join(keys[:5])}"
                  + (" ..." if len(keys) > 5 else ""))
        return 1

    return run(args.lane, args.keys, args.lang, max_keys=args.max_keys,
               mode=args.mode, dry_run=args.dry_run,
               report_path=Path(args.report) if args.report else None)


if __name__ == "__main__":
    sys.exit(main())
