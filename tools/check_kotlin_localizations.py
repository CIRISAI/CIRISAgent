#!/usr/bin/env python3
"""Check that all localization keys used in Kotlin code exist in JSON files.

This tool scans Kotlin source files for localization key references and validates
they exist in the localization JSON files.

Usage:
    python -m tools.check_kotlin_localizations [--fix]
"""

import json
import re
import sys
from pathlib import Path

# Patterns to find localization key usage in Kotlin
PATTERNS = [
    # localizedString("key") or localizedString("key", ...)
    r'localizedString\s*\(\s*"([^"]+)"',
    # LocalizationHelper.getString("key") or getString("key", ...)
    r'getString\s*\(\s*"([^"]+)"',
    # Direct string literals that look like keys (mobile.*, setup.*, etc.)
    r'"(mobile\.[a-z_]+)"',
    r'"(setup\.[a-z_]+)"',
    r'"(interact\.[a-z_]+)"',
    r'"(settings\.[a-z_]+)"',
    r'"(common\.[a-z_]+)"',
    r'"(prefs\.[a-z_]+)"',
    r'"(memory_[a-z_]+)"',
]

KOTLIN_DIRS = [
    "client/shared/src/commonMain/kotlin",
    "client/shared/src/androidMain/kotlin",
    "client/shared/src/desktopMain/kotlin",
]

LOCALIZATION_FILES = [
    "localization/en.json",
    "client/androidApp/src/main/assets/localization/en.json",
    "client/shared/src/desktopMain/resources/localization/en.json",
]


def get_nested_value(obj: dict, key: str):
    """Get a nested value from a dict using dot notation."""
    parts = key.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def load_localization_keys(file_path: Path) -> set[str]:
    """Load all keys from a localization JSON file using dot notation."""
    keys = set()

    def extract_keys(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    extract_keys(v, new_key)
                else:
                    keys.add(new_key)

    try:
        with open(file_path) as f:
            data = json.load(f)
        extract_keys(data)
    except Exception as e:
        print(f"Warning: Could not load {file_path}: {e}")

    return keys


def find_kotlin_keys(kotlin_dir: Path) -> dict[str, list[tuple[Path, int]]]:
    """Find all localization keys used in Kotlin files.

    Returns:
        Dict mapping key -> list of (file, line_number) tuples
    """
    keys: dict[str, list[tuple[Path, int]]] = {}

    for kt_file in kotlin_dir.rglob("*.kt"):
        try:
            content = kt_file.read_text()
            lines = content.split("\n")

            for line_num, line in enumerate(lines, 1):
                for pattern in PATTERNS:
                    for match in re.finditer(pattern, line):
                        key = match.group(1)
                        if key not in keys:
                            keys[key] = []
                        keys[key].append((kt_file, line_num))
        except Exception as e:
            print(f"Warning: Could not read {kt_file}: {e}")

    return keys


def main():
    root = Path(__file__).parent.parent

    # Load all localization keys from en.json (as reference)
    all_loc_keys: set[str] = set()
    for loc_file in LOCALIZATION_FILES:
        loc_path = root / loc_file
        if loc_path.exists():
            all_loc_keys.update(load_localization_keys(loc_path))
            print(f"Loaded {len(load_localization_keys(loc_path))} keys from {loc_file}")

    print(f"\nTotal unique localization keys: {len(all_loc_keys)}")

    # Find all keys used in Kotlin code
    all_kotlin_keys: dict[str, list[tuple[Path, int]]] = {}
    for kotlin_dir in KOTLIN_DIRS:
        kotlin_path = root / kotlin_dir
        if kotlin_path.exists():
            dir_keys = find_kotlin_keys(kotlin_path)
            for key, locations in dir_keys.items():
                if key not in all_kotlin_keys:
                    all_kotlin_keys[key] = []
                all_kotlin_keys[key].extend(locations)

    print(f"Found {len(all_kotlin_keys)} unique keys in Kotlin code")

    # Find missing keys
    missing_keys: dict[str, list[tuple[Path, int]]] = {}
    for key, locations in all_kotlin_keys.items():
        if key not in all_loc_keys:
            missing_keys[key] = locations

    if missing_keys:
        print(f"\n❌ MISSING KEYS ({len(missing_keys)}):")
        print("=" * 60)
        for key in sorted(missing_keys.keys()):
            locations = missing_keys[key]
            print(f'\n  "{key}"')
            for file_path, line_num in locations[:3]:  # Show first 3 locations
                rel_path = file_path.relative_to(root)
                print(f"    └─ {rel_path}:{line_num}")
            if len(locations) > 3:
                print(f"    └─ ... and {len(locations) - 3} more locations")

        # Generate JSON snippet for easy copy-paste
        print("\n" + "=" * 60)
        print("JSON snippet to add to localization files:")
        print("=" * 60)

        # Group by prefix
        prefixes: dict[str, list[str]] = {}
        for key in sorted(missing_keys.keys()):
            parts = key.split(".")
            if len(parts) >= 2:
                prefix = parts[0]
                suffix = ".".join(parts[1:])
                if prefix not in prefixes:
                    prefixes[prefix] = []
                prefixes[prefix].append(suffix)
            else:
                if "" not in prefixes:
                    prefixes[""] = []
                prefixes[""].append(key)

        for prefix, suffixes in sorted(prefixes.items()):
            if prefix:
                print(f'\n  "{prefix}": {{')
                for suffix in sorted(suffixes):
                    # Generate a readable placeholder
                    readable = suffix.replace("_", " ").title()
                    print(f'    "{suffix}": "[EN] {readable}",')
                print("  },")
            else:
                for key in sorted(suffixes):
                    readable = key.replace("_", " ").title()
                    print(f'  "{key}": "[EN] {readable}",')

        return 1
    else:
        print("\n✅ All Kotlin localization keys exist in JSON files!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
