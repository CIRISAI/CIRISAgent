"""
Comprehensive test suite for signing_protocol.py.

Tests cover:
- CIRISVerifySigner: signing, verification via CIRISVerify singleton
- UnifiedSigningKey: initialization, singleton behavior, registration
- Error handling with SIGNER_NOT_INITIALIZED constant
- Base64 encoding/decoding utilities

Note: CIRISVerify is the ONLY source of signing keys. These tests mock the
CIRISVerify singleton to test the signing protocol logic without requiring
the actual CIRISVerify Rust library.
"""

import base64
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.audit.signing_protocol import (
    SIGNER_NOT_INITIALIZED,
    CIRISVerifySigner,
    SigningAlgorithm,
    UnifiedSigningKey,
    get_unified_signing_key,
    reset_unified_signing_key,
)

# Patch path for get_verifier - it's imported from verifier_singleton inside the functions
VERIFIER_PATCH_PATH = "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.get_verifier"


class TestSignerNotInitializedConstant:
    """Test the SIGNER_NOT_INITIALIZED constant is used correctly."""

    def test_constant_value(self):
        """Test the constant has expected value."""
        assert SIGNER_NOT_INITIALIZED == "Signer not initialized"

    def test_ciris_verify_signer_key_id_raises_with_constant(self):
        """Test CIRISVerifySigner.key_id raises with the constant message."""
        signer = CIRISVerifySigner()
        # Not initialized, should raise
        with pytest.raises(RuntimeError) as exc_info:
            _ = signer.key_id
        assert SIGNER_NOT_INITIALIZED in str(exc_info.value)

    def test_ciris_verify_signer_public_key_bytes_raises_with_constant(self):
        """Test CIRISVerifySigner.public_key_bytes raises with the constant message."""
        signer = CIRISVerifySigner()
        with pytest.raises(RuntimeError) as exc_info:
            _ = signer.public_key_bytes
        assert SIGNER_NOT_INITIALIZED in str(exc_info.value)

    def test_ciris_verify_signer_sign_raises_with_constant(self):
        """Test CIRISVerifySigner.sign raises with the constant message."""
        signer = CIRISVerifySigner()
        with pytest.raises(RuntimeError) as exc_info:
            signer.sign(b"test data")
        assert SIGNER_NOT_INITIALIZED in str(exc_info.value)


class TestSigningAlgorithm:
    """Test SigningAlgorithm enum."""

    def test_ed25519_value(self):
        """Test ED25519 enum value."""
        assert SigningAlgorithm.ED25519.value == "ed25519"

    def test_rsa_2048_pss_value(self):
        """Test RSA_2048_PSS enum value (legacy)."""
        assert SigningAlgorithm.RSA_2048_PSS.value == "rsa_2048_pss"

    def test_enum_is_string_enum(self):
        """Test SigningAlgorithm is a string enum."""
        assert isinstance(SigningAlgorithm.ED25519, str)
        assert SigningAlgorithm.ED25519 == "ed25519"


