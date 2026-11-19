"""Synthetic locales for fallback tests: a real locale with one field taken out.

A fallback test ("a locale without the field gets the English one") must not
depend on a shipped locale happening to lack the field: the i18n lane
translates fields, and the test's premise silently goes stale. These helpers
build a temporary copy of the engine's prompt or string tree in which the
requested locale is the real translated one minus the named field, so the
fallback is exercised however far translation has got.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DMA_PROMPTS = REPO_ROOT / "ciris_engine" / "logic" / "dma" / "prompts"
CONSCIENCE_PROMPTS = REPO_ROOT / "ciris_engine" / "logic" / "conscience" / "prompts"
LOCALIZED_STRINGS = REPO_ROOT / "ciris_engine" / "data" / "localized"


def prompts_dir_without_field(source: Path, dest: Path, language: str, field: str) -> Path:
    """Copy ``source`` (a loader's prompts dir) to ``dest`` with ``language``'s templates lacking ``field``.

    The English templates are copied unchanged; every ``localized/<language>/*.yml``
    is the shipped translation with the top-level ``field`` removed. Other
    locales are not copied (they are not under test).
    """
    dest.mkdir(parents=True, exist_ok=True)
    for template in source.glob("*.yml"):
        shutil.copy2(template, dest / template.name)
    src_locale = source / "localized" / language
    dst_locale = dest / "localized" / language
    dst_locale.mkdir(parents=True, exist_ok=True)
    if src_locale.is_dir():
        for template in src_locale.glob("*.yml"):
            data: Dict[str, Any] = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
            data.pop(field, None)
            (dst_locale / template.name).write_text(
                yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
            )
    return dest


def strings_dir_without_keys(dest: Path, language: str, dotted_keys: Iterable[str]) -> Path:
    """Copy ``en.json`` and ``<language>.json`` into ``dest`` with ``dotted_keys`` removed from the latter."""
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LOCALIZED_STRINGS / "en.json", dest / "en.json")
    data: Dict[str, Any] = json.loads((LOCALIZED_STRINGS / f"{language}.json").read_text(encoding="utf-8"))
    for dotted in dotted_keys:
        *parents, leaf = dotted.split(".")
        node: Any = data
        for part in parents:
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            node.pop(leaf, None)
    (dest / f"{language}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return dest


__all__ = [
    "CONSCIENCE_PROMPTS",
    "DMA_PROMPTS",
    "LOCALIZED_STRINGS",
    "prompts_dir_without_field",
    "strings_dir_without_keys",
]
