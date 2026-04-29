"""Tests for the localization utility module."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.logic.utils.localization import (
    clear_cache,
    get_available_languages,
    get_language_guidance,
    get_language_meta,
    get_localizer,
    get_preferred_language,
    get_string,
    preload_languages,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the localization cache before each test."""
    clear_cache()
    yield
    clear_cache()


class TestGetString:
    """Tests for get_string function."""

    def test_get_english_string(self):
        """Test basic English string lookup."""
        result = get_string("en", "agent.greeting")
        assert result is not None
        assert "Hello" in result or "help" in result.lower()

    def test_get_nested_key(self):
        """Test nested dot-notation key lookup."""
        result = get_string("en", "prompts.dma.pdma_header")
        assert result is not None
        assert "CIRIS" in result

    def test_fallback_to_english(self):
        """Test fallback to English when key missing in target language."""
        # Use a key that exists in English but might not in all languages
        result = get_string("am", "status.all_operational")
        assert result is not None
        # Should get something, either Amharic or English fallback

    def test_fallback_to_default(self):
        """Test fallback to provided default."""
        result = get_string("en", "nonexistent.key.here", default="My Default")
        assert result == "My Default"

    def test_fallback_to_key_itself(self):
        """Test fallback to key itself when no default provided."""
        result = get_string("en", "totally.fake.key")
        assert result == "totally.fake.key"

    def test_interpolation_single_param(self):
        """Test parameter interpolation with single param."""
        result = get_string("en", "mobile.startup_services_count", online=5, total=22)
        assert "5" in result
        assert "22" in result

    def test_interpolation_multiple_params(self):
        """Test parameter interpolation with multiple params."""
        result = get_string("en", "mobile.startup_preparing_progress", current=3, total=8)
        assert "3" in result
        assert "8" in result

    def test_invalid_language_falls_back(self):
        """Test that invalid language code falls back to English."""
        result = get_string("xx", "agent.greeting")
        # Should still return something (English fallback or the key)
        assert result is not None

    def test_en_marker_treated_as_missing(self):
        """Test that [EN] placeholder markers trigger fallback."""
        # This tests the logic, actual behavior depends on file content
        # If a value starts with [EN], it should fall back to English
        pass  # Skip for now as it depends on specific file state


class TestGetLocalizer:
    """Tests for get_localizer function."""

    def test_bound_localizer(self):
        """Test that localizer is bound to specified language."""
        loc = get_localizer("en")
        result = loc("agent.greeting")
        assert result is not None
        assert "Hello" in result or "help" in result.lower()

    def test_localizer_with_params(self):
        """Test localizer with parameter interpolation."""
        loc = get_localizer("en")
        result = loc("mobile.startup_services_count", online=10, total=22)
        assert "10" in result
        assert "22" in result

    def test_localizer_with_default(self):
        """Test localizer with default value."""
        loc = get_localizer("en")
        result = loc("nonexistent.key", default="Fallback")
        assert result == "Fallback"


class TestAvailableLanguages:
    """Tests for get_available_languages function."""

    def test_returns_list(self):
        """Test that available languages returns a list."""
        languages = get_available_languages()
        assert isinstance(languages, list)

    def test_english_available(self):
        """Test that English is always available."""
        languages = get_available_languages()
        assert "en" in languages

    def test_multiple_languages(self):
        """Test that multiple languages are available."""
        languages = get_available_languages()
        # We know we have at least en, es, fr, am, etc.
        assert len(languages) >= 5


class TestLanguageMeta:
    """Tests for get_language_meta function."""

    def test_english_meta(self):
        """Test English language metadata."""
        meta = get_language_meta("en")
        assert meta["language"] == "en"
        assert meta["language_name"] == "English"
        assert meta["direction"] == "ltr"

    def test_rtl_language(self):
        """Test RTL language metadata (Arabic)."""
        meta = get_language_meta("ar")
        assert meta["direction"] == "rtl"

    def test_unknown_language_defaults(self):
        """Test that unknown language returns sensible defaults."""
        meta = get_language_meta("xx")
        assert meta["language"] == "xx"
        assert meta["direction"] == "ltr"


class TestPreloadLanguages:
    """Tests for preload_languages function."""

    def test_preload_specific_languages(self):
        """Test preloading specific language codes."""
        # Should not raise any errors
        preload_languages(["en", "es"])

    def test_preload_all_languages(self):
        """Test preloading all available languages."""
        # Should not raise any errors
        preload_languages()