class TestCIRISVerifySigner:
    """Test CIRISVerifySigner implementation with mocked CIRISVerify."""

    def test_init_sets_algorithm(self):
        """Test initialization sets correct algorithm."""
        signer = CIRISVerifySigner()
        assert signer._algorithm == SigningAlgorithm.ED25519

    def test_init_client_is_none(self):
        """Test initialization leaves client as None."""
        signer = CIRISVerifySigner()
        assert signer._client is None
        assert signer._public_key_cache is None
        assert signer._key_id is None

    def test_initialize_with_existing_key(self):
        """Test initialize when CIRISVerify has a key."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"x" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            signer = CIRISVerifySigner()
            result = signer.initialize()

            assert result is True
            assert signer._client is mock_client
            assert signer._public_key_cache == b"x" * 32
            assert signer._algo_name == "Ed25519"
            assert signer._key_id.startswith("agent-")

    def test_initialize_without_key_generates_ephemeral(self):
        """Test initialize generates ephemeral key when CIRISVerify has no key."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = False
        mock_client.generate_key_sync.return_value = None  # Generation succeeds
        mock_client.get_ed25519_public_key_sync.return_value = b"e" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            signer = CIRISVerifySigner()
            result = signer.initialize()

            # Now generates ephemeral key instead of returning False
            assert result is True
            assert signer._client is mock_client
            assert signer._public_key_cache == b"e" * 32
            mock_client.generate_key_sync.assert_called_once()

    def test_initialize_without_key_no_generator(self):
        """Test initialize returns False when no key and no generator available."""
        mock_client = MagicMock(spec=["has_key_sync"])  # Only has_key_sync, no generate
        mock_client.has_key_sync.return_value = False

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            signer = CIRISVerifySigner()
            result = signer.initialize()

            assert result is False
            assert signer._client is mock_client
            assert signer._public_key_cache is None

    def test_initialize_no_verifier(self):
        """Test initialize when CIRISVerify singleton not available."""
        with patch(VERIFIER_PATCH_PATH, return_value=None):
            signer = CIRISVerifySigner()
            result = signer.initialize()

            assert result is False
            assert signer._client is None

    def test_sign_calls_client(self):
        """Test sign delegates to CIRISVerify client."""
        mock_client = MagicMock()
        mock_client.sign_ed25519_sync.return_value = b"signature" * 8  # 64 bytes

        signer = CIRISVerifySigner()
        signer._client = mock_client

        signature = signer.sign(b"test data")

        mock_client.sign_ed25519_sync.assert_called_once_with(b"test data")
        assert signature == b"signature" * 8

    def test_sign_fetches_public_key_if_not_cached(self):
        """Test sign fetches public key after signing if not cached."""
        mock_client = MagicMock()
        mock_client.sign_ed25519_sync.return_value = b"x" * 64
        mock_client.get_ed25519_public_key_sync.return_value = b"pubkey" + b"\x00" * 26

        signer = CIRISVerifySigner()
        signer._client = mock_client
        signer._public_key_cache = None

        signer.sign(b"data")

        mock_client.get_ed25519_public_key_sync.assert_called_once()
        assert signer._public_key_cache == b"pubkey" + b"\x00" * 26
        assert signer._key_id is not None

    def test_verify_ed25519_signature(self):
        """Test verify with Ed25519 algorithm."""
        # Generate a real Ed25519 keypair for testing
        from cryptography.hazmat.primitives.asymmetric import ed25519

        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        from cryptography.hazmat.primitives import serialization

        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        data = b"test data to verify"
        signature = private_key.sign(data)

        signer = CIRISVerifySigner()
        signer._public_key_cache = pub_bytes
        signer._algo_name = "Ed25519"

        assert signer.verify(data, signature) is True

    def test_verify_invalid_signature(self):
        """Test verify returns False for invalid signature."""
        from cryptography.hazmat.primitives.asymmetric import ed25519

        private_key = ed25519.Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        from cryptography.hazmat.primitives import serialization

        pub_bytes = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

        signer = CIRISVerifySigner()
        signer._public_key_cache = pub_bytes
        signer._algo_name = "Ed25519"

        # Wrong signature
        assert signer.verify(b"data", b"wrong" * 13) is False

    def test_algorithm_property(self):
        """Test algorithm property returns correct value."""
        signer = CIRISVerifySigner()
        assert signer.algorithm == SigningAlgorithm.ED25519


