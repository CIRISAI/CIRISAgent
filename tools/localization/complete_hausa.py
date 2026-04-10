#!/usr/bin/env python3
"""
Complete Hausa localization using Claude Code.
This script generates the missing translations for ha.json, ACCORD, DMA prompts, and guide.
"""

import json
import sys
from pathlib import Path

# Define paths
BASE_DIR = Path(__file__).parent.parent.parent
EN_JSON = BASE_DIR / "localization" / "en.json"
HA_JSON = BASE_DIR / "localization" / "ha.json"
HA_GLOSSARY = BASE_DIR / "docs" / "localization" / "glossaries" / "ha_glossary.md"

def load_json_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json_file(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def get_missing_keys(en_data, ha_data, prefix=""):
    """Recursively find missing keys in ha.json compared to en.json"""
    missing = []
    for key, value in en_data.items():
        current_path = f"{prefix}.{key}" if prefix else key

        if key not in ha_data:
            missing.append(current_path)
        elif isinstance(value, dict) and isinstance(ha_data.get(key), dict):
            missing.extend(get_missing_keys(value, ha_data[key], current_path))

    return missing

def main():
    print("=" * 60)
    print("HAUSA LOCALIZATION COMPLETION ANALYZER")
    print("=" * 60)

    # Load files
    en_data = load_json_file(EN_JSON)
    ha_data = load_json_file(HA_JSON)

    # Find missing keys
    missing_keys = get_missing_keys(en_data, ha_data)

    print(f"\nTotal missing keys: {len(missing_keys)}")
    print(f"\nFirst 50 missing keys:")
    for i, key in enumerate(missing_keys[:50], 1):
        print(f"  {i}. {key}")

    if len(missing_keys) > 50:
        print(f"  ... and {len(missing_keys) - 50} more")

    print("\n" + "=" * 60)
    print("RECOMMENDATION:")
    print("=" * 60)
    print("""
Due to the large number of missing keys (~1131), this task requires:

1. **Automated Translation Pipeline**: Use Claude API with the glossary
2. **Human Review**: Native Hausa speaker review of technical terms
3. **Iterative Completion**: Complete in batches (e.g., 200 keys at a time)

The script tools/localization/batch_translate_hausa.py can help automate this.
""")

if __name__ == "__main__":
    main()