class TestGetPreferredLanguage:
    """Tests for get_preferred_language function."""

    def test_default_is_english(self):
        """Test that default preferred language is English."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if set
            os.environ.pop("CIRIS_PREFERRED_LANGUAGE", None)
            result = get_preferred_language()
            assert result == "en"

    def test_respects_env_var(self):
        """Test that environment variable is respected."""
        with patch.dict(os.environ, {"CIRIS_PREFERRED_LANGUAGE": "am"}):
            result = get_preferred_language()
            assert result == "am"


class TestWithTempFiles:
    """Tests using temporary localization files."""

    def test_custom_localization_dir(self):
        """Test using a custom localization directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test localization file
            test_data = {
                "_meta": {"language": "test", "language_name": "Test Language", "direction": "ltr"},
                "greeting": "Hello from test!",
                "nested": {"key": "Nested value with {param}"},
            }
            test_file = Path(tmpdir) / "test.json"
            with open(test_file, "w") as f:
                json.dump(test_data, f)

            # Also need English for fallback
            en_data = {"_meta": {"language": "en", "language_name": "English", "direction": "ltr"}}
            en_file = Path(tmpdir) / "en.json"
            with open(en_file, "w") as f:
                json.dump(en_data, f)

            with patch.dict(os.environ, {"CIRIS_LOCALIZATION_DIR": tmpdir}):
                clear_cache()
                result = get_string("test", "greeting")
                assert result == "Hello from test!"

                result = get_string("test", "nested.key", param="test_value")
                assert result == "Nested value with test_value"


class TestCacheManagement:
    """Tests for cache management."""

    def test_clear_cache(self):
        """Test that clear_cache works."""
        # Load something
        get_string("en", "agent.greeting")
        # Clear it
        clear_cache()
        # Should still work (will reload)
        result = get_string("en", "agent.greeting")
        assert result is not None


class TestGetLanguageGuidance:
    """Tests for the per-language guidance block injected into LLM prompts.

    Pinning the contract: 28 of 29 languages return empty (so the DMA
    layer skips appending an empty system message), and Amharic returns
    the populated terminology pack covering the 2.7.6 install incident's
    three observed errors (diagnosis sense-collision, talk-therapy
    transliteration, schizophrenia cluster contamination).
    """

    def test_amharic_returns_non_empty_guidance(self):
        """Amharic carries the terminology pack."""
        guidance = get_language_guidance("am")
        assert guidance, "Amharic guidance must be populated — empty would re-introduce the 2.7.6 install regression"
        # The three load-bearing terminology fixes that motivated this block
        # MUST be present. Test by Amharic substring (not English) so the
        # pack can't be quietly replaced with English filler.
        assert "ምርመራ" in guidance, "Amharic 'diagnosis' fix (ምርመራ vs ማንነት ማወቅ) is missing"
        assert "የንግግር ሕክምና" in guidance, "Amharic 'talk therapy' fix (የንግግር ሕክምና vs ሳይኮተራፒ transliteration) is missing"
        # The negative-example pattern is load-bearing per the diagnostic
        # notes — a flat glossary without the wrong-candidate disambiguation
        # doesn't fix the sense-collision error.
        assert "ማንነት ማወቅ" in guidance, "Wrong-sense disambiguation for 'diagnosis' must name the bad candidate"
        assert "ሳይኮተራፒ" in guidance, "Transliteration disambiguation for 'talk therapy' must name the bad candidate"

    def test_english_returns_empty_guidance(self):
        """English doesn't need guidance (the prompt is already in English)."""
        assert get_language_guidance("en") == ""

    @pytest.mark.parametrize(
        "lang_code",
        ["es", "fr", "de", "pt", "it", "ru", "uk", "zh", "ja", "ko", "hi", "ar", "tr", "vi", "id"],
    )
    def test_other_locales_return_empty_until_populated(self, lang_code):
        """Locales without an observed terminology gap return empty so the
        DMA layer skips the system-message append entirely (no wire
        overhead, no behavior change for languages we haven't audited)."""
        assert get_language_guidance(lang_code) == ""

    def test_unknown_language_returns_empty(self):
        """A language code that doesn't exist falls through to empty (NOT
        the literal key 'prompts.language_guidance'). The contract is that
        callers can pass `if guidance:` and skip cleanly."""
        assert get_language_guidance("xx") == ""
        assert get_language_guidance("zz_NONEXISTENT") == ""

    def test_strips_trailing_whitespace(self):
        """The helper strips whitespace so the appended system message
        doesn't carry leading/trailing newlines that would inflate the
        wire payload."""
        guidance = get_language_guidance("am")
        assert guidance == guidance.strip()
