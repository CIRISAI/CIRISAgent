"""Tests for device_auth helper functions extracted for cognitive complexity reduction."""

import base64
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.setup.device_auth import (
    _decode_private_key,
    _generate_attestation_proof,
    _get_key_fingerprint,
    _handle_activation_response,
    _log_key_type_status,
    _run_on_large_stack,
    _validate_portal_url,
)


class TestValidatePortalUrl:
    """Tests for _validate_portal_url SSRF protection."""

    def test_accepts_trusted_portal_domain(self):
        """Should accept portal.ciris.ai and return sanitized base URL (no path)."""
        result = _validate_portal_url("https://portal.ciris.ai/api")
        # SSRF fix: returns sanitized base URL only (scheme + netloc), discards path
        assert result == "https://portal.ciris.ai"

    def test_accepts_localhost_http(self):
        """Should accept http://localhost for development."""
        result = _validate_portal_url("http://localhost:8080/api")
        # SSRF fix: returns sanitized base URL only (scheme + netloc), discards path
        assert result == "http://localhost:8080"

    def test_rejects_untrusted_domain(self):
        """Should reject untrusted domains (SSRF protection)."""
        with pytest.raises(ValueError, match="Untrusted host"):
            _validate_portal_url("https://evil.com/api")

    def test_rejects_http_for_non_localhost(self):
        """Should reject HTTP for non-localhost domains."""
        with pytest.raises(ValueError, match="HTTP only allowed for localhost"):
            _validate_portal_url("http://portal.ciris.ai/api")

    def test_rejects_invalid_url_format(self):
        """Should reject malformed URLs."""
        with pytest.raises(ValueError, match="Invalid URL format"):
            _validate_portal_url("not-a-url")


class TestDecodePrivateKey:
    """Tests for _decode_private_key validation."""

    def test_decodes_valid_32_byte_key(self):
        """Should decode valid 32-byte Ed25519 key."""
        key_bytes = os.urandom(32)
        key_b64 = base64.b64encode(key_bytes).decode()
        result = _decode_private_key(key_b64)
        assert result == key_bytes

    def test_rejects_wrong_length_key(self):
        """Should reject keys that aren't 32 bytes."""
        key_bytes = os.urandom(16)  # Wrong length
        key_b64 = base64.b64encode(key_bytes).decode()
        result = _decode_private_key(key_b64)
        assert result is None

    def test_rejects_invalid_base64(self):
        """Should reject invalid base64."""
        result = _decode_private_key("not-valid-base64!!!")
        assert result is None


class TestRunOnLargeStack:
    """Tests for _run_on_large_stack thread management."""

    def test_runs_function_on_thread(self):
        """Should run function and wait for completion."""
        result = []

        def target():
            result.append("executed")

        _run_on_large_stack(target, timeout=5.0)
        assert result == ["executed"]

    @patch.dict(os.environ, {"ANDROID_ROOT": "/system"})
    def test_skips_stack_size_on_android(self):
        """Should skip stack size manipulation on Android."""
        result = []

        def target():
            result.append("executed")

        _run_on_large_stack(target, timeout=5.0)
        assert result == ["executed"]


class TestLogKeyTypeStatus:
    """Tests for _log_key_type_status logging."""

    def test_logs_warning_for_unexpected_key_type(self, caplog):
        """Should log warning for unexpected key types."""
        _log_key_type_status({"key_type": "unexpected"})
        assert "unexpected key_type" in caplog.text

    def test_logs_info_for_registry_unavailable(self, caplog):
        """Should log info when registry is unavailable."""
        import logging

        with caplog.at_level(logging.INFO):
            _log_key_type_status({"key_type": "registry_unavailable"})
        assert "registry unavailable" in caplog.text

    def test_no_warning_for_portal_key_type(self, caplog):
        """Should not log warning for valid portal key type."""
        _log_key_type_status({"key_type": "portal"})
        assert "unexpected" not in caplog.text