class TestUnifiedSigningKey:
    """Test UnifiedSigningKey management class."""

    def test_init_default(self):
        """Test initialization with defaults."""
        key = UnifiedSigningKey()
        assert key._signer is None
        assert key._initialized is False

    def test_signer_raises_before_init(self):
        """Test accessing signer before initialization raises."""
        key = UnifiedSigningKey()
        with pytest.raises(RuntimeError) as exc_info:
            _ = key.signer
        assert "UnifiedSigningKey not initialized" in str(exc_info.value)

    def test_has_key_false_before_init(self):
        """Test has_key is False before initialization."""
        key = UnifiedSigningKey()
        assert key.has_key is False

    def test_initialize_requires_ciris_verify(self):
        """Test initialization fails without CIRISVerify."""
        with patch(VERIFIER_PATCH_PATH, return_value=None):
            key = UnifiedSigningKey()
            with pytest.raises(RuntimeError) as exc_info:
                key.initialize()
            assert "CIRISVerify is not available" in str(exc_info.value)

    def test_initialize_with_key_available(self):
        """Test initialization when CIRISVerify has a key."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"x" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.initialize()

            assert key._initialized is True
            assert key._signer is not None
            assert key.has_key is True

    def test_initialize_idempotent(self):
        """Test initialize is idempotent."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"y" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.initialize()
            key_id = key.key_id

            # Second init should not change anything
            key.initialize()
            assert key.key_id == key_id

    def test_properties_delegate_to_signer(self):
        """Test properties delegate to underlying signer."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"z" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.initialize()

            assert key.key_id == key.signer.key_id
            assert key.public_key_bytes == key.signer.public_key_bytes
            assert key.public_key_base64 == key.signer.public_key_base64
            assert key.algorithm == SigningAlgorithm.ED25519

    def test_sign_delegates_to_signer(self):
        """Test sign delegates to signer."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"a" * 32
        mock_client.sign_ed25519_sync.return_value = b"sig" * 22  # ~64 bytes

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.initialize()

            signature = key.sign(b"test data")
            assert signature == b"sig" * 22

    def test_sign_base64(self):
        """Test sign_base64 produces URL-safe base64."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"b" * 32
        mock_client.sign_ed25519_sync.return_value = b"x" * 64

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.initialize()

            sig_b64 = key.sign_base64(b"base64 test")

            # Should be URL-safe base64 without padding
            assert "+" not in sig_b64
            assert "/" not in sig_b64
            assert not sig_b64.endswith("=")

    def test_get_registration_payload(self):
        """Test registration payload for CIRISLens."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"c" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.initialize()

            payload = key.get_registration_payload("test description")

            assert payload["key_id"] == key.key_id
            assert payload["public_key_base64"] == key.public_key_base64
            assert payload["algorithm"] == "ed25519"
            assert payload["description"] == "test description"

    def test_load_provisioned_key_deprecated(self):
        """Test load_provisioned_key raises NotImplementedError (FSD-002 Self-Custody)."""
        mock_client = MagicMock()
        mock_client.get_ed25519_public_key_sync.return_value = b"d" * 32

        # Create a valid 32-byte key
        test_key = b"e" * 32
        test_key_b64 = base64.b64encode(test_key).decode()

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            # FSD-002: Portal no longer issues private keys, agents generate their own
            with pytest.raises(NotImplementedError, match="DEPRECATED"):
                key.load_provisioned_key(test_key_b64)


