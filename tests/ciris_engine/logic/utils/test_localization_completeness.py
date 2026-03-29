"""
Tests for localization file completeness.

This module validates that all localized files have:
1. Complete key coverage (all keys from en.json present)
2. No duplicate keys
3. Complete ACCORD and Guide translations
4. Complete DMA prompt translations
"""

import json
from pathlib import Path
from typing import Set

import pytest

# Project root for file lookups
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent


def get_nested_keys(obj: dict, prefix: str = "") -> Set[str]:
    """Extract all nested keys from a dict using dot notation."""
    keys = set()
    for k, v in obj.items():
        full_key = f"{prefix}{k}" if prefix else k
        if isinstance(v, dict):
            keys.update(get_nested_keys(v, f"{full_key}."))
        else:
            keys.add(full_key)
    return keys


def check_duplicate_keys(filepath: Path) -> list:
    """Check for duplicate keys in JSON file by parsing raw content."""
    duplicates = []
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Use json decoder with custom object_pairs_hook to detect duplicates
    def detect_duplicates(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    json.loads(content, object_pairs_hook=detect_duplicates)
    return duplicates


class TestLocalizationKeyCompleteness:
    """Tests that all language files have complete key coverage."""

    @pytest.fixture(scope="class")
    def localization_dir(self) -> Path:
        """Get the localization directory."""
        return PROJECT_ROOT / "localization"

    @pytest.fixture(scope="class")
    def english_keys(self, localization_dir: Path) -> Set[str]:
        """Load all keys from the English source file."""
        en_path = localization_dir / "en.json"
        with open(en_path, "r", encoding="utf-8") as f:
            en_data = json.load(f)
        return get_nested_keys(en_data)

    @pytest.fixture(scope="class")
    def language_files(self, localization_dir: Path) -> list:
        """Get all language JSON files except manifest."""
        return [
            f
            for f in localization_dir.glob("*.json")
            if f.name != "manifest.json" and f.name != "en.json"
        ]

    def test_english_has_expected_key_count(self, english_keys: Set[str]):
        """Verify English has the expected number of keys."""
        # As of current version, we expect ~1257 keys
        assert len(english_keys) >= 1200, f"English has only {len(english_keys)} keys"

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_language_has_all_keys(
        self, localization_dir: Path, english_keys: Set[str], lang_code: str
    ):
        """Test that a language file has all keys from English."""
        lang_path = localization_dir / f"{lang_code}.json"
        if not lang_path.exists():
            pytest.skip(f"{lang_code}.json does not exist yet")

        with open(lang_path, "r", encoding="utf-8") as f:
            lang_data = json.load(f)

        lang_keys = get_nested_keys(lang_data)
        missing = english_keys - lang_keys

        assert len(missing) == 0, (
            f"{lang_code}.json is missing {len(missing)} keys. "
            f"First 10 missing: {sorted(missing)[:10]}"
        )

    @pytest.mark.parametrize(
        "lang_code",
        ["en", "ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_no_extra_keys(
        self, localization_dir: Path, english_keys: Set[str], lang_code: str
    ):
        """Test that a language file has no extra keys not in English."""
        lang_path = localization_dir / f"{lang_code}.json"
        if not lang_path.exists():
            pytest.skip(f"{lang_code}.json does not exist yet")

        with open(lang_path, "r", encoding="utf-8") as f:
            lang_data = json.load(f)

        lang_keys = get_nested_keys(lang_data)
        extra = lang_keys - english_keys

        # Allow _meta keys which may vary
        extra = {k for k in extra if not k.startswith("_meta")}

        assert len(extra) == 0, (
            f"{lang_code}.json has {len(extra)} extra keys. "
            f"Extra keys: {sorted(extra)[:10]}"
        )

    @pytest.mark.parametrize(
        "lang_code",
        ["en", "ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_no_duplicate_keys(self, localization_dir: Path, lang_code: str):
        """Test that language files have no duplicate keys."""
        lang_path = localization_dir / f"{lang_code}.json"
        if not lang_path.exists():
            pytest.skip(f"{lang_code}.json does not exist yet")

        duplicates = check_duplicate_keys(lang_path)
        assert len(duplicates) == 0, f"{lang_code}.json has duplicate keys: {duplicates}"


class TestACCORDCompleteness:
    """Tests that ACCORD translations are complete."""

    @pytest.fixture(scope="class")
    def data_dir(self) -> Path:
        """Get the data directory."""
        return PROJECT_ROOT / "ciris_engine" / "data"

    @pytest.fixture(scope="class")
    def english_accord_lines(self, data_dir: Path) -> int:
        """Get line count of English ACCORD."""
        en_path = data_dir / "accord_1.2b.txt"
        with open(en_path, "r", encoding="utf-8") as f:
            return len(f.readlines())

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_accord_translation_complete(
        self, data_dir: Path, english_accord_lines: int, lang_code: str
    ):
        """Test that ACCORD translation has similar line count to English."""
        localized_dir = data_dir / "localized"
        accord_path = localized_dir / f"accord_1.2b_{lang_code}.txt"

        if not accord_path.exists():
            pytest.skip(f"accord_1.2b_{lang_code}.txt does not exist yet")

        with open(accord_path, "r", encoding="utf-8") as f:
            lang_lines = len(f.readlines())

        # Allow 10% variance for translation expansion/contraction
        min_lines = int(english_accord_lines * 0.9)
        max_lines = int(english_accord_lines * 1.1)

        assert min_lines <= lang_lines <= max_lines, (
            f"accord_1.2b_{lang_code}.txt has {lang_lines} lines, "
            f"expected ~{english_accord_lines} (English reference)"
        )


class TestGuideCompleteness:
    """Tests that Comprehensive Guide translations are complete."""

    @pytest.fixture(scope="class")
    def data_dir(self) -> Path:
        """Get the data directory."""
        return PROJECT_ROOT / "ciris_engine" / "data"

    @pytest.fixture(scope="class")
    def english_guide_lines(self, data_dir: Path) -> int:
        """Get line count of English Guide."""
        en_path = data_dir / "CIRIS_COMPREHENSIVE_GUIDE.md"
        if not en_path.exists():
            return 560  # Expected line count
        with open(en_path, "r", encoding="utf-8") as f:
            return len(f.readlines())

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_guide_translation_exists(self, data_dir: Path, lang_code: str):
        """Test that Guide translation exists."""
        localized_dir = data_dir / "localized"
        guide_path = localized_dir / f"CIRIS_COMPREHENSIVE_GUIDE_{lang_code}.md"

        assert guide_path.exists(), f"CIRIS_COMPREHENSIVE_GUIDE_{lang_code}.md does not exist"

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_guide_translation_complete(
        self, data_dir: Path, english_guide_lines: int, lang_code: str
    ):
        """Test that Guide translation has reasonable line count."""
        localized_dir = data_dir / "localized"
        guide_path = localized_dir / f"CIRIS_COMPREHENSIVE_GUIDE_{lang_code}.md"

        if not guide_path.exists():
            pytest.skip(f"CIRIS_COMPREHENSIVE_GUIDE_{lang_code}.md does not exist yet")

        with open(guide_path, "r", encoding="utf-8") as f:
            lang_lines = len(f.readlines())

        # Allow 20% variance for translation expansion/contraction
        min_lines = int(english_guide_lines * 0.8)

        assert lang_lines >= min_lines, (
            f"CIRIS_COMPREHENSIVE_GUIDE_{lang_code}.md has only {lang_lines} lines, "
            f"expected at least {min_lines} (English has {english_guide_lines})"
        )


class TestDMAPromptCompleteness:
    """Tests that DMA prompt translations are complete."""

    @pytest.fixture(scope="class")
    def prompts_dir(self) -> Path:
        """Get the DMA prompts directory."""
        return PROJECT_ROOT / "ciris_engine" / "logic" / "dma" / "prompts"

    @pytest.fixture(scope="class")
    def english_prompt_files(self, prompts_dir: Path) -> list:
        """Get list of English prompt files."""
        return [f.name for f in prompts_dir.glob("*.yml") if f.is_file()]

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_dma_prompts_directory_exists(self, prompts_dir: Path, lang_code: str):
        """Test that localized DMA prompts directory exists."""
        localized_dir = prompts_dir / "localized" / lang_code
        assert localized_dir.exists(), f"DMA prompts directory for {lang_code} does not exist"

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_dma_prompts_complete(
        self, prompts_dir: Path, english_prompt_files: list, lang_code: str
    ):
        """Test that all English prompt files exist in localized directory."""
        localized_dir = prompts_dir / "localized" / lang_code

        if not localized_dir.exists():
            pytest.skip(f"DMA prompts directory for {lang_code} does not exist yet")

        localized_files = [f.name for f in localized_dir.glob("*.yml")]
        missing = set(english_prompt_files) - set(localized_files)

        # Filter out test/example files that may not need translation
        missing = {f for f in missing if not f.startswith("test_")}

        assert len(missing) == 0, (
            f"{lang_code} DMA prompts missing {len(missing)} files: {missing}"
        )


class TestGlossaryCompleteness:
    """Tests that translation glossaries exist for all languages."""

    @pytest.fixture(scope="class")
    def glossary_dir(self) -> Path:
        """Get the glossary directory."""
        return PROJECT_ROOT / "docs" / "localization" / "glossaries"

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_glossary_exists(self, glossary_dir: Path, lang_code: str):
        """Test that glossary exists for each language."""
        glossary_path = glossary_dir / f"{lang_code}_glossary.md"
        assert glossary_path.exists(), f"Glossary for {lang_code} does not exist"

    @pytest.mark.parametrize(
        "lang_code",
        ["ar", "de", "es", "fr", "hi", "it", "ja", "ko", "pt", "ru", "sw", "tr", "zh", "am", "ur"],
    )
    def test_glossary_has_content(self, glossary_dir: Path, lang_code: str):
        """Test that glossary has meaningful content."""
        glossary_path = glossary_dir / f"{lang_code}_glossary.md"

        if not glossary_path.exists():
            pytest.skip(f"Glossary for {lang_code} does not exist yet")

        with open(glossary_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for expected sections
        assert "Core Action Verbs" in content, f"{lang_code} glossary missing Core Action Verbs"
        assert "Core Concepts" in content, f"{lang_code} glossary missing Core Concepts"
        assert len(content) > 3000, f"{lang_code} glossary seems too short ({len(content)} chars)"
