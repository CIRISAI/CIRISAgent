"""
Regression test for CIRISAgent#849 — SDK credential file permissions.

API keys and refresh tokens are persisted to ~/.ciris/auth.json in plaintext;
the file must never be created world-readable, even transiently (TOCTOU).
"""

import os
import stat
import sys

import pytest

from ciris_sdk.auth_store import AuthStore


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file-mode semantics")
def test_auth_file_is_owner_only(tmp_path):
    """The persisted auth.json must be 0600 (owner read/write only)."""
    auth_file = tmp_path / ".ciris" / "auth.json"
    store = AuthStore(auth_file=auth_file)
    store.store_api_key("super-secret-key", "https://example.test")

    assert auth_file.exists()
    mode = stat.S_IMODE(os.stat(auth_file).st_mode)
    assert mode == 0o600, f"auth.json mode {oct(mode)} exposes secrets; expected 0o600"

    # No stray world/group-readable temp file left behind either.
    leftovers = list(auth_file.parent.glob("*.tmp"))
    assert not leftovers, f"temp file not cleaned up: {leftovers}"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file-mode semantics")
def test_auth_dir_is_owner_only(tmp_path):
    """The ~/.ciris dir should be created 0700."""
    sub = tmp_path / ".ciris"
    store = AuthStore(auth_file=sub / "auth.json")
    store.store_api_key("k", "https://example.test")
    mode = stat.S_IMODE(os.stat(sub).st_mode)
    assert mode == 0o700, f"auth dir mode {oct(mode)} too permissive; expected 0o700"
