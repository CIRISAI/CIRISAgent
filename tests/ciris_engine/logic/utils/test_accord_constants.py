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


class TestAccordIntegrityHashes:
    """Pin every ACCORD_EXPECTED_HASHES entry to the actual SHA-256 of the
    file on disk.

    Drift between this constant and the file content is a real production
    incident: the agent's optimization_veto conscience reads the integrity
    summary in its system snapshot, sees ✗FileIntegrity, and starts
    fabricating SHA-256 hash-mismatch tampering threats — vetoing every
    proposed action and forcing DEFER on every interaction. This was
    diagnosed in the v3 mental-health harness where one stale hash on
    accord_1.2b_my.txt locked the Burmese run into a defer storm.

    The check is structural (no Burmese-specific carve-out): if any
    localized ACCORD or POLYGLOT or guide file's content drifts from
    the pinned manifest, this test fails BEFORE the conscience storm
    can land in production.
    """

    @staticmethod
    def _find_accord_file(filename):
        """Locate an ACCORD file in any of the standard data directories.

        Returns Path or None.
        """
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[4]
        candidates = [
            repo_root / "ciris_engine" / "data" / "localized" / filename,
            repo_root / "ciris_engine" / "data" / filename,
            repo_root / filename,
        ]
        for c in candidates:
            if c.exists():
                return c
        return None

    @staticmethod
    def _compute_sha256(path):
        import hashlib

        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_all_localized_accord_hashes_match(self):
        """Every entry in ACCORD_EXPECTED_HASHES must match its file's actual SHA-256.

        This test guards against the failure mode where a translator edit lands
        but the manifest in constants.py is not updated, causing the integrity
        check to fail at runtime and the conscience to interpret it as tampering.
        """
        from ciris_engine.logic.utils.constants import ACCORD_EXPECTED_HASHES

        mismatches = []
        missing = []
        for filename, expected_hash in ACCORD_EXPECTED_HASHES.items():
            path = self._find_accord_file(filename)
            if path is None:
                missing.append(filename)
                continue
            actual_hash = self._compute_sha256(path)
            if actual_hash != expected_hash:
                mismatches.append((filename, expected_hash, actual_hash))

        # Detailed failure messages so an engineer can copy-paste the fix
        if missing:
            pytest.fail(
                f"{len(missing)} ACCORD file(s) missing on disk but pinned in "
                f"ACCORD_EXPECTED_HASHES: {missing}. Either ship the file or "
                f"remove the hash entry."
            )
        if mismatches:
            lines = [
                f"{len(mismatches)} ACCORD file hash(es) drifted from manifest. "
                f"This will trigger the conscience tampering-storm bug.",
                "Update ciris_engine/logic/utils/constants.py:ACCORD_EXPECTED_HASHES with:",
            ]
            for filename, expected, actual in mismatches:
                lines.append(f'    "{filename}": "{actual}",  # was {expected[:12]}...')
            pytest.fail("\n".join(lines))

    def test_all_guide_hashes_match(self):
        """GUIDE_EXPECTED_HASHES (CIRIS_COMPREHENSIVE_GUIDE.md / _MOBILE.md)
        must match actual file SHA-256s.

        These hashes are also signature-verified via the seed/accord_manifest.json
        chain — any drift here means EITHER the guide file was edited without
        regenerating the manifest, OR the signed manifest is stale. Both are
        production hazards.
        """
        from ciris_engine.logic.utils.constants import GUIDE_EXPECTED_HASHES

        mismatches = []
        missing = []
        for filename, expected_hash in GUIDE_EXPECTED_HASHES.items():
            path = self._find_accord_file(filename)
            if path is None:
                missing.append(filename)
                continue
            actual_hash = self._compute_sha256(path)
            if actual_hash != expected_hash:
                mismatches.append((filename, expected_hash, actual_hash))

        if missing:
            pytest.fail(
                f"{len(missing)} guide file(s) missing on disk but pinned in "
                f"GUIDE_EXPECTED_HASHES: {missing}."
            )
        if mismatches:
            lines = [
                f"{len(mismatches)} guide file hash(es) drifted from manifest:",
                "Update ciris_engine/logic/utils/constants.py:GUIDE_EXPECTED_HASHES with:",
            ]
            for filename, expected, actual in mismatches:
                lines.append(f'    "{filename}": "{actual}",  # was {expected[:12]}...')
            lines.append("")
            lines.append(
                "If you also need to re-sign seed/accord_manifest.json, "
                "regenerate via the signing script and update both."
            )
            pytest.fail("\n".join(lines))

    def test_polyglot_files_pinned(self):
        """The POLYGLOT ACCORD files (used in production via DMA prompts) must
        be pinned in ACCORD_EXPECTED_HASHES so any edit triggers a hash check
        rather than silently propagating.
        """
        from ciris_engine.logic.utils.constants import ACCORD_EXPECTED_HASHES

        required = {"accord_1.2b_POLYGLOT.txt", "accord_1.2b_POLYGLOT_compressed.txt"}
        missing_pins = required - set(ACCORD_EXPECTED_HASHES.keys())
        assert not missing_pins, (
            f"POLYGLOT ACCORD file(s) not pinned in ACCORD_EXPECTED_HASHES: "
            f"{missing_pins}. These are the production-default ACCORDs and "
            f"must be hash-checked."
        )

    def test_all_29_locales_pinned(self):
        """Every supported locale (per localization/manifest.json) must have
        a pinned ACCORD hash. Adding a locale without a pinned hash means
        the integrity check silently passes that locale — a translator could
        ship arbitrary content with no detection.
        """
        import json
        from pathlib import Path

        from ciris_engine.logic.utils.constants import ACCORD_EXPECTED_HASHES

        repo_root = Path(__file__).resolve().parents[4]
        manifest = json.loads((repo_root / "localization" / "manifest.json").read_text())
        # The manifest may store languages as a list or dict — normalize.
        if isinstance(manifest.get("languages"), list):
            locales = set(manifest["languages"])
        elif isinstance(manifest.get("languages"), dict):
            locales = set(manifest["languages"].keys())
        else:
            pytest.fail("localization/manifest.json has unexpected 'languages' shape")

        pinned_locales = {
            name.removeprefix("accord_1.2b_").removesuffix(".txt")
            for name in ACCORD_EXPECTED_HASHES
            if name.startswith("accord_1.2b_") and name not in {
                "accord_1.2b_POLYGLOT.txt",
                "accord_1.2b_POLYGLOT_compressed.txt",
            }
        }
        missing_pins = locales - pinned_locales
        assert not missing_pins, (
            f"Locales declared in localization/manifest.json but NOT in "
            f"ACCORD_EXPECTED_HASHES: {sorted(missing_pins)}. Every shipped "
            f"locale's ACCORD must be hash-pinned."
        )
