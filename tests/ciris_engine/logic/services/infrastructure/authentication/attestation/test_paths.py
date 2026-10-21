"""Tests for attestation paths module."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation.paths import (
    AUDIT_DB_FILENAME,
    find_audit_db_path,
    get_agent_root,
    get_audit_db_search_paths,
    get_ed25519_fingerprint,
)


class TestGetAgentRoot:
    """Tests for get_agent_root function."""

    def test_desktop_uses_env_var(self):
        """Test desktop mode uses CIRIS_AGENT_ROOT env var."""
        env = os.environ.copy()
        env.pop("ANDROID_ROOT", None)
        env.pop("CIRIS_IOS_FRAMEWORK_PATH", None)
        env.pop("CIRIS_IOS_STATIC_LINK", None)
        env["CIRIS_AGENT_ROOT"] = "/custom/agent/root"

        with patch.dict(os.environ, env, clear=True):
            assert get_agent_root() == "/custom/agent/root"

    def test_desktop_uses_cwd_when_no_env(self):
        """Test desktop mode uses cwd when env var not set."""
        env = os.environ.copy()
        env.pop("ANDROID_ROOT", None)
        env.pop("CIRIS_IOS_FRAMEWORK_PATH", None)
        env.pop("CIRIS_IOS_STATIC_LINK", None)
        env.pop("CIRIS_AGENT_ROOT", None)

        with patch.dict(os.environ, env, clear=True):
            assert get_agent_root() == os.getcwd()

    def test_mobile_uses_package_path(self):
        """Test mobile mode uses Python package path."""
        with patch.dict(os.environ, {"ANDROID_ROOT": "/system"}):
            with patch(
                "ciris_engine.logic.services.infrastructure.authentication.attestation.paths.is_mobile",
                return_value=True,
            ):
                # The actual implementation would use ciris_engine.__file__
                root = get_agent_root()
                # Should not be empty
                assert root


class TestGetAuditDbSearchPaths:
    """Tests for get_audit_db_search_paths function."""

    def test_returns_expected_paths(self):
        """Test that expected paths are returned."""
        paths = get_audit_db_search_paths("/ciris/home")

        assert len(paths) == 6
        assert Path("/ciris/home/data") / AUDIT_DB_FILENAME in paths
        assert Path("/ciris/home") / AUDIT_DB_FILENAME in paths

    def test_includes_android_paths(self):
        """Test that Android-specific paths are included."""
        paths = get_audit_db_search_paths("/ciris/home")

        android_path = Path("/data/user/0/ai.ciris.mobile/files/ciris/data") / AUDIT_DB_FILENAME
        assert android_path in paths


class TestFindAuditDbPath:
    """Tests for find_audit_db_path function."""

    def test_finds_existing_db(self, tmp_path):
        """Test finding an existing audit database."""
        db_path = tmp_path / "data" / AUDIT_DB_FILENAME
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.touch()

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.attestation.paths.get_audit_db_search_paths",
            return_value=[db_path],
        ):
            result = find_audit_db_path(str(tmp_path))

        assert result == str(db_path)

    def test_returns_none_when_not_found(self, tmp_path):
        """Test returning None when no database found."""
        # Use a non-existent directory as CIRIS_HOME to avoid finding real audit.db
        nonexistent_dir = tmp_path / "nonexistent_subdir"
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.attestation.paths.get_audit_db_search_paths",
            return_value=[nonexistent_dir / "audit.db"],
        ):
            result = find_audit_db_path(str(nonexistent_dir))
        assert result is None

    def test_uses_ciris_home_env(self, tmp_path):
        """Test using CIRIS_HOME environment variable."""
        with patch.dict(os.environ, {"CIRIS_HOME": str(tmp_path)}):
            result = find_audit_db_path()
            # Should not error, just return None if not found
            assert result is None or isinstance(result, str)


class TestGetEd25519Fingerprint:
    """Tests for get_ed25519_fingerprint function."""

    def test_gets_fingerprint_from_verifier(self):
        """Test getting fingerprint from verifier."""
        mock_verifier = MagicMock()
        mock_verifier.get_ed25519_public_key_sync.return_value = b"test_public_key"

        fingerprint = get_ed25519_fingerprint(mock_verifier)

        assert fingerprint is not None
        assert len(fingerprint) == 64  # SHA256 hex = 64 chars

    def test_returns_none_when_no_key(self):
        """Test returning None when verifier has no key."""
        mock_verifier = MagicMock()
        mock_verifier.get_ed25519_public_key_sync.return_value = None

        fingerprint = get_ed25519_fingerprint(mock_verifier)

        assert fingerprint is None

    def test_returns_none_when_method_missing(self):
        """Test returning None when method doesn't exist."""
        mock_verifier = MagicMock(spec=[])  # No methods

        fingerprint = get_ed25519_fingerprint(mock_verifier)

        assert fingerprint is None

    def test_handles_exception(self):
        """Test handling exception from verifier."""
        mock_verifier = MagicMock()
        mock_verifier.get_ed25519_public_key_sync.side_effect = Exception("FFI error")

        fingerprint = get_ed25519_fingerprint(mock_verifier)

        assert fingerprint is None
