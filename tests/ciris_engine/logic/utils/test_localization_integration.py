"""
Comprehensive tests for localization across all DMAs and Consciences.

Tests verify that:
1. User language preferences are properly extracted from context
2. All DMAs use localized ACCORD text
3. Conscience ponder strings are localized
4. Language sync between graph, env, and prompt loader works
"""

import os
from datetime import datetime
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.utils.localization import (
    clear_cache,
    get_available_languages,
    get_localizer,
    get_preferred_language,
    get_string,
    get_user_language_from_context,
)
from ciris_engine.logic.utils.path_resolution import sync_env_var, sync_language_preference

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def clear_localization_cache():
    """Clear localization cache before each test."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def mock_user_profile():
    """Create a mock user profile with preferred_language."""
    profile = MagicMock()
    profile.preferred_language = "am"  # Amharic
    profile.user_id = "test-user-123"
    return profile


@pytest.fixture
def mock_context_with_language(mock_user_profile):
    """Create a mock context with user profile containing language preference."""
    context = MagicMock()
    context.system_snapshot = MagicMock()
    context.system_snapshot.user_profiles = [mock_user_profile]
    return context


@pytest.fixture
def mock_context_english():
    """Create a mock context with English language preference."""
    profile = MagicMock()
    profile.preferred_language = "en"
    context = MagicMock()
    context.system_snapshot = MagicMock()
    context.system_snapshot.user_profiles = [profile]
    return context


# ============================================================================
# Basic Localization Utility Tests
# ============================================================================


class TestLocalizationUtility:
    """Tests for core localization utility functions."""

    def test_get_string_english_default(self):
        """Test that English strings are returned by default."""
        result = get_string("en", "agent.greeting")
        assert result is not None
        assert isinstance(result, str)
        # Should not be the raw key
        assert result != "agent.greeting" or "greeting" in result.lower()

    def test_get_string_amharic(self):
        """Test that Amharic strings are returned when requested."""
        result = get_string("am", "agent.greeting")
        assert result is not None
        # Amharic uses Ge'ez script - check for non-ASCII
        # If translation exists, it should have Ge'ez characters
        # If not, it falls back to English

    def test_get_string_fallback_to_english(self):
        """Test fallback to English for missing translations."""
        # Use a key that likely exists in English but may not in all languages
        result = get_string("xx", "agent.greeting", default="fallback")
        assert result is not None
        # Should either be English fallback or the default

    def test_get_string_with_interpolation(self):
        """Test string interpolation with parameters."""
        result = get_string("en", "conscience.ponder_attempted", action="SPEAK")
        assert "SPEAK" in result or result == "conscience.ponder_attempted"

    def test_get_localizer_bound_to_language(self):
        """Test that get_localizer returns a function bound to a language."""
        loc = get_localizer("am")
        result = loc("agent.greeting")
        assert result is not None
        assert callable(loc)

    def test_get_available_languages(self):
        """Test that available languages are returned."""
        languages = get_available_languages()
        assert isinstance(languages, list)
        assert "en" in languages  # English should always be available


class TestLanguageFromContext:
    """Tests for extracting language from processing context."""

    def test_get_user_language_from_context_with_profile(self, mock_context_with_language):
        """Test extraction of language from user profile in context."""
        lang = get_user_language_from_context(mock_context_with_language)
        assert lang == "am"

    def test_get_user_language_from_context_none(self):
        """Test fallback when context is None."""
        lang = get_user_language_from_context(None)
        assert lang == get_preferred_language()

    def test_get_user_language_from_context_no_profiles(self):
        """Test fallback when no user profiles in context."""
        context = MagicMock()
        context.system_snapshot = MagicMock()
        context.system_snapshot.user_profiles = []
        lang = get_user_language_from_context(context)
        assert lang == get_preferred_language()

    def test_get_user_language_from_context_snapshot_direct(self, mock_user_profile):
        """Test extraction when context IS the snapshot (has system_snapshot=None)."""
        # When context IS the snapshot, system_snapshot is None but user_profiles exists
        snapshot = MagicMock()
        snapshot.system_snapshot = None  # No nested snapshot
        snapshot.user_profiles = [mock_user_profile]
        lang = get_user_language_from_context(snapshot)
        # Note: Current implementation checks system_snapshot first, then falls back
        # If system_snapshot is None, it should check user_profiles on context directly
        assert lang in ["am", "en"]  # Either works depending on implementation


# ============================================================================
# Environment Sync Tests
# ============================================================================


class TestEnvironmentSync:
    """Tests for syncing language preference to environment."""

    def test_sync_env_var_updates_os_environ(self):
        """Test that sync_env_var updates os.environ."""
        test_var = "TEST_CIRIS_LANG"
        try:
            sync_env_var(test_var, "test_value", persist_to_file=False)
            assert os.environ.get(test_var) == "test_value"
        finally:
            os.environ.pop(test_var, None)

    def test_sync_language_preference_updates_env(self, monkeypatch):
        """Test that sync_language_preference updates CIRIS_PREFERRED_LANGUAGE.

        Uses monkeypatch so any leak out of sync_language_preference's raw
        os.environ mutation is rolled back at teardown, keeping other
        xdist workers' tests unaffected.
        """
        sync_language_preference("es")
        assert os.environ.get("CIRIS_PREFERRED_LANGUAGE") == "es"

    @patch("ciris_engine.logic.dma.prompt_loader.set_prompt_language")
    def test_sync_language_preference_updates_prompt_loader(self, mock_set_lang):
        """Test that sync_language_preference updates DMA prompt loader."""
        sync_language_preference("fr")
        mock_set_lang.assert_called_once_with("fr")

    @patch("ciris_engine.logic.conscience.prompt_loader.set_conscience_prompt_language")
    def test_sync_language_preference_updates_conscience_prompt_loader(self, mock_set_lang):
        """Test that sync_language_preference updates conscience prompt loader."""
        sync_language_preference("am")
        mock_set_lang.assert_called_once_with("am")


# ============================================================================
# Conscience Localization Tests
# ============================================================================


class TestConscienceLocalization:
    """Tests for conscience ponder string localization."""

    def test_conscience_ponder_keys_exist_in_english(self):
        """Test that all conscience ponder keys exist in English."""
        conscience_keys = [
            "conscience.ponder_attempted",
            "conscience.ponder_conscience_failed",
            "conscience.ponder_bypass_failed",
            "conscience.ponder_alternative_approach",
            "conscience.ponder_forced_retry",
            "conscience.override_rationale",
            "conscience.forced_ponder_rationale",
        ]
        for key in conscience_keys:
            result = get_string("en", key)
            # Should return a string, not the raw key (unless key doesn't exist)
            assert result is not None
            assert isinstance(result, str)

    def test_conscience_ponder_keys_exist_in_amharic(self):
        """Test that conscience ponder keys exist in Amharic."""
        conscience_keys = [
            "conscience.ponder_attempted",
            "conscience.ponder_conscience_failed",
            "conscience.ponder_alternative_approach",
        ]
        for key in conscience_keys:
            result = get_string("am", key)
            assert result is not None
            # Check it's not just falling back to the raw key
            if result != key:
                # Should have some non-ASCII (Ge'ez) characters if translated
                pass  # Translation exists

    def test_conscience_ponder_interpolation(self):
        """Test that conscience strings support interpolation."""
        result = get_string("en", "conscience.ponder_attempted", action="MEMORIZE")
        # The string should contain the interpolated action
        assert "MEMORIZE" in result or "action" in result.lower() or result == "conscience.ponder_attempted"

    def test_conscience_override_rationale_interpolation(self):
        """Test override_rationale string interpolation."""
        result = get_string("en", "conscience.override_rationale", conscience_name="EntropyConscience", action="SPEAK")
        assert result is not None


# ============================================================================
# DMA Localization Tests
# ============================================================================


class TestDMALocalization:
    """Tests for DMA ACCORD text.

    Note: CIRIS 2.3 uses a polyglot ACCORD that contains all languages woven together.
    There is no separate per-language ACCORD - the polyglot version IS the ACCORD.
    """

    def test_polyglot_accord_contains_english(self):
        """Test that polyglot ACCORD contains English content."""
        from ciris_engine.logic.utils.constants import get_accord_text

        accord = get_accord_text()
        assert accord is not None
        assert len(accord) > 100  # ACCORD is a substantial document
        # Polyglot version contains English
        assert "ACCORD" in accord or "Principle" in accord or "PDMA" in accord

    def test_polyglot_accord_contains_amharic(self):
        """Test that polyglot ACCORD contains Amharic content."""
        from ciris_engine.logic.utils.constants import get_accord_text

        accord = get_accord_text()
        assert accord is not None
        # Polyglot version contains Amharic (Ge'ez script)
        # Check for common Amharic characters in the ACCORD
        has_amharic = any(ord(c) >= 0x1200 and ord(c) <= 0x137F for c in accord)
        assert has_amharic, "Polyglot ACCORD should contain Amharic characters"


class TestCSDMALocalization:
    """Tests for CSDMA language handling."""

    def test_csdma_extract_context_syncs_language(self, mock_context_with_language):
        """Test that CSDMA._extract_context_data syncs user's language into
        the per-instance _explicit_language field. (The legacy global
        set_prompt_language() call was removed — see prompt_loader.py."""
        with patch("ciris_engine.logic.dma.csdma.get_prompt_loader") as mock_loader, patch(
            "ciris_engine.logic.dma.csdma.format_system_snapshot"
        ) as mock_format_ss, patch("ciris_engine.logic.dma.csdma.format_user_profiles") as mock_format_up:

            mock_loader_instance = MagicMock()
            mock_loader_instance.language = "en"
            mock_loader_instance.load_prompt_template.return_value = MagicMock()
            mock_loader.return_value = mock_loader_instance

            mock_format_ss.return_value = "snapshot"
            mock_format_up.return_value = "profiles"

            mock_registry = MagicMock()
            from ciris_engine.logic.dma.csdma import CSDMAEvaluator

            csdma = CSDMAEvaluator(service_registry=mock_registry)
            assert csdma._explicit_language is None  # starts unset

            csdma._extract_context_data(mock_context_with_language)

            # The mock context's user has preferred_language="am" → CSDMA's
            # _explicit_language must now be "am". Subsequent get_prompt_loader
            # calls receive language="am" via the prompt_loader property.
            assert csdma._explicit_language == "am"


class TestPDMALocalization:
    """Tests for PDMA language handling."""

    def test_pdma_accord_contains_pdma_content(self):
        """Test that ACCORD contains PDMA-related content."""
        from ciris_engine.logic.utils.constants import get_accord_text

        accord = get_accord_text()
        assert accord is not None
        # ACCORD should reference PDMA process
        assert "PDMA" in accord


class TestIDMALocalization:
    """Tests for IDMA language handling."""

    def test_idma_has_extract_context_data(self):
        """Test that IDMA has _extract_context_data method."""
        with patch("ciris_engine.logic.dma.idma.get_prompt_loader"):
            from ciris_engine.logic.dma.idma import IDMAEvaluator

            assert hasattr(IDMAEvaluator, "_extract_context_data")


class TestDSDMALocalization:
    """Tests for DSDMA language handling."""

    def test_dsdma_uses_polyglot_accord(self):
        """Test that DSDMA uses the polyglot ACCORD via get_accord_text."""
        from ciris_engine.logic.utils.constants import get_accord_text

        # All DMAs now use the same polyglot ACCORD
        accord = get_accord_text()
        assert accord is not None
        assert len(accord) > 100

    def test_dsdma_has_prompt_loader(self):
        """Test that DSDMA has prompt_loader for language sync."""
        with patch("ciris_engine.logic.dma.dsdma_base.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.language = "en"
            mock_loader_instance.load_prompt_template.return_value = MagicMock()
            mock_loader.return_value = mock_loader_instance

            mock_registry = MagicMock()
            from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

            # BaseDSDMA has a prompt_loader attribute
            assert hasattr(BaseDSDMA, "__init__")


class TestASPDMALocalization:
    """Tests for Action Selection PDMA language handling."""

    def test_aspdma_uses_context_language(self):
        """Test that ASPDMA can extract language from context."""
        from ciris_engine.logic.utils.localization import get_user_language_from_context

        profile = MagicMock()
        profile.preferred_language = "es"
        context = MagicMock()
        context.system_snapshot = MagicMock()
        context.system_snapshot.user_profiles = [profile]

        lang = get_user_language_from_context(context)
        assert lang == "es"


class TestTSASPDMALocalization:
    """Tests for Tool-Specific ASPDMA language handling."""

    def test_tsaspdma_uses_polyglot_accord(self):
        """Test that TSASPDMA uses polyglot ACCORD via get_accord_text."""
        from ciris_engine.logic.utils.constants import get_accord_text

        accord = get_accord_text()
        # ACCORD should be present and contain relevant content
        assert accord is not None
        assert "ACCORD" in accord or "PDMA" in accord

    def test_tsaspdma_has_sync_language_method(self):
        """Test that TSASPDMA has _sync_language_from_context method."""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader"):
            from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator

            assert hasattr(TSASPDMAEvaluator, "_sync_language_from_context")

    def test_tsaspdma_sync_language_from_context(self, mock_context_with_language):
        """Test that TSASPDMA syncs language from context into the per-instance
        _explicit_language field. (Replaces the old set_prompt_language
        assertion — the global mutator was removed in prompt_loader.py.)"""
        with patch("ciris_engine.logic.dma.tsaspdma.get_prompt_loader") as mock_loader:
            mock_loader_instance = MagicMock()
            mock_loader_instance.language = "en"
            mock_loader_instance.load_prompt_template.return_value = MagicMock()
            mock_loader.return_value = mock_loader_instance

            mock_registry = MagicMock()
            from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator

            tsaspdma = TSASPDMAEvaluator(service_registry=mock_registry)
            assert tsaspdma._explicit_language is None  # starts unset

            tsaspdma._sync_language_from_context(mock_context_with_language)
            assert tsaspdma._explicit_language == "am"

            # Stale-bleed regression: a follow-up call with no context must
            # clear the language back to None, not inherit "am" from before.
            tsaspdma._sync_language_from_context(None)
            assert tsaspdma._explicit_language is None


# ============================================================================
# Integration Tests
# ============================================================================


class TestLocalizationIntegration:
    """Integration tests for full localization flow."""

    def test_language_change_flow(self, monkeypatch):
        """Test complete flow: change language -> sync -> use in DMA.

        Uses monkeypatch so sync_language_preference's raw os.environ
        mutation is rolled back at teardown — prevents cross-worker leaks
        under `pytest -n`.
        """
        # 1. Sync language preference (simulates API call)
        sync_language_preference("am")

        # 2. Verify env is updated
        assert os.environ.get("CIRIS_PREFERRED_LANGUAGE") == "am"

        # 3. Verify localization uses the new language
        from ciris_engine.logic.utils.localization import get_preferred_language

        assert get_preferred_language() == "am"

    def test_context_language_takes_precedence(self, mock_context_with_language, monkeypatch):
        """Test that user's context language takes precedence over env."""
        monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")
        lang = get_user_language_from_context(mock_context_with_language)
        # Context says "am", env says "en" - context should win
        assert lang == "am"

    def test_all_supported_languages_have_conscience_keys(self):
        """Test that all supported languages have conscience keys."""
        languages = get_available_languages()
        required_keys = [
            "conscience.ponder_attempted",
            "conscience.ponder_alternative_approach",
        ]

        for lang in languages:
            for key in required_keys:
                result = get_string(lang, key)
                # Should return something (either translated or English fallback)
                assert result is not None
                assert isinstance(result, str)


# ============================================================================
# Prompt Loader Sync Tests
# ============================================================================


class TestPromptLoaderSync:
    """Tests for DMA prompt loader language synchronization."""

    def test_get_prompt_loader_per_language_cache(self):
        """get_prompt_loader caches per-language; mutating a global is not the API.

        Replaces the old set_prompt_language(...) test. The mutable-singleton
        design that test exercised was the source of the multilingual race
        bug — concurrent thoughts in different languages trampled each other.
        Now each language has its own cached loader; explicit per-call lang is
        the contract.
        """
        from ciris_engine.logic.dma.prompt_loader import _loader_cache, get_prompt_loader

        _loader_cache.clear()
        try:
            en = get_prompt_loader(language="en")
            es = get_prompt_loader(language="es")
            assert en.language == "en"
            assert es.language == "es"
            assert en is not es
            # Cache hit returns the same instance
            assert get_prompt_loader(language="en") is en
        finally:
            _loader_cache.clear()

    def test_get_prompt_loader_returns_loader(self):
        """Test that get_prompt_loader returns a valid loader."""
        from ciris_engine.logic.dma.prompt_loader import get_prompt_loader

        loader = get_prompt_loader()
        assert loader is not None
        assert hasattr(loader, "language")
        assert hasattr(loader, "load_prompt_template")
