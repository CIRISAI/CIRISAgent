"""#991 — the formatter labels must actually be READ from the bundle.

The defect, stated plainly: ``ciris_engine/data/localized/*.json`` carried 57
``prompts.formatters.*`` keys, fully translated into all 29 locales — 1,653
human-written strings — and ``ciris_engine/logic/formatters/`` contained
exactly ONE ``get_string`` call. Every label the keys existed to translate was
a hardcoded English twin in Python. So a Spanish agent received

    === System Snapshot ===
    Pending Tasks: 3

inside a prompt whose ACCORD, language guidance and DMA templates were all in
Spanish. Nothing failed; nothing logged; the translated copies simply shadowed
by nobody reading them. 29 translated copies of a label read, to any reviewer,
as proof the label ships — the same illusion #990 found in the prompt YAML.

This is the #991 shape and its inverse property is what this file asserts:

1. **Every bundle key has a reader.** Not "some formatter calls get_string" —
   all 57, checked against the live override scanner, which is the same
   mechanism a research manifest uses to decide a key is reachable.
2. **A non-English locale actually renders translated text.** A reader that
   resolves to English anyway would satisfy (1) and fix nothing.
3. **English is byte-identical.** Every call site passes the current English
   string as ``default=``, and at ``en`` the bundle value IS that string. If
   these two ever diverge, English output moves — which is a production change
   nobody asked for. The 12 goldens in
   ``tests/ciris_engine/logic/dma/test_compose_messages_golden.py`` are the
   end-to-end version of this; this is the per-key version that says WHICH key
   drifted.

Why (3) is a test and not a comment: the temptation when a translator improves
an English label is to edit ``en.json`` alone. That silently rewrites every
English prompt in the system. The bundle is not the place to make that call.
"""

from __future__ import annotations

import ast
import json
import pathlib
from typing import Dict, List, Set, Tuple

import pytest

BUNDLE_DIR = pathlib.Path("ciris_engine/data/localized")
FORMATTER_DIR = pathlib.Path("ciris_engine/logic/formatters")
PREFIX = "prompts.formatters."

#: Formatters whose labels are routed. crisis_resources.py and escalation.py are
#: NOT here: they are wholly inline English and have no bundle keys at all, so
#: they are a different (still open) piece of the same surface, pinned in
#: ``research_overrides.RESIDUE_SITES`` rather than covered here.
WIRED_MODULES = ("system_snapshot.py", "identity.py", "user_profiles.py", "prompt_blocks.py")


def _bundle(lang: str) -> Dict[str, str]:
    data = json.loads((BUNDLE_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    return dict(data["prompts"]["formatters"])


def _locales() -> List[str]:
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    languages = manifest.get("languages", manifest)
    if isinstance(languages, dict):
        return sorted(languages)
    return sorted(languages)


def _call_sites() -> Set[Tuple[str, str]]:
    """(key, english_default) for every literal formatter-label lookup.

    Read out of the AST rather than by import, so a key that is only reachable
    down some rare branch still counts — and so a key passed as a VARIABLE
    (which the override scanner cannot follow either) is invisible here too,
    exactly as it is to a research manifest.
    """
    sites: Set[Tuple[str, str]] = set()
    for module in WIRED_MODULES:
        tree = ast.parse((FORMATTER_DIR / module).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "localizer" or len(node.args) < 2:
                continue
            key, default = node.args[0], node.args[1]
            if (
                isinstance(key, ast.Constant)
                and isinstance(key.value, str)
                and key.value.startswith(PREFIX)
                and isinstance(default, ast.Constant)
                and isinstance(default.value, str)
            ):
                sites.add((key.value, default.value))
    return sites


def test_every_bundle_key_has_a_reader() -> None:
    """The inverse property nothing else asserted: 57 authored, 57 read."""
    declared = {PREFIX + k for k in _bundle("en")}
    read = {key for key, _ in _call_sites()}
    assert declared - read == set(), (
        f"{len(declared - read)} formatter label(s) are translated into 29 locales and read by "
        f"nobody: {sorted(declared - read)}. Every non-English agent receives them in English. "
        f"Wire them with `localizer(\"<key>\", \"<current English>\")`."
    )
    assert read - declared == set(), f"formatter reads a key absent from en.json: {sorted(read - declared)}"


def test_readers_are_visible_to_the_research_override_scanner() -> None:
    """A reader the manifest cannot reach is only half a fix.

    ``scan_reachable_string_keys`` follows LITERAL keys only. Building one by
    joining a prefix would render fine and make all 57 invisible to a research
    manifest again — a silent regression this catches and a render test cannot.
    """
    from ciris_engine.logic.utils.research_overrides import scan_reachable_string_keys

    declared = {PREFIX + k for k in _bundle("en")}
    scanned = set(scan_reachable_string_keys())
    assert declared <= scanned, f"not reachable by a manifest: {sorted(declared - scanned)}"


def test_english_bundle_matches_the_inline_default_byte_for_byte() -> None:
    """The byte-identity contract. At ``en`` the bundle wins over the default,
    so any divergence silently rewrites production English."""
    english = _bundle("en")
    drifted = {
        key: (english[key[len(PREFIX) :]], default)
        for key, default in _call_sites()
        if english.get(key[len(PREFIX) :]) != default
    }
    assert not drifted, (
        f"en.json and the inline default disagree for {sorted(drifted)}: {drifted}. "
        f"At `en` the bundle wins, so this MOVES English prompt output. Change both, "
        f"deliberately, and re-run the #972 goldens."
    )


@pytest.mark.parametrize("lang", [locale for locale in _locales() if locale != "en"])
def test_every_locale_carries_every_key(lang: str) -> None:
    """A missing key falls back to English, which is the defect this closes."""
    missing = sorted(set(_bundle("en")) - set(_bundle(lang)))
    assert not missing, f"{lang}.json is missing formatter labels: {missing}"


@pytest.mark.parametrize("lang", ["es", "ja", "am", "ar"])
def test_a_non_english_locale_actually_renders_translated_text(lang: str, monkeypatch) -> None:
    """End-to-end: the wired formatter emits the locale's words, not English.

    Four locales chosen for coverage of the failure modes: a Latin-script
    romance language, a CJK language, a Tier-0 Ethiopic language (the hardest
    and highest-need case), and an RTL language.
    """
    from ciris_engine.logic.formatters.prompt_blocks import format_parent_task_chain
    from ciris_engine.logic.formatters.system_snapshot import format_system_snapshot
    from ciris_engine.logic.formatters.user_profiles import format_user_profiles
    from ciris_engine.logic.utils.localization import clear_language_cache
    from ciris_engine.schemas.runtime.system_context import SystemSnapshot

    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", lang)
    clear_language_cache()

    bundle = _bundle(lang)
    english = _bundle("en")

    rendered = "\n".join(
        [
            format_system_snapshot(SystemSnapshot(system_counts={"pending_tasks": 3, "total_tasks": 9})),
            format_user_profiles({"u1": {"display_name": "Ada", "interest": "x"}}),
            format_parent_task_chain([{"description": "d", "task_id": "t"}]),
        ]
    )

    for key in ("system_snapshot_header", "pending_tasks", "user_label", "parent_task_chain", "root_task"):
        assert bundle[key] in rendered, f"{lang}: '{key}' did not render as '{bundle[key]}'"
        # And the English twin is gone — a reader that resolved to English
        # anyway would pass the line above whenever a translation happens to
        # contain the English word.
        if english[key] != bundle[key]:
            assert english[key] not in rendered, f"{lang}: still emitting the English '{english[key]}'"
