#!/usr/bin/env python3
"""Rename clawdbot_ prefixed adapters to generic names."""

import json
import os
import re
import shutil
from pathlib import Path

ADAPTERS_DIR = Path(__file__).parent.parent / "ciris_adapters"

# Special cases where we need different names
SPECIAL_RENAMES = {
    "clawdbot_1password": "onepassword",  # Can't start with number
}


def get_new_name(old_name: str) -> str:
    """Get the new name for an adapter."""
    if old_name in SPECIAL_RENAMES:
        return SPECIAL_RENAMES[old_name]
    # Remove clawdbot_ prefix
    if old_name.startswith("clawdbot_"):
        return old_name[9:]  # len("clawdbot_") = 9
    return old_name


def update_file_content(file_path: Path, old_name: str, new_name: str) -> bool:
    """Update references in a file. Returns True if changes were made."""
    try:
        content = file_path.read_text()
        new_content = content.replace(old_name, new_name)
        if content != new_content:
            file_path.write_text(new_content)
            return True
    except Exception as e:
        print(f"  Error updating {file_path}: {e}")
    return False


def rename_adapter(old_path: Path) -> tuple[str, str] | None:
    """Rename a single adapter directory and update internal references."""
    old_name = old_path.name
    new_name = get_new_name(old_name)

    if old_name == new_name:
        return None

    new_path = old_path.parent / new_name

    if new_path.exists():
        print(f"  SKIP: {new_name} already exists")
        return None

    print(f"  {old_name} -> {new_name}")

    # Update files before renaming
    for file_path in old_path.rglob("*"):
        if file_path.is_file() and file_path.suffix in (".py", ".json", ".md"):
            if update_file_content(file_path, old_name, new_name):
                print(f"    Updated: {file_path.name}")

    # Rename directory
    shutil.move(str(old_path), str(new_path))

    return old_name, new_name


def main():
    """Main entry point."""
    print("Renaming clawdbot adapters to generic names...")
    print(f"Adapters directory: {ADAPTERS_DIR}")
    print()

    # Find all clawdbot_ adapters
    clawdbot_adapters = sorted([
        p for p in ADAPTERS_DIR.iterdir()
        if p.is_dir() and p.name.startswith("clawdbot_")
    ])

    print(f"Found {len(clawdbot_adapters)} clawdbot adapters")
    print()

    renamed = []
    for adapter_path in clawdbot_adapters:
        result = rename_adapter(adapter_path)
        if result:
            renamed.append(result)

    print()
    print(f"Renamed {len(renamed)} adapters")

    # Also check tools/clawdbot_skill_converter
    converter_path = Path(__file__).parent / "clawdbot_skill_converter"
    if converter_path.exists():
        print()
        print("Note: tools/clawdbot_skill_converter still exists (kept for reference)")


if __name__ == "__main__":
    main()