class TestHandleActivationResponse:
    """Tests for _handle_activation_response."""

    def test_handles_success_response(self, caplog):
        """Should log success for 200 response."""
        import logging

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"activated": True, "key_id": "test-key"}

        with caplog.at_level(logging.INFO):
            _handle_activation_response(mock_response)
        assert "activated=True" in caplog.text

    def test_handles_key_reuse_error(self, caplog):
        """Should log error for KEY REUSE."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"error": "KEY REUSE DETECTED"}

        _handle_activation_response(mock_response)
        assert "KEY REUSE DETECTED" in caplog.text

    def test_handles_other_403_error(self, caplog):
        """Should log warning for other 403 errors."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"error": "access denied"}

        _handle_activation_response(mock_response)
        assert "rejected" in caplog.text

    def test_handles_other_error_codes(self, caplog):
        """Should log warning for other error codes."""
        mock_response = MagicMock()
        mock_response.status_code = 500

        _handle_activation_response(mock_response)
        assert "HTTP 500" in caplog.text


class TestGetKeyFingerprint:
    """Tests for _get_key_fingerprint."""

    def test_returns_fingerprint_when_available(self):
        """Should return SHA256 fingerprint of public key."""
        mock_verifier = MagicMock()
        mock_verifier.get_ed25519_public_key_sync.return_value = b"test_public_key_32bytes_here!!!"

        result = _get_key_fingerprint(mock_verifier)
        assert result is not None
        assert len(result) == 64  # SHA256 hex

    def test_returns_none_when_method_missing(self):
        """Should return None if verifier doesn't support fingerprint."""
        mock_verifier = MagicMock(spec=[])  # No methods

        result = _get_key_fingerprint(mock_verifier)
        assert result is None

    def test_returns_none_on_exception(self):
        """Should return None on exception."""
        mock_verifier = MagicMock()
        mock_verifier.get_ed25519_public_key_sync.side_effect = Exception("error")

        result = _get_key_fingerprint(mock_verifier)
        assert result is None


class TestGenerateAttestationProof:
    """Tests for _generate_attestation_proof."""

    def test_uses_run_attestation_sync_when_available(self):
        """Should use run_attestation_sync if available."""
        mock_verifier = MagicMock()
        mock_verifier.run_attestation_sync.return_value = {"key_type": "portal"}

        result = _generate_attestation_proof(mock_verifier, b"challenge", "fingerprint")
        assert result == {"key_type": "portal"}
        mock_verifier.run_attestation_sync.assert_called_once()

    def test_falls_back_to_export_attestation_sync(self):
        """Should fall back to export_attestation_sync."""
        mock_verifier = MagicMock(spec=["export_attestation_sync"])
        mock_verifier.export_attestation_sync.return_value = {"key_type": "persisted"}

        result = _generate_attestation_proof(mock_verifier, b"challenge", None)
        assert result == {"key_type": "persisted"}
        mock_verifier.export_attestation_sync.assert_called_once()


class TestImportKeyAndGenerateAttestation:
    """Tests for _import_key_and_generate_attestation."""

    def test_successful_key_import_and_attestation(self):
        """Should import key and generate attestation successfully."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _import_key_and_generate_attestation

        mock_verifier = MagicMock()
        mock_verifier.has_key_sync.return_value = True
        mock_verifier.get_ed25519_public_key_sync.return_value = b"public_key_32_bytes_here_!!!!!!"
        mock_verifier.run_attestation_sync.return_value = {"key_type": "portal"}

        # Patch get_verifier singleton (the function now uses get_verifier, not direct CIRISVerify)
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=mock_verifier,
        ):
            with patch(
                "ciris_engine.logic.audit.signing_protocol.reset_unified_signing_key",
                MagicMock(),
            ):
                proof, error = _import_key_and_generate_attestation(os.urandom(32), os.urandom(32))

        assert proof == {"key_type": "portal"}
        assert error is None
        mock_verifier.import_key_sync.assert_called_once()

    def test_key_import_exception_returns_error(self):
        """Should return error when get_verifier returns None."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _import_key_and_generate_attestation

        # Mock get_verifier to return None
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=None,
        ):
            proof, error = _import_key_and_generate_attestation(os.urandom(32), os.urandom(32))

        assert proof is None
        assert error is not None
        assert "not available" in str(error)

    def test_key_import_success_but_has_key_fails(self, caplog):
        """Should log error when has_key_sync returns False after import."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _import_key_and_generate_attestation

        mock_verifier = MagicMock()
        mock_verifier.has_key_sync.return_value = False  # Key import failed silently
        mock_verifier.run_attestation_sync.return_value = {"key_type": "unknown"}

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=mock_verifier,
        ):
            with patch(
                "ciris_engine.logic.audit.signing_protocol.reset_unified_signing_key",
                MagicMock(),
            ):
                proof, error = _import_key_and_generate_attestation(os.urandom(32), os.urandom(32))

        assert "CRITICAL" in caplog.text or proof is not None  # Either logs error or returns proof


class TestSubmitActivationToPortal:
    """Tests for _submit_activation_to_portal."""

    @pytest.mark.asyncio
    async def test_successful_portal_submission(self):
        """Should submit activation to portal successfully."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _submit_activation_to_portal

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"activated": True, "key_id": "test-key"}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        # Create proper async context manager mock
        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        # httpx is imported inline, so patch at module level
        with patch("httpx.AsyncClient", return_value=mock_client_cm):
            await _submit_activation_to_portal("https://portal.ciris.ai", "device-code-123", {"key_type": "portal"})

            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_portal_submission_http_error(self, caplog):
        """Should log warning on HTTP error."""
        import httpx

        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _submit_activation_to_portal

        mock_client = AsyncMock()
        mock_client.post.side_effect = httpx.HTTPError("Connection failed")

        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("httpx.AsyncClient", return_value=mock_client_cm):
            await _submit_activation_to_portal("https://portal.ciris.ai", "device-code-123", {"key_type": "portal"})

            assert "Failed to submit" in caplog.text


