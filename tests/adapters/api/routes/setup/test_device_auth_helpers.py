"""Tests for device_auth helper functions - Self-Custody Key Registration (FSD-002).

These tests verify the self-custody key management flow where:
- Agent generates its own Ed25519 keypair via CIRISVerify
- Private key is TPM-protected and NEVER leaves the agent
- Only the PUBLIC key is registered with Portal
- Portal NEVER issues or receives private keys
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.setup.device_auth import (
    _get_public_key_from_verifier,
    _run_on_large_stack,
    _sign_with_verifier,
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


class TestGetPublicKeyFromVerifier:
    """Tests for _get_public_key_from_verifier (self-custody)."""

    def test_returns_public_key_when_available(self):
        """Should return public key from CIRISVerify."""
        mock_verifier = MagicMock()
        test_pubkey = b"public_key_32_bytes_here_!!!!!!"
        mock_verifier.get_ed25519_public_key_sync.return_value = test_pubkey

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=mock_verifier,
        ):
            pubkey, error = _get_public_key_from_verifier()

        assert pubkey == test_pubkey
        assert error is None

    def test_returns_error_when_verifier_unavailable(self):
        """Should return error when CIRISVerify singleton not available."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=None,
        ):
            pubkey, error = _get_public_key_from_verifier()

        assert pubkey is None
        assert error is not None
        assert "not available" in str(error)

    def test_returns_error_when_no_public_key(self):
        """Should return error when no public key available."""
        mock_verifier = MagicMock()
        mock_verifier.get_ed25519_public_key_sync.return_value = None

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=mock_verifier,
        ):
            pubkey, error = _get_public_key_from_verifier()

        assert pubkey is None
        assert error is not None
        assert "No Ed25519 public key" in str(error)


class TestSignWithVerifier:
    """Tests for _sign_with_verifier (self-custody signing)."""

    def test_signs_message_successfully(self):
        """Should sign message using CIRISVerify."""
        mock_verifier = MagicMock()
        test_signature = b"signature_64_bytes_here_abcdefgh" * 2
        mock_verifier.sign_ed25519_sync.return_value = test_signature

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=mock_verifier,
        ):
            signature, error = _sign_with_verifier(b"test message")

        assert signature == test_signature
        assert error is None
        mock_verifier.sign_ed25519_sync.assert_called_once_with(b"test message")

    def test_returns_error_when_verifier_unavailable(self):
        """Should return error when CIRISVerify singleton not available."""
        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=None,
        ):
            signature, error = _sign_with_verifier(b"test message")

        assert signature is None
        assert error is not None
        assert "not available" in str(error)

    def test_returns_error_when_sign_sync_missing(self):
        """Should return error when sign_ed25519_sync method not available."""
        mock_verifier = MagicMock(spec=[])  # No methods

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier",
            return_value=mock_verifier,
        ):
            signature, error = _sign_with_verifier(b"test message")

        assert signature is None
        assert error is not None
        assert "sign_ed25519_sync not available" in str(error)