class TestGlobalSigningKey:
    """Test global singleton functions."""

    def setup_method(self):
        """Reset global state before each test."""
        reset_unified_signing_key()

    def teardown_method(self):
        """Reset global state after each test."""
        reset_unified_signing_key()

    def test_get_unified_signing_key_creates_instance(self):
        """Test get_unified_signing_key creates and initializes instance."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"f" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = get_unified_signing_key()

            assert key is not None
            assert key._initialized is True
            assert key.key_id.startswith("agent-")

    def test_get_unified_signing_key_returns_same_instance(self):
        """Test get_unified_signing_key returns singleton."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"g" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key1 = get_unified_signing_key()
            key2 = get_unified_signing_key()

            assert key1 is key2

    def test_reset_unified_signing_key(self):
        """Test reset_unified_signing_key clears the singleton."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"h" * 32

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key1 = get_unified_signing_key()

            reset_unified_signing_key()

            # New call should create new instance
            key2 = get_unified_signing_key()
            assert key2 is not key1


class TestBaseSigner:
    """Test BaseSigner abstract class behavior via CIRISVerifySigner."""

    def test_compute_key_id_format(self):
        """Test _compute_key_id produces correct format."""
        signer = CIRISVerifySigner()
        # Use known bytes to get deterministic result
        test_bytes = b"test public key bytes for hashing"
        key_id = signer._compute_key_id(test_bytes)

        assert key_id.startswith("agent-")
        # Hash part should be 12 hex chars
        hex_part = key_id[6:]
        assert len(hex_part) == 12
        # Should be valid hex
        int(hex_part, 16)

    def test_compute_key_id_deterministic(self):
        """Test _compute_key_id is deterministic."""
        signer = CIRISVerifySigner()
        test_bytes = b"same bytes"

        id1 = signer._compute_key_id(test_bytes)
        id2 = signer._compute_key_id(test_bytes)

        assert id1 == id2

    def test_compute_key_id_different_for_different_bytes(self):
        """Test _compute_key_id produces different IDs for different inputs."""
        signer = CIRISVerifySigner()

        id1 = signer._compute_key_id(b"bytes one")
        id2 = signer._compute_key_id(b"bytes two")

        assert id1 != id2


class TestKeyRegistrationCallback:
    """Test key registration callback mechanism for audit_signing_keys sync."""

    def test_set_key_registration_callback(self):
        """Test callback can be set."""
        key = UnifiedSigningKey()
        callback = MagicMock()

        key.set_key_registration_callback(callback)

        assert key._on_key_registered is callback

    def test_callback_not_called_without_signer(self):
        """Test callback is not called when no signer is present."""
        key = UnifiedSigningKey()
        callback = MagicMock()

        key.set_key_registration_callback(callback)
        key._notify_key_registered()

        callback.assert_not_called()

    def test_portal_key_import_deprecated(self):
        """Test Portal key import raises NotImplementedError (FSD-002 Self-Custody)."""
        mock_client = MagicMock()
        mock_client.get_ed25519_public_key_sync.return_value = b"x" * 32

        callback = MagicMock()
        test_key = b"y" * 32
        test_key_b64 = base64.b64encode(test_key).decode()

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.set_key_registration_callback(callback)
            # FSD-002: Portal no longer issues private keys
            with pytest.raises(NotImplementedError, match="DEPRECATED"):
                key.load_provisioned_key(test_key_b64)

    def test_callback_called_on_ephemeral_key_creation(self):
        """Test callback is called when ephemeral key is created during initialize."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = False  # No key initially
        mock_client.generate_key_sync.return_value = None  # Generation succeeds
        mock_client.get_ed25519_public_key_sync.return_value = b"p" * 32

        callback = MagicMock()

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.set_key_registration_callback(callback)
            key.initialize()  # Now generates ephemeral key during initialize

            # Callback should be triggered during initialize when key is generated
            callback.assert_called_once()
            call_kwargs = callback.call_args.kwargs
            assert call_kwargs["key_id"].startswith("agent-")
            assert call_kwargs["algorithm"] == "ed25519"

    def test_callback_not_called_when_signing_with_existing_key(self):
        """Test callback is not called when signing with existing key."""
        mock_client = MagicMock()
        mock_client.has_key_sync.return_value = True
        mock_client.get_ed25519_public_key_sync.return_value = b"q" * 32
        mock_client.sign_ed25519_sync.return_value = b"r" * 64

        callback = MagicMock()

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.initialize()
            key.set_key_registration_callback(callback)

            # Sign should NOT trigger callback since key already exists
            key.sign(b"test data")

            callback.assert_not_called()

    def test_callback_exception_on_deprecated_method(self):
        """Test load_provisioned_key raises NotImplementedError (FSD-002 Self-Custody)."""
        mock_client = MagicMock()
        mock_client.get_ed25519_public_key_sync.return_value = b"t" * 32

        def failing_callback(**kwargs):
            raise RuntimeError("DB connection failed")

        test_key_b64 = base64.b64encode(b"u" * 32).decode()

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            key = UnifiedSigningKey()
            key.set_key_registration_callback(failing_callback)

            # FSD-002: Portal no longer issues private keys
            with pytest.raises(NotImplementedError, match="DEPRECATED"):
                key.load_provisioned_key(test_key_b64)


