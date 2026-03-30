"""Tests for ACCORD constants and get_accord_text function.

Tests the ACCORD_MODE global setting and get_accord_text() centralized function
that controls which ACCORD version is used in DMA system prompts.

Note: Tests avoid reloading modules to prevent interference with parallel test execution.
"""

import os

import pytest


class TestAccordMode:
    """Tests for ACCORD_MODE configuration.

    Note: These tests check the current module state rather than reloading,
    to avoid interference with parallel test execution.
    """

    def test_accord_mode_is_valid_value(self):
        """ACCORD_MODE should be a valid mode string."""
        from ciris_engine.logic.utils.constants import ACCORD_MODE

        valid_modes = {"compressed", "full", "none"}
        assert ACCORD_MODE in valid_modes, f"ACCORD_MODE '{ACCORD_MODE}' not in {valid_modes}"

    def test_accord_mode_env_var_mechanism(self):
        """CIRIS_ACCORD_MODE env var mechanism should work via get_env_var."""
        from ciris_engine.logic.config.env_utils import get_env_var

        # Test that get_env_var returns correct default
        result = get_env_var("CIRIS_ACCORD_MODE", "compressed")
        assert result is not None

    def test_accord_mode_documented_default(self):
        """Default ACCORD_MODE should be 'compressed' per documentation."""
        # This tests the code's documented default, not runtime value
        # (runtime may be overridden by env var)
        from ciris_engine.logic.config.env_utils import get_env_var

        # Simulate what the default would be without env var
        if "CIRIS_ACCORD_MODE" not in os.environ:
            from ciris_engine.logic.utils.constants import ACCORD_MODE

            assert ACCORD_MODE == "compressed"
        else:
            # Env var is set, just verify it's valid
            pass


class TestAccordTextLoading:
    """Tests for ACCORD text file loading."""

    def test_accord_text_loads_full_polyglot(self):
        """ACCORD_TEXT should load the full polyglot file."""
        from ciris_engine.logic.utils.constants import ACCORD_TEXT

        # Should be loaded and non-empty
        assert ACCORD_TEXT is not None
        assert len(ACCORD_TEXT) > 0

        # Should be the large polyglot version (with guide appended)
        assert len(ACCORD_TEXT) > 50000  # Full polyglot is ~88KB+

    def test_accord_text_compressed_loads_polyglot_synthesis(self):
        """ACCORD_TEXT_COMPRESSED should load the polyglot synthesis."""
        from ciris_engine.logic.utils.constants import ACCORD_TEXT_COMPRESSED

        # Should be loaded and non-empty
        assert ACCORD_TEXT_COMPRESSED is not None
        assert len(ACCORD_TEXT_COMPRESSED) > 0

        # Should be the compressed version (~6-8KB)
        assert len(ACCORD_TEXT_COMPRESSED) < 15000
        assert len(ACCORD_TEXT_COMPRESSED) > 5000

        # Should contain polyglot marker
        assert "POLYGLOT" in ACCORD_TEXT_COMPRESSED

    def test_accord_text_compressed_contains_polyglot_characters(self):
        """Compressed ACCORD should preserve cross-cultural characters."""
        from ciris_engine.logic.utils.constants import ACCORD_TEXT_COMPRESSED

        # Should contain multiple scripts (polyglot synthesis)
        # Amharic
        assert "ጸጥተኛው" in ACCORD_TEXT_COMPRESSED or "የመግቢያ" in ACCORD_TEXT_COMPRESSED
        # Chinese
        assert "静寂" in ACCORD_TEXT_COMPRESSED or "门槛" in ACCORD_TEXT_COMPRESSED
        # Arabic
        assert "قبل" in ACCORD_TEXT_COMPRESSED or "السؤال" in ACCORD_TEXT_COMPRESSED

    def test_accord_text_compressed_contains_mcas(self):
        """Compressed ACCORD should contain MCAS case study."""
        from ciris_engine.logic.utils.constants import ACCORD_TEXT_COMPRESSED

        # MCAS is critical safety lesson - must be preserved
        assert "MCAS" in ACCORD_TEXT_COMPRESSED
        assert "346" in ACCORD_TEXT_COMPRESSED  # 346 lives lost


