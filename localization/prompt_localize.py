#!/usr/bin/env python3
"""Translate the DMA prompt templates with the vendored localization pipeline.

AGENT-OWNED adapter (see ``localization/VENDORED.md``). Not vendored.

The agent reads its DMA prompts from
``ciris_engine/logic/dma/prompts/<template>.yml`` in English and from
``.../prompts/localized/<lang>/<template>.yml`` in each of the 28 other locales.
The pipeline (``localize.py``, vendored byte-identical from CIRISClient)
translates a JSON key bundle: ``en.json`` plus one ``<lang>.json``. This module
is the bridge, in the shape ``accord_localize.py`` already has for the Accord:

  stage    every translatable field of every template becomes one key,
           ``<template>.<field>``, in a throwaway bundle directory
  run      ``localize.py``'s own CLI over that bundle -- translate, evaluate
           (MQM, a reviewer of a different model family) or repair -- with the
           provider backoff the other targets use
  write    each value the lane accepted goes back into the locale's YAML, in
           place, and only if it still renders: same placeholders, same doubled
           braces, same JSON field names, same action verbs

**A field left in English counts as missing.** A locale file whose value is
byte-identical to the English source is an untranslated copy, however it got
there, so it is not staged and the translate lane's default selection --
"whatever is missing" -- picks it up. That is how a new template is translated:
commit English copies in the 28 locale folders (``test_localization_completeness``
requires the files to exist), then dispatch the lane.

Three fields are English in every locale on purpose (#974 routed them out of
inline Python, where they were compiled-in English) and are never staged; see
``ENGLISH_BY_DESIGN``.

Read-only unless a real translate or repair lane runs: ``--dry-run``,
``--check``, ``--verify`` and the evaluate lane never write a prompt file.

    python3 localization/prompt_localize.py --check
    python3 localization/prompt_localize.py --lane translate --keys 'rsaspdma.*' --dry-run
    python3 localization/prompt_localize.py --verify
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import string
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:  # PyYAML is not on a bare CI runner. lane_shards imports this module for
    # every target (it only needs template_names), so the import must not fail
    # there; run_lane.sh installs it before a prompts run.
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised on a bare runner only
    yaml = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import lane_backoff  # noqa: E402

PROMPTS_REL = "ciris_engine/logic/dma/prompts"
PROMPTS = REPO_ROOT / PROMPTS_REL
UI_MANIFEST = REPO_ROOT / "ciris_engine" / "data" / "localized" / "manifest.json"

#: Top-level fields that are identifiers or settings, not prose.
NOT_TRANSLATED = frozenset({"component_name", "version", "accord_mode"})

#: Fields that are English in every locale by decision, not by omission. #974
#: moved them out of inline Python literals, where they had always been English
#: for every locale; the chain-localization tests exempt them on the condition
#: that the localized bytes equal the base bytes. Staging them would offer them
#: to the translate lane as "missing" and break that byte-equality.
ENGLISH_BY_DESIGN = frozenset(
    {
        "action_selection_pdma.action_params_defer_guidance",
        "action_selection_pdma.context_integration",
        "dsdma_base.context_integration",
    }
)

#: The marker a hand-committed English copy carries at the top of the file. It
#: is removed when the last English field in that file is translated.
ENGLISH_COPY_MARKER = "# --- English verbatim"

#: The ten handler verbs. A model reading a prompt must be able to echo these.
ACTION_VERBS = (
    "SPEAK",
    "PONDER",
    "DEFER",
    "TOOL",
    "REJECT",
    "OBSERVE",
    "MEMORIZE",
    "RECALL",
    "FORGET",
    "TASK_COMPLETE",
)

_SINGLE_PLACEHOLDER = re.compile(r"(?<!\{)\{([A-Za-z0-9_]+)\}(?!\})")
_JSON_FIELD = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:')
_BACKTICKED = re.compile(r"`([^`\n]+)`")

PROMPT_RULES = """
THESE STRINGS ARE NOT UI LABELS. Each one is a block of an instruction prompt
that the CIRIS agent's own language model reads before it acts. Additional hard
rules for this run, which override anything above about brevity or UI style:
- Translate every sentence in full. Keep the source's line breaks, blank lines,
  indentation, numbering, bullet marks and === HEADING === layout.
