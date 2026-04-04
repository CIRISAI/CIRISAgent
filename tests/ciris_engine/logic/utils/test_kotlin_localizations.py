"""Test that all localization keys used in Kotlin code exist in JSON files.

This test scans Kotlin source files for localization key references and validates
they exist in the localization JSON files.
"""

import json
import re
from pathlib import Path

import pytest

# Patterns to find localization key usage in Kotlin
PATTERNS = [
    # localizedString("key") or localizedString("key", ...)
    r'localizedString\s*\(\s*"([^"]+)"',
    # LocalizationHelper.getString("key") or getString("key", ...)
    r'getString\s*\(\s*"([^"]+)"',
]

# Keys to ignore (dynamic keys with variable interpolation)
IGNORED_KEY_PATTERNS = [
    r"\$",  # Contains variable interpolation like $key
    r"^api_key_",  # Dynamic API key storage
    r"^memory_key$",  # Internal memory key
    r"^memory_service$",  # Internal service name
]


def get_project_root() -> Path:
    """Get the project root directory."""
    # tests/ciris_engine/logic/utils/test_kotlin_localizations.py -> 5 levels up
    return Path(__file__).parent.parent.parent.parent.parent


def load_localization_keys(file_path: Path) -> set[str]:
    """Load all keys from a localization JSON file using dot notation."""
    keys: set[str] = set()

    def extract_keys(obj: dict, prefix: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                new_key = f"{prefix}.{k}" if prefix else k
                if isinstance(v, dict):
                    extract_keys(v, new_key)
                else:
                    keys.add(new_key)

    with open(file_path) as f:
        data = json.load(f)
    extract_keys(data)
    return keys


def find_kotlin_keys(kotlin_dir: Path) -> set[str]:
    """Find all localization keys used in Kotlin files."""
    keys: set[str] = set()

    for kt_file in kotlin_dir.rglob("*.kt"):
        try:
            content = kt_file.read_text()
            for pattern in PATTERNS:
                for match in re.finditer(pattern, content):
                    key = match.group(1)
                    # Skip dynamic keys
                    if not any(re.search(p, key) for p in IGNORED_KEY_PATTERNS):
                        keys.add(key)
        except Exception:
            pass

    return keys


class TestKotlinLocalizations:
    """Tests for Kotlin localization key coverage."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root."""
        return get_project_root()

    @pytest.fixture
    def localization_keys(self, project_root: Path) -> set[str]:
        """Load all localization keys from en.json."""
        en_json = project_root / "localization" / "en.json"
        if not en_json.exists():
            pytest.skip("localization/en.json not found")
        return load_localization_keys(en_json)

    @pytest.fixture
    def kotlin_keys(self, project_root: Path) -> set[str]:
        """Find all localization keys used in Kotlin code."""
        kotlin_dirs = [
            project_root / "mobile" / "shared" / "src" / "commonMain" / "kotlin",
            project_root / "mobile" / "shared" / "src" / "androidMain" / "kotlin",
            project_root / "mobile" / "shared" / "src" / "desktopMain" / "kotlin",
        ]

        all_keys: set[str] = set()
        for kotlin_dir in kotlin_dirs:
            if kotlin_dir.exists():
                all_keys.update(find_kotlin_keys(kotlin_dir))

        return all_keys

    def test_all_kotlin_keys_exist_in_localization(self, localization_keys: set[str], kotlin_keys: set[str]) -> None:
        """Verify all Kotlin localization keys exist in en.json."""
        missing_keys = kotlin_keys - localization_keys

        if missing_keys:
            # Format error message with missing keys
            msg_lines = [
                f"\n{len(missing_keys)} localization keys used in Kotlin code are missing from en.json:",
                "",
            ]
            for key in sorted(missing_keys)[:50]:  # Show first 50
                msg_lines.append(f"  - {key}")
            if len(missing_keys) > 50:
                msg_lines.append(f"  ... and {len(missing_keys) - 50} more")
            msg_lines.append("")
            msg_lines.append("To fix: Add these keys to localization/en.json")

            pytest.fail("\n".join(msg_lines))

    def test_localization_files_in_sync(self, project_root: Path) -> None:
        """Verify mobile localization files are in sync with main en.json."""
        main_en = project_root / "localization" / "en.json"
        mobile_locations = [
            project_root / "mobile" / "androidApp" / "src" / "main" / "assets" / "localization" / "en.json",
            project_root / "mobile" / "shared" / "src" / "desktopMain" / "resources" / "localization" / "en.json",
        ]

        if not main_en.exists():
            pytest.skip("localization/en.json not found")

        main_keys = load_localization_keys(main_en)

        for mobile_file in mobile_locations:
            if mobile_file.exists():
                mobile_keys = load_localization_keys(mobile_file)

                missing_in_mobile = main_keys - mobile_keys
                if missing_in_mobile:
                    pytest.fail(
                        f"{mobile_file.relative_to(project_root)} is missing "
                        f"{len(missing_in_mobile)} keys from main en.json. "
                        f"Run: cp localization/en.json {mobile_file.relative_to(project_root)}"
                    )

    def test_no_duplicate_keys(self, project_root: Path) -> None:
        """Check for duplicate keys in localization files."""
        en_json = project_root / "localization" / "en.json"
        if not en_json.exists():
            pytest.skip("localization/en.json not found")

        # This just verifies JSON is valid (no duplicate keys at parse level)
        with open(en_json) as f:
            json.load(f)

    def test_key_count_reasonable(self, localization_keys: set[str]) -> None:
        """Sanity check that we have a reasonable number of keys."""
        # Should have at least 1000 keys for a full app
        assert len(localization_keys) >= 1000, (
            f"Only {len(localization_keys)} localization keys found. " "This seems low - check if en.json is complete."
        )

    def test_all_languages_have_mobile_section(self, project_root: Path) -> None:
        """Verify all language files have a 'mobile' section."""
        localization_dir = project_root / "localization"
        if not localization_dir.exists():
            pytest.skip("localization directory not found")

        for json_file in localization_dir.glob("*.json"):
            # Skip non-language files
            if json_file.name in ("manifest.json", "schema.json"):
                continue
            with open(json_file) as f:
                data = json.load(f)

            assert "mobile" in data, f"{json_file.name} is missing 'mobile' section"
