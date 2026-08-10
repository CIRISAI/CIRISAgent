#!/usr/bin/env python3
"""Structural audit for the fanned-out msaspdma.yml translations.

Structural validation is necessary and NOT sufficient. A prior fan-out passed a
prefix-check and still shipped word-salad in 5 of 28 locales, because the check
only proved the shape survived, not that the prose meant anything. So this
reports the mechanical facts and prints what a human (or a native-reading pass)
has to look at — it does not pronounce a locale good.

Checks, in the order a break would bite:

1. FILE EXISTS. `test_localization_completeness` fails without it.
2. YAML PARSES.
3. KEYS ARE THE ENGLISH ONES, all present, none extra. A translated key is
   invisible to `get_prompt` and the block silently disappears from the prompt.
4. PLACEHOLDERS SURVIVE VERBATIM. A dropped `{proposed_node_id}` renders a
   prompt with a hole in it; a translated one raises KeyError at .format().
5. JSON BRACES STAY DOUBLED in `response_format` — the #1 recurring bug in this
   work, per localization/CLAUDE.md.
6. CODE IDENTIFIERS SURVIVE — `user/`, `MEMORIZE`, `memorized_attributes` and
   friends are what the agent must literally emit; translating them makes the
   guidance wrong in a way that reads fine.
7. THE CLASS PARTITION HOLDS — prohibitions belong in `memory_prohibitions`.
   English-language "do not" cannot be detected across 28 languages, so this
   only checks that the prohibitions block is non-trivially sized relative to
   the source, i.e. that it was translated rather than emptied.
8. LENGTH SANITY — a block far shorter than English usually means content was
   dropped; far longer usually means the model narrated instead of translating.

Usage:  python3 -m tools.dev.check_msaspdma_localization
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ciris_engine/logic/dma/prompts/msaspdma.yml"
LOCALIZED = ROOT / "ciris_engine/logic/dma/prompts/localized"

PLACEHOLDERS = [
    "{original_thought_content}",
    "{aspdma_reasoning}",
    "{proposed_node_id}",
    "{proposed_node_type}",
    "{proposed_node_scope}",
    "{proposed_attributes}",
    "{candidate_nodes}",
    "{system_owned_attributes}",
]

# Literal syntax and enum values the agent must reproduce exactly.
CODE_TOKENS = ["user/", "channel/", "MEMORIZE", "SPEAK", "PONDER", "memorized_attributes", "DREAM"]

# JSON field names inside response_format.
JSON_FIELDS = ["final_action", "node_id", "node_type", "node_scope", "attributes", "reasoning"]


def _load(path: Path) -> Tuple[dict | None, str]:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")), ""
    except Exception as exc:  # noqa: BLE001
        return None, f"{type(exc).__name__}: {exc}"


def audit(code: str, src: dict) -> List[str]:
    path = LOCALIZED / code / "msaspdma.yml"
    if not path.exists():
        return ["MISSING FILE"]

    doc, err = _load(path)
    if doc is None:
        return [f"YAML DOES NOT PARSE — {err}"]

    problems: List[str] = []

    src_keys = set(src) - {"description"}
    got_keys = set(doc)
    missing = src_keys - got_keys
    extra = got_keys - set(src)
    if missing:
        problems.append(f"missing keys (block vanishes from the prompt): {sorted(missing)}")
    if extra:
        problems.append(f"unexpected keys (probably translated key names): {sorted(extra)}")

    if doc.get("component_name") != "msaspdma":
        problems.append(f"component_name must stay 'msaspdma', got {doc.get('component_name')!r}")

    ctx = str(doc.get("context_integration") or "")
    lost = [p for p in PLACEHOLDERS if p not in ctx]
    if lost:
        problems.append(f"placeholders lost or translated: {lost}")

    rf = str(doc.get("response_format") or "")
    if "{{" not in rf or "}}" not in rf:
        problems.append("response_format lost its {{ }} escaping — .format() will raise")
    for field in JSON_FIELDS:
        if f'"{field}"' not in rf:
            problems.append(f"response_format JSON field {field!r} was translated or dropped")
            break

    body = "\n".join(str(v) for v in doc.values() if isinstance(v, str))
    for token in CODE_TOKENS:
        if token not in body:
            problems.append(f"code identifier {token!r} missing — likely translated as prose")

    for key in ("memory_model", "addressing_convention", "memory_prohibitions", "evaluation_steps"):
        s, g = str(src.get(key) or ""), str(doc.get(key) or "")
        if not g.strip():
            problems.append(f"{key} is empty")
            continue
        ratio = len(g) / max(len(s), 1)
        # CJK writes the same content in far fewer characters, so one floor for
        # all 28 locales flags dense scripts that lost nothing. Observed on this
        # prompt: zh rendered every sentence of the source at 39-42% of English
        # length while ja/ko sat at 57-61%. Give the logographic scripts their
        # own floor rather than reporting a translation that is complete.
        floor = 0.30 if code in {"zh", "ja", "ko"} else 0.45
        if ratio < floor:
            problems.append(f"{key} is {ratio:.0%} of English length — content likely dropped")
        elif ratio > 2.6:
            problems.append(f"{key} is {ratio:.0%} of English length — likely narrated, not translated")

    return problems


def main() -> int:
    src, err = _load(SOURCE)
    if src is None:
        print(f"source prompt does not parse: {err}")
        return 2

    codes = sorted(p.name for p in LOCALIZED.iterdir() if p.is_dir())
    results: Dict[str, List[str]] = {c: audit(c, src) for c in codes}

    clean = [c for c, p in results.items() if not p]
    dirty = {c: p for c, p in results.items() if p}

    print(f"msaspdma.yml across {len(codes)} locales: {len(clean)} structurally clean, {len(dirty)} with findings\n")
    for code in sorted(dirty):
        print(f"  {code}:")
        for problem in dirty[code]:
            print(f"      - {problem}")
    if clean:
        print(f"\n  structurally clean: {' '.join(clean)}")

    print(
        "\nSTRUCTURE ONLY. This proves the shape survived, not that the prose reads\n"
        "natively — a previous fan-out passed a check like this and still shipped\n"
        "word-salad in 5 of 28 locales. A native-language read is still required."
    )
    return 1 if dirty else 0


if __name__ == "__main__":
    raise SystemExit(main())
