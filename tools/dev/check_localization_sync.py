#!/usr/bin/env python3
"""Guard the localization bundles against the two failure modes that have
actually shipped to production.

This replaces the old key-parity-only checker, which could not find the bug
that motivated it: when a key is dropped from *every* locale including
``en.json``, cross-locale parity still "passes" at the wrong baseline while the
UI renders the raw key (e.g. ``mobile.login_owner_hint`` shipping literally on
the Android/iOS login screen in 2.9.4/2.9.5 — CIRISAgent#240).

Three checks, two severities:

  ERROR (exit 1 — blocks commit/CI):
    1. Reference coverage. Every string-literal key passed to
       ``localizedString("…")`` / ``getString("…")`` in commonMain Kotlin MUST
       resolve in ``en.json`` (the universal fallback). A referenced-but-undefined
       key renders raw on EVERY platform. THIS is the regression guard.
    2. Mirror parity. The tracked ``en.json`` source mirrors (one per platform
       bundle) MUST carry identical flattened key sets, so a key cannot be added
       to one platform's bundle and silently dropped from another.

  WARNING (exit 0 by default; exit 1 only under --strict):
    3. Cross-language parity. Within the primary bundle, each locale file should
       carry the same keys as ``en.json``. Missing translations degrade
       gracefully (fallback to English), so this informs rather than blocks.

The supported-language list is read from the bundle ``manifest.json`` (the
source of truth per CLAUDE.md), never hardcoded.

Usage:
    python tools/dev/check_localization_sync.py            # ERRORs block, warnings print
    python tools/dev/check_localization_sync.py --strict   # warnings also block

Exit codes:
    0 - no errors (and no warnings under --strict)
    1 - reference/mirror error (or any warning under --strict)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# The tracked, kept-in-sync UI string bundles that back the Kotlin
# ``localizedString``/``getString`` runtime path — one per platform packaging
# location. All must carry the same en.json key set. (The partial iOS-bundled
# python copy under iosApp/Resources/app/ciris_engine is intentionally excluded:
# it mirrors the server-side data/localized subset, not the UI bundle.)
UI_MIRRORS: Tuple[str, ...] = (
    "ciris_engine/data/localized",
    "apps/android/src/main/assets/localization",
    "apps/ios/iosApp/localization",
    "apps/ios/Resources/app/localization",
)

# Primary bundle used for cross-language parity reporting + manifest read.
PRIMARY_BUNDLE = "apps/android/src/main/assets/localization"

# Kotlin source set whose literal string keys must resolve against en.json.

# localizedString("key" …) / getString("key" …) — capture the literal first arg.
# ``[^"$]`` rejects interpolated keys ("mobile.foo_${x}") which can't be checked
# statically; those are skipped, not failed.
_KEY_CALL = re.compile(r'(?:localizedString|getString)\(\s*"([^"$\\]+)"')


# Per-file bookkeeping subtree (translator, review_status, native_name, …) —
# legitimately varies between locales and is never a UI key, so it's excluded
# from every key-set comparison.
_IGNORED_ROOTS = ("_meta",)


def flatten(obj: dict, prefix: str = "") -> Set[str]:
    """Flatten a nested localization dict to dotted leaf keys (excluding _meta)."""
    out: Set[str] = set()
    for k, v in obj.items():
        if prefix == "" and k in _IGNORED_ROOTS:
            continue
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out |= flatten(v, key)
        else:
            out.add(key)
    return out


def load_flat(path: Path) -> Set[str]:
    return flatten(json.load(open(path, encoding="utf-8")))


# ``prompts.language_guidance`` is DUAL-SHAPED since #997: an ordered dict of
# single-class parts in the five locales whose prose partitions on the English
# boundaries, the original single scalar in the other 24. Both compose the same
# block — the split changes what a research ablation can address, not what the
# model receives — so for CROSS-LANGUAGE parity the two shapes are the same key.
#
# Only the cross-language WARNING collapses them. Mirror parity (an ERROR) keeps
# comparing exact keys, because a mirror carrying a different shape from its
# source really is a bug.
_LANGUAGE_GUIDANCE = "prompts.language_guidance"


def collapse_dual_shaped(keys: Set[str]) -> Set[str]:
    """Fold ``prompts.language_guidance.<part>`` back onto its parent key."""
    prefix = f"{_LANGUAGE_GUIDANCE}."
    folded = {k for k in keys if not k.startswith(prefix)}
    if len(folded) != len(keys):
        folded.add(_LANGUAGE_GUIDANCE)
    return folded


def manifest_languages(bundle: Path) -> List[str]:
    """Read the supported-language list from the bundle manifest (source of truth)."""
    manifest = json.load(open(bundle / "manifest.json", encoding="utf-8"))
    langs = manifest.get("languages")
    if isinstance(langs, dict):
        return list(langs.keys())
    if isinstance(langs, list):
        return [x.get("code") if isinstance(x, dict) else x for x in langs]
    raise SystemExit("❌ ERROR: could not read 'languages' from manifest.json")


# REFERENCE COVERAGE MOVED UPSTREAM
#
# `referenced_keys()` / `check_reference_coverage()` scanned commonMain Kotlin for
# `getString("some.key")` literals and asserted each resolves in en.json — the
# guard against a key rendering RAW on every platform.
#
# That source is built by CIRISAI/CIRISClient now. The functions were REMOVED
# rather than pointed at an empty directory: a scan with nothing to scan reports
# zero unresolved keys and passes, which is indistinguishable from a clean tree.
#
# THE COVERAGE IS GONE FROM THIS REPO. Nothing here catches a getString() typo;
# that check belongs beside the code it guards. What remains below is what this
# repo still owns — mirror parity and cross-language lag over the bundles the
# app shells actually ship.


def check_mirror_parity() -> List[str]:
    """ERROR: all UI en.json mirrors must carry identical key sets."""
    errors: List[str] = []
    baseline: Set[str] = set()
    baseline_name = ""
    mirror_keys: Dict[str, Set[str]] = {}
    for m in UI_MIRRORS:
        f = REPO_ROOT / m / "en.json"
        if not f.exists():
            errors.append(f"missing en.json mirror: {m}")
            continue
        mirror_keys[m] = load_flat(f)
    if not mirror_keys:
        return ["no en.json mirrors found"]
    # Use the largest mirror as baseline so a drop anywhere is reported.
    baseline_name = max(mirror_keys, key=lambda k: len(mirror_keys[k]))
    baseline = mirror_keys[baseline_name]
    for m, keys in mirror_keys.items():
        if m == baseline_name:
            continue
        missing = baseline - keys
        extra = keys - baseline
        if missing or extra:
            errors.append(
                f"{m}/en.json diverges from {baseline_name}/en.json: " f"missing={len(missing)} extra={len(extra)}"
            )
            for k in sorted(missing)[:8]:
                errors.append(f"    - missing: {k}")
            for k in sorted(extra)[:8]:
                errors.append(f"    + extra:   {k}")
    return errors


def check_cross_language(bundle: Path, langs: List[str], en_keys: Set[str]) -> List[str]:
    """WARNING: each locale file should match en.json's key set."""
    warnings: List[str] = []
    en_keys = collapse_dual_shaped(en_keys)
    for lang in langs:
        if lang == "en":
            continue
        f = bundle / f"{lang}.json"
        if not f.exists():
            warnings.append(f"{lang}.json missing from {bundle.name} bundle")
            continue
        keys = collapse_dual_shaped(load_flat(f))
        missing = en_keys - keys
        extra = keys - en_keys
        if missing or extra:
            detail = []
            if missing:
                detail.append(f"missing {len(missing)} ({', '.join(sorted(missing)[:3])}…)")
            if extra:
                detail.append(f"extra {len(extra)} ({', '.join(sorted(extra)[:3])}…)")
            warnings.append(f"{lang}.json: {'; '.join(detail)}")
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Localization bundle guard")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="treat cross-language drift (untranslated keys) as a failure too",
    )
    args = ap.parse_args()

    bundle = REPO_ROOT / PRIMARY_BUNDLE
    if not (bundle / "en.json").exists():
        print(f"[FAIL] ERROR: primary bundle en.json not found at {PRIMARY_BUNDLE}")
        return 1

    langs = manifest_languages(bundle)
    en_keys = load_flat(bundle / "en.json")

    print(" Localization guard")
    print(f"   bundle: {PRIMARY_BUNDLE}  ({len(en_keys)} keys, {len(langs)} languages)")
    print()

    errors: List[str] = []
    errors += check_mirror_parity()

    warnings = check_cross_language(bundle, langs, en_keys)

    if errors:
        print("[FAIL] ERRORS (block):")
        for e in errors:
            print(f"  {e}" if e.startswith("    ") else f"  • {e}")
        print()
    else:
        print("[OK] mirror parity OK (reference coverage now lives upstream with the Kotlin)")
        print()

    if warnings:
        sev = "❌ ERRORS (--strict)" if args.strict else "⚠️  WARNINGS (translation drift — fallback to English)"
        print(sev + ":")
        for w in warnings:
            print(f"  • {w}")
        print()
    else:
        print("[OK] all locales at key parity")
        print()

    failed = bool(errors) or (args.strict and bool(warnings))
    if failed:
        print("[FAIL] localization check failed")
        if errors:
            print("   Fix: add the undefined key(s) to en.json across ALL mirrors:")
            for m in UI_MIRRORS:
                print(f"     {m}/en.json")
        return 1

    print("[OK] localization check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
