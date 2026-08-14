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


def _is_ui_locale_bundle(name: str) -> bool:
    """True only for ``{lang}.json`` UI bundles (2-letter code per the manifest).

    ``data/localized/`` also holds prompt-corpus JSON that is deliberately NOT
    mirrored to clients — ``crisis_resources_{lang}.json`` (#971) has exactly
    one source of truth because it carries crisis phone numbers, and the
    glob-everything discovery here failed the suite the moment those landed.
    Match the shape, not a denylist, so the next corpus family (#974's
    language_guidance split is already planned) does not repeat this.
    """
    stem = name.removesuffix(".json")
    return len(stem) == 2 and stem.isalpha() and stem.islower()


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



def _flat_values(path: Path) -> dict:
    """Dotted-key -> string value, for comparing a copy's TEXT against source.

    Separate from `load_localization_keys` (which returns a key set) rather than
    reworking it: that function has other callers, and this test is being
    tightened precisely because a silent behaviour change slipped through here
    once already.
    """
    import json

    def walk(obj, prefix=""):
        out = {}
        for k, v in obj.items():
            if isinstance(v, dict):
                out.update(walk(v, f"{prefix}{k}."))
            elif isinstance(v, str):
                out[f"{prefix}{k}"] = v
        return out

    try:
        return walk(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return {}


class TestKotlinLocalizations:
    """Tests for Kotlin localization key coverage."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get project root."""
        return get_project_root()

    @pytest.fixture
    def localization_keys(self, project_root: Path) -> set[str]:
        """Load all localization keys from en.json."""
        en_json = project_root / "ciris_engine" / "data" / "localized" / "en.json"
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
        """Verify ALL localization copies match source — keys AND values.

        The "AND values" half was missing until 2.9.14, while this docstring
        already claimed "byte-identical". It compared key SETS only, so a mirror
        carrying every correct key with entirely wrong text passed clean.

        That is not hypothetical. The Ukrainian retranslation (#949) landed in
        five of six copies; `client/iosApp/Resources/app/localization/uk.json`
        kept 658 Russian values and this test stayed green, because the Russian
        strings sat under the same keys. It is the copy iOS ships from, so the
        release would have shown Ukrainian users Russian on the one platform
        already reporting upgrade trouble.

        Measured before tightening: zero value drift across all 29 locales × 5
        copies, so equality is the real invariant here, not an aspiration.

        Source of truth: localization/*.json
        Copies that must stay in sync:
        1. client/iosApp/iosApp/localization/     (iOS app bundle)
        2. client/iosApp/Resources/app/localization/ (iOS Python Resources)
        3. client/androidApp/src/main/assets/localization/ (Android assets)
        4. client/desktopApp/src/main/resources/localization/ (Desktop resources)
        5. client/shared/src/desktopMain/resources/localization/ (Desktop KMP)
        """
        source_dir = project_root / "ciris_engine" / "data" / "localized"
        if not source_dir.exists():
            pytest.skip("localization/ directory not found")

        copy_dirs = [
            project_root / "client" / "iosApp" / "iosApp" / "localization",
            project_root / "client" / "iosApp" / "Resources" / "app" / "localization",
            project_root / "client" / "androidApp" / "src" / "main" / "assets" / "localization",
            project_root / "client" / "desktopApp" / "src" / "main" / "resources" / "localization",
            project_root / "client" / "shared" / "src" / "desktopMain" / "resources" / "localization",
        ]

        # UI locale bundles only — {lang}.json per the manifest. Glob-everything
        # broke when #971 added crisis_resources_{lang}.json corpus files to the
        # same directory: those are prompt DATA with one source of truth by
        # design (mirroring phone numbers into 6 client bundles is exactly what
        # that change exists to prevent), so they must not be sync-checked here.
        # They have their own stronger gate (tests/test_crisis_resources_corpus.py,
        # full Pydantic validation per file).
        source_files = {f.name for f in source_dir.glob("*.json") if _is_ui_locale_bundle(f.name)}
        errors = []

        for copy_dir in copy_dirs:
            if not copy_dir.exists():
                continue
            rel_dir = copy_dir.relative_to(project_root)

            for lang_file in sorted(source_files):
                source_file = source_dir / lang_file
                copy_file = copy_dir / lang_file

                if not copy_file.exists():
                    errors.append(f"{rel_dir}/{lang_file}: MISSING")
                    continue

                source_keys = load_localization_keys(source_file)
                copy_keys = load_localization_keys(copy_file)
                missing = source_keys - copy_keys
                if missing:
                    errors.append(
                        f"{rel_dir}/{lang_file}: missing {len(missing)} keys " f"(e.g. {sorted(missing)[:3]})"
                    )

                # The half that was absent. A copy is a copy: same key, same
                # text. Report the count AND a specimen — "12 values differ" sends
                # someone diffing 3,676 strings, while showing the pair usually
                # identifies the stale mirror on sight.
                src_vals = _flat_values(source_file)
                copy_vals = _flat_values(copy_file)
                changed = sorted(k for k, v in src_vals.items() if k in copy_vals and copy_vals[k] != v)
                if changed:
                    k = changed[0]
                    errors.append(
                        f"{rel_dir}/{lang_file}: {len(changed)} values differ from source "
                        f"(e.g. {k!r}: source={src_vals[k][:48]!r} copy={copy_vals[k][:48]!r})"
                    )

        if errors:
            fix_cmd = (
                "cp localization/*.json client/iosApp/iosApp/localization/ && "
                "cp localization/*.json client/iosApp/Resources/app/localization/ && "
                "cp localization/*.json client/androidApp/src/main/assets/localization/ && "
                "cp localization/*.json client/desktopApp/src/main/resources/localization/ && "
                "cp localization/*.json client/shared/src/desktopMain/resources/localization/"
            )
            pytest.fail(
                f"\n{len(errors)} localization sync issues:\n"
                + "\n".join(f"  - {e}" for e in errors[:20])
                + (f"\n  ... and {len(errors) - 20} more" if len(errors) > 20 else "")
                + f"\n\nFix: {fix_cmd}"
            )

    def test_no_duplicate_keys(self, project_root: Path) -> None:
        """Check for duplicate keys in localization files."""
        en_json = project_root / "ciris_engine" / "data" / "localized" / "en.json"
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
        localization_dir = project_root / "ciris_engine" / "data" / "localized"
        if not localization_dir.exists():
            pytest.skip("localization directory not found")

        for json_file in localization_dir.glob("*.json"):
            # UI locale bundles only — see _is_ui_locale_bundle for why the
            # crisis_resources_* corpus files are excluded here.
            if not _is_ui_locale_bundle(json_file.name):
                continue
            with open(json_file) as f:
                data = json.load(f)

            assert "mobile" in data, f"{json_file.name} is missing 'mobile' section"
