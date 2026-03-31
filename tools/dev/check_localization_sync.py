#!/usr/bin/env python3
"""
Pre-commit hook to ensure all localization files stay in sync.

Checks:
1. All language files have the same keys as en.json
2. Reports missing keys that need translation
3. Reports extra keys that should be removed
4. BLOCKS commit if any language file is out of sync

Usage:
    python tools/dev/check_localization_sync.py

Exit codes:
    0 - All files in sync
    1 - Files out of sync (commit blocked)
"""

import json
import sys
from pathlib import Path
from typing import Dict, Set


# Supported languages (excluding manifest.json)
SUPPORTED_LANGUAGES = [
    "am", "ar", "de", "en", "es", "fr", "hi", "it",
    "ja", "ko", "pt", "ru", "sw", "tr", "ur", "zh"
]


def load_language_keys(localization_dir: Path) -> Dict[str, Set[str]]:
    """Load all keys from each language file."""
    lang_keys: Dict[str, Set[str]] = {}

    for lang in SUPPORTED_LANGUAGES:
        filepath = localization_dir / f"{lang}.json"
        if filepath.exists():
            try:
                with open(filepath, encoding="utf-8") as f:
                    data = json.load(f)
                    lang_keys[lang] = set(data.keys())
            except json.JSONDecodeError as e:
                print(f"❌ ERROR: Invalid JSON in {lang}.json: {e}")
                sys.exit(1)
        else:
            print(f"⚠️  WARNING: Missing language file: {lang}.json")
            lang_keys[lang] = set()

    return lang_keys


def check_localization_sync() -> bool:
    """
    Check that all language files have the same keys as en.json.

    Returns:
        True if all files are in sync, False otherwise.
    """
    localization_dir = Path("localization")

    if not localization_dir.exists():
        print("❌ ERROR: localization/ directory not found")
        return False

    lang_keys = load_language_keys(localization_dir)

    if "en" not in lang_keys or not lang_keys["en"]:
        print("❌ ERROR: en.json not found or empty")
        return False

    en_keys = lang_keys["en"]
    print(f"📋 English (en.json): {len(en_keys)} keys")
    print()

    all_synced = True
    missing_report: Dict[str, Set[str]] = {}
    extra_report: Dict[str, Set[str]] = {}

    for lang in SUPPORTED_LANGUAGES:
        if lang == "en":
            continue

        keys = lang_keys.get(lang, set())
        missing = en_keys - keys
        extra = keys - en_keys

        if missing:
            missing_report[lang] = missing
            all_synced = False

        if extra:
            extra_report[lang] = extra
            all_synced = False

    if all_synced:
        print("✅ All localization files are in sync!")
        return True

    # Report issues
    print("=" * 60)
    print("❌ LOCALIZATION FILES OUT OF SYNC")
    print("=" * 60)
    print()

    if missing_report:
        print("🔴 MISSING TRANSLATIONS (keys in en.json but missing in other files):")
        print("-" * 60)
        for lang, keys in sorted(missing_report.items()):
            print(f"\n  {lang}.json ({len(keys)} missing):")
            for key in sorted(keys)[:10]:  # Show first 10
                print(f"    - {key}")
            if len(keys) > 10:
                print(f"    ... and {len(keys) - 10} more")
        print()

    if extra_report:
        print("🟡 EXTRA KEYS (keys in other files but not in en.json):")
        print("-" * 60)
        for lang, keys in sorted(extra_report.items()):
            print(f"\n  {lang}.json ({len(keys)} extra):")
            for key in sorted(keys)[:10]:  # Show first 10
                print(f"    - {key}")
            if len(keys) > 10:
                print(f"    ... and {len(keys) - 10} more")
        print()

    print("=" * 60)
    print("💡 To fix this:")
    print("   1. Add missing translations to the language files")
    print("   2. Or remove extra keys that are no longer needed")
    print("   3. Use: python tools/dev/check_localization_sync.py")
    print("=" * 60)

    return False


def main() -> int:
    """Main entry point."""
    print()
    print("🌍 Checking localization file synchronization...")
    print()

    if check_localization_sync():
        return 0
    else:
        print()
        print("❌ COMMIT BLOCKED: Localization files are out of sync")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
