#!/usr/bin/env python3
"""Generate Burmese (my) and Thai (th) localization JSON files."""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent


def load_glossary(lang_code: str) -> dict[str, str]:
    """Load glossary and extract English -> Target mappings."""
    glossary_path = BASE_DIR / f"docs/localization/glossaries/{lang_code}_glossary.md"
    mappings = {}

    with open(glossary_path, "r", encoding="utf-8") as f:
        for line in f:
            if "|" in line and "---" not in line:
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 3 and parts[1] and parts[2]:
                    eng = parts[1].strip()
                    target = parts[2].strip()
                    if eng and target and eng != "English" and target != "Burmese" and target != "Thai":
                        mappings[eng] = target
    return mappings


def translate_value(value: str, mappings: dict[str, str]) -> str:
    """Apply glossary mappings to a string."""
    result = value
    # Sort by length descending to match longer phrases first
    for eng, target in sorted(mappings.items(), key=lambda x: -len(x[0])):
        # Case-insensitive word boundary replacement
        pattern = re.compile(re.escape(eng), re.IGNORECASE)
        result = pattern.sub(target, result)
    return result


def translate_recursive(obj, mappings: dict[str, str]):
    """Recursively translate all string values."""
    if isinstance(obj, dict):
        return {k: translate_recursive(v, mappings) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [translate_recursive(item, mappings) for item in obj]
    elif isinstance(obj, str):
        return translate_value(obj, mappings)
    return obj


def generate_localization(lang_code: str, lang_name: str):
    """Generate a complete localization JSON file."""
    # Load English source
    en_path = BASE_DIR / "ciris_engine/data/localized/en.json"
    with open(en_path, "r", encoding="utf-8") as f:
        en = json.load(f)

    # Load glossary mappings
    mappings = load_glossary(lang_code)
    print(f"Loaded {len(mappings)} glossary mappings for {lang_code}")

    # Translate
    translated = translate_recursive(en, mappings)

    # Set metadata
    translated["_meta"] = {"language": lang_code, "language_name": lang_name, "direction": "ltr"}

    # Write output
    out_path = BASE_DIR / f"localization/{lang_code}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(translated, f, ensure_ascii=False, indent=2)

    print(f"Written {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    # Generate Burmese
    generate_localization("my", "မြန်မာ")

    # Generate Thai
    generate_localization("th", "ไทย")

    print("\nDone! Files created:")
    print("  - localization/my.json")
    print("  - localization/th.json")
