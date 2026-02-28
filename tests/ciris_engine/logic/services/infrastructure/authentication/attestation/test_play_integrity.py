"""Tests for Play Integrity verification module."""

import threading
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.services.infrastructure.authentication.attestation.play_integrity import (
    _verify_on_large_stack,
    get_verifier_or_error,
    run_play_integrity_verification,
)


class TestVerifyOnLargeStack:
    """Tests for _verify_on_large_stack function."""

    def test_returns_error_when_lib_missing(self):
        """Test error when verifier has no _lib attribute."""
        verifier = MagicMock(spec=[])
        result: dict = {}

        _verify_on_large_stack(verifier, "token", "nonce", result)

        assert result["error"] == "Play Integrity FFI not available (need CIRISVerify >= 0.10.0)"
        assert result["verified"] is False

    def test_returns_error_when_ffi_function_missing(self):
        """Test error when FFI function not available."""
        verifier = MagicMock()
        verifier._lib = MagicMock(spec=[])  # No ciris_verify_verify_integrity_token
        result: dict = {}

        _verify_on_large_stack(verifier, "token", "nonce", result)

        assert result["error"] == "Play Integrity FFI not available (need CIRISVerify >= 0.10.0)"
        assert result["verified"] is False

    def test_returns_error_when_handle_missing(self):
        """Test error when verifier handle not available."""
        verifier = MagicMock()
        verifier._lib = MagicMock()
        verifier._lib.ciris_verify_verify_integrity_token = MagicMock()
        verifier._handle = None
        result: dict = {}

        _verify_on_large_stack(verifier, "token", "nonce", result)

        assert result["error"] == "CIRISVerify handle not available"
        assert result["verified"] is False

    def test_returns_error_on_ffi_error_code(self):
        """Test error when FFI returns non-zero code."""
        verifier = MagicMock()
        verifier._lib = MagicMock()
        verifier._lib.ciris_verify_verify_integrity_token = MagicMock(return_value=1)
        verifier._handle = MagicMock()
        result: dict = {}

        _verify_on_large_stack(verifier, "token", "nonce", result)

        assert result["error"] == "FFI error code: 1"
        assert result["verified"] is False

    def test_handles_exception(self):
        """Test handling of exceptions during FFI call."""
        verifier = MagicMock()
        verifier._lib = MagicMock()
        verifier._lib.ciris_verify_verify_integrity_token = MagicMock(side_effect=Exception("FFI crash"))
        verifier._handle = MagicMock()
        result: dict = {}

        _verify_on_large_stack(verifier, "token", "nonce", result)

        assert "FFI crash" in result["error"]
        assert result["verified"] is False


class TestRunPlayIntegrityVerification:
    """Tests for run_play_integrity_verification function."""

    def test_runs_verification_in_thread(self):
        """Test that verification runs in a separate thread."""
        verifier = MagicMock(spec=[])

        result = run_play_integrity_verification(verifier, "token", "nonce", timeout_seconds=5)

        # Should return error since verifier has no _lib
        assert result["verified"] is False
        assert "FFI not available" in result["error"]

    def test_timeout_returns_error(self):
        """Test that timeout returns appropriate error."""
        verifier = MagicMock()
        verifier._lib = MagicMock()

        # Mock the FFI to hang
        def slow_ffi(*args, **kwargs):
            import time
            time.sleep(10)  # Sleep longer than timeout
            return 0

        verifier._lib.ciris_verify_verify_integrity_token = slow_ffi
        verifier._handle = MagicMock()

        # Use very short timeout
        result = run_play_integrity_verification(verifier, "token", "nonce", timeout_seconds=1)

        assert result["verified"] is False
        assert "timed out" in result["error"]

    def test_restores_stack_size_on_success(self):
        """Test that stack size is restored after successful verification."""
        verifier = MagicMock(spec=[])
        original_stack_size = threading.stack_size()

        run_play_integrity_verification(verifier, "token", "nonce", timeout_seconds=5)

        assert threading.stack_size() == original_stack_size

    def test_restores_stack_size_on_error(self):
        """Test that stack size is restored after error."""
        verifier = MagicMock()
        verifier._lib = MagicMock()
        verifier._lib.ciris_verify_verify_integrity_token = MagicMock(side_effect=Exception("Error"))
        verifier._handle = MagicMock()
        original_stack_size = threading.stack_size()

        run_play_integrity_verification(verifier, "token", "nonce", timeout_seconds=5)

        assert threading.stack_size() == original_stack_size


class TestGetVerifierOrError:
    """Tests for get_verifier_or_error function."""

    def test_returns_verifier_when_available(self):
        """Test returning verifier when available."""
        mock_verifier = MagicMock()

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=mock_verifier,
        ):
            verifier, error = get_verifier_or_error()

        assert verifier is mock_verifier
        assert error is None

    def test_returns_error_when_verifier_none(self):
        """Test returning error when verifier is None."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=None,
        ):
            verifier, error = get_verifier_or_error()

        assert verifier is None
        assert error is not None
        assert error["error"] == "CIRISVerify not initialized"
        assert error["verified"] is False

    def test_returns_error_on_exception(self):
        """Test returning error when get_verifier raises exception."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            side_effect=Exception("Import error"),
        ):
            verifier, error = get_verifier_or_error()

        assert verifier is None
        assert error is not None
        assert "CIRISVerify not available" in error["error"]
        assert "Import error" in error["error"]
        assert error["verified"] is False