- Keep VERBATIM, never translated, transliterated or re-cased: doubled braces
  {{ and }} (literal JSON braces: keep them doubled, same count as the source);
  JSON field names (a quoted word followed by a colon, e.g. "final_action":);
  the action verbs SPEAK, PONDER, DEFER, TOOL, REJECT, OBSERVE, MEMORIZE,
  RECALL, FORGET, TASK_COMPLETE; anything inside `backticks`; node-id prefixes
  such as user/ and channel/; and values the model must output literally.
- DO translate the descriptive prose inside JSON example values, and the labels
  that introduce a placeholder ("Original thought:").
- A heading named in running text (CANDIDATE NODES) and the heading itself must
  be the same words in the translation.
- These are safety instructions. Do not soften, summarize, expand or comment.
"""


# ─────────────────────────────────────────────────────────────────────────────
# The bundle
# ─────────────────────────────────────────────────────────────────────────────


def languages() -> List[str]:
    """Every shipped language code, English first, from the agent's manifest."""
    manifest = json.loads(UI_MANIFEST.read_text(encoding="utf-8"))["languages"]
    codes = (
        list(manifest) if isinstance(manifest, dict) else [x["code"] if isinstance(x, dict) else x for x in manifest]
    )
    return ["en"] + sorted(c for c in codes if c != "en")


def template_names(prompts: Path = PROMPTS) -> List[str]:
    return sorted(p.stem for p in prompts.glob("*.yml"))


def locale_path(prompts: Path, lang: str, template: str) -> Path:
    if lang == "en":
        return prompts / f"{template}.yml"
    return prompts / "localized" / lang / f"{template}.yml"


def read_template(path: Path) -> Dict[str, Any]:
    if yaml is None:
        raise SystemExit("[refuse] prompt_localize.py needs PyYAML: pip install pyyaml")
    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def translatable(template: str, doc: Dict[str, Any]) -> Dict[str, str]:
    """``field -> text`` for the fields of one English template the lane may translate."""
    return {
        field: value
        for field, value in doc.items()
        if isinstance(value, str)
        and value.strip()
        and field not in NOT_TRANSLATED
        and f"{template}.{field}" not in ENGLISH_BY_DESIGN
    }


def english_bundle(prompts: Path = PROMPTS) -> Dict[str, Dict[str, str]]:
    return {t: translatable(t, read_template(locale_path(prompts, "en", t))) for t in template_names(prompts)}


def locale_bundle(lang: str, en: Dict[str, Dict[str, str]], prompts: Path = PROMPTS) -> Dict[str, Dict[str, str]]:
    """What ``lang`` has actually translated. A value equal to the English one is absent."""
    out: Dict[str, Dict[str, str]] = {}
    for template, fields in en.items():
        doc = read_template(locale_path(prompts, lang, template))
        have = {
            f: doc[f]
            for f, english in fields.items()
            if isinstance(doc.get(f), str) and doc[f].strip() and doc[f] != english
        }
        if have:
            out[template] = have
    return out


def build_stage(stage: Path, prompts: Path = PROMPTS) -> Dict[str, Dict[str, str]]:
    """Write the key bundle ``localize.py`` works on. Returns the English bundle."""
    stage.mkdir(parents=True, exist_ok=True)
    en = english_bundle(prompts)
    codes = languages()
    _write_json(stage / "manifest.json", {"languages": codes})
    _write_json(stage / "en.json", en)
    for lang in codes[1:]:
        _write_json(stage / f"{lang}.json", locale_bundle(lang, en, prompts))
    return en


