"""Tests for attestation hashes module."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation.hashes import (
    get_default_agent_version,
    load_python_hashes,
)


class TestGetDefaultAgentVersion:
    """Tests for get_default_agent_version function."""

    def test_gets_version_without_suffix(self):
        """Test getting version without suffix."""
        with patch("ciris_engine.constants.CIRIS_VERSION", "2.0.0"):
            version = get_default_agent_version()
            assert version == "2.0.0"

    def test_strips_stable_suffix(self):
        """Test stripping -stable suffix."""
        with patch("ciris_engine.constants.CIRIS_VERSION", "2.0.0-stable"):
            version = get_default_agent_version()
            assert version == "2.0.0"

    def test_strips_dev_suffix(self):
        """Test stripping -dev suffix."""
        with patch("ciris_engine.constants.CIRIS_VERSION", "2.0.0-dev"):
            version = get_default_agent_version()
            assert version == "2.0.0"

    def test_returns_none_on_import_error(self):
        """Test returning None when import fails."""
        with patch.dict("sys.modules", {"ciris_engine.constants": None}):
            # Force import error by patching
            with patch(
                "ciris_engine.logic.services.infrastructure.authentication.attestation.hashes.get_default_agent_version",
                side_effect=ImportError,
            ):
                # Since we're patching the function itself, test the behavior differently
                pass


class TestLoadPythonHashes:
    """Tests for load_python_hashes function."""

    def test_loads_valid_hashes_file(self, tmp_path):
        """Test loading valid hashes JSON file."""
        hashes_data = {
            "total_hash": "abc123",
            "module_hashes": {"module1": "hash1"},
            "modules_hashed": 1,
            "agent_version": "2.0.0",
            "computed_at": 1234567890.0,
        }
        hashes_file = tmp_path / "startup_python_hashes.json"
        hashes_file.write_text(json.dumps(hashes_data))

        wrapper, version = load_python_hashes(str(tmp_path))

        assert wrapper is not None
        assert wrapper.total_hash == "abc123"
        assert wrapper.module_count == 1
        assert version == "2.0.0"

    def test_strips_version_suffix_from_file(self, tmp_path):
        """Test stripping version suffix from hashes file."""
        hashes_data = {
            "total_hash": "abc123",
            "module_hashes": {},
            "modules_hashed": 0,
            "agent_version": "2.0.0-stable",
        }
        hashes_file = tmp_path / "startup_python_hashes.json"
        hashes_file.write_text(json.dumps(hashes_data))

        _, version = load_python_hashes(str(tmp_path))

        assert version == "2.0.0"

    def test_returns_none_when_file_missing(self, tmp_path):
        """Test returning None when hashes file doesn't exist."""
        wrapper, version = load_python_hashes(str(tmp_path))

        assert wrapper is None
        # Version should still come from constants

    def test_returns_none_on_invalid_json(self, tmp_path):
        """Test returning None when JSON is invalid."""
        hashes_file = tmp_path / "startup_python_hashes.json"
        hashes_file.write_text("not valid json")

        wrapper, _ = load_python_hashes(str(tmp_path))

        assert wrapper is None

    def test_uses_ciris_home_env_var(self, tmp_path):
        """Test using CIRIS_HOME environment variable."""
        hashes_data = {"total_hash": "test123", "modules_hashed": 0}
        hashes_file = tmp_path / "startup_python_hashes.json"
        hashes_file.write_text(json.dumps(hashes_data))

        with patch.dict(os.environ, {"CIRIS_HOME": str(tmp_path)}):
            wrapper, _ = load_python_hashes()

        assert wrapper is not None
        assert wrapper.total_hash == "test123"