class TestGetAccordText:
    """Tests for get_accord_text() centralized function."""

    def test_get_accord_text_default_uses_accord_mode(self):
        """get_accord_text('default') should respect ACCORD_MODE setting."""
        from ciris_engine.logic.utils.constants import ACCORD_MODE, ACCORD_TEXT, ACCORD_TEXT_COMPRESSED, get_accord_text

        result = get_accord_text("default")

        if ACCORD_MODE == "compressed":
            assert result == ACCORD_TEXT_COMPRESSED
        elif ACCORD_MODE == "full":
            assert result == ACCORD_TEXT
        else:
            assert result == ""

    def test_get_accord_text_full_uses_accord_mode(self):
        """get_accord_text('full') should also respect ACCORD_MODE setting."""
        from ciris_engine.logic.utils.constants import ACCORD_MODE, ACCORD_TEXT, ACCORD_TEXT_COMPRESSED, get_accord_text

        result = get_accord_text("full")

        # "full" now respects the global mode, not always returning full
        if ACCORD_MODE == "compressed":
            assert result == ACCORD_TEXT_COMPRESSED
        elif ACCORD_MODE == "full":
            assert result == ACCORD_TEXT

    def test_get_accord_text_compressed_always_returns_compressed(self):
        """get_accord_text('compressed') should always return compressed version."""
        from ciris_engine.logic.utils.constants import ACCORD_TEXT_COMPRESSED, get_accord_text

        result = get_accord_text("compressed")
        assert result == ACCORD_TEXT_COMPRESSED

    def test_get_accord_text_force_full_bypasses_mode(self):
        """get_accord_text('force_full') should bypass ACCORD_MODE and return full."""
        from ciris_engine.logic.utils.constants import ACCORD_TEXT, get_accord_text

        result = get_accord_text("force_full")
        assert result == ACCORD_TEXT

    def test_get_accord_text_none_returns_empty(self):
        """get_accord_text('none') should return empty string."""
        from ciris_engine.logic.utils.constants import get_accord_text

        result = get_accord_text("none")
        assert result == ""

    def test_get_accord_text_unknown_mode_returns_empty(self):
        """Unknown mode should return empty string."""
        from ciris_engine.logic.utils.constants import get_accord_text

        result = get_accord_text("unknown_mode")
        assert result == ""

    def test_get_accord_text_size_difference(self):
        """Compressed should be significantly smaller than full."""
        from ciris_engine.logic.utils.constants import get_accord_text

        full_size = len(get_accord_text("force_full"))
        compressed_size = len(get_accord_text("compressed"))

        # Compressed should be at least 10x smaller
        assert full_size > compressed_size * 10


class TestAccordModeIntegration:
    """Integration tests for ACCORD mode with DMAs."""

    def test_accord_mode_compressed_saves_tokens(self):
        """Using compressed mode should significantly reduce token count."""
        from ciris_engine.logic.utils.constants import get_accord_text

        full_text = get_accord_text("force_full")
        compressed_text = get_accord_text("compressed")

        # Rough token estimate (4 chars per token)
        full_tokens = len(full_text) / 4
        compressed_tokens = len(compressed_text) / 4

        # Should save at least 80% of tokens
        savings_pct = (full_tokens - compressed_tokens) / full_tokens * 100
        assert savings_pct > 80, f"Token savings {savings_pct:.1f}% should be > 80%"

    def test_accord_exports_available(self):
        """All ACCORD constants should be exported from utils module."""
        from ciris_engine.logic.utils import ACCORD_MODE, ACCORD_TEXT, ACCORD_TEXT_COMPRESSED, get_accord_text

        assert ACCORD_MODE is not None
        assert ACCORD_TEXT is not None
        assert ACCORD_TEXT_COMPRESSED is not None
        assert callable(get_accord_text)