def _write_json(path: Path, doc: Dict[str, Any]) -> None:
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def flat(bundle: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    return {f"{t}.{f}": v for t, fields in bundle.items() for f, v in fields.items()}


# ─────────────────────────────────────────────────────────────────────────────
# What a translated prompt block must still do
# ─────────────────────────────────────────────────────────────────────────────


def _formats(text: str) -> Optional[str]:
    """None if ``str.format`` accepts ``text`` with every named field supplied, else why not."""
    try:
        names = {name for _, name, _, _ in string.Formatter().parse(text) if name}
        text.format(**{n: "x" for n in names})
    except (ValueError, KeyError, IndexError) as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


def _count(text: str, token: str) -> int:
    """Occurrences of a Latin token not embedded in a longer Latin word (MEMORIZE, not MEMORIZED)."""
    return len(re.findall(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text))


def prompt_problems(english: str, value: str) -> List[str]:
    """Why ``value`` may not replace ``english`` in a prompt. Empty = acceptable.

    Every check is a way the agent breaks at runtime rather than a matter of
    taste: a lost placeholder is a hole in the prompt, an undoubled brace is a
    ``KeyError`` at ``.format()``, a translated field name is output the parser
    rejects, a translated verb is an action the dispatcher does not know.
    """
    problems: List[str] = []
    if not value.strip():
        return ["empty"]
    if value == english:
        return ["identical to the English source"]
    want, have = Counter(_SINGLE_PLACEHOLDER.findall(english)), Counter(_SINGLE_PLACEHOLDER.findall(value))
    if want != have:
        problems.append(f"placeholders {dict(have)} != source {dict(want)}")
    for brace in ("{{", "}}"):
        if english.count(brace) != value.count(brace):
            problems.append(f"{brace!r} appears {value.count(brace)}x, source {english.count(brace)}x")
    if _formats(english) is None:
        broken = _formats(value)
        if broken:
            problems.append(f"str.format() fails: {broken}")
    if sorted(set(_JSON_FIELD.findall(english))) != sorted(set(_JSON_FIELD.findall(value))):
        lost = sorted(set(_JSON_FIELD.findall(english)) - set(_JSON_FIELD.findall(value)))
        added = sorted(set(_JSON_FIELD.findall(value)) - set(_JSON_FIELD.findall(english)))
        problems.append(f"JSON field names differ (lost {lost}, added {added})")
    for verb in ACTION_VERBS:
        if _count(value, verb) < _count(english, verb):
            problems.append(f"{verb} appears {_count(value, verb)}x, source {_count(english, verb)}x")
    for span in sorted(set(_BACKTICKED.findall(english))):
        if f"`{span}`" not in value:
            problems.append(f"lost `{span}`")
    return problems


# ─────────────────────────────────────────────────────────────────────────────
# Writing one value into a YAML file, in place
# ─────────────────────────────────────────────────────────────────────────────


def render_scalar(value: str) -> Tuple[str, bool]:
    """``value`` as YAML source for a top-level key: ``(text after "key:", is_block)``.

    A block scalar comes back WITHOUT its final line break; ``set_field`` adds
    the breaks, because how many blank lines follow a clipped or stripped block
    is layout the file already has and the value does not determine.
    """
    body = value.rstrip("\n")
    trailing = len(value) - len(body)
    block_ok = (
        "\n" in value
        and bool(body)
        and trailing <= 1
        and not body.startswith((" ", "\t"))
        and not any(line != line.rstrip() for line in body.split("\n"))
        and not any(ord(c) < 32 and c not in "\n\t" for c in value)
    )
    if not block_ok:
        return " " + json.dumps(value, ensure_ascii=False), False
    chomp = "-" if trailing == 0 else ""
    rendered = "\n".join(("  " + line) if line else "" for line in body.split("\n"))
    return f" |{chomp}\n{rendered}", True


def set_field(text: str, field: str, value: str) -> str:
    """Return YAML ``text`` with top-level ``field`` set to ``value``; everything else byte-identical.

    The value's span comes from the YAML parser's own marks, so comments and
    the other keys are untouched. The result is re-parsed and compared before it
    is returned: a rewrite that changed any other key, or did not round-trip
    this one, raises instead of being written.
    """
    before = yaml.safe_load(text) or {}
    root = yaml.compose(text)
    rendered, is_block = render_scalar(value)
    new_text: Optional[str] = None
    if isinstance(root, yaml.MappingNode):
        for key_node, value_node in root.value:
            if key_node.value == field:
                colon = text.index(":", key_node.end_mark.index)
                end = value_node.end_mark.index
                span = text[colon + 1 : end]
                # A block scalar's span runs through the blank lines after it;
                # a quoted or plain one stops at its last character.
                breaks = span[len(span.rstrip("\n")) :]
                if is_block:
                    rendered += breaks or "\n"
                elif breaks:
                    rendered += breaks
                new_text = text[: colon + 1] + rendered + text[end:]
                break
    if new_text is None:
        new_text = text.rstrip("\n") + f"\n{field}:{rendered}\n"
    after = yaml.safe_load(new_text)
    expected = dict(before)
    expected[field] = value
    if after != expected:
        raise ValueError(f"rewriting {field!r} did not round-trip; the file is left as it was")
    return new_text


def strip_english_marker(text: str) -> str:
    """Drop the leading 'English verbatim' comment block of a hand-committed copy."""
    lines = text.split("\n")
    if not lines or not lines[0].startswith(ENGLISH_COPY_MARKER):
        return text
    i = 0
    while i < len(lines) and lines[i].startswith("# ---"):
        i += 1
    return "\n".join(lines[i:])


def write_back(stage: Path, langs: Sequence[str], prompts: Path = PROMPTS) -> Tuple[List[str], Dict[str, List[str]]]:
    """Copy every newly staged value into its locale YAML.

    Returns ``(written keys as lang:key, {lang:key -> problems})``. A value
    with problems is not written: the field stays English, which the chain
    tests and the next ``--check`` both still report.
    """
    en = english_bundle(prompts)
    written: List[str] = []
    rejected: Dict[str, List[str]] = {}
    for lang in langs:
        staged_path = stage / f"{lang}.json"
        if not staged_path.is_file():
            continue
        staged = json.loads(staged_path.read_text(encoding="utf-8"))
        for template, fields in en.items():
            path = locale_path(prompts, lang, template)
            if not path.is_file():
                if staged.get(template):
                    rejected[f"{lang}:{template}.*"] = [
                        f"localized/{lang}/{template}.yml does not exist; commit an English copy first"
                    ]
                continue
            text = original = path.read_text(encoding="utf-8")
            current = read_template(path)
            for field, english in fields.items():
                value = (staged.get(template) or {}).get(field)
                if not isinstance(value, str) or value == current.get(field):
                    continue
                problems = prompt_problems(english, value)
                if problems:
                    rejected[f"{lang}:{template}.{field}"] = problems
                    continue
                text = set_field(text, field, value)
                written.append(f"{lang}:{template}.{field}")
            if text != original:
                now = yaml.safe_load(text)
                if not any(now.get(f) == english for f, english in fields.items()):
                    text = strip_english_marker(text)
                path.write_text(text, encoding="utf-8")
    return written, rejected


# ─────────────────────────────────────────────────────────────────────────────
# The gate
# ─────────────────────────────────────────────────────────────────────────────


def _committed(path: Path) -> Dict[str, Any]:
    """The template as HEAD has it ({} if untracked or git is unavailable)."""
    import subprocess

    try:
        rel = path.resolve().relative_to(REPO_ROOT).as_posix()
        shown = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "show", f"HEAD:{rel}"], capture_output=True, text=True, check=False
        )
    except (OSError, ValueError):
        return {}
    if shown.returncode != 0:
        return {}
    try:
        doc = yaml.safe_load(shown.stdout)
    except yaml.YAMLError:
        return {}
    return doc if isinstance(doc, dict) else {}