class TestRegisterSelfCustodyKey:
    """Tests for _register_self_custody_key (FSD-002 flow)."""

    @pytest.mark.asyncio
    async def test_invalid_portal_url_returns_none(self, caplog):
        """Should return None on invalid portal URL."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _register_self_custody_key

        result = await _register_self_custody_key("device-code", "https://evil.com")

        assert result is None
        assert "Invalid portal URL" in caplog.text

    @pytest.mark.asyncio
    async def test_returns_none_when_public_key_unavailable(self, caplog):
        """Should return None when public key cannot be retrieved."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _register_self_custody_key

        def mock_run_on_large_stack(func, timeout):
            func()

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.device_auth._run_on_large_stack",
            side_effect=mock_run_on_large_stack,
        ):
            with patch(
                "ciris_engine.logic.adapters.api.routes.setup.device_auth._get_public_key_from_verifier",
                return_value=(None, RuntimeError("CIRISVerify not available")),
            ):
                result = await _register_self_custody_key("device-code", "https://portal.ciris.ai")

        assert result is None
        assert "Key registration skipped" in caplog.text

    @pytest.mark.asyncio
    async def test_returns_none_when_signing_fails(self, caplog):
        """Should return None when registration signing fails."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _register_self_custody_key

        def mock_run_on_large_stack(func, timeout):
            func()

        call_count = [0]

        def mock_get_public_key():
            return b"test_public_key_32_bytes_here!!", None

        def mock_sign(msg):
            # First call succeeds, simulating we get the key
            call_count[0] += 1
            if call_count[0] == 1:
                return None, RuntimeError("Signing failed")
            return None, RuntimeError("Signing failed")

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.device_auth._run_on_large_stack",
            side_effect=mock_run_on_large_stack,
        ):
            with patch(
                "ciris_engine.logic.adapters.api.routes.setup.device_auth._get_public_key_from_verifier",
                return_value=(b"test_public_key_32_bytes_here!!", None),
            ):
                with patch(
                    "ciris_engine.logic.adapters.api.routes.setup.device_auth._sign_with_verifier",
                    return_value=(None, RuntimeError("Signing failed")),
                ):
                    result = await _register_self_custody_key("device-code", "https://portal.ciris.ai")

        assert result is None
        assert "Registration signing failed" in caplog.text

    @pytest.mark.asyncio
    async def test_successful_registration_flow(self, caplog):
        """Should complete full self-custody registration flow successfully."""
        import logging

        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _register_self_custody_key

        def mock_run_on_large_stack(func, timeout):
            func()

        # Mock successful Portal responses
        mock_register_response = MagicMock()
        mock_register_response.status_code = 200
        mock_register_response.json.return_value = {
            "key_id": "test-key-id",
            "activation_challenge": "0102030405060708",
            "public_key_fingerprint": "abc123",
        }
        mock_register_response.headers = {"content-type": "application/json"}

        mock_activate_response = MagicMock()
        mock_activate_response.status_code = 200
        mock_activate_response.json.return_value = {
            "activated": True,
            "key_id": "test-key-id",
            "message": "Key activated",
        }
        mock_activate_response.headers = {"content-type": "application/json"}

        mock_client = AsyncMock()
        mock_client.post.side_effect = [mock_register_response, mock_activate_response]

        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.device_auth._run_on_large_stack",
            side_effect=mock_run_on_large_stack,
        ):
            with patch(
                "ciris_engine.logic.adapters.api.routes.setup.device_auth._get_public_key_from_verifier",
                return_value=(b"test_public_key_32_bytes_here!!", None),
            ):
                with patch(
                    "ciris_engine.logic.adapters.api.routes.setup.device_auth._sign_with_verifier",
                    return_value=(b"signature_64_bytes_here_abcdefgh" * 2, None),
                ):
                    with patch("httpx.AsyncClient", return_value=mock_client_cm):
                        with caplog.at_level(logging.INFO):
                            result = await _register_self_custody_key("device-code", "https://portal.ciris.ai")

        assert result == "test-key-id"
        assert "Key ACTIVATED" in caplog.text
        # Verify both register-key and activate-key were called
        assert mock_client.post.call_count == 2


class TestSelfCustodySecurityInvariants:
    """Tests ensuring private keys never leave the agent (FSD-002 security)."""

    @pytest.mark.asyncio
    async def test_private_key_never_sent_to_portal(self):
        """Verify that only PUBLIC key is sent to Portal, never private."""
        from ciris_engine.logic.adapters.api.routes.setup.device_auth import _register_self_custody_key

        def mock_run_on_large_stack(func, timeout):
            func()

        captured_requests = []

        async def capture_post(url, json=None):
            captured_requests.append({"url": url, "json": json})
            mock_response = MagicMock()
            if "register-key" in url:
                mock_response.status_code = 200
                mock_response.json.return_value = {
                    "key_id": "test-key-id",
                    "activation_challenge": "0102030405060708",
                    "public_key_fingerprint": "abc123",
                }
            else:
                mock_response.status_code = 200
                mock_response.json.return_value = {"activated": True, "key_id": "test-key-id"}
            mock_response.headers = {"content-type": "application/json"}
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = capture_post

        mock_client_cm = MagicMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cm.__aexit__ = AsyncMock(return_value=None)

        # 32-byte test public key (Ed25519 public keys are 32 bytes)
        test_pubkey = b"public_key_32_bytes_test_here!!!"  # Exactly 32 bytes
        assert len(test_pubkey) == 32, f"Test key must be 32 bytes, got {len(test_pubkey)}"

        with patch(
            "ciris_engine.logic.adapters.api.routes.setup.device_auth._run_on_large_stack",
            side_effect=mock_run_on_large_stack,
        ):
            with patch(
                "ciris_engine.logic.adapters.api.routes.setup.device_auth._get_public_key_from_verifier",
                return_value=(test_pubkey, None),
            ):
                with patch(
                    "ciris_engine.logic.adapters.api.routes.setup.device_auth._sign_with_verifier",
                    return_value=(b"s" * 64, None),  # 64-byte signature
                ):
                    with patch("httpx.AsyncClient", return_value=mock_client_cm):
                        await _register_self_custody_key("device-code", "https://portal.ciris.ai")

        # Verify no private key fields in any request
        for req in captured_requests:
            json_data = req.get("json", {})
            assert "private" not in str(json_data).lower(), "Private key found in request!"
            assert "ed25519_private" not in str(json_data).lower(), "Private key found in request!"

            # Verify only public key is sent
            if "register-key" in req["url"]:
                assert "ed25519_public_key" in json_data
                # Public key should be hex-encoded (32 bytes = 64 hex chars)
                assert (
                    len(json_data["ed25519_public_key"]) == 64
                ), f"Expected 64 hex chars, got {len(json_data['ed25519_public_key'])}"