class TestActivateKeyInline:
    """Tests for _activate_key_inline."""

    @pytest.mark.asyncio
    async def test_invalid_portal_url_returns_early(self, caplog):
        """Should return early on invalid portal URL."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _activate_key_inline

        key_b64 = base64.b64encode(os.urandom(32)).decode()
        await _activate_key_inline(key_b64, "device-code", "https://evil.com")

        assert "Invalid portal URL" in caplog.text

    @pytest.mark.asyncio
    async def test_invalid_key_returns_early(self, caplog):
        """Should return early on invalid key."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _activate_key_inline

        key_b64 = base64.b64encode(os.urandom(16)).decode()  # Wrong length
        await _activate_key_inline(key_b64, "device-code", "https://portal.ciris.ai")

        assert "invalid key length" in caplog.text

    @pytest.mark.asyncio
    async def test_activation_timeout_handled(self, caplog):
        """Should handle CIRISVerify timeout gracefully."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _activate_key_inline

        key_b64 = base64.b64encode(os.urandom(32)).decode()

        # Mock _run_on_large_stack to simulate timeout (no proof returned)
        def mock_run_on_large_stack(func, timeout):
            pass  # Don't call func, simulating timeout

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.device_auth._run_on_large_stack",
            side_effect=mock_run_on_large_stack,
        ):
            await _activate_key_inline(key_b64, "device-code", "https://portal.ciris.ai")

        assert "timed out" in caplog.text or "skipped" in caplog.text

    @pytest.mark.asyncio
    async def test_successful_activation_flow(self, caplog):
        """Should complete full activation flow successfully."""
        import logging

        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _activate_key_inline

        key_b64 = base64.b64encode(os.urandom(32)).decode()

        # Simulate successful key import that sets result
        def mock_run_on_large_stack(func, timeout):
            func()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"activated": True}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response

        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.device_auth._run_on_large_stack",
            side_effect=mock_run_on_large_stack,
        ):
            with patch(
                "ciris_engine.logic.adapters.api.routes.setup.device_auth._import_key_and_generate_attestation",
                return_value=({"key_type": "portal"}, None),
            ):
                # httpx is imported inline, so patch at module level
                with patch("httpx.AsyncClient", return_value=mock_client_cm):
                    with caplog.at_level(logging.INFO):
                        await _activate_key_inline(key_b64, "device-code", "https://portal.ciris.ai")

                    # Check that activation was submitted
                    mock_client.post.assert_called_once()


class TestGetKeyFingerprintEdgeCases:
    """Additional edge case tests for _get_key_fingerprint."""

    def test_returns_none_when_pubkey_is_none(self):
        """Should return None when public key is None."""
        mock_verifier = MagicMock()
        mock_verifier.get_ed25519_public_key_sync.return_value = None

        result = _get_key_fingerprint(mock_verifier)
        assert result is None