def verify(prompts: Path = PROMPTS, *, changed_only: bool = False) -> Tuple[List[str], List[str]]:
    """Structural problems in the locale prompts: ``(blocking, standing)``.

    Checks what breaks the agent, on every TRANSLATED value: the file parses,
    carries no key the English template lacks, and each value keeps its
    placeholders and ``str.format`` validity. It does not judge whether a field
    is translated at all -- that is ``--check`` and the chain-localization
    tests -- nor how well.

    With ``changed_only`` a finding blocks only when the field's value differs
    from the one committed at HEAD: the lane's gate must refuse what THIS run
    wrote, not fail on debt that was already in the tree and that the run did
    not touch (the same ratchet ``check_localization_integrity --fail-on``
    applies to the UI bundle). The standing findings are still printed.
    """
    blocking: List[str] = []
    standing: List[str] = []
    en = english_bundle(prompts)
    for lang in languages()[1:]:
        for template, fields in en.items():
            path = locale_path(prompts, lang, template)
            name = f"{lang}/{template}"
            if not path.is_file():
                blocking.append(f"{name}.yml: missing")
                continue
            try:
                doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                blocking.append(f"{name}.yml: does not parse ({exc.__class__.__name__})")
                continue
            if not isinstance(doc, dict):
                blocking.append(f"{name}.yml: not a mapping")
                continue
            head = _committed(path) if changed_only else {}

            def file(finding: str, field: Optional[str] = None) -> None:
                untouched = changed_only and (
                    (field is not None and head.get(field) == doc.get(field)) or (field is None and head == doc)
                )
                (standing if untouched else blocking).append(finding)

            english_doc = read_template(locale_path(prompts, "en", template))
            extra = sorted(set(doc) - set(english_doc))
            if extra:
                file(f"{name}.yml: keys the English template lacks: {extra}")
            for field, english in fields.items():
                value = doc.get(field)
                if not isinstance(value, str) or value == english:
                    continue
                want = Counter(_SINGLE_PLACEHOLDER.findall(english))
                have = Counter(_SINGLE_PLACEHOLDER.findall(value))
                if want != have:
                    file(f"{name}.{field}: placeholders {dict(have)} != source {dict(want)}", field)
                elif _formats(english) is None and _formats(value):
                    file(f"{name}.{field}: str.format() fails: {_formats(value)}", field)
    return blocking, standing