class TestHardwareKeyRecovery:
    """Test recovery from deleted/corrupted hardware keys (CIRISVerify v1.6.3+).

    When hardware keys are deleted or corrupted, CIRISVerify v1.6.3+ returns
    a clear error message and auto-clears the stale hardware marker.
    The signing protocol should detect this and regenerate the key.

    Note: Tests that involve key regeneration failures must also patch
    reset_verifier and the local get_verifier call in _try_generate_key_with_retry,
    otherwise the real CIRISVerify library will be invoked.
    """

    # Paths for patching - must patch at the source module since imports happen inside function
    RESET_VERIFIER_PATH = "ciris_engine.logic.services.infrastructure.authentication.verifier_singleton.reset_verifier"

    def test_initialize_recovers_from_deleted_corrupted_key(self):
        """Test initialize regenerates key when 'deleted or corrupted' error occurs."""
        mock_client = MagicMock()

        # First has_key call raises the new v1.6.3 error
        call_count = [0]

        def has_key_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Hardware key was deleted or corrupted. Please create a new signing key.")
            return True  # After regeneration, key exists

        mock_client.has_key_sync.side_effect = has_key_side_effect
        mock_client.generate_key_sync.return_value = None  # Generation succeeds
        mock_client.get_ed25519_public_key_sync.return_value = b"recovered" + b"\x00" * 24

        with patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            signer = CIRISVerifySigner()
            result = signer.initialize()

            # Should have recovered and initialized successfully
            assert result is True
            assert signer._public_key_cache is not None
            mock_client.generate_key_sync.assert_called()

    def test_initialize_fails_if_regeneration_fails(self):
        """Test initialize returns False if key regeneration fails after 'deleted or corrupted'."""
        mock_client = MagicMock()

        # has_key raises the error
        mock_client.has_key_sync.side_effect = RuntimeError(
            "Hardware key was deleted or corrupted. Please create a new signing key."
        )
        # generate_key also fails
        mock_client.generate_key_sync.side_effect = RuntimeError("Keystore unavailable")

        # Must also patch reset_verifier to prevent real lib init during retry
        with (
            patch(VERIFIER_PATCH_PATH, return_value=mock_client),
            patch(self.RESET_VERIFIER_PATH),
        ):
            signer = CIRISVerifySigner()
            result = signer.initialize()

            # Should fail gracefully
            assert result is False

    def test_sign_recovers_from_deleted_corrupted_key(self):
        """Test sign regenerates key and retries when 'deleted or corrupted' error occurs."""
        mock_client = MagicMock()

        # First sign call fails with v1.6.3 error, second succeeds
        call_count = [0]

        def sign_side_effect(data):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Hardware key was deleted or corrupted. Please create a new signing key.")
            return b"recovered_signature" + b"\x00" * 45  # ~64 bytes

        mock_client.sign_ed25519_sync.side_effect = sign_side_effect
        mock_client.generate_key_sync.return_value = None  # Generation succeeds
        mock_client.get_ed25519_public_key_sync.return_value = b"newkey" + b"\x00" * 26

        signer = CIRISVerifySigner()
        signer._client = mock_client
        signer._public_key_cache = b"oldkey" + b"\x00" * 26  # Pre-existing cached key

        # Sign should recover and return signature
        signature = signer.sign(b"test data")

        assert signature == b"recovered_signature" + b"\x00" * 45
        mock_client.generate_key_sync.assert_called()
        # Public key should be updated
        assert signer._public_key_cache == b"newkey" + b"\x00" * 26

    def test_sign_raises_if_recovery_fails(self):
        """Test sign raises RuntimeError if recovery fails after 'deleted or corrupted'."""
        mock_client = MagicMock()

        # Sign always fails
        mock_client.sign_ed25519_sync.side_effect = RuntimeError(
            "Hardware key was deleted or corrupted. Please create a new signing key."
        )
        # generate_key fails too
        mock_client.generate_key_sync.side_effect = RuntimeError("TPM unavailable")

        signer = CIRISVerifySigner()
        signer._client = mock_client

        # Must patch reset_verifier to prevent real lib init during retry
        with patch(self.RESET_VERIFIER_PATH), patch(VERIFIER_PATCH_PATH, return_value=mock_client):
            with pytest.raises(RuntimeError) as exc_info:
                signer.sign(b"test data")

            assert "CIRISVerify signing failed" in str(exc_info.value)

    def test_sign_raises_if_retry_after_regeneration_fails(self):
        """Test sign raises if signing fails even after successful key regeneration."""
        mock_client = MagicMock()

        # Both sign attempts fail
        mock_client.sign_ed25519_sync.side_effect = RuntimeError(
            "Hardware key was deleted or corrupted. Please create a new signing key."
        )
        # But key generation succeeds
        mock_client.generate_key_sync.return_value = None
        mock_client.get_ed25519_public_key_sync.return_value = b"x" * 32

        signer = CIRISVerifySigner()
        signer._client = mock_client

        with pytest.raises(RuntimeError) as exc_info:
            signer.sign(b"test data")

        assert "after key regeneration" in str(exc_info.value)

    def test_other_errors_not_treated_as_deleted_corrupted(self):
        """Test that other signing errors don't trigger recovery flow."""
        mock_client = MagicMock()

        # Different error message - not related to deleted/corrupted
        mock_client.sign_ed25519_sync.side_effect = RuntimeError("TPM communication timeout")

        signer = CIRISVerifySigner()
        signer._client = mock_client

        with pytest.raises(RuntimeError) as exc_info:
            signer.sign(b"test data")

        # Should fail without attempting regeneration
        assert "CIRISVerify signing failed" in str(exc_info.value)
        mock_client.generate_key_sync.assert_not_called()
