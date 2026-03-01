"""Tests for attestation types module."""

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation.types import (
    PythonHashesWrapper,
    VerifyThreadResult,
)


class TestPythonHashesWrapper:
    """Tests for PythonHashesWrapper."""

    def test_default_values(self):
        """Test default values for PythonHashesWrapper."""
        wrapper = PythonHashesWrapper()
        assert wrapper.total_hash == ""
        assert wrapper.module_hashes == {}
        assert wrapper.module_count == 0
        assert wrapper.agent_version == ""
        assert wrapper.computed_at == 0.0

    def test_from_dict(self):
        """Test creating wrapper from dictionary."""
        data = {
            "total_hash": "abc123",
            "module_hashes": {"module1": "hash1", "module2": "hash2"},
            "modules_hashed": 2,
            "agent_version": "1.0.0",
            "computed_at": 1234567890.0,
        }
        wrapper = PythonHashesWrapper.from_dict(data)
        assert wrapper.total_hash == "abc123"
        assert wrapper.module_hashes == {"module1": "hash1", "module2": "hash2"}
        assert wrapper.module_count == 2
        assert wrapper.agent_version == "1.0.0"
        assert wrapper.computed_at == 1234567890.0

    def test_from_dict_with_missing_keys(self):
        """Test creating wrapper from dictionary with missing keys."""
        data = {"total_hash": "abc123"}
        wrapper = PythonHashesWrapper.from_dict(data)
        assert wrapper.total_hash == "abc123"
        assert wrapper.module_hashes == {}
        assert wrapper.module_count == 0
        assert wrapper.agent_version == ""
        assert wrapper.computed_at == 0.0

    def test_from_empty_dict(self):
        """Test creating wrapper from empty dictionary."""
        wrapper = PythonHashesWrapper.from_dict({})
        assert wrapper.total_hash == ""
        assert wrapper.module_hashes == {}
        assert wrapper.module_count == 0


class TestVerifyThreadResult:
    """Tests for VerifyThreadResult."""

    def test_default_values(self):
        """Test default values for VerifyThreadResult."""
        result = VerifyThreadResult()
        assert result.result is None
        assert result.error is None
        assert result.success is False

    def test_with_result(self):
        """Test VerifyThreadResult with result data."""
        result = VerifyThreadResult(result={"version": "1.0.0"})
        assert result.result == {"version": "1.0.0"}
        assert result.error is None
        assert result.success is True

    def test_with_error(self):
        """Test VerifyThreadResult with error."""
        result = VerifyThreadResult(error="Something went wrong")
        assert result.result is None
        assert result.error == "Something went wrong"
        assert result.success is False

    def test_with_both_result_and_error(self):
        """Test that error takes precedence."""
        result = VerifyThreadResult(
            result={"version": "1.0.0"},
            error="Error occurred"
        )
        assert result.success is False  # Error takes precedence