# ─────────────────────────────────────────────────────────────────────────────
# Running the vendored lane
# ─────────────────────────────────────────────────────────────────────────────


def import_localize(stage: Path) -> ModuleType:
    """Import the vendored ``localize.py`` against the staged prompt bundle."""
    os.environ["LOCALIZE_TARGET"] = "prompts"
    os.environ["LOCALIZE_PROMPTS_STAGE"] = str(stage.resolve())
    for name in ("localize", "check_localization_sync", "glossary"):
        sys.modules.pop(name, None)
    return importlib.import_module("localize")


def install(L: ModuleType) -> None:
    """Provider backoff, and the rules that make a prompt block not a button label."""
    lane_backoff.install(L)
    for name in ("SYSTEM_TRANSLATE", "SYSTEM_REVIEW", "SYSTEM_REPAIR"):
        setattr(L, name, getattr(L, name) + "\n" + PROMPT_RULES)


def run_localize(L: ModuleType, argv: Sequence[str]) -> int:
    saved = sys.argv
    sys.argv = ["localize.py", *argv]
    try:
        rc: int = L.main()
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            rc = code
        else:
            print(code)
            rc = 1
    finally:
        sys.argv = saved
    return rc


def refuse_batch_mode(argv: Sequence[str]) -> None:
    prev = ""
    for a in argv:
        if a == "--mode=batch" or (prev == "--mode" and a == "batch"):
            raise SystemExit(
                "[refuse] --mode batch: OpenRouter :batch slugs 404 on /chat/completions. Use --mode fast."
            )
        prev = a


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--verify", action="store_true", help="gate the committed locale prompts, then exit")
    ap.add_argument(
        "--changed",
        action="store_true",
        help="with --verify: block only on fields whose value differs from HEAD (the lane's gate)",
    )
    ap.add_argument(
        "--stage", type=Path, default=None, help="bundle directory to keep (default: a temporary one, removed)"
    )
    ap.add_argument("--lane", choices=["translate", "evaluate", "repair"], default="translate")
    ap.add_argument("--lang", action="append", default=[], metavar="CODE")
    ap.add_argument("--check", action="store_true", help="list fields still in English per language, then exit")
    ap.add_argument("--dry-run", action="store_true", help="plan only: no API call, nothing written")
    args, rest = ap.parse_known_args(argv)

    if args.verify:
        blocking, standing = verify(changed_only=args.changed)
        for f in standing:
            print(f"[verify] standing (not written by this run): {f}")
        for f in blocking:
            print(f"[verify] {f}")
        where = f"{PROMPTS_REL}/localized"
        print(f"[verify] {'FAIL' if blocking else 'OK'}: {len(blocking)} blocking, {len(standing)} standing in {where}")
        return 1 if blocking else 0

    refuse_batch_mode(rest)
    with tempfile.TemporaryDirectory(prefix="ciris-prompt-stage-") as tmp:
        stage = args.stage or Path(tmp)
        build_stage(stage)
        L = import_localize(stage)
        install(L)

        passed = ["--lane", args.lane, *rest]
        for lang in args.lang:
            passed += ["--lang", lang]
        if args.check:
            passed.append("--check")
        if args.dry_run:
            passed.append("--dry-run")
        rc = run_localize(L, passed)

        read_only = args.check or args.dry_run or args.lane == "evaluate"
        if read_only:
            return rc
        langs = args.lang or languages()[1:]
        written, rejected = write_back(stage, langs)
        print(f"[prompts] wrote {len(written)} field(s) into {PROMPTS_REL}/localized")
        for key, problems in sorted(rejected.items()):
            print(f"[prompts] NOT written {key}: {'; '.join(problems)}")
        if rejected:
            print(
                f"[prompts] {len(rejected)} field(s) rejected and left in English; they stay 'missing' for the next run"
            )
            return rc or 1
        return rc


if __name__ == "__main__":
    sys.exit(main())
